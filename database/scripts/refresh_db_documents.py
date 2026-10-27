"""Refresh DB content while preserving existing ERD UI and report styles."""
import json,re,sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.database.deployment import connect
from src.database.final_schema import snapshot
from src.database.erd import render

ROOT=Path(__file__).resolve().parents[2]

def refresh(c,root=ROOT):
    meta=snapshot(c)
    counts={t:c.execute('SELECT count(*) AS n FROM '+t).fetchone()['n'] for t in meta}
    day=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    results=[]
    for path in (root/'docs/ERD_최종.html',root/'database/docs/ERD_최종.html'):
        old=path.read_text(encoding='utf-8')
        # render() replaces only the const D JSON slot, preserving CSS and JS.
        result=render(c,path,path)
        new=path.read_text(encoding='utf-8')
        style=lambda s:re.findall(r'<style\b[^>]*>.*?</style>',s,re.S)
        if style(old)!=style(new):raise ValueError('ERD style changed unexpectedly')
        results.append(result)
    path=root/'docs/DATABASE.md'
    source=path.read_text(encoding='utf-8')
    start=source.index('## 각 테이블의 현재 구조')
    end=source.index('## 실제 적재·활용 점검',start)
    rows=['## 각 테이블의 현재 구조','',f'{day} 실제 로컬 DB 조회 기준. 호환 뷰는 테이블 목록에 포함하지 않는다.','']
    for table,spec in meta.items():
        rows.extend([f'### `{table}` · {counts[table]}행',''])
        pk=next((x['definition'] for x in spec['constraints'] if x['type']=='p'),'없음')
        rows.extend(['기본키: '+pk,'','| 컬럼 | 자료형 | NULL 허용 |','| --- | --- | --- |'])
        rows.extend(f"| `{col['column']}` | {col['type']} | {'NO' if col['not_null'] else 'YES'} |" for col in spec['columns'])
        rows.append('')
        if spec['fks']:
            rows.extend(['참조 관계:','']+[f"- `{fk['definition']}`" for fk in spec['fks']]+[''])
        checks=[x['definition'] for x in spec['constraints'] if x['type']=='c']
        if checks:rows.extend(['검증 조건:','']+[f'- `{x}`' for x in checks]+[''])
    source=source[:start]+'\n'.join(rows)+'\n'+source[end:]
    n=lambda name:counts['public.'+name]
    resource=c.execute('SELECT count(*) AS n FROM public.learning_resource_embeddings').fetchone()['n']
    regs=counts['regulations.rag_chunk_embeddings']
    total=len(meta); fk=sum(len(x['fks']) for x in meta.values())
    summary=f"현재 로컬 DB는 실제 테이블 {total}개·FK {fk}개다. 호환 뷰는 테이블 수에 포함하지 않는다."
    source=re.sub(r'실제 테이블은 운영 .*?전체 50개다\.',summary,source,count=1)
    source=re.sub(r'스킬 36·강좌 718·도서 345·자격증 66·직무 80·전공 132건의 학습 자료 벡터 1,377개가 모두 최신이다\.',f"스킬 {n('skill_tags')}·강좌 {n('courses')}·도서 {n('books')}·자격증 {n('certifications')}·직무 {n('jobs')}·전공 {n('majors')}건, 자료 벡터 {resource}개를 실제 조회했다.",source)
    source=re.sub(r'강좌·도서·자격증의 공식 이미지 URL은.*?추천 품질 등급을 올리지 않는다\.', '강좌·도서·자격증의 이미지 URL은 각 테이블의 image_url에 저장한다. 없는 값은 NULL을 유지하며 이미지 유무로 추천 품질을 판정하지 않는다.',source,flags=re.S)
    current=f"""## 실제 적재·활용 점검

{day} 최신 로컬 DB 직접 조회: {summary} 강좌 {n('courses')}·도서 {n('books')}·자격증 {n('certifications')}·직무 {n('jobs')}·전공 {n('majors')}·스킬 {n('skill_tags')}건. 자료 벡터 {resource}개·규정 벡터 {regs}개다. 저장 건수와 추천 가능 건수·수집 완료 여부는 구분한다.

직원 {n('employees')}명은 실제 조회값이다. 부서 {n('departments')}개에는 기존 5개와 시트용 9개(상위 조직 2개 포함)가 있다. 부서 마스터 등록은 기존 직원 소속의 변경이나 시트 직원 정보의 실제 적재를 의미하지 않는다. 2급(을)·3급·4급·5급 ID는 각각 9·7·4·6이다.

016~020 마이그레이션으로 직원 날짜·설문 전 프로젝트 설명·미등재 자격 원문·학력 입학/졸업일을 추가했다. 새 날짜는 nullable DATE이며 미확인 날짜를 추정하지 않는다. 각 날짜 쌍의 종료/배치 날짜가 시작 날짜보다 빠를 수 없다.

시트의 직무·직급·부서 ID는 최신 마스터로 조회한다. 이름은 화면 표시, FK ID는 직원 저장에 사용한다. 직원별 미등재 자격은 공통 자격증 마스터와 분리한다. 날짜는 기본 달력 선택과 YYYY-MM-DD 직접 입력을 유지한다. 별도 날짜입력 탭은 사용자 요청으로 제거했다.

이번 문서는 로컬 public DB 조회 기준이다. 과거 Cloud 100명 원본은 현재 연결에서 찾지 못했으며, 승인된 시드로 로컬 TEST_MANUAL 100명을 재구성했다. 과거 Cloud 원본과 동일 복원이라고 표현하지 않는다. 실제 팀원 시트 적재는 하지 않았다. 로컬의 잘못된 시트 정보 적재는 직전 백업과 동일하게 복구했다. 위의 2026-10-21 백업·복원 수치는 과거 검증 이력이며 현재 DB 전체 백업의 검증 결과로 사용하지 않는다. 변경 이유와 상태는 [최상위 변경점 문서](../시트_DB_변경점.md)를 참고한다.
"""
    source=source[:source.index('## 실제 적재·활용 점검')]+current
    path.write_text(source,encoding='utf-8')
    # Only DB sections of the existing combined report change; theme and training sections stay intact.
    report=root/'docs/DB_데이터_파인튜닝_통합보고서.html'
    old=report.read_text(encoding='utf-8')
    db=f'<section><h2>구조와 DB</h2><p>{day} 로컬 PostgreSQL 17.11 + pgvector 0.8.2 직접 조회 기준이다. {summary} 업무 DB와 팩토리 실험 DB는 별도다.</p><p>강좌 {n("courses")}·도서 {n("books")}·자격증 {n("certifications")}·직무 {n("jobs")}·전공 {n("majors")}·스킬 {n("skill_tags")}건, 자료 벡터 {resource}개·규정 벡터 {regs}개다.</p><p>전체 컬럼·제약·FK는 DATABASE.md, 실제 구조와 건수는 ERD_최종.html을 참고한다. ERD의 테마와 인터랙션은 유지하고 DB 메타데이터만 갱신했다.</p></section>'
    latest=f'<section><h2>최신 DB 확정 상태</h2><p>{day} 로컬 DB에 001~020 마이그레이션 적용. employees에 hire_date·department_start_date·planned_project_description·unlisted_certifications, employee_education_records에 enrollment_date·graduation_date를 추가했다. 날짜는 미확인 시 NULL이고 날짜 선후 관계를 검사한다.</p><p>직원 {n("employees")}명 실측. 부서 {n("departments")}개에는 기존 5개와 시트용 9개가 있다. 기존 사용자 5명의 행은 보존하고 가상 9명의 소속·직급·프로필은 승인된 재구성 범위에서 변경했다. 선택 직급은 2급(을)~5급이며 DB ID와 급수는 구분한다. 부서·직급·상위 부서 FK를 유지했다.</p><p>직원별 업무·구상 프로젝트 설명은 설문 전 추천 입력이며 생성 질문과 분리한다. 미등재 자격은 직원 원문으로 보존한다. 시트 날짜는 기본 달력으로 선택한다. 코드·매핑·변경 이유는 최상위 시트_DB_변경점.md에 기록한다.</p><p>로컬 TEST_MANUAL 100명은 사용자 승인으로 기존 규칙을 재구성한 합성 데이터다. 기존 사용자 5명은 보존했다. 과거 Cloud 100명과 완전히 같은 원본 복원이 아니며 테스트 직원 100명의 비밀번호는 사용자 지정 공통값으로 통일하고 전원 검증했다. 시트 적재·자동 저장·백그라운드 생성은 하지 않는다. 로컬의 잘못된 시트 적재는 직전 백업으로 복구했다. 기존 백업 검증은 과거 이력이다. 학습 관련 절은 이번 DB 갱신 대상이 아니다.</p></section>'
    new=re.sub(r'<section><h2>구조와 DB</h2>.*?</section>',lambda _:db,old,count=1,flags=re.S)
    new=re.sub(r'<section><h2>최신 DB 확정 상태</h2>.*?</section>',lambda _:latest,new,count=1,flags=re.S)
    style=lambda s:re.findall(r'<style\b[^>]*>.*?</style>',s,re.S)
    if style(old)!=style(new):raise ValueError('Report style changed unexpectedly')
    report.write_text(new,encoding='utf-8')
    return {'erd':results,'tables':total,'foreign_keys':fk,'date':day}

if __name__=='__main__':
    with connect('SUPABASE_DB_URL') as c:
        c.execute('SET TRANSACTION READ ONLY')
        print(json.dumps(refresh(c),ensure_ascii=False,indent=2))
