from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import patch
from src.finetuning.final_generation import DurableBudget,generate_one,generation_format


class FinalGenerationTests(TestCase):
    def test_progress_schema_preserves_history_and_unapproved_regulation_boundary(self):
        schema=generation_format({'task':'progress_checkin'})['response_format']['json_schema']['schema']
        self.assertEqual(schema['properties']['preserve_previous_version']['enum'],[True])
        self.assertEqual(schema['properties']['regulation_citations']['maxItems'],0)
        self.assertFalse(schema['additionalProperties'])
    def test_attempt_limit_is_persisted_before_send_and_survives_resume(self):
        state={'http_attempts':{}};saved=[]
        b=DurableBudget(state,lambda s:saved.append(dict(s['http_attempts'])))
        self.assertTrue(b.reserve('a'));self.assertEqual(saved[-1],{'a':1})
        resumed=DurableBudget(state,lambda s:None)
        self.assertTrue(resumed.reserve('a'));self.assertTrue(resumed.reserve('a'))
        self.assertFalse(resumed.reserve('a'));self.assertEqual(state['http_attempts']['a'],3)

    def test_global_cap_cannot_be_exceeded(self):
        b=DurableBudget({'http_attempts':{'past':789}},lambda s:None)
        self.assertFalse(b.reserve('new'))

    def test_invalid_answer_has_at_most_three_http_calls_and_no_candidate(self):
        calls=[]
        def create(**kwargs):calls.append(kwargs);return NS(usage=None,choices=[NS(finish_reason='stop',message=NS(content='invalid json'))])
        client=NS(chat=NS(completions=NS(create=create)))
        req={'task':'evidence_boundary','family_id':'f','split':'train','skill_ids':[1],
             'source_fingerprint':'db','request_id':'r','seed_candidate_id':'s','scenario_case':'missing',
             'messages':[{'role':'system','content':'JSON'},{'role':'user','content':'{}'}]}
        b=DurableBudget({'http_attempts':{}},lambda s:None)
        candidate,result=generate_one(req,client,b)
        self.assertIsNone(candidate);self.assertEqual(len(calls),3)
        self.assertEqual(result['status'],'FAILED_WITHIN_APPROVED_BUDGET')
        self.assertTrue(all(c['model']=='gpt-5-mini' for c in calls))
