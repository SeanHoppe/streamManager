1. Expanded walkthrough

  /report-research

  - Catalog — Fans out one agent per corpus area (instructions, trackers, oversight cards, verification reports,
  decisions). Each agent sorts that area's artifacts into categories (orchestration prompt, tasklist, phase spec,
  oversight card, tracker, verification report, governance doc, dead residue) and tags each with dominant failure-modes.
  This builds a map of where pathologies cluster before any finding is made, and surfaces dead/superseded files early.
  - Find — Runs a dedicated finder per failure-mode lens, each blind to the others so coverage is by-kind not by-luck:
  rework-loop (one defect re-attacked across renamed fix/reqa rounds), stall (work gated on a human/unbuilt dependency
  that just ages), stale (marked DONE but contradicted by evidence), self-destructive (green-by-bypass, guardrails that
  fail their own JOB, concurrency wiping in-flight work), intent-reality-gap (docs ahead of built reality, non-monotonic
  pass counts), scaffolding-debt (effort spent debugging the test harness not the product), code-defect (file-localized
  testable bugs). Quality bar: ≥2 distinct evidence paths, root cause over symptom. thorough arg re-sweeps up to 3
  rounds, asking only for new tail instances, stopping when a round comes up dry.
  - Verify — Each candidate goes to 2 reviewers in isolated contexts told to refute, not agree — they must open the
  cited files and either confirm, mark overstated (real but inflated → de-escalated), or refuted (doesn't hold). An
  adjudicator reads both verdicts and emits the final vetted finding; survives=false only on a decisive contradiction.
  This is the gate that stops plausible-but-wrong findings reaching the report.
  - Report — Survivors only. Writes ./REPORT.md in a fixed house-style (pin the denominator so counts can't silently
  re-baseline, explicit in/out scope, cite invariant IDs when a boundary is touched, every actionable item gets a
  runnable Verify command + binary pass criteria, ASCII-only) plus a self-contained brief per finding, each stamped
  type=code (with real files[]) or type=process. That format is the input contract for the next workflow.

  /report-fixes

  - Split — Parses REPORT.md back into structured findings, re-writes the per-finding briefs, then partitions code
  findings with union-find so any two findings sharing a file land in the same partition. Concurrent partitions are
  therefore file-disjoint — parallel editing can't collide; same-file findings run serially inside one partition.
  - Fix & refute — Each fix is a minimal direct edit confined to the finding's declared files (+ their tests), following
  CLAUDE.md standards and invariants. Then 2 isolated reviewers try to refute the fix (reading current code: is the
  root cause shallow, the fix masking a symptom, breaking callers, violating an invariant?). A bounded correction loop
  (≤2 rounds) applies required fixes. A partition is shippable only if every fix in it is unanimously sound.
  - Proposals — Process findings never touch code. Each becomes a written *.proposal.md: problem, root cause, and a
  specific change to prompts/process/docs/config with cited evidence.
  - Verify & ship — Runs only the relevant tests (targeted jules test for .py, targeted vitest for .ts/.tsx), never the
  full suite, with a ≤2-round repair loop. On green: cuts a fresh branch fix/report-<date>-<tag>, stages only changed
  files, commits citing finding IDs, pushes, opens a GitLab MR. Never commits to main, never force-pushes or skips
  hooks. Blocked partitions (skipped or reviewer-flawed) are reported for manual handling.

  2. Generic or repo-specific?

  - Report — Survivors only. Writes ./REPORT.md in a fixed house-style (pin the denominator so counts can't silently
  re-baseline, explicit in/out scope, cite invariant IDs when a boundary is touched, every actionable item gets a
  runnable Verify command + binary pass criteria, ASCII-only) plus a self-contained brief per finding, each stamped
  type=code (with real files[]) or type=process. That format is the input contract for the next workflow.

  /report-fixes

  - Split — Parses REPORT.md back into structured findings, re-writes the per-finding briefs, then partitions code
  findings with union-find so any two findings sharing a file land in the same partition. Concurrent partitions are
  therefore file-disjoint — parallel editing can't collide; same-file findings run serially inside one partition.
  - Fix & refute — Each fix is a minimal direct edit confined to the finding's declared files (+ their tests), following
  CLAUDE.md standards and invariants. Then 2 isolated reviewers try to refute the fix (reading current code: is the
  root cause shallow, the fix masking a symptom, breaking callers, violating an invariant?). A bounded correction loop
  (≤2 rounds) applies required fixes. A partition is shippable only if every fix in it is unanimously sound.
  - Proposals — Process findings never touch code. Each becomes a written *.proposal.md: problem, root cause, and a
  specific change to prompts/process/docs/config with cited evidence.
  - Verify & ship — Runs only the relevant tests (targeted jules test for .py, targeted vitest for .ts/.tsx), never the
  full suite, with a ≤2-round repair loop. On green: cuts a fresh branch fix/report-<date>-<tag>, stages only changed
  files, commits citing finding IDs, pushes, opens a GitLab MR. Never commits to main, never force-pushes or skips
  hooks. Blocked partitions (skipped or reviewer-flawed) are reported for manual handling.

  2. Generic or repo-specific?

  The architecture is generic; the content is hard-wired to certPortal. The reusable skeleton — catalog → dimensional
  finders → 2-reviewer adversarial refutation → routed report → file-partitioned parallel fixes → adversarial fix-review
  → targeted tests → MR — is a portable pattern you could lift to any repo.

  But as written they are specifically tailored to this repo, baked in at multiple layers:

  - Corpus paths — oversight/agents/*/, instructions/**, taste_reports/**, requirements_reports/**, OPEN-ISSUES.md, etc.
  None of these exist in a generic project.
  - Finder lenses — cite real incidents (INC-002 mc/step-reset, ISSUE-001 cron, transport :8003/:18000 down, jinja2
  premature-done, "300 vs 457" denominator). These are certPortal war stories, not abstract heuristics.
  - Invariants & rules — NC-01/02/03, INV-04, REACT-INV-05, TRANS-INV-03, ADR-053, "main is MR-only," ASCII-only for
  Windows cp1252. All certPortal governance.
  - Toolchain — python -m testing.certportal_jules_test, vitest in frontend/, glab mr create, GitLab MR flow.

  So: borrow the harness, rewrite the inputs. To reuse elsewhere you'd swap the CORPUS map, the DIMENSIONS lenses, the
  HOUSE_STYLE rules, the invariant IDs, and the test/ship commands. The control flow (fan-out, loop-until-dry, isolated
  refuters, union-find partitioning, bounded repair) would carry over unchanged.

✻ Cogitated for 28s

※ recap: I created REPORT-WORKFLOWS-SYNOPSIS.md summarizing the /report-research and /report-fixes workflows, then
  expanded each phase and explained they're generic in architecture but hardcoded to this repo. Next action is yours;
  the file is ready if you want edits. (disable recaps in /config)