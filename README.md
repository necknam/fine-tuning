# GrowPath DB · Qwen Factory

시트·DB의 변경 이유와 적용 상태는 [시트_DB_변경점.md](시트_DB_변경점.md)에 기록합니다. 로컬 반영과 Cloud 배포 상태를 구분합니다.


PostgreSQL 관리와 파인튜닝 실험을 관리하는 저장소다.

```text
project/
├── database/                 # 스키마·규정/자료 적재·벡터·전체 백업/복원
│   ├── config/               # paths.yaml · rules.yaml, 스킬 태그 유지
│   ├── scripts/              # 설치·백업·복원·서버 관리
│   ├── src/database/         # DB 모듈·마이그레이션·적재·벡터
│   ├── src/shared/           # DB에서 사용하는 공통 검증·스킬 매칭
│   ├── data/exports/         # Git 포함: 전체 DB 덤프·해시·pgvector
│   ├── data/regulations/     # 규정 원본
│   ├── data/local_db/        # Git 제외: 실제 PostgreSQL 파일
│   ├── load_data.py          # 공식 5종 자료 수집·적재
│   ├── diagnose_catalog.py   # API·DB 읽기 전용 진단
│   ├── requirements.txt
│   ├── .env                  # 각종 API 설정, Git 제외
│   └── .env.local            # 로컬 DB 설정, Git 제외
├── qwen_factory/             # Streamlit 실험 관리·학습·비교
│   ├── scripts/
│   ├── configs/
│   ├── data/production/curation_1500/ # 확정 1,500건·분할·출처
│   ├── data/eval/            # 공통 입력 10개, 버전별 보존
│   ├── requirements.txt
│   ├── requirements-runpod.txt
│   └── .env                  # HF·Neon·RunPod, Git 제외
├── docs/                     # 공통 DB 문서·학습 안내·ERD·참고 문서
├── DB_복원.md                # 새 PC 설치·전체 복원 안내
├── .gitignore                # 최상위에서 제외 정책 관리
├── .gitattributes
├── requirements.txt          # Cloud용 팩토리 의존성 진입점
└── streamlit_app.py          # Cloud용 팩토리 진입점
```

로드맵 UI·에이전트·학습 데이터 생성 코드는 제거했다. 업무 DB 테이블과 적재 데이터는 유지한다. 확정 학습 데이터의 중복 사본은 qwen_factory로 모았다. 두 영역은 서로의 Python 모듈을 import하지 않는다.

## 설치·실행

전체 DB 설치·복원은 [DB_복원.md](DB_복원.md)를 따른다. 기존 DB는 아래처럼 실행한다.

```powershell
cd database
python -m pip install -r requirements.txt
python scripts/local_db.py start
python scripts/db.py verify
```

팩토리는 별도 Python 3.12 가상환경을 권장한다.

```powershell
cd qwen_factory
python -m pip install -r requirements.txt
streamlit run scripts/local_dashboard.py
```

Streamlit Cloud의 저장소는 necknam/fine-tuning, main 브랜치, 최상위 streamlit_app.py다. Cloud Secrets는 별도로 설정한다. GPU용 requirements-runpod.txt는 RunPod Linux 전용이며 로컬 대시보드 환경과 구분한다.

## 데이터와 현재 실험

로컬 PostgreSQL 17.11 + pgvector 0.8.2, 팩토리 Neon PostgreSQL 18.6을 사용한다. 전체 DB 백업과 확정 학습 데이터는 Git에 포함한다. 실제 실행 DB 폴더·.env·토큰·로그·모델 가중치는 제외한다.

개선 v4 P01 비교와 별도 승인된 복구 원본 P02~P06 학습은 완료됐다. 현재 상태는 [핸드오프](docs/CODEX_HANDOFF.md)를 따른다. [학습·비교 실행 기준](docs/학습_비교_실행기준_20261023.md)은 당시 실험 조건을 보존한 문서이며 새 학습 실행 지시가 아니다.

최종 기록(2026-10-28):
- **27B 가중치 결합 완성형 모델(`v_fin`) 배포 및 평가 완료 (타 모델 대비 약 10% 성능 우위로 최종 선정)**: 전체 후보 모델군 대비 제약 준수율·부분 수정 정확도·실무 구체성에서 **약 10%의 성능 이점**을 보인 `V18` LoRA 가중치를 `Qwen/Qwen3.8-27B` 베이스 모델에 영구 결합(`merge_and_unload`)하여 **[`Ssum-mer/qwen3.8-27b-growpath-v18`](https://huggingface.co/Ssum-mer/qwen3.8-27b-growpath-v18)**에 배포하고, 개정된 공통 평가 입력 10종(`prompts.app_v2.jsonl`, 4~12주 및 사내 정기 업무 보고서 자동화)에 대한 A100 BF16 추론 보고서(`v_fin`)와 AI/휴먼 평가를 Streamlit 및 Neon DB에 동기화 완료했다.
- **Qwen3.5-4B 확장 3,000건 P01~P03 완료**: `Qwen/Qwen3.5-4B` 확장 3,000건 학습(P01, P02, P03) 및 1단계~4단계 비교 보고서(`docs/model_evaluation_reports/`)와 대시보드 연동을 완료했다. 상세 내역은 [파인튜닝 히스토리](docs/파인튜닝_히스토리.md) 및 [최신 평가 결과 보고서](docs/최신_평가_결과_보고서.md)를 참조한다.

project_v2는 별도 로컬 저장소이며 push 금지다. 기존 project P01 실행 설정은 별도 유지한다.

- [로컬 DB 테이블·벡터](docs/DATABASE.md)
- [팩토리 Neon DB](docs/FACTORY_DATABASE.md)
- [학습·평가 안내](docs/FINETUNING_GUIDE.md)
- [현재 상태·남은 일](docs/CODEX_HANDOFF.md)
- [ERD 최종](docs/ERD_최종.html)
- [HTML 통합 보고서](docs/DB_데이터_파인튜닝_통합보고서.html)
