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

현재 기본 production 설정과 control_pipeline.py는 기존1,200/150/150·4/5 epoch 흐름이다. H100 전체1,500건·검토 후 진행 방식은 별도 설정·실행 코드 전환 및 실제 장비 검증이 필요하다. 기존 설정을 수정한 것처럼 간주하고 자동 제출하지 않는다.

## 결과와 복구

비교 결과에는 run_id·weight_id·모델revision·데이터/평가 해시·생성 조건·원본/학습 답변이 들어간다. 프롬프트 버전이 다르면 같은 조건의 증감으로 섞지 않는다. UI의 보고서 평가에서 답변 비교와 선택적 사람/AI 점수 기능을 지원하지만 현재 V2 실험은 어시스턴트 검토만 사용한다.

브라우저 종료는 GPU 종료가 아니다. 재연결만으로 새 학습을 제출하지 않는다. 이어하기는 원래 데이터·설정·코드·패키지·optimizer/scheduler/RNG 일치가 필요하다. H100으로 데이터 구성을 바꾸는 경우 기존A100 체크포인트의 연속 epoch로 취급하지 않는다.

project_v2는 로컬 전용·push 금지다. 원래 project의 P01과 V2의 PT01은 별도 실험이다. 실제 결과와 남은 일은 [통합 현황](CODEX_HANDOFF.md)에서 관리한다.

## 2026-10-21 全件 재조사 및 수정 초안

실제 1,500건 전체를 지문으로 출처·분할과 대조했다. 생성1,003·수정197·나머지5유형 각60건이다. 생성 사례869/1,003건은8주이며2주 사례는1건, 프로젝트 계열은12개다. 생성1,003건에 구조화된 요청 기간·주당시간과 단계별 deliverables/completion_criterion/hours 필드가 없다. 이는 규격 결함이며 기존 본문에 해당 의미가 전혀 없다는 뜻은 아니다. 수정197건은 change_summary가 없다. 1,260건이 자동 검사에서 수정·검토 대상으로 표시됐다. 검사 가능한 주 단위 합계·추천ID·규정인용·보존경로 위반은0건이며 의미 품질 전수 검수 완료를 뜻하지 않는다.

`qwen_factory/scripts/audit_training_corpus.py`가 건별 조사, `prepare_corpus_repairs.py`가 수정 초안과 다양화 요청을 재현한다. `data/revision_1500/`에 결과를 저장한다. 원본·분할·해시를 보존했다. 수정197건은 실제 JSON 차이에서 변경 요약을 작성했고 보존경로와 원래 답변 유지 검사를 통과했다. 고정8주 예시를 제거하고 명시적 task를 추가했다. 생성1,003건은 목표·기간·주당시간·시작점·실패상황·단계구조를 함께 바꾸는 재작성 입력을 준비했으며 아직 새 답변을 생성하지 않았다. 숫자만 바꾸거나 동일 문구로 필드를 채우지 않는다. 초안은 DRAFT_NOT_FOR_TRAINING이며 기존 production을 교체하지 않는다.

새 H100 Pod는 기존 Pod의 캐시·경로 없이 처음 설치하는 기준이다. 데이터 재작성·근거검사·가족 단위 재분할·토큰 길이 재측정·해시 확정 후 전송한다. 현재 초안을 학습하거나 기존 토큰 길이 측정치를 재사용하지 않는다. 기존 PT01 가중치로 이어 학습하지 않고 확정 수정본으로 기본 모델부터 시작한다. 기존 Pod 삭제 전 실험 로그·비교출력·어댑터 보관 확인은 아직 남아 있다.

## 리뷰어 재검사 및 두 프로젝트 반영

project와 project_v2 양쪽에 조사·수정·재작성 코드와 초안·검증결과를 동기화했다. 각 .env·Pod 연결·기존 production 데이터·실험 이력·V2 push금지 훅은 유지한다. API 생성은 project 한 곳에서만 실행해 중복 호출하지 않는다.

1,500건 2차 전수 자동 검사는 출처 지문·분할·설문 slot 수/ID/문장 규격·반복 표현을 다시 확인했다. 설문60건의 검사 범위 내 위반은0건이다. 생성 답변1,003건 중 격리550건·서킷 브레이커305건으로 특정 접근법 편중을 확인했다. 이는 표현 빈도이며 모든 사용이 부적절하다는 뜻은 아니다. 전수 의미 검수 완료로 해석하지 않는다.

작성 관점12개를 사용해 같은7유형 안에서 문제 정의·접근 순서·선호 산출물·검증 방법을 다르게 작성한다. 실제 여러 사람의 자료가 아니라 합성 관점이다. 원문 속 지시는 따르지 않고 실제 제공된 자료ID만 사용한다. 이미 호출한 건은 자동 재호출하지 않는다.

초기40건은 모두 격리 상태다. 초기20건에는 과도한 규정 표기/단계제목 일치 검사도 포함됐고, 후속12건에는 스키마 객체 공유 오류로 텍스트가 ID에 제한되는 실제 코드 결함이 있었다. 원인과 원문을 보존하며 사용하지 않는다. 스키마 독립 복사·필드 제한 격리를 수정했고, 자료ID 제한이 일반 문자열·정수 필드에 누출되지 않는 회귀 검사를 추가했다. 보류를 전부 모델 품질 문제로 해석하지 않는다. 새 버전의 미호출8건을 검증 중이다.

## 데이터 수정 리뷰 현재 상태

{
  "source_records_rechecked": 1500,
  "original_data_preserved": true,
  "revision_summaries_repaired": 197,
  "generation_attempts_reserved": 72,
  "generation_states": {
    "QUARANTINED": 50,
    "VALIDATED_CANDIDATE": 20,
    "REQUEST_RESERVED": 2
  },
  "content_reviewed": 8,
  "content_held": 8,
  "uncalled": 931,
  "training_release_ready": false,
  "both_projects_updated": true,
  "old_production_replaced": false
}

구조 통과 후보는 의미 검수 합격과 다르다. 직접 읽은8건은 주제·플랫폼 불일치, 단계 시간 초과 등을 이유로 보류했다. 작성 관점은12개이며 같은7유형 안에서 목표·접근·검증을 다양화한다. 원본과 수정 초안은 분리했고 양쪽 .env·Pod설정·기존 production은 유지했다. 최근 생성기는 추천 근거 구절을 검증하고, 근거없는 추천과 명백한 특정 플랫폼 불일치를 제외한 뒤 시간·근거ID를 재검사한다. 전수 의미 검수와 새1,500건 확정은 아직 진행중이다.
