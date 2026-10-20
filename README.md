# GrowPath Qwen Factory

Streamlit 대시보드에서 **파라미터 수정·실험 등록·사람/AI 평가**를 합니다. RunPod는 GPU 학습과 답변 생성을 실행하고, 기록은 Neon에 저장합니다.

현재 확정 상태와 남은 일은 [DB·데이터·학습 통합 보고서](docs/CODEX_HANDOFF.md), 실행 순서는 [파인튜닝 가이드](docs/FINETUNING_GUIDE.md)를 참고하세요.

실제 데이터는 총 1,500건(학습 1,200 / 검증 150 / 별도 평가 150)이며 공통 비교 입력 10개는 별도입니다. HF·Neon 연결은 확인됐고 본 데이터의 GPU 학습은 아직 실행하지 않았습니다.

## 샘플 시험과 실제 데이터 학습

- 화면의 **학습 데이터 구분**에서 샘플 시험 또는 실제 데이터 학습을 선택합니다.
- 실제 학습은 학습/검증 `messages` JSONL을 각각 업로드합니다. 필요하면 평가 입력도 별도로 올립니다. 본 데이터는 Git에 올리지 않습니다.
- **새 실험 등록**은 같은 파라미터라도 새 실행 ID를 만듭니다. 데이터 내용 해시와 샘플/실제 모드도 식별에 포함하며, 기존 완료 가중치를 자동 재사용하지 않습니다.
- 중단된 작업의 **이어하기**와 **기존 가중치 평가**는 실행 이력/보고서에서 명시적으로 선택합니다.
- 보고서는 샘플/실제를 구분하고 입력을 위, 답변 보고서를 아래에 전체 너비로 표시합니다.
- AI 평가 기준은 **엄격 v3 (`growpath_judge_v3_evidence`)**입니다. 이전 점수는 이력으로 남기고 새 규칙으로 별도 평가합니다. 자동 평가를 켜면 새 기준에 대한 API 비용이 발생합니다.

## 화면 조회 방식

열린 탭만 실행합니다. 첫 화면에서 꺼진 RunPod에 접속을 시도하지 않습니다. 실행 현황 자동 갱신은 기본 OFF이며 필요할 때 **지금 갱신**, **새 보고서 확인**, **AI 결과 갱신**을 누릅니다.
파라미터 수정이나 설명 탭에서 모든 보고서를 조회하지 않습니다. 점수는 묶어서 조회하고, 문서는 바뀐 내용만 내려받습니다.
화면 조회를 멈춰도 이미 시작한 RunPod 작업과 별도 AI 평가 프로세스는 독립적으로 진행합니다.

## 빠른 시작 · 로컬 Windows

프로젝트 폴더에서 PowerShell을 열고 실행합니다.

```powershell
.\start_dashboard.ps1
```

브라우저에서 `http://127.0.0.1:8501`을 엽니다. 실행 스크립트는 프로젝트 안의 `.venv-dashboard`를 사용합니다.
처음 실행할 때 환경과 패키지를 설치합니다. 기존 환경의 패키지를 강제로 변경하지 않습니다.

직접 설치·실행하려면 아래 명령을 사용합니다.

```powershell
python -m venv --system-site-packages .venv-dashboard
.\.venv-dashboard\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-dashboard\Scripts\python.exe -m pip check
.\.venv-dashboard\Scripts\python.exe -m streamlit run scripts/local_dashboard.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

Python 3.12를 기준으로 확인했습니다. Conda를 쓴다면 먼저 `conda activate qwen-factory`로 활성화하세요.
환경이 없으면 `conda create -n qwen-factory python=3.12 pip -y`로 만듭니다.
PowerShell이 스크립트 실행을 차단하면 보안 설정을 바꾸는 대신 위 직접 실행 명령을 사용합니다.

## requirements는 두 개

| 파일 | 설치 위치 | 포함 내용 |
| --- | --- | --- |
| `requirements.txt` | 로컬 PC / Streamlit Cloud | Streamlit, Jupyter 연결, YAML, HF·DB 클라이언트 |
| `requirements-runpod.txt` | RunPod Linux | 시험한 GPU 학습·추론 패키지와 HF·DB 클라이언트 |

로컬에 GPU requirements를 설치할 필요가 없습니다. 이전 local/lock/smoke/factory/dashboard/verified 파일과
별도 constraints는 통합했습니다. `packaging @ file:///home/conda/...` 같은 이전 머신의 절대 경로도 제거했습니다.
이전 원본은 `outputs/legacy_requirements`에 보관하며 설치 입력으로 사용하지 않습니다.
이 두 파일은 직접 의존성 버전을 고정한 것이며 모든 간접 의존성을 잠근 lock 파일은 아닙니다.

## 처음 한 번 연결

1. 왼쪽에 Pod의 Jupyter HTTPS 주소와 토큰 또는 비밀번호를 입력하고 `연결`을 누릅니다.
   RunPod의 `JUPYTER_PASSWORD` 또는 Jupyter 로그인 화면에 사용한 값입니다. HF 토큰·RunPod API 키와 다릅니다.
2. Jupyter 파일 브라우저 기준 경로는 보통 `workspace/qwen_factory`입니다.
   서버 루트가 `/workspace`라면 `qwen_factory`를 입력합니다.
3. `HF·Neon 인증정보`를 열어 HF_TOKEN, HF_REPO_ID, DATABASE_URL을 적용합니다.
4. 안내 탭의 GPU를 사용하지 않는 연결 시험을 실행합니다.

주소와 파일 브라우저 경로만 로컬 설정에 저장합니다. 토큰은 파일에 저장하지 않습니다.
HF·Neon 값은 사용자가 적용 버튼을 누를 때 HTTPS로 해당 Pod의 제어 커널에 전달하며 원격 파일에 저장하지 않습니다.
대시보드를 새로 연결하거나 Pod를 재시작했다면 인증정보를 다시 적용합니다.
로컬 `.env`가 있으면 HF·Neon 입력칸에 불러오며 `.env` 자체를 업로드하지 않습니다.

SSH 키 없이 기존 Jupyter 서비스로 연결합니다. 현재 Linux 프로젝트 경로는 `/workspace/qwen_factory`입니다.
제어용 커널을 별도로 만들기 때문에 기존 노트북의 셀과 저장 내용을 바꾸지 않습니다.

## 매일 하는 일

### 파라미터 수정

`파라미터·실험 대기열`에서 추천 프리셋을 고른 뒤 학습률, LoRA r/alpha/dropout,
배치, 누적 횟수, 최대 토큰 길이, 가중치 감쇠, 워밍업, 스케줄, 시드를 수정합니다.
YAML은 내부 작업지시서로 자동 저장하므로 직접 편집할 필요가 없습니다.
추천 25개의 목적과 변경점은 Streamlit의 **최초 연결·새 Pod 안내 → 추천 파라미터 25개**에서 확인합니다.

`실험 등록` 한 번으로 다음 순서가 실행됩니다.

1. 설정·데이터 해시로 실험 등록과 중복 확인
2. 5에포크 학습 또는 기존 체크포인트에서 재개
3. 4·5에포크 어댑터 각각 저장, HF 업로드, Neon 상태 갱신
4. 고정한 샘플 평가 입력 전체에 대해 기본 모델·어댑터 답변 생성
5. 로컬로 보고서와 실제 실행 파라미터 자동 수신

현재 연결된 학습기는 **가상 샘플 54/3/3의 5에포크 통합 시험용**입니다.
실제 3,000개 데이터에 대한 학습기로 완성됐다는 뜻은 아닙니다.
새 설정의 학습·추론은 GPU 시간과 저장공간을 사용합니다. 25개 프리셋을 자동으로 모두 실행하지 않습니다.

### 실행 순서

실행 중인 작업은 그대로 두고 새 실험은 대기열에 들어갑니다. 우선순위는 높은 항목부터,
같은 우선순위에서는 먼저 등록한 작업부터 실행합니다. `다음 실행으로`는 대기 작업만 앞으로 옮깁니다.
낮은 숫자가 높은 우선순위입니다. 실행 상태·로그는 5초마다 갱신합니다.
한 실험의 학습과 비교 생성까지 끝난 뒤 다음 실험으로 넘어갑니다.

대기 작업은 제출 시점의 파라미터와 데이터를 사용합니다. 이후 화면에서 값을 바꿔도 이미 등록한 실험은 바뀌지 않습니다.
같은 명령이 실행·대기 중일 때 재등록하면 중복 작업을 추가하지 않습니다.
로컬 화면을 닫아도 Pod가 살아 있으면 분리 실행 중인 작업과 대기 작업은 계속됩니다.
Pod 중지·삭제 후에는 프로세스가 유지되지 않습니다. 중단 작업은 자동으로 새 학습하지 않으며
환경·파일을 복구한 뒤 같은 설정으로 다시 등록해 재개합니다.
별도로 SSH/Jupyter에서 GPU 작업을 실행하면 이 대기열이 추적하지 못하므로 중복 실행하지 마세요.

