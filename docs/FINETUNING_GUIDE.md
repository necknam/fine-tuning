# 파인튜닝 실행·평가 안내

2026-10-21 기준. 데이터 생성·선별과 GPU 학습은 구분한다. 이 저장소에는 확정 학습 데이터와 학습·평가 코드만 남기고 생성 코드는 제거했다.

## 파일과 의존성

- 확정본: data/production/curation_1500/all.jsonl (1,500건), train.jsonl (1,200), validation.jsonl (150), test.jsonl (150). all.jsonl은 전체학습용 원본이며 기존 분할 파일을 덮어쓰지 않는다.
- 현재 공통 평가: data/eval/prompts.app_v2.jsonl (10개). 질문·근거는 app_v1과 같고 시스템 프롬프트 충돌만 정리했다. 변경 사유·부모 해시·새 해시는 옆 manifest에 기록한다.
- 로컬 Python 3.12: pip install -r requirements.txt. Linux RunPod: requirements-runpod.txt.
- 원격 검증 환경: torch 2.8.0+cu128, transformers 5.20.0, peft 0.21.2, accelerate 1.15.0, bitsandbytes 0.50.2, HF Hub 2.2.0, SQLAlchemy 2.1.5, psycopg 3.3.6, pgvector는 로컬DB 확장으로 별도 설치.
- 최적화 커널: triton 3.4.0, fla-core/flash-linear-attention 0.5.2, causal-conv1d 1.7.0. causal-conv1d의 고정 wheel은 Linux x64·Python3.12·torch2.8/cu12·CXX11 ABI용이다.
- 2026-10-21 실제 RunPod pip check 통과. Windows 두 앱 고정 의존성의 설치 dry-run도 충돌 없이 해결됐다.
- 공용 llm_env는 고정 파일과 버전이 다르며 gradio/HF Hub, typeddict/pydantic 충돌을 보고했다. 공용 환경을 자동 업그레이드하지 않고 별도 가상환경에 고정 파일을 설치한다.

## 연결

각 폴더 .env를 독립 관리한다. 팩토리는 Cloud Secrets > 환경변수 > qwen_factory/.env 순서다. HF_TOKEN·HF_REPO_ID·DATABASE_URL·RUNPOD_JUPYTER_URL·RUNPOD_JUPYTER_TOKEN을 로컬에서 설정한다. Jupyter에는 실제 로그인 값/JUPYTER_PASSWORD를 사용한다. 토큰·DB 비밀번호는 Git·ZIP·로그에 넣지 않는다.

python scripts/check_connections.py로 HF·Neon 연결을 확인하고 streamlit run scripts/local_dashboard.py로 화면을 실행한다. Cloud는 최상위 streamlit_app.py와 requirements.txt를 사용한다. DB 내용은 [팩토리 DB](FACTORY_DATABASE.md)를 참고한다.

## 확정 비교 절차

1. 현재 A100 사전 점검: 1,200건 학습의 checkpoint50에서75까지 이어 총1 epoch로 종료. 기존5 epoch 스케줄을 따른 중간 결과이므로 새1 epoch 스케줄과 구분한다. 300건 BF16 검증 손실은0.622479이며 원본 대비 개선률이 아니다.
2. 고정8주 지시가 있던 app_v1 비교는 완료했으나 유효성 통과는 보류했다. 충돌을 정리한 app_v2의 같은10개를 저장된 가중치로 재비교한다. 5개 시점1차,10개 시점2차 어시스턴트 검토. 별도 유료 AI 채점·점수 저장은 하지 않는다.
3. 사전 점검을 통과한 뒤 H100 본 실험은 전체1,500건을 기본 모델부터 새로 학습한다. 2/3/4/5 epoch의 파라미터·가중치·동일10개 출력, 최대40개를 비교한다. 개선이 미미하면 중단하고 최대5 epoch다.
4. 선택된 가중치를 최종 사용한다. 전체1,500건 학습 뒤 기존150건은 독립 테스트가 아니며,10개 비교는 일반 성능을 입증하지 않는다.

현재 Cloud 기본은 hyperparameters.compare.reviewed_v4_full1500.yaml이다. 개선 v4의 all.jsonl 1,500건 전체를 B200 BF16 LoRA로 5에포크 학습하며 별도 검증/150건 평가 없이 2·5에포크 고정10개를 비교한다. 이전 데이터는 B200_P01_epoch2/epoch5의 저장 가중치를 재사용한다. 기존 분할·실험 이력은 보존한다.

## 결과와 복구

비교 결과에는 run_id·weight_id·모델revision·데이터/평가 해시·생성 조건·원본/학습 답변이 들어간다. 프롬프트 버전이 다르면 같은 조건의 증감으로 섞지 않는다. UI의 보고서 평가에서 답변 비교와 선택적 사람/AI 점수 기능을 지원하지만 현재 V2 실험은 어시스턴트 검토만 사용한다.

브라우저 종료는 GPU 종료가 아니다. 재연결만으로 새 학습을 제출하지 않는다. 이어하기는 원래 데이터·설정·코드·패키지·optimizer/scheduler/RNG 일치가 필요하다. H100으로 데이터 구성을 바꾸는 경우 기존A100 체크포인트의 연속 epoch로 취급하지 않는다.

project_v2는 로컬 전용·push 금지다. 원래 project의 P01과 V2의 PT01은 별도 실험이다. 실제 결과와 남은 일은 [통합 현황](CODEX_HANDOFF.md)에서 관리한다.
