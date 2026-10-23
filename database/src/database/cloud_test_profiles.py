"""Synchronize only synthetic TEST_MANUAL profiles and required masters."""
import hashlib,json
from psycopg import sql

def sync(source,target,reader_role='growpath_evidence_reader'):
    target.execute('SELECT pg_advisory_xact_lock(763250134)')
    source.execute("SET LOCAL TIME ZONE 'UTC'");target.execute("SET LOCAL TIME ZONE 'UTC'")
    people=source.execute("SELECT employee_id FROM public.employees WHERE source_type='TEST_MANUAL' ORDER BY employee_id").fetchall()
    ids=[r['employee_id'] for r in people]
    if not ids:raise ValueError('No source test accounts')
    cloud_ids=[r['employee_id'] for r in target.execute("SELECT employee_id FROM growpath_hr.employees WHERE source_type='TEST_MANUAL'").fetchall()]
    if set(cloud_ids)-set(ids):raise ValueError('Cloud contains independently maintained test accounts. Local-to-Cloud profile overwrite is disabled; use the Cloud workforce tools.')
    collision=target.execute("SELECT employee_id FROM growpath_hr.employees WHERE employee_id=ANY(%s) AND source_type<>'TEST_MANUAL'",(ids,)).fetchall()
    if collision:raise ValueError('Cloud ID collision with a non-test account')
    def columns(name):
        return [r['column_name'] for r in source.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s AND is_generated='NEVER' ORDER BY ordinal_position",(name,)).fetchall()]
    def upsert(schema,name,rows,key,cols):
        query=sql.SQL('INSERT INTO {}.{} ({}) VALUES ({}) ON CONFLICT({}) DO UPDATE SET {}').format(sql.Identifier(schema),sql.Identifier(name),sql.SQL(',').join(map(sql.Identifier,cols)),sql.SQL(',').join(sql.Placeholder() for _ in cols),sql.Identifier(key),sql.SQL(',').join(sql.SQL('{}=EXCLUDED.{}').format(sql.Identifier(k),sql.Identifier(k)) for k in cols if k!=key))
        for row in rows:target.execute(query,[row[k] for k in cols])
    for name,key in [('institutions','institution_id'),('departments','department_id'),('job_grades','job_grade_id')]:
        cols=columns(name)
        rows=source.execute(sql.SQL('SELECT {} FROM public.{} ORDER BY {}').format(sql.SQL(',').join(map(sql.Identifier,cols)),sql.Identifier(name),sql.Identifier(key))).fetchall()
        upsert('growpath_live',name,rows,key,cols)
    cols=columns('employees')
    employees=source.execute(sql.SQL("SELECT {} FROM public.employees WHERE source_type='TEST_MANUAL' ORDER BY employee_id").format(sql.SQL(',').join(map(sql.Identifier,cols)))).fetchall()
    upsert('growpath_hr','employees',employees,'employee_id',cols)
    counts={'employees':len(employees)}
    for name in ['employee_skills','employee_certifications','employee_education_records']:
        cols=columns(name)
        rows=source.execute(sql.SQL('SELECT {} FROM public.{} WHERE employee_id=ANY(%s) ORDER BY 1,2').format(sql.SQL(',').join(map(sql.Identifier,cols)),sql.Identifier(name)),(ids,)).fetchall()
        target.execute(sql.SQL('DELETE FROM growpath_hr.{} WHERE employee_id=ANY(%s)').format(sql.Identifier(name)),(ids,))
        for row in rows:
            target.execute(sql.SQL('INSERT INTO growpath_hr.{} ({}) VALUES ({})').format(sql.Identifier(name),sql.SQL(',').join(map(sql.Identifier,cols)),sql.SQL(',').join(sql.Placeholder() for _ in cols)),[row[k] for k in cols])
        checked=target.execute(sql.SQL('SELECT {} FROM growpath_hr.{} WHERE employee_id=ANY(%s) ORDER BY 1,2').format(sql.SQL(',').join(map(sql.Identifier,cols)),sql.Identifier(name)),(ids,)).fetchall()
        if rows!=checked:raise ValueError('Cloud test relation mismatch: '+name)
        counts[name]=len(rows)
    checked=target.execute(sql.SQL('SELECT {} FROM growpath_hr.employees WHERE employee_id=ANY(%s) ORDER BY employee_id').format(sql.SQL(',').join(map(sql.Identifier,columns('employees')))),(ids,)).fetchall()
    if employees!=checked:raise ValueError('Cloud test employee mismatch')
    if target.execute("SELECT count(*) AS n FROM growpath_hr.employees WHERE source_type<>'TEST_MANUAL'").fetchone()['n']:raise ValueError('Unexpected non-test employee in Cloud HR')
    role=sql.Identifier(reader_role)
    target.execute(sql.SQL('GRANT USAGE ON SCHEMA growpath_hr TO {}').format(role))
    visible=[k for k in columns('employees') if k not in ('password_hash','email')]
    target.execute(sql.SQL('GRANT SELECT ({}) ON growpath_hr.employees TO {}').format(sql.SQL(',').join(map(sql.Identifier,visible)),role))
    target.execute('DROP POLICY IF EXISTS test_profile_read ON growpath_hr.employees')
    target.execute(sql.SQL("CREATE POLICY test_profile_read ON growpath_hr.employees FOR SELECT TO {} USING(source_type='TEST_MANUAL')").format(role))
    for name in ['employee_skills','employee_certifications','employee_education_records']:
        target.execute(sql.SQL('GRANT SELECT ON growpath_hr.{} TO {}').format(sql.Identifier(name),role))
        target.execute(sql.SQL('DROP POLICY IF EXISTS test_profile_read ON growpath_hr.{}').format(sql.Identifier(name)))
        target.execute(sql.SQL("CREATE POLICY test_profile_read ON growpath_hr.{} FOR SELECT TO {} USING(EXISTS(SELECT 1 FROM growpath_hr.employees e WHERE e.employee_id={}.employee_id AND e.source_type='TEST_MANUAL'))").format(sql.Identifier(name),role,sql.Identifier(name)))
    return {'source_type':'TEST_MANUAL','employee_ids':ids,'counts':counts,'real_user_rows_copied':0,'recommendations_generated':0,'password_hash_exposed_to_reader':False}
