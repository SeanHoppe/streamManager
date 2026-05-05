# S10 — Merge ship PR + tag v1.6.0

**Goal:** Merge S9 PR to main, tag merge commit `v1.6.0`, push tag.

## Context

After S9 PR merges, the merge commit becomes the v1.6.0 ship anchor.
S6's ADR-5 baseline section has a SHA placeholder — fill it post-merge.

## Steps

1. Confirm S9 PR merged to main. Capture merge SHA: `git rev-parse origin/main`.
2. Update ADR-5 v1.6 baseline section: replace `<ship-sha>` placeholder w/
   actual merge SHA. Commit + push to main as a tiny follow-up
   (or fold into S9 commit if not yet merged — preferred).
3. Tag:
   ```
   git tag -a v1.6.0 <merge-sha> -m "v1.6.0 ship-gate"
   git push origin v1.6.0
   ```
4. Verify tag visible on GitHub.

## Acceptance

- `git tag -l v1.6.0` shows tag.
- `git ls-remote origin refs/tags/v1.6.0` resolves on remote.
- ADR-5 v1.6 section has real SHA, no placeholder.

## On-done ack

`- [x] tag v1.6.0 @ <sha> **S10 — Merge + tag v1.6.0**`

## Mint-new check

- If post-tag smoke (basic `python -m stream_manager ...` OR re-run a quick
  cassette) breaks, mint `S10a-tag-recovery.md`.
- If tag push fails (auth/perms), mint `S10b-tag-push-debug.md`.
