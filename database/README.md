# PostgreSQL 관리

스키마·마이그레이션·공식 자료 수집·규정·벡터 검색·전체 백업/복원을 관리한다. 로드맵 UI·에이전트·학습 데이터 생성기는 포함하지 않는다. 업무 테이블과 DB 저장 API는 유지한다.

```powershell
python -m pip install -r requirements.txt
python scripts/local_db.py start
python scripts/db.py verify
# 미리보기: 수집·검증만 실행하며 DB에는 저장하지 않음
python load_data.py --dry-run --report data/transfer/catalog_preview.json

# 실제 적재: DB 저장 후 유료 임베딩 API로 벡터 갱신
python load_data.py --report data/transfer/catalog_refresh.json

# 실제 적재만 먼저 실행하고 임베딩 갱신은 나중에 수행
python load_data.py --skip-embeddings --report data/transfer/catalog_refresh.json
python diagnose_catalog.py --output data/transfer/api_diagnosis.json
```

진단은 .env.local이 .env보다 우선하며 로컬 DB 기본 SSL은 disable, 원격 기본 SSL은 require다. 접속 문자열의 명시된 SSL 설정을 존중한다. 진단은 적재하거나 유료 LLM·임베딩 API를 호출하지 않는다. 실제 자료 갱신은 load_data.py에서 수행한다.

[새 PC 전체 복원](../DB_복원.md) · [전체 DB 구조·테이블·PyCharm 접속](../docs/DATABASE.md) · [ERD](../docs/ERD_최종.html)

paths.yaml·rules.yaml·기존36개 스킬 태그는 유지한다. 실제 규정·강좌·도서·자격증·직무·전공 데이터만 적재한다. .env와 .env.local은 각 PC에서 관리한다. DB 내부 파일은 data/local_db/postgres에 두고 Git에 포함하지 않는다.

수집 로그의 `N개 수집`은 저장 완료가 아니다. 실행 마지막 JSON에서 `status: SUCCESS`, `database_changes: true`를 확인한다. `--dry-run`이면 `database_changes: false`다. 수집 실패나 저장 트랜잭션 오류가 있으면 최종 보고서의 실패 사유를 확인한다.
