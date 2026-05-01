# Spike C — Results

## Environment

- Date: 2026-05-01
- OS / Python: Windows 11 Home 10.0.26200 / Python 3.12.10
- Subprocess used: `spikes/poc_wire/echo_subprocess.py` (real-claude testing
  left to user — see RUN.md)
- Wire port: 8770 (chosen distinct from spikes A's 8765/8766)

## Numbers

| Hypothesis | Target | Measured | Verdict |
|---|---|---|---|
| Subprocess stdin/stdout proxies through WS | echo replies | **3/3 prompts echoed** | ✓ |
| ANSI escape stripped before WS forward | no `\x1b` in client output | **none observed** | ✓ |
| Subprocess exits cleanly on wire stop | `returncode != None` after teardown | **PID 26444 reaped after wire kill** | ✓ |
| Multi-client broadcast | both clients receive | **passes in unit test** | ✓ |
| Unit tests | all pass | **8 / 8** (4 strip + 3 wire + 1 smoke) | ✓ |
| Round-trip latency over wire (50 RTTs) | n/a (added) | **median 0.20 ms / p95 0.41 ms** | ~5× faster than Spike A (no bus, no governance) |
| Wire process RAM | n/a (added) | **~26 MB** | comparable to Spike A (28 MB) |
| Subprocess RAM (echo) | n/a (added) | ~4 MB | trivial; varies by subprocess |

## How it was run

Bridge:
```
$ python -m spikes.poc_wire.run_wire --port 8770
2026-05-01 05:28:47 [INFO] cli_client: spawning subprocess: ...echo_subprocess.py
2026-05-01 05:28:47 [INFO] cli_client: subprocess pid=26444
2026-05-01 05:28:47 [INFO] websockets.server: server listening on 127.0.0.1:8770
2026-05-01 05:28:47 [INFO] cli_client: wire WS on ws://127.0.0.1:8770 wrapping pid=26444
```

Client:
```
$ python -m spikes.poc_wire.wire_test --uri ws://127.0.0.1:8770 \
    "first prompt" "second prompt" "third prompt"
[echo] first prompt
[echo] second prompt
[echo] third prompt
```

50-RTT bench:
```
n=50  median=0.20 ms  p95=0.41 ms  min=0.15 ms  max=0.42 ms
```

Hard-kill teardown:
```
$ taskkill /PID 26920 /F  # kill wire
SUCCESS: The process with PID 26920 has been terminated.
$ tasklist /FI "PID eq 26444"  # subprocess
INFO: No tasks are running which match the specified criteria.
```
The subprocess gets reaped via stdin EOF when its parent (wire) dies — even on
hard kill where wire's `_teardown()` doesn't run. This is OS-level hygiene
(stdin pipe closes when parent dies), not something the wire code itself
guarantees on hard kill. Worth noting: graceful teardown also works (verified
in `test_wire_cli_terminates_subprocess_on_stop`).

## Surprises

1. **Initial subprocess output is lost if no client is connected.** The echo
   subprocess emits a "ready" line at startup, before any WS client connects.
   That line gets read by the stdout pump, broadcast to an empty client set,
   and discarded. Two unit tests originally failed waiting for "ready"; the
   fix was to not depend on pre-connect output. **Hardening implication:**
   wire needs either a bounded replay buffer for late-connecting clients,
   or a "session-start" semantics where client connection precedes subprocess
   spawn.

2. **Latency is dominated by Python subprocess pipe IPC**, not WS or
   marshalling. 0.20 ms median round-trip with `echo_subprocess.py` (a
   minimal Python script) is essentially the cost of `read(stdin) + write(stdout)`
   inside the subprocess plus one async drain on each side. Real `claude`
   will be slower because the model call dominates, but the wire's own
   overhead is sub-millisecond.

3. **OS-level cleanup is the safety net.** Even when wire is hard-killed
   (no graceful teardown), the subprocess dies because its stdin pipe
   closes. This is a happy coincidence of how Windows + Python handle
   broken pipes in `input()`, not something the wire architecture
   guarantees. A subprocess that ignores stdin EOF (e.g., one running an
   infinite loop with no input read) would NOT be reaped by hard-killing
   wire — it would orphan. **Hardening implication:** add an explicit
   process-group / job-object teardown for hard-kill scenarios.

## Verdict

**Wire is solved for the structural mechanics.** Subprocess stdin/stdout
proxies cleanly through a WS server, ANSI strip works, multi-client
broadcast works, graceful teardown works, OS-level cleanup acts as a
safety net for hard-kill cases.

The spike's primary "unknown unknowns" risk — does asyncio.subprocess +
websockets compose on Windows for real bidirectional IPC — is **resolved
positively**. The remaining wire questions (`--output-format json`
parsing fidelity, real `claude` interactive vs print modes, backpressure
under sustained load, orphan-resistant teardown) are hardening concerns,
not spike-killers.

If this spike wins for hardening, the followups are: replay buffer for
late-connecting clients, real-claude integration test, `--output-format
json` line-by-line parser, process-group teardown for orphan resistance,
and proper backpressure (drop / pause / disconnect policy when a client
can't drain).

## Gaps deliberately left

- **Real `claude` binary not exercised** in this session. The same binary
  is running this Claude Code conversation; recursive invocation would
  muddy the signal. Documented as a manual user step in `RUN.md`.
- **FR-CC-3 `--output-format json`** not validated. Generic line-buffered
  stdout works for any subprocess; structured parsing is a hardening
  concern.
- **Backpressure** not exercised. The 50-RTT bench fits comfortably in
  the websockets default buffer; no sustained-rate test.
- **Orphan teardown on hard-kill** works coincidentally for stdin-reading
  subprocesses; an explicit process-group / Windows-Job-Object guard is
  needed before this is production-grade.
