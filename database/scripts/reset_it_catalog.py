"""Replace the five catalogs from a reviewed official-source batch. Defaults to rollback."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.database import deployment
from src.database.local_runtime import native_bin, DATA
from src.database.catalog_reset import replace_catalogs

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch",type=Path,required=True)
    parser.add_argument("--backup",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--embed",action="store_true")
    args=parser.parse_args()
    if not args.batch.is_file() or not args.backup.is_file():parser.error("Reviewed batch and full backup must exist")
    batch=json.loads(args.batch.read_text(encoding="utf-8"))
    check=subprocess.run([str(native_bin()/"pg_restore.exe"),"--list",str(args.backup)],capture_output=True)
    if check.returncode or b"TABLE DATA public books" not in check.stdout:parser.error("Unreadable full backup")
    with deployment.connect("SUPABASE_DB_URL") as conn:
        if conn.info.host not in ("127.0.0.1","localhost","::1"):raise ValueError("Local DB required")
        actual=Path(conn.execute("SHOW data_directory").fetchone()["data_directory"]).resolve()
        if actual!=DATA.resolve():raise ValueError("Unexpected local database")
        result=replace_catalogs(conn,batch,embed=args.embed)
        if args.apply:conn.commit()
        else:conn.rollback()
    result.update(committed=args.apply,backup_sha256=hashlib.sha256(args.backup.read_bytes()).hexdigest())
    args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
