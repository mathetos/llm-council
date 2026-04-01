"""Tests for model pairing settings and role assignment validation."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend import main, storage


class ModelPairingApiTests(unittest.TestCase):
    """Verify pairing settings endpoints and failure diagnostics."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self.data_dir = base / "conversations"
        self.verdicts_dir = base / "verdicts"
        self.research_dir = base / "research_packets"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.verdicts_dir.mkdir(parents=True, exist_ok=True)
        (self.research_dir / "marketing").mkdir(parents=True, exist_ok=True)
        (self.research_dir / "marketing" / "default.json").write_text(
            """
{
  "packet_id": "default",
  "profile_id": "marketing",
  "title": "Marketing Packet",
  "as_of": "2026-03-31",
  "summary": "Packet summary",
  "facts": [{"statement": "Fact", "confidence": "high"}],
  "assumptions": ["A1"],
  "constraints": ["C1"],
  "open_questions": ["Q1"],
  "references": ["R1"]
}
            """.strip(),
            encoding="utf-8",
        )

        storage.DATA_DIR = str(self.data_dir)
        storage.VERDICTS_DIR = str(self.verdicts_dir)
        storage.RESEARCH_PACKETS_DIR = str(self.research_dir)
        main.INTERROGATION_SESSIONS.clear()
        self.client = TestClient(main.app)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _interrogation_payload(self):
        return {
            "completed": True,
            "steps": [{"question": "Q1", "answer": "A1", "deferred": False}],
            "summary": "- s",
            "model": "test-model",
            "min_questions": 2,
            "max_questions": 5,
            "questions_asked": 1,
            "run_context": {
                "profile_id": "marketing",
                "packet_id": "default",
                "role_assignments": [],
            },
        }

    def test_settings_model_pairings_endpoint_lists_expected_pairings(self):
        res = self.client.get("/api/settings/model-pairings")
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        ids = {item["id"] for item in payload["pairings"]}
        self.assertIn("premium", ids)
        self.assertIn("free_auto_router", ids)
        self.assertEqual(ids, {"premium", "free_auto_router"})

    def test_test_pairing_returns_actionable_failure_hint(self):
        with patch(
            "backend.main.list_user_visible_models_with_error",
            new=AsyncMock(return_value=(None, "upstream unavailable")),
        ), patch(
            "backend.main.query_model_with_error",
            new=AsyncMock(return_value=(None, "HTTP 401: unauthorized")),
        ):
            res = self.client.post(
                "/api/settings/test-pairing",
                json={"model_pairing_id": "free_auto_router"},
            )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertFalse(payload["all_passed"])
        self.assertTrue(payload["checks"])
        first = payload["checks"][0]
        self.assertEqual(first["status"], "fail")
        self.assertEqual(first["error_type"], "auth")
        self.assertTrue(first["hint"])

    def test_test_pairing_pass_includes_routed_model(self):
        with patch(
            "backend.main.list_user_visible_models_with_error",
            new=AsyncMock(return_value=(None, "upstream unavailable")),
        ), patch(
            "backend.main.query_model_with_error",
            new=AsyncMock(
                return_value=(
                    {"content": "OK", "model_used": "google/gemma-3-27b-it:free"},
                    None,
                )
            ),
        ):
            res = self.client.post(
                "/api/settings/test-pairing",
                json={"model_pairing_id": "free_auto_router"},
            )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertTrue(payload["all_passed"])
        self.assertTrue(payload["checks"])
        self.assertEqual(payload["checks"][0]["status"], "pass")
        self.assertIn("routed_model", payload["checks"][0])

    def test_pairing_eligibility_marks_filtered_models(self):
        visible = [
            "google/gemma-3-27b-it:free",
            "google/gemini-3.1-flash-lite-preview",
        ]
        with patch(
            "backend.main.list_user_visible_models_with_error",
            new=AsyncMock(return_value=(visible, None)),
        ):
            res = self.client.get("/api/settings/model-pairings/free_auto_router/eligibility")
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload["model_pairing_id"], "free_auto_router")
        self.assertTrue(payload["checks"])
        statuses = {item["model"]: item["status"] for item in payload["checks"]}
        self.assertEqual(statuses.get("nvidia/nemotron-3-nano-30b-a3b:free"), "filtered")

    def test_pairing_eligibility_reports_upstream_error(self):
        with patch(
            "backend.main.list_user_visible_models_with_error",
            new=AsyncMock(return_value=(None, "HTTP 401: unauthorized")),
        ):
            res = self.client.get("/api/settings/model-pairings/premium/eligibility")
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload["error"], "HTTP 401: unauthorized")
        self.assertTrue(all(item["eligible"] is None for item in payload["checks"]))

    def test_test_pairing_marks_preflight_filtered_as_blocked(self):
        with patch(
            "backend.main.list_user_visible_models_with_error",
            new=AsyncMock(return_value=(["google/gemma-3-27b-it:free"], None)),
        ):
            res = self.client.post(
                "/api/settings/test-pairing",
                json={"model_pairing_id": "free_auto_router"},
            )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        blocked = [item for item in payload["checks"] if item["status"] == "blocked"]
        self.assertTrue(blocked)
        self.assertEqual(blocked[0]["error_type"], "preflight_filtered")

    def test_pairing_diagnostics_returns_resolution_payload(self):
        with patch(
            "backend.main.list_user_visible_models_with_error",
            new=AsyncMock(return_value=(["openrouter/free", "google/gemma-3-27b-it:free"], None)),
        ), patch(
            "backend.main.list_models_with_error",
            new=AsyncMock(
                return_value=(
                    [
                        {"id": "openrouter/free", "context_length": 131072},
                        {"id": "google/gemma-3-27b-it:free", "context_length": 131072},
                    ],
                    None,
                )
            ),
        ):
            res = self.client.get("/api/settings/model-pairings/free_auto_router/diagnostics")
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload["model_pairing_id"], "free_auto_router")
        self.assertIn("requested", payload)
        self.assertIn("resolved", payload)
        self.assertIn("substitutions", payload)

    def test_free_models_endpoint_lists_visible_free_models(self):
        with patch(
            "backend.main.list_user_visible_models_with_error",
            new=AsyncMock(
                return_value=(
                    [
                        "openrouter/free",
                        "google/gemma-3-27b-it:free",
                        "nvidia/nemotron-3-nano-30b-a3b:free",
                    ],
                    None,
                )
            ),
        ), patch(
            "backend.main.list_models_with_error",
            new=AsyncMock(
                return_value=(
                    [
                        {
                            "id": "google/gemma-3-27b-it:free",
                            "context_length": 131072,
                            "pricing": {"prompt": "0", "completion": "0"},
                        },
                        {
                            "id": "nvidia/nemotron-3-nano-30b-a3b:free",
                            "context_length": 256000,
                            "pricing": {"prompt": "0", "completion": "0"},
                        },
                    ],
                    None,
                )
            ),
        ):
            res = self.client.get("/api/settings/free-models")
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        ids = [item["id"] for item in payload["models"]]
        self.assertNotIn("openrouter/free", ids)
        self.assertIn("google/gemma-3-27b-it:free", ids)
        self.assertIn("nvidia/nemotron-3-nano-30b-a3b:free", ids)
        self.assertEqual(payload["eligible_count"], 2)
        self.assertEqual(payload["catalog_count"], 2)

    def test_free_variant_check_reports_available_and_eligible(self):
        with patch(
            "backend.main.list_user_visible_models_with_error",
            new=AsyncMock(return_value=(["nvidia/nemotron-3-nano-30b-a3b:free"], None)),
        ), patch(
            "backend.main.list_models_with_error",
            new=AsyncMock(
                return_value=(
                    [
                        {
                            "id": "nvidia/nemotron-3-nano-30b-a3b:free",
                            "pricing": {"prompt": "0", "completion": "0"},
                        }
                    ],
                    None,
                )
            ),
        ):
            res = self.client.post(
                "/api/settings/free-variant-check",
                json={"model_id": "nvidia/nemotron-3-nano-30b-a3b"},
            )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload["variant_model_id"], "nvidia/nemotron-3-nano-30b-a3b:free")
        self.assertEqual(payload["status"], "available_and_eligible")
        self.assertTrue(payload["in_catalog"])
        self.assertTrue(payload["eligible"])

    def test_free_variant_check_reports_available_but_filtered(self):
        with patch(
            "backend.main.list_user_visible_models_with_error",
            new=AsyncMock(return_value=(["google/gemma-3-27b-it:free"], None)),
        ), patch(
            "backend.main.list_models_with_error",
            new=AsyncMock(
                return_value=(
                    [
                        {
                            "id": "nvidia/nemotron-3-nano-30b-a3b:free",
                            "pricing": {"prompt": "0", "completion": "0"},
                        }
                    ],
                    None,
                )
            ),
        ):
            res = self.client.post(
                "/api/settings/free-variant-check",
                json={"model_id": "nvidia/nemotron-3-nano-30b-a3b"},
            )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload["status"], "available_but_filtered")
        self.assertTrue(payload["in_catalog"])
        self.assertFalse(payload["eligible"])

    def test_free_variant_check_reports_not_available(self):
        with patch(
            "backend.main.list_user_visible_models_with_error",
            new=AsyncMock(return_value=(["google/gemma-3-27b-it:free"], None)),
        ), patch(
            "backend.main.list_models_with_error",
            new=AsyncMock(
                return_value=(
                    [
                        {
                            "id": "google/gemma-3-27b-it:free",
                            "pricing": {"prompt": "0", "completion": "0"},
                        }
                    ],
                    None,
                )
            ),
        ):
            res = self.client.post(
                "/api/settings/free-variant-check",
                json={"model_id": "openai/not-a-real-model"},
            )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload["status"], "not_available")
        self.assertFalse(payload["in_catalog"])

    def test_message_rejects_unknown_pairing(self):
        conv = self.client.post("/api/conversations", json={}).json()
        conv_id = conv["id"]
        res = self.client.post(
            f"/api/conversations/{conv_id}/message",
            json={
                "content": "Question",
                "model_pairing_id": "does-not-exist",
                "interrogation": self._interrogation_payload(),
            },
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Unknown model_pairing_id", res.json()["detail"])

    def test_message_rejects_override_role_not_in_profile(self):
        dummy_stage1 = [{"model": "m1", "response": "r1"}]
        dummy_stage2 = [{"model": "m1", "ranking": "FINAL RANKING:\n1. Response A"}]
        dummy_stage3 = {"model": "m1", "response": "final"}
        dummy_meta = {"label_to_model": {}, "aggregate_rankings": []}

        with patch(
            "backend.main.run_full_council",
            new=AsyncMock(return_value=(dummy_stage1, dummy_stage2, dummy_stage3, dummy_meta)),
        ), patch(
            "backend.main.generate_conversation_title",
            new=AsyncMock(return_value="Test Title"),
        ):
            conv = self.client.post("/api/conversations", json={}).json()
            conv_id = conv["id"]
            res = self.client.post(
                f"/api/conversations/{conv_id}/message",
                json={
                    "content": "Question",
                    "interrogation": self._interrogation_payload(),
                    "role_assignments_override": {"not_a_role": "openai/gpt-4o-mini"},
                },
            )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Unknown role ids", res.json()["detail"])


if __name__ == "__main__":
    unittest.main()
