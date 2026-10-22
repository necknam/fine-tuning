"""Canonical persistence behind the existing local app API; no UI or LLM calls."""
import json
from uuid import uuid4
from datetime import date,datetime,timezone
from psycopg.types.json import Jsonb
from src.shared.assessment_schema import validate_questions,validate_responses

def extend(Base):
 class Store(Base):
    def get_employee_recommended_prompts(self,employee_id):
        with self.transaction() as c:
            return c.execute('SELECT prompt_id,employee_id,prompt_text,display_order,updated_at FROM public.employee_recommended_prompts WHERE employee_id=%s ORDER BY display_order NULLS LAST,prompt_id',(employee_id,)).fetchall()

    def save_employee_recommended_prompts(self,employee_id,prompts):
        if employee_id is None:
            raise ValueError('Employee ID is required when saving employee recommendations')
        if prompts is None:
            prompts=[]
        if not isinstance(prompts,list) or len(prompts)>3:
            raise ValueError('Provide up to three suggested questions')
        if any(p is not None and (not isinstance(p,str) or not p.strip() or '\n' in p or '\r' in p) for p in prompts):
            raise ValueError('Each suggested question must be a nonempty single line or None')
        with self.transaction() as c:
            if not c.execute('SELECT employee_id FROM public.employees WHERE employee_id=%s FOR UPDATE',(employee_id,)).fetchone():
                raise ValueError('Employee not found')
            c.execute('DELETE FROM public.employee_recommended_prompts WHERE employee_id=%s',(employee_id,))
            for order,prompt in enumerate(prompts,1):
                c.execute('INSERT INTO public.employee_recommended_prompts(employee_id,prompt_text,display_order) VALUES(%s,%s,%s)',(employee_id,prompt.strip() if prompt is not None else None,order))
        return True

    def _round(self,c,project_id):
        r=c.execute('SELECT * FROM public.diagnostic_rounds WHERE project_id=%s ORDER BY round_number DESC LIMIT 1',(project_id,)).fetchone()
        if r:return r
        return c.execute("INSERT INTO public.diagnostic_rounds(project_id,round_number,project_snapshot) SELECT project_id,1,jsonb_build_object('extracted_text',extracted_text,'refined_plan',refined_plan,'project_goal',project_goal,'project_scope',project_scope) FROM public.projects WHERE project_id=%s RETURNING *",(project_id,)).fetchone()

    def save_project_plan(self,session_id,plan_data,**kwargs):
        from psycopg import sql
        keys=('draft_plan','refined_plan','draft_prompt_version_id','plan_prompt_version_id','project_goal','project_scope','tech_stack','milestones','key_issues','deliverables','validation_criteria')
        payload={k:v for k,v in plan_data.items() if k in keys}
        if not payload:raise ValueError('No supported project plan fields')
        with self.transaction() as c:
            self._session_lock(c,session_id)
            if 'draft_plan' in payload:payload['extracted_text']=payload['draft_plan']
            if payload.get('refined_plan'):payload.update(draft_plan=None,draft_conversations=[])
            terms=sql.SQL(',').join(sql.SQL('{}=%s').format(sql.Identifier(k)) for k in payload)
            values=[Jsonb(v) if isinstance(v,(dict,list)) else v for v in payload.values()]
            c.execute(sql.SQL('UPDATE public.projects SET {},updated_at=now() WHERE project_id=%s').format(terms),(*values,session_id))
        return True

    def save_plan_conversation(self,session_id,role,content,sequence_no):
        if role not in ('user','assistant','system'):raise ValueError('Invalid role')
        with self.transaction() as c:
            self._session_lock(c,session_id)
            c.execute("UPDATE public.projects SET draft_conversations=draft_conversations||%s::jsonb WHERE project_id=%s AND nullif(refined_plan,'') IS NULL",(Jsonb([{'session_id':str(session_id),'role':role,'content':content,'sequence_no':sequence_no}]),session_id))
        return True

    def get_plan_conversations(self,session_id):
        with self.transaction() as c:
            r=c.execute('SELECT draft_conversations FROM public.projects WHERE project_id=%s',(session_id,)).fetchone()
            return r['draft_conversations'] if r else []

    def _employee_profiles(self,c,employee_id=None,test_only=False):
        return c.execute("""SELECT e.employee_id,e.employee_id AS user_id,e.name,e.email,e.source_type,
            e.institution_id,e.employee_number,e.department_id,e.job_grade_id,e.job_id,e.is_department_head,
            e.hire_date,e.department_start_date,
            coalesce(d.name,e.department,'') AS department,
            coalesce(g.name,e.grade,'') AS grade,coalesce(j.title,e.job_title,'') AS job_title
            FROM public.employees e LEFT JOIN public.departments d USING(department_id)
            LEFT JOIN public.job_grades g USING(job_grade_id) LEFT JOIN public.jobs j USING(job_id)
            WHERE (%s::integer IS NULL OR e.employee_id=%s)
            AND (NOT %s OR e.source_type IN ('TEST_MANUAL','TEST_AUTO')) ORDER BY e.employee_id""",(employee_id,employee_id,test_only)).fetchall()

    def list_test_users(self):
        with self.transaction() as c:return self._employee_profiles(c,test_only=True)

    def get_employee_profile(self,employee_id):
        from .db_client import user_id_value
        with self.transaction() as c:
            rows=self._employee_profiles(c,user_id_value(employee_id))
            return rows[0] if rows else None

    def update_employee_dates(self,employee_id,*,hire_date,department_start_date):
        """Set both dates explicitly; None clears an unknown date. Accept date or ISO YYYY-MM-DD."""
        from .db_client import user_id_value
        def parse(value):
            if value is None:return None
            if type(value) is date:return value
            if isinstance(value,str):
                try:
                    parsed=date.fromisoformat(value)
                    if parsed.isoformat()==value:return parsed
                except ValueError:pass
            raise ValueError('Employee dates must be YYYY-MM-DD, date, or None')
        hire_date=parse(hire_date);department_start_date=parse(department_start_date)
        if hire_date and department_start_date and department_start_date<hire_date:
            raise ValueError('Department start date cannot precede hire date')
        with self.transaction() as c:
            row=c.execute("UPDATE public.employees SET hire_date=%s,department_start_date=%s,updated_at=now() WHERE employee_id=%s RETURNING employee_id",(hire_date,department_start_date,user_id_value(employee_id))).fetchone()
            if row is None:raise ValueError('Employee does not exist')
        return True

    def update_employee_assignment(self,employee_id,*,institution_id,employee_number,department_id,job_grade_id,job_id):
        from .db_client import user_id_value
        actor=user_id_value(employee_id)
        if not isinstance(employee_number,str) or not employee_number.strip():raise ValueError('Employee number is required')
        if not institution_id or any(type(v) is not int or v<=0 for v in (department_id,job_grade_id,job_id)):raise ValueError('Confirmed institution, department, grade and job IDs are required')
        with self.transaction() as c:
            row=c.execute("""UPDATE public.employees SET institution_id=%s,employee_number=%s,
                department_id=%s,job_grade_id=%s,job_id=%s,department=NULL,grade=NULL,job_title=NULL,updated_at=now()
                WHERE employee_id=%s RETURNING employee_id""",(institution_id,employee_number.strip(),department_id,job_grade_id,job_id,actor)).fetchone()
            if row is None:raise ValueError('Employee does not exist')
        return True

    def get_or_create_user(self,username,email,department='',job_title='',grade='',source_type='TEST_MANUAL'):
        if not username.strip() or not email.strip() or source_type not in ('TEST_MANUAL','TEST_AUTO','REAL_USER'):raise ValueError('Invalid employee data')
        with self.transaction() as c:
            c.execute('INSERT INTO public.employees(name,email,department,job_title,grade,source_type) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(email) DO NOTHING',(username.strip(),email.strip(),department,job_title,grade,source_type))
            return c.execute('SELECT employee_id FROM public.employees WHERE email=%s',(email.strip(),)).fetchone()['employee_id']

    def save_assessment_questions(self,session_id,assessment_type,questions):
        self._assessment_type(assessment_type);validate_questions(questions,require_ids=False)
        with self.transaction() as c:
            s=self._session_lock(c,session_id);r=self._round(c,session_id)
            if s['current_stage'] not in ((2,3) if assessment_type=='PRE' else (5,6)):raise ValueError('Questions cannot be changed at this stage')
            if c.execute('SELECT 1 FROM public.assessment_responses a JOIN public.assessment_questions q USING(question_id) WHERE q.diagnostic_round_id=%s AND q.assessment_type=%s LIMIT 1',(r['diagnostic_round_id'],assessment_type)).fetchone():raise ValueError('Answered questions cannot be replaced')
            if assessment_type=='POST':
                before=self._questions(c,session_id,'PRE')
                signature=lambda q:(q.get('skill_id'),q.get('skill',q.get('skill_name','')),q['question'],q.get('options',[]))
                if [signature(q) for q in before]!=[signature(q) for q in questions]:raise ValueError('POST must reuse the same PRE questions and scale')
            names={x['skill_id']:x['name'] for x in c.execute('SELECT skill_id,name FROM public.skill_tags').fetchall()}
            if any(names.get(q['skill_id'])!=q.get('skill',q.get('skill_name','')) for q in questions):raise ValueError('Skill ID/name mismatch')
            c.execute('DELETE FROM public.assessment_questions WHERE diagnostic_round_id=%s AND assessment_type=%s',(r['diagnostic_round_id'],assessment_type))
            for i,q in enumerate(questions,1):
                c.execute('INSERT INTO public.assessment_questions(project_id,diagnostic_round_id,assessment_type,skill_id,skill,question,options,sequence_no) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',(session_id,r['diagnostic_round_id'],assessment_type,q['skill_id'],q.get('skill',q.get('skill_name','')),q['question'],Jsonb(q.get('options',[])),i))
        return True

    def _questions(self,c,project_id,kind):
        r=self._round(c,project_id)
        return c.execute('SELECT * FROM public.assessment_questions WHERE diagnostic_round_id=%s AND assessment_type=%s ORDER BY sequence_no',(r['diagnostic_round_id'],kind)).fetchall()

    def get_assessment_questions(self,session_id,assessment_type):
        self._assessment_type(assessment_type)
        with self.transaction() as c:return self._questions(c,session_id,assessment_type)

    def save_assessment_responses(self,session_id,assessment_type,responses):
        self._assessment_type(assessment_type)
        with self.transaction() as c:
            s=self._session_lock(c,session_id);r=self._round(c,session_id)
            if s['current_stage']!=(3 if assessment_type=='PRE' else 6):raise ValueError('Responses cannot change after use')
            if assessment_type=='POST' and r['post_completed_at'] is not None:raise ValueError('POST assessment is allowed once')
            questions=self._questions(c,session_id,assessment_type);validate_responses(questions,responses)
            ids=[q['question_id'] for q in questions]
            c.execute('DELETE FROM public.assessment_responses WHERE question_id=ANY(%s)',(ids,))
            for a in responses:
                c.execute('INSERT INTO public.assessment_responses(project_id,assessment_type,question_id,selected_option,score) VALUES(%s,%s,%s,%s,%s)',(session_id,assessment_type,a['question_id'],str(a.get('selected_option','')),a['score']))
            col='pre_completed_at' if assessment_type=='PRE' else 'post_completed_at'
            c.execute('UPDATE public.diagnostic_rounds SET '+col+'=now() WHERE diagnostic_round_id=%s',(r['diagnostic_round_id'],))
        return True

    def get_assessment_responses(self,session_id,assessment_type):
        self._assessment_type(assessment_type)
        with self.transaction() as c:
            r=self._round(c,session_id)
            return c.execute('SELECT a.* FROM public.assessment_responses a JOIN public.assessment_questions q USING(question_id) WHERE q.diagnostic_round_id=%s AND q.assessment_type=%s ORDER BY q.sequence_no',(r['diagnostic_round_id'],assessment_type)).fetchall()

    def save_roadmap_generations(self,session_id,generations):
        if not generations or any(g.get('status')=='FAILED' or not isinstance(g.get('roadmap_content'),dict) or g['roadmap_content'].get('error') for g in generations):raise ValueError('Only successful generations are accepted')
        choices=[dict(g,generation_id=str(uuid4()),session_id=str(session_id),generation_order=i) for i,g in enumerate(generations,1)]
        with self.transaction() as c:
            self._session_lock(c,session_id)
            if c.execute('SELECT 1 FROM public.roadmaps WHERE project_id=%s',(session_id,)).fetchone():raise ValueError('Already selected roadmap cannot be replaced by alternatives')
            c.execute('UPDATE public.projects SET draft_choices=%s WHERE project_id=%s',(Jsonb(choices),session_id))
        return True

    def get_roadmap_generations(self,session_id):
        with self.transaction() as c:
            rows=c.execute('SELECT roadmap_id AS generation_id,project_id AS session_id,strategy_type,strategy_title,summary,content AS roadmap_content,prompt_version_id,1 AS generation_order FROM public.roadmaps WHERE project_id=%s',(session_id,)).fetchall()
            if rows:return rows
            r=c.execute('SELECT draft_choices FROM public.projects WHERE project_id=%s',(session_id,)).fetchone()
            return r['draft_choices'] if r else []

    def select_roadmap_with_report(self,session_id,generation_id,report_content):
        from .final_schema import populate_steps
        with self.transaction() as c:
            self._session_lock(c,session_id);r=self._round(c,session_id)
            current=c.execute('SELECT roadmap_id FROM public.roadmaps WHERE diagnostic_round_id=%s',(r['diagnostic_round_id'],)).fetchone()
            if current:
                if str(current['roadmap_id'])==str(generation_id):return True
                raise ValueError('A roadmap is already selected for this diagnostic round')
            items=c.execute('SELECT draft_choices FROM public.projects WHERE project_id=%s',(session_id,)).fetchone()['draft_choices']
            selected=next((g for g in items if str(g['generation_id'])==str(generation_id)),None)
            if selected is None:raise ValueError('Selected roadmap does not belong to this project')
            content=selected['roadmap_content']
            c.execute('INSERT INTO public.roadmaps(roadmap_id,project_id,diagnostic_round_id,strategy_type,strategy_title,summary,content,baseline_content,report_content,prompt_version_id,selected_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())',(generation_id,session_id,r['diagnostic_round_id'],selected['strategy_type'],selected.get('strategy_title'),selected.get('summary'),Jsonb(content),Jsonb(content),Jsonb(report_content),selected.get('prompt_version_id')))
            c.execute('UPDATE public.diagnostic_rounds SET agent_input=%s WHERE diagnostic_round_id=%s',(Jsonb(content.get('assessment_input',{})),r['diagnostic_round_id']))
            populate_steps(c,generation_id,content)
            c.execute("UPDATE public.projects SET draft_choices='[]' WHERE project_id=%s",(session_id,))
        return True

    def save_roadmap_selection(self,session_id,generation_id):
        return self.select_roadmap_with_report(session_id,generation_id,{})

    def save_roadmap_report(self,session_id,generation_id,report_content):
        with self.transaction() as c:
            self._session_lock(c,session_id)
            row=c.execute('UPDATE public.roadmaps SET report_content=%s WHERE project_id=%s AND roadmap_id=%s RETURNING roadmap_id',(Jsonb(report_content),session_id,generation_id)).fetchone()
            if row is None:raise ValueError('Report requires the selected roadmap of this project')
        return True

    def get_selection_statistics(self,user_type='REAL_USER'):
        with self.transaction() as c:
            rows=c.execute('SELECT m.strategy_type,count(*) AS n FROM public.roadmaps m JOIN public.projects p USING(project_id) JOIN public.employees e USING(employee_id) WHERE (%s::text IS NULL OR e.source_type=%s) GROUP BY m.strategy_type',(user_type,user_type)).fetchall()
        counts={r['strategy_type']:r['n'] for r in rows};total=sum(counts.values())
        return {'total_selections':total,'counts':counts,'rates':{k:v/total for k,v in counts.items()}}

    def get_roadmap_selection(self,session_id):
        with self.transaction() as c:return c.execute('SELECT roadmap_id AS generation_id,project_id AS session_id,selected_at FROM public.roadmaps WHERE project_id=%s ORDER BY selected_at DESC LIMIT 1',(session_id,)).fetchone()

    def get_roadmap_report(self,session_id):
        with self.transaction() as c:return c.execute('SELECT roadmap_id AS report_id,roadmap_id AS generation_id,project_id AS session_id,report_content FROM public.roadmaps WHERE project_id=%s ORDER BY selected_at DESC LIMIT 1',(session_id,)).fetchone()

    def save_assessment_report(self,session_id,report_content,report_type='PRE_POST'):
        with self.transaction() as c:
            self._session_lock(c,session_id);r=self._round(c,session_id)
            if r['post_completed_at'] is None:raise ValueError('POST assessment must be completed first')
            roadmap=c.execute('SELECT roadmap_id FROM public.roadmaps WHERE diagnostic_round_id=%s',(r['diagnostic_round_id'],)).fetchone()
            if roadmap is None:raise ValueError('No selected roadmap')
            old=c.execute('SELECT report_content FROM public.growth_reports WHERE roadmap_id=%s',(roadmap['roadmap_id'],)).fetchone()
            if old:
                if old['report_content']==report_content:return True
                raise ValueError('Growth report is read-only')
            c.execute('INSERT INTO public.growth_reports(project_id,roadmap_id,report_type,report_content) VALUES(%s,%s,%s,%s)',(session_id,roadmap['roadmap_id'],report_type,Jsonb(report_content)))
        return True

    def get_assessment_report(self,session_id):
        with self.transaction() as c:return c.execute('SELECT * FROM public.growth_reports WHERE project_id=%s',(session_id,)).fetchone()

    def _project_access(self,c,project_id,employee_id,write=False):
        from .db_client import user_id_value
        actor=user_id_value(employee_id)
        row=c.execute('SELECT employee_id FROM public.projects WHERE project_id=%s'+(' FOR UPDATE' if write else ''),(project_id,)).fetchone()
        if row is None:raise ValueError('Project does not exist')
        if write:
            allowed=row['employee_id']==actor
        else:
            allowed=c.execute('SELECT public.employee_can_read_project(%s,%s) AS allowed',(actor,project_id)).fetchone()['allowed']
        if not allowed:raise ValueError('Employee does not have access to this project')
        return actor

    def set_employee_skills(self,employee_id,skill_ids):
        return self._set_possessions(employee_id,skill_ids,'employee_skills','skill_id')

    def set_employee_certifications(self,employee_id,certification_ids):
        return self._set_possessions(employee_id,certification_ids,'employee_certifications','certification_id')

    def _set_possessions(self,employee_id,ids,table,column):
        from .db_client import user_id_value
        actor=user_id_value(employee_id)
        if any(type(i) is not int or i<=0 for i in ids):raise ValueError('Possession IDs must be positive integers')
        with self.transaction() as c:
            if not c.execute('SELECT 1 FROM public.employees WHERE employee_id=%s FOR UPDATE',(actor,)).fetchone():raise ValueError('Employee does not exist')
            c.execute('DELETE FROM public.'+table+' WHERE employee_id=%s',(actor,))
            for i in sorted(set(ids)):
                c.execute('INSERT INTO public.'+table+'(employee_id,'+column+') VALUES(%s,%s)',(actor,i))
        return True

    def update_roadmap_content(self,employee_id,roadmap_id,content):
        from .final_schema import populate_steps
        if not isinstance(content,dict) or not isinstance(content.get('milestones'),list):raise ValueError('A roadmap requires milestones')
        with self.transaction() as c:
            row=c.execute('SELECT project_id FROM public.roadmaps WHERE roadmap_id=%s FOR UPDATE',(roadmap_id,)).fetchone()
            if row is None:raise ValueError('Roadmap does not exist')
            self._project_access(c,row['project_id'],employee_id,write=True)
            c.execute('UPDATE public.roadmaps SET content=%s,updated_at=now() WHERE roadmap_id=%s',(Jsonb(content),roadmap_id))
            populate_steps(c,roadmap_id,content)
        return True

    def set_step_completed(self,employee_id,step_id,completed):
        if type(completed) is not bool:raise ValueError('Completion must be boolean')
        with self.transaction() as c:
            row=c.execute('SELECT m.project_id FROM public.roadmap_steps s JOIN public.roadmaps m USING(roadmap_id) WHERE step_id=%s',(step_id,)).fetchone()
            if row is None:raise ValueError('Roadmap step does not exist')
            self._project_access(c,row['project_id'],employee_id,write=True)
            c.execute('UPDATE public.roadmap_steps SET is_completed=%s WHERE step_id=%s',(completed,step_id))
        return True

    def get_roadmap_progress(self,employee_id,roadmap_id):
        with self.transaction() as c:
            row=c.execute('SELECT project_id FROM public.roadmaps WHERE roadmap_id=%s',(roadmap_id,)).fetchone()
            if row is None:raise ValueError('Roadmap does not exist')
            self._project_access(c,row['project_id'],employee_id)
            return c.execute('SELECT * FROM public.roadmap_progress WHERE roadmap_id=%s',(roadmap_id,)).fetchone()

    def add_roadmap_comment(self,employee_id,roadmap_id,body):
        if not isinstance(body,str) or not body.strip():raise ValueError('Comment must not be empty')
        from .db_client import user_id_value
        actor=user_id_value(employee_id)
        with self.transaction() as c:
            c.execute("SELECT set_config('growpath.employee_id',%s,true)",(str(actor),))
            return c.execute('INSERT INTO public.roadmap_comments(roadmap_id,author_employee_id,body) VALUES(%s,%s,%s) RETURNING *',(roadmap_id,actor,body.strip())).fetchone()

    def update_roadmap_comment(self,employee_id,comment_id,body):
        if not isinstance(body,str) or not body.strip():raise ValueError('Comment must not be empty')
        from .db_client import user_id_value
        actor=user_id_value(employee_id)
        with self.transaction() as c:
            c.execute("SELECT set_config('growpath.employee_id',%s,true)",(str(actor),))
            row=c.execute('UPDATE public.roadmap_comments SET body=%s WHERE comment_id=%s RETURNING *',(body.strip(),comment_id)).fetchone()
            if row is None:raise ValueError('Comment does not exist')
            return row

    def delete_roadmap_comment(self,employee_id,comment_id):
        from .db_client import user_id_value
        actor=user_id_value(employee_id)
        with self.transaction() as c:
            c.execute("SELECT set_config('growpath.employee_id',%s,true)",(str(actor),))
            row=c.execute('DELETE FROM public.roadmap_comments WHERE comment_id=%s RETURNING comment_id',(comment_id,)).fetchone()
            return row is not None

    def log_prompt_evaluation(self,**kwargs):raise ValueError('Automatic app evaluation is disabled')
    def log_prompt_optimization(self,**kwargs):raise ValueError('Automatic prompt optimization is disabled')
    def check_prompt_update_trigger(self,threshold=10,user_type='REAL_USER'):return {'should_trigger':False,'current_real_selections':0,'lowest_agent_id':None,'selection_rates':{}}
 from functools import wraps
 from .db_client import serializable
 def serialize_result(method):
    @wraps(method)
    def wrapped(*args,**kwargs):return serializable(method(*args,**kwargs))
    return wrapped
 for name,method in list(vars(Store).items()):
    if not name.startswith('_') and callable(method):setattr(Store,name,serialize_result(method))
 return Store
