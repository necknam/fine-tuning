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
