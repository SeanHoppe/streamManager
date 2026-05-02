# Task 5 — `axe-core` WCAG audit + report

**Branch:** `claude/hopeful-sutherland-89389d`
**Base PR:** #16
**Spec ref:** NFR-UI-1 — "Audited per release with an automated checker (e.g. `axe-core`)"
**Status:** Not run

## Goal

Run an `axe-core` scan of the live dashboard and commit the report; fix any AA violations found.

## Steps

1. Start the dashboard:
   ```bash
   python -m uvicorn dashboard.server:app --host 127.0.0.1 --port 8765
   ```
   (background)
2. Seed test data:
   ```bash
   python -m stream_manager.cli_client --session axe-test -- echo hello
   ```
   so frames A/B/C all have content.
3. Run `axe-core`. Two viable approaches:
   - **(a) puppeteer + `@axe-core/puppeteer`** in a node script (preferred, fully scriptable). Install dev-only via `package.json` if it doesn't exist; pin dependencies.
   - **(b) playwright + axe** — equivalent, slightly heavier.

   Pick (a). Script path: `tools/axe_audit.mjs`. Output JSON to `reports/axe-{timestamp}.json` and a human-readable summary to `reports/axe-latest.md`.
4. For each violation at `impact: "serious"` or `impact: "critical"`: fix in `dashboard/static/index.html`. Re-run until clean at AA level (impact serious+critical).
5. Commit: tool script + `reports/` entries + any fixes + README note on how to re-run.

## Out of scope

- AAA-level violations.
- Color-only violations already handled by FR-UI-6 label-pairing (those should pass).

## When done

Report under 200 words: count of issues found, count fixed, any deferrals with rationale.
