"""Idempotent registration of the approved fictional sheet organization."""
INSTITUTION_ID='bf3c2943-9f96-549e-bef7-88d85936e63c'
DEPARTMENTS=(
 ('AIHQ','AI본부',None),('MGMT','경영부문',None),
 ('AIINNOV','AI혁신처','AIHQ'),('DIGITAL','디지털관리처','AIHQ'),
 ('AIDATA','AI데이터센터','AIHQ'),('HR','인재경영실','MGMT'),
 ('BIZ','업무시스템팀','DIGITAL'),('INFRA','인프라운영팀','DIGITAL'),
 ('DATA','데이터운영팀','AIDATA'),
)
GRADES=('일반직 2급(을)','일반직 3급','일반직 4급','일반직 5급')

def ensure_sheet_organization(c):
    """Caller owns transaction. Abort on conflicting codes; never reassign staff."""
    c.execute('SELECT pg_advisory_xact_lock(763250131)')
    institution=c.execute('SELECT name FROM public.institutions WHERE institution_id=%s',(INSTITUTION_ID,)).fetchone()
    if not institution or institution['name']!='한국수자원공사':
        raise ValueError('Confirmed sheet institution is missing or has a different name')
    ids={}
    for code,name,parent in DEPARTMENTS:
        parent_id=ids.get(parent)
        row=c.execute('SELECT department_id,name,parent_department_id FROM public.departments WHERE institution_id=%s AND department_code=%s FOR UPDATE',(INSTITUTION_ID,code)).fetchone()
        if row:
            if row['name']!=name or row['parent_department_id']!=parent_id:
                raise ValueError('Existing department conflicts with approved sheet organization: '+code)
        else:
            row=c.execute('INSERT INTO public.departments(institution_id,department_code,name,parent_department_id) VALUES(%s,%s,%s,%s) RETURNING department_id',(INSTITUTION_ID,code,name,parent_id)).fetchone()
        ids[code]=row['department_id']
    grades={}
    for order,name in enumerate(GRADES,2):
        c.execute('INSERT INTO public.job_grades(institution_id,name,sort_order) VALUES(%s,%s,%s) ON CONFLICT(institution_id,name) DO NOTHING',(INSTITUTION_ID,name,order))
        grades[name]=c.execute('SELECT job_grade_id FROM public.job_grades WHERE institution_id=%s AND name=%s',(INSTITUTION_ID,name)).fetchone()['job_grade_id']
    return {'departments':ids,'grades':grades,'employees_reassigned':False}
