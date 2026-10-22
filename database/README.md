# 다른 PC로 전달받은 경우

이 ZIP은 `database/` 전체 복사본이며 실제 `.env`·데이터·백업을 포함합니다. 지정된 수신자에게만 직접 전달하세요. 새 PC의 준비와 최신 DB 복원은 [새 PC 실행 안내](RESTORE_OTHER_PC.md)를 먼저 따릅니다. `data/exports/growpath_enrollment_20261022.dump`와 같은 이름의 manifest가 최신 전달 DB입니다. 기존 날짜 백업은 과거 상태입니다.

# PostgreSQL 관리와 AI·IT 학습자료 자동 적재

한국어·국내 대상 AI·IT 역량 학습자료를 수집하고 GPT-6 Luna가 승인한 자료만 적재합니다. 기존 테이블·외래키·스킬 ID는 유지하며, 승인된 신청 기간 컬럼 3개·상태 조회 뷰와 향후 자료별 요약용 nullable ai_mention 컬럼만 추가합니다.

## 처음 한 번 설정

Python 3.12 환경에서 이 README가 있는 `database` 폴더를 엽니다.

```powershell
python -m pip install -r requirements.txt
python scripts/local_db.py start
python scripts/db.py verify
```

기존 DB가 복원되어 있어야 합니다. 새 PC는 [전체 복원 안내](../DB_복원.md)를 먼저 따릅니다. 자료 적재 명령으로 테이블이나 컬럼을 자동 생성·확장하지 않습니다.

`.env.sample`을 참고해 `.env`에 `OPENAI_API_KEY`, K-MOOC·도서관 정보나루·CareerNet 등 수집 API 키와 DB 접속 정보를 설정합니다. `.env.local`이 `.env`보다 우선합니다. 실제 키는 저장소에 올리지 않습니다. **분류 모델은 코드의 `gpt-6-luna`로 고정**하며 일반 `OPENAI_MODEL` 설정과 무관합니다. 해당 모델의 API 사용 권한이 필요합니다. 임베딩은 기존 `text-embedding-3-small`을 사용합니다.

## 한 번에 실행

```powershell
python load_data.py
```

Windows에서는 Python 환경을 준비한 뒤 **`run_catalog.cmd`를 더블클릭**해도 됩니다. `database/.venv/Scripts/python.exe`가 있으면 해당 환경을, 없으면 PATH의 `python`을 사용합니다.

실행 순서는 다음과 같습니다.

1. 기존 DB·API 키 설정을 확인합니다. **기본 실행은 초기화하지 않고 기존 자료를 유지하며 갱신합니다.**
2. 공식 API에서 AI·IT 자료를 다시 수집하고 출처·한국어·분야·상세 내용·이용 가능성을 검사합니다. 유효한 원본 API 캐시는 재사용합니다.
3. GPT-6 Luna가 AI·IT 학습 적합성과 스킬 연결을 승인/제외합니다. AI 모델 개발·학습·평가 외에도 성인 대상 생성형 AI 활용·프롬프트 작성·AI 에이전트·업무 자동화 실습을 포함합니다. 키워드만 등장하는 교양·전망·아동·문학은 제외합니다.
4. 승인 자료를 기존 ID/출처 기준으로 추가·갱신하고 API 설명·시험 과목·교육과정 원문을 저장합니다. 임의 자료나 AI 생성 설명은 넣지 않습니다.
5. 부적합 자료·연결을 자동 정리하고 임베딩을 갱신합니다. 출처·설명·상태·스킬 연결·벡터 검사가 통과한 경우에만 적재를 확정합니다. 실패하면 해당 갱신을 롤백합니다.

도서는 KDC 004·005를 기본으로 하고, 구체적인 AI 실습 내용과 AI 심사를 통과한 업무 활용서는 325(경영) 분류도 허용합니다. 경영 분류나 AI라는 단어만으로 승인하지 않습니다. 새 스킬 ID나 테이블·컬럼은 추가하지 않습니다.

API 설명은 도서·자격증·직무·전공의 `description`, 강좌의 `syllabus_summary`에 저장합니다. 별도 소개가 없으면 API 시험 과목·교육과정 원문을 그대로 재사용합니다. 내용은 추천용 임베딩에도 반영됩니다.

