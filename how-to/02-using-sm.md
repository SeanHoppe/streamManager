# Using StreamManager

SM runs silently in the background during a Claude Desktop session. This page explains what SM does, how to interpret verdicts, and how to interact via HITL and the dashboard.

---

## What SM governs

Every tool call from Claude Desktop triggers the `hook_evaluate.py` PreToolUse hook. SM evaluates each message against:

- **Safety rules** (absolute — see [README.md](README.md#safety-priorities))
- **Plan alignment** — does this action move toward stated requirements in the project's `*.md` files?
- **Agent scope** — reviewer agents cannot directly execute CLI commands; developer agents near protected files escalate automatically
- **Cadence** — SM warns when a session stalls or drifts from plan

---

## Governance verdicts

| Verdict | Meaning | What happens |
|---|---|---|
| `ALLOW` | Routine action, within scope | Forwarded immediately |
| `SUGGEST` | Within scope but worth flagging | Forwarded; advisory note logged to dashboard |
| `GUIDE` | Borderline; operator should be aware | Forwarded; badge raised on dashboard |
| `INTERVENE` | Out of scope or risky; human review recommended | Paused; HITL prompt surfaced if HITL is ON |
| `BLOCK` | Hard safety rule or destructive pattern | Rejected; never forwarded |

Latency budget (ADR-5 v1.8): p50 ≤ 7 s · p95 ≤ 12 s · hard timeout 25 s. On timeout SM degrades to `OBSERVE` — tool call forwards.

---

## Decision graph layers

SM evaluates messages through L0→L4:

| Layer | What it checks |
|---|---|
| L0 | Static safety rules (always-on; result: ALLOW or BLOCK) |
| L1 | Known-safe patterns (routine dev commands → fast ALLOW) |
| L2 | Scope rules (agent role vs action type) |
| L3 | Plan alignment (project context vs current action) |
| L4 | Ambiguous / complex content — Haiku-first with Sonnet fallback |

L0–L1 are fast (< 50 ms). L2–L3 use project context loaded from all `*.md` files in the repo. L4 calls `claude -p` via the CliPool.

---

## Dashboard

Open `http://localhost:8765` while uvicorn is running. Three visual themes: **Obsidian** (dark) · **Phosphor** (green-on-black) · **Paper** (light).

Dashboard frames:

| Frame | Content |
|---|---|
| Interactive REPL | Live message stream; verdict badges per event |
| Sub-Agents | Agent registry: discovered roles, active sessions, scope flags |
| Background Jobs | CliPool health, LM categorizer queue depth, soak status |

Only true escalations (`INTERVENE`, negative regression, static-rule fire) auto-foreground a frame. Lower-severity signals badge in place.

---

## HITL (Human-in-the-Loop)

When HITL mode is ON and SM emits `INTERVENE`, the dashboard surfaces a ranked option list. You pick; SM persists the pick and uses it as advisory bias for future similar events.

When HITL is OFF, SM posts its proposed answer as a read-only card — monitor-only by default, with per-card opt-in to take action.

Learn Mode pre-fills the HITL prompt with the categorizer's suggested action. You still confirm before SM acts.

---

## Monitoring sessions from the terminal

```powershell
# list all sessions (active flag from registry if dashboard running)
sm sessions list

# stream live bus envelopes for a session
sm sessions tail <session_id>

# with explicit DB path
sm --db .claude/gov.db sessions list

# emit JSON instead of table
sm sessions list --json
```

---

## Sub-agent governance rules

SM discovers sub-agents via message metadata and pattern inference. Role-specific rules:

| Role | Default scope |
|---|---|
| Developer | `GUIDE` near protected files (`governance.py`, `message_bus.py`); `INTERVENE` on force-push |
| Code Reviewer | `SUGGEST` only; direct CLI execution from reviewer → `BLOCK` |
| Tester | Routine test commands → fast `ALLOW` |
| Unknown | Treated as `unknown` role; standard engine rules until pattern inference resolves |

Agent profiles that repeatedly exceed scope escalate governance mode for that agent specifically (not all agents).

---

## Project context loading

SM loads all `*.md` files from the governed repo at startup and refreshes them mid-session (10 s debounce) when any file changes. Rank order for alignment checks:

```
INTENT > REQUIREMENTS > CLAUDE.md > README > others
```

400-token budget for alignment checks consumed by ranked excerpts, not full dumps.

---

## Routine commands SM fast-allows

These are promoted to `ALLOW` patterns quickly and should not incur L4 latency:

- `pip install -e ".[dev]"`, `pytest`, `ruff check`, `mypy`
- File edits under `src/stream_manager/**` and `spikes/**`
- Commits to feature branches
