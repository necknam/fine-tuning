# GrowPath

```text
project/
├── roadmap_app/      # 로컬 로드맵 앱·DB·데이터 생성
├── qwen_factory/     # 학습·평가 관리 앱 — 로컬 또는 Streamlit Cloud
└── README.md
```

## 실행

로드맵 앱은 로컬 PostgreSQL을 사용한다.

```powershell
cd roadmap_app
python scripts/local_db.py start
streamlit run app.py
```

팩토리는 별도 터미널에서 실행한다.

```powershell
cd qwen_factory
streamlit run scripts/local_dashboard.py
```

Cloud의 기존 진입 파일 `streamlit_app.py`는 팩토리 화면으로 연결된다. 루트 requirements는 팩토리 의존성만 설치한다. 로드맵 앱은 Cloud에 배포하지 않는다.

## 설정과 연계

각 폴더의 .env는 독립적으로 관리한다. roadmap_app/.env.local은 로컬 DB, roadmap_app/.env는 API, qwen_factory/.env는 HF·Neon·RunPod 설정이다. Cloud는 별도 Secrets를 사용하며 .env를 업로드하지 않는다.

로드맵 앱이 만든 확정 데이터를 팩토리로 전달한다. 실행 시 서로의 Python 모듈이나 DB를 직접 공유하지 않는다. 최종 1,500건은 학습 1,200·검증 150·별도 평가 150이며 공통 비교 입력 10개는 별도다. 데이터·DB 파일은 Git에서 제외한다.

[DB·데이터·학습 통합 보고서](qwen_factory/docs/CODEX_HANDOFF.md) · [로컬 DB 안내](roadmap_app/docs/LOCAL_DB_REVIEW_20261020.md)
