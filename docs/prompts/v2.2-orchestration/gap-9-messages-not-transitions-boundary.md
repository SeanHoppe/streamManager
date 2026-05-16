# Gap 9 — "Governs messages, not transitions" boundary regression (backlog seed)

> Minted from `docs/intent-todo-gap-2026-05-16.md` §Gap 9. **Backlog
> seed** — promotion-gated.

## Why

INTENT.md §"Sub-agent governance principles" (verbatim, two
mutually reinforcing claims):

- "Each sub-agent is governed independently by its role profile."
- "SM MUST NOT gate one agent based on another's completion state."
- Frame line: "Pipeline ordering remains with Desktop orchestration.
  SM governs messages, not transitions."

This is a **structural** boundary, not a feature. Crossing it
silently is a category error — SM would creep into orchestration
territory, duplicating Desktop's job and breaking the
independence-per-agent contract.

Today: zero structural guard. A well-meaning PR adding "wait for
Reviewer before forwarding Tester" or similar cross-agent gate
lands silent.

## Promotion criterion (re-stated)

PROMOTE this seed when **either**:

1. A todo / PR review surfaces a code path that gates one agent on
   another's completion state (exact INTENT-forbidden pattern).
2. `governance.py` (or adjacent) review surfaces transition-gating
   helpers — e.g. `wait_for_agent_complete()`, `gate_on_role()`,
   pipeline-state machines.

Until then: speculative. No drift observed.

## Deliverable shape (when promoted)

### 1. Architectural-fitness lint

`tests/test_governance_message_not_transition.py`:

- Static scan over `src/stream_manager/governance.py` +
  `cli_governance.py` + `message_bus.py` for forbidden patterns:
  - Function names containing `wait_for_*_complete`,
    `gate_on_role`, `block_until_*`, `transition_*`, `pipeline_*`.
  - `agent_profiles` queries that JOIN across two different
    `agent_type` rows in a single verdict path.
  - `governance.evaluate` calls referencing peer agent state
    (not own message + own profile).
- Allowlist: legitimate read-only telemetry (e.g. "how many
  open agents are there" for dashboard) — narrow scope.
- Test fails with grep-style hit location + remediation pointer.

### 2. Boundary-fixture roundtrip

`tests/test_governance_independence_per_agent.py`:

- Synth two simultaneous agent JSONLs (Developer + Reviewer).
- Hold Reviewer in "in-progress" state.
- Forward Developer message; assert verdict computed using
  ONLY Developer's profile + own message — Reviewer state must
  not appear in evaluate input.
- Concretely: instrument `evaluate()` to record `inputs` dict;
  assert `inputs.keys() ⊆ {own message, own profile, project
  context, system rules}`.

### 3. ADR cross-link

When this gap lands, add a one-paragraph ADR entry
(`docs/adr/ADR-NN-message-vs-transition-boundary.md`) codifying
the INTENT line as a load-bearing architectural decision —
prevents the rule from being "just a doc line".

## Cross-refs

- INTENT §"Sub-agent governance principles" — all three lines.
- INTENT §"What this project is" final paragraph.
- `src/stream_manager/governance.py` — primary surface.
- `src/stream_manager/cli_governance.py` — secondary surface.
- Gap doc §"Gap 9 — Governs messages, not transitions".
- `docs/v2.2-backlog.md` §"INTENT.md gap-analysis seeds".

## DOD (when promoted)

- [ ] Architectural-fitness lint landed.
- [ ] Boundary-fixture roundtrip test landed.
- [ ] New ADR codifying the boundary landed.
- [ ] Backlog seed struck.
- [ ] Gap doc §Gap 9 LANDED.

## ADR-18 posture

- Test/lint + new ADR (docs). No FROZEN surface touched on land
  (unless surface scan reveals an existing violation — then
  remediation is in-cycle scope).
- LOC estimate: ~150 tests + ~50 ADR. Small.
- No DORMANT-N implication.
