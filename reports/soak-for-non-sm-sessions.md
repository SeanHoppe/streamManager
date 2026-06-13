# How the soak process works for non-SM sessions

**Status:** Explainer (directive #2 + #r1). Read-only synthesis; no runtime change.
**Scope:** what "soak" means in SM, the three tiers, and -- critically -- the
gap between the *synthetic* soak the driver runs today and the *live non-SM
Claude session* soak the project rule (`#r1`,
`feedback_soak_needs_live_non_sm_session.md`) actually asks for.
**Denominator note:** counts below are pinned to the artifacts cited; they do
not silently re-baseline.
**ASCII-only (cp1252).** Dash = "--".

---

## 1. The two things called "soak"

There are two distinct activities, and conflating them is the main source of
second-guessing:

| | A. Synthetic soak (what `soak_driver.py` runs) | B. Live non-SM-session soak (what `#r1` means) |
|---|---|---|
| Load source | a hard-coded synthetic message mix inside the driver | a real local `claude -p` session in a non-SM project, tailed via learn-mode JSONL |
| Drives | `GovernanceEngine.evaluate` directly | the JsonlTailWorker -> bus -> governance path end to end |
| Polarity | N/A (no session rows; pure engine input) | load-bearing: the monitored `project_slug` MUST NOT be `streamManager` |
| Purpose | latency + plumbing + pool-warmup regression | does governance behave correctly against *real* operator/agent traffic |
| Source of truth for | ADR-5 latency budget (Tier 3 only) | empirical shadow validation (`#112` chain) |

Both are legitimate. A. is the cheap, repeatable harness; B. is the thing the
MVP gate (`#112` -> `#131` -> `#124/#125`) is actually blocked on.

---

## 2. A. The synthetic soak driver -- mechanics

`tools/soak_driver.py` (docstring `tools/soak_driver.py:1-29`):

1. Spawns the dashboard server (uvicorn) on the requested port
   (`tools/soak_driver.py:7-8`).
2. Spawns the SSE consumer `tools/soak_sse_consumer.py` so a driver hang does
   not corrupt event-count metrics (`tools/soak_driver.py:9-11`).
3. Builds a `GovernanceEngine` wired to a soak-only WAL DB
   (`tmp/soak_gov.db` by default) and pumps **60 synthetic messages** through
   `engine.evaluate`, one per `--interval-seconds` for `--total-seconds`
   (`tools/soak_driver.py:12-17`).
4. The load mix is **50 routine ALLOW patterns + 5 L2/L3-trigger prose + 5
   longer L4-alignment prose** (`tools/soak_driver.py:60-90`, `_ROUTINE` list).
   The mix is shuffled with a fixed seed so a window sees a representative
   interleave and the same seed reproduces the same order.
5. Per-minute `psutil` metrics for the server PID (RSS, FD/handle count,
   gov.db row counts) are tracked (`tools/soak_driver.py:17-19`).
6. After the publish loop a tail window lets the SSE consumer flush, then
   everything shuts down and a markdown report is written to
   `reports/soak-{ISO-ts}.md`; exit 0 PASS / 2 FAIL
   (`tools/soak_driver.py:18-28`).

**Key fact:** the synthetic mix is SM-authored prose. It is *not* a real
session transcript, so the polarity rule has nothing to exclude here -- there
are no session rows to leak. The driver tests the engine + pool + bus + SSE
plumbing, not the learn-mode tail path.

---

## 3. The three tiers (ADR-17)

From `docs/adr/ADR-17-soak-tiers.md` + `docs/soak-trigger-matrix.md`:

- **Tier 1 -- replay (0 quota).** `soak_driver.py --cli-replay <cassette.jsonl>`.
  No real `claude` subprocess; each cassette line is a canned envelope replayed
  with its recorded latency. Tests plumbing only
  (`ADR-17:26-37`). `--cli-replay` short-circuits before the `claude`-on-PATH
  check (`ADR-17:71-78`); `tests/test_soak_replay.py` runs it with PATH
  scrubbed of `claude`.
- **Tier 1.5 -- smoke (~6 real calls, ~90 s).**
  `soak_driver.py --cli-pool-size 2 --total-seconds 120 --interval-seconds 20`.
  Binary gate: pool warmed (`cli_pool_send_ms` p95 finite) + clean shutdown.
  NOT a latency gate, NOT an alignment gate (`ADR-17:116-160`). This is the
  per-PR gate for the four FROZEN hot surfaces (`docs/soak-trigger-matrix.md`).
- **Tier 2 -- cassette record (~60 Haiku calls).** `tools/cassette_record.py`
  records a real Haiku soak to `tests/fixtures/soak_cassette_<date>.jsonl`.
  Cassette p95 is a *relative* signal only -- compare cassette-to-cassette, never
  to the ADR-5 budget (`ADR-17:59-68`).
- **Tier 3 -- ship-gate (~60 real calls, ~32 min).**
  `soak_driver.py --cli-pool-size 2`. The **only** tier whose numbers feed the
  ADR-5 latency budget (`ADR-17:50-58`). Release-tag PRs also run alignment-eval
  `--ci-gate` (sonnet >= 0.95, haiku >= 0.85, 0 FR-OG-7 regressions).

**Operator obligation:** always pass `--cli-pool-size 2`. The default of 0
silently reproduces the v1.0 cold-start latency regression
(`feedback_soak_cli_pool_flag.md`).

---

## 4. B. The non-SM-session requirement -- where it actually bites

The project rule says: *testing/soaking must be driven by an active local
Claude CLI session in a non-SM project (certPortal etc.); stale fixtures /
self-loop do not satisfy* (`feedback_soak_needs_live_non_sm_session.md`).

Two separate concerns ride on this:

### 4.1 Polarity (the hard rule)

SM monitors NON-SM sessions, never itself (CLAUDE.md "Session-source exception
rule"). For any corpus / replay / ingest / OPE / training path reading from
`.claude/gov.db` or transcripts:

```
INCLUDE iff session.project_slug NOT IN (STREAM_MANAGER_PROJECT_SLUGS)
        AND session_id != BRIDGE_SM_SELF_SESSION_ID
```

- `project_slug` is the durable read-side key (the SQL `WHERE` self-exclusion).
- `session_id != BRIDGE_SM_SELF_SESSION_ID` is the load-bearing WRITE-time gate
  (`episode_logger` raises `SelfMonitorRefusal`; env-conditional) plus a cheap
  read-time Python backstop -- not the durable selector.
- Default-exclude is deliberate: leakage shows up as zero rows (loud), never as
  silent corpus poisoning.

The synthetic soak (section 2) sidesteps polarity because it has no session
rows. The moment a soak is fed a *real* session (the thing `#r1` asks for),
polarity is the first thing that must hold.

### 4.2 The live tail path is what makes it a "real" soak

A genuine non-SM-session soak exercises:

`live claude -p session (non-SM cwd)` -> `JsonlTailWorker` tails its JSONL ->
`MessageBus` envelopes -> `GovernanceEngine` -> `gov.db` decisions -> dashboard.

The synthetic driver injects at the `engine.evaluate` step and therefore skips
the tail -> bus front half entirely. That front half is exactly where
learn-mode bias + source-label + self-exclusion live.

### 4.3 Live evidence this path works today

The operator walkthrough (directive #3, `reports/ui-next-walkthrough.json`)
confirmed the live dashboard is rendering a real non-SM monitored corpus from
`.claude/gov.db`: **21366 decisions, 1252 "active" sessions**, Frame A scoped to
a real governed session (`pid 33804`) with OBSERVING decisions flowing. So the
runtime tail->bus->governance->dashboard chain is live against non-SM traffic
right now -- what is missing is a *driver* that turns that into a repeatable,
gated soak rather than ad-hoc observation.

---

## 5. The gap (this is the part worth fixing)

1. **No driver runs the live-session path.** Every tier of `soak_driver.py`
   either injects synthetic prose at `engine.evaluate` (Tiers 1.5/3) or replays
   a cassette (Tier 1). None attaches to a live non-SM `claude -p` session and
   soaks the JsonlTailWorker front half. The `#112` empirical shadow soak --
   the binding MVP gate -- has no harness; it is run by hand.
2. **Polarity in the synthetic + cassette paths is untested by construction.**
   Because synthetic load has no session rows, a regression that broke the
   `project_slug` exclusion would not be caught by Tiers 1/1.5/3. Only a
   live-session soak (or a fixture that carries a real `project_slug`) would
   surface it.
3. **"1252 active sessions" is almost certainly mostly stale.** The live
   readout counts 1252 active sessions; the operator monitors a handful. A
   live-session soak needs a way to *pick* the target session deterministically
   (busy + recent `updatedAt`, exclude SM-self, refuse a firewalled cwd --
   `feedback_session_monitor_target.md`) instead of drowning in stale entries.
   This is the same friction the stale-session-cleanup comfort (#5) addresses.

---

## 6. Bottom line

- **Today's soak** = a self-contained synthetic latency/plumbing harness across
  three tiers; robust, cheap, and the source of truth for ADR-5 (Tier 3). It
  does NOT exercise a live non-SM session.
- **`#r1`'s soak** = attach to a real non-SM `claude -p` session, tail it, and
  validate governance behaves -- with polarity (`project_slug != streamManager`)
  as the non-negotiable floor. This path runs in production (the dashboard
  proves it) but has no repeatable, gated driver.
- **The actionable gap** (carried into the proposals, directive #5/#6): a
  `--live-session <id>` soak mode that (a) picks a non-SM target deterministically,
  (b) refuses SM-self + firewalled cwd, (c) soaks the tail->bus->governance chain,
  and (d) emits the same report shape as the synthetic tiers so it slots into the
  existing matrix. That is the harness `#112` has been missing.

---

### Verify

- `python tools/soak_driver.py --cli-replay tests/fixtures/soak_cassette_*.jsonl`
  runs without `claude` on PATH (Tier 1 regression; `tests/test_soak_replay.py`).
- `grep -n "project_slug NOT IN" src/stream_manager/rl/ope.py` (or the corpus
  loaders) confirms the durable read-side polarity key is present.
- Pinned counts above re-derivable from `reports/ui-next-walkthrough.json`
  (footer line) and `tools/soak_driver.py:60-90` (the 50/5/5 mix).
