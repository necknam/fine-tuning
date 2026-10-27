"""B200 P01 / Qwen3.5-4B: reviewed 3000 -> independent 60-row probe -> fresh training.

Preview is local/CPU-only. --execute is required for GPU or public model download.
No registry, mail, paid grader, model upload or Pod management is performed here.
"""
import argparse,contextlib,hashlib,importlib.metadata,json,math,os,platform,re,sys,time
from pathlib import Path
import yaml

MODEL='Qwen/Qwen3.5-4B'
REVISION='851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a'
ORIGINAL_SHA='998a9499a14f6c08de0526919567bcf5a9fcf31642f75aa24fca143c51265529'
EVAL_SHA='d0e1b2d687063250aadeed1b7735dafaaa5d9fce25a82566b79dffbe30b050ac'
ROOT=Path(__file__).resolve().parents[1]

def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(2**20),b''):h.update(chunk)
 return h.hexdigest()

def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def identity(cfg):return hashlib.sha256(canonical(cfg).encode()).hexdigest()
def read_rows(path):return [json.loads(l) for l in Path(path).read_text(encoding='utf-8-sig').splitlines() if l.strip()]
def atomic(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');tmp.replace(path)

def inside(root,relative):
 path=(Path(root)/relative).resolve();path.relative_to(Path(root).resolve());return path

PRESETS={
 'P01':{'learning_rate':0.0001,'r':32,'lora_alpha':64},
 'P02':{'learning_rate':0.00005,'r':32,'lora_alpha':64},
 'P03':{'learning_rate':0.000075,'r':32,'lora_alpha':64},
 'P04':{'learning_rate':0.00015,'r':32,'lora_alpha':64},
 'P05':{'learning_rate':0.0001,'r':16,'lora_alpha':32},
 'P06':{'learning_rate':0.0001,'r':64,'lora_alpha':128},
}

def validate_config(cfg):
 preset=cfg.get('preset')
 if preset not in PRESETS:raise ValueError(f'Unsupported preset {preset}; P01..P06 supported')
 if cfg.get('profile')!=f'qwen35_4b_b200_3000_{preset.lower()}_v1':raise ValueError('Wrong profile')
 if cfg['model']!={'base_model_id':MODEL,'revision':REVISION}:raise ValueError('Pinned Qwen3.5-4B required')
 if cfg.get('hardware')!='B200':raise ValueError('B200 required')
 if cfg['quantization']!={'load_in_4bit':False,'dtype':'bfloat16'}:raise ValueError('BF16 LoRA without base quantization required')
 p_spec=PRESETS[preset]
 expected={'learning_rate':p_spec['learning_rate'],'num_train_epochs':5,'per_device_train_batch_size':1,
  'gradient_accumulation_steps':16,'max_length':7168,'packing':False,'bf16':True,
  'gradient_checkpointing':True,'loss_policy':'final_assistant_only','seed':42,
  'data_seed':42,'warmup_ratio':0.05,'lr_scheduler_type':'cosine','weight_decay':0.01,
  'optim':'paged_adamw_8bit'}
 if cfg['training']!=expected:raise ValueError(f'{preset} training contract changed; use a new reviewed profile')
 expected_lora={'r':p_spec['r'],'lora_alpha':p_spec['lora_alpha'],'lora_dropout':0.05,'bias':'none','scope':'language_model/all-linear'}
 if cfg['lora']!=expected_lora:raise ValueError(f'{preset} LoRA scope changed')
 if cfg['save_epochs']!=[2,5] or cfg['sample']!={'records':60,'epochs':1,'maximum_memory_fraction':0.95}:raise ValueError('Probe/save plan changed')
 if cfg['data']['expected_records']!=3000 or cfg['evaluation']['sha256']!=EVAL_SHA:raise ValueError('Data/evaluation contract changed')
 if cfg['inference']!={'max_new_tokens':4096,'do_sample':False,'enable_thinking':False}:raise ValueError('Comparison settings changed')

def checked_artifact(root,item):
 p=inside(root,item['path'])
 if not p.is_file() or digest(p)!=item.get('sha256'):raise ValueError('Review artifact missing or hash mismatch: '+item['path'])
 return p

def validate_release(root,cfg):
 """No fabricated ready flags: all five role-review artifacts must exist and match."""
 validate_config(cfg)
 release_path=inside(root,cfg['data']['release_manifest'])
 if not release_path.is_file():raise ValueError('3000-row release manifest missing; production is blocked')
 release=json.loads(release_path.read_text(encoding='utf-8'))
 if release.get('status')!='REVIEWED_CANDIDATE' or release.get('blocking_findings')!=0:raise ValueError('Dataset review is incomplete or blocked')
 if release.get('original_sha256')!=ORIGINAL_SHA or release.get('records')!=3000:raise ValueError('Original data/count mismatch')
 data=inside(root,cfg['data']['train_file'])
 if not data.is_file() or digest(data)!=release.get('data_sha256'):raise ValueError('Dataset SHA mismatch')
 original=inside(root,cfg['data']['original_file'])
 if digest(original)!=ORIGINAL_SHA:raise ValueError('Original 1500 changed')
 rows=read_rows(data)
 if len(rows)!=3000 or rows[:1500]!=read_rows(original):raise ValueError('Exactly 3000 rows with original 1500 preserved required')
 rounds=release.get('rounds',[])
 if len(rounds)!=5 or [x.get('round') for x in rounds]!=list(range(1,6)):raise ValueError('Five ordered review cycles required')
 for cycle in rounds:
  if cycle.get('new_records')!=300 or cycle.get('status')!='REVIEW_COMPLETE':raise ValueError('Incomplete 300-row review cycle')
  if not cycle.get('reviewed_sample_count',0)>0:raise ValueError('Actual content review sample required')
  for role in ('maker','reviewer','inspector'):checked_artifact(root,cycle[role])
 checks=json.loads(checked_artifact(root,release['automatic_checks']).read_text(encoding='utf-8'))
 if checks.get('status')!='PASS' or checks.get('checked_records')!=3000:raise ValueError('Full automatic checks not passed')
 provenance=read_rows(checked_artifact(root,release['provenance']))
 if len(provenance)!=1500:raise ValueError('New 1500 provenance rows required')
 ev=inside(root,cfg['evaluation']['file'])
 if digest(ev)!=EVAL_SHA or len(read_rows(ev))!=10:raise ValueError('Fixed ten inputs changed')
 # Exact evaluation user leakage and duplicate new user/answer pairs.
 prompts=set();answers=set()
 for n,row in enumerate(rows):
  m=row.get('messages',[])
  if len(m)<2 or m[-1].get('role')!='assistant' or m[-2].get('role')!='user':raise ValueError('Final user/assistant pair required')
  if any(not isinstance(x.get('content'),str) or not x['content'].strip() for x in m):raise ValueError('Empty/non-text message')
  u=canonical(json.loads(m[-2]['content']));a=m[-1]['content'].strip()
  if n>=1500 and (u in prompts or a in answers):raise ValueError('Duplicate new user or answer')
  prompts.add(u);answers.add(a)
 for row in read_rows(ev):
  m=row['messages'];m=m[:-1] if m[-1]['role']=='assistant' else m
  try:u=canonical(json.loads(m[-1]['content']))
  except json.JSONDecodeError:u=m[-1]['content']
  if u in prompts:raise ValueError('Fixed evaluation input leaked into training')
 return rows,{'data_sha256':release['data_sha256'],'release_sha256':digest(release_path),'evaluation_sha256':EVAL_SHA,'config_sha256':identity(cfg),'runner_sha256':digest(Path(__file__))}

def encode(rows,tok,limit):
 result=[]
 for n,row in enumerate(rows,1):
  m=row['messages']
  ids=tok.apply_chat_template(m,tokenize=True,enable_thinking=False,add_generation_prompt=False,return_dict=False)
  prefix=tok.apply_chat_template(m[:-1],tokenize=True,enable_thinking=False,add_generation_prompt=True,return_dict=False)
  if not isinstance(ids,list) or not all(type(x)is int for x in ids):raise ValueError('Unexpected tokenizer output')
  if len(ids)>limit:raise ValueError(f'Row {n}: {len(ids)} > {limit}; no truncation performed')
  if not prefix or len(prefix)>=len(ids) or ids[:len(prefix)]!=prefix:raise ValueError(f'Row {n}: assistant mask prefix mismatch')
  result.append({'input_ids':ids,'attention_mask':[1]*len(ids),'labels':[-100]*len(prefix)+ids[len(prefix):]})
 return result

def sample_indices(encoded,count=60):
 if len(encoded)<count:raise ValueError('Too few rows')
 order=sorted(range(len(encoded)),key=lambda i:(len(encoded[i]['input_ids']),i))
 return [order[round(i*(len(order)-1)/(count-1))] for i in range(count)]

def steady_step_mean(times,records,batch=1,accumulation=16):
 # First compile/update and partial final update are excluded in each epoch.
 per_epoch=math.ceil(records/(batch*accumulation))
 good=[v for i,v in enumerate(times) if i!=0 and not (records%(batch*accumulation) and (i+1)%per_epoch==0)]
 return sum(good)/len(good) if good else None

def verify_files(folder,manifest):
 for name,sha in manifest['files'].items():
  if Path(name).name!=name or digest(Path(folder)/name)!=sha:raise ValueError('Saved artifact hash mismatch')

def validate_probe(receipt,contract,runtime):
 if receipt.get('status')!='PASS' or receipt.get('contract')!=contract or receipt.get('runtime')!=runtime:raise ValueError('Matching successful B200/4B/3000 probe required')
 if receipt.get('records')!=60 or receipt.get('steps')!=4 or not receipt.get('finite_loss'):raise ValueError('Probe result incomplete')
 fraction=receipt.get('peak_memory_fraction',1)
 if not 0<fraction<0.95:raise ValueError('Probe memory exceeds 95%')
 if not receipt.get('steady_step_mean_seconds',0)>0:raise ValueError('Probe steady-step measurement missing')

@contextlib.contextmanager
def gpu_guard(root):
 import fcntl,subprocess
 p=Path(root)/'outputs/control_jobs/gpu.lock';p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('a') as f:
  try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise ValueError('Another GPU job holds the shared lock') from None
  active=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True)
  if any(s.strip().isdigit() and int(s.strip())!=os.getpid() for s in active.splitlines()):raise ValueError('Another GPU compute process exists; no duplicate start')
  yield

