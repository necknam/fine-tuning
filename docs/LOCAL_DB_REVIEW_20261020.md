# 로컬 DB 사용 안내

앱은 Docker 없이 PostgreSQL 17.11 + pgvector 0.8.2를 사용한다. 앱 데이터는 로컬 growpath, 팩토리 실험 기록은 Neon에 저장한다. 전체 현황과 남은 일은 [통합 보고서](CODEX_HANDOFF.md)를 참고한다.

## 실행과 백업

최상위 project 안의 roadmap_app 폴더에서 실행한다.

```powershell
python scripts/local_db.py start
python scripts/local_db.py status
python scripts/db.py verify
python -m src.db.resource_vectors status
python -m src.db.regulation_vectors status
```

중지는 `python scripts/local_db.py stop`, 백업은 `python scripts/local_db.py backup --output 원하는경로.dump`다. 물리 파일은 `data/local_db/postgres` 전체이며 개별 파일을 삭제하거나 편집하지 않는다. 연결은 `.env.local`, 실행 파일은 그 안의 `POSTGRES_BIN_DIR` 설정을 사용한다.

## PyCharm 접속

View → Tool Windows → Database → ＋ → Data Source → PostgreSQL에서 입력한다.

| 항목 | 값 |
| --- | --- |
| Host | 127.0.0.1 |
| Port | 55433 |
| User | postgres |
| Password | roadmap_app/.env.local의 POSTGRES_PASSWORD |
| Database | **growpath** |
| SSL | 사용 안 함 |

Test Connection 후 Schemas에서 public, regulations, growpath_meta, growpath_legacy를 선택한다. SQL 콘솔도 growpath 연결을 선택해야 한다. postgres DB에서는 앱 테이블이 보이지 않는다.

```sql
SELECT current_database(), inet_server_port();
SELECT COUNT(*) FROM public.courses;
SELECT * FROM public.skill_tags ORDER BY skill_id;
```

현재 구조는 [ERD 최종](ERD_최종.html)을 참고한다. 실제 테이블은 운영 41개·관리 2개·보관 6개로 전체 49개다. 빈 과거 테이블 ai_cases·regulations·employee_skill_gaps는 008 마이그레이션에서 제거했다. 원본 자료의 중복 embedding 컬럼은 제거했으며, 검색 벡터는 public.learning_resource_embeddings와 regulations.rag_chunk_embeddings에서 관리한다. 기존 명령 호환용 뷰는 테이블 수에 포함하지 않는다.

미확정 직원 14명의 기관·부서·직급·직무는 추정해서 채우지 않았다. 직원 조회는 정식 기관·부서·직급·직무 참조를 우선 사용한다. `update_employee_assignment`로 소속을 확정하면 중복 department·grade·job_title 문자열을 비운다. 미확정 값이 남아 있어 컬럼 자체는 아직 제거하지 않는다.

로드맵 수정은 `update_roadmap_content`가 content와 단계·자료 연결을 같은 트랜잭션에서 갱신한다. 변경 없는 활동은 완료 상태를 유지하고, 제목·활동·기간이 바뀐 단계는 완료 상태를 해제한다. 최초 baseline_content는 변경하지 않는다. 진행 체크만 바꾸는 경우 코멘트에 수정 완료 표시를 하지 않는다. DB를 직접 수정하는 SQL은 이 API의 동기화를 거치지 않으므로 앱 수정 경로에서는 사용하지 않는다.

부서장은 담당 부서·하위 부서 프로젝트를 조회하고 본인 코멘트를 작성·수정·삭제할 수 있으며, 일반 직원의 로드맵이나 완료 체크를 수정할 수 없다. 직원 계정 정보를 조회하는 API는 password_hash를 반환하지 않는다.

신규 설치는 `python scripts/db.py migrate`, 구조 검증은 `python scripts/db.py verify`를 사용한다. 벡터 테이블·수집 이력 테이블도 설치 단계에 포함된다. 실제 DB 기준 메타데이터는 src/database/catalog.current.json, 이전 패키지를 읽기 위한 메타데이터는 catalog.json이다. 이전 001~008 마이그레이션 파일은 적용 후 수정하지 않는다.

스킬 36·강좌 718·도서 345·자격증 66·직무 80·전공 132건의 학습 자료 벡터 1,377개가 모두 최신이다. 규정 청크 벡터 1,410개는 별도 테이블에 유지한다. 두 벡터 테이블은 같은 검색 대상으로 무조건 혼합하지 않는다.

복구 백업과 data/local_db/postgres는 정리 대상이 아니다. ERD는 `python -m src.database.erd --template ../docs/ERD_최종.html`로 현재 DB 기준 재생성할 수 있다.

강좌·도서·자격증의 공식 이미지 URL은 각 자료 테이블의 image_url에 저장한다. 강좌 671개, 도서 345개, 자격증 59개에 URL이 있다. 이미지 없는 도서는 `python load_data.py --refresh-book-images`로 ISBN을 조회한다. URL 없는 자료는 NULL을 유지하며 이미지 확인만으로 추천 품질 등급을 올리지 않는다.
