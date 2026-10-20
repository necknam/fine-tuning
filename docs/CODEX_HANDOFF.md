# DB · 파인튜닝 데이터 · 파인튜닝 실행 보고서

기준일: 2026-10-20. IT 직무의 목표·경험·5점 자기보고 설문을 받아 실제 DB 자료에 근거한 학습 로드맵을 만드는 프로젝트다. 이 문서는 현재 확정 상태와 남은 작업만 관리한다.

| 분야 | 현재 상태 | 다음 작업 |
| --- | --- | --- |
| DB | 스키마·적재 코드·이미지 저장·ERD 반영, 규정 전용 SQL 복원 검증 완료 | 미확정 직원 소속 확인, 규정 검토 |
| 파인튜닝 데이터 | 최종 1,500건 구성·로컬 검사 완료 | 학습 중 데이터·분할 고정 |
| 파인튜닝 실행 | 현재 CPU Pod 연결·환경 점검, 로컬 평가 코드 53개 테스트 통과(1개 Windows에서 Linux 전용 테스트 제외) | 다른 GPU 환경에서 설치·파일 검증 → GPU 점검 → 본 학습·비교 |

로드맵 앱은 로컬에서만 실행하고 팩토리는 로컬 또는 Streamlit Cloud에서 실행한다. 각 폴더의 .env를 독립 관리한다. Cloud에서는 로드맵 로컬 DB에 접근하지 않는다.

## 1. DB

앱 데이터는 Docker 없이 PC의 PostgreSQL 17.11 + pgvector 0.8.2에 저장한다. 팩토리 실험 기록은 별도 Neon DB에 저장한다.

| 항목 | 확정 내용 |
| --- | --- |
| 앱 접속 | 127.0.0.1:55433 / growpath / postgres |
| 물리 저장 폴더 | roadmap_app/data/local_db/postgres — PostgreSQL이 관리하며 직접 편집하지 않는다 |
| 앱 설정 | roadmap_app/.env.local의 로컬 DB 연결이 우선 |
| 테이블 | 운영 41개·관리 2개·보관 6개, 전체 49개 |
| 사용자 | employees를 단일 원본으로 사용하며 기존 정수 ID 유지. users는 호환 뷰 |
| 검색 | 실제 DB의 규정·스킬·추천 자원과 canonical 벡터 사용 |
| 가상 데이터 | 사용자·프로젝트 시나리오에만 사용. 자료 사실은 실데이터 사용 |

마지막 DB 확인 기준: 스킬 36, 강좌 718(K-MOOC 201 + Microsoft 517), 도서 345, 자격증 66, 직무 80, 전공 132건이다. 저장 건수와 추천 가능한 건수는 다르다. 당시 품질·출처 조건을 만족한 강좌는 621, 도서 32, 자격증 26, 직무 13, 전공 29건이었다. 이후 적재에 따라 바뀔 수 있다.

남은 일: 부족한 MSA·FastAPI/Django 자료와 도서·자격증의 활용 가능한 근거를 공식 출처로 보완한다. 직무·전공의 IT 연결과 상세 내용을 점검한다. 규정의 검토 대기를 승인으로 취급하지 않는다. 학습 데이터의 근거 스냅샷은 수정하지 않는다.

강좌·도서·자격증은 image_url 컬럼에 공식 API 이미지 URL을 저장한다. 강좌 671/718·도서 345/345·자격증 59/66건이며 없는 값은 NULL이다. 직무·전공을 포함한 학습 자원 벡터 1,377개가 최신이고 규정 벡터 1,410개는 별도로 유지한다. 규정 전달용 SQL은 roadmap_app/data/exports/regulations_review_20261020.sql이며 Git에서 제외한다.

접속·실행·백업 방법은 [로컬 DB 안내](LOCAL_DB_REVIEW_20261020.md), 테이블 구조는 [ERD 최종](ERD_최종.html)를 따른다.

## 2. 파인튜닝 데이터

