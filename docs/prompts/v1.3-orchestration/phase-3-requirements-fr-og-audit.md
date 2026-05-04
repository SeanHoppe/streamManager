You are implementing **Phase P3 — REQUIREMENTS FR-OG drift audit** from the streamManager v1.3 cycle.

## Branch + base

- Base: `main`.
- PR target: `main`.
- Branch: `docs/v1.3-requirements-audit` (or operator's choice).
- If `main` is unexpectedly behind v1.2 close-out (`7b7dc64`), ABORT and tell the user.

## ⚠️ CRITICAL: Do-not-touch guard

P3 is **docs only** — zero code edits. Do not edit ADRs (they are historical record once shipped). Bumping the spec version pin in `REQUIREMENTS.md` is in scope; rewriting prior version sections is not.

Pre-flight check:

```
git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard
```

Expect empty output. Any non-docs row: STOP.

## Task brief

v1.2 close-out (M4/PR #51) found that `docs/v1.2-task-plan.md` §B referenced adding an `FR-OG-X` entry for the session picker, but `REQUIREMENTS.md` was never touched in the v1.2 cycle (last touched at `b66c840`, pre-v1.2). Spec-vs-impl drift.

Audit Tasks B (session picker), C (lifecycle bridge), D (long-poll removal), E (json transport removal) for any FR-* drift.

### Steps

1. Read `docs/v1.2-task-plan.md` Tasks B, C, D, E. For each, list which FR-OG-* (or FR-* generally) entries should exist and check whether they do.

2. Add missing entries to `REQUIREMENTS.md`:
   - Session picker (Task B) — operator surface requirement
   - Lifecycle bridge dashboard pane (Task C) — operator surface requirement
   - SSE-only desktop command transport (Task D) — transport requirement (mark long-poll as removed)
   - WireCLI default + json transport refusal (Task E) — transport requirement

3. Bump `REQUIREMENTS.md` spec version pin to reflect v1.2 surface fully.

4. Cross-link each new FR entry to the originating task in `docs/v1.2-task-plan.md`.

5. No code touched.

## DOD

- [ ] All four v1.2 tasks audited; missing FR entries added
- [ ] Spec version pin bumped
- [ ] `git --no-pager diff origin/main..HEAD --stat` shows only `REQUIREMENTS.md`
- [ ] Single PR against `main`

## Final verification before opening PR

```
git --no-pager diff origin/main..HEAD --stat
```

Expected file:
- `REQUIREMENTS.md` (modified)

If any other file appears, STOP and report.

No pytest required (docs only).

Report back: PR URL, diff stat.
