> 2026-10-26 로컬 PostgreSQL 실측: 가상 직원 100명·기존 사용자 5명, 총 105명. 마이그레이션 001~020 적용. 이전 Cloud 원본과 완전 일치하는 복원이 아닌 승인된 시드 재구성이다.

# 로컬 DB 사용 안내

DB는 Docker 없이 PostgreSQL 17.11 + pgvector 0.8.2를 사용한다. 업무 데이터는 로컬 growpath, 팩토리 실험 기록은 Neon에 저장한다. 전체 현황과 남은 일은 [통합 보고서](CODEX_HANDOFF.md)를 참고한다.

## 실행과 백업

최상위 project 안의 database 폴더에서 실행한다. 로드맵 UI·에이전트·학습 데이터 생성 코드는 이 저장소에서 제거했다. 기존 테이블과 DB 저장 API는 유지한다.

```powershell
$py = "$env:USERPROFILE\miniforge3\envs\llm_env\python.exe"
& $py scripts/local_db.py start
& $py scripts/local_db.py status
& $py scripts/db.py verify
& $py -m src.database.vectors.resource_vectors status
& $py -m src.database.vectors.regulation_vectors status
```

중지는 `& $py scripts/local_db.py stop`, 백업은 `& $py scripts/local_db.py backup --output 원하는경로.dump`다. 물리 파일은 `data/local_db/postgres` 전체이며 개별 파일을 삭제하거나 편집하지 않는다. 연결은 `.env.local`, 실행 파일은 그 안의 `POSTGRES_BIN_DIR` 설정을 사용한다.

## PyCharm 접속

View → Tool Windows → Database → ＋ → Data Source → PostgreSQL에서 입력한다.

| 항목 | 값 |
| --- | --- |
| Host | 127.0.0.1 |
| Port | 55433 |
| User | postgres |
| Password | database/.env.local의 POSTGRES_PASSWORD |
| Database | **growpath** |
| SSL | 사용 안 함 |

Test Connection 후 Schemas에서 public, regulations, growpath_meta, growpath_legacy를 선택한다. SQL 콘솔도 growpath 연결을 선택해야 한다. postgres DB에서는 앱 테이블이 보이지 않는다.

```sql
SELECT current_database(), inet_server_port();
SELECT COUNT(*) FROM public.courses;
SELECT * FROM public.skill_tags ORDER BY skill_id;
```

현재 구조는 [ERD 최종](ERD_최종.html)을 참고한다. 현재 로컬 DB는 실제 테이블 50개·FK 85개다. 호환 뷰는 테이블 수에 포함하지 않는다. 빈 과거 테이블 ai_cases·regulations·employee_skill_gaps는 008 마이그레이션에서 제거했다. 원본 자료의 중복 embedding 컬럼은 제거했으며, 검색 벡터는 public.learning_resource_embeddings와 regulations.rag_chunk_embeddings에서 관리한다. 기존 명령 호환용 뷰는 테이블 수에 포함하지 않는다.

미확정 직원 14명의 기관·부서·직급·직무는 추정해서 채우지 않았다. 직원 조회는 정식 기관·부서·직급·직무 참조를 우선 사용한다. `update_employee_assignment`로 소속을 확정하면 중복 department·grade·job_title 문자열을 비운다. 미확정 값이 남아 있어 컬럼 자체는 아직 제거하지 않는다.

로드맵 수정은 `update_roadmap_content`가 content와 단계·자료 연결을 같은 트랜잭션에서 갱신한다. 변경 없는 활동은 완료 상태를 유지하고, 제목·활동·기간이 바뀐 단계는 완료 상태를 해제한다. 최초 baseline_content는 변경하지 않는다. 진행 체크만 바꾸는 경우 코멘트에 수정 완료 표시를 하지 않는다. DB를 직접 수정하는 SQL은 이 API의 동기화를 거치지 않으므로 앱 수정 경로에서는 사용하지 않는다.

부서장은 담당 부서·하위 부서 프로젝트를 조회하고 본인 코멘트를 작성·수정·삭제할 수 있으며, 일반 직원의 로드맵이나 완료 체크를 수정할 수 없다. 직원 계정 정보를 조회하는 API는 password_hash를 반환하지 않는다.

신규 설치는 `& $py scripts/db.py migrate`, 구조 검증은 `& $py scripts/db.py verify`를 사용한다. 벡터 테이블·수집 이력 테이블도 설치 단계에 포함된다. 실제 DB 기준 메타데이터는 src/database/catalog.current.json, 이전 패키지를 읽기 위한 메타데이터는 catalog.json이다. 이전 001~008 마이그레이션 파일은 적용 후 수정하지 않는다.

스킬 36·강좌 116·도서 334·자격증 26·직무 6·전공 7건, 자료 벡터 525개를 실제 조회했다. 규정 청크 벡터 1,410개는 별도 테이블에 유지한다. 두 벡터 테이블은 같은 검색 대상으로 무조건 혼합하지 않는다.

복구 백업과 data/local_db/postgres는 정리 대상이 아니다. ERD는 `python -m src.database.erd --template ../docs/ERD_최종.html`로 현재 DB 기준 재생성할 수 있다.

강좌·도서·자격증의 이미지 URL은 각 테이블의 image_url에 저장한다. 없는 값은 NULL을 유지하며 이미지 유무로 추천 품질을 판정하지 않는다.

계획 초안·확정은 projects.draft_prompt_version_id·plan_prompt_version_id, 선택 로드맵은 roadmaps.prompt_version_id로 실제 사용한 prompt_versions를 참조한다. 과거 결과·코드 폴백은 NULL을 유지하며 현재 활성 버전을 과거 결과에 소급하지 않는다.


## 전체 백업과 재현

