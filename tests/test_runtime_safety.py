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
from runpod_client import RunPodClient, JupyterHTTPError


class RuntimeSafety(unittest.TestCase):
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
