# Develop Research Packet — Reference

SSOT for schema, council consumption, triage, and size targets. Keep `SKILL.md` lean.

## How the council consumes packets

| Stage | Sees packet? | How it uses it |
|-------|--------------|----------------|
| Stage 0 Interrogator | Yes | Steers clarifying questions; `open_questions` and `constraints` matter most |
| Stage 1 roles | Yes | Shared grounding; instructed to separate facts vs assumptions |
| Stage 2 rankings | **No** | Profile rubric only |
| Stage 3 Chairman | Yes | Marketing **Evidence Used** must cite packet facts with confidence vs assumptions |

`format_research_packet_context` injects: title, `as_of`, `summary`, `facts` (with confidence + optional `source`), `assumptions`, `constraints`, `open_questions`.

**`references[]` is not injected into model prompts.** It is a human provenance index. Put URLs on fact `source` when models should see them.

## Packet schema

Path: `data/research_packets/<profile_id>/<packet_id>.json`

Required keys (backend `_validate_packet_schema`):

| Key | Type | Rules |
|-----|------|-------|
| `packet_id` | string | Matches filename stem |
| `profile_id` | string | Must match folder name |
| `title` | string | Human label |
| `as_of` | string | ISO date preferred (`YYYY-MM-DD`) |
| `summary` | string | 2–4 sentences: decision scope + in/out |
| `facts` | object[] | **Non-empty**; each needs `statement`, `confidence` |
| `assumptions` | string[] | Working beliefs for this decision class |
| `constraints` | string[] | Hard rails on recommendations |
| `open_questions` | string[] | Interrogator seed bank |
| `references` | string[] | Canonical URLs / citations for humans |

Fact object:

| Field | Required | Notes |
|-------|----------|-------|
| `statement` | yes | One atomic, citable claim |
| `confidence` | yes | `high` \| `medium` \| `low` only |
| `source` | no | URL shown to models; prefer when available |

### Blank template

```json
{
  "packet_id": "example-decision-class",
  "profile_id": "marketing",
  "title": "Example decision-class packet",
  "as_of": "2026-07-23",
  "summary": "Scope sentence. What this packet is for. What it is not for.",
  "facts": [
    {
      "statement": "One falsifiable claim relevant to the decision class.",
      "confidence": "medium",
      "source": "https://example.com/source"
    }
  ],
  "assumptions": [
    "Working belief for this decision class."
  ],
  "constraints": [
    "Hard limit on feasible recommendations."
  ],
  "open_questions": [
    "Question whose answer would change the Decision Contract."
  ],
  "references": [
    "https://example.com/source"
  ]
}
```

## Field jobs (write for the job)

| Field | Job |
|-------|-----|
| `summary` | Instant “what decision world is this?” |
| `facts` | Citable grounding for Stage 1 + Stage 3 Evidence Used |
| `assumptions` | Beliefs the council may use but must label |
| `constraints` | Bounds on recommendations |
| `open_questions` | Seed high-value Interrogator questions |
| `references` | Human audit trail |

If a line cannot do one of these jobs, discard it.

## Triage rubric

For each candidate claim from the vault:

| Bucket | Put it here when… |
|--------|-------------------|
| **fact** | External support exists; chairman could cite it under Evidence Used |
| **assumption** | Working belief for the decision class; not firmly evidenced |
| **constraint** | Limits what recommendations are allowed |
| **open_question** | User/run must resolve or explicitly defer |
| **discard** | Interesting but unused by Stage 0/1/3 |

### Confidence

| Level | Use when |
|-------|----------|
| `high` | Multiple solid sources or strong primary evidence |
| `medium` | Credible single source or strong industry pattern |
| `low` | Thin, dated, or contested — keep only if load-bearing |

Prefer deleting low-confidence noise over padding `facts`.

### Decision-class vs case file

| Reusable packet fact | Run-specific (query / interrogation) |
|----------------------|--------------------------------------|
| “Pricing transparency is a common gap on WP support plan SERPs.” | “Vendor X’s managed plan is $169/mo.” |
| “Zero-authority domains cannot buy rankings overnight.” | “Current organic traffic is ~0.” |

Product-specific packets are allowed when the user explicitly wants them (e.g. one launch). Mark that in `summary`.

## Size targets

| Field | Target | Soft max |
|-------|--------|----------|
| `facts` | 8–15 | 20 |
| `assumptions` | 5–10 | 12 |
| `constraints` | 5–10 | 12 |
| `open_questions` | 5–10 | 12 |
| `summary` | 2–4 sentences | 6 sentences |

Waive only with user approval; note waiver in the closeout message.

## Source note template

File: `data/research_packets/_sources/<packet_id>/<short-slug>.md`

```markdown
# <Source title>

- URL: https://example.com/...
- Accessed: YYYY-MM-DD
- Relevance to decision class: high | medium | low

## Extractable claims

1. Claim… (evidence | inference | anecdote)
2. Claim…

## Notes

Optional caveats, date sensitivity, contradictions with other sources.
```

## Validate

From repo root, after writing the JSON:

```bash
python -c "from backend.storage import load_research_packet; p=load_research_packet('PROFILE_ID','PACKET_ID'); print(p['packet_id'], len(p['facts']), 'facts OK')"
```

Replace `PROFILE_ID` and `PACKET_ID`. Success prints the id and fact count. Failure raises `ValueError` with the schema problem.

Optional: list packets for a profile via API `GET /api/profiles/{profile_id}/packets` when the backend is running.

## Marketing open-question alignment

When `profile_id` is `marketing`, prefer open questions that expose gaps in:

- target audience
- goal / metric
- offer or value prop
- distribution channel
- constraints
- kill criteria / first experiment design

Avoid questions already answered by a typical user paste for that decision class.
