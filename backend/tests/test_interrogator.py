"""Tests for Interrogator Stage 0 flow and contracts."""

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend import council, main, storage


class ConfigBoundsTests(unittest.TestCase):
    """Validate interrogator config bounds behavior."""

    def test_invalid_min_max_falls_back_to_defaults(self):
        with patch.dict(
            os.environ,
            {
                "INTERROGATOR_MIN_QUESTIONS": "9",
                "INTERROGATOR_MAX_QUESTIONS": "3",
            },
            clear=False,
        ):
            cfg = importlib.import_module("backend.config")
            cfg = importlib.reload(cfg)
            self.assertEqual(cfg.INTERROGATOR_MIN_QUESTIONS, 2)
            self.assertEqual(cfg.INTERROGATOR_MAX_QUESTIONS, 5)


class InterrogatorLogicTests(unittest.IsolatedAsyncioTestCase):
    """Test bounded continuation and prompt integration logic."""

    async def test_should_continue_bounds_and_model_decision(self):
        steps = [{"question": "Q1?", "answer": "A1", "deferred": False}]
        should_continue, _ = await council.should_continue_interrogation(
            "Query",
            steps,
            min_questions=2,
            max_questions=5,
        )
        self.assertTrue(should_continue, "Must continue before min questions are reached")

        steps = [{"question": "Q1", "answer": "A1", "deferred": False}] * 5
        should_continue, _ = await council.should_continue_interrogation(
            "Query",
            steps,
            min_questions=2,
            max_questions=5,
        )
        self.assertFalse(should_continue, "Must stop at max questions")

        with patch(
            "backend.council.query_model_with_error",
            new=AsyncMock(return_value=({"content": "ASK_NEXT"}, None)),
        ):
            steps = [{"question": "Q1", "answer": "A1", "deferred": False}] * 2
            should_continue, _ = await council.should_continue_interrogation(
                "Query",
                steps,
                min_questions=2,
                max_questions=5,
            )
            self.assertTrue(should_continue)

        with patch(
            "backend.council.query_model_with_error",
            new=AsyncMock(return_value=({"content": "STOP"}, None)),
        ):
            steps = [{"question": "Q1", "answer": "A1", "deferred": False}] * 2
            should_continue, _ = await council.should_continue_interrogation(
                "Query",
                steps,
                min_questions=2,
                max_questions=5,
            )
            self.assertFalse(should_continue)

    async def test_stage1_prompt_includes_interrogation_context(self):
        capture = {}

        async def fake_parallel(models, messages):
            capture["messages"] = messages
            return {"fake/model": {"content": "answer", "reasoning_details": None}}

        interrogation = {
            "completed": True,
            "summary": "- Goal: improve onboarding conversion",
            "steps": [
                {
                    "question": "Who is the audience?",
                    "answer": "B2B founders",
                    "deferred": False,
                }
            ],
        }

        with patch("backend.council.query_models_parallel", new=fake_parallel):
            results = await council.stage1_collect_responses(
                "How do I improve retention?",
                interrogation=interrogation,
            )

        self.assertEqual(len(results), 1)
        sent_prompt = capture["messages"][0]["content"]
        self.assertIn("Interrogator Summary", sent_prompt)
        self.assertIn("B2B founders", sent_prompt)
        self.assertIn("Original Query", sent_prompt)


