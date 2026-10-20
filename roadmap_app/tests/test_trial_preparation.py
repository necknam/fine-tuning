from copy import deepcopy
import json
from unittest import TestCase
from src.finetuning.trial_preparation import build_trial_requests,choose_seeds


class TrialPreparationTests(TestCase):
    def test_reprocessing_preserves_eight_and_limits_changes_to_unresolved_cases(self):
        from src.finetuning.trial_preparation import build_reprocess_requests
        c,m,o=self.fixture();requests,_=build_trial_requests(c,m,o)
        holds={'low_self_report','high_self_report','mixed_self_report','stale_self_report',
               'practice_verification_pending','project_priority','zero_duration'}
        errors={'zero_duration','unknown_catalog_cost','conflicting_start','conflicting_scope'}
        rows=[];outcomes=[];missing=[]
        for i,req in enumerate(requests):
            if req['trial_case']=='unanswered_skill':missing.append({'request_id':req['request_id']});continue
            rows.append({'id':'c'+str(i),'request_id':req['request_id'],'messages':deepcopy(req['messages'])})
            verdict='error' if req['trial_case'] in errors else 'needs_review' if req['trial_case']=='time_overload' else 'pass'
            outcomes.append({'request_id':req['request_id'],'provisional_pass':verdict=='pass' and req['trial_case'] not in holds,
                             'agent_findings':[{'code':'hold'}] if req['trial_case'] in holds else []})
        summary={'records':outcomes,'missing_requests':missing};before=deepcopy((requests,rows,summary))
        retry,plan=build_reprocess_requests(requests,rows,summary)
        self.assertEqual(len(retry),8);self.assertEqual(len(plan['preserved']),8)
        self.assertEqual(plan['counts'],{'regenerate_and_review':8,'review_only':4})
        self.assertEqual(plan['base_llm_calls'],20)
        original={r['request_id']:r for r in requests}
        for req in retry:
            self.assertEqual(req['messages'][1],original[req['parent_request_id']]['messages'][1])
            self.assertNotEqual(req['request_id'],req['parent_request_id'])
        self.assertEqual((requests,rows,summary),before)
        with self.assertRaisesRegex(ValueError,'SCOPE_MISMATCH'):
            build_reprocess_requests(requests,rows[:-1],summary)

    def fixture(self):
        candidates=[]
        for i in range(12):
            split='train' if i<10 else 'validation' if i==10 else 'test'
            user={'job_title':'가상 학습자','target_skills':['A','B'],'work_context_summary':'기존 프로젝트 '+str(i)}
            payload={'user_context':user,'retrieved_context':{'courses':[{'course_id':'real-source'}],
                    'books':[],'certifications':[],'regulation_rag':{'approved':[],'review_only':[]}}}
            candidates.append({'id':str(i),'origin':'existing','task':'generate_roadmap','family_id':'f'+str(i),
                'split':split,'skill_ids':[1,2],'errors':[],
                'messages':[{'role':'system','content':'instructions'},{'role':'user','content':json.dumps(payload)}]})
        return candidates,{'source_fingerprint':'fp'},{'skill_catalog':[{'skill_id':1,'name':'A'},{'skill_id':2,'name':'B'}]}

    def test_twenty_requests_have_ten_variations_per_type_and_keep_source_splits(self):
        candidates,manifest,onto=self.fixture();before=deepcopy(candidates)
        requests,report=build_trial_requests(candidates,manifest,onto)
        self.assertEqual(report['tasks'],{'interpret_assessment':10,'resolve_constraints':10})
        self.assertEqual(report['splits'],{'train':16,'validation':2,'test':2})
        self.assertEqual(report['distinct_families'],10)
        self.assertFalse(report['api_called']);self.assertEqual(candidates,before)
        source={c['id']:c for c in candidates}
        for req in requests:
            seed=source[req['seed_candidate_id']]
            self.assertEqual((req['family_id'],req['split']),(seed['family_id'],seed['split']))
            self.assertEqual(json.loads(req['messages'][1]['content'])['retrieved_context'],
                             json.loads(seed['messages'][1]['content'])['retrieved_context'])
        self.assertEqual(len({r['trial_case'] for r in requests}),20)
        again,_=build_trial_requests(candidates,manifest,onto);self.assertEqual(requests,again)

    def test_partial_response_is_not_filled_and_time_conflict_is_exact(self):
        c,m,o=self.fixture();requests,_=build_trial_requests(c,m,o)
        partial=next(r for r in requests if r['trial_case']=='unanswered_skill')
        d=json.loads(partial['messages'][1]['content'])['task_data']
        self.assertEqual(len(d['responses']),1);self.assertEqual(len(d['unanswered_skill_ids']),1)
        self.assertNotEqual(d['responses'][0]['skill_id'],d['unanswered_skill_ids'][0])
        conflict=next(r for r in requests if r['trial_case']=='time_overload')
        p=json.loads(conflict['messages'][1]['content'])
        self.assertEqual(p['task_data']['available_hours'],p['user_context']['constraints']['duration_weeks']*p['user_context']['constraints']['weekly_hours'])
        self.assertGreater(p['task_data']['requested_hours'],p['task_data']['available_hours'])

    def test_missing_heldout_family_stops_preparation(self):
        c,m,o=self.fixture()
        with self.assertRaisesRegex(ValueError,'DISTINCT_SOURCE_FAMILIES'):
            build_trial_requests([r for r in c if r['split']=='train'],m,o)
