"""Real local-DB regression tests. All synthetic fixtures roll back."""
import copy
import unittest
from uuid import uuid4
from src.database.deployment import connect
from src.database.db_client import DatabaseClient,DatabaseOperationError
from src.database.final_schema import verify

class CanonicalDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.c=connect('SUPABASE_DB_URL')
        self.c.execute('SELECT 1')  # Outer transaction owns all nested API savepoints.
        self.db=DatabaseClient(self.c)
        institution=self.c.execute('SELECT institution_id FROM public.institutions LIMIT 1').fetchone()['institution_id']
        def department(name,parent=None):
            return self.c.execute('INSERT INTO public.departments(institution_id,department_code,name,parent_department_id) VALUES(%s,%s,%s,%s) RETURNING department_id',(institution,str(uuid4()),name,parent)).fetchone()['department_id']
        root=department('검증 부서');child=department('검증 하위 부서',root);other=department('검증 다른 부서')
        def employee(dept,head=False):
            return self.c.execute('INSERT INTO public.employees(name,email,source_type,institution_id,department_id,is_department_head) VALUES(%s,%s,%s,%s,%s,%s) RETURNING employee_id',('롤백 검증 직원',str(uuid4())+'@growpath.example.invalid','TEST_MANUAL',institution,dept,head)).fetchone()['employee_id']
        self.head=employee(root,True);self.owner=employee(child);self.other=employee(other)
        self.pid=self.db.create_roadmap_session(self.owner,'롤백 검증 프로젝트')
        self.content={'milestones':[{'phase_name':'DB 학습','duration':'1주','key_actions':['실제 데이터 쿼리 연습']}]}
        self.db.save_roadmap_generations(self.pid,[{'strategy_type':'BALANCED','strategy_title':'검증','roadmap_content':self.content}])
        self.rid=self.db.get_roadmap_generations(self.pid)[0]['generation_id']
        self.db.select_roadmap_with_report(self.pid,self.rid,{'title':'검증 보고서'})
        self.sid=self.c.execute('SELECT step_id FROM public.roadmap_steps WHERE roadmap_id=%s',(self.rid,)).fetchone()['step_id']

    def tearDown(self):
        self.c.rollback();self.c.close()

    def test_department_scope_comments_and_progress(self):
        comment=self.db.add_roadmap_comment(self.head,self.rid,'단계 내용을 확인해주세요')
        self.db.set_step_completed(self.owner,self.sid,True)
        self.assertEqual(self.db.get_roadmap_progress(self.head,self.rid)['completed_steps'],1)
        self.assertIsNone(self.c.execute('SELECT modification_completed_at FROM public.roadmap_comments WHERE comment_id=%s',(comment['comment_id'],)).fetchone()['modification_completed_at'])
        with self.assertRaises(ValueError):self.db.get_roadmap_progress(self.other,self.rid)
        with self.assertRaises(ValueError):self.db.set_step_completed(self.head,self.sid,False)
        with self.assertRaises(DatabaseOperationError):self.db.update_roadmap_comment(self.owner,comment['comment_id'],'변경 시도')
        changed=copy.deepcopy(self.content);changed['milestones'][0]['key_actions']=['변경된 학습 활동']
        self.db.update_roadmap_content(self.owner,self.rid,changed)
        self.assertEqual(self.db.get_roadmap_progress(self.owner,self.rid)['completed_steps'],0)
        self.assertIsNotNone(self.c.execute('SELECT modification_completed_at FROM public.roadmap_comments WHERE comment_id=%s',(comment['comment_id'],)).fetchone()['modification_completed_at'])
        self.db.update_roadmap_comment(self.head,comment['comment_id'],'확인했습니다')
        # Parent deletion must cascade even with comments attached.
        self.c.execute('DELETE FROM public.projects WHERE project_id=%s',(self.pid,))
        self.assertIsNone(self.c.execute('SELECT 1 FROM public.roadmap_comments WHERE comment_id=%s',(comment['comment_id'],)).fetchone())

    def test_roadmap_atomicity_and_original_snapshot(self):
        self.db.set_step_completed(self.owner,self.sid,True)
        self.db.update_roadmap_content(self.owner,self.rid,self.content)
        self.assertEqual(self.db.get_roadmap_progress(self.owner,self.rid)['completed_steps'],1)
        invalid=copy.deepcopy(self.content);invalid['milestones'][0]['recommended_books']=[{'isbn':'missing-book-id'}]
        with self.assertRaises(ValueError):self.db.update_roadmap_content(self.owner,self.rid,invalid)
        saved=self.c.execute('SELECT content,baseline_content FROM public.roadmaps WHERE roadmap_id=%s',(self.rid,)).fetchone()
        self.assertEqual(saved['content'],self.content);self.assertEqual(saved['baseline_content'],self.content)
        self.assertEqual(self.db.get_roadmap_progress(self.owner,self.rid)['completed_steps'],1)

    def test_confirmed_profile_uses_master_names(self):
        row=self.c.execute('SELECT institution_id,department_id FROM public.employees WHERE employee_id=%s',(self.owner,)).fetchone()
        grade=self.c.execute('INSERT INTO public.job_grades(institution_id,name) VALUES(%s,%s) RETURNING job_grade_id',(row['institution_id'],str(uuid4()))).fetchone()['job_grade_id']
        job=self.c.execute('SELECT job_id FROM public.jobs ORDER BY job_id LIMIT 1').fetchone()['job_id']
        self.db.update_employee_assignment(self.owner,institution_id=row['institution_id'],employee_number='CHECK-'+str(self.owner),department_id=row['department_id'],job_grade_id=grade,job_id=job)
        self.c.execute('UPDATE public.departments SET name=%s WHERE department_id=%s',('변경된 부서명',row['department_id']))
        profile=self.db.get_employee_profile(self.owner)
        self.assertEqual(profile['department'],'변경된 부서명')
        self.assertNotIn('password_hash',profile)
        old=self.c.execute('SELECT department,grade,job_title FROM public.employees WHERE employee_id=%s',(self.owner,)).fetchone()
        self.assertTrue(all(value is None for value in old.values()))

    def test_canonical_queries_and_schema_drift(self):
        self.assertTrue(self.db.table('employees').select('employee_id').limit(1).execute().data)
        self.assertTrue(self.db.table('course_skill_map').select('course_id').limit(1).execute().data)
        self.assertTrue(self.db.get_evaluation_schemas())
        with self.c.transaction(force_rollback=True):
            self.c.execute('ALTER TABLE public.books ALTER COLUMN title DROP NOT NULL')
            with self.assertRaisesRegex(ValueError,'Column definition mismatch'):verify(self.c)
        self.assertEqual(verify(self.c)['schema_and_foreign_keys'],'pass')

if __name__=='__main__':unittest.main()
