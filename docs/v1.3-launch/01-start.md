# 01 — Start

Bring up the v1.3 surface locally. Sanity check it answers requests at all before spending model quota on M1/M2/M3.

## Prereqs

- Python venv with project deps installed (`pip install -e .` or equivalent)
- Dashboard deps: `pip install -r dashboard/requirements.txt`
- `claude` CLI on `$PATH` (governance escalation uses it via subprocess — see memory `feedback_cli_over_sdk.md`)
- Working dir: `C:\Users\SeanHoppe\VS\streamManager`
- Existing bus DB at `.claude/gov.db` (already present)

## Components to start

| Component | Purpose | Default port |
|---|---|---|
| Dashboard server (FastAPI + SSE) | Live session pane, lifecycle pane, HITL queue, beacon pane | 8765 |
| Governance hook (PreToolUse) | Wired via `.claude/settings.json` — fires on Desktop tool use | n/a (subprocess) |
| `desktop_command_consumer` | SSE consumer for `desktop_command` envelopes | n/a |
| Learn Mode categorizer worker | Out-of-band Sonnet worker (P5c) | n/a |

## Step 1 — start dashboard

```bash
cd C:/Users/SeanHoppe/VS/streamManager
pip install -r dashboard/requirements.txt   # one-time
GOV_DB=.claude/gov.db uvicorn dashboard.server:app --port 8765 --reload
```

Open `http://localhost:8765`. Three themes (Obsidian / Phosphor / Paper). Confirm:

- Sessions list populates from `.claude/gov.db`
- Lifecycle pane (`/api/lifecycle/jobs`) responds (Task C surface)
- HITL queue pane responds
- Bias-hint badge renders on HITL rows when present (v1.3 C9+C10 — PR #70 at `51b6284`)

## Step 2 — verify governance hook is wired

Hook config lives in `.claude/settings.json`. Confirm `PreToolUse` references `tools/hook_evaluate.py`:

```bash
cat .claude/settings.json | python -m json.tool | grep -A3 PreToolUse
```

Smoke test:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"ls"}}' | python tools/hook_evaluate.py
```

Expect a JSON verdict object (action ∈ `{ALLOW, SUGGEST, GUIDE, INTERVENE, BLOCK}`).

## Step 3 — verify v1.3 surface boots

Touch each new v1.3 surface to confirm import + table creation:

```bash
# JSONL tailer recognises desktop_prompt / user_reply (P5b)
python -c "from stream_manager.jsonl_tail import _MESSAGE_TYPES; print(_MESSAGE_TYPES)"

# learn_categorizer module imports + tables created on bus init (P5c)
python -c "from stream_manager.message_bus import MessageBus; b = MessageBus('.claude/gov.db'); print([r[0] for r in b._conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()])"
```

Expect `learn_patterns_canonical` and `learn_patterns_audit` (and earlier `learn_patterns` if migration history) in the table list.

## Step 4 — start a session

In Claude Desktop, start a new orchestrated session in this repo. The PreToolUse hook fires on each tool call, writes envelopes to `.claude/gov.db`, and the dashboard streams them via SSE. The Learn Mode JSONL tailer ingests Desktop dialogue turns out-of-band.

## Stop conditions before moving on

Do **not** advance to `02-test.md` until:

- [ ] Dashboard 200s on `/api/sessions/`
- [ ] Hook smoke test returns a valid verdict
- [ ] `learn_patterns_canonical` + `learn_patterns_audit` tables exist
- [ ] At least one envelope from a live Desktop session shows up in the dashboard sessions pane
