import json,tempfile,unittest,sys,copy
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import cloud_evaluation as live
import practical_reports

class DB:
 def __init__(self):self.docs={};self.result=None
 def execute(self,query,args=()):
  if query.startswith('SELECT content'):self.result=(self.docs[args[0]],) if args[0] in self.docs else None
  elif query.startswith('INSERT INTO documents'):self.docs[args[0]]=args[1];self.result=None
  else:self.result=None
  return self
 def fetchone(self):return self.result
 def commit(self):pass
 def close(self):pass
class LiveEvaluationTests(unittest.TestCase):
 def fixture(self,root):
  p=root/'data/eval/template.jsonl';p.parent.mkdir(parents=True)
  rows=[{'messages':[{'role':'user','content':json.dumps({'case':i})}]} for i in range(10)]
  p.write_text(''.join(json.dumps(x)+'\n' for x in rows),encoding='utf-8')
  return rows,{'data':{'test_file':'data/eval/template.jsonl'},'evaluation':{'file':'data/eval/template.jsonl','sha256':live.hashlib.sha256(p.read_bytes()).hexdigest()},'live_evaluation':{'enabled':True,'cohort_id':'test_v1'}}
 def test_freeze_once_reuses_database_receipt_across_weights(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);rows,cfg=self.fixture(root);db=DB()
   with patch.object(live.dashboard_store,'pg',return_value=db),patch.object(live,'fetch_ten',return_value=rows) as fetch:
    first,r1=live.freeze(root,cfg);second,r2=live.freeze(root,cfg)
    self.assertEqual(r1,r2);fetch.assert_called_once();self.assertNotEqual(first['data']['test_file'],cfg['data']['test_file'])
    self.assertEqual(cfg['data']['test_file'],'data/eval/template.jsonl')
 def test_changed_template_cannot_reuse_batch(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);rows,cfg=self.fixture(root);db=DB()
   with patch.object(live.dashboard_store,'pg',return_value=db),patch.object(live,'fetch_ten',return_value=rows):
    live.freeze(root,cfg);p=root/'data/eval/template.jsonl';p.write_bytes(p.read_bytes()+b'\n');cfg['evaluation']['sha256']=live.hashlib.sha256(p.read_bytes()).hexdigest()
    with self.assertRaisesRegex(ValueError,'다른 요청'):live.freeze(root,cfg)
 def test_tampered_receipt_is_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);rows,cfg=self.fixture(root);db=DB()
   with patch.object(live.dashboard_store,'pg',return_value=db),patch.object(live,'fetch_ten',return_value=rows):
    live.freeze(root,cfg);key=next(iter(db.docs));receipt=json.loads(db.docs[key]);receipt['rows'][0]['messages'][0]['content']='tampered';db.docs[key]=json.dumps(receipt)
    with self.assertRaisesRegex(ValueError,'해시'):live.freeze(root,cfg)
 def test_report_does_not_invent_missing_totals_or_resource_names(self):
  report={'messages':[{'role':'user','content':json.dumps({'user_context':{},'retrieved_context':{}})}], 'tuned':{'text':json.dumps({'milestones':[{'recommended_courses':[{'course_id':'unknown'}]}]})}}
  output=practical_reports.render(report);self.assertIn('총시간: 미확인',output);self.assertIn('제공 근거에서 확인되지 않음',output);self.assertNotIn('총비용: 0',output)
 def test_batch_path_traversal_rejected(self):
  with self.assertRaises(ValueError):live.validate_batch('../unsafe')
 def test_bf16_and_custom_epochs_are_validated(self):
  import yaml
  from runpod_factory_sample import check_settings
  cfg=yaml.safe_load((ROOT/'configs/hyperparameters.production.pinned.yaml').read_text(encoding='utf-8'))
  cfg['quantization']['load_in_4bit']=False;cfg['experiments'][0]['training']['num_train_epochs']=2;cfg['experiments'][0]['artifacts']['save_epochs']=[1,2];check_settings(cfg)
  cfg['experiments'][0]['artifacts']['save_epochs']=[3]
  with self.assertRaises(ValueError):check_settings(cfg)

