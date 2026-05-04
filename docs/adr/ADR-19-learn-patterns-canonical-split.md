# ADR-19: Learn Mode `learn_patterns` audit/canonical two-table split

- **Status**: Accepted (v1.3)
- **Date**: 2026-05-04
- **Related**: `docs/learn-mode-design.md` §3.2, `REQUIREMENTS.md` §4.12
  FR-LM-3 / FR-LM-4, `docs/v1.3-corrective-action.md` §12 (Phase C6),
  PR #62 (P5c), PR #64 (P5e)

## Context

P5c (PR #62) introduced `learn_patterns` as an **append-only audit log**.
Every categorization observation produced by the Sonnet categorizer
worker writes a fresh row keyed by `(prompt_hash, observed_ts)`. The
audit log answers the question "what categorizations did we ever
observe for this prompt?"

The PR #62 review surfaced a nit asking for `UNIQUE(prompt_hash)` so
the table could be UPSERTed in place. Treating the existing rows as
UPSERT targets would, however, destroy the observation history that
the audit log was created to preserve.

P5e (PR #64) responded by introducing a second table,
`learn_patterns_canonical`, with `UNIQUE(prompt_hash)` and UPSERT
semantics. `consolidate_patterns` and `decay_sweep` write the
canonical row; reinforcement, contradiction snap-demote, and the
30/60/90/120-day decay ladder all mutate the canonical row in place.
The audit log is left untouched.

The split was introduced inside the cycle without an ADR. This
document is the retroactive record so future maintainers see the same
two tables and either re-merge them or invent a third do not
re-litigate the decision blindly.

## Decision

Keep the two-table split as the v1.3 contract.

- **`learn_patterns` (audit log)** — append-only. Source of truth for
  "what categorizations did we ever observe." Written exclusively by
  the P5c categorizer worker on every observation. Never mutated
  in place. Never deleted.
- **`learn_patterns_canonical` (current effective bias)** — UPSERT,
  `UNIQUE(prompt_hash)`. One row per unique `prompt_hash` carrying
  the **current** effective `category`, `confidence`, `ladder_step`,
  and `last_reinforced_ts`. Written exclusively by
  `consolidate_patterns` (reinforcement / contradiction) and
  `decay_sweep` (time-based demote).
- **`bias_for` reads canonical** (post Phase C1 of the corrective
  plan). The verdict path therefore sees the post-decay,
  post-reinforcement, post-contradiction state — not "newest insert
  wins" against the audit log.

The decay state required by FR-LM-4 lives on the canonical row.
The historical record required for replay and post-hoc review lives
on the audit log. Neither replaces the other.

## Consequences

- `consolidate_patterns` is the **only** writer to
  `learn_patterns_canonical`. Any other future code path that wants to
  mutate the canonical row goes through `consolidate_patterns` so the
  EMA-weighted confidence math and ladder transitions stay in one
  place.
- Audit log writes are independent of canonical writes. The P5c
  categorizer worker does not need to know the canonical table
  exists. This keeps the categorizer hot-path-free of UPSERT
  contention.
- Storage cost is modest: one canonical row per unique
  `prompt_hash`, plus the audit log, which grows monotonically. Audit
  log retention policy is a future concern (see "Open questions"
  below); v1.3 keeps everything.
- A future cycle MAY collapse the two tables to a single table with a
  `current=1` flag (or equivalent) if audit-log retention requirements
  change such that historical rows are pruned. That collapse would
  require a successor ADR; it does not happen in v1.3.
- The split is invisible to FR-LM-3 / FR-LM-5 consumers — the bias
  envelope and the silent audit row both flow from `bias_for`'s read,
  which sees only the canonical projection.

## Alternatives considered

### (a) Single table with `UNIQUE(prompt_hash)` + UPSERT

Rejected. The PR #62 review nit proposed this. UPSERT in place
overwrites the prior `category`, `confidence`, and observation
timestamp for the same `prompt_hash`. That destroys the audit history
the table was created to preserve and removes the ability to replay
"what did we ever observe" for post-hoc review. The audit log is
load-bearing for the silent-audit-row UX (FR-LM-5) and for any future
"why did this pattern decay?" debugging.

### (b) Materialized view of the audit log

Rejected. SQLite has no native materialized view; emulation requires
either trigger-driven projection tables (effectively re-implementing
option (a)'s problem at the trigger layer) or query-time computation
on every `bias_for` read. The complexity is meaningful and the
operational gain over a plain second table is marginal.

### (c) Keep audit-only, discard P5e

Rejected. FR-LM-4 requires explicit decay state (ladder rung,
reinforcement reset, contradiction snap-demote) to reach the verdict
path. An append-only audit log can simulate "newest wins" but cannot
represent "this prompt is at L2 because it was reinforced three times
and then aged 60 days" without re-deriving that state on every read.
The canonical projection is where that derived state lives.

## Open questions / future work

- **Audit log retention.** v1.3 keeps every audit row. A future cycle
  may add a TTL (e.g. drop rows older than the deepest decay
  threshold) once the dashboard's replay window is defined.
- **Single-table collapse.** If retention is added and the audit log
  is bounded, the canonical projection may be re-expressible as a
  `current=1` flag on the audit table. A successor ADR would record
  that decision.
- **Cross-session propagation.** If v1.4+ enables HITL-gated
  cross-session learning (Q3 OQ5 in the design doc), the canonical
  table is the natural propagation surface; the audit log stays
  per-session.

## References

- `docs/learn-mode-design.md` §3.2 — component table (cross-links
  here).
- `REQUIREMENTS.md` §4.12 FR-LM-3 / FR-LM-4 — advisory bias and decay
  ladder (FR-LM-4 cross-links here).
- `docs/v1.3-corrective-action.md` §1, §7, §12 — incident summary,
  Phase C1 (`bias_for` reader migration), Phase C6 (this ADR).
- `src/stream_manager/message_bus.py` — `learn_patterns` and
  `learn_patterns_canonical` schemas.
- `src/stream_manager/decay.py` — `consolidate_patterns`,
  `decay_sweep` (canonical writers).
- `src/stream_manager/learn_categorizer.py` — categorizer worker
  (audit-log writer) and `bias_for` (post-C1 canonical reader).
- PR #62 (P5c — categorizer + audit log).
- PR #64 (P5e — decay + canonical projection).
