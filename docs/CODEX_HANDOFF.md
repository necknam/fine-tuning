# 다른 Codex에 전달할 작업 프롬프트

아래 내용을 새 Codex에 전달하고 동일 로컬 프로젝트를 열어 작업하세요.

---

GrowPath의 Qwen 실험 운영 도구를 이어서 작업해 주세요. 먼저 프로젝트 README와 적용되는 AGENTS.md를 읽고, 현재 파일·실행 상태를 확인한 뒤 수정하세요. 이 문서는 2026-10-17 작업의 인계용입니다.

## 프로젝트와 확정된 구조

- 프로젝트: `C:\Users\오호민\Desktop\Study\qwen_factory`
- 로컬 Streamlit: `http://127.0.0.1:8501/`
- RunPod: `https://wsmwv2tt9t8txp-8888.proxy.runpod.net`
- RunPod 프로젝트: `/workspace/qwen_factory`; Jupyter API 기준 `workspace/qwen_factory`.
- GPU Python: `/workspace/qwen_factory/.venv-runpod/bin/python`.
- 확정: RunPod에서 **4비트 QLoRA 학습 → 어댑터 저장/HF 업로드 → 동일 모델·revision의 원본 BF16 + 어댑터로 답변 생성**. 로컬은 설정·대기열·보고서 수신·사람/AI 평가 담당.
- 로컬 RTX 4060 8GB에서 27B BF16 답변을 생성하는 방향으로 바꾸지 마세요. 이 논의는 끝났고 RunPod 답변 생성으로 확정했습니다.
- 모델: `Qwen/Qwen3.8-27B`; revision `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`.
- 모델을 임의로 작은 모델/다른 모델로 바꾸거나 학습 어댑터를 다른 기본 모델에 붙이지 마세요.
- 현재 학습은 가상 샘플 54개/검증 3개입니다. 실제 학습 데이터는 아직 연결하지 않았습니다. 실제 데이터 학습은 사용자의 다음 범위에 따라 별도로 진행하세요.

## 사용자에게 제공하는 사용 방식

사용자는 프리셋/파라미터 수정과 사람 평가만 원합니다. YAML 직접 편집을 요구하지 마세요. 작업 중 등록은 대기열, 우선순위 변경 가능, 기존 실행은 중단하지 않는 구조입니다. 화면 종료·재접속 후 상태와 기록을 조회해야 합니다.

프리셋 P01~P25와 P00 커스텀을 제공합니다. 평가 입력은 `data/eval/prompts.jsonl`의 10개이며 README에 비활성 후보 25개가 있습니다. 기획서에 맞는 개발·운영 직원의 AI/RAG 후보 작성과 부분 수정입니다. 첫 3개는 동일 목표·자료·한도에서 관점만 비용/시간/업무 적용으로 바꿉니다.

기획서: https://docs.google.com/document/d/1pM5mKfXJ8lH4HLiS0aRLpp3iDeYy0MUc/edit?tab=t.0
학습 대상은 후보 작성/수정이며 규정 상담·진단·권한 검사는 별도 시스템입니다. 자료는 검색 제공 목록 ID만 사용하고 실습과 구분하며, 미확정 지원금은 차감하지 않고 수정 요청 밖 변경은 피합니다.

## 주요 코드

- `scripts/local_dashboard.py`: 화면·설정·보고서 수신·현황. 30초 자동 갱신 토글과 수동 갱신. 현재/다음 단계·시간 표시. 사람과 AI 평균 별도 표시.
- `scripts/runpod_client.py`: HTTPS Jupyter REST/WebSocket 연결, 토큰 또는 쿠키 로그인. Cloudflare 회피용 명시적 User-Agent. 비밀값을 로그에 출력하지 않습니다.
- `scripts/runpod_bridge.py`: Linux fcntl 기반 직렬 GPU 대기열. detached worker. `evaluate_existing`은 기존 가중치 평가 전용 작업입니다.
- `scripts/control_pipeline.py`: 등록/학습/평가 순서. `--evaluate-only`는 등록과 학습을 호출하지 않습니다. `--case-limit 2`는 검증용 일부 입력입니다. BF16 완료 캐시 조건이 맞는 입력은 건너뜁니다.
- `scripts/compare_factory_sample.py`: 어댑터와 manifest/hash 검증 후 원본 BF16 모델 로딩. `--case-indices 0 1 ...`로 **에포크별 1회 모델 로딩** 후 입력별 순차 생성·즉시 저장. 기존 `--case-index`도 지원합니다. 입력별 peak GPU 메모리도 기록합니다. 같은 BF16 모델·입력·생성 옵션·토크나이저 해시의 EOS 종료/비잘림 기본 답변은 에포크 간 재사용하고 `base_reused`/출처를 기록합니다. 기본 답변의 표시 시간은 최초 생성 기록입니다. 자동 4비트 대체는 하지 않습니다.
- `scripts/human_reports.py`: 정밀도·평가 입력별 결과 분리. `catalog(root,precision=None/"bf16"/"4bit")`. 사람 점수와 AI 점수는 합치지 않습니다. 제목은 사람 평균입니다.
- `scripts/ai_evaluation.py`: 로컬 OpenAI Responses API + strict JSON schema. 전체 새 답변 자동 평가, 성공 결과 재사용, SQLite 대기열/오류/worker lease. 실패 자동 반복 호출 없음. 같은 답변/모델/규칙만 점수 재사용. 사람 평가와 별도 테이블.

