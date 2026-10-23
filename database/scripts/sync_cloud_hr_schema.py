"""Create/verify empty private HR tables. Copies no employee or sheet rows."""
import json,os,sys
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.database.deployment import connect
from src.database.cloud_hr_schema import synchronize_schema

if __name__=='__main__':
    root=Path(__file__).resolve().parents[2]
    load_dotenv(root/'qwen_factory/.env.cloud-target',override=False)
    url=os.environ.get('GROWPATH_ADMIN_DB_URL')
    if not url:raise SystemExit('Set server-only GROWPATH_ADMIN_DB_URL; credentials are never printed.')
    with connect('SUPABASE_DB_URL') as source,psycopg.connect(url,sslmode='require',connect_timeout=15,row_factory=dict_row,prepare_threshold=None) as target:
        source.execute('SET TRANSACTION READ ONLY')
        target.execute("SET LOCAL statement_timeout='40s'; SET LOCAL lock_timeout='5s'")
        result=synchronize_schema(source,target)
    print(json.dumps(result,ensure_ascii=False,indent=2))
