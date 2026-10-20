"""Generate the explicitly approved supplement, with durable HTTP attempt limits."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import json
import re
from threading import Lock

from src.finetuning import curate_dataset as cli
from src.finetuning.curation_core import validate_candidate, quality_findings, validation_failure_code
from src.finetuning.export_finetuning_dataset import strip_code_fences
from src.finetuning.sampled_selection import template_holds

APPROVED_SHA = 'e15b953ec02f44cb2f99a4b69378f10904535240a38cd07379f198258791f716'


def generation_format(req):
    if req['task']!='progress_checkin':return {}
    props={'self_report_interpretation':{'type':'string'},'action_plan':{'type':'string'},
           'preserve_previous_version':{'type':'boolean','enum':[True]},
           'regulation_summary':{'type':'string','enum':['규정 확인 필요']},
           'regulation_citations':{'type':'array','items':{'type':'string'},'maxItems':0}}
    return {'response_format':{'type':'json_schema','json_schema':{'name':'growpath_progress_v1','strict':True,
        'schema':{'type':'object','properties':props,'required':list(props),'additionalProperties':False}}}}


class DurableBudget:
    def __init__(self, state, save):
        self.state=state; self.save=save; self.lock=Lock()

    def reserve(self, request_id):
        with self.lock:
            counts=self.state['http_attempts']
            if counts.get(request_id,0)>=3 or sum(counts.values())>=789:
                return False
            counts[request_id]=counts.get(request_id,0)+1
            # Persist before transmission; even an interrupted call consumes its slot.
            self.save(self.state)
            return True


def generate_one(req, client, budget):
    c={k:deepcopy(req[k]) for k in ('task','family_id','split','skill_ids','source_fingerprint')}
    c.update(origin='supplement',request_id=req['request_id'],attempt=1,synthetic_scenario=True,
             seed_candidate_id=req['seed_candidate_id'],scenario_case=req['scenario_case'],errors=[])
    messages=deepcopy(req['messages']); last_code='ATTEMPT_BUDGET_EXHAUSTED'; usage=Counter()
    while budget.reserve(req['request_id']):
        try:
            cli.llm_payload(messages)
            response=client.chat.completions.create(model='gpt-5-mini',messages=messages,
                reasoning_effort='low',max_completion_tokens=6000,**generation_format(req))
            if response.usage:
                usage.update(prompt_tokens=response.usage.prompt_tokens,
                             completion_tokens=response.usage.completion_tokens,
                             total_tokens=response.usage.total_tokens)
            choice=response.choices[0]
            if choice.finish_reason!='stop': raise ValueError('INCOMPLETE_GENERATION')
            answer=json.loads(strip_code_fences(choice.message.content or ''))
            c['messages']=deepcopy(req['messages'])+[{'role':'assistant','content':json.dumps(answer,ensure_ascii=False,sort_keys=True)}]
            validate_candidate(c)
            findings=quality_findings(c)
            holds=template_holds(c)
            if findings or holds:
                raise ValueError((findings[0]['code'] if findings else holds[0]))
            c.update(provider={'provider':'openai','model':'gpt-5-mini'},id=cli.candidate_id(c))
            return c, {'request_id':req['request_id'],'status':'GENERATED_LOCAL_PASS_CONTENT_REVIEW_PENDING',
                       'usage':dict(usage)}
        except Exception as exc:
            # Never put raw provider exceptions, keys, or model output into feedback/logs.
            last_code=validation_failure_code(exc)
            if last_code=='UNCLASSIFIED_ERROR':
                known=re.match(r'^([A-Z][A-Z0-9_]{2,70})(?::|$)',str(exc))
                last_code=known.group(1) if known else type(exc).__name__
            messages=deepcopy(req['messages'])
            messages[-1]['content']+='\n[로컬 검증 피드백] 직전 응답 오류 코드: '+last_code+'. 원래 입력과 규격을 지켜 JSON을 다시 작성하세요.'
    return None,{'request_id':req['request_id'],'status':'FAILED_WITHIN_APPROVED_BUDGET',
                 'error_code':last_code,'usage':dict(usage)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work-dir',default=cli.DEFAULT_WORK)
    p.add_argument('--ontology',default='config/finetuning_ontology.yaml')
    p.add_argument('--workers',type=int,default=4)
    p.add_argument('--execute',action='store_true')
    args=p.parse_args();args.minimum_per_task=None;args.model='gpt-5-mini'
    if not 1<=args.workers<=4:raise ValueError('WORKERS_OUTSIDE_1_TO_4')
    work,manifest,onto,_,_,snapshot=cli.load_run(args)
    path=work/'final_supplement_requests.jsonl'
    if cli.file_hash(path)!=APPROVED_SHA:raise ValueError('APPROVED_INPUT_CHANGED')
    plan=json.loads((work/'final_supplement_plan.json').read_text(encoding='utf-8'))
    for field,name in [('selection_sha256','local_selected_candidates.jsonl'),('composition_sha256','composition_plan.json')]:
        if cli.file_hash(work/name)!=plan[field]:raise ValueError('SELECTION_PLAN_CHANGED')
    if plan['source_fingerprint']!=manifest['source_fingerprint']:raise ValueError('SOURCE_CHANGED')
    requests=cli.read_jsonl(path)
    if len(requests)!=263 or len({r['request_id'] for r in requests})!=263:raise ValueError('SCOPE_CHANGED')
    for req in requests:cli.verify_context(req,snapshot,onto);cli.llm_payload(req['messages'])
    if not args.execute:
        print(json.dumps({'status':'PREVIEW','count':263,'max_http_attempts':789,'api_called':False}));return
    from src.clients.llm_adapter import LLMAdapter
    adapter=LLMAdapter();client=adapter._openai_client
    if client is None or str(client.base_url).rstrip('/')!='https://api.openai.com/v1' or client.max_retries!=0:
        raise ValueError('EXACT_OPENAI_ENDPOINT_WITHOUT_SDK_RETRY_REQUIRED')
    state_path=work/'final_supplement_execution.json'
    state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {
        'approved_requests_sha256':APPROVED_SHA,'provider':'openai','model':'gpt-5-mini',
        'external_transfer_approved':True,'http_attempts':{},'results':{},
        'database_changes':False,'training_approved':False}
    if state['approved_requests_sha256']!=APPROVED_SHA:raise ValueError('EXECUTION_SCOPE_CHANGED')
    journal=cli.read_jsonl(work/'generated.jsonl')
    done={r['request_id'] for r in journal if r.get('request_id') in {q['request_id'] for q in requests}}
    # Boundary refusals are locally authored after observed free-text catalog hallucinations.
    # Preserve all previous API outputs and charges; do not spend more calls on this task.
    state['local_authoring_tasks']=['evidence_boundary']
    pending=[r for r in requests if r['task']!='evidence_boundary' and r['request_id'] not in done
             and state['http_attempts'].get(r['request_id'],0)<3]
    state['phase']='generating';cli.write_json(state_path,state)
    budget=DurableBudget(state,lambda s:cli.write_json(state_path,s))
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures={executor.submit(generate_one,req,client,budget):req for req in pending}
        for f in as_completed(futures):
            candidate,result=f.result()
            with budget.lock:
                if candidate is not None:
                    journal.append(candidate);done.add(candidate['request_id'])
                    cli.write_jsonl(work/'generated.jsonl',journal)
                state['results'][result['request_id']]=result
                state.update(generated=len(done),http_attempts_total=sum(state['http_attempts'].values()))
                cli.write_json(state_path,state)
                print(json.dumps({'generated':len(done),'processed':len(state['results']),
                                  'http_attempts':state['http_attempts_total'],'last_status':result['status']}),flush=True)
    with budget.lock:
        remaining_api=[r for r in requests if r['task']!='evidence_boundary' and r['request_id'] not in done]
        state.update(phase='external_generation_complete_boundary_local_authoring_pending' if not remaining_api else 'incomplete',
                     generated=len(done),http_attempts_total=sum(state['http_attempts'].values()),
                     usage=dict(sum((Counter(r.get('usage',{})) for r in state['results'].values()),Counter())))
        cli.write_json(state_path,state)
    print(json.dumps({k:state[k] for k in ('phase','generated','http_attempts_total','usage')}),flush=True)


if __name__=='__main__':main()
