"""Validate the fixed employee sheet and synchronize supplied fields atomically."""
import csv,hashlib,io,re
from datetime import date
from uuid import UUID,uuid5
import httpx
from psycopg import sql

SHEET_ID='1Rt2zvnjizTrMyI4RPdBcMrO6mR_EnbdMahnXjRKdabw'
INPUT_GID=794346946
EDUCATION={'중학교 이하':'middle_school_or_lower','고등학교':'high_school','전문학사':'associate','학사':'bachelor','석사':'master','박사':'doctorate','기타':'other'}
NAMESPACE=UUID('06dc65ce-96bd-54e5-8401-6f4071389c03')

def normalize(value):return re.sub(r'[\s★*]+','',value)

def fetch_sheet():
    response=httpx.get(f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/export',
        params={'format':'csv','gid':INPUT_GID},timeout=30,follow_redirects=True)
    response.raise_for_status()
    if 'text/csv' not in response.headers.get('content-type','') or len(response.content)>1000000:
        raise ValueError('시트 CSV 형식·접근 권한을 확인하세요.')
    return response.text

def parse_sheet(text):
    rows=list(csv.reader(io.StringIO(text.lstrip('\ufeff'))))
    labels={}
    for row in rows:
        if row and normalize(row[0]):
            key=normalize(row[0])
            if key in labels:raise ValueError('시트 항목명이 중복되었습니다: '+row[0])
            labels[key]=row
    def value(label,col,required=False):
        row=labels.get(normalize(label),[])
        result=row[col].strip() if len(row)>col else ''
        if required and not result:raise ValueError(f'{chr(65+col)}열 필수 항목 누락: {label}')
        return result
    result=[]
    for col in range(3,8):
        raw=value('바꿀 계정 번호',col,True)
        if not raw.isdecimal() or not 0<int(raw)<=2147483647:raise ValueError('계정 번호 형식 오류')
        item={'employee_id':int(raw),'expected_name':value('기존 계정 이름',col,True),
              'name':value('이름',col,True),'institution':value('기관',col,True),
              'department':value('소속 부서',col,True),'grade':value('직급',col,True),
              'job':value('직무',col,True),'position':value('직책',col,True)}
        if item['position'] not in ('부서장','일반 직원'):raise ValueError('직책 선택 오류')
        item['is_department_head']=item['position']=='부서장'
        for label,key in [('계정 이메일','email'),('사번','employee_number'),('목록에 없는 자격','unlisted_certifications'),('본인 업무 설명','planned_project_description')]:
            textvalue=value(label,col)
            if textvalue:item[key]=textvalue
        degree=value('학위 취득 희망',col)
        if degree:
            if degree not in ('예','아니오'):raise ValueError('학위 취득 희망 선택 오류')
            item['is_degree_seeker']=degree=='예'
        for label,key in [('입사일','hire_date'),('현 부서 시작일','department_start_date'),('입학일','enrollment_date'),('졸업일','graduation_date')]:
            raw=value(label,col)
            if raw:
                try:parsed=date.fromisoformat(raw)
                except ValueError:raise ValueError(f'{label}: YYYY-MM-DD 형식이 필요합니다.') from None
                if parsed.isoformat()!=raw:raise ValueError('날짜 형식 오류: '+label)
                item[key]=parsed
        for prefix,key,cap in [('보유 기술','skills',5),('보유 자격','certifications',3)]:
            names=[value(prefix+str(i),col) for i in range(1,cap+1)]
            names=[n for n in names if n]
            if '없음' in names and len(set(names))>1:raise ValueError(prefix+' 없음과 실제 항목이 함께 선택됐습니다.')
            if names:item[key]=[] if names==['없음'] or set(names)=={'없음'} else sorted(set(names))
        level=value('최종 학력',col);school=value('학교명',col)
        if level or school or 'enrollment_date' in item or 'graduation_date' in item:
            if level not in EDUCATION or not school:raise ValueError('학력과 학교명을 함께 입력하세요.')
            item['education']={'education_level':EDUCATION[level],'school_name':school}
            major=value('학과',col)
            if major:item['education']['department_name']=major
            for key in ('enrollment_date','graduation_date'):
                if key in item:item['education'][key]=item.pop(key)
        result.append(item)
    if len({x['employee_id'] for x in result})!=5:raise ValueError('계정 번호가 중복되었습니다.')
    return result

def table(schema,name):
    if schema not in ('public','growpath_hr','growpath_live'):raise ValueError('Unsupported schema')
    return sql.Identifier(schema,name)

