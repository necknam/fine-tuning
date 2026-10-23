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

class LiveTrainingStage(unittest.TestCase):
    def stage(self,text,kind='experiment'):
        import ast
        tree=ast.parse((ROOT/'scripts/local_dashboard.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='job_stage')
        env={};exec(compile(ast.Module(body=[node],type_ignores=[]),'stage-test','exec'),env)
        return env['job_stage']({'state':'RUNNING','kind':kind,'log_tail':text})
    def test_real_steps_replace_loading_stage(self):
        log="PIPELINE: train or resume\nLoading weights: 100%| 1184/1184 [05:36]\n 1%| 4/470 [05:45<11:14:29, 86.84s/it]\n{'loss': '0.6601', 'epoch': '0.04267'}"
        self.assertEqual(self.stage(log)[0],'학습 진행')
    def test_inference_loading_is_never_reported_as_training(self):
        self.assertEqual(self.stage('PIPELINE: compare epoch=2 cases=10\nLoading weights: 51%| 600/1184 [01:00]')[0],'평가 입력 답변 생성')
        self.assertEqual(self.stage('SAVED B200 EVALUATION: epoch=2; pending=[0]; no training','evaluate_saved_b200')[0],'기존 가중치 평가 진행')

class SavedConnectionRecovery(unittest.TestCase):
    def test_validated_public_address_survives_stale_cloud_default(self):
        from unittest.mock import patch
        import recovery
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'reports/connection_settings.json';path.parent.mkdir()
            public={'url':'https://current-8888.proxy.runpod.net','remote_path':'workspace/qwen_factory'}
            path.write_text(json.dumps(public),encoding='utf-8')
            settings={'RUNPOD_JUPYTER_URL':'https://obsolete-8888.proxy.runpod.net','RUNPOD_JUPYTER_TOKEN':'fixture-token'}
            with patch.object(recovery.app_settings,'get',side_effect=lambda root,key,default='':settings.get(key,default)),patch.object(recovery,'RunPodClient') as client:
                self.assertIs(recovery.reconnect(root,{},force=True),client.return_value)
                client.assert_called_once_with(public['url'],'fixture-token',public['remote_path'])
            self.assertEqual(set(json.loads(path.read_text(encoding='utf-8'))),{'url','remote_path'})
