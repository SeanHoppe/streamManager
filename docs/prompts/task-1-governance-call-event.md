# Task 1 — `governance_call` bus event for L4 cost transparency

**Branch:** `claude/hopeful-sutherland-89389d` (worktree at `.claude/worktrees/hopeful-sutherland-89389d`)
**Base PR:** #16
**Spec ref:** Audit recommendation; counter to wiring `track_subprocess` into `cli_governance.py`
**Status:** Not built

## Goal

Emit a dedicated `governance_call` bus event whenever `cli_governance.CliGovernor.evaluate` runs a subprocess, so the dashboard can render L4 Sonnet (and L2/L3 Haiku) cost telemetry without polluting the frame-C "background jobs" stream (which is for user dev jobs per FR-UI-1).

## Why

L4 alignment escalation now invokes `claude -p ...` per commits `ca09ad7` / `d1ffffe`. Subprocess is invisible to the user — no latency, no token count, no model attribution. Audit recommended a dedicated event channel rather than wiring `track_subprocess` into `cli_governance` (which would conflate SM-internal model calls with user dev-job streams).

## Files to touch

- `src/stream_manager/cli_governance.py` — accept optional `bus: MessageBus | None` + `session_id: str | None` in `CliGovernor.__init__`; emit one `governance_call` event with `status="running"` before `subprocess.run`, one with `status="exited"|"failed"` + `latency_ms` + parsed token counts after. Token counts come from the Claude CLI JSON envelope (envelope keys: `usage.input_tokens`, `usage.output_tokens`, `total_cost_usd` if present); pass through as-is.
- `src/stream_manager/governance.py` — thread `bus` + `session_id` through to `CliGovernor` when constructed.
- `src/stream_manager/model_router.py` (or wherever L4 dispatch lives) — same.
- `dashboard/static/index.html` — subscribe to `type=="governance_call"`. Render in a NEW small fourth strip ABOVE the three frames (or as a header-row badge — your call) showing: last call's model, latency, input+output tokens, cumulative cost this session. Use existing badge tokens; keep monochrome / `OBSERVING`-styled (slate). DO NOT route into frame C.
- `tests/test_governance_call_event.py` — new.

## Tests

1. `running` event emitted before subprocess.
2. `exited` event emits with `latency_ms > 0` and token fields when envelope contains `usage`.
3. `failed` event when subprocess returns non-zero.
4. `bus=None` path silent (back-compat for unit tests).

## Event metadata shape

```json
{
  "model": "claude-haiku-4-5-20251001",
  "tier": "L2|L3|L4",
  "status": "running|exited|failed",
  "latency_ms": 1234,
  "input_tokens": 128,
  "output_tokens": 64,
  "cost_usd": 0.0021,
  "trigger": "alignment|safety|unknown"
}
```

## Out of scope

- Frame C wiring (don't touch `cli_client.py`).
- Persistent cost ledger (cumulative computed client-side from event stream).

## Run

```bash
pip install -e . --no-deps && pytest tests/test_governance_call_event.py -x
```

Then full suite.

## When done

Commit, push to `claude/hopeful-sutherland-89389d`. Do NOT open new PR (folds into #16 or follow-up at user's call). Report summary in <200 words.
