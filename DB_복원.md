# PostgreSQL 전체 DB 설치·복원

Windows x64 / Python 3.12 / PostgreSQL 17.11 / pgvector 0.8.2 기준. Git에서 받는 파일은 전체 논리 백업이며 실제 테이블·데이터·임베딩을 포함한다. 실행 중인 DB 내부 파일이나 로컬 관리자 비밀번호는 포함하지 않는다.

## 1. 준비와 의존성 설치

Python 3.12와 [Miniforge](https://github.com/conda-forge/miniforge)를 설치한다. 아래 명령은 project 최상위에서 실행한다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r database/requirements.txt
powershell -ExecutionPolicy Bypass -File database/scripts/install_postgres.ps1
```

설치 스크립트는 Conda의 growpath_db 환경에 PostgreSQL 17.11을 설치하고 포함된 pgvector 파일을 해시 검증 후 배치한다. 동일 파일은 유지하며 다른 확장이 이미 설치돼 있으면 덮어쓰지 않는다. 기존 환경을 쓸 때는 `-SkipPackageInstall`을 추가한다. 기본 경로가 아니면 `-CondaExe`로 conda.exe를 지정한다.

## 2. 새 PC에서 전체 복원

```powershell
cd database
..\.venv\Scripts\python.exe scripts/restore_db.py restore --archive data/exports/growpath_full_20261021.dump --initialize --write-config
```

새 관리자 비밀번호를 물으면 터미널에 입력한다. 비밀번호는 출력하지 않는다. 새 PostgreSQL 저장 폴더를 만들고 127.0.0.1:55433에서 시작한 뒤 growpath DB를 생성·복원한다. 성공하면 `.env.local`에 연결을 저장한다.

이미 DB 저장 폴더·대상 DB·`.env.local`이 있으면 덮어쓰지 않는다. 기존 서버에 별도 DB로 복원할 때는 아래처럼 실행한다. 비밀번호는 `.env.local`의 POSTGRES_PASSWORD 또는 환경변수·입력값을 사용한다.

```powershell
python scripts/restore_db.py restore --archive data/exports/growpath_full_20261021.dump --database growpath_review
```

다른 설치 경로는 `--pg-bin "C:/.../Library/bin"`, 다른 포트는 `--port`로 지정한다. 복원 실패 DB는 조사할 수 있게 남기며 자동 삭제하지 않는다.

## 3. 확인·시작·중지

```powershell
python scripts/local_db.py status
python scripts/db.py verify
python scripts/local_db.py stop
python scripts/local_db.py start
```

PyCharm은 Host 127.0.0.1, Port 55433, Database growpath, User postgres, Password `.env.local`의 값, SSL 사용 안 함으로 연결한다. SQL 콘솔도 growpath를 선택한다.

```sql
SELECT current_database(), current_setting('server_version');
SELECT count(*) FROM public.courses;
SELECT extname, extversion FROM pg_extension ORDER BY extname;
```

복원 스크립트는 백업 SHA-256, 50개 테이블 건수, 기본키·외래키·CHECK 등 202개 제약조건, 뷰·확장, 자료/규정 벡터 거리 연산을 확인한다. 2026-10-21 별도 검증 DB에서 총 15,608행 복원 검증을 통과했다. 결과는 Git 제외 경로 `data/local_db/restore_verification.json`에 저장한다.

## 4. 새 백업 만들기

```powershell
python scripts/restore_db.py backup --output data/exports/growpath_full_새날짜.dump
```

동일 스냅샷에서 메타데이터와 DB 백업을 만들고 옆에 `.manifest.json`을 저장한다. 기존 파일은 덮어쓰지 않는다. 포함 대상은 모든 DB 스키마·테이블·행·벡터·뷰·함수·시퀀스이며, 클러스터 역할·관리자 비밀번호와 외부 파일 저장소는 별도다. 규정 원본은 database/data/regulations에 보존한다.

## Git 범위

전체 DB 백업·manifest·pgvector 설치 파일·확정 학습 데이터는 포함한다. `.env`·`.env.local`·토큰·실제 실행 DB 폴더·로그·캐시·모델 가중치는 제외한다. 실행 DB 파일을 직접 복사하거나 수정하지 않는다.

상세 테이블: [로컬 DB](docs/DATABASE.md), [팩토리 Neon](docs/FACTORY_DATABASE.md). 공식 형식: [pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html), [pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).
