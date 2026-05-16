# Gap 5 — Project-context rank + 400-token budget invariant (backlog seed)

> **Disposition 2026-05-16 at v2.2 P0 mint: GRADUATED to
> `docs/v2.2-backlog.md`** §"INTENT.md gap-analysis seeds (GRADUATED
> 2026-05-16 at v2.2 P0)". Promotion criterion below remains the
> gate before this prompt fires.
>
> Minted from `docs/intent-todo-gap-2026-05-16.md` §Gap 5. **Backlog
> seed** — promotion-gated. Stays in `docs/v2.2-backlog.md` until
> criterion fires.

## Why

INTENT.md §"Project context loading" (verbatim claims):

- "All `*.md` files in the governed project root are loaded, ranked
  by governance relevance."
- "Rank order: INTENT > REQUIREMENTS > CLAUDE.md > README > others."
- "Context refreshes mid-session (10 s debounce) when any monitored
  file changes."
- "The 400-token budget for alignment checks is consumed by ranked
  excerpts, not full file dumps."

Zero regression test today. Any refactor of `project_context.py`
could silently invert rank order or blow the 400-tok budget without
ship-gate flagging.

## Promotion criterion (re-stated)

PROMOTE this seed to v2.x P-N when **any** of:

1. A PR touches `src/stream_manager/project_context.py`.
2. INTENT-priority field rank changes (rank-list edit in INTENT.md
   §"Project context loading").
3. Sonnet-alignment dip recurs AND root cause traces to context-
   loading drift (e.g. wrong file ranked first, budget overflow).

Until then: speculative. Do NOT promote.

## Deliverable shape (when promoted)

### 1. Rank-order test

`tests/test_project_context_rank.py`:

- Synth fixture project dir with all five rank-list files +
  decoys.
- Call ranker (likely `project_context.rank_files()` or
  equivalent).
- Assert returned order = `[INTENT, REQUIREMENTS, CLAUDE, README,
  ...others]`.
- Negative: synth a project with `INTENT.md` missing → assert
  fallback per INTENT line ("If the file is missing, governance
  falls back to README/CONTRIBUTING/manifests").

### 2. Budget-cap test

`tests/test_project_context_budget.py`:

- Synth fixture with one file ≥ 10× 400 tokens.
- Assert serialised context excerpt ≤ 400 tokens (use any tokenizer
  approximation already in repo — `len(text.split())` if no
  tokenizer present; otherwise `tiktoken`).
- Assert ranked-excerpt strategy (NOT raw file dump) — first chunk
  is from highest-ranked file, not arbitrary.

### 3. 10-s debounce test

`tests/test_project_context_debounce.py`:

- Tap context-refresh callback.
- Issue 5 rapid file-change events within 1 s.
- Assert callback fires ≤ 1× within 10 s window.

## Cross-refs

- INTENT §"Project context loading" — all four bullets.
- `src/stream_manager/project_context.py`.
- Gap doc §"Gap 5 — Project-context rank + 400-token budget".
- `docs/v2.2-backlog.md` §"INTENT.md gap-analysis seeds" — paired
  seed entry.

## DOD (when promoted)

- [ ] Three regression tests landed (rank, budget, debounce).
- [ ] Confirm `project_context.py` semantics match INTENT line-by-
      line; flag any drift in the same PR.
- [ ] Backlog seed in `docs/v2.2-backlog.md` struck (or
      `docs/v2.3-backlog.md` etc).
- [ ] Gap doc §Gap 5 LANDED.

## ADR-18 posture

- Test-only. EXPERIMENTAL on land.
- LOC estimate: ~150 tests. Negligible.
- No DORMANT-N implication.
