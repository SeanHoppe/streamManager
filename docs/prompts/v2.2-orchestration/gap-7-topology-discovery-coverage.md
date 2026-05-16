# Gap 7 — Topology-discovery coverage (backlog seed)

> Minted from `docs/intent-todo-gap-2026-05-16.md` §Gap 7. **Backlog
> seed** — promotion-gated.

## Why

INTENT.md §"What this project is" (verbatim): SM "discovers the
Desktop's sub-agent topology (Prompt Constructor, Developer, Code
Reviewer, Tester, and others) via hybrid metadata + pattern
inference, and governs each agent independently per its role scope."

INTENT §"Sub-agent governance principles" addendum: "Unknown agents:
treated as `unknown` role under standard engine rules until pattern
inference resolves their profile."

Today: topology discovery is silent. An unknown-agent JSONL stream
gets classified `unknown` and stays there indefinitely if pattern
inference fails to converge. No regression test detects mis-class.

## Promotion criterion (re-stated)

PROMOTE this seed when **either**:

1. New unknown-agent pattern surfaces in production logs — i.e.
   `agent_profiles` row with `role = "unknown"` persists > 1
   cycle (operator confirms via SQL on running gov.db).
2. A known-agent profile mis-classifies in a ship-gate run — e.g.
   Code-Reviewer JSONL gets classified Developer or Tester.

Until then: speculative.

## Deliverable shape (when promoted)

### 1. Topology fixture corpus

`tests/fixtures/topology/`:

- `prompt_constructor_session.jsonl` — synth Desktop session with
  Prompt-Constructor agent signatures.
- `developer_session.jsonl` — synth Developer agent signatures.
- `code_reviewer_session.jsonl` — synth Code-Reviewer signatures.
- `tester_session.jsonl` — synth Tester signatures.
- `unknown_session.jsonl` — synth agent that intentionally does NOT
  match any known role pattern.

**Slug pin (mandatory).** Every fixture JSONL MUST carry a
`project_slug` field set to a non-SM value (e.g. `"certPortal"` or
a synthetic `"fixture-topology"`). The SM polarity-flip rule
(`CLAUDE.md` §"Session-source exception rule") excludes any session
whose slug is in `STREAM_MANAGER_PROJECT_SLUGS` (default
`{"streamManager"}`). A fixture without a slug, or one that defaults
to an SM-pattern slug, will be silently filtered out at the SQL
`WHERE` boundary and ingest-path tests will return zero rows. Add an
assertion in the test harness that confirms the slug field is
present + non-SM before running inference.

### 2. Inference-roundtrip test

`tests/test_topology_inference.py`:

- For each known fixture, run topology discovery; assert
  `agent_profiles.role` resolves to expected value within N
  ingest iterations (N = current pattern-convergence threshold).
- For unknown fixture, assert `role = "unknown"` AND inference
  state persists "still trying" (NOT silently graduates to a
  wrong role).

### 3. Role-confidence threshold test

`tests/test_topology_confidence_threshold.py`:

- Synth borderline session (50/50 Developer vs Reviewer signals).
- Assert classifier abstains (role = "unknown") rather than guess.
- ADR-18 falsify-before-extend: confidence threshold parameter
  itself becomes a DORMANT-N candidate if first introduced here.

## Cross-refs

- INTENT §"What this project is" + §"Sub-agent governance
  principles" (unknown-agent rule).
- `agent_profiles` table schema (likely `src/stream_manager/
  agent_profiles.py` or `message_bus.py` schema).
- Pattern inference site (grep `infer_role` / `classify_agent` /
  similar at promotion time).
- Gap doc §"Gap 7 — Topology-discovery coverage".
- `docs/v2.2-backlog.md` §"INTENT.md gap-analysis seeds".

## DOD (when promoted)

- [ ] Topology fixture corpus added (5 fixture JSONLs).
- [ ] Inference-roundtrip test landed.
- [ ] Role-confidence threshold test landed.
- [ ] Backlog seed struck.
- [ ] Gap doc §Gap 7 LANDED.

## ADR-18 posture

- Test-only (assuming inference site doesn't need refactor). If
  refactor needed: EVOLVING surface; record at P-N.
- LOC estimate: ~150 tests + ~50 fixture data. Small.
- DORMANT-N: confidence-threshold parameter counts as new lever
  if introduced; falsify within ≤ 2 cycles or rip out.
