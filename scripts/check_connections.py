import os
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi
from sqlalchemy import create_engine, text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def check_hugging_face():
    token = os.getenv("HF_TOKEN")
    repo_id = os.getenv("HF_REPO_ID")

    if not token or not repo_id:
        print("[FAIL] HF_TOKEN 또는 HF_REPO_ID가 비어 있습니다.")
        return False

    try:
        api = HfApi(token=token)
        api.whoami()
        api.repo_info(repo_id=repo_id, repo_type="model")
        print("[OK] Hugging Face 인증 및 저장소 조회 성공")
        return True
    except Exception:
        print("[FAIL] Hugging Face 연결 실패")
        print("토큰, 저장소 ID, 저장소 접근 권한을 확인하세요.")
        return False


def check_database():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("[FAIL] DATABASE_URL이 비어 있습니다.")
        return False

    engine = None

    try:
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 15},
        )
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1")).scalar_one()

        if result != 1:
            raise RuntimeError("Unexpected database response")

        print("[OK] PostgreSQL 연결 성공")
        return True
    except Exception:
        print("[FAIL] PostgreSQL 연결 실패")
        print("연결 주소, 비밀번호, SSL 옵션을 확인하세요.")
        return False
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    hf_ok = check_hugging_face()
    db_ok = check_database()
    raise SystemExit(0 if hf_ok and db_ok else 1)