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

## Dashboard web UI

Open `http://localhost:8765` while uvicorn is running.

### Theme

Three themes selectable via the theme buttons in the header:

| Theme | Style |
|---|---|
| **Obsidian** | Dark industrial, amber accent |
| **Phosphor** | CRT green-on-black terminal |
| **Paper** | Light editorial, red accent |

---

### Header controls

| Control | What it does |
|---|---|
| Session selector (dropdown) | Filter all feeds to one session; "All sessions" = unfiltered |
| **LIVE** dot | Green = SSE connected and receiving events; grey = disconnected |
| **LM** toggle | Toggle Learn Mode categorizer on/off at runtime (no restart needed) |
| ⚙ gear button | Open settings panel (HITL mode, timeout, confidence floor, motion, audible cue) |

---

### Governance mode bar

Horizontal bar below the header. Shows the current governance posture for the active session:

`OBSERVE → SUGGEST → GUIDE → INTERVENE → BLOCK`

Color matches verdict palette. Updates live on each incoming decision event.

---

### Last-call strip

Thin strip below the governance mode bar. Shows metrics from the most recent governance call:

| Field | Meaning |
|---|---|
| Status | Verdict of the call (`ALLOW`, `BLOCK`, etc.) |
| Tier | Decision graph layer that fired (L0–L4) |
| Model | `haiku` or `sonnet` (which model was used for L4) |
| Latency | Wall-clock ms from hook entry to verdict |
| Tokens | Prompt + completion tokens consumed |
| Cost | Estimated cost of the call |

---

### Three frames

#### Frame A — Interactive Sessions

Live decision stream. Each row shows:

- **Verdict badge** — color-coded: green (ALLOW) → yellow (SUGGEST/GUIDE) → orange (INTERVENE) → red (BLOCK)
- **Confidence pips** — visual indicator of model confidence (0.0–1.0)
- **Layer** — L0–L4 which graph layer made the decision
- **Model** — haiku / sonnet
- **Agent profile** — inferred role slug (developer, reviewer, tester, unknown)
- **Content excerpt** — truncated message content

Click any decision row to expand reasoning and see ranked candidate actions (FR-UI-5 suggestions).

#### Frame B — Sub-Agents

Two tabs:

- **Swimlane** — each discovered agent in its own lane; verdict history as a timeline
- **Filtered feed** — decisions filtered to the selected agent only

Each agent card shows: profile slug, attribution plugin/skill, sidechain flag, first/last seen, active mode override (if set).

To set a per-agent governance mode override: click the agent card → select override mode from the dropdown. Override is in-memory (session-scoped, not persisted to WAL).

#### Frame C — Background Jobs

Three sub-sections:

| Sub-section | Content |
|---|---|
| **Jobs list** | CliPool worker health; shows running, idle, and stale workers |
| **Active Jobs / Agents** | Lifecycle bridge jobs — background tasks and spawned subagents with open start but no end event yet |
| **Async HITL Queue** | Unresolved async HITL items (visible when HITL mode is `async` and items are pending) |

---

### Session Mirror panel

Slide-out panel below the main frames. Shows raw `tool_call` / `tool_result` bus events for the selected session in real time. Useful for watching what Claude Desktop is executing without switching to the terminal.

Controls: **PAUSE** (stop scrolling) · **CLEAR** (reset view) · **▼/▲** (collapse/expand).

---

### Stats sidebar (right column)

| Stat | Meaning |
|---|---|
| Total decisions | Cumulative decision count across all sessions |
| Sessions `[ASYNC]` | Session count; badge shows current HITL mode |
| Graph % | Percentage of decisions resolved by graph (L0–L3) vs L4 model call |
| Avg confidence | Mean confidence score across all decisions |
| Distribution | Per-verdict bar chart (ALLOW / SUGGEST / GUIDE / INTERVENE / BLOCK) |
| Session list | Recent sessions with start time and active flag |
| Agent badges | Identified agent roles for the active session |

---

## HITL (Human-in-the-Loop)

### HITL modes

Set via gear ⚙ → HITL mode, or via the settings API:

| Mode | Behavior |
|---|---|
| `async` | SM flags `INTERVENE` events in the Async HITL Queue; session continues; you resolve when ready |
| `sync` | SM pauses the session on `INTERVENE` and waits for your decision (gate-and-wait) |
| `off` | No HITL gate; SM posts verdict as read-only advisory card |

Mode changes persist to `gov.db` and emit a `hitl_mode_promoted` bus event.

### Resolving a HITL item

When an item appears in the Async HITL Queue (Frame C) or blocks the session (sync mode):

1. Review the proposed action and reasoning
2. If Learn Mode is active, the prompt is pre-filled with the categorizer's suggestion — you can accept or override
3. Choose a resolution:
   - **Approved** — accept SM's proposed action
   - **Dismissed** — dismiss without acting; session unblocks
   - **Override** — select a different verdict: `ALLOW`, `SUGGEST`, `GUIDE`, `INTERVENE`, `BLOCK`
4. Click confirm. SM persists the resolution and optionally uses it as advisory bias for future similar events.

### Post-hoc annotation

On any decision row in Frame A, click **Annotate** to record an override action + optional note. Writes to `hitl_overrides` WAL table. Used to correct decisions after the fact without blocking the session.

---

### Cross-session patterns

Visible at the bottom of the stats sidebar when patterns with `cross_session=1` exist. These are patterns that SM has promoted for use across all sessions (not just the originating one).

To demote a pattern back to session-local: click **Demote** on the pattern row.

---

### Export decisions

Download all governance decisions as NDJSON:

```
http://localhost:8765/api/decisions/export
```

Optional filter: `?session_id=<id>`. Each line is one decision record with fields: `decision_id`, `session_id`, `timestamp`, `action`, `confidence`, `reasoning`, `matched_hash`, `model_used`, `layer`, `agent_profile_slug`, `trigger_reason`.

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
