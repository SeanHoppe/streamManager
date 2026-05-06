# CLI Reference

---

## End-user commands

### `sm` — operator CLI

Installed via `pip install -e .` as the `sm` entry point.

```
sm [--db PATH] [--dashboard-url URL] <command>
```

| Flag | Default | Description |
|---|---|---|
| `--db PATH` | `$GOV_DB` or `.claude/gov.db` | Governance DB path |
| `--dashboard-url URL` | `$SM_DASHBOARD_URL` | Dashboard base URL for registry-sourced active flag |

#### `sm sessions list`

Print all sessions as a fixed-width table.

```powershell
sm sessions list

# emit JSON (one object per line)
sm sessions list --json

# source active flag from registry
sm --dashboard-url http://localhost:8765 sessions list
```

Output columns: `session_id`, `started_at`, `last_msg_ts`, `active`

Active flag resolution:
1. If `--dashboard-url` set → calls `GET /api/registry/active`
2. Otherwise → `sessions.ended_at IS NULL` from `gov.db`

#### `sm sessions tail <session_id>`

Stream a session's bus envelopes as JSONL on stdout. Runs until Ctrl-C.

```powershell
sm sessions tail abc-123

# custom poll interval (default 250 ms)
sm sessions tail abc-123 --poll-ms 500
```

Each output line is a JSON object with: `session_id`, `timestamp`, `type`, `context`, `metadata`.

---

### Environment variables (end-user)

| Variable | Purpose |
|---|---|
| `GOV_DB` | Override default `.claude/gov.db` path for all `sm` commands |
| `SM_DASHBOARD_URL` | Equivalent to `sm --dashboard-url`; avoids repeating the flag |

---

## Dashboard

```
http://localhost:8765
```

Three themes selectable in-app: **Obsidian** · **Phosphor** · **Paper**

REST endpoints (read-only):

| Endpoint | Returns |
|---|---|
| `GET /api/registry/active` | `{"active_session_ids": [...]}` |

---

## Developer commands

### Install

```powershell
# editable install with dev extras (run from repo root)
pip install -e ".[dev]"
pip install -r dashboard/requirements.txt
```

If import fails after switching worktrees:

```powershell
pip install -e . --no-deps
```

### Test suite

```powershell
# full suite
pytest

# fast tier only (no slow integration tests)
pytest -m "not slow"

# alignment eval harness (drives real claude -p; opt-in)
pytest -m alignment_eval
```

### Lint and type-check

```powershell
ruff check .
mypy src tests
```

---

### `tools/soak_driver.py` — Tier-3 soak

Runs a 30-minute synthetic soak: spawns uvicorn, pumps 60 governance events, tracks psutil metrics, writes a markdown report.

```powershell
$env:BRIDGE_API_GOV = "1"
python tools/soak_driver.py `
    --port 8766 `
    --gov-db tmp/soak_gov.db `
    --total-seconds 1800 `
    --interval-seconds 30 `
    --cli-pool-size 2
```

| Flag | Default | Description |
|---|---|---|
| `--port` | 8765 | Uvicorn port for soak run |
| `--gov-db` | `tmp/soak_gov.db` | Isolated DB (does not touch `.claude/gov.db`) |
| `--total-seconds` | 1800 | Total soak duration |
| `--interval-seconds` | 30 | Seconds between synthetic events |
| `--cli-pool-size` | 2 | CliWorker pool size (always pass 2; default 0 reproduces v1.0 cold-start regression) |
| `--seed` | 4242 | RNG seed for synthetic corpus |

Exits 0 on PASS, 2 on FAIL. Report written to `reports/soak-{ISO-ts}.md`.

### `tools/cli_soak.py` — Real-CLI replay

Replays a captured transcript through the governance pipeline. Validates parse-success + p95 latency. Optional drift analysis.

```powershell
$env:BRIDGE_API_GOV = "true"
python tools/cli_soak.py `
    --transcript <path>.jsonl `
    --intent . `
    --cli-pool-size 2
```

| Flag | Description |
|---|---|
| `--transcript PATH` | Required. JSONL transcript to replay |
| `--intent PATH` | Directory to load as project context |
| `--max-messages N` | Stop after N messages |
| `--compare PATH` | Drift comparison baseline |
| `--cli-pool-size N` | Pool size (same note as soak_driver) |

### `tools/alignment_eval.py` — Alignment eval harness

Runs golden-row regression tests against the decision graph. Drives real `claude -p`. Used to produce `reports/alignment-eval-*.md`.

```powershell
# run with CI gate (exits non-zero on regression)
python tools/alignment_eval.py --ci-gate
```

### `tools/hook_evaluate.py` — PreToolUse hook

Direct entry point for the governance hook. Not normally called manually — wired via `.claude/settings.json`. Can be invoked directly for debugging:

```powershell
echo '{"tool": "Bash", "input": {"command": "ls"}}' | python tools/hook_evaluate.py
```

### `tools/cassette_record.py` — Cassette recorder

Records and replays governance cassettes for deterministic test coverage. Used during development to capture new bus envelope types.

```powershell
python tools/cassette_record.py --help
```

---

## Installed entry points summary

| Command | Source | Audience | Purpose |
|---|---|---|---|
| `sm` | `tools/sm_cli.py` | End-user | Session listing and bus tail |
| `stream-manager` | `src/stream_manager/__main__.py` | Dev | Version info / scaffold |
| `uvicorn dashboard.server:app` | `dashboard/` | End-user | Dashboard + LM worker |
| `python tools/soak_driver.py` | `tools/soak_driver.py` | Dev | Tier-3 soak |
| `python tools/cli_soak.py` | `tools/cli_soak.py` | Dev | Real-CLI replay harness |
| `python tools/alignment_eval.py` | `tools/alignment_eval.py` | Dev | Golden-row alignment eval |
| `python tools/hook_evaluate.py` | `tools/hook_evaluate.py` | Dev | Direct hook invocation |
| `python tools/cassette_record.py` | `tools/cassette_record.py` | Dev | Cassette record/replay |
