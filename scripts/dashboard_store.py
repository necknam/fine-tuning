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
        bool(re.fullmatch(r'reports/smoke_compare_[^/]+/comparison.json', key)) or
        bool(re.fullmatch(r'reports/run_configs/[^/]+\.yaml', key)) or
        bool(re.fullmatch(r'reports/human_evaluations/[^/]+\.json', key)) or
        bool(re.fullmatch(r'data/sample/eval/[^/]+\.jsonl', key)))

def hydrate(root):
    if not remote(root): return
    root = Path(root).resolve()
    with closing(pg(root)) as db:
        rows = db.execute('SELECT path,content FROM documents').fetchall()
    for key, content in rows:
        if not allowed(key): raise ValueError('DB 문서 경로가 올바르지 않습니다.')
        path = (root/key).resolve()
        path.relative_to(root)
        if not path.exists() or path.read_text(encoding='utf-8') != content:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(path.name+'.restore.'+__import__('uuid').uuid4().hex)
            temp.write_text(content, encoding='utf-8')
            temp.replace(path)

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
