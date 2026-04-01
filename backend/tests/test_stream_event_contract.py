"""Contract tests for stream event sequence and payload shape."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend import main, storage


def _parse_sse_events(raw_text: str):
    events = []
    for line in raw_text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if not payload:
            continue
        events.append(json.loads(payload))
    return events


class StreamEventContractTests(unittest.TestCase):
    """Ensure streaming event names/order and metadata contract stay stable."""

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

    @staticmethod
    def _interrogation_payload():
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
                "role_assignments": [
                    {
                        "model": "m1",
                        "role_id": "systems_thinker",
                        "role_name": "Systems Thinker",
                        "mandate": "Map system interactions",
                        "must_include": ["Dependencies"],
                    }
                ],
            },
        }

    def test_stream_events_have_expected_order_and_metadata(self):
        stage1 = [
            {
                "model": "m1",
                "response": "Stage 1 response",
                "role_validation": {"valid": True, "missing": []},
            }
        ]
        stage2 = [
            {
                "model": "m2",
                "ranking": "FINAL RANKING:\n1. Response A",
                "parsed_ranking": ["Response A"],
                "rubric_coverage": {"all_present": True, "present": {}},
            }
        ]
        stage3 = {
            "model": "m3",
            "response": (
                "## Facts\nx\n## Assumptions\nx\n## Reconciliation\nx\n"
                "## Risks\n- risk\n## Recommendation\nx"
            ),
            "section_validation": {"valid": True, "missing": []},
        }

        with patch(
            "backend.main.generate_conversation_title",
            new=AsyncMock(return_value="Stream Title"),
        ), patch(
            "backend.council.stage1_collect_responses",
            new=AsyncMock(return_value=stage1),
        ), patch(
            "backend.council.stage2_collect_rankings",
            new=AsyncMock(return_value=(stage2, {"Response A": "m1"})),
        ), patch(
            "backend.council.stage3_synthesize_final",
            new=AsyncMock(return_value=stage3),
        ):
            conv = self.client.post("/api/conversations", json={}).json()
            response = self.client.post(
                f"/api/conversations/{conv['id']}/message/stream",
                json={
                    "content": "Question",
                    "interrogation": self._interrogation_payload(),
                },
            )

        self.assertEqual(response.status_code, 200)
        events = _parse_sse_events(response.text)
        event_types = [event["type"] for event in events]
        self.assertEqual(
            event_types,
            [
                "stage1_start",
                "stage1_complete",
                "stage2_start",
                "stage2_complete",
                "stage3_start",
                "stage3_complete",
                "title_complete",
                "complete",
            ],
        )

        stage2_complete = next(event for event in events if event["type"] == "stage2_complete")
        self.assertIn("metadata", stage2_complete)
        self.assertIn("run_context", stage2_complete["metadata"])
        self.assertIn("role_assignments", stage2_complete["metadata"])
        self.assertEqual(
            set(stage2_complete["metadata"]["role_assignments"][0].keys()),
            {"model", "role_id", "role_name"},
        )

        stage3_complete = next(event for event in events if event["type"] == "stage3_complete")
        self.assertIn("metadata", stage3_complete)
        self.assertIn("diagnostics", stage3_complete["metadata"])
        self.assertIn("guardrail_status", stage3_complete["metadata"])


if __name__ == "__main__":
    unittest.main()
