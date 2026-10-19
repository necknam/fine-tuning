"""Reconnect control sessions without submitting or resuming GPU jobs."""
import time
from pathlib import Path
import app_settings
from runpod_client import RunPodClient

SERVICE_FILES = ('app_settings.py','dashboard_store.py','human_reports.py',
                 'ai_evaluation.py','runpod_service.py')

def reconnect(root, state, force=False):
    if not force and time.time()-state.get('reconnect_attempt_at',0)<60:
        return state.get('client')
    old=state.get('client')
    remembered=state.get('_reconnect_settings',{})
    url=app_settings.get(root,'RUNPOD_JUPYTER_URL',getattr(old,'url',remembered.get('url','')))
    token=app_settings.get(root,'RUNPOD_JUPYTER_TOKEN',getattr(old,'token',remembered.get('token','')))
    remote=app_settings.get(root,'RUNPOD_REMOTE_PATH',getattr(old,'remote_path',remembered.get('remote','workspace/qwen_factory')))
    if not (url and token):
        state['recovery_notice']='저장 기록 복원 완료 · 최신 RunPod 상태를 보려면 왼쪽에서 연결하세요.'
        return old
    state['reconnect_attempt_at']=time.time()
    state['_reconnect_settings']={'url':url,'token':token,'remote':remote}
    client=RunPodClient(url,token,remote)
    try:
        client.connect()
        client.call('runpod_bridge.overview()')
    except Exception:
        state['client']=None
        state['recovery_notice']='RunPod 재연결 대기 · Pod 상태와 Jupyter 인증정보를 확인하세요. 60초 후 재시도합니다.'
        return None
    state['client']=client
    state['recovery_notice']='RunPod 재연결 완료 · 기존 작업 상태를 확인합니다. 학습을 새로 시작하지 않습니다.'
    return client

def deploy_service(root,client,auto_ai=True):
    root=Path(root)
    for name in SERVICE_FILES:
        client.contents('scripts/'+name,(root/'scripts'/name).read_text(encoding='utf-8'))
    values=app_settings.read(root)
    env={k:values[k] for k in ('DATABASE_URL','OPENAI_API_KEY','OPENAI_EVAL_MODEL','HF_TOKEN','HF_REPO_ID') if values.get(k)}
    env['DASHBOARD_STORAGE']='neon'
    if not env.get('DATABASE_URL'):
        raise ValueError('복구 서비스에 DATABASE_URL 설정이 필요합니다.')
    # execute uses store_history=False; values remain in process memory, not files.
    client.execute('import os, sys, importlib\n'
        "sys.path.insert(0, '/workspace/qwen_factory/scripts')\n"
        +'os.environ.update('+repr(env)+')\n'
        +'import psycopg, dashboard_store, ai_evaluation, runpod_service\n'
        +'dashboard_store.pg(runpod_service.ROOT).close()\n'
        +'importlib.reload(runpod_service)\n'
        +'runpod_service.start(auto_ai='+repr(bool(auto_ai))+')\n')

def ensure_service(root,state,auto_ai=True):
    client=state.get('client')
    if client is None:return
    marker=(client.kernel_id,bool(auto_ai))
    if state.get('recovery_service_ready')==marker:
        if time.time()-state.get('recovery_service_checked_at',0)<60:return
        result=client.call("__import__('runpod_service').status()")
        state['recovery_service_checked_at']=time.time()
        if result.get('state')=='RUNNING':return
    deploy_service(root,client,auto_ai)
    state['recovery_service_ready']=marker
    state['recovery_service_checked_at']=time.time()
