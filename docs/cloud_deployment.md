# GitHub → Streamlit Community Cloud

## 배포 설정

- 저장소: https://github.com/necknam/fine-tuning
- 브랜치: `main`
- Main file path: `streamlit_app.py`
- Advanced settings의 Python 버전: `3.12`
- Python 의존성: 루트 `requirements.txt` (GPU 패키지는 Cloud에 설치하지 않음)

Streamlit Community Cloud에서 Create app → Deploy from GitHub를 선택하고 위 값을 입력합니다.
Advanced settings 또는 배포 후 App settings → Secrets에서
`.streamlit/secrets.toml.example`을 참고해 실제 인증정보를 직접 입력합니다.
실제 `.env`나 `secrets.toml` 파일은 Git에 올리지 않습니다.

필수 Secrets: DASHBOARD_PASSWORD, DASHBOARD_STORAGE="neon", DATABASE_URL.
RunPod 제어: RUNPOD_JUPYTER_URL, RUNPOD_JUPYTER_TOKEN, RUNPOD_REMOTE_PATH, HF_TOKEN, HF_REPO_ID.
AI 평가: OPENAI_API_KEY, OPENAI_EVAL_MODEL.
자세한 값의 의미는 `cloud_secrets.md`, 입장 방법은 `shared_password.md`를 참고하세요.

입장한 모든 사람은 같은 권한으로 GPU 학습과 AI 평가를 실행할 수 있습니다.
이 공용 비밀번호 방식에는 Google 로그인이나 사용자별 역할 구분이 없습니다.

## Git에 포함되는 항목

소스, 실행 설정, 설명 문서, 가상 학습54/검증3/평가 예시 데이터만 포함합니다.
본 데이터, 비밀값, 로컬 접속 설정, 캐시, 가상환경, 보고서, 백업, 모델 가중치는 제외합니다.
GitHub에서 수정/커밋한 코드를 배포 앱이 사용하며 런타임 결과는 Neon에 저장합니다.
Cloud 실행 중 임시 파일 변경을 Git 저장소에 자동 커밋하지 않습니다.

## 로컬 Miniforge

Conda 설정은 Cloud가 잘못 선택하지 않도록 `configs/environment.local.yml`로 옮겼습니다.
로컬에서 새 환경을 만드는 경우:

```powershell
conda env create -f configs/environment.local.yml
conda activate qwen-factory
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

기존 `start_dashboard.ps1`도 계속 사용할 수 있습니다.

## 배포 후 확인

1. 비밀번호가 없거나 틀리면 보고서/실행 화면에 접근하지 못하는지 확인합니다.
2. 입장 후 Neon에 보관한 보고서와 사람/AI 점수가 나타나는지 확인합니다.
3. RunPod가 꺼져 있으면 마지막 저장 기록을 표시합니다. GPU 작업은 시작하지 않습니다.
4. Pod를 켠 뒤 연결 및 독립 복구 서비스 기동을 확인합니다.
5. 기존 어댑터의 소수 입력으로 실제 실행을 확인한 뒤, 브라우저를 닫고 다시 열어 결과가 저장됐는지 확인합니다.


공식 문서:
https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies
