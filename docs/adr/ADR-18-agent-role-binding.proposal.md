# Freeze-lift proposal: agent role-binding fields on `governance_decision` envelope

- **Status**: PROPOSAL (not adopted). Reroute target for finding
  `F7-extract-gov-jsonl-agent-role-0002`.
- **Tracking issue**: #215
- **Surface**: FROZEN `governance_decision` bus envelope (ADR-18
  "Amendments" 2026-05-12, schema table). Emitted by
  `MessageBus.record_decision`; consumed by `rl.episode_logger` via
  `rl.bus_subscriber` and materialised by `tools/extract_gov_to_jsonl.py`.

## Why this is a proposal, not an edit

The `governance_decision` envelope schema is FROZEN under ADR-18 Rule 1.
The schema (ADR-18 2026-05-12 amendment) does NOT carry `agent_role` or
`agent_profile_slug`. Adding those producer-side fields is a change to a
FROZEN bus envelope schema, which the cycle hard-guards route to a
freeze-amendment proposal rather than an in-place edit. The gap is real
(agent role-binding is not observable from an extracted episode) but it
is an intentional, documented deferral, not a contract violation.

Touching `tools/extract_gov_to_jsonl.py` or `rl/episode_logger.py` to
read `agent_role` today would write dead code: no upstream producer
populates the field on the envelope, so the column would always be NULL
and would falsely imply the seam exists.

## Proposed change (deferred to a P5 cycle slot)

1. Extend the `governance_decision` envelope schema with two additive,
   optional fields:
   - `agent_role` (str, optional) -- monitored-session agent role binding.
   - `agent_profile_slug` (str, optional) -- resolved agent-profile slug.
   Both default absent; additive-only, no existing field reshaped.
2. Populate them at the single producer
   (`MessageBus.record_decision`) from the resolved agent profile.
3. Thread them through `rl.episode_logger.record_decision` and
   `tools/extract_gov_to_jsonl.py` as nullable persisted fields, and add
   a nullable `agent_role` / `agent_profile_slug` column to
   `rl/schema.sql` in the SAME PR (mirrors the project_slug pattern).

## Guard rationale

- ADR-18 Rule 1: FROZEN envelope schema change requires an ADR amendment.
- Cycle hard-guard G-FROZEN: a new field on a FROZEN bus envelope for an
  unfilled producer reroutes to a freeze-lift proposal; the
  `governance_decision` agent_role gap is the named deliberate-freeze
  example deferred to Issue #215.

No FROZEN surface is modified by this proposal file.
