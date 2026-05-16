# Gap 12 — MASTER.md stale reference in INTENT (bookkeeping)

> Minted from `docs/intent-todo-gap-2026-05-16.md` §Gap 12. Bookkeeping
> drift. Apply at v2.2 P0 INTENT-refresh pass per ADR-18 Rule 6 (#133).

## Why

INTENT.md §"Authoritative status references" reads (verbatim):

> `docs/jobs/MASTER.md` — cross-cycle issue tracker (note: still
> rows-stale on #111 hold-lift; update pending).

todo.md sticking point #4 marks this RESOLVED via PR #158
(2026-05-16). MASTER.md reconciliation shipped — row for #111
corrected (HELD Q4 → READY corpus-gated); LANDED rows added for
#107 / #108 / #109 / #128 / #129; status legend extended with
`READY`.

The stale-suffix in INTENT lags reality by one PR.

## Action

Edit INTENT.md §"Authoritative status references":

```
- `docs/jobs/MASTER.md` — cross-cycle issue tracker (note: still
  rows-stale on #111 hold-lift; update pending).
```

→ becomes:

```
- `docs/jobs/MASTER.md` — cross-cycle issue tracker.
```

Single-line edit. Strike the parenthetical.

## Verification

Before strike:

- [ ] Read current `docs/jobs/MASTER.md` row for #111 — confirm
      reads `READY corpus-gated`, NOT `HELD (Q4)`.
- [ ] Confirm LANDED rows present for #107 / #108 / #109 / #128 /
      #129.

If verification fails (memory stale per ADR-18 Rule 6 pre-flight):
do NOT strike yet — reconcile MASTER.md first.

## Cross-refs

- INTENT.md §"Authoritative status references".
- `docs/jobs/MASTER.md` — verify current row state.
- todo.md §"Sticking points / blockers" #4 — RESOLVED stamp ref.
- PR #158 — actual MASTER.md reconciliation merge.
- ADR-18 Rule 6 (#133) — INTENT-refresh pass at cycle frame.
- Gap doc §"Gap 12 — `docs/jobs/MASTER.md` stale reference".

## DOD (at v2.2 P0 INTENT-refresh pass)

- [ ] MASTER.md row state verified per "Verification" above.
- [ ] INTENT.md edit applied (parenthetical struck).
- [ ] Gap doc §Gap 12 LANDED.

## ADR-18 posture

- Pure documentation strike. Zero LOC src/test.
- Trivial.
- No DORMANT-N implication.
