import json
from copy import deepcopy
from unittest import TestCase
from src.finetuning.supplement_preparation import build_request, prepare
from src.finetuning.curation_core import SPLITS,TASKS


def seed(split='train', index=0):
    user={'target_skills':['실제스킬1','실제스킬2'],'work_context_summary':f'{split} 프로젝트 {index}: 데이터 처리 오류를 재현하고 회귀 테스트 결과표를 저장한다.'}
    context={'courses':[{'course_id':'real-db-course','title':'실제 강좌'}], 'books':[], 'certifications':[],
             'regulation_rag':{'approved':[],'pending_review':[],'as_of':'2026-10-20'}}
    roadmap={'milestones':[{'phase_name':'테스트 구현','key_actions':['회귀 테스트와 결과표 작성'],'duration':'2주'}]}
    return {'id':f'{split}-{index}','family_id':split+'-family','split':split,'task':'generate_roadmap',
            'source_fingerprint':'db','skill_ids':[1,2],
            'messages':[{'role':'system','content':'plan'}, {'role':'user','content':json.dumps({'user_context':user,'retrieved_context':context},ensure_ascii=False)},
                        {'role':'assistant','content':json.dumps(roadmap,ensure_ascii=False)}]}


MANIFEST={'source_fingerprint':'db','preparation_as_of':'2026-10-20'}
ONTO={'skill_catalog':[{'skill_id':1,'name':'실제스킬1'},{'skill_id':2,'name':'실제스킬2'}]}


class SupplementPreparationTests(TestCase):
    def test_every_case_is_offline_real_context_and_family_preserving(self):
        original=seed();before=deepcopy(original)
        for task in ('generate_survey','interpret_assessment','resolve_constraints','evidence_boundary','progress_checkin'):
            for i in range(10):
                req=build_request(original,task,i,MANIFEST,ONTO)
                self.assertEqual(req['family_id'],original['family_id'])
                self.assertEqual(req['split'],'train')
                self.assertEqual([m['role'] for m in req['messages']],['system','user'])
                payload=json.loads(req['messages'][1]['content'])
                if task!='generate_survey' and not(task=='evidence_boundary' and i==3):
                    self.assertEqual(payload['retrieved_context'],json.loads(original['messages'][1]['content'])['retrieved_context'])
        self.assertEqual(original,before)

    def test_unanswered_skill_has_no_fabricated_score(self):
        req=build_request(seed(),'interpret_assessment',6,MANIFEST,ONTO)
        data=json.loads(req['messages'][1]['content'])['task_data']
        self.assertEqual(data['unanswered_skill_ids'],[2])
        self.assertEqual([r['skill_id'] for r in data['responses']],[1])

    def test_attack_is_separate_from_database_facts(self):
        req=build_request(seed(),'evidence_boundary',5,MANIFEST,ONTO)
        p=json.loads(req['messages'][1]['content'])
        self.assertEqual(p['task_data']['untrusted_material']['source'],'synthetic_attack_fixture_not_database_fact')
        self.assertEqual(p['retrieved_context']['regulation_rag']['approved'],[])

    def test_progress_uses_plan_without_invented_verified_completion(self):
        req=build_request(seed(),'progress_checkin',7,MANIFEST,ONTO)
        p=json.loads(req['messages'][1]['content'])['task_data']
        self.assertEqual(p['current_week_available_hours'],1)
        self.assertEqual(p['verified_completed'],[])
        self.assertEqual(p['current_phase']['phase_name'],'테스트 구현')

    def test_survey_slots_have_single_scope_and_real_skill_names(self):
        req=build_request(seed(),'generate_survey',1,MANIFEST,ONTO)
        p=json.loads(req['messages'][1]['content'])
        self.assertEqual(len(p['slots']),10)
        self.assertEqual(p['slots'][0]['focus'],'오류 원인 진단')
        self.assertEqual({s['skill'] for s in p['slots']},{'실제스킬1','실제스킬2'})

    def test_exact_263_requests_and_final_split_targets(self):
        missing={'train':{'generate_survey':28,'interpret_assessment':46,'resolve_constraints':44,'evidence_boundary':44,'progress_checkin':48},
                 'validation':{'generate_survey':3,'interpret_assessment':6,'resolve_constraints':6,'evidence_boundary':6,'progress_checkin':6},
                 'test':{'generate_survey':2,'interpret_assessment':6,'resolve_constraints':6,'evidence_boundary':6,'progress_checkin':6}}
        rows=[]
        for split,target in SPLITS.items():
            for task in TASKS:
                for i in range(60*target//1500-missing[split].get(task,0)):
                    r=seed(split,len(rows));r['task']=task;rows.append(r)
            while sum(r['split']==split for r in rows)<target-sum(missing[split].values()):
                rows.append(seed(split,len(rows)))
        composition={'policy':'local-full-sample10/v1','selected_count':1237,'source_fingerprint':'db',
                     'minimum_shortfalls':{s:{t:missing[s].get(t,0) for t in TASKS} for s in SPLITS}}
        reqs,report=prepare(rows,composition,MANIFEST,ONTO)
        self.assertEqual(len(reqs),263)
        self.assertEqual(report['splits'],{'train':210,'validation':27,'test':26})
        self.assertFalse(report['api_called']);self.assertFalse(report['external_transfer_approved'])
        self.assertEqual(len({r['request_id'] for r in reqs}),263)
        broken=deepcopy(rows);broken[-1]['split']='train'
        with self.assertRaises(ValueError):prepare(broken,composition,MANIFEST,ONTO)
