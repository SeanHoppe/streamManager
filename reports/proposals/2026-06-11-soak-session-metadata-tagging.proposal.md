# Session soak_id + soak_metadata tagging for audit hygiene

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (flywheel) 2026-06-11; idea BACKEND-3; boldness SAFE; refute verdict CONSTRAIN; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

v10 RL evaluation runs share the same decision log, pattern store, and HITL queue as operator sessions. No explicit 'is this session under soak?' metadata exists to let operators and the governance engine filter evaluation traffic when reviewing decisions or designing HITL thresholds. Pattern learning conflates deterministic evaluation-fixture behaviour with operator decision-making, biasing operator HITL decisions and ship-gate pattern quarantine.

## Proposal

Add optional soak_id, soak_metadata, soak_started_by columns to the sessions table (schema additive per ADR-18). On session start, read SM_SOAK_ID env var (e.g., from tools/soak_driver.py --run-uuid or explicit operator setting) and stamp into session record -- WITH POLARITY GUARD: check session cwd/entrypoint against _SM_ENTRYPOINT_MARKERS (matching existing session_watcher.py:65 pattern) and silently skip soak_id assignment if SM-self is detected (prevents SM's own session from being tagged as soak). Expose two dashboard endpoints: (a) GET /api/sessions?soak_id={id} to list all sessions belonging to a soak; (b) GET /api/sessions/{id}/is-soak returning {is_soak: bool, soak_id, soak_type: "rl_evaluation|ship_gate|operator_manual", started_by_user_id?, tool_version?}. Dashboard can use this to: (i) filter decisions feed to exclude soak sessions by default (settable toggle); (ii) warn operators when adding patterns learned under soak to cross-session promotion; (iii) wire a soak-lifecycle panel showing all sessions grouped by soak_id with single close/cleanup control. No new bus envelope kinds; existing governance_call envelope metadata extended only.

## Operator value

Prevents stray soak patterns from biasing operator HITL decisions. Enables ship-gate decision quarantine (don't let v10 RL corpus changes escape into production patterns). Powers operator hygiene (see at a glance which sessions are noise vs. signal). Unblocks v10 MVP gate #112 by giving the alignment-eval pipeline explicit audit-only session tagging.

## Surfaces touched / added

- src/stream_manager/message_bus.py -- sessions table schema addendum (soak_id TEXT, soak_metadata JSON, soak_started_by TEXT)
- src/stream_manager/governance.py or session_watcher.py -- read SM_SOAK_ID env at session start, stamp into bus with self-monitor guard
- dashboard/server.py -- new GET /api/sessions?soak_id={id}, GET /api/sessions/{id}/is-soak endpoints

## Feasibility

HIGH. Schema migration is additive (proven pattern: provenance_assertions, learn_patterns_canonical). Session start reads env var + checks cwd/entrypoint (existing guard logic). Endpoints map directly to SQL queries. No changes to frozen surfaces (governance.py, message_bus.py decision/pattern/envelope logic unchanged). Guards prevent self-monitor regression.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- no certPortal coupling beyond existing learn-mode source registry pattern
- **Polarity (G2):** CONSTRAIN -- SM-self session MUST be excluded from soak_id stamping via cwd/entrypoint check at governance.py or session_watcher.py session start (matching existing _SM_ENTRYPOINT_MARKERS logic). Document guard in endpoint docstrings so dashboard filter (point a, exclude soak by default) does not trigger false positives on SM-self
- **ADR-18 MUST floor:** PASS -- no changes to 3-frame presence, escalation-only foreground, label+color badges, HITL gate, domain-agnostic vocab, a11y, latency budget, non-goals. Endpoints are auxiliary; decision logic unchanged
- **Frozen-surface note:** NONE -- no changes to governance.py, message_bus.py, cli_governance.py, model_router.py, cli_pool.py core logic. Schema extension only (additive per ADR-18 pattern)
- **New-envelope note:** NONE -- no new bus envelope kinds. Existing governance_call envelopes carry soak metadata as optional context field (backwards-compatible). cassette_record.py + soak_driver.py require no new coverage (envelope set unchanged)

## Grounding

- C:\Users\SeanHoppe\vs\streamManager\src\stream_manager\session_watcher.py:65 -- _SM_ENTRYPOINT_MARKERS constant + _is_self_session guard pattern
- C:\Users\SeanHoppe\vs\streamManager\src\stream_manager\message_bus.py:52-58 -- sessions table schema (additive extension target)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\server.py:720-757 -- existing /api/sessions endpoint (pattern for new endpoints)
- C:\Users\SeanHoppe\vs\streamManager\docs\adr\ADR-18-mvp-surface-freeze.md -- FROZEN surface classification, additive migration pattern
- C:\Users\SeanHoppe\vs\streamManager\docs\v10-mvp-status.md:45 -- v10 MVP gate #112 blocker context
