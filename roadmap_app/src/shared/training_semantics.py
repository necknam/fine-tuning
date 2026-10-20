"""High-precision training checks: no invented score facts or guaranteed outcomes."""
import json,re

def strings(value):
    if isinstance(value,str):yield value
    elif isinstance(value,list):
        for item in value:yield from strings(item)
    elif isinstance(value,dict):
        for item in value.values():yield from strings(item)

def validate_training_semantics(record):
    messages=record['messages'];answer=json.loads(messages[-1]['content'])
    texts=list(strings(answer))
    for text in texts:
        for match in re.finditer(r'(?:\d+(?:\.\d+)?\s*%|성공률|합격)[^.!?\n]{0,40}보장',text):
            after=text[match.end():match.end()+24]
            if not re.match(r'\s*(?:하지|할\s*수\s*없|하진|하는\s*것은\s*아니|을\s*하지)',after):
                raise ValueError('UNSUPPORTED_GUARANTEED_OUTCOME')
    try:payload=json.loads(messages[1]['content'])
    except (ValueError,TypeError):return
    if not isinstance(payload,dict):return
    assessment=payload.get('hidden_assessment_responses') or {}
    scores=[r.get('score') for r in assessment.get('responses',[]) if type(r.get('score')) in (int,float)]
    means=[assessment.get('overall_mean_score')]+[s.get('mean_score') for s in assessment.get('skills',[])]
    means=[float(x) for x in means if type(x) in (int,float)]
    for text in texts:
        if scores and min(scores)>2 and re.search(r'(?:낮은|취약|하위)[^.!?\n]{0,16}[12]\s*[~∼-]\s*[12]\s*점',text):
            raise ValueError('SELF_REPORT_LOW_SCORE_NOT_PRESENT')
        for match in re.finditer(r'(?:평균\s*(?:(?:자기보고|self[- ]report)\s*)?점수|자기보고\s*평균)\s*([0-5](?:\.\d+)?)',text,re.I):
            value=float(match.group(1))
            if means and not any(abs(value-x)<=.051 for x in means):
                raise ValueError('SELF_REPORT_MEAN_MISMATCH')
    if not isinstance(answer,dict):return
    context=payload.get('retrieved_context') or {}
    courses={str(c['course_id']):c for c in context.get('courses',[])}
    project=json.dumps(payload.get('user_context') or payload.get('current_roadmap') or {},ensure_ascii=False)
    for milestone in answer.get('milestones',[]):
        for item in milestone.get('recommended_courses',[]):
            course=courses.get(str(item.get('course_id')),{});title=course.get('title') or ''
            for pattern in (r'Dynamics\s*365\s*Commerce',r'Quantum|양자'):
                if re.search(pattern,title,re.I) and not re.search(pattern,project,re.I):
                    raise ValueError('COURSE_TOPIC_MISMATCH')
