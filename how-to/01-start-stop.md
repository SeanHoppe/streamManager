# Start / Stop StreamManager

## Prerequisites

- Python 3.11+
- Claude Code CLI (`claude`) on PATH and authenticated
- Repo cloned; run once from repo root:

```powershell
pip install -e ".[dev]"
pip install -r dashboard/requirements.txt
```

---

## One-time setup: governance hook

SM intercepts every Claude Desktop tool call via a PreToolUse hook wired in `.claude/settings.json`. This is already configured in the repo — no manual step required on a fresh clone.

Verify wiring:

```powershell
# should show hook_evaluate.py in the hooks.PreToolUse list
cat .claude/settings.json
```

If the repo is a fresh clone and `.claude/settings.json` is missing the hook, re-run the editable install — the hook path references the repo root.

---

## Start SM

Starting SM = starting the dashboard server. The governance hook and Learn Mode categorizer both run inside the same uvicorn process.

```powershell
# from repo root
uvicorn dashboard.server:app --port 8765 --reload
```

What starts automatically:
- **Dashboard** — SSE server + UI at `http://localhost:8765`
- **Learn Mode categorizer** — background worker thread; drains Desktop dialogue pairs and writes to `learn_patterns` table
- **EngineRegistry** — session lifecycle tracker; `sm sessions list` uses this

Leave uvicorn running for the duration of your Claude Desktop session.

### Environment variables (optional)

| Variable | Default | Purpose |
|---|---|---|
| `GOV_DB` | `.claude/gov.db` | Override governance DB path |
| `SM_DASHBOARD_URL` | _(none)_ | Base URL for `sm` CLI to resolve active sessions via registry |
| `BRIDGE_API_GOV` | `false` | Set `true` / `1` to enable real CLI governance path |
| `BRIDGE_L4_FALLBACK_CONFIDENCE` | `0.70` | Haiku confidence floor; Sonnet retry fires below this |

---

## Verify SM is running

```powershell
# list governance sessions (uses registry if dashboard URL set)
sm sessions list

# or with explicit dashboard URL
sm --dashboard-url http://localhost:8765 sessions list
```

Open `http://localhost:8765` — dashboard shows active sessions, decisions feed, and sub-agent cards.

---

## Stop SM

```
Ctrl+C  (in the uvicorn terminal)
```

The Learn Mode categorizer and EngineRegistry stop with the server. The `gov.db` WAL file persists — sessions resume correctly on next start.

---

## Restart after crash

Uvicorn crash leaves `gov.db` intact (WAL journal). Restart with the same command:

```powershell
uvicorn dashboard.server:app --port 8765 --reload
```

Any in-flight session that was interrupted resumes normally on the next Claude Desktop message.

---

## Fresh DB (test or reset)

Governance state lives in `.claude/gov.db`. To start clean:

```powershell
Remove-Item .claude/gov.db -ErrorAction SilentlyContinue
uvicorn dashboard.server:app --port 8765 --reload
```

> **Warning:** This deletes all session history, decision log, and Learn Mode patterns. Cannot be undone.
