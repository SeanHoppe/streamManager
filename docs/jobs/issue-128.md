# #128 — v2.1 P1 PPP transport: HTTP vs direct MessageBus writer

**Status:** DECIDED 2026-05-08 — **Option B (direct MessageBus writer)**.
P1 prompt §6 + DOD updated; HTTP `/api/sm-probe` retained for browser/operator path.
GH issue stays OPEN until P1 PR lands the implementation.
**Bucket:** NOW.
**GH:** https://github.com/SeanHoppe/streamManager/issues/128

## Decision (2026-05-08)

**Option B.** Soak driver writes `audit.probe` directly via
`MessageBus.write_envelope(...)`. HTTP `/api/sm-probe` retained for browser. Two
writers, one bus, dashboard SSE consumes from bus.

Rationale: keeps Tier 3 soak process-direct invariant. No dashboard-up dependency
at soak time. SM monitoring reach unchanged (probe transport ≠ JSONL monitoring
transport — both A and B local-only; remote-CLI monitoring tracked separately as
v2.2 backlog seed).

HMAC seam: reuse `desktop_command` secret of record (commit `595df23`). Both
writers sign single-keyed.

Browser no-subscriber contract: HTTP 503 + structured error body. No silent
fire-and-forget.

## Summary

P1 prompt §6 fires `/api/sm-probe?force=1` over HTTP from `tools/soak_driver.py`.
Soak driver is process-direct today → HTTP coupling adds dashboard-up dep.
Pick before P1 branch opens.

## Options

- **A.** HTTP probe + dashboard uptime invariant + soak pre-flight (5×2s retry).
- **B.** Direct `MessageBus.write_envelope(audit.probe)` — keeps soak process-direct.
  HTTP path retained for browser-driven probes (two writers, one bus).

**Recommend B.**

## Acceptance (folded refinements)

- [x] Decision recorded — P1 prompt §6 + DOD updated, this job file updated (2026-05-08).
- [x] §A1 HMAC secret distribution spec'd: reuse `desktop_command` HMAC seam (commit `595df23`).
- [x] §A2 Browser no-subscriber contract: HTTP 503 + structured error.
- [~] §A4 (skipped — Option B path).
- [ ] (P1 PR) `tools/soak_driver.py --ppp-auto-probe` direct bus write.
- [ ] (P1 PR) Cassette: `audit.probe` + `audit.probe_ack` recorded same-PR.
- [ ] (P1 PR) Test asserts browser 503 path on zero subscribers.
- [ ] (P1 PR) Test asserts both writers sign single-keyed via shared HMAC seam.

## Refs

- `docs/v2.1-task-plan.md` §"Cross-cutting risks" item 5.
- `docs/prompts/v2.1-orchestration/phase-1-ppp-stream-disambiguation.md` §6.
- ADR-17, ADR-14.
- `feedback_cassette_must_cover_new_envelopes.md`.

## Action

DONE 2026-05-08:
- Operator picked B.
- P1 prompt §6 ABORT/CLARIFY caveat dropped; transport decision codified.
- P1 prompt DOD updated.

NEXT:
- Mint `feat/v2.1-p1-ppp-stream-disambiguation` branch off `origin/main` (#127 merged 2026-05-07 @ `07bc540`).
- Implementation per P1 prompt.
