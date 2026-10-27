"""Reconstruct synthetic local profiles; does not claim identity with lost Cloud data."""
import argparse,json,random,sys,uuid
from datetime import date,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.database.deployment import connect
from src.database.organization_setup import ensure_sheet_organization
SEED=20261023
DEPARTMENTS=['AI데이터센터','인재경영실','업무시스템팀','인프라운영팀','데이터운영팀']

def seed(c,apply=False):
 if c.info.host not in ('127.0.0.1','localhost','::1'):raise ValueError('Local DB only')
 c.execute('SELECT pg_advisory_xact_lock(763250199)')
 real=c.execute("SELECT * FROM public.employees WHERE source_type<>'TEST_MANUAL' ORDER BY employee_id").fetchall()
 old=c.execute("SELECT * FROM public.employees WHERE source_type='TEST_MANUAL' ORDER BY employee_id").fetchall()
 if len(old)==100:
  distribution=c.execute("SELECT d.name,count(*) AS total,count(*) FILTER(WHERE e.is_department_head) AS heads FROM public.employees e JOIN public.departments d USING(department_id) WHERE e.source_type='TEST_MANUAL' GROUP BY d.name ORDER BY d.name").fetchall()
  if len(distribution)!=5 or any(r['total']!=20 or r['heads']!=1 or r['name'] not in DEPARTMENTS for r in distribution):raise ValueError('Existing 100 differ; do not overwrite')
  return {'status':'ALREADY_COMPLETE','test_employees':100,'departments':distribution,'modified':False}
 if len(old)!=9:raise ValueError('Expected nine old local test accounts or completed 100')
 plan={'seed':SEED,'existing_test_accounts':9,'new_test_accounts':91,'target_test_accounts':100,'existing_other_accounts':len(real),'cloud_exact_restore':False,'synthetic':True}
 if not apply:return plan
 ensure_sheet_organization(c)
 deps=c.execute('SELECT * FROM public.departments WHERE name=ANY(%s)',(DEPARTMENTS,)).fetchall()
 if len(deps)!=5:raise ValueError('Five departments required')
 deps.sort(key=lambda x:DEPARTMENTS.index(x['name']))
 jobs=c.execute('SELECT job_id,title FROM public.jobs ORDER BY job_id').fetchall()
 skills=[r['skill_id'] for r in c.execute('SELECT skill_id FROM public.skill_tags ORDER BY skill_id').fetchall()]
 certs=[r['cert_id'] for r in c.execute('SELECT cert_id FROM public.certifications ORDER BY cert_id').fetchall()]
 grades=c.execute("SELECT * FROM public.job_grades WHERE name IN ('일반직 2급(을)','일반직 3급','일반직 4급','일반직 5급') ORDER BY job_grade_id").fetchall()
 links=c.execute('SELECT job_id,skill_id FROM public.job_skills ORDER BY 1,2').fetchall()
 identities={r['employee_id']:(r['name'],r['email'],r['password_hash']) for r in old}
 c.execute("SELECT setval(pg_get_serial_sequence('public.employees','employee_id'),GREATEST((SELECT max(employee_id) FROM public.employees),1),true)")
 # Distribute old identities first; no existing account or history is deleted.
 assignment={(i%5,i//5+1):r for i,r in enumerate(old)}
 for di,d in enumerate(deps):
  for index in range(1,21):
   rng=random.Random(f'{SEED}:{d["department_id"]}:{index}')
   person=assignment.get((di,index));job=rng.choice(jobs);head=index==1
   eligible=[g for g in grades if g['institution_id']==d['institution_id'] and (('2급' in g['name'] or '3급' in g['name']) if head else ('4급' in g['name'] or '5급' in g['name']))]
   grade=rng.choice(eligible);hire=date(2010,1,1)+timedelta(days=rng.randrange(5000));start=hire+timedelta(days=rng.randrange((date(2026,10,23)-hire).days+1))
   number=(person['employee_number'] if person else None) or f'TM26-{d["department_id"]:03d}-{index:02d}'
   description=f'[합성 가데이터] {d["name"]}의 {job["title"]} 역할을 가정한 업무 자동화 시제품. 모의 입력의 정상·실패 결과를 비교한다. 실제 직원 이력이나 검증된 역량이 아니다.'
   values=(job['job_id'],d['institution_id'],number,d['department_id'],grade['job_grade_id'],head,hire,start,description,rng.random()<.2,d['name'],job['title'],grade['name'])
   if person:
    eid=person['employee_id']
    c.execute('UPDATE public.employees SET job_id=%s,institution_id=%s,employee_number=%s,department_id=%s,job_grade_id=%s,is_department_head=%s,hire_date=%s,department_start_date=%s,planned_project_description=%s,is_degree_seeker=%s,department=%s,job_title=%s,grade=%s WHERE employee_id=%s',values+(eid,))
   else:
    eid=c.execute("INSERT INTO public.employees(job_id,institution_id,employee_number,department_id,job_grade_id,is_department_head,hire_date,department_start_date,planned_project_description,is_degree_seeker,department,job_title,grade,name,source_type) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'TEST_MANUAL') RETURNING employee_id",values+(f'가상직원_{d["department_id"]}_{index:02d}',)).fetchone()['employee_id']
   associated=[r['skill_id'] for r in links if r['job_id']==job['job_id']]
   chosen={rng.choice(associated)} if associated else set()
   chosen.update(rng.sample([s for s in skills if s not in chosen],rng.randrange(1,4)))
   for sid in sorted(chosen):c.execute('INSERT INTO public.employee_skills(employee_id,skill_id) VALUES(%s,%s) ON CONFLICT DO NOTHING',(eid,sid))
   for cid in rng.sample(certs,rng.randrange(3)):c.execute('INSERT INTO public.employee_certifications(employee_id,certification_id) VALUES(%s,%s) ON CONFLICT DO NOTHING',(eid,cid))
   grad=date(hire.year-1,2,20)
   c.execute("INSERT INTO public.employee_education_records(education_record_id,employee_id,school_name,education_level,department_name,enrollment_date,graduation_date) VALUES(%s,%s,'가상대학교','bachelor',%s,%s,%s)",(uuid.uuid5(uuid.NAMESPACE_URL,'growpath:local-reconstructed:'+str(eid)),eid,rng.choice(['컴퓨터공학과','정보통신학과','데이터과학과']),date(grad.year-4,3,2),grad))
 after=c.execute("SELECT * FROM public.employees WHERE source_type<>'TEST_MANUAL' ORDER BY employee_id").fetchall()
 if after!=real:raise ValueError('Non-test employees changed')
 for r in c.execute("SELECT * FROM public.employees WHERE source_type='TEST_MANUAL'").fetchall():
  if r['employee_id'] in identities and identities[r['employee_id']]!=(r['name'],r['email'],r['password_hash']):raise ValueError('Existing identity changed')
 groups=c.execute("SELECT d.name,count(*) AS total,count(*) FILTER(WHERE e.is_department_head) AS heads FROM public.employees e JOIN public.departments d USING(department_id) WHERE e.source_type='TEST_MANUAL' GROUP BY d.name ORDER BY d.name").fetchall()
 if len(groups)!=5 or any(r['total']!=20 or r['heads']!=1 for r in groups):raise ValueError('Distribution failed')
 return {**plan,'status':'PASS','departments':groups,'non_test_rows_unchanged':True,'old_ids_and_credentials_preserved':True,'new_passwords_set':False,'total_employees':100+len(real)}

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');args=p.parse_args()
 with connect('SUPABASE_DB_URL') as c:result=seed(c,args.apply)
 print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
