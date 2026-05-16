# Task — v2.1 P4 Sonnet alignment dip: row-level audit (🟡 carry-forward)

> Investigation task. Surfaced at v2.1 P4 ship-gate. ADR-5 §"v2.1
> ship-gate baseline / Caveats" calls out the dip. Causally NOT
> PPP-attributable per v2.1 P4 close-out analysis. Promote to v2.2 P0
> sub-task OR run as standalone v2.1.1 patch cycle.

## What dropped

| Metric | v2.0 ship-gate | v2.1 ship-gate | Δ |
|---|---|---|---|
| Sonnet pass rate | 0.95 (19/20) | 0.8636 (19/22) | -0.0864 |
| Sonnet stable count | 20 | 22 | +2 |
| Sonnet pass count | 19 | 19 | 0 |
| Haiku pass rate | 0.95 (19/20) | 0.95 (19/20) | 0 |
| FR-OG-7 regressions | 0 | 0 | 0 |
| haiku-vs-sonnet regressions | 0 | 0 | 0 |

**Pass *count* unchanged.** Rate dropped because stability denominator
rose (+2 rows resolved stable-wrong).

## Hypotheses (ranked at v2.1 P4 close-out)

1. **Corpus rot (primary).** Golden verdicts on 2 newly-stable-wrong
   rows may no longer match modern Sonnet behaviour.
2. **Sonnet behavioural shift (secondary).** Model-side drift
   2026-05-07 → 2026-05-12 on those 2 rows.
3. **FALSIFIED — transient CLI latency variance.** Stability count
   ROSE 20 → 22; latency is not the explanation.

## Audit procedure

### Step 1 — identify the 2 rows

Diff per-row tables:

```bash
diff \
  <(grep -E '^[|] [a-z0-9_-]+' reports/alignment-eval-20260507T191138Z.md) \
  <(grep -E '^[|] [a-z0-9_-]+' reports/alignment-eval-20260511T185249Z.md)
```

Find the 2 rows whose Sonnet majority flipped golden-match →
golden-miss between v2.0 and v2.1 ship-gates. Record row IDs.

### Step 2 — replay each row (corpus-rot test)

For each identified row, run the prompt through `claude -p` against
current Sonnet. Compare:

- Current live Sonnet verdict.
- 2026-05-07 cassette Sonnet verdict (if cassette captured).
- Golden verdict in `tools/alignment_eval.py` golden set.

Decision matrix:

| Live = Golden | Cassette = Golden | Diagnosis |
|---|---|---|
| YES | YES | Transient flake — re-run; do not promote |
| NO | YES | Sonnet behavioural shift (H2 confirmed) → REQUIREMENTS amendment OR golden update with rationale |
| NO | NO | Corpus rot (H1 confirmed) → golden update; document |
| YES | NO | Cassette-side artefact; investigate cassette record/replay |

### Step 3 — document + close

- Update `docs/adr/ADR-5-latency-budget.md` §"v2.1 ship-gate baseline /
  Caveats" with row-level finding + disposition per matrix.
- If golden update required: file as a separate `chore(alignment):`
  PR referencing the 2 row IDs explicitly. NO bundling with cycle
  scope.
- If REQUIREMENTS amendment required: file as `docs(requirements):`
  PR referencing FR-OG-7 + the rule change.
- Update `docs/v2.1-backlog.md` §"Carry-forwards from v2.1" item 3
  status: 🟡 → CLOSED with disposition stamp.

## Promotion criteria

- 🟡 stays at v2.2 P0 disposition gate (carry-forward).
- 🔴 if v2.2 P0 reproduces the dip on a fresh-corpus + fresh-CLI
  control AND no row-level cause is found.

## ADR-18 posture

Audit itself is documentation + (possibly) golden-set update. No
FROZEN seam touched. LOC budget ~10–30 docs.

## DOD

- [ ] 2 specific row IDs identified + recorded.
- [ ] Replay procedure run for each row.
- [ ] Diagnosis matrix row recorded.
- [ ] ADR-5 caveat updated.
- [ ] v2.1-backlog item disposition stamped.
- [ ] If golden update OR REQUIREMENTS amendment fired: separate PR
      opened.

## Cross-references

- `reports/alignment-eval-20260511T185249Z.md` (v2.1 P4 baseline).
- `reports/alignment-eval-20260507T191138Z.md` (v2.0 P4 baseline).
- `docs/adr/ADR-5-latency-budget.md` §"v2.1 ship-gate baseline".
- `docs/v2.1-backlog.md` §"Carry-forwards from v2.1" → Alignment-
  recovery investigation entry.
- `tools/alignment_eval.py` (golden set source).
