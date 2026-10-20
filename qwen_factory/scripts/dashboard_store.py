"""Dashboard persistence. Explicit Neon mode never falls back to local writes."""
import json
import os
import re
from pathlib import Path
from contextlib import closing, contextmanager
import app_settings

SCHEMA = 'qf_dashboard'

def values(root):
    return app_settings.read(root)

def remote(root):
    mode = values(root).get('DASHBOARD_STORAGE', 'neon')
    if mode != 'neon':
        raise RuntimeError('대시보드는 Neon만 지원합니다. DASHBOARD_STORAGE=neon을 사용하세요.')
    return True

class ScopedPG:
    """SET LOCAL per transaction also works with Neon's transaction pooler."""
    def __init__(self,db):self.db=db
    def execute(self,sql,args=None):
        from psycopg import sql as pgsql
        self.db.execute(pgsql.SQL('SET LOCAL search_path TO {}').format(pgsql.Identifier(SCHEMA)))
        return self.db.execute(sql,args)
    def commit(self):self.db.commit()
    def rollback(self):self.db.rollback()
    def close(self):self.db.close()

def pg(root):
    import psycopg
    url = values(root).get('DATABASE_URL', '')
    if not url:
        raise RuntimeError('Neon DATABASE_URL 설정이 필요합니다.')
    url = url.replace('postgresql+psycopg://', 'postgresql://', 1)
    try:
        return ScopedPG(psycopg.connect(url, connect_timeout=15))
    except Exception:
        raise RuntimeError('Neon 연결 실패: 연결 설정과 서비스 상태를 확인하세요. 로컬 대체 저장은 하지 않습니다.') from None

class Connection:
    def __init__(self, root):
        self.db = pg(root)
    def execute(self, sql, args=()):
        if 'sqlite_master' in sql:
            name = re.search(r"name='([^']+)'", sql)[1]
            return self.db.execute('SELECT 1 FROM information_schema.tables WHERE table_schema=%s AND table_name=%s', (SCHEMA, name))
        if sql == 'BEGIN IMMEDIATE':
            return self.db.execute('SELECT pg_advisory_xact_lock(67429401)')
        sql = sql.replace('?', '%s').replace(' REAL', ' DOUBLE PRECISION')
        if 'INSERT OR IGNORE INTO' in sql:
            sql = sql.replace('INSERT OR IGNORE INTO', 'INSERT INTO') + ' ON CONFLICT DO NOTHING'
        if 'INSERT OR REPLACE INTO ai_worker_lease' in sql:
            sql = sql.replace('INSERT OR REPLACE INTO', 'INSERT INTO') + ' ON CONFLICT (id) DO UPDATE SET owner=EXCLUDED.owner, expires=EXCLUDED.expires'
        return self.db.execute(sql, args)
    def commit(self): self.db.commit()
    def rollback(self): self.db.rollback()
    def close(self): self.db.close()

def connect(root):
    remote(root)
    return Connection(root)

def initialize(root):
    with closing(pg(root)) as db:
        from psycopg import sql
        db.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(SCHEMA)))
        db.execute('CREATE TABLE IF NOT EXISTS documents (path TEXT PRIMARY KEY, content TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now())')
        db.commit()

def persist(root, path):
    if not remote(root): return
    root, path = Path(root).resolve(), Path(path).resolve()
    key = path.relative_to(root).as_posix()
    if not allowed(key): raise ValueError('허용되지 않은 DB 문서 경로')
    content = path.read_text(encoding='utf-8')
    with closing(pg(root)) as db:
        db.execute('INSERT INTO documents(path,content) VALUES (%s,%s) ON CONFLICT(path) DO UPDATE SET content=EXCLUDED.content,updated_at=now() WHERE documents.content IS DISTINCT FROM EXCLUDED.content', (key,content))
        db.commit()

def allowed(key):
    return (key in ('reports/candidate_versions.json','reports/control_history.json') or
        bool(re.fullmatch(r'reports/(?:smoke|heldout)_compare_[^/]+/comparison.json', key)) or
        bool(re.fullmatch(r'reports/run_configs/[^/]+\.yaml', key)) or
        bool(re.fullmatch(r'reports/human_evaluations/[^/]+\.json', key)) or
        bool(re.fullmatch(r'data/sample/eval/[^/]+\.jsonl', key)) or
        bool(re.fullmatch(r'data/sample/processed/(?:(?:train|validation)_[a-f0-9]{64}|control_[a-f0-9]{20})\.jsonl', key)) or
        bool(re.fullmatch(r'data/production/eval/control_[a-f0-9]+\.jsonl', key)) or
        bool(re.fullmatch(r'data/production/processed/(?:train|validation)_[a-f0-9]{64}\.jsonl', key)))

def database_key(root):
    import hashlib
    return hashlib.sha256((values(root).get('DATABASE_URL','')+SCHEMA).encode()).hexdigest()

def persist_many(root, paths):
    root=Path(root).resolve()
    entries={}
    for path in paths:
        path=Path(path).resolve();key=path.relative_to(root).as_posix()
        if not allowed(key):raise ValueError('허용되지 않은 DB 문서 경로')
        entries[key]=path.read_text(encoding='utf-8')
    if not entries:return
    with closing(pg(root)) as db:
        for key,content in entries.items():
            db.execute('INSERT INTO documents(path,content) VALUES (%s,%s) ON CONFLICT(path) DO UPDATE SET content=EXCLUDED.content,updated_at=now() WHERE documents.content IS DISTINCT FROM EXCLUDED.content',(key,content))
        db.commit()


