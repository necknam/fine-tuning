# 로컬 DB 사용 안내

DB는 Docker 없이 PostgreSQL 17.11 + pgvector 0.8.2를 사용한다. 업무 데이터는 로컬 growpath, 팩토리 실험 기록은 Neon에 저장한다. 전체 현황과 남은 일은 [통합 보고서](CODEX_HANDOFF.md)를 참고한다.

## 실행과 백업

최상위 project 안의 database 폴더에서 실행한다. 로드맵 UI·에이전트·학습 데이터 생성 코드는 이 저장소에서 제거했다. 기존 테이블과 DB 저장 API는 유지한다.

```powershell
python scripts/local_db.py start
python scripts/local_db.py status
python scripts/db.py verify
python -m src.db.resource_vectors status
python -m src.db.regulation_vectors status
```

중지는 `python scripts/local_db.py stop`, 백업은 `python scripts/local_db.py backup --output 원하는경로.dump`다. 물리 파일은 `data/local_db/postgres` 전체이며 개별 파일을 삭제하거나 편집하지 않는다. 연결은 `.env.local`, 실행 파일은 그 안의 `POSTGRES_BIN_DIR` 설정을 사용한다.

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

현재 구조는 [ERD 최종](ERD_최종.html)을 참고한다. 실제 테이블은 운영 42개·관리 2개·보관 6개로 전체 50개다. 빈 과거 테이블 ai_cases·regulations·employee_skill_gaps는 008 마이그레이션에서 제거했다. 원본 자료의 중복 embedding 컬럼은 제거했으며, 검색 벡터는 public.learning_resource_embeddings와 regulations.rag_chunk_embeddings에서 관리한다. 기존 명령 호환용 뷰는 테이블 수에 포함하지 않는다.

미확정 직원 14명의 기관·부서·직급·직무는 추정해서 채우지 않았다. 직원 조회는 정식 기관·부서·직급·직무 참조를 우선 사용한다. `update_employee_assignment`로 소속을 확정하면 중복 department·grade·job_title 문자열을 비운다. 미확정 값이 남아 있어 컬럼 자체는 아직 제거하지 않는다.

로드맵 수정은 `update_roadmap_content`가 content와 단계·자료 연결을 같은 트랜잭션에서 갱신한다. 변경 없는 활동은 완료 상태를 유지하고, 제목·활동·기간이 바뀐 단계는 완료 상태를 해제한다. 최초 baseline_content는 변경하지 않는다. 진행 체크만 바꾸는 경우 코멘트에 수정 완료 표시를 하지 않는다. DB를 직접 수정하는 SQL은 이 API의 동기화를 거치지 않으므로 앱 수정 경로에서는 사용하지 않는다.

부서장은 담당 부서·하위 부서 프로젝트를 조회하고 본인 코멘트를 작성·수정·삭제할 수 있으며, 일반 직원의 로드맵이나 완료 체크를 수정할 수 없다. 직원 계정 정보를 조회하는 API는 password_hash를 반환하지 않는다.

신규 설치는 `python scripts/db.py migrate`, 구조 검증은 `python scripts/db.py verify`를 사용한다. 벡터 테이블·수집 이력 테이블도 설치 단계에 포함된다. 실제 DB 기준 메타데이터는 src/database/catalog.current.json, 이전 패키지를 읽기 위한 메타데이터는 catalog.json이다. 이전 001~008 마이그레이션 파일은 적용 후 수정하지 않는다.

스킬 36·강좌 718·도서 345·자격증 66·직무 80·전공 132건의 학습 자료 벡터 1,377개가 모두 최신이다. 규정 청크 벡터 1,410개는 별도 테이블에 유지한다. 두 벡터 테이블은 같은 검색 대상으로 무조건 혼합하지 않는다.

복구 백업과 data/local_db/postgres는 정리 대상이 아니다. ERD는 `python -m src.database.erd --template ../docs/ERD_최종.html`로 현재 DB 기준 재생성할 수 있다.

강좌·도서·자격증의 공식 이미지 URL은 각 자료 테이블의 image_url에 저장한다. 강좌 671개, 도서 345개, 자격증 59개에 URL이 있다. 이미지 없는 도서는 `python load_data.py --refresh-book-images`로 ISBN을 조회한다. URL 없는 자료는 NULL을 유지하며 이미지 확인만으로 추천 품질 등급을 올리지 않는다.

