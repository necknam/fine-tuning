"""Manage the native PostgreSQL instance whose files belong to this project."""
from pathlib import Path
import argparse,json,os,subprocess
from dotenv import load_dotenv
from psycopg.conninfo import conninfo_to_dict
from src.database.deployment import ROOT,connect

DATA=ROOT/'data/local_db/postgres'

def native_bin():
    load_dotenv(ROOT/'.env.local',override=True)
    return Path(os.getenv('POSTGRES_BIN_DIR',str(Path.home()/'miniforge3/envs/growpath_db/Library/bin')))

def run_control(command):
    binary=native_bin()/'pg_ctl.exe'
    if not binary.is_file() or not (DATA/'PG_VERSION').is_file():
        raise ValueError('Native PostgreSQL runtime or restored data directory is missing.')
    if (DATA/'PG_VERSION').read_text(encoding='ascii').strip()!='17':
        raise ValueError('PostgreSQL 17 data directory required; no automatic conversion.')
    args=[str(binary),'-D',str(DATA)]
    if command=='start':args+=['-l',str(DATA.parent/'postgres.log'),'-w','start']
    elif command=='stop':args+=['-m','fast','-w','stop']
    else:args+=['status']
    env=os.environ.copy();env['PATH']=str(binary.parent)+';'+env.get('PATH','')
    # File handles prevent Windows server descendants keeping a PIPE open forever.
    with (DATA.parent/'control.log').open('ab') as log:
        p=subprocess.run(args,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,
            timeout=45,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    return p.returncode


def data_directory(conn):
    # PostgreSQL on Windows can return its OS path in the ANSI code page even
    # when database text is UTF-8. Fetch bytes without a UTF-8 text loader.
    hex_path = conn.execute("SELECT encode(pg_catalog.textsend(current_setting('data_directory')), 'hex') AS path_hex").fetchone()['path_hex']
    raw = bytes.fromhex(hex_path)
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        if os.name != 'nt': raise
        return raw.decode('mbcs')


def status():
    running=run_control('status')==0
    result={'running':running,'docker_required':False,'data_directory':str(DATA)}
    if running:
        with connect('SUPABASE_DB_URL') as c:
            c.execute('SET TRANSACTION READ ONLY')
            actual=data_directory(c)
            if Path(actual).resolve()!=DATA.resolve():raise ValueError('Application points at another PostgreSQL instance.')
            result.update(database=c.info.dbname,host=c.info.host,port=c.info.port,
                          server_version=c.execute('SHOW server_version').fetchone()['server_version'])
    return result

def backup(output):
    output=output.resolve()
    if output.exists():raise ValueError('Backup destination exists; not overwriting.')
    with connect('SUPABASE_DB_URL') as c:
        if Path(data_directory(c)).resolve()!=DATA.resolve():
            raise ValueError('Refusing to back up an unexpected database.')
    params=conninfo_to_dict(os.environ['SUPABASE_DB_URL']);env=os.environ.copy()
    for key,field in [('PGHOST','host'),('PGPORT','port'),('PGUSER','user'),('PGPASSWORD','password'),('PGDATABASE','dbname')]:
        env[key]=params[field]
    env['PGSSLMODE']='disable';env['PATH']=str(native_bin())+';'+env.get('PATH','')
    output.parent.mkdir(parents=True,exist_ok=True)
    with (DATA.parent/'control.log').open('ab') as log:
        p=subprocess.run([str(native_bin()/'pg_dump.exe'),'--format=custom','--no-owner','--no-acl','--file='+str(output)],
            env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if p.returncode:raise RuntimeError('Native backup failed; inspect data/local_db/control.log.')
    return {'status':'PASS','backup':str(output),'bytes':output.stat().st_size}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    for name in ('start','stop','status'):commands.add_parser(name)
    p=commands.add_parser('backup');p.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='backup':result=backup(args.output)
    else:
        if args.command=='start' and run_control('status')!=0:
            if run_control('start')!=0:raise RuntimeError('Native DB start failed; inspect data/local_db/postgres.log.')
        if args.command=='stop' and run_control('status')==0:
            if run_control('stop')!=0:raise RuntimeError('Native DB stop failed; inspect data/local_db/control.log.')
        result=status()
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
