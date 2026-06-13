# Policy-preview chip: "what will governance do" from the corpus

**Status:** Proposal (data-flywheel, directive follow-up F). Boldness STRETCH; effort M.
**Scope:** proposal only. ASCII-only (cp1252).
**Floor:** advisory pre-fill only -- never pre-decides; M18 off the verdict hot path; polarity dual-key.

## Problem

The operator makes two decisions blind to what the 21k-decision corpus already knows: (a) before flipping
a session HITL SYNC/ASYNC or adjusting the confidence floor, and (b) when eyeballing a session's likely
behaviour. The corpus can answer "for command shapes like this, governance has landed ALLOW 100% (n=14)"
-- but that prediction is never surfaced at the moment of choice. The data exists; the foresight does not.

## Proposal

A **policy-preview chip** -- a read-only retrieval over historical decisions, rendered as an advisory
chip at the decision point:

1. Backend: `GET /api/governance/predict?shape=<hash>&session_id=<id>` returns the corpus distribution for
   the nearest historical decisions of that shape: `{action_hist: {ALLOW:14, SUGGEST:1}, mean_conf,
   n, dominant_layer}`. Retrieval = exact-shape match first, then a cheap normalized-command k-NN.
   Polarity dual-key over the corpus.
2. UI: where the operator is about to act -- the session mode toggle, a pending HITL row, the confidence
   slider -- render a dashed advisory chip (same visual grammar as the Learn-Mode advisory chip, M8):
   "corpus: 14/15 ALLOW, mean 0.97, L1 -- advisory only, your decision stands." It NEVER pre-selects an
   option; it informs.
3. The chip is strictly post-hoc retrieval; it adds nothing to the live verdict path (M18) and degrades
   silently to "no history" on a cold shape.

## Operator value

The operator decides with the corpus's memory in view: a session full of routine shapes shows a calm
"this looks 100% routine" preview, so they can leave it ASYNC and look away; a session with a novel shape
shows "no history / mixed" and earns attention. Foresight from accumulated decisions -- the flywheel's
output rendered at the exact moment it helps.

## Surfaces touched / added

- additive `GET /api/governance/predict` in `dashboard/server.py` (read-only retrieval)
- `dashboard/ui-next/src/lib/components/PolicyPreviewChip.svelte` (new); consumed by `HitlModeToggle`, `HitlPendingRow`, settings confidence slider
- reuse `AdvisoryChip.svelte` visual grammar so the M8 "advisory only" framing is identical

## Feasibility

FEASIBLE. Retrieval over the existing `decisions` table; exact-shape match is a cheap indexed query, k-NN
can start as normalized-string similarity (no embeddings needed for v1). Additive endpoint, new component,
no FROZEN surface. M18 respected (post-hoc, not on the verdict path).

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- SM corpus only; domain-agnostic (shape hashes, not project vocab).
- **Polarity (G2):** PASS -- dual-key corpus read; SM-self excluded from the predictive corpus.
- **ADR-18 MUST floor:** PASS -- advisory chip uses the M8 dashed non-verdict grammar; never pre-selects, never bypasses the HITL gate or a BLOCK; monitor-first preserved; M18 off the hot path.
- **Frozen-surface note:** none touched -- pure read-side retrieval + a UI chip. It must NOT be wired INTO `governance.evaluate` (that is FROZEN and would put it on the hot path, violating M18).
- **New-envelope note:** none (no bus envelope; a REST read endpoint).

## Grounding

- `index.html:3286-3307` / `governance.py:902-941` (M8 advisory-chip grammar to mirror)
- `REQUIREMENTS.md:494,556` (M18 latency budget -- stay off the hot path)
- `CLAUDE.md:31-45` (dual-key polarity read)
- gov.db `decisions` schema (action/confidence/layer/content) = the retrieval source

### Verify
- `GET /api/governance/predict?shape=<known-routine>` returns a distribution with `n>0`; a cold shape returns `n:0` and the chip renders "no history".
- The chip never sets a default selection on any HITL row (grep: no write to selection state from the chip).
