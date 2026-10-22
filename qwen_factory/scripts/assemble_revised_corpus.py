"""Assemble reviewed revisions without overwriting the frozen original release."""
import collections,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 src=ROOT/'data/revision_1500';dest=src/'assembled';dest.mkdir(exist_ok=True)
 records=[json.loads(x) for x in (src/'repair_log.jsonl').read_text(encoding='utf-8').splitlines()]
 by={(r['split'],r['line']):r for r in records};allrows=[];provenance=[];counts=collections.Counter();periods=collections.Counter();stages=collections.Counter();flags=[]
 for split in ['train','validation','test']:
  rows=[]
  for i,line in enumerate((src/(split+'.draft.jsonl')).read_text(encoding='utf-8').splitlines(),1):
   original=json.loads(line);info=by[(split,i)];u=json.loads(original['messages'][-2]['content']);task=u['task'];row=original
   if task=='generate_roadmap':
    review=json.loads((src/'reviewed_candidates'/(info['id']+'.json')).read_text(encoding='utf-8'))
    assert review['status']=='STRUCTURAL_REVIEW_CANDIDATE' and not review['errors']
    row=review['candidate'];answer=json.loads(row['messages'][-1]['content']);periods[str(answer.get('total_duration_weeks'))]+=1;stages[len(answer.get('milestones',[]))]+=1
   assert row['messages'][-1]['role']=='assistant';a=json.loads(row['messages'][-1]['content'])
   # Every record is parsed and traced. These checks are not a substitute for semantic acceptance.
   assert isinstance(a,(dict,list));counts[task]+=1;rows.append(row)
   provenance.append({'id':info['id'],'task':task,'source_split':split,'parent_sha256':info['parent_sha256'],'row_sha256':sha(json.dumps(row,ensure_ascii=False,sort_keys=True).encode()),'semantic_acceptance':'NOT_YET_CONFIRMED'})
  raw=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows).encode();(dest/(split+'.jsonl')).write_bytes(raw);allrows+=rows
 assert len(allrows)==1500 and len({p['id'] for p in provenance})==1500 and len(counts)==7
 (dest/'all.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in allrows),encoding='utf-8')
 (dest/'provenance.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in provenance),encoding='utf-8')
 report={'total':1500,'task_counts':dict(counts),'generated_duration_distribution':dict(periods),'generated_stage_distribution':dict(stages),'training_release_ready':False,'semantic_review_completed':False,'token_measurement_completed':False,'source_preserved':True,'all_1500_training_makes_old_splits_nonindependent':True,'files':{f.name:sha(f.read_bytes()) for f in dest.glob('*.jsonl')}}
 (dest/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
