# tools/

Dev-only utilities for `streamManager`. Nothing here ships with the
runtime package.

## `axe_audit.mjs` — WCAG audit (NFR-UI-1)

Runs `@axe-core/puppeteer` against the live FR-UI dashboard, writes a
timestamped JSON report and a markdown summary, and exits non-zero if
any **serious** or **critical** violation remains (excluding rules
explicitly out-of-scope for task-5: `color-contrast` and AAA-level).

### Re-run

```bash
# 1. Install dev deps (downloads a vendored Chromium for puppeteer ~ 200 MB).
npm install

# 2. Start the dashboard on port 8765.
python -m uvicorn dashboard.server:app --host 127.0.0.1 --port 8765 &

# 3. (Optional) seed gov.db so all three frames have content.
python -m stream_manager.cli_client --session axe-test -- echo hello

# 4. Run the audit.
node tools/axe_audit.mjs            # default URL = http://127.0.0.1:8765/
node tools/axe_audit.mjs --url=http://staging.example/  # any deploy
```

### Output

- `reports/axe-{ISO-timestamp}.json` — full axe-core result JSON.
- `reports/axe-latest.md` — human-readable summary; counts by impact,
  per-violation node selectors, fix hints.

### Exit codes

| code | meaning                                                             |
| ---- | ------------------------------------------------------------------- |
| `0`  | No serious/critical violations (CI-clean at AA, color-contrast off) |
| `1`  | At least one serious/critical violation outside the scoped rules    |
| `2`  | Tool error (browser launch, navigation, etc.)                       |

### Out of scope

Per `docs/prompts/task-5-axe-core-audit.md`:

- AAA-level violations.
- `color-contrast` — NFR-UI-6 already pairs labels with non-color
  affordances; the existing palette is intentional and the contrast
  ratios in the dim-themed UI are tracked separately.
- CI integration.

## Other tools

- `cli_soak.py` — see governance soak harness docs.
- `monitor.py` — runtime monitor for SM bus.
- `hook_evaluate.py` — pre-tool-use hook entry point.
