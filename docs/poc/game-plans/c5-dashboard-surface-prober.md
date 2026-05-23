# C5 — `dashboard-surface-prober` game plan

**Agent file:** `.claude/agents/dashboard-surface-prober.md`
**Role:** Dashboard-surface latency + render-shape prober.
**Tools:** Read, Bash.

## Role in fleet

Closes the live-monitoring loop: C4's decision_id MUST surface in dashboard live-feed within latency budget AND render shape MUST honor INTENT.md §"UI / HITL principles" (3-frame layout, paired label+color badges, HITL ranked-option list).

## Inputs

- C4's `decision_id` + `created_at`.
- `dashboard/server.py` (read-only).
- `dashboard/static/index.html` (read-only).
- INTENT.md §"UI / HITL principles".
- ADR-5 §"NFR-P2".
- `docs/adr/ADR-9-hitl-as-mode.md`.

## Steps

1. Locate the live-feed endpoint in `dashboard/server.py` (SSE / WebSocket).
2. Locate 3-frame containers in `index.html` (Interactive REPL / Sub-Agents / Background Jobs).
3. Latency probe: connect to endpoint, wait ≤ 30 s for `decision_id` event, measure latency.
4. Render-shape probe: confirm event payload has paired `label` + `color`; for HITL decisions, confirm `ranked_options` array present; for auto-foreground flag, confirm only escalation classes trigger it.

## PASS criteria

- Latency ≤ 5000 ms (target) / ≤ 15000 ms (ADR-5 NFR-P2 ceiling = WARN if between).
- All three frame containers present.
- Paired label+color badges.
- HITL ranked-option list rendered when applicable.
- Auto-foreground only on escalation classes.

## Outputs to coordinator

- Latency reading (ms).
- §4 INTENT §"UI / HITL principles" row read.
- Gates C9 (C9 chains C3→C4→C5 with timing).

## Failure modes

- `latency-exceeds-15000ms` — POC fails ADR-5 ceiling; HARD FAIL.
- `missing-frame-container` — UI does not honor INTENT 3-frame mandate; §4 FAIL.
- `color-only-badge` — INTENT §"UI / HITL principles" violation; §4 FAIL.

## Refs

- `dashboard/server.py`, `dashboard/static/index.html`.
- INTENT.md §"UI / HITL principles".
- ADR-5 §"NFR-P2".
- `docs/adr/ADR-9-hitl-as-mode.md`.
