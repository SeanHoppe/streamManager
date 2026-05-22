# v2.8 P0 — Cycle frame (Convergence cycle)

> **Minted at v2.7.1 P2 S13 (2026-05-22)** per v2.7.1 P2 prompt
> §"S13 — mint v2.8 P0 frame" + status doc `docs/2026-05-22-status.md`
> §"Proposal — Convergence cycle to move the needle, not the margin".
>
> **Skeleton scope.** This file bounds the v2.8 P0 decision surface and
> surfaces the §"Cycle-type call" + §"Bundle order" decision blocks.
> Operator fills decision blocks at P0 fire time. NO operator decision
> is pre-empted by this skeleton — the recommended frame (3-in-a-row
> FEATURE Convergence) is presented alongside the alternation-hygiene
> consolidation fallback per ADR-18 Amendment A §"Default lean
> rationale" honest-presentation rule.
>
> **Comparison anchor.** `docs/v2.8-next-steps.md` §"P0 frame —
> operator-bound decisions" (drafted alongside this frame in the
> v2.7.1 P2 ship-gate PR per PR #191 / PR #199 / PR #208 PM-mint
> precedent).

## Branch + base

- Base: `main` after v2.7.1 ship (v2.7.1 tag SHA filled at fire-PR
  open from v2.7.1 P2 S9 tag output).
- Branch: `feat/v2.8-p0-cycle-frame` (feature default; rename to
  `chore/v2.8-p0-cycle-frame` only if operator overrides to
  consolidation at fire time).
- PR target: `main`.

## §Memory pre-flight (Rule 6 — ADR-18 Amendment B)

Verify each load-bearing memory against current repo state before
opening P0 PR. If any cited memory is stale, update BEFORE opening
P0 PR. Record verification stamp in P0 PR body.

**Minimum re-read list for v2.8 P0** (operator may extend):

- `project_v271_cycle_close.md` (minted at v2.7.1 P2 S11) — v2.7.1
  ship reference; Hatch-B per-row exclusion outcome; Seed v2.7-B
  CARRY-WITH-EXCLUSION disposition.
- `feedback_certportal_dev_firewall.md` — dev-session firewall
  unchanged scope.
- `feedback_no_self_monitor.md` — polarity-flip rule unchanged.
- `feedback_alignment_eval_stability_window.md` — n=6 mandate +
  hatches (3) + (4); will be re-tested at v2.8 P3 ship-gate after
  cap-clip resolution.
- `feedback_soak_cli_pool_flag.md` — `--cli-pool-size 2` mandate
  unchanged.
