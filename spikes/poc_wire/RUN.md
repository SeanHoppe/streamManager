# Spike C — "Prove the wire"

WireCLI wraps a subprocess and exposes its stdio over a WebSocket server.
Validates that the IPC story (subprocess + stdio + WS multiplexing + ANSI
strip + lifecycle management) works end-to-end. No bus, no governance.

## Setup

Same as Spikes A and B:
```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -e ".[dev]"
```

## Run

**Terminal 1 — WireCLI wrapping the bundled echo subprocess (no claude needed):**
```bash
python -m spikes.poc_wire.run_wire
```

**Terminal 2 — smoke client:**
```bash
python -m spikes.poc_wire.wire_test "hello" "second message"
```

**Wrapping the real claude binary:**
```bash
python -m spikes.poc_wire.run_wire -- claude --no-browser
```
or with a specific output mode:
```bash
python -m spikes.poc_wire.run_wire -- claude --print "say hi"
```
Then send your prompt from `wire_test.py` (or any WS client of your choice).

**Multi-client broadcast test:**
Start the wire, then open two `wire_test` clients in two terminals; send from
either, observe both receive the subprocess output.

## Targets

| Hypothesis | Source | Pass condition |
|---|---|---|
| Subprocess stdin/stdout proxies through a WS client | FR-CC-1 | echo response visible in `wire_test` |
| ANSI escape sequences stripped before forwarding | FR-CC-2 | no `\x1b` bytes in client output |
| Subprocess exits cleanly when wire shuts down | implicit | `returncode != None` after teardown |
| Multi-Desktop broadcast | FR-SM-5 | two clients both see the same reply |

## Methodology

The `echo_subprocess.py` is a stand-in for `claude` so the spike is
self-contained. It deliberately emits ANSI color codes so the strip path
gets exercised. Real-claude testing is a manual user step (the `claude`
binary on this machine is the same one running this Code session, so
recursive invocation here would be confusing — left to the user to run
in a separate terminal when they want).

## What goes in `RESULTS.md`

The four target rows above plus surprises and any FR-CC-3 (`--output-format
json`) findings if claude was actually exercised.
