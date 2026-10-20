"""Detached, CPU-only report synchronization and AI-queue supervisor on RunPod."""
import json
import os
import sys
import time
import subprocess
import hashlib
from pathlib import Path
from datetime import datetime,timezone
from contextlib import closing
import app_settings
import dashboard_store

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'outputs/control_service'
IDLE_DB_INTERVAL=900
SERVICE_VERSION=hashlib.sha256(b''.join((ROOT/'scripts'/name).read_bytes() for name in (
    'runpod_service.py','runpod_bridge.py','dashboard_store.py','human_reports.py',
    'ai_evaluation.py','app_settings.py'))).hexdigest()

def settings(auto_ai):
    FOLDER.mkdir(parents=True,exist_ok=True)
    path=FOLDER/'options.json'
    content=json.dumps({'auto_ai':bool(auto_ai)})
    if not path.exists() or path.read_text()!=content:
        path.write_text(content,encoding='utf-8')

def enabled():
    return json.loads((FOLDER/'options.json').read_text()).get('auto_ai',False)

def status():
    from runpod_bridge import alive
    path=FOLDER/'service.json'
    if not path.exists():return {'state':'NOT_STARTED'}
    record=json.loads(path.read_text())
    record['state']='RUNNING' if record.get('pid') and alive(record['pid'],record.get('stamp')) else 'STOPPED'
    record['heartbeat_delayed']=time.time()-record.get('heartbeat',0)>=90
    if record['state']=='RUNNING' and record['heartbeat_delayed']:
        record['state']='UNRESPONSIVE'
    return record

def start(auto_ai=True):
    import fcntl
    from runpod_bridge import atomic,process_stamp
    settings(auto_ai)
    # The supervisor's lifetime lock also prevents two launchers starting duplicate services.
    with (FOLDER/'launch.lock').open('a') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX)
        record=status()
        if record.get('state')=='RUNNING':
            if record.get('version')==SERVICE_VERSION:return record
            # Replace only this identified CPU supervisor after a source deployment.
            import signal
            from runpod_bridge import alive
            if alive(record['pid'],record.get('stamp')):
                os.kill(record['pid'],signal.SIGTERM)
            deadline=time.monotonic()+5
            while alive(record['pid'],record.get('stamp')) and time.monotonic()<deadline:
                time.sleep(.1)
            if alive(record['pid'],record.get('stamp')):
                raise RuntimeError('이전 복구 서비스 종료 대기 중입니다. 중복 시작하지 않습니다.')
        if record.get('state')=='UNRESPONSIVE':
            raise RuntimeError('복구 서비스 응답이 지연됩니다. 기존 프로세스를 확인하세요. 중복 서비스를 시작하지 않습니다.')
        with (FOLDER/'service.lock').open('a') as service_guard:
            try:fcntl.flock(service_guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('기존 복구 서비스가 잠금을 유지하고 있습니다. 상태를 확인하세요.') from None
        python=ROOT/'.venv-runpod/bin/python'
        with (FOLDER/'service.log').open('ab') as log:
            child=subprocess.Popen([str(python),str(Path(__file__)),'--serve'],cwd=ROOT,
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        record={'pid':child.pid,'stamp':process_stamp(child.pid),'heartbeat':time.time(),'phase':'starting','version':SERVICE_VERSION}
        atomic(FOLDER/'service.json',record)
        return record

def fingerprint(root):
    paths=[]
    for pattern in ('outputs/control_jobs/*/job.json','outputs/control_jobs/*/job.log',
                    'reports/smoke_compare_*/comparison.json','outputs/factory_*/*/config.yaml'):
        for p in Path(root).glob(pattern):
            st=p.stat();paths.append((str(p.relative_to(root)),st.st_size,st.st_mtime_ns))
    return hashlib.sha256(json.dumps(sorted(paths)).encode()).hexdigest()

def sync_snapshot(root,overview):
    root=Path(root)
    documents={}
    for relative in overview.get('reports',[]):
        if not dashboard_store.allowed(relative):continue
        path=(root/relative).resolve();path.relative_to(root.resolve())
        text=path.read_text(encoding='utf-8');json.loads(text)
        documents[relative]=text
    import yaml
    for run,text in overview.get('configurations',{}).items():
        import uuid
        uuid.UUID(run)
        documents['reports/run_configs/'+run+'.yaml']=text
        data=yaml.safe_load(text).get('data',{})
        for field in ('train_file','validation_file','test_file','heldout_test_file'):
            relative=data.get(field)
            if relative and dashboard_store.allowed(relative) and (root/relative).is_file():
                documents[relative]=(root/relative).read_text(encoding='utf-8')
    dashboard_store.merge_history(root,overview.get('jobs',[]),overview.get('observed_at'),documents)
    return len(documents)+1

def serve():
    import fcntl
    import ai_evaluation
    import runpod_bridge
    FOLDER.mkdir(parents=True,exist_ok=True)
    with (FOLDER/'service.lock').open('a') as guard:
        try:fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        previous=None;last_db=0;retry_at=0;backoff=15
        while True:
            phase='idle'
            try:
                current=fingerprint(ROOT)
                if time.time()>=retry_at and (current!=previous or time.time()-last_db>=IDLE_DB_INTERVAL):
                    # Recover cache/versions before discovering newly generated reports.
                    dashboard_store.hydrate(ROOT)
                    sync_snapshot(ROOT,runpod_bridge.overview())
                    if enabled():ai_evaluation.ensure_worker(ROOT)
                    previous=fingerprint(ROOT);last_db=time.time()
                    backoff=15;retry_at=0
                    phase='synchronized'
            except Exception:
                phase='retry_pending'
                retry_at=time.time()+backoff
                backoff=min(backoff*2,300)
                # No raw exceptions or credential values in supervisor logs.
            record={'pid':os.getpid(),'stamp':runpod_bridge.process_stamp(os.getpid()),
                    'heartbeat':time.time(),'last_sync':last_db,'phase':phase,'version':SERVICE_VERSION}
            runpod_bridge.atomic(FOLDER/'service.json',record)
            time.sleep(15)

if __name__=='__main__' and sys.argv[1:]==['--serve']:serve()
