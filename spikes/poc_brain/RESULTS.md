# Spike B — Results

## Environment

- Date: 2026-05-01
- OS / Python: Windows 11 Home 10.0.26200 / Python 3.12.10
- Repo loaded for context: `C:\Users\SeanHoppe\VS\streamManager` (this repo, dogfooded)
- Fixture: 70 synthetic Claude CLI session messages

## Numbers

| Hypothesis | Target | With INTENT.md | Without INTENT.md | Verdict |
|---|---|---|---|---|
| `fast_precheck` median latency | < 1000 µs | **12.4 µs** | 3.25 µs | ✓ ~80× headroom |
| `fast_precheck` p99 latency | — | 254.8 µs | 11.2 µs | — intent rules cost ~10× |
| L0 pattern count | — | 31 | 31 | identical |
| L1 pattern count after 70 msgs | ≥ 3 | 75 | 76 | ✓ but see surprise #1 |
| L2 pattern count after 70 msgs | ≥ 1 | **1** | 1 | ✓ math reaches L2 |
| L3 / L4 pattern count | — | 0 / 0 | 0 / 0 | expected (fixture too short) |
| Total pattern count / msg ratio | < 1.0 (sub-linear) | **1.53** | 1.54 | **✗ MISS** |
| Final mode (positive feedback only) | ≥ SUGGEST | **BLOCK** | BLOCK | over-promoted, see surprise #2 |
| Mode promotions during run | ≥ 1 | 4 | 4 | ✓ ladder works |
| INTENT.md A/B diverging decisions | ≥ 1 | — | — | **✓ 3 divergences** |
| Replay accuracy (mode-aware) | — | 1.000 (70/70) | 1.000 (70/70) | both at 100% |
| Unit tests | all pass | 14 / 14 | n/a | ✓ |

## A/B intent test — diverging decisions

| msg id | content (truncated) | with INTENT | without INTENT | source |
|---|---|---|---|---|
| 31 | `session_token = 'abcdef0123456789'` | **INTERVENE** | ALLOW | precheck vs default |
| 36 | `auth_token = 'eyJhbGciOiJIUzI1NiJ9'` | **INTERVENE** | ALLOW | precheck vs default |
| 51 | `secret_token = 'sup3rs3cr3t'` | **INTERVENE** | ALLOW | precheck vs default |

These are precisely the messages where the static safety rule list does **not**
match (they don't contain `api_key` / `aws_secret_access_key` / `bearer …`),
but the INTENT.md "no plaintext token storage" rule does. **The intent file
adds 3 governance detections in 70 messages that would otherwise be silently
allowed.** Extrapolated to the doc's 200-msg session, that's ~9 additional
catches.

## Surprises

1. **Sequence-pattern explosion.** Naive 2-gram sequence detection generates
   one new L1 candidate per consecutive message pair. With 70 msgs we got 75
   L1 sequences, of which only ~5 had ≥ 5 occurrences (the threshold for
   real consolidation). The remaining 70 are singleton noise, blowing past
   the "sub-linear pattern growth" target (ratio 1.53 instead of < 1.0).
   **Fix in hardening:** deferred materialization — only store a sequence
   after it's been observed twice, or hash by *normalized intent* of the
   pair rather than the raw L0 hash chain.

2. **Mode ladder over-promotes on positive-only feedback.** With every
   correct ALLOW counting as accuracy, the engine promoted OBSERVE→SUGGEST
   →GUIDE→INTERVENE→BLOCK in 70 routine messages. That's clearly wrong —
   you wouldn't want a bridge to graduate to BLOCK mode after 70 `git
   status` calls. **Fix in hardening:** weight the rolling-accuracy window
   by intervention-eligible decisions only, or require some minimum number
   of actual interventions in the window before promoting up.

3. **Intent rules cost ~10× the static-rule baseline** at p99 (254 µs vs
   11 µs), but both are still ~4× under the 1 ms FR-PC-5 target. Intent
   rule cost scales with `len(intent_text)` — keeping the INTENT.md
   summary near the doc's 600-token cap matters at the rule edge, not for
   typical traffic.

4. **L2 patterns emerged in 70 msgs.** Encouraging — the doc's L2
   threshold (10 occurrences) is reachable with light traffic. L3/L4 will
   need a real session to validate, but the math is healthy at L0–L2.

## Verdict

**Brain shape works.** The four core mechanisms — feature projection,
cosine match, hierarchical promotion, mode ladder, intent-aware precheck —
are individually correct (14/14 unit tests) and compose end-to-end on a
realistic-shape fixture. The INTENT.md A/B confirms the load-bearing
hypothesis: project intent provably changes decisions on intent-specific
risks (session-token-in-source) that static rules miss.

Two real architectural issues surfaced (sequence explosion, over-promotion).
Both are fixable in hardening; neither invalidates the design.

If this spike wins for hardening, the followups are: deferred sequence
materialization, intervention-weighted mode promotion, real-session
fixture replay, and finally wiring the Anthropic API stub for the cases
where graph + precheck don't decide.

## Gaps deliberately left

- Fixture is **synthetic**; a real recorded Claude CLI session is the next
  fidelity step.
- **Anthropic API not wired.** The hybrid plan was stub-by-default; this
  spike's load-bearing experiment was project intent value, not API
  fidelity. API integration belongs to whichever spike wins.
- **L3 / L4 promotions** require ≥ 10 / ≥ 20 occurrences per pattern; the
  70-msg fixture is too short to drive them. Validated indirectly via
  `tests/test_decision_graph.py` thresholds.
- **Real-outcome feedback signals** are heuristic (`expected == "ALLOW"`).
  Production needs actual signals from Claude CLI's exit codes / errors
  / user override actions.
