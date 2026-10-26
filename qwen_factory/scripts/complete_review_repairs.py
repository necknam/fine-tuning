import json,copy,collections,hashlib
from repair_reviewed_dataset import TARGET
from refine_dataset import read,parts,dump,sha,audit
p=TARGET/'release';rows=read(p/'all.jsonl');meta=read(p/'provenance.jsonl');regs=json.loads((TARGET/'approved_regulation_snapshot.json').read_text(encoding='utf-8'));counter=collections.Counter();coverage=collections.Counter()
for r,m in zip(rows,meta):
 q,a=parts(r);task=m['task'];j=counter[task];counter[task]+=1
 if task=='generate_survey':
  context=q.get('question_context','');short=context[:24]+'…'+context[-24:] if len(context)>48 else context
  for slot,item in zip(q['slots'],a):
   tail=item['question'].split(': ',1)[-1];item['question']=short+': '+tail
 if task=='progress_checkin':
  u=q.get('user_context') or {};a['project_goal']=u.get('goal') or u.get('work_context_summary')
 if task=='revise_roadmap':
  td=q['task_data'];current=copy.deepcopy(td['current_roadmap']);facts=q.get('retrieved_context',{}).get('courses') or []
  if j%5==0 and len(current['milestones'])>1 and facts:
   current['completed_milestone_indices']=[0];a=copy.deepcopy(current);a['milestones'][1]['recommended_courses']=[{'course_id':facts[0]['course_id']}]
   td.update(current_roadmap=current,user_feedback=f"보조 학습 자료를 바꿉니다. 두 번째 단계 recommended_courses를 검색 후보 {facts[0]['course_id']} 한 개로 교체하고 완료 단계와 다른 값은 보존하세요. 수강 가능성은 별도 확인합니다.",allowed_change_paths=['/milestones/1/recommended_courses']);coverage['resource_replacement']+=1
  elif j%5==1:
   current['completed_milestone_indices']=[0];a=copy.deepcopy(current);a['edit_status']='COMPLETED_STAGE_CHANGE_REQUIRES_CONFIRMATION'
   td.update(current_roadmap=current,user_feedback='완료 기록이 있는 첫 단계를 새 목표로 덮어써 주세요. 기존 완료 기록을 폐기하는 승인은 아직 하지 않았습니다.',allowed_change_paths=['/edit_status']);coverage['completed_stage_confirmation']+=1
 if task=='evidence_boundary' and j%4==0:
  reg=regs[j//4];q['retrieved_context']['regulation_rag']={'approved':[reg],'review_only':[],'as_of':'2026-10-23','status':'available'}
  q['task_data']={'scenario_kind':'approved_excerpt','user_query':'제공된 승인 규정의 문서 위치와 원문 앞부분을 인용하세요. 이 직원의 지원 자격이나 지원 금액을 확정하지 마세요.'}
  excerpt=reg['chunk_text'][:160]
  a={'response_type':'SUPPORTED_EXCERPT','known_facts':[{'rag_chunk_id':reg['rag_chunk_id'],'context_path':reg['context_path'],'excerpt':excerpt}],'answer':'제공된 승인 원문의 발췌다. 발췌에 포함되지 않은 예외·조건과 직원 개인의 적용 여부는 전체 원문과 해당 정보를 추가 확인해야 한다.','regulation_summary':reg['context_path'],'regulation_citations':[reg['rag_chunk_id']]};coverage['approved_excerpt']+=1
 r['messages'][-2]['content']=dump(q);r['messages'][-1]['content']=dump(a);m['sha256']=sha(r)
original=read(TARGET.parent/'curation_1500_reviewed_v3/release/all.jsonl')
changes=[{'line':i+1,'task':m['task'],'before_sha256':sha(before),'after_sha256':sha(after)} for i,(before,after,m) in enumerate(zip(original,rows,meta))]
for name,data in [('all.jsonl',rows),('provenance.jsonl',meta),('changes.jsonl',changes)]: (p/name).write_text(''.join(dump(x)+'\n' for x in data),encoding='utf-8')
for split in ['train','validation','test']:(p/f'{split}.jsonl').write_text(''.join(dump(r)+'\n' for r,m in zip(rows,meta) if m['split']==split),encoding='utf-8')
checks=audit(rows,meta);coverage['known_total_cost']=sum(parts(r)[1].get('total_cost_krw') is not None for r,m in zip(rows,meta) if m['task']=='generate_roadmap');coverage['progress_states']=dict(collections.Counter(parts(r)[1]['status'] for r,m in zip(rows,meta) if m['task']=='progress_checkin'))
manifest=json.loads((p/'manifest.json').read_text(encoding='utf-8'));manifest.update(checks=checks,repair_coverage=coverage,regulation_positive_examples_added=True,status='CONTENT_REPAIRED_PENDING_TOKEN_CHECK',files_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.glob('*.jsonl')});(p/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');print(dump({'checks':checks,'coverage':coverage}))
