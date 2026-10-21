"""Canonical DB migration, verification and metadata. No LLM or training imports."""
from pathlib import Path
import hashlib,json,re
from psycopg import sql
from psycopg.types.json import Jsonb

ROOT=Path(__file__).resolve().parents[2]
MIGRATION=ROOT/'src/database/migrations/007_final_schema.sql'
RENAMES={
 'public.course_skill_map':'public.course_skills','public.book_skill_map':'public.book_skills',
 'public.cert_skill_map':'public.certification_skills','public.job_skill_map':'public.job_skills',
 'public.major_skill_map':'public.major_skills','public.learning_resource_embedding':'public.learning_resource_embeddings',
 'hr_regulation_pilot.institution':'public.institutions',
 **{'hr_regulation_pilot.'+old:'regulations.'+new for old,new in {
 'regulation':'regulations','regulation_version':'regulation_versions','regulation_file':'regulation_files',
 'regulation_node':'regulation_nodes','regulation_scope':'regulation_scopes','regulation_reference':'regulation_references',
 'rag_chunk':'rag_chunks','rag_chunk_source':'rag_chunk_sources','rag_chunk_embedding':'rag_chunk_embeddings',
 'evaluation_result_schema':'evaluation_result_schemas','evaluation_item_definition':'evaluation_item_definitions',
 'evaluation_schema_source':'evaluation_schema_sources'}.items()},
 'growpath_legacy.user_skill_gap':'growpath_legacy.employee_skill_gaps',
}

def active(c):
 return bool(c.execute("SELECT to_regclass('public.employees') AS id").fetchone()['id'])

def snapshot(c):
 result={}
 tables=c.execute("SELECT n.nspname AS schema,t.relname AS name FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace WHERE t.relkind='r' AND n.nspname IN ('public','regulations','growpath_meta','growpath_legacy') ORDER BY 1,2").fetchall()
 for t in tables:
  key=t['schema']+'.'+t['name']
  cols=c.execute("SELECT a.attname AS column,format_type(a.atttypid,a.atttypmod) AS type,a.attnotnull AS not_null,pg_get_expr(d.adbin,d.adrelid) AS default,a.attidentity AS identity,a.attgenerated AS generated FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum WHERE a.attrelid=%s::regclass AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum",(key,)).fetchall()
  constraints=c.execute("SELECT co.conname AS name,co.contype AS type,pg_get_constraintdef(co.oid,true) AS definition,co.confrelid::regclass::text AS target,ARRAY(SELECT attname FROM unnest(co.conkey) WITH ORDINALITY k(num,ord) JOIN pg_attribute a ON a.attrelid=co.conrelid AND a.attnum=k.num ORDER BY ord) AS columns,ARRAY(SELECT attname FROM unnest(co.confkey) WITH ORDINALITY k(num,ord) JOIN pg_attribute a ON a.attrelid=co.confrelid AND a.attnum=k.num ORDER BY ord) AS target_columns FROM pg_constraint co WHERE co.conrelid=%s::regclass ORDER BY co.conname",(key,)).fetchall()
  for x in constraints:
   if x['type']=='f' and '.' not in x['target']:x['target']='public.'+x['target']
  pk=next((x['columns'] for x in constraints if x['type']=='p'),[])
  result[key]={'columns':cols,'pk':pk,'fks':[x for x in constraints if x['type']=='f'],'constraints':constraints}
 return result

def _compatibility_views(c):
 # Read aliases let older exporters consume the renamed real source tables.
 # Application writes are migrated to canonical tables; no duplicate source rows.
 c.execute('CREATE SCHEMA IF NOT EXISTS hr_regulation_pilot')
 c.execute('REVOKE ALL ON SCHEMA hr_regulation_pilot FROM PUBLIC')
 for old,new in RENAMES.items():
  a,b=old.split('.');x,y=new.split('.')
  c.execute(sql.SQL('CREATE OR REPLACE VIEW {}.{} AS SELECT * FROM {}.{}').format(*map(sql.Identifier,(a,b,x,y))))
 c.execute("CREATE OR REPLACE VIEW public.users AS SELECT employee_id AS user_id,name,job_id AS target_job_id,created_at,is_degree_seeker,email,department,job_title,grade,source_type,updated_at FROM public.employees")
 c.execute("CREATE OR REPLACE VIEW public.roadmap_sessions AS SELECT project_id AS session_id,employee_id AS user_id,project_name,status,current_stage,created_at,updated_at FROM public.projects")
 c.execute("CREATE OR REPLACE VIEW public.project_plans AS SELECT project_id AS plan_id,project_id AS session_id,draft_plan,refined_plan,project_goal,project_scope,tech_stack,milestones,key_issues,deliverables,validation_criteria,created_at,updated_at FROM public.projects")


