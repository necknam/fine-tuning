"""Deterministic synthetic TEST_MANUAL profiles; never writes REAL_USER records."""
import hashlib,json,random
from .sheet_sync import parse_sheet

SEED=20261023

def fill_test_profiles(c,sheet_text,seed=SEED):
    rng=random.Random(seed)
    donors=parse_sheet(sheet_text)
    people=c.execute("SELECT employee_id,name,email,password_hash FROM public.employees WHERE source_type='TEST_MANUAL' ORDER BY employee_id FOR UPDATE").fetchall()
    if len(people)!=9:raise ValueError('Expected the existing nine TEST_MANUAL accounts; refusing to create or change other accounts')
    real_before=c.execute("SELECT * FROM public.employees WHERE source_type<>'TEST_MANUAL' ORDER BY employee_id").fetchall()
    jobs=c.execute('SELECT job_id,title FROM public.jobs ORDER BY job_id').fetchall()
    certs=c.execute('SELECT cert_id FROM public.certifications ORDER BY cert_id').fetchall()
    iid=c.execute("SELECT institution_id FROM public.institutions WHERE name='한국수자원공사'").fetchone()['institution_id']
    grades=[x['job_grade_id'] for x in c.execute("SELECT job_grade_id FROM public.job_grades WHERE institution_id=%s AND name=ANY(%s) ORDER BY name",(iid,['일반직 2급(을)','일반직 3급','일반직 4급','일반직 5급'])).fetchall()]
    unlisted=[x['unlisted_certifications'] for x in donors if x.get('unlisted_certifications')]
    from uuid import uuid5,NAMESPACE_URL
    manifest=[]
    for index,person in enumerate(people):
        eid=person['employee_id'];donor=donors[rng.randrange(len(donors))];education=dict(donors[rng.randrange(len(donors))]['education'])
        job=jobs[index%len(jobs)]
        department=c.execute('SELECT department_id FROM public.departments WHERE institution_id=%s AND name=%s',(iid,donor['department'])).fetchone()['department_id']
        linked=c.execute('SELECT s.skill_id,s.name FROM public.job_skills j JOIN public.skill_tags s USING(skill_id) WHERE j.job_id=%s ORDER BY s.skill_id',(job['job_id'],)).fetchall()
        if not linked:raise ValueError('Test job has no source-linked skills')
        selected=rng.sample(linked,min(3,len(linked)))
        # A synthetic work/project goal is an input assumption, not a generated recommendation.
        description=f"[가상 테스트 입력] {donor['department']}의 {job['title']} 업무를 가정한다. {selected[0]['name']}를 활용한 업무 개선 시제품을 만들고 입력·출력 예시와 점검 결과를 정리하려고 한다. 실제 직원 이력이나 구현 완료 사실이 아니다."
        c.execute("""UPDATE public.employees SET institution_id=%s,department_id=%s,job_grade_id=%s,job_id=%s,
          hire_date=%s,department_start_date=%s,is_department_head=false,is_degree_seeker=%s,
          planned_project_description=%s,unlisted_certifications=%s,department=NULL,grade=NULL,job_title=NULL,updated_at=now()
          WHERE employee_id=%s AND source_type='TEST_MANUAL'""",(iid,department,rng.choice(grades),job['job_id'],donor.get('hire_date'),donor.get('department_start_date'),bool(index%3==0),description,rng.choice(unlisted) if unlisted else None,eid))
        c.execute('DELETE FROM public.employee_skills WHERE employee_id=%s',(eid,))
        for skill in selected:c.execute('INSERT INTO public.employee_skills(employee_id,skill_id) VALUES(%s,%s)',(eid,skill['skill_id']))
        c.execute('DELETE FROM public.employee_certifications WHERE employee_id=%s',(eid,))
        certification=rng.choice(certs)['cert_id']
        c.execute('INSERT INTO public.employee_certifications(employee_id,certification_id) VALUES(%s,%s)',(eid,certification))
        # Only the deterministic test-fixture education row is replaced; other history is preserved.
        record=uuid5(NAMESPACE_URL,'growpath:synthetic-test-education:'+str(eid))
        c.execute('DELETE FROM public.employee_education_records WHERE education_record_id=%s',(record,))
        c.execute('INSERT INTO public.employee_education_records(education_record_id,employee_id,education_level,school_name,department_name,enrollment_date,graduation_date) VALUES(%s,%s,%s,%s,%s,%s,%s)',(record,eid,education['education_level'],education['school_name'],education.get('department_name'),education.get('enrollment_date'),education.get('graduation_date')))
        manifest.append({'employee_id':eid,'source_type':'TEST_MANUAL','synthetic':True,'job_id':job['job_id'],'skill_ids':[x['skill_id'] for x in selected],'cert_id':certification})
    if real_before!=c.execute("SELECT * FROM public.employees WHERE source_type<>'TEST_MANUAL' ORDER BY employee_id").fetchall():raise ValueError('Non-test employee data changed')
    after=c.execute("SELECT employee_id,name,email,password_hash FROM public.employees WHERE source_type='TEST_MANUAL' ORDER BY employee_id").fetchall()
    if people!=after:raise ValueError('Test account identity or password changed')
    return {'seed':seed,'source_sheet_sha256':hashlib.sha256(sheet_text.encode()).hexdigest(),'profiles':manifest,'real_user_rows_changed':0,'recommendations_generated':0}