진행 기록은 RunPod의 `outputs/control_jobs/<job_id>/job.json`, `job.log`에 남고,
화면을 보는 동안 로컬 `reports/control_history.json`에도 마지막 확인 기록을 저장합니다.
Streamlit을 다시 열면 연결 전에도 마지막 상태·진행 단계·로그를 볼 수 있으며, 재연결하면 실제 상태로 갱신합니다.
등록·시작·종료 시각은 한국 시간으로 표시하고, 최근 10개 외에 `지난 실험 전체 보기`도 지원합니다.
로컬에 저장된 상태가 실행 중이어도 재연결 전에는 실시간 상태라고 단정하지 않습니다.

실패·중단한 실험은 연결과 HF·Neon 인증정보 적용 후 `이 실험 이어하기`를 누릅니다.
원래 설정으로 대기열에 등록하고 전체 체크포인트에서 재개합니다. 이미 학습이 끝났다면
남은 비교 생성을 진행합니다. 원래 실행 폴더가 없으면 처음부터 학습하지 않고 실패로 남깁니다.
실패 원인이 데이터·패키지·인증·업로드라면 로그의 원인을 해결한 뒤 이어가야 합니다.

### 보고서 평가

`보고서 평가`는 통합 실험 목록입니다. 실험명·모델·학습률·LoRA r·평가 진행률·평균으로 찾아
보고서를 열고, 입력 하나당 답변을 읽어 **종합 1~5점**을 저장합니다. 입력이 25개면 25건을 평가합니다.
입력은 목표·수준·기간·시간·예산·자료 카드로, 답변은 단계별 활동·결과물·완료 기준으로 보여줍니다.
기본 모델 답변과 원본 JSON은 필요할 때 펼쳐봅니다.
`저장하고 다음 미평가 입력`으로 넘길 수 있고, 이미 평가한 입력만 따로 다시 볼 수도 있습니다.
평가 도중 자동 새로고침하지 않으며 `새 보고서 확인`으로 새로 받은 답변을 목록에 반영합니다.

- 후보마다 가중치 ID와 연결된 `v1`, `v2` 등의 고정 버전을 부여합니다.
- 입력별 종합 점수의 산술평균으로 제목을 `v1_2.5(5점 만점)`처럼 표시합니다.
- 미평가 입력은 평균에서 제외하고, 완료 개수·진행률·임시 평균 여부를 함께 표시합니다.
- 평가자가 여러 명이면 입력별 최신 점수를 먼저 평균하고, 입력들을 같은 비중으로 평균합니다.
- 같은 사람이 같은 입력을 다시 평가하면 최신 점수를 반영하고 이전 이력도 DB에 남깁니다.
- 답변·입력·생성 조건이 바뀐 사례는 예전 점수를 자동으로 재사용하지 않습니다.
- Markdown 보고서에도 모델·파라미터·입력·답변·사람 점수·평균을 포함합니다.
- 자동 품질 점수나 자동 최종 가중치 선정은 하지 않습니다.

평가 이력은 Neon의 `qf_dashboard` 스키마에 모읍니다. 입력마다 CSV·JSON 파일을 만들지 않습니다.
평소에는 Streamlit만 사용하고, 필요할 때 선택 보고서 Markdown 또는 전체 실험 목록 CSV를 내려받습니다.
기존 JSON 평가 이력이 있다면 보존합니다. 비교 원본 JSON은 프로그램 내부 자료로 유지합니다.
현재 사람 평가 기록의 Neon 자동 동기화는 미구현입니다. 실험·가중치 상태는 기존 Neon 코드를 사용합니다.

## 데이터를 수정하는 위치

샘플 모드는 `configs/hyperparameters.sample.pinned.yaml`을 기준으로 사용합니다. 실제 모드는 화면에서 학습·검증 JSONL을 업로드해 실행에 연결합니다.
화면의 `현재 데이터 위치`에서도 프로젝트의 실제 절대 경로를 확인할 수 있습니다.

| 용도 | 프로젝트 기준 파일 | 현재 연결 |
| --- | --- | --- |
| 샘플 학습 | `data/sample/processed/train.jsonl` | 학습에 사용 |
| 샘플 검증 | `data/sample/processed/validation.jsonl` | 에포크별 검증에 사용 |
| 기존 간이 평가 | `data/sample/eval/test.jsonl` | 이전 1개 입력 시험용 |
| 현재 기본 평가 예시 | `data/eval/prompts.jsonl` | 새 실험 기본 입력 10개; 별도 업로드로 교체 가능 |
| 본 데이터 원본 | `data/raw/dataset.jsonl` | 본 데이터 작성 위치; Git 제외 |
| 본 학습 분리본 | `data/processed/train.jsonl` | 원본 전처리 후 생성; 실제 모드에서 업로드해 연결 |
| 본 검증 분리본 | `data/processed/validation.jsonl` | 원본 전처리 후 생성; 실제 모드에서 업로드해 연결 |
| 본 평가 분리본 | `data/eval/test.jsonl` | 원본 전처리 후 생성; 실제 모드에서 업로드해 연결 |

본 데이터는 원본 JSONL을 수정한 뒤 아래 명령으로 검증·분리합니다.
현재 예시 1개로는 실행되지 않으며 최소 20개의 서로 다른 첫 사용자 프롬프트 그룹이 필요합니다.

```powershell
python scripts/prepare_data.py --input data/raw/dataset.jsonl
```

각 줄은 다음처럼 `messages`만 포함하며, 마지막 메시지는 assistant 정답입니다.

```json
{"messages":[{"role":"system","content":"역할·출력 규칙"},{"role":"user","content":"목표·조건·자료 또는 수정 요청"},{"role":"assistant","content":"검토한 정답"}]}
```

`prepare_data.py`는 첫 사용자 프롬프트를 정규화해 그룹을 나눕니다. 표현이 다른 같은 사례의 파생본까지
자동으로 알아내지는 못하므로 원본 작성·분리 시 별도 검토가 필요합니다. 이미 출력이 있으면 덮어쓰지 않습니다.
학습 사례가 검증·평가에 섞이지 않게 하고, 비교 중에는 평가 입력을 고정하세요.

본 데이터는 파일만 수정해 두는 것으로 실행에 연결되지 않습니다. 화면에서 **실제 데이터 학습**을 선택하고 준비한 학습·검증 파일을 업로드하세요. 평가 입력도 별도로 선택할 수 있으며, 내용 해시를 붙인 스냅샷을 새 실험에 연결합니다.
샘플 파일을 직접 수정해 행 수가 달라지면 pinned 설정의 `expected_train_samples`도 일치해야 합니다.
평가 입력도 내용 해시를 붙인 별도 스냅샷으로 올려 실험 설정에 연결합니다.
원격의 기존 `test.jsonl`을 덮어쓰지 않으므로 다른 실행의 평가 입력과 충돌하지 않습니다.

## 새 RunPod 만들기

### Pod와 디스크

A100 80GB 1장, Python 3.12, CUDA PyTorch 2.8.0+cu128을 기준으로 GPU 시험을 통과했습니다.
다른 환경은 별도 검증이 필요하며 현재 시험 코드는 A100 80GB만 허용합니다.
8888 Jupyter 서비스를 켜고 새 주소와 로그인 토큰을 확인합니다.

`/workspace`가 어떤 저장소에 연결됐는지 Pod 설정에서 확인합니다.
Pod 삭제 후에도 보존하려면 별도로 유지하는 Network Volume 또는 외부 백업이 필요합니다.
GPU 가중치 다운로드 캐시·재개용 체크포인트·실험 폴더의 보존 여부를 함께 확인하세요.

### 코드 올리기

로컬에서 다음 명령으로 설치 ZIP을 만듭니다.

```powershell
.\.venv-dashboard\Scripts\python.exe scripts/pack_runpod_upload.py
```

`outputs/runpod_control_bundle.zip`을 Jupyter 파일 브라우저의 `/workspace`에 업로드합니다.
이 ZIP에는 코드·기본 설정·샘플 데이터·GPU requirements와 README만 포함됩니다.
토큰·`.env`·가중치·캐시·평가 이력은 포함하지 않습니다.

새 Pod의 Jupyter 터미널에서 한 번 실행합니다.

```bash
mkdir -p /workspace/qwen_factory
cd /workspace/qwen_factory
python -m zipfile -e /workspace/runpod_control_bundle.zip .
python -m venv --system-site-packages .venv-runpod
.venv-runpod/bin/python -c "import sys,platform,torch; assert sys.version_info[:2]==(3,12) and platform.machine()=='x86_64'; assert torch.__version__.split('+')[0]=='2.8.0' and torch.version.cuda.startswith('12.') and torch._C._GLIBCXX_USE_CXX11_ABI; print(torch.__version__,torch.version.cuda,torch.cuda.is_available())"
.venv-runpod/bin/python -m pip install -r requirements-runpod.txt
.venv-runpod/bin/python -m pip check
.venv-runpod/bin/python scripts/runpod_smoke.py --output outputs/environment_check_new
```

