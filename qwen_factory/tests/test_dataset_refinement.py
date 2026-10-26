import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import refine_dataset as refine
class RefinementTests(unittest.TestCase):
 def test_roadmap_hours_and_duration_match_constraints(self):
  q={'user_context':{},'conversation_history':[{'content':'old'}]};a={'milestones':[{'duration':'2주','focus_goal':'조인','key_actions':[]},{'duration':'1주','focus_goal':'검증','key_actions':[]}],'total_duration_weeks':99}
  _,out,did=refine.revision(q,a,{'task':'generate_roadmap','skill_ids':[1]},7,4)
  self.assertTrue(did);self.assertEqual(out['total_duration_weeks'],3)
  self.assertEqual(out['total_hours'],sum(s['hours'] for s in out['milestones']))
  self.assertIsNone(out['total_cost_krw']);self.assertNotIn('conversation_history',q)
 def test_duration_revision_updates_total_and_preserves_completed(self):
  current={'milestones':[{'duration':'2주','phase_name':'완료','focus_goal':'첫 단계'},{'duration':'2주','phase_name':'다음','focus_goal':'둘째'}],'total_duration_weeks':4,'summary':'원본'}
  original=copy.deepcopy(current)
  q,a,did=refine.revision({'task_data':{'current_roadmap':current}},None,{'task':'revise_roadmap','skill_ids':[1]},3,5)
  self.assertEqual(a['total_duration_weeks'],5);self.assertEqual(a['milestones'][0],original['milestones'][0])
  self.assertEqual(current,original);self.assertEqual(len(q['task_data']['allowed_change_paths']),2)
 def test_unclear_duration_is_not_invented(self):
  current={'milestones':[{'duration':None,'focus_goal':'조인','phase_name':'원본'}],'summary':'원본'}
  q,a,_=refine.revision({'task_data':{'current_roadmap':current}},None,{'task':'revise_roadmap','skill_ids':[1]},3,5)
  self.assertIsNone(a['milestones'][0]['duration']);self.assertEqual(q['task_data']['allowed_change_paths'],['/milestones/0/phase_name'])
 def test_all_constraint_modes_are_present(self):
  modes=set();expenses=set()
  for i in range(30):
   q,a,_=refine.revision({'user_context':{'goal':'조인 확인'}},{},{'task':'resolve_constraints','skill_ids':[1]},i,3)
   modes.add(i%5);expenses.add(q['task_data']['planned_expense_krw'])
  self.assertEqual(len(modes),5);self.assertGreater(len(expenses),10)
