"""Full PostgreSQL logical backup and non-destructive restore into a NEW database."""
import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import quote
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from dotenv import dotenv_values
from .deployment import ROOT, connect
from .local_runtime import native_bin


def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def inventory(c):
    schemas=("public","regulations","growpath_meta","growpath_legacy")
    tables=c.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname=ANY(%s) ORDER BY 1,2",(list(schemas),)).fetchall()
    counts={}
    for row in tables:
        counts[row["schemaname"]+"."+row["tablename"]]=c.execute(sql.SQL("SELECT count(*) AS n FROM {}.{}").format(sql.Identifier(row["schemaname"]),sql.Identifier(row["tablename"]))).fetchone()["n"]
    constraints=c.execute("SELECT n.nspname AS schema,t.relname AS table_name,c.conname,pg_get_constraintdef(c.oid) AS definition FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname=ANY(%s) ORDER BY 1,2,3",(list(schemas),)).fetchall()
    views=c.execute("SELECT schemaname,viewname FROM pg_views WHERE schemaname=ANY(%s) ORDER BY 1,2",(list(schemas),)).fetchall()
    ext=c.execute("SELECT extname,extversion FROM pg_extension ORDER BY extname").fetchall()
    return {"tables":counts,"constraints":constraints,"views":views,"extensions":ext}