GPU 커널은 공식 `causal-conv1d` 1.7.0 휠과 `flash-linear-attention`/`fla-core` 0.5.2를 사용합니다. 위 휠은 Linux x86_64·Python 3.12·torch 2.8·CUDA 12·CXX11 ABI=True 전용입니다. 환경이 다르면 해당 조합의 공식 휠을 확인해야 하며 torch를 임의로 업그레이드하지 마세요. [공식 causal-conv1d](https://github.com/Dao-AILab/causal-conv1d), [공식 FLA](https://github.com/fla-org/flash-linear-attention).



PyTorch 출력이 시험한 CUDA 환경인지 확인하고 설치합니다. CPU PyTorch 환경이라면 CUDA용 템플릿을 먼저 준비합니다.
마지막 환경 검사 명령에는 `--execute`가 없어 모델 가중치 다운로드나 학습을 시작하지 않습니다.
같은 출력 폴더가 이미 있다면 다른 이름을 사용합니다.
로컬 화면에서 주소·토큰을 새 값으로 바꾸고 연결·인증정보 적용·연결 시험을 진행하면 됩니다.

### 보관과 복구

| 대상 | 보관 위치 | 새 Pod에서 복구 |
| --- | --- | --- |
| 코드·기본 설정·샘플 | 로컬 프로젝트 | 설치 ZIP |
| GPU 직접 의존성 버전 | `requirements-runpod.txt` | 설치 후 `pip check` |
| 모델 캐시 | `/workspace/qwen_factory/.cache/huggingface` | 볼륨 유지 또는 재다운로드 |
| 평가용 어댑터 | HF 비공개 저장소 | Neon의 repo/revision/subfolder로 다운로드 |
| 실험·가중치 장부 | Neon | 같은 DATABASE_URL |
| 전체 체크포인트·runtime manifest | `outputs/factory_sample/<run_id>` | 볼륨 또는 별도 백업 |
| 제어 작업 상태·로그 | `outputs/control_jobs` | 볼륨 또는 별도 백업 |
| 비교 보고서·실행 설정 | 로컬 `reports` | 로컬 백업 |
| 사람 평가 기록·점수 보고서 | 로컬 `reports` | 로컬 백업 |

어댑터만으로 학습을 정확히 재개할 수 없습니다. optimizer, scheduler, Trainer/RNG 상태와
동일 코드·환경을 포함하는 전체 체크포인트가 필요합니다. 원래 `runtime_manifest.json`과
실행 설정도 함께 보존하세요. 없는 파일을 임의로 만들어 재개 검사를 우회하지 않습니다.
HF 어댑터로 비교할 때도 `factory_manifest.json`과 해당 실험의 `runtime_manifest.json`이 필요합니다.

## 오류 해결

- `Missing environment variable`: 화면에서 HF·Neon 인증정보를 다시 적용합니다.
- `already has a local directory`: 폴더를 지우지 말고 기존 체크포인트로 재개합니다.
- `Runtime/config changed`: 원래 코드·패키지·설정을 복원해야 기존 실험을 재개할 수 있습니다.
- `Jupyter HTTP 403`: 메시지의 실패 단계(GET/POST 경로)를 확인합니다. Pod의 `JUPYTER_PASSWORD` 또는
  Jupyter 로그인 값을 입력하세요. 연결기는 토큰 인증 실패 시 일반 로그인 쿠키 인증도 시도하며,
  인증을 끄거나 XSRF 검사를 우회하지 않습니다.
- `Cloudflare 1010`: Jupyter 인증 전에 RunPod 프록시가 클라이언트를 거절한 경우입니다.
  연결기는 `GrowPathLocalDashboard/1.0` User-Agent를 명시합니다. 오래된 연결 코드를 사용 중인지 확인하세요.
- `Jupyter file or kernel not found`: 파일 브라우저 경로를 확인하거나 다시 연결합니다.
- SSH `id_ed25519` 없음: 현재 PC에 해당 키가 없는 상태입니다. 이 화면은 Jupyter로 연결하므로 SSH가 필수는 아닙니다.
- 노트북 `File Changed`: 저장본과 열린 내용을 확인한 뒤 선택합니다. 로컬 대시보드는 노트북 파일을 저장하지 않습니다.
- 이전 lock의 `/home/conda/...` 경로 오류: 통합한 로컬 `requirements.txt`로 설치합니다.

## 구현과 검증 범위

기존 Pod에서 샘플 5에포크, 4·5에포크 HF 업로드와 DB 상태 갱신, 비교 생성 성공을 확인했습니다.
로컬 화면 렌더링·프리셋 전환·보고서 평균과 재평가 이력은 자동 검사했습니다.
새 Streamlit 제어기로 P01 등록·학습·4/5에포크 각각 10개 답변 수신을 완료했고 사람·AI 평가 각 20건의 저장과 화면 표시를 확인했습니다. BF16 추가 검증 상태는 보고서와 인계 문서의 최신 확인 기록을 참조하세요.
GPU 학습을 중복 실행해 검증하지 않습니다.

참고: [Jupyter REST API](https://jupyter-server.readthedocs.io/en/latest/developers/rest-api.html),
[Jupyter 커널 메시지](https://jupyter-client.readthedocs.io/en/stable/messaging.html).

## 평가용 입력 프롬프트

로컬 `data/eval/prompts.jsonl`을 수정합니다. 고정 난도 평가 10개(동일 조건의 3관점 비교, 자료 없음·0원, 시작 단계/자기평가 충돌, 미확정 지원금, 모순·불충분 입력, 자료 속 지시 무시, 부분 수정 2개)가 들어 있습니다. 첫 3개는 같은 목표·예산·시간에서 관점만 다르게 비교합니다. 기존 보고서에는 소급 적용하지 않으며 새 실험부터 사용합니다. 학습 데이터와 별도이며 정답은 필요하지 않습니다.

학습·평가 범위는 **GrowPath 개발·운영 직원용 AI 학습 로드맵 생성·부분 수정**에 집중합니다. 범용 대화나 다른 직무 전반으로 확장하는 목적이 아닙니다. RAG 시제품은 학습 목표의 예시이며 모델이 직접 시스템을 구현하거나 규정 승인·진단을 대신하는 역할은 아닙니다.

고정 평가 10개는 다음 실패 유형을 구분합니다. 1~3번은 같은 조건에서 활동 선택과 시간 배분이 관점별로 달라지는지 비교합니다.

| 입력 | 핵심 확인 사항 |
| --- | --- |
| 1~3 | 비용·시간·업무 적용 관점의 실질적 차이, 6시간·2만원 한도 |
| 4 | 자료 없음·예산 0원에서도 가능한 직접 실습 |
| 5 | 확정 시작 단계 3 준수, 낮은 자기평가로 경력·의지를 단정하지 않기 |
| 6 | 미확정 지원금을 차감하지 않고 현 예산으로 계획하기 |
| 7 | 0주·불명확 목표에서는 임의 계획 대신 필요한 확인 질문 반환 |
| 8 | 자료 본문 속 명령을 사용자 지시로 따르지 않기 |
| 9 | 지정한 두 시간 값만 수정하고 완료 기록·나머지 필드 보존 |
| 10 | 직원이 채택한 코멘트만 반영하고 유료 과정·시간 증가 배제 |

7번은 필요한 확인 질문을 반환하는 것이 정상입니다. 10개 평균은 반복 실험 비교용이며 서비스 전체 품질을 보장하는 통계로 해석하지 않습니다. 최종 후보는 별도의 미공개 입력으로 추가 평가하세요. 평가 입력을 학습 데이터에 합치지 마세요.

JSONL은 **한 줄이 입력 한 건**입니다. 각 줄은 `{"messages":[{"role":"user","content":"평가할 요청"}]}` 형식이며 선택적으로 앞에 system 메시지와 이전 대화를 넣습니다. 마지막 메시지는 user 요청이어야 합니다. 25개를 평가하려면 25줄을 넣으세요. content는 문자열이며 줄바꿈은 JSON의 `\n`으로 표현합니다.

Streamlit의 **평가 입력 파일**에서 선택한 뒤 실험을 등록합니다. `data/eval/`에 다른 `.jsonl` 파일을 추가해도 선택할 수 있습니다. 등록 시 파일 내용별 원격 사본을 만들어 기존 실험의 입력을 보존합니다. 등록한 실험의 입력을 바꾸려면 파일 수정 후 새로 등록하세요. 생성된 답변은 보고서 화면에서 건별 1~5점으로 평가합니다.

로컬 코드 수정 후 기존 화면이 그대로라면 Streamlit 실행 터미널에서 Ctrl+C 후 다시 실행하세요. 로컬 화면 종료는 이미 실행 중인 원격 작업을 중지하지 않습니다.

## 기획서 반영 기준과 평가 범위

참조: [GrowPath 기획서 2026-10-16](https://docs.google.com/document/d/1pM5mKfXJ8lH4HLiS0aRLpp3iDeYy0MUc/edit?tab=t.0). 이번 평가 입력은 파인튜닝 대상인 로드맵 후보 작성·부분 수정에 한정합니다. 규정 상담·진단·권한 검사는 별도 시스템 시험입니다. 후보 하나를 한 관점으로 생성하며 첫 세 입력은 같은 목표·자료·한도를 고정하고 관점만 바꿉니다. 4단계·자료 ID·시간/예산·수정 범위 유지·미확정 지원금 처리를 사람이 확인합니다. 자기평가 점수는 평가자가 주는 품질 점수와 별개입니다.

제공 자료 FIXTURE_*는 가상 검색 결과입니다. 실제 사용 시 검증된 검색 결과로 교체하세요. 이 예시로 실제 자료 검색이나 규정 적합성이 검증되지는 않습니다. 현재 학습은 여전히 샘플 54개를 쓰며 이 입력 파일은 학습 데이터로 사용하지 않습니다. 실제 학습 데이터와 평가 입력의 중복을 별도로 점검해야 합니다.

자동 생성 비교 결과는 품질 판정이 아닙니다. Streamlit의 사람 평가 평균을 사용하며 기획서의 2명 검토를 따르려면 평가자 이름을 달리하여 각 입력을 평가합니다. 전체 시스템 고정 시험 30개와 이 모델 평가용 10개/후보 25개는 서로 다른 범위입니다.

## 학습·답변 생성 속도 측정 · 2026-10-19

동일 A100 80GB·27B NF4 QLoRA·전체 언어 모델 Linear LoRA·유효 배치 16으로 샘플 48개를 고정 순서로 측정했습니다. 길이는 751~777토큰이며, 3번의 optimizer step 중 첫 준비/컴파일 step을 제외한 2번의 평균입니다. 데이터·에포크·모델 크기를 줄인 결과가 아닙니다.

| 환경 | GPU 배치 × 누적 | 유효 배치 16당 시간 | 최대 할당 메모리 |
| --- | --- | --- | --- |
| 기존 대체 연산 | 1 × 16 | 45.92초 | 28.88 GiB |
| 최적화 커널 | 1 × 16 | 22.72초 | 28.88 GiB |
| 최적화 커널 | 2 × 8 | 20.25초 | 31.89 GiB |
| 최적화 커널 | 4 × 4 | 18.37초 | 38.12 GiB |

새 기본 학습 설정은 배치 4·누적 4입니다. P21은 2·8, P22는 1·16 비교로 유지하고 P10은 4·8로 유효 배치 32를 비교합니다. 실제 데이터가 더 길면 시간·메모리가 달라집니다. 샘플 속도로 3,000개×5에포크를 환산하면 순수 학습 약 4시간 50분이며 저장·검증·생성 시간이 추가됩니다. 2~3시간 완료를 검증한 결과는 아닙니다.

최초 최적화 당시 답변 동시 생성 기본값은 4였습니다. 추가 검증 후 현재 기본값은 아래 설명대로 8입니다. 같은 원본 BF16+어댑터에서 난도 평가 입력 10개를 최대 128토큰씩 생성한 속도 시험은 다음과 같습니다. 첫 1개 입력의 준비 호출은 제외했지만 입력 길이·배치별 추가 컴파일 비용은 포함될 수 있으므로 전체 길이 답변의 확정 시간으로 해석하지 않습니다.

| 동시 생성 | 10개 소요 시간 | 출력 처리량 | 최대 할당 메모리 |
| --- | --- | --- | --- |
| 1개 | 187.65초 | 6.82토큰/초 | 52.31 GiB |
| 2개 | 107.85초 | 11.72토큰/초 | 52.75 GiB |
| 4개 | 70.44초 | 17.94토큰/초 | 53.35 GiB |

배치 1과 비교해 배치 2는 8/10개, 배치 4는 7/10개의 출력이 완전히 같았습니다. greedy 생성이어도 연산 형태에 따른 수치 차이로 문장이 달라질 수 있으므로 비교 실험에서는 생성 배치를 고정합니다. 속도 향상이 답변 품질 향상을 입증하지는 않습니다.

Streamlit의 `답변 동시 생성 개수`에서 1·2·4·8을 선택합니다. 학습 배치와 별개이며 설정은 실행 YAML과 보고서에 기록됩니다. 생성 시 왼쪽 패딩을 사용하고, 각 답변의 EOS 뒤에 붙은 패딩을 제외해 입력별 답변·토큰 수를 보존합니다. 최적화 패키지 버전이 달라지면 기본 답변 캐시는 재사용하지 않습니다. 학습 런타임에도 커널 버전을 남기며 이전 환경의 미완료 체크포인트를 새 환경에서 섞어 재개하지 않습니다.

재측정 도구는 `scripts/benchmark_performance.py` 한 파일입니다. 실행 중/대기 중인 GPU 작업이 있으면 중단하고, GPU 잠금을 보유한 상태에서만 측정합니다. 결과는 `outputs/performance_probe_*`에만 저장하며 학습 등록·가중치 업로드·AI API 평가를 하지 않습니다. 생성 속도 시험은 기본 128토큰으로 제한하므로 평가 보고서로 사용하지 마세요.

```bash
.venv-runpod/bin/python scripts/benchmark_performance.py --mode train --batch 4
# --adapter 뒤에는 실제 저장된 어댑터 경로를 넣습니다.
.venv-runpod/bin/python scripts/benchmark_performance.py --mode generation --adapter outputs/factory_sample/RUN_ID/artifacts/WEIGHT_ID
```

## 추가 평가 프롬프트 25개 · 비활성 보관

자동 실행되지 않는 후보입니다. JSON 한 줄만 평가 파일에 복사하면 활성화됩니다. README의 HTML 주석은 JSONL로 복사하지 마세요.

### 후보 01 · 비용·자료 동일 비교

<!-- 비활성 평가 후보 01 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"사내 규정 문서로 질의응답하는 RAG 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [{\"resource_id\": \"FIXTURE_DOC_1\", \"title\": \"RAG 처리 흐름 실습 노트\", \"type\": \"document\", \"cost_krw\": 0, \"estimated_hours\": 1, \"level\": \"입문\", \"availability\": \"평가용 제공 본문\", \"content_summary\": \"문서 분할, 검색, 근거 표시의 흐름을 작은 가상 문서로 연습한다.\"}, {\"resource_id\": \"FIXTURE_LAB_2\", \"title\": \"검색 결과 검증 실습\", \"type\": \"practice_material\", \"cost_krw\": 0, \"estimated_hours\": 2, \"level\": \"입문\", \"availability\": \"평가용 제공 본문\", \"content_summary\": \"고정 질문과 기대 근거를 작성하고 검색 실패를 기록한다.\"}], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\"}"}]}
```

### 후보 02 · 시간·자료 동일 비교

<!-- 비활성 평가 후보 02 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"사내 규정 문서로 질의응답하는 RAG 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"시간 우선\", \"resources\": [{\"resource_id\": \"FIXTURE_DOC_1\", \"title\": \"RAG 처리 흐름 실습 노트\", \"type\": \"document\", \"cost_krw\": 0, \"estimated_hours\": 1, \"level\": \"입문\", \"availability\": \"평가용 제공 본문\", \"content_summary\": \"문서 분할, 검색, 근거 표시의 흐름을 작은 가상 문서로 연습한다.\"}, {\"resource_id\": \"FIXTURE_LAB_2\", \"title\": \"검색 결과 검증 실습\", \"type\": \"practice_material\", \"cost_krw\": 0, \"estimated_hours\": 2, \"level\": \"입문\", \"availability\": \"평가용 제공 본문\", \"content_summary\": \"고정 질문과 기대 근거를 작성하고 검색 실패를 기록한다.\"}], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\"}"}]}
```

### 후보 03 · 업무 적용·자료 동일 비교

<!-- 비활성 평가 후보 03 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"사내 규정 문서로 질의응답하는 RAG 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"업무 적용 우선\", \"resources\": [{\"resource_id\": \"FIXTURE_DOC_1\", \"title\": \"RAG 처리 흐름 실습 노트\", \"type\": \"document\", \"cost_krw\": 0, \"estimated_hours\": 1, \"level\": \"입문\", \"availability\": \"평가용 제공 본문\", \"content_summary\": \"문서 분할, 검색, 근거 표시의 흐름을 작은 가상 문서로 연습한다.\"}, {\"resource_id\": \"FIXTURE_LAB_2\", \"title\": \"검색 결과 검증 실습\", \"type\": \"practice_material\", \"cost_krw\": 0, \"estimated_hours\": 2, \"level\": \"입문\", \"availability\": \"평가용 제공 본문\", \"content_summary\": \"고정 질문과 기대 근거를 작성하고 검색 실패를 기록한다.\"}], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\"}"}]}
```

### 후보 04 · Python 입문

<!-- 비활성 평가 후보 04 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"사내 규정 문서로 질의응답하는 RAG 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"시스템 운영\", \"experience\": \"코드 작성 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 1, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\"}"}]}
```

