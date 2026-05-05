# S9a — Ship PR fixups

**Goal:** Apply caveman-review findings on PR #87 before S10 merge. None
are blockers — accuracy/consistency cleanups + one ADR-5 rule
articulation.

## Context

`/caveman:caveman-review pr 87` surfaced 1 question, 3 risks, 6 nits on
the docs-only diff. No bugs, no security, no runtime risk. PR is
docs-only so all fixes are doc edits.

Findings being addressed (others deferred):

1. 🟡 `docs/prompts/v1.6-shipgate-checklist.md:L13` — S2 row stale
   `[~]`, should be `[x]` (soak finished + report consumed).
2. 🟡 `docs/prompts/v1.6-shipgate-checklist.md:L29` — mint rule names
   `S5a-lm-watch-extend.md`; actual mint = `S5a-lm-regression-triage.md`.
   Update rule to match what was minted.
3. ❓ ADR-5 v1.5 LM bullet — v1.4 watch criterion was "re-measure if next
   ship-gate also lands above 18 s". v1.6 = 18.60 s technically trips
   re-measure under the original rule. Articulate explicit
   sustained-vs-noise threshold (≥1 s magnitude over ceiling = sustained
   regression that re-measures; <1 s = noise band, ship-with-watch).
4. 🔵 ADR-5 v1.5 LM bullet — strikethrough "No v1.6 follow-up needed"
   instead of append-and-contradict.
5. 🔵 CHANGELOG — "PR #86, da0f271" → use merge SHA `380f453` (or drop
   SHA + keep PR cite).
6. 🔵 CHANGELOG — memory-file cite `feedback_soak_cli_pool_flag.md` is
   not a repo file; reader hits 404. Inline one-clause rationale.
7. 🔵 ADR-5 finding paragraph — `cli_pool.py:255` line cite will rot.
   Use symbol `CliWorker.send` for durable reference; keep filename for
   locator.
8. 🔵 v1.7-backlog Haiku fastpath item — alignment-eval gate buried in
   prose. Promote to its own bullet.

Findings deferred (justified):

- ADR-5 ship-SHA placeholder `<filled by S10>` — S10's job; not S9a.
- Session-log verbosity in checklist — live state, fine in repo.

## Steps

1. Edit each file per finding list above.
2. Single fixup commit `fix(v1.6 P2): caveman-review fixups for PR #87`.
3. Push to existing branch — PR #87 auto-updates.

## Acceptance

- All 8 findings addressed.
- No new files created (all edits in place).
- PR diff shows only the fixup commit on top of `8495f84`.

## On-done ack

`- [x] <fixup-sha> **S9a — Ship PR fixups** (8 findings addressed; ship SHA placeholder remains for S10)`

## Mint-new check

- If a fixup itself surfaces a new caveman-review finding round, mint
  `S9b-ship-pr-fixups-2.md`. Don't recurse more than once — at S9b,
  push back to S10 unless something is actively broken.