def command(binary, args, env, log):
    with log.open("ab") as f:
        result=subprocess.run([str(binary),*map(str,args)],env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=f,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
    if result.returncode:
        raise RuntimeError("PostgreSQL command failed; inspect " + str(log))


def backup(output):
    output=output.resolve()
    if output.exists() or output.with_suffix(".manifest.json").exists():
        raise ValueError("Backup already exists; choose a new filename")
    output.parent.mkdir(parents=True,exist_ok=True)
    log=ROOT/"data/local_db/transfer.log";log.parent.mkdir(parents=True,exist_ok=True)
    with connect("SUPABASE_DB_URL") as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        snapshot=c.execute("SELECT pg_export_snapshot() AS id").fetchone()["id"]
        content=inventory(c)
        env=os.environ.copy()
        env.update(PGHOST=c.info.host,PGPORT=str(c.info.port),PGUSER=c.info.user,PGPASSWORD=c.info.password,PGDATABASE=c.info.dbname,PGSSLMODE="disable")
        binary=native_bin();env["PATH"]=str(binary)+os.pathsep+env.get("PATH","")
        command(binary/"pg_dump.exe",["--format=custom","--no-owner","--no-acl","--snapshot="+snapshot,"--file="+str(output)],env,log)
        manifest={"format":1,"created_at":datetime.now(timezone.utc).isoformat(),"database":c.info.dbname,"server_version":c.execute("SHOW server_version").fetchone()["server_version"],"archive":output.name,"sha256":digest(output),"bytes":output.stat().st_size,"inventory":content,"scope":"All schemas, table data, vectors, functions, views and sequences in this database; cluster roles/passwords and external PDF/storage files are separate."}
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    return {"status":"PASS","archive":str(output),"bytes":manifest["bytes"],"tables":len(content["tables"])}


def comparable_inventory(value):
    value=json.loads(json.dumps(value))
    for constraint in value["constraints"]:
        text=constraint["definition"]
        text=re.sub(r"\(('[^']*'::character varying)\)::text",r"\1",text)
        text=re.sub(r"\((ARRAY\[[^\]]*\])\)::text\[\]",r"\1",text)
        constraint["definition"]=text
    return value


def restore(args):
    archive=args.archive.resolve();manifest=json.loads(archive.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    if digest(archive)!=manifest["sha256"]:
        raise ValueError("Backup SHA-256 mismatch")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}",args.database):
        raise ValueError("Use a lowercase PostgreSQL database identifier")
    envfile=ROOT/".env.local"
    if args.write_config and envfile.exists():
        raise ValueError(".env.local already exists; preserved. Omit --write-config or use a fresh checkout")
    values=dotenv_values(envfile) if envfile.exists() else {}
    password=os.getenv("POSTGRES_PASSWORD") or values.get("POSTGRES_PASSWORD") or getpass.getpass("PostgreSQL password (not printed): ")
    binary=Path(args.pg_bin).resolve() if args.pg_bin else native_bin()
    if not (binary/"pg_restore.exe").is_file():
        raise ValueError("Run scripts/install_postgres.ps1 first or specify --pg-bin")
    env=os.environ.copy();env.update(PGHOST=args.host,PGPORT=str(args.port),PGUSER=args.user,PGPASSWORD=password,PGSSLMODE="disable")
    env["PATH"]=str(binary)+os.pathsep+env.get("PATH","")
    log=ROOT/"data/local_db/transfer.log";log.parent.mkdir(parents=True,exist_ok=True)
    if args.verify_only and (args.initialize or args.write_config):raise ValueError("Verification cannot initialize or write config")
    if args.initialize:
        if args.host!="127.0.0.1":raise ValueError("Initialization is local only")
        data=(ROOT/"data/local_db/postgres").resolve()
        if data.exists():raise ValueError("PostgreSQL data directory exists; preserved")
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",delete=False) as f:
            secret=Path(f.name);f.write(password+chr(10))
        try:
            command(binary/"initdb.exe",["-D",data,"-U",args.user,"--auth-host=scram-sha-256","--auth-local=scram-sha-256","--encoding=UTF8","--locale=C","--pwfile="+str(secret)],env,log)
        finally:secret.unlink(missing_ok=True)
        with (data/"postgresql.conf").open("a",encoding="utf-8") as f:
            f.write(chr(10)+"listen_addresses='127.0.0.1'"+chr(10)+"port="+str(args.port)+chr(10))
        command(binary/"pg_ctl.exe",["-D",data,"-l",data.parent/"postgres.log","-w","start"],env,log)
    params={"host":args.host,"port":args.port,"user":args.user,"password":password,"dbname":"postgres","row_factory":dict_row,"connect_timeout":10}
    with psycopg.connect(**params,autocommit=True) as admin:
        version=int(admin.execute("SHOW server_version_num").fetchone()["server_version_num"])
        if version//10000!=17:raise ValueError("PostgreSQL 17 required")
        if not args.verify_only and admin.execute("SELECT 1 FROM pg_database WHERE datname=%s",(args.database,)).fetchone():
            raise ValueError("Destination database exists; not overwriting")
        if not args.verify_only:admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0 ENCODING 'UTF8'").format(sql.Identifier(args.database)))
    env["PGDATABASE"]=args.database
    if not args.verify_only:command(binary/"pg_restore.exe",["--exit-on-error","--single-transaction","--no-owner","--no-acl","--dbname="+args.database,archive],env,log)
    params["dbname"]=args.database
    with psycopg.connect(**params) as c:
        actual=inventory(c)
        if comparable_inventory(actual)!=comparable_inventory(manifest["inventory"]):raise RuntimeError("Restored inventory differs from backup; database preserved for inspection")
        vector_checks={}
        for schema,table in [("public","learning_resource_embeddings"),("regulations","rag_chunk_embeddings")]:
            result=c.execute(sql.SQL("SELECT embedding <=> embedding AS distance FROM {}.{} WHERE embedding IS NOT NULL LIMIT 1").format(sql.Identifier(schema),sql.Identifier(table))).fetchone()
            vector_checks[schema+"."+table]=result is None or abs(result["distance"])<1e-5
        if not all(vector_checks.values()):raise RuntimeError("Vector similarity check failed")
    result={"status":"PASS","database":args.database,"tables":len(actual["tables"]),"rows":sum(actual["tables"].values()),"constraints":len(actual["constraints"]),"vector_checks":vector_checks,"archive_sha256":manifest["sha256"]}
    (ROOT/"data/local_db/restore_verification.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    if args.write_config:
        url="postgresql://"+quote(args.user,safe="")+":"+quote(password,safe="")+"@"+args.host+":"+str(args.port)+"/"+args.database
        envfile.write_text("POSTGRES_PASSWORD="+json.dumps(password)+chr(10)+"POSTGRES_BIN_DIR="+binary.as_posix()+chr(10)+"SUPABASE_DB_URL="+json.dumps(url)+chr(10),encoding="utf-8")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest="action",required=True)
    p=sub.add_parser("backup");p.add_argument("--output",type=Path,required=True)
    p=sub.add_parser("restore");p.add_argument("--archive",type=Path,required=True);p.add_argument("--database",default="growpath");p.add_argument("--host",default="127.0.0.1");p.add_argument("--port",type=int,default=55433);p.add_argument("--user",default="postgres");p.add_argument("--pg-bin");p.add_argument("--initialize",action="store_true");p.add_argument("--write-config",action="store_true");p.add_argument("--verify-only",action="store_true")
    args=parser.parse_args()
    try:print(json.dumps(backup(args.output) if args.action=="backup" else restore(args),ensure_ascii=False,indent=2))
    except Exception as error:
        print("FAILED: "+type(error).__name__)
        if isinstance(error,(ValueError,RuntimeError)):print(str(error))
        return 1
    return 0

if __name__=="__main__":raise SystemExit(main())
