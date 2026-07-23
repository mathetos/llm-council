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

    def test_marketing_stage3_uses_decision_contract(self):
        self.assertEqual(
            get_profile("marketing")["stage3_required_sections"],
            [
                "Decision",
                "Hypothesis",
                "Metric",
                "First Experiment",
                "Kill Criteria",
                "Evidence Used",
                "Risks",
            ],
        )

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


class ConversionOperatorBaselineLockTests(unittest.TestCase):
    """
    Lock the run-d500e977 failure mode: gpt-4o-mini as Conversion Operator
    produced a prose-only Stage 1 answer (missing all required section labels)
    and a Stage 2 ranking without rubric labels, causing 0.75/0.75 guardrail
    degradation. Synthetic texts reproduce the exact missing lists.
    """

    CONVERSION_OPERATOR_MUST_INCLUDE = [
        "Execution Plan",
        "Experiment Design",
        "Resource Assumptions",
    ]

    # Prose-only answer in the style that failed: helpful content, no headings.
    PROSE_ONLY_STAGE1 = (
        "The fastest path is to publish the pricing table first and drive a "
        "small paid test toward the booking form. Start with the comparison "
        "asset, then measure booked calls weekly and adjust copy. The team "
        "should sequence the audit before the page launch."
    )

    # Ranking that discusses quality but names only one rubric label.
    RANKING_MISSING_RUBRIC = (
        "Response A is thorough and practical. Response B is weaker on "
        "sequencing. On Execution Feasibility, Response A wins clearly.\n\n"
        "FINAL RANKING:\n1. Response A\n2. Response B"
    )

    def test_stage1_prose_only_fails_exactly_the_observed_sections(self):
        validation = council.validate_required_sections(
            self.PROSE_ONLY_STAGE1,
            self.CONVERSION_OPERATOR_MUST_INCLUDE + ["Where I Disagree"],
        )
        self.assertFalse(validation["valid"])
        self.assertEqual(
            validation["missing"],
            [
                "Execution Plan",
                "Experiment Design",
                "Resource Assumptions",
                "Where I Disagree",
            ],
        )

    def test_stage1_with_exact_labels_passes(self):
        compliant = (
            "Execution Plan: publish pricing table first.\n"
            "Experiment Design: paid probe to booking form.\n"
            "Resource Assumptions: 2.5 marketers.\n"
            "Where I Disagree: organic-first is too slow here."
        )
        validation = council.validate_required_sections(
            compliant,
            self.CONVERSION_OPERATOR_MUST_INCLUDE + ["Where I Disagree"],
        )
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["missing"], [])

    def test_stage2_ranking_misses_exactly_four_marketing_rubric_labels(self):
        rubric = get_profile("marketing")["rubric_dimensions"]
        coverage = council.rubric_coverage_from_text(
            self.RANKING_MISSING_RUBRIC, rubric
        )
        self.assertFalse(coverage["all_present"])
        missing = [label for label, present in coverage["present"].items() if not present]
        self.assertEqual(
            missing,
            [
                "Strategic Clarity",
                "Message Resonance",
                "Differentiation Strength",
                "Testability",
            ],
        )
        self.assertTrue(coverage["present"]["Execution Feasibility"])

    def test_single_model_failure_yields_075_ratios_and_degraded(self):
        """One bad model out of four produces the observed 0.75 / 0.75 degradation."""
        diagnostics = {
            "role_schema_compliance": {"valid": 3, "total": 4},
            "rubric_coverage": {"all_present_count": 3, "total": 4},
            "stage3_required_sections_valid": True,
            "recommendation_overlap_score": 0.4,
            "unique_risk_count": 6,
        }
        status = council.evaluate_guardrails(
            diagnostics,
            thresholds={
                "role_schema_min_ratio": 1.0,
                "rubric_coverage_min_ratio": 1.0,
                "max_recommendation_overlap": 0.8,
                "min_unique_risk_count": 1,
            },
            enforcement_mode="degraded",
        )
        self.assertEqual(status["status"], "degraded")
        self.assertEqual(
            status["violations"],
            [
                "Role schema compliance ratio 0.75 below 1.00",
                "Rubric coverage ratio 0.75 below 1.00",
            ],
        )


class ChairmanDecisionContractPromptTests(unittest.IsolatedAsyncioTestCase):
    """Phase 4: marketing chairman prompt must force ICP choice, evidence floor, override disclosure."""

    STAGE1 = [{"model": "m1", "response": "r1"}]
    STAGE2 = [{"model": "m1", "ranking": "FINAL RANKING:\n1. Response A"}]

    async def _capture_prompt(self, run_context):
        capture = {}

        async def fake_query(model, messages, timeout=None):
            capture["prompt"] = messages[0]["content"]
            return {"content": "## Decision\nx"}, None

        with patch("backend.council.query_model_with_error", new=fake_query):
            await council.stage3_synthesize_final(
                "Should we target SMB or 6M+ pageview publishers?",
                self.STAGE1,
                self.STAGE2,
                run_context=run_context,
                chairman_model="test/chairman",
            )
        return capture["prompt"]

    async def test_marketing_with_packet_includes_icp_and_evidence_floor(self):
        run_context = {
            "profile": get_profile("marketing"),
            "research_packet": {
                "packet_id": "p1",
                "title": "Packet",
                "as_of": "2026-07-01",
                "summary": "s",
                "facts": [{"statement": "Fact one", "confidence": "high"}],
                "assumptions": ["A"],
                "constraints": ["No paid expansion"],
                "open_questions": [],
                "references": [],
            },
        }
        prompt = await self._capture_prompt(run_context)
        self.assertIn("pick ONE primary ICP", prompt)
        self.assertIn("secondary or later", prompt)
        self.assertIn("at least TWO specific research packet facts", prompt)
        self.assertIn("confidence label", prompt)
        self.assertIn("violates or overrides any packet constraint", prompt)

    async def test_marketing_without_packet_waives_evidence_floor_explicitly(self):
        prompt = await self._capture_prompt({"profile": get_profile("marketing")})
        self.assertIn("pick ONE primary ICP", prompt)
        self.assertNotIn("at least TWO specific research packet facts", prompt)
        self.assertIn("no research packet was provided", prompt)

    async def test_non_marketing_profile_gets_no_decision_contract_guidance(self):
        prompt = await self._capture_prompt({"profile": get_profile("product_development")})
        self.assertNotIn("Decision Contract", prompt)
        self.assertNotIn("pick ONE primary ICP", prompt)


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
                "## Decision\nx\n## Hypothesis\nx\n## Metric\nx\n"
                "## First Experiment\nx\n## Kill Criteria\nx\n"
                "## Evidence Used\nx\n## Risks\n- risk a"
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