목표는 지식 암기보다 **근거 활용·조건 준수·실행 가능한 활동 제안·자료 부족 시 정직한 대응**을 학습시키는 것이다. 약 10개 설문 문항은 프로젝트에 따라 달라지며, 자기보고 점수를 객관적 능력으로 단정하지 않는다.

**1,500건을 선택한 이유는 일정상 학습·검증 시간을 단축하기 위해서다.** 이 수량이 최적이라는 실험 결과는 아직 없다. 긴 입력이 많아 데이터 수 감소와 실행 시간 감소가 정확히 비례하지는 않는다.

선별 방법: 기존 3,000건 중 범위 밖 400건을 제외하고, 기존 시험 답변 19건을 합친 2,619건을 점검했다. 로컬 검사와 대표 내용 검토에서 455건을 보류한 뒤, 유효 후보 2,164건 중 1,237건을 선택했다. 부족한 유형 263건을 보강해 총 1,500건으로 확정했다. 유형별 최소 60건을 확보하고 나머지는 로컬 검사·선별 우선순위에 따라 구성했다.

| 유형 | 총 건수 |
| --- | ---: |
| 로드맵 생성 | 1,003 |
| 부분 수정 | 197 |
| 5점 설문 | 60 |
| 자기평가 해석 | 60 |
| 제약 충돌 대응 | 60 |
| 근거 부족 대응 | 60 |
| 진행 점검 | 60 |
| 합계 | **1,500** |

| 용도 | 건수 | 사용 방법 |
| --- | ---: | --- |
| 학습 | 1,200 | 전체 사용 |
| 검증 | 150 | 학습 중 검증 |
| 별도 평가 | 150 | 학습에 넣지 않고 원본·어댑터 비교 |
| 보고서 공통 입력 | 10 | 위 1,500건과 별개로 동일 입력을 모든 비교에 사용 |

신규 263건은 OpenAI 원문 180, 에이전트 수정 7, 에이전트 직접 작성 76건이다. 직접 작성도 실제 입력·DB 근거를 사용한 답변이며 가짜 자료를 추가한 것이 아니다. 출처·선별 이유는 provenance에 기록한다.

검증 완료: 1,500건의 형식·자료 ID·DB 근거·중복·분할 검사, 실제 모델 토크나이저 길이·학습 마스크 검사. 기존 대표 10건과 보강 대표 10건을 에이전트가 내용 검토했다. **전수 의미 검수나 사람의 전수 검수는 하지 않았다.** 프로젝트 family가 12개로 제한돼 새로운 직무 전반의 성능을 보장하지 않는다. 승인된 규정 인용의 긍정 사례도 부족하다.

최대 길이는 6,858토큰으로, 설정 길이 7,168 안에 들어간다. 길이 적합성은 GPU 메모리 적합성과 별개다.

- 원본 확정본: roadmap_app/data/processed/curation_1500/release
- 학습 실행본: qwen_factory/data/production/curation_1500
- 공통 비교 입력: qwen_factory/data/eval/prompts.app_v1.jsonl
- 데이터 기준: roadmap_app/config/finetuning_1500.yaml

남은 일: 현재 분할과 파일 해시를 유지해 학습한다. 평가 150건과 보고서 10개의 정답을 학습에 넣지 않는다.

## 3. 파인튜닝 실행

| 항목 | 확정 내용 |
| --- | --- |
| 학생 모델 | Qwen/Qwen3.8-27B |
| 모델 revision | 1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0 |
| 장비 | 기존 RunPod A100 PCIe 80GB 1장 — 사용자 확인 |
| 방법 | NF4 4bit QLoRA, r32 / alpha64 / dropout 0.05 |
| 학습 범위 | 마지막 assistant 답변만 loss 계산 |
| 배치·길이 | 배치 1, 누적 16, 최대 길이 7,168 |
| 학습률·횟수 | 0.0001, 5 epoch, 4·5 epoch 어댑터 저장·비교 |
| 실행 설정 | configs/hyperparameters.production.pinned.yaml |
| 외부 연결 | HF 인증·저장소 조회 및 Neon SELECT 연결 성공 — 사용자 실행 결과 |
| 유료 자동 AI 평가 | 기본 꺼짐 |
| 현재 결과 | **최종 1,500건을 사용한 GPU 학습·성능 비교는 아직 실행하지 않음** |

