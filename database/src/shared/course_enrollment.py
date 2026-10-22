"""Enrollment periods only. Learning/study dates are intentionally not used."""
from datetime import datetime, timezone

PERIOD_FIELDS=('enrollment_start','enrollment_end','enrollment_period_type')

def enrollment_fields(source, raw):
    from src.shared.catalog_eligibility import timestamp
    raw=raw if isinstance(raw,dict) else {}
    start=timestamp(raw.get('enrollment_start'));end=timestamp(raw.get('enrollment_end'))
    invalid_order=start is not None and end is not None and start>end
    if invalid_order:start=end=None
    absent=not raw.get('enrollment_start') and not raw.get('enrollment_end')
    policy=('unrestricted' if source=='API_MS_LEARN' and absent else
            'scheduled' if start is not None and end is not None else 'unknown')
    return {'enrollment_start':start.isoformat() if start else None,
            'enrollment_end':end.isoformat() if end else None,'enrollment_period_type':policy}

def enrollment_status(fields, *, now=None):
    from src.shared.catalog_eligibility import timestamp
    now=now or datetime.now(timezone.utc)
    if fields.get('enrollment_period_type')=='unrestricted':return 'ongoing'
    if fields.get('enrollment_period_type')!='scheduled':return None
    start=timestamp(fields.get('enrollment_start'));end=timestamp(fields.get('enrollment_end'))
    if not start or not end or start>end:return None
    return 'upcoming' if now<start else 'ongoing' if now<=end else 'ended'

def enrollment_reason(source, raw, *, fields=None, now=None):
    from src.shared.catalog_eligibility import timestamp
    expected=enrollment_fields(source,raw)
    if fields and 'enrollment_period_type' in fields:
        if fields['enrollment_period_type']!=expected['enrollment_period_type']:
            return 'enrollment_period_mismatch'
        for key in ('enrollment_start','enrollment_end'):
            if timestamp(fields.get(key))!=timestamp(expected[key]):return 'enrollment_period_mismatch'
    if source=='API_KMOOC' and raw.get('public_yn')!='Y':return 'course_not_confirmed_open'
    return None if enrollment_status(expected,now=now)=='ongoing' else 'course_not_confirmed_open'