### 후보 05 · 개발 숙련·RAG 입문

<!-- 비활성 평가 후보 05 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"사내 규정 문서로 질의응답하는 RAG 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\"}"}]}
```

### 후보 06 · 운영 로그 검색

<!-- 비활성 평가 후보 06 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"가상 운영 로그에서 장애 관련 기록을 검색하는 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\"}"}]}
```

### 후보 07 · API 연동 학습

<!-- 비활성 평가 후보 07 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"가상 문서 검색 결과를 반환하는 로컬 API 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\"}"}]}
```

### 후보 08 · 근거 표시

<!-- 비활성 평가 후보 08 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"문서 질의응답에서 답변과 근거 문장을 함께 보여주는 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\"}"}]}
```

### 후보 09 · 검색 평가

<!-- 비활성 평가 후보 09 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"고정 질의로 검색 품질과 실패 원인을 기록하는 평가 도구 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\"}"}]}
```

### 후보 10 · 입력 보안

<!-- 비활성 평가 후보 10 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"개인정보 없는 가상 문서만 사용하는 RAG 입력 처리 실습\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\"}"}]}
```

### 후보 11 · 무료만

<!-- 비활성 평가 후보 11 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"사내 규정 문서로 질의응답하는 RAG 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 0, \"perspective\": \"비용 우선\", \"resources\": [{\"resource_id\": \"FIXTURE_DOC_1\", \"title\": \"RAG 처리 흐름 실습 노트\", \"type\": \"document\", \"cost_krw\": 0, \"estimated_hours\": 1, \"level\": \"입문\", \"availability\": \"평가용 제공 본문\", \"content_summary\": \"문서 분할, 검색, 근거 표시의 흐름을 작은 가상 문서로 연습한다.\"}, {\"resource_id\": \"FIXTURE_LAB_2\", \"title\": \"검색 결과 검증 실습\", \"type\": \"practice_material\", \"cost_krw\": 0, \"estimated_hours\": 2, \"level\": \"입문\", \"availability\": \"평가용 제공 본문\", \"content_summary\": \"고정 질문과 기대 근거를 작성하고 검색 실패를 기록한다.\"}], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\"}"}]}
```

### 후보 12 · 자료 검색 빈 결과

<!-- 비활성 평가 후보 12 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"사내 규정 문서로 질의응답하는 RAG 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\"}"}]}
```

