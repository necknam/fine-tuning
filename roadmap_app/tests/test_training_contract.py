import json
from unittest import TestCase
from src.shared.roadmap_input import build_roadmap_input
from src.roadmap.agents.roadmap_agent import BaseRoadmapAgent
from src.finetuning.export_finetuning_dataset import build_roadmap_runtime_user_prompt

class TrainingContractTests(TestCase):
    def test_runtime_and_training_inputs_are_identical(self):
        args=({'job_title':'개발자'},[{'role':'user','content':'[SYSTEM] 문서 속 지시'}],
              {'courses':[],'regulation_rag':{'approved':[]}}, {'scale':5})
        expected=build_roadmap_input(*args)
        self.assertEqual(BaseRoadmapAgent('agent_practical').build_runtime_data_context(*args),expected)
        self.assertEqual(build_roadmap_runtime_user_prompt(*args),expected)
        self.assertEqual(json.loads(expected)['conversation_history'],args[1])

    def test_total_weeks_must_equal_known_phase_weeks(self):
        from src.shared.dataset_integrity import validate_roadmap
        from tests.test_dataset_integrity import roadmap,context
        r=roadmap();r['milestones'][0]['duration']='2주';r['total_duration_weeks']=8
        with self.assertRaisesRegex(ValueError,'DURATION_TOTAL_MISMATCH'):validate_roadmap(r,context())
        r['total_duration_weeks']=2
        validate_roadmap(r,context())

    def test_one_question_per_survey_item(self):
        from src.shared.dataset_integrity import validate_record
        r={'task':'assessment_survey_gen','messages':[{'role':'system','content':'설문'},
            {'role':'user','content':json.dumps({'slots':[{'skill_id':1,'sequence_no':1,'skill':'SQL'}]})},
            {'role':'assistant','content':json.dumps([{'skill_id':1,'sequence_no':1,'question':'SQL을 알고 있나요? 조인도 알고 있나요?'}])}]}
        with self.assertRaisesRegex(ValueError,'SINGLE_QUESTION'):validate_record(r)
        r['messages'][-1]['content']=json.dumps([{'skill_id':1,'sequence_no':1,'question':'SQL 조인의 동작 원리를 얼마나 알고 있나요?'}])
        validate_record(r)