앞으로 할 일은 다음 순서다.

1. 아래 환경 인계 절차로 다른 GPU 환경에 코드·고정 데이터를 전달한다. 현재 Pod은 CPU 점검 용도다.
2. 짧은 메모리·속도 점검 후 전체 실행 시간·비용을 산정한다. 시간당 GPU 요금과 총 비용 상한은 미확정이다.
3. 학습 1,200건 전체로 본 학습하고 검증 150건으로 상태를 확인한다.
4. 동일 조건에서 원본과 4·5 epoch 어댑터를 비교한다. 별도 평가 150건과 공통 보고서 입력 10개를 사용한다.
5. JSON 규격, 근거 밖 자료 추천, 시간·비용 준수, 수정 시 기존 조건 보존, 부족한 근거 대응을 평가한다.
6. 실제 측정값과 대표 답변을 이 문서에 반영하고 서비스 연결을 검증한다.

학습 전에는 향상률·학습 시간·비용을 결과처럼 기재하지 않는다. 서비스는 OpenAI 우선, 검증된 파인튜닝 Qwen 차순위이며 둘 다 사용 불가하면 'LLM 모델 없음'으로 처리한다.

## 실행 환경과 연결 확인

최상위 project 아래 roadmap_app과 qwen_factory를 사용한다. roadmap_app은 로컬 전용이고 팩토리만 Cloud에 배포한다. 최상위에는 통합 .env를 만들지 않는다. 실행 명령과 설정·복구는 [팩토리 안내](FINETUNING_GUIDE.md), 로컬 DB 사용법은 [DB 안내](LOCAL_DB_REVIEW_20261020.md)에서 관리한다.

이동 후 로드맵 회귀 131건 통과, 팩토리 회귀 47건 통과·Linux 전용 1건 제외. 실제 1,500건 양쪽 사본의 바이트/해시, DB 근거 스냅샷, 팩토리 등록 계획, Cloud 4개 파일 설치의 건수·분할 검증을 통과했다. Cloud 실제 실행·RunPod GPU 실행은 별도 확인 대상이다.


## 현재 환경 인계 상태 · 2026-10-20

현재 사용자 지시는 CPU 점검과 다른 환경에서 실행할 수 있는 인계 준비다. GPU 학습·모델 추론·가중치 다운로드는 실행하지 않았다. CPU Pod이 켜졌다는 이유로 학습을 제출하지 않는다.

| 확인 항목 | 결과 |
| --- | --- |
| 현재 Jupyter REST·WebSocket | 연결 성공. 점검용 커널은 종료함 |
| 원격 OS·Python | Linux / Python 3.12.3 |
| 원격 프로젝트 | /workspace/qwen_factory, .venv-runpod 존재 |
| 전용 가상환경 | torch 2.8.0+cu128, transformers 5.20.0, peft 0.21.2, accelerate 1.15.0, bitsandbytes 0.50.2, huggingface-hub 2.2.0, psycopg 3.3.6 |
| 의존성 차이 | 현재 CPU Pod SQLAlchemy 2.1.4, requirements-runpod.txt는 2.1.5. 다른 GPU 환경에서는 고정 파일 기준으로 설치·검증 |
| CPU Pod의 확정 설정·데이터 | production 설정과 train/validation/test 파일이 없음. 현재 Pod을 학습 준비 완료로 간주하지 않음 |
| CPU Pod 저장소 | /workspace: /dev/md127 150G, 사용 131G·여유 약 20G(87%). 컨테이너 overlay: 30G·거의 미사용. 모델·실험 공간 확장 대상은 /workspace의 Volume Disk |
| 모델 ID·revision | HF 메타데이터 접근 성공, 고정 revision 일치. 가중치는 다운로드하지 않음 |
| 로컬 학습 계획 | config_hash 2d392e23819e849415c837e02e4359f98325eaddeb4229f81f23d1df3015f8d3 |
| 로컬 검증 | 팩토리 53개 테스트 실행: 52 통과·Windows에서 실행할 수 없는 Linux 전용 테스트 1개 제외. Streamlit 실제 평가 함수의 묶음 전환 AppTest 통과 |
| 코드 전송 | 현재 CPU Pod에 변경 소스를 올리는 작업은 자동 승인 검토에서 명시적 외부 전송 승인 부족으로 차단됨. 전송하지 않음 |

