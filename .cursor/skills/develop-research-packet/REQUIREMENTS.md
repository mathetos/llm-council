# Develop Research Packet — Requirements

Project-local skill for **llm-council**. Not a public marketing skill.

## Runtime / paths

| Item | Requirement |
|------|-------------|
| Repo | LLM Council repo root (contains `backend/` and `data/`) |
| Packet output | `data/research_packets/<profile_id>/<packet_id>.json` |
| Source vault | `data/research_packets/_sources/<packet_id>/` (optional but preferred) |
| Profiles | Must be a valid council profile id (`marketing`, `product_development`, `business_development`) |
| Validation | `backend.storage.load_research_packet` / `_validate_packet_schema` |

## Tooling

| Tool | Required? | Notes |
|------|-----------|-------|
| Local filesystem read/write | Yes | Packet + vault |
| Backend running | No for authoring; yes for live smoke test | Port from `.env` `BACKEND_PORT` |
| NotebookLM / web research | Optional | User-directed intake |
| MCP | No | |

## Inputs the user must supply

- Decision class **or** existing `packet_id` to refresh
- Confirmation of `profile_id` when not obvious
- Research materials, URLs, NotebookLM export, or permission to gather sources

## Non-requirements

- Does not call OpenRouter
- Does not modify profile guardrails in `backend/config.py`
- Does not select the packet for an active conversation
