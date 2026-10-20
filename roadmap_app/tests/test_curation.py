import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from src.finetuning.curation_core import (POLICY, DIMENSIONS, normalize_messages,
    select_candidates, validate_candidate, validate_review, choose_batch, validate_comparison,
    answer_spans,bind_review_quotes)
from src.finetuning import curate_dataset as cli


def candidate(task='evidence_boundary', family='family', split='train', label='one'):
    request={'task':task,'retrieved_context':{},'user_context':{},'task_data':{}}
    answer={'answer':'근거가 부족합니다. '+label,'next_step':'실습 기록을 확인하세요. '+label,
            'response_type':'VERIFICATION_REQUIRED','regulation_summary':'규정 확인 필요','regulation_citations':[]}
    c={'task':task,'family_id':family,'split':split,'source_fingerprint':'snapshot',
       'messages':[{'role':'system','content':'JSON만 반환'},
                   {'role':'user','content':json.dumps(dict(request,label=label))},
                   {'role':'assistant','content':json.dumps(answer)}],'errors':[]}
    c['id']=cli.candidate_id(c)
    return c


def review(c, score=4):
    return {'candidate_id':c['id'],'scores':{k:score for k in DIMENSIONS},'verdict':'pass',
            'issues':[],'reason':'입력과 답변 대조 완료','source_fingerprint':'snapshot',
            'policy_sha256':cli.digest(POLICY),'provider':{'model':'judge'}}