- 전체 백업: `database/data/exports/growpath_full_20261021.dump` (45,390,365바이트).
- 무결성·건수·제약조건: 옆의 `.manifest.json`. 같은 DB 스냅샷에서 조회한 메타데이터와 SHA-256을 기록한다.
- 별도 DB `growpath_restore_verify_20261021`에 복원 검증 완료: 50개 테이블, 29,903행, 202개 제약조건, 자료·규정 벡터 연산 통과.
- 설치·복원: 최상위 [DB_복원.md](../DB_복원.md). 로컬 관리자 비밀번호와 역할은 복원 대상에 포함하지 않고 새 PC에서 설정한다.
- 데이터 파일·시퀀스·함수·뷰·임베딩은 전체 덤프에 포함한다. 외부 PDF는 `database/data/regulations`에 따로 보존한다. 외부 저장소의 파일까지 DB 덤프가 복사하지는 않는다.
- Windows x64 PostgreSQL 17용 pgvector 0.8.2 파일은 exports의 `pgvector_pg17_windows_x64`에 라이선스·해시와 함께 둔다. 다른 OS/메이저 버전에는 그대로 설치하지 않는다.

## 각 테이블의 현재 구조

2026-10-26 실제 로컬 DB 조회 기준. 호환 뷰는 테이블 목록에 포함하지 않는다.

### `growpath_legacy.agent_generations` · 71행

