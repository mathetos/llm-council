# LLM Council

This idea is forked from [karpathy/llm-council](https://github.com/karpathy/llm-council).

This project helps you pressure-test important questions with a small "AI advisory group" instead of trusting one model's first take.

## Prerequisites

Before using this project, make sure you have:

- **Cursor with AI chat access** (using Claude in Cursor works great for day-to-day edits and prompt iteration)
- **An OpenRouter account + API key** with available credits
- **Model access in OpenRouter** for the model IDs configured in this repo

You will place your OpenRouter key in `.env` as `OPENROUTER_API_KEY`.

## Why this is useful

If you've ever thought "this answer sounds good, but I don't totally trust it yet," this setup is for that exact moment.

Instead of one polished response, you get a full decision flow:

- independent first takes from multiple models
- anonymous peer critique (so they judge ideas, not model brands)
- one final synthesis that weighs both arguments and objections

The payoff is usually:

- fewer blind spots
- clearer tradeoffs
- better confidence before you commit to a plan

## How this version is scoped

This version is tuned for real-world decision work where context and consistency matter:

- an opening "interrogation" step to help refine the problem you are trying to solve so the council has enough context to give accurate responses
- profile-based roles and rubrics so output matches your use case
- optional research packets to ground the discussion
- guardrail status you can actually see per run
- save your verdicts as markdown locally or re-run the same question with different models

## What this project includes

### Four-stage workflow

1. **Interrogator (Stage 0)** asks a few context questions on a new thread (default 2-5) so the council does not guess your intent.
2. **Stage 1** collects independent responses in parallel.
3. **Stage 2** anonymizes responses, then models critique and rank them.
4. **Stage 3** produces one final council answer.

### Profile-driven guidance

Runs can be shaped by a profile:

- `marketing`
- `product_development`
- `business_development`

Profiles keep things focused. They define perspective roles, evaluation rubrics, and output structure so the council stays aligned with the actual job you're trying to do.

### Research packets

Research packets are optional context packs you can attach per profile. They give the council shared grounding up front (facts, assumptions, constraints, open questions, references) before deliberation starts.

### Guardrail status

Each run emits guardrail status and diagnostics:

- `pass`
- `degraded`
- `fail` (when strict mode is enabled)

This gives you a quick quality signal instead of having to guess how disciplined the run was.

### Practical UX additions

- save final answers as markdown verdict files
- per-conversation deletion from sidebar history
- settings modal for model pairing choices
- shared orchestration path for sync and stream endpoints (same stage/metadata behavior)

## Setup

If you just want to use the app, you mainly need a valid OpenRouter key and one command to start.

### 1) Install dependencies

Backend (Python):

```bash
uv sync
```

Frontend (Node):

```bash
cd frontend
npm install
cd ..
```

### 2) Configure environment

Create `.env` in the project root:

```bash
OPENROUTER_API_KEY=sk-or-v1-...
BACKEND_PORT=8001
```

Get your key from [openrouter.ai](https://openrouter.ai/).

## Run the app

Default URLs:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8001`

Start both together (recommended):

```bash
npm run start
```

Or run separately:

Backend:

```bash
npm run server
```

Frontend:

```bash
npm run dev
```

## Configuration details

Edit `backend/config.py` (or env vars) to control:

- council model list
- chairman model
- interrogator model and min/max question bounds
- profile defaults
- guardrail enforcement mode and thresholds

Key settings include:

```python
COUNCIL_MODELS = [
    "google/gemini-3.1-flash-lite-preview",
    "anthropic/claude-sonnet-4.6",
    "openai/gpt-4o-mini",
]

CHAIRMAN_MODEL = "google/gemini-2.5-flash"
INTERROGATOR_MIN_QUESTIONS = 2
INTERROGATOR_MAX_QUESTIONS = 5
DEFAULT_PROFILE_ID = "marketing"
GUARDRAIL_ENFORCEMENT_MODE = "degraded"  # off | degraded | strict_fail
```

## Research packet format

How these packets were created:

- We started with source notes and research intake for each domain (for example, marketing context from NotebookLM-assisted synthesis and working notes).
- Then we distilled that into a standard JSON shape so every run gets consistent, structured context.
- We split information by type on purpose: facts, assumptions, constraints, open questions, and references.
- Think of packets as living context docs: update them as your market, product, or strategy evolves.

Packet path pattern:

```text
data/research_packets/<profile_id>/<packet_id>.json
```

Required fields:

- `packet_id`, `profile_id`, `title`, `as_of`, `summary`
- `facts` (non-empty; each fact has `statement` and `confidence` of `high|medium|low`)
- `assumptions`, `constraints`, `open_questions`, `references` (lists)

## Developer notes

- Run backend from project root as: `python -m backend.main`
- Backend default port is `8001`
- Frontend API base resolves via `VITE_API_BASE` or backend port fallback
- Sync and stream message routes share the same orchestration path
- Architecture details and contributor guidance live in `AGENTS.md`

## Troubleshooting

- `ERR_CONNECTION_REFUSED`: backend is down or port mismatch
- Port in use: change `BACKEND_PORT` in `.env` and restart
- Missing model responses: verify OpenRouter credits and model IDs
