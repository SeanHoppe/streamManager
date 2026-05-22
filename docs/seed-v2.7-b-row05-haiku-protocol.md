# Seed v2.7-A — `frog7-phase-timings-keys-05` n=12 re-measure protocol

> Authored 2026-05-22 ahead of v2.7.1 P2 ship-gate. Design-only:
> fixture, runner invocation, decision tree, stability gate. ADR-18
> surface-freeze applies (golden cited only; Hatch A edit is the
> operator's call). Lifetime: closes at v2.7.1 P2 disposition. Lineage:
> `docs/seed-v2.6-a-row10-remeasure-protocol.md` (J3, v2.6 P2).

## Background

v2.7 P3 ship-gate BLOCKED at PR #207 S4 CI gate on
`frog7-phase-timings-keys-05`: Haiku-stabilisation regression under
`--runs 6` not seen in v2.6 P2 (row 05 baseline:
`haiku_runs=[ALLOW, SUGGEST, SUGGEST, SUGGEST, ALLOW, SUGGEST]`,
`haiku_stable=false`, timeouts 0/6, p50 ~15.4 s — see
`reports/alignment-eval-20260520T205842Z.json`). Status:
`docs/2026-05-22-status.md` §"v2.7 P3 ship-gate verdict (PR #207 —
BLOCKED)". v2.7.1 P1 fires this protocol; P2 lands disposition.
Predecessor: `docs/seed-v2.6-a-row10-remeasure-protocol.md` §"Background"
(row-10 Sonnet content drift). This file is the **Haiku-stabilisation**
equivalent.

## Re-measure design

**Fixture.** New single-row JSONL `reports/seed-v2.7-a-row05/row05-fixture.jsonl`
extracted from `tests/golden/l4_alignment.jsonl` row 05 verbatim
(`expected_verdict`, `model_floor`, `source_note` preserved). Mirrors
J3 anchor §"Re-measure design" fixture pattern
(`reports/seed-v2.5-a/row10-fixture.jsonl`).

**Runner invocation.** Per J3 anchor §"Re-measure design" runner-flag
rationale (`tools/alignment_eval.py` argparse lines 207–221; no
`--filter-row` flag — single-row scope is via `--golden` pointing at
a one-row fixture):

```
python -m tools.alignment_eval \
  --golden reports/seed-v2.7-a-row05/row05-fixture.jsonl \
  --runs 12 \
  --candidate-only-control \
  --report-only \
  --reports-dir reports/seed-v2.7-a-row05
```

`--candidate-only-control` is retained **only if**
`model_floor=sonnet`; this protocol targets Haiku stability, so for
`model_floor=haiku` rows drop the flag (Haiku runs must fire). v2.7.1
P1 prompt (J2, parallel) confirms the floor at fixture-extraction.
Default: row 05 is Haiku-gated → flag **dropped** → both control +
candidate runs fire (n=12 each). `--report-only` keeps the single-row
fixture out of `--ci-gate`. Runner auto-sets `BRIDGE_API_GOV=1`
(line 223); real `claude -p` per `feedback_cli_over_sdk.md`.

**Output sidecar.** `reports/seed-v2.7-a-row05/alignment-eval-<UTC>Z.{md,json}`
(new directory; row-10 fixture stays under `reports/seed-v2.5-a/`).

## Stability check

After n=12 lands, count majority + stability across
`rows.frog7-phase-timings-keys-05.haiku_runs`. This protocol gates on
**Haiku stability**, not Sonnet content (J3 anchor §"Stability check"
measured Sonnet content-drift; gate inverted here). Thresholds mirror
J3:

- **≥ 9/12 stable Haiku majority → STABLE-HAIKU-MAJORITY.** ≥ 75 %
  rate is sufficient to conclude Haiku has settled on a single verdict
  for this row; the v2.6 P2 4/6 SUGGEST reading was either noise that
  has cleared, or the new corpus has nudged the row to a different but
  now-stable majority. Hatch A.
- **6–8/12 stable Haiku majority → STILL-UNSTABLE.** 50–67 % rate
  stays inside the noise band; row remains structurally unstable for
  Haiku. Hatch B.
- **< 6/12 stable Haiku majority → BROAD-HAIKU-INSTABILITY.** No
  verdict dominates; the row's Haiku-response surface is wider than
  expected. Hatch C.

