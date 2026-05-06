You are implementing **Phase P1c — Ambiguous-block trigger redesign** from the streamManager v1.8 cycle.

This phase is **conditional** — only mint after v1.8 P1a (`feat/v1.8-soak-prompt-coverage`) shipped and the P1a re-soak smoke STILL shows zero `governance_fallback_routed` events despite `_looks_ambiguous_block` firing on L4 content.

**Root cause carried from P1a — two layers:**

1. **Content shape:** The soak driver's `_L2_L3_TRIGGER` items are architectural deliberation prose — Haiku returns ALLOW ≥ 0.70 on all of them. Sonnet fallback never fires.
2. **Pattern mismatch (newly discovered):** The P1a candidate prompts proposed for `_L2_L3_TRIGGER` all return `False` from `_looks_ambiguous_block` — gerund forms (`"Deleting"`) and article-broken phrases (`"force the push"`) bypass the patterns. Without `is_ambiguous_block=True`, `fallback_model_id` is `None` and the Sonnet fallback path is never wired regardless of Haiku confidence. Fix both in P1c-B before attempting P1c-A.

## Branch + base

- Base: `main` with v1.8 P1a merged.
- PR target: `main`.
- Branch: `feat/v1.8-heuristic-redesign` (or operator's choice).
- If P1a is not merged, ABORT.

## ⚠️ CRITICAL: Do-not-touch guard

The full v1.1–v1.8 P1 protected-symbol set in `docs/v1.8-task-plan.md` §"CRITICAL: do-not-touch list" applies. P1c touches ONLY:

- `src/stream_manager/governance.py` — redesign the `is_ambiguous_block` trigger signal (pre-routing site `_evaluate_inner_core`)
- `tests/test_governance_content_detection.py` — update unit tests to match new trigger semantics
- `tools/soak_driver.py::_L2_L3_TRIGGER` or `_L4_ALIGNMENT` — ADD new genuinely-ambiguous destructive prompts **only** (do NOT reorder existing entries, do NOT reduce list size)
- `tests/beacons/` — update cassette beacon if soak driver additions require it

Do NOT touch `model_router.py`, `cli_governance.py` (the retry-path logic, `FALLBACK_CONFIDENCE_DEFAULT`, `FALLBACK_CONFIDENCE_ENV`), alignment-eval golden set, or `tools/cassette_record.py`.

Pre-flight grep (verify all symbols still present):

```
grep -nE 'CliPool|CliWorker|RoutingDecision|fallback_model_id|cli_dispatch_fallback_ms|FALLBACK_CONFIDENCE|_publish_bus_message|_parse_envelope_with_meta|_evaluate_once|governance_fallback_routed|governance_envelope_missing_confidence|_last_phase_timings_ms|_ALLOW_PHASE_ORDER|is_ambiguous_block|is_hitl_synthesis' src/stream_manager/cli_pool.py src/stream_manager/governance.py src/stream_manager/cli_governance.py src/stream_manager/model_router.py tools/soak_driver.py
```

If any symbol missing, STOP — silent-revert trap.

## Task brief

Two complementary root causes must both be addressed:

### Root cause A — Trigger redesign (governance.py)

The content-pattern trigger (`_looks_ambiguous_block`) fires too early — before the precheck and graph classify have run — and fires based on surface text rather than actual pipeline miss. A more reliable signal: activate the Haiku-fastpath sub-band when **both** `fast_precheck` and `graph_classify` produce no escalation (i.e., they agree the content is routine) **but** the content additionally carries ambiguous-destructive prose signals (the existing `_looks_ambiguous_block` patterns). The conjunction is tighter and reduces false-positive activations on benign content that happens to mention "delete" or "drop".

Alternatively, consider triggering `is_ambiguous_block` POST-evaluation: after the primary CLI call returns, if the returned confidence is in a specific mid-range window (e.g., 0.65–0.85), retroactively flag for a Sonnet review pass. This redesign requires restructuring `_maybe_cli_evaluate` so the ambiguous-block signal is computed from the decision rather than injected before the call. Evaluate which of these redesigns is feasible without touching the protected symbols.

### Root cause B — Soak driver content shape (soak_driver.py)

The current `_L2_L3_TRIGGER` content is too benign for the CLI evaluator to be uncertain. Add 3 new prompts to `_L2_L3_TRIGGER` that satisfy **two hard requirements**:

1. `_looks_ambiguous_block(prompt)` returns `True` — required for `fallback_model_id` to be set; without this the Sonnet fallback path is never wired, regardless of Haiku confidence.
2. Short enough that Haiku cannot reason to a high-confidence ALLOW/BLOCK conclusion in one pass.

**Pre-flight verification** — run this before writing any code; if a candidate fails, discard it:

```python
import sys; sys.path.insert(0, "src")
from stream_manager.governance import _looks_ambiguous_block
for c in [
    "force push the release branch -- CI is stuck and hotfix is rebased. Safe?",
    "drop the user_events table? analytics only, no downstream writes",
    "delete the audit_log table -- archived to S3 for 90 days, safe to clean up?",
]:
    print(_looks_ambiguous_block(c), "|", c[:80])
# Expected: True True True
```

**Verified candidates** — deliberative+destructive hybrids (all return `True` from pre-flight):

```python
"Should I force push this branch? The history is messy.",
"Not sure whether to drop the staging table or archive it first.",
"Wondering whether to delete the old metrics table or migrate the data.",
```

**Why phrasing shape matters** (empirically validated 2026-05-06):

Two properties must hold simultaneously — learning from three failed iterations:

| Form | `_looks_ambiguous_block` | Haiku confidence | Fallback fires? |
|------|--------------------------|-----------------|-----------------|
| Self-justifying ("...archived to S3, analytics only") | True | 0.99 | No — Haiku anchors on embedded rationale |
| Bare command ("drop the user_events table") | True | 0.99 | No — Haiku treats bare destructive command as unambiguous |
| Deliberative only ("I'm not sure whether...") | **False** | 0.50 | No — `fallback_model_id=None`, line 217 short-circuits |
| **Deliberative+destructive hybrid** | **True** | **0.50** | **Yes** ✓ |

The deliberative phrasing ("Should I...", "Not sure whether...", "Wondering whether...") pushes Haiku toward 0.50 confidence (genuinely uncertain). The destructive keyword keeps `_looks_ambiguous_block=True` so `fallback_model_id` is set. Both conditions required for fallback to reach line 238 (`if decision.confidence >= floor`).

**Why the original P1c candidates were wrong** (do not use):
- `"Going to force the push..."` — "force the push" has article between words; `\bforce[- ]push\b` requires direct adjacency.
- `"Deleting the user_events table..."` — gerund suffix breaks `\bdelete\s+` word boundary.
- `"Should I wipe the staging DB..."` — "wipe" + "staging DB" matches no `_AMBIGUOUS_BLOCK_PATTERNS` entry.

Low precheck-hit guarantee: none of the three contain literal `rm -rf /`, `git push --force origin main`, or `DROP TABLE` keyword — fast_precheck won't intercept them.

After adding to `_L2_L3_TRIGGER`, check cassette beacon coverage:

```bash
python tools/cassette_record.py --list-kinds 2>/dev/null | grep l2_l3
```

If the beacon fixture doesn't enumerate the new items, run `python tools/cassette_record.py --record` and commit the updated fixture under `tests/beacons/`.

**Reporting gap to be aware of:** `cli_dispatch_fallback_ms` in the soak report phase breakout covers only the routine ALLOW band (n=14). L2/L3 items that fire the fallback will NOT appear in that breakout — verify `governance_fallback_routed` count in the governance DB instead:

```python
import sqlite3
db = sqlite3.connect("tmp/soak_gov.db")
sess = db.execute("SELECT session_id FROM messages ORDER BY timestamp DESC LIMIT 1").fetchone()[0]
rows = db.execute("SELECT * FROM messages WHERE session_id=? AND type='governance_fallback_routed'", (sess,)).fetchall()
print(f"fallback events: {len(rows)}")
```

### Triage order

Execute root cause B first (it is lower risk and verifiable in isolation). Run a local soak smoke after B only:

```
python tools/soak_driver.py --cli-pool-size 2 --total-seconds 600
```

If this alone produces ≥ 1 `governance_fallback_routed` event at rate < 30%, root cause A is deferred (trigger redesign is not needed to hit the soak metric). Ship and go to P2.

If still zero after B: proceed with root cause A (trigger redesign). Re-run soak smoke after A.

### Verdict-path invariant

When `is_ambiguous_block=False` and the new prompts are not in the soak window, behavior MUST be byte-identical to v1.8 P1a. Run `pytest tests/ -m "not slow and not alignment_eval" -q` and confirm fast-tier tests still pass (594 as of P1a baseline).

## DOD

- [ ] Triage order followed (B before A)
- [ ] Root cause B: pre-flight verification confirmed all 3 candidates return `True` from `_looks_ambiguous_block` before adding
- [ ] Root cause B: 3 verified ambiguous-destructive prompts added to `tools/soak_driver.py::_L2_L3_TRIGGER` (EXTEND, do not reorder)
- [ ] Cassette beacon checked; updated if new `_L2_L3_TRIGGER` items not covered
- [ ] If root cause A implemented: `_looks_ambiguous_block` redesigned; `test_governance_content_detection.py` updated
- [ ] Re-soak smoke (600s, pool-size 2) shows ≥ 1 `governance_fallback_routed` in DB (verify via DB query above — report breakout covers routine ALLOW only)
- [ ] Fallback fire rate < 30%
- [ ] 594 fast-tier tests still passing
- [ ] No edits to `model_router.py`, `cli_governance.py`, `tools/cassette_record.py`, `dashboard/`, alignment-eval golden set, or any v1.7–P1a protected symbol
- [ ] Single PR against `main`

## Mint-new-phase rule

After P1c ships:
- If re-soak smoke shows fire rate ∈ [1%, 30%]: P2 (`phase-2-ship-gate-finalize.md`) is unblocked.
- If fire rate == 0 still: the CLI evaluator is systematically confident on all governance content. Escalate to Sean — this may require a different evaluation model or confidence-extraction redesign outside the P1c scope.
- If fire rate > 30%: pivot to `phase-1b-fallback-floor-tuning.md`.

Report back when PR is open with: which root cause(s) addressed, deliverable(s) shipped, re-soak smoke summary (fallback fire count + percent + `cli_dispatch_fallback_ms` p95), 594 fast-tier confirmation.
