# 로컬 DB 사용 안내

앱은 Docker 없이 PostgreSQL 17.11 + pgvector 0.8.2를 사용한다. 앱 데이터는 로컬 growpath, 팩토리 실험 기록은 Neon에 저장한다. 전체 현황과 남은 일은 [통합 보고서](../../qwen_factory/docs/CODEX_HANDOFF.md)를 참고한다.

## 실행과 백업

project 폴더에서 실행한다.

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

Test Connection 후 Schemas에서 public, hr_regulation_pilot, growpath_meta, growpath_legacy를 선택한다. SQL 콘솔도 growpath 연결을 선택해야 한다. postgres DB에서는 앱 테이블이 보이지 않는다.

```sql
SELECT current_database(), inet_server_port();
SELECT COUNT(*) FROM public.courses;
SELECT * FROM public.skill_tags ORDER BY skill_id;
```

현재 구조는 [최신 ERD](통합ERD_1020_로컬DB확인본.html)를 참고한다. 보관 스키마·기존 임베딩 컬럼은 호환성을 위해 유지하며 검색·갱신은 canonical 벡터를 사용한다. 복구 백업과 data/local_db/postgres는 정리 대상이 아니다.
