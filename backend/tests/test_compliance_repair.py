"""Tests for Stage 1/2 prompt hardening and the single compliance repair retry."""

import unittest
from unittest.mock import AsyncMock, patch

from backend import council
from backend.config import get_profile

COMPLIANT_STAGE1 = (
    "## Execution Plan\npublish pricing table first.\n"
    "## Experiment Design\npaid probe to booking form.\n"
    "## Resource Assumptions\n2.5 marketers.\n"
    "## Where I Disagree\norganic-first is too slow here."
)

PROSE_ONLY_STAGE1 = (
    "The fastest path is to publish the pricing table first and drive a small "
    "paid test toward the booking form."
)

COMPLIANT_RANKING = (
    "Strategic Clarity: A 8/10 clear, B 5/10 vague.\n"
    "Message Resonance: A 7/10, B 6/10.\n"
    "Differentiation Strength: A 6/10, B 4/10.\n"
    "Testability: A 8/10, B 3/10.\n"
    "Execution Feasibility: A 7/10, B 5/10.\n\n"
    "FINAL RANKING:\n1. Response A\n2. Response B"
)

RANKING_MISSING_RUBRIC = (
    "Response A is thorough. On Execution Feasibility, Response A wins.\n\n"
    "FINAL RANKING:\n1. Response A\n2. Response B"
)


def _conversion_operator_assignment():
    return {
        "model": "openai/gpt-4o-mini",
        "role_id": "conversion_operator",
        "role_name": "Conversion Operator",
        "mandate": "Prioritize practical experiments and execution sequence.",
        "must_include": ["Execution Plan", "Experiment Design", "Resource Assumptions"],
    }