AI 판정 이유·원문 응답·심사 이력·판정 캐시는 DB나 파일에 저장하지 않습니다. 실행 중 승인·제외 건수만 표시하며 같은 실행 내 중복 호출만 메모리에서 방지합니다. 재실행하면 다시 심사합니다. AI 응답 오류/거절/잘림·접근 권한 오류를 승인으로 처리하거나 다른 모델로 대체하지 않습니다.

초기화가 필요한 경우에만 `--reset-catalog`를 명시합니다. 이 옵션은 스킬 관련 자료와 해당 자료 연결만 먼저 초기화하며, 직원·프로젝트·진단·로드맵 본문·규정과 스킬 ID는 유지합니다. 기본 실행에서는 이 과정을 수행하지 않습니다.

자료의 제목·소개·교육과정·시험 과목·후보 스킬을 OpenAI API에 보내므로 AI 심사와 임베딩 비용이 발생합니다. 직원·프로젝트·규정 데이터는 분류 요청에 포함하지 않습니다. 원본 API의 호출 한도나 자료 부재로 수집이 덜 끝나면 결과가 `INCOMPLETE` 또는 `PARTIAL`일 수 있습니다.

## 다른 실행 옵션

```powershell
# 미리보기: 수집 + 유료 AI 심사. 초기화·DB 저장·임베딩은 실행하지 않음
python load_data.py --dry-run

# 기본 동작과 같은 초기화 없는 갱신 (기존 호환 옵션)
python load_data.py --incremental

# 명시적으로 스킬 관련 자료를 먼저 초기화해야 할 때만 사용
python load_data.py --reset-catalog

# 임베딩만 나중에 실행 (AI 심사는 그대로 필수)
python load_data.py --skip-embeddings
python -m src.database.vectors.resource_vectors embed

# API 연결 진단: 적재·AI·임베딩 호출 없이 확인
python diagnose_catalog.py --output data/transfer/api_diagnosis.json
```

`--skip-embeddings`는 AI 심사를 생략하는 옵션이 아닙니다. `--allow-partial`은 일부 수집 분류 실패를 허용하는 기존 옵션이며 AI 심사 실패를 우회하지 못합니다. `--max-pages`는 API 페이지 수를 제한합니다. `--report`를 명시한 경우에만 기존 형식의 실행 요약을 저장하며 AI 개별 판정은 저장하지 않습니다.

완료 시 마지막 결과의 `status`, `database_changes`, 벡터의 `missing_or_stale_vectors`를 확인합니다. 수집 도중의 건수는 저장 완료를 의미하지 않습니다. 초기화 전 백업은 자료 복구용이며 AI 심사 이력이 아닙니다.

## 범위와 점검

[IT 분야 제한](IT_SCOPE.md) · [DB 구조와 접속](../docs/DATABASE.md) · [ERD](../docs/ERD_최종.html)

```powershell
python -m unittest tests.test_ai_it_scope tests.test_ai_catalog_filter tests.test_catalog_scope tests.test_catalog_expansion tests.test_regulation_vectors -v
```

테스트는 AI/수집 응답을 모의 처리하며 유료 API나 실행 DB에 연결하지 않습니다. 모델의 실제 의미 판정 정확도를 보장하는 검사는 아닙니다.

AI 응답 형식은 [OpenAI 공식 Structured Outputs 안내](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat)를 따릅니다. 로드맵 UI·에이전트·학습 데이터 생성기는 이 폴더에 포함하지 않습니다.


## 이번 전달본 상태 (2026-10-22)

AI·IT 범위로 초기화 없이 갱신했습니다. 도서 334·강좌 116·자격증 26·직무 6·전공 7건, 총 489건이 설명·출처·스킬 연결·벡터 검사를 통과했습니다. 최신 백업은 `data/exports/growpath_enrollment_20261022.dump`입니다. 이전 이름의 백업은 과거 DB입니다.

