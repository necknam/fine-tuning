# Qwen Factory

Streamlit 실험 관리·RunPod QLoRA 학습·원본/어댑터 답변 비교를 담당한다. 실험 기록은 Neon, 가중치는 HF와 RunPod에 둔다. 옆 database의 Python 모듈이나 로컬 DB에 의존하지 않는다.

```powershell
python -m pip install -r requirements.txt
streamlit run scripts/local_dashboard.py
```

Cloud는 necknam/fine-tuning main의 최상위 streamlit_app.py다. 로컬 .env와 Cloud Secrets는 별도 관리한다. 확정 학습1,500건과 공통10개 입력은 data에 포함하며 가중치·체크포인트·비밀값은 Git에서 제외한다. GPU 의존성은 Linux RunPod 전용 requirements-runpod.txt다.

현재 공통 평가 버전은 prompts.app_v2.jsonl이다. 개선 v4 P01의 기존/개선 2·5에포크 총40개 비교는 완료됐으며 품질 gate는 FAILED다. 개선 v4 P02~P06은 진행하지 않았다. 이후 별도 승인된 복구 원본 P02~P06 저장 전용 학습은 완료됐고, 가중치10개·고정10개 번들5개의 외부 해시를 검증했다. 해당 실행의 생성 답변은0건이며 다른 PC 생성기는 미구현이다.

2026-10-25 문서 정리는 2026-10-24 최종 기록 기준이다. Pod STOP 요청은 수락됐지만 실제 정지 상태는 미확인이다. [최종 결과](../docs/이전원본_P02_P06_최종완료_20261024.md)를 따른다. Cloud 기본 설정 hyperparameters.compare.reviewed_v4_full1500.yaml이 남아 있는 것과 현재 실행할 실험은 구분한다.

[실행·비교·의존성](../docs/FINETUNING_GUIDE.md) · [실험 DB](../docs/FACTORY_DATABASE.md) · [현황](../docs/CODEX_HANDOFF.md)

B200 고속 FLA 오류 수정 환경은 기본 GPU 요구사항 설치 후 `python -m pip install --no-deps -r requirements-kernel-b200.txt`로 검증된 Triton3.6만 별도 적용한다. Torch2.8의 기본 Triton 핀과 구분하며 [전환 근거](../docs/B200_고속커널_전환_20261023.md)를 따른다.


## Qwen3.5-4B · B200 · 확장3000 P01 (2026-10-26)

별도 설정 `configs/hyperparameters.qwen35_4b_3000.P01.yaml`, 실행 `scripts/qwen35_b200_runner.py`. 준비 확인은 `python scripts/qwen35_b200_runner.py --phase check`. 현재 데이터 5회 검토 release 미완료로 학습은 차단된다. 60건 시험 통과 후 새 기본모델 5에폭·2/5 저장·동일10개 비교이며, 기존27B 버튼/러너와 구분한다. 전체 실행·재개·한계와 release 계약은 프로젝트 docs/FINETUNING_GUIDE.md의 2026-10-26 절을 따른다.
