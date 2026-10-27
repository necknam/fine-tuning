# 로컬 DB 설치·복원 — Miniforge 기준

2026-10-26 이 PC에서 로컬 PostgreSQL을 실행하고 마이그레이션 001~020 및 가상 직원 100명을 확인했다. 업무 DB는 `127.0.0.1:55433/growpath`다. 기존 사용자 5명을 포함한 직원 총수는 105명이다.

## 1. 환경 준비

프로젝트 최상위 PowerShell에서 실행한다. 이 PC에는 Python 3.12.13 `llm_env`와 PostgreSQL용 `growpath_db` Miniforge 환경이 이미 있다. `.venv`를 추가로 만들지 않는다. 다른 PC에서 `llm_env`가 없을 때만 `conda create -n llm_env python=3.12 pip -y`로 생성한다.

```powershell
cd C:\final_team2\project
$py = "$env:USERPROFILE\miniforge3\envs\llm_env\python.exe"
& $py -m pip install -r database/requirements.txt
# PostgreSQL이 없는 새 PC에서만 설치. 이미 준비된 이 PC에서는 생략한다.
powershell -ExecutionPolicy Bypass -File database/scripts/install_postgres.ps1
cd database
```

Python 패키지는 `llm_env`, PostgreSQL 17.11 실행 파일은 `growpath_db/Library/bin`에 있다. pgvector 0.8.2는 설치 스크립트가 포함된 파일의 해시를 검사해 배치한다. 기본 Miniforge 위치가 다르면 `$py`와 `-CondaExe`, 복원의 `--pg-bin`을 실제 경로로 지정한다.

## 2. 이 PC의 기존 DB 실행

```powershell
& $py scripts/local_db.py start
& $py scripts/local_db.py status
& $py scripts/db.py verify
```

이 PC에서는 이미 복원·갱신했으므로 `--initialize --write-config`를 다시 실행하지 않는다. `.env.local`은 이 PC 연결용이고 기존 키·연결 비밀번호는 보존했다. 주소·비밀번호를 Git에 올리지 않는다.

## 3. 다른 PC 또는 별도 DB에 최신 덤프 복원

최신 파일은 `data/exports/growpath_local_100_passwords_20261026.dump`와 같은 이름의 `.manifest.json`이다. 2026-10-21/22 덤프와 이전 `growpath_latest.dump`는 과거 상태다.

실행 DB 폴더와 `.env.local`이 없는 새 PC에서만:

```powershell
& $py scripts/restore_db.py restore --archive data/exports/growpath_local_100_passwords_20261026.dump --initialize --write-config
```

기존 서버에 비교용 새 DB를 만들 때:

```powershell
& $py scripts/restore_db.py restore --archive data/exports/growpath_local_100_passwords_20261026.dump --database growpath_review
```

기존 DB·실행 폴더·`.env.local`은 자동 덮어쓰지 않는다. 비교 DB 검증은 `--database growpath_review --verify-only`와 같은 덤프를 지정한다. 비밀번호는 `.env.local` 또는 터미널 입력으로 받으며 출력하지 않는다. `.env.local`은 비교 DB로 자동 전환하지 않는다.

## 4. 가상 직원 100명과 보존 범위

AI데이터센터·인재경영실·업무시스템팀·인프라운영팀·데이터운영팀에 각 20명, 부서장 각 1명이다. 기존 TEST_MANUAL 9명의 ID·이름·이메일·비밀번호 해시를 보존하고 프로필·배정을 재구성했으며 신규 91명을 추가했다. 기술 2~4개, 자격 0~2개, 가상 학력·날짜·프로젝트 설명을 기존 마스터 FK로 연결했다. 실제 사용자 5명은 행 전체를 변경하지 않았다.

이전 Cloud 100명 원본은 현재 연결에 없어서 사용자 승인으로 기존 시드 20261023과 부서 배정 규칙을 이용해 재구성했다. 이전 Cloud의 모든 프로필·ID와 일치하는 원본 복원이 아니다. 테스트 직원 100명의 비밀번호는 사용자 지정 공통값으로 통일하고 개별 솔트 Argon2id 해시 100건을 검증했다. 기존 공통 Cloud 비밀번호가 그대로 통한다고 가정하지 않는다. 실제 팀원 시트를 적재하거나 새 AI 추천·보고서를 생성한 작업도 아니다.

```powershell
# 미리보기. 완료된 100명이면 ALREADY_COMPLETE이며 다시 생성하지 않는다.
& $py scripts/seed_local_test_workforce.py
# 최초 재구성이 필요한 로컬 DB에서만:
& $py scripts/seed_local_test_workforce.py --apply
```

기존 사용자 5명의 사번은 원래 NULL이므로 추정값을 넣지 않았다. 020의 `employees_number_required` CHECK는 이 과거 누락만 NOT VALID로 보존하고 신규·수정 행에는 적용한다. `verify`는 누락 5건을 `legacy_constraint_warnings`로 명시한다. 그 밖의 미검증 제약은 실패 처리한다.

## 5. 문서·백업 갱신

```powershell
& $py scripts/refresh_db_documents.py
& $py scripts/restore_db.py backup --output data/exports/growpath_local_새날짜.dump
& $py scripts/local_db.py stop
```

ERD 두 경로의 기존 테마와 통합 보고서의 학습 절은 유지하고 실제 DB 구조·건수만 갱신한다. 덤프 manifest는 SHA-256·테이블 건수·제약·확장·뷰를 기록하며 복원 시 대조하고 벡터 자기 유사도를 검사한다. 기존 사용자와 인증 해시가 포함된 전체 덤프는 지정 수신자에게만 전달하며 Git push하지 않는다.

변경 전 백업: `data/exports/before_local_refresh_20261026.dump`. 실제 접속 설정은 `.env.local`, 상세 구조는 프로젝트 `docs/DATABASE.md`, ERD는 `database/docs/ERD_최종.html`을 참고한다. 권한은 서버에서 별도로 검증해야 하며 구조 검사 성공이 추천 품질 합격을 뜻하지 않는다.

관련 문서: [DB 구조](docs/DATABASE.md) · [ERD](docs/ERD_최종.html)


검증 완료(2026-10-26): 별도 growpath_verify_20261026 DB에 실제 복원, 50테이블·12,519행·210제약·자료/규정 벡터 검사 PASS. 회귀 테스트 4/4 PASS. 가상 직원 기술 293행·자격 96행·학력 100행. 검증 기록은 data/local_db/local_refresh_verification.json. 복원 검증 DB는 조사·비교용으로 보존했다.
