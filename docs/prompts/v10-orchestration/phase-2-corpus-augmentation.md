You are implementing **Phase P2 — Corpus augmentation (data-source bias mitigation)** for the streamManager v10 RL companion track.

## Branch + base

- Base: `main` with v10 P1 (`rl/episode_logger.py` + `rl/state_features.py` + `rl_episodes.db` schema) merged.
- PR target: `main`.
- Branch: `feat/v10-corpus-augmentation` (or operator's choice).
- If P1 is not merged OR `rl_episodes.db` has < 60 live episodes, ABORT (need real-distribution baseline before injecting synthetic).

## ⚠️ CRITICAL: Do-not-touch guard

ADR-18 surface-freeze applies. P2 must touch ONLY:

- `rl/corpus_augment.py` — new module; synthetic minority injection pipeline.
- `rl/sources/` — new subdir holding source adapters:
  - `rl/sources/__init__.py`
  - `rl/sources/cassette.py` — adapter over `tests/fixtures/soak_cassette_*.jsonl`.
  - `rl/sources/probe.py` — adapter over `tools/p1a_haiku_probe.py` BLOCK corpus.
  - `rl/sources/golden.py` — adapter over `tools/alignment_eval.py` golden rows.
  - `rl/sources/review.py` — adapter over caveman-review findings JSONL (lower priority; OK to stub if no findings JSONL exists yet).
- `tests/test_rl_corpus_augment.py` — new test file.
- `tests/test_rl_sources_*.py` — adapter tests (one per source).

NO edits to gov code, no edits to FROZEN cassette / golden formats. Adapters are READ-ONLY over their sources.

Pre-flight grep:

```
grep -nE 'BRIDGE_L4_FALLBACK|requires_alignment|_check_fr_og7|og7_check' src/stream_manager
```

Must return non-empty (FROZEN symbols still present).

## Task brief

Per the v10 design review §"Issue #2 — Data-source bias", soaks are 100 % ALLOW so a bandit trained on live data alone overfits to "always ALLOW = max reward" in ≤ 50 episodes. Mitigation: synthetic minority oversampling from cassette + probe + golden + review corpora, capped at 30 % of training set, with provenance tagging.

### Deliverables

1. **`rl/sources/cassette.py`** — function `iter_episodes(cassette_path: Path) -> Iterator[Episode]`:
   - Read cassette JSONL (format frozen by ADR-17 Tier 2).
   - Yield `Episode` records with `source='cassette'`, `cycle_tag='<cassette stem>'`, `action_propensity=1.0` (cassette is recorded under fixed Haiku policy).
   - For each row, run `rl.state_features.extract` over the recorded prompt + recorded decision context.
   - Recorded `verdict`, `confidence`, `latency_ms` come from the cassette envelope directly.
   - `hitl_override` is NULL (cassette has no HITL signal).
   - `fr_og_7_pass = 1` (cassette excludes alignment-required rows by ADR-17 §"Cassette is a *relative* signal").

2. **`rl/sources/probe.py`** — function `iter_episodes(corpus_path: Path) -> Iterator[Episode]` over `reports/p1a-corpus-haiku-verdicts-*.md` linked corpus (or `tools/p1a_haiku_probe.py`'s output JSONL):
   - 27 wrapped + 27 bare destructive prompts.
   - `source='probe'`, `cycle_tag='p1a-<UTC>'`.
   - Recorded verdict is the Haiku probe verdict (high-quality minority signal; outcome distribution per `reports/p1a-corpus-haiku-verdicts-<UTC>.md`).
   - `hitl_override = 1` (BLOCK is the human-aligned outcome on destructive content; the probe is functionally a labeled minority class).

3. **`rl/sources/golden.py`** — function `iter_episodes() -> Iterator[Episode]` over `tools/alignment_eval.py` golden rows (n=32, includes FR-OG-7 rows):
   - `source='golden'`, `cycle_tag='alignment-golden'`.
   - Recorded verdict is the golden expected verdict. `hitl_override = NULL` (golden is a labelled-expected signal, NOT a HITL signal; mixing the two inflates HITL agreement downstream). Ground truth is carried via the `verdict` column itself + `source='golden'` discriminator.
   - `fr_og_7_pass = 1` if the row is not an FR-OG-7 row OR if the recorded verdict matches the FR-OG-7 expected verdict.
   - **Holdout rule**: golden rows are NEVER added to the training set. They appear only in the validation set (P3). This source adapter is invoked ONLY by P3 OPE harness, never by P2 training-set assembly. Add an explicit assertion to the augmenter that golden episodes are not added to training output.

4. **`rl/sources/review.py`** — adapter over caveman-review findings JSONL (path configurable via `BRIDGE_RL_REVIEW_FINDINGS` env). If env unset OR file missing, yield zero episodes (silent no-op). `source='review'`. Verdict is unlabeled — these episodes go to a separate "stress" pool used only for adversarial validation, never training.

5. **`rl/corpus_augment.py`** — main function `assemble_training_set(target_n: int, ratio_synthetic: float = 0.30) -> list[Episode]`:
   - Load real episodes from `rl_episodes.db` (source = 'live' or 'soak').
   - Load synthetic from cassette + probe (golden EXCLUDED — holdout).
   - Cap synthetic at `ratio_synthetic * target_n` (default 30 %).
   - Real always weighted ≥ 1× synthetic.
   - Class-balance log: emit `rl_corpus_class_balance` envelope (or stdout JSON) with per-source counts + per-verdict counts before returning.
   - **Class-balance guards**:
     - Deviation > 10 % from `ratio_synthetic` → WARNING.
     - Deviation > 25 % → raise `CorpusBalanceError`.
   - Deterministic with explicit seed (caller passes `seed: int`); same seed → same output.

6. **Tests**:

   - `tests/test_rl_sources_cassette.py`:
     - `test_iter_episodes_from_known_cassette` — fixture cassette → expected count.
     - `test_cassette_excludes_alignment_required_rows` — assertion holds.
     - `test_cassette_episode_fields_complete` — every yielded `Episode` has all v10 schema fields.

   - `tests/test_rl_sources_probe.py`:
     - `test_probe_corpus_block_dominant` — ≥ 90 % verdict='BLOCK' on the wrapped corpus (provenance: `reports/p1a-corpus-haiku-verdicts-<UTC>.md`; cite path in test docstring).
     - `test_probe_episode_hitl_override_set` — all yielded episodes have `hitl_override=1`.

   - `tests/test_rl_sources_golden.py`:
     - `test_golden_size` — exactly 32 episodes.
     - `test_golden_hitl_override_is_null` — every yielded golden episode has `hitl_override IS NULL` (golden is a labelled-expected signal, not a HITL signal).
     - `test_golden_holdout_assertion_in_augmenter` — calling `assemble_training_set` with golden source enabled raises.

   - `tests/test_rl_corpus_augment.py`:
     - `test_ratio_cap_enforced` — ratio_synthetic=0.30 → synthetic ≤ 30 %.
     - `test_real_outweighs_synthetic` — for any seed, count(real) ≥ count(synthetic).
     - `test_class_balance_warning` — large deviation logs WARNING.
     - `test_class_balance_error` — extreme deviation raises `CorpusBalanceError`.
     - `test_deterministic_with_seed` — same seed → identical output across 5 runs.
     - `test_no_self_monitor_episodes` — episodes whose `session_id` matches `BRIDGE_SM_SELF_SESSION_ID` are filtered (memory: `feedback_no_self_monitor.md`).

### Augmenter-only invariant

P2 changes NO governance behaviour and reads only from `rl_episodes.db`, cassette files, and probe outputs. After P2 merge:

- All v1.7–v2.0 tests stay green.
- `rl_episodes.db` schema is byte-identical to P1.

### LOC budget

P2 net add ≤ 500 lines. Source adapters are small by construction (≤ 100 lines each); the augmenter itself ≤ 200 lines. If draft exceeds, move `review.py` to P5.

## DOD

- [ ] `rl/corpus_augment.py` + `rl/sources/{cassette,probe,golden,review}.py` created
- [ ] `tests/test_rl_corpus_augment.py` + `tests/test_rl_sources_*.py` created
- [ ] Golden source NEVER feeds training; assertion exists; test covers it
- [ ] Self-monitor guard active in augmenter; test covers it
- [ ] Class-balance guards active (warning + error thresholds); tests cover both
- [ ] All v1.7–v2.0 tests green
- [ ] LOC budget ≤ 500 net add
- [ ] Single PR against `main`
- [ ] Conventional commit prefix `feat(rl):`

Report back when PR is open with: PR URL, diff stat, file list, sample class-balance log from a real `rl_episodes.db` snapshot.