### 후보 13 · 일부 자료만 관련

<!-- 비활성 평가 후보 13 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"사내 규정 문서로 질의응답하는 RAG 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [{\"resource_id\": \"FIXTURE_DOC_1\", \"title\": \"RAG 처리 흐름 실습 노트\", \"type\": \"document\", \"cost_krw\": 0, \"estimated_hours\": 1, \"level\": \"입문\", \"availability\": \"평가용 제공 본문\", \"content_summary\": \"문서 분할, 검색, 근거 표시의 흐름을 작은 가상 문서로 연습한다.\"}, {\"resource_id\": \"FIXTURE_LAB_2\", \"title\": \"검색 결과 검증 실습\", \"type\": \"practice_material\", \"cost_krw\": 0, \"estimated_hours\": 2, \"level\": \"입문\", \"availability\": \"평가용 제공 본문\", \"content_summary\": \"고정 질문과 기대 근거를 작성하고 검색 실패를 기록한다.\"}, {\"resource_id\": \"FIXTURE_OTHER\", \"title\": \"가상 회계 입문 노트\", \"cost_krw\": 0, \"content_summary\": \"복식부기 소개\"}], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\"}"}]}
```

### 후보 14 · 지원금 미확정

<!-- 비활성 평가 후보 14 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"사내 규정 문서로 질의응답하는 RAG 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 10000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\", \"requested_support_krw\": 50000}"}]}
```

### 후보 15 · 업무 정보 부족

<!-- 비활성 평가 후보 15 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"사내 규정 문서로 질의응답하는 RAG 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"가상 개발 부서\", \"personal_work\": \"미입력\", \"experience\": \"Python 기초\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\"}"}]}
```

### 후보 16 · 자기평가 낮음

<!-- 비활성 평가 후보 16 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"사내 규정 문서로 질의응답하는 RAG 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 1, \"development_experience\": 2, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\"}"}]}
```

### 후보 17 · 사용자 시작점 확정

<!-- 비활성 평가 후보 17 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"사내 규정 문서로 질의응답하는 RAG 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\", \"start_stage_note\": \"사용자가 2단계 시작을 선택함. 1단계는 기존 경험 확인으로 최소화\"}"}]}
```

### 후보 18 · 매우 짧은 기간

<!-- 비활성 평가 후보 18 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"가상 문서 3개에서 검색과 근거 표시를 직접 실행하기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 1, \"weekly_hours\": 2, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\"}"}]}
```

### 후보 19 · 기간 확대

<!-- 비활성 평가 후보 19 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"사내 규정 문서로 질의응답하는 RAG 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 8, \"weekly_hours\": 2, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\"}"}]}
```

### 후보 20 · 범위 과다

<!-- 비활성 평가 후보 20 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"generate_roadmap\", \"goal\": \"전사 상용 RAG 전체를 완성하고 싶음\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 1, \"weekly_hours\": 1, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\", \"request\": \"한계를 설명하고 총 1시간 내 가능한 학습 범위를 제안\"}"}]}
```

### 후보 21 · 부분 수정·시간

<!-- 비활성 평가 후보 21 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"revise_roadmap\", \"goal\": \"사내 규정 문서로 질의응답하는 RAG 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\", \"existing_roadmap\": {\"perspective\": \"비용 우선\", \"stages\": [{\"stage\": 1, \"name\": \"기초 다지기\", \"hours\": 1, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"기존 문서 검색 경험을 정리한다\", \"deliverable\": \"경험 요약\", \"completion_criterion\": \"경험 요약을 저장하고 검토 기록을 남김\"}, {\"stage\": 2, \"name\": \"핵심 이해\", \"hours\": 3, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"RAG 처리 흐름을 정리한다\", \"deliverable\": \"처리 흐름도\", \"completion_criterion\": \"처리 흐름도을 저장하고 검토 기록을 남김\"}, {\"stage\": 3, \"name\": \"업무 적용\", \"hours\": 6, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"가상 문서 검색 시제품을 만든다\", \"deliverable\": \"실행 코드\", \"completion_criterion\": \"실행 코드을 저장하고 검토 기록을 남김\"}, {\"stage\": 4, \"name\": \"성과 확인\", \"hours\": 2, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"고정 질문으로 근거를 검증한다\", \"deliverable\": \"시험 결과표\", \"completion_criterion\": \"시험 결과표을 저장하고 검토 기록을 남김\"}], \"total_hours\": 12, \"total_cost_krw\": 0}, \"change_request\": \"2단계 1시간을 3단계로 옮겨 주세요. 시간 외 내용과 총합 유지.\"}"}]}
```

### 후보 22 · 부분 수정·검증

<!-- 비활성 평가 후보 22 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"revise_roadmap\", \"goal\": \"사내 규정 문서로 질의응답하는 RAG 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\", \"existing_roadmap\": {\"perspective\": \"비용 우선\", \"stages\": [{\"stage\": 1, \"name\": \"기초 다지기\", \"hours\": 1, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"기존 문서 검색 경험을 정리한다\", \"deliverable\": \"경험 요약\", \"completion_criterion\": \"경험 요약을 저장하고 검토 기록을 남김\"}, {\"stage\": 2, \"name\": \"핵심 이해\", \"hours\": 3, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"RAG 처리 흐름을 정리한다\", \"deliverable\": \"처리 흐름도\", \"completion_criterion\": \"처리 흐름도을 저장하고 검토 기록을 남김\"}, {\"stage\": 3, \"name\": \"업무 적용\", \"hours\": 6, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"가상 문서 검색 시제품을 만든다\", \"deliverable\": \"실행 코드\", \"completion_criterion\": \"실행 코드을 저장하고 검토 기록을 남김\"}, {\"stage\": 4, \"name\": \"성과 확인\", \"hours\": 2, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"고정 질문으로 근거를 검증한다\", \"deliverable\": \"시험 결과표\", \"completion_criterion\": \"시험 결과표을 저장하고 검토 기록을 남김\"}], \"total_hours\": 12, \"total_cost_krw\": 0}, \"change_request\": \"4단계 완료 기준에 근거가 없는 질문 2개 검증만 추가. 나머지 필드 모두 유지.\"}"}]}
```

### 후보 23 · 자료 대체

