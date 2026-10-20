# GrowPath roadmap_app

앱·DB·벡터 RAG·학습 데이터 생성을 관리합니다. QLoRA 학습·평가·RunPod 관리는 옆의 `../qwen_factory`에서 수행합니다.

```text
C:/final_team2/project/
├── roadmap_app/
└── qwen_factory/
```

## 현재 실행

Docker 없이 Windows 네이티브 PostgreSQL 17+pgvector를 사용합니다. 실제 DB 파일은 `data/local_db/postgres`에 있으며 접속은 `127.0.0.1:55433`입니다.

```powershell
python scripts/local_db.py start
python scripts/db.py verify
streamlit run app.py
```

`.env.local`의 로컬 DB 연결이 기존 `.env`보다 우선합니다. 실제 파일은 Git에 넣지 않습니다. OpenAI/API 설정은 기존 `.env`를 유지합니다. 클라우드 원본은 변경하지 않았습니다.

## 개발 모듈

`src/database`는 적재·스키마·벡터, `src/finetuning`은 학습 데이터 생성·통합, `src/roadmap`은 앱 서비스·에이전트, `src/shared`는 공통 입력·검증, `src/clients`는 외부 모델 호출을 담당합니다. 옛 Python 경로는 기존 명령을 위한 호환 진입점만 유지합니다.

## 기준 문서

- [DB·파인튜닝 데이터·파인튜닝 통합 보고서](../docs/CODEX_HANDOFF.md)
- [로컬 DB 실행·PyCharm 접속·백업](../docs/LOCAL_DB_REVIEW_20261020.md)
- [최신 로컬 DB ERD](../docs/통합ERD_1020_로컬DB확인본.html)
- [확정 데이터 기준](config/finetuning_1500.yaml)

최종 1,500건 데이터 준비와 로컬 검사는 완료됐다. 실제 GPU 학습과 비교 평가는 남아 있다. 원문·선별 근거·학습 데이터·DB 파일은 보존한다.
