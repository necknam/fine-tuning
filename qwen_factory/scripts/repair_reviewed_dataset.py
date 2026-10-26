"""Repair documented v3 content gaps into a new, immutable v4 candidate."""
import json,copy,hashlib,collections,re
from decimal import Decimal
from pathlib import Path
from refine_dataset import ROOT,read,parts,dump,sha,audit
from reviewed_curriculum import SPECS
SOURCE=ROOT/'data/production/curation_1500_reviewed_v3'
TARGET=ROOT/'data/production/curation_1500_reviewed_v4'
def build():
 if TARGET.exists():raise ValueError('Refusing overwrite')
 rows=read(SOURCE/'release/all.jsonl');meta=read(SOURCE/'release/provenance.jsonl');catalog=json.loads((SOURCE/'catalog_snapshot.json').read_text(encoding='utf-8'));log=[]
 for i,(r,m) in enumerate(zip(rows,meta)):
  q,a=parts(r);old=sha(r);t=m['task'];u=q.get('user_context') or {};ids=m['skill_ids'];sid=ids[i%len(ids)];exercise=SPECS[sid][1];criterion=SPECS[sid][2]
  constraints=u.get('constraints') or {};hours=constraints.get('weekly_hours')
  if hours is not None:
   for field in ['work_context_summary','goal']:
    if isinstance(u.get(field),str):u[field]=re.sub(r'((?:주당|주)\s*)\d+(\s*시간)',lambda x:x[1]+str(hours)+x[2],u[field])
  if t=='generate_roadmap':
   ctx=q['retrieved_context'];mode=i%3;quote=5000+(i%11)*1000
   if mode==0:
    known=[c for c in catalog['courses'] if c.get('cost') is not None and set(c['skill_ids'])&set(ids)]
    if known:
     fact={k:v for k,v in known[(i//3)%len(known)].items() if k in ['course_id','title','cost','url','skill_ids']};fact['availability_status']='verification_required';ctx['courses']=[fact]
     for st in a['milestones']:st['recommended_courses']=[];st['recommended_books']=[];st['recommended_certifications']=[]
     a['milestones'][0]['recommended_courses']=[{'course_id':fact['course_id']}]
   selected={str(ref['course_id']) for st in a['milestones'] for ref in st.get('recommended_courses',[])}
   facts={str(c['course_id']):c for c in ctx['courses']};known=[facts[x] for x in selected if facts[x].get('cost') is not None];unknown=[x for x in selected if facts[x].get('cost') is None]
   other=any(st.get('recommended_books') or st.get('recommended_certifications') for st in a['milestones'])
   subtotal=int(sum(Decimal(str(c['cost'])) for c in known))
   q.setdefault('task_data',{})['environment_quote']={'amount_krw':quote if mode==0 else None,'source':'synthetic_user_scenario','note':'합성 사용자가 제시한 실습 환경 전체 견적. 실제 DB 가격이나 실제 청구 내역이 아님.'}
   a['known_resource_subtotal_krw']=subtotal;a['cost_basis']={'course_ids':[c['course_id'] for c in known],'unknown_course_ids':unknown,'environment_quote_source':'synthetic_user_scenario','total_is_scenario_estimate':True}
   complete=mode==0 and not unknown and not other
   a['total_cost_krw']=subtotal+quote if complete else None
   a['summary']=re.sub(r'전체 비용은 미확인이다\.', '',a['summary']).strip()
   a['summary']+=f' 확인된 강좌비 소계는 {subtotal}원이다. '+(f'합성 사용자의 환경 견적 {quote}원을 포함한 시나리오 예상 총비용은 {subtotal+quote}원이다. 실제 청구금액은 아니다.' if complete else '미확인 자료비·환경비가 있어 전체 비용은 확정하지 않는다.')
   seen=set()
   for j,st in enumerate(a['milestones']):
    new=[str(x['course_id']) for x in st.get('recommended_courses',[]) if str(x['course_id']) not in seen];seen.update(new)
    st['cost_krw']=sum(int(Decimal(str(facts[x]['cost']))) for x in new)+(quote if j==0 else 0) if complete else None
    st['cost_note']='합성 환경 견적은 첫 단계에 한 번, 강좌비는 최초 선택 단계에 한 번만 반영한 예상 비용.' if complete else '확인된 자료비 소계와 미확인 전체 비용을 구분한다.'
   angle=u['perspective']
   a['perspective_decision']={'비용':'유료 결제와 비용 미확인 항목을 실행 전 보류하고 확인된 자료·기존 환경부터 검토한다.','시간':'각 단계 마지막 1시간을 재현 검증에 남기고 선택 학습은 핵심 테스트 이후로 미룬다.','업무 적용':'운영 반영 전 모의 입력과 부서 업무 흐름의 입출력을 대조하고 배포 승인 항목을 분리한다.'}[angle]
  elif t=='generate_survey':
   goal=(q.get('project_goal') or '').split('|')[0].removeprefix('[확정 목표]:').strip();q['question_context']=goal
   for slot,x in zip(q['slots'],a):
    tail=x['question'].split('’에서 ',1)[-1].replace('원리에 대해 원리를','원리를')
    x['question']=f"{goal[:36]}…: {tail}" if len(goal)>36 else f'{goal}: {tail}'
  elif t=='interpret_assessment':
   mode=i%3;td=q['task_data'];evidence={'source':'synthetic_test_fixture','skill_id':sid,'test_cases':3,'passed_cases':3 if mode==1 else 1,'note':'합성 실행 결과. 실제 직원 역량 증거가 아님.'}
   if mode:
    td['execution_evidence']=evidence;td['experience_evidence']['status']='synthetic_execution_provided'
    a['evidence_observation']=f"합성 과제 {exercise}: 제공 테스트 3건 중 {evidence['passed_cases']}건 통과. 이 과제 범위에만 해당하며 전체 숙련도를 입증하지 않는다."
    for priority in a['priorities']:
     if priority['skill_id']==sid:priority['next_action']=('제공된 성공 입력을 다시 반복하기보다 경계값·실패 복구 테스트를 추가한다.' if mode==1 else f'실패한 입력을 분리하고 {criterion} 기준과 실제 결과를 비교한다.')
  elif t=='resolve_constraints':
   td=q['task_data'];capacity=constraints['weekly_hours']*constraints['duration_weeks'];budget=constraints['budget_krw']
   a['alternatives'].append({'adjustment':f"첫 주에 '{exercise}'의 정상 입력 한 종류와 실패 입력 한 종류를 검증하고, 운영 연동·부하 확장은 별도 범위로 보류한다.",'reason':f'가용 {capacity}시간·예산 {budget}원에서 먼저 측정할 축소안이다. 원래 전체 목표 달성으로 처리하지 않으며 사용자의 범위 변경 합의가 필요하다.'})
  elif t=='evidence_boundary' and not a.get('known_facts'):
   a['answer']=a['answer'].replace('제공된 후보의 제목·표시 비용은 인용할 수 있지만','제공된 검색 결과에는 확인 가능한 학습 후보가 없다. 따라서')
  elif t=='progress_checkin':
   mode=i%5;passed=[3,2,0,None,3][mode];total=3
   td=q['task_data'];td['execution_evidence']={'source':'synthetic_test_fixture','exercise':exercise,'expected':criterion,'tests_total':total,'tests_passed':passed,'deadline':'missed' if mode==4 else 'within_schedule','note':'평가용 합성 기록이며 실제 실행한 결과가 아님.'}
   td['user_report']=['합성 테스트 전부 통과','일부 테스트 통과','테스트 실패','실행 자료 미제출','테스트 통과했지만 기한 초과'][mode]
   a.update(status=['COMPLETED','PARTIALLY_COMPLETED','FAILED','NOT_VERIFIED','DELAYED'][mode],completed=mode==0,summary=f"가상 프로젝트의 과제 '{exercise}': "+['제공된 합성 테스트 3/3 통과로 이 과제의 완료를 인정한다. 전체 프로젝트 완료는 별도다.','3개 중 2개만 통과해 부분 완료다.','3개 모두 실패하여 원인 분석이 필요하다.','제공된 실행 자료가 없어 완료를 확인할 수 없다.','3/3 통과했으나 기한을 넘겨 지연으로 구분한다.'][mode])
   a['next_actions'][0]['title']=['범위 밖 경계값 테스트 추가','실패한 한 개 테스트의 원인 재현','최소 실패 입력으로 원인 분리','실행 코드와 실제 출력을 먼저 제출','남은 일정 재계획과 지연 원인 기록'][mode]
  elif t=='revise_roadmap':
   current=q['task_data']['current_roadmap'];durations=[re.fullmatch(r'(\d+)주',s.get('duration') or '') for s in a['milestones']]
   if all(durations) and a.get('total_duration_weeks') is None:
    a['consistency_warning']='기존 전체 기간이 미확인이다. 요청 외 필드 보존 조건에 따라 합계를 임의 확정하지 않는다.'
    q['task_data']['allowed_change_paths'].append('/consistency_warning')
  r['messages'][-2]['content']=dump(q);r['messages'][-1]['content']=dump(a);m.update(sha256=sha(r),origin='v3_review_repairs',per_record_semantic_review_completed=False);log.append({'line':i+1,'task':t,'before_sha256':old,'after_sha256':sha(r)})
 TARGET.mkdir();release=TARGET/'release';release.mkdir()
 for name,data in [('all.jsonl',rows),('provenance.jsonl',meta),('changes.jsonl',log)]:
  (release/name).write_text(''.join(dump(x)+'\n' for x in data),encoding='utf-8')
 for split in ['train','validation','test']:(release/f'{split}.jsonl').write_text(''.join(dump(r)+'\n' for r,m in zip(rows,meta) if m['split']==split),encoding='utf-8')
 checks=audit(rows,meta)
 # Warnings are an explicitly permitted additive response, not a copied roadmap field.
 manifest={'version':'reviewed-v4','status':'REVIEW_REPAIRS_PENDING_FINAL_VALIDATION','checks':checks,'files_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in release.glob('*.jsonl')},'regulation_positive_examples_added':False,'training_started':False}
 (release/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');print(dump(checks))
if __name__=='__main__':build()
