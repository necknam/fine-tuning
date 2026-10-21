# Qwen Factory

Streamlit 실험 관리·RunPod QLoRA 학습·원본/어댑터 답변 비교를 담당한다. 실험 기록은 Neon, 가중치는 HF와 RunPod에 둔다. 옆 database의 Python 모듈이나 로컬 DB에 의존하지 않는다.

```powershell
python -m pip install -r requirements.txt
streamlit run scripts/local_dashboard.py
```

Cloud는 necknam/fine-tuning main의 최상위 streamlit_app.py다. 로컬 .env와 Cloud Secrets는 별도 관리한다. 확정 학습1,500건과 공통10개 입력은 data에 포함하며 가중치·체크포인트·비밀값은 Git에서 제외한다. GPU 의존성은 Linux RunPod 전용 requirements-runpod.txt다.

현재 공통 평가 버전은 prompts.app_v2.jsonl이며 과거 app_v1 결과와 분리한다. 기존 production 설정은1,200/150/150·5 epoch·4/5 저장 흐름이다. 확정한 전체1,500건·H100·2~5 epoch 비교는 실행 코드 전환이 남아 있으므로 기본 버튼으로 준비 완료라 간주하지 않는다.

[실행·비교·의존성](../docs/FINETUNING_GUIDE.md) · [실험 DB](../docs/FACTORY_DATABASE.md) · [현황](../docs/CODEX_HANDOFF.md)