def _backfill(c, steps=True):
 # Preserve employee IDs, names and unconfirmed profile values. Never guess a real affiliation.
 # Explicit demo profiles may be mapped to the sole real institution using their existing labels.
 inst=c.execute('SELECT institution_id FROM public.institutions ORDER BY institution_id').fetchall()
 if len(inst)==1:
  iid=inst[0]['institution_id']
  demo=c.execute("SELECT employee_id,department,grade FROM public.employees WHERE source_type IN ('TEST_MANUAL','TEST_AUTO') ORDER BY employee_id").fetchall()
  for row in demo:
   did=gid=None
   if row['department']:
    did=c.execute("INSERT INTO public.departments(institution_id,department_code,name) VALUES(%s,%s,%s) ON CONFLICT(institution_id,department_code) DO UPDATE SET name=EXCLUDED.name RETURNING department_id",(iid,'LEGACY-'+hashlib.sha256(row['department'].encode()).hexdigest()[:12],row['department'])).fetchone()['department_id']
   if row['grade']:
    gid=c.execute('INSERT INTO public.job_grades(institution_id,name) VALUES(%s,%s) ON CONFLICT(institution_id,name) DO UPDATE SET name=EXCLUDED.name RETURNING job_grade_id',(iid,row['grade'])).fetchone()['job_grade_id']
   c.execute('UPDATE public.employees SET institution_id=coalesce(institution_id,%s),employee_number=coalesce(employee_number,%s),department_id=coalesce(department_id,%s),job_grade_id=coalesce(job_grade_id,%s) WHERE employee_id=%s',(iid,str(row['employee_id']),did,gid,row['employee_id']))
 for row in (c.execute('SELECT roadmap_id,content FROM public.roadmaps ORDER BY created_at').fetchall() if steps else []):
  populate_steps(c,row['roadmap_id'],row['content'])


def populate_steps(c,roadmap_id,content):
 if not isinstance(content,dict) or not isinstance(content.get('milestones',[]),list):raise ValueError('Roadmap milestones must be a list')
 for i,step in enumerate(content.get('milestones',[]),1):
  sid=c.execute("INSERT INTO public.roadmap_steps(roadmap_id,step_order,title,activity,estimated_duration,details) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(roadmap_id,step_order) DO UPDATE SET title=EXCLUDED.title,activity=EXCLUDED.activity,estimated_duration=EXCLUDED.estimated_duration,details=EXCLUDED.details,is_completed=CASE WHEN (roadmap_steps.title,roadmap_steps.activity,roadmap_steps.estimated_duration) IS NOT DISTINCT FROM (EXCLUDED.title,EXCLUDED.activity,EXCLUDED.estimated_duration) THEN roadmap_steps.is_completed ELSE false END,completed_at=CASE WHEN (roadmap_steps.title,roadmap_steps.activity,roadmap_steps.estimated_duration) IS NOT DISTINCT FROM (EXCLUDED.title,EXCLUDED.activity,EXCLUDED.estimated_duration) THEN roadmap_steps.completed_at ELSE NULL END RETURNING step_id",(roadmap_id,i,step.get('phase_name') or str(step.get('phase',i)),json.dumps(step.get('key_actions',[]),ensure_ascii=False),step.get('duration'),Jsonb(step))).fetchone()['step_id']
  c.execute('DELETE FROM public.roadmap_step_resources WHERE step_id=%s',(sid,))
  for field,col,table,pk in [('recommended_courses','course_id','courses','course_id'),('recommended_books','isbn','books','isbn'),('recommended_certifications','certification_id','certifications','cert_id')]:
   for r in step.get(field,[]):
    if not isinstance(r,dict):raise ValueError('Saved recommendation must contain an actual source ID')
    rid=r.get(pk,r.get('id'))
    if rid is None:raise ValueError('Missing saved source ID: '+field)
    exists=c.execute(sql.SQL('SELECT 1 FROM public.{} WHERE {}=%s').format(sql.Identifier(table),sql.Identifier(pk)),(rid,)).fetchone()
    if not exists:raise ValueError('Saved roadmap source not found: '+field)
    c.execute(sql.SQL('INSERT INTO public.roadmap_step_resources(step_id,{}) VALUES(%s,%s) ON CONFLICT DO NOTHING').format(sql.Identifier(col)),(sid,rid))

 c.execute('DELETE FROM public.roadmap_steps WHERE roadmap_id=%s AND step_order>%s',(roadmap_id,len(content.get('milestones',[]))))


