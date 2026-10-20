"""Validate a v8 source run and its final accepted messages against current DB."""
import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.shared.dataset_integrity import VERSION, digest, current_evidence, validate_current_context
from src.finetuning.merge_finetuning_dataset import load_accepted_records
from src.finetuning.export_finetuning_dataset import current_source_fingerprint
from src.database.deployment import connect


def validate(source):
    manifest, records = load_accepted_records(source)
    if manifest.get('settings', {}).get('as_of') != date.today().isoformat():
        raise ValueError('AS_OF_CHANGED_REVALIDATE_OR_REGENERATE')
    with connect('SUPABASE_DB_URL') as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        if current_source_fingerprint(conn) != manifest.get('source_sha256'):
            raise ValueError('SOURCE_DB_CHANGED')
        current = current_evidence(conn)
        for _, record in records:
            if record['task'].startswith('agent_'):
                context = json.loads(record['messages'][1]['content'])['retrieved_context']
                validate_current_context(context, current)
    expected = {'combined_3000': [], 'train': [], 'validation': []}
    tasks = Counter()
    for entry, record in records:
        h = digest({'messages': record['messages']})
        expected['combined_3000'].append(h)
        expected[entry['split']].append(h)
        tasks[entry['task']] += 1
    for name, hashes in expected.items():
        rows = [json.loads(line) for line in (source / (name + '.jsonl')).read_text(encoding='utf-8').splitlines() if line.strip()]
        if [digest(row) for row in rows] != hashes:
            raise ValueError('FINAL_OUTPUT_DIFFERS_FROM_ACCEPTED_INDEX:' + name)
    if set(expected['train']) & set(expected['validation']):
        raise ValueError('TRAIN_VALIDATION_LEAKAGE')
    return {'status': 'PASS', 'version': VERSION, 'records': len(records), 'tasks': dict(tasks),
            'generation_status': manifest.get('status'), 'shortfall': manifest.get('shortfall'),
            'database_changes': False, 'llm_or_embedding_called': False,
            'semantic_human_review_required': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate(args.input.resolve())
    except (ValueError, KeyError, OSError, TypeError) as exc:
        print(json.dumps({'status': 'FAIL', 'reason': str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
