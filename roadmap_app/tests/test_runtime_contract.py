import json
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from src.shared.runtime_contract import runtime_checks,active_criteria,task_of
from src.shared.survey_contract import SURVEY_SYSTEM_PROMPT,build_survey_input,validate_survey_output

def sample():
 request={'user_context':{'constraints':{'duration_weeks':4,'weekly_hours':3,'budget_krw':0}},
 'retrieved_context':{'courses':[{'course_id':'allowed'}],'books':[],'certifications':[],
 'regulation_rag':{'approved':[],'as_of':'2026-10-20'}}}
 answer={'total_duration_weeks':2,'total_hours':4,'total_cost_krw':0,'regulation_citations':[],
 'regulation_summary':'규정 확인 필요','milestones':[{'duration':'2주','hours':4,'cost_krw':0,
 'recommended_courses':[{'course_id':'allowed'}],'recommended_books':[],'recommended_certifications':[]}]}
 return request,answer

class RuntimeContractTests(TestCase):
 def test_actual_milestones_and_rag_ids_are_checked(self):
  r,a=sample();checks=runtime_checks(r,a)
  self.assertIn('자료 ID: 목록 내 ID만 사용',checks)
  self.assertIn('시간 합계: 일치',checks)
  self.assertIn('규정 인용: 준수',checks)
  a['milestones'][0]['recommended_courses']=[{'course_id':'invented'}]
  self.assertTrue(any('미제공 ID 사용' in s for s in runtime_checks(r,a)))
 def test_unknown_hours_are_not_zero_or_pass(self):
  r,a=sample();del a['milestones'][0]['hours']
  self.assertIn('시간 합계: 구조화된 수치 부족으로 확인 불가',runtime_checks(r,a))
 def test_duration_and_budget_violation(self):
  r,a=sample();a['total_duration_weeks']=5;a['total_cost_krw']=100
  checks=runtime_checks(r,a)
  self.assertIn('기간 합계: 불일치',checks);self.assertIn('기간 한도: 위반',checks);self.assertIn('예산 한도: 위반',checks)
 def test_review_or_future_regulations_are_rejected(self):
  r,a=sample();row={'rag_chunk_id':'r','review_status':'pending_review','search_status':'active',
  'requires_review':False,'availability_status':'available','effective_from':'2025-01-01','effective_to':None}
  r['retrieved_context']['regulation_rag']['approved']=[row];a['regulation_citations']=['r']
  self.assertIn('규정 인용: 위반',runtime_checks(r,a))
  row['review_status']='approved';row['effective_from']='2027-01-01'
  self.assertIn('규정 인용: 위반',runtime_checks(r,a))
 def test_partial_revision_preserves_explicit_paths(self):
  r,a=sample();r['task']='revise_roadmap';r['task_data']={'current_roadmap':deepcopy(a),'preserve_paths':['/milestones/0/duration']}
  self.assertIn('부분 수정 보존: 준수',runtime_checks(r,a))
  a['milestones'][0]['duration']='3주'
  self.assertIn('부분 수정 보존: 위반',runtime_checks(r,a))
 def test_survey_uses_its_own_rubric(self):
  slots=[{'skill_id':1,'skill':'SQL','sequence_no':1}]
  answer=[{'skill_id':1,'sequence_no':1,'question':'SQL 조인의 동작을 얼마나 알고 있나요?'}]
  checks=runtime_checks({'slots':slots},answer)
  self.assertEqual(checks,['설문 슬롯·스킬·단일 문항: 준수'])
  self.assertEqual(active_criteria('generate_survey'),{'goal_fit','constraints'})
  answer[0]['question']='SQL을 아나요? 조인도 아나요?'
  self.assertIn('위반',runtime_checks({'slots':slots},answer)[0])
 def test_unknown_task_is_not_scored_as_a_roadmap(self):
  with self.assertRaisesRegex(ValueError,'UNSUPPORTED'):task_of({'task':'delete_database'})
 def test_runtime_and_generator_survey_inputs_prompts_and_validation_match(self):
  from src.roadmap.agents import assessment_agent as module
  from src.finetuning.export_finetuning_dataset import SURVEY_GEN_SYSTEM_PROMPT,validate_survey_array
  skills=[{'skill_id':1,'name':'SQL'}];slots=[{'sequence_no':i+1,'skill_id':1,'skill':'SQL',
   'focus':('핵심 개념','프로젝트 적용 방법','검증과 오류 진단','설계 선택과 제약')[i%4]} for i in range(8)]
  answer=[{'sequence_no':i+1,'skill_id':1,'question':f'SQL 프로젝트 항목 {i+1}의 동작을 얼마나 알고 있나요?'} for i in range(8)]
  with patch.object(module.assessment_service,'get_project_plan',return_value={'refined_plan':'p','project_goal':'g'}),patch.object(module.assessment_service,'resolve_skill_names',return_value=skills),patch.object(module.llm_adapter,'generate',return_value=SimpleNamespace(success=True,content=json.dumps(answer))) as call:
   actual=module.AssessmentAgent().generate_pre_assessment('test',8,['SQL'])
  messages=call.call_args.args[0]
  self.assertEqual(messages[0]['content'],SURVEY_GEN_SYSTEM_PROMPT)
  self.assertEqual(messages[1]['content'],build_survey_input('p','g',slots))
  self.assertEqual(actual,validate_survey_array(answer,slots))
  answer[0]['question']='SQL을 아나요? 조인도 아나요?'
  with self.assertRaisesRegex(ValueError,'SINGLE_QUESTION'):validate_survey_output(answer,slots)
