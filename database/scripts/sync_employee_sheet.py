"""Validation preview only. Real sheet data loading is not currently authorized."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.database.deployment import connect
from src.database.sheet_sync import fetch_sheet,synchronize

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    args=parser.parse_args()
    text=fetch_sheet()
    with connect('SUPABASE_DB_URL') as c:
        result=synchronize(c,text,apply=False)
        c.rollback()
    print(json.dumps(result,ensure_ascii=False,indent=2))
