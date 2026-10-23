import ast,copy,hashlib,json,sys,tempfile,unittest,uuid
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from db_registry import build_plans,digest
import human_reports

class SavedB200Evaluation(unittest.TestCase):
    def module(self):
        source=ast.parse((ROOT/'scripts/saved_b200_evaluation.py').read_text(encoding='utf-8-sig'))
        functions=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in ('immutable','prepare','evaluate')]
        scope={'Path':Path,'copy':copy,'hashlib':hashlib,'json':json,'yaml':yaml,'uuid':uuid,'digest':digest,'build_plans':build_plans,'shutil':__import__('shutil'),'subprocess':__import__('subprocess'),'sys':sys,'os':__import__('os')}
        exec(compile(ast.Module(body=functions,type_ignores=[]),'saved-b200-test','exec'),scope)
        return scope
    def fixture(self,folder):
        root=Path(folder);cfg=yaml.safe_load((ROOT/'configs/hyperparameters.compare.reviewed_v4_full1500.yaml').read_text(encoding='utf-8'))
        data=root/'data/production/old_all.jsonl';data.parent.mkdir(parents=True)
        data.write_text(''.join(json.dumps({'messages':[{'role':'user','content':str(i)},{'role':'assistant','content':'a'}]})+'\n' for i in range(1500)),encoding='utf-8')
        report=root/'data/eval/frozen.jsonl';report.parent.mkdir(parents=True)
        report.write_text(''.join(json.dumps({'messages':[{'role':'user','content':str(i)}]})+'\n' for i in range(10)),encoding='utf-8')
        config=root/'configs/improved.yaml';config.parent.mkdir()
        config.write_text(yaml.safe_dump(cfg),encoding='utf-8')
        live=copy.deepcopy(cfg);live['data']['test_file']='data/eval/frozen.jsonl';live['evaluation'].update(file='data/eval/frozen.jsonl',sha256=digest(report))
        config.with_name('improved_live_eval.yaml').write_text(yaml.safe_dump(live),encoding='utf-8')
        for epoch in (2,5):
            folder=root/'outputs'/f'B200_P01_epoch{epoch}';adapter=folder/'adapter';adapter.mkdir(parents=True)
            hashes={}
            for name in ('adapter_config.json','adapter_model.safetensors','tokenizer.json'):
                p=adapter/name;p.write_bytes(('fixture'+str(epoch)+name).encode());hashes[name]=digest(p)
            execution={'epochs':epoch,'train_samples':1500,'data_file':data.relative_to(root).as_posix(),'data_sha256':digest(data),'run_id':str(uuid.uuid4()),'weight_id':str(uuid.uuid4())}
            (folder/'execution.json').write_text(json.dumps(execution),encoding='utf-8')
            result={'epochs':epoch,'train_samples':1500,'model':cfg['model']['base_model_id'],'revision':cfg['model']['revision'],'data_sha256':digest(data),'adapter_hashes':hashes}
            (folder/'training_result.json').write_text(json.dumps(result),encoding='utf-8')
        return root,config
    def test_preserves_original_and_invokes_only_fixed10_inference(self):
        with tempfile.TemporaryDirectory() as folder:
            root,config=self.fixture(folder)
            original={p:digest(p) for p in (root/'outputs').rglob('*') if p.is_file()}
            calls=[];scope=self.module()
            scope['evaluate'](root,config,execute=lambda argv,**kw:calls.append(argv))
            self.assertEqual(len(calls),2)
            for call in calls:
                self.assertIn('scripts/compare_factory_sample.py',call)
                self.assertNotIn('--execute',call)
                self.assertEqual(call[call.index('--case-indices')+1:call.index('--max-new-tokens')],list(map(str,range(10))))
            self.assertTrue(all(digest(p)==sha for p,sha in original.items()))
            relative,cfg,adapters=scope['prepare'](root,config)
            self.assertEqual(cfg['execution_policy'],'evaluate_only')
            self.assertEqual(cfg['data']['test_file'],'data/eval/frozen.jsonl')
            self.assertEqual([json.loads((p/'factory_manifest.json').read_text(encoding='utf-8'))['trained_epoch'] for p in adapters],[2,5])
    def test_changed_saved_weights_cannot_be_evaluated(self):
        with tempfile.TemporaryDirectory() as folder:
            root,config=self.fixture(folder)
            (root/'outputs/B200_P01_epoch5/adapter/adapter_model.safetensors').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):self.module()['prepare'](root,config)
            self.assertFalse((root/'outputs/factory_production').exists())

class HistoricalReportDisplay(unittest.TestCase):
    def test_missing_timestamp_keeps_source_and_uses_recorded_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'reports/smoke_compare_old/comparison.json';path.parent.mkdir(parents=True)
            report={'model':{'base_model_id':'model','revision':'pin'},'factory_manifest':{'run_id':'legacy','weight_id':'weight','trained_epoch':2},'case_index':0,'quantization':{'load_in_4bit':False,'dtype':'bfloat16'}}
            raw=json.dumps(report);path.write_text(raw,encoding='utf-8')
            (root/'reports/candidate_versions.json').write_text(json.dumps({'weight':1}),encoding='utf-8')
            groups=human_reports.catalog(root,'bf16')
            _,loaded=groups['weight']['cases'][0]
            self.assertEqual(loaded['created_at'],'')
            self.assertEqual(loaded['timestamp_status'],'not_recorded')
            self.assertEqual(groups['weight']['manifest']['model'],report['model'])
            self.assertNotIn('is_sample',groups['weight']['manifest'])
            self.assertEqual(path.read_text(encoding='utf-8'),raw)
