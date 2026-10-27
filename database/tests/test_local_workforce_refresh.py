"""Local integration checks. Mutation tests always roll back."""
import importlib.util
from pathlib import Path
import unittest
import psycopg
from src.database.deployment import connect
from src.database.final_schema import verify

class LocalRefreshTests(unittest.TestCase):
 def setUp(self):
  self.c=connect('SUPABASE_DB_URL')
  self.assertIn(self.c.info.host,('127.0.0.1','localhost','::1'))
 def tearDown(self):
  self.c.rollback();self.c.close()
 def test_workforce_and_idempotency(self):
  path=Path(__file__).resolve().parents[1]/'scripts/seed_local_test_workforce.py'
  spec=importlib.util.spec_from_file_location('local_seed',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  before=self.c.execute('SELECT * FROM public.employees ORDER BY employee_id').fetchall()
  result=m.seed(self.c,True)
  self.assertEqual(result['status'],'ALREADY_COMPLETE')
  self.assertEqual(before,self.c.execute('SELECT * FROM public.employees ORDER BY employee_id').fetchall())
  self.assertEqual(len(before),105)
  self.assertEqual(sum(r['source_type']=='TEST_MANUAL' for r in before),100)
  self.assertEqual(self.c.execute('SELECT count(*) AS n FROM public.employee_education_records').fetchone()['n'],100)
 def test_legacy_number_warning_and_new_row_rejected(self):
  result=verify(self.c)
  self.assertEqual(result['legacy_constraint_warnings'][0]['legacy_missing_numbers'],5)
  with self.assertRaises(psycopg.errors.CheckViolation):
   with self.c.transaction():
    self.c.execute("INSERT INTO public.employees(name,source_type) VALUES('rollback-only','TEST_MANUAL')")
 def test_other_unvalidated_constraints_still_fail(self):
  with self.c.transaction(force_rollback=True):
   self.c.execute('ALTER TABLE public.employees ADD CONSTRAINT refresh_regression_probe CHECK (employee_id>0) NOT VALID')
   with self.assertRaisesRegex(ValueError,'Unvalidated DB constraints remain'):verify(self.c)
 def test_expected_name_does_not_allow_wrong_expression(self):
  with self.c.transaction(force_rollback=True):
   self.c.execute('ALTER TABLE public.employees DROP CONSTRAINT employees_number_required')
   self.c.execute('ALTER TABLE public.employees ADD CONSTRAINT employees_number_required CHECK (employee_id>0) NOT VALID')
   with self.assertRaisesRegex(ValueError,'Unvalidated DB constraints remain'):verify(self.c)

if __name__=='__main__':unittest.main()