def runtime_info(cfg):
 import torch
 if platform.system()!='Linux' or not torch.cuda.is_available() or torch.cuda.device_count()!=1:raise ValueError('One Linux CUDA B200 required')
 gpu=torch.cuda.get_device_properties(0)
 if 'B200' not in gpu.name or torch.cuda.get_device_capability(0)!=(10,0) or not torch.cuda.is_bf16_supported():raise ValueError('B200 sm100 BF16 required')
 if not torch.version.cuda or tuple(map(int,torch.version.cuda.split('.')[:2]))<(12,8):raise ValueError('CUDA 12.8+ required')
 expected=cfg['runtime']['packages'];versions={p:importlib.metadata.version(p) for p in expected}
 for p,want in expected.items():
  if versions[p].split('+')[0]!=want:raise ValueError('Pinned runtime version mismatch: '+p)
 return {'packages':versions,'gpu':gpu.name,'compute_capability':[10,0],'total_memory_bytes':gpu.total_memory,'cuda':torch.version.cuda}

def load_model(cfg,staged):
 import torch
 from transformers import AutoModelForImageTextToText
 from peft import LoraConfig,get_peft_model
 model=AutoModelForImageTextToText.from_pretrained(staged,local_files_only=True,trust_remote_code=False,dtype=torch.bfloat16,device_map={'':0},attn_implementation='sdpa')
 tc=model.config.text_config
 if model.config.model_type!='qwen3_5' or tc.hidden_size!=2560 or tc.num_hidden_layers!=32:raise ValueError('Loaded architecture is not pinned Qwen3.5-4B')
 model.config.use_cache=False;tc.use_cache=False;model.requires_grad_(False)
 if getattr(model,'is_loaded_in_4bit',False):raise ValueError('Unexpected base quantization')
 model.enable_input_require_grads()
 targets=[n for n,m in model.named_modules() if 'language_model' in n.split('.') and isinstance(m,torch.nn.Linear) and not n.endswith('lm_head')]
 if not targets:raise ValueError('No language-model LoRA targets')
 hp=cfg['lora'];model=get_peft_model(model,LoraConfig(r=hp['r'],lora_alpha=hp['lora_alpha'],lora_dropout=hp['lora_dropout'],bias='none',target_modules=targets,task_type='CAUSAL_LM'))
 trainable=[n for n,p in model.named_parameters() if p.requires_grad]
 if not trainable or any('lora_' not in n or 'language_model' not in n.split('.') for n in trainable):raise ValueError('Trainable parameters outside language LoRA')
 return model,targets

