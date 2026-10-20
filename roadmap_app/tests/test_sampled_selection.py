import json
from unittest import TestCase
from unittest.mock import patch
from src.finetuning.sampled_selection import allocate, template_holds, build_draft, POLICY_VERSION
from src.finetuning.curation_core import SPLITS, TASKS


class SampledSelectionTests(TestCase):
    def test_reserves_missing_type_slots_in_each_split(self):
        rows=[]
        for split, size in SPLITS.items():
            for i in range(size+10):
                rows.append({'id':f'{split}-{i}', 'task':'generate_roadmap', 'split':split,
                             'family_id':split, 'messages':[{'content':'활동 테스트 리포트'}]})
        selected, missing=allocate(rows)
        for split,size in SPLITS.items():
            self.assertEqual(sum(r['split']==split for r in selected), size-6*(60*size//1500))
            self.assertEqual(missing[split]['generate_roadmap'],0)
        self.assertEqual(len({r['id'] for r in selected}),len(selected))

    def test_detects_only_observed_progress_template(self):
        def row(text):
            return {'task':'progress_checkin','messages':[{'content':json.dumps({'action_plan':text})}]}
        self.assertTrue(template_holds(row('Phase 1의 남은 실습과 이번 주 가용 시간을 확인한 뒤 1주 순연하는 보완 계획을 협의합니다.')))
        self.assertFalse(template_holds(row('회귀 테스트 3개를 실행하고 결과표를 저장한다. 실패 0건이면 완료한다.')))
        self.assertFalse(template_holds(row({'activity':'회귀 테스트 실행','artifact':'결과표'})))

    def test_requires_ten_bound_samples_before_selection(self):
        with self.assertRaisesRegex(ValueError,'EXACTLY_TEN'):
            build_draft([],{'policy':POLICY_VERSION,'records':[]},{})

    def test_survey_skill_name_ampersand_alone_is_not_multi_concept(self):
        row={'task':'generate_survey','messages':[{'content':json.dumps([{'question':'데이터 거버넌스 & 보안 규정 준수의 접근 권한 설정에 대해 얼마나 알고 있나요?'}],ensure_ascii=False)}]}
        self.assertEqual(template_holds(row),[])

    def test_sampled_mode_never_fabricates_per_record_semantic_approval(self):
        from src.finetuning import curate_dataset as cli
        rows=[]
        for i in range(10):
            rows.append({'id':str(i),'task':'evidence_boundary','split':'train','family_id':str(i),
                         'messages':[{'role':'user','content':json.dumps({'index':i})},
                                     {'role':'assistant','content':json.dumps({'answer':f'확인이 필요합니다 {i}'})}]})
        samples={'policy':POLICY_VERSION,'records':[
            {'candidate_id':r['id'],'messages_sha256':cli.digest(r['messages']),
             'decision':'hold' if r['id']=='0' else 'retain','reason':'실제 내용 검토'} for r in rows]}
        with patch('src.finetuning.sampled_selection.validate_candidate'), patch('src.finetuning.sampled_selection.quality_findings',return_value=[]):
            selected,decisions,report=build_draft(rows,samples,{'1':{'provisional_pass':False}})
        self.assertNotIn('0',{r['id'] for r in selected})
        self.assertNotIn('1',{r['id'] for r in selected})
        self.assertFalse(report['training_approved'])
        self.assertFalse(report['per_record_semantic_review_completed'])
        self.assertFalse(report['api_called'])
        samples['records'][0]['messages_sha256']='changed'
        with self.assertRaisesRegex(ValueError,'BINDING'):
            build_draft(rows,samples,{})
