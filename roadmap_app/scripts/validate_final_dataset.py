"""Read-only audit of the released SFT/DPO files and current Supabase facts."""
from pathlib import Path
from collections import Counter
import argparse,gzip,hashlib,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.shared.dataset_integrity import digest,validate_record,validate_roadmap,current_evidence,validate_current_context
from src.shared.training_semantics import validate_training_semantics
from src.finetuning.export_finetuning_dataset import current_source_fingerprint
from src.database.deployment import connect

def read(path):
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]

def validate(path):
    manifest=json.loads((path/'manifest.json').read_text(encoding='utf-8'))
    for name,expected in manifest['files_sha256'].items():
        target=(path/name).resolve()
        if not target.is_relative_to(path.resolve()):raise ValueError('UNSAFE_MANIFEST_PATH')
        if hashlib.sha256(target.read_bytes()).hexdigest()!=expected:raise ValueError('FILE_HASH_MISMATCH:'+name)
    with connect('SUPABASE_DB_URL') as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        if current_source_fingerprint(c)!=manifest['source_sha256']:raise ValueError('SOURCE_DB_CHANGED')
        snapshot=current_evidence(c)
    allrows=read(path/'sft_all.jsonl');provenance=read(path/'provenance.jsonl')
    if len(allrows)!=3000 or len(provenance)!=3000:raise ValueError('COUNT_MISMATCH')
    groups={};seen=set();prompts={};expected={s:[] for s in ('train','validation','test')};tasks=Counter()
    primary={'assessment_plan_refine','assessment_survey_gen','agent_practical','agent_certified','agent_fasttrack'}
    for row,p in zip(allrows,provenance):
        h=digest(row)
        if h!=p['sha256'] or h in seen:raise ValueError('HASH_OR_DUPLICATE_ERROR')
        seen.add(h);s=p['split'];expected[s].append(h);tasks[p['task']]+=1
        old=groups.setdefault(p['family_id'],s)
        if old!=s:raise ValueError('FAMILY_LEAKAGE')
        ph=digest(row['messages'][:2]);old=prompts.setdefault(ph,s)
        if old!=s:raise ValueError('PROMPT_LEAKAGE')
        messages=row['messages']
        if [m['role'] for m in messages]!=['system','user','assistant']:raise ValueError('MESSAGE_SCHEMA')
        output=json.loads(messages[2]['content'])
        validate_training_semantics({'messages':messages})
        if p['task'] in primary:validate_record({'task':p['task'],'messages':messages})
        if p['task'].startswith('agent_') or p['task'] not in primary:
            payload=json.loads(messages[1]['content']);ctx=payload['retrieved_context']
            validate_current_context(ctx,snapshot)
            if p['task'].startswith('agent_'):validate_roadmap(output,ctx)
            elif p['task']=='roadmap_iterative_edit':
                validate_roadmap(output,ctx);before=payload['current_roadmap']
                if len(before['milestones'])!=len(output['milestones']):raise ValueError('EDIT_PHASE_COUNT')
                changes=0
                for old,new in zip(before['milestones'],output['milestones']):
                    if old!=new:
                        changes+=1
                        if {k:v for k,v in old.items() if k!='duration'}!={k:v for k,v in new.items() if k!='duration'}:
                            raise ValueError('EDIT_INVARIANCE')
                if changes!=1:raise ValueError('EDIT_CHANGE_COUNT')
            elif p['task']=='growth_checkin':
                validate_roadmap(payload['current_roadmap'],ctx)
                if payload['self_rating_5pt']!=3 or '보통' not in output['self_report_interpretation']:
                    raise ValueError('SELF_REPORT_INTERPRETATION')
            elif p['task']!='boundary_and_evidence_check':raise ValueError('UNKNOWN_DERIVED_TASK')
            if output.get('regulation_citations',[]):raise ValueError('UNAPPROVED_CITATION')
    for s,hashes in expected.items():
        if [digest(r) for r in read(path/f'sft_{s}.jsonl')]!=hashes:raise ValueError('SPLIT_CONTENT_MISMATCH')
    dpoprovs=read(path/'dpo_provenance.jsonl');dpopairs={s:read(path/f'dpo_{s}.jsonl') for s in expected}
    dpo_count=0
    for s,pairs in dpopairs.items():
        ps=[p for p in dpoprovs if p['split']==s]
        if len(ps)!=len(pairs):raise ValueError('DPO_PROVENANCE_COUNT')
        for pair,p in zip(pairs,ps):
            if groups[p['family_id']]!=s:raise ValueError('DPO_FAMILY_LEAKAGE')
            chosen={'messages':pair['prompt']+pair['chosen']}
            if digest(chosen)!=p['sft_sha256']:raise ValueError('DPO_CHOSEN_NOT_SFT')
            ctx=json.loads(pair['prompt'][1]['content'])['retrieved_context']
            good=json.loads(pair['chosen'][0]['content']);bad=json.loads(pair['rejected'][0]['content'])
            validate_roadmap(good,ctx)
            try:validate_roadmap(bad,ctx)
            except ValueError:pass
            else:raise ValueError('DPO_NEGATIVE_VALID')
            rid=str(bad['milestones'][0]['recommended_courses'][0]['course_id'])
            if ('courses',rid) not in snapshot['usable']:raise ValueError('DPO_NEGATIVE_RESOURCE_NOT_REAL_AVAILABLE')
            dpo_count+=1
    if dpo_count!=1000:raise ValueError('DPO_COUNT')
    tokenized={}
    token_report=json.loads((path/'tokenization_report.json').read_text(encoding='utf-8'))
    for name,h in token_report['source_sft_sha256'].items():
        if hashlib.sha256((path/name).read_bytes()).hexdigest()!=h:raise ValueError('TOKENIZATION_SOURCE_MISMATCH')
    for s in expected:
        file=path/f'sft_tokenized_{s}.jsonl.gz'
        if not file.exists():raise ValueError('TOKENIZED_FILE_MISSING')
        count=0
        with gzip.open(file,'rt',encoding='utf-8') as handle:
            for line in handle:
                row=json.loads(line);ids,labels=row['input_ids'],row['labels']
                if len(ids)!=len(labels):raise ValueError('TOKEN_LABEL_LENGTH')
                first=next((i for i,x in enumerate(labels) if x!=-100),None)
                if first is None or first==0 or labels[first:]!=ids[first:]:raise ValueError('ASSISTANT_MASK')
                count+=1
        if count!=len(expected[s]):raise ValueError('TOKENIZED_COUNT')
        tokenized[s]=count
    return {'status':'PASS','sft_records':3000,'dpo_pairs':dpo_count,'task_counts':dict(tasks),
        'split_counts':{s:len(v) for s,v in expected.items()},'tokenized_counts':tokenized,
        'exact_duplicates':0,'family_overlap':0,'prompt_overlap':0,'source_sha256':manifest['source_sha256'],
        'human_review_completed':False,'model_weights_loaded':False,'database_changes':False,
        'llm_or_embedding_called':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--report',type=Path)
    args=p.parse_args()
    try:result=validate(args.input.resolve())
    except Exception as exc:
        result={'status':'FAIL','error_type':type(exc).__name__,'reason':str(exc) if isinstance(exc,ValueError) else 'Audit failed; inspect local files or DB connection.'}
    text=json.dumps(result,ensure_ascii=False,indent=2);print(text)
    if args.report:args.report.write_text(text+'\n',encoding='utf-8')
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