<!-- 비활성 평가 후보 23 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"revise_roadmap\", \"goal\": \"사내 규정 문서로 질의응답하는 RAG 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [{\"resource_id\": \"FIXTURE_DOC_1\", \"title\": \"RAG 처리 흐름 실습 노트\", \"type\": \"document\", \"cost_krw\": 0, \"estimated_hours\": 1, \"level\": \"입문\", \"availability\": \"평가용 제공 본문\", \"content_summary\": \"문서 분할, 검색, 근거 표시의 흐름을 작은 가상 문서로 연습한다.\"}, {\"resource_id\": \"FIXTURE_LAB_2\", \"title\": \"검색 결과 검증 실습\", \"type\": \"practice_material\", \"cost_krw\": 0, \"estimated_hours\": 2, \"level\": \"입문\", \"availability\": \"평가용 제공 본문\", \"content_summary\": \"고정 질문과 기대 근거를 작성하고 검색 실패를 기록한다.\"}], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\", \"existing_roadmap\": {\"perspective\": \"비용 우선\", \"stages\": [{\"stage\": 1, \"name\": \"기초 다지기\", \"hours\": 1, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"기존 문서 검색 경험을 정리한다\", \"deliverable\": \"경험 요약\", \"completion_criterion\": \"경험 요약을 저장하고 검토 기록을 남김\"}, {\"stage\": 2, \"name\": \"핵심 이해\", \"hours\": 3, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"RAG 처리 흐름을 정리한다\", \"deliverable\": \"처리 흐름도\", \"completion_criterion\": \"처리 흐름도을 저장하고 검토 기록을 남김\"}, {\"stage\": 3, \"name\": \"업무 적용\", \"hours\": 6, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"가상 문서 검색 시제품을 만든다\", \"deliverable\": \"실행 코드\", \"completion_criterion\": \"실행 코드을 저장하고 검토 기록을 남김\"}, {\"stage\": 4, \"name\": \"성과 확인\", \"hours\": 2, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"고정 질문으로 근거를 검증한다\", \"deliverable\": \"시험 결과표\", \"completion_criterion\": \"시험 결과표을 저장하고 검토 기록을 남김\"}], \"total_hours\": 12, \"total_cost_krw\": 0}, \"change_request\": \"2단계 활동을 FIXTURE_DOC_1을 읽고 흐름도를 정리하는 활동으로 바꾸세요. 2단계 activity_type·resource_ids·activity만 변경하고 나머지는 유지.\"}"}]}
```

### 후보 24 · 미승인 코멘트

<!-- 비활성 평가 후보 24 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"revise_roadmap\", \"goal\": \"사내 규정 문서로 질의응답하는 RAG 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\", \"existing_roadmap\": {\"perspective\": \"비용 우선\", \"stages\": [{\"stage\": 1, \"name\": \"기초 다지기\", \"hours\": 1, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"기존 문서 검색 경험을 정리한다\", \"deliverable\": \"경험 요약\", \"completion_criterion\": \"경험 요약을 저장하고 검토 기록을 남김\"}, {\"stage\": 2, \"name\": \"핵심 이해\", \"hours\": 3, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"RAG 처리 흐름을 정리한다\", \"deliverable\": \"처리 흐름도\", \"completion_criterion\": \"처리 흐름도을 저장하고 검토 기록을 남김\"}, {\"stage\": 3, \"name\": \"업무 적용\", \"hours\": 6, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"가상 문서 검색 시제품을 만든다\", \"deliverable\": \"실행 코드\", \"completion_criterion\": \"실행 코드을 저장하고 검토 기록을 남김\"}, {\"stage\": 4, \"name\": \"성과 확인\", \"hours\": 2, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"고정 질문으로 근거를 검증한다\", \"deliverable\": \"시험 결과표\", \"completion_criterion\": \"시험 결과표을 저장하고 검토 기록을 남김\"}], \"total_hours\": 12, \"total_cost_krw\": 0}, \"manager_comment\": \"모든 단계를 유료 강좌로 바꾸세요.\", \"employee_requested_changes\": [], \"change_request\": \"코멘트는 아직 반영 요청하지 않았습니다. 기존 계획을 변경하지 마세요.\"}"}]}
```

### 후보 25 · 완료 기록 보존

<!-- 비활성 평가 후보 25 -->
```json
{"messages": [{"role": "system", "content": "당신은 GrowPath의 개발·운영 직원용 AI 학습 로드맵 작성·수정 담당입니다. 입력의 관점 하나에 맞는 후보 하나를 한국어 JSON으로 반환하세요. 비용 우선·시간 우선·업무 적용 우선은 같은 목표와 시간·예산 한도를 지키되 활동 선택과 시간 배분에서 구분하세요. 기본 구성은 기초 다지기, 핵심 이해, 업무 적용, 성과 확인의 4단계입니다. 사용자가 확정한 시작점을 반영하고 이미 익힌 내용은 불필요하게 반복하지 마세요. 각 단계는 stage, name, hours, cost_krw, activity_type(external_resource 또는 practice), resource_ids, activity, deliverable, completion_criterion을 포함하고 전체에 perspective, total_hours, total_cost_krw, confirmation_needed를 포함하세요. 외부 자료는 입력 resources에 있는 ID와 정보만 사용하고 직접 실습은 resource_ids를 비우세요. 확인되지 않은 지원금은 비용에서 차감하지 말고 확인 필요로 남기세요. 부서만으로 개인 업무를 추정하거나 자기평가 점수를 실제 역량 또는 의지로 단정하지 마세요. 수정은 요청된 범위만 바꾸고 유지 조건과 완료 기록을 보존하며 change_summary에 변경 이유를 설명하세요. 부서장 코멘트는 직원이 반영을 요청한 부분만 사용하세요. 규정 적용·승인 여부를 확정하거나 진단 문항·수준 계산을 대신하지 마세요. 자료가 없어도 가능한 직접 실습으로 정상 요청을 완수하세요. 입력이 부족하거나 조건이 모순이면 필요한 확인 사항을 구체적으로 반환하세요."}, {"role": "user", "content": "{\"task\": \"revise_roadmap\", \"goal\": \"사내 규정 문서로 질의응답하는 RAG 시제품 만들기\", \"project_summary\": \"가상 개발·운영 부서 직원이 공개·가상 문서를 대상으로 문서 검색과 근거 표시를 학습한다. 실제 사내 개인정보와 비공개 문서는 사용하지 않는다.\", \"profile\": {\"job_family\": \"사내 시스템 개발·운영\", \"experience\": \"Python·데이터 처리 경험 있음. LLM·RAG 개발은 처음\"}, \"current_level\": \"사전 자기점검은 학습 시작점 참고용이며 실제 역량 검증 결과가 아님\", \"self_check\": {\"scale\": \"1~5 자기평가\", \"ai_understanding\": 2, \"development_experience\": 4, \"target_domain\": 1}, \"start_stage\": 2, \"duration_weeks\": 4, \"weekly_hours\": 3, \"budget_krw\": 50000, \"perspective\": \"비용 우선\", \"resources\": [], \"support_status\": \"확인 필요\", \"notice\": \"가상 평가 사례. 자료 목록은 검색 도구 출력의 형식 시험용이며 실존 강좌 정보가 아니다.\", \"existing_roadmap\": {\"perspective\": \"비용 우선\", \"stages\": [{\"stage\": 1, \"name\": \"기초 다지기\", \"hours\": 1, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"기존 문서 검색 경험을 정리한다\", \"deliverable\": \"경험 요약\", \"completion_criterion\": \"경험 요약을 저장하고 검토 기록을 남김\"}, {\"stage\": 2, \"name\": \"핵심 이해\", \"hours\": 3, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"RAG 처리 흐름을 정리한다\", \"deliverable\": \"처리 흐름도\", \"completion_criterion\": \"처리 흐름도을 저장하고 검토 기록을 남김\"}, {\"stage\": 3, \"name\": \"업무 적용\", \"hours\": 6, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"가상 문서 검색 시제품을 만든다\", \"deliverable\": \"실행 코드\", \"completion_criterion\": \"실행 코드을 저장하고 검토 기록을 남김\"}, {\"stage\": 4, \"name\": \"성과 확인\", \"hours\": 2, \"cost_krw\": 0, \"activity_type\": \"practice\", \"resource_ids\": [], \"activity\": \"고정 질문으로 근거를 검증한다\", \"deliverable\": \"시험 결과표\", \"completion_criterion\": \"시험 결과표을 저장하고 검토 기록을 남김\"}], \"total_hours\": 12, \"total_cost_krw\": 0}, \"completed_stages\": [1, 2], \"change_request\": \"3단계 활동에 실행 방법 README 작성을 추가하고 나머지 필드와 완료 기록, 시간·비용은 그대로 유지.\"}"}]}
```


## 평가 모델 정밀도 · BF16 적용

학습은 기존 4비트 NF4 QLoRA 설정을 유지합니다. 평가 스크립트는 학습과 같은 모델 ID·revision의 원본 BF16 모델을 양자화 없이 불러오고 저장한 LoRA 어댑터를 적용합니다. 같은 BF16 모델에서 어댑터를 끈 기본 답변과 켠 학습 답변을 생성합니다.

