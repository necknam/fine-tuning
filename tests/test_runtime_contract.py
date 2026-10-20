import json,sys
from pathlib import Path
from unittest import TestCase
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import ai_evaluation as ai

class RuntimeEvaluationTests(TestCase):
 def report(self,r,a):return {'messages':[{'role':'user','content':json.dumps(r)}],'tuned':{'text':json.dumps(a)}}
 def test_runtime_milestones_and_legacy_stages_both_supported(self):
  r={'user_context':{},'retrieved_context':{'courses':[],'books':[],'certifications':[]}}
  a={'milestones':[{'duration':'1주','recommended_courses':[],'recommended_books':[],'recommended_certifications':[]}],
   'total_duration_weeks':1,'regulation_summary':'규정 확인 필요','regulation_citations':[]}
  self.assertIn('자료 ID: 목록 내 ID만 사용',ai.check_numbers(self.report(r,a)))
  legacy={'stages':[{'hours':1,'cost_krw':0,'resource_ids':[]}],'total_hours':1,'total_cost_krw':0}
  self.assertIn('시간 합계: 일치',ai.check_numbers(self.report({'resources':[]},legacy)))
 def test_survey_scores_have_no_roadmap_only_dimensions(self):
  schema=ai.schema('generate_survey')
  self.assertEqual(schema['properties']['resources']['properties']['score'],{'type':'null'})
  review={k:{'score':4 if k in ('goal_fit','constraints') else None,'reason':'검토','evidence':[]} for k in ai.DIMENSIONS}
  review.update(summary='검토',issues=[])
  self.assertEqual(ai.validate_review(review,task='generate_survey'),4)
  review['resources']['score']=5
  with self.assertRaises(ValueError):ai.validate_review(review,task='generate_survey')
 def test_unknown_source_id_and_unapproved_regulation_cap_resources(self):
  r={'user_context':{},'retrieved_context':{'courses':[],'books':[],'certifications':[]}}
  a={'milestones':[{'recommended_courses':[{'course_id':'fake'}],'recommended_books':[],'recommended_certifications':[]}],
    'regulation_citations':['fake'],'regulation_summary':'지원 확정'}
  review={k:{'score':4,'reason':'검토','evidence':['지원 확정']} for k in ai.DIMENSIONS}
  review['revision']['score']=None;review.update(summary='검토',issues=[])
  result,_=ai.apply_strict_checks(review,self.report(r,a))
  self.assertEqual(result['resources']['score'],1);self.assertEqual(review['resources']['score'],4)
 def test_rubric_is_versioned_without_overwriting_old_history(self):
  self.assertEqual(ai.RUBRIC_VERSION,'growpath_judge_v4_runtime_tasks')
  self.assertIn('앞의 공통 항목 점수 필수 지침보다 우선',ai.task_instructions('generate_survey'))


class ReportInputPolicyTests(TestCase):
 def test_runpod_bundle_contains_active_cohort_without_secrets(self):
  import tempfile,runpy,hashlib,zipfile,yaml
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)
   for name in ('scripts','configs','data/eval','data/sample','tests','docs'):(root/name).mkdir(parents=True,exist_ok=True)
   for name in ('requirements-runpod.txt','README.md','docs/FINETUNING_GUIDE.md','docs/hyperparameters.html'):
    (root/name).write_text('fixture',encoding='utf-8')
   active=root/'data/eval/prompts.app_v1.jsonl'
   active.write_text(''.join(json.dumps({'messages':[{'role':'user','content':str(i)}]})+'\n' for i in range(10)),encoding='utf-8')
   active.with_suffix('.manifest.json').write_text('{}',encoding='utf-8')
   (root/'data/eval/prompts.jsonl').write_text('legacy',encoding='utf-8')
   cfg={'data':{'test_file':'data/eval/prompts.app_v1.jsonl'},'evaluation':{'mode':'shared_fixed_10',
        'file':'data/eval/prompts.app_v1.jsonl','expected_count':10,'sha256':hashlib.sha256(active.read_bytes()).hexdigest()}}
   (root/'configs/hyperparameters.sample.pinned.yaml').write_text(yaml.safe_dump(cfg),encoding='utf-8')
   (root/'.env').write_text('SECRET=fixture',encoding='utf-8')
   script=root/'scripts/pack_runpod_upload.py';script.write_bytes((ROOT/'scripts/pack_runpod_upload.py').read_bytes())
   runpy.run_path(str(script))
   with zipfile.ZipFile(root/'outputs/runpod_control_bundle.zip') as bundle:
    self.assertIn('data/eval/prompts.app_v1.jsonl',bundle.namelist())
    self.assertIn('data/eval/prompts.app_v1.manifest.json',bundle.namelist())
    self.assertNotIn('.env',bundle.namelist())
 def make(self,folder):
  import hashlib
  root=Path(folder);p=root/'data/eval/prompts.jsonl';p.parent.mkdir(parents=True)
  p.write_text(''.join(json.dumps({'messages':[{'role':'user','content':str(i)}]})+'\n' for i in range(10)),encoding='utf-8')
  config={'data':{'test_file':'data/eval/prompts.jsonl'},'evaluation':{'mode':'shared_fixed_10',
   'file':'data/eval/prompts.jsonl','expected_count':10,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}}
  return root,p,config
 def test_fixed_ten_and_changed_input_blocked(self):
  from tempfile import TemporaryDirectory
  from db_registry import report_input_info
  with TemporaryDirectory() as folder:
   root,p,cfg=self.make(folder)
   self.assertEqual(report_input_info(root,cfg)['rows'],10)
   p.write_text(p.read_text()+'\n',encoding='utf-8')
   with self.assertRaisesRegex(ValueError,'changed'):report_input_info(root,cfg)
 def test_new_report_file_override_is_rejected(self):
  from tempfile import TemporaryDirectory
  from db_registry import report_input_info
  with TemporaryDirectory() as folder:
   root,p,cfg=self.make(folder);cfg['data']['test_file']='data/sample/eval/test.jsonl'
   with self.assertRaisesRegex(ValueError,'override'):report_input_info(root,cfg)
 def test_legacy_experiment_config_still_readable(self):
  from db_registry import report_input_info
  self.assertIsNone(report_input_info(Path('.'),{'data':{'test_file':'legacy.jsonl'}}))
 def test_time_estimate_uses_1200_training_rows_not_1500_or_3000(self):
  import ast,yaml
  from tempfile import TemporaryDirectory
  from streamlit.testing.v1 import AppTest
  text=(ROOT/'scripts/local_dashboard.py').read_text(encoding='utf-8')
  node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='show_measured_estimate')
  function=ast.get_source_segment(text,node)
  cfg=yaml.safe_load((ROOT/'configs/hyperparameters.sample.pinned.yaml').read_text(encoding='utf-8'))
  cfg['data']['expected_train_samples']=1200
  with TemporaryDirectory() as folder:
   path=Path(folder);(path/'recipe.yaml').write_text(yaml.safe_dump(cfg),encoding='utf-8')
   source=("import streamlit as st\nimport yaml\nfrom pathlib import Path\nROOT=Path("+repr(folder)+")\n"
    +"def measured_training_speed(log,steps): return 2.0\n"
    +"def duration_text(seconds): return str(int(seconds))\n"+function
    +"\nshow_measured_estimate({'config':'recipe.yaml','job_id':'test','log_tail':''},None,None)\n")
   app=AppTest.from_string(source,default_timeout=15).run()
   self.assertEqual(len(app.exception),0)
   self.assertEqual(app.metric[0].value,'750')
   self.assertIn('1,200',app.metric[0].label)
