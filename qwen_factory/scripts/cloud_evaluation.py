"""Freeze live-DB evidence once after training; reuse identical inputs across weights."""
import copy,hashlib,json,re
from contextlib import closing
from pathlib import Path
import yaml
import dashboard_store
from cloud_evidence import fetch_ten,canonical


def validate_batch(value):
 if not isinstance(value,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',value):raise ValueError('평가 묶음 ID는 영문·숫자·하이픈·밑줄 1~64자로 입력하세요.')
 return value

def freeze(root,cfg):
 policy=cfg.get('live_evaluation') or {}
 if not policy.get('enabled'):return cfg,None
 root=Path(root).resolve();batch=validate_batch(policy.get('cohort_id'))
 source=(root/cfg['evaluation']['file']).resolve();source.relative_to(root/'data/eval');raw=source.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=cfg['evaluation']['sha256']:raise ValueError('평가 요청 원본이 등록 후 변경됐습니다.')
 rows=[json.loads(x) for x in raw.decode('utf-8-sig').splitlines() if x.strip()]
 if len(rows)!=10:raise ValueError('평가 요청 원본은 정확히10개여야 합니다.')
 template_hash=hashlib.sha256(raw).hexdigest();key='reports/live_cohorts/'+batch+'.json'
 employee_ids=policy.get('case_employee_ids')
 if employee_ids is not None:
  from cloud_employee_context import validate_assignment
  employee_ids=validate_assignment(employee_ids)
 lock=int(hashlib.sha256(('cohort:'+batch).encode()).hexdigest()[:15],16)
 with closing(dashboard_store.pg(root)) as db:
  db.execute('SELECT pg_advisory_xact_lock(%s)',(lock,))
  saved=db.execute('SELECT content FROM documents WHERE path=%s',(key,)).fetchone()
  if saved:
   receipt=json.loads(saved[0])
   if receipt['template_sha256']!=template_hash:raise ValueError('같은 평가 묶음에 다른 요청이 등록됐습니다. 새 묶음 ID를 사용하세요.')
   if receipt.get('case_employee_ids')!=employee_ids:raise ValueError('같은 평가 묶음의 직원 배정은 바꿀 수 없습니다. 새 묶음 ID를 사용하세요.')
   frozen=receipt['rows'];body=''.join(canonical(x)+'\n' for x in frozen)
   if hashlib.sha256(body.encode()).hexdigest()!=receipt['sha256']:raise ValueError('저장된 실전 평가 묶음의 해시가 일치하지 않습니다.')
  else:
   frozen=fetch_ten(root,rows,employee_ids=employee_ids) if employee_ids is not None else fetch_ten(root,rows)
   body=''.join(canonical(x)+'\n' for x in frozen);digest=hashlib.sha256(body.encode()).hexdigest()
   receipt={'version':'growpath-live-evidence/v2','cohort_id':batch,'template_sha256':template_hash,'sha256':digest,'case_employee_ids':employee_ids,'rows':frozen}
   db.execute('INSERT INTO documents(path,content) VALUES (%s,%s)',(key,canonical(receipt)))
  db.commit()
 relative='data/eval/live_'+receipt['sha256']+'.jsonl';path=root/relative;path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists() and path.read_bytes()!=body.encode():raise ValueError('기존 실전 평가 파일을 덮어쓰지 않습니다.')
 path.write_bytes(body.encode());manifest_path=path.with_suffix('.manifest.json')
 manifest_path.write_text(canonical({k:v for k,v in receipt.items() if k!='rows'}),encoding='utf-8')
 result=copy.deepcopy(cfg);result['data']['test_file']=relative;result['evaluation']={'mode':'shared_fixed_10','file':relative,'expected_count':10,'sha256':receipt['sha256']}
 return result,{'cohort_id':batch,'file':relative,'sha256':receipt['sha256']}
