"""Read-only Cloud catalog retrieval from the verified latest-local Supabase copy."""
import hashlib,json,math
from datetime import date,datetime,timezone
from decimal import Decimal
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
import app_settings

MODEL='text-embedding-3-small'
def serial(value):
 if isinstance(value,(date,datetime,Decimal)):return str(value)
 raise TypeError(type(value).__name__)
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,default=serial)
def connection(root):
 url=app_settings.get(root,'GROWPATH_DB_URL')
 if not url:raise ValueError('Cloud Secrets에 GROWPATH_DB_URL을 설정하세요. 실험 기록 DATABASE_URL과 다릅니다.')
 try:return psycopg.connect(url,sslmode='require',connect_timeout=15,row_factory=dict_row,prepare_threshold=None)
 except psycopg.Error:raise RuntimeError('근거 DB 연결 실패. Cloud Secrets의 pooler 주소·계정·네트워크를 확인하세요.') from None

def status(root):
 with connection(root) as c:
  c.execute('BEGIN READ ONLY');c.execute("SET LOCAL statement_timeout='20s'")
  receipt=c.execute('SELECT receipt_sha256,created_at FROM growpath_source.sync_receipts ORDER BY created_at DESC LIMIT 1').fetchone()
  counts={t:c.execute('SELECT count(*) AS n FROM '+t).fetchone()['n'] for t in ['growpath_live.skill_tags','growpath_live.courses','growpath_live.books','growpath_live.certifications','growpath_live.learning_resource_embeddings','growpath_regulations.rag_chunk_embeddings']}
  return {'receipt':receipt,'counts':counts,'read_only':True}

def skill_ids(c,request):
 user=request.get('user_context') or {};ids=user.get('target_skill_ids') or []
 if ids:
  if not isinstance(ids,list) or any(type(x)is not int or x<=0 for x in ids):raise ValueError('Invalid target_skill_ids')
  found=c.execute('SELECT skill_id FROM growpath_live.skill_tags WHERE skill_id=ANY(%s)',(ids,)).fetchall()
  if {x['skill_id'] for x in found}!=set(ids):raise ValueError('Unknown target skill')
  return sorted(set(ids))
 labels=user.get('target_skills') or []
 return [x['skill_id'] for x in c.execute('SELECT skill_id FROM growpath_live.skill_tags WHERE name=ANY(%s) ORDER BY skill_id',(labels,)).fetchall()]

