You are implementing **Phase P2e — Tag recovery** from the streamManager v1.8 cycle.

This phase is **conditional** — only mint if the v1.8 P2 ship-gate finalize PR merged successfully but `git tag v1.8.0 <merge-sha>` failed OR `git push origin v1.8.0` failed OR a post-tag smoke surfaced a regression.

## Branch + base

- Base: `main` with v1.8 P2 ship-gate finalize merged.
- This phase is local-only (tag operations) UNLESS the recovery requires a fix-PR — in which case branch `ship/v1.8-tag-recovery`.

## ⚠️ CRITICAL: Do-not-touch guard

NEVER force-push a published tag. NEVER reset a remote branch. NEVER use `git tag -f` on `v1.8.0` if the tag already pushed to origin (downstream consumers and ADR-5 baselines reference the SHA). If the tag is wrong, mint `v1.8.1` instead.

NEVER bypass git hooks (`--no-verify`) per global instructions.

## Task brief

Three failure modes:

### A) Tag creation failed locally

```
git tag -a v1.8.0 <merge-sha> -m "..."
# error: ...
```

Diagnose:
- SHA does not exist locally → `git fetch origin main` then retry
- Tag name conflicts → unlikely (v1.8.0 is fresh); investigate stale local tags with `git tag -l v1.8.0` (delete with `git tag -d v1.8.0` if local-only)
- Other → diagnose error message; fix root cause

Fix and retry tag creation. Verify with `git show v1.8.0 --stat` before pushing.

### B) Tag push failed

```
git push origin v1.8.0
# error: ...
```

Diagnose:
- Network / auth → retry
- Pre-receive hook rejection → unlikely on a tag; investigate
- Tag already exists on remote pointing at different SHA → STOP. The tag was already pushed by another session/CI. Verify the remote SHA matches the intended SHA. If yes, P2e is complete. If no, mint `v1.8.1` and document.

### C) Post-tag smoke surfaced a regression

After tag push, a quick post-tag check (e.g. `pip install . && python -c "import stream_manager"` or running the test suite) reveals a regression that ship-gate did not catch.

Triage severity:
- **Trivial (typo in CHANGELOG, broken doc link):** ship `v1.8.1` with the fix. Tag stays.
- **Moderate (a fast-tier test fails on the tagged commit but not on prior local commits):** investigate flaky test vs real regression. If real, ship `v1.8.1` with the fix.
- **Critical (verdict-path break, security regression, ship-gate baseline misrepresented):** consider yanking — coordinate with operator; do NOT yank unilaterally. Document in `## [Unreleased]` of CHANGELOG + ADR-5 §"Caveats" addendum.

### Deliverables

Depending on failure mode:

**A) Local tag failure:**
- Diagnose + fix + retry
- Document the diagnostic steps in a brief postmortem appended to `docs/v1.8-task-plan.md` PHASE P2 P3-disposition block

**B) Push failure:**
- If transient (network/auth): retry + document
- If conflict: investigate + decide (P2e complete vs mint v1.8.1)

**C) Post-tag regression:**
- Land fix on `feat/v1.8.1-<short-desc>` branch
- Tag `v1.8.1` on the merge commit
- Push v1.8.1 tag
- Update CHANGELOG with `## [1.8.1]` entry
- Update ADR-5 §"v1.8 ship-gate baseline" §"Caveats" with a forward pointer to v1.8.1 if the regression invalidates any of the v1.8 baseline numbers

### Post-recovery verification

```
git tag -l "v1.*"
# v1.6.0, v1.7.0, v1.8.0, [v1.8.1 if minted]

git ls-remote --tags origin | grep v1.8
# verify remote tag SHAs match local

gh release list 2>/dev/null | head -5
# if releases are part of the workflow, verify the v1.8 entry
```

## DOD

- [ ] Failure mode classified (A / B / C)
- [ ] Recovery action taken (retry / mint v1.8.1 / yank coordination)
- [ ] Tag operations verified locally + remote
- [ ] If C: v1.8.1 PR merged, tag pushed, CHANGELOG updated, ADR-5 forward pointer added if needed
- [ ] Postmortem appended to `docs/v1.8-task-plan.md` P2 disposition (lessons for v1.9 P2)
- [ ] No force-push of published tag, no `--no-verify` bypass

## Mint-new-phase rule

P2e is the recovery itself. Further follow-ups (e.g. v1.8.2 from a chain of regressions) are minted ad-hoc, not pre-planned.

Report back when recovery completes with: failure mode classification, action taken, post-recovery tag state (`git show v1.8.0 --stat` + remote ls), CHANGELOG state.