계획 초안·확정은 projects.draft_prompt_version_id·plan_prompt_version_id, 선택 로드맵은 roadmaps.prompt_version_id로 실제 사용한 prompt_versions를 참조한다. 과거 결과·코드 폴백은 NULL을 유지하며 현재 활성 버전을 과거 결과에 소급하지 않는다.


## 전체 백업과 재현

- 전체 백업: `database/data/exports/growpath_full_20261021.dump` (45,390,365바이트).
- 무결성·건수·제약조건: 옆의 `.manifest.json`. 같은 DB 스냅샷에서 조회한 메타데이터와 SHA-256을 기록한다.
- 별도 DB `growpath_restore_verify_20261021`에 복원 검증 완료: 50개 테이블, 29,903행, 202개 제약조건, 자료·규정 벡터 연산 통과.
- 설치·복원: 최상위 [DB_복원.md](../DB_복원.md). 로컬 관리자 비밀번호와 역할은 복원 대상에 포함하지 않고 새 PC에서 설정한다.
- 데이터 파일·시퀀스·함수·뷰·임베딩은 전체 덤프에 포함한다. 외부 PDF는 `database/data/regulations`에 따로 보존한다. 외부 저장소의 파일까지 DB 덤프가 복사하지는 않는다.
- Windows x64 PostgreSQL 17용 pgvector 0.8.2 파일은 exports의 `pgvector_pg17_windows_x64`에 라이선스·해시와 함께 둔다. 다른 OS/메이저 버전에는 그대로 설치하지 않는다.

## 각 테이블의 현재 구조

2026-10-21 실제 DB 조회 기준. 호환 뷰는 아래 테이블 목록에 포함하지 않는다.

### `growpath_legacy.agent_generations` · 71행

