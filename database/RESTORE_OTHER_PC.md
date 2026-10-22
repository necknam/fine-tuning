# 새 PC 실행 순서 (Windows x64)

압축을 풀어 `database` 폴더 안에서 PowerShell을 엽니다. Python 3.12와 Miniforge가 필요합니다. [Miniforge 설치 안내](https://github.com/conda-forge/miniforge)를 따릅니다.

## 1. Python 및 PostgreSQL 준비

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File scripts/install_postgres.ps1
```

설치 도구는 Miniforge의 `growpath_db` 환경에 PostgreSQL 17.11과 포함된 pgvector 0.8.2 파일을 준비합니다. pgvector 파일의 manifest 해시도 검사합니다. Conda 설치 위치가 다르면 `-CondaExe "실제경로/conda.exe"`를 지정합니다.

## 2. 전달자의 PC 경로·실행 DB 파일을 보관하고 새로 복원

ZIP에 실행 DB의 내부 파일과 실제 설정도 들어 있습니다. 다른 PC에서는 이 내부 파일을 바로 실행하기보다 포함된 논리 백업을 새 환경에 복원하는 방법을 권장합니다. 아래 이름 변경은 전달 파일을 삭제하지 않고 보관합니다. 이미 실행 중인 해당 PostgreSQL이 있다면 먼저 중지합니다.

```powershell
# 같은 보관 이름이 이미 있으면 덮어쓰지 말고 다른 이름을 선택
Rename-Item -LiteralPath .env.local -NewName .env.local.sender
Rename-Item -LiteralPath data/local_db/postgres -NewName postgres.sender

.\.venv\Scripts\python.exe scripts/restore_db.py restore --archive data/exports/growpath_enrollment_20261022.dump --initialize --write-config
```

복원 도구가 출력하지 않는 비밀번호를 입력받습니다. 새 PC에서 사용할 PostgreSQL 비밀번호를 입력합니다. `.env.local`은 새 PC의 PostgreSQL 경로·비밀번호·DB URL로 생성됩니다. 기존 `.env.local`이나 실행 DB 폴더가 없으면 해당 Rename-Item만 생략합니다. 새 DB는 `127.0.0.1:55433`, 이름은 `growpath`입니다. 다른 서비스가 이 포트를 점유하면 해당 서비스를 확인하고 복원 명령에 다른 `--port`를 명시합니다. 기존 DB를 덮어쓰지 않습니다.

기본 Miniforge 위치가 아니면 복원 명령에 `--pg-bin "실제 PostgreSQL Library/bin 경로"`도 지정합니다. 실제 키는 `.env`에 포함돼 있으므로 공유 범위를 제한하고 필요하면 수신자의 키로 교체합니다. 분류 모델은 `gpt-6-luna`, 임베딩은 `text-embedding-3-small`입니다. 이 모델들에 대한 API 사용 권한이 필요합니다.

## 3. 복원 확인 및 이후 실행

```powershell
.\.venv\Scripts\python.exe scripts/db.py verify
.\.venv\Scripts\python.exe scripts/restore_db.py restore --archive data/exports/growpath_enrollment_20261022.dump --verify-only
```

복원 도구는 manifest의 SHA-256, 테이블 건수, 제약조건, 벡터 자기 유사도를 검사합니다. `PASS`를 확인합니다. 이후 DB 중지·시작은 다음과 같습니다.

```powershell
.\.venv\Scripts\python.exe scripts/local_db.py stop
.\.venv\Scripts\python.exe scripts/local_db.py start
```

최신 DB를 그대로 사용하려면 재수집을 실행할 필요가 없습니다. 새로 수집·심사·적재하려면 `run_catalog.cmd`를 더블클릭합니다. 기본 실행은 DB를 초기화하지 않고 AI·IT 자료를 갱신합니다. 초기화는 `--reset-catalog`를 명시한 경우에만 실행합니다. 자세한 옵션은 README.md를 참고합니다.

새 PC의 실제 복원은 수신자가 실행해야 합니다. 이 안내를 작성하면서 수신 PC에서 복원했다고 표시하지 않습니다.
