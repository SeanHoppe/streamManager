# Spike A — Results

## Environment

- Date: 2026-05-01
- OS / Python: Windows 11 Home 10.0.26200 / Python 3.12.10
- websockets: installed via `pip install -e ".[dev]"` (>=12.0)
- Test rig: single host, all three processes on 127.0.0.1; bridge + echo_cli + bench_desktop

## Numbers

| Metric | Target | Measured | Verdict |
|---|---|---|---|
| Median round-trip (ms) | ≤ 50 (NFR-P1) | **0.96** | ✓ ~50× headroom |
| p95 round-trip (ms) | — | 1.68 | — |
| p99 round-trip (ms) | — | 8.28 | — |
| Max round-trip (ms) | — | 11.22 | — |
| Throughput (RTT/s, n=1000) | ≥ 500 (NFR-P3) | **852.6** | ✓ |
| Active RAM after 1000-msg burst (MB) | ≤ 50 | **~28** | ✓ |
| Idle RAM (MB) | ≤ 25 (NFR-R1) | not measured | — see notes |
| Bus row count after bench | 2000 (1000 each direction) | **2000** | ✓ |
| Decisions row count | 2000 (one per msg) | **2000** | ✓ |
| WAL durability under SIGKILL mid-stream | no message loss | **not tested** | gap |

## How it was run

```
$ python -m stream_manager &           # bridge on 8765 (Desktop) / 8766 (CLI)
$ python spikes/poc_pipe/echo_cli.py & # fake CLI side
$ python spikes/poc_pipe/bench_desktop.py --n 1000
n           = 1000
elapsed     = 1.173 s
throughput  = 852.6 msg/s
median (ms) = 0.96
p95    (ms) = 1.68
p99    (ms) = 8.28
min    (ms) = 0.73
max    (ms) = 11.22
```

DB inspection post-run:
```
messages=2000 decisions=2000 sessions=1
by direction: [('cli_to_desktop', 1000), ('desktop_to_cli', 1000)]
```

## Surprises

- **Latency much lower than budgeted.** Sub-1 ms median *with* synchronous SQLite WAL writes per message in the critical path. The doc's 50 ms budget was set conservatively; the real floor is hundreds of microseconds for the in-process plumbing. The latency budget will be entirely consumed by the governance API call when it's wired in (Spike B / hardening), not by transport.
- **The bench's "throughput" is round-trip throughput**, not raw send rate. Each ping awaits its reply before the next send, so 852 RTT/s corresponds to ~1700 msg-events/s through the bus (2000 rows in 1.17 s). True one-way send throughput would be considerably higher.
- **Active RAM measured during burst, not after settle.** The 28 MB number is the bridge process post-1000-message burst, not after a settle. A truly idle measurement (a minute after the burst, no clients connected) was not captured in this session — that's the gap on NFR-R1 idle.

## Gaps (deliberately not tested in this pass)

- **SIGKILL durability.** A clean `taskkill /F` at end-of-test doesn't exercise mid-stream crash. To validate FR-MB-1 / NFR-R4 properly: kill the bridge during a bench run, restart, query messages table, confirm row count matches what the bench had acknowledged.
- **Concurrent multi-client load.** Single Desktop client / single CLI client. FR-SM-5 (multi-Desktop broadcast) is implemented (gather over `desktop_clients`) but not exercised.
- **Sustained 100 msg/s soak.** NFR-R1 specifies "active ≤ 50 MB at sustained 100 msg/s" — bench was a 1.17 s burst, not a sustained soak.

## Verdict

**Pipe shape holds.** SQLite WAL + `websockets` + `asyncio` together introduce no latency floor remotely near the 50 ms budget. The architecture's bus-as-critical-path concern (synchronous WAL writes blocking the event loop) is empirically a non-issue at this scale.

The real latency risk in the production path is the governance API call (200–2000 ms per ADR-5), which entirely dominates this microsecond-scale plumbing. That's exactly what Spike B is for. Spike A's signal is that **transport is solved**; effort should go to the brain.

If this spike wins for hardening, the followups are: SIGKILL durability test, sustained soak for NFR-R1, multi-Desktop broadcast load test, and a clean `--help` / `--status` CLI surface in `__main__.py`.

## Implementation note

The doc names the WS router module `stream_manager.py`. We renamed it to `router.py` to avoid the awkward `stream_manager.stream_manager.StreamManager` chain (package and module would share a name). Class is `Router`. Update the requirements doc on next revision.
