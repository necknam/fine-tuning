"""Set all synthetic Cloud account passwords; never changes local/REAL_USER rows."""
import argparse,getpass,json,os
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from dotenv import dotenv_values
from argon2 import PasswordHasher
ROOT=Path(__file__).resolve().parents[2]
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
 with psycopg.connect(dotenv_values(ROOT/'qwen_factory/.env.cloud-target')['GROWPATH_ADMIN_DB_URL'],sslmode='require',connect_timeout=15,row_factory=dict_row,prepare_threshold=None) as c:
  c.execute('SELECT pg_advisory_xact_lock(763250199)')
  ids=c.execute("SELECT employee_id FROM growpath_hr.employees WHERE source_type='TEST_MANUAL' ORDER BY employee_id FOR UPDATE").fetchall()
  if len(ids)!=100:raise ValueError('Expected 100 test accounts; inspect scope first')
  if args.apply:
   password=os.environ.get('TEST_LOGIN_PASSWORD') or getpass.getpass('Common test password: ')
   if not password:raise ValueError('Empty password')
   hasher=PasswordHasher();updates=[(hasher.hash(password),r['employee_id']) for r in ids]
   with c.cursor() as cur:cur.executemany("UPDATE growpath_hr.employees SET password_hash=%s,updated_at=now() WHERE source_type='TEST_MANUAL' AND employee_id=%s",updates)
   hashes=c.execute("SELECT password_hash FROM growpath_hr.employees WHERE source_type='TEST_MANUAL'").fetchall()
   assert all(hasher.verify(r['password_hash'],password) for r in hashes)
 print(json.dumps({'test_accounts':len(ids),'applied':args.apply,'local_modified':False}))
