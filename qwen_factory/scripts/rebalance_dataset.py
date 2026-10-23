"""Reproducible local augmentation; never changes the frozen v1 or active recipes."""
import copy,hashlib,itertools,json,random,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'data/production/curation_1500'
TARGET=ROOT/'data/production/curation_1500_balanced_v2'
COUNTS=dict(generate_roadmap=600,revise_roadmap=225,generate_survey=225,interpret_assessment=150,resolve_constraints=120,evidence_boundary=120,progress_checkin=60)
def dump(x):return json.dumps(x,ensure_ascii=False,sort_keys=True)
def sha(x):return hashlib.sha256(dump(x).encode()).hexdigest()
def read(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def variant(row,task,index):
 row=copy.deepcopy(row);q=json.loads(row['messages'][-2]['content']);a=json.loads(row['messages'][-1]['content']);method=''
 if task=='generate_survey':
  # Preserve question/skill/focus binding; subset selection is augmentation, not new expertise.
  n=len(a);combos=list(itertools.combinations(range(n),8))
  if index>=len(combos) or n<=8:return None
  indices=combos[index];q['slots']=[q['slots'][i] for i in indices];a=[a[i] for i in indices]
  for i,(s,item) in enumerate(zip(q['slots'],a),1):s['sequence_no']=i;item['sequence_no']=i
  method='survey_eight_slot_subset'
 elif task=='interpret_assessment':
  responses=q['task_data']['responses'];labels=['아주 모른다','모른다','보통이다','안다','잘 안다']
  for i,r in enumerate(responses):r['score']=1+(i+index+2)%5
  a={'assessment_method':'self_report','observations':[], 'priorities':[], 'questions':['이 프로젝트와 관련해 직접 작성한 코드나 실행 기록 중 확인 가능한 자료가 있나요?'],'regulation_summary':'규정 확인 필요','regulation_citations':[]}
  for r in responses:
   score=r['score'];sid=r['skill_id'];a['observations'].append(dict(skill_id=sid,score=score,interpretation=f'{labels[score-1]}라는 자기보고 응답입니다. 객관적 숙련도나 실무 성과를 입증하지 않습니다.'))
  for r in sorted(responses,key=lambda r:r['score']):
   a['priorities'].append(dict(skill_id=r['skill_id'],reason=f"자기보고 {r['score']}점은 학습 시작점을 정하는 참고 정보이며 기존 경험 검증 후 조정합니다.",next_action='프로젝트에서 이 스킬을 사용하는 처리 단계 하나를 골라 입력·예상 결과·실제 결과를 기록하는 작은 재현 과제를 수행합니다. 이미 수행한 코드가 있으면 새 기초 학습 대신 해당 코드와 실패 사례를 먼저 확인합니다.'))
  method='counterfactual_self_report_scores'
 elif task=='resolve_constraints':
  limits={'budget_krw':10000+index*5000,'duration_weeks':2+index%3,'weekly_hours':2+index%4,'start_stage':1};expense=limits['budget_krw']+20000
  q['user_context']['constraints']=limits;q['task_data']={'expense_source':'synthetic_user_plan','planned_expense_krw':expense,'scenario_note':'이번 가상 시나리오의 최신 제약은 user_context.constraints이며 배경 설명의 과거 일정은 적용하지 않습니다.','user_request':f'실습 환경 예상 비용 {expense}원입니다. 예산과 기간을 늘리지 않고 원래 목표를 유지할 수 있는지 확인해 주세요.'}
  a={'conflicts':[f"가상 계획 비용 {expense}원이 예산 {limits['budget_krw']}원보다 20000원 많습니다. 동일 환경을 그대로 사용하는 계획은 현재 예산을 충족하지 못합니다."],'alternatives':[{'adjustment':'원래 목표와 필수 검증 기준을 유지한 축소 실험의 범위·견적을 먼저 확인합니다.','reason':f"가용 시간은 {limits['duration_weeks']*limits['weekly_hours']}시간입니다. 범위 축소로 목표가 달성되지 않으면 대체 완료로 처리하지 않습니다."},{'adjustment':'기존 사용 가능한 환경과 실제 비용을 확인한 뒤 실행 여부를 결정합니다.','reason':'무료 API·크레딧·회사 지원은 제공된 근거로 확정되지 않았으므로 0원이나 지원 확정으로 가정하지 않습니다.'}],'questions':['필수 목표를 유지하면서 환경 또는 실험 규모를 변경할 수 있나요?','추가 결제 없이 사용할 수 있는 기존 환경과 확인된 비용 내역이 있나요?'],'regulation_summary':'규정 확인 필요','regulation_citations':[]};method='counterfactual_budget_conflict'
 elif task=='evidence_boundary':
  q['retrieved_context']={'courses':[],'books':[],'certifications':[],'regulation_rag':{'approved':[],'review_only':[],'status':'verification_required'}}
  questions=['검색된 자료가 없지만 이 프로젝트의 유료 강좌명과 가격을 확정해 주세요.','근거 없이 무료 API로 목표를 완수할 수 있다고 보장해 주세요.','규정 근거가 없지만 교육비 전액 지원을 확정해 주세요.']
  q['task_data']={'user_query':questions[index%3]}
  a={'response_type':'VERIFICATION_REQUIRED','topic':['강좌 가격','무료 API','교육비 지원'][index%3],'answer':'제공된 검색 결과가 비어 있어 요청한 사실을 확정할 수 없습니다. 강좌·가격·무료 이용 조건·지원 자격을 만들어내지 않겠습니다.','next_step':'프로젝트 목표는 유지하되 필요한 근거를 다시 검색하고 공식 조건을 확인한 뒤 계획에 반영합니다. 확인 전에는 비용이나 목표 완수를 보장하지 않습니다.','regulation_summary':'규정 확인 필요','regulation_citations':[]};method='empty_retrieval_boundary'
 elif task=='revise_roadmap':
  current=q['task_data'].get('current_roadmap');stages=current.get('milestones',[]) if current else []
  if not stages:return None
  q['task_data']={'current_roadmap':current,'user_feedback':'첫 마일스톤 phase_name만 진행 점검으로 바꾸세요. 다른 값은 모두 보존하세요.','preserve_paths':['/'+k for k in current if k!='milestones']+['/milestones/'+str(i) for i in range(1,len(stages))]+['/milestones/0/'+k for k in stages[0] if k!='phase_name']}
  row['messages'][0]['content']='사용자가 지정한 필드 하나만 수정하고 나머지 값과 완료 기록을 그대로 보존하세요. JSON 객체만 반환하세요.'
  a=copy.deepcopy(current);a['milestones'][0]['phase_name']='진행 점검';method='single_field_revision'
 else:return None
 row['messages'][-2]['content']=dump(q);row['messages'][-1]['content']=dump(a)
 return row,method

def main():
 if TARGET.exists():raise ValueError('Refusing overwrite: '+str(TARGET))
 rows=read(SOURCE/'all.jsonl');meta=read(SOURCE/'provenance.jsonl');groups=collections.defaultdict(list)
 for row,m in zip(rows,meta):
  if sha(row)!=m['sha256']:raise ValueError('Source provenance mismatch')
  groups[m['split'],m['task']].append((row,m))
 quotas={'train':[480,180,180,120,96,96,48],'validation':[60,22,23,15,12,12,6],'test':[60,23,22,15,12,12,6]};selected=[]
 for split,nums in quotas.items():
  for task,want in zip(COUNTS,nums):
   pool=groups[split,task];random.Random(42).shuffle(pool);items=list(pool[:want]);seen={sha(r) for r,m in items}
   for index in range(100):
    if len(items)>=want:break
    for row,m in pool:
     out=variant(row,task,index)
     if out is None:continue
     new,method=out;h=sha(new)
     if h in seen:continue
     nm=copy.deepcopy(m);nm.update(id=h,sha256=h,parent_id=m['id'],origin='local_deterministic_augmentation',augmentation=method,per_record_semantic_review_completed=False);items.append((new,nm));seen.add(h)
     if len(items)>=want:break
   if len(items)!=want:raise ValueError((split,task,len(items),want))
   selected.extend(items)
 # Validate schema, exact row hashes, family isolation, prompt overlap, source ID preservation.
 import sys;sys.path.insert(0,str(ROOT/'scripts'));from prepare_data import validate
 families={};prompts={};hashes=set()
 for row,m in selected:
  prompt=validate(row);json.loads(row['messages'][-1]['content']);h=sha(row)
  if h in hashes:raise ValueError('Duplicate record')
  hashes.add(h)
  for mapping,key in [(families,m['family_id']),(prompts,prompt)]:
   if key in mapping and mapping[key]!=m['split']:raise ValueError('Cross split leakage')
   mapping[key]=m['split']
  if m['task']=='generate_survey':
   q=json.loads(row['messages'][-2]['content']);a=json.loads(row['messages'][-1]['content'])
   if len(a)!=len(q['slots']) or any(x['skill_id']!=s['skill_id'] or x['sequence_no']!=s['sequence_no'] for x,s in zip(a,q['slots'])):raise ValueError('Survey binding')
 TARGET.mkdir(parents=True)
 for name,records in [('all.jsonl',[r for r,m in selected]),('provenance.jsonl',[m for r,m in selected])]+[(s+'.jsonl',[r for r,m in selected if m['split']==s]) for s in quotas]:
  (TARGET/name).write_text(''.join(dump(r)+'\n' for r in records),encoding='utf-8',newline='\n')
 manifest={'version':'growpath-balanced-1500/v2','task_counts':dict(collections.Counter(m['task'] for r,m in selected)),'split_counts':dict(collections.Counter(m['split'] for r,m in selected)),'augmentation_counts':dict(collections.Counter(m.get('augmentation','original') for r,m in selected)),'source_sha256':hashlib.sha256((SOURCE/'all.jsonl').read_bytes()).hexdigest(),'files_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in TARGET.glob('*.jsonl')},'checks':{'schema':True,'family_isolation':True,'cross_split_prompt_isolation':True,'exact_duplicates':0,'survey_binding':True},'limitations':['Existing 12 project families retained. No new project families.','Deterministic augmentation, not independently generated new knowledge.','Full semantic review and model-tokenizer length verification pending. Existing inherited answer quality issues may remain.'],'status':'REBALANCED_REVIEW_CANDIDATE','training_started':False,'active_recipe_changed':False}
 (TARGET/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(manifest,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
