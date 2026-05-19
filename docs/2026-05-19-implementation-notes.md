# 2026-05-19 implementation notes

> **Purpose:** Running journal of how this session's task-list execution diverges from or interprets [`docs/2026-05-19-task-list.md`](2026-05-19-task-list.md). Captures design decisions, deviations, tradeoffs, and open questions for the operator.
>
> **Lifetime:** Discardable at v2.5 P0 cycle frame mint.

---

## Scoping decisions (pre-dispatch)

### D-1 — agent-dispatchable subset

The status doc's "What's next" list is 6 items, all of which are either operator-bound (cycle-type decision, promotion votes, ship-gate fires) or downstream of an operator gate (Path-D synthetic-fixture implementation requires the v2.5 P0 cycle-type call to be "feature"; v2.5 P2 watches require an actual ship-gate run).

The genuinely **agent-dispatchable now** subset reduces to three prep artifacts:

1. **J1** — refresh `docs/v10-mvp-status.md` (stale post-#111 closure + Amendment D + corpus 240 → 360).
2. **J2** — author the Seed v2.4-G CLI timeout audit (evidence prep for the v2.5 P0 promotion-to-🔴 decision).
3. **J3** — mint the v2.5 P0 cycle-frame skeleton prompt (matches the precedent set by PR #182 / #181 — mint phase prompts ahead of operator fire).

**Why three, not more?** Anything beyond these either needs a real ship-gate run (watch closures), an operator decision (cycle-type, promotion, sign-off), or the v2.5 P0 mint to have actually fired (Path-D fixture implementation, v2.5 phase prompts other than P0). Spawning a "stub" job for those would produce work that has to be redone after the operator decision lands.

### D-2 — no PR per job

All three jobs are docs-only writes. Bundling them into the existing branch (or operator-chosen branch) is preferable to one-PR-per-job because:

- The branch `fix/seed-v24-o-loc-pathspec` already has unrelated staged work (`docs/prompts/v2.4-orchestration/phase-2-ship-gate-finalize.md`, `docs/v2.4-backlog.md`, `tests/test_soak_summary_loc_anchors.py`, `tools/soak_driver.py`) carried from the PR #184 review-fix cycle. Operator will branch / PR appropriately when ready.
- Each artifact is small (~150–300 lines). Three small PRs is more review overhead than one bundle.
- None of the three artifacts touches frozen surface; ADR-18 risk surface is zero.

**Deviation flag.** If operator prefers one PR per artifact, J1 / J2 / J3 can be split cleanly because each touches exactly one new or modified file.

### D-3 — J3 prompt skeleton, not a fire

J3 mints the **skeleton** of `docs/prompts/v2.5-orchestration/phase-0-cycle-frame.md`. It does not fire P0, does not decide cycle-type, does not pre-empt any operator decision. The skeleton is a decision-bounded form the operator fills in at fire time. Precedent: PR #182 minted P2 ship-gate finalize prompt ahead of fire; PR #181 minted the Sonnet-DIP investigation prompt ahead of v2.4 P1.

---

## Dispatch decisions

### D-4 — parallel dispatch

J1 / J2 / J3 are independent (no shared file; no shared decision; each writes its own target path). Spawning in parallel is correct under the "make independent tool calls in parallel" rule.

### D-5 — subagent type: general-purpose

Each job is a self-contained doc author with a specific output path and acceptance criteria. The `caveman:cavecrew-builder` subagent is bounded to 1–2 file edits and refuses 3+ file scope, which fits — each of these jobs is a 1-file write. But the bounded-scope safeguard isn't load-bearing here; general-purpose is fine and avoids the caveman-builder refusal path for any unexpected cross-reference write (e.g. updating a sibling index file). General-purpose with explicit out-of-scope guards in the prompt is the safer pick.

### D-6 — firewall + polarity-flip constraints in every prompt

Each spawned agent receives explicit reminders that:

- `C:\Users\SeanHoppe\VS\certPortal\` is OFF LIMITS (CLAUDE.md firewall).
- SM polarity-flip (default-exclude self from corpus/ingest) — none of these jobs touch ingest paths, so this is a non-binding check, but the reminder is cheap.
- Long-running tasks (>5 min) must launch from main thread — none of these jobs run soaks; reminder is precautionary.
- Code/commits/security write normal English; caveman mode is for chat only.

---

## Tradeoffs considered

### T-1 — refresh `docs/v10-mvp-status.md` vs new file

**Considered.** Mint a new `docs/v10-mvp-status-2026-05-19.md` snapshot and leave the old file untouched.

**Rejected.** `docs/v10-mvp-status.md` is the *ledger* — a living document that the v10 orchestration prompts reference by path. Splitting it into dated snapshots breaks the references and forces every prompt to track which snapshot is "current". The refresh-in-place pattern is what the file's lifetime contract assumes.

### T-2 — Seed v2.4-G audit as docs vs as a JOB

**Considered.** File a `docs/jobs/seed-v2.4-g-cli-timeout-audit.md` JOB entry per the `docs/jobs/MASTER.md` pattern.

**Rejected.** `docs/jobs/*.md` are tracked issues with state machines; this is one-shot evidence prep that feeds a single operator decision at v2.5 P0. A flat doc under `docs/` is the right size. If the v2.5 P0 promotion decision spawns multi-cycle follow-up (e.g. timeout value tuning experiments), then minting a JOB at that point is the correct trigger.

### T-3 — v2.5 P0 skeleton location

**Considered.** Place the new prompt under `docs/prompts/v2.5/` (no `-orchestration` suffix) since the longer name was a v2.4-era convention.

**Rejected.** `docs/prompts/v2.4-orchestration/` is the established pattern (also `docs/prompts/v10-orchestration/` and `docs/prompts/v10x-orchestration/`). Continuity beats brevity here; the operator's muscle memory expects the suffix.

### T-4 — bundle all three jobs into one subagent vs three subagents

**Considered.** One subagent that authors all three artifacts sequentially.

**Rejected.** Parallelism wins on wall-clock. Bundling provides no token savings (each artifact reads disjoint context). The only risk to splitting is per-agent context startup, which is negligible vs the parallel time saving.

---

## Open questions (for operator)

### Q-1 — branch / commit / PR strategy

The three artifacts are docs-only writes. Operator can:

1. Bundle into the current branch `fix/seed-v24-o-loc-pathspec` (already has unrelated staged work) — efficient but mixes unrelated work.
2. Open a new branch for the three artifacts together — clean single PR; recommended.
3. Three branches / three PRs — maximum reviewability; most overhead.

**Default action without operator input:** leave the three artifacts in the working tree, do not commit, surface to operator at session end.

### Q-2 — v2.5 P0 skeleton: how much pre-loaded content?

Two stances are defensible for J3:

- **Lean skeleton** (recommended) — section headings + decision-block placeholders + cap-counted reading + Amendment cross-refs. Operator fills in at fire time.
- **Pre-loaded skeleton** — every section pre-filled with the most-likely operator answer (e.g. cycle-type pre-marked "consolidation" since Seed v2.4-C Path-D is the only feature trigger and may defer further).

**Default chosen:** lean skeleton. Pre-loading the cycle-type call would pre-empt the operator decision, which is exactly what the prompt is supposed to surface.

### Q-3 — Seed v2.4-G audit: name a specific replacement value?

The audit recommendation block can either:

- **Recommend a specific `TIMEOUT_SECONDS` value** (e.g. "30.0 s based on observed Sonnet p99 of ~27 s") — concrete but requires confidence in the p99 estimate.
- **Recommend a range + measurement protocol** (e.g. "30–45 s pending one more cycle of p99 sampling") — conservative; defers the specific value to v2.5 P1 or P2 if the promotion lands.

**Default chosen for J2:** recommend a range + measurement protocol unless the v2.4 P2 data supports a tight p99 estimate (n is small — 22 rows). Operator can override at v2.5 P0.

### Q-4 — PR #154 disposition

Out of scope for this session per the task list (operator-bound, O4). But noted here for awareness — title still prefixed `DRAFT` per `gh pr view 154` despite `isDraft=false` on the API. Either the title needs updating, the draft flag flipping back, or the PR closing.

---

## Landing log

> Updated as each job lands. Each entry: timestamp + job ID + path + size + acceptance verdict + any deviations from the spec.

### J1 — `docs/v10-mvp-status.md` refresh

- **Dispatched:** 2026-05-19 (parallel batch with J2 + J3)
- **Landed:** 2026-05-19. Diff scope clean (single-file edit), +53 / −22 / net +31 LOC.
- **Acceptance:** ✅ All criteria met. Sections changed: header date-stamp, §2 phase ledger (P4+P5 rows flipped), §2 aggregate completeness (~60% → ~80%), §3 P4 detail (READY → SHIPPED + #111 CLOSED + PR #179 `b35e982` + v2.3 PR #176 `cf7d003` + corpus 240 → 360), §3 P5 detail (Amendment D split + Seed v2.4-C as head-of-chain), §4 held-chain map (5-deep → 4-deep), §5 open follow-ups (#111 + #177 closed, #112 added), §12 cross-refs (Amendment D + Seed v2.4-C + `project_v10_p5_gate_deadlock.md` + `2026-05-19-status.md`), §13 sequencing paragraph rewritten to past-tense + v2.5 P0 next-step. Removed stale READY/BLOCKED/30%-of-200-gate language. No code-side changes; no deviations from spec.

**Sub-note (working-tree drift observed by J1 agent):** the session-start tracked changes (`M docs/prompts/v2.4-orchestration/phase-2-ship-gate-finalize.md`, `M docs/v2.4-backlog.md`, `M tests/test_soak_summary_loc_anchors.py`, `M tools/soak_driver.py`) are no longer in the working tree — they were absorbed by the PR #184 squash-merge. Branch is now at the post-merge state with only the docs/ artifacts from this session being modified. No action needed; flagged for operator awareness.

### J2 — `docs/seed-v2.4-g-cli-timeout-audit.md` author

- **Dispatched:** 2026-05-19 (parallel batch with J1 + J3).
- **Landed:** 2026-05-19. 289 lines (within 150–300 cap). Diff scope = single new file.
- **Acceptance:** ✅ All criteria met. Recommendation: **PROMOTE TO 🔴 with measurement-protocol stance** — promote at v2.5 P0, do not touch `TIMEOUT_SECONDS = 25.0` at P0, instrument per-run wall-clock in the alignment-eval row runner first (~30 LOC tooling, no FROZEN-surface touches), then choose a value in the **30–45 s range** at v2.5 P1/P2 backed by measured p99. p99 estimate **17–19 s, n=55** (5 consecutive soaks × 11 escalation envelopes; L4-only subsample n=20). Evidence rows cited: v2.3 row-08 `frog7-lifecycle-bridge-08` 3× NONE; v2.4 P2 row-10 `frog7-wirecli-module-10` 2× NONE; v2.4 P2 rows 05, 13, 15, 18 each 1× NONE.

**Deviation D-8 — J2 row citation correction.** The dispatch prompt cited "rows 14 / 15 / 17 / 18" as the v2.4 P2 timeout rows (lifted from the status doc's Seed v2.4-D summary). The actual `alignment-eval-20260519T101249Z.json` shows Sonnet NONEs on rows 05, 10, 13, 15, 18; row 14 is clean; row 17's NONE is on the haiku side. The audit doc follows the data and calls out the deviation explicitly in §"Evidence — empirical hooks". **Operator action item:** the status doc and Seed v2.4-D summary upstream of this audit have a stale row-citation; should be reconciled at v2.5 P0 (or earlier if the operator wants to update `docs/2026-05-19-status.md` and `reports/sonnet-dip-v23-v24.md`).

**Deviation D-9 — J2 line-count trim.** First-pass draft was 353 lines; trimmed to 289 to fit the 150–300 cap. No content omitted; redundancy and prose tightened. No spec impact.

### J3 — `docs/prompts/v2.5-orchestration/phase-0-cycle-frame.md` mint

- **Dispatched:** 2026-05-19 (parallel batch with J1 + J2). **First attempt crashed** with "API Error: The socket connection was closed unexpectedly" mid-flight; file not written (target path verified absent post-crash).
- **Re-dispatched:** 2026-05-19 with retry-hardened prompt (single Read + single Write to minimise crash-window).
- **Landed:** 2026-05-19 on retry. 315 lines + new parent directory `docs/prompts/v2.5-orchestration/`. 7 tool uses on retry vs 15 before first-attempt crash — hardening worked.
- **Acceptance:** ✅ All criteria met. Sections: Branch+base; Memory pre-flight (Rule 6); Cycle-type call; Rule 5 cap-counted reading; Seed v2.4-G promotion question; Seed v2.4-C deferral/fire decision; Seed v2.4-Q carry-forward; v2.4 carry-forward dispositions (quick-ref table); ADR-18 reference block (Amendments A=L342, B=L403, C=L437, D=L515, E=L648); Phase prompt stubs; DoD; Refs. Cap-counted = 5 (v2.4-Q + v2.4-C/E/F/G); EXEMPT = 6 (v2.4-I..N). Cross-refs: J2 audit doc, `docs/v2.4-backlog.md`, ADR-18, v2.4 P0 anchor prompt, PR #182 + #181 precedent, 5 minimum-re-read memories. **No operator decisions pre-empted**: cycle-type left as two unchecked options + blank pick line; Seed v2.4-G has all three dispositions (FREEZE / PROMOTE / NO-ACTION) unchecked; Seed v2.4-C FIRE/DEFER both unchecked with explicit cycle-coupling guard.

**Deviation D-7 — J3 retry.** First J3 attempt died on an API socket error after ~190 s of work (15 tool uses). Verified post-crash that the target file was not written. Re-dispatched with a single-Read-single-Write hardening note added to the prompt to minimise retry surface area on a second potential crash. Retry succeeded in 7 tool uses / 141 s.

---

## End-of-session synthesis

### Jobs landed

All three agent-dispatchable jobs from `docs/2026-05-19-task-list.md` landed.

| Job | Status | Tool uses | Notes |
| --- | ------ | --------- | ----- |
| J1 | ✅ LANDED first-try | n/a (single-agent) | Single-file edit, +53 / −22 LOC. |
| J2 | ✅ LANDED first-try | 27 | Single new file, 289 lines. Surfaced row-citation drift in status doc (D-8). |
| J3 | ✅ LANDED on retry | 15 (crashed) + 7 (retry success) | First attempt crashed mid-flight (API socket error). Retry-hardened prompt (single-Read-single-Write) succeeded in 7 uses. |

### Deviations surfaced during execution

- **D-7 — J3 socket crash + retry.** API socket closure mid-flight on first attempt; retry with hardening note succeeded cleanly. Cost: ~190 s wasted on first attempt + 141 s on retry vs ~140 s for a single clean run.
- **D-8 — Row-citation drift (J2).** Status doc + Seed v2.4-D summary cite v2.4 P2 timeout rows as 14/15/17/18; actual alignment-eval JSON shows Sonnet NONEs on rows 05/10/13/15/18 (row 14 clean; row 17 NONE is haiku-side). J2 audit follows the data and flags the discrepancy. **Operator action:** reconcile `docs/2026-05-19-status.md` §"Seed v2.4-G" + `reports/sonnet-dip-v23-v24.md` upstream of v2.5 P0.
- **D-9 — J2 line-count trim.** First-pass 353 lines → trimmed to 289 to fit cap. No content loss.

### Operator queue at session end

**Inherited from task list §"Operator-bound items" (unchanged):**

- O1 — Fire v2.5 P0 cycle frame (cycle-type decision).
- O2 — Seed v2.4-G promotion to 🔴 at v2.5 P0 (now backed by J2 audit doc).
- O3 — Seed v2.4-Q row-level disposition (at v2.5 P2 if 5th-cycle Sonnet 0.80–0.85 band holds).
- O4 — PR #154 sign-off (title still prefixed `DRAFT`).
- O5 — v2.3 / v2.4 phase fires post-mint (Path-D fixture, v10.x cycle frame, #124, #125).

**New follow-ups surfaced this session:**

- **F-1 (from D-8).** Reconcile row-citations: `docs/2026-05-19-status.md` and `reports/sonnet-dip-v23-v24.md` say rows 14/15/17/18; the JSON says 05/10/13/15/18. Quick docs edit; could fold into v2.5 P0 mint.
- **F-2.** J2 audit recommends instrumenting per-run wall-clock in the alignment-eval row runner before tuning `TIMEOUT_SECONDS`. ~30 LOC tooling (no FROZEN-surface touch). Becomes a v2.5 P1 task if Seed v2.4-G promotion lands at P0.
- **F-3.** Working tree carries 3 new docs + 1 modified doc + 2 session docs (task list + notes) + 1 new prompt directory. Operator picks branch/PR strategy (Q-1 in the open questions section).

### Where v2.5 P0 picks up

When the operator is ready to mint v2.5 P0:

1. Read `docs/prompts/v2.5-orchestration/phase-0-cycle-frame.md` (J3 output) — this is the skeleton.
2. Read `docs/seed-v2.4-g-cli-timeout-audit.md` (J2 output) — evidence input for the §"Seed v2.4-G promotion question" decision block.
3. Read `docs/v10-mvp-status.md` (J1 output) — current v10 chain state for context on the §"Seed v2.4-C deferral/fire decision" block.
4. Fill in the decision blocks in the J3 prompt; pull trigger.

All open questions in this notes file (Q-1 .. Q-4) should be resolved at or before that fire.