- `feedback_parallel_operator_state.md` — `git fetch` + `gh pr list`
  before docs-mint subagent dispatch (v2.7.1 PM-mint collision
  precedent already absorbed at PR #208).
- `feedback_subagent_long_task_abandonment.md` — Tier-3 soak from
  main thread only.

**Stamp output (P0 PR body):** for each memory above, record
`fresh / updated-in-this-PR / superseded-by-X`. Empty stamp =
non-compliant (Amendment B §"Required output").

## §Cycle-type call

Decision-block (operator picks at P0 fire):

- [x] **FEATURE — Convergence cycle (RECOMMENDED).** 3-in-a-row
      feature (v2.6 + v2.7 + v2.8). Bundles 3 mutually-reinforcing
      landings; collapses next 2–3 cycles into one. Soft LOC ≤ 1500;
      BLOCK at 2250.
- [ ] **CONSOLIDATION — alternation-hygiene fallback.** Net LOC ≤ 0
      vs P0-merge tip per ADR-18 Amendment C. Defers Convergence
      bundle by 1 cycle.

**Default lean rationale (honest presentation).** Both stances are
surfaced so the operator weighs them at fire time without skeleton
bias.

- **(a) FEATURE / Convergence stance.** Status doc §"Proposal"
  argues that every open issue except Seed v2.6-C Path-D P5 is a
  side-quest; the held-chain depth is 4 issues deep behind one ~600
  LOC seed deferred 5 consecutive cycles. The Convergence cycle
  bundles:

    | # | Landing | LOC est. | Bucket            | Effect                                                                                                                                                       |
    |---|---------|---------:|-------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
    | 1 | Seed v2.6-C Path-D synthetic-fixture P5 | ~600   | `rl/` + tests     | Unblocks #112 → #131 → #124 + #125; collapses entire v10 tail                                                                                                |
    | 2 | Seed v2.6-G step (3) env-split          | ~50    | `src/cli_governance.py` + tests | Decouples prod-path user-wait from eval-path measurement; lets eval cap widen to 60 s for cap-clip resolution without prod-path latency risk                |
    | 3 | Seed v2.7-A-CLIP corpus-wide re-measure | 0      | reports only      | Surfaces true Sonnet response distribution; settles Seed v2.6-A content-drift verdict + Seed v2.6-A-T close-vote in one read; corroborated by Seed v2.7-B P1 |

  Total production-bucket delta: ~650 LOC. Well inside envelope
  (43% of soft cap).

- **(b) CONSOLIDATION stance.** Alternation hygiene argues every
  third cycle should clean up. v2.6 + v2.7 were both feature
  cycles; v2.7.1 corrective sub-cycle does NOT reset the
  alternation counter. Consolidation would land cap-clip
  investigation + step (3) env-split (~50 LOC) only and defer
  Path-D to v2.9. Marginal cost of NOT bundling = exactly 2 cycles
  ≈ 2–4 calendar days of operator time per status doc velocity
  gauge.

The recommended pick is **FEATURE / Convergence** because:

1. Backlog deflation count is 5-seeds-in-one-cycle (closes Seed
   v2.6-C, Seed v2.6-G step (3) parent, Seed v2.6-A, Seed v2.6-A-T,
   Seed v2.7-A-CLIP). Exits at 2 cap-counted (v2.4-E + v2.4-F
   watch-only).
2. Step (3) env-split is the structural fix the J2 audit
   falsification at v2.7 P2 demanded; the Convergence bundle is the
   first cycle where the operator can actually deliver it.
3. Path-D under Amendment D's v10.1-mode entry gate is
   infrastructure validation, not a writeback gate — the v10.3
   stochastic-propensity uncertainty does NOT block fire.

## §Bundle order

Decision-block (operator picks at P0 fire; applies only if FEATURE):

- [x] **P1 Path-D, P2 step (3) + cap-clip re-measure, P3 ship-gate
      (RECOMMENDED).** Path-D is the high-LOC item and benefits
      from the full cycle's CI exposure; step (3) + cap-clip
      re-measure is the lower-LOC measurement-bearing phase that
      validates the new eval-cap handling on top of Path-D's
      landing.
- [ ] **P1 step (3) + cap-clip re-measure, P2 Path-D, P3 ship-gate.**
      Lower-LOC fail-fast first; defer Path-D to mid-cycle. Risk:
      Path-D ~600 LOC has less CI exposure before ship.

**Default lean: option 1.** Path-D-first bundles the high-risk
landing into P1; step (3) env-split + cap-clip re-measure ride on
top in P2 with the new env-split shape proven safe by P1's CI.

## §Monitor target (operator binding at v2.8 P0 fire — 2026-05-22)

Decision-block (operator picks at P0 fire):

- [x] **certPortal sessions; peer SM sessions EXCLUDED (BOUND at v2.8
      P0 fire 2026-05-22).** v2.8 cycle testing routes JsonlTailWorker
      at certPortal session JSONL per polarity-flip rule (SM never
      self-monitors). Applies to all v2.8 phase fires (P1 Path-D
      shadow validation, P2 step (3) eval-cap measurement,
      P3 Tier-3 soak) AND v10 P4 corpus piggyback runs.
- [ ] **default (no operator binding); polarity-flip default-exclude
      stands; target unconstrained per phase.** NOT picked.

### Binding origin

Operator instruction at v2.8 P0 fire trigger (2026-05-22): *"do not
monitor peer sm sessions.. look to monitor certPortal for testing"*.
Cross-ref [[feedback_no_self_monitor]] §"Polarity flip" + CLAUDE.md
§"Session-source exception rule (polarity-flip)" + CLAUDE.md
§"Firewall: certPortal isolation" §"Runtime is unaffected".

### SM-side wire site (audit @ v2.8 P0 fire)

`dashboard/server.py:292-331` is the canonical JsonlTailWorker start
site. Polarity-flip refusal already wired (l.300-308): if target
slug ∈ SM-self set, dashboard logs operator-actionable warning + skips
start. No code change required at v2.8 P0 for the binding — it is a
pure env-var configuration applied at phase-fire time.

### Convention split — DIR-name vs ENVELOPE-emit slug

⚠ Live audit at v2.8 P0 fire surfaced a convention split in the wire
sites. There is no normalization layer in `src/stream_manager/
project_context.py`, so operator MUST supply both conventions in env
explicitly:

- **DIR-name slug (encoded form)** — used by
  `JsonlTailWorker._newest_jsonl` (`src/stream_manager/jsonl_tail.py:178`)
  as `projects_dir / project_slug`. The directories under
  `~/.claude/projects/` are encoded paths
  (`C--Users-SeanHoppe-VS-certPortal`, `C--Users-SeanHoppe-VS-streamManager`,
  + worktree suffix variants). `BRIDGE_PROJECT_SLUG` value MUST be
  the encoded form OR jsonl_tail silently emits zero rows.
- **ENVELOPE-emit slug (short form)** — emitted by SM governance into
  envelope `project_slug` field, compared against the SM-self set
  inside `rl/episode_logger.py:110`. Convention is the short literal
  (`streamManager`, `certPortal`).
- **Dashboard refusal at `dashboard/server.py:300`** compares
  `BRIDGE_PROJECT_SLUG` value (encoded) against `BRIDGE_SM_PROJECT_SLUGS`
  set by string-membership. Therefore `BRIDGE_SM_PROJECT_SLUGS` MUST
  contain BOTH encoded SM dir names AND short-form `streamManager`
  (and any short worktree-aliases) for the refusal to fire at both
  layers.

### Env-var mandate (binds v2.8 phase fires)

For every v2.8 phase that exercises JsonlTailWorker (soak,
ship-gate), the runtime env MUST set:

| env var                          | required value                                                                                                                                            | enforced by                          |
|----------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------|
| `BRIDGE_PROJECT_SLUG`            | encoded certPortal dir name `C--Users-SeanHoppe-VS-certPortal` (per `~/.claude/projects/` dir enumeration; primary, not worktree variant)                  | `dashboard/server.py:292` + `src/stream_manager/jsonl_tail.py:178` |
| `BRIDGE_SM_PROJECT_SLUGS`        | encoded SM dir set (all 12 from step (1) below) + short-form alias `streamManager` (envelope-layer refusal); comma-separated, no spaces                    | `dashboard/server.py:294-308` (encoded) + `rl/episode_logger.py:45,110` (short) + `tools/extract_gov_to_jsonl.py:200` |
| `BRIDGE_SM_SELF_SESSION_ID`      | this SM dev-session's session_id (refuses self-ingestion at envelope layer)                                                                                | `rl/episode_logger.py:105`           |
| `BRIDGE_PROJECTS_DIR`            | default `~/.claude/projects/` (unchanged)                                                                                                                  | `dashboard/server.py:312`            |
| `SM_OWN_SESSION_ID`              | bridge process session_id (filtered out of tail by `JsonlTailWorker._is_sm_originated`)                                                                    | `dashboard/server.py:322` + `src/stream_manager/jsonl_tail.py:144-146` |

### Scope clarification — what this binding actually redirects

- **JsonlTailWorker live tail** (dashboard process; learn-mode source):
  REDIRECTED by `BRIDGE_PROJECT_SLUG` to certPortal sessions. ← the
  new binding.
- **v10 P4 corpus piggyback** (`rl_episodes.db` writes via
  `rl/episode_logger.record_decision` when `BRIDGE_RL_LOGGER_ENABLED=1`):
  unchanged. Source is soak-emitted envelopes carrying short-form
  `project_slug` from SM governance engine. The polarity-flip refusal
  ensures self-exclusion (status quo). The "monitor certPortal"
  binding does NOT redirect soak-RL corpus to certPortal envelopes —
  v10 P4 piggyback continues to land soak-emitted rows minus SM-self.

### Operator action for v2.8 P1 fire-PR (pre-launch checklist)

Before launching any v2.8 phase that runs the dashboard / JsonlTailWorker:

0. **Restart dashboard process** so the FastAPI startup event re-runs
   `_start_jsonl_tail` and re-reads the env. The worker is started
   only at startup; live env changes do NOT propagate to an already-
   running worker.
1. Enumerate operator-local SM project dir names (encoded form):
   ```powershell
   Get-ChildItem $env:USERPROFILE\.claude\projects -Directory `
     | Where-Object { $_.Name -like '*streamManager*' } `
     | Select-Object -ExpandProperty Name
   ```
   — record full set in phase-fire-PR body. Verified at v2.8 P0 fire
   (2026-05-22): 12 encoded SM dirs on operator machine —
   `C--Users-SeanHoppe-VS-streamManager` + 11 worktree variants
   matching `C--Users-SeanHoppe-VS-streamManager--claude-worktrees-*`.
2. Export `BRIDGE_SM_PROJECT_SLUGS` containing every encoded slug
   from step (1) AND short-form alias `streamManager` (joint coverage
   per §"Convention split"). Comma-separated, no spaces. Example
   shape: `streamManager,C--Users-SeanHoppe-VS-streamManager,
   C--Users-SeanHoppe-VS-streamManager--claude-worktrees-...,...`.
3. Export `BRIDGE_PROJECT_SLUG=C--Users-SeanHoppe-VS-certPortal`
   (encoded dir name). Worktree variants of certPortal are NOT
   monitored by this binding; if operator picks a worktree target,
   substitute that encoded form.
4. Export `BRIDGE_SM_SELF_SESSION_ID=<current-session-id>`.
5. Verify dashboard log emits
   `jsonl_tail: started (... slug=C--Users-SeanHoppe-VS-certPortal ...)`
   (NOT the `REFUSED to start` line); persist log snippet in
   phase-fire-PR body as proof-of-binding.
6. If `~/.claude/projects/` contains no `C--Users-SeanHoppe-VS-certPortal`
   directory (fresh clone / new machine), abort the phase and surface
   to operator — do NOT attempt to read certPortal repo to bootstrap
   the slug (firewall holds; CLAUDE.md §"Firewall").

### Firewall reaffirmation

This binding is a **runtime-target configuration**, NOT a dev-session
licence to read certPortal repo files. SM dev session (this Claude
Code session) MUST NOT:

- Read any file under `C:\Users\SeanHoppe\VS\certPortal\` or
  `**/certPortal/**` (deny rules in `.claude/settings.local.json`
  fire if attempted).
- Glob / Grep into certPortal repo paths.
- Spawn sub-agents whose task is to triage certPortal repo issues,
  PRs, or JOBs.

What IS allowed: SM runtime (dashboard process, JsonlTailWorker,
governance loop, episode logger) reading
`~/.claude/projects/<certPortal-slug>/sessions/*.jsonl` at runtime —
that is the product surface. CLAUDE.md §"Firewall" §"Runtime is
unaffected" is the binding distinction.

## §LOC envelope

Feature cycle: soft target ≤ 1500 / BLOCK at 2250 per ADR-18
Amendment A. Cycle-tip anchor minted at P0-merge SHA (fill at fire
time).

Expected cumulative cycle-tip delta vs v2.8 P0-merge SHA:

- P1 Path-D: ~+600 LOC (`rl/` + tests).
- P2 step (3) env-split: ~+50 LOC (`src/stream_manager/cli_governance.py`
  + tests).
- P2 Seed v2.7-A-CLIP corpus re-measure: 0 production LOC (reports
  only).
- P3 ship-gate: 0 production LOC (docs + memory + ADR-5 +
  CHANGELOG only; conditional Hatch-A flip absent because v2.7.1
  P1 verdict B already disposed Seed v2.7-B).

Total expected: **~+650 LOC** (~43 % of soft cap).

## §Held-chain tail collapse (velocity-gauge effect)

Per status doc §"Velocity gauge — single-number read":

- **Pre-Convergence nominal:** v2.8 consolidation → v2.9 Path-D →
  v2.10 cap-clip → v2.11 shadow + freeze-lift = 4 cycles to v10
  MVP 100%.
- **Post-Convergence nominal:** v2.8 Convergence → v2.9 shadow +
  freeze-lift = **2 cycles** to v10 MVP 100%.

Marginal cost of NOT bundling = exactly 2 cycles ≈ 2–4 calendar
days of operator time.

## §Cycle-discipline carries from v2.7.1 P2

- **Cycle-tip anchor:** v2.8 P0-merge SHA (fill at fire). v2.7.1
  inherited `4902cca` per Amendment C; v2.8 mints a fresh anchor.
- **WIRED_LEVER_LEDGER:** posture exits v2.7.1 at **3 production /
  0 soak** unchanged. v2.8 step (3) env-split brings ledger to **4
  production / 0 soak** (4th FROZEN-surface lever wire on
  `cli_governance.py` — `TIMEOUT_SECONDS` already wired at v2.7 P1;
  step (3) extends that classification to cover
  `BRIDGE_CLI_TIMEOUT_EVAL` env-driven override).
- **ADR-18 Rule 5 (backlog cap):** Pre-cycle = 7 cap-counted (6 +
  Seed v2.7-A-CLIP). Convergence cycle closes 5 seeds
  (v2.6-C / step (3) parent / v2.6-A / v2.6-A-T / v2.7-A-CLIP);
  exits at **2 cap-counted** (v2.4-E + v2.4-F watch-only). Massive
  backlog deflation.

## §Goal-cadence pre-authorization

NO `/goal` pre-authorization signal issued at this v2.7.1 P2 S13
mint. Operator picks cycle-type at v2.8 P0 fire without prior
implicit lean — the §"Cycle-type call", §"Bundle order", and
§"Monitor target" (added at v2.8 P0 fire 2026-05-22) decision
blocks above are the only sanctioned binding paths.

## Cross-refs

- `docs/2026-05-22-status.md` §"Proposal — Convergence cycle" —
  source proposal text + LOC + velocity reasoning.
- `docs/v2.8-task-plan.md` — companion v2.8 task-plan skeleton
  (minted at v2.7.1 P2 S13).
- `docs/v2.8-next-steps.md` — companion v2.8 next-steps skeleton
  (minted at v2.7.1 P2 S13); operator-bound decision blocks.
- `docs/seed-v2.7-a-clip-corpus-protocol.md` — J5 protocol for the
  P2 corpus re-measure landing.
- `project_v271_cycle_close.md` — v2.7.1 ship close memory; load-
  bearing for P0 pre-flight.
- ADR-18 Amendment A (3-bucket LOC) — feature soft 1500 / BLOCK
  2250 applies.
- ADR-18 Amendment D (v10 P5 gate split) — Path-D fires under
  v10.1-mode entry gate; no v10.3 dependency.
- v2.6 P0 (PR #200 `4902cca`) — most recent FEATURE precedent.
- v2.7 P0 (PR #200) — 2-in-a-row FEATURE precedent (Amendment A
  §"Default lean rationale" honest presentation source).

## DoD (P0 frame mint)

- [x] Cycle-type call decision block filled at fire (Q-A = FEATURE /
      Convergence; default lean accepted).
- [x] Bundle order decision block filled at fire (Q-B = option 1; default
      lean accepted).
- [x] Monitor target decision block filled at fire (Q-D = certPortal;
      operator binding 2026-05-22).
- [x] LOC envelope numbers re-confirmed against latest
      cycle-tip-merge SHA (v2.7.1 tag `5e971b4` is predecessor;
      v2.8 P0-merge SHA fills at PR merge — separate backfill PR per
      v2.7 P0 / PR #201 precedent).
- [x] Memory pre-flight stamp recorded for the minimum re-read list
      (7 memories verified fresh; stamp body staged in
      `tmp/v2.8-p0-pr-body.md` pending `gh pr create` by operator —
      `gh pr create` denied twice for this session's permission scope).
- [x] Cross-refs verified live (no broken citations).
- [x] Operator records any deviation from §"Default lean
      rationale" recommendation (none — all defaults accepted; sole
      additive binding is Q-D monitor target).
