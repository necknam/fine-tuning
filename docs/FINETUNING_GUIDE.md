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


## 2026-10-26 · Qwen3.5-4B / 동일 B200 / 확장 3,000건 P01

사용자 지정으로 GPU는 B200을 유지하고 모델만 `Qwen/Qwen3.5-4B`로 바꾼 별도 실행 경로를 추가했다. 기존 27B 프리셋·실행·가중치·UI 기본값은 과거 실험용으로 보존했다. 기존 27B 버튼이나 `run_b200_trial.py`는 이 4B 실행 명령이 아니다. 27B 어댑터를 4B에 로드하거나 이어 학습하지 않는다.

| 항목 | 4B 신규 설정 |
|---|---|
| 설정 | `qwen_factory/configs/hyperparameters.qwen35_4b_3000.P01.yaml` |
| 실행 | `qwen_factory/scripts/qwen35_b200_runner.py` |
| 모델 revision | `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a` (공개 HF 메타데이터로 확인) |
| GPU·정밀도 | B200 1장, sm100, BF16 LoRA, 기본모델 양자화 없음 |
| P01 | LR 0.0001, r32/alpha64/dropout0.05, weight decay0.01 |
| 학습 | batch1 × accumulation16, max10240, packing=false, 최종 assistant만 loss |
| 에폭·저장 | 총5에폭 단일 cosine·warmup5%, 2·5에폭 어댑터 저장 |
| 재개 | 에폭별 optimizer/scheduler/RNG 포함 checkpoint, 명시적 `--resume`만 |
| 속도 시험 | 전체 길이분포에서 60건 선택(최단·최장 포함), 독립1에폭·4업데이트 |
| 본학습 | 기본모델부터 새로 시작, 188업데이트/에폭·총940 예상 |
| 비교 | 개정된 `prompts.app_v2.jsonl` 고정10개(4~12주, Case 7 12주, Case 10 일반 보고서 자동화, SHA `7c1565e2...`), 원본/학습 답변을 2·5에폭 각각 저장 |

5에폭과 저장 시점은 이번 P01의 기준 설정이며 4B의 최적 에폭으로 확인된 값이 아니다. 시험 마지막 불완전 업데이트와 첫 컴파일 업데이트는 평균 step 시간에서 제외한다. 학습 업데이트 시간과 저장·비교·전체 경과는 구분한다. 60건 유한손실·GPU 예약 메모리95%미만·실제 step 측정·동일 데이터/설정/환경/코드 해시를 만족해야 본학습을 실행한다. 60건 학습 가중치를 본학습에 이어 쓰지 않는다.

### 현재 검증된 범위와 차단 상태

설정·검토 gate·원본보존·중복·토큰 잘림 차단·마스킹·시험 조건의 신규7개 검사와 기존 loss6개/백엔드3개, 총16개가 통과했다. 로컬 check는 `BLOCKED_DATA_NOT_READY`를 반환했다. 데이터 신규1,500건 제작·5회 검토는 아직 미완료다. 실제 4B 모델 가중치 다운로드, B200 forward/backward·60건 시험·메모리·속도·본학습은 수행하지 않았다. 기존 27B B200 커널 실측은 4B 실측으로 간주하지 않는다.

### RunPod 실행 순서

데이터 release 검토 완료 후 이 전용 패커로 업로드 ZIP을 만든다. 준비 전에는 패커도 차단한다. 기본 ZIP 최상위는 `qwen_factory/` 하나이며 `/workspace`에 풀면 중첩 없이 `/workspace/qwen_factory`가 된다. `.env`·키·모델 가중치는 포함하지 않고 원본1500·신규포함3000·검토근거·고정10개·고정 requirements·실행코드만 포함한다.

```powershell
# 로컬 qwen_factory 폴더에서 데이터 확정 후에만
& "$env:USERPROFILE\miniforge3\envs\llm_env\python.exe" scripts/pack_qwen35_b200.py --output D:/qwen_factory_local/bundles/qwen35_4b_3000_P01.zip
```

새 Pod 구매·시작·삭제는 이 변경에 포함하지 않는다. 사용자가 제공한 동일 B200 연결에서 이 프로젝트를 `/workspace/qwen_factory`로 올리고 ZIP 해시·경로를 확인한 다음 수행한다. 현재는 로컬 수정만 했으며 Pod 업로드·Git push는 하지 않았다.

