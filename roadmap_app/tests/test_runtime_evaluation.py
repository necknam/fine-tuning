import json
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from src.finetuning.runtime_evaluation import build_cases
from src.shared.runtime_contract import runtime_checks


class AppEvaluationCasesTests(TestCase):
    def cases(self):
        legacy=Path(__file__).resolve().parents[1]/'data/reference/eval10_legacy_fixture.jsonl'
        if not legacy.exists():
            legacy=Path(__file__).resolve().parents[2]/'qwen_factory/data/eval/prompts.jsonl'
        rows=[json.loads(x) for x in legacy.read_text(encoding='utf-8').splitlines()]
        return rows,build_cases(rows,{'courses':[{'course_id':'real-1','title':'DB source'}],
                'books':[],'certifications':[],'regulation_rag':{'approved':[],'review_only':[]}},
                {p:'app prompt' for p in ('비용 우선','시간 우선','업무 적용 우선')})[0]

    def test_ten_scenarios_keep_user_constraints_and_remove_mock_catalog(self):
        old,cases=self.cases();self.assertEqual(len(cases),10)
        for before,after in zip(old,cases):
            b=json.loads(before['messages'][1]['content']);a=json.loads(after['messages'][1]['content'])
            self.assertNotIn('resources',a)
            self.assertEqual(a['user_context']['goal'],b['goal'])
            for key in ('budget_krw','weekly_hours','duration_weeks','start_stage'):
                self.assertEqual(a['user_context']['constraints'][key],b[key])
            self.assertEqual(bool(a['retrieved_context']['courses']),bool(b['resources']))
        attack=json.loads(cases[7]['messages'][1]['content'])['retrieved_context']['untrusted_documents'][0]
        self.assertEqual(attack['source_type'],'synthetic_adversarial_test')

    def test_revision_preserves_completion_and_detects_unrequested_edit(self):
        _,cases=self.cases();request=json.loads(cases[8]['messages'][1]['content'])
        answer=deepcopy(request['task_data']['current_roadmap'])
        self.assertTrue(answer['milestones'][0]['completed'])
        answer['milestones'][1]['hours']=2;answer['milestones'][2]['hours']=7
        self.assertIn('부분 수정 보존: 준수',runtime_checks(request,answer))
        answer['milestones'][0]['completion_record']='invented'
        self.assertIn('부분 수정 보존: 위반',runtime_checks(request,answer))