Stability boolean: `haiku_stable=true` iff the n=12 majority count
≥ 9 AND no single non-majority verdict appears > 2 times (matches the
existing runner's per-row stability rule scaled from n=6 to n=12).

## Decision tree

For each n=12 stability outcome (4 paths, mirrors J3 anchor §"Decision
tree"):

- **Hatch A — STABLE-HAIKU-MAJORITY (≥ 9/12 stable).** Golden
  re-baseline path. If the new Haiku majority diverges from current
  golden `expected_verdict`, edit `tests/golden/l4_alignment.jsonl`
  row 05 to the new majority (sole golden-file edit; ADR-18 freeze
  otherwise unchanged); update `source_note` to cite the v2.7.1 P2
  re-calibration. Re-fire v2.7.1 ship-gate S4 with new golden. **Seed
  v2.7-A: CLOSED RECOVERED.** v2.7-A-CLIP remains at "confirmed P3"
  status (not promoted).
- **Hatch B — STILL-UNSTABLE (6–8/12 stable).** Per-row exclusion
  path per `feedback_alignment_eval_stability_window.md` hatch (4):
  row 05 is "timeout-attributable or instability-attributable" and
  drops out of the gate denominator on this measurement run. Re-fire
  v2.7.1 ship-gate S4 with row 05 excluded; track row 05 for v2.8
  re-instrumentation. **Seed v2.7-A: CARRIES to v2.8** as
  `unstable_haiku` row. v2.7-A-CLIP remains at "confirmed P3" status.
- **Hatch C — BROAD-HAIKU-INSTABILITY (< 6/12 stable).** The row's
  Haiku-response surface is fundamentally broader than the binary the
  golden assumes. Escalate to corpus-wide cap-clip investigation;
  promote Seed v2.7-A-CLIP from "confirmed P3" to "v2.8 P1
  candidate" (see §"Coupling with Seed v2.7-A-CLIP"). Do **NOT**
  re-fire v2.7.1 ship-gate; halt the v2.7.1 sub-cycle and roll the
  question into v2.8 P0 frame. **Seed v2.7-A: CARRIES to v2.8 as
  blocking gate.**
- **Special case — STILL-100%-TIMEOUT-ESCALATE (≥ 6/12 NONE /
  timeout responses).** Mirrors J3 anchor §"Decision tree" special
  case. Timeout-boundary signal dominates regardless of content runs;
  halt the Haiku-stabilisation verdict pending a cap-tighten or
  cap-widen decision via Seed v2.7-A-CLIP. Couples directly to the
  cap-clip artefact — flag Seed v2.7-A-CLIP as the precondition seed
  for any re-fire; same fixture, re-run after the new cap lands.
  **Seed v2.7-A: CARRIES to v2.8 pending v2.7-A-CLIP resolution.**

## Expected runtime

Anchored on v2.6 P2 corpus readings
(`reports/alignment-eval-20260520T205842Z.json`): Haiku p50 **14.508 s**,
p99 25.035 s; Sonnet p50 16.14 s.

- **Candidate-only n=12:** 12 × 14.5 s ≈ **2.9 min**.
- **Control + candidate n=12** (default for `model_floor=haiku`
  rows): 24 × ~15.3 s ≈ **6.1 min**.
- **Worst case** (both at p99 ~25 s): 24 × 25 s ≈ **10 min**.

Fits inside the v2.7.1 P2 alignment-eval window; < 20 % incremental
against the full 32-row n=6 eval (~32 min) and does NOT extend Tier-3
soak envelope.

## Coupling with Seed v2.7-A-CLIP

Seed v2.7-A-CLIP (corpus-wide cap-clip artefact, ELEVATED at v2.7 P3
from "hypothesised P2" to "confirmed P3" per status doc §"v2.7 P3
ship-gate verdict") shares row 05's timeout-boundary sensitivity but
is **corpus-wide** (multiple rows with p99 at-or-near 30 s cap), where
v2.7-A is **row-specific** (Haiku-stabilisation for row 05).

Promotion ladder for v2.7-A-CLIP:

- **Pre-v2.7 P2:** hypothesised. **v2.7 P3 S4 failure:** confirmed
  P3 (current state).
- **Hatch A or B:** stays at "confirmed P3"; row 05 resolves
  independently; v2.7-A-CLIP carries to v2.8 P0 as scheduled.
- **Hatch C:** promoted to "v2.8 P1 candidate". Broad Haiku
  instability on a cap-clip-zone row indicates row-level fixes are
  insufficient; corpus-wide cap-clip resolution leads v2.8.
- **STILL-100%-TIMEOUT-ESCALATE:** v2.7-A-CLIP becomes blocking
  precondition; re-measure waits on cap decision.

## v2.7.1 P2 question (verbatim operator decision block)

Paste into v2.7.1 P2 ship-gate close-out under §"Seed v2.7-A
disposition":

```
Re-measure stability (n=12 single-row, frog7-phase-timings-keys-05):
- [ ] Hatch A — STABLE-HAIKU-MAJORITY (≥ 9/12 stable)
- [ ] Hatch B — STILL-UNSTABLE (6–8/12 stable)
- [ ] Hatch C — BROAD-HAIKU-INSTABILITY (< 6/12 stable)
- [ ] STILL-100%-TIMEOUT-ESCALATE (≥ 6/12 NONE / timeout)

Disposition:
- [ ] Hatch A — golden update (edit `tests/golden/l4_alignment.jsonl`
      row 05 expected_verdict to new Haiku majority); re-fire S4.
- [ ] Hatch B — per-row exclusion (drop row 05 from S4 denominator
      this run); re-fire S4; carry Seed v2.7-A to v2.8.
- [ ] Hatch C — halt v2.7.1; promote Seed v2.7-A-CLIP to v2.8 P1
      candidate; roll Seed v2.7-A into v2.8 P0 frame as blocking.
- [ ] Timeout escalate — halt re-measure verdict; gate on Seed
      v2.7-A-CLIP cap decision; carry Seed v2.7-A to v2.8.

Re-measure report path:
- `reports/seed-v2.7-a-row05/alignment-eval-<UTC>Z.{md,json}`

Seed v2.7-A-CLIP promotion (fill per disposition):
- v2.7-A-CLIP status post-disposition: [ ] confirmed P3 (Hatch A/B)
  [ ] v2.8 P1 candidate (Hatch C) [ ] blocking precondition (timeout)
```

## v2.7.1 P1 fire-conditions

Pre-conditions for deterministic fire:

- **PR #207 disposition recorded.** Folded into v2.7.1 (fresh branch
  off `main` post-#207-close) OR carried as v2.7.1 base. Re-measure
  MUST NOT fire while PR #207 is mid-edit.
- **No concurrent ship-gate runs.** Soak driver + alignment-eval
  share CLI worker pool; concurrent fires cross-contaminate p95/p99.
  Verify `tools/soak_driver.py` not running before invocation.
- **Fixture extracted.** `reports/seed-v2.7-a-row05/row05-fixture.jsonl`
  matches `tests/golden/l4_alignment.jsonl` row 05 byte-for-byte
  (`expected_verdict` + `model_floor` equal).
- **Cap state pinned.** Record `src/stream_manager/cli_governance.py`
  `TIMEOUT_SECONDS` at fire-time in the sidecar (cited only — no
  `src/` edit; ADR-18 freeze).
- **No golden edits in-flight.** `tests/golden/l4_alignment.jsonl`
  at `main`-tracked SHA. Hatch A's edit lands at v2.7.1 P2, not P1.

## Refs

- `docs/seed-v2.6-a-row10-remeasure-protocol.md` — J3 structural
  anchor (row-10 Sonnet content drift). Reused §Background +
  §Re-measure design + §Decision tree + §Expected runtime.
- `docs/2026-05-22-status.md` §"v2.7 P3 ship-gate verdict (PR #207
  — BLOCKED)" — S4 failure summary.
- `reports/alignment-eval-20260520T205842Z.{md,json}` — v2.6 P2 n=6
  baseline; row 05 Haiku readings + corpus Haiku p50 14.508 s.
- `tests/golden/l4_alignment.jsonl` row 05 — golden source (cited;
  no edit in this protocol; Hatch A edit at v2.7.1 P2).
- `tools/alignment_eval.py` argparse lines 207–221 — runner flags.
- `src/stream_manager/cli_governance.py` `TIMEOUT_SECONDS` — current
  cap (cited; no `src/` edit per ADR-18).
- `feedback_alignment_eval_stability_window.md` hatch (4) — per-row
  exclusion rule (Hatch B).
- `feedback_cli_over_sdk.md` — real `claude -p` subprocess.
- PR #196 (`7220b33`) — instrumentation source (v2.6 P1).
- PR #207 — v2.7 P3 ship-gate fire (BLOCKED at fire-time).
