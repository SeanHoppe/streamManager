# Spike B — "Prove the brain"

Decision graph + project context + mode-laddered governance, replayed against
a synthetic 70-message Claude CLI session. No WebSockets, no bus persistence —
this spike is about the brain, not the wire.

## Setup

Same as Spike A:
```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -e ".[dev]"
```

## Run

**Replay (with INTENT.md loaded):**
```bash
python -m spikes.poc_brain.replay --repo .
```

**Replay (intent ignored, baseline):**
```bash
python -m spikes.poc_brain.replay --repo . --ignore-intent
```

**A/B intent comparison:**
```bash
python -m spikes.poc_brain.ab_intent --repo .
```

## Targets / hypotheses

| Hypothesis | Source | Pass condition |
|---|---|---|
| `fast_precheck` is sub-millisecond on a real `ProjectContext` | FR-PC-5 | median < 1000 us |
| L0→L1 promotion thresholds (3 occ, 0.55 success) trip on ordinary CLI traffic | FR-DG-2 | at least 3 L1 patterns after 70 msgs |
| Mode ladder math actually advances on synthetic positive feedback | FR-GE-3 | mode reaches at least SUGGEST by msg 70 |
| Pattern count grows sub-linearly | NFR-P4-adjacent | total patterns / msgs < 1.0 |
| INTENT.md changes decisions on intent-specific risks | new requirement | A/B diff > 0 messages |

## Methodology notes

- Fixture is **synthetic**, not a recorded real session. The math correctness
  it validates is independent of fixture realism, but pattern-shape signal is
  not. A real session replay is a Phase 1 alpha follow-up.
- Anthropic API is **not wired in this spike** (per plan: hybrid stub-by-default,
  but the spike's load-bearing experiment is project-context value, not API
  fidelity). API integration belongs to hardening of whichever spike wins.
- "Success" feedback for graph learning is heuristic (`expected == "ALLOW"`),
  not real outcome data.

## What goes in `RESULTS.md`

The four target rows above plus surprises and a verdict on whether the brain
shape holds.
