# GrowPath Qwen Factory

학습·평가를 관리하는 Streamlit 앱이다. GPU 작업은 RunPod, 실험 기록은 Neon, 어댑터는 HF 저장소를 사용한다. 로드맵 앱의 로컬 DB와 별개다.

```powershell
cd C:/final_team2/project/qwen_factory
streamlit run scripts/local_dashboard.py
```

Cloud 배포는 저장소 necknam/fine-tuning, 브랜치 main, 최상위 streamlit_app.py를 유지한다. Cloud에는 별도 Secrets를 설정한다. 비밀값·DB 파일·실제 학습 JSONL은 Git에 올리지 않는다.

최종 데이터는 학습 1,200·검증 150·별도 평가 150건이며 공통 비교 입력 10개는 별도다. production 설정은 configs/hyperparameters.production.pinned.yaml이다. 실제 데이터 학습 화면에서 준비된 파일을 사용하거나 확정 파일 4개를 모두 업로드한다. 샘플 시험과 본 학습은 구분한다.

[DB·데이터·학습 통합 보고서](../docs/CODEX_HANDOFF.md) · [실행·연결·복구 안내](../docs/FINETUNING_GUIDE.md)

파라미터 의미·현재 설정·25개 탐색 후보는 Streamlit 안내 화면에서 확인한다. 프리셋은 검증된 최적값이 아니며 선택한 실험만 실행한다. 유료 자동 AI 평가는 기본 꺼짐이다.

로컬 의존성은 requirements.txt, RunPod GPU 의존성은 requirements-runpod.txt로 분리한다. 기존 start_dashboard.ps1은 팩토리 폴더의 전용 환경을 사용한다. 설치 명령은 해당 환경에서 pip install -r requirements.txt이며, 로컬 PC에 GPU용 requirements를 설치하지 않는다.
