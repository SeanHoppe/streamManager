# StreamManager

Governance + adaptive-learning bridge between Claude Desktop sub-agent orchestration and a Claude CLI executor. SM acts as the **project manager layer** — reading all project `*.md` files, governing per-agent scope, and enforcing plan alignment and cadence across the full development pipeline.

**Status:** POC hardened (99 tests, soak PASS). Requirements v1.1 — agent registry and orchestration governance scoped.

## What SM does

- **Reads full project context** — all `*.md` files from the Desktop project repo (INTENT, REQUIREMENTS, CLAUDE, todos, plans); refreshes mid-session on file change
- **Discovers sub-agents** — hybrid identification: explicit message metadata + pattern inference via L0→L4 decision graph
- **Governs per agent role** — reviewer scope ≠ developer scope; each agent governed independently, no cross-agent gating
- **Enforces plan alignment** — orchestration prompts evaluated against stated requirements and current goals, not just safety
- **Tracks cadence** — emits warnings when a session stalls or drifts from plan

## Architecture

```
Claude Desktop Orchestration (Prompt Constructor, Developer, Reviewer, Tester, ...)
                    │ ws://localhost:8765
               Stream Manager
               ├─ Project Context (all *.md, live refresh)
               ├─ Agent Registry (metadata + pattern inference)
               ├─ Orchestration Governance (alignment + cadence)
               └─ Governance Engine + Decision Graph (L0→L4)
                    │ ws://localhost:8766
               Claude CLI (executor)
```

## Documents

- [REQUIREMENTS.md](REQUIREMENTS.md) — full PRD/RFC/ADR (v1.1, 2026-05-01)
- [INTENT.md](INTENT.md) — governance intent and safety priorities
- [POC_FINDINGS.md](POC_FINDINGS.md) — findings from hardening phase
- [INITIAL_PLAN.md](INITIAL_PLAN.md) — original framework skeleton

## Monitoring

```bash
pip install -r dashboard/requirements.txt
uvicorn dashboard.server:app --port 8765 --reload
# open http://localhost:8765  (3 visual themes: Obsidian / Phosphor / Paper)
```

## Tools

```bash
# Real-CLI soak (replays transcript, validates parse-success + p95 latency)
BRIDGE_API_GOV=true python tools/cli_soak.py --transcript <path>.jsonl --intent .

# Governance hook (PreToolUse — wired via .claude/settings.json)
python tools/hook_evaluate.py
```