평가 코드는 공통 10개(report)와 별도 150건(heldout)을 화면·동기화·저장 경로에서 구분한다. 학습 설정·데이터 해시·모델 revision·어댑터·생성 조건·출력·평가 이력을 연결한다. 서로 다른 생성 조건의 결과는 같은 평가 묶음 평균에 섞지 않는다. 기존 휴먼 평가 서명은 이전 결과에서도 유효하도록 유지한다.

별도 평가 150건에는 확정 데이터의 assistant 기준 답변이 있다. 전수 전문가 검수를 거친 정답은 아니므로 모델 출력과 함께 비교하되 사실의 절대 정답으로 취급하지 않는다. 공통 입력 10개에는 기준 답변이 없다. 임의 답변을 추가하지 않고 원본·어댑터 출력 비교에 사용한다. 기준 답변은 모델 프롬프트에서 제외한다.

### 다른 GPU 환경에 전달할 파일

qwen_factory에서 `python scripts/pack_production_handoff.py`를 실행하면 `outputs/gpu_production_handoff.zip`을 만든다. 이 로컬 ZIP에는 qwen_factory 코드·설정·의존성·테스트·확정 데이터 4종과 최상위 docs의 인계 문서 2종, 파일별 SHA-256을 담은 handoff_manifest.json이 들어간다. .env·토큰·DB·모델 가중치는 포함하지 않는다. 실제 데이터가 있으므로 Git에 올리지 않는다. 다른 환경으로의 업로드는 사용자 승인 범위에서 진행한다.

새 작업 폴더에서 ZIP을 풀면 qwen_factory와 docs가 나란히 생긴다. 기존 실험 폴더 위에 덮어쓰지 않는다. .env.example을 참고해 해당 환경의 .env를 직접 만들고 HF_TOKEN·HF_REPO_ID·DATABASE_URL을 설정한다. 웹 대시보드로 연결할 때만 해당 환경의 Jupyter URL·토큰을 설정한다. 기존 CPU Pod의 주소·토큰을 그대로 복사하지 않는다.

GPU 환경은 CUDA PyTorch·Python 3.12·A100 80GB 1장을 기준으로 준비했다. requirements-runpod.txt에는 CUDA 전용 패키지가 포함되므로 CPU 검증용으로 설치하지 않는다. 다른 GPU·CUDA·Python을 사용할 경우 호환성을 먼저 확인한다. 실제 GPU 메모리·처리 속도와 총 비용은 아직 측정하지 않았다.

### 새 환경 실행 순서

ZIP을 푼 최상위 폴더에서 먼저 파일 해시를 확인한다.

```python
import hashlib, json
from pathlib import Path
root = Path.cwd().resolve()
manifest = json.loads((root / "handoff_manifest.json").read_text(encoding="utf-8"))
for relative, expected in manifest["files"].items():
    path = (root / relative).resolve()
    assert path.is_relative_to(root)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, relative
print("handoff files verified")
```

다음 명령은 qwen_factory 폴더에서 실행한다.

```bash
python -m venv --system-site-packages .venv-runpod
source .venv-runpod/bin/activate
python -m pip install -r requirements-runpod.txt
python scripts/runpod_factory_sample.py --config configs/hyperparameters.production.pinned.yaml
python scripts/check_connections.py
```

