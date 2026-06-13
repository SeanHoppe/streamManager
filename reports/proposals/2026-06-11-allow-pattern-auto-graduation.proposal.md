# ALLOW-pattern auto-graduation (learn-mode -> static rule, operator-confirmed)

**Status:** Proposal (data-flywheel, directive follow-up F). Boldness WILD; effort L.
**Scope:** proposal only. ASCII-only (cp1252).
**Floor:** safety-floor shapes NEVER auto-graduate; every graduation is operator-confirmed; polarity dual-key.

## Problem

INTENT says governance should LEARN that routine commands are routine -- a shape seen ALLOWed at high
confidence dozens of times with zero operator override is, empirically, a rule. Today that knowledge
stays implicit in the corpus: every `git status`, `ruff check`, `pytest -q` is re-evaluated from scratch
(latency + quota) instead of graduating to a cheap static ALLOW. The corpus knows the answer; the policy
never promotes it.

## Proposal

A **graduation candidate engine** that promotes proven-routine shapes to static ALLOW rules, gated by
the operator:

1. Backend scan: per command-shape, compute `n_allow`, `mean_confidence`, `n_override`, `n_block_ever`.
   A shape is a graduation CANDIDATE iff `n_allow >= N` (e.g. 30) AND `mean_confidence >= 0.95` AND
   `n_override == 0` AND `n_block_ever == 0` AND it never matched a safety-floor rule. Polarity dual-key
   over the corpus (SQL `project_slug NOT IN` + `session_id` backstop).
2. UI: a "Graduation candidates" list (settings or Frame A) -- "git status: 497 ALLOW, 100% conf, 0
   overrides -> graduate to static ALLOW?" with a one-tap **operator confirm**. NO auto-promotion.
3. On confirm, write a static ALLOW rule to the existing rule store (the same mechanism static rules
   already use). Graduated shapes short-circuit to ALLOW (faster, 0 quota) while STILL being recorded.
4. **Hard guard:** safety-floor / destructive-shell / credential / force-push / eval-exec shapes are
   PERMANENTLY ineligible -- they can never graduate, even at 100% history (the floor is not learnable).
   A demote path (reuse the `/api/patterns/{hash}/demote` affordance) reverses any graduation.

## Operator value

The flywheel made concrete: routine toil stops costing a model call + a glance; the operator's repeated
"yes this is fine" graduates into a rule once, with their explicit sign-off. Latency + quota drop on the
long tail of routine commands; attention concentrates on the genuinely novel.

## Surfaces touched / added

- backend graduation-candidate scan (read-only) + the existing static-rule write path
- `dashboard/ui-next/src/lib/components/GraduationCandidates.svelte` (new) + poller
- reuse existing demote affordance for reversal

## Feasibility

HARD (honest). The candidate scan is easy (aggregation). The graduation WRITE touches the rule/decision
path -- if that path is `governance.py` (FROZEN per ADR-18), this needs an ADR-18 amendment BEFORE any
code. The safety-floor ineligibility guard must be airtight and tested. Ship as proposal; the wiring is a
deliberate v2.x cycle, not a spike edit.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- SM corpus only; domain-agnostic (shapes, not project vocab).
- **Polarity (G2):** PASS -- dual-key corpus read; SM-self excluded.
- **ADR-18 MUST floor:** PASS as a proposal. Operator-confirmed (HITL gate absolute -- M8 -- no auto-apply). Safety floor never auto-graduates. BUT the graduation write likely touches FROZEN `governance.py` rule evaluation -> see frozen-surface note.
- **Frozen-surface note:** the static-rule WRITE path may be FROZEN (`governance.py` `_evaluate_inner_core` / rule store). Shipping requires an ADR-18 amendment lifting that specific seam, with a Tier-1.5 soak per the trigger matrix. This proposal authorizes nothing FROZEN.
- **New-envelope note:** a `pattern_graduated` envelope needs same-PR `cassette_record.py` + `soak_driver.py` coverage.

## Grounding

- `INTENT.md` "what governance should learn" (routine -> ALLOW within POC window) -- see `learn-mode-bias-prober` charter
- soak `_ROUTINE` mix (`tools/soak_driver.py:60-90`) = exactly the shapes that would graduate
- `docs/adr/ADR-18-mvp-surface-freeze.md` (governance.py FROZEN)
- `INTENT.md` "Safety priorities" (the never-graduate floor)

### Verify
- A seeded destructive-shell shape at 100% ALLOW history is NOT offered as a candidate (floor guard).
- Graduation requires an operator click; no rule appears without confirmation (grep: no auto-write).
