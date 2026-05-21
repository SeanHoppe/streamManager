# 2026-05-21 implementation notes

> **Purpose:** Running journal of how this session's task-list execution diverges from or interprets [`docs/2026-05-21-task-list.md`](2026-05-21-task-list.md). Captures design decisions, deviations, tradeoffs, and open questions for the operator.
>
> **Aspirational baseline:** [`docs/2026-05-19-implementation-notes.md`](2026-05-19-implementation-notes.md) — same shape (scoping decisions → dispatch decisions → tradeoffs → open questions → landing log → end-of-session synthesis). D-1..D-9 deviation labels continue; new deviations resume at D-10.
>
> **Lifetime:** Discardable at v2.7 P0 cycle frame fire.

---

## Scoping decisions (pre-dispatch)

### D-10 — agent-dispatchable subset

Post-v2.6.0 ship state has 9 operator-bound items (O1..O9 in the task list) and 4 agent-dispatchable prep artifacts. The dispatchable subset is **one larger than the 2026-05-19 set** because v2.6 P2 ship-gate spawned two new content-/timeout-boundary seeds (v2.6-A + v2.6-A-T) and the J2-equivalent audit splits into two: (a) Seed v2.6-G step (2) timeout-tighten value selection (J2 this session) + (b) Seed v2.6-A row-10 re-measure protocol (J3 this session, NEW vs 2026-05-19 set).

**Why four, not three.** The 2026-05-19 set had a single audit-style job (J2 v2.4-G CLI timeout audit). The current state has two audit-style decisions queued at v2.7 P0 (step (2) cap value + row-10 re-measure design). Bundling them into one doc would risk the same operator-decision-conflation the 2026-05-19 D-3 lean-skeleton stance warns against. Two separate audits keep the decision surfaces clean.

### D-11 — J4 is a bundle (P0 skeleton + next-steps)

The 2026-05-19 set's J3 minted only the P0 skeleton. PR #191 (v2.6 PM-mint) showed the bundle pattern (P0 skeleton + next-steps in one PR) is preferred. J4 follows PR #191 precedent: one job authors two tightly-coupled files. Splitting them into J4a + J4b would force one of them to refer to the other before it lands, and both would need cross-PR coordination. Bundle is cleaner.

### D-12 — no PR per job

All four jobs are docs-only writes. Bundle into a single branch is preferable to one-PR-per-job because:

- The working tree is clean post-v2.6.0 ship; no carry-over staged work to disambiguate.
- Each artifact is small (~150–300 lines). Four small PRs is more review overhead than one bundle.
- None of the four artifacts touches frozen surface; ADR-18 risk surface is zero.

**Deviation flag.** If operator prefers one PR per artifact, J1 / J2 / J3 / J4 can split cleanly: J1 is a single-file edit; J2 + J3 are each new single-file writes; J4 is a 2-file + 1-directory write that could split into J4a (P0 skeleton) + J4b (next-steps) if the operator wants three PRs for v2.7 PM-mint surface.

**Default action without operator input:** leave artifacts in working tree, do not commit, surface to operator at session end.

---

## Dispatch decisions

### D-13 — parallel dispatch

J1 / J2 / J3 / J4 are independent (no shared file; no shared decision; each writes its own target path). Parallel dispatch per the "make independent tool calls in parallel" rule.

### D-14 — subagent type: general-purpose

Same reasoning as D-5 (2026-05-19). `caveman:cavecrew-builder` is bounded 1–2 file edits and refuses 3+ file scope. J4 bundles 2 new files + 1 new directory — within builder's hard scope cap, but the cross-file shape coordination (P0 skeleton ↔ next-steps decision surface mirror) is judgment-heavy and general-purpose is the safer pick. J1 (single-file edit), J2 + J3 (single new files) are all within builder scope, but for consistency with J4 and to keep all four agents on the same subagent type, general-purpose for all four.

### D-15 — firewall + polarity-flip constraints in every prompt

Same as D-6 (2026-05-19). Each spawned agent receives explicit reminders that:

