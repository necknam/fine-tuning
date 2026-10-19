# Cloud Secrets 설정

설정 우선순위: Streamlit Secrets → 프로세스 환경변수 → 프로젝트 .env.
대시보드, Neon 저장 모듈, AI 평가 프로세스가 scripts/app_settings.py를 공유합니다.
로컬에서는 기존 .env를 그대로 사용합니다. 이 작업에서 실제 인증정보를 복사하거나 변경하지 않았습니다.

## Cloud에 등록할 때

1. `.streamlit/secrets.toml.example`을 열어 필요한 설정 이름을 확인합니다.
2. Streamlit Community Cloud 배포의 Advanced settings → Secrets 또는 배포 후 App settings → Secrets에 TOML 내용을 넣습니다.
3. 예시 값을 실제 값으로 직접 교체합니다. 채팅이나 GitHub에 붙여넣지 않습니다.
4. 저장 후 앱을 다시 실행합니다.

필수: DATABASE_URL, DASHBOARD_STORAGE="neon".
학습 연결: HF_TOKEN, HF_REPO_ID, RUNPOD_JUPYTER_URL, RUNPOD_JUPYTER_TOKEN, RUNPOD_REMOTE_PATH.
자동 AI 평가: OPENAI_API_KEY, OPENAI_EVAL_MODEL.
RUNPOD_JUPYTER_TOKEN에는 Jupyter 로그인 토큰 또는 Pod의 JUPYTER_PASSWORD를 사용합니다.
RunPod API 키나 HF 토큰을 이 항목에 넣지 않습니다.

Secrets의 항목은 예시처럼 최상위 문자열로 작성합니다.
실제 `.streamlit/secrets.toml`은 Git 제외 대상입니다. 예시 파일에는 가짜 값만 있습니다.
Cloud Secrets가 있으면 기존 .env의 같은 항목보다 우선합니다.
설정 형식이 잘못되면 비밀값을 표시하지 않는 오류로 중단합니다.

AI 평가 자식 프로세스에는 실행 시 유효한 DB/OpenAI 설정을 환경변수로 전달합니다.
이 기능은 기존 프로세스의 설정 전달이며, Cloud 종료 후 계속 동작하는 영구 워커 구현은 다음 복구 단계입니다.
RunPod GPU 학습 스크립트는 기존 원격 환경변수 전달 방식을 유지합니다.
Cloud 배포와 로그인 보호는 아직 완료되지 않았습니다. 로그인 구현 전 공개 운영하지 않습니다.

검증: Secrets/환경변수/.env 우선순위, 자식 프로세스 설정, 기본값,
비밀값 가림, 잘못된 TOML/타입 오류, 로컬 기존 설정 읽기, Python 구문 검사 통과.
OpenAI 호출이나 GPU 작업은 수행하지 않았습니다.

공식 안내: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management
