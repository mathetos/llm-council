---
name: Develop-Research-Packet
description: >
  Use when developing a research packet, building a council evidence brief,
  distilling NotebookLM sources into a packet, refreshing an existing packet,
  or turning scraped .md source notes into LLM Council JSON grounding.
  Produces a decision-class packet shaped for how Stage 0/1/3 consume context.
version: 0.1.0
---

# Develop Research Packet

Build **decision-class** research packets for LLM Council: shared priors the Interrogator, Stage 1 roles, and Stage 3 Evidence Used can actually use. Same process every run; packet content varies by decision class.

**Force-load:** ask for `Develop-Research-Packet` / develop research packet by name.

## Purpose

Compress research into `data/research_packets/<profile_id>/<packet_id>.json` so council runs stay grounded without stuffing a case file into the packet.

## Not this skill

- Choosing which packet to attach to a live run (product/UX question)
- Writing the user query or running the council
- Building profile guardrails (roles, rubrics, Stage 3 sections)
- Dumping NotebookLM output unchanged into JSON

## Input policy

- **Decision class** (or existing `packet_id` to refresh) — from the user. Ask once if missing.
- **Profile id** — from the user; default `marketing` only if they agree.
- **Research intake** — NotebookLM export, URLs, or local source notes the user provides or asks you to gather. Do not invent sources.
- **Case-specific client facts** — belong in the user query / interrogation, not in reusable packet facts, unless the user explicitly wants a product-specific packet.

## Branches

| Branch | Use when |
|--------|----------|
| **create** | New `packet_id`; no packet file yet |
| **refresh** | Existing packet; bump evidence / `as_of` |
| **distill** | Source vault already exists; produce or rewrite JSON only |

## Quick start

1. Confirm branch + decision class + `profile_id` + `packet_id`.
2. Follow Steps 1–8 for that branch (skip intake on **distill** if vault is ready; skip vault rebuild on **refresh** if sources are already filed).
3. Write JSON to `data/research_packets/<profile_id>/<packet_id>.json`.
4. Meet Done definition.

## Steps

### 1. Decision brief

Write and confirm with the user:

- One-sentence **decision class**
- 5–10 **in-scope questions** this packet should sharpen
- **Out-of-scope** questions (other packets)
- `profile_id`, `packet_id` (stable slug), working title

**Completion criterion:** decision class is one sentence; in-scope and out-of-scope lists exist; ids are agreed.

### 2. Research intake

Run or accept decision-shaped research (NotebookLM or equivalent). Prefer evidence for decide/kill/metric patterns over topic encyclopedias.

**Completion criterion:** source list exists with URLs (or explicit “no URL / primary note” labels); each source marked for relevance to the decision class.

### 3. Source vault

Store notes under:

`data/research_packets/_sources/<packet_id>/`

One `.md` per source (or one file with clear source headers). Capture URL, accessed date, 3–7 extractable claims, evidence strength, relevance.

Template: see `REFERENCE.md` § Source note template.

**Completion criterion:** every intake source used for distillation has a vault note; no full-article paste planned for the JSON.

### 4. Triage

Force every candidate claim into exactly one bucket: **fact**, **assumption**, **constraint**, **open_question**, or **discard**.

Apply the triage rubric in `REFERENCE.md`. Confidence for facts: `high` | `medium` | `low`.

**Completion criterion:** every kept claim has one bucket; every fact has confidence; discards are not smuggled into `summary`.

### 5. Compress for prompt injection

Write council-sized fields (targets in `REFERENCE.md` § Size targets). Put provenance on each fact’s `source` when a URL exists. Keep `references[]` as the human index (not model context today).

**Completion criterion:** fact count and list sizes within targets unless user explicitly waives; each fact is one citable sentence; Stage 3 could quote a fact without rewriting it.

### 6. Align open questions

Shape `open_questions` to pull Interrogator toward decision-critical gaps (and Marketing profile fields when `profile_id` is `marketing`: audience, goal, offer, channel, constraints).

**Completion criterion:** no generic textbook questions; each open question would change the Decision Contract if answered.

### 7. Write and validate JSON

Emit the schema in `REFERENCE.md` § Packet schema. Path:

`data/research_packets/<profile_id>/<packet_id>.json`

Validate with the project contract (keys, non-empty facts, confidence enum, profile_id match). Prefer loading via backend validation or the check in `REFERENCE.md` § Validate.

**Completion criterion:** file exists at the correct path; schema validation passes; `as_of` is set (ISO date).

### 8. Smoke test guidance

Tell the user how to verify (do not invent a full council run unless asked):

1. Start interrogation with a short prompt in this decision class and this packet selected.
2. Confirm questions feel packet-informed.
3. After one council run, check Stage 3 **Evidence Used** for cited packet facts with confidence labels.

**Completion criterion:** smoke-test steps are stated; known packet risks (vague facts, off-decision noise) called out if present.

## Done definition

- [ ] Branch identified (create / refresh / distill)
- [ ] Decision brief complete (class, in/out scope, ids)
- [ ] Source vault updated for sources used
- [ ] Triage applied; facts have confidence (+ `source` when URL exists)
- [ ] Sizes within targets (or waiver noted)
- [ ] JSON written under `data/research_packets/<profile_id>/<packet_id>.json`
- [ ] Schema validation passes
- [ ] Smoke-test guidance given
- [ ] Packet remains a **decision-class** brief, not a single-run case file (unless user requested product-specific)

## Context pointers

- Council consumption, schema, triage, size targets, validate command → `REFERENCE.md`
- Fictional worked example → `EXAMPLES.md`
- Runtime paths / tooling → `REQUIREMENTS.md`