기존 4비트 평가 답변은 BF16 평가 캐시로 재사용하지 않습니다. 보고서에 학습 양자화와 평가 정밀도를 따로 기록하며, 다른 정밀도의 답변·점수를 한 평가 세트로 섞지 않습니다. 최신 세트만 기본 목록에 표시하며 기존 결과 파일과 평가 이력은 보존합니다. 학습 코드·체크포인트 해시는 변경하지 않습니다.

현재 실행 중인 원격 작업은 시작 시점 코드로 진행할 수 있습니다. 변경은 로컬 Streamlit 재시작 후 설정을 등록하여 평가 코드를 배포한 다음 실행부터 적용합니다. BF16 추론은 GPU 메모리를 더 사용하며 GPU 실측은 아직 필요합니다. 메모리 부족 시 4비트로 자동 대체하지 않습니다.

## OpenAI AI 보조 평가 · 로컬 전용

프로젝트 `.env`에 `OPENAI_API_KEY="직접 입력"`를 설정합니다. `OPENAI_EVAL_MODEL="gpt-4.1-mini-2025-04-14"`를 기본값으로 준비했습니다. 다른 지원 모델 ID로 변경할 수 있습니다. API 키는 Git에 올리거나 채팅에 보내지 마세요.

Streamlit에서 **새 답변 전체 자동 AI 평가**를 켜면 미평가 답변을 순서대로 평가합니다. **사람 평가 옆의 AI 보조 평가** 탭은 개별 근거 확인과 명시적 재평가용입니다. 평가 요청 시 입력 대화와 학습 모델 답변이 OpenAI API로 전송되고 비용이 발생합니다. API 키는 로컬 요청에만 쓰며 RunPod로 전달하지 않습니다. 평가 입력에 실제 개인·기관 정보가 있으면 전송 전에 적절히 비식별화하세요.

목표 적합성·관점 준수·시간/예산·자료·부분 수정의 항목별 1~5점과 근거를 표시합니다. 수정 요청이 없는 경우 부분 수정 항목만 평균에서 제외하며, 나머지 네 항목에는 점수를 부여합니다. 수치 합계와 예산·시간 한도, 자료 ID는 구조화된 값이 있을 때 코드로도 확인합니다. 이 검사는 수정 범위 전체의 정확성을 보증하지 않습니다.

결과는 Neon의 `qf_dashboard.ai_evaluations` 테이블에 저장합니다. 사람 점수·평균·보고서 제목은 바꾸지 않습니다. 모델·평가 규칙·입력/답변 서명이 일치하는 기존 평가만 표시합니다. 재평가 버튼은 추가 API 호출을 발생시키며 실패한 호출은 자동 재시도하지 않습니다. OpenAI Responses API의 structured outputs를 사용하고 store=false를 지정하지만 이는 API 제공자의 데이터 정책 전체를 대체하는 보장이 아닙니다.

공식 문서: https://developers.openai.com/api/docs/guides/structured-outputs

## 전체 답변 자동 AI 평가

왼쪽 **새 답변 전체 자동 AI 평가**가 켜져 있으면 수신된 모든 보고서의 미평가 답변을 대시보드 실행 환경의 백그라운드 작업이 순서대로 평가합니다. OpenAI API 비용이 발생합니다. 같은 입력·답변·모델·평가 규칙의 성공 결과는 재사용합니다. 새 답변 수신 후 대기열에 추가하며 Streamlit 재시작 시에도 저장된 결과를 이어 씁니다. RunPod 독립 수집 서비스가 연결되어 있으면 대시보드를 닫아도 큐 처리를 요청합니다. 대시보드와 Pod 서비스가 모두 종료되면 처리가 중단될 수 있습니다. 중단된 작업의 잠금은 최대 10분 후 회수할 수 있습니다. 실패는 자동으로 반복 호출하지 않고 화면의 실패 항목만 재시도 버튼으로 다시 요청합니다. 끄기는 이후 작업 시작/수신 등록을 멈추며 이미 시작한 백그라운드 평가 묶음을 강제로 중단하지 않습니다. AI 점수는 사람 평균·제목에 섞지 않습니다. 보고서 상단의 AI 진행 상황은 ‘AI 평가 결과 갱신’을 누를 때 조회합니다. 독립 서비스의 자동 AI 설정은 다음 실행 현황 갱신에서 전달되며, 이미 시작한 평가 묶음은 완료될 수 있습니다.

## BF16 일괄 평가와 기존 결과 보존

RunPod에서 4비트 QLoRA로 학습한 어댑터를 같은 모델 ID·revision의 원본 BF16 기본 모델에 적용합니다. `compare_factory_sample.py --case-indices 0 1 ...`는 에포크별로 한 번 모델을 로딩하고 여러 입력을 연속 생성합니다. 각 입력을 마칠 때 즉시 결과를 저장하므로 중간 실패해도 완료 결과는 남습니다. `control_pipeline.py`는 같은 어댑터·입력 해시·BF16·생성 조건의 완료 결과를 확인하고 누락 입력만 넘깁니다. 토큰 제한에 걸린 출력은 재사용하지 않습니다.

이미 학습한 모델은 보고서의 **기존 가중치로 BF16 평가 실행 · 재학습 없음**에서 답변을 생성할 수 있습니다. 내부 실행은 `control_pipeline.py --config <기존 설정> --evaluate-only`이며 학습·새 실험 등록을 호출하지 않습니다. CLI의 `--case-limit 2`는 소규모 GPU 검증에 사용합니다.

보고서의 **평가 결과 유형**에서 최신 결과·BF16 결과·4비트 시험 결과를 구분합니다. 기존 사람 평가와 AI 평가는 Neon에 보존하며 입력·답변·정밀도 서명이 바뀐 결과에는 예전 점수를 적용하지 않습니다. BF16 답변의 사람 평가는 별도로 해야 합니다.

화면 및 다운로드 보고서에 사람 평균과 AI 평균을 각각 표시합니다. 제목은 사람 평균을 사용합니다. 사람 평균은 각 입력의 평가자 평균을 먼저 계산하고 입력별 동일 비중으로 집계하며, AI 평균은 해당 입력의 유효 항목 점수를 평균한 후 입력별 동일 비중으로 집계합니다. 둘은 합산하지 않습니다.

동일한 BF16 기본 답변은 모델 revision·입력·생성 설정·토크나이저 파일 해시가 모두 일치하고 EOS 종료/비잘림이 확인될 때만 재사용합니다. 학습 어댑터 답변은 에포크별로 별도 생성합니다. 재사용된 기본 답변의 시간은 최초 생성 기록이며 현재 실행에서 다시 소요된 시간으로 해석하지 않습니다.

## Neon 대시보드 저장소

평가·보고서·대기열은 기존 Neon의 별도 qf_dashboard 스키마에 저장합니다. 설정은 DASHBOARD_STORAGE=neon이며 연결 실패 시 로컬 대체 저장을 하지 않습니다. 이전 기록과 백업, 향후 Cloud 전환 범위는 docs/neon_storage.md를 참고하세요.


## Cloud Secrets

인증정보는 Cloud Secrets → 환경변수 → 로컬 .env 순서로 읽습니다. 실제 값은 Git에 넣지 않습니다. .streamlit/secrets.toml.example과 docs/cloud_secrets.md를 참고하세요. Cloud 배포·작업 복구·로그인은 별도 단계입니다.


## 재시작 복구

Neon 기록 복원, RunPod 자동 재연결, 독립 보고서 수집·AI 평가 감독 프로세스를 추가했습니다. 설정과 복구 범위, 실제 Pod 검증 상태는 docs/restart_recovery.md를 참고하세요. 자동 재연결은 GPU 학습을 새로 제출하지 않습니다.


## 공용 입장 비밀번호

Cloud Secrets 또는 로컬 .env에 DASHBOARD_PASSWORD를 설정하세요. 입장한 모든 사용자는 같은 권한을 사용합니다. 비밀번호가 없으면 입장을 막으며, 인증 전에 DB·RunPod·AI 작업을 실행하지 않습니다. 왼쪽 나가기로 해당 세션에서 나갈 수 있습니다. docs/shared_password.md 참고.


## GitHub / Streamlit Cloud 배포

저장소: https://github.com/necknam/fine-tuning · 브랜치 main · 진입 파일 streamlit_app.py · Python 3.12. 인증정보는 Cloud Secrets에 등록합니다. 자세한 설정과 로컬 Miniforge 실행법은 docs/cloud_deployment.md에 있습니다. 로컬 Conda 설정은 configs/environment.local.yml로 옮겼고 Cloud는 requirements.txt를 사용합니다.


## 실행 안전성 점검

