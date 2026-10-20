"""Offline selection draft: full local checks plus ten explicitly recorded samples.

This does not create a training release or fabricate per-record semantic scores.
Run: python -m src.finetuning.sampled_selection --samples PATH
"""
import argparse
from collections import Counter, defaultdict
import json

from src.finetuning import curate_dataset as cli
from src.finetuning.curation_core import (
    SPLITS, TASKS, LexicalDuplicateIndex, answer_key, quality_findings, validate_candidate,
)

POLICY_VERSION = 'local-full-sample10/v1'


def template_holds(row):
    """Narrow reproducible patterns observed in the ten samples, not a semantic judge."""
    answer = json.loads(row['messages'][-1]['content'])
    if row['task'] == 'progress_checkin':
        text = answer.get('action_plan', '')
        if isinstance(text,str) and text.endswith('의 남은 실습과 이번 주 가용 시간을 확인한 뒤 1주 순연하는 보완 계획을 협의합니다.'):
            return ['GENERIC_PROGRESS_TEMPLATE_NO_DELIVERABLE_OR_CHECK']
    if row['task'] == 'generate_survey':
        text = json.dumps(answer, ensure_ascii=False)
        if any(p in text for p in (
            '동작 검증 기준 수립과 오류 원인 진단',
            '장애 격리, 예외 처리 및 안전한 복구 절차',
        )):
            return ['SURVEY_KNOWN_MULTI_CONCEPT_TEMPLATE']
    if row['task'] == 'evidence_boundary':
        request = json.loads(row['messages'][1]['content'])
        query = str(request.get('task_data', {}).get('user_query', ''))
        if (answer.get('next_step') == '학습 계획과 관련한 확인 항목을 정리하고, 인사·급여·지원 결정은 공식 담당 창구에 확인하세요.'
                and not any(w in query for w in ('인사', '급여', '지원', '수당', '평가', '승진'))):
            return ['BOUNDARY_UNRELATED_HR_TEMPLATE']
    return []


def priority(row, sample_pass):
    # Textual indicators only; these are NOT model grades or semantic approval.
    text = row['messages'][-1]['content']
    indicators = sum(w in text for w in ('산출물', '리포트', '테스트', '완료', '검증', '기준'))
    return (row['id'] not in sample_pass, -indicators, cli.digest(row['id']))