class Stage1RepairTests(unittest.IsolatedAsyncioTestCase):
    def _failing_item(self):
        required = _conversion_operator_assignment()["must_include"] + ["Where I Disagree"]
        return {
            "model": "openai/gpt-4o-mini",
            "perspective_role_id": "conversion_operator",
            "perspective_role_name": "Conversion Operator",
            "response": PROSE_ONLY_STAGE1,
            "role_validation": council.validate_required_sections(
                PROSE_ONLY_STAGE1, required
            ),
        }

    async def test_successful_repair_replaces_response_and_records_event(self):
        item = self._failing_item()
        run_context = {}
        mock_query = AsyncMock(return_value=({"content": COMPLIANT_STAGE1}, None))
        with patch("backend.council.query_model_with_error", new=mock_query):
            await council._repair_stage1_noncompliant(
                [item], [_conversion_operator_assignment()], run_context
            )

        self.assertTrue(item["role_validation"]["valid"])
        self.assertEqual(item["response"], COMPLIANT_STAGE1)
        self.assertTrue(item.get("repaired"))
        events = run_context["repair_events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["slot"], "stage1_role")
        self.assertTrue(events[0]["success"])
        self.assertIn("Execution Plan", events[0]["missing_before"])
        # Repair prompt must show the model its own prior answer and the labels.
        repair_prompt = mock_query.call_args.args[1][0]["content"]
        self.assertIn(PROSE_ONLY_STAGE1, repair_prompt)
        self.assertIn("Where I Disagree", repair_prompt)

    async def test_failed_repair_keeps_original_and_records_failure(self):
        item = self._failing_item()
        original = item["response"]
        run_context = {}
        with patch(
            "backend.council.query_model_with_error",
            new=AsyncMock(return_value=({"content": "still just prose"}, None)),
        ):
            await council._repair_stage1_noncompliant(
                [item], [_conversion_operator_assignment()], run_context
            )

        self.assertEqual(item["response"], original)
        self.assertFalse(item["role_validation"]["valid"])
        self.assertNotIn("repaired", item)
        self.assertFalse(run_context["repair_events"][0]["success"])

    async def test_compliant_items_trigger_no_repair_call(self):
        required = _conversion_operator_assignment()["must_include"] + ["Where I Disagree"]
        item = {
            "model": "openai/gpt-4o-mini",
            "perspective_role_id": "conversion_operator",
            "response": COMPLIANT_STAGE1,
            "role_validation": council.validate_required_sections(
                COMPLIANT_STAGE1, required
            ),
        }
        mock_query = AsyncMock()
        with patch("backend.council.query_model_with_error", new=mock_query):
            await council._repair_stage1_noncompliant(
                [item], [_conversion_operator_assignment()], {}
            )
        mock_query.assert_not_called()

    async def test_repair_query_failure_is_recorded_as_unsuccessful(self):
        item = self._failing_item()
        run_context = {}
        with patch(
            "backend.council.query_model_with_error",
            new=AsyncMock(return_value=(None, "timeout")),
        ):
            await council._repair_stage1_noncompliant(
                [item], [_conversion_operator_assignment()], run_context
            )
        self.assertFalse(item["role_validation"]["valid"])
        self.assertFalse(run_context["repair_events"][0]["success"])


class Stage2RepairTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.profile = get_profile("marketing")

    def _failing_item(self):
        return {
            "model": "openai/gpt-4o-mini",
            "ranking": RANKING_MISSING_RUBRIC,
            "parsed_ranking": council.parse_ranking_from_text(RANKING_MISSING_RUBRIC),
            "rubric_coverage": council.rubric_coverage_from_text(
                RANKING_MISSING_RUBRIC, self.profile["rubric_dimensions"]
            ),
        }

    async def test_successful_repair_updates_ranking_coverage_and_parse(self):
        item = self._failing_item()
        run_context = {}
        with patch(
            "backend.council.query_model_with_error",
            new=AsyncMock(return_value=({"content": COMPLIANT_RANKING}, None)),
        ):
            await council._repair_stage2_noncompliant([item], self.profile, run_context)

        self.assertTrue(item["rubric_coverage"]["all_present"])
        self.assertEqual(item["parsed_ranking"], ["Response A", "Response B"])
        self.assertTrue(item.get("repaired"))
        event = run_context["repair_events"][0]
        self.assertEqual(event["slot"], "stage2_ranking")
        self.assertTrue(event["success"])
        self.assertIn("Strategic Clarity", event["missing_before"])

    async def test_failed_repair_keeps_original_text(self):
        item = self._failing_item()
        run_context = {}
        with patch(
            "backend.council.query_model_with_error",
            new=AsyncMock(return_value=({"content": "no labels, no ranking"}, None)),
        ):
            await council._repair_stage2_noncompliant([item], self.profile, run_context)

        self.assertEqual(item["ranking"], RANKING_MISSING_RUBRIC)
        self.assertFalse(item["rubric_coverage"]["all_present"])
        self.assertFalse(run_context["repair_events"][0]["success"])

    async def test_no_profile_means_no_repair(self):
        mock_query = AsyncMock()
        with patch("backend.council.query_model_with_error", new=mock_query):
            await council._repair_stage2_noncompliant(
                [{"model": "m", "ranking": "x", "parsed_ranking": []}], None, {}
            )
        mock_query.assert_not_called()

    async def test_compliant_ranking_triggers_no_repair(self):
        item = {
            "model": "m",
            "ranking": COMPLIANT_RANKING,
            "parsed_ranking": council.parse_ranking_from_text(COMPLIANT_RANKING),
            "rubric_coverage": council.rubric_coverage_from_text(
                COMPLIANT_RANKING, self.profile["rubric_dimensions"]
            ),
        }
        mock_query = AsyncMock()
        with patch("backend.council.query_model_with_error", new=mock_query):
            await council._repair_stage2_noncompliant([item], self.profile, {})
        mock_query.assert_not_called()


class PromptHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def test_stage1_prompt_states_verbatim_label_contract(self):
        capture = {}
        profile = get_profile("marketing")

        async def fake_query(model, messages, timeout=None):
            capture.setdefault("prompts", []).append(messages[0]["content"])
            return {"content": COMPLIANT_STAGE1}, None

        run_context = {
            "profile": profile,
            "role_assignments": [_conversion_operator_assignment()],
        }
        with patch("backend.council.query_model_with_error", new=fake_query):
            await council.stage1_collect_responses(
                "How do we grow?",
                run_context=run_context,
                council_models=["openai/gpt-4o-mini"],
            )
        prompt = capture["prompts"][0]
        self.assertIn("VERBATIM", prompt)
        self.assertIn("discarded", prompt)
        self.assertIn("Execution Plan", prompt)

    async def test_stage2_prompt_warns_about_exact_rubric_labels(self):
        capture = {}
        profile = get_profile("marketing")

        async def fake_parallel(models, messages):
            capture["prompt"] = messages[0]["content"]
            return {"m1": {"content": COMPLIANT_RANKING}}

        stage1 = [{"model": "m1", "response": "r1"}, {"model": "m2", "response": "r2"}]
        with patch("backend.council.query_models_parallel", new=fake_parallel):
            await council.stage2_collect_rankings(
                "How do we grow?",
                stage1,
                run_context={"profile": profile},
                council_models=["m1"],
            )
        self.assertIn("VERBATIM", capture["prompt"])
        self.assertIn("exact labels", capture["prompt"])
        self.assertIn("Strategic Clarity", capture["prompt"])

    async def test_stage2_repair_reaches_metadata_via_run_context(self):
        profile = get_profile("marketing")
        run_context = {"profile": profile}

        async def fake_parallel(models, messages):
            return {"m1": {"content": RANKING_MISSING_RUBRIC}}

        with patch("backend.council.query_models_parallel", new=fake_parallel), patch(
            "backend.council.query_model_with_error",
            new=AsyncMock(return_value=({"content": COMPLIANT_RANKING}, None)),
        ):
            stage2, label_to_model = await council.stage2_collect_rankings(
                "How do we grow?",
                [{"model": "m1", "response": "r1"}],
                run_context=run_context,
                council_models=["m1"],
            )

        self.assertTrue(stage2[0]["rubric_coverage"]["all_present"])
        metadata = council._build_stage2_metadata(run_context, label_to_model, [])
        self.assertEqual(len(metadata["repair_events"]), 1)
        self.assertEqual(metadata["repair_events"][0]["slot"], "stage2_ranking")


if __name__ == "__main__":
    unittest.main()