def plan_sync(c,items,employee_schema='public',master_schema='public'):
    plans=[]
    def one(name,column,value,extra=None):
        stmt=sql.SQL('SELECT * FROM {} WHERE {}=%s').format(table(master_schema,name),sql.Identifier(column))
        args=[value]
        if extra:stmt+=sql.SQL(' AND institution_id=%s');args.append(extra)
        rows=c.execute(stmt,args).fetchall()
        if len(rows)!=1:raise ValueError('최신 DB 목록에서 한 항목으로 확인되지 않습니다: '+name+' / '+str(value))
        return rows[0]
    for item in items:
        eid=item['employee_id']
        old=c.execute(sql.SQL('SELECT * FROM {} WHERE employee_id=%s FOR UPDATE').format(table(employee_schema,'employees')),(eid,)).fetchone()
        if not old:raise ValueError(f'기존 계정 {eid}가 없습니다. 신규 계정을 자동 생성하지 않습니다.')
        if old['name'] not in (item['expected_name'],item['name']):raise ValueError(f'계정 {eid}의 기존 이름이 일치하지 않습니다.')
        iid=one('institutions','name',item['institution'])['institution_id']
        dept=one('departments','name',item['department'],iid)
        grade=one('job_grades','name',item['grade'],iid)
        if item['grade'] not in ('일반직 2급(을)','일반직 3급','일반직 4급','일반직 5급'):raise ValueError('직급은 2~5급이어야 합니다.')
        payload={k:item[k] for k in ('name','email','employee_number','is_department_head','is_degree_seeker','hire_date','department_start_date','unlisted_certifications','planned_project_description') if k in item}
        payload.update(institution_id=iid,department_id=dept['department_id'],job_grade_id=grade['job_grade_id'],
            job_id=None if item['job']=='해당 없음' else one('jobs','title',item['job'])['job_id'],source_type='REAL_USER')
        merged={**old,**payload}
        if merged.get('hire_date') and merged.get('department_start_date') and merged['department_start_date']<merged['hire_date']:raise ValueError('부서 시작일은 입사일보다 빠를 수 없습니다.')
        related={}
        for key,name,titlecol,idcol in [('skills','skill_tags','name','skill_id'),('certifications','certifications','title','cert_id')]:
            if key in item:related[key]=[one(name,titlecol,n)[idcol] for n in item[key]]
        edu=item.get('education')
        if edu:
            edu=dict(edu)
            existing=c.execute(sql.SQL('SELECT * FROM {} WHERE employee_id=%s AND school_name=%s AND education_level=%s ORDER BY education_record_id').format(table(employee_schema,'employee_education_records')),(eid,edu['school_name'],edu['education_level'])).fetchall()
            if len(existing)>1:raise ValueError(f'계정 {eid}의 같은 학력이 여러 건입니다. 자동 덮어쓰기를 중단합니다.')
            edu['education_record_id']=existing[0]['education_record_id'] if existing else uuid5(NAMESPACE,f'{SHEET_ID}:{eid}:{edu["school_name"]}:{edu["education_level"]}')
            dates={**(existing[0] if existing else {}),**edu}
            if dates.get('enrollment_date') and dates.get('graduation_date') and dates['graduation_date']<dates['enrollment_date']:raise ValueError('졸업일이 입학일보다 빠릅니다.')
        plans.append({'employee_id':eid,'payload':payload,'related':related,'education':edu})
    heads={}
    for p in plans:
        if p['payload']['is_department_head']:
            dept=p['payload']['department_id']
            if dept in heads:raise ValueError('같은 부서에 부서장이 중복됩니다.')
            heads[dept]=p['employee_id']
    ids=[p['employee_id'] for p in plans]
    if heads:
        other=c.execute(sql.SQL('SELECT employee_id FROM {} WHERE is_department_head AND department_id=ANY(%s) AND NOT (employee_id=ANY(%s))').format(table(employee_schema,'employees')),(list(heads),ids)).fetchall()
        if other:raise ValueError('동기화 대상 외 직원이 이미 해당 부서의 부서장입니다.')
    return plans

def synchronize(c,text,employee_schema='public',master_schema='public',apply=False):
    """Caller owns transaction. Dry-run locks/validates but never writes."""
    c.execute('SELECT pg_advisory_xact_lock(763250132)')
    plans=plan_sync(c,parse_sheet(text),employee_schema,master_schema)
    digest=hashlib.sha256(text.encode()).hexdigest()
    if apply:
        ids=[p['employee_id'] for p in plans]
        # Release old head assignments inside this transaction before applying all new ones.
        c.execute(sql.SQL('UPDATE {} SET is_department_head=false WHERE employee_id=ANY(%s) AND is_department_head').format(table(employee_schema,'employees')),(ids,))
        for p in plans:
            payload=p['payload'];eid=p['employee_id']
            fields=list(payload)
            assignments=sql.SQL(',').join(sql.SQL('{}=%s').format(sql.Identifier(k)) for k in fields)
            c.execute(sql.SQL('UPDATE {} SET {},department=NULL,grade=NULL,job_title=NULL,updated_at=now() WHERE employee_id=%s').format(table(employee_schema,'employees'),assignments),[payload[k] for k in fields]+[eid])
            for key,name,col in [('skills','employee_skills','skill_id'),('certifications','employee_certifications','certification_id')]:
                if key in p['related']:
                    c.execute(sql.SQL('DELETE FROM {} WHERE employee_id=%s').format(table(employee_schema,name)),(eid,))
                    for rid in p['related'][key]:c.execute(sql.SQL('INSERT INTO {}(employee_id,{}) VALUES(%s,%s)').format(table(employee_schema,name),sql.Identifier(col)),(eid,rid))
            if p['education']:
                edu={**p['education'],'employee_id':eid};keys=list(edu)
                c.execute(sql.SQL('INSERT INTO {} ({}) VALUES ({}) ON CONFLICT(education_record_id) DO UPDATE SET {}').format(table(employee_schema,'employee_education_records'),sql.SQL(',').join(map(sql.Identifier,keys)),sql.SQL(',').join(sql.Placeholder() for _ in keys),sql.SQL(',').join(sql.SQL('{}=EXCLUDED.{}').format(sql.Identifier(k),sql.Identifier(k)) for k in keys if k not in ('education_record_id','employee_id'))),list(edu.values()))
    return {'applied':apply,'employee_ids':[p['employee_id'] for p in plans],'source_sha256':digest,
            'employees':len(plans),'education_records':sum(bool(p['education']) for p in plans),
            'skills':sum(len(p['related'].get('skills',[])) for p in plans),
            'certifications':sum(len(p['related'].get('certifications',[])) for p in plans),
            'missing_employee_numbers':[p['employee_id'] for p in plans if not p['payload'].get('employee_number')]}
