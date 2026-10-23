"""Register approved sheet departments without changing existing employee assignments."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.database.deployment import connect
from src.database.organization_setup import ensure_sheet_organization

if __name__=='__main__':
    with connect('SUPABASE_DB_URL') as c:
        result=ensure_sheet_organization(c)
    print(json.dumps(result,ensure_ascii=False,indent=2))