- `C:\Users\SeanHoppe\VS\certPortal\` is OFF LIMITS (CLAUDE.md firewall).
- SM polarity-flip (default-exclude self from corpus/ingest) — non-binding here.
- Long-running tasks (>5 min) must launch from main thread — non-binding here.
- Code/commits/security write normal English; caveman mode is for chat only.

---

## Tradeoffs considered

### T-5 — Seed v2.6-G step (2) audit: recommend specific cap value vs range

**Considered.** Continue the v2.5 P0 J2 audit stance (range 30–45 s + measurement protocol; defer specific value).

**Rejected for J2 this session.** v2.5 P0 deferred because n was small (eval-time p99 was estimated from per-row observations, n=55 across runs). v2.6 P1 PR #196 instrumentation now yields **n=192** Sonnet wall-clock observations with p99 = 25.048 s. Sufficient signal to recommend a specific value (and document the residual uncertainty). The audit MAY still recommend a 2- or 3-candidate selection (e.g. "30 s conservative / 35 s default / 40 s generous") but should land on a primary recommendation. Operator overrides at v2.7 P0 fire as before.

**Default for J2:** primary cap recommendation + 1–2 alternates + per-candidate trade-off table. Concrete enough to act on; honest about the residual variance.

### T-6 — Seed v2.6-A re-measure: n=12 vs n=24

**Considered.** n=24 single-row re-measure would tighten the stable-INTERVENE confidence interval but doubles runtime (~6 min for the single row; ~6 min × 2 = 12 min total inside the v2.7 P2 alignment-eval window).

**Rejected.** n=12 is enough to distinguish "stable INTERVENE majority" (≥ 9/12) from "still unstable" (6–8/12) at reasonable confidence; n=12 doubles the v2.6 P2 S6.5 n=6 sample which is the meaningful comparison anchor. n=24 incurs ~2× cost for marginal signal gain. n=12 also fits within a ~3-min runtime budget (Sonnet p50 16s × 12 = 192 s ≈ 3.2 min) which the v2.7 P2 alignment-eval can absorb without extending the soak envelope.

**Default for J3:** n=12 fixture; protocol allows n=24 escalation if 6–8/12 reading lands.

### T-7 — J4 next-steps default-lean: feature, consolidation, or TBD

**Considered.** Pre-fill the v2.7 P0 cycle-type default-lean. Three plausible stances:

- **Feature default-lean:** Seed v2.6-G step (2) is ready (J2 evidence); Seed v2.6-C carries 4-cycle deferral pressure; both feature triggers.
- **Consolidation default-lean:** Alternation hygiene (v2.6 was feature; v2.7 alternates).
- **TBD (no default-lean pre-filled):** Let the operator choose at P0 fire without skeleton bias.

**Rejected feature + consolidation.** The 2026-05-19 J3 lean-skeleton stance (Q-2) was "do not pre-empt operator cycle-type call". v2.7 PM-mint should preserve that — TBD with both stances surfaced in the §"Default lean rationale" paragraph.

**Default for J4:** TBD. Document both stances in the rationale block; operator picks at fire time. (This is a slight deviation from v2.6 PM-mint PR #191 which pre-filled feature lean per /goal pre-authorization at PM-mint time. The /goal directive for this session does NOT pre-authorize a cycle-type; therefore TBD is the correct shape.)

### T-8 — bundle all four jobs into one subagent vs four subagents

Same as T-4 (2026-05-19). Parallelism wins on wall-clock; bundling provides no token savings; per-agent startup cost is negligible vs parallel time savings.

---

## Open questions (for operator)

### Q-5 — branch / commit / PR strategy

The four artifacts are docs-only writes. Same three options as Q-1 (2026-05-19):

1. Bundle into a single new branch — clean single PR; recommended.
2. Bundle into the current branch (none staged; working tree clean post-v2.6.0 ship). Effectively the same as option 1 but using main-tracking branch.
3. Four branches / four PRs — maximum reviewability; most overhead.

**Default action without operator input:** leave artifacts in working tree, do not commit, surface to operator at session end.

### Q-6 — J4 next-steps default-lean

Per T-7 above: TBD chosen. Operator may override at PM-mint review time (before P0 fire) to either feature or consolidation if they want the skeleton to record a default-lean. Default action: TBD shape preserved.

### Q-7 — Seed v2.6-G step (2) recommended cap value

J2 audit recommends a specific cap in the 30–45 s band. Operator may override at v2.7 P0 fire OR at v2.7 P1 mint (the actual `TIMEOUT_SECONDS` change lands at P1 if step (2) fires). Default action: J2 recommendation lands as the audit's primary recommendation; operator decides final value at P0/P1.

### Q-8 — Seed v2.6-A re-measure runner location

J3 protocol assumes re-measure runs at v2.7 P2 inside the alignment-eval row runner (per Seed v2.6-A `docs/v2.6-backlog.md` item 6 path (c)). Operator may instead choose to re-measure inside v2.7 P1 if step (2) timeout-tighten fires that phase (so the re-measure benefits from the new cap). Default action: protocol documents both placements; v2.7 P2 default; v2.7 P1 alternate path noted.

### Q-9 — PR #154 disposition

Carry from Q-4 (2026-05-19). Still prefixed `DRAFT` per `gh pr list --state open`. Out of scope this session.

---

## Landing log

> Updated as each job lands. Each entry: timestamp + job ID + path + size + acceptance verdict + any deviations from the spec.

### J1 — `docs/v10-mvp-status.md` refresh

- **Dispatched:** 2026-05-21 (parallel batch with J2 + J3 + J4).
- **Landed:** 2026-05-21. Diff scope clean (single-file edit), +21 / −14 = +7 net LOC.
- **Acceptance:** ✅ All 6 enumerated edits landed. Header `Last refresh` flipped to `2026-05-21 (post v2.6.0 ship, c3a964c)`. §3 P4 corpus block now carries Run 5 absence narrative + Run 6 (v2.5.1 P2 PR #190 `c1e9070` = 548) + Run 7 (v2.6 P2 PR #198 `c3a964c` = 608). §3 P4 narrative line reads "608 episodes / 408-row margin / 3.04× gate clearance". §4 held-chain rename Seed v2.4-C → v2.6-C; 4-consecutive-deferral count. §5 #112 row reflects v2.6-C blocker rename. §12 +3 crossrefs (`project_v25_cycle_close.md`, `project_v26_cycle_close.md`, `docs/v2.6-backlog.md`). §13 past-tense sweep through v2.6.0 ship; next decision = v2.7 P0 cycle-type call. Aggregate completeness narrative ~80% unchanged.

**Deviation D-10 — J1 net-line undershoot.** Spec target +20 to +40 net lines; actual +7 net. Cause: rename-heavy in-place rewrites of ~7 Seed v2.4-C → v2.6-C citations substitute rather than append. Content-wise every required edit landed. No spec-impact follow-up.

### J2 — `docs/seed-v2.6-g-step2-timeout-tighten-audit.md` author

- **Dispatched:** 2026-05-21 (parallel batch with J1 + J3 + J4).
- **Landed:** 2026-05-21. 272 lines (within 200–300 cap). Diff scope = single new file.
- **Acceptance:** ✅ All 8 required sections present. Primary cap recommendation: **30 s** (≈20% margin above Sonnet n=192 p99 25.048 s; closes Seed v2.6-A-T with 5.04 s margin vs the 2 s threshold). Alternates: 35 s (defensive against censored-sample artefact at 25 s cap) + 28 s (minimum-disturbance). Step (3) coupling: CARRY independently at 30 s primary (ops complexity outweighs +5 s prod-vs-eval split); BUNDLE only if operator picks cap ≥ 35 s. Sonnet n=192 p99 25.048 s cited verbatim with source `reports/alignment-eval-20260520T205842Z.{md,json}` + JSON key `summary.sonnet_duration_s_p99`. 5 cap candidates (28/30/35/40/45 s) evaluated with margin / v2.6-A-T close-check / false-timeout reduction / eval-runtime worst-case / production-path risk per row. §v2.7 P0 question decision block paste-ready. No FROZEN-surface edits.

### J3 — `docs/seed-v2.6-a-row10-remeasure-protocol.md` author

- **Dispatched:** 2026-05-21 (parallel batch with J1 + J2 + J4).
- **Landed:** 2026-05-21. 220 lines (top of 150–220 cap). Diff scope = single new file.
- **Acceptance:** ✅ All 9 required sections present, in order. Stability gate ≥ 9/12 INTERVENE → STABLE-CONTENT-DRIFT (75% threshold). Decision tree with 4 outcome paths (STABLE-CONTENT-DRIFT / STILL-UNSTABLE / VERDICT-DIVERSITY / STILL-100%-TIMEOUT-ESCALATE), each with disposition + carry-forward call. Runtime: ≈ 3.2 min minimum (corpus-p50 surrogate 16.14 s) / ≈ 4.58 min realistic (row-10 p50 22.891 s) / ≈ 5 min worst (row-10 p95 band); fits inside v2.7 P2 alignment-eval window without extending soak envelope. v2.6 P2 S6.5 n=6 facts cited verbatim (sonnet_runs, sonnet_majority 4/6, sonnet_stable false, timeout_count 1/6, p50/p95/p99/max 22.891 / 24.613 / 24.960 / 25.047 s, 24.5 s threshold). Seed v2.6-A-T coupling explicit (both conditions: step (2) cap-tighten lands + re-measured p99 ≥ 2 s under new cap). §v2.7 P2 question decision block paste-ready. No golden edits.

### J4 — v2.7 PM-mint bundle

- **Dispatched:** 2026-05-21 (parallel batch with J1 + J2 + J3).
- **Landed:** 2026-05-21. Two new files + 1 new directory:
  - `docs/prompts/v2.7-orchestration/phase-0-cycle-frame.md` — 617 lines.
  - `docs/v2.7-next-steps.md` — 495 lines.
- **Acceptance:** ✅ All structural requirements satisfied. ALL 25 decision-block checkbox lines UNCHECKED (verified via grep: 25 `[ ]` / 0 `[x]` in P0 skeleton); both cycle-type options blank + blank pick line; default-lean rationale paragraph surfaces feature + consolidation honestly. §Memory pre-flight cites `project_v26_cycle_close.md`. §Alignment-eval n=6 stability rule encodes prior_sonnet = 0.9412 → default `--runs 3` (v2.7 P2 entry condition; POSIX + PowerShell shell variants present). 12 seed entries (6 cap-counted + 6 EXEMPT); verbatim external-trigger citations for v2.4-I..N per Amendment E §"Acceptance". J2 + J3 outputs cited as evidence inputs for relevant decision blocks. ADR-18 Amendments A/B/C/D/E reference block with file:line cites (`:342`, `:403`, `:437`, `:515`, `:648`). Canonical S2 env block (`BRIDGE_RL_LOGGER_ENABLED=1` + `BRIDGE_LOC_PATHSPEC=src/,tests/,tools/,dashboard/`) verbatim from v2.6 P0. NO operator decision pre-empted.

**Deviation D-11 — J4 line-count overshoot.** Spec target 300–500 lines per file; actual P0 skeleton 617 / next-steps 495. Cause: v2.7 has 12 seeds vs v2.6's 11 (one extra cap-counted = v2.6-A-T), and the P0 skeleton carries 4 fire-decision blocks (Seed v2.6-G step (2) + step (3) + Seed v2.6-C + Seed v2.6-A re-measure) vs v2.6's 2 (Seed v2.5-G + Seed v2.5-C), which structurally pushes both files longer. No content trimmed to fit; flagged for operator review. Acceptance verdict still PASS — line count is advisory, structural requirements are load-bearing.

**Deviation D-12 — J4 single-attempt success, no retry.** D-7 retry-hardening note in J4 prompt (single-batch reads + one-shot writes per file) succeeded first attempt at 13 tool uses / ~365 s. The 2026-05-19 J3 socket-crash incident did not recur this session.

---

## End-of-session synthesis

### Jobs landed

All four agent-dispatchable jobs from `docs/2026-05-21-task-list.md` landed first-try (no retries).

| Job | Status | Tool uses | Notes |
| --- | ------ | --------- | ----- |
| J1 | ✅ LANDED first-try | 19 | Single-file edit, +21 / −14 = +7 net (D-10 undershoot, rename-heavy). |
| J2 | ✅ LANDED first-try | 23 | Single new file, 272 lines. Primary cap 30 s + alternates 35 / 28. |
| J3 | ✅ LANDED first-try | 37 | Single new file, 220 lines. ≥ 9/12 INTERVENE stability gate. |
| J4 | ✅ LANDED first-try | 13 | 2 new files + 1 new dir (617 + 495 lines; D-11 overshoot, 12-seed corpus + 4-decision surface). D-12 D-7 hardening succeeded. |

### Deviations surfaced during execution

- **D-10 — J1 net-line undershoot.** Spec +20 to +40; actual +7. Rename-heavy in-place edits substitute rather than append. Content-complete.
- **D-11 — J4 line-count overshoot.** Spec 300–500 per file; actual 617 + 495. Driven by 12-seed corpus (v2.6 had 11) + 4 fire-decision blocks (v2.6 had 2). No content padding; no content trim warranted.
- **D-12 — J4 single-attempt success.** D-7 (2026-05-19 J3 socket-crash) retry-hardening note in prompt succeeded first-try; no API-socket recurrence this session.

### Operator queue at session end

**Inherited from task list §"Operator-bound items":**

- O1 — Fire v2.7 P0 cycle frame (cycle-type decision).
- O2 — Seed v2.6-G step (2) timeout-tighten fire/defer at v2.7 P0 (J2 provides evidence).
- O3 — Seed v2.6-G step (3) env-split fire/defer at v2.7 P0.
- O4 — Seed v2.6-A golden-update vs DIP-watch hold at v2.7 P2 (J3 provides protocol).
- O5 — Seed v2.6-C 4th-consecutive deferral call at v2.7 P0.
- O6 — Seed v2.4-E p95 watch close-vote at v2.7 P2.
- O7 — Seed v2.4-F L4 half close-vote at v2.7 P2.
- O8 — PR #154 sign-off (carry from 2026-05-19 Q-4).
- O9 — v10 chain unblock via Seed v2.6-C Path-D if cycle = feature.

**New follow-ups surfaced this session:**

- **F-4 (from D-11).** J4 P0 skeleton 617 lines + next-steps 495 lines exceed predecessor v2.6 P0 (541) + v2.6 next-steps (440). Structural drivers: extra seed (v2.6-A-T) + extra fire-decision blocks. Operator may elect to trim at PM-mint review time OR accept; neither path blocks v2.7 P0 fire.
- **F-5.** Working tree carries 6 new docs (J1 modified + J2 + J3 new + J4 P0 skeleton + J4 next-steps new + this notes file + task-list file) + 1 new directory `docs/prompts/v2.7-orchestration/`. Operator picks branch/PR strategy (Q-5).
- **F-6 (carry from 2026-05-19 D-8).** Status-doc row-citation drift surfaced 2026-05-19 (rows 14/15/17/18 vs actual JSON 05/10/13/15/18). v2.6 cycle close absorbed/superseded the source doc (`docs/2026-05-19-status.md` is now historical; v2.6 backlog + next-steps are canonical). F-1 from 2026-05-19 is RESOLVED-BY-SUPERSESSION; no further action.

### Where v2.7 P0 picks up

When the operator is ready to mint v2.7 P0 fire:

1. Read `docs/prompts/v2.7-orchestration/phase-0-cycle-frame.md` (J4 output) — this is the skeleton.
2. Read `docs/seed-v2.6-g-step2-timeout-tighten-audit.md` (J2 output) — evidence input for the §"Seed v2.6-G step (2) fire decision" block.
3. Read `docs/seed-v2.6-a-row10-remeasure-protocol.md` (J3 output) — evidence input for the §"Seed v2.6-A re-measure decision" block.
4. Read `docs/v10-mvp-status.md` (J1 output) — current v10 chain state for context on §"Seed v2.6-C deferral/fire decision".
5. Read `docs/v2.7-next-steps.md` (J4 output) — comparison anchor for the cycle.
6. Fill in decision blocks in the J4 P0 skeleton; pull trigger.

All open questions in this notes file (Q-5 .. Q-9) should be resolved at or before that fire.
