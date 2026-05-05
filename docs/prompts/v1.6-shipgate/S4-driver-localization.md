# S4 — Decide driver localization

**Goal:** Identify which residue sub-component dominates `evaluate_inner` p95
tail. Output: one sentence ADR-5 update + v1.7 lever pointer.

## Context

v1.5 ship-gate showed `evaluate_inner` p95 ~5599 ms with v1.5 sub-phases
summing to 0.13 ms. v1.6 P1 added 5 CLI residue keys to attribute the gap.
Likely candidate per memory `project_v16_cycle_frame.md`:
synchronous `cli_pool_send_ms` round-trip on escalation branch.

## Steps

1. Read S3-captured residue p95 numbers.
2. Rank: largest first.
3. Per category, recommend lever:
   - `cli_pool_send_ms` dominant → v1.7 lever = pool sizing OR Haiku fastpath.
   - `cli_pool_acquire_ms` dominant → v1.7 lever = pool capacity (>2).
   - `cli_dispatch_ms` >> sum(send+acquire+parse+setup) → unattributed gap
     remains; mint S4a (residue still incomplete).
   - `cli_parse_ms` dominant → v1.7 lever = JSON parse / output streaming.
   - `cli_setup_ms` dominant → v1.7 lever = process model rework (unlikely).
4. Draft ADR-5 §"Caveats" delta — replace v1.5 "residue location unidentified"
   line with v1.6 attribution sentence.

## Acceptance

- Driver finding written as single sentence + supporting numbers.
- v1.7 lever recommendation chosen (single primary lever, optional fallback).
- ADR-5 caveat draft text ready for S6.

## On-done ack

`- [x] driver=<component> p95=<X>ms **S4 — Decide driver localization** (v1.7 lever: <lever>)`

## Mint-new check

- If `cli_dispatch_ms` p95 >> `setup + acquire + send + parse` p95 sum →
  un-attributed gap inside dispatch. Mint `S4a-dispatch-decomp.md` (v1.7 P1
  candidate: split dispatch into pre-send + post-send waits).
- If two components tied within ~10%, mint `S4b-multi-driver-tie.md`
  (v1.7 needs two levers, document both).
