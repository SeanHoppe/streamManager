# Task — Soak-summary dual-anchor LOC delta (🟡 Seed 4)

> Minted 2026-05-17 as part of v2.3-pm-mint PR. Comparison anchor:
> `docs/v2.3-next-steps.md` §"Seed 4 — 🟡 ADR-18 Amendment A L388 +
> Amendment C dual-anchor soak-summary".

## Why

ADR-18 §"Amendments / Amendment A" acceptance checklist L388 has
been OPEN since v2.2 P0:

> `tools/soak_driver.py` post-soak LOC delta summary updated against
> new threshold (additive output only).

ADR-18 §"Amendments / Amendment C" (minted at v2.2 P2) clarified the
cycle-discipline LOC gate binds at the **P0-merge tip → HEAD**, with
the predecessor tag retained as narrative comparator. The soak
driver currently renders NEITHER anchor — operator hand-computes at
ship-gate via `git diff --stat <SHA>..HEAD`. v2.2 P2 discovered the
hand-compute step against the literal P2-prompt anchor produced a
false-BLOCK; mechanising both anchors in the soak summary closes the
gap.

## Deliverable

`tools/soak_driver.py` post-soak summary (markdown + stdout) gains a
new section that renders **both** LOC-delta anchors. Additive output
only; no surface change.

### Inputs

Two new env vars:

- `BRIDGE_CYCLE_TIP_SHA` — P0-merge tip SHA (cycle-discipline gate
  anchor, per Amendment C). REQUIRED at ship-gate; if unset, the
  block renders `cycle-tip: UNSET` and the gate verdict is
  `UNKNOWN`.
- `BRIDGE_PREDECESSOR_TAG_SHA` — predecessor release-tag SHA
  (narrative comparator, per Amendment A). OPTIONAL; if unset,
  narrative block renders `predecessor-tag: UNSET` (advisory only).

Rationale for env-driven inputs (not CLI flags): ship-gate operator
already sets `BRIDGE_RL_LOGGER_ENABLED` etc via env; consistent
shape. CLI flags require P2-prompt template churn each cycle.

### Output shape (markdown report)

Inserted between existing §"Decision-action distribution" and
§"Latency" (or wherever fits before final verdict line):

```markdown
## Cycle-discipline LOC delta

| Anchor              | SHA          | Gate?     | LOC delta (insertions / deletions / net) |
|---------------------|--------------|-----------|------------------------------------------|
| Cycle-tip (Amend C) | <SHA[:7]>    | BINDING   | +<I> / -<D> / <NET>                       |
| Predecessor-tag (A) | <SHA[:7]>    | NARRATIVE | +<I> / -<D> / <NET>                       |

**Gate verdict (Amendment C):** <PASS|BLOCK|UNKNOWN>
- Consolidation cycle: net ≤ 0 vs cycle-tip = PASS.
- Feature cycle: net ≤ 1500 (soft) / < 2250 (BLOCK at 1.5×) vs
  cycle-tip = PASS.
- Cycle type from `BRIDGE_CYCLE_TYPE` env (`consolidation` |
  `feature`); UNKNOWN if unset.
```

### Output shape (stdout)

```
[soak] cycle-tip LOC delta (Amend C): +<I> / -<D> / <NET>  [<PASS|BLOCK|UNKNOWN>]
[soak] predecessor-tag LOC delta (Amend A): +<I> / -<D> / <NET>  [narrative]
```

### Implementation sketch

```python
def _git_diff_loc(anchor_sha: str) -> tuple[int, int, int] | None:
    """Returns (insertions, deletions, net) or None if anchor invalid."""
    if not anchor_sha:
        return None
    try:
        out = subprocess.run(
            ["git", "diff", "--shortstat", f"{anchor_sha}..HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout
        # parse "N files changed, X insertions(+), Y deletions(-)"
        ...
    except subprocess.CalledProcessError:
        return None
```

Edge cases:
- Anchor SHA does not exist in repo → render `INVALID-SHA`.
- HEAD == anchor SHA → render `0 / 0 / 0` with `PASS`.
- Not in a git checkout → render `NOT-A-GIT-REPO` (don't crash; soak
  may run in a CI tarball deploy).

## Tests

`tests/test_soak_summary_loc_anchors.py` (NEW, ~ 60 LOC):

- Mock `subprocess.run` for `git diff --shortstat`.
- Case 1: both env vars set, valid SHAs → both rows render with
  correct deltas.
- Case 2: `BRIDGE_CYCLE_TIP_SHA` unset → gate verdict = UNKNOWN,
  predecessor-tag still renders (or also UNSET if also unset).
- Case 3: `BRIDGE_CYCLE_TYPE=consolidation` + net = +5 → BLOCK.
- Case 4: `BRIDGE_CYCLE_TYPE=feature` + net = +1499 → PASS (soft).
- Case 5: `BRIDGE_CYCLE_TYPE=feature` + net = +2249 → PASS (still <
  1.5× hard).
- Case 6: `BRIDGE_CYCLE_TYPE=feature` + net = +2250 → BLOCK (≥
  1.5× hard).

## Dependencies

- Seed 3 (`task-soak-driver-pythonpath-fix.md`) does NOT block this
  task — the PYTHONPATH bug is at L1243/L1574; the dual-anchor work
  adds a new helper near the summary block. Can be fired in parallel.
- BUT — coordinate the merge order: if BOTH land in v2.3, sequence
  Seed 3 first (cleaner test env), Seed 4 second.

## Cycle-discipline (Amendment A scope analysis)

- Production (`src/`): 0 LOC. **NOT load-bearing.**
- Test (`tests/`): ~ 60 LOC. Advisory.
- Tooling (`tools/`): ~ 70 LOC additive (helper + summary block +
  stdout lines). **Soak driver counts as tooling, not src; advisory
  per Amendment A 3-bucket scope.**
- Docs: 0 LOC change beyond this prompt + ADR-18 acceptance tick.

## DoD

- [ ] `tools/soak_driver.py` renders dual-anchor block in markdown
      report + stdout.
- [ ] `tests/test_soak_summary_loc_anchors.py` PASSES.
- [ ] ADR-18 §"Amendments / Amendment A" L388 acceptance ticked.
- [ ] `docs/v2.3-next-steps.md` Seed 4 row updated:
      `[x] Seed 4 — soak summary renders both anchors PR #___`.
- [ ] v2.3 P2 ship-gate report (when fired) carries the dual-anchor
      block — verify by reading `reports/soak-<TS>.md` post-soak.

## Refs

- `docs/adr/ADR-18-mvp-surface-freeze.md` §"Amendments / Amendment A"
  L388, §"Amendments / Amendment C".
- `tools/soak_driver.py` summary section (L850-L870, L1810-L1820).
- `project_v22_cycle_close.md` §"Subagent observation worth
  remembering" (Amendment C anchor-discrepancy story).
- `docs/v2.2-backlog.md` §"Carry-forwards from v2.2" #4.
