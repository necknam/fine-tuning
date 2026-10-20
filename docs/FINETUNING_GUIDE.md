# 확정 데이터로 학습하기

데이터 구성·선별 이유·학습 설정·남은 일은 [통합 보고서](CODEX_HANDOFF.md) 한 곳에서 관리한다.

## 사용할 파일

- 설정: configs/hyperparameters.production.pinned.yaml
- 학습: data/production/curation_1500/train.jsonl — 1,200건
- 검증: data/production/curation_1500/validation.jsonl — 150건
- 별도 평가: data/production/curation_1500/test.jsonl — 150건
- 공통 비교 입력: data/eval/prompts.app_v1.jsonl — 10개

이미 확정된 데이터는 다시 무작위 분할하지 않는다. 원본을 수정하거나 과거 sample 데이터를 실제 학습 데이터로 선택하지 않는다. 파일 해시가 다르면 실행 전에 확인한다.

## 실행 순서

1. .env에 HF·Neon·Jupyter 연결을 설정한다. 비밀값은 Git이나 채팅에 넣지 않는다.
2. `python scripts/check_connections.py`로 HF·Neon 조회를 확인한다. RunPod 연결 확인은 별도다.
3. `streamlit run scripts/local_dashboard.py`를 실행하고 기존 Pod에 연결한다.
4. 실제 데이터 학습 모드를 선택하고 확정 설정·학습 1,200건·검증 150건·평가 경로를 확인한다.
5. GPU 메모리·속도 점검 후 본 실험을 등록한다. 새 실험과 중단 작업의 이어하기는 구분한다.
6. 별도 평가 150건과 공통 10개 입력으로 원본·어댑터를 비교한다. 유료 AI 평가는 명시적으로 켤 때만 실행한다.

데이터의 길이 검사는 완료됐지만 이 확정본의 GPU 학습은 아직 미실행이다. 기존 샘플 실험 결과를 본 학습 결과로 사용하지 않는다.

## 연결과 Cloud 배포

- 각 폴더의 .env를 독립 관리한다. 팩토리 설정 우선순위는 Cloud Secrets > 환경변수 > qwen_factory/.env다.
- 필수 설정은 DASHBOARD_PASSWORD, DASHBOARD_STORAGE="neon", DATABASE_URL, HF_TOKEN, HF_REPO_ID다. GPU 연결에는 RUNPOD_JUPYTER_URL, RUNPOD_JUPYTER_TOKEN, RUNPOD_REMOTE_PATH가 필요하다.
- Jupyter 토큰에는 Pod의 JUPYTER_PASSWORD 또는 Jupyter 로그인 값을 사용한다. RunPod 관리 API 키가 아니다.
- Cloud 저장소는 necknam/fine-tuning, 브랜치는 main, 진입점은 루트 streamlit_app.py를 사용한다. 루트 requirements.txt는 팩토리 의존성을 설치한다.
- Cloud Secrets는 팩토리 .streamlit/secrets.toml.example 항목을 참고해 실제 값으로 입력한다. OPENAI_API_KEY/OPENAI_EVAL_MODEL은 유료 보조 평가에만 사용하며 자동 평가는 기본 꺼짐이다.
- Cloud에 학습 JSONL은 들어 있지 않다. 실제 데이터 학습 화면에서 train.jsonl, validation.jsonl, test.jsonl, prompts.app_v1.jsonl을 모두 업로드한다. 고정 해시·건수·분할을 검증하며 줄바꿈도 변환하지 않는다.
- 파일 위치는 qwen_factory/data/production/curation_1500과 qwen_factory/data/eval이다. Cloud 재시작 후 로컬 파일이 사라지면 다시 업로드한다.

## 중단과 복구

RunPod 작업과 독립 수집기는 브라우저와 별도로 실행된다. 브라우저를 닫는 것은 GPU 중지가 아니다. Pod를 중지하면 작업도 중단된다.

실행 설정·보고서·평가 기록은 Neon에 저장하고 화면에서 복원한다. 재연결 전의 기록은 현재 실행 상태와 구분한다. 재연결만으로 GPU 학습을 새로 제출하지 않는다.

중단 시 Pod 연결·인증정보와 원래 체크포인트를 확인한 뒤 실행 이력에서 **이 실험 이어하기**를 선택한다. 새 실험 등록은 새 실행 ID를 만든다. 원래 폴더가 없거나 설정·데이터·코드 검증이 맞지 않으면 자동 재개하지 않는다. GPU 작업 중에는 별도 SSH/Jupyter 학습을 중복 실행하지 않는다.

자동 AI 평가를 끄더라도 이미 시작한 호출이 완료될 수 있다. 보고서와 점수는 사람 검토·유료 AI 보조 평가를 구분해 읽는다.
