"""Read synthetic TEST_MANUAL profiles for post-training report inputs."""
import copy
from cloud_evidence import connection,canonical

# Drawn once with seed 20261023; never randomize during rendering/training.
FIXED_CASE_EMPLOYEE_IDS=(12,14,6,8,16,7,15,17,13,12)
def fixed_assignment():
 return list(FIXED_CASE_EMPLOYEE_IDS)

def validate_assignment(ids):
 if not isinstance(ids,list) or len(ids)!=10 or any(type(i)is not int or i<=0 for i in ids):
  raise ValueError('TEST_MANUAL 평가에는 정확히 10개의 직원 배정 ID가 필요합니다.')
 return list(ids)

def list_profiles(root):
 with connection(root) as c:
  c.execute('BEGIN READ ONLY')
  return c.execute("""SELECT e.employee_id,e.name,d.name AS department,g.name AS grade,j.title AS job_title
   FROM growpath_hr.employees e LEFT JOIN growpath_live.departments d USING(department_id)
   LEFT JOIN growpath_live.job_grades g USING(job_grade_id) LEFT JOIN growpath_live.jobs j USING(job_id)
   WHERE e.source_type='TEST_MANUAL' ORDER BY e.employee_id""").fetchall()

def profile(c,employee_id):
 if type(employee_id)is not int or employee_id<=0:raise ValueError('Invalid test employee ID')
 row=c.execute("""SELECT e.employee_id,e.source_type,e.name,e.job_id,e.department_id,e.job_grade_id,
   e.hire_date,e.department_start_date,e.is_department_head,e.is_degree_seeker,
   e.planned_project_description,e.unlisted_certifications,d.name AS department,g.name AS grade,j.title AS job_title
   FROM growpath_hr.employees e LEFT JOIN growpath_live.departments d USING(department_id)
   LEFT JOIN growpath_live.job_grades g USING(job_grade_id) LEFT JOIN growpath_live.jobs j USING(job_id)
   WHERE e.employee_id=%s AND e.source_type='TEST_MANUAL'""",(employee_id,)).fetchone()
 if row is None:raise ValueError('선택한 직원은 TEST_MANUAL이 아니거나 Cloud에 없습니다.')
 row=dict(row)
 row['skills']=c.execute('SELECT s.skill_id,s.name FROM growpath_hr.employee_skills x JOIN growpath_live.skill_tags s USING(skill_id) WHERE x.employee_id=%s ORDER BY s.skill_id',(employee_id,)).fetchall()
 row['certifications']=c.execute('SELECT x.certification_id AS cert_id,s.title FROM growpath_hr.employee_certifications x JOIN growpath_live.certifications s ON s.cert_id=x.certification_id WHERE x.employee_id=%s ORDER BY x.certification_id',(employee_id,)).fetchall()
 row['education']=c.execute('SELECT education_level,school_name,department_name,enrollment_date,graduation_date FROM growpath_hr.employee_education_records WHERE employee_id=%s ORDER BY education_record_id',(employee_id,)).fetchall()
 row['synthetic']=True
 row['provenance']='승인된 시트 항목의 가상 조합. 실제 직원 이력·검증된 역량이 아님.'
 return row

def apply_profile(request,employee):
 """Keep fixed task constraints/perspective, replacing template biography and goal."""
 if employee.get('source_type')!='TEST_MANUAL' or not employee.get('synthetic'):raise ValueError('Synthetic TEST_MANUAL profile required')
 result=copy.deepcopy(request)
 user=result.setdefault('user_context',{})
 scenario={k:copy.deepcopy(user.get(k)) for k in ('goal','target_skill_ids','target_skills') if k in user}
 for key in ('self_check','experience','current_level','job_title','goal','work_context_summary','profile_snapshot'):
  user.pop(key,None)
 user.update(employee_id=employee['employee_id'],employee_source_type='TEST_MANUAL',
  job_title=employee.get('job_title'),goal=employee.get('planned_project_description'),
  current_level='합성 테스트 프로필. 진단·실제 역량 검증 결과 없음.',
  experience='보유 기술·자격은 평가용 가정이며 실제 수행 경험으로 검증되지 않음.',
  profile_snapshot=employee,
  work_context_summary='DB의 합성 직원 프로필을 입력으로 사용한다. 비어 있는 정보는 미확인이며 실제 이력으로 추정하지 않는다. 시간·예산·관점은 고정 평가 시나리오 조건이다.')
 # Target skills describe this fictional employee's project; avoid old template RAG assumptions.
 skills=employee.get('skills') or []
 user['target_skill_ids']=[s['skill_id'] for s in skills]
 user['target_skills']=[s['name'] for s in skills]
 if result.get('task')=='revise_roadmap':
  # The fixed revision fixture is a scenario, not this employee's real history.
  for key in ('goal','target_skill_ids','target_skills'):user.pop(key,None)
  user.update(scenario)
  user['scenario_context']='수정 전 로드맵과 변경 요청은 고정 평가 시나리오이며 이 직원의 실제 수행 이력이 아니다. 직원 프로필은 가상 배경 정보다.'
 return result
