# Spike A — "Prove the pipe"

Bus + two WebSocket servers + dummy echo clients + no-op governance. Measures
whether the architecture's transport layer can hold the latency, throughput,
and durability budgets named in the requirements.

## Setup (once)

```bash
python -m venv .venv
source .venv/Scripts/activate     # Git Bash on Windows
pip install -e ".[dev]"
```

## Run (three terminals)

**Terminal 1 — bridge:**
```bash
python -m stream_manager
```

**Terminal 2 — fake CLI echo:**
```bash
python spikes/poc_pipe/echo_cli.py
```

**Terminal 3 — bench:**
```bash
python spikes/poc_pipe/bench_desktop.py --n 1000
```

## Targets

| Metric | Target | Source |
|---|---|---|
| median round-trip latency | ≤ 50 ms | NFR-P1 |
| throughput | ≥ 500 msg/s | NFR-P3 |
| idle RAM | ≤ 25 MB | NFR-R1 |
| WAL durability under SIGKILL | no message loss | NFR-R4 |

## Durability check

1. Start bridge + cli echo.
2. Run a small bench: `python spikes/poc_pipe/bench_desktop.py --n 200`.
3. Note bus stats logged at shutdown (or `sqlite3 .bridge/adaptive_bridge.db "SELECT COUNT(*) FROM messages"`).
4. Restart the bridge, run bench again, verify counts grow correctly across restarts.
5. For SIGKILL: re-run bench while killing the bridge mid-stream (`kill -9`); the bus DB should still parse and contain all rows for any messages whose `INSERT` was acknowledged.

## What to record in `RESULTS.md`

The numbers, the surprises, and a one-line verdict per target (met / missed).
The plan rule is: hardening goes to the spike that surfaced the most surprise,
not necessarily the one with the prettiest numbers.
