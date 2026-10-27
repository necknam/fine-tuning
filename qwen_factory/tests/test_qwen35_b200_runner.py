import copy,hashlib,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import yaml
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import qwen35_b200_runner as r

class FakeTokenizer:
 def apply_chat_template(self,messages,*,add_generation_prompt,**kwargs):
  tokens=[]
  for m in messages:tokens += [1 if m['role']=='user' else 2,*[ord(x) for x in m['content']],3]
  return tokens+[2] if add_generation_prompt else tokens

class Qwen35B200Tests(unittest.TestCase):
 def cfg(self):return yaml.safe_load((ROOT/'configs/hyperparameters.qwen35_4b_3000.P01.yaml').read_text(encoding='utf-8'))
 def fixture(self,d):
  root=Path(d);cfg=self.cfg()
  def put(relative,value,rows=False):
   p=root/relative;p.parent.mkdir(parents=True,exist_ok=True)
   p.write_text(''.join(json.dumps(x)+'\n' for x in value) if rows else json.dumps(value),encoding='utf-8')
   return p
  rows=[{'messages':[{'role':'user','content':json.dumps({'case':i})},{'role':'assistant','content':'answer '+str(i)}]} for i in range(3000)]
  original=put(cfg['data']['original_file'],rows[:1500],True)
  data=put(cfg['data']['train_file'],rows,True)
  ev=put(cfg['evaluation']['file'],[{'messages':[{'role':'user','content':json.dumps({'eval':i})}]} for i in range(10)],True)
  cfg['evaluation']['sha256']=r.digest(ev)
  def artifact(name,value,lines=False):
   p=put('data/production/expanded_3000/'+name,value,lines);return {'path':str(p.relative_to(root)),'sha256':r.digest(p)}
  cycles=[]
  for n in range(1,6):
   cycle={'round':n,'new_records':300,'status':'REVIEW_COMPLETE','reviewed_sample_count':10}
   for role in ('maker','reviewer','inspector'):cycle[role]=artifact(f'{role}{n}.json',{'review':'actual fixture'})
   cycles.append(cycle)
  release={'status':'REVIEWED_CANDIDATE','blocking_findings':0,'records':3000,'data_sha256':r.digest(data),'original_sha256':r.digest(original),'rounds':cycles,'automatic_checks':artifact('checks.json',{'status':'PASS','checked_records':3000}),'provenance':artifact('provenance.jsonl',[{'id':i} for i in range(1500)],True)}
  put(cfg['data']['release_manifest'],release)
  return root,cfg,release,r.digest(original),r.digest(ev)
 def test_p01_rejects_wrong_model_lr_and_quantization(self):
  for field,value in [('model',{'base_model_id':'Qwen/Qwen3.8-27B','revision':r.REVISION}),('quantization',{'load_in_4bit':True,'dtype':'bfloat16'})]:
   cfg=self.cfg();cfg[field]=value
   with self.assertRaises(ValueError):r.validate_config(cfg)
  cfg=self.cfg();cfg['training']['learning_rate']=.0002
  with self.assertRaises(ValueError):r.validate_config(cfg)
 def test_p01_through_p06_configs_pass_validation(self):
  for pid in ('P01','P02','P03','P04','P05','P06','P07','P50','P111'):
   path=ROOT/f'configs/hyperparameters.qwen35_4b_3000.{pid}.yaml'
   self.assertTrue(path.is_file(),f'{pid} config missing')
   cfg=yaml.safe_load(path.read_text(encoding='utf-8'))
   r.validate_config(cfg)
 def test_loss_mask_and_no_truncation(self):
  rows=[{'messages':[{'role':'user','content':'q'},{'role':'assistant','content':'a'}]}]
  encoded=r.encode(rows,FakeTokenizer(),100)
  self.assertEqual(encoded[0]['labels'],[-100]*4+[ord('a'),3])
  with self.assertRaisesRegex(ValueError,'no truncation'):r.encode(rows,FakeTokenizer(),3)
  class Broken(FakeTokenizer):
   def apply_chat_template(self,messages,**kw):return [999] if kw['add_generation_prompt'] else super().apply_chat_template(messages,**kw)
  with self.assertRaisesRegex(ValueError,'prefix mismatch'):r.encode(rows,Broken(),100)
 def test_probe_covers_full_length_range_and_excludes_compile_partial(self):
  ids=r.sample_indices([{'input_ids':[0]*i} for i in range(1,3001)])
  self.assertEqual(len(set(ids)),60);self.assertEqual((ids[0],ids[-1]),(0,2999))
  self.assertEqual(r.steady_step_mean([100,2,4,1],60),3)
 def test_missing_review_blocks_without_importing_gpu(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaisesRegex(ValueError,'release manifest missing'):r.validate_release(Path(d),self.cfg())
  self.assertNotIn('torch',sys.modules)
 def test_release_preserves_original_and_binds_review_hashes(self):
  with tempfile.TemporaryDirectory() as d:
   root,cfg,release,original,ev=self.fixture(d)
   with patch.object(r,'ORIGINAL_SHA',original),patch.object(r,'EVAL_SHA',ev):
    rows,contract=r.validate_release(root,cfg);self.assertEqual(len(rows),3000)
    p=root/release['rounds'][0]['reviewer']['path'];p.write_text('edited',encoding='utf-8')
    with self.assertRaisesRegex(ValueError,'hash mismatch'):r.validate_release(root,cfg)
 def test_unfinished_round_and_duplicate_new_input_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root,cfg,release,original,ev=self.fixture(d)
   with patch.object(r,'ORIGINAL_SHA',original),patch.object(r,'EVAL_SHA',ev):
    release['rounds'][4]['status']='PENDING'
    (root/cfg['data']['release_manifest']).write_text(json.dumps(release),encoding='utf-8')
    with self.assertRaisesRegex(ValueError,'Incomplete'):r.validate_release(root,cfg)
    release['rounds'][4]['status']='REVIEW_COMPLETE'
    p=root/cfg['data']['train_file'];rows=r.read_rows(p);rows[-1]=rows[0];p.write_text(''.join(json.dumps(x)+'\n' for x in rows),encoding='utf-8');release['data_sha256']=r.digest(p)
    (root/cfg['data']['release_manifest']).write_text(json.dumps(release),encoding='utf-8')
    with self.assertRaisesRegex(ValueError,'Duplicate new'):r.validate_release(root,cfg)
 def test_probe_must_match_runtime_and_dataset_and_memory(self):
  contract={'hash':'x'};runtime={'gpu':'B200'}
  good={'status':'PASS','contract':contract,'runtime':runtime,'records':60,'steps':4,'finite_loss':True,'peak_memory_fraction':.4,'steady_step_mean_seconds':2}
  r.validate_probe(good,contract,runtime)
  for change in ({'runtime':{'gpu':'A100'}},{'contract':{'hash':'y'}},{'peak_memory_fraction':.95},{'finite_loss':False}):
   with self.assertRaises(ValueError):r.validate_probe(good|change,contract,runtime)

if __name__=='__main__':unittest.main()