def allocate(eligible, sample_pass=()):
    """Reserve missing task minima before filling the remaining split capacity."""
    minimum = {s: 60 * n // 1500 for s, n in SPLITS.items()}
    capacity = Counter((r['split'], r['task']) for r in eligible)
    missing = {s: {t: max(0, minimum[s] - capacity[s, t]) for t in TASKS} for s in SPLITS}
    limits = {s: SPLITS[s] - sum(missing[s].values()) for s in SPLITS}
    selected = []; counts = Counter(); picked = set(); family_counts = Counter()
    ranked = sorted(eligible, key=lambda r: priority(r, set(sample_pass)))

    def take(r):
        selected.append(r); picked.add(r['id'])
        counts[r['split'], r['task']] += 1
        family_counts[r['split'], r['family_id']] += 1

    for s in SPLITS:
        for t in TASKS:
            for r in ranked:
                if r['split'] == s and r['task'] == t and counts[s, t] < minimum[s]:
                    take(r)
        while sum(counts[s, t] for t in TASKS) < limits[s]:
            remaining = [r for r in ranked if r['split'] == s and r['id'] not in picked]
            if not remaining:
                break
            # Preserve project-family variety before lexical priority, with deterministic ties.
            r = min(remaining, key=lambda r: (family_counts[s, r['family_id']], priority(r, set(sample_pass))))
            take(r)
    return selected, missing


def build_draft(candidates, samples, trial, blocked_inputs=()):
    by_id = {r['id']: r for r in candidates}
    entries = samples['records']
    if len(entries) != 10 or len({r['candidate_id'] for r in entries}) != 10:
        raise ValueError('EXACTLY_TEN_DISTINCT_SAMPLES_REQUIRED')
    if samples.get('policy') != POLICY_VERSION:
        raise ValueError('SAMPLE_POLICY_MISMATCH')
    for entry in entries:
        c = by_id.get(entry['candidate_id'])
        if (c is None or entry['messages_sha256'] != cli.digest(c['messages'])
                or entry['decision'] not in ('retain', 'hold') or not entry.get('reason')):
            raise ValueError('SAMPLE_BINDING_OR_DECISION_INVALID')
    sample_pass = {r['candidate_id'] for r in entries if r['decision'] == 'retain'}
    sample_hold = {r['candidate_id'] for r in entries if r['decision'] == 'hold'}
    family_splits = defaultdict(set)
    for c in candidates:
        family_splits[c['family_id']].add(c['split'])
    eligible = []; decisions = []; inputs = set(blocked_inputs); answers = set()
    near = LexicalDuplicateIndex()
    for row in sorted(candidates, key=lambda r: priority(r, sample_pass)):
        reasons = list(row.get('errors') or [])
        if row.get('selection_block_reason'): reasons.append(row['selection_block_reason'])
        if row['id'] in sample_hold: reasons.append('REPRESENTATIVE_CONTENT_REVIEW_HOLD')
        if row['id'] in trial and not trial[row['id']]['provisional_pass']:
            reasons.append('TRIAL_UNRESOLVED_OR_FAILED')
        if len(family_splits[row['family_id']]) != 1: reasons.append('CROSS_SPLIT_FAMILY')
        try:
            validate_candidate(row)
            reasons.extend(x['code'] for x in quality_findings(row))
            reasons.extend(template_holds(row))
        except (ValueError, KeyError, TypeError):
            reasons.append('LOCAL_VALIDATION_FAILED')
        ik = cli.digest(row['messages'][:-1]); ak = answer_key(row)
        if ik in inputs: reasons.append('DUPLICATE_OR_RESERVED_INPUT')
        if ak in answers: reasons.append('DUPLICATE_ANSWER')
        signature = near.signature(row)
        if signature and near.match(row['task'], signature): reasons.append('LEXICAL_NEAR_DUPLICATE')
        if not reasons:
            eligible.append(row); inputs.add(ik); answers.add(ak); near.add(row, signature)
        decisions.append({'candidate_id': row['id'], 'task': row['task'], 'split': row['split'],
                          'reasons': sorted(set(reasons)), 'status': 'HOLD' if reasons else 'ELIGIBLE_LOCAL_ONLY'})
    selected, missing = allocate(eligible, sample_pass)
    picked = {r['id'] for r in selected}
    for d in decisions:
        if d['status'] != 'HOLD':
            d['status'] = 'SELECTED_DRAFT' if d['candidate_id'] in picked else 'RESERVE_LOWER_PRIORITY'
    report = {'policy': POLICY_VERSION, 'status': 'DRAFT_SUPPLEMENT_REQUIRED', 'target': 1500,
              'input_count': len(candidates), 'eligible_count': len(eligible), 'selected_count': len(selected),
              'task_counts': dict(Counter(r['task'] for r in selected)),
              'split_counts': dict(Counter(r['split'] for r in selected)),
              'minimum_shortfalls': missing,
              'supplement_by_split': {s: SPLITS[s] - sum(r['split'] == s for r in selected) for s in SPLITS},
              'hold_reasons': dict(Counter(x for d in decisions for x in d['reasons'])),
              'sample_count': 10, 'sample_retained': len(sample_pass), 'sample_held': len(sample_hold),
              'human_review_completed': False, 'per_record_semantic_review_completed': False,
              'training_approved': False, 'api_called': False, 'database_changes': False,
              'priority_basis': 'sample retention, capped lexical indicators, project-family variety; not semantic scores',
              'limitations': ['Ten purposive samples do not estimate population accuracy.',
                              'Local checks and narrow template rules cannot establish relevance or absence of hallucinations.',
                              'Selected draft is not a final release; missing types and split quotas remain.']}
    return selected, decisions, report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work-dir', default=cli.DEFAULT_WORK)
    p.add_argument('--ontology', default='config/finetuning_ontology.yaml')
    p.add_argument('--samples', required=True)
    args = p.parse_args(); args.minimum_per_task = None; args.model = 'gpt-5-mini'
    work, manifest, _, pool, _, _ = cli.load_run(args)
    for name, expected in manifest['source_file_hashes'].items():
        if cli.file_hash(cli.resolve(manifest['source']) / name) != expected:
            raise ValueError('HISTORICAL_SOURCE_CHANGED')
    samples = json.loads(cli.resolve(args.samples).read_text(encoding='utf-8'))
    if samples['source_fingerprint'] != manifest['source_fingerprint']:
        raise ValueError('SAMPLE_DATABASE_MISMATCH')
    trial = {r['candidate_id']: r for r in json.loads((work/'trial_summary.json').read_text(encoding='utf-8'))['records']}
    benchmark = cli.PROJECT_ROOT.parent/'qwen_factory/data/eval/prompts.app_v1.jsonl'
    if not benchmark.exists(): raise ValueError('COMMON_BENCHMARK_MISSING')
    blocked = {cli.digest(r['messages']) for r in cli.read_jsonl(benchmark)}
    # Repaired variants require their own explicit adoption decision, not implicit replacement.
    pool = [r for r in pool if r.get('origin') in ('existing', 'supplement')]
    selected, decisions, report = build_draft(pool, samples, trial, blocked)
    report.update(source_fingerprint=manifest['source_fingerprint'],
                  sample_manifest_sha256=cli.file_hash(cli.resolve(args.samples)),
                  benchmark_sha256=cli.file_hash(benchmark))
    cli.write_jsonl(work/'local_selected_candidates.jsonl', selected)
    cli.write_jsonl(work/'local_selection_decisions.jsonl', decisions)
    cli.write_json(work/'composition_plan.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
