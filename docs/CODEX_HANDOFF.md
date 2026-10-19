# GrowPath 현재 상태와 다음 작업

## 현재 구조

- GitHub: https://github.com/necknam/fine-tuning (`main`)
- Streamlit: https://fine-tuning-sqe6zc4q4p4qfczulumyue.streamlit.app/
- 진입 파일 `streamlit_app.py`, Python 3.12, CPU 의존성 `requirements.txt`.
- 공용 DASHBOARD_PASSWORD로 입장하며 모든 입장자의 권한은 같습니다.
- Secrets → 환경변수 → 로컬 .env. 실제 비밀값은 Git에 넣지 않습니다.
- 원본 기록은 Neon `qf_dashboard`, 가중치는 기존 HF 저장소, GPU 작업은 RunPod.
- 같은 Qwen 모델/revision을 4비트 QLoRA로 학습하고 원본 BF16+어댑터로 답변을 생성합니다.
- 모델을 작은 모델로 바꾸거나 로컬 GPU에서 27B 추론하는 방향으로 변경하지 마세요.

## 2026-10-19 변경

1. **샘플/실제 구분**: 대시보드에서 모드를 선택합니다. 실제 학습/검증 messages JSONL 업로드와 선택적 평가 입력 업로드를 지원합니다. 실제 데이터는 Git에 올리지 않고 내용 해시로 고정하여 Neon과 RunPod에 전달합니다.
2. **새 실험/이어하기 구분**: 새 등록마다 experiment_id(UUID)를 생성합니다. 기존부터 데이터 SHA-256이 실험 식별에 포함됐으며, 이번에는 실행 ID와 업로드 당시 해시 검증을 추가했습니다. 새 요청은 기존 디렉터리/완료 가중치를 자동 재사용하지 않습니다. 이어하기와 기존 가중치 평가는 별도 명시적 동작입니다.
3. **독립 저장**: 실제 실행은 outputs/factory_production, HF production/; 시험은 기존 factory_sample, sample/. 보고서에 구분과 데이터 해시를 표시합니다.
4. **엄격 AI 기준**: growpath_judge_v2_strict. 형식만으로 고득점하지 않고 구체적인 활동/산출물/완료 기준, 입력 조건, 자료 활용을 평가합니다. 수치로 입증된 예산/시간 위반은 constraints 최대2, 미제공 자료 ID는 resources 최대1. 모델 원점수와 조정 근거를 함께 보관합니다. 이전 v1 점수는 삭제하지 않고 새 버전으로 별도 평가합니다. 자동 AI 평가가 켜져 있으면 v2 결과가 없는 답변은 새 API 호출로 평가됩니다.
5. **보고서 배치**: 입력 위, 모델 답변 아래의 전체 너비. 예산과 합계는 말줄임 metric 대신 줄바꿈 가능한 텍스트로 표시합니다. AI 요약도 펼쳐서 전체 문장을 읽습니다.
6. **필요할 때 조회**: 트래킹 탭의 .open을 사용해 열린 탭만 실행합니다. 실행 현황 자동 갱신 기본 OFF. 보고서는 탭 진입/새 보고서 확인, AI 점수는 AI 결과 갱신 때 갱신합니다. 파라미터 편집이나 설명 탭에서 보고서를 전부 조회하지 않습니다. 입력25개 AI 점수는 가중치별 단일 조회로 묶고 10초 캐시합니다. 문서는 메타데이터 비교 후 바뀐 내용만 전송합니다.

## 검증 범위

통과: 데이터 변경/모드 변경에 따른 식별 분리, 새 등록 UUID, 명시적 재개만 resume 플래그,
평가 전용 경로의 학습 미호출, 학습/검증 요청 누출 차단, 기존 샘플 identity 호환,
엄격 점수 상한, 전체 너비 보고서, 변경 문서만 복원, 입력25개 단일 DB 조회,
깨끗한 Git 체크아웃의 입장/지연 탭 실행/기본 자동 갱신 OFF/업로드 전 등록 차단.
테스트는 모의 GPU/API와 격리된 데이터로 수행하며 실제 재학습을 시작하지 않았습니다.
RunPod가 꺼져 있어 실제 GPU 학습 및 독립 복구 서비스의 실제 재기동은 미검증입니다.
코드가 준비됐다는 사실과 실제 Pod 검증 완료를 구분하세요.
구형 샘플의 미완료 체크포인트는 학습 코드 해시가 바뀌면 안전상 자동 재개하지 못할 수 있습니다.
기존 완료 가중치의 조회/평가와 점수 이력은 유지합니다.

## 파일 경량화 후보 (자동 삭제하지 않음)

실측 기준 로컬 .venv-dashboard 약333MB, reports 약1.3MB, docs 약0.1MB입니다.
용량 대부분은 코드 파일 수가 아니라 Python 패키지입니다. 캐시/가상환경/가중치는 이미 Git에서 제외합니다.

- `.venv-dashboard`: Miniforge 환경 하나로 실행을 통일하고 start_dashboard.ps1을 바꾼 뒤 제거 가능. 현재 스크립트는 이 폴더를 다시 만들므로 먼저 실행 방식을 변경해야 합니다.
- `.cache/`, `__pycache__/`, `.idea/`: 캐시/개인 IDE 설정으로 정리 가능. Git 제외 상태입니다.
- `outputs/legacy_requirements/`, `outputs/before_local_dashboard/`, `outputs/before_production_mode/`: 예전 파일 백업. 복구가 필요 없으면 별도 보관 후 정리 가능.
- `scripts/compare_smoke.py`: 구형 단일 입력 비교 도구. 현재 대시보드는 compare_factory_sample.py를 사용하므로 구형 실험을 더 열지 않으면 보관 폴더로 이동 가능.
- `scripts/runpod_smoke.py`, `scripts/check_connections.py`, `scripts/preflight_hf.py`: 환경/접속/모델 확인 도구. 역할을 한 점검 명령으로 통합한 뒤 정리 가능. runpod_smoke.py는 새 Pod 안내에서 사용하므로 지금 바로 삭제하면 안내도 바꿔야 합니다.
- `configs/hyperparameters.sample.yaml`, `configs/hyperparameters.yaml`: 현재 대시보드는 pinned 파일을 기준으로 실행합니다. CLI로 별도 사용하지 않으면 기준 파일 하나로 정리할 후보입니다.
- `docs/verification_2026-10-17.json`, `docs/neon_migration_verification.json` 및 과거 HTML: 운영 기능에 필수는 아닌 검증 증거/기록입니다. 문서 보관 위치로 모을 수 있습니다.
- `requirements.txt`와 `requirements-runpod.txt`는 합치지 않습니다. Cloud에 GPU 패키지를 설치하지 않도록 분리해야 합니다.
- `reports/` 전체, 등록 실행 설정, HF 가중치는 일괄 삭제하지 않습니다. 캐시와 보존해야 할 옛 결과/백업이 섞여 있습니다.

## 다음 실제 확인

배포 후 샘플/실제 선택, 가로 잘림 없는 보고서, 자동 갱신 기본 OFF, 엄격 v2 표시를 확인합니다.
Pod를 켜면 연결 후 독립 서비스 기동과 소수 입력의 실제 실행·복구를 검증합니다.
실제 데이터 학습 시작은 사용자가 데이터를 준비하고 새 실험을 등록할 때 수행합니다.
