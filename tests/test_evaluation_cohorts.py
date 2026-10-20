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
            for name in ('control_pipeline.py','compare_factory_sample.py','runpod_bridge.py','db_registry.py','runpod_factory_sample.py','prepare_data.py','factory_state.py'):
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
            sent={};client=SimpleNamespace(contents=lambda *a:None,ensure_file=lambda name,text:sent.__setitem__(name,text))
            env={'ROOT':root,'connection':lambda:client,'sample_mode':sample_mode,'report_input_info':report_input_info,
                 'hashlib':hashlib,'json':json,'yaml':yaml,'dashboard_store':SimpleNamespace(persist=lambda *a:None)}
            exec(compile(ast.Module(body=[publish],type_ignores=[]),'publish-test','exec'),env)
            env['publish'](cfg)
            self.assertEqual(cfg['data']['test_file'],'data/eval/prompts.app_v1.jsonl')
            self.assertIn(cfg['data']['heldout_test_file'],sent)
            self.assertEqual(hashlib.sha256(sent[cfg['data']['heldout_test_file']].encode()).hexdigest(),cfg['data']['heldout_sha256'])
            self.assertEqual(hashlib.sha256(sent[cfg['data']['test_file']].encode()).hexdigest(),cfg['evaluation']['sha256'])
            self.assertTrue(report_input_info(root,cfg))

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