def merge_history(root, observed_jobs, observed_at=None, documents=None):
    """All UI/service writers merge against the latest DB row under one lock."""
    import time
    from datetime import datetime, timezone
    observed_at = time.time() if observed_at is None else float(observed_at)
    entries = dict(documents or {})
    if any(not allowed(key) for key in entries):
        raise ValueError('허용되지 않은 DB 문서 경로')
    safe = json.loads(app_settings.redact(root, json.dumps(observed_jobs, ensure_ascii=False)))
    with closing(pg(root)) as db:
        db.execute('SELECT pg_advisory_xact_lock(67429403)')
        row = db.execute("SELECT content FROM documents WHERE path='reports/control_history.json'").fetchone()
        old = json.loads(row[0]) if row else {'jobs': []}
        jobs = {job['job_id']: dict(job, stale=True) for job in old.get('jobs', [])}
        for job in safe:
            previous = jobs.get(job['job_id'], {})
            if observed_at >= previous.get('_observed_at', 0):
                jobs[job['job_id']] = dict(job, stale=False, _observed_at=observed_at)
        previous_sync = old.get('last_sync')
        previous_time = datetime.fromisoformat(previous_sync).timestamp() if previous_sync else 0
        history = {'last_sync': datetime.fromtimestamp(max(observed_at, previous_time), timezone.utc).isoformat(),
                   'jobs': sorted(jobs.values(), key=lambda job: job['created_at'])}
        entries['reports/control_history.json'] = json.dumps(history, ensure_ascii=False)
        for key, content in entries.items():
            db.execute('INSERT INTO documents(path,content) VALUES (%s,%s) ON CONFLICT(path) DO UPDATE SET content=EXCLUDED.content,updated_at=now() WHERE documents.content IS DISTINCT FROM EXCLUDED.content', (key, content))
        db.commit()
    return history

def hydrate(root, force=False, section="all"):
    import time,hashlib,uuid
    root=Path(root).resolve()
    if section not in ('all','history','reports'):raise ValueError('Unknown document section')
    state_path=root/'.cache'/('neon_sync_'+database_key(root)[:16]+'_'+section+'.json')
    try:state=json.loads(state_path.read_text(encoding='utf-8'))
    except (FileNotFoundError,ValueError):state={}
    if not force and time.time()-state.get('checked',0)<15:return
    known=state.get('files',{});changed=[];fresh={}
    with closing(pg(root)) as db:
        query='SELECT path,md5(content) FROM documents'
        if section=='history':query+=" WHERE path='reports/control_history.json' OR path LIKE 'reports/run_configs/%'"
        elif section=='reports':query+=" WHERE path LIKE 'reports/%'"
        metadata=db.execute(query).fetchall()
        for key,checksum in metadata:
            if not allowed(key):raise ValueError('DB 문서 경로가 올바르지 않습니다.')
            path=(root/key).resolve();path.relative_to(root)
            old=known.get(key,{})
            stat=path.stat() if path.is_file() else None
            if stat and old.get('checksum')==checksum and old.get('mtime')==stat.st_mtime_ns and old.get('size')==stat.st_size:
                fresh[key]=old;continue
            if stat and hashlib.md5(path.read_text(encoding='utf-8').encode()).hexdigest()==checksum:
                fresh[key]={'checksum':checksum,'mtime':stat.st_mtime_ns,'size':stat.st_size};continue
            changed.append(key)
        rows=db.execute('SELECT path,content FROM documents WHERE path=ANY(%s)',(changed,)).fetchall() if changed else []
    for key,content in rows:
        path=(root/key).resolve();path.relative_to(root)
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_name(path.name+'.restore.'+uuid.uuid4().hex)
        temp.write_text(content,encoding='utf-8',newline='');temp.replace(path)
        stat=path.stat()
        fresh[key]={'checksum':hashlib.md5(content.encode()).hexdigest(),'mtime':stat.st_mtime_ns,'size':stat.st_size}
    state_path.parent.mkdir(parents=True,exist_ok=True)
    temporary=state_path.with_name(state_path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps({'checked':time.time(),'files':fresh}),encoding='utf-8');temporary.replace(state_path)

@contextmanager
def version_lock(root):
    if not remote(root):
        yield
        return
    with closing(pg(root)) as db:
        db.execute('SELECT pg_advisory_xact_lock(67429402)')
        # Restore authoritative versions while the global lock is held.
        row=db.execute("SELECT content FROM documents WHERE path='reports/candidate_versions.json'").fetchone()
        path=Path(root)/'reports/candidate_versions.json'
        if row:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(row[0],encoding='utf-8')
        yield
        if path.exists():
            db.execute("INSERT INTO documents(path,content) VALUES ('reports/candidate_versions.json',%s) ON CONFLICT(path) DO UPDATE SET content=EXCLUDED.content WHERE documents.content IS DISTINCT FROM EXCLUDED.content",(path.read_text(encoding='utf-8'),))
        db.commit()
