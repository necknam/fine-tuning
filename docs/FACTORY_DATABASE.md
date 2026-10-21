# 팩토리 실험 DB

2026-10-21 실제 조회 기준. Neon PostgreSQL 18.6을 사용한다. 로컬 업무 DB와 독립적이며 `qwen_factory/.env`의 DATABASE_URL 또는 Cloud Secrets로 연결한다. 비밀값은 문서·Git에 넣지 않는다.

## 역할

- `public.qf_runs`: 실험 UUID, 설정·데이터 해시, 확정 설정, 실행 상태.
- `public.qf_artifacts`: run_id와 epoch별 weight_id, 저장·업로드 상태, HF 저장소·커밋·하위 경로. 실제 어댑터 파일은 HF와 RunPod에 둔다.
- `public.qf_run_leases`: 중복 실행을 막는 만료형 실행권. qf_runs를 참조한다.
- `qf_dashboard.documents`: 화면 복원용 설정·실험 이력·비교 결과 JSON.
- `qf_dashboard.case_evaluations`: 사용자가 입력한 평가 이력.
- `qf_dashboard.ai_evaluations`, `ai_queue`, `ai_worker_lease`: 선택적 유료 AI 평가 기능의 기록·대기열·실행권. 현재 실험에서는 호출하거나 점수를 저장하지 않는다.

run_id → weight_id → 고정 평가 입력 해시·생성 조건·출력으로 실험을 추적한다. 다른 프롬프트 버전의 결과를 같은 조건의 개선량으로 해석하지 않는다. 현재 V2 평가는 어시스턴트 내용 검토만 수행한다.

## 설치·연결

`python scripts/check_connections.py`는 HF 인증·저장소 및 DB 연결을 확인한다. 신규 팩토리 테이블은 db_registry.py의 등록 단계, 화면 문서는 dashboard_store.initialize, 평가 테이블은 각 기능 초기화 시 생성한다. 기존 Neon을 초기화하거나 로컬 업무 DB 전체 백업을 Neon에 덮어쓰지 않는다.

## 실제 테이블·관계

### `public.qf_artifacts`

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `weight_id` | character varying | NO |
| `run_id` | character varying | NO |
| `trained_epoch` | integer | NO |
| `status` | character varying | NO |
| `hf_repo_id` | character varying | YES |
| `hf_revision` | character varying | YES |
| `hf_subfolder` | character varying | YES |

- `PRIMARY KEY (weight_id)`

- `FOREIGN KEY (run_id) REFERENCES qf_runs(run_id)`

- `NOT NULL run_id`

- `NOT NULL status`

- `NOT NULL trained_epoch`

- `NOT NULL weight_id`

- `UNIQUE (run_id, trained_epoch)`

### `public.qf_run_leases`

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `run_id` | character varying | NO |
| `owner_token` | character varying | NO |
| `expires_at` | timestamp with time zone | NO |

- `NOT NULL expires_at`

- `NOT NULL owner_token`

- `PRIMARY KEY (run_id)`

- `FOREIGN KEY (run_id) REFERENCES qf_runs(run_id)`

- `NOT NULL run_id`

### `public.qf_runs`

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `run_id` | character varying | NO |
| `config_hash` | character varying | NO |
| `recipe_name` | character varying | NO |
| `is_sample` | boolean | NO |
| `status` | character varying | NO |
| `config` | json | NO |
| `created_at` | timestamp with time zone | NO |

- `UNIQUE (config_hash)`

- `NOT NULL config_hash`

- `NOT NULL config`

- `NOT NULL created_at`

- `NOT NULL is_sample`

- `PRIMARY KEY (run_id)`

- `NOT NULL recipe_name`

- `NOT NULL run_id`

- `NOT NULL status`

### `qf_dashboard.ai_evaluations`

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `id` | text | NO |
| `weight_id` | text | YES |
| `signature` | text | YES |
| `model` | text | YES |
| `rubric` | text | YES |
| `created_at` | text | YES |
| `payload` | text | YES |

- `NOT NULL id`

- `PRIMARY KEY (id)`

### `qf_dashboard.ai_queue`

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `task` | text | NO |
| `weight` | text | YES |
| `case_index` | integer | YES |
| `model` | text | YES |
| `state` | text | YES |
| `error` | text | YES |
| `updated` | double precision | YES |

- `PRIMARY KEY (task)`

- `NOT NULL task`

### `qf_dashboard.ai_worker_lease`

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `id` | integer | NO |
| `owner` | text | YES |
| `expires` | double precision | YES |

- `NOT NULL id`

- `PRIMARY KEY (id)`

### `qf_dashboard.case_evaluations`

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `evaluation_id` | text | NO |
| `weight_id` | text | NO |
| `case_index` | integer | NO |
| `evaluator` | text | NO |
| `created_at` | text | NO |
| `payload` | text | NO |

- `NOT NULL case_index`

- `NOT NULL created_at`

- `NOT NULL evaluation_id`

- `NOT NULL evaluator`

- `NOT NULL payload`

- `PRIMARY KEY (evaluation_id)`

- `NOT NULL weight_id`

### `qf_dashboard.documents`

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `path` | text | NO |
| `content` | text | NO |
| `updated_at` | timestamp with time zone | NO |

- `NOT NULL content`

- `NOT NULL path`

- `PRIMARY KEY (path)`

- `NOT NULL updated_at`
