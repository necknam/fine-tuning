"""Portable, dependency-free runtime evaluation contract. No source data or secrets."""
import json,math,re
from datetime import date

CONTRACT_VERSION='growpath-runtime/v1'
TASKS=('generate_roadmap','revise_roadmap','generate_survey','interpret_assessment',
       'resolve_constraints','evidence_boundary','progress_checkin')
ALIASES={'agent_practical':'generate_roadmap','agent_certified':'generate_roadmap',
 'agent_fasttrack':'generate_roadmap','roadmap_iterative_edit':'revise_roadmap',
 'assessment_survey_gen':'generate_survey','growth_checkin':'progress_checkin',
 'boundary_and_evidence_check':'evidence_boundary'}
FIELDS={'recommended_courses':('courses','course_id'),
 'recommended_books':('books','isbn'),'recommended_certifications':('certifications','cert_id')}

def task_of(request):
    if not isinstance(request,dict):return 'generate_roadmap'
    task=request.get('task')
    if task is None:task='generate_survey' if 'slots' in request else 'generate_roadmap'
    task=ALIASES.get(task,task)
    if task not in TASKS:raise ValueError('UNSUPPORTED_CONTRACT_TASK:'+str(task))
    return task

def active_criteria(task):
    if task not in TASKS:raise ValueError('UNSUPPORTED_CONTRACT_TASK')
    keys={'goal_fit','constraints'}
    if task in ('generate_roadmap','revise_roadmap'):keys.add('perspective')
    if task not in ('generate_survey','interpret_assessment'):keys.add('resources')
    if task=='revise_roadmap':keys.add('revision')
    return keys

def report_request(report):
    request=json.loads(next(m['content'] for m in reversed(report['messages']) if m['role']=='user'))
    if not isinstance(request,dict):raise ValueError('OBJECT_REQUEST_REQUIRED')
    return request

def report_answer(report):
    text=report['tuned']['text'].strip()
    if text.startswith('```'):text='\n'.join(text.splitlines()[1:-1])
    return json.loads(text)

def number(value):return type(value) in (int,float) and math.isfinite(value)

def approved_evidence(row,as_of):
    if not isinstance(row,dict) or not (row.get('search_status')=='active'
            and row.get('review_status')=='approved' and row.get('requires_review') is False
            and row.get('availability_status')=='available'):return False
    try:
        day=date.fromisoformat(str(as_of)) if as_of else date.today()
        start=date.fromisoformat(str(row['effective_from']))
        end=date.fromisoformat(str(row['effective_to'])) if row.get('effective_to') else None
        return start<=day and (end is None or day<end)
    except (ValueError,TypeError,KeyError):return False

def pointer(value,path):
    if not isinstance(path,str) or not path.startswith('/'):raise ValueError('JSON_POINTER_REQUIRED')
    for token in path.split('/')[1:]:
        token=token.replace('~1','/').replace('~0','~')
        value=value[int(token)] if isinstance(value,list) else value[token]
    return value

