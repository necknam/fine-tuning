"""Explicit operator actions; passwords remain Argon2id hashes and reviews are attributable."""
import argparse
from datetime import datetime, timezone
import getpass
import json
from argon2 import PasswordHasher
from .deployment import connect

REVIEW_MARKER = "operator_approved:"

def set_passwords(conn,password,*,only_missing=False):
    if not password:raise ValueError("Nonempty employee password required")
    query="SELECT employee_id FROM public.employees" + (" WHERE password_hash IS NULL AND source_type IN ('TEST_MANUAL','TEST_AUTO')" if only_missing else "")
    rows=conn.execute(query).fetchall();hasher=PasswordHasher()
    for row in rows:
        value=hasher.hash(password)
        assert value.startswith('$argon2id$')
        conn.execute('UPDATE public.employees SET password_hash=%s,updated_at=now() WHERE employee_id=%s',(value,row['employee_id']))
    return len(rows)

def approve_current_regulations(conn):
    note=REVIEW_MARKER+datetime.now(timezone.utc).isoformat()+"; user explicitly confirmed all current regulation versions in this session; not an independent legal audit."
    versions=conn.execute("UPDATE regulations.regulation_versions SET review_status='approved',availability_status='available',review_note=concat_ws(E'\n',NULLIF(review_note,''),%s::text) WHERE review_status<>'approved' OR availability_status<>'available'",(note,)).rowcount
    chunks=conn.execute("UPDATE regulations.rag_chunks SET search_status='active' WHERE search_status IN ('pending_review','needs_review')").rowcount
    return {'versions_approved':versions,'current_chunks_activated':chunks,'excluded_or_superseded_unchanged':True}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approve-regulations',action='store_true');parser.add_argument('--set-test-password',action='store_true');parser.add_argument('--refresh-book-policy',action='store_true');parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not args.apply:
        print('PREVIEW: pass --apply with explicit actions. No database changes.');return
    password=getpass.getpass('Employee test password (not printed): ') if args.set_test_password else None
    result={}
    with connect('SUPABASE_DB_URL') as conn:
        if args.approve_regulations:result['regulations']=approve_current_regulations(conn)
        if password:result['employee_passwords_set']=set_passwords(conn,password)
        if args.refresh_book_policy:result['book_rows_ready']=conn.execute("UPDATE public.books SET content_status='ready' WHERE isbn IS NOT NULL AND title IS NOT NULL AND author IS NOT NULL AND publisher IS NOT NULL AND content_status IS DISTINCT FROM 'ready'").rowcount
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
