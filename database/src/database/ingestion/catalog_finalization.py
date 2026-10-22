"""Automatic finalization of official-source catalogs. No schema or review-history changes."""
from src.shared.catalog_eligibility import eligible_keys
from src.shared.catalog_scope import scoped_matches
from src.shared.skill_matching import SkillMatcher
from src.database.vectors import resource_vectors
from src.database.ingestion.catalog_details import copy_api_description

TABLES={'courses':('course_id','course_skills'),'books':('isbn','book_skills'),
        'certifications':('cert_id','certification_skills'),'jobs':('job_id','job_skills'),
        'majors':('major_id','major_skills')}

def finalize_catalog(conn, *, embed=True, embedding_client=None):
    """Run inside the ingestion transaction: normalize, exclude, embed, assert invariants."""
    matcher=SkillMatcher(conn.execute('SELECT skill_id,name,category FROM public.skill_tags ORDER BY skill_id').fetchall())
    copied=0;excluded=0
    for kind,(pk,_) in TABLES.items():
        if kind=='courses':continue
        rows=conn.execute(f"SELECT to_jsonb(t)-'embedding' fields FROM public.{kind} t WHERE content_status='ready'").fetchall()
        for wrap in rows:
            fields=wrap['fields']
            # Reuse existing official subject/curriculum text only; never generate an introduction.
            if not conn.execute('SELECT 1 AS present FROM growpath_meta.catalog_api_sources WHERE resource_type=%s AND entity_key=%s LIMIT 1',
                                (kind,str(fields[pk]))).fetchone():continue
            if not fields.get('description'):
                copy_api_description(kind,fields)
                if fields.get('description'):
                    conn.execute(f'UPDATE public.{kind} SET description=%s WHERE {pk}=%s',(fields['description'],fields[pk]));copied+=1
    allowed,_=eligible_keys(conn)
    for kind,(pk,mapping) in TABLES.items():
        rows=conn.execute(f"SELECT to_jsonb(t)-'embedding' fields FROM public.{kind} t").fetchall()
        for wrap in rows:
            fields=wrap['fields'];rid=fields[pk];key=(kind,str(rid))
            links={r['skill_id'] for r in conn.execute(f'SELECT skill_id FROM public.{mapping} WHERE {pk}=%s',(rid,)).fetchall()}
            supported=set(scoped_matches(matcher,fields))
            unsupported=links-supported
            for sid in unsupported:
                conn.execute(f'DELETE FROM public.{mapping} WHERE {pk}=%s AND skill_id=%s',(rid,sid))
            desc=fields.get('syllabus_summary' if kind=='courses' else 'description')
            usable=key in allowed and bool(links & supported) and bool(str(desc or '').strip())
            if not usable:
                conn.execute(f'DELETE FROM public.{mapping} WHERE {pk}=%s',(rid,))
                conn.execute('DELETE FROM public.learning_resource_embeddings WHERE resource_type=%s AND resource_id=%s',(kind,str(rid)))
                if fields.get('content_status')=='ready':
                    conn.execute(f"UPDATE public.{kind} SET content_status='scope_excluded' WHERE {pk}=%s",(rid,));excluded+=1
    from src.database.catalog_reset import delete_catalog_rows
    deleted=delete_catalog_rows(conn,excluded_only=True)
    result=resource_vectors.embed(conn,client=embedding_client) if embed else resource_vectors.status(conn)
    allowed,_=eligible_keys(conn);counts={};link_count=0
    for kind,(pk,mapping) in TABLES.items():
        rows=conn.execute(f"SELECT to_jsonb(t)-'embedding' fields FROM public.{kind} t WHERE content_status='ready'").fetchall()
        ready=set()
        for wrap in rows:
            fields=wrap['fields'];key=(kind,str(fields[pk]));ready.add(key)
            if key not in allowed:raise ValueError('적재 최종 검사 실패: 추천 범위 밖 자료')
            if not str(fields.get('syllabus_summary' if kind=='courses' else 'description') or '').strip():
                raise ValueError('적재 최종 검사 실패: API 설명 누락')
            links={r['skill_id'] for r in conn.execute(f'SELECT skill_id FROM public.{mapping} WHERE {pk}=%s',(fields[pk],)).fetchall()}
            if not links or not links<=set(scoped_matches(matcher,fields)):
                raise ValueError('적재 최종 검사 실패: 스킬 연결')
            link_count+=len(links)
        if ready!={key for key in allowed if key[0]==kind}:raise ValueError('적재 최종 검사 실패: 상태 불일치')
        counts[kind]=len(ready)
    if embed:
        if any(r['missing_or_stale_vectors'] for r in result['resources'].values()) or result['orphan_vectors_ignored']:
            raise ValueError('적재 최종 검사 실패: 누락·오래된 벡터')
    return result,{'passed':True,'catalogs':counts,'skill_links':link_count,'api_descriptions_copied':copied,
                   'unusable_rows_excluded':excluded,'removed_rows':deleted,'vectors_verified':embed}
