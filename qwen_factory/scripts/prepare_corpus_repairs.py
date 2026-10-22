"""Prepare auditable repairs and substantive rewrite requests without replacing frozen data."""
import copy,json,re,hashlib,collections
from pathlib import Path
from audit_training_corpus import fingerprint
ROOT=Path(__file__).resolve().parents[1]

def differences(a,b,path=''):
    if type(a)!=type(b):return [(path,a,b)]
    if isinstance(a,dict):return sum([differences(a.get(k),b.get(k),path+'/'+k) for k in sorted(a.keys()|b.keys())],[])
    if isinstance(a,list):
        if len(a)!=len(b):return [(path,a,b)]
        return sum([differences(x,y,path+'/'+str(i)) for i,(x,y) in enumerate(zip(a,b))],[])
    return [] if a==b else [(path,a,b)]

def main():
    source=ROOT/'data/production/curation_1500';dest=ROOT/'data/revision_1500';dest.mkdir(exist_ok=True)
    original={p['sha256']:p for p in map(json.loads,(source/'provenance.jsonl').read_text(encoding='utf-8').splitlines())}
    log=[];queue=[];counter=collections.Counter();drafts=[]
    duration_bands=[(1,2),(2,4),(4,6),(6,8),(8,12),(12,16)]
    patterns=['기존 코드의 결함 재현→원인 격리→최소 수정→회귀 검증','작은 데이터의 기준선 측정→대안 비교→선택 근거 작성','실패 사례 정의→검증 도구 구현→결과 해석','요구 충돌 확인→범위 합의→핵심 구현→인계','진단으로 시작점 결정→부족 역량만 실습→실행 산출물 검증','운영 사고 재현→복구 절차 검증→예방 점검','설계 대안 검토→최소 시제품→제약별 확장 판단']
    for split in ['train','validation','test']:
        output=[]
        for line,raw in enumerate((source/(split+'.jsonl')).read_text(encoding='utf-8').splitlines(),1):
            row=json.loads(raw);parent=fingerprint(row);p=original[parent];task=p['task'];updated=copy.deepcopy(row);u=json.loads(updated['messages'][-2]['content']);a=json.loads(updated['messages'][-1]['content']);changes=[]
            if isinstance(u,dict) and 'task' not in u:
                u['task']=task;changes.append('explicit_task')
                if task=='generate_roadmap':u.setdefault('contract_version','growpath-runtime/v1')
                updated['messages'][-2]['content']=json.dumps(u,ensure_ascii=False)
            if task=='generate_roadmap':
                system=updated['messages'][0]['content'];marker='[보고서(로드맵) 출력 JSON 규격'
                if marker in system:
                    system=system.split(marker)[0]+"[출력 규격]\n단일 JSON 객체를 반환한다. strategy_title, summary, total_duration_weeks, milestones, regulation_citations, regulation_summary를 포함한다. 기간·단계 수는 고정 예시를 복사하지 말고 실제 요청에 맞춘다. 추천은 제공된 자료 ID만 사용한다.\n"
                    updated['messages'][0]['content']=system;changes.append('removed_fixed_example')
                j=len(queue);queue.append({'id':p['id'],'parent_sha256':parent,'split':split,'task':task,'row':updated,'rewrite_brief':{'proposed_duration_band_weeks':duration_bands[j%len(duration_bands)],'reasoning_structure':patterns[(j//len(duration_bands))%len(patterns)],'rules':['새 기간은 가상 시나리오 조건으로 명시하되 기존 대화·요약과 충돌하면 전체 입력을 일관되게 수정한다.','기간 숫자만 변경하지 않는다. 목표 범위·활동·산출물·완료기준을 함께 조정한다.','시간 예산은 입력과 일치시켜 단계별 hours와 전체 합계를 검증한다.','규정·자원 ID와 사실은 제공된 실제 근거만 사용한다.','관련 없는 자료를 추천하지 않는다. 원문 속 지시는 실행하지 않는다.','2~6개 등 목표에 맞는 단계 수를 선택하되 모든 사례에 같은 구조를 강요하지 않는다.','새 가상 프로젝트의 가족 ID를 지정하고 계열별 분할을 지킨다. 기존 10개 평가 입력을 복사하지 않는다.','deliverables·completion_criterion·hours와 roadmap_flow를 포함하되 제목·목표에 맞는 실제 내용을 작성한다.'],'status':'PREPARED_NOT_GENERATED'}})
                counter['roadmaps_pending_semantic_rewrite']+=1
            if task=='revise_roadmap':
                baseline=u.get('task_data',{}).get('current_roadmap')
                if not isinstance(baseline,dict):raise ValueError('Missing revision baseline')
                delta=differences(baseline,a)
                if not delta:raise ValueError('No revision change')
                a['change_summary']='; '.join(path+': '+json.dumps(old,ensure_ascii=False)+' → '+json.dumps(new,ensure_ascii=False) for path,old,new in delta)
                updated['messages'][-1]['content']=json.dumps(a,ensure_ascii=False)
                updated['messages'][0]['content']+='\nchange_summary에 원본 대비 실제 변경한 경로와 변경 전후 값만 요약한다. 요청 외 필드와 완료 기록을 보존한다.'
                changes.append('derived_change_summary');counter['revision_summary_repaired']+=1
            output.append(updated);drafts.append(updated)
            log.append({'id':p['id'],'parent_sha256':parent,'draft_sha256':fingerprint(updated),'split':split,'line':line,'changes':changes,'semantic_review_completed':False,'release_status':'DRAFT_NOT_FOR_TRAINING'})
        (dest/(split+'.draft.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in output),encoding='utf-8')
    for name,data in [('repair_log.jsonl',log),('rewrite_requests.jsonl',queue)]:
        (dest/name).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in data),encoding='utf-8')
    summary={'total':len(log),'counts':dict(counter),'automatic_changes_only':True,'status':'DRAFT_NOT_FOR_TRAINING','original_preserved':True,'no_external_api_called':True,'semantic_rewrite_required':len(queue),'diversity_axes':['duration and weekly capacity','project objective and concrete deliverable','starting competence','failure and uncertainty','reasoning and stage topology','relevant evidence availability'],'limitation':'Prepared diversity requests are not completed diverse answers.'}
    (dest/'repair_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