## 파일과 기록을 지키는 규칙

- 평가 DB: `reports/evaluations.sqlite3`. 사람 점수 `case_evaluations`, AI `ai_evaluations`, 자동 작업 `ai_queue`와 lease 테이블. 초기 사람이 평가한 4비트 결과와 새 BF16 결과의 점수를 섞거나 복사하지 마세요.
- `reports/control_history.json`: 마지막 동기화/원격 작업 기록. 오프라인이면 마지막 상태임을 표시합니다.
- 예전 1건짜리 보고서는 `reports/archive/legacy_*`로 보관했습니다. 원래 경로의 작은 `comparison.json`은 `archived:true`인 재동기화 방지 표식입니다. 이를 지우면 오래된 결과가 다시 수신될 수 있습니다.
- 원격 평가 파일은 `data/sample/eval/control_<내용해시>.jsonl`로 보존합니다. 기존 `test.jsonl`을 덮어쓰지 마세요.
- 학습 체크포인트의 원래 `runpod_factory_sample.py`, `factory_state.py`, `db_registry.py` 해시는 재개 검증에 사용합니다. 무심코 수정해서 이전 재개를 깨뜨리지 마세요.
- 전체 체크포인트를 지우거나 학습을 중복 시작하지 마세요. 이번 BF16 검증은 저장된 가중치로만 합니다.

## 연결과 인증

- `.env`: HF_TOKEN, HF_REPO_ID, DATABASE_URL, OPENAI_API_KEY, OPENAI_EVAL_MODEL. 키 내용은 출력/채팅/보고서/업로드 번들에 넣지 마세요.
- OpenAI 모델 기본값 `gpt-4.1-mini-2025-04-14`. Responses API의 `store:false`, 판정 근거와 항목 점수 저장. 입력 대화와 학습 모델 답변만 평가 API로 보냅니다.
- Jupyter 로그인은 Pod의 JUPYTER_PASSWORD/로그인 토큰입니다. HF 토큰/RunPod API 키와 혼동하지 마세요. UI 재연결 후 HF·Neon 인증정보도 적용합니다. Jupyter 비밀번호는 로컬 파일에 저장하지 않는 설계입니다.
- 로컬 환경: `.venv-dashboard` 또는 사용자가 준비한 Conda/Miniforge 환경. `requirements.txt`는 로컬, `requirements-runpod.txt`는 GPU 서버용입니다. requirements 파일을 다시 여러 개로 늘리지 마세요.
- 실행: `.\start_dashboard.ps1` 또는 `.\.venv-dashboard\Scripts\python.exe -m streamlit run scripts/local_dashboard.py`.

## 완료 기준과 다음 범위

인계 시점 검증 상태는 아래 자동 첨부를 먼저 확인하세요. 4비트 샘플에서 이미 학습/저장/보고서/사람/AI 평가 20건을 완료했고, BF16 일괄 평가의 실제 GPU 검증을 추가했습니다. BF16에서 새로 생성한 답변의 사람 점수는 자동으로 만들지 않습니다.

다음 본 작업은 실제 작성·수정 데이터의 스키마/분리/중복/토큰 길이 점검과 샘플 전용 제약 해소입니다. 원본은 `data/raw/dataset.jsonl`인데 아직 placeholder이므로 실제 데이터라고 가정하지 마세요. 기획서의 전체 서비스 완료나 모델 품질 향상을 샘플 통합 시험만으로 주장하지 마세요.

사용자는 불필요한 확인 질문·파일 추가·같은 설명 반복을 싫어합니다. 기존 파일을 수정하고, 가능한 것은 실행·검증한 뒤 결과를 짧게 말하세요. UI는 테두리·영역·색 대비를 갖추고, 1/1 같은 과거 보고서와 현재 실험을 혼동시키지 마세요. 마지막 점수 저장 후 ‘평가 완료’ 안내가 분명해야 합니다.

---

## 인계 시점 검증 상태

BF16 검증 작업 ID: `20261017_015330_f13d664b` (RunPod 시작 시각 2026-10-17 10:53 KST). 이 작업은 재학습하지 않습니다.


검증 시각: 2026-10-17T11:32:33.163816+09:00

- BF16 GPU 작업: 20261017_015330_f13d664b / SUCCEEDED. 재학습 없음.
- BF16 답변 생성: 4·5에포크 각각 10/10 완료, 각 에포크 모델 1회 로딩.
- BF16 OpenAI 자동 평가: 각 10/10 완료.
- 기존 4비트 답변과 사람 평가(각 10/10)는 보존. BF16 사람 평가는 별도 입력이 필요하며 임의 점수로 채우지 않았음.
- 상세 메모리·시간·점수·길이 제한: docs/verification_2026-10-17.json.
- 로컬 테스트: 모델 1회 로딩/복수 입력, 동일 조건 기본 답변 재사용/상이 조건 배제, 위젯 점수 저장/다음 입력 이동/완료 평균 표시, evaluate-only 학습 미호출, BF16 캐시 재개, 보고서 정밀도 분리, 자동 AI 큐·오류·재시도, 사람 평균·재평가, 입력 보존, Jupyter 인증, 화면 렌더 통과.
