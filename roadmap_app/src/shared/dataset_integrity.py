"""Shared fail-closed boundaries for generated and selected training records."""
from copy import deepcopy
from datetime import date
import hashlib
import json
import re

from src.shared.resource_grounding import attach_resource_evidence

VERSION = 'grounded-sft/v8-reviewed-evidence'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    default=str).encode('utf-8')).hexdigest()


def is_approved(chunk, as_of=None):
    if (chunk.get('search_status') != 'active' or chunk.get('review_status') != 'approved'
            or chunk.get('availability_status') != 'available' or chunk.get('requires_review') is not False):
        return False
    try:
        day = date.fromisoformat(str(as_of)) if as_of else date.today()
        start = date.fromisoformat(str(chunk['effective_from']))
        end = date.fromisoformat(str(chunk['effective_to'])) if chunk.get('effective_to') else None
        return start <= day and (end is None or day < end)
    except (ValueError, KeyError, TypeError):
        return False


def validate_roadmap(output, context):
    if not isinstance(output, dict) or not isinstance(context, dict):
        raise ValueError('INVALID_ROADMAP_CONTEXT')
    reg = context.get('regulation_rag', {})
    approved = reg.get('approved', [])
    if any(not is_approved(c, reg.get('as_of')) for c in approved):
        raise ValueError('UNAPPROVED_EVIDENCE_IN_APPROVED_POOL')
    ids = {c['rag_chunk_id'] for c in approved}
    citations = output.get('regulation_citations')
    if not isinstance(citations, list) or any(not isinstance(c, str) or c not in ids for c in citations):
        raise ValueError('UNSUPPORTED_REGULATION_CITATION')
    summary = output.get('regulation_summary')
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError('MISSING_REGULATION_SUMMARY')
    if not ids and (citations or summary != '규정 확인 필요'):
        raise ValueError('UNAPPROVED_REGULATION_ASSERTION')
    for milestone in output.get('milestones', []):
        for field in ('recommended_courses', 'recommended_books', 'recommended_certifications'):
            if field not in milestone:
                raise ValueError('MISSING_RESOURCE_ARRAY')
    milestones = output.get('milestones', [])
    if isinstance(milestones,list) and milestones and all(isinstance(m,dict) for m in milestones):
        weeks = [re.fullmatch(r'(\d+)\s*주', str(m.get('duration') or '')) for m in milestones]
        total = output.get('total_duration_weeks')
        if all(weeks) and type(total) is int and sum(int(w.group(1)) for w in weeks) != total:
            raise ValueError('ROADMAP_DURATION_TOTAL_MISMATCH')
    # Validate a copy: never repair IDs, recommendations, citations or duration.
    attach_resource_evidence(deepcopy(output), context)


def validate_record(record):
    messages = record.get('messages')
    if not isinstance(messages, list) or [m.get('role') for m in messages] != ['system', 'user', 'assistant']:
        raise ValueError('INVALID_MESSAGES')
    if any(not isinstance(m.get('content'), str) or not m['content'].strip() for m in messages):
        raise ValueError('EMPTY_MESSAGE')
    task = record.get('task')
    output = json.loads(messages[2]['content'])
    if task in ('agent_practical', 'agent_certified', 'agent_fasttrack'):
        payload = json.loads(messages[1]['content'])
        validate_roadmap(output, payload['retrieved_context'])
    elif task == 'assessment_survey_gen':
        payload = json.loads(messages[1]['content'])
        slots = payload['slots']
        if not isinstance(output, list) or len(output) != len(slots):
            raise ValueError('SURVEY_SLOT_COUNT')
        for row, slot in zip(output, slots):
            if row.get('question','').count('?') != 1:
                raise ValueError('SURVEY_SINGLE_QUESTION_REQUIRED')
            if (row.get('skill_id') != slot['skill_id'] or row.get('sequence_no') != slot['sequence_no']
                    or slot['skill'] not in row.get('question', '')):
                raise ValueError('SURVEY_SKILL_OR_SEQUENCE_MISMATCH')
    elif task == 'assessment_plan_refine':
        if not isinstance(output, dict) or not output.get('refined_plan') or not output.get('project_goal'):
            raise ValueError('INVALID_REFINED_PLAN')
    else:
        raise ValueError('UNKNOWN_TRAINING_TASK')


