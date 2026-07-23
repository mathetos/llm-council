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


class PacketOpenQuestionMandateTests(unittest.IsolatedAsyncioTestCase):
    """Phase 2: interrogator prompts must prioritize unresolved packet open questions."""

    PACKET = {
        "packet_id": "seo-aeo-post-2025-11",
        "title": "SEO/AEO Packet",
        "as_of": "2026-07-01",
        "summary": "Summary",
        "facts": [{"statement": "Fact", "confidence": "high"}],
        "assumptions": [],
        "constraints": [],
        "open_questions": [
            "What kill criteria end a content or on-page AEO experiment on priority prompts?",
            "Which answer engines should this run optimize for first: AI Overviews, ChatGPT search, or Perplexity?",
        ],
        "references": [],
    }

    async def _capture_question_prompt(self, steps):
        capture = {}

        async def fake_query(model, messages, timeout=None):
            capture["prompt"] = messages[0]["content"]
            return {"content": "What is your budget?"}, None

        with patch("backend.council.query_model_with_error", new=fake_query):
            await council.generate_interrogator_question(
                "Plan our AEO push",
                steps,
                run_context={"profile": None, "research_packet": self.PACKET},
            )
        return capture["prompt"]

    async def test_question_prompt_lists_unresolved_open_questions_first(self):
        prompt = await self._capture_question_prompt([])
        self.assertIn("Unresolved research-packet open questions (HIGHEST PRIORITY)", prompt)
        self.assertIn("kill criteria", prompt)
        self.assertIn("answer engines", prompt)

    async def test_addressed_open_question_drops_out_of_prompt(self):
        steps = [
            {
                "question": (
                    "What kill criteria should end the on-page AEO experiment "
                    "on your priority prompts?"
                ),
                "answer": "No citations after 6 weeks",
                "deferred": False,
            }
        ]
        prompt = await self._capture_question_prompt(steps)
        # Inspect only the priority block; the packet context below it still
        # lists every open question by design.
        priority_block = prompt.split("Profile and packet context:")[0]
        self.assertIn("Unresolved research-packet open questions", priority_block)
        self.assertNotIn("kill criteria end a content", priority_block)
        self.assertIn("answer engines", priority_block)

    async def test_coverage_prompt_includes_unresolved_open_questions(self):
        capture = {}

        async def fake_query(model, messages, timeout=None):
            capture["prompt"] = messages[0]["content"]
            return {"content": "- goal: COVERED\nDECISION: STOP\nSUMMARY: ok"}, None

        steps = [{"question": "Q1?", "answer": "A1", "deferred": False}] * 2
        with patch("backend.council.query_model_with_error", new=fake_query):
            await council.assess_interrogation_coverage(
                "Plan our AEO push",
                steps,
                ["goal"],
                min_questions=2,
                max_questions=5,
                research_packet=self.PACKET,
            )
        self.assertIn("Unresolved research-packet open questions", capture["prompt"])
        self.assertIn("kill criteria", capture["prompt"])

    async def test_coverage_prompt_omits_block_without_packet(self):
        capture = {}

        async def fake_query(model, messages, timeout=None):
            capture["prompt"] = messages[0]["content"]
            return {"content": "- goal: COVERED\nDECISION: STOP\nSUMMARY: ok"}, None

        steps = [{"question": "Q1?", "answer": "A1", "deferred": False}] * 2
        with patch("backend.council.query_model_with_error", new=fake_query):
            await council.assess_interrogation_coverage(
                "Plan our AEO push",
                steps,
                ["goal"],
                min_questions=2,
                max_questions=5,
            )
        self.assertNotIn("Unresolved research-packet open questions", capture["prompt"])

    def test_stage1_context_calls_out_unresolved_packet_questions(self):
        interrogation = {
            "completed": True,
            "summary": "- Goal: AEO visibility",
            "steps": [{"question": "Q?", "answer": "A", "deferred": False}],
            "packet_open_questions": {
                "total": 2,
                "addressed": [self.PACKET["open_questions"][0]],
                "unresolved": [self.PACKET["open_questions"][1]],
            },
        }
        context = council.format_interrogation_context(interrogation)
        self.assertIn("Unresolved Research-Packet Open Questions", context)
        self.assertIn("answer engines", context)
        self.assertNotIn("kill criteria", context)

    def test_build_interrogation_payload_tracks_packet_open_questions(self):
        session = {
            "conversation_id": "c1",
            "model": "test/model",
            "model_pairing_id": "premium",
            "model_resolution": {},
            "profile_id": "marketing",
            "profile_name": "Marketing Council",
            "packet_id": self.PACKET["packet_id"],
            "packet_title": self.PACKET["title"],
            "packet_as_of": self.PACKET["as_of"],
            "research_packet": self.PACKET,
            "min_questions": 2,
            "max_questions": 5,
            "summary": "- s",
            "steps": [
                {
                    "question": (
                        "What kill criteria should end the on-page AEO experiment "
                        "on your priority prompts?"
                    ),
                    "answer": "No citations after 6 weeks",
                    "deferred": False,
                },
                {"question": "What is your budget?", "answer": "1000", "deferred": False},
            ],
        }
        payload = main._build_interrogation_payload(session)
        tracking = payload["packet_open_questions"]
        self.assertEqual(tracking["total"], 2)
        self.assertEqual(tracking["addressed"], [self.PACKET["open_questions"][0]])
        self.assertEqual(tracking["unresolved"], [self.PACKET["open_questions"][1]])


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
        ask_next_assessment = {
            "coverage": {"fields": {}, "coverage_ratio": 0.4},
            "decision": "ask_next",
            "next_question": None,
            "confirmation_summary": None,
            "error": None,
        }
        stop_assessment = {
            "coverage": {"fields": {}, "coverage_ratio": 0.9},
            "decision": "stop_sufficient",
            "next_question": None,
            "confirmation_summary": None,
            "error": None,
        }
        with patch(
            "backend.main.generate_interrogator_question",
            new=AsyncMock(side_effect=[("Q1?", None), ("Q2?", None)]),
        ), patch(
            "backend.main.assess_interrogation_coverage",
            new=AsyncMock(side_effect=[ask_next_assessment, stop_assessment]),
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
