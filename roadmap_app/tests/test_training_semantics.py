import json
from unittest import TestCase
from src.shared.training_semantics import validate_training_semantics

def record(answer,payload=None):
    return {'messages':[{'role':'system','content':'JSON'},
        {'role':'user','content':json.dumps(payload or {},ensure_ascii=False)},
        {'role':'assistant','content':json.dumps(answer,ensure_ascii=False)}]}

class TrainingSemanticsTests(TestCase):
    def test_guarantee_is_blocked_but_its_denial_is_allowed(self):
        with self.assertRaisesRegex(ValueError,'GUARANTEED'):
            validate_training_semantics(record({'summary':'마이그레이션 성공률 99% 보장'}))
        validate_training_semantics(record({'summary':'마이그레이션 성공률 99%를 보장하지 않습니다.'}))
        validate_training_semantics(record({'summary':'트랜잭션 원자성 보장 원리를 학습합니다.'}))

    def test_low_score_claim_must_be_supported(self):
        payload={'hidden_assessment_responses':{'responses':[{'score':4},{'score':3}],
                  'overall_mean_score':3.5,'skills':[{'mean_score':3.5}]}}
        with self.assertRaisesRegex(ValueError,'LOW_SCORE'):
            validate_training_semantics(record({'summary':'낮은(1~2점) 병목 스킬에 집중합니다.'},payload))
        validate_training_semantics(record({'summary':'평균 자기보고 점수 3.5를 참고해 계획합니다.'},payload))
        with self.assertRaisesRegex(ValueError,'MEAN_MISMATCH'):
            validate_training_semantics(record({'summary':'평균 자기보고 점수 1.5입니다.'},payload))

    def test_course_topic_must_fit_explicit_project_scope(self):
        payload={'user_context':{'project':'운영체제 동시성 실습'},'retrieved_context':{'courses':[
            {'course_id':'real-course','title':'Get started with Dynamics 365 Commerce channels'}]}}
        answer={'milestones':[{'recommended_courses':[{'course_id':'real-course'}]}]}
        with self.assertRaisesRegex(ValueError,'TOPIC_MISMATCH'):
            validate_training_semantics(record(answer,payload))
        payload['user_context']['project']='Dynamics 365 Commerce 운영 실습'
        validate_training_semantics(record(answer,payload))