class EmployeeInputTests(unittest.TestCase):
 def test_assignment_is_stable_and_returns_copy(self):
  from cloud_employee_context import fixed_assignment
  ids=fixed_assignment();self.assertEqual(len(ids),10);self.assertEqual(len(set(ids)),9)
  ids[0]=999;self.assertEqual(fixed_assignment(),[12,14,6,8,16,7,15,17,13,12])
 def test_template_biography_is_removed_and_revision_keeps_scenario(self):
  from cloud_employee_context import apply_profile
  person={'employee_id':12,'source_type':'TEST_MANUAL','synthetic':True,'skills':[{'skill_id':1,'name':'SQL'}],'planned_project_description':'가상 프로젝트'}
  request={'task':'generate_roadmap','user_context':{'self_check':{'score':5},'goal':'원본 목표','target_skill_ids':[13],'constraints':{'weekly_hours':3}}}
  result=apply_profile(request,person)
  self.assertNotIn('self_check',result['user_context']);self.assertEqual(result['user_context']['goal'],'가상 프로젝트')
  self.assertEqual(request['user_context']['goal'],'원본 목표')
  request['task']='revise_roadmap';request['task_data']={'current_roadmap':{'title':'보존'}}
  result=apply_profile(request,person)
  self.assertEqual(result['user_context']['goal'],'원본 목표');self.assertEqual(result['task_data'],request['task_data'])
  with self.assertRaises(ValueError):apply_profile(request,{**person,'source_type':'REAL_USER'})
 def test_changed_assignment_cannot_reuse_frozen_cohort(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);rows,cfg=LiveEvaluationTests().fixture(root);db=DB()
   cfg['live_evaluation']['case_employee_ids']=[6]*10
   with patch.object(live.dashboard_store,'pg',return_value=db),patch.object(live,'fetch_ten',return_value=rows):
    live.freeze(root,cfg);cfg['live_evaluation']['case_employee_ids']=[7]*10
    with self.assertRaisesRegex(ValueError,'직원 배정'):live.freeze(root,cfg)


class ReportInputDisplay(unittest.TestCase):
 def test_nested_db_input_and_revision_details_are_visible_without_mutation(self):
  request={'task':'revise_roadmap','user_context':{'goal':'고정 프로젝트','constraints':{'duration_weeks':4,'weekly_hours':3,'budget_krw':0},'profile_snapshot':{'synthetic':True,'name':'가상 직원'}},'task_data':{'current_roadmap':{'stages':[]},'user_feedback':'두 단계만 변경'},'retrieved_context':{'courses':[{'course_id':17,'title':'DB 교육','cost':None}],'books':[],'certifications':[]}}
  original=copy.deepcopy(request);view=practical_reports.input_view(request)
  self.assertEqual(request,original)
  self.assertEqual((view['goal'],view['weekly_hours'],view['budget_krw']),('고정 프로젝트',3,0))
  self.assertEqual(view['revision_request'],'두 단계만 변경')
  self.assertEqual(view['resources'][0]['resource_id'],17)
  self.assertIsNone(view['resources'][0]['cost'])
  self.assertEqual(view['existing_roadmap'],{'stages':[]})
 def test_legacy_flat_input_is_used_as_supplied_in_report(self):
  request={'goal':'기존 프로젝트','duration_weeks':2,'weekly_hours':4,'budget_krw':9000,'perspective':'시간 우선'}
  report={'messages':[{'role':'user','content':json.dumps(request)}],'tuned':{'text':json.dumps({'stages':[{'name':'확인 단계','activity':'고정 입력 실행'}]})}}
  output=practical_reports.render(report)
  for text in ['기존 프로젝트','시간 우선','2주','9000원','확인 단계','고정 입력 실행']:self.assertIn(text,output)
  self.assertIn('총비용: 미확인',output)
 def test_cloud_input_panel_understands_nested_contract(self):
  import ast
  from streamlit.testing.v1 import AppTest
  source=(ROOT/'scripts/local_dashboard.py').read_text(encoding='utf-8');tree=ast.parse(source)
  snippets='\n'.join(ast.get_source_segment(source,node) for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in ('parse_payload','case_request','show_input'))
  request={'user_context':{'goal':'검증 프로젝트','constraints':{'duration_weeks':4,'weekly_hours':3,'budget_krw':12000}},'retrieved_context':{'courses':[{'course_id':17,'title':'실제 DB 교육'}]}}
  report={'messages':[{'role':'user','content':json.dumps(request)}]}
  app=AppTest.from_string('import json,streamlit as st\n'+snippets+'\nshow_input('+repr(report)+')',default_timeout=15).run()
  self.assertEqual(len(app.exception),0)
  visible='\n'.join(item.value for item in app.markdown)
  for text in ['검증 프로젝트','4주','3시간','12,000원','실제 DB 교육']:self.assertIn(text,visible)
