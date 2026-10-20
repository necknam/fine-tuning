import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.database.db_client import db_client


def test_schema_file_exists():
    """Canonical schema resources exist; obsolete direct DDL fails closed."""
    from src.database.deployment import CATALOG, MIGRATIONS
    schema_path = project_root / "src" / "database" / "schema.sql"
    assert schema_path.is_file(), "Canonical schema guard is missing"
    assert "RAISE EXCEPTION" in schema_path.read_text(encoding="utf-8")
    assert list(MIGRATIONS.glob("*.sql")), "Canonical migrations are missing"
    for table in ("skill_tags", "courses", "prompt_versions", "users"):
        assert "public." + table in CATALOG, "Canonical table definition missing: " + table
    print("[PASS] 2-1. Canonical schema/catalog/migration resources verified")


def test_database_client_health():
    """데이터베이스 클라이언트 헬스체크 및 연결 상태 진단"""
    health = db_client.check_health()
    assert isinstance(health, dict), "check_health 반환값이 dict가 아닙니다."

    if health.get("connected"):
        print(f"[PASS] 2-2. DB 연결 성공: {health.get('message')}")
    else:
        print(f"[INFO] 2-2. DB 연결 실패: SUPABASE_DB_URL 또는 로컬 Docker 상태 확인: {health.get('message')}")


def test_mock_profile_fallback():
    """보관 스키마의 기존 테스트 프로필 호환 조회 확인"""
    profiles = db_client.fetch_mock_profiles()
    assert isinstance(profiles, list), "fetch_mock_profiles 반환값이 list가 아닙니다."
    print(f"[PASS] 2-3. 모의 프로필 인출 루틴 정상 (인출 건수: {len(profiles)}건)")


if __name__ == "__main__":
    print("=== [Step 2] DB 클라이언트 및 스키마 검증 시작 ===")
    test_schema_file_exists()
    test_database_client_health()
    test_mock_profile_fallback()
    print("=== [Step 2] 검증 완료 ===\n")