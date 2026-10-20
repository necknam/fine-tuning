"""Export reviewed runtime selections without copying them into legacy tables."""
from collections import Counter
from copy import deepcopy
import json
import logging
from pathlib import Path

from src.shared.dataset_integrity import (VERSION, digest, validate_roadmap,
                                         current_evidence, validate_current_context)
from src.shared.pii_masking import pii_masker
from src.database.db_client import db_client

logger = logging.getLogger('DATASET_PIPELINE')


class DatasetPipeline:
    def __init__(self):
        self.db = db_client
        self.masker = pii_masker
        self.last_report = {}

    def _runtime_groups(self, user_type='REAL_USER', request_id=None):
        if user_type not in (None, 'REAL_USER', 'TEST_MANUAL', 'TEST_AUTO'):
            raise ValueError('INVALID_USER_TYPE')
        groups, skipped = [], Counter()
        with self.db.transaction() as conn:
            if getattr(self.db, '_connection', None) is None:
                conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            selections = conn.execute('''SELECT s.session_id,s.generation_id,u.source_type
                FROM public.roadmap_selections s JOIN public.roadmap_sessions r USING(session_id)
                JOIN public.users u ON u.user_id=r.user_id
                WHERE (%s::text IS NULL OR u.source_type=%s)
                  AND (%s::uuid IS NULL OR s.session_id=%s::uuid)
                ORDER BY s.session_id''', (user_type, user_type, request_id, request_id)).fetchall()
            current = current_evidence(conn)
            for selection in selections:
                rows = conn.execute('''SELECT generation_id,roadmap_content FROM public.roadmap_generations
                    WHERE session_id=%s ORDER BY generation_order''', (selection['session_id'],)).fetchall()
                valid = {}
                for row in rows:
                    try:
                        content = row['roadmap_content']
                        snapshot = deepcopy(content.get('training_snapshot') or {})
                        claimed = snapshot.pop('sha256', None)
                        if snapshot.get('version') != VERSION or claimed != digest(snapshot):
                            raise ValueError('MISSING_OR_OLD_GENERATION_SNAPSHOT')
                        actual = {k: v for k, v in content.items()
                                  if k not in ('training_snapshot', 'resource_grounding', 'regulation_grounding', 'assessment_input')}
                        if digest(actual) != digest(snapshot['target']):
                            raise ValueError('GENERATION_CHANGED_SINCE_CAPTURE')
                        if not all(isinstance(snapshot.get(k), str) and snapshot[k].strip() for k in ('system', 'user')):
                            raise ValueError('MISSING_ORIGINAL_PROMPT')
                        validate_roadmap(snapshot['target'], snapshot['context'])
                        validate_current_context(snapshot['context'], current)
                        valid[str(row['generation_id'])] = snapshot
                    except (ValueError, KeyError, TypeError) as exc:
                        skipped[str(exc) if isinstance(exc, ValueError) else 'INVALID_SNAPSHOT'] += 1
                chosen = valid.get(str(selection['generation_id']))
                if chosen:
                    groups.append((selection['session_id'], chosen,
                                   [v for k, v in valid.items() if k != str(selection['generation_id'])]))
                else:
                    skipped['SELECTED_GENERATION_NOT_EXPORTABLE'] += 1
        self.last_report = {'source': 'roadmap_selections', 'version': VERSION,
                            'selected_groups': len(groups), 'excluded': dict(skipped),
                            'legacy_logs_preserved': True}
        return groups

    def _messages(self, snapshot, mask_pii):
        messages = [{'role': 'system', 'content': snapshot['system']},
                    {'role': 'user', 'content': snapshot['user']},
                    {'role': 'assistant', 'content': json.dumps(snapshot['target'], ensure_ascii=False)}]
        if not mask_pii:
            return messages
        # Protect exact DB IDs (including ISBNs) from broad numeric PII regexes.
        protected = set()
        def collect(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if (key.endswith('_id') or key == 'isbn') and isinstance(item, str) and len(item) >= 6:
                        protected.add(item)
                    collect(item)
            elif isinstance(value, list):
                for item in value: collect(item)
        collect(snapshot['context'])
        tokens = {value: '__DB_ID_' + digest(value) + '__' for value in protected}
        for message in messages:
            text = message['content']
            for value, token in sorted(tokens.items(), key=lambda p: -len(p[0])):
                text = text.replace(value, token)
            text = self.masker.mask_text(text)
            for value, token in tokens.items(): text = text.replace(token, value)
            message['content'] = text
        # Masking must never corrupt an output ID or its JSON representation.
        validate_roadmap(json.loads(messages[-1]['content']), snapshot['context'])
        return messages

    def build_preference_pairs(self, request_id=None, user_type='REAL_USER', mask_pii=True):
        """Return pairs in memory. Current runtime tables are the source of truth."""
        pairs = []
        for sid, chosen, alternatives in self._runtime_groups(user_type, request_id):
            good = self._messages(chosen, mask_pii)
            for alternative in alternatives:
                # Different strategies use distinct system instructions. Only user input is
                # shared; expose the DPO comparison as explicit strategy alternatives.
                if digest(chosen['context']) != digest(alternative['context']) or chosen['user'] != alternative['user']:
                    continue
                bad = self._messages(alternative, mask_pii)
                if good[-1]['content'] == bad[-1]['content']:
                    continue
                prompt = json.dumps({'user_request': good[1]['content'],
                                     'comparison': '사용자가 선호한 로드맵 대안을 선택합니다.',
                                     'resource_and_regulation_rules': '검색된 자원과 승인 규정만 사용합니다.'}, ensure_ascii=False)
                pairs.append({'prompt': prompt, 'chosen': good[-1]['content'], 'rejected': bad[-1]['content']})
        self.last_report['preference_pairs'] = len(pairs)
        return pairs

    def _write(self, output_path, rows, dataset_type, mask_pii, user_type):
        target = Path(output_path).resolve()
        if target.exists():
            raise ValueError('OUTPUT_EXISTS_USE_NEW_FILENAME')
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + '.tmp')
        temporary.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
        temporary.replace(target)
        self.last_report.update(records=len(rows), dataset_type=dataset_type, mask_pii=mask_pii,
                                user_type=user_type, database_changes=False)
        target.with_suffix(target.suffix + '.report.json').write_text(
            json.dumps(self.last_report, ensure_ascii=False, indent=2), encoding='utf-8')
        return len(rows)

    def export_sft_jsonl(self, output_path, user_type='REAL_USER', mask_pii=True):
        rows = [{'messages': self._messages(chosen, mask_pii)}
                for _, chosen, _ in self._runtime_groups(user_type)]
        return self._write(output_path, rows, 'SFT_JSONL', mask_pii, user_type)

    def export_dpo_jsonl(self, output_path, user_type='REAL_USER', mask_pii=True):
        rows = self.build_preference_pairs(user_type=user_type, mask_pii=mask_pii)
        return self._write(output_path, rows, 'DPO_JSONL', mask_pii, user_type)


dataset_pipeline = DatasetPipeline()
