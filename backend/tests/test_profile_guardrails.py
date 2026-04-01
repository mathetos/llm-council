"""Tests for profile guardrails contracts and packet API surface."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend import council, main, storage
from backend.config import COUNCIL_PROFILES, DEFAULT_PROFILE_ID, get_profile


class ConfigProfileContractTests(unittest.TestCase):
    """Validate profile contracts loaded from config."""

    def test_default_profile_exists(self):
        self.assertIn(DEFAULT_PROFILE_ID, COUNCIL_PROFILES)

    def test_each_profile_has_required_sections(self):
        for profile_id, profile in COUNCIL_PROFILES.items():
            self.assertEqual(profile["id"], profile_id)
            self.assertTrue(profile["required_context_fields"])
            self.assertTrue(profile["rubric_dimensions"])
            self.assertTrue(profile["perspective_roles"])
            self.assertTrue(profile["stage3_required_sections"])

    def test_get_profile_rejects_unknown(self):
        with self.assertRaises(ValueError):
            get_profile("does_not_exist")


class ProfileGuardrailsApiTests(unittest.TestCase):
    """Verify profile listing and packet resolution endpoints."""

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

    def test_profiles_endpoint_returns_default_and_profiles(self):
        res = self.client.get("/api/profiles")
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertIn("default_profile_id", payload)
        self.assertTrue(payload["profiles"])

    def test_profile_packets_endpoint_lists_local_packets(self):
        res = self.client.get("/api/profiles/marketing/packets")
        self.assertEqual(res.status_code, 200)
        packets = res.json()["packets"]
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0]["packet_id"], "default")

    def test_profile_packets_endpoint_rejects_unknown_profile(self):
        res = self.client.get("/api/profiles/unknown_profile/packets")
        self.assertEqual(res.status_code, 400)

    def test_start_interrogation_rejects_unknown_packet(self):
        conv = self.client.post("/api/conversations", json={}).json()
        conv_id = conv["id"]
        res = self.client.post(
            f"/api/conversations/{conv_id}/interrogation/start",
            json={
                "content": "Plan this",
                "profile_id": "marketing",
                "packet_id": "does-not-exist",
            },
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("not found", res.json()["detail"].lower())


class GuardrailEvaluationTests(unittest.TestCase):
    """Validate diagnostics-to-status gate behavior."""

    def test_evaluate_guardrails_pass(self):
        diagnostics = {
            "role_schema_compliance": {"valid": 3, "total": 3},
            "rubric_coverage": {"all_present_count": 3, "total": 3},
            "stage3_required_sections_valid": True,
            "recommendation_overlap_score": 0.4,
            "unique_risk_count": 2,
        }
        thresholds = {
            "role_schema_min_ratio": 1.0,
            "rubric_coverage_min_ratio": 1.0,
            "max_recommendation_overlap": 0.8,
            "min_unique_risk_count": 1,
        }
        status = council.evaluate_guardrails(
            diagnostics,
            thresholds=thresholds,
            enforcement_mode="degraded",
        )
        self.assertEqual(status["status"], "pass")
        self.assertEqual(status["violations"], [])

    def test_evaluate_guardrails_degraded_on_multiple_violations(self):
        diagnostics = {
            "role_schema_compliance": {"valid": 1, "total": 3},
            "rubric_coverage": {"all_present_count": 1, "total": 3},
            "stage3_required_sections_valid": False,
            "recommendation_overlap_score": 0.95,
            "unique_risk_count": 0,
        }
        thresholds = {
            "role_schema_min_ratio": 1.0,
            "rubric_coverage_min_ratio": 1.0,
            "max_recommendation_overlap": 0.8,
            "min_unique_risk_count": 1,
        }
        status = council.evaluate_guardrails(
            diagnostics,
            thresholds=thresholds,
            enforcement_mode="degraded",
        )
        self.assertEqual(status["status"], "degraded")
        self.assertGreaterEqual(len(status["violations"]), 4)

    def test_evaluate_guardrails_strict_fail(self):
        diagnostics = {
            "role_schema_compliance": {"valid": 0, "total": 2},
            "rubric_coverage": {"all_present_count": 0, "total": 2},
            "stage3_required_sections_valid": False,
            "recommendation_overlap_score": 0.99,
            "unique_risk_count": 0,
        }
        thresholds = {
            "role_schema_min_ratio": 1.0,
            "rubric_coverage_min_ratio": 1.0,
            "max_recommendation_overlap": 0.8,
            "min_unique_risk_count": 1,
        }
        status = council.evaluate_guardrails(
            diagnostics,
            thresholds=thresholds,
            enforcement_mode="strict_fail",
        )
        self.assertEqual(status["status"], "fail")
        self.assertTrue(status["violations"])


class GuardrailMetadataIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Ensure full runs always emit guardrail status metadata."""

    async def test_run_full_council_includes_guardrail_status(self):
        profile = get_profile("marketing")
        run_context = {
            "profile_id": "marketing",
            "profile": profile,
            "packet_id": "default",
            "packet_title": "Packet",
            "packet_as_of": "2026-03-31",
            "research_packet": {
                "packet_id": "default",
                "profile_id": "marketing",
                "title": "Packet",
                "as_of": "2026-03-31",
                "summary": "Summary",
                "facts": [{"statement": "Fact", "confidence": "high"}],
                "assumptions": ["A1"],
                "constraints": ["C1"],
                "open_questions": ["Q1"],
                "references": ["R1"],
            },
            "role_assignments": [
                {
                    "model": "m1",
                    "role_id": "systems_thinker",
                    "role_name": "Systems Thinker",
                    "mandate": "m",
                    "must_include": ["Dependencies"],
                }
            ],
        }

        stage1 = [
            {
                "model": "m1",
                "response": "r1",
                "role_validation": {"valid": True, "missing": []},
            }
        ]
        stage2 = [
            {
                "model": "m1",
                "ranking": "FINAL RANKING:\n1. Response A",
                "parsed_ranking": ["Response A"],
                "rubric_coverage": {"all_present": True, "present": {}},
            }
        ]
        stage3 = {
            "model": "m1",
            "response": (
                "## Facts\nx\n## Assumptions\nx\n## Reconciliation\nx\n"
                "## Risks\n- risk a\n## Recommendation\nx"
            ),
            "section_validation": {"valid": True, "missing": []},
        }

        with patch("backend.council.stage1_collect_responses", new=AsyncMock(return_value=stage1)), patch(
            "backend.council.stage2_collect_rankings",
            new=AsyncMock(return_value=(stage2, {"Response A": "m1"})),
        ), patch(
            "backend.council.stage3_synthesize_final",
            new=AsyncMock(return_value=stage3),
        ), patch(
            "backend.council.GUARDRAIL_ENFORCEMENT_MODE",
            new="degraded",
        ):
            _, _, _, metadata = await council.run_full_council(
                "question",
                run_context=run_context,
            )

        self.assertIn("guardrail_status", metadata)
        self.assertIn(metadata["guardrail_status"]["status"], {"pass", "degraded"})


if __name__ == "__main__":
    unittest.main()
