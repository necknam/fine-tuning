"""Dependency-free unit tests for src.database.vectors.regulation_vectors and V11 regulation RAG grounding."""
import hashlib
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.database.vectors import regulation_vectors as rv


class RegulationVectorTests(unittest.TestCase):
    def test_input_text_and_hash_strip_null_bytes(self):
        row = {
            "rag_chunk_id": "c1",
            "context_path": "인재개발규정 > 별표 1",
            "chunk_text": "일반직 4급\x00 80시간",
        }
        cleaned = rv.input_text(row)
        self.assertNotIn("\x00", cleaned)
        self.assertEqual(cleaned, "인재개발규정 > 별표 1\n\n일반직 4급 80시간")
        expected_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
        self.assertEqual(rv.input_hash(row), expected_hash)

    def test_embedding_api_text_bounds_utf8_bytes_to_8000(self):
        long_text = "가나다라마바사아자차카타파하 " * 400  # > 10,000 UTF-8 bytes
        self.assertGreater(len(long_text.encode("utf-8")), 8000)
        bounded = rv.embedding_api_text(long_text, max_utf8_bytes=8000)
        self.assertLessEqual(len(bounded.encode("utf-8")), 8000)
        self.assertIsInstance(bounded.encode("utf-8").decode("utf-8"), str)

    def test_vector_values_validation(self):
        valid = [0.01] * 1536
        self.assertEqual(len(rv.vector_values(valid)), 1536)
        self.assertEqual(len(rv.vector_values(json.dumps(valid))), 1536)
        for invalid in ([0.0] * 1536, [0.1] * 10, [float("nan")] * 1536):
            with self.assertRaisesRegex(ValueError, "Invalid regulation vector"):
                rv.vector_values(invalid)

    def test_prepare_regulation_context_falls_back_to_review_for_v11(self):
        fake_llm_module = types.ModuleType("src.clients.llm_adapter")
        fake_llm_module.llm_adapter = MagicMock()
        fake_llm_module.DISCONNECTED_STANDARD_MESSAGE = "DISCONNECTED"
        with patch.dict(sys.modules, {"src.clients.llm_adapter": fake_llm_module}):
            from src.roadmap.agents import roadmap_agent as ra

            sample_review_chunk = {
                "rag_chunk_id": "781aff70-ea11-5178-96a9-313352d61b40",
                "context_path": "인재개발규정 > 별표 1 > 일반직 및 운영직 4급",
                "chunk_text": "연간 기준학습시간: 80시간",
                "requires_review": True,
            }
            fake_conn = MagicMock()
            fake_conn.__enter__.return_value = fake_conn

            def fake_search(conn, query, limit=5, include_review=False, **kwargs):
                if not include_review:
                    return {"matches": [], "as_of": "2026-10-16", "embedding_model": rv.MODEL}
                return {"matches": [sample_review_chunk], "as_of": "2026-10-16", "embedding_model": rv.MODEL}

            with patch.object(rv, "connect", return_value=fake_conn), patch.object(rv, "search", side_effect=fake_search):
                ctx = ra.prepare_regulation_context(
                    {"job_title": "전산 엔지니어 (일반직 4급)", "work_context_summary": "데이터 파이프라인 구축", "target_skills": ["SQL 기본 문법 & 조인"]},
                    {},
                )
                self.assertEqual(ctx["regulation_rag"]["status"], "verification_required")
                self.assertEqual(ctx["regulation_rag"]["approved"], [])
                self.assertEqual(len(ctx["regulation_rag"]["review_only"]), 1)
                self.assertEqual(ctx["regulation_rag"]["review_only"][0]["rag_chunk_id"], "781aff70-ea11-5178-96a9-313352d61b40")


if __name__ == "__main__":
    unittest.main(verbosity=2)