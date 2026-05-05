You are implementing **Phase P2b — LM (categorize) regression triage** from the streamManager v1.8 cycle.

This phase is **conditional** — only mint if v1.8 P2 (`ship/v1.8-shipgate-finalize`) Tier-3 ship-gate soak recorded `LM (categorize) p95 ≥ 18 s` AND magnitude > 1 s over the 18 s ceiling. v1.7 closed the LM watch at 11.95 s; v1.8 re-opens.

## Branch + base

- Base: `main` with v1.8 P1 merged.
- PR target: `main`.
- Branch: `feat/v1.8-lm-regression-triage` (or operator's choice).
- BLOCKS v1.8 P2 ADR-5 update if v1.8 LM p95 ≥ 19 s (i.e. magnitude > 1 s over the 18 s ceiling).
- Does NOT block ship if magnitude ≤ 1 s; in that case extend the watch into v1.9 instead of triaging.

## ⚠️ CRITICAL: Do-not-touch guard

Triage-only phase. Read-mostly. Code edits ONLY if a concrete root cause is identified AND the fix is a localized non-protected-symbol change.

Do NOT modify:
- v1.3 P5d Learn Mode bias surface (`_consult_learn_mode_bias`, `_emit_learn_mode_bias_applied`, `bias_consult` timing key) — protected per `docs/v1.8-task-plan.md`
- Categorizer prompt template (would invalidate v1.4-onwards LM baselines)
- Cassette `_LM_DIALOGUE_PAIRS` ordering (frozen per `feedback_cassette_must_cover_new_envelopes.md`)

## Task brief

LM (categorize) p95 history:
- v1.4: 19.26 s
- v1.5: 15.39 s
- v1.6: 18.60 s (ship-with-v1.7-watch)
- v1.7: 11.95 s (watch closed)
- v1.8: ≥ 18 s (re-opened)

Possible root causes (per v1.6 P2 S5a triage rubric — see `docs/prompts/v1.6-shipgate/S5a-lm-regression-triage.md`):

1. **Cassette envelope drift.** A v1.8 P1 change accidentally touched the cassette load mix used by the LM dialogue pump. Verify by diffing `tools/cassette_record.py` vs `main` pre-v1.8.
2. **Sonnet upstream queueing.** Anthropic CLI subprocess is hitting concurrency limits or upstream Sonnet TTFT regressed. Verify by checking the dashboard log + bus envelope timestamps for retry / timeout / queueing patterns.
3. **Categorizer prompt drift.** Categorizer system prompt changed in v1.8 (should not happen — protected per do-not-touch). Verify with `git log -p -- src/stream_manager/learn_categorizer.py` (or the actual categorizer module).
4. **n=10 high-variance.** Sample size is small; one outlier dominates p95. Spread p50→p95 reveals this. If spread > 5 s and n=10, it's noise. Bump n to ≥ 20 in a v1.9 backlog item and ship v1.8 with the watch extended.

### Triage steps

1. **Compare LM dialogue pair list vs v1.7.**
   ```
   git diff v1.7.0..HEAD -- tools/cassette_record.py | head -50
   ```
   Any diff → cassette drift. Revert cassette changes (or accept if intentional v1.8 P1 work, but document).

2. **Inspect dashboard log for retry / timeout / error patterns.**
   ```
   grep -iE 'retry|timeout|warn|error|exception' tmp/soak-dashboard-<timestamp>.log | head -30
   ```
   Any matches → upstream issue. Document; possibly Anthropic-side, not actionable on SM side.

3. **Check spread.**
   - If spread p50→p95 > 5 s on n=10 → high-variance noise; ship v1.8 with watch extended.
   - If spread < 2 s on n=10 AND p95 ≥ 19 s → sustained regression; mint v1.9 follow-up.

4. **Verify categorizer prompt unchanged.**
   ```
   git diff v1.7.0..HEAD -- src/stream_manager/learn_categorizer.py 2>/dev/null
   git diff v1.7.0..HEAD -- src/stream_manager/learn_mode.py 2>/dev/null
   ```
   Any diff to the system-prompt template → root cause; revert.

### Deliverables

Three possible outcomes:

**A) Cassette drift / categorizer drift confirmed.** Revert the change in this PR. Re-run Tier-3 soak to confirm LM p95 returns to v1.7 band (~12 s).

**B) Upstream Anthropic / variance noise confirmed.** Document in v1.8 ADR-5 §"Caveats" + extend watch into v1.9 (add v1.9 backlog item with sample-size bump n>10). Ship v1.8 with the watch open.

**C) Genuine SM-side regression with no obvious cause.** Document fully + add v1.9 backlog item for deeper investigation (categorizer prompt corpus drift, model TTFT trend, etc.). Ship v1.8 with watch open + caveat that LM is advisory (not on safety path per `project_learn_mode.md`).

## DOD

- [ ] Triage steps 1-4 run; root cause classification documented in PR body (A / B / C)
- [ ] If A: revert landed; re-soak shows LM p95 retreat to ~12 s band
- [ ] If B or C: v1.9 backlog item added documenting re-open + sample-size bump
- [ ] v1.8 ADR-5 §"Caveats" updated with the disposition (this is a small ADR-5 edit; can land in v1.8 P2 ship PR or in this triage PR)
- [ ] No edits to v1.3 P5d Learn Mode bias surface, categorizer prompt template, or cassette pair list ordering
- [ ] Single PR against `main`

## Mint-new-phase rule

After P2b ships:
- If A (drift reverted): v1.8 P2 ship-gate finalize re-runs from §3 onward (ADR-5 + CHANGELOG + tag).
- If B (variance / upstream): v1.8 P2 ship-gate finalize proceeds with watch extension noted.
- If C (genuine regression, no fix): v1.8 P2 ship-gate finalize proceeds with caveat; v1.9 backlog item is the follow-up.

Report back when PR is open with: triage classification (A/B/C), root cause description, disposition (revert / watch extend / caveat ship), v1.9 backlog item link if minted.