def train(root,cfg,encoded,tok,staged,contract,runtime,folder,sample=False,resume=False):
 import torch
 from transformers import Trainer,TrainerCallback,TrainingArguments,set_seed
 from transformers.trainer_utils import get_last_checkpoint
 from safetensors import safe_open
 set_seed(42)
 selection=sample_indices(encoded) if sample else list(range(len(encoded)))
 data=[encoded[i] for i in selection];epochs=1 if sample else cfg['training']['num_train_epochs']
 expected_steps=math.ceil(len(data)/16)*epochs
 expected={'contract':contract,'runtime':runtime,'sample':sample,'runner_sha256':digest(Path(__file__))}
 old=folder/'execution.json';checkpoint=None
 if folder.exists():
  if not old.is_file() or json.loads(old.read_text())!=expected:raise ValueError('Existing run identity differs; preserved')
  done=folder/'result.json'
  if done.exists():
   result=json.loads(done.read_text());verify_files(folder/'adapter',result)
   if result.get('status')!='PASS':raise ValueError('Existing result is not PASS')
   return result
  if not resume:raise ValueError('Incomplete run exists; inspect and explicitly use --resume')
  checkpoint=get_last_checkpoint(str(folder/'checkpoints'))
  if not checkpoint or any(not (Path(checkpoint)/n).is_file() for n in ['trainer_state.json','optimizer.pt','scheduler.pt','rng_state.pth']):raise ValueError('Complete optimizer/scheduler/RNG checkpoint required')
 else:
  if resume:raise ValueError('No existing run to resume')
  folder.mkdir(parents=True);atomic(old,expected)
 model,targets=load_model(cfg,staged);atomic(folder/'lora_targets.json',targets)
 model.peft_config['default'].base_model_name_or_path=MODEL;model.peft_config['default'].revision=REVISION
 times=[];losses=[];start=time.perf_counter();torch.cuda.reset_peak_memory_stats()
 def status(stage,**kw):atomic(folder/'status.json',{'stage':stage,'contract':contract,'updated_at':time.time(),**kw})
 def collate(batch):
  length=max(len(x['input_ids']) for x in batch)
  return {k:torch.tensor([x[k]+[pad]*(length-len(x[k])) for x in batch]) for k,pad in [('input_ids',tok.pad_token_id),('attention_mask',0),('labels',-100)]}
 class Monitor(TrainerCallback):
  def on_step_begin(self,args,state,control,**kwargs):torch.cuda.synchronize();self.started=time.perf_counter()
  def on_step_end(self,args,state,control,**kwargs):
   torch.cuda.synchronize();times.append(time.perf_counter()-self.started)
   mean=steady_step_mean(times,len(data))
   status('training',step=state.global_step,total_steps=state.max_steps,epoch=state.epoch,training_elapsed_seconds=time.perf_counter()-start,steady_step_mean_seconds=mean,remaining_training_estimate_seconds=(state.max_steps-state.global_step)*mean if mean else None,save_and_comparison_excluded=True)
  def on_log(self,args,state,control,logs=None,**kwargs):
   if logs and 'loss' in logs:
    if not math.isfinite(logs['loss']):raise ValueError('Nonfinite training loss')
    losses.append(logs['loss'])
  def on_save(self,args,state,control,**kwargs):
   epoch=round(state.epoch or 0)
   if not sample and abs((state.epoch or 0)-epoch)<1e-5 and epoch in cfg['save_epochs']:
    out=folder/f'epoch{epoch}'/'adapter'
    if out.exists():
     prior=json.loads((out/'snapshot.json').read_text())
     if prior.get('contract')!=contract or prior.get('epoch')!=epoch or prior.get('step')!=state.global_step:raise ValueError('Existing epoch adapter identity differs')
     verify_files(out,prior)
     return
    model.save_pretrained(out);tok.save_pretrained(out)
    files={p.name:digest(p) for p in out.iterdir() if p.is_file()}
    atomic(out/'snapshot.json',{'contract':contract,'epoch':epoch,'step':state.global_step,'files':files})
    verify_files(out,{'files':files})
 t=cfg['training']
 args=TrainingArguments(output_dir=str(folder/'checkpoints'),num_train_epochs=epochs,per_device_train_batch_size=1,gradient_accumulation_steps=16,per_device_eval_batch_size=1,learning_rate=t['learning_rate'],lr_scheduler_type='cosine',warmup_steps=math.ceil(expected_steps*.05),weight_decay=.01,bf16=True,gradient_checkpointing=True,gradient_checkpointing_kwargs={'use_reentrant':False},optim=t['optim'],logging_steps=1,logging_nan_inf_filter=False,eval_strategy='no',save_strategy='epoch',save_total_limit=3,save_only_model=False,report_to='none',seed=42,data_seed=42,remove_unused_columns=False,dataloader_num_workers=0,disable_tqdm=True)
 trainer=Trainer(model=model,args=args,train_dataset=data,processing_class=tok,data_collator=collate,callbacks=[Monitor()])
 status('starting',step=0,total_steps=expected_steps)
 metrics=trainer.train(resume_from_checkpoint=checkpoint).metrics
 if not math.isfinite(metrics['train_loss']) or trainer.state.global_step!=expected_steps or not math.isclose(trainer.state.epoch,epochs,abs_tol=1e-5):raise ValueError('Training completion verification failed')
 fraction=torch.cuda.max_memory_reserved()/runtime['total_memory_bytes']
 if sample and fraction>=.95:raise ValueError('Sample exceeds 95% memory; full training blocked')
 out=folder/'adapter';trainer.save_model(out);tok.save_pretrained(out);trainer.save_state()
 with safe_open(out/'adapter_model.safetensors',framework='pt',device='cpu') as f:
  if not f.keys():raise ValueError('Empty adapter')
  for key in f.keys():
   if not torch.isfinite(f.get_tensor(key)).all().item():raise ValueError('Nonfinite adapter weights')
 files={p.name:digest(p) for p in out.iterdir() if p.is_file()}
 result={'status':'PASS','contract':contract,'runtime':runtime,'records':len(data),'epochs':epochs,'steps':trainer.state.global_step,'finite_loss':True,'training_loss':metrics['train_loss'],'peak_memory_fraction':fraction,'steady_step_mean_seconds':steady_step_mean(times,len(data)),'step_seconds':times,'training_wall_seconds':time.perf_counter()-start,'sample_indices':selection if sample else None,'files':files,'full_semantic_quality_pass':False,'schedule':'independent probe' if sample else 'one continuous five-epoch cosine, fresh optimizer/base model'}
 verify_files(out,result);atomic(folder/'result.json',result);status('complete',steps=expected_steps)
 del trainer,model;import gc;gc.collect();torch.cuda.empty_cache()
 return result