def _followup_migrations(c):
 done=[]
 for path in sorted(MIGRATION.parent.glob('*.sql')):
  if path.name <= MIGRATION.name:continue
  sha=hashlib.sha256(path.read_bytes()).hexdigest()
  old=c.execute('SELECT sha256 FROM growpath_meta.schema_migrations WHERE version=%s',(path.name,)).fetchone()
  if old:
   if old['sha256']!=sha:raise ValueError('Applied migration checksum mismatch: '+path.name)
   continue
  c.execute(path.read_text(encoding='utf-8'),prepare=False)
  c.execute('INSERT INTO growpath_meta.schema_migrations(version,sha256) VALUES(%s,%s)',(path.name,sha))
  done.append(path.name)
 return done


def migrate(c):
 c.execute('SELECT pg_advisory_xact_lock(763250130)')
 sha=hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
 if active(c):
  row=c.execute('SELECT sha256 FROM growpath_meta.schema_migrations WHERE version=%s',(MIGRATION.name,)).fetchone()
  if row is None or row['sha256']!=sha:raise ValueError('Applied final migration checksum mismatch')
  return {'applied':_followup_migrations(c),'verification':verify(c)}
 c.execute(MIGRATION.read_text(encoding='utf-8'),prepare=False)
 _backfill(c)
 _compatibility_views(c)
 # Index every referencing FK; parent unique/PK indexes already exist.
 for table,spec in snapshot(c).items():
  schema,name=table.split('.')
  for fk in spec['fks']:
   idx='ix_fk_'+hashlib.sha256((table+','.join(fk['columns'])).encode()).hexdigest()[:16]
   c.execute(sql.SQL('CREATE INDEX IF NOT EXISTS {} ON {}.{} ({})').format(sql.Identifier(idx),sql.Identifier(schema),sql.Identifier(name),sql.SQL(',').join(map(sql.Identifier,fk['columns']))))
  c.execute(sql.SQL('ALTER TABLE {}.{} ENABLE ROW LEVEL SECURITY').format(sql.Identifier(schema),sql.Identifier(name)))
  c.execute(sql.SQL('REVOKE ALL ON {}.{} FROM PUBLIC').format(sql.Identifier(schema),sql.Identifier(name)))
 c.execute('INSERT INTO growpath_meta.schema_migrations(version,sha256) VALUES(%s,%s)',(MIGRATION.name,sha))
 return {'applied':[MIGRATION.name]+_followup_migrations(c),'verification':verify(c)}


def verify(c):
 meta=snapshot(c)
 expected=json.loads(Path(__file__).with_name('catalog.current.json').read_text(encoding='utf-8'))
 for table,spec in expected.items():
  if table not in meta:raise ValueError('Required table is missing: '+table)
  actual=meta[table];columns={x['column']:x for x in actual['columns']}
  for col in spec['columns']:
   got=columns.get(col['column'])
   if got is None or got['type']!=col['type'] or got['not_null']!=col['not_null']:raise ValueError('Column definition mismatch: '+table+'.'+col['column'])
  if actual['pk']!=spec['pk']:raise ValueError('Primary key mismatch: '+table)
  signature=lambda f:(tuple(f['columns']),f['target'],tuple(f['target_columns']))
  if not {signature(f) for f in spec['fks']}.issubset({signature(f) for f in actual['fks']}):raise ValueError('Foreign key mismatch: '+table)
 invalid=c.execute("SELECT conname FROM pg_constraint WHERE NOT convalidated AND connamespace IN (SELECT oid FROM pg_namespace WHERE nspname IN ('public','regulations','growpath_meta','growpath_legacy'))").fetchall()
 if invalid:raise ValueError('Unvalidated DB constraints remain')
 counts=[]
 for table in meta:
  schema,name=table.split('.')
  n=c.execute(sql.SQL('SELECT COUNT(*) AS n FROM {}.{}').format(sql.Identifier(schema),sql.Identifier(name))).fetchone()['n']
  counts.append({'table':table,'count':n})
 vectors=c.execute('SELECT resource_type,count(*) AS n FROM public.learning_resource_embeddings GROUP BY resource_type ORDER BY resource_type').fetchall()
 return {'schema_and_foreign_keys':'pass','tables':counts,'foreign_keys':sum(len(x['fks']) for x in meta.values()),'resource_vectors':vectors,'unconfirmed_employee_profiles':c.execute('SELECT count(*) AS n FROM public.employees WHERE institution_id IS NULL OR department_id IS NULL OR job_grade_id IS NULL OR job_id IS NULL').fetchone()['n']}