def validate_checkpoint(checkpoint, settings_hash, case_id=None):
    if (checkpoint.get('generator_version') != VERSION or checkpoint.get('settings_sha256') != settings_hash
            or (case_id is not None and checkpoint.get('case_id') != case_id)):
        raise ValueError('CHECKPOINT_VERSION_OR_SETTINGS_MISMATCH_USE_NEW_DIRECTORY')
    if checkpoint.get('split') not in ('train', 'validation') or not checkpoint.get('group_id'):
        raise ValueError('INVALID_CHECKPOINT_SPLIT')
    records = checkpoint.get('records')
    if not isinstance(records, list) or not records:
        raise ValueError('EMPTY_CHECKPOINT')
    if checkpoint.get('records_sha256') != digest(records):
        raise ValueError('CHECKPOINT_CONTENT_HASH_MISMATCH')
    contexts = [json.loads(r['messages'][1]['content'])['retrieved_context'] for r in records
                if r.get('task', '').startswith('agent_')]
    if checkpoint.get('retrieval_sha256') != digest(contexts):
        raise ValueError('CHECKPOINT_RETRIEVAL_HASH_MISMATCH')
    for record in records:
        validate_record(record)


def current_evidence(conn):
    """Read catalog facts and approved regulation IDs; never call embeddings/LLMs."""
    from src.shared.catalog_eligibility import eligible_keys
    usable, _ = eligible_keys(conn)
    resources = {}
    for kind, pk in (('courses', 'course_id'), ('books', 'isbn'), ('certifications', 'cert_id')):
        rows = conn.execute(f"SELECT to_jsonb(t)-'embedding' AS data FROM public.{kind} t").fetchall()
        resources[kind] = {str(r['data'][pk]): r['data'] for r in rows}
    rows = conn.execute('''SELECT c.rag_chunk_id,c.chunk_text,c.search_status,v.review_status,
        v.availability_status,v.effective_from,v.effective_to,false AS requires_review
        FROM hr_regulation_pilot.rag_chunk c JOIN hr_regulation_pilot.regulation_version v
          ON v.regulation_version_id=c.regulation_version_id
        WHERE c.search_status='active' AND v.review_status='approved' AND v.availability_status='available'
          AND EXISTS (SELECT 1 FROM hr_regulation_pilot.rag_chunk_source s WHERE s.rag_chunk_id=c.rag_chunk_id)
          AND NOT EXISTS (SELECT 1 FROM hr_regulation_pilot.rag_chunk_source s
            JOIN hr_regulation_pilot.regulation_node n ON n.regulation_node_id=s.regulation_node_id
            WHERE s.rag_chunk_id=c.rag_chunk_id AND s.source_role='primary' AND
              (n.effective_from_override>current_date OR n.effective_to_override<=current_date))''').fetchall()
    return {'usable': {(k, str(i)) for k, i in usable}, 'resources': resources,
            'approved': {r['rag_chunk_id']: r for r in rows if is_approved(r)}}


def validate_current_context(context, snapshot):
    for kind, pk in (('courses', 'course_id'), ('books', 'isbn'), ('certifications', 'cert_id')):
        for row in context.get(kind, []):
            key = str(row[pk])
            if (kind, key) not in snapshot['usable']:
                raise ValueError('RESOURCE_NO_LONGER_ELIGIBLE')
            current = snapshot['resources'][kind][key]
            for field in ('title', 'org_name', 'url', 'author', 'publisher', 'provider'):
                if field in row and row[field] != current.get(field):
                    raise ValueError('RESOURCE_FACT_CHANGED')
    for chunk in context.get('regulation_rag', {}).get('approved', []):
        current = snapshot['approved'].get(chunk.get('rag_chunk_id'))
        if current is None or chunk.get('chunk_text') != current['chunk_text']:
            raise ValueError('REGULATION_NO_LONGER_APPROVED_OR_CHANGED')
