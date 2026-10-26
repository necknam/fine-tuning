"""Fill only the existing TEST_MANUAL accounts with seeded synthetic sheet combinations."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.database.deployment import connect
from src.database.sheet_sync import fetch_sheet
from src.database.test_profiles import fill_test_profiles,SEED
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');p.add_argument('--seed',type=int,default=SEED);args=p.parse_args()
    text=fetch_sheet()
    with connect('SUPABASE_DB_URL') as c:
        result=fill_test_profiles(c,text,args.seed)
        if not args.apply:c.rollback()
    result['applied']=args.apply
    print(json.dumps(result,ensure_ascii=False,indent=2))
