import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from db_registry import build_plans
from prepare_data import install_curated_uploads
from runpod_factory_sample import check_settings

class FullTrainingContract(unittest.TestCase):
    def fixture(self,folder,count=1500):
        root=Path(folder)
        cfg=yaml.safe_load((ROOT/'configs/hyperparameters.compare.reviewed_v4_full1500.yaml').read_text(encoding='utf-8'))
        train=b''.join((json.dumps({'messages':[{'role':'user','content':str(i)},{'role':'assistant','content':'answer'}]})+'\n').encode() for i in range(count))
        report=b''.join((json.dumps({'messages':[{'role':'user','content':'report '+str(i)}]})+'\n').encode() for i in range(10))
        for relative,raw in [(cfg['data']['train_file'],train),(cfg['evaluation']['file'],report)]:
            path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        cfg['data']['train_sha256']=hashlib.sha256(train).hexdigest()
        cfg['evaluation']['sha256']=hashlib.sha256(report).hexdigest()
        config=root/'recipe.yaml';config.write_text(yaml.safe_dump(cfg),encoding='utf-8')
        return root,config,cfg,{'train':train,'report':report}
    def test_whole_1500_and_only_ten_report_inputs_install(self):
        with tempfile.TemporaryDirectory() as folder:
            root,path,cfg,uploads=self.fixture(folder)
            plan=build_plans(root,path,False)[0]
            self.assertEqual(plan['config']['data']['train']['rows'],1500)
            self.assertIsNone(plan['config']['data']['validation'])
            self.assertNotIn('heldout',plan['config']['data'])
            self.assertEqual(plan['config']['save_epochs'],[2,5])
            check_settings(cfg)
            self.assertEqual(install_curated_uploads(root,uploads,cfg),{'train':1500,'report':10})
    def test_1200_rows_cannot_run_as_whole_1500(self):
        with tempfile.TemporaryDirectory() as folder:
            root,path,cfg,uploads=self.fixture(folder,1200)
            with self.assertRaisesRegex(ValueError,'exactly 1500'):build_plans(root,path,False)
    def test_no_hidden_validation_or_heldout_partition(self):
        with tempfile.TemporaryDirectory() as folder:
            root,path,cfg,uploads=self.fixture(folder)
            for field in ('validation_file','heldout_test_file'):
                changed=copy.deepcopy(cfg);changed['data'][field]='data/production/unused.jsonl'
                path.write_text(yaml.safe_dump(changed),encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'forbids'):build_plans(root,path,False)
            cfg['experiments'][0]['training']['eval_strategy']='epoch'
            path.write_text(yaml.safe_dump(cfg),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'disables'):build_plans(root,path,False)
