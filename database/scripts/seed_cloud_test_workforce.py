"""Seed synthetic Cloud-only TEST_MANUAL workforce; no sheet/local DB writes."""
import argparse,json,random,uuid
from datetime import date,timedelta
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[2]
DEPARTMENTS=['AI데이터센터','인재경영실','업무시스템팀','인프라운영팀','데이터운영팀']
SEED=20261023

def seed(c,apply=False):
 c.execute('SELECT pg_advisory_xact_lock(763250199)')
 departments=c.execute('SELECT department_id,institution_id,name FROM growpath_live.departments WHERE name=ANY(%s) ORDER BY department_id',(DEPARTMENTS,)).fetchall()
 if len(departments)!=5:raise ValueError('Expected five target departments')
 before=c.execute('SELECT * FROM growpath_hr.employees ORDER BY employee_id').fetchall();original={x['employee_id']:x for x in before}
 counts={d['department_id']:sum(x['source_type']=='TEST_MANUAL' and x['department_id']==d['department_id'] for x in before) for d in departments}
 if any(n>20 for n in counts.values()):raise ValueError('Existing department exceeds target; never delete accounts')
 if any(x['source_type']=='TEST_MANUAL' and x['department_id'] not in counts for x in before):raise ValueError('Test accounts outside target departments need an explicit plan')
 plan={'seed':SEED,'target_test_employees':100,'add_count':sum(20-n for n in counts.values()),'departments':[{**d,'existing':counts[d['department_id']],'target':20} for d in departments]}
 if not apply:return plan
 skills=[x['skill_id'] for x in c.execute('SELECT skill_id FROM growpath_live.skill_tags ORDER BY skill_id').fetchall()]
 certs=[x['cert_id'] for x in c.execute('SELECT cert_id FROM growpath_live.certifications ORDER BY cert_id').fetchall()]
 jobs=c.execute('SELECT job_id,title FROM growpath_live.jobs ORDER BY job_id').fetchall()
 grades=c.execute("SELECT job_grade_id,institution_id,name FROM growpath_live.job_grades WHERE name IN ('일반직 2급(을)','일반직 3급','일반직 4급','일반직 5급') ORDER BY job_grade_id").fetchall()
 mappings=c.execute('SELECT job_id,skill_id FROM growpath_live.job_skills ORDER BY job_id,skill_id').fetchall()
 c.execute("SELECT setval('growpath_hr.employees_employee_id_seq',GREATEST((SELECT last_value FROM growpath_hr.employees_employee_id_seq),(SELECT COALESCE(max(employee_id),1) FROM growpath_hr.employees)),true)")
 added=[]
 for d in departments:
  did=d['department_id'];head_count=c.execute('SELECT count(*) AS n FROM growpath_hr.employees WHERE department_id=%s AND is_department_head',(did,)).fetchone()['n']
  if head_count>1:raise ValueError('Multiple existing heads')
  missing=20-counts[did]
  if not missing and head_count!=1:raise ValueError('Full department lacks one head; existing profiles preserved')
  for index in range(counts[did]+1,21):
   rng=random.Random(f'{SEED}:{did}:{index}');number=f'TM26-{did:03d}-{index:02d}'
   if c.execute('SELECT 1 FROM growpath_hr.employees WHERE employee_number=%s',(number,)).fetchone():raise ValueError('Employee number collision')
   job=rng.choice(jobs);is_head=head_count==0
   eligible=[g for g in grades if g['institution_id']==d['institution_id'] and (('2급' in g['name'] or '3급' in g['name']) if is_head else ('4급' in g['name'] or '5급' in g['name']))]
   grade=rng.choice(eligible);hire=date(2010,1,1)+timedelta(days=rng.randrange(0,5000));start=hire+timedelta(days=rng.randrange(0,(date(2026,10,23)-hire).days+1))
   name=f'가상직원_{did}_{index:02d}';description=f'[합성 가데이터] {d["name"]}의 {job["title"]} 역할을 가정한 업무 자동화 시제품. 모의 입력의 정상·실패 결과를 비교한다. 실제 직원 이력이나 검증된 역량이 아니다.'
   eid=c.execute("""INSERT INTO growpath_hr.employees(name,job_id,institution_id,employee_number,department_id,job_grade_id,is_department_head,source_type,hire_date,department_start_date,planned_project_description,is_degree_seeker,department,job_title,grade) VALUES(%s,%s,%s,%s,%s,%s,%s,'TEST_MANUAL',%s,%s,%s,%s,%s,%s,%s) RETURNING employee_id""",(name,job['job_id'],d['institution_id'],number,did,grade['job_grade_id'],is_head,hire,start,description,rng.random()<.2,d['name'],job['title'],grade['name'])).fetchone()['employee_id']
   if is_head:head_count=1
   associated=[m['skill_id'] for m in mappings if m['job_id']==job['job_id']];chosen={rng.choice(associated)} if associated else set()
   chosen.update(rng.sample([s for s in skills if s not in chosen],rng.randrange(1,4)))
   for sid in sorted(chosen):c.execute('INSERT INTO growpath_hr.employee_skills(employee_id,skill_id) VALUES(%s,%s)',(eid,sid))
   for cid in rng.sample(certs,rng.randrange(0,3)):c.execute('INSERT INTO growpath_hr.employee_certifications(employee_id,certification_id) VALUES(%s,%s)',(eid,cid))
   graduation=date(hire.year-1,2,20);enrollment=date(graduation.year-4,3,2)
   c.execute("INSERT INTO growpath_hr.employee_education_records(education_record_id,employee_id,school_name,education_level,department_name,enrollment_date,graduation_date) VALUES(%s,%s,%s,'bachelor',%s,%s,%s)",(uuid.uuid5(uuid.NAMESPACE_URL,'growpath:workforce:'+number),eid,'가상대학교',rng.choice(['컴퓨터공학과','정보통신학과','데이터과학과']),enrollment,graduation))
   added.append(eid)
 after=c.execute('SELECT * FROM growpath_hr.employees ORDER BY employee_id').fetchall()
 if any(original[x['employee_id']]!=x for x in after if x['employee_id'] in original):raise ValueError('Existing account changed')
 verification=c.execute("SELECT d.name,count(*) AS total,count(*) FILTER(WHERE e.is_department_head) AS heads FROM growpath_hr.employees e JOIN growpath_live.departments d USING(department_id) WHERE e.source_type='TEST_MANUAL' GROUP BY d.name ORDER BY d.name").fetchall()
 if len(verification)!=5 or any(x['total']!=20 or x['heads']!=1 for x in verification):raise ValueError('Workforce distribution failed')
 return {**plan,'added_ids':added,'verified_departments':verification,'original_accounts_preserved':True,'new_passwords_set':False,'local_database_modified':False}
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
 secret=dotenv_values(ROOT/'qwen_factory/.env.cloud-target')['GROWPATH_ADMIN_DB_URL']
 with psycopg.connect(secret,sslmode='require',connect_timeout=15,row_factory=dict_row,prepare_threshold=None) as c:
  c.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='60s'")
  result=seed(c,args.apply)
 print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