도서 신규 검색 일부는 API의 `LIBRARY_IP_REGISTRATION_REQUIRED` 응답으로 미완료입니다. 확보한 공식 응답과 유효한 원본 API 캐시를 사용했으며 임의 자료로 채우지 않았습니다. 수신 PC에서도 이 응답이 발생하면 도서관 정보나루 발급 계정의 IP 등록 및 호출 한도를 확인해야 합니다. 필요한 접근 설정을 마친 뒤 같은 명령을 재실행하면 초기화 없이 갱신합니다. `validation.passed`는 저장 자료의 정합성 검사이며 원본 API 전수 수집 완료를 의미하지 않습니다.


## 강좌 수강신청 기간

새 테이블 없이 `courses`에 `enrollment_start`, `enrollment_end`(timestamptz), `enrollment_period_type`을 추가했습니다. K-MOOC는 공식 API 신청 기간을 저장합니다. MS Learn은 신청 기간이 없으면 `unrestricted`(기간 제한 없음), 날짜가 있는데 해석할 수 없으면 `unknown`으로 구분합니다. 가짜 종료일을 만들지 않습니다. 학습·수강 가능 기간은 관리하지 않으며 수강자가 원문에서 확인합니다.

신청 상태는 시간이 지나면 바뀌므로 고정 저장하지 않고 `course_availability` 뷰에서 조회 시 계산합니다. 뷰는 새 테이블이 아닙니다.

| 조회 값 | 의미 |
| --- | --- |
| `upcoming` | 예정: 신청 시작 전 |
| `ongoing` | 진행중: 신청 시작부터 종료 시각까지. MS 기간 제한 없음도 포함 |
| `ended` | 종료: 신청 종료 시각 경과 |
| NULL | 신청 기간 확인 필요 |

화면에는 `enrollment_status_label`을 바로 표시할 수 있습니다. MS는 `기간 제한 없음`으로 표시됩니다. 조회 예시는 다음과 같습니다.

```sql
SELECT course_id,title,enrollment_period_type,
       enrollment_start AT TIME ZONE 'Asia/Seoul' AS enrollment_start_kst,
       enrollment_end AT TIME ZONE 'Asia/Seoul' AS enrollment_end_kst,
       enrollment_status,enrollment_status_label
FROM public.course_availability;
```

추천은 신청 진행중 또는 기간 제한 없는 강좌만 대상으로 합니다. 신청 기간은 매 조회 때 다시 검사하므로 매일 상태 변경 배치를 실행할 필요가 없습니다. 기존 DB는 `python scripts/db.py migrate`로 013 마이그레이션을 적용하며, 전달 백업에는 적용된 상태가 포함됩니다. 기존 마이그레이션 12개는 변경하지 않았습니다. 현재 ERD는 `docs/ERD_최종.html`을 엽니다.


## 향후 자료별 AI 요약 자리

`courses.ai_mention`, `books.ai_mention`, `certifications.ai_mention`은 nullable TEXT이며 현재 모두 NULL입니다. 공식 API의 기존 설명과 별개로 향후 짧은 AI 요약을 넣기 위한 자리입니다. 지금은 요약 생성이나 AI 호출을 하지 않으며 현재 심사·임베딩에서도 사용하지 않습니다. `skill_tags`에는 ai_mention을 두지 않습니다. 014에서 만든 빈 스킬 태그 컬럼을 015에서 제거하고 자료 테이블로 바로잡았습니다. 기존 마이그레이션 파일은 수정하지 않습니다.

## 직원 날짜 정보

016 마이그레이션은 `employees`에 입사일 `hire_date DATE NULL`과 현 부서 시작일 `department_start_date DATE NULL`만 추가합니다. 기존 직원 날짜는 추정하지 않고 NULL로 유지합니다. 둘 다 있으면 부서 시작일은 입사일 이후 또는 같은 날이어야 합니다.
`get_employee_profile()`에서 두 날짜를 조회하며, `update_employee_dates(employee_id, hire_date="2024-03-01", department_start_date="2026-01-01")`로 저장합니다. 각 값은 YYYY-MM-DD 문자열·Python date·None을 받으며 None은 해당 날짜를 지웁니다. 기존 부서 변경 API는 날짜를 자동 변경하지 않으므로 배치일이 바뀌면 날짜 API도 호출합니다. `python scripts/db.py migrate`로 적용합니다.