def runtime_checks(request,answer):
    task=task_of(request);result=[]
    if task=='generate_survey':
        slots=request.get('slots',[])
        if not isinstance(slots,list) or not slots or not isinstance(answer,list):return ['설문 형식: 위반']
        valid=len(slots)==len(answer);texts=[]
        for item,slot in zip(answer,slots):
            if not isinstance(item,dict) or not isinstance(slot,dict):valid=False;continue
            text=item.get('question');valid=valid and isinstance(text,str)
            if not isinstance(text,str):continue
            texts.append(' '.join(text.split()).casefold())
            valid=valid and (type(item.get('skill_id')) is int and type(item.get('sequence_no')) is int
                and item['skill_id']==slot.get('skill_id') and item['sequence_no']==slot.get('sequence_no')
                and isinstance(slot.get('skill'),str) and slot['skill'] in text
                and 5<=len(text.strip())<=500 and text.count('?')==1 and text.strip().endswith('알고 있나요?'))
        valid=valid and len(texts)==len(set(texts))
        return ['설문 슬롯·스킬·단일 문항: '+('준수' if valid else '위반')]
    if not isinstance(answer,dict):return ['응답 형식: 위반']
    if task=='interpret_assessment':
        result.append('진단 방식: '+('준수' if answer.get('assessment_method')=='self_report' else '위반'))
        return result
    roadmap=answer.get('roadmap',answer)
    if not isinstance(roadmap,dict):return ['로드맵 형식: 위반']
    stages=roadmap.get('milestones')
    if not isinstance(stages,list):return ['로드맵 마일스톤: 구조화된 데이터 부족으로 확인 불가']
    if not stages or any(not isinstance(s,dict) for s in stages):return ['로드맵 형식: 위반']
    context=request.get('retrieved_context') or {}
    if not isinstance(context,dict):return ['검색 근거 형식: 위반']
    allowed={(kind,type(r.get(pk)).__name__,str(r.get(pk))) for kind,pk in FIELDS.values()
             for r in context.get(kind,[]) if isinstance(r,dict) and type(r.get(pk)) in (int,str)}
    used=set();resource_valid=True
    for stage in stages:
        for field,(kind,pk) in FIELDS.items():
            choices=stage.get(field)
            if not isinstance(choices,list):resource_valid=False;continue
            for item in choices:
                if not isinstance(item,dict) or type(item.get(pk)) not in (int,str):resource_valid=False;continue
                used.add((kind,type(item[pk]).__name__,str(item[pk])))
    if used-allowed:result.append('자료 ID: 미제공 ID 사용: '+', '.join(sorted(k[0]+':'+k[2] for k in used-allowed)))
    elif not resource_valid:result.append('자료 ID: 구조 누락·형식 위반')
    else:result.append('자료 ID: 목록 내 ID만 사용')
    reg=context.get('regulation_rag') or {};approved=reg.get('approved',[]) if isinstance(reg,dict) else []
    approved_ids={r.get('rag_chunk_id') for r in approved if approved_evidence(r,reg.get('as_of'))}
    citations=roadmap.get('regulation_citations')
    valid=isinstance(citations,list) and all(isinstance(x,str) and x in approved_ids for x in citations)
    if not approved_ids:valid=valid and not citations and roadmap.get('regulation_summary')=='규정 확인 필요'
    result.append('규정 인용: '+('준수' if valid else '위반'))
    user=request.get('user_context') or {};limits=user.get('constraints') or user
    if not isinstance(limits,dict):limits={}
    for field,total,label in [('hours','total_hours','시간'),('cost_krw','total_cost_krw','비용')]:
        values=[s.get(field) for s in stages]
        if all(number(x) and x>=0 for x in values) and number(roadmap.get(total)):
            result.append(label+' 합계: '+('일치' if abs(sum(values)-roadmap[total])<.001 else '불일치'))
        else:result.append(label+' 합계: 구조화된 수치 부족으로 확인 불가')
    if number(limits.get('budget_krw')) and number(roadmap.get('total_cost_krw')):
        result.append('예산 한도: '+('준수' if 0<=roadmap['total_cost_krw']<=limits['budget_krw'] else '위반'))
    if all(number(limits.get(k)) for k in ('duration_weeks','weekly_hours')) and number(roadmap.get('total_hours')):
        result.append('시간 한도: '+('준수' if 0<=roadmap['total_hours']<=limits['duration_weeks']*limits['weekly_hours']+.001 else '위반'))
    weeks=[re.fullmatch(r'(\d+)\s*주',str(s.get('duration') or '')) for s in stages]
    total=roadmap.get('total_duration_weeks')
    if all(weeks) and type(total) is int:
        result.append('기간 합계: '+('일치' if sum(int(w[1]) for w in weeks)==total else '불일치'))
    else:result.append('기간 합계: 구조화된 수치 부족으로 확인 불가')
    if type(limits.get('duration_weeks')) is int and type(total) is int:
        result.append('기간 한도: '+('준수' if 0<total<=limits['duration_weeks'] else '위반'))
    start=limits.get('start_stage')
    if task=='generate_roadmap' and type(start) is int and start>1:
        phases=[s.get('stage',s.get('phase')) for s in stages]
        if any(type(x) is not int for x in phases):result.append('시작 단계: 단계 번호 부족으로 확인 불가')
        else:
            bad=[s for s,n in zip(stages,phases) if n<start and number(s.get('hours')) and s['hours']>0
                 and not s.get('completed') and s.get('status') not in ('completed','done')]
            result.append('시작 단계: '+('위반 · 이전 단계 신규 시간 배정' if bad else '이전 단계 신규 시간 배정 없음'))
    if task=='revise_roadmap':
        data=request.get('task_data') or {};current=data.get('current_roadmap') or request.get('current_roadmap')
        paths=data.get('preserve_paths',[])
        if not current or not paths:result.append('부분 수정 보존: 명시된 보존 경로 부족으로 확인 불가')
        else:
            try:valid=all(pointer(current,p)==pointer(roadmap,p) for p in paths)
            except (KeyError,IndexError,TypeError,ValueError):valid=False
            result.append('부분 수정 보존: '+('준수' if valid else '위반'))
    return result
