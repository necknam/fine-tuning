"""Five auditable content revisions; frozen v1 and active recipes remain immutable.
This authors supervised examples locally. Rule validation is not a claim of full
semantic review or measured model improvement.
"""
import copy,collections,hashlib,json,re
from pathlib import Path
from reviewed_curriculum import SPECS
from prepare_data import validate
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'data/production/curation_1500_balanced_v2'
TARGET=ROOT/'data/production/curation_1500_reviewed_v3'
def dump(x):return json.dumps(x,ensure_ascii=False,sort_keys=True)
def sha(x):return hashlib.sha256(dump(x).encode()).hexdigest()
def read(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def parts(row):return json.loads(row['messages'][-2]['content']),json.loads(row['messages'][-1]['content'])
def goal(q):
 u=q.get('user_context') or {}
 return q.get('project_goal') or u.get('goal') or u.get('work_context_summary') or '입력 프로젝트'
def skill_ids(m):return [s for s in m['skill_ids'] if s in SPECS]
def exercise(s):return SPECS[s][1]
def expected(s):return SPECS[s][2]
def revision(q,a,m,i,round_no):
 task=m['task'];ids=skill_ids(m)
 if not ids:raise ValueError('Unknown curriculum skill')
 changed=False
 if round_no==1 and task=='generate_survey':
  n=(8,10,12)[i%3];old=q['slots'];slots=[];a=[];used=collections.Counter()
  for k in range(n):
   slot=copy.deepcopy(old[k%len(old)]);s=slot['skill_id'];concepts=SPECS[s][0].split('|');concept=concepts[(used[s]+i//3)%6];used[s]+=1
   slot.update(sequence_no=k+1,focus=concept);slots.append(slot)
   a.append(dict(sequence_no=k+1,skill_id=s,question=f"이번 프로젝트에서 {concept}에 대해 {('원리를 설명할','작은 예제로 설명할','잘못된 적용을 구별할')[(i//18+(used[s]-1)//6)%3]} 수 있나요?"))
  q['slots']=slots;changed=True
 elif round_no==2 and task=='interpret_assessment':
  # Include missing responses, stale responses and experience mismatch, not only high scores.
  mode=i%5;responses=[dict(skill_id=s,score=1+(i+k)%5) for k,s in enumerate(ids)]
  if mode==2:responses=responses[:-1]
  td=q.setdefault('task_data',{});td.update(responses=responses,response_date='2026-06-01' if mode==3 else '2026-10-20',as_of='2026-10-23',measurement='self_report_5pt')
  td['experience_evidence']={'status':'unverified','user_claim':'직접 실행한 기록 없음' if mode==4 else '실행 기록 제출 여부 미확인'}
  a=dict(assessment_method='self_report',observations=[],priorities=[],questions=[],regulation_summary='규정 확인 필요',regulation_citations=[])
  for r in responses:
   s=r['skill_id'];score=r['score'];a['observations'].append(dict(skill_id=s,score=score,interpretation=f"이해도 {score}/5의 자기보고이며 실제 구현 능력이나 업무 성과의 증거가 아니다."))
  for r in sorted(responses,key=lambda r:(r['score'],r['skill_id'])):
   s=r['skill_id'];a['priorities'].append(dict(skill_id=s,reason=f"자기보고 {r['score']}점은 시작점 참고값이다. 프로젝트 연결: {goal(q)}",next_action=f"확인 과제 제안: {exercise(s)}. 확인 기준: {expected(s)}. 이미 같은 결과를 재현한 코드가 있으면 기초 반복 대신 실패 사례를 확인한다."))
  for s in set(ids)-{r['skill_id'] for r in responses}:a['questions'].append(f"스킬 {s}의 응답이 없습니다. {SPECS[s][0].split('|')[0]}에 대한 이해도를 알려주세요.")
  if mode==3:a['questions'].append('응답 이후 경험이 바뀌었나요? 오래된 자기보고를 현재 진단으로 확정하지 않고 다시 확인합니다.')
  a['questions'].append('실행 코드·입력·실제 출력 중 제출할 수 있는 검증 자료가 있나요?');changed=True
 elif round_no==3 and task=='resolve_constraints':
  mode=i%5;weeks=2+i%7;weekly=2+(i//5)%6;capacity=weeks*weekly;budget=10000+(i%13)*5000
  needed=capacity+3+i%9 if mode==1 else max(1,capacity-2);expense=budget+5000+i*100 if mode==0 else max(0,budget-2000)
  if mode==2:expense=None
  q.setdefault('user_context',{})['constraints']=dict(duration_weeks=weeks,weekly_hours=weekly,budget_krw=budget)
  q['task_data']=dict(scenario_note='가상 계획. 최신 제약은 user_context.constraints. 배경의 과거 조건은 적용하지 않음.',requested_hours=needed,estimate_source='synthetic_user_estimate',planned_expense_krw=expense,support_status='pending' if mode==3 else 'not_assumed',user_request='목표를 보존하면서 이 계획의 실행 조건을 검토해 주세요.')
  conflict=[]
  if mode==0:conflict.append(f"예상비용 {expense}원이 예산 {budget}원보다 {expense-budget}원 많다.")
  if mode==1:conflict.append(f"가용 {capacity}시간보다 사용자 추정 {needed}시간이 {needed-capacity}시간 많다.")
  if mode==2:conflict.append('환경 비용 미확인으로 예산 충족 여부를 확정할 수 없다.')
  if mode==3:conflict.append('지원 승인 대기 중이다. 지원금을 확정 수입으로 차감하지 않는다.')
  a=dict(conflicts=conflict,alternatives=[dict(adjustment=f"프로젝트 목표: {goal(q)}",reason=f"총 {capacity}시간 중 확인 과제 '{exercise(ids[0])}'의 실제 소요시간을 측정한다. 사용자 추정은 확정 소요시간이 아니다."),dict(adjustment='필수 완료 기준을 유지하는 범위와 환경 견적을 확인한 뒤 계획을 조정한다.',reason='목표나 예산·기간 변경은 사용자 합의가 필요하다. 기존 환경·무료 API·지원금의 이용 가능성을 추정하지 않는다.')],questions=['가용 환경과 실제 견적을 확인할 수 있나요?','필수 완료 기준을 유지하면서 범위 또는 조건을 변경할 수 있나요?'],regulation_summary='규정 확인 필요',regulation_citations=[])
  if mode==4:a['alternatives'].append(dict(adjustment='제공된 추정치 범위에서는 시간과 예산 조건을 충족한다.',reason=f"{needed}≤{capacity}시간, {expense}≤{budget}원이다. 실제 완료나 미래 비용은 보장하지 않는다."))
  changed=True
 elif round_no==3 and task=='evidence_boundary':
  mode=i%5;ctx=q.setdefault('retrieved_context',{});courses=ctx.get('courses') or [];candidate=copy.deepcopy(courses[i%len(courses)]) if courses else None
  ctx.update(courses=[],books=[],certifications=[],regulation_rag={'approved':[],'review_only':[],'status':'verification_required'})
  if candidate and mode in (1,2,4):ctx['courses']=[candidate]
  topics=['empty','partial','unrelated','pending_support','candidate_only'];td={'scenario_kind':topics[mode],'user_query':'프로젝트에 맞는 자료와 확정 가능한 비용·지원 조건을 구분해 주세요.'};q['task_data']=td
  known=[]
  if candidate and mode in (1,2,4):known=[dict(course_id=candidate['course_id'],title=candidate.get('title'),catalog_cost=candidate.get('cost'),source_url=candidate.get('url'))]
  if mode==2:td['relevance_evidence']='이 사례에서는 제공된 후보와 프로젝트의 관련성을 확인하지 못했다.'
  if mode==3:td['support_status']='승인 대기. 지급 확정 근거 없음.'
  a=dict(response_type='PARTIAL_EVIDENCE' if known else 'VERIFICATION_REQUIRED',topic=topics[mode],known_facts=known,answer=f"프로젝트: {goal(q)}. 제공된 후보의 제목·표시 비용은 인용할 수 있지만 환경비, 모집 상태, 목표 적합성, 지원 승인은 별도 확인해야 한다. 비용 누락은 0원이 아니다.",next_step='프로젝트 목표와 연결되는 강의 내용·현재 모집 조건·환경 견적을 확인한다. 무근거 지원 확정과 무료 완수 보장은 하지 않는다.',regulation_summary='규정 확인 필요',regulation_citations=[])
  changed=True
 elif round_no==4 and task=='generate_roadmap':
  u=q.setdefault('user_context',{});stages=a.get('milestones') or []
  if not stages:raise ValueError('Roadmap has no milestones')
  durations=[]
  for st in stages:
   match=re.fullmatch(r'\s*(\d+)\s*주\s*',st.get('duration',''))
   durations.append(int(match[1]) if match else 1)
  weeks=sum(durations);weekly=2+i%5
  u['constraints']=dict(duration_weeks=weeks,weekly_hours=weekly,budget_krw=50000+(i%5)*25000)
  u['perspective']=('비용','시간','업무 적용')[i%3]
  u['scenario_note']='가상 학습 계획의 최신 시간·예산은 constraints. 과거 대화의 수치는 배경이며 현재 제약을 덮어쓰지 않음.'
  q.pop('conversation_history',None)
  for k,(st,w) in enumerate(zip(stages,durations)):
   s=ids[k%len(ids)];st.update(duration=f'{w}주',hours=w*weekly,cost_krw=None,deliverable=f"단계 활동의 실행 코드·입력·실제 출력 및 오류 기록. 보조 확인 과제: {exercise(s)}",completion_criterion=f"본 단계 목표 '{st.get('focus_goal')}'의 사전 기대표와 실제 출력을 대조하고 실패를 기록한다. 보조 과제 기준: {expected(s)}. 실행 전에는 완료로 표시하지 않는다.")
   st['cost_note']='추천 자료의 비용과 실습 환경비·시험료를 포함한 전체 견적이 확인되지 않아 단계 비용을 미확인으로 둠.'
  a.update(total_duration_weeks=weeks,total_hours=weeks*weekly,total_cost_krw=None,confirmation_needed=['환경비·시험료·자료의 현재 이용 가능성 확인','자기보고와 실제 수행 경험 구분','목표 규모 대비 단계별 예상시간의 타당성 확인'])
  a['summary']=f"입력의 프로젝트 목표에 대해 단계별 활동과 실행 기록을 제안한다. 최신 시나리오: {weeks}주×주 {weekly}시간={weeks*weekly}시간. {u['perspective']} 관점으로 계획을 검토하며 목표 완수를 보장하지 않는다. 전체 비용은 미확인이다."
  angle={'비용':'추가 결제 전 실제 견적과 보유 환경을 확인하고 미확인 비용은 보류한다.','시간':'단계 시간 상한 안에서 핵심 실행 결과를 먼저 확인하고 초과 예상 시 범위를 합의한다.','업무 적용':'운영 반영 전 모의 데이터로 검증하고 권한·배포 승인을 별도로 확인한다.'}
  for st in stages:st['key_actions']=list(st.get('key_actions',[]))+[angle[u['perspective']]]
  changed=True
 elif round_no==5 and task=='generate_survey':
  # One distinct concept per slot; six focused questions are preferable to filler.
  seen=set();slots=[];answers=[]
  context=goal(q).split('|')[0].removeprefix('[확정 목표]:').strip()
  for slot,item in zip(q['slots'],a):
   key=(slot['skill_id'],slot['focus'])
   if key in seen:continue
   seen.add(key);slot['sequence_no']=len(slots)+1;item['sequence_no']=len(slots)+1
   item['question']=f"프로젝트 ‘{context}’에서 "+item['question'].removeprefix('이번 프로젝트에서 ')
   slots.append(slot);answers.append(item)
  offset=(i//54)%len(slots)
  slots=slots[offset:]+slots[:offset];answers=answers[offset:]+answers[:offset]
  for seq,(slot,item) in enumerate(zip(slots,answers),1):slot['sequence_no']=seq;item['sequence_no']=seq
  q['slots']=slots;a=answers;changed=True
 elif round_no==5 and task=='evidence_boundary':
  mode=i%5;catalog=json.loads((TARGET/'catalog_snapshot.json').read_text(encoding='utf-8'))
  candidates=[c for c in catalog['courses'] if set(c['skill_ids'])&set(ids)]
  ctx=q['retrieved_context'];a['known_facts']=[]
  if candidates and mode in (1,2,4):
   fact=copy.deepcopy(candidates[(i//5)%len(candidates)]);fact['availability_status']='verification_required';ctx['courses']=[fact]
   a['known_facts']=[dict(course_id=fact['course_id'],title=fact['title'],catalog_cost=fact['cost'],source_url=fact['url'])]
   a['response_type']='PARTIAL_EVIDENCE'
  else:
   ctx['courses']=[];a['response_type']='VERIFICATION_REQUIRED'
   if mode in (1,2,4):q['task_data']['scenario_kind']='no_matching_candidate';a['topic']='no_matching_candidate'
  if mode==2 and a['known_facts']:
   a['answer']+=' 제공된 사례 조건에서 프로젝트 적합성은 확인되지 않았으므로 확정 추천 목록에는 넣지 않는다.'
  if mode==4 and a['known_facts']:
   a['answer']+=' 스킬 연결이 있는 학습 후보로 제시하며 현재 수강 가능성을 확정하지 않는다.'
  changed=True
 elif round_no==5 and task=='revise_roadmap':
  current=q.get('task_data',{}).get('current_roadmap');stages=current.get('milestones',[]) if current else []
  if not stages:return q,a,False
  current=copy.deepcopy(current);a=copy.deepcopy(current);mode=i%4;idx=i%len(stages)
  if mode==3 and not all(re.fullmatch(r'\s*\d+\s*주\s*',(st.get('duration') or '')) for st in stages):mode=0
  if mode==0:
   target=f"Phase {idx+1}: 구현 결과 재현 점검";a['milestones'][idx]['phase_name']=target
   feedback=f"{idx+1}번째 단계의 phase_name만 '{target}'으로 바꾸고 다른 값·완료 기록은 보존해 주세요."
   allowed=f'/milestones/{idx}/phase_name'
  elif mode==1:
   target=f"{stages[idx]['focus_goal']} — {exercise(ids[idx%len(ids)])} 결과를 보조 확인"
   a['milestones'][idx]['focus_goal']=target;feedback=f"{idx+1}번째 단계의 focus_goal만 '{target}'으로 바꾸고 나머지는 보존해 주세요.";allowed=f'/milestones/{idx}/focus_goal'
  elif mode==2:
   current['completed_milestone_indices']=[0];a=copy.deepcopy(current)
   target=f"진행 기록을 보존하고 다음 단계에서 {exercise(ids[0])}의 실패 사례를 확인한다."
   a['summary']=target;feedback=f"summary만 '{target}'으로 바꾸세요. 완료 단계와 다른 값은 보존하세요.";allowed='/summary'
  else:
   idx=1 if len(stages)>1 else 0
   current['completed_milestone_indices']=[] if idx==0 else [0];a=copy.deepcopy(current)
   durations=[int(re.search(r'\d+',st.get('duration','1'))[0]) for st in stages]
   durations[idx]+=1;a['milestones'][idx]['duration']=f'{durations[idx]}주';a['total_duration_weeks']=sum(durations)
   feedback=f'{idx+1}번째 단계 기간을 1주 늘리고 total_duration_weeks도 단계 기간 합계로 갱신하세요. 완료 단계와 다른 값은 보존하세요.'
   allowed=[f'/milestones/{idx}/duration','/total_duration_weeks']
  q['task_data']=dict(current_roadmap=current,user_feedback=feedback,allowed_change_paths=allowed if isinstance(allowed,list) else [allowed]);changed=True
 elif round_no==5 and task=='progress_checkin':
  s=ids[i%len(ids)];u=q.setdefault('user_context',{});weekly=3+i%8;u['constraints']={'weekly_hours':weekly}
  q['task_data']=dict(scenario_note='가상 진행 점검. 사용자 자료는 자기보고이며 실행 결과로 검증되지 않음.',execution_evidence='not_submitted',user_report='계획 문서만 작성했습니다. 아직 실행하지 못했습니다.',requested_next_step=exercise(s))
  a=dict(status='NOT_VERIFIED',summary=f"프로젝트 {goal(q)}의 계획 작성은 실행·구현 완료를 입증하지 않는다.",next_actions=[dict(title=exercise(s),estimated_hours=weekly-1,verification_method=expected(s)),dict(title='실행 코드·입력·출력·실패를 함께 저장하고 다음 범위 결정',estimated_hours=1,verification_method='실행 기록이 없으면 미실행으로 표시한다.')],weekly_hours=weekly,completed=False,questions=['실행을 막은 환경·비용·시간 조건은 무엇인가요?'],regulation_summary='규정 확인 필요',regulation_citations=[]);changed=True
 return q,a,changed

def refresh_catalog(q,a,m):
 catalog=json.loads((TARGET/'catalog_snapshot.json').read_text(encoding='utf-8'));ids=skill_ids(m)
 specs=[('courses','course_id','recommended_courses'),('books','isbn','recommended_books'),('certifications','cert_id','recommended_certifications')]
 def clean(value):
  if isinstance(value,list):
   for v in value:clean(v)
  elif isinstance(value,dict):
   for kind,pk,field in specs:
    if field in value:
     valid={str(r[pk]) for r in catalog[kind]}
     value[field]=[r for r in value[field] if str(r.get(pk) if isinstance(r,dict) else r) in valid]
   for v in value.values():clean(v)
 clean(a);clean(q.get('task_data',{}))
 ctx=q.get('retrieved_context')
 if ctx is None or m['task']=='evidence_boundary':return q,a
 for kind,pk,field in specs:
  candidates=[r for r in catalog[kind] if set(r['skill_ids'])&set(ids)]
  limit=2 if kind=='courses' else 1
  fields={pk,'title','cost','url','source_url','org_name','provider','syllabus_summary','description','skill_ids'}
  ctx[kind]=[{**{k:v for k,v in r.items() if k in fields},'availability_status':'verification_required'} for r in candidates[:limit]]
 ctx['catalog_snapshot_note']='最新'.replace('最新','2026-10-23 최신 DB 스냅샷. 후보의 스킬 연결은 확인했으며 현재 모집·전체 비용은 별도 확인.')
 if m['task']=='generate_roadmap':
  for index,stage in enumerate(a['milestones']):
   sid=ids[index%len(ids)];facts=[r for r in ctx['courses'] if sid in r['skill_ids']]
   stage['recommended_courses']=[{'course_id':facts[0]['course_id']}] if facts else []
   stage['resource_usage_note']='보조 확인 과제를 위한 스킬 연결 후보다. 제목·DB 비용 외에 수강 가능성이나 환경 비용을 확정하지 않는다.'
 return q,a

def audit(rows,meta):
 errors=[];families={};prompts={};answers=collections.defaultdict(set);tasks=collections.Counter();lens=[]
 for n,(r,m) in enumerate(zip(rows,meta)):
  try:
   validate(r);q,a=parts(r);task=m['task'];tasks[task]+=1
   family=m['family_id'];split=m['split']
   if family in families and families[family]!=split:raise ValueError('Cross-split family')
   families[family]=split;ph=sha(r['messages'][:-1])
   if ph in prompts and prompts[ph]!=split:raise ValueError('Cross-split prompt')
   prompts[ph]=split;answers[sha(a)].add(split);lens.append(sum(len(x['content']) for x in r['messages']))
   if task=='generate_survey':
    if len(a)!=len(q['slots']):raise ValueError('Survey length')
    if len({x['question'] for x in a})!=len(a):raise ValueError('Repeated survey question')
    if any((x['skill_id'],x['sequence_no'])!=(y['skill_id'],y['sequence_no']) for x,y in zip(a,q['slots'])):raise ValueError('Survey binding')
   if task=='generate_roadmap' and 'total_hours' in a:
    if sum(x['hours'] for x in a['milestones'])!=a['total_hours']:raise ValueError('Hours')
    if sum(int(x['duration'][:-1]) for x in a['milestones'])!=a['total_duration_weeks']:raise ValueError('Weeks')
   if task=='revise_roadmap' and q.get('task_data',{}).get('allowed_change_paths'):
    before=copy.deepcopy(q['task_data']['current_roadmap'])
    for allowed in q['task_data']['allowed_change_paths']:
     path=allowed.split('/')[1:];obj=before;value=a
     for key in path[:-1]:
      key=int(key) if isinstance(obj,list) else key;obj=obj[key];value=value[key]
     obj[path[-1]]=value[path[-1]]
    if before!=a:raise ValueError('Unrequested revision')
  except Exception as error:errors.append({'row':n,'task':m['task'],'error':str(error)})
 return dict(records=len(rows),task_counts=dict(tasks),errors=errors,exact_duplicates=len(rows)-len({sha(r) for r in rows}),cross_split_identical_answer_groups=sum(len(v)>1 for v in answers.values()),max_characters=max(lens),full_semantic_review_completed=False,model_token_length_verified=False)

def run(round_no):
 if round_no not in range(1,6):raise ValueError('Round must be 1..5')
 TARGET.mkdir(exist_ok=True)
 out=TARGET/f'round_{round_no}'
 if out.exists():raise ValueError('Refusing to overwrite an audit round')
 source=SOURCE if round_no==1 else TARGET/f'round_{round_no-1}'
 rows=read(source/'all.jsonl');meta=read(source/'provenance.jsonl');before=audit(rows,meta);changed=[];seen_rows=set()
 for i,(r,m) in enumerate(zip(rows,meta)):
  q,a=parts(r)
  if round_no==5:q,a=refresh_catalog(q,a,m)
  q,a,did=revision(q,a,m,i,round_no)
  if round_no==5:did=True
  if did:
   old=sha(r);r['messages'][-2]['content']=dump(q);r['messages'][-1]['content']=dump(a)
   # A shorter focused survey is a distinct task; don't pad repeated concepts.
   while sha(r) in seen_rows and m['task']=='generate_survey' and len(a)>4:
    a=a[:-1];q['slots']=q['slots'][:-1]
    r['messages'][-2]['content']=dump(q);r['messages'][-1]['content']=dump(a)
   changed.append(dict(row=i,task=m['task'],before_sha256=old,after_sha256=sha(r)))
   m.setdefault('revision_history',[]).append(dict(round=round_no,parent_sha256=old));m.update(sha256=sha(r),origin='locally_authored_content_revision',per_record_semantic_review_completed=False)
  seen_rows.add(sha(r))
 after=audit(rows,meta)
 if after['errors'] or after['exact_duplicates']:raise ValueError(dump(after))
 out.mkdir()
 for name,data in [('all.jsonl',rows),('provenance.jsonl',meta),('changes.jsonl',changed)]:
  (out/name).write_text(''.join(dump(x)+'\n' for x in data),encoding='utf-8')
 report=dict(round=round_no,changed=len(changed),before=before,after=after,status='RULE_VALIDATED_AWAITING_CONTENT_REVIEW',training_started=False)
 (out/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(dump({k:v for k,v in report.items() if k not in ('before','after')}));print(dump(after))
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--round',type=int,required=True);run(parser.parse_args().round)
