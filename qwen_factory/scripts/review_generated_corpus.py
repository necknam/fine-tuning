"""Review every generated record, preserve evidence and stage a single explicit regeneration round."""
import argparse,collections,concurrent.futures,copy,hashlib,json,math,time
from pathlib import Path
import app_settings
from rewrite_diverse_corpus import ROOT,filter_evidence,reconcile_justifications,validate,call_one,RUNTIME

def load_requests(folder):return {x['id']:x for x in map(json.loads,(folder/'rewrite_requests.jsonl').read_text(encoding='utf-8').splitlines())}

def inspect(folder, latest=False):
    requests=load_requests(folder);held={x['id']:x['findings'] for x in map(json.loads,(folder/'content_reviews.jsonl').read_text(encoding='utf-8').splitlines())} if (folder/'content_reviews.jsonl').exists() else {}
    output=folder/'reviewed_candidates';output.mkdir(exist_ok=True);summary=collections.Counter();retry=[]
    paths={p.name:p for p in (folder/'generated').glob('*.json')}
    if latest:
        for directory in sorted(folder.glob('generated_retry_*')):
            for p in directory.glob('*.json'):paths[p.name]=p
    for path in sorted(paths.values()):
        item=json.loads(path.read_text(encoding='utf-8'));request=requests[item['id']];review={'id':item['id'],'parent_sha256':request['parent_sha256'],'raw_artifact_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'semantic_review_completed':False,'training_release_ready':False,'edits':[],'errors':[]}
        if item['status']=='REQUEST_RESERVED':review['status']='PENDING';summary['pending']+=1;continue
        value=copy.deepcopy(item.get('output'))
        if not value:review['errors']=['generation_failed_or_incomplete']
        elif item.get('generation_version')=='diversity-v3-multi-author':review['errors']=['schema_object_alias_corruption']
        else:
            try:
                u=filter_evidence(json.loads(request['row']['messages'][-2]['content']));a=value['answer'];c=value['scenario']['constraints'];ms=a['milestones']
                value.setdefault('resource_uses',[])
                if a['strategy_id'] not in ('agent_practical','agent_fasttrack','agent_certified'):
                    system=request['row']['messages'][0]['content'];a['strategy_id']=next((x for x in ['agent_fasttrack','agent_certified','agent_practical'] if x in system),'agent_practical');review['edits'].append('canonical_strategy_id_from_original_role')
                approved={x['rag_chunk_id'] for x in u['retrieved_context'].get('regulation_rag',{}).get('approved',[])}
                citations=[x for x in a['regulation_citations'] if x in approved]
                if citations!=a['regulation_citations']:review['edits'].append('removed_nonapproved_citations');a['regulation_citations']=citations
                if not approved and a['regulation_summary']!='규정 확인 필요':a['regulation_summary']='규정 확인 필요';review['edits'].append('canonical_unapproved_regulation_label')
                _,removed=reconcile_justifications(value,u)
                if removed:review['edits'].append({'removed_recommendations_without_verified_direct_basis':removed})
                if ms and c['duration_weeks']>0 and c['weekly_hours']>0:
                    hours=sum(x['hours'] for x in ms);capacity=c['duration_weeks']*c['weekly_hours']
                    if 0<hours<=capacity and all(x['hours']>0 for x in ms) and (a['total_duration_weeks']!=c['duration_weeks'] or not math.isclose(sum(x['duration'] for x in ms),c['duration_weeks'],abs_tol=.001) or any(x['hours']>x['duration']*c['weekly_hours']+.001 for x in ms)):
                        # Repartition calendar estimates; activities, estimated effort and user's duration are preserved.
                        assigned=0
                        for i,m in enumerate(ms):
                            m['duration']=round(c['duration_weeks']*m['hours']/hours,6) if i<len(ms)-1 else round(c['duration_weeks']-assigned,6);assigned+=m['duration']
                        a['total_duration_weeks']=c['duration_weeks'];review['edits'].append('calendar_repartition_same_effort_same_capacity')
                if ms:
                    for i,m in enumerate(ms,1):m['phase']=i
                    flow=[{'step':i,'title':m['phase_name'],'duration':m['duration'],'focus':m['focus_goal']} for i,m in enumerate(ms,1)]
                    if a['roadmap_flow']!=flow:a['roadmap_flow']=flow;review['edits'].append('rebuild_flow_from_unchanged_milestones')
                review['errors']=validate(value,u)
                if item['id'] in held and path.parent.name=='generated':review['errors'].append('manual_content_hold');review['manual_findings']=held[item['id']]
                review['candidate']={'messages':[{'role':'system','content':RUNTIME},{'role':'user','content':json.dumps({'contract_version':'growpath-runtime/v1','task':'generate_roadmap','conversation_history':[],'hidden_assessment_responses':None,'retrieved_context':u['retrieved_context'],'task_data':{},'user_context':{**value['scenario'],'target_skills':u.get('user_context',{}).get('target_skills',[])}},ensure_ascii=False)},{'role':'assistant','content':json.dumps(a,ensure_ascii=False)}]}
                review['resource_uses']=value['resource_uses'];review['scenario_family']=value.get('scenario_family')
            except (KeyError,TypeError,ValueError,ZeroDivisionError) as e:review['errors']=['local_review_exception_'+type(e).__name__]
        review['status']='REGENERATION_REQUIRED' if review['errors'] else 'STRUCTURAL_REVIEW_CANDIDATE'
        summary[review['status']]+=1
        (output/path.name).write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
        if review['errors']:
            r=copy.deepcopy(request);r['rewrite_brief']['previous_review_findings']=review['errors']+review.get('manual_findings',[]);retry.append(r)
    (folder/'regeneration_requests.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in retry),encoding='utf-8')
    report={'counts':dict(summary),'regeneration_count':len(retry),'structural_review_is_not_semantic_acceptance':True,'training_release_ready':False}
    (folder/'generated_review_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False),flush=True);return retry

def main():
    p=argparse.ArgumentParser();p.add_argument('--regenerate-after-complete',action='store_true');args=p.parse_args();folder=ROOT/'data/revision_1500'
    if args.regenerate_after_complete:
        while True:
            files=list((folder/'generated').glob('*.json'));pending=sum(json.loads(f.read_text(encoding='utf-8'))['status']=='REQUEST_RESERVED' for f in files)
            if len(files)==1003 and pending==0:break
            print('WAITING_FIRST_PASS',len(files),pending,flush=True);time.sleep(30)
    retry=inspect(folder)
    if args.regenerate_after_complete:
        key=app_settings.read(ROOT).get('OPENAI_API_KEY')
        if not key:raise ValueError('OPENAI_API_KEY missing')
        target=folder/'generated_retry_01';target.mkdir(exist_ok=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            futures=[pool.submit(call_one,r,key,target) for r in retry]
            for future in concurrent.futures.as_completed(futures):future.result()
        print('REGENERATION_ROUND_FINISHED; raw first pass and production preserved',flush=True)
if __name__=='__main__':main()