기본키: PRIMARY KEY (generation_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `generation_id` | uuid | NO |
| `request_id` | uuid | NO |
| `agent_id` | character varying | NO |
| `prompt_version_id` | uuid | YES |
| `provider` | character varying | NO |
| `model` | character varying | NO |
| `roadmap_content` | jsonb | NO |
| `summary` | text | NO |
| `latency_ms` | integer | NO |
| `status` | character varying | NO |
| `created_at` | timestamp with time zone | NO |

참조 관계:

- `FOREIGN KEY (prompt_version_id) REFERENCES prompt_versions(prompt_version_id)`
- `FOREIGN KEY (request_id) REFERENCES growpath_legacy.roadmap_requests(request_id) ON DELETE CASCADE`

### `growpath_legacy.agent_selections` · 20행

기본키: PRIMARY KEY (selection_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `selection_id` | uuid | NO |
| `request_id` | uuid | NO |
| `chosen_generation_id` | uuid | NO |
| `chosen_agent_id` | character varying | NO |
| `selection_reason` | text | YES |
| `user_type` | character varying | NO |
| `created_at` | timestamp with time zone | NO |

참조 관계:

- `FOREIGN KEY (chosen_generation_id) REFERENCES growpath_legacy.agent_generations(generation_id) ON DELETE CASCADE`
- `FOREIGN KEY (request_id) REFERENCES growpath_legacy.roadmap_requests(request_id) ON DELETE CASCADE`

### `growpath_legacy.finetuning_datasets` · 2행

기본키: PRIMARY KEY (dataset_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `dataset_id` | uuid | NO |
| `dataset_type` | character varying | NO |
| `record_count` | integer | NO |
| `export_path` | text | NO |
| `pii_masked` | boolean | NO |
| `filter_criteria` | jsonb | NO |
| `created_at` | timestamp with time zone | NO |

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
| `user_type` | character varying | NO |
| `created_at` | timestamp with time zone | NO |

참조 관계:

- `FOREIGN KEY (chosen_generation_id) REFERENCES growpath_legacy.agent_generations(generation_id) ON DELETE CASCADE`
- `FOREIGN KEY (rejected_generation_id) REFERENCES growpath_legacy.agent_generations(generation_id) ON DELETE CASCADE`
- `FOREIGN KEY (request_id) REFERENCES growpath_legacy.roadmap_requests(request_id) ON DELETE CASCADE`

### `growpath_legacy.roadmap_requests` · 25행

기본키: PRIMARY KEY (request_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `request_id` | uuid | NO |
| `user_type` | character varying | NO |
| `employee_id` | character varying | YES |
| `raw_user_prompt` | text | NO |
| `conversation_history` | jsonb | NO |
| `user_requirements` | jsonb | NO |
| `retrieved_context` | jsonb | NO |
| `created_at` | timestamp with time zone | NO |

### `growpath_legacy.test_mock_profiles` · 39행

기본키: PRIMARY KEY (profile_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `profile_id` | uuid | NO |
| `source_type` | character varying | NO |
| `profile_name` | character varying | NO |
| `department` | character varying | NO |
| `grade` | character varying | NO |
| `job_title` | character varying | NO |
| `career_years` | integer | NO |
| `current_skills` | jsonb | NO |
| `target_skills` | jsonb | NO |
| `work_context_summary` | text | NO |
| `created_at` | timestamp with time zone | NO |

### `growpath_meta.catalog_api_sources` · 1219행

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

### `growpath_meta.schema_migrations` · 12행

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
| `assessment_type` | character varying | NO |
| `skill_id` | integer | YES |
| `skill` | character varying | NO |
| `question` | text | NO |
| `options` | jsonb | YES |
| `sequence_no` | integer | NO |
| `created_at` | timestamp with time zone | NO |
| `diagnostic_round_id` | uuid | NO |

참조 관계:

- `FOREIGN KEY (diagnostic_round_id, project_id) REFERENCES diagnostic_rounds(diagnostic_round_id, project_id) ON DELETE CASCADE`
- `FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE`
- `FOREIGN KEY (skill_id) REFERENCES skill_tags(skill_id)`

### `public.assessment_responses` · 25행

기본키: PRIMARY KEY (response_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `response_id` | uuid | NO |
| `project_id` | uuid | NO |
| `question_id` | uuid | NO |
| `assessment_type` | character varying | NO |
| `selected_option` | text | NO |
| `score` | integer | NO |
| `answered_at` | timestamp with time zone | NO |

참조 관계:

- `FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE`
- `FOREIGN KEY (question_id, project_id, assessment_type) REFERENCES assessment_questions(question_id, project_id, assessment_type) ON DELETE CASCADE`

### `public.book_skills` · 643행

기본키: PRIMARY KEY (isbn, skill_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `isbn` | character varying | NO |
| `skill_id` | integer | NO |

참조 관계:

- `FOREIGN KEY (isbn) REFERENCES books(isbn) ON DELETE CASCADE`
- `FOREIGN KEY (skill_id) REFERENCES skill_tags(skill_id) ON DELETE CASCADE`

### `public.books` · 345행

기본키: PRIMARY KEY (isbn)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `isbn` | character varying | NO |
| `title` | character varying | NO |
| `author` | character varying | YES |
| `publisher` | character varying | YES |
| `loan_count` | integer | YES |
| `kdc_code` | character varying | YES |
| `last_batch_updated` | timestamp with time zone | YES |
| `record_source` | character varying | NO |
| `source_url` | text | YES |
| `content_status` | text | YES |
| `source_verified_at` | timestamp with time zone | YES |
| `description` | text | YES |
| `image_url` | text | YES |

### `public.certification_skills` · 115행

기본키: PRIMARY KEY (cert_id, skill_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `cert_id` | integer | NO |
| `skill_id` | integer | NO |

참조 관계:

- `FOREIGN KEY (cert_id) REFERENCES certifications(cert_id) ON DELETE CASCADE`
- `FOREIGN KEY (skill_id) REFERENCES skill_tags(skill_id) ON DELETE CASCADE`

### `public.certifications` · 66행

기본키: PRIMARY KEY (cert_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `cert_id` | integer | NO |
| `title` | character varying | NO |
| `provider` | character varying | YES |
| `test_subjects` | text | YES |
| `career_outlook` | text | YES |
| `exam_type` | character varying | YES |
| `pass_score` | integer | YES |
| `last_batch_updated` | timestamp with time zone | YES |
| `record_source` | character varying | NO |
| `source_url` | text | YES |
| `content_status` | text | YES |
| `source_verified_at` | timestamp with time zone | YES |
| `description` | text | YES |
| `image_url` | text | YES |

### `public.course_skills` · 997행

기본키: PRIMARY KEY (course_id, skill_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `course_id` | character varying | NO |
| `skill_id` | integer | NO |

참조 관계:

- `FOREIGN KEY (course_id) REFERENCES courses(course_id) ON DELETE CASCADE`
- `FOREIGN KEY (skill_id) REFERENCES skill_tags(skill_id) ON DELETE CASCADE`

### `public.courses` · 718행

기본키: PRIMARY KEY (course_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `course_id` | character varying | NO |
| `title` | character varying | NO |
| `category_name` | character varying | YES |
| `org_name` | character varying | YES |
| `url` | character varying | YES |
| `is_matchup` | boolean | YES |
| `cost` | numeric | YES |
| `duration_weeks` | integer | YES |
| `recruitment_status` | character varying | YES |
| `syllabus_summary` | text | YES |
| `last_batch_updated` | timestamp with time zone | YES |
| `platform` | character varying | NO |
| `difficulty` | character varying | YES |
| `record_source` | character varying | NO |
| `source_url` | text | YES |
| `content_status` | text | YES |
| `source_verified_at` | timestamp with time zone | YES |
| `image_url` | text | YES |

### `public.departments` · 5행

기본키: PRIMARY KEY (department_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `department_id` | bigint | NO |
| `institution_id` | character varying | NO |
| `department_code` | text | NO |
| `name` | text | NO |
| `parent_department_id` | bigint | YES |

참조 관계:

- `FOREIGN KEY (institution_id) REFERENCES institutions(institution_id)`
- `FOREIGN KEY (parent_department_id, institution_id) REFERENCES departments(department_id, institution_id)`

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

### `public.employee_certifications` · 0행

기본키: PRIMARY KEY (employee_id, certification_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `employee_id` | integer | NO |
| `certification_id` | integer | NO |

참조 관계:

- `FOREIGN KEY (certification_id) REFERENCES certifications(cert_id)`
- `FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE`

### `public.employee_education_records` · 0행

기본키: PRIMARY KEY (education_record_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `education_record_id` | uuid | NO |
| `employee_id` | integer | NO |
| `school_name` | text | NO |
| `education_level` | text | NO |
| `department_name` | text | YES |
| `major_id` | integer | YES |

참조 관계:

- `FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE`
- `FOREIGN KEY (major_id) REFERENCES majors(major_id)`

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

### `public.employee_skills` · 0행

기본키: PRIMARY KEY (employee_id, skill_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `employee_id` | integer | NO |
| `skill_id` | integer | NO |

참조 관계:

- `FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE`
- `FOREIGN KEY (skill_id) REFERENCES skill_tags(skill_id)`

### `public.employees` · 14행

기본키: PRIMARY KEY (employee_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `employee_id` | integer | NO |
| `name` | character varying | NO |
| `job_id` | integer | YES |
| `created_at` | timestamp with time zone | YES |
| `is_degree_seeker` | boolean | YES |
| `email` | character varying | YES |
| `department` | character varying | YES |
| `job_title` | character varying | YES |
| `grade` | character varying | YES |
| `source_type` | character varying | YES |
| `updated_at` | timestamp with time zone | YES |
| `institution_id` | character varying | YES |
| `employee_number` | text | YES |
| `password_hash` | text | YES |
| `department_id` | bigint | YES |
| `job_grade_id` | bigint | YES |
| `is_department_head` | boolean | NO |

참조 관계:

- `FOREIGN KEY (department_id, institution_id) REFERENCES departments(department_id, institution_id)`
- `FOREIGN KEY (job_grade_id, institution_id) REFERENCES job_grades(job_grade_id, institution_id)`
- `FOREIGN KEY (institution_id) REFERENCES institutions(institution_id)`
- `FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE SET NULL`

### `public.growth_reports` · 1행

기본키: PRIMARY KEY (report_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `report_id` | uuid | NO |
| `project_id` | uuid | NO |
| `report_type` | character varying | NO |
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
| `institution_id` | character varying | NO |
| `name` | character varying | NO |
| `external_code` | character varying | YES |
| `institution_code` | text | YES |

### `public.job_grades` · 5행

기본키: PRIMARY KEY (job_grade_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `job_grade_id` | bigint | NO |
| `institution_id` | character varying | NO |
| `name` | text | NO |
| `sort_order` | integer | NO |

참조 관계:

- `FOREIGN KEY (institution_id) REFERENCES institutions(institution_id)`

### `public.job_skills` · 31행

기본키: PRIMARY KEY (job_id, skill_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `job_id` | integer | NO |
| `skill_id` | integer | NO |

참조 관계:

- `FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE`
- `FOREIGN KEY (skill_id) REFERENCES skill_tags(skill_id) ON DELETE CASCADE`

### `public.jobs` · 80행

기본키: PRIMARY KEY (job_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `job_id` | integer | NO |
| `title` | character varying | NO |
| `ncs_units` | text | YES |
| `last_batch_updated` | timestamp with time zone | YES |
| `record_source` | character varying | NO |
| `source_url` | text | YES |
| `content_status` | text | YES |
| `source_verified_at` | timestamp with time zone | YES |
| `description` | text | YES |

### `public.learning_resource_embeddings` · 1377행

기본키: PRIMARY KEY (resource_type, resource_id, embedding_model)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `resource_type` | text | NO |
| `resource_id` | text | NO |
| `embedding_model` | text | NO |
| `dimensions` | integer | NO |
| `input_version` | text | NO |
| `input_sha256` | text | NO |
| `embedding` | vector | NO |
| `updated_at` | timestamp with time zone | NO |
| `skill_id` | integer | YES |
| `course_id` | character varying | YES |
| `isbn` | character varying | YES |
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

### `public.major_skills` · 202행

기본키: PRIMARY KEY (major_id, skill_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `major_id` | integer | NO |
| `skill_id` | integer | NO |

참조 관계:

- `FOREIGN KEY (major_id) REFERENCES majors(major_id) ON DELETE CASCADE`
- `FOREIGN KEY (skill_id) REFERENCES skill_tags(skill_id) ON DELETE CASCADE`

### `public.majors` · 132행

기본키: PRIMARY KEY (major_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `major_id` | integer | NO |
| `title` | character varying | NO |
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
| `project_name` | character varying | NO |
| `status` | character varying | NO |
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
| `agent_id` | character varying | NO |
| `version_num` | integer | NO |
| `system_prompt` | text | NO |
| `is_active` | boolean | NO |
| `parent_version_id` | uuid | YES |
| `change_reason` | text | NO |
| `created_at` | timestamp with time zone | NO |
| `deactivated_at` | timestamp with time zone | YES |

참조 관계:

- `FOREIGN KEY (parent_version_id) REFERENCES prompt_versions(prompt_version_id)`

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

### `public.roadmap_step_resources` · 9행

기본키: PRIMARY KEY (step_resource_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `step_resource_id` | bigint | NO |
| `step_id` | uuid | NO |
| `course_id` | character varying | YES |
| `isbn` | character varying | YES |
| `certification_id` | integer | YES |

참조 관계:

- `FOREIGN KEY (certification_id) REFERENCES certifications(cert_id)`
- `FOREIGN KEY (course_id) REFERENCES courses(course_id)`
- `FOREIGN KEY (isbn) REFERENCES books(isbn)`
- `FOREIGN KEY (step_id) REFERENCES roadmap_steps(step_id) ON DELETE CASCADE`

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
| `estimated_cost` | numeric | YES |
| `is_completed` | boolean | NO |
| `completed_at` | timestamp with time zone | YES |
| `details` | jsonb | NO |

참조 관계:

- `FOREIGN KEY (roadmap_id) REFERENCES roadmaps(roadmap_id) ON DELETE CASCADE`

### `public.roadmaps` · 1행

기본키: PRIMARY KEY (roadmap_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `roadmap_id` | uuid | NO |
| `project_id` | uuid | NO |
| `strategy_type` | character varying | NO |
| `strategy_title` | character varying | YES |
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
| `name` | character varying | NO |
| `category` | character varying | YES |

### `regulations.evaluation_item_definitions` · 70행

기본키: PRIMARY KEY (evaluation_item_definition_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `evaluation_item_definition_id` | character varying | NO |
| `evaluation_result_schema_id` | character varying | NO |
| `parent_item_id` | character varying | YES |
| `skill_id` | integer | YES |
| `item_code` | character varying | NO |
| `item_name` | character varying | NO |
| `value_kind` | character varying | NO |
| `aggregation_role` | character varying | NO |
| `score_min` | numeric | YES |
| `score_max` | numeric | YES |
| `weight_percent` | numeric | YES |
| `unit` | character varying | YES |
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
| `evaluation_result_schema_id` | character varying | NO |
| `institution_id` | character varying | NO |
| `schema_name` | character varying | NO |
| `version_label` | character varying | NO |
| `evaluation_kind` | character varying | NO |
| `applicability_condition` | jsonb | NO |
| `applicability_note` | text | YES |
| `effective_from` | date | YES |
| `effective_to` | date | YES |
| `rule_origin` | character varying | NO |
| `source_status` | character varying | NO |
| `review_status` | character varying | NO |
| `calculation_rule` | jsonb | YES |
| `calculation_status` | character varying | NO |
| `source_note` | text | YES |

참조 관계:

- `FOREIGN KEY (institution_id) REFERENCES institutions(institution_id)`

### `regulations.evaluation_schema_sources` · 172행

기본키: PRIMARY KEY (evaluation_schema_source_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `evaluation_schema_source_id` | character varying | NO |
| `evaluation_result_schema_id` | character varying | NO |
| `evaluation_item_definition_id` | character varying | YES |
| `regulation_node_id` | character varying | NO |
| `source_role` | character varying | NO |
| `review_status` | character varying | NO |
| `source_note` | text | YES |

참조 관계:

- `FOREIGN KEY (evaluation_item_definition_id, evaluation_result_schema_id) REFERENCES regulations.evaluation_item_definitions(evaluation_item_definition_id, evaluation_result_schema_id)`
- `FOREIGN KEY (regulation_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id)`
- `FOREIGN KEY (evaluation_result_schema_id) REFERENCES regulations.evaluation_result_schemas(evaluation_result_schema_id)`

### `regulations.rag_chunk_embeddings` · 1410행

기본키: PRIMARY KEY (rag_chunk_id, embedding_model)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `rag_chunk_id` | character varying | NO |
| `embedding_model` | text | NO |
| `dimensions` | integer | NO |
| `input_version` | text | NO |
| `input_sha256` | text | NO |
| `embedding` | vector | NO |
| `created_at` | timestamp with time zone | NO |
| `updated_at` | timestamp with time zone | NO |

참조 관계:

- `FOREIGN KEY (rag_chunk_id) REFERENCES regulations.rag_chunks(rag_chunk_id) ON DELETE CASCADE`

### `regulations.rag_chunk_sources` · 1774행

기본키: PRIMARY KEY (rag_chunk_source_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `rag_chunk_source_id` | character varying | NO |
| `rag_chunk_id` | character varying | NO |
| `regulation_node_id` | character varying | NO |
| `source_order` | integer | NO |
| `source_role` | character varying | NO |
| `source_span` | jsonb | YES |

참조 관계:

- `FOREIGN KEY (rag_chunk_id) REFERENCES regulations.rag_chunks(rag_chunk_id)`
- `FOREIGN KEY (regulation_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id)`

### `regulations.rag_chunks` · 1552행

기본키: PRIMARY KEY (rag_chunk_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `rag_chunk_id` | character varying | NO |
| `regulation_version_id` | character varying | NO |
| `chunk_text` | text | NO |
| `chunk_type` | character varying | NO |
| `context_path` | character varying | NO |
| `content_hash` | character varying | NO |
| `chunking_version` | character varying | NO |
| `index_revision` | character varying | NO |
| `embedding_model` | character varying | YES |
| `search_status` | character varying | NO |
| `created_at` | timestamp with time zone | NO |
| `token_count` | integer | YES |

참조 관계:

- `FOREIGN KEY (regulation_version_id) REFERENCES regulations.regulation_versions(regulation_version_id)`

### `regulations.regulation_files` · 28행

기본키: PRIMARY KEY (regulation_file_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `regulation_file_id` | character varying | NO |
| `regulation_version_id` | character varying | NO |
| `source_file_id` | character varying | YES |
| `file_name` | character varying | NO |
| `file_format` | character varying | NO |
| `file_role` | character varying | NO |
| `storage_key` | character varying | NO |
| `source_type` | character varying | NO |
| `source_url` | character varying | YES |
| `retrieved_at` | timestamp with time zone | NO |
| `file_hash` | character varying | NO |
| `is_extraction_source` | boolean | NO |
| `parse_status` | character varying | NO |
| `access_level` | character varying | NO |

참조 관계:

- `FOREIGN KEY (regulation_version_id) REFERENCES regulations.regulation_versions(regulation_version_id)`
- `FOREIGN KEY (source_file_id) REFERENCES regulations.regulation_files(regulation_file_id)`

### `regulations.regulation_nodes` · 3451행

기본키: PRIMARY KEY (regulation_node_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `regulation_node_id` | character varying | NO |
| `regulation_version_id` | character varying | NO |
| `regulation_file_id` | character varying | NO |
| `parent_node_id` | character varying | YES |
| `node_type` | character varying | NO |
| `label` | character varying | NO |
| `title` | character varying | YES |
| `path` | character varying | NO |
| `display_order` | integer | NO |
| `body_text` | text | NO |
| `source_locator` | jsonb | NO |
| `effective_from_override` | date | YES |
| `effective_to_override` | date | YES |
| `extraction_status` | character varying | NO |
| `review_note` | text | YES |

참조 관계:

- `FOREIGN KEY (parent_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id)`
- `FOREIGN KEY (regulation_file_id) REFERENCES regulations.regulation_files(regulation_file_id)`
- `FOREIGN KEY (regulation_version_id) REFERENCES regulations.regulation_versions(regulation_version_id)`

### `regulations.regulation_references` · 462행

기본키: PRIMARY KEY (regulation_reference_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `regulation_reference_id` | character varying | NO |
| `regulation_node_id` | character varying | NO |
| `reference_type` | character varying | NO |
| `target_text` | text | NO |
| `target_regulation_id` | character varying | YES |
| `target_version_id` | character varying | YES |
| `target_node_id` | character varying | YES |
| `resolution_status` | character varying | NO |
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
| `regulation_scope_id` | character varying | NO |
| `regulation_node_id` | character varying | NO |
| `scope_type` | character varying | NO |
| `condition_text` | text | NO |
| `condition_json` | jsonb | YES |
| `applies_to_node_id` | character varying | YES |
| `review_status` | character varying | NO |

참조 관계:

- `FOREIGN KEY (applies_to_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id)`
- `FOREIGN KEY (regulation_node_id) REFERENCES regulations.regulation_nodes(regulation_node_id)`

### `regulations.regulation_versions` · 28행

기본키: PRIMARY KEY (regulation_version_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `regulation_version_id` | character varying | NO |
| `regulation_id` | character varying | NO |
| `version_label` | character varying | NO |
| `title_at_version` | character varying | NO |
| `content_kind` | character varying | NO |
| `coverage_status` | character varying | NO |
| `amendment_date` | date | YES |
| `effective_from` | date | YES |
| `effective_to` | date | YES |
| `date_status` | character varying | NO |
| `review_status` | character varying | NO |
| `availability_status` | character varying | NO |
| `previous_version_id` | character varying | YES |
| `review_note` | text | YES |

참조 관계:

- `FOREIGN KEY (previous_version_id) REFERENCES regulations.regulation_versions(regulation_version_id)`
- `FOREIGN KEY (regulation_id) REFERENCES regulations.regulations(regulation_id)`

### `regulations.regulations` · 28행

기본키: PRIMARY KEY (regulation_id)

| 컬럼 | 자료형 | NULL 허용 |
| --- | --- | --- |
| `regulation_id` | character varying | NO |
| `institution_id` | character varying | NO |
| `name` | character varying | NO |
| `category` | character varying | NO |
| `document_kind` | character varying | NO |

참조 관계:

- `FOREIGN KEY (institution_id) REFERENCES institutions(institution_id)`


## 실제 적재·활용 점검

2026-10-21 최종 DB 점검: 강좌 1,149(추천 1,052), 도서 3,327(서지 필수정보 기준 추천 3,327), 자격증 68(추천 44), 직무 80(추천 13), 전공 132(추천 29). 도서 소장 조건은 제거했고 새 수집은 IT 스킬 매칭을 유지한다. IT 전문성의 전수 내용 검수는 미완료다. 자격증은 공식 정보·시험과목으로 판단하며 종료·종료 예정·상태 미확인은 제외한다. 이미지 URL은 강좌 1,102·도서 3,276·자격증 61건이며 나머지는 NULL이다. 규정 28개 버전은 사용자 지시로 approved/available, 검색 대상 1,406청크는 active로 변경하고 운영자 승인 이력을 남겼다. 제외·대체 상태는 유지했다. 직원14명은 요청한 테스트 비밀번호를 Argon2id 해시로 저장·검증했다. 전체 백업은 45,390,365바이트, 별도 복원 검증은 50테이블·29,903행·202제약조건·벡터연산 통과다.

직원 job_id14건과 기관·부서·직급·사번5건은 미등록이다. 원문에서 제공하지 않는 선택값은 임의 생성하지 않는다.
