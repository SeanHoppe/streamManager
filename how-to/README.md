# StreamManager How-To Guide

Operator and developer reference for SM v1.8+.

## Contents

| File | Audience | Topic |
|---|---|---|
| [01-start-stop.md](01-start-stop.md) | Both | Install, start, stop all SM components |
| [02-using-sm.md](02-using-sm.md) | End-user | Day-to-day usage: verdicts, HITL, dashboard |
| [03-learn-mode.md](03-learn-mode.md) | End-user | Learn Mode: how it works, what to expect |
| [04-cli-reference.md](04-cli-reference.md) | Both | Full CLI command reference |
| [05-appendix.md](05-appendix.md) | Developer | Future roadmap and v1.9 backlog |

## Quick start (returning operator)

```powershell
# from repo root
uvicorn dashboard.server:app --port 8765 --reload
# governance hook fires automatically on each Claude Desktop PreToolUse event
# dashboard: http://localhost:8765
```

## Architecture in one line

```
Claude Desktop → [hook_evaluate.py PreToolUse] → GovernanceEngine → CliPool → claude -p
                                                       ↓
                                              dashboard (SSE) + gov.db (WAL)
```

## Safety priorities (always enforced, never overrideable)

1. `rm -rf /`, `rm -rf ~`, `dd … /dev/…`, `DROP DATABASE/TABLE` — **BLOCK**
2. `git push --force` to `main`/`master`/`production` — **INTERVENE**
3. `eval(` / `exec(` in untrusted message bodies — **INTERVENE**
4. Credential / API-key shapes in content — **BLOCK**
5. Governance API timeout → degrade to **OBSERVE**, never stall

These fire regardless of Learn Mode patterns or operator history.
