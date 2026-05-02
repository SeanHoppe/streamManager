# Task 6 — Real-CLI soak test

**Branch:** `claude/hopeful-sutherland-89389d`
**Base PR:** #16
**Spec ref:** Outstanding from POC hardening (memory ref `project_poc_state.md`)
**Status:** Not run

## Goal

Run a 30-min soak with the real Claude CLI in the loop end-to-end and confirm no leaks / hangs / dropped events.

## Steps

1. Confirm `claude` CLI on PATH (`which claude` or `where claude`). If missing, document and exit early.
2. Set `BRIDGE_API_GOV=1` to enable `cli_governance` escalation.
3. Start dashboard server.
4. Drive a synthetic load: a small script `tools/soak_driver.py` that publishes 60 messages to the bus over 30 minutes (one every 30 s), mixing:
   - Routine ALLOW patterns.
   - A few escalation triggers (e.g., low-confidence content that forces L4 escalation).
5. Track:
   - Process RSS every minute (`psutil`).
   - Open file descriptors.
   - `gov.db` row counts.
   - Dashboard SSE event count received vs sent.
6. Report `reports/soak-{timestamp}.md` with: total events emitted, events received via SSE, any escalations hit + their latency, peak RSS, FD count drift, any errors logged.

## Acceptance

- 100% events received (or documented loss reason).
- RSS does not grow unbounded (< 50 MB drift).
- No uncaught exceptions in server log.

## Out of scope

- CI integration (separate work).
- Production load (this is dev-machine soak).

## When done

Report under 200 words; include `reports/soak-*.md` path.