기본키: PRIMARY KEY (generation_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `generation_id` | uuid | NO |
| `request_id` | uuid | NO |
| `agent_id` | character varying(50) | NO |
| `prompt_version_id` | uuid | YES |
| `provider` | character varying(50) | NO |
| `model` | character varying(100) | NO |
| `roadmap_content` | jsonb | NO |
| `summary` | text | NO |
| `latency_ms` | integer | NO |
| `status` | character varying(20) | NO |
| `created_at` | timestamp with time zone | NO |

참조 관계:

- `FOREIGN KEY (prompt_version_id) REFERENCES prompt_versions(prompt_version_id)`
- `FOREIGN KEY (request_id) REFERENCES growpath_legacy.roadmap_requests(request_id) ON DELETE CASCADE`

검증 조건:

- `CHECK (agent_id::text = ANY (ARRAY['agent_practical'::character varying::text, 'agent_certified'::character varying::text, 'agent_fasttrack'::character varying::text]))`
- `CHECK (status::text = ANY (ARRAY['SUCCESS'::character varying::text, 'FAILED'::character varying::text, 'TIMEOUT'::character varying::text]))`

### `growpath_legacy.agent_selections` · 20행

기본키: PRIMARY KEY (selection_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `selection_id` | uuid | NO |
| `request_id` | uuid | NO |
| `chosen_generation_id` | uuid | NO |
| `chosen_agent_id` | character varying(50) | NO |
| `selection_reason` | text | YES |
| `user_type` | character varying(20) | NO |
| `created_at` | timestamp with time zone | NO |

참조 관계:

- `FOREIGN KEY (chosen_generation_id) REFERENCES growpath_legacy.agent_generations(generation_id) ON DELETE CASCADE`
- `FOREIGN KEY (request_id) REFERENCES growpath_legacy.roadmap_requests(request_id) ON DELETE CASCADE`

검증 조건:

- `CHECK (chosen_agent_id::text = ANY (ARRAY['agent_practical'::character varying::text, 'agent_certified'::character varying::text, 'agent_fasttrack'::character varying::text]))`
- `CHECK (user_type::text = ANY (ARRAY['REAL_USER'::character varying::text, 'TEST_MANUAL'::character varying::text, 'TEST_AUTO'::character varying::text]))`

### `growpath_legacy.finetuning_datasets` · 2행

기본키: PRIMARY KEY (dataset_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `dataset_id` | uuid | NO |
| `dataset_type` | character varying(20) | NO |
| `record_count` | integer | NO |
| `export_path` | text | NO |
| `pii_masked` | boolean | NO |
| `filter_criteria` | jsonb | NO |
| `created_at` | timestamp with time zone | NO |

검증 조건:

- `CHECK (dataset_type::text = ANY (ARRAY['SFT_JSONL'::character varying::text, 'DPO_JSONL'::character varying::text, 'HF_DATASET'::character varying::text]))`

### `growpath_legacy.preference_pairs` · 4행

기본키: PRIMARY KEY (pair_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `pair_id` | uuid | NO |
| `request_id` | uuid | NO |
| `chosen_generation_id` | uuid | NO |
| `rejected_generation_id` | uuid | NO |
| `prompt_input` | jsonb | NO |
| `chosen_output` | jsonb | NO |
| `rejected_output` | jsonb | NO |
| `user_type` | character varying(20) | NO |
| `created_at` | timestamp with time zone | NO |

참조 관계:

- `FOREIGN KEY (chosen_generation_id) REFERENCES growpath_legacy.agent_generations(generation_id) ON DELETE CASCADE`
- `FOREIGN KEY (rejected_generation_id) REFERENCES growpath_legacy.agent_generations(generation_id) ON DELETE CASCADE`
- `FOREIGN KEY (request_id) REFERENCES growpath_legacy.roadmap_requests(request_id) ON DELETE CASCADE`

검증 조건:

- `CHECK (user_type::text = ANY (ARRAY['REAL_USER'::character varying::text, 'TEST_MANUAL'::character varying::text, 'TEST_AUTO'::character varying::text]))`

### `growpath_legacy.roadmap_requests` · 25행

기본키: PRIMARY KEY (request_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `request_id` | uuid | NO |
| `user_type` | character varying(20) | NO |
| `employee_id` | character varying(64) | YES |
| `raw_user_prompt` | text | NO |
| `conversation_history` | jsonb | NO |
| `user_requirements` | jsonb | NO |
| `retrieved_context` | jsonb | NO |
| `created_at` | timestamp with time zone | NO |

검증 조건:

- `CHECK (user_type::text = ANY (ARRAY['REAL_USER'::character varying::text, 'TEST_MANUAL'::character varying::text, 'TEST_AUTO'::character varying::text]))`

### `growpath_legacy.test_mock_profiles` · 39행

기본키: PRIMARY KEY (profile_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `profile_id` | uuid | NO |
| `source_type` | character varying(20) | NO |
| `profile_name` | character varying(100) | NO |
| `department` | character varying(100) | NO |
| `grade` | character varying(50) | NO |
| `job_title` | character varying(100) | NO |
| `career_years` | integer | NO |
| `current_skills` | jsonb | NO |
| `target_skills` | jsonb | NO |
| `work_context_summary` | text | NO |
| `created_at` | timestamp with time zone | NO |

검증 조건:

- `CHECK (source_type::text = ANY (ARRAY['TEST_MANUAL'::character varying::text, 'TEST_AUTO'::character varying::text]))`

### `growpath_meta.catalog_api_sources` · 489행

기본키: PRIMARY KEY (resource_type, source, external_key)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `resource_type` | text | NO |
| `source` | text | NO |
| `external_key` | text | NO |
| `entity_key` | text | NO |
| `payload` | jsonb | NO |
| `mapping_evidence` | jsonb | NO |
| `fetched_at` | timestamp with time zone | NO |

### `growpath_meta.schema_migrations` · 20행

기본키: PRIMARY KEY (version)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `version` | text | NO |
| `sha256` | text | NO |
| `applied_at` | timestamp with time zone | NO |

### `public.assessment_questions` · 25행

기본키: PRIMARY KEY (question_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `question_id` | uuid | NO |
| `project_id` | uuid | NO |
| `assessment_type` | character varying(20) | NO |
| `skill_id` | integer | YES |
| `skill` | character varying(100) | NO |
| `question` | text | NO |
| `options` | jsonb | YES |
| `sequence_no` | integer | NO |
| `created_at` | timestamp with time zone | NO |
| `diagnostic_round_id` | uuid | NO |

참조 관계:

- `FOREIGN KEY (diagnostic_round_id, project_id) REFERENCES diagnostic_rounds(diagnostic_round_id, project_id) ON DELETE CASCADE`
- `FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE`
- `FOREIGN KEY (skill_id) REFERENCES skill_tags(skill_id)`

검증 조건:

- `CHECK (assessment_type::text = ANY (ARRAY['PRE'::character varying::text, 'POST'::character varying::text]))`

### `public.assessment_responses` · 25행

기본키: PRIMARY KEY (response_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `response_id` | uuid | NO |
| `project_id` | uuid | NO |
| `question_id` | uuid | NO |
| `assessment_type` | character varying(20) | NO |
| `selected_option` | text | NO |
| `score` | integer | NO |
| `answered_at` | timestamp with time zone | NO |

참조 관계:

- `FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE`
- `FOREIGN KEY (question_id, project_id, assessment_type) REFERENCES assessment_questions(question_id, project_id, assessment_type) ON DELETE CASCADE`

검증 조건:

- `CHECK (assessment_type::text = ANY (ARRAY['PRE'::character varying::text, 'POST'::character varying::text]))`
- `CHECK (score >= 1 AND score <= 5)`

### `public.book_skills` · 506행

기본키: PRIMARY KEY (isbn, skill_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `isbn` | character varying(20) | NO |
| `skill_id` | integer | NO |

참조 관계:

- `FOREIGN KEY (isbn) REFERENCES books(isbn) ON DELETE CASCADE`
- `FOREIGN KEY (skill_id) REFERENCES skill_tags(skill_id) ON DELETE CASCADE`

### `public.books` · 334행

기본키: PRIMARY KEY (isbn)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `isbn` | character varying(20) | NO |
| `title` | character varying(200) | NO |
| `author` | character varying(100) | YES |
| `publisher` | character varying(100) | YES |
| `loan_count` | integer | YES |
| `kdc_code` | character varying(10) | YES |
| `last_batch_updated` | timestamp with time zone | YES |
| `record_source` | character varying(40) | NO |
| `source_url` | text | YES |
| `content_status` | text | YES |
| `source_verified_at` | timestamp with time zone | YES |
| `description` | text | YES |
| `image_url` | text | YES |
| `ai_mention` | text | YES |

### `public.certification_skills` · 43행

기본키: PRIMARY KEY (cert_id, skill_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `cert_id` | integer | NO |
| `skill_id` | integer | NO |

참조 관계:

- `FOREIGN KEY (cert_id) REFERENCES certifications(cert_id) ON DELETE CASCADE`
- `FOREIGN KEY (skill_id) REFERENCES skill_tags(skill_id) ON DELETE CASCADE`

### `public.certifications` · 26행

기본키: PRIMARY KEY (cert_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `cert_id` | integer | NO |
| `title` | character varying(100) | NO |
| `provider` | character varying(50) | YES |
| `test_subjects` | text | YES |
| `career_outlook` | text | YES |
| `exam_type` | character varying(20) | YES |
| `pass_score` | integer | YES |
| `last_batch_updated` | timestamp with time zone | YES |
| `record_source` | character varying(40) | NO |
| `source_url` | text | YES |
| `content_status` | text | YES |
| `source_verified_at` | timestamp with time zone | YES |
| `description` | text | YES |
| `image_url` | text | YES |
| `ai_mention` | text | YES |

### `public.course_skills` · 173행

기본키: PRIMARY KEY (course_id, skill_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `course_id` | character varying(50) | NO |
| `skill_id` | integer | NO |

참조 관계:

- `FOREIGN KEY (course_id) REFERENCES courses(course_id) ON DELETE CASCADE`
- `FOREIGN KEY (skill_id) REFERENCES skill_tags(skill_id) ON DELETE CASCADE`

### `public.courses` · 116행

기본키: PRIMARY KEY (course_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `course_id` | character varying(50) | NO |
| `title` | character varying(200) | NO |
| `category_name` | character varying(50) | YES |
| `org_name` | character varying(100) | YES |
| `url` | character varying(255) | YES |
| `is_matchup` | boolean | YES |
| `cost` | numeric(10,2) | YES |
| `duration_weeks` | integer | YES |
| `recruitment_status` | character varying(30) | YES |
| `syllabus_summary` | text | YES |
| `last_batch_updated` | timestamp with time zone | YES |
| `platform` | character varying(50) | NO |
| `difficulty` | character varying(20) | YES |
| `record_source` | character varying(40) | NO |
| `source_url` | text | YES |
| `content_status` | text | YES |
| `source_verified_at` | timestamp with time zone | YES |
| `image_url` | text | YES |
| `enrollment_start` | timestamp with time zone | YES |
| `enrollment_end` | timestamp with time zone | YES |
| `enrollment_period_type` | text | NO |
| `ai_mention` | text | YES |

검증 조건:

- `CHECK (difficulty::text = ANY (ARRAY['BEGINNER'::character varying::text, 'INTERMEDIATE'::character varying::text, 'ADVANCED'::character varying::text]))`
- `CHECK (enrollment_start IS NULL OR enrollment_end IS NULL OR enrollment_start <= enrollment_end)`
- `CHECK (enrollment_period_type = ANY (ARRAY['scheduled'::text, 'unrestricted'::text, 'unknown'::text]))`
- `CHECK (enrollment_period_type = 'scheduled'::text AND enrollment_start IS NOT NULL AND enrollment_end IS NOT NULL OR enrollment_period_type = 'unrestricted'::text AND enrollment_start IS NULL AND enrollment_end IS NULL OR enrollment_period_type = 'unknown'::text)`

### `public.departments` · 14행

기본키: PRIMARY KEY (department_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `department_id` | bigint | NO |
| `institution_id` | character varying(64) | NO |
| `department_code` | text | NO |
| `name` | text | NO |
| `parent_department_id` | bigint | YES |

참조 관계:

- `FOREIGN KEY (institution_id) REFERENCES institutions(institution_id)`
- `FOREIGN KEY (parent_department_id, institution_id) REFERENCES departments(department_id, institution_id)`

검증 조건:

- `CHECK (parent_department_id IS DISTINCT FROM department_id)`

### `public.diagnostic_rounds` · 2행

기본키: PRIMARY KEY (diagnostic_round_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `diagnostic_round_id` | uuid | NO |
| `project_id` | uuid | NO |
| `round_number` | integer | NO |
| `project_snapshot` | jsonb | NO |
| `agent_input` | jsonb | YES |
| `diagnostic_result` | jsonb | YES |
| `pre_completed_at` | timestamp with time zone | YES |
| `post_completed_at` | timestamp with time zone | YES |
| `created_at` | timestamp with time zone | NO |

참조 관계:

- `FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE`

검증 조건:

- `CHECK (round_number > 0)`

### `public.employee_certifications` · 96행

기본키: PRIMARY KEY (employee_id, certification_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `employee_id` | integer | NO |
| `certification_id` | integer | NO |

참조 관계:

- `FOREIGN KEY (certification_id) REFERENCES certifications(cert_id)`
- `FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE`

### `public.employee_education_records` · 100행

기본키: PRIMARY KEY (education_record_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `education_record_id` | uuid | NO |
| `employee_id` | integer | NO |
| `school_name` | text | NO |
| `education_level` | text | NO |
| `department_name` | text | YES |
| `major_id` | integer | YES |
| `enrollment_date` | date | YES |
| `graduation_date` | date | YES |

참조 관계:

- `FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE`
- `FOREIGN KEY (major_id) REFERENCES majors(major_id)`

검증 조건:

- `CHECK (enrollment_date IS NULL OR graduation_date IS NULL OR graduation_date >= enrollment_date)`
- `CHECK (education_level = ANY (ARRAY['middle_school_or_lower'::text, 'high_school'::text, 'associate'::text, 'bachelor'::text, 'master'::text, 'doctorate'::text, 'other'::text]))`
- `CHECK (length(TRIM(BOTH FROM school_name)) > 0)`

### `public.employee_recommended_prompts` · 0행

기본키: PRIMARY KEY (prompt_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `prompt_id` | uuid | NO |
| `employee_id` | integer | YES |
| `prompt_text` | text | YES |
| `display_order` | smallint | YES |
| `updated_at` | timestamp with time zone | YES |

참조 관계:

- `FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE`

검증 조건:

- `CHECK (display_order >= 1 AND display_order <= 3)`
- `CHECK (prompt_text IS NULL OR length(btrim(prompt_text)) > 0)`

### `public.employee_skills` · 293행

기본키: PRIMARY KEY (employee_id, skill_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `employee_id` | integer | NO |
| `skill_id` | integer | NO |

참조 관계:

- `FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE`
- `FOREIGN KEY (skill_id) REFERENCES skill_tags(skill_id)`

### `public.employees` · 105행

기본키: PRIMARY KEY (employee_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `employee_id` | integer | NO |
| `name` | character varying(50) | NO |
| `job_id` | integer | YES |
| `created_at` | timestamp with time zone | YES |
| `is_degree_seeker` | boolean | YES |
| `email` | character varying(255) | YES |
| `department` | character varying(100) | YES |
| `job_title` | character varying(100) | YES |
| `grade` | character varying(50) | YES |
| `source_type` | character varying(20) | YES |
| `updated_at` | timestamp with time zone | YES |
| `institution_id` | character varying(64) | YES |
| `employee_number` | text | YES |
| `password_hash` | text | YES |
| `department_id` | bigint | YES |
| `job_grade_id` | bigint | YES |
| `is_department_head` | boolean | NO |
| `hire_date` | date | YES |
| `department_start_date` | date | YES |
| `planned_project_description` | text | YES |
| `unlisted_certifications` | text | YES |

참조 관계:

- `FOREIGN KEY (department_id, institution_id) REFERENCES departments(department_id, institution_id)`
- `FOREIGN KEY (job_grade_id, institution_id) REFERENCES job_grades(job_grade_id, institution_id)`
- `FOREIGN KEY (institution_id) REFERENCES institutions(institution_id)`
- `FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE SET NULL`

검증 조건:

- `CHECK (department_id IS NULL OR institution_id IS NOT NULL)`
- `CHECK (hire_date IS NULL OR department_start_date IS NULL OR department_start_date >= hire_date)`
- `CHECK (job_grade_id IS NULL OR institution_id IS NOT NULL)`
- `CHECK (NOT is_department_head OR department_id IS NOT NULL)`
- `CHECK (employee_number IS NOT NULL AND employee_number !~ '^[[:space:]]*$'::text) NOT VALID`
- `CHECK (password_hash IS NULL OR password_hash ~~ '$argon2id$%%'::text)`
- `CHECK (planned_project_description IS NULL OR length(btrim(planned_project_description)) > 0)`
- `CHECK (unlisted_certifications IS NULL OR length(btrim(unlisted_certifications)) > 0)`

### `public.growth_reports` · 1행

기본키: PRIMARY KEY (report_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `report_id` | uuid | NO |
| `project_id` | uuid | NO |
| `report_type` | character varying(30) | NO |
| `report_content` | jsonb | NO |
| `created_at` | timestamp with time zone | NO |
| `roadmap_id` | uuid | NO |

참조 관계:

- `FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE`
- `FOREIGN KEY (roadmap_id) REFERENCES roadmaps(roadmap_id) ON DELETE CASCADE`
- `FOREIGN KEY (roadmap_id, project_id) REFERENCES roadmaps(roadmap_id, project_id) ON DELETE CASCADE`

### `public.institutions` · 1행

기본키: PRIMARY KEY (institution_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `institution_id` | character varying(64) | NO |
| `name` | character varying(255) | NO |
| `external_code` | character varying(255) | YES |
| `institution_code` | text | YES |

### `public.job_grades` · 5행

기본키: PRIMARY KEY (job_grade_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `job_grade_id` | bigint | NO |
| `institution_id` | character varying(64) | NO |
| `name` | text | NO |
| `sort_order` | integer | NO |

참조 관계:

- `FOREIGN KEY (institution_id) REFERENCES institutions(institution_id)`

### `public.job_skills` · 8행

기본키: PRIMARY KEY (job_id, skill_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `job_id` | integer | NO |
| `skill_id` | integer | NO |

참조 관계:

- `FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE`
- `FOREIGN KEY (skill_id) REFERENCES skill_tags(skill_id) ON DELETE CASCADE`

### `public.jobs` · 6행

기본키: PRIMARY KEY (job_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `job_id` | integer | NO |
| `title` | character varying(100) | NO |
| `ncs_units` | text | YES |
| `last_batch_updated` | timestamp with time zone | YES |
| `record_source` | character varying(40) | NO |
| `source_url` | text | YES |
| `content_status` | text | YES |
| `source_verified_at` | timestamp with time zone | YES |
| `description` | text | YES |

### `public.learning_resource_embeddings` · 525행

기본키: PRIMARY KEY (resource_type, resource_id, embedding_model)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `resource_type` | text | NO |
| `resource_id` | text | NO |
| `embedding_model` | text | NO |
| `dimensions` | integer | NO |
| `input_version` | text | NO |
| `input_sha256` | text | NO |
| `embedding` | vector(1536) | NO |
| `updated_at` | timestamp with time zone | NO |
| `skill_id` | integer | YES |
| `course_id` | character varying(255) | YES |
| `isbn` | character varying(20) | YES |
| `certification_id` | integer | YES |
| `job_id` | integer | YES |
| `major_id` | integer | YES |

참조 관계:

- `FOREIGN KEY (certification_id) REFERENCES certifications(cert_id) ON DELETE CASCADE`
- `FOREIGN KEY (course_id) REFERENCES courses(course_id) ON DELETE CASCADE`
- `FOREIGN KEY (isbn) REFERENCES books(isbn) ON DELETE CASCADE`
- `FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE`
- `FOREIGN KEY (major_id) REFERENCES majors(major_id) ON DELETE CASCADE`
- `FOREIGN KEY (skill_id) REFERENCES skill_tags(skill_id) ON DELETE CASCADE`

검증 조건:

- `CHECK (dimensions = 1536)`
- `CHECK (vector_norm(embedding) > 0::double precision)`
- `CHECK (length(input_sha256) = 64)`
- `CHECK (resource_type = ANY (ARRAY['skills'::text, 'courses'::text, 'books'::text, 'certifications'::text, 'jobs'::text, 'majors'::text]))`
- `CHECK (num_nonnulls(skill_id, course_id, isbn, certification_id, job_id, major_id) = 1)`
- `CHECK (resource_type = 'skills'::text AND skill_id::text = resource_id OR resource_type = 'courses'::text AND course_id::text = resource_id OR resource_type = 'books'::text AND isbn::text = resource_id OR resource_type = 'certifications'::text AND certification_id::text = resource_id OR resource_type = 'jobs'::text AND job_id::text = resource_id OR resource_type = 'majors'::text AND major_id::text = resource_id)`
- `CHECK (
CASE resource_type
    WHEN 'skills'::text THEN skill_id IS NOT NULL
    WHEN 'courses'::text THEN course_id IS NOT NULL
    WHEN 'books'::text THEN isbn IS NOT NULL
    WHEN 'certifications'::text THEN certification_id IS NOT NULL
    WHEN 'jobs'::text THEN job_id IS NOT NULL
    WHEN 'majors'::text THEN major_id IS NOT NULL
    ELSE false
END)`

### `public.major_skills` · 14행

기본키: PRIMARY KEY (major_id, skill_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `major_id` | integer | NO |
| `skill_id` | integer | NO |

참조 관계:

- `FOREIGN KEY (major_id) REFERENCES majors(major_id) ON DELETE CASCADE`
- `FOREIGN KEY (skill_id) REFERENCES skill_tags(skill_id) ON DELETE CASCADE`

### `public.majors` · 7행

기본키: PRIMARY KEY (major_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `major_id` | integer | NO |
| `title` | character varying(100) | NO |
| `curriculum` | text | YES |
| `last_batch_updated` | timestamp with time zone | YES |
| `source_url` | text | YES |
| `content_status` | text | YES |
| `source_verified_at` | timestamp with time zone | YES |
| `description` | text | YES |

### `public.projects` · 2행

기본키: PRIMARY KEY (project_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `project_id` | uuid | NO |
| `employee_id` | integer | NO |
| `project_name` | character varying(255) | NO |
| `status` | character varying(50) | NO |
| `current_stage` | integer | NO |
| `created_at` | timestamp with time zone | NO |
| `updated_at` | timestamp with time zone | NO |
| `extracted_text` | text | YES |
| `draft_plan` | text | YES |
| `refined_plan` | text | YES |
| `project_goal` | text | YES |
| `project_scope` | text | YES |
| `tech_stack` | jsonb | NO |
| `milestones` | jsonb | NO |
| `key_issues` | jsonb | NO |
| `deliverables` | jsonb | NO |
| `validation_criteria` | jsonb | NO |
| `draft_conversations` | jsonb | NO |
| `draft_choices` | jsonb | NO |
| `draft_prompt_version_id` | uuid | YES |
| `plan_prompt_version_id` | uuid | YES |

참조 관계:

- `FOREIGN KEY (draft_prompt_version_id) REFERENCES prompt_versions(prompt_version_id)`
- `FOREIGN KEY (plan_prompt_version_id) REFERENCES prompt_versions(prompt_version_id)`
- `FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE`

### `public.prompt_versions` · 6행

기본키: PRIMARY KEY (prompt_version_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `prompt_version_id` | uuid | NO |
| `agent_id` | character varying(50) | NO |
| `version_num` | integer | NO |
| `system_prompt` | text | NO |
| `is_active` | boolean | NO |
| `parent_version_id` | uuid | YES |
| `change_reason` | text | NO |
| `created_at` | timestamp with time zone | NO |
| `deactivated_at` | timestamp with time zone | YES |

참조 관계:

- `FOREIGN KEY (parent_version_id) REFERENCES prompt_versions(prompt_version_id)`

검증 조건:

- `CHECK (agent_id::text = ANY (ARRAY['agent_practical'::character varying, 'agent_certified'::character varying, 'agent_fasttrack'::character varying, 'agent_plan_draft'::character varying, 'agent_plan_refine'::character varying]::text[]))`

### `public.roadmap_comments` · 0행

기본키: PRIMARY KEY (comment_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `comment_id` | uuid | NO |
| `roadmap_id` | uuid | NO |
| `author_employee_id` | integer | NO |
| `body` | text | NO |
| `created_at` | timestamp with time zone | NO |
| `updated_at` | timestamp with time zone | NO |
| `modification_completed_at` | timestamp with time zone | YES |

참조 관계:

- `FOREIGN KEY (author_employee_id) REFERENCES employees(employee_id)`
- `FOREIGN KEY (roadmap_id) REFERENCES roadmaps(roadmap_id) ON DELETE CASCADE`

검증 조건:

- `CHECK (length(TRIM(BOTH FROM body)) > 0)`

### `public.roadmap_step_resources` · 1행

기본키: PRIMARY KEY (step_resource_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `step_resource_id` | bigint | NO |
| `step_id` | uuid | NO |
| `course_id` | character varying(255) | YES |
| `isbn` | character varying(20) | YES |
| `certification_id` | integer | YES |

참조 관계:

- `FOREIGN KEY (certification_id) REFERENCES certifications(cert_id)`
- `FOREIGN KEY (course_id) REFERENCES courses(course_id)`
- `FOREIGN KEY (isbn) REFERENCES books(isbn)`
- `FOREIGN KEY (step_id) REFERENCES roadmap_steps(step_id) ON DELETE CASCADE`

검증 조건:

- `CHECK (num_nonnulls(course_id, isbn, certification_id) = 1)`

### `public.roadmap_steps` · 3행

기본키: PRIMARY KEY (step_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `step_id` | uuid | NO |
| `roadmap_id` | uuid | NO |
| `step_order` | integer | NO |
| `title` | text | NO |
| `activity` | text | YES |
| `estimated_duration` | text | YES |
| `target_start_date` | date | YES |
| `target_end_date` | date | YES |
| `estimated_cost` | numeric(14,2) | YES |
| `is_completed` | boolean | NO |
| `completed_at` | timestamp with time zone | YES |
| `details` | jsonb | NO |

참조 관계:

- `FOREIGN KEY (roadmap_id) REFERENCES roadmaps(roadmap_id) ON DELETE CASCADE`

검증 조건:

- `CHECK (target_end_date IS NULL OR target_start_date IS NULL OR target_end_date >= target_start_date)`
- `CHECK (is_completed = (completed_at IS NOT NULL))`
- `CHECK (estimated_cost >= 0::numeric)`
- `CHECK (step_order > 0)`

### `public.roadmaps` · 1행

기본키: PRIMARY KEY (roadmap_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `roadmap_id` | uuid | NO |
| `project_id` | uuid | NO |
| `strategy_type` | character varying(50) | NO |
| `strategy_title` | character varying(255) | YES |
| `summary` | text | YES |
| `content` | jsonb | NO |
| `created_at` | timestamp with time zone | NO |
| `selected_at` | timestamp with time zone | YES |
| `report_content` | jsonb | YES |
| `baseline_content` | jsonb | NO |
| `updated_at` | timestamp with time zone | NO |
| `diagnostic_round_id` | uuid | NO |
| `prompt_version_id` | uuid | YES |

참조 관계:

- `FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE`
- `FOREIGN KEY (diagnostic_round_id, project_id) REFERENCES diagnostic_rounds(diagnostic_round_id, project_id) ON DELETE CASCADE`
- `FOREIGN KEY (prompt_version_id) REFERENCES prompt_versions(prompt_version_id)`

### `public.skill_tags` · 36행

기본키: PRIMARY KEY (skill_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `skill_id` | integer | NO |
| `name` | character varying(50) | NO |
| `category` | character varying(50) | YES |

### `regulations.evaluation_item_definitions` · 70행

기본키: PRIMARY KEY (evaluation_item_definition_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `evaluation_item_definition_id` | character varying(64) | NO |
| `evaluation_result_schema_id` | character varying(64) | NO |
| `parent_item_id` | character varying(64) | YES |
| `skill_id` | integer | YES |
| `item_code` | character varying(255) | NO |
| `item_name` | character varying(255) | NO |
| `value_kind` | character varying(40) | NO |
| `aggregation_role` | character varying(40) | NO |
| `score_min` | numeric(12,3) | YES |
| `score_max` | numeric(12,3) | YES |
| `weight_percent` | numeric(6,3) | YES |
| `unit` | character varying(40) | YES |
| `scale_note` | text | YES |
| `display_order` | integer | NO |
| `definition_note` | text | YES |

참조 관계:

- `FOREIGN KEY (parent_item_id, evaluation_result_schema_id) REFERENCES regulations.evaluation_item_definitions(evaluation_item_definition_id, evaluation_result_schema_id)`
- `FOREIGN KEY (evaluation_result_schema_id) REFERENCES regulations.evaluation_result_schemas(evaluation_result_schema_id)`
- `FOREIGN KEY (skill_id) REFERENCES skill_tags(skill_id)`

### `regulations.evaluation_result_schemas` · 11행

기본키: PRIMARY KEY (evaluation_result_schema_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `evaluation_result_schema_id` | character varying(64) | NO |
| `institution_id` | character varying(64) | NO |
| `schema_name` | character varying(255) | NO |
| `version_label` | character varying(255) | NO |
| `evaluation_kind` | character varying(40) | NO |
| `applicability_condition` | jsonb | NO |
| `applicability_note` | text | YES |
| `effective_from` | date | YES |
| `effective_to` | date | YES |
| `rule_origin` | character varying(40) | NO |
| `source_status` | character varying(40) | NO |
| `review_status` | character varying(40) | NO |
| `calculation_rule` | jsonb | YES |
| `calculation_status` | character varying(40) | NO |
| `source_note` | text | YES |

참조 관계:

- `FOREIGN KEY (institution_id) REFERENCES institutions(institution_id)`

### `regulations.evaluation_schema_sources` · 172행

기본키: PRIMARY KEY (evaluation_schema_source_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `evaluation_schema_source_id` | character varying(64) | NO |
| `evaluation_result_schema_id` | character varying(64) | NO |
| `evaluation_item_definition_id` | character varying(64) | YES |
| `regulation_node_id` | character varying(64) | NO |
| `source_role` | character varying(40) | NO |
| `review_status` | character varying(40) | NO |
| `source_note` | text | YES |

참조 관계:

- `FOREIGN KEY (evaluation_item_definition_id, evaluation_result_schema_id) REFERENCES regulations.evaluation_item_definitions(evaluation_item_definition_id, evaluation_result_schema_id)`
- `FOREIGN KEY (regulation_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id)`
- `FOREIGN KEY (evaluation_result_schema_id) REFERENCES regulations.evaluation_result_schemas(evaluation_result_schema_id)`

### `regulations.rag_chunk_embeddings` · 1410행

기본키: PRIMARY KEY (rag_chunk_id, embedding_model)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `rag_chunk_id` | character varying(64) | NO |
| `embedding_model` | text | NO |
| `dimensions` | integer | NO |
| `input_version` | text | NO |
| `input_sha256` | text | NO |
| `embedding` | vector(1536) | NO |
| `created_at` | timestamp with time zone | NO |
| `updated_at` | timestamp with time zone | NO |

참조 관계:

- `FOREIGN KEY (rag_chunk_id) REFERENCES regulations.rag_chunks(rag_chunk_id) ON DELETE CASCADE`

검증 조건:

- `CHECK (dimensions = 1536)`
- `CHECK (vector_norm(embedding) > 0::double precision)`
- `CHECK (length(input_sha256) = 64)`

### `regulations.rag_chunk_sources` · 1774행

기본키: PRIMARY KEY (rag_chunk_source_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `rag_chunk_source_id` | character varying(64) | NO |
| `rag_chunk_id` | character varying(64) | NO |
| `regulation_node_id` | character varying(64) | NO |
| `source_order` | integer | NO |
| `source_role` | character varying(40) | NO |
| `source_span` | jsonb | YES |

참조 관계:

- `FOREIGN KEY (rag_chunk_id) REFERENCES regulations.rag_chunks(rag_chunk_id)`
- `FOREIGN KEY (regulation_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id)`

### `regulations.rag_chunks` · 1552행

기본키: PRIMARY KEY (rag_chunk_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `rag_chunk_id` | character varying(64) | NO |
| `regulation_version_id` | character varying(64) | NO |
| `chunk_text` | text | NO |
| `chunk_type` | character varying(40) | NO |
| `context_path` | character varying(1024) | NO |
| `content_hash` | character varying(128) | NO |
| `chunking_version` | character varying(255) | NO |
| `index_revision` | character varying(255) | NO |
| `embedding_model` | character varying(255) | YES |
| `search_status` | character varying(40) | NO |
| `created_at` | timestamp with time zone | NO |
| `token_count` | integer | YES |

참조 관계:

- `FOREIGN KEY (regulation_version_id) REFERENCES regulations.regulation_versions(regulation_version_id)`

### `regulations.regulation_files` · 28행

기본키: PRIMARY KEY (regulation_file_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `regulation_file_id` | character varying(64) | NO |
| `regulation_version_id` | character varying(64) | NO |
| `source_file_id` | character varying(64) | YES |
| `file_name` | character varying(255) | NO |
| `file_format` | character varying(40) | NO |
| `file_role` | character varying(40) | NO |
| `storage_key` | character varying(2048) | NO |
| `source_type` | character varying(40) | NO |
| `source_url` | character varying(2048) | YES |
| `retrieved_at` | timestamp with time zone | NO |
| `file_hash` | character varying(128) | NO |
| `is_extraction_source` | boolean | NO |
| `parse_status` | character varying(40) | NO |
| `access_level` | character varying(40) | NO |

참조 관계:

- `FOREIGN KEY (regulation_version_id) REFERENCES regulations.regulation_versions(regulation_version_id)`
- `FOREIGN KEY (source_file_id) REFERENCES regulations.regulation_files(regulation_file_id)`

### `regulations.regulation_nodes` · 3451행

기본키: PRIMARY KEY (regulation_node_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `regulation_node_id` | character varying(64) | NO |
| `regulation_version_id` | character varying(64) | NO |
| `regulation_file_id` | character varying(64) | NO |
| `parent_node_id` | character varying(64) | YES |
| `node_type` | character varying(40) | NO |
| `label` | character varying(255) | NO |
| `title` | character varying(255) | YES |
| `path` | character varying(1024) | NO |
| `display_order` | integer | NO |
| `body_text` | text | NO |
| `source_locator` | jsonb | NO |
| `effective_from_override` | date | YES |
| `effective_to_override` | date | YES |
| `extraction_status` | character varying(40) | NO |
| `review_note` | text | YES |

참조 관계:

- `FOREIGN KEY (parent_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id)`
- `FOREIGN KEY (regulation_file_id) REFERENCES regulations.regulation_files(regulation_file_id)`
- `FOREIGN KEY (regulation_version_id) REFERENCES regulations.regulation_versions(regulation_version_id)`

### `regulations.regulation_references` · 462행

기본키: PRIMARY KEY (regulation_reference_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `regulation_reference_id` | character varying(64) | NO |
| `regulation_node_id` | character varying(64) | NO |
| `reference_type` | character varying(40) | NO |
| `target_text` | text | NO |
| `target_regulation_id` | character varying(64) | YES |
| `target_version_id` | character varying(64) | YES |
| `target_node_id` | character varying(64) | YES |
| `resolution_status` | character varying(40) | NO |
| `review_note` | text | YES |

참조 관계:

- `FOREIGN KEY (regulation_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id)`
- `FOREIGN KEY (target_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id)`
- `FOREIGN KEY (target_regulation_id) REFERENCES regulations.regulations(regulation_id)`
- `FOREIGN KEY (target_version_id) REFERENCES regulations.regulation_versions(regulation_version_id)`

### `regulations.regulation_scopes` · 389행

기본키: PRIMARY KEY (regulation_scope_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `regulation_scope_id` | character varying(64) | NO |
| `regulation_node_id` | character varying(64) | NO |
| `scope_type` | character varying(40) | NO |
| `condition_text` | text | NO |
| `condition_json` | jsonb | YES |
| `applies_to_node_id` | character varying(64) | YES |
| `review_status` | character varying(40) | NO |

참조 관계:

- `FOREIGN KEY (applies_to_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id)`
- `FOREIGN KEY (regulation_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id)`

### `regulations.regulation_versions` · 28행

기본키: PRIMARY KEY (regulation_version_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `regulation_version_id` | character varying(64) | NO |
| `regulation_id` | character varying(64) | NO |
| `version_label` | character varying(255) | NO |
| `title_at_version` | character varying(255) | NO |
| `content_kind` | character varying(40) | NO |
| `coverage_status` | character varying(40) | NO |
| `amendment_date` | date | YES |
| `effective_from` | date | YES |
| `effective_to` | date | YES |
| `date_status` | character varying(40) | NO |
| `review_status` | character varying(40) | NO |
| `availability_status` | character varying(40) | NO |
| `previous_version_id` | character varying(64) | YES |
| `review_note` | text | YES |

참조 관계:

- `FOREIGN KEY (previous_version_id) REFERENCES regulations.regulation_versions(regulation_version_id)`
- `FOREIGN KEY (regulation_id) REFERENCES regulations.regulations(regulation_id)`

### `regulations.regulations` · 28행

기본키: PRIMARY KEY (regulation_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `regulation_id` | character varying(64) | NO |
| `institution_id` | character varying(64) | NO |
| `name` | character varying(255) | NO |
| `category` | character varying(40) | NO |
| `document_kind` | character varying(40) | NO |

참조 관계:

- `FOREIGN KEY (institution_id) REFERENCES institutions(institution_id)`

## 실제 적재·활용 점검

2026-10-26 최신 로컬 DB 직접 조회: 현재 로컬 DB는 실제 테이블 50개·FK 85개다. 호환 뷰는 테이블 수에 포함하지 않는다. 강좌 116·도서 334·자격증 26·직무 6·전공 7·스킬 36건. 자료 벡터 525개·규정 벡터 1410개다. 저장 건수와 추천 가능 건수·수집 완료 여부는 구분한다.

직원 105명은 실제 조회값이다. 부서 14개에는 기존 5개와 시트용 9개(상위 조직 2개 포함)가 있다. 부서 마스터 등록은 기존 직원 소속의 변경이나 시트 직원 정보의 실제 적재를 의미하지 않는다. 2급(을)·3급·4급·5급 ID는 각각 9·7·4·6이다.

016~020 마이그레이션으로 직원 날짜·설문 전 프로젝트 설명·미등재 자격 원문·학력 입학/졸업일을 추가했다. 새 날짜는 nullable DATE이며 미확인 날짜를 추정하지 않는다. 각 날짜 쌍의 종료/배치 날짜가 시작 날짜보다 빠를 수 없다.

시트의 직무·직급·부서 ID는 최신 마스터로 조회한다. 이름은 화면 표시, FK ID는 직원 저장에 사용한다. 직원별 미등재 자격은 공통 자격증 마스터와 분리한다. 날짜는 기본 달력 선택과 YYYY-MM-DD 직접 입력을 유지한다. 별도 날짜입력 탭은 사용자 요청으로 제거했다.

이번 문서는 로컬 public DB 조회 기준이다. 과거 Cloud 100명 원본은 현재 연결에서 찾지 못했으며, 승인된 시드로 로컬 TEST_MANUAL 100명을 재구성했다. 과거 Cloud 원본과 동일 복원이라고 표현하지 않는다. 실제 팀원 시트 적재는 하지 않았다. 로컬의 잘못된 시트 정보 적재는 직전 백업과 동일하게 복구했다. 위의 2026-10-21 백업·복원 수치는 과거 검증 이력이며 현재 DB 전체 백업의 검증 결과로 사용하지 않는다. 변경 이유와 상태는 [최상위 변경점 문서](../시트_DB_변경점.md)를 참고한다.
