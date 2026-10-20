"""Regression tests for approval, resume/merge provenance and runtime exports."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, MagicMock

from src.shared.dataset_integrity import (VERSION, digest, validate_checkpoint,
    validate_roadmap, validate_current_context)
from src.finetuning import export_finetuning_dataset as gen
from src.finetuning import merge_finetuning_dataset as merge
from src.finetuning.dataset_pipeline import DatasetPipeline


def context():
    return {'courses': [{'course_id': 'course-real', 'title': 'SQL 실습'}], 'books': [],
            'certifications': [], 'regulation_rag': {'approved': [], 'review_only': [],
            'as_of': date.today().isoformat()}, 'resource_rag': {'no_evidence': False}}


def roadmap():
    return {'strategy_title': '실무 SQL 계획', 'summary': '자기보고 결과를 참고한 학습 계획',
            'total_duration_weeks': None, 'regulation_citations': [], 'regulation_summary': '규정 확인 필요',
            'milestones': [{'phase_name': '기초 실습', 'focus_goal': '실제 쿼리 작성', 'key_actions': ['JOIN 결과 검증'],
                            'duration': None, 'recommended_courses': [], 'recommended_books': [],
                            'recommended_certifications': []}]}


def chunk(**updates):
    value = {'rag_chunk_id': 'real-chunk', 'chunk_text': '검토할 규정 원문', 'search_status': 'needs_review',
             'review_status': 'pending_review', 'availability_status': 'review_only', 'requires_review': True,
             'effective_from': '2024-01-01', 'effective_to': None}
    value.update(updates)
    return value


def checkpoint():
    records = [{'task': 'agent_practical', 'messages': [
        {'role': 'system', 'content': 'DB 근거만 사용'},
        {'role': 'user', 'content': json.dumps({'retrieved_context': context()}, ensure_ascii=False)},
        {'role': 'assistant', 'content': json.dumps(roadmap(), ensure_ascii=False)}]}]
    return {'generator_version': VERSION, 'settings_sha256': 'settings', 'case_id': 'a' * 20,
            'split': 'train', 'group_id': 'sql-domain', 'records': records,
            'records_sha256': digest(records), 'retrieval_sha256': digest([context()])}


class IntegrityTests(unittest.TestCase):
    def test_review_not_promoted(self):
        c = context(); c['regulation_rag']['review_only'] = [chunk()]
        before = deepcopy(c)
        result = gen.compact_context(c)
        self.assertEqual(result['regulation_rag']['approved'], [])
        self.assertEqual(result['regulation_rag']['review_only'][0]['search_status'], 'needs_review')
        self.assertEqual(c, before)

    def test_invalid_approved_pool_demoted_without_rewriting(self):
        c = context(); c['regulation_rag']['approved'] = [chunk()]
        result = gen.compact_context(c)
        self.assertFalse(result['regulation_rag']['approved'])
        self.assertTrue(result['regulation_rag']['review_only'][0]['requires_review'])

    def test_real_approval_preserves_full_text_and_dates(self):
        c = context(); approved = chunk(search_status='active', review_status='approved',
                                       availability_status='available', requires_review=False)
        approved['chunk_text'] = '가' * 800
        c['regulation_rag']['approved'] = [approved]
        result = gen.compact_context(c)['regulation_rag']['approved'][0]
        self.assertEqual(result['chunk_text'], approved['chunk_text'])
        self.assertEqual(result['effective_to'], None)

    def test_review_citation_rejected_and_not_erased(self):
        r = roadmap(); r['regulation_citations'] = ['real-chunk']; before = deepcopy(r)
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED'):
            gen.validate_roadmap_report(r, context(), 'agent_practical')
        self.assertEqual(r, before)

    def test_fake_resource_rejected_without_replacement(self):
        r = roadmap(); r['milestones'][0]['recommended_courses'] = [{'course_id': 'fake'}]
        before = deepcopy(r)
        with self.assertRaises(ValueError): validate_roadmap(r, context())
        self.assertEqual(r, before)

    def test_no_forced_resource_or_duration(self):
        r = roadmap(); before = deepcopy(r)
        gen.validate_roadmap_report(r, context(), 'agent_certified')
        self.assertEqual(r, before)

    def test_false_approval_pool_rejected_even_with_no_citations(self):
        c = context(); c['regulation_rag']['approved'] = [chunk()]
        with self.assertRaisesRegex(ValueError, 'UNAPPROVED_EVIDENCE'):
            validate_roadmap(roadmap(), c)

    def test_expired_approval_rejected(self):
        c = context(); c['regulation_rag']['approved'] = [chunk(search_status='active', review_status='approved',
            availability_status='available', requires_review=False, effective_to='2025-01-01')]
        with self.assertRaises(ValueError): validate_roadmap(roadmap(), c)

    def test_no_approved_summary_must_be_explicit(self):
        r = roadmap(); r['regulation_summary'] = '교육비 지급 확정'
        with self.assertRaisesRegex(ValueError, 'UNAPPROVED_REGULATION_ASSERTION'):
            validate_roadmap(r, context())

    def test_resume_blocks_legacy_version(self):
        c = checkpoint(); c['generator_version'] = 'v7'
        with self.assertRaisesRegex(ValueError, 'VERSION_OR_SETTINGS'): validate_checkpoint(c, 'settings')

    def test_resume_blocks_changed_settings(self):
        with self.assertRaisesRegex(ValueError, 'VERSION_OR_SETTINGS'): validate_checkpoint(checkpoint(), 'other')

    def test_checkpoint_hash_detects_changed_target(self):
        c = checkpoint(); c['records'][0]['messages'][2]['content'] = '{}'
        with self.assertRaisesRegex(ValueError, 'CONTENT_HASH'): validate_checkpoint(c, 'settings')

    def test_checkpoint_search_hash_checked(self):
        c = checkpoint(); c['retrieval_sha256'] = 'bad'
        with self.assertRaisesRegex(ValueError, 'RETRIEVAL_HASH'): validate_checkpoint(c, 'settings')

    def test_valid_checkpoint_accepted(self):
        validate_checkpoint(checkpoint(), 'settings', 'a' * 20)

    def test_survey_missing_skill_rejected_without_repair(self):
        rows = [{'sequence_no': 1, 'skill_id': 1, 'question': '내부 원리에 대해 얼마나 알고 있나요?'}]
        slots = [{'sequence_no': 1, 'skill_id': 1, 'skill': 'SQL', 'focus': 'JOIN'}]
        before = deepcopy(rows)
        with self.assertRaisesRegex(ValueError, 'SKILL_NAME'): gen.validate_survey_array(rows, slots)
        self.assertEqual(rows, before)

    def test_wrong_plan_skill_not_repaired(self):
        out = {'tech_stack': ['fake']}; before = deepcopy(out)
        with self.assertRaisesRegex(ValueError, 'SKILL_TAG'): gen.validate_refined_plan(out, [{'name': 'SQL'}])
        self.assertEqual(out, before)

    def test_merge_reads_only_final_accepted_index(self):
        with TemporaryDirectory() as temp:
            p = Path(temp); (p / 'cases').mkdir(); cp = checkpoint()
            (p / 'cases' / ('a' * 20 + '.json')).write_text(json.dumps(cp), encoding='utf-8')
            # An unrelated stale case must never be scanned.
            (p / 'cases' / 'stale.json').write_text('{broken', encoding='utf-8')
            index = [{'case_id': cp['case_id'], 'group_id': cp['group_id'], 'split': 'train',
                      'task': 'agent_practical', 'sha256': digest({'messages': cp['records'][0]['messages']})}]
            (p / 'accepted_records.json').write_text(json.dumps(index), encoding='utf-8')
            manifest = {'version': VERSION, 'settings_sha256': 'settings', 'accepted_index_sha256': digest(index),
                        'counts': {'accepted_total': 1}}
            (p / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            _, rows = merge.load_accepted_records(p)
            self.assertEqual(len(rows), 1)

    def test_replan_does_not_claim_measured_ability(self):
        _, pair = merge.build_task7_replan_or_refusal(checkpoint()['records'][0]['messages'], 2)
        self.assertIn('확인되지 않았습니다', pair['chosen'])
        self.assertNotIn('기초 개념은 확보', pair['chosen'])

    def test_generic_derived_refusal_is_not_duplicated_across_splits(self):
        with TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'source'; (source / 'cases').mkdir(parents=True)
            index = []
            for i, split in ((1, 'train'), (2, 'train'), (3, 'validation')):
                cp = checkpoint(); cp['case_id'] = f'{i:020x}'; cp['group_id'] = f'domain-{i}'; cp['split'] = split
                output = roadmap(); output['strategy_title'] += str(i)
                cp['records'][0]['messages'][-1]['content'] = json.dumps(output, ensure_ascii=False)
                cp['records_sha256'] = digest(cp['records'])
                (source / 'cases' / (cp['case_id'] + '.json')).write_text(json.dumps(cp), encoding='utf-8')
                index.append({'case_id': cp['case_id'], 'group_id': cp['group_id'], 'split': split,
                              'task': 'agent_practical', 'sha256': digest({'messages': cp['records'][0]['messages']})})
            manifest = {'version': VERSION, 'settings_sha256': 'settings', 'source_sha256': 'db',
                        'settings': {'as_of': date.today().isoformat()}, 'accepted_index_sha256': digest(index),
                        'counts': {'accepted_total': 3}}
            (source / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            (source / 'accepted_records.json').write_text(json.dumps(index), encoding='utf-8')
            prefix = root / 'merged'
            with patch.object(merge, 'connect', return_value=MagicMock()), \
                 patch.object(merge, 'current_source_fingerprint', return_value='db'), \
                 patch('sys.argv', ['merge', '--input', str(source), '--output-prefix', str(prefix)]):
                self.assertEqual(merge.main(), 0)
            report = json.loads((root / 'merged_report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['derived_duplicates']['cross_split_removed'], 1)
            rows = lambda name: {digest(json.loads(s)) for s in (root / name).read_text(encoding='utf-8').splitlines()}
            self.assertFalse(rows('merged_train.jsonl') & rows('merged_validation.jsonl'))

    def test_current_eligibility_blocks_retired_resource(self):
        with self.assertRaisesRegex(ValueError, 'NO_LONGER_ELIGIBLE'):
            validate_current_context(context(), {'usable': set(), 'resources': {}, 'approved': {}})

    def test_runtime_export_uses_original_snapshot_not_active_prompt(self):
        pipe = DatasetPipeline()
        snapshot = {'system': '생성 당시 프롬프트', 'user': '사용자 원본 입력', 'target': roadmap(), 'context': context()}
        with TemporaryDirectory() as temp, patch.object(pipe, '_runtime_groups', return_value=[('sid', snapshot, [])]):
            path = Path(temp) / 'sft.jsonl'
            self.assertEqual(pipe.export_sft_jsonl(path), 1)
            row = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(row['messages'][0]['content'], '생성 당시 프롬프트')


if __name__ == '__main__':
    unittest.main()