class CurationTests(TestCase):
    def test_force_review_is_scoped_and_does_not_call_api_in_preview(self):
        from argparse import Namespace
        a=candidate(label='a');b=candidate(label='b')
        with TemporaryDirectory() as folder:
            path=Path(folder)/'ids.json';path.write_text(json.dumps([a['id']]),encoding='utf-8')
            state=(Path(folder),{}, {},[a,b],{a['id']:review(a),b['id']:review(b)}, {})
            args=Namespace(limit=20,execute=False,candidate_ids=str(path),force_review=True)
            with patch.object(cli,'load_run',return_value=state),patch.object(cli,'adapter_for',side_effect=AssertionError('API forbidden')):
                result=cli.review(args)
                self.assertEqual(result['batch_size'],1);self.assertFalse(result['api_called'])
                args.candidate_ids=None
                with self.assertRaisesRegex(ValueError,'REQUIRES_CANDIDATE_IDS'):cli.review(args)
                args.candidate_ids=str(path);path.write_text(json.dumps(['unknown']),encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'UNKNOWN_REVIEW'):cli.review(args)

    def test_failure_diagnostics_return_only_allowlisted_codes(self):
        from src.finetuning.curation_core import validation_failure_code
        self.assertEqual(validation_failure_code(ValueError('SELF_CORRECTION_EXHAUSTED (ValueError: ASSESSMENT_SCORE_CHANGED)')),'ASSESSMENT_SCORE_CHANGED')
        self.assertEqual(validation_failure_code(ValueError('secret-dsn-and-key-value')),'UNCLASSIFIED_ERROR')
        self.assertEqual(validation_failure_code(ValueError('SELF_CORRECTION_EXHAUSTED (JSONDecodeError: content)')),'INVALID_JSON')

    def test_understanding_rating_cannot_establish_absent_work_experience(self):
        from src.finetuning.curation_core import quality_findings
        c=candidate('interpret_assessment')
        answer={'observations':[{'skill_id':1,'score':1,'interpretation':'진단 실무 경험이 거의 없음. 실습이 필요함.'}]}
        c['messages'][-1]['content']=json.dumps(answer)
        self.assertEqual(quality_findings(c)[0]['code'],'SELF_REPORT_EXPERIENCE_INFERENCE')
        request=json.loads(c['messages'][1]['content'])
        request['task_data']['user_report']='해당 프로젝트의 실무 경험이 아직 없습니다.'
        c['messages'][1]['content']=json.dumps(request)
        self.assertEqual(quality_findings(c),[])

    def test_correct_self_report_caveat_does_not_trigger_experience_rule(self):
        from src.finetuning.curation_core import quality_findings
        c=candidate('interpret_assessment')
        for text in ('이해도가 낮다고 응답했습니다. 실무 경험은 확인되지 않았습니다.',
                     '점수가 낮다고 실무 경험이 없다는 뜻은 아닙니다.'):
            c['messages'][-1]['content']=json.dumps({'observations':[{'interpretation':text}]})
            self.assertEqual(quality_findings(c),[])

    def test_known_survey_double_judgment_is_rejected_even_when_judge_passes(self):
        from src.finetuning.curation_core import quality_findings
        c=candidate('generate_survey')
        c['messages'][-1]['content']=json.dumps([{'question':'스킬 이해도는 어느 정도이며 얼마나 알고 있나요?'}])
        self.assertEqual(quality_findings(c)[0]['code'],'SURVEY_REPEATED_JUDGMENT')
        selected,rejected,report=select_candidates([c],{c['id']:review(c,5)})
        self.assertEqual(selected,[])
        self.assertIn('SURVEY_REPEATED_JUDGMENT',rejected[0]['reasons'])

    def test_unsupported_personnel_score_implication_is_flagged(self):
        from src.finetuning.curation_core import quality_findings
        c=candidate();request=json.loads(c['messages'][1]['content'])
        request['task_data']={'user_query':'설문 점수로 인사평가를 감점하나요?'}
        c['messages'][1]['content']=json.dumps(request)
        answer=json.loads(c['messages'][-1]['content'])
        answer['answer']='점수는 판단의 한 지표일 수 있지만 정책 확인이 필요합니다.'
        c['messages'][-1]['content']=json.dumps(answer)
        self.assertEqual(quality_findings(c)[0]['code'],'UNSUPPORTED_PERSONNEL_SCORE_USE')
        answer['answer']='승인 근거가 없어 인사평가 연계 여부를 확인할 수 없습니다.'
        c['messages'][-1]['content']=json.dumps(answer)
        self.assertEqual(quality_findings(c),[])

    def test_review_quote_ids_resolve_only_to_actual_answer(self):
        answer={'answer':'실제 답변','next_step':'검증 기록 확인'}
        result=bind_review_quotes({'issues':[{'quote_id':'A0002','reason':'검토'}]},answer)
        self.assertEqual(result['issues'][0]['quote'],'검증 기록 확인')
        with self.assertRaisesRegex(ValueError,'UNKNOWN_QUOTE_ID'):
            bind_review_quotes({'issues':[{'quote_id':'A9999','reason':'가짜'}]},answer)

    def test_credential_in_payload_is_blocked_before_transmission(self):
        with patch.dict('os.environ',{'OPENAI_API_KEY':'fake-secret-abcdef123456'}):
            with self.assertRaisesRegex(ValueError,'CREDENTIAL'):
                cli.llm_payload({'note':'fake-secret-abcdef123456'})
        with self.assertRaisesRegex(ValueError,'CREDENTIAL'):
            cli.llm_payload({'note':'postgresql://user:password@localhost/db'})

    def test_trial_batch_covers_small_tasks_not_only_majority(self):
        pool=[candidate(task='generate_roadmap',family=str(i),label=str(i)) for i in range(30)]
        pool.append(candidate(task='evidence_boundary',family='rare',label='rare'))
        batch=choose_batch(pool,10)
        self.assertEqual(len(batch),10)
        self.assertIn('evidence_boundary',{c['task'] for c in batch})

    def test_unpreferred_rewrite_is_never_selected(self):
        c=candidate();c['selection_block_reason']='REFINEMENT_NOT_YET_PREFERRED'
        self.assertEqual(select_candidates([c],{c['id']:review(c,5)})[0],[])

    def test_pairwise_evidence_must_quote_both_real_answers(self):
        result={'preferred':'revised','reason':'구체적 산출물','evidence':[{'original_quote':'옛 문장','revised_quote':'없는 문장'}]}
        with self.assertRaisesRegex(ValueError,'QUOTE'):
            validate_comparison(result,{'answer':'옛 문장'},{'answer':'새 문장'})

    def test_refine_improves_compares_and_retains_immutable_original(self):
        from argparse import Namespace
        from types import SimpleNamespace
        from src.finetuning import export_finetuning_dataset as legacy
        c=candidate();c['origin']='existing';before_messages=deepcopy(c['messages'])
        improved=json.loads(c['messages'][-1]['content']);improved['next_step']='실습 결과 파일을 저장하고 입력 3개에 대한 재현 결과를 확인하세요.'
        args=Namespace(limit=10,execute=True,attempt=1)
        calls=[]
        def fake_call(adapter,system,user,parser,validator,**kwargs):
            payload=json.loads(user);calls.append(system)
            if system==POLICY:
                self.assertTrue(kwargs['response_format']['json_schema']['strict'])
                result={k:v for k,v in review(c).items() if k in ('scores','verdict','issues','reason')}
            elif system==cli.REFINEMENT_POLICY:result=improved
            else:
                result={'preferred':'revised','reason':'산출물과 확인 기준을 구체화',
                        'evidence':[{'original_quote':'실습 기록을 확인하세요.', 'revised_quote':'실습 결과 파일을 저장하고 입력 3개에 대한 재현 결과를 확인하세요.'}]}
            validator(result);return result,{'provider':'test','model':'fake'}
        with TemporaryDirectory() as folder:
            work=Path(folder)
            onto={'behaviors':{'evidence_boundary':{}},'constraints':{},'skill_catalog':[]}
            state=(work,{'source_fingerprint':'snapshot'},onto,[c],{}, {'usable':set(),'resources':{},'approved':{}})
            adapter=SimpleNamespace(get_usage_summary=lambda:{'total_tokens':0})
            with patch.object(cli,'load_run',return_value=state),patch.object(cli,'adapter_for',return_value=adapter),patch.object(legacy,'call_llm_with_retry',side_effect=fake_call):
                result=cli.refine(args)
                first_calls=len(calls);second=cli.refine(args)
            self.assertEqual(result['decisions'],{'PREFERRED_REVISED':1})
            self.assertEqual(len(calls),first_calls)
            child=cli.read_jsonl(work/'refined.jsonl')[0]
            self.assertNotIn('selection_block_reason',child)
            self.assertEqual(child['messages'][:-1],before_messages[:-1])
            self.assertEqual(c['messages'],before_messages)

    def test_unreviewed_or_low_quality_does_not_fill_quota(self):
        c=candidate()
        selected,_,report=select_candidates([c],{})
        self.assertEqual(selected,[]);self.assertFalse(report['complete'])
        bad=review(c);bad['scores']['grounding']=2
        self.assertEqual(select_candidates([c],{c['id']:bad})[0],[])

    def test_families_cannot_cross_split_even_if_task_differs(self):
        a=candidate(split='train',label='a');b=candidate(split='test',label='b')
        selected,_,report=select_candidates([a,b],{c['id']:review(c) for c in (a,b)})
        self.assertEqual(selected,[]);self.assertEqual(report['family_leaks_blocked'],1)

    def test_reformatted_duplicate_answers_are_removed(self):
        a=candidate(family='a',label='a');b=candidate(family='b',label='b')
        b['messages'][-1]['content']=json.dumps(json.loads(a['messages'][-1]['content']),indent=4)
        b['id']=cli.candidate_id(b)
        selected,_,_=select_candidates([a,b],{c['id']:review(c) for c in (a,b)})
        self.assertEqual(len(selected),1)

    def test_long_nearly_identical_answers_do_not_inflate_dataset(self):
        a=candidate(family='a',label='a');b=candidate(family='b',label='b')
        for c,ending in ((a,'first'),(b,'second')):
            answer=json.loads(c['messages'][-1]['content'])
            answer['answer']=' '.join('activity'+str(i) for i in range(240))+' '+ending
            c['messages'][-1]['content']=json.dumps(answer);c['id']=cli.candidate_id(c)
        selected,rejected,_=select_candidates([a,b],{c['id']:review(c) for c in (a,b)})
        self.assertEqual(len(selected),1)
        self.assertTrue(any('LEXICAL_NEAR_DUPLICATE' in r['reasons'] for r in rejected))

    def test_critic_cannot_invent_quote_or_award_inconsistent_pass(self):
        c=candidate();r=review(c)
        r.update(verdict='fail',issues=[{'quote':'없는 문장','reason':'잘못된 근거'}])
        with self.assertRaisesRegex(ValueError,'QUOTE'):validate_review(r,json.loads(c['messages'][-1]['content']))
        r=review(c);r['scores']['grounding']=3
        with self.assertRaisesRegex(ValueError,'CONTRADICTION'):validate_review(r,{})

    def test_pending_regulation_cannot_be_cited(self):
        c=candidate();answer=json.loads(c['messages'][-1]['content'])
        answer['regulation_citations']=['pending']
        c['messages'][-1]['content']=json.dumps(answer)
        with self.assertRaisesRegex(ValueError,'REGULATION'):validate_candidate(c)

    def test_diagnosis_requires_exact_self_report_scores(self):
        c=candidate(task='interpret_assessment')
        request=json.loads(c['messages'][1]['content']);request['task_data']={'responses':[{'skill_id':1,'score':2}]}
        c['messages'][1]['content']=json.dumps(request)
        answer={'assessment_method':'self_report','observations':[{'skill_id':1,'score':5,'interpretation':'이해도'}],
                'priorities':[{'skill_id':1,'reason':'기초 확인','next_action':'예제 검증'}],
                'regulation_summary':'규정 확인 필요','regulation_citations':[]}
        c['messages'][-1]['content']=json.dumps(answer)
        with self.assertRaisesRegex(ValueError,'SCORE_CHANGED'):validate_candidate(c)
        answer['observations'][0]['score']=2;c['messages'][-1]['content']=json.dumps(answer)
        validate_candidate(c)

    def test_legacy_edit_gains_preserve_paths_without_changing_answer(self):
        c=candidate();current={'summary':'보존','milestones':[{'duration':'3주','key_actions':['산출물 작성']}], 'total_duration_weeks':3}
        feedback='1번째 마일스톤의 계획상 기간만 1주로 변경해 주세요. 나머지 내용과 추천 ID는 유지하세요. 전체 기간을 계산할 수 없으면 null로 표시하세요.'
        c['messages'][1]['content']=json.dumps({'current_roadmap':current,'user_feedback':feedback,'retrieved_context':{}})
        before=c['messages'][-1]['content'];messages=normalize_messages(c,'revise_roadmap')
        self.assertEqual(messages[-1]['content'],before)
        paths=json.loads(messages[1]['content'])['task_data']['preserve_paths']
        self.assertIn('/summary',paths);self.assertIn('/milestones/0/key_actions',paths)
        self.assertNotIn('/milestones/0/duration',paths)

    def test_preview_never_constructs_paid_adapter(self):
        from argparse import Namespace
        c=candidate();args=Namespace(limit=20,execute=False)
        with patch.object(cli,'load_run',return_value=(Path('.'),{}, {},[c],{},{})),patch.object(cli,'adapter_for',side_effect=AssertionError('API forbidden')):
            result=cli.review(args)
        self.assertEqual(result['status'],'PREVIEW');self.assertFalse(result['api_called'])

    def test_candidate_tampering_is_detected_before_any_api_call(self):
        c=candidate();old=cli.candidate_id(c)
        c['messages'][-1]['content']='{}'
        self.assertNotEqual(cli.candidate_id(c),old)

    def test_minimum_coverage_prevents_false_complete(self):
        # Even perfect scores on one task never prove seven-behavior coverage.
        candidates=[candidate(family=str(i),label=str(i)) for i in range(10)]
        _,_,report=select_candidates(candidates,{c['id']:review(c,5) for c in candidates},minimum_per_task=10)
        self.assertFalse(report['complete']);self.assertGreater(report['minimum_shortfalls']['test']['interpret_assessment'],0)

    def test_exact_1500_and_split_sizes_with_all_behaviors(self):
        from src.shared.runtime_contract import TASKS
        pool=[]
        for split,n in (('train',1200),('validation',150),('test',150)):
            for i in range(n):pool.append(candidate(task=TASKS[i%7],family=split+str(i),split=split,label=split+str(i)))
        selected,_,report=select_candidates(pool,{c['id']:review(c) for c in pool})
        self.assertTrue(report['complete']);self.assertEqual(len(selected),1500)
        self.assertEqual(report['split_counts'],{'train':1200,'validation':150,'test':150})
        self.assertFalse(report['training_approved'])

    def test_generation_checkpoint_keeps_audit_manifest_immutable(self):
        from argparse import Namespace
        from src.finetuning import export_finetuning_dataset as legacy
        c=candidate();req={k:c[k] for k in ('task','family_id','split','source_fingerprint')}
        req.update(skill_ids=[1],request_id='request-1',messages=c['messages'][:-1])
        answer=json.loads(c['messages'][-1]['content'])
        args=Namespace(requests=None,attempt=1,limit=1,execute=True,model=None)
        with TemporaryDirectory() as folder:
            work=Path(folder);cli.write_jsonl(work/'supplement_requests.jsonl',[req]);(work/'run.json').write_text('immutable')
            state=(work,{'source_fingerprint':'snapshot'}, {'skill_catalog':[{'skill_id':1,'name':'SQL'}]},[],{},
                   {'usable':set(),'resources':{},'approved':{}})
            def fake_call(adapter,system,user,parser,validator):
                validator(answer);return answer,{'provider':'test','model':'fake'}
            with patch.object(cli,'load_run',return_value=state),patch.object(cli,'adapter_for',return_value=object()),patch.object(legacy,'call_llm_with_retry',side_effect=fake_call):
                result=cli.generate(args)
            self.assertEqual(result['added'],1)
            self.assertEqual((work/'run.json').read_text(),'immutable')
            saved=cli.read_jsonl(work/'generated.jsonl')
            self.assertEqual(saved[0]['id'],cli.candidate_id(saved[0]))

    def test_saved_plan_survives_partial_generation(self):
        from argparse import Namespace
        with TemporaryDirectory() as folder:
            work=Path(folder);req={'request_id':'unfinished'}
            cli.write_jsonl(work/'supplement_requests.jsonl',[req])
            with patch.object(cli,'load_run',return_value=(work,{}, {},[],{},{})):
                result=cli.plan(Namespace())
            self.assertEqual(result['status'],'SAVED_PLAN_PENDING')
            self.assertEqual(cli.read_jsonl(work/'supplement_requests.jsonl'),[req])

    def test_new_attempt_skips_already_accepted_request(self):
        from argparse import Namespace
        c=candidate();c.update(origin='supplement',request_id='passed',attempt=1)
        with TemporaryDirectory() as folder:
            work=Path(folder);cli.write_jsonl(work/'supplement_requests.jsonl',[{'request_id':'passed'}])
            args=Namespace(requests=None,attempt=2,limit=20,execute=False)
            with patch.object(cli,'load_run',return_value=(work,{}, {},[c],{c['id']:review(c)},{})):
                result=cli.generate(args)
            self.assertEqual(result['batch_size'],0)
