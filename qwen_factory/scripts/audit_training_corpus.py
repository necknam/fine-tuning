"""Read-only corpus audit. Findings are repair candidates, not semantic quality scores."""
import argparse, collections, hashlib, json, re
from pathlib import Path

def fingerprint(row):
    return hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def pointer(obj,path):
    for part in path.strip('/').split('/'):
        part=part.replace('~1','/').replace('~0','~')
        obj=obj[int(part)] if isinstance(obj,list) else obj[part]
    return obj

def audit(root,output):
    provenance=[json.loads(x) for x in (root/'provenance.jsonl').read_text(encoding='utf-8').splitlines()]
    byhash={p['sha256']:p for p in provenance}
    findings=[]; counts=collections.Counter(); tasks=collections.Counter(); periods=collections.Counter();families=set(); answers=collections.Counter();systems=collections.Counter()
    for split in ['train','validation','test']:
        for line,raw in enumerate((root/(split+'.jsonl')).read_text(encoding='utf-8').splitlines(),1):
            row=json.loads(raw);sha=fingerprint(row);p=byhash[sha];assert p['split']==split
            task=p['task'];tasks[task]+=1;families.add(p['family_id']);issues=[]
            messages=row['messages'];system=messages[0]['content'];u=json.loads(messages[-2]['content']);a=json.loads(messages[-1]['content']);systems[hashlib.sha256(system.encode()).hexdigest()]+=1;answers[fingerprint(a)]+=1
            if re.search(r'"total_duration_weeks"\s*:\s*8',system):issues.append('fixed_8_week_example_in_system')
            if isinstance(u,dict):
                if 'task' not in u:issues.append('implicit_task_input')
                context=u.get('retrieved_context') or {}; td=u.get('task_data') or {};uc=u.get('user_context') or {};constraints=uc.get('constraints') or {}
            else:context={};td={};uc={};constraints={}
            if task=='generate_roadmap' and isinstance(a,dict):
                ms=a.get('milestones',[]);periods[str(a.get('total_duration_weeks'))]+=1
                if 'duration_weeks' not in constraints:issues.append('no_structured_requested_duration')
                if 'weekly_hours' not in constraints:issues.append('no_structured_weekly_hours')
                for key in ['deliverables','completion_criterion','hours']:
                    if any(key not in m for m in ms):issues.append('missing_stage_'+key)
                ds=[re.fullmatch(r'(\d+)주',str(m.get('duration'))) for m in ms]
                if ms and all(ds) and isinstance(a.get('total_duration_weeks'),int) and sum(int(d.group(1)) for d in ds)!=a['total_duration_weeks']:issues.append('stage_week_sum_mismatch')
                if constraints.get('duration_weeks') is not None and a.get('total_duration_weeks')!=constraints['duration_weeks']:issues.append('requested_duration_mismatch')
            if task=='revise_roadmap' and isinstance(a,dict):
                if not a.get('change_summary'):issues.append('missing_change_summary')
                original=td.get('current_roadmap')
                for path in td.get('preserve_paths',[]):
                    try:
                        if pointer(original,path)!=pointer(a,path):issues.append('preserve_path_changed');break
                    except (KeyError,IndexError,TypeError,ValueError):issues.append('preserve_path_missing');break
            if isinstance(a,dict):
                approved={x['rag_chunk_id'] for x in (context.get('regulation_rag') or {}).get('approved',[])}
                if set(a.get('regulation_citations',[]))-approved:issues.append('unapproved_regulation_citation')
                for kind,key,field in [('courses','course_id','recommended_courses'),('books','isbn','recommended_books'),('certifications','cert_id','recommended_certifications')]:
                    allowed={str(x[key]) for x in context.get(kind,[]) if key in x}
                    for ms in a.get('milestones',[]):
                        if any(not isinstance(x,dict) or key not in x or str(x.get(key)) not in allowed for x in ms.get(field,[])):issues.append('resource_id_not_in_context');break
            issues=sorted(set(issues));counts.update(issues)
            findings.append({'id':p['id'],'sha256':sha,'split':split,'line':line,'task':task,'family_id':p['family_id'],'issues':issues,'disposition':'repair_review' if issues else 'semantic_review_pending','semantic_review_completed':False})
    assert len(findings)==1500
    output.mkdir(parents=True,exist_ok=True)
    (output/'record_audit.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in findings),encoding='utf-8')
    summary={'count':len(findings),'tasks':dict(tasks),'families':len(families),'generation_periods':dict(periods),'findings':dict(counts),'unique_system_prompts':len(systems),'duplicate_answer_groups':sum(n>1 for n in answers.values()),'records_flagged':sum(bool(x['issues']) for x in findings),'status':'AUDITED_NOT_REPAIRED','semantic_review_completed':False,'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.jsonl')},'limitations':['Field absence is a contract gap, not proof that substantive content is absent.','No automatic numeric shortening or fabricated deliverables.','No external model calls; no new training; original files unchanged.']}
    (output/'audit_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]/'data/production/curation_1500');p.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'data/revision_1500');a=p.parse_args();audit(a.root,a.output)
