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
    return record

def start(auto_ai=True):
    import fcntl
    from runpod_bridge import atomic,process_stamp
    settings(auto_ai)
    # The supervisor's lifetime lock also prevents two launchers starting duplicate services.
    with (FOLDER/'launch.lock').open('a') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX)
        record=status()
        if record.get('state')=='RUNNING':return record
        python=ROOT/'.venv-runpod/bin/python'
        with (FOLDER/'service.log').open('ab') as log:
            child=subprocess.Popen([str(python),str(Path(__file__)),'--serve'],cwd=ROOT,
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        record={'pid':child.pid,'stamp':process_stamp(child.pid),'heartbeat':time.time(),'phase':'starting'}
        atomic(FOLDER/'service.json',record)
        return record

def fingerprint(root):
    paths=[]
    for pattern in ('outputs/control_jobs/*/job.json','outputs/control_jobs/*/job.log',
                    'reports/smoke_compare_*/comparison.json','outputs/factory_sample/*/config.yaml'):
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
        relative=yaml.safe_load(text).get('data',{}).get('test_file')
        if relative and dashboard_store.allowed(relative) and (root/relative).is_file():
            documents[relative]=(root/relative).read_text(encoding='utf-8')
    # Replace only this Pod's observations; never mark an unobserved old job complete.
    safe=json.loads(app_settings.redact(root,json.dumps(overview.get('jobs',[]),ensure_ascii=False)))
    with closing(dashboard_store.pg(root)) as db:
        db.execute('SELECT pg_advisory_xact_lock(67429403)')
        row=db.execute("SELECT content FROM documents WHERE path='reports/control_history.json'").fetchone()
        old=json.loads(row[0]) if row else {'jobs':[]}
        jobs={j['job_id']:dict(j,stale=True) for j in old.get('jobs',[])}
        for j in safe:jobs[j['job_id']]=dict(j,stale=False)
        documents['reports/control_history.json']=json.dumps({'last_sync':datetime.now(timezone.utc).isoformat(),
            'jobs':sorted(jobs.values(),key=lambda j:j['created_at'])},ensure_ascii=False)
        for key,text in documents.items():
            db.execute('INSERT INTO documents(path,content) VALUES (%s,%s) ON CONFLICT(path) DO UPDATE SET content=EXCLUDED.content,updated_at=now() WHERE documents.content IS DISTINCT FROM EXCLUDED.content',(key,text))
        db.commit()
    return len(documents)

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
                    'heartbeat':time.time(),'last_sync':last_db,'phase':phase}
            runpod_bridge.atomic(FOLDER/'service.json',record)
            time.sleep(15)

if __name__=='__main__' and sys.argv[1:]==['--serve']:serve()
