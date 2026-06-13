# Regret-mining: close the operator-override feedback loop

**Status:** Proposal (data-flywheel, directive follow-up F). Authored to fill a gap the propose
workflow's fixed lanes diluted. Boldness STRETCH; effort M.
**Scope:** proposal only -- no FROZEN-surface edit authorized. ASCII-only (cp1252).
**Floor:** advisory only -- NEVER auto-applies a policy change; polarity dual-key; HITL gate untouched.

## Problem

Every time the operator OVERRIDES governance (HITL APPROVE-over-a-SUGGEST, DISMISS-of-an-INTERVENE,
or a free-text override), that divergence is the single richest learning signal the system produces --
the human said "you were wrong here." Today it lands in `hitl_overrides` and is used only for the
per-message reinforcement pre-fill. The aggregate signal -- *where does governance systematically
disagree with the operator?* -- is never mined. So the same class of wrong verdict recurs, and the
operator re-corrects it by hand each time. That is the opposite of a flywheel.

## Proposal

A read-only **Regret dashboard** (UI) backed by a **regret aggregator** (backend job):

1. Backend `tools/regret_aggregate.py` (or an additive `/api/governance/regret` endpoint) scans the
   decisions x `hitl_overrides` join over the corpus and computes, per command-shape / layer / action
   cluster: `n_decisions`, `n_overridden`, `override_rate`, and the dominant override direction
   (operator escalated vs de-escalated). Polarity dual-key: SQL `WHERE project_slug NOT IN
   (BRIDGE_SM_PROJECT_SLUGS)` + the cheap `session_id != BRIDGE_SM_SELF_SESSION_ID` Python backstop
   (CLAUDE.md L42-43). Default-exclude makes SM-self leakage a zero-row failure, not contamination.
2. UI: a Frame-A (or settings) "Regret" pane lists the top divergence clusters: "governance said
   SUGGEST, you APPROVED, 14/14 times -- candidate: raise this shape's advisory bias" with a paired
   label+badge and a one-tap **"Open as proposal"** that drafts a bias/rule adjustment for operator
   review. It NEVER mutates policy itself.
3. The adjustment is staged as advisory bias (the same channel Learn-Mode uses), gated behind the
   absolute HITL gate -- it pre-fills, the operator still decides.

## Operator value

Turns the operator's own corrections into a ranked "here's where I keep fixing you" list, so a recurring
wrong verdict gets fixed once (as bias) instead of re-corrected forever. The flywheel: more overrides ->
sharper bias -> fewer overrides on that shape. Read-only + advisory keeps it safe.

## Surfaces touched / added

- `tools/regret_aggregate.py` (new, read-only) OR additive `GET /api/governance/regret` in `dashboard/server.py`
- `dashboard/ui-next/src/lib/components/RegretPane.svelte` (new) + a poller in `pollers.js`
- advisory-bias write path reuses the existing Learn-Mode bias channel (no new verdict path)

## Feasibility

FEASIBLE. Pure aggregation over existing `decisions` + `hitl_overrides` tables; the dual-key polarity
pattern is precedented in `rl/corpus_augment.py`. No FROZEN surface: the aggregator is read-only, the
endpoint additive, the bias write reuses the existing advisory channel.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- aggregates SM's own gov.db; no certPortal coupling; domain-agnostic.
- **Polarity (G2):** PASS -- dual-key (durable `project_slug` SQL WHERE + ephemeral `session_id` Python backstop). SM-self never enters the regret corpus.
- **ADR-18 MUST floor:** PASS -- advisory only; HITL gate absolute (M8) -- bias pre-fills, never bypasses the operator or a BLOCK; monitor-first (read-only pane, no auto-foreground).
- **Frozen-surface note:** none touched. The bias write reuses the Learn-Mode advisory channel; if it instead needed `governance.py`, that is FROZEN and would require an ADR-18 amendment first.
- **New-envelope note:** if a `regret_adjustment_proposed` envelope is added, same-PR `cassette_record.py` + `soak_driver.py` coverage is mandatory (feedback_cassette_must_cover_new_envelopes).

## Grounding

- `CLAUDE.md:31-45` (dual-key polarity read/write split)
- `MEMORY.md` / `project_hitl.md` (hitl_overrides persisted for reinforcement)
- `INTENT.md` "what governance should learn from this project" (override = learning signal)
- `reports/proposals/2026-06-11-polarity-dual-key-read-write-split.proposal.md`

### Verify
- `GET /api/governance/regret` returns clusters with `override_rate`; a seeded SM-self row is absent (polarity).
- The pane's "Open as proposal" drafts a bias change but does NOT mutate any verdict (grep: no write to `decisions`).
