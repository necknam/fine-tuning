# Qwen Factory

Streamlit 실험 관리·RunPod QLoRA 학습·원본/어댑터 답변 비교를 담당한다. 실험 기록은 Neon, 가중치는 HF와 RunPod에 둔다. 옆 database의 Python 모듈이나 로컬 DB에 의존하지 않는다.

```powershell
python -m pip install -r requirements.txt
streamlit run scripts/local_dashboard.py
```

Cloud는 necknam/fine-tuning main의 최상위 streamlit_app.py다. 로컬 .env와 Cloud Secrets는 별도 관리한다. 확정 학습1,500건과 공통10개 입력은 data에 포함하며 가중치·체크포인트·비밀값은 Git에서 제외한다. GPU 의존성은 Linux RunPod 전용 requirements-runpod.txt다.

현재 공통 평가 버전은 prompts.app_v2.jsonl이다. 개선 v4 전체1,500건·B200·BF16 LoRA·5에포크 학습 후 2·5에포크 고정10개 입력을 기존 저장 가중치와 비교한다. Cloud 기본 설정은 hyperparameters.compare.reviewed_v4_full1500.yaml이며 학습 all.jsonl과 공통 입력 JSONL 두 파일을 직접 업로드한다. 이전 데이터 재학습은 진행하지 않는다.

[실행·비교·의존성](../docs/FINETUNING_GUIDE.md) · [실험 DB](../docs/FACTORY_DATABASE.md) · [현황](../docs/CODEX_HANDOFF.md)
