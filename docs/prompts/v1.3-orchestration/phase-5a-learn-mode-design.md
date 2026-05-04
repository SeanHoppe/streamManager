You are implementing **Phase P5a — Learn Mode design doc + REQUIREMENTS additions** from the streamManager v1.3 cycle.

## Branch + base

- Base: `main` (cut new feature branch from here).
- Feature branch: `ship/v1.3-learn-mode` — cut from `main` as the FIRST action of P5a. Push to set upstream.
- PR target: `ship/v1.3-learn-mode` (this PR seeds the design doc + REQUIREMENTS entries on the feature branch; subsequent P5b–P5e PRs target the same feature branch).
- If `ship/v1.3-learn-mode` already exists with prior commits, ABORT and tell the user — confirm whether to rebase or continue.

## ⚠️ CRITICAL: Do-not-touch guard

P5a is **docs only**. Zero code edits. Do not touch anything under `src/`, `tests/`, `tools/`, `dashboard/`.

Pre-flight check:

```
git --no-pager diff origin/main..HEAD --stat -- src tests tools dashboard
```

Expect empty output. Any non-docs row: STOP.

## Task brief

Source of truth for design seeds: memory note `project_learn_mode.md` (locked decisions 2026-05-03). Note: that memory note references `smartai.md` at repo root; that file does NOT exist. Treat the memory note as the authoritative source.

P5a captures the locked decisions into `docs/learn-mode-design.md` (ADR-style) and adds `REQUIREMENTS.md` §4.x FR-LM-1..6 entries. P5b, P5c, P5d, P5e all depend on this doc.

### Steps

1. Cut the feature branch:
   ```
   git checkout main && git pull && git checkout -b ship/v1.3-learn-mode && git push -u origin ship/v1.3-learn-mode
   ```

2. Create `docs/learn-mode-design.md` (ADR-style) capturing:
   - **Ingest** — extend `src/stream_manager/jsonl_tail.py` to extract `assistant` text turns → `messages.type='desktop_prompt'` and `user` text turns → `messages.type='user_reply'`. Pair via existing `parentUuid` chain. No new Desktop hook surface.
   - **Scope** — Desktop orchestrator turns. SM HITL prompts excluded (memory `feedback_no_self_monitor.md`).
   - **Auto-resolve** — pre-fill only in v1.3. No silent skip of HITL gate. Revisit auto-resolve in v1.4+.
   - **Categorizer** — Sonnet, out-of-band worker. Off verdict hot path → ADR-5 latency budget unaffected.
   - **Decay** — time-based step demote (30/60/90/120 day ladder) + reinforcement reset + contradiction snap-demote.
   - **UX** — silent audit row. No toast, no undo card.
   - **Multi-user** — single-user assumed; no `owner_user` tag.
   - **Safety** — `INTENT.md` §"Safety priorities" remains absolute (destructive shell verbs, force-push to main, eval/exec, credential exfil cannot be auto-allowed by learned preference).

3. Add `REQUIREMENTS.md` §4.x FR-LM-1..6:
   - FR-LM-1 — JSONL tailer emits `desktop_prompt` and `user_reply` message types
   - FR-LM-2 — Sonnet categorizer worker runs off the verdict hot path
   - FR-LM-3 — Patterns surface as advisory bias on next decision; never override HITL or safety priorities
   - FR-LM-4 — Decay ladder + reinforcement reset + contradiction snap-demote
   - FR-LM-5 — Silent audit row UX
   - FR-LM-6 — Single-user scope; SM HITL prompts excluded from ingest

4. Bump `REQUIREMENTS.md` spec version pin to reflect FR-LM additions.

## DOD

- [ ] `ship/v1.3-learn-mode` branch exists on origin
- [ ] `docs/learn-mode-design.md` merged on `ship/v1.3-learn-mode`
- [ ] `REQUIREMENTS.md` FR-LM-1..6 added; spec version pin bumped
- [ ] `git --no-pager diff origin/ship/v1.3-learn-mode..HEAD --stat` shows only `docs/learn-mode-design.md` and `REQUIREMENTS.md`
- [ ] No code touched

## Final verification before opening PR

```
git --no-pager diff origin/ship/v1.3-learn-mode..HEAD --stat
```

Expected files:
- `docs/learn-mode-design.md` (new)
- `REQUIREMENTS.md` (modified)

If any other file appears, STOP and report.

No pytest required (docs only).

Report back: PR URL, diff stat, confirmation that `ship/v1.3-learn-mode` is now on origin.
