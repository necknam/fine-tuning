"""Offline regression tests: python -m unittest discover -s tests -v."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
if os.name == 'nt':
    sys.modules.setdefault('fcntl', SimpleNamespace(LOCK_EX=2, LOCK_NB=4, flock=lambda *args: None))
import dashboard_store as store
import runpod_bridge as bridge
import runpod_service as service
import recovery
import ai_evaluation as ai
from runpod_client import RunPodClient, JupyterHTTPError


class RuntimeSafety(unittest.TestCase):
    def test_disabling_recomputation_requires_the_tested_batch_size(self):
        import yaml
        from runpod_factory_sample import check_settings
        cfg=yaml.safe_load((ROOT/'configs/hyperparameters.sample.pinned.yaml').read_text(encoding='utf-8'))
        check_settings(cfg)
        training=cfg['experiments'][0]['training'];training['gradient_checkpointing']=False
        with self.assertRaisesRegex(ValueError,'batch 1'):check_settings(cfg)
        training.update(per_device_train_batch_size=1,gradient_accumulation_steps=16)
        check_settings(cfg)
        training['gradient_checkpointing']='false'
        with self.assertRaisesRegex(ValueError,'boolean'):check_settings(cfg)

    def test_gpu_step_lease_check_is_local_and_expires_closed(self):
        from factory_state import RunLease
        from unittest.mock import Mock
        engine=Mock();lease=RunLease(engine,'test')
        lease.confirmed_until=time.monotonic()+30
        lease.assert_healthy();engine.connect.assert_not_called()
        lease.confirmed_until=time.monotonic()-1
        with self.assertRaises(RuntimeError):lease.assert_healthy()
        self.assertTrue(lease.lost.is_set())
        lease.confirmed_until=time.monotonic()+30
        with self.assertRaises(RuntimeError):lease.assert_healthy()

    def test_heartbeat_refreshes_deadline_only_after_commit(self):
        from factory_state import RunLease
        from unittest.mock import MagicMock
        engine=MagicMock();lease=RunLease(engine,'test')
        engine.begin.return_value.__enter__.return_value.execute.return_value.rowcount=1
        lease.assert_owned=MagicMock();lease.stop.wait=MagicMock(side_effect=[False,True])
        lease._heartbeat();self.assertGreater(lease.confirmed_until,time.monotonic())
        self.assertFalse(lease.lost.is_set())
        lease.confirmed_until=0
        engine.begin.return_value.__exit__.side_effect=RuntimeError('commit failed')
        lease.stop.wait=MagicMock(return_value=False);lease._heartbeat()
        self.assertEqual(lease.confirmed_until,0);self.assertTrue(lease.lost.is_set())

    def test_snapshot_upload_does_not_block_training_callback(self):
        import ast,threading,uuid
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import Mock
        source=ast.parse((ROOT/'scripts/runpod_factory_sample.py').read_text(encoding='utf-8'))
        callback=next(n for n in ast.walk(source) if isinstance(n,ast.ClassDef) and n.name=='Export')
        started=threading.Event();release=threading.Event();uploaded=[]
        with tempfile.TemporaryDirectory() as folder,ThreadPoolExecutor(max_workers=1) as uploader:
            output=Path(folder);pending={};artifact={'trained_epoch':4,'weight_id':'w4','status':'PENDING'}
            def upload(*args):
                started.set()
                if not release.wait(5):raise TimeoutError('upload test')
                uploaded.append(args[4])
            def save(path):Path(path,'adapter_model.safetensors').write_bytes(b'fake weights')
            env={'TrainerCallback':object,'lease':SimpleNamespace(assert_owned=Mock()),'engine':None,'record':{'run_id':'r'},
                 'artifact_rows':lambda *a:[artifact],'output':output,'uuid':uuid,'json':json,
                 'digest':lambda p:'test-hash','plan':{'config_hash':'hash','config':{'is_sample':True,'data':{}}},
                 'cfg':{'model':{}},'runtime':{},'tokenizer':SimpleNamespace(save_pretrained=lambda p:None),
                 'verify_snapshot':Mock(),'set_local_saved':Mock(),'upload_snapshot':upload,'api':None,
                 'repo_id':'fake','pending_uploads':pending,'uploader':uploader}
            exec(compile(ast.Module(body=[callback],type_ignores=[]),'callback-test','exec'),env)
            try:
                env['Export']().on_save(None,SimpleNamespace(epoch=4,global_step=16),None,
                                      model=SimpleNamespace(save_pretrained=save))
                self.assertTrue(started.wait(2));self.assertFalse(pending['w4'].done())
                self.assertTrue((output/'artifacts/w4/factory_manifest.json').is_file())
                env['verify_snapshot'].assert_called_once();env['set_local_saved'].assert_called_once()
            finally:release.set()
            pending['w4'].result(timeout=3);self.assertEqual(uploaded,[output/'artifacts/w4'])

    def test_training_cannot_succeed_when_background_upload_fails(self):
        import ast
        from concurrent.futures import ThreadPoolExecutor
        source=ast.parse((ROOT/'scripts/runpod_factory_sample.py').read_text(encoding='utf-8'))
        block=next(n for n in ast.walk(source) if isinstance(n,ast.With) and
                   any(isinstance(i.context_expr,ast.Call) and
                       getattr(i.context_expr.func,'id','')=='ThreadPoolExecutor' for i in n.items))
        env={'ThreadPoolExecutor':ThreadPoolExecutor,'pending_uploads':{},'resume':None}
        def fail():raise RuntimeError('upload failed; local files retained')
        def train(**kwargs):env['pending_uploads']['w4']=env['uploader'].submit(fail)
        env['trainer']=SimpleNamespace(train=train)
        with self.assertRaisesRegex(RuntimeError,'upload failed'):
            exec(compile(ast.Module(body=[block],type_ignores=[]),'upload-drain-test','exec'),env)

    def test_manual_and_worker_share_paid_evaluation_lock(self):
        import threading
        gate=threading.Lock();entered=threading.Event();release=threading.Event()
        results=[];errors=[]
        class DB:
            owned=False
            def execute(self,query,args):
                self.owned=gate.acquire(blocking=False)
                return SimpleNamespace(fetchone=lambda:(self.owned,))
            def rollback(self):
                if self.owned:self.owned=False;gate.release()
            def close(self):pass
        def paid(*args):
            entered.set()
            if not release.wait(5):raise TimeoutError('Test synchronization timeout')
            return {'average':3}
        def worker():
            try:results.append(ai.evaluate(ROOT,'weight',{},lease_owner='worker'))
            except BaseException as exc:errors.append(exc)
        with patch.object(ai,'settings',return_value=('test','model')), \
             patch.object(ai,'task_id',return_value='same-task'), \
             patch.object(ai.dashboard_store,'connect',side_effect=lambda root:DB()), \
             patch.object(ai,'latest',return_value=None), \
             patch.object(ai,'_evaluate_owned',side_effect=paid) as api:
            thread=threading.Thread(target=worker);thread.start()
            try:
                self.assertTrue(entered.wait(5))
                # Even an explicit paid re-evaluation cannot overlap a running one.
                with self.assertRaises(ai.EvaluationInProgress):
                    ai.evaluate(ROOT,'weight',{},force=True)
            finally:
                release.set();thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors,[])
            self.assertEqual(results,[{'average':3}])
            self.assertEqual(api.call_count,1)
            self.assertFalse(gate.locked())

    def test_finished_manual_result_is_reused_by_late_worker(self):
        guard=SimpleNamespace(execute=lambda *args:SimpleNamespace(fetchone=lambda:(True,)),
                              rollback=lambda:None,close=lambda:None)
        entry={'average':2.75}
        with patch.object(ai,'settings',return_value=('test','model')), \
             patch.object(ai,'task_id',return_value='task'), \
             patch.object(ai.dashboard_store,'connect',return_value=guard), \
             patch.object(ai,'latest',return_value=entry), \
             patch.object(ai,'_evaluate_owned',return_value={'average':3}) as api:
            self.assertIs(ai.evaluate(ROOT,'weight',{},lease_owner='worker'),entry)
            api.assert_not_called()
            self.assertEqual(ai.evaluate(ROOT,'weight',{},force=True),{'average':3})
            api.assert_called_once()

    def test_evaluation_lock_releases_after_api_failure(self):
        from unittest.mock import Mock
        guard=Mock()
        guard.execute.return_value.fetchone.return_value=(True,)
        with patch.object(ai,'settings',return_value=('test','model')), \
             patch.object(ai,'task_id',return_value='task'), \
             patch.object(ai.dashboard_store,'connect',return_value=guard), \
             patch.object(ai,'latest',return_value=None), \
             patch.object(ai,'_evaluate_owned',side_effect=ValueError('API failure')):
            with self.assertRaisesRegex(ValueError,'API failure'):
                ai.evaluate(ROOT,'weight',{})
        guard.rollback.assert_called_once()
        guard.close.assert_called_once()

    def test_batched_generation_keeps_case_alignment_and_eos_lengths(self):
        import ast
        from contextlib import nullcontext
        class Tensor:
            def __init__(self,rows):self.rows=rows;self.shape=(len(rows),len(rows[0]))
            def sum(self,dim):return SimpleNamespace(tolist=lambda:[sum(row) for row in self.rows])
            def tolist(self):return self.rows
            def __getitem__(self,key):return Tensor([row[key[1]] for row in self.rows[key[0]]])
        torch=SimpleNamespace(tensor=Tensor,cuda=SimpleNamespace(synchronize=lambda:None),inference_mode=nullcontext)
        source=ast.parse((ROOT/'scripts/compare_factory_sample.py').read_text(encoding='utf-8'))
        functions=[next(n for n in ast.walk(source) if isinstance(n,ast.FunctionDef) and n.name==name)
                   for name in ('trim_generated','generate_batch')]
        class Inputs(dict):
            def to(self,device):return self
        class Tokenizer:
            eos_token_id=9
            def apply_chat_template(self,messages,**kwargs):return messages[0]['content']
            def __call__(self,texts,**kwargs):
                self.padding=kwargs['padding']
                return Inputs(input_ids=torch.tensor([[0,1],[2,3]]),attention_mask=torch.tensor([[0,1],[1,1]]))
            def decode(self,ids,**kwargs):return str(ids)
        tokenizer=Tokenizer()
        scope=dict(tokenizer=tokenizer,torch=torch,time=time,cfg={'experiments':[{'training':{'max_length':10}}]},
                   args=SimpleNamespace(max_new_tokens=3),generation={},
                   model=SimpleNamespace(generate=lambda **kwargs:torch.tensor([[0,1,4,9,0],[2,3,5,6,9]])))
        exec(compile(ast.Module(body=functions,type_ignores=[]),'comparison_batch','exec'),scope)
        responses,lengths=scope['generate_batch']([(0,[{'content':'a'}],None),(1,[{'content':'b'}],None)])
        self.assertTrue(tokenizer.padding)
        self.assertEqual(lengths,[1,2])
        self.assertEqual([r['tokens'] for r in responses],[2,3])
        self.assertEqual([r['text'] for r in responses],['[4, 9]','[5, 6, 9]'])
        self.assertTrue(all(r['ended_with_eos'] for r in responses))
        self.assertEqual([r['generation_batch_size'] for r in responses],[2,2])

    def test_base_answer_cache_requires_matching_kernel_packages(self):
        import compare_factory_sample as comparison
        manifest={'file_sha256':{name:'hash' for name in ('tokenizer.json','tokenizer_config.json','chat_template.jinja')}}
        cfg={'model':{'base_model_id':'test','revision':'pinned'}}
        messages=[{'role':'user','content':'question'}];generation={'max_new_tokens':128}
        entry={'model':cfg['model'],'quantization':{'load_in_4bit':False,'dtype':'bfloat16'},'messages':messages,
               'batch_context_sha256':'same-batch','generation':generation,'factory_manifest':manifest,'packages':{'torch':'test','fla-core':'new'},
               'base':{'text':'answer','ended_with_eos':True,'hit_token_limit':False}}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);report=root/'reports/smoke_compare_test/comparison.json';report.parent.mkdir(parents=True)
            report.write_text(json.dumps(entry),encoding='utf-8')
            with patch.object(comparison,'inference_packages',return_value=entry['packages']):
                self.assertIsNotNone(comparison.find_base_cache(root,cfg,messages,generation,manifest,'same-batch'))
                self.assertIsNone(comparison.find_base_cache(root,cfg,messages,generation,manifest,'other-batch'))
                self.assertIsNone(comparison.find_base_cache(root,cfg,messages,generation,manifest,None))
            with patch.object(comparison,'inference_packages',return_value={'torch':'test','fla-core':'old'}):
                self.assertIsNone(comparison.find_base_cache(root,cfg,messages,generation,manifest,'same-batch'))

    def test_preset_effective_batch_stays_consistent_after_speed_defaults(self):
        import yaml
        from experiment_presets import PRESETS
        cfg=yaml.safe_load((ROOT/'configs/hyperparameters.sample.pinned.yaml').read_text(encoding='utf-8'))
        default=cfg['experiments'][0]['training'];self.assertEqual(len(PRESETS),25)
        for pid,_,changes,_ in PRESETS:
            recipe=dict(default,**changes)
            effective=recipe['per_device_train_batch_size']*recipe['gradient_accumulation_steps']
            self.assertEqual(effective,32 if pid=='P10' else 16,pid)

    def test_partial_base_cache_regenerates_identical_batch_context(self):
        import ast,hashlib
        from contextlib import nullcontext
        from datetime import datetime,timezone
        from uuid import uuid4
        source=ast.parse((ROOT/'scripts/compare_factory_sample.py').read_text(encoding='utf-8'))
        loop=next(n for n in ast.walk(source) if isinstance(n,ast.For) and
                  isinstance(n.target,ast.Name) and n.target.id=='offset')
        cases=[(i,[{'role':'user','content':str(i)}],None) for i in range(2)]
        calls=[];reports=[];root=Path('test-root')
        def generate(selected):
            calls.append([c[0] for c in selected])
            return ([{'text':'generated','ended_with_eos':True,'hit_token_limit':False} for _ in selected],
                    [1]*len(selected))
        env={'range':range,'len':len,'cases':cases,'args':SimpleNamespace(batch_size=8,adapter='fake'),
             'manifest':{'trained_epoch':4},'torch':SimpleNamespace(cuda=SimpleNamespace(
                 reset_peak_memory_stats=lambda:None,max_memory_allocated=lambda:0,max_memory_reserved=lambda:0)),
             'hashlib':hashlib,'json':json,'root':root,'cfg':{'model':{},'quantization':{}},'generation':{},
             'find_base_cache':lambda root,cfg,messages,*a:(root/'reports/old',{'text':'cached'}) if messages[0]['content']=='0' else None,
             'model':SimpleNamespace(disable_adapter=nullcontext),'generate_batch':generate,
             'datetime':datetime,'timezone':timezone,'evaluation_precision':{},'adapter_digest':'a',
             'test_digest':'t','total_cases':2,'inference_packages':lambda:{},'uuid4':uuid4,
             'save_report':lambda output,result:reports.append(result)}
        exec(compile(ast.Module(body=[loop],type_ignores=[]),'partial-cache-test','exec'),env)
        self.assertEqual(calls,[[0,1],[0,1]])
        self.assertEqual(len(reports),2)
        self.assertTrue(all(not r['base_reused'] and r['base']['text']=='generated' for r in reports))
        self.assertEqual(reports[0]['batch_context_sha256'],reports[1]['batch_context_sha256'])

    def test_hard_evaluation_suite_is_ten_fixed_held_out_requests(self):
        entries=[json.loads(line) for line in (ROOT/'data/eval/prompts.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        self.assertEqual(len(entries),10)
        requests=[json.loads(entry['messages'][-1]['content']) for entry in entries]
        self.assertTrue(all(entry['messages'][-1]['role']=='user' for entry in entries))
        self.assertEqual(sum(r['task']=='revise_roadmap' for r in requests),2)
        original=dict(requests[0]);original.pop('perspective')
        for request in requests[1:3]:
            comparable=dict(request);comparable.pop('perspective');self.assertEqual(comparable,original)
        self.assertEqual(len({r['perspective'] for r in requests[:3]}),3)
        self.assertTrue(requests[8]['existing_roadmap']['stages'][0]['completed'])
        self.assertTrue(requests[9]['employee_requested_changes'])

    def test_strict_judge_start_stage_and_grounded_evidence(self):
        request={'task':'generate_roadmap','start_stage':2,'duration_weeks':4,'weekly_hours':3,'budget_krw':50000,'resources':[]}
        answer={'stages':[{'stage':1,'hours':2,'cost_krw':0,'resource_ids':[],'activity':'질문 작성'},
                          {'stage':2,'hours':10,'cost_krw':0,'resource_ids':[]}], 'total_hours':12,'total_cost_krw':0}
        report={'messages':[{'role':'user','content':json.dumps(request,ensure_ascii=False)}],
                'tuned':{'text':json.dumps(answer,ensure_ascii=False)}}
        review={key:{'score':4,'reason':'검토 근거','evidence':['질문 작성']} for key in ai.DIMENSIONS}
        review['revision']={'score':None,'reason':'수정 요청 없음','evidence':[]}
        review.update(summary='평가',issues=[])
        adjusted,changes=ai.apply_strict_checks(review,report)
        self.assertEqual(adjusted['goal_fit']['score'],2)
        self.assertEqual(adjusted['constraints']['score'],4, 'Start-stage violation belongs to goal fit')
        self.assertEqual(review['goal_fit']['score'],4, 'Preserve raw judge output')
        self.assertTrue(any(change['criterion']=='goal_fit' for change in changes))
        request['task']='revise_roadmap'
        report['messages'][0]['content']=json.dumps(request)
        adjusted,_=ai.apply_strict_checks(review,report)
        self.assertEqual(adjusted['goal_fit']['score'],4, 'Preserved completed history is not a new-start violation')
        review['resources']['evidence']=['답변에 없는 만들어낸 인용']
        adjusted,_=ai.apply_strict_checks(review,report)
        self.assertEqual(adjusted['resources']['score'],3)
        self.assertIn('evidence',ai.schema()['properties']['goal_fit']['required'])

    def test_new_production_directories_and_immutable_files(self):
        nodes = {'workspace/qwen_factory': {'type': 'directory'}}
        client = RunPodClient('https://example.invalid', 'test')

        def api(endpoint, data=None, method='GET'):
            path = urllib.parse.unquote(endpoint.split('/api/contents/')[1].split('?')[0])
            if method == 'GET':
                if path not in nodes: raise FileNotFoundError(path)
                return nodes[path]
            if path.rsplit('/', 1)[0] not in nodes: raise FileNotFoundError('Missing parent')
            nodes[path] = data
            return data

        client.api = api
        name = 'data/production/processed/train_'+'a'*64+'.jsonl'
        client.ensure_file(name, '{}\n')
        client.ensure_file(name, '{}\n')
        client.ensure_file('data/production/eval/control_abc.jsonl', '{}\n')
        self.assertEqual(nodes['workspace/qwen_factory/data/production']['type'], 'directory')
        with self.assertRaises(ValueError): client.ensure_file(name, 'changed')
        with self.assertRaises(ValueError): client.contents('../escape', 'bad')

    def test_directory_creation_race_and_file_parent(self):
        client = RunPodClient('https://example.invalid', 'test')
        calls = []
        def api(endpoint, data=None, method='GET'):
            calls.append(method)
            if len(calls)==1: raise FileNotFoundError()
            if method=='PUT': raise JupyterHTTPError(409, endpoint, method)
            return {'type': 'directory'}
        client.api = api
        client.ensure_directory('data')
        self.assertEqual(calls, ['GET', 'PUT', 'GET'])
        client.api = lambda *args: {'type': 'file'}
        with self.assertRaises(ValueError): client.ensure_directory('data')
        with self.assertRaises(ValueError): client.ensure_directory('../outside')

    def test_control_uses_pod_venv_instead_of_jupyter_python(self):
        client = RunPodClient('https://example.invalid', 'test')
        code = []
        client.execute = lambda source: code.append(source) or 'QF_RESULT={"ok":true,"value":7}\n'
        self.assertEqual(client.call('7'), 7)
        self.assertIn('/workspace/qwen_factory/.venv-runpod/bin/python', code[0])
        self.assertIn('subprocess.run', code[0])

    def test_recovery_rechecks_stalled_service(self):
        client = SimpleNamespace(kernel_id='test',call=lambda expression: {'state':'UNRESPONSIVE','heartbeat_delayed':True})
        state={'client':client}
        with patch.object(recovery,'deploy_service') as deploy:
            recovery.ensure_service(ROOT,state,False)
            state['recovery_service_checked_at']=0
            recovery.ensure_service(ROOT,state,False)
            self.assertEqual(deploy.call_count,2)

    def test_zombies_pid_reuse_and_permission_fail_closed(self):
        # /proc stat starts at field 3 after the final ')' (names can contain ')').
        fields = ['S'] + ['0']*18 + ['123']
        with patch.object(bridge.os, 'kill'), patch.object(bridge.Path, 'read_text', return_value='1 (name)) '+' '.join(fields)):
            self.assertTrue(bridge.alive(1, '123'))
            self.assertFalse(bridge.alive(1, 'old'))
        for state in ('Z', 'X'):
            fields[0] = state
            with patch.object(bridge.os, 'kill'), patch.object(bridge.Path, 'read_text', return_value='1 (test) '+' '.join(fields)):
                self.assertFalse(bridge.alive(1, '123'))
        with patch.object(bridge.os, 'kill', side_effect=PermissionError):
            self.assertTrue(bridge.alive(1, '123'))

    def test_stalled_service_does_not_launch_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            record = {'pid': 1, 'stamp': '123', 'heartbeat': time.time()-300}
            (folder/'service.json').write_text(json.dumps(record), encoding='utf-8')
            with patch.object(service, 'FOLDER', folder), patch.object(bridge, 'alive', return_value=True), patch.object(service.subprocess, 'Popen') as spawn:
                self.assertEqual(service.status()['state'], 'UNRESPONSIVE')
                with self.assertRaisesRegex(RuntimeError, '중복'):
                    service.start(False)
                spawn.assert_not_called()

    def test_history_merges_database_and_rejects_older_observation(self):
        class DB:
            def __init__(self):
                self.content = json.dumps({'jobs': [dict(job_id='B', created_at=2, state='SUCCEEDED', _observed_at=20)]})
                self.calls = []
            def execute(self, query, args=None):
                self.calls.append(query)
                if query.startswith('SELECT content'):
                    return SimpleNamespace(fetchone=lambda: (self.content,))
                if query.startswith('INSERT') and args[0]=='reports/control_history.json': self.content=args[1]
                return SimpleNamespace(fetchone=lambda: None)
            def commit(self): pass
            def close(self): pass
        db = DB()
        with patch.object(store, 'pg', return_value=db), patch.object(store.app_settings, 'redact', side_effect=lambda root, text: text):
            store.merge_history(ROOT, [dict(job_id='A', created_at=1, state='RUNNING')], observed_at=21)
            result = store.merge_history(ROOT, [dict(job_id='B', created_at=2, state='RUNNING')], observed_at=19)
        jobs = {job['job_id']: job for job in result['jobs']}
        self.assertEqual(set(jobs), {'A', 'B'})
        self.assertEqual(jobs['B']['state'], 'SUCCEEDED')
        self.assertTrue(db.calls[0].startswith('SELECT pg_advisory_xact_lock'))

    def test_pipeline_forwards_gpu_descriptor_to_trainer_and_comparison(self):
        import ast
        source = (ROOT/'scripts/control_pipeline.py').read_text(encoding='utf-8')
        function = next(node for node in ast.walk(ast.parse(source))
                        if isinstance(node, ast.FunctionDef) and node.name=='execute')
        calls=[]
        scope=dict(os=os,sys=sys,root=ROOT,args=SimpleNamespace(config='configs/test.yaml'),
                   subprocess=SimpleNamespace(run=lambda *args, **kwargs: calls.append(kwargs)))
        exec(compile(ast.Module(body=[function],type_ignores=[]),'control_pipeline.py','exec'),scope)
        with tempfile.TemporaryFile() as guard, patch.dict(os.environ,{'QF_GPU_LOCK_FD':str(guard.fileno())}):
            scope['execute']('runpod_factory_sample.py','--execute')
            scope['execute']('compare_factory_sample.py','--case-index','0')
            self.assertEqual([call['pass_fds'] for call in calls],[(guard.fileno(),)]*2)

    @unittest.skipUnless(os.name == 'posix', 'Linux flock / inherited descriptor integration')
    def test_orphan_descendant_retains_gpu_lock(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(bridge, 'JOBS', Path(folder)):
            guard = bridge.gpu_lock()
            fd = guard.fileno()
            grandchild = 'import time; time.sleep(2)'
            parent = ('import subprocess,sys; '
                      f'subprocess.Popen([sys.executable,"-c",{grandchild!r}],pass_fds=({fd},),'
                      'stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)')
            subprocess.run([sys.executable, '-c', parent], pass_fds=(fd,), check=True)
            guard.close()
            self.assertIsNone(bridge.gpu_lock(), 'Orphan trainer must keep the next GPU job blocked')
            deadline = time.monotonic()+6
            while time.monotonic()<deadline:
                next_guard = bridge.gpu_lock()
                if next_guard is not None:
                    next_guard.close()
                    break
                time.sleep(.05)
            else: self.fail('GPU lock was not released when the last descendant exited')


if __name__ == '__main__':
    unittest.main()
