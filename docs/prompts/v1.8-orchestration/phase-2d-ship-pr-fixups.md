You are implementing **Phase P2d — Ship PR fixups** from the streamManager v1.8 cycle.

This phase is **conditional** — only mint if v1.8 P2 (`ship/v1.8-shipgate-finalize`) PR review surfaces blockers (cavecrew-reviewer findings, manual review comments, CI failures). Pattern mirrors v1.6 P2 fixups (`docs(v1.6 P2): caveman-review fixups for PR #87`) and v1.7 P1 fixups (`docs(v1.7 P1): caveman-review fixup for PR #89`).

## Branch + base

- Base: `ship/v1.8-shipgate-finalize` branch (the v1.8 P2 PR branch — fixups land on the SAME branch, NOT a new one).
- PR target: `main` (already open as the v1.8 P2 ship PR).
- This is a fixup commit pushed to the existing PR branch, not a new PR.

## ⚠️ CRITICAL: Do-not-touch guard

Same as v1.8 P2 — finalize PR is docs / reports only. Fixups are docs / reports only. NO `src/` or `tools/` hunks unless the reviewer specifically requested a code-side fix that's strictly cosmetic (e.g. typo in a comment) AND it's a single-line surgical edit.

If the reviewer flagged a substantive code issue, do NOT fix it on the ship branch — that contaminates the finalize PR's diff. Instead:
1. Mint a new branch (e.g. `feat/v1.8-postship-fixup`) off `main`
2. Land the code fix in a separate PR
3. Re-run the relevant ship-gate verification (alignment-eval, soak smoke) on the post-fix code
4. Decide whether to revert the v1.8.0 tag intent OR ship v1.8.0 with caveat + immediate v1.8.1 follow-up

## Task brief

Triage the reviewer findings:

1. **Doc-only findings (typos, broken links, missing context, unclear bullet, ADR-5 number drift):** fix on the ship branch as a fixup commit. Push, re-verify mergeable, confirm with reviewer.
2. **Report numerical findings (ADR-5 cell value disagrees with soak report):** verify against the actual soak report; if ADR-5 wrong, fix on ship branch. If soak report wrong (unlikely — soak driver auto-generates), re-run soak.
3. **Code-side findings:** see "Do-not-touch guard" above — separate PR + decide on v1.8.0 tag scheduling.
4. **Cross-PR seam findings (e.g. ADR-5 cites wrong report path):** doc fix on ship branch.

### Deliverables

For each reviewer finding:
1. Quote the finding in the fixup commit message
2. Cite the file:line of the fix
3. State the disposition (fixed in this branch / deferred to separate PR / acknowledged as nit)
4. Re-verify mergeable + clean

Fixup commit message convention (matches `b556966`, `057fdba`):

```
docs(v1.8 P2): caveman-review fixup for PR #<n>

<one-paragraph triage of findings>

<file>: <line>: fix description (severity)
<file>: <line>: fix description (severity)
...

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

### After fixup

- Re-confirm `gh pr view <n> --json mergeable,mergeStateStatus` is `MERGEABLE` + `CLEAN`
- Re-run cavecrew-reviewer on the updated branch tip
- If reviewer returns CLEAN, proceed to merge

## DOD

- [ ] All doc-only / report findings addressed in fixup commit on ship branch
- [ ] Code-side findings deferred to separate PR (with link in fixup commit message)
- [ ] PR remains MERGEABLE + CLEAN
- [ ] Re-running cavecrew-reviewer returns CLEAN OR remaining findings explicitly accepted
- [ ] No new src/tools hunks on ship branch (verify with diff)

## Mint-new-phase rule

After P2d ships:
- If reviewer continues to flag the same finding after fixup: escalate to operator; do NOT bypass.
- If a code-side finding requires a separate PR: that PR becomes a new mini-phase, not P2d. Track in v1.9 backlog if it slips past v1.8.0.
- If ship-gate numbers shift after a code-side fix: re-run Tier-3 soak; ship-gate finalize re-runs from §3.

Report back when fixup pushes with: PR URL, reviewer findings list, disposition per finding, post-fixup mergeable + clean confirmation.
