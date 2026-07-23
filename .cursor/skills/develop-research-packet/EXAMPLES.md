# Develop Research Packet — Examples

Fictional only (`example.com`). Do not copy these claims into real packets without fresh sources.

## Worked example: create `seo-aeo-commercial-page`

### Decision brief

- **Decision class:** Whether to publish a high-intent commercial plan page on a low-authority domain, and what “good enough to ship” means.
- **In-scope:** SERP patterns for plan/pricing pages, content deltas buyers expect, AEO/FAQ blocks, authority constraints, MVP vs full page, conversion proxies.
- **Out-of-scope:** Always-on brand content calendars; generic paid social creative; unrelated product roadmap.
- **profile_id:** `marketing`
- **packet_id:** `seo-aeo-commercial-page`

### Sample vault note

`data/research_packets/_sources/seo-aeo-commercial-page/serp-plan-pages.md`

```markdown
# Plan-page SERP patterns (fictional note)

- URL: https://example.com/research/support-plan-serps
- Accessed: 2026-07-23
- Relevance to decision class: high

## Extractable claims

1. Ranking URLs for commercial “support plans” queries are often plan/pricing pages, not soft brand blogs. (evidence)
2. Buyers expect visible pricing, inclusions/exclusions, and who each plan is for. (inference)
3. Domain authority still bounds how fast a new site can compete on competitive commercial terms. (evidence)

## Notes

Treat vendor blogs as medium confidence unless methodology is clear.
```

### Triage sketch

| Claim | Bucket | Confidence |
|-------|--------|------------|
| Commercial SERPs skew to plan/pricing pages | fact | high |
| Pricing transparency is a common content gap | fact | medium |
| Zero authority cannot be manufactured by copy alone | fact | high |
| Organic page before paid search for this class | assumption | — |
| Recommendations must not assume net-new domain authority | constraint | — |
| What booked-call rate kills the page bet? | open_question | — |
| History of Google’s 2011 Panda update | discard | — |

### Resulting packet (abridged)

```json
{
  "packet_id": "seo-aeo-commercial-page",
  "profile_id": "marketing",
  "title": "SEO/AEO commercial page bets (low-authority domains)",
  "as_of": "2026-07-23",
  "summary": "Grounds council runs that decide whether to ship a high-intent commercial plan/pricing page and what minimum on-page proof is required. Not for always-on thought-leadership calendars or paid social creative systems.",
  "facts": [
    {
      "statement": "For commercial ‘support plans’ style queries, ranking results are frequently plan or pricing pages rather than soft brand blog posts.",
      "confidence": "high",
      "source": "https://example.com/research/support-plan-serps"
    },
    {
      "statement": "Buyers evaluating support plans commonly expect published prices, inclusions versus exclusions, and clear use-case segmentation.",
      "confidence": "medium",
      "source": "https://example.com/research/support-plan-serps"
    },
    {
      "statement": "Strong on-page information gain does not remove domain-authority constraints on competitive commercial queries.",
      "confidence": "high",
      "source": "https://example.com/research/support-plan-serps"
    }
  ],
  "assumptions": [
    "For this decision class, a focused commercial page is evaluated before broad top-of-funnel content expansion.",
    "Qualified lead definitions should tie to sales actions (for example booked calls), not only clicks."
  ],
  "constraints": [
    "Do not recommend strategies that require manufacturing domain authority in a short window.",
    "MVP publish criteria must be explicit; ‘full delta’ pages need a separate resource plan."
  ],
  "open_questions": [
    "What primary metric and baseline define success for the commercial page in the next 60 days?",
    "What on-page proof is mandatory before the primary CTA?",
    "Is authority the binding constraint, or is message/offer clarity the blocker?",
    "What kill criteria stop further investment after publish?"
  ],
  "references": [
    "https://example.com/research/support-plan-serps"
  ]
}
```

### Smoke-test expectation

Interrogator should ask about metric, ICP, proof before CTA, and resources/timeline — not generic “what is SEO?” Stage 3 Evidence Used should quote packet facts with `[high]` / `[medium]` style confidence, not only narrative vibes.

## Refresh branch (pattern)

1. Keep `packet_id` stable.
2. Add vault notes for new sources.
3. Re-triage; demote or delete stale facts.
4. Bump `as_of`.
5. Re-validate schema.

## Distill branch (pattern)

User already has `_sources/<packet_id>/`. Skip intake. Start at triage → compress → write JSON → validate.
