import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from practical_reports import render


class ReportAliasDisplayTests(unittest.TestCase):
    def report(self, answer):
        return {'messages':[{'role':'user','content':json.dumps({'user_context':{},'retrieved_context':{}})}],
                'tuned':{'text':json.dumps(answer)}}

    def test_model_deliverable_array_and_zero_cost_remain_visible(self):
        report=self.report({'milestones':[{'deliverables':['code and input','actual output'],'cost':0}], 'total_cost':0})
        text=render(report)
        self.assertIn('- 산출물: code and input',text)
        self.assertIn('- 산출물: actual output',text)
        self.assertIn('비용: 0원',text)
        self.assertIn('- 총비용: 0원',text)

    def test_explicit_unknown_canonical_cost_does_not_take_alias_value(self):
        text=render(self.report({'milestones':[{'cost_krw':None,'cost':0}], 'total_cost_krw':None,'total_cost':0}))
        self.assertIn('- 총비용: 미확인원',text)
        self.assertNotIn('- 총비용: 0원',text)