첫 번째 runpod_factory_sample 명령은 CPU 미리보기다. 학습·Neon 등록·HF 업로드를 하지 않는다. 데이터 1,200/150/150, 공통 입력 10개와 고정 해시·모델 revision이 일치해야 한다. 실험을 시작하기 전 GPU 메모리·속도 점검을 실시하고 사용자와 실행 범위·비용을 확인한다.

GPU 실행이 가능하고 승인된 뒤에만 아래 명령으로 신규 학습과 전체 비교를 실행한다.

```bash
python scripts/control_pipeline.py --config configs/hyperparameters.production.pinned.yaml
```

이 명령은 실험 등록·학습 1,200건 전체·4/5 epoch 어댑터 저장 및 HF 업로드·공통 입력 10개와 별도 평가 150건의 원본/어댑터 비교를 수행한다. 유료 LLM 검수는 기본 꺼짐이다. 실패 재개는 원래 outputs/factory_*/실험 폴더·체크포인트·설정을 복원한 후 `--resume-existing`, 학습이 끝난 기존 가중치 비교만 실행할 때는 `--evaluate-only`를 추가한다. 기존 폴더 없이 임의로 재개하지 않는다.

완료 후 같은 문서에 실제 학습 시간·비용·손실·150건 평가·10개 대표 출력 비교와 한계를 반영한다. 아직 학습 결과나 향상률은 없다. 다음 작업자는 로컬 변경 사항의 테스트·Git 상태와 외부 전송 승인 여부부터 확인하고, 사용자에게 완료된 1~5번(DB·이미지·ERD)을 다시 질문하지 않는다.

저장 공간 관리: 같은 모델 revision의 HF 캐시를 공유하고, 필요하면 HF_HOME을 영구 볼륨 경로로 지정한다. 체크포인트 보관 3개 제한은 실험별 제한이므로 실험 수만큼 총량이 늘어난다. 재개에 필요한 최신 체크포인트와 최종 어댑터를 보존하고, 검증된 HF 업로드·백업 후 불필요한 중간 체크포인트를 정리한다. 삭제·볼륨 증설은 이번 작업에서 실행하지 않았다.


### 확인된 저장소 정리 후보

현재 /workspace/.cache는 56G, /workspace/qwen_factory/.cache는 53G(내부 huggingface 52G)다. 두 hub 디렉터리에 모두 Qwen/Qwen3.8-27B, revision 1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0이 있다. 동일 모델 캐시를 한곳으로 통합하면 약 52G 확보 가능성이 있다. 이 확인은 폴더·revision 메타데이터 기준이며 실제 삭제 전 블롭 완전성, 사용 중인 HF_HOME과 심볼릭 링크를 확인해야 한다.

outputs는 22G(factory_sample 18G, smoke_002 4.5G)다. 샘플 어댑터는 파일당 약 0.87G이며 중간 체크포인트와 최종 artifacts에 여러 개 있다. reports는 약 1.2M라 삭제 효과가 작다. 원본 학습 데이터도 632K인 기존 샘플만 원격에 있으며, 현재 디스크 사용량의 주요 원인은 데이터 1,500건이 아니다.

정리 순서: 캐시 한곳 통합 → 끝난 샘플 실험의 중간 체크포인트 검토 → 불필요한 smoke 출력 검토. 최종 4/5 epoch 어댑터·매니페스트·고정 데이터·설정·평가 결과는 보존한다. HF 업로드가 정상인지 확인하고 재개가 필요하면 최신 체크포인트의 optimizer/scheduler/RNG 상태도 함께 남긴다. 완료된 실험만 대상으로 하며 실행 중이거나 미완료 실험은 정리하지 않는다. 캐시·출력 삭제와 볼륨 증설은 현재 승인·실행하지 않았다. 기존 고정 설정의 save_total_limit=3은 변경하지 않았다.
