# AGENTS.md — LLM Council (Cursor / AI assistants)

Repository technical notes for **Cursor Agent** and other coding assistants. Keep this file accurate when you change architecture, ports, or data flow.

## Project overview

LLM Council is a deliberation system where multiple LLMs collaboratively answer user questions. It includes a first-message Stage 0 Interrogator to gather context, then anonymized peer review in Stage 2 to prevent models from playing favorites.

## Architecture

### Backend (`backend/`)

**`config.py`**

- `COUNCIL_MODELS` — list of OpenRouter model identifiers (must match [openrouter.ai/models](https://openrouter.ai/models) exactly)
- `CHAIRMAN_MODEL` — model for Stage 3 synthesis (defaults to a slug shared with title generation so a bad preview id does not silently break only Stage 3)
- `INTERROGATOR_MODEL` — Stage 0 model for adaptive clarification (defaults to `CHAIRMAN_MODEL` when unset)
- `INTERROGATOR_MIN_QUESTIONS` / `INTERROGATOR_MAX_QUESTIONS` — bounded Stage 0 question count (defaults: 2 / 5, validated in config)
- `COUNCIL_PROFILES` — profile guardrail contracts (marketing / product_development / business_development)
- `DEFAULT_PROFILE_ID` — default profile resolved by API and UI selector
- `GUARDRAIL_ENFORCEMENT_MODE` — guardrail gate behavior (`off`, `degraded`, `strict_fail`)
- `GUARDRAIL_*` thresholds — role/rubric/overlap/risk gate thresholds
- `OPENROUTER_API_KEY` from `.env`
- Backend runs on **port 8001** (not 8000 — avoids common conflicts)

**`openrouter.py`**

- `query_model()` — single async model query
- `query_models_parallel()` — parallel queries via `asyncio.gather()`
- Returns dict with `content` and optional `reasoning_details`
- Graceful degradation: returns `None` on failure, continues with successful responses

**`council.py`** (core logic)

- `generate_interrogator_question()` / `should_continue_interrogation()` / `summarize_interrogation()` — Stage 0 interrogator loop helpers
- `stage1_collect_responses()` — parallel queries to all council models (includes Stage 0 context when present)
- `stage2_collect_rankings()`:
  - Anonymizes responses as "Response A, B, C, …"
  - `label_to_model` mapping for de-anonymization
  - Prompts models to evaluate and rank (strict format)
  - Returns `(rankings_list, label_to_model_dict)`; each ranking has raw text and `parsed_ranking`
- `stage3_synthesize_final()` — chairman synthesizes from all responses + rankings
- `parse_ranking_from_text()` — extracts `FINAL RANKING:` section; numbered lists and plain format
- `calculate_aggregate_rankings()` — average rank position across peer evaluations
- `run_full_council()` — canonical Stage 1→2→3 orchestration used by both sync and stream endpoints; optionally emits progress events via callback while preserving one metadata/guardrail code path

**`storage.py`**

- JSON conversations in `data/conversations/`
- Each conversation: `{id, created_at, messages[]}`
- Assistant messages: `{role, stage1, stage2, stage3, interrogation?, metadata?}`
- Local research packets loaded from `data/research_packets/<profile_id>/<packet_id>.json`
- Run context, role assignments, and diagnostics are persisted in assistant `metadata`

**`main.py`**

- FastAPI, CORS for `localhost:5173` and `localhost:3000`
- Profile endpoints:
  - `GET /api/profiles`
  - `GET /api/profiles/{profile_id}/packets`
- Stage 0 endpoints:
  - `POST /api/conversations/{id}/interrogation/start`
  - `POST /api/conversations/{id}/interrogation/answer`
- First message gating: `/message` and `/message/stream` require completed interrogation payload for the first turn
- Sync and stream routes resolve run-context via shared `_resolve_message_context()` and both execute the same council orchestration logic
- POST `/api/conversations/{id}/message` returns metadata with stages
- Metadata: `label_to_model`, `aggregate_rankings`, `run_context`, `role_assignments`, `diagnostics`, `guardrail_status`

### Frontend (`frontend/src/`)

**`App.jsx`** — conversations list, current conversation, profile/packet selector state, message send, metadata in UI state

**`components/ChatInterface.jsx`** — multiline textarea (3 rows), Enter to send, Shift+Enter newline; user messages use `markdown-content`; first-message Interrogator modal stepper

**`components/Stage1.jsx`** — tabs per model; ReactMarkdown + `markdown-content`

**`components/Stage2.jsx`**

- Tabs with **raw** evaluation text per model
- De-anonymization for **display** is client-side
- "Extracted Ranking" under each evaluation; aggregate rankings with average position and vote count
- Copy explains bold model names are for readability only

**`components/Stage3.jsx`** — chairman answer; background `#f0fff0`

**Styling (`*.css`)** — light theme, primary `#4a90e2`, global `.markdown-content` in `index.css` (12px padding)

## Design decisions

### Stage 2 prompt format

1. Evaluate each response individually first  
2. `FINAL RANKING:` header  
3. Numbered list: `1. Response C`, etc.  
4. No extra text after the ranking section  

Enables reliable parsing while keeping useful evaluations.

### De-anonymization

- Models see "Response A", "Response B", …
- Backend maps to real model IDs; UI shows names in **bold** with explanation

### Stage 0 interrogation behavior

- Runs only on the first message in a conversation
- Asks one question at a time, adaptively, within min/max bounds from config
- Users can answer or defer specific aspects to the council
- Transcript + summary are injected into Stage 1 prompt context and persisted with the assistant message
- Uses selected profile + research packet to prioritize clarification questions

### Profile guardrails and packets

- Selected profile defines:
  - required context fields
  - perspective role cards for Stage 1
  - rubric dimensions for Stage 2
  - required section headings for Stage 3
- Local packet contributes:
  - facts with confidence labels
  - assumptions and constraints
  - open questions and references
- Profile/payload run context is threaded through Stage 1–3 and stored in metadata

### Errors

- Partial success: continue if some models fail  
- Do not fail the whole request for one model failure  
- Log errors; surface to user only if all models fail  

### UI transparency

- Raw outputs in tabs; parsed rankings visible for validation  

## Implementation details

### Relative imports

Backend uses relative imports (`from .config import …`). Run as `python -m backend.main` from the **project root**.

### Ports

- Backend: **`BACKEND_PORT`** in root `.env` (default **8001**) — `backend/config.py` + `uvicorn.run` in `main.py`
- Frontend API URL: built from **`VITE_API_BASE`** or **`http://localhost:$BACKEND_PORT`** — see `frontend/vite.config.js` and `frontend/src/api.js`
- CORS allows `localhost` / `127.0.0.1` on **any port** so Vite can use 5174+ if 5173 is busy
- Frontend dev server: **5173** by default (Vite)

### Markdown

Wrap ReactMarkdown output in `<div className="markdown-content">`.

### Models

Configured in `backend/config.py`. Chairman may match or differ from council members.

## Gotchas

1. **Imports** — always `python -m backend.main` from repo root, not `cd backend`  
2. **CORS** — frontend origin must match `main.py` middleware  
3. **Ranking parse** — fallback regex can pick up `Response X` patterns if format drifts  
4. **Interrogation gating** — first-message calls to `/message` require completed interrogation payload with run_context  

## Future ideas

- Council/chairman from UI  
- Streaming UX  
- Export conversations  
- Model analytics  
- Custom ranking criteria  
- Reasoning-model handling (o1-style)  

## Testing

There is no committed `test_openrouter.py` in this fork. To sanity-check OpenRouter, run the app with a valid `.env`, send one message, or add a small script that calls `query_model()` with a single cheap model id.

## Data flow

```
User Query
    → Stage 0 (first message only): Interrogator Q/A loop (2..5 by default)
    → Stage 1: parallel queries → individual responses (with Stage 0 context when present)
    → Stage 2: anonymize → parallel rankings → evaluations + parsed rankings
    → Aggregate rankings → sort by average position
    → Stage 3: chairman synthesis
    → Return { stage1, stage2, stage3, metadata }
    → Frontend: tabs + validation UI
```

Use async/parallel paths wherever possible to reduce latency.