class InterrogatorApiTests(unittest.TestCase):
    """API-level tests for first-message gating and interrogation flow."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name) / "conversations"
        self.verdicts_dir = Path(self.temp_dir.name) / "verdicts"
        self.research_dir = Path(self.temp_dir.name) / "research_packets"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.verdicts_dir.mkdir(parents=True, exist_ok=True)
        (self.research_dir / "marketing").mkdir(parents=True, exist_ok=True)
        (self.research_dir / "marketing" / "default.json").write_text(
            """
{
  "packet_id": "default",
  "profile_id": "marketing",
  "title": "Test Packet",
  "as_of": "2026-03-31",
  "summary": "Summary",
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

    def test_interrogation_start_answer_done_flow(self):
        with patch(
            "backend.main.generate_interrogator_question",
            new=AsyncMock(side_effect=[("Q1?", None), ("Q2?", None)]),
        ), patch(
            "backend.main.should_continue_interrogation",
            new=AsyncMock(side_effect=[(True, None), (False, None)]),
        ), patch(
            "backend.main.summarize_interrogation",
            new=AsyncMock(return_value="- Summary bullet"),
        ):
            conv = self.client.post("/api/conversations", json={}).json()
            conv_id = conv["id"]

            started = self.client.post(
                f"/api/conversations/{conv_id}/interrogation/start",
                json={
                    "content": "Help me plan a launch",
                    "profile_id": "marketing",
                    "packet_id": "default",
                },
            )
            self.assertEqual(started.status_code, 200)
            session_id = started.json()["session_id"]
            self.assertEqual(started.json()["question"], "Q1?")
            self.assertEqual(started.json()["profile_id"], "marketing")
            self.assertEqual(started.json()["packet_id"], "default")

            answer1 = self.client.post(
                f"/api/conversations/{conv_id}/interrogation/answer",
                json={"session_id": session_id, "answer": "B2B audience"},
            )
            self.assertEqual(answer1.status_code, 200)
            self.assertFalse(answer1.json()["done"])
            self.assertEqual(answer1.json()["question"], "Q2?")

            answer2 = self.client.post(
                f"/api/conversations/{conv_id}/interrogation/answer",
                json={"session_id": session_id, "answer": "__DEFER_TO_COUNCIL__"},
            )
            self.assertEqual(answer2.status_code, 200)
            self.assertTrue(answer2.json()["done"])
            steps = answer2.json()["interrogation"]["steps"]
            self.assertTrue(steps[-1]["deferred"])
            self.assertIn("run_context", answer2.json()["interrogation"])

    def test_first_message_requires_interrogation_but_second_message_does_not(self):
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

            missing = self.client.post(
                f"/api/conversations/{conv_id}/message",
                json={"content": "First message without interrogation"},
            )
            self.assertEqual(missing.status_code, 400)

            ok_first = self.client.post(
                f"/api/conversations/{conv_id}/message",
                json={
                    "content": "First message with interrogation",
                    "interrogation": {
                        "completed": True,
                        "steps": [{"question": "Q1", "answer": "A1", "deferred": False}],
                        "summary": "- s",
                        "model": "test",
                        "min_questions": 2,
                        "max_questions": 5,
                        "questions_asked": 1,
                        "run_context": {
                            "profile_id": "marketing",
                            "profile": {
                                "id": "marketing",
                                "name": "Marketing Council",
                                "description": "x",
                                "required_context_fields": ["goal"],
                                "rubric_dimensions": [{"id": "r", "label": "R", "description": "d"}],
                                "perspective_roles": [
                                    {
                                        "id": "p",
                                        "name": "P",
                                        "mandate": "m",
                                        "must_include": ["Dependencies"],
                                    }
                                ],
                                "stage3_required_sections": ["Facts"],
                            },
                            "packet_id": "default",
                            "packet_title": "Test Packet",
                            "packet_as_of": "2026-03-31",
                            "research_packet": {
                                "packet_id": "default",
                                "profile_id": "marketing",
                                "title": "Test Packet",
                                "as_of": "2026-03-31",
                                "summary": "Summary",
                                "facts": [{"statement": "Fact", "confidence": "high"}],
                                "assumptions": ["A1"],
                                "constraints": ["C1"],
                                "open_questions": ["Q1"],
                                "references": ["R1"],
                            },
                            "role_assignments": [],
                        },
                    },
                },
            )
            self.assertEqual(ok_first.status_code, 200)

            ok_second = self.client.post(
                f"/api/conversations/{conv_id}/message",
                json={"content": "Second message no interrogation"},
            )
            self.assertEqual(ok_second.status_code, 200)


class VerdictExportTests(unittest.TestCase):
    """Ensure markdown export includes interrogation details when available."""

    def test_verdict_markdown_contains_interrogation_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage.VERDICTS_DIR = str(Path(tmp) / "verdicts")
            conversation = {"id": "abc-123", "title": "Launch Plan"}
            stage3 = {"model": "openai/gpt-4o-mini", "response": "Final answer"}
            interrogation = {
                "model": "anthropic/claude-sonnet-4.6",
                "min_questions": 2,
                "max_questions": 5,
                "questions_asked": 2,
                "summary": "- Need timeline clarity",
                "steps": [
                    {"question": "Timeline?", "answer": "6 weeks", "deferred": False},
                    {"question": "Budget?", "answer": "Deferred to council", "deferred": True},
                ],
            }

            result = storage.save_verdict_markdown(
                conversation,
                stage3,
                interrogation=interrogation,
            )
            saved = Path(result["path"]).read_text(encoding="utf-8")
            self.assertIn("## Interrogation Context", saved)
            self.assertIn("Deferred to council", saved)
            self.assertIn("## Final Council Answer", saved)


if __name__ == "__main__":
    unittest.main()
