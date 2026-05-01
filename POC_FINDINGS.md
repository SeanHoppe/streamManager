# POC Findings — Synthesis

**Date:** 2026-05-01
**Author:** original planning + spike session
**Branches synthesized:** `poc/pipe` (23f707d), `poc/brain` (fe7353d), `poc/wire` (f05febb)

## TL;DR

Three throwaway spikes, ~1 day each. **All three "held"** their target
hypothesis. Hardening pick: **Spike B (`poc/brain`)** — it surfaced the
most architectural surprise, and its load-bearing experiment (INTENT.md
A/B) confirmed the project's distinctive value prop. Spike A's transport
result and Spike C's wire mechanics are preserved as findings; their code
will be re-implemented on top of brain when needed.

---

## Per-spike summary

### Spike A — "Prove the pipe" — `poc/pipe` @ `23f707d`

| Metric | Target | Measured |
|---|---|---|
| Median round-trip latency | ≤ 50 ms (NFR-P1) | **0.96 ms** |
| Throughput | ≥ 500 RTT/s (NFR-P3) | **852 RTT/s** |
| Active RAM after 1000-msg burst | ≤ 50 MB | **28 MB** |
| Bus persistence | 2000 rows | **2000 ✓** |

**Status:** Held. Few surprises.

**Key surprise:** how much headroom there is. The 50 ms latency budget
is not the constraint; the eventual governance API call (200–2000 ms per
ADR-5) will entirely dominate. Synchronous SQLite WAL writes in the
critical path do not introduce a measurable latency floor.

**Verdict:** Transport is solved. Future hardening on the wire is a
refinement task (SIGKILL durability test, sustained 100 msg/s soak,
multi-Desktop broadcast load), not an unknown.

---

### Spike B — "Prove the brain" — `poc/brain` @ `fe7353d`

| Hypothesis | Target | With INTENT | Without INTENT |
|---|---|---|---|
| `fast_precheck` median | < 1000 µs | **12.4 µs** | 3.25 µs |
| L2 patterns emerge | ≥ 1 | 1 | 1 |
| Sub-linear pattern growth | ratio < 1.0 | **1.53 ✗** | 1.54 ✗ |
| Mode promotions | ≥ 1 | 4 | 4 |
| INTENT.md A/B divergent decisions | ≥ 1 | **3** | — |
| Unit tests | all pass | 14 / 14 | — |

**Status:** Held with caveats.

**Key surprises (architectural — must address before hardening):**

1. **Sequence-pattern explosion.** Naive 2-gram sequence detection
   materializes one new L1 candidate per consecutive message pair. With
   70 messages we got 75 L1 sequences, of which only ~5 had ≥ 5
   occurrences (the threshold for real consolidation). The remaining 70
   are singleton noise, blowing past the sub-linear-growth target. At
   production scale this becomes a memory leak in disguise that grows
   linearly with session length.

2. **Mode ladder over-promotes on positive-only feedback.** Every
   correct ALLOW counts toward accuracy, so the engine promoted
   OBSERVE → SUGGEST → GUIDE → INTERVENE → BLOCK in 70 routine
   messages. You wouldn't want a bridge to graduate to BLOCK after 70
   `git status` calls. This is the difference between a system users
   keep enabled and one they disable on day 2.

**Load-bearing positive result:** INTENT.md provably catches 3 cases
in 70 messages that static rules miss (`session_token`, `auth_token`,
`secret_token` patterns). This validates the new requirement raised in
the planning session: project-intent ingest is real value, not theoretical.

**Verdict:** Brain math is correct end-to-end. INTENT.md adds measurable
governance value. Two real architectural fixes needed before this is
trustworthy.

---

### Spike C — "Prove the wire" — `poc/wire` @ `f05febb`

| Hypothesis | Target | Measured |
|---|---|---|
| Subprocess stdio proxies through WS | echo replies | **3/3 ✓** |
| ANSI escape stripped | no `\x1b` in client output | **none observed** |
| Subprocess exits cleanly on stop | `returncode != None` | **PID reaped** |
| Multi-client broadcast | both clients receive | **passes in unit test** |
| Round-trip latency (50 RTTs) | n/a | median **0.20 ms** / p95 0.41 ms |
| Wire RAM | n/a | **~26 MB** |
| Unit tests | all pass | **8 / 8** |

**Status:** Held.

**Key surprises (well-bounded):**

1. **Pre-connect subprocess output is lost.** The subprocess emits a
   "ready" line at startup, before any WS client connects. That line
   gets read by the stdout pump, broadcast to an empty client set, and
   discarded. Hardening implication: bounded replay buffer for
   late-connecting clients, or session-start semantics where client
   connection precedes subprocess spawn.

2. **Hard-kill subprocess cleanup relies on OS stdin-EOF cascade.**
   When wire is hard-killed (no graceful teardown), the subprocess dies
   because its stdin pipe closes. This is a happy coincidence of how
   Windows + Python handle broken pipes in `input()`, not something the
   wire architecture guarantees. A subprocess that ignores stdin EOF
   would orphan. Hardening implication: explicit process-group /
   Windows-Job-Object teardown for hard-kill scenarios.

**Verdict:** Wire mechanics are sound; the gaps are inherit-from-OS-default
edge cases, not design flaws.

---

## Synthesis: why Spike B is the hardening pick

The plan rule was: *"hardening goes to the spike that surfaced the most
surprise, not necessarily the one with the prettiest numbers."*

| | Spike A | Spike B | Spike C |
|---|---|---|---|
| Surprises that change behavior at scale | 0 | **2** | 1 (orphan teardown) |
| Surprises that change user trust | 0 | **1** (over-promotion) | 0 |
| Load-bearing experiment for project value-prop | n/a | **passed (3 catches)** | n/a |
| Targets met | all | most (sub-linear missed) | all |