def compare(cfg,tok,staged,contract,folder):
 import torch
 from transformers import AutoModelForImageTextToText
 from peft import PeftModel
 from compare_factory_sample import load_case
 base=AutoModelForImageTextToText.from_pretrained(staged,local_files_only=True,trust_remote_code=False,dtype=torch.bfloat16,device_map={'':0},attn_implementation='sdpa')
 for epoch in cfg['save_epochs']:
  adapter=folder/f'epoch{epoch}'/'adapter';snap=json.loads((adapter/'snapshot.json').read_text());verify_files(adapter,snap)
  if snap['contract']!=contract or snap['epoch']!=epoch:raise ValueError('Snapshot identity differs')
  model=PeftModel.from_pretrained(base,adapter,is_trainable=False);model.eval()
  for i in range(10):
   out=folder/f'epoch{epoch}'/'comparison'/f'case{i:02d}.json'
   if out.exists():
    saved=json.loads(out.read_text())
    if saved.get('contract')!=contract or saved.get('adapter_sha256')!=digest(adapter/'adapter_model.safetensors') or saved.get('case_index')!=i:raise ValueError('Existing comparison identity differs')
    continue
   messages,reference=load_case(inside(ROOT,cfg['evaluation']['file']),i)
   inputs=tok.apply_chat_template(messages,tokenize=True,enable_thinking=False,add_generation_prompt=True,return_dict=True,return_tensors='pt').to(model.device)
   outputs={}
   for label in ('base','tuned'):
    started=time.perf_counter()
    with torch.inference_mode(),(model.disable_adapter() if label=='base' else contextlib.nullcontext()):
     ids=model.generate(**inputs,do_sample=False,max_new_tokens=4096,pad_token_id=tok.pad_token_id)
    gen=ids[0,inputs['input_ids'].shape[-1]:];torch.cuda.synchronize()
    outputs[label]={'text':tok.decode(gen,skip_special_tokens=True),'tokens':len(gen),'hit_token_limit':len(gen)>=4096,'seconds':time.perf_counter()-started}
   atomic(out,{'contract':contract,'epoch':epoch,'case_index':i,'messages':messages,'reference_unreviewed':reference,'adapter_sha256':digest(adapter/'adapter_model.safetensors'),'base':outputs['base'],'tuned':outputs['tuned'],'semantic_review':'PENDING_ACTUAL_CONTENT_REVIEW'})
   atomic(folder/f'epoch{epoch}'/'comparison_status.json',{'completed':i+1,'total':10,'contract':contract})
  base=model.unload();del model
 del base;import gc;gc.collect();torch.cuda.empty_cache()

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',default='configs/hyperparameters.qwen35_4b_3000.P01.yaml');p.add_argument('--phase',choices=['check','sample','train','compare','all'],default='check');p.add_argument('--execute',action='store_true');p.add_argument('--resume',action='store_true');args=p.parse_args()
 cfg=yaml.safe_load(inside(ROOT,args.config).read_text(encoding='utf-8'));validate_config(cfg)
 try:rows,contract=validate_release(ROOT,cfg)
 except (ValueError,FileNotFoundError) as e:
  if args.execute:raise
  print(json.dumps({'status':'BLOCKED_DATA_NOT_READY','model':MODEL,'hardware':'B200','reason':str(e),'gpu_started':False,'download_started':False},ensure_ascii=False));return 0
 if not args.execute or args.phase=='check':
  print(json.dumps({'status':'DATA_READY_GPU_UNVERIFIED','contract':contract,'records':len(rows),'sample_steps':4,'steps_per_epoch':188,'training_steps':940,'save_epochs':[2,5],'gpu_started':False}));return 0
 if args.resume and args.phase not in ('train','all'):raise ValueError('Resume is only for full training')
 with gpu_guard(ROOT):
  runtime=runtime_info(cfg)
  import shutil
  cache=Path(cfg['model_cache']);cache.mkdir(parents=True,exist_ok=True)
  if shutil.disk_usage(cache).free<12*2**30:raise ValueError('At least 12GiB free RAM/model-cache space required')
  outputs=inside(ROOT,cfg['output_root']);outputs.mkdir(parents=True,exist_ok=True)
  if shutil.disk_usage(outputs).free<10*2**30:raise ValueError('At least 10GiB free checkpoint/output space required')
  from model_runtime import configure
  configure({'runtime':{'linear_attention_backend':'installed'}})
  os.environ.setdefault('TRITON_CACHE_DIR','/tmp/qwen35_4b_triton_cache')
  os.environ.setdefault('TORCHINDUCTOR_CACHE_DIR','/tmp/qwen35_4b_inductor_cache')
  from huggingface_hub import snapshot_download
  staged=snapshot_download(MODEL,revision=REVISION,cache_dir=cfg['model_cache'],token=False)
  from transformers import AutoTokenizer
  tok=AutoTokenizer.from_pretrained(staged,local_files_only=True,trust_remote_code=False)
  if tok.pad_token_id is None:tok.pad_token=tok.eos_token
  tok.padding_side='right';encoded=encode(rows,tok,cfg['training']['max_length'])
  folder=inside(ROOT,cfg['output_root'])/contract['config_sha256'][:16]
  atomic(folder/'token_measurement.json',{'contract':contract,'records':len(encoded),'max_tokens':max(len(x['input_ids']) for x in encoded),'total_tokens':sum(len(x['input_ids']) for x in encoded),'truncated':0,'loss_policy':'final_assistant_only'})
  probe=folder/'sample60'
  if args.phase in ('sample','all'):train(ROOT,cfg,encoded,tok,staged,contract,runtime,probe,sample=True)
  if args.phase in ('train','all'):
   if not (probe/'result.json').is_file():raise ValueError('Run the 60-row probe first')
   receipt=json.loads((probe/'result.json').read_text());verify_files(probe/'adapter',receipt);validate_probe(receipt,contract,runtime)
   train(ROOT,cfg,encoded,tok,staged,contract,runtime,folder/'full3000',resume=args.resume)
  if args.phase in ('compare','all'):
   completed=folder/'full3000/result.json'
   if not completed.is_file():raise ValueError('Full training not completed')
   result=json.loads(completed.read_text());verify_files(folder/'full3000/adapter',result)
   if result['contract']!=contract or result['epochs']!=5:raise ValueError('Full training identity differs')
   compare(cfg,tok,staged,contract,folder/'full3000')
 print('COMPLETE: artifacts preserved; actual answer review remains separate')
 return 0

if __name__=='__main__':
 try:sys.exit(main())
 except Exception as e:
  # Avoid tracebacks containing authenticated URLs or request parameters.
  print('FAILED:',type(e).__name__)
  if isinstance(e,(ValueError,FileNotFoundError)) and not any(x in str(e) for x in ('://','hf_','npg_')):print(str(e))
  sys.exit(1)