```bash
cd /workspace/qwen_factory
# 기존에 검증된 B200 환경이면 재설치 없이 우선 버전을 확인한다.
# 새 환경 준비가 필요한 경우에만 기존 고정 requirements를 아래 두 단계로 설치한다.
python -m pip install -r requirements-runpod.txt
python -m pip install --no-deps -r requirements-kernel-b200.txt

# GPU/다운로드/DB 연결 없이 준비 상태 확인
python scripts/qwen35_b200_runner.py --phase check

# 3000건 검토 release가 준비되고 B200 연결을 확인한 뒤에만 실행
# 60건 시험 -> 새 기본모델 3000건 학습 -> 저장한 2/5에폭 각각 고정10개 비교
python -u scripts/qwen35_b200_runner.py --phase all --execute
```

개별 단계는 `--phase sample`, `--phase train`, `--phase compare`다. 중단 원인을 수정하고 optimizer/scheduler/RNG checkpoint를 검증한 경우에만 `--phase all --execute --resume`으로 본학습을 재개한다. 불완전 60건 시험은 자동 재실행하지 않는다. 같은 구성의 완료 학습과 같은 어댑터·입력의 완료 비교는 재실행하지 않는다. 기존 GPU 작업과 같은 `outputs/control_jobs/gpu.lock`을 사용하고 잠금 외 GPU compute 프로세스도 있으면 중단한다.

캐시는 `/dev/shm/qwen35_4b_model_cache`, Triton/컴파일 캐시는 `/tmp`를 사용한다. 실행 전에 RAM 캐시12GiB·결과 경로10GiB 여유를 확인한다. 결과는 `outputs/qwen35_4b_3000_P01/<설정해시앞16자리>/`에 저장한다. 각 어댑터 파일 SHA를 기록·검증한다. `/workspace`가 영구볼륨인지 확인하고, Pod 삭제 전 가중치·결과·checkpoint를 로컬/영구볼륨에 별도로 복사해 SHA를 확인해야 한다. 이 러너는 HF 업로드·Neon 등록·유료 AI 채점·자동 품질 합격을 하지 않는다. 비교 후 실제 답변 검토와 기존 보고서 갱신은 별도 후속 작업이다.

### 3,000건 release 계약

확정 후보는 `data/production/expanded_3000/all.jsonl`, 검토 완료 gate는 같은 폴더의 `release_manifest.json`이다. 원본 `data/revision_1500/assembled/all.jsonl`의 SHA `998a9499a14f6c08de0526919567bcf5a9fcf31642f75aa24fca143c51265529`와 앞1,500행을 그대로 보존한다. 신규1,500건의 출처와 300건씩5회 제작/리뷰/독립검사 기록이 필요하다. 원래 존재하는 의미상 한계는 보고서에 남기며 자동 전수 검사를 전수 의미 합격으로 표현하지 않는다.

release 필수값: `status: REVIEWED_CANDIDATE`, `blocking_findings: 0`, `records: 3000`, `data_sha256`, `original_sha256`, `rounds` 5개, `automatic_checks`, `provenance`. 각 round는 `round: 1..5`, `new_records: 300`, `status: REVIEW_COMPLETE`, 실제 `reviewed_sample_count > 0`, 세 역할 `maker/reviewer/inspector` 기록을 가진다. 각 기록·checks·provenance는 `{path: 프로젝트 상대경로, sha256: 파일SHA}` 형태이며 내용이 바뀌면 차단한다. checks 파일은 `status: PASS`, `checked_records: 3000`, provenance는 신규1,500행이다. 검토되지 않은 후보에 ready 값을 임의로 채워 실행하지 않는다.

자료가 준비돼도 4B 토크나이저로 3,000건을 다시 인코딩해 prefix 마스크와 실제 길이를 전수 확인한다. 10240 초과는 자르거나 버리지 않고 오류로 멈춘다. 고정 평가 SHA `7c1565e23373411d1adf5ef50c31ac8842ad68b92fb9c3610440ea1cc411cafe`는 유지하고 학습 입력과 정확히 겹치면 차단한다.

공식 모델·구조: https://huggingface.co/Qwen/Qwen3.5-4B · https://huggingface.co/Qwen/Qwen3.5-4B/blob/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a/config.json


로컬 준비 검증: `qwen_factory/check_qwen35_local.ps1`은 전용 Miniforge 환경에서 pip check와 GPU 없는 profile/data check만 실행한다. 패키지 정합성 PASS·새 환경에서도16개 검사 PASS. 상세 증거는 `qwen_factory/outputs/qwen35_4b_preparation_20261026/readiness.json`. 데이터 미완료 상태는 정상적으로 차단하며, RunPod 연결·시작·모델 가중치 다운로드를 하지 않는다.
