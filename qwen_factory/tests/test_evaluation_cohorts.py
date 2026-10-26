import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ast,json,tempfile,unittest,hashlib,yaml
from pathlib import Path
from types import SimpleNamespace
from compare_factory_sample import load_case,save_report
from db_registry import sample_mode,report_input_info
ROOT=Path(__file__).resolve().parents[1]


class EvaluationCohortTests(unittest.TestCase):
    def test_publish_includes_heldout_and_preserves_common_report_path(self):
        tree=ast.parse((ROOT/'scripts/local_dashboard.py').read_text(encoding='utf-8'))
        publish=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='publish')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'scripts').mkdir();(root/'configs').mkdir();(root/'data/eval').mkdir(parents=True)
            for name in ('control_pipeline.py','model_runtime.py','runtime_migration.py','inference_identity.py','local_evaluation_bundle.py','compare_factory_sample.py','runpod_bridge.py','db_registry.py','runpod_factory_sample.py','prepare_data.py','factory_state.py','cloud_evidence.py','cloud_evaluation.py','cloud_employee_context.py','practical_reports.py'):
                (root/'scripts'/name).write_text('# source',encoding='utf-8')
            data=root/'data/production';data.mkdir()
            for name in ('train','validation','test'):
                (data/f'{name}.jsonl').write_text(json.dumps({'messages':[{'role':'user','content':name},{'role':'assistant','content':'answer'}]})+'\n',encoding='utf-8')
            fixed=root/'data/eval/prompts.app_v1.jsonl'
            fixed.write_text('\n'.join(json.dumps({'messages':[{'role':'user','content':str(i)}]}) for i in range(10))+'\n',encoding='utf-8')
            cfg={'dataset_mode':'production','data':{'train_file':'data/production/train.jsonl','validation_file':'data/production/validation.jsonl',
                'test_file':'data/eval/prompts.app_v1.jsonl','heldout_test_file':'data/production/test.jsonl',
                'heldout_sha256':hashlib.sha256((data/'test.jsonl').read_bytes()).hexdigest()},
                'evaluation':{'mode':'shared_fixed_10','expected_count':10,'file':'data/eval/prompts.app_v1.jsonl','sha256':hashlib.sha256(fixed.read_bytes()).hexdigest()}}
            sent={};client=SimpleNamespace(contents=lambda name,text:sent.__setitem__(name,text),ensure_file=lambda name,text:sent.__setitem__(name,text))
            env={'ROOT':root,'connection':lambda:client,'sample_mode':sample_mode,'report_input_info':report_input_info,
                 'hashlib':hashlib,'json':json,'yaml':yaml,'dashboard_store':SimpleNamespace(persist=lambda *a:None)}
            exec(compile(ast.Module(body=[publish],type_ignores=[]),'publish-test','exec'),env)
            env['publish'](cfg)
            self.assertEqual(cfg['data']['test_file'],'data/eval/prompts.app_v1.jsonl')
            self.assertIn(cfg['data']['heldout_test_file'],sent)
            self.assertEqual(hashlib.sha256(sent[cfg['data']['heldout_test_file']].encode()).hexdigest(),cfg['data']['heldout_sha256'])
            self.assertEqual(hashlib.sha256(sent[cfg['data']['test_file']].encode()).hexdigest(),cfg['evaluation']['sha256'])
            self.assertTrue(report_input_info(root,cfg))
            self.assertIn('scripts/inference_identity.py',sent)
            self.assertIn('scripts/local_evaluation_bundle.py',sent)

    def test_heldout_reference_is_not_sent_as_prompt(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.jsonl'
            path.write_text(json.dumps({'messages':[{'role':'user','content':'question'},{'role':'assistant','content':'secret reference'}]}),encoding='utf-8')
            prompt,reference=load_case(path,0)
            self.assertEqual(prompt,[{'role':'user','content':'question'}]);self.assertEqual(reference,'secret reference')

    def test_heldout_reports_do_not_create_per_case_markdown(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'report';save_report(target,{'cohort':'heldout'},write_markdown=False)
            self.assertEqual({p.name for p in target.iterdir()},{'comparison.json'})

    def test_pipeline_defaults_to_full_150_and_separate_fixed_ten(self):
        tree=ast.parse((ROOT/'scripts/control_pipeline.py').read_text(encoding='utf-8'))
        loop=next(n for n in ast.walk(tree) if isinstance(n,ast.For) and isinstance(n.target,ast.Tuple)
                  and [e.id for e in n.target.elts]==['cohort','cohort_file'])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'data').mkdir()
            for name,count in [('report',10),('heldout',150)]:
                (root/f'data/{name}.jsonl').write_text('\n'.join(json.dumps({'messages':[{'role':'user','content':str(i)}]}) for i in range(count)),encoding='utf-8')
            calls=[]
            env={'root':root,'cohorts':[('report','data/report.jsonl'),('heldout','data/heldout.jsonl')],
                 'json':json,'max_new_tokens':3072,'args':SimpleNamespace(case_limit=None),
                 'snapshots':[{'status':'TRAINED','weight_id':'fake','trained_epoch':5}],
                 'output':root/'outputs/run','cfg':{'model':{}},'execute':lambda *a:calls.append(a),'print':lambda *a,**k:None}
            exec(compile(ast.Module(body=[loop],type_ignores=[]),'cohort-loop','exec'),env)
            self.assertEqual(len(calls),2)
            for call,expected,cohort in zip(calls,[10,150],['report','heldout']):
                begin=call.index('--case-indices')+1;end=call.index('--max-new-tokens')
                self.assertEqual(list(call[begin:end]),list(map(str,range(expected))))
                self.assertEqual(call[-2:],('--cohort',cohort))


class CuratedCloudUploadTests(unittest.TestCase):
    def fixture(self):
        uploads={key:(key+'\r\n').encode() for key in ('train','validation','heldout','report')}
        data={key+'_file':'data/production/'+key+'.jsonl' for key in ('train','validation')}
        data.update(heldout_test_file='data/production/test.jsonl')
        for key in ('train','validation','heldout'):data[key+'_sha256']=hashlib.sha256(uploads[key]).hexdigest()
        return uploads,{'data':data,'evaluation':{'file':'data/eval/fixed.jsonl','sha256':hashlib.sha256(uploads['report']).hexdigest()}}

    def test_keeps_raw_bytes_and_all_four_cohorts(self):
        from prepare_data import install_curated_uploads
        from unittest.mock import patch
        uploads,cfg=self.fixture()
        with tempfile.TemporaryDirectory() as folder,patch('db_registry.build_plans') as validate:
            root=Path(folder)
            result=install_curated_uploads(root,uploads,cfg)
            validate.assert_called_once()
            self.assertEqual(result,{'train':1200,'validation':150,'heldout':150,'report':10})
            self.assertEqual((root/cfg['data']['heldout_test_file']).read_bytes(),uploads['heldout'])
            self.assertEqual((root/cfg['evaluation']['file']).read_bytes(),uploads['report'])

    def test_missing_heldout_or_changed_file_cannot_install(self):
        from prepare_data import install_curated_uploads
        uploads,cfg=self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(ValueError):install_curated_uploads(root,{k:v for k,v in uploads.items() if k!='heldout'},cfg)
            uploads['train']+=b'changed'
            with self.assertRaises(ValueError):install_curated_uploads(root,uploads,cfg)
            self.assertFalse((root/'data').exists())

    def test_failed_split_validation_cannot_install(self):
        from prepare_data import install_curated_uploads
        from unittest.mock import patch
        uploads,cfg=self.fixture()
        with tempfile.TemporaryDirectory() as folder,patch('db_registry.build_plans',side_effect=ValueError('leakage')):
            root=Path(folder)
            with self.assertRaises(ValueError):install_curated_uploads(root,uploads,cfg)
            self.assertFalse((root/'data').exists())


class CohortReportStorageTests(unittest.TestCase):
    def test_both_cohorts_can_sync_without_allowing_arbitrary_documents(self):
        import dashboard_store
        self.assertTrue(dashboard_store.allowed('reports/heldout_compare_run/comparison.json'))
        self.assertTrue(dashboard_store.allowed('reports/smoke_compare_run/comparison.json'))
        self.assertFalse(dashboard_store.allowed('reports/heldout_compare_run/secrets.json'))

    def test_catalog_separates_cohorts_and_generation_conditions(self):
        import human_reports
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();(root/'reports').mkdir()
            (root/'reports/candidate_versions.json').write_text(json.dumps({'weight':1}))
            def add(prefix,name,index,created,tokens):
                path=root/'reports'/(prefix+name);path.mkdir()
                row={'created_at':created,'case_index':index,'test_sha256':prefix,
                     'factory_manifest':{'weight_id':'weight','run_id':'run','trained_epoch':5},
                     'quantization':{'dtype':'bfloat16','load_in_4bit':False},'generation':{'max_new_tokens':tokens}}
                (path/'comparison.json').write_text(json.dumps(row))
            add('smoke_compare_','old',0,'1',100)
            add('smoke_compare_','new',1,'2',200)
            add('heldout_compare_','held',0,'3',200)
            report=human_reports.catalog(root)['weight'];heldout=human_reports.catalog(root,cohort='heldout')['weight']
            self.assertEqual(set(report['cases']),{1});self.assertEqual(set(heldout['cases']),{0})
            self.assertEqual(heldout['cohort'],'heldout')

    def test_legacy_rating_signature_remains_stable(self):
        import human_reports
        row={'model':{},'quantization':{},'messages':[],'generation':{},'test_sha256':'hash','case_index':0,'adapter_sha256':'adapter','tuned':{'text':'answer'}}
        old={k:row.get(k) for k in ('model','quantization','messages','generation','test_sha256','case_index','adapter_sha256')};old['answer']='answer'
        self.assertEqual(human_reports.case_signature(row),hashlib.sha256(json.dumps(old,sort_keys=True,ensure_ascii=False).encode()).hexdigest())