Only Spike B surfaced issues that change how the system would behave
*at production scale and over time*:

- The sequence explosion is a memory leak in disguise that grows with
  session length.
- The over-promoting mode ladder erodes user trust within a single
  session.

Both are fixable, but they ARE the hardening work. Neither A nor C has
an analogous "hidden behavior I have to fix to ship this" finding.

Plus: Spike B's INTENT.md A/B was the load-bearing experiment for the
new project requirement raised in this planning session ("hook into the
governed repo's intent"). The 3-divergent-decisions result confirms the
prop is real. **Hardening B closes the loop on what makes StreamManager
distinctive.** A and C don't.

Spike A's empirical signal — that transport is solved — is preserved
without keeping its code. We now know we can write the production
transport in a few hundred lines whenever we need to, with confidence
the latency budget holds. Spike C's mechanics are similarly preserved.
WireCLI from `poc/wire` is the right shape; we'll re-implement on top
of brain when the project reaches the point of wrapping a real
subprocess.

---

## Hardening followups for `poc/brain` → `main`

### Critical (architectural — block merge to main) — DONE

1. **Defer sequence-pattern materialization.** ✅ Shipped 2026-04-30
   (`82a6193`). Singletons live in `_sequence_candidates` until their
   second observation. Validated on a real 1,483-msg session: ratio
   0.297 (target < 1.0; pre-fix synthetic fixture was 1.53).

2. **Intervention-weighted mode promotion.** ✅ Shipped 2026-04-30
   (`d44021d`). `ELIGIBLE_SOURCES` filters the rolling window to
   precheck/graph/api decisions; `MIN_INTERVENTIONS_FOR_PROMOTE = 3`
   gate added. Validated on the same real session: 600+ routine ALLOWs
   left mode in OBSERVE (pre-fix would have walked to BLOCK).

### Production readiness — DONE

3. **Real-session fixture.** ✅ Shipped 2026-05-01 (`a008f7b`).
   `transcript_loader.py` ingests Claude Code JSONL transcripts;
   `tools/replay_transcript.py` runs them through `GovernanceEngine`
   and reports growth ratio + mode timeline + level distribution.
   Test fixture in `tests/fixtures/mini_session.jsonl`.

4. **Wire the Anthropic API.** ✅ Shipped 2026-05-01 (`ea105b5`).
   `api_governance.py` adds an L2 escalation path gated on
   `BRIDGE_API_GOV=true`; uses `claude-haiku-4-5` with a 2 s wall-clock
   budget, structured `output_config.format` (json_schema), and
   prompt-cached system+intent prefix. Stub-by-default — env unset
   means the engine path is byte-identical to pre-wiring.

5. **L3/L4 promotion validation.** ✅ Shipped 2026-05-01 (`20cece4`).
   `tests/test_l3_l4_promotion.py` walks a single content pattern to
   L4 (20 occurrences), asserts L4 is terminal, and validates
   sub-linear ratio + OBSERVE-mode-stable on a 600-msg, 8-routine
   synthetic multi-session fixture.

### Re-incorporate from other spikes (when needed)

- **From `poc/pipe`:** the SQLite WAL bus + 2-WS router. Re-implement
  on top of brain when transport is needed. Reference:
  `spike-a-final` tag (commit `23f707d`) — its numbers and shape are
  captured above and in this file.

- **From `poc/wire`:** the WireCLI subprocess wrapper. Re-implement on
  top of brain when subprocess wrapping is needed. Reference:
  `spike-c-final` tag (commit `f05febb`).

---

## Branch cleanup proposal *(propose, do not execute without sign-off)*

Tag the spike tips first (so they're recoverable past branch deletion):

```bash
git tag spike-a-final 23f707d
git tag spike-c-final f05febb
git tag spike-b-final fe7353d   # in case poc/brain ever needs reset to spike state
```

Then delete the loser branches:

```bash
git branch -D poc/pipe       # local
git branch -D poc/wire       # local
# When the github.com/SeanHoppe/streamManager remote exists:
git push origin --delete poc/pipe poc/wire
```

`poc/brain` becomes the active development branch. After hardening
items 1–2 land on `poc/brain`, fast-forward merge to `main`.

**Why tags before deletion:** branches are pointers; deleting them only
removes the pointer. The commits themselves remain reachable via reflog
for ~90 days, then become candidates for garbage collection. Tags are
permanent pointers — they survive `git gc` and let you `git checkout
spike-a-final` years from now if a question comes up.

---

## What this synthesis explicitly does NOT do

- **Does not delete the branches.** Tag commands and `git branch -D`
  commands above are proposals, not executed.
- **Does not start hardening work.** Items 1–2 above are the next
  user-greenlit step.
- **Does not modify** INTENT.md, the project skeleton, or any spike
  branch beyond adding this file on `main`.

---

## 2026-05-01 status update

All 5 hardening followups landed. Test count: 41 passing. Branch
cleanup proposal executed: `poc/pipe` and `poc/wire` deleted (local +
remote); tags `spike-a-final`, `spike-b-final`, `spike-c-final`
preserved. `main` is the active development line.

Outstanding work this doc does NOT cover:
- Re-incorporation of the SQLite WAL bus (from `spike-a-final`) when
  transport is needed.
- Re-incorporation of WireCLI (from `spike-c-final`) when subprocess
  wrapping is needed.
- Real-API soak test with `BRIDGE_API_GOV=true` against a live Anthropic
  endpoint — current Item 4 tests use an injected mock client.