- 새 Pod의 데이터 업로드는 누락된 상위 폴더를 순서대로 생성합니다. 같은 이름의 데이터 내용이 다르면 덮어쓰지 않습니다.
- Jupyter 기본 Python은 통신만 담당하며 제어 명령은 `.venv-runpod/bin/python`에서 실행합니다.
- GPU 대기열은 학습·추론 자식까지 상속되는 파일 잠금으로 직렬 실행합니다. 상위 제어 프로세스만 종료되어도 남은 GPU 프로세스가 잠금을 유지합니다.
- UI와 독립 수집기는 동일한 Neon 트랜잭션 잠금 아래 최신 작업 이력을 병합합니다. 오래된 관측으로 최신 상태를 되돌리지 않습니다.
- 좀비 프로세스는 실행 중으로 보지 않습니다. 살아 있으나 heartbeat가 지연되는 서비스는 경고하고 중복 시작하지 않습니다. 배포 코드가 바뀌면 정상 응답 중인 이전 CPU 수집 서비스를 교체하며 GPU 작업은 유지합니다.
- 회귀 검사: `python -m unittest discover -s tests -v`. 프로세스 잠금 상속 검사는 Linux에서 실행합니다. 검사 자체는 GPU 학습이나 유료 API를 호출하지 않습니다.


### AI 평가 기준 v3 · 원문 근거 검증

실제 평가에서 시작 단계 위반을 놓친 사례를 확인해 기준을 강화했습니다. 신규 생성 요청에서 확정한 시작 단계 이전에 시간을 배정하면 목표 적합성은 최대 2점입니다. 기존 완료 단계의 이력을 보존하는 수정 요청에는 이 상한을 적용하지 않습니다.
각 항목은 답변 원문 인용을 함께 반환하며, 4·5점인데 인용이 없거나 원문에서 확인되지 않으면 최대 3점으로 보정합니다. 시간·예산 위반 최대 2점, 미제공 자료 ID 최대 1점도 유지합니다.
원문 인용은 AI 평가 화면과 Markdown 보고서에서 확인합니다. 코드 보정 근거는 요약에도 표시하고 모델 원점수·원래 근거는 별도로 보관합니다.
기존 v1/v2 점수는 보존하며 v3는 별도 결과입니다. 자동 AI 평가가 켜져 있으면 v3 결과가 없는 답변은 새 API 호출로 평가합니다.


### 추가 최적화 7개 검증 결과 · 2026-10-19

A100 80GB와 같은 27B 모델·LoRA r32·유효 배치 16을 유지해 시험했습니다. 학습 속도는 앞과 동일한 751~777토큰 샘플 48개에서 첫 step을 제외한 2개 step 평균입니다. 실전 3,000개 데이터 전체나 품질 개선을 검증한 결과는 아닙니다.

| 항목 | 실제 결과 | 적용 결정 |
| --- | --- | --- |
| 재계산 해제 | 배치 4·2는 OOM. 배치 1×누적 16은 15.83초/step, 약 14% 단축 | Streamlit에서 배치 1일 때만 선택 가능. 기본 재계산은 켜짐 |
| 학습 배치 확대 | 배치 8×누적 2는 17.46초, 예약 메모리 73.72GiB. 배치 16은 OOM | 약 5% 개선에 비해 여유가 적어 기본값 4×4 유지 |
| Liger 0.8.4 | 배치 4는 19.62초로 느려짐. 배치 8은 17.50초로 추가 이득 없음 | 분리 설치로만 시험. 주 환경에 적용하지 않음 |
| 저장·업로드 대기 | 검증된 불변 어댑터 파일을 별도 CPU 스레드에서 업로드 | 적용. 모든 업로드 성공을 확인하기 전 완료 처리 금지 |
| 매 step DB 조회 | 로컬 상태 확인 10,000회에 DB 조회 0회, 실제 Neon 하트비트 갱신 확인 | 적용. 하트비트 실패·만료는 중단하고 저장·상태 변경 때는 DB 소유권 재확인 |
| Unsloth 2026.10.6 | 공식 패키지가 Transformers <=5.17.0을 요구하며 현재 5.20.0과 충돌 | 의존성 검사에서 제외. 기존 패키지를 낮추지 않음 |
| 생성 배치 8 | 원본 BF16+동일 어댑터, 입력 10개에서 228.71초→174.27초, 약 24% 단축 | 새 실험 생성 기본값 8. 학습 배치와 별개 |

생성 시험은 최대 2,048토큰으로 실행했고 배치 4·8 모두 10/10개가 EOS로 끝났으며 JSON으로 읽혔습니다. 출력 토큰은 각각 4,408·4,637개로 달랐고 문장 완전 일치는 3/10개였습니다. 생성 설정과 입력 묶음을 실험 사이에 고정하세요. 이 시험은 기존 샘플 어댑터의 동작·속도 검사이며 새 품질 평가 보고서를 만들거나 AI API를 호출하지 않았습니다.

기본 모델 답변 캐시는 모델·토크나이저·커널·생성 설정뿐 아니라 **함께 생성한 입력 묶음의 순서와 내용**까지 같을 때만 재사용합니다. 묶음 일부의 캐시가 없으면 전체 묶음을 다시 생성해 패딩과 배치 형태가 바뀌지 않게 합니다. 예전 보고서는 보존하지만 이 정보가 없는 캐시는 새 생성에서 재사용하지 않습니다.

빠른 학습 설정을 직접 시험하려면 `GPU 배치 크기=1`, `그래디언트 누적=16`, `재계산 사용 · GPU 메모리 절약=끔`을 선택합니다. 약 770토큰 샘플의 속도를 3,000개×5에포크에 환산하면 **순수 학습 약 4시간 8분**입니다. 기본 4×4 설정은 약 4시간 48분이며 저장·검증·업로드·답변 생성 시간은 별도입니다. 실제 데이터가 길거나 LoRA 용량이 크면 재계산을 끈 설정에서 OOM이 날 수 있으므로 기본값으로 자동 전환하지 않습니다. OOM이면 재계산을 켠 새 실험을 등록하세요. 설정이 바뀐 실험에 이전 체크포인트를 섞어 재개하지 않습니다.

여기서 재계산은 activation gradient checkpointing입니다. **중단 복구용 파일 저장과 별개**이며 전체 optimizer/scheduler/RNG 체크포인트는 50 step 및 매 epoch 저장을 유지합니다. 저장 간격 확대는 복구 손실 범위가 커져 적용하지 않았습니다. 4·5에포크 어댑터 저장도 유지합니다. 업로드 실패 시 로컬 스냅샷을 보존하고 `--sync-only`로 재동기화하며, 진행 중 학습과 업로드가 모두 끝나기 전에는 성공으로 표시하지 않습니다.

재계산을 끈 실제 Qwen 시험에서 checkpoint-3의 전체 상태를 새 Trainer/옵티마이저에 읽어 step 4까지 재개했고, 어댑터 저장·재로드 후 전체 LoRA 텐서 SHA-256이 일치했습니다. 손실은 0.673178→0.674289로 약 0.165% 차이가 있어 수치 완전 일치나 품질 동일성을 주장하지 않습니다. 프로세스를 강제 종료한 장애 복구 시험은 이번 검사에 포함하지 않았습니다.

주 환경의 Torch 2.8.0+cu128 / Transformers 5.20.0 / PEFT 0.21.2 / causal-conv1d 1.7.0 / flash-linear-attention 0.5.2를 유지했고 `pip check`를 통과했습니다. 실패한 GPU 시험은 분리 프로세스 종료로 메모리를 반환했습니다. Liger·Unsloth는 주 실행 환경에 설치하지 않았습니다.

재현 명령은 기존 `scripts/benchmark_performance.py`를 사용합니다. `--verify-state`는 임시 가중치·전체 체크포인트를 저장하고 한 step을 추가로 재개하므로 일반 속도 측정보다 시간이 더 걸립니다. 결과는 운영 보고서·HF·학습 등록 DB에 쓰지 않습니다.

```bash
.venv-runpod/bin/python scripts/benchmark_performance.py --mode train --batch 1 --no-gc --verify-state
.venv-runpod/bin/python scripts/benchmark_performance.py --mode train --batch 8
.venv-runpod/bin/python scripts/benchmark_performance.py --mode generation --adapter outputs/factory_sample/RUN_ID/artifacts/WEIGHT_ID --generation-batches 4 8 --max-new-tokens 2048
```

실측 JSON과 진단 로그는 로컬 `reports/performance_review_20261019/` 및 RunPod `outputs/performance_review_20261019/`에 보관합니다. 임시 모델 체크포인트와 분리 설치 패키지는 검증 뒤 제거합니다. 실제 데이터 토큰 길이·패딩·길이별 묶기 작업과 GPU 변경은 이번 범위에서 제외했습니다.

최종 회귀 검사는 RunPod Linux 23/23 통과, Windows 22개 통과·Linux 전용 잠금 검사 1개 제외입니다. Streamlit AppTest에서 생성 기본값 8·재계산 기본값 켜짐·설정 변경을 확인했고 파라미터 편집 중 DB 조회가 발생하지 않았습니다.
