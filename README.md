# StreamManager

Resource-efficient governance + adaptive-learning bridge between Claude Desktop and a Claude CLI session.

**Status:** Pre-POC. Requirements drafted, framework planned, spike work not yet started.

## Documents

- [REQUIREMENTS.md](REQUIREMENTS.md) — full PRD/RFC/ADR (v1.0, 2026-05-01)
- [INITIAL_PLAN.md](INITIAL_PLAN.md) — framework skeleton + three-spike POC strategy

## What's next

Three throwaway POC spikes, ~1 day each:

- `poc/pipe` — SQLite WAL bus + two WebSocket servers + echo clients (prove the transport)
- `poc/brain` — Replay log through governance + decision graph (prove the learning math, including project-INTENT signal value)
- `poc/wire` — Wrap real `claude` subprocess (prove the IPC story end-to-end)

After all three, the spike that surfaced the most surprise becomes v0.1. The other two are deleted; their findings live in `POC_FINDINGS.md`.
