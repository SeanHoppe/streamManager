# MEMORY — Coding & Approach Nuances

> Project-root memory. Claude updates this when Sean teaches a coding
> preference, approach nuance, or "do/don't do X" rule that should persist
> across sessions in **this repo**.
>
> **This file is distinct from the auto-memory store** at
> `C:\Users\SeanHoppe\.claude\projects\C--Users-SeanHoppe-vs-streamManager\memory\`
> (per-topic markdown files, machine-managed, not checked in). When in
> doubt:
> - Hard project rules / firewall / ADR-18 → `CLAUDE.md` (checked in, law).
> - Sean's coding habits + approach nuances → this file (checked in,
>   shareable with future sessions / collaborators).
> - One-off project state / cycle facts → auto-memory store.

## How Claude uses this file

- **Read** at session start (CLAUDE.md references this file).
- **Consult** before writing code or proposing approach in PR-shaped work.
- **Write** a new bullet under the matching section the moment Sean states
  a preference. Date-prefix `YYYY-MM-DD`. One line per rule. Add a `Why:`
  fragment if the reason is non-obvious.
- **Update in place** rather than appending a duplicate.
- **Mark obsolete** rules with `~~strikethrough~~` + a one-line successor;
  do not silently delete (history matters for future-Claude).

## Coding style

_Sean's preferences for Python / scripts / configs in this repo._

- _(empty — append as Sean teaches)_

## Approach nuances

_How Sean wants Claude to plan, scope, and sequence work._

- _(empty)_

## Do-not-do

_Anti-patterns Sean has called out. Always include the **Why** so future-Claude
can judge edge cases instead of blindly following._

- _(empty)_

## Tooling preferences

_Which tools, agents, CLIs to prefer for which jobs._

- **2026-05-22 — SM testing/soaking requires a live non-SM Claude CLI session.** Before firing any soak / ship-gate / Tier-3 / RL-track run, confirm an active local Claude session is running on the laptop in a non-SM project (certPortal, certPortal-oversight, pycoreEdi, etc.) and producing real bus envelopes / JSONL writes. Stale fixture JSONL, replayed transcripts alone, or SM-self traffic do NOT satisfy. If no live non-SM session exists, ask Sean to start one (or refuse to fire). **Why:** SM's production code paths (JsonlTailWorker tail-cursor, bus subscriber, Learn-Mode, alignment-eval timing) only exercise correctly under live, in-progress session writes; fixtures pass syntactic checks but skip timing/partial-line/tail-cursor code. Cross-ref `feedback_soak_needs_live_non_sm_session.md`, `feedback_no_self_monitor.md` (polarity-flip), `feedback_session_monitor_target.md`.

## Review / PR conventions

_Commit message shape, PR body shape, reviewer expectations._

- _(empty)_

## Cross-refs

- `CLAUDE.md` — firewall + polarity-flip + ADR-18 + robin-agent law.
- `docs/adr/ADR-18-mvp-surface-freeze.md` — surface-freeze rules.
- Auto-memory store (per-topic): `C:\Users\SeanHoppe\.claude\projects\C--Users-SeanHoppe-vs-streamManager\memory\`.
