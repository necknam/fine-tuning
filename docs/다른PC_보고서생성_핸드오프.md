# 다른 PC 보고서 생성 핸드오프

2026-10-23 사용자 최신 지시. 현재 PC의 GPU로 모델을 실행하지 않는다. 아래 보고서 생성 연결은 사용자가 다른 PC에서 이어서 작업할 범위이며, 현재 PC에서 모델 다운로드·추론·백그라운드 생성기를 자동으로 시작하지 않는다.

## 현재 작업과 경계

현재 RunPod kq65qxmwibvy27에서는 P01을 기존 방식으로 완료하고 이전 저장 가중치의2·5에포크와 개선2·5에포크를 같은 고정10개로 비교한다. 품질이 동등 이상이고 중대한 오류가 늘지 않는다는 출력 내용 검토를 통과할 때만 P02~P06을 진행한다. 이전 데이터와 P01을 재학습하지 않는다.

P02~P06은 RunPod에서 각각 전체1500건·5에포크 학습 후2·5에포크 가중치 저장·원격 백업·해시 검증만 수행한다. 현재 PC에서는 추론하지 않는다. P06까지 저장·외부 검증과 필요한 GPU 작업 종료 후 STOP을 시도하며, 다른 PC 생성기 구현이나 보고서 완료를 기다려 Pod를 유지하지 않는다. 정지 실패/상태 미확인은 사용자 지정 이메일로 알린다.

## 다른 PC에서 만들 흐름

Streamlit Cloud 화면에서 저장 가중치 선택 → 다른 PC의 실행기가 Cloud 생성 요청을 가져옴 → 고정10개 입력으로 모델 답변 생성 → 보고서 및 실행 정보를 Cloud 저장소에 기록 → Cloud에서 결과 확인·평가한다. Cloud가 다른 PC의 GPU에 직접 연결하는 구조가 아니라 다른 PC 실행기가 요청을 가져가는 방식이다. PC는 켜져 있고 실행기가 실행 중이어야 한다.

이 Cloud 요청 큐·다른 PC 실행기·가중치 선택 후 자동 실행 UI는 아직 구현하지 않았다. 실행 가능하다고 간주하지 않는다. 현재 PC에서27B 로컬 추론을 실제 검증한 기록도 없다.

## 이미 구현된 코드와 저장 형식

- qwen_factory/scripts/runpod_bridge.py: train_save_only 종류를 사용한다. experiment는 답변 생성까지 포함하므로 P02 이후에는 사용하지 않는다.
- qwen_factory/scripts/control_pipeline.py --train-save-only: 등록→학습→가중치 업로드→외부 검증과 묶음 저장 후 반환한다. 답변 생성 경로로 들어가지 않는다.
- qwen_factory/scripts/local_evaluation_bundle.py: P01에서 이미 생성한 고정10개 receipt를 읽기만 한다. 새 직원 DB 조회/스냅샷 생성은 하지 않는다. 에포크별 HF commit과 manifest 파일 해시를 내려받아 검증한다.
- 승인된 private HF 모델 저장소의 local_evaluation/<run_id>/bundle.json과 fixed10.jsonl: 고정입력 SHA256, 모델 ID/revision, 학습 설정/해시, epoch2/5 weight_id, 각 adapter HF repo/revision/subfolder 및 파일 SHA256, greedy 생성 조건을 포함한다. repo ID/인증은 기존 설정에서 읽고 토큰을 문서에 넣지 않는다.
- 생성 묶음은 해당 프리셋 저장 전용 작업이 성공한 후에만 실제 존재한다. 현재는 P01 진행 중이므로 P02~P06 묶음이 이미 저장됐다고 가정하지 않는다.
- 전체 테스트98개 중97개 통과·1개 건너뜀. 저장 전용 경로의 답변 생성 방지와 고정입력 변조 거부 등을 확인했다. 실제 P02~P06 완료를 뜻하지 않는다.

## 구현 시 유지할 조건

1. 기존 승인된 인증은 해당 다른 PC에서 안전하게 설정한다. 비밀번호·토큰·DB 연결 문자열을 Git/문서/로그에 넣지 않는다.
2. 현재 PC에 저장된 인증이 다른 PC로 자동 이전된다고 가정하지 않는다. 다른 PC의GPU·VRAM·RAM·디스크를 확인한 뒤 별도 가상환경에 필요한 모델 런타임을 준비한다.
3. 가중치와 base model revision을 고정하고 파일 SHA를 검증한다. fixed10.jsonl은 bundle의 해시와 일치해야 한다. 로컬 DB는 수정하지 않으며 비교 입력을 새로 만들거나 직원 배정을 바꾸지 않는다.
4. 선택한 weight_id+고정입력해시+생성조건+실행정밀도로 작업을 구분한다. Cloud 재실행/연결 단절로 중복 생성하지 않도록 작업 잠금·heartbeat·실패 복구·입력별 재개를 구현한다. 가중치를 선택한 후 동일10개 입력이 자동으로 들어가도록 한다.
5. GPU 작업은 Cloud 서버에서 수행하지 않는다. 다른 PC 실행기가 요청을 가져가 모델을 실행한다. PC가 꺼져 있거나 실행기가 없으면 대기 상태로 표시한다.
6. Qwen/Qwen3.8-27B의 BF16 전체 모델은 약55GB 규모다. 해당 PC 자원에 맞춰 실행 가능 여부와 속도를 실제 검증한다. 양자화/정밀도를 바꾸면 기록하고 같은 환경의 P01 기준 출력도 생성해 비교한다. 현재 RunPod P01 비교를 임의로 변경하지 않는다.
7. 생성 상한4096, greedy/do_sample=false,num_beams=1,use_cache=true 등 bundle 조건을 유지한다. 토큰 초과/잘림/오류를 성공으로 처리하지 않는다. 출력 내용에 대한 에이전트 검토와 사용자 평가 점수를 구분한다.
8. 기존 comparison.json 및 practical_reports/human_reports 표시·평가 형식에 맞춰 Cloud 저장·재조회와 화면을 검증한다. 문자열 형식 보고서 렌더링 자체에는 모델/GPU가 필요 없다. 모델 답변 생성과 렌더링을 구분한다.

## 이어받을 때 먼저 확인

docs/CODEX_HANDOFF.md와 docs/CLOUD_WORKFLOW.md를 읽고 최신 Git main을 확인한다. 실행 계획은 현재 제어 PC의 Documents/Codex/conditional-p02-p05-plan.json, 원격 계획은 Pod outputs/conditional_p02_p05/plan.json이며 파일명과 달리 P06까지 포함한다. Pod가 정지됐으면 HF 묶음과 Cloud 메타데이터로 복원하고 단지 보고서를 만들기 위해 Pod를 다시 켜거나 재학습하지 않는다. 보고서 생성은 사용자의 후속 작업으로 남긴다.
