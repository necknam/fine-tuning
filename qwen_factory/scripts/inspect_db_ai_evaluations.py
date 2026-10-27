import sys, json
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import dashboard_store

with closing(dashboard_store.connect(ROOT)) as conn:
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ai_evaluations'").fetchone()
    print('ai_evaluations table exists?', bool(exists))
    if exists:
        rows = conn.execute('SELECT id, weight_id, model, created_at FROM ai_evaluations').fetchall()
        print(f'Total existing ai_evaluations: {len(rows)}')
        for r in rows[:10]:
            print(' ', r)

