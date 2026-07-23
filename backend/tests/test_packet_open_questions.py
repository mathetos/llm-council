"""Tests for packet open-question helpers (Phase 1 baseline lock)."""

import unittest

from backend.packet_questions import (
    packet_open_question_was_addressed,
    unresolved_packet_open_questions,
)

PACKET = {
    "packet_id": "seo-aeo-post-2025-11",
    "open_questions": [
        "Which audience and query set should this run optimize for first: classic organic SERPs, Google AI Overviews / AI Mode, ChatGPT search, Perplexity, or a defined mix?",
        "What kill criteria end a content or on-page AEO experiment (for example no Generative AI impressions or answer-engine citations after N weeks on priority prompts)?",
        "What robots.txt and WAF policy is already in place for Googlebot, Google-Extended, OAI-SearchBot, GPTBot, and PerplexityBot, and which are intentional?",
    ],
}


class AddressedRuleTests(unittest.TestCase):
    """Deterministic token-overlap rule for 'addressed'."""

    def test_close_paraphrase_is_addressed(self):
        asked = (
            "What kill criteria should end the on-page AEO experiment, for example "
            "no Generative AI impressions or answer-engine citations after several weeks?"
        )
        self.assertTrue(
            packet_open_question_was_addressed(asked, PACKET["open_questions"][1])
        )

    def test_generic_profile_question_is_not_addressed(self):
        asked = "What is the primary goal the business aims to achieve with this page?"
        for oq in PACKET["open_questions"]:
            self.assertFalse(packet_open_question_was_addressed(asked, oq))

    def test_single_shared_token_is_not_enough(self):
        asked = "Which distribution channel will drive the audience to this page?"
        # Shares only 'audience' with the first open question.
        self.assertFalse(
            packet_open_question_was_addressed(asked, PACKET["open_questions"][0])
        )

    def test_short_open_question_falls_back_to_substring(self):
        self.assertTrue(packet_open_question_was_addressed("Why now exactly?", "Why now?"))
        self.assertFalse(packet_open_question_was_addressed("What budget?", "Why now?"))


class UnresolvedListTests(unittest.TestCase):
    """Unresolved list shrinks only when a step targets an open question."""

    def test_empty_transcript_returns_all_in_order(self):
        result = unresolved_packet_open_questions(PACKET, [])
        self.assertEqual(result, PACKET["open_questions"])

    def test_addressed_question_is_removed(self):
        steps = [
            {
                "question": (
                    "Which audience and query set should we optimize for first: "
                    "classic organic SERPs, Google AI Overviews, ChatGPT search, or Perplexity?"
                ),
                "answer": "Organic first",
                "deferred": False,
            }
        ]
        result = unresolved_packet_open_questions(PACKET, steps)
        self.assertEqual(len(result), 2)
        self.assertNotIn(PACKET["open_questions"][0], result)
        self.assertEqual(result[0], PACKET["open_questions"][1])

    def test_generic_steps_remove_nothing(self):
        steps = [
            {"question": "What is your monthly budget?", "answer": "1000", "deferred": False},
            {"question": "Who signs off on the plan?", "answer": "Me", "deferred": False},
        ]
        result = unresolved_packet_open_questions(PACKET, steps)
        self.assertEqual(result, PACKET["open_questions"])

    def test_no_packet_or_no_open_questions_returns_empty(self):
        self.assertEqual(unresolved_packet_open_questions(None, []), [])
        self.assertEqual(unresolved_packet_open_questions({}, []), [])
        self.assertEqual(
            unresolved_packet_open_questions({"open_questions": []}, []), []
        )
        self.assertEqual(
            unresolved_packet_open_questions({"open_questions": ["", "   "]}, []), []
        )


if __name__ == "__main__":
    unittest.main()
