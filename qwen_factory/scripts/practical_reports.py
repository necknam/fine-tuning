"""Render only model-supplied content and supplied DB facts; never fill missing answers."""
import json

def text(value):
 if value is None:return '미확인'
 return str(value).replace('|','\\|').replace('\n',' ')
def render(report,side='tuned'):
 try:
  request=json.loads(next(m['content'] for m in reversed(report['messages']) if m['role']=='user'))
  answer=json.loads(report[side]['text'])
 except (KeyError,ValueError,StopIteration,TypeError):return '# 학습 결과 보고서\n\n구조화된 답변을 해석하지 못했습니다. 원문을 확인하세요.\n'
 user=request.get('user_context') or {};limits=user.get('constraints') or {};ctx=request.get('retrieved_context') or {}
 roadmap=answer.get('roadmap',answer) if isinstance(answer,dict) else None
 lines=['# 맞춤형 학습 계획 보고서','','## 프로젝트와 조건','',f"- 목표: {text(user.get('goal',user.get('work_context_summary')))}",f"- 관점: {text(user.get('perspective'))}",f"- 기간: {text(limits.get('duration_weeks'))}주 · 주당 {text(limits.get('weekly_hours'))}시간 · 예산 {text(limits.get('budget_krw'))}원",'']
 profile=user.get('profile_snapshot') or {}
 if profile.get('synthetic'):
  lines+=['## 평가용 가상 직원','',f"- 직원: {text(profile.get('name'))} · ID {text(profile.get('employee_id'))}",f"- 소속·직급·직무: {text(profile.get('department'))} · {text(profile.get('grade'))} · {text(profile.get('job_title'))}",'- TEST_MANUAL 합성 정보이며 실제 직원의 이력·역량 평가가 아닙니다.','']
 if not isinstance(roadmap,dict):return '\n'.join(lines+['## 모델 응답','',json.dumps(answer,ensure_ascii=False,indent=2)])
 lines+=['## 계획', '',text(roadmap.get('strategy_title')), '',text(roadmap.get('summary')),'']
 stages=roadmap.get('milestones',roadmap.get('stages',[]))
 for i,stage in enumerate(stages,1):
  if not isinstance(stage,dict):continue
  lines += [f"### {i}. {text(stage.get('phase_name',stage.get('title')))}",'',f"- 목표: {text(stage.get('focus_goal'))}",f"- 기간: {text(stage.get('duration'))} · 시간: {text(stage.get('hours'))}시간 · 비용: {text(stage.get('cost_krw'))}원"]
  actions=stage.get('key_actions',[])
  if isinstance(actions,list):lines += ['- 활동: '+text(x) for x in actions]
  lines += [f"- 산출물: {text(stage.get('deliverable'))}",f"- 완료 기준: {text(stage.get('completion_criterion'))}"]
  for field,kind,pk in [('recommended_courses','courses','course_id'),('recommended_books','books','isbn'),('recommended_certifications','certifications','cert_id')]:
   source={str(x.get(pk)):x for x in ctx.get(kind,[]) if isinstance(x,dict)}
   for selected in stage.get(field,[]) or []:
    identifier=selected.get(pk) if isinstance(selected,dict) else selected;fact=source.get(str(identifier))
    if fact is None:lines.append(f'- 추천 자료 {text(identifier)}: 제공 근거에서 확인되지 않음');continue
    lines.append(f"- 추천 자료: {text(fact.get('title'))} · ID {text(identifier)} · DB 비용 {text(fact.get('cost'))}원 · 이용 상태 {text(fact.get('availability_status'))}")
    url=fact.get('url') or fact.get('source_url')
    if isinstance(url,str) and url.startswith('https://'):lines.append('- 자료 출처: '+url)
  lines.append('')
 lines+=['## 합계와 확인 사항','',f"- 총기간: {text(roadmap.get('total_duration_weeks'))}주",f"- 총시간: {text(roadmap.get('total_hours'))}시간",f"- 총비용: {text(roadmap.get('total_cost_krw'))}원",f"- 규정 안내: {text(roadmap.get('regulation_summary'))}",f"- 규정 인용: {text(roadmap.get('regulation_citations'))}"]
 for item in roadmap.get('confirmation_needed',[]) or []:lines.append('- 추가 확인: '+text(item))
 retrieval=ctx.get('retrieval') or {}
 lines+=['','## 조회 근거 추적','',f"- 원본 동기화 해시: {text(retrieval.get('source_receipt_sha256'))}",f"- 평가 입력 해시: {text(report.get('test_sha256'))}",'','※ 빈 항목은 모델이 제공하지 않은 값입니다. 보고서 변환 과정에서 숫자·근거·승인 상태를 채워 넣지 않았습니다.']
 return '\n'.join(lines)+'\n'