def retrieve(c,request,as_of):
 ids=skill_ids(c,request)
 if not ids:return {'courses':[],'books':[],'certifications':[],'regulation_rag':{'approved':[],'review_only':[],'as_of':as_of},'retrieval':{'method':'skill_links_and_stored_vector_centroid/v1','skill_ids':[],'reason':'no_exact_skill_mapping'}}
 vector=c.execute("SELECT avg(embedding)::text AS vec FROM growpath_live.learning_resource_embeddings WHERE resource_type='skills' AND skill_id=ANY(%s) AND embedding_model=%s AND dimensions=1536",(ids,MODEL)).fetchone()['vec']
 if vector is None:raise ValueError('Selected skills have no compatible stored vectors')
 context={'courses':[],'books':[],'certifications':[]}
 specs=[('courses','course_skills','course_id','course_id'),('books','book_skills','isbn','isbn'),('certifications','certification_skills','cert_id','cert_id')]
 for kind,links,pk,fk in specs:
  # Identifiers are fixed source-code constants. Values remain bound parameters.
  query=f'''SELECT r.*, (e.embedding <=> %s::extensions.vector) AS vector_distance
    FROM growpath_live.{kind} r JOIN growpath_live.learning_resource_embeddings e
    ON e.resource_type=%s AND e.resource_id=r.{pk}::text AND e.embedding_model=%s AND e.dimensions=1536
    WHERE r.content_status='ready' AND EXISTS(SELECT 1 FROM growpath_live.{links} m WHERE m.{fk}=r.{pk} AND m.skill_id=ANY(%s))
    ORDER BY e.embedding <=> %s::extensions.vector,r.{pk} LIMIT 2'''
  for row in c.execute(query,(vector,kind,MODEL,ids,vector)).fetchall():
   # Records are candidates; unknown cost/enrollment never become zero/available.
   row.pop('embedding',None);row['source_snapshot_as_of']=as_of
   if kind=='courses':
    start=row.get('enrollment_start');end=row.get('enrollment_end');day=date.fromisoformat(as_of)
    if row.get('enrollment_period_type')=='scheduled':
     if start and start.date()>day:continue
     if end and end.date()<day:continue
     row['availability_status']='available' if start and end else 'verification_required'
    else:row['availability_status']='available' if row.get('enrollment_period_type')=='unrestricted' else 'verification_required'
    row['cost_status']='known' if row.get('cost') is not None else 'verification_required'
   else:row['cost_status']='verification_required';row['availability_status']='verification_required'
   context[kind].append(row)
 regs=c.execute('''SELECT r.rag_chunk_id,r.regulation_version_id,r.chunk_text,r.context_path,r.search_status,
   v.effective_from,v.effective_to,v.review_status,v.availability_status,
   EXISTS(SELECT 1 FROM growpath_regulations.rag_chunk_sources s
     JOIN growpath_regulations.regulation_nodes n USING(regulation_node_id)
     WHERE s.rag_chunk_id=r.rag_chunk_id AND
       (n.extraction_status='needs_review' OR n.effective_from_override IS NOT NULL OR n.effective_to_override IS NOT NULL)) AS requires_review,
   (e.embedding <=> %s::extensions.vector) AS vector_distance
   FROM growpath_regulations.rag_chunks r
   JOIN growpath_regulations.regulation_versions v USING(regulation_version_id)
   JOIN growpath_regulations.rag_chunk_embeddings e USING(rag_chunk_id)
   WHERE r.search_status='active' AND e.embedding_model=%s AND e.dimensions=1536
     AND length(r.chunk_text)<=1600
     AND (r.chunk_text LIKE '%%교육%%' OR r.chunk_text LIKE '%%훈련%%')
   ORDER BY e.embedding <=> %s::extensions.vector,r.rag_chunk_id LIMIT 8''',(vector,MODEL,vector)).fetchall()
 approved=[];review=[];day=date.fromisoformat(as_of)
 for row in regs:
  valid=(row['review_status']=='approved' and row['availability_status']=='available' and not row['requires_review'] and row['effective_from'] is not None and row['effective_from']<=day and (row['effective_to'] is None or day<row['effective_to']))
  (approved if valid else review).append(row)
 context['books']=context['books'][:1];context['certifications']=context['certifications'][:1]
 context['regulation_rag']={'approved':approved[:1],'review_only':review[:1],'as_of':as_of,'status':'available' if approved else 'verification_required'}
 context['retrieval']={'method':'skill_links_and_stored_vector_centroid/v1','skill_ids':ids,'embedding_model':MODEL,'dimensions':1536,'note':'스킬 관계로 후보를 제한하고 저장된 스킬벡터 평균으로 순위를 정함. 자유문장 임베딩 검색은 아님.'}
 return json.loads(canonical(context))

def fetch_ten(root,rows,as_of=None,employee_ids=None):
 if len(rows)!=10:raise ValueError('Exactly ten evaluation requests required')
 as_of=as_of or datetime.now(timezone.utc).date().isoformat();result=[]
 if employee_ids is not None:
  from cloud_employee_context import validate_assignment,profile,apply_profile
  employee_ids=validate_assignment(employee_ids)
 with connection(root) as c:
  c.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');c.execute('SET LOCAL search_path TO extensions,public');c.execute("SET LOCAL statement_timeout='30s'")
  receipt=c.execute('SELECT receipt_sha256 FROM growpath_source.sync_receipts ORDER BY created_at DESC LIMIT 1').fetchone()
  if not receipt:raise ValueError('No verified latest-local sync receipt')
  profiles={}
  for index,row in enumerate(rows):
   copied=json.loads(json.dumps(row));messages=copied['messages']
   # Reference targets from older evidence must not become answers for changed evidence.
   if messages[-1]['role']=='assistant':messages.pop()
   request=json.loads(messages[-1]['content'])
   if employee_ids is not None:
    employee_id=employee_ids[index]
    if employee_id not in profiles:profiles[employee_id]=profile(c,employee_id)
    request=apply_profile(request,profiles[employee_id])
   request['retrieved_context']=retrieve(c,request,as_of)
   request['retrieved_context']['retrieval']['source_receipt_sha256']=receipt['receipt_sha256']
   messages[-1]['content']=canonical(request);result.append(copied)
 return result
