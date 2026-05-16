# Gap 6 — Learn-mode ALLOW-promotion regression coverage (backlog seed)

> Minted from `docs/intent-todo-gap-2026-05-16.md` §Gap 6. **Backlog
> seed** — promotion-gated. Lives at `docs/v2.2-backlog.md` until
> criterion fires.

## Why

INTENT.md §"What governance should learn from this project" lists
four routine commands that "should promote to ALLOW patterns
quickly":

- `pip install -e ".[dev]"`
- `pytest`
- `ruff check`
- `mypy`

Plus the broader rule: "File edits under `src/stream_manager/**`
are routine. File edits under `spikes/**` are throwaway and lower-
stakes."

No regression test today. Learn-mode (v1.3) silently regressing
promotion thresholds or pattern-matchers would only surface as
operator friction days later.

## Promotion criterion (re-stated)

PROMOTE this seed when **either**:

1. Learn-Mode telemetry shows promotion count drop ≥ 30% week-
   over-week (compare against `learn_mode` table rolling counts).
2. User reports a routine command (e.g. `pytest`, `ruff check`)
   failing to promote after the documented threshold (N
   observations within M sessions — pull current thresholds from
   `src/stream_manager/learn_mode.py` or equivalent).

Until then: speculative. Do NOT promote.

## Deliverable shape (when promoted)

### 1. Promotion-graduation regression test

`tests/test_learn_mode_allow_promotion.py`:

- Fixture: synth N observations of `pytest` invocation across
  M synth sessions (where N, M = current promotion threshold).
- Run learn-mode ingest path.
- Assert `pattern_promotions` (or equivalent table) gains a row
  with `pattern="pytest" AND mode="ALLOW"`.
- Repeat for `pip install`, `ruff check`, `mypy`.
- Negative: synth N-1 observations → assert NO promotion (off-by-
  one guard).

### 2. Path-class promotion test

`tests/test_learn_mode_path_class_routine.py`:

- Synth N observations of edits under `src/stream_manager/**`.
- Assert path-class graduates to "routine" tier (lower friction
  on next-encounter).
- Repeat for `spikes/**` → assert "throwaway / lower-stakes" tag
  applied (NOT auto-ALLOW; lower-friction not zero-friction).

### 3. Telemetry-drop sentinel (optional — only if metric path
exists)

If learn-mode emits weekly promotion-count metric:

- `tests/test_learn_mode_telemetry_sentinel.py`: synth two adjacent
  weeks of input; assert promotion-count metric within tolerance
  band of expected count. Drift > 30% = test fails loudly.

## Cross-refs

- INTENT §"What governance should learn from this project".
- `src/stream_manager/learn_mode.py` (or wherever current learn-mode
  ingest path lives — confirm at promotion time).
- Memory `project_learn_mode.md`.
- Gap doc §"Gap 6 — Learn-mode ALLOW-promotion regression".
- `docs/v2.2-backlog.md` §"INTENT.md gap-analysis seeds" — paired
  seed entry.

## DOD (when promoted)

- [ ] Promotion-graduation test landed (all four commands +
      off-by-one negative).
- [ ] Path-class test landed (src/stream_manager + spikes).
- [ ] Telemetry-drop sentinel landed IF metric path exists.
- [ ] Backlog seed struck.
- [ ] Gap doc §Gap 6 LANDED.

## ADR-18 posture

- Test-only. EXPERIMENTAL on land.
- LOC estimate: ~200 tests + ~10 src adjustments (if telemetry
  hook absent). Negligible to small.
- No DORMANT-N implication (no new lever wired).
