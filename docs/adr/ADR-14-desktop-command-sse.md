# ADR-14: desktop_command transport — SSE in v1.1, long-poll deprecated v1.2

- **Status**: Accepted (v1.1)
- **Date**: 2026-05-02
- **Supersedes (partial)**: OQ4 v1.0 lock in `docs/sync-comms-qa.md`
  (long-poll transport for desktop_command), retained as the legacy
  fallback for one minor cycle.
- **Companion**: `docs/v1.1-task-plan.md` Task K.

## Context

The v1.0 sync-comms freeze chose long-poll for the SM → governed-session
desktop_command control plane (`docs/sync-comms-qa.md` OQ4). Rationale at
the time: simplest viable transport, no new server primitives, exercises
the existing `/api/commands/pending` endpoint that the dashboard already
needed. Trade-off: ack latency floor of ~1 s (the OQ4 poll cadence), with
worst-case ~2 s for a row that arrives just after a poll completes.

v1.1 needs sub-second command delivery for two reasons:

1. **Operator-perceived responsiveness**: a `pause` or `request_attention`
   command issued from the dashboard should reach the governed session
   well under the human-perception threshold (~250 ms). At 1 Hz poll the
   p95 ack latency is structurally above that.
2. **HITL surface latency**: `surface_hitl` is dispatched as a desktop
   command. ADR-5 (v1.1) ratchets the latency budget downward; the
   long-poll floor consumes more of that budget than necessary.

The producer side (`stream_manager.desktop_commands.emit_command`) writes
to the same `desktop_commands` WAL row regardless of transport. Only the
*read* path needs to change. SSE is the natural fit: the dashboard already
implements an SSE pattern for `/events` (governance decisions + Mirror)
and the consumer process already depends on `httpx`, which has first-class
streaming support via `httpx.Client.stream`.

## Decision

In **v1.1**:

- **Add** a new endpoint `GET /api/commands/stream?session_id=X` returning
  `text/event-stream`. Server-side filters: `status='pending'`,
  `session_id` match, `session_id != SM_OWN_SESSION_ID`. On connect, the
  handler replays the current pending rows oldest-first; then tails the
  table at a 200 ms cadence and emits any new pending rows (rowid
  cursor). TTL behaviour is preserved — rows older than
  `_DESKTOP_COMMAND_TTL_SECONDS` (30 s) are flipped to `expired` in the
  same connection and are not emitted.
- **Keep** the legacy `GET /api/commands/pending` endpoint unchanged.
- **Add** `transport='long-poll'|'sse'` to `CommandConsumer.__init__`,
  default `'long-poll'` for one-cycle compatibility. The SSE path uses
  `httpx.Client.stream("GET", "/api/commands/stream")` and reconnects
  on transport error with exponential backoff (base 0.5 s, cap 10 s).
  The signature-validate → execute → ack POST chain is unchanged.
- **Add** `--transport` to `tools/sm_consumer.py`, default `long-poll`.
- **Frame shape parity**: a row emitted on the SSE stream has the same
  JSON shape that `/api/commands/pending` returns, so the post-parse
  code path is transport-agnostic.

In **v1.2**:

- Flip `CommandConsumer(transport=...)` default to `'sse'`.
- Remove the `/api/commands/pending` endpoint and the long-poll branch
  in `CommandConsumer.run_forever`.
- Update `tools/sm_consumer.py --transport` to default `'sse'` and emit a
  deprecation warning if `'long-poll'` is passed.

## Rationale

**Why SSE and not WebSockets, gRPC, or NATS.** Direction is one-way (SM →
governed session) — WebSockets' bidirectional plane is unused weight.
gRPC adds a second wire format and a second runtime dependency
(`grpc-tools`). NATS / external message brokers add a deployment
dependency that breaks the single-binary local-dev model. SSE is plain
HTTP, falls back gracefully through proxies, and `httpx` already streams
SSE without an extra library.

**Why a 200 ms tail-poll on the server side instead of bus.subscribe.**
The producer writes through `bus._lock`/`bus._conn` directly without
calling `bus.publish()` (desktop commands are deliberately out-of-band —
they never land in the `messages` table and never trigger
`engine.evaluate`). Adding a `bus.subscribe` callback would require
emitting a synthetic event from `desktop_commands.emit_command`, which
risks cross-talk with engine evaluation. A 200 ms SQL tail-poll on a
single indexed table (one session_id at a time) is cheaper than
re-architecting the bus, and gives the same sub-second user experience.
v1.2 may revisit this if soak data shows the tail-poll is measurable.

**Why default 'long-poll' instead of flipping to 'sse' immediately.**
Existing v1.0 consumers may already be deployed with `tools/sm_consumer.py`
spawned by external hooks. A default flip in v1.1 would silently change
their behaviour mid-cycle. Holding the default at `'long-poll'` for one
minor version (v1.1 → v1.2) gives operators a window to opt in via
`--transport sse` and observe the new behaviour before the breaking
change.

**Why server-side dedupe of replayed rows is not needed.** The SSE
endpoint replays current `status='pending'` rows on connect. A row is
only `'pending'` until acked or expired. After a successful dispatch,
the consumer's ack POST flips the row to `'ok'` (or `'rejected'`),
and the next replay window will exclude it. The window between
"executor fired" and "ack POST landed" is bounded by HTTP RTT (~ms), so
the practical replay-after-reconnect duplication is negligible. As a
defence-in-depth, the consumer maintains an in-process `_dispatched`
set so a same-process reconnect cannot double-fire an executor for a
row whose ack was in-flight.

**Why exponential backoff with a 10 s cap.** Cap matches operator
expectations for "noticeable but not annoying". Base 0.5 s gives fast
recovery from transient network blips. A 10 s ceiling means a downed SM
dashboard never produces more than ~6 reconnect attempts per minute,
keeping logs readable.

## Consequences

- **Latency**: p95 ack-to-emit drops from ~1 s (long-poll @ 1 Hz) to
  ~250 ms (SSE 200 ms tail + HTTP RTT). Validated by
  `tests/test_desktop_command_sse.py::test_sse_producer_to_consumer_under_250ms`.
- **Test surface**: new live-uvicorn fixture mirrors
  `tests/test_dashboard_og7_banner.py`. Long-poll regression test stays
  green.
- **API surface +1 endpoint**: `/api/commands/stream`. The legacy
  `/api/commands/pending` is documented as deprecated in v1.2.
- **Operational**: SSE keeps a long-lived TCP connection per consumer.
  At v1.1's expected fan-out (≤ 4 governed sessions per SM), this is
  trivial. If multi-tenant deployment lands (Task O trigger), revisit
  connection budgeting then.
- **Dependency**: no new runtime deps. `httpx` already supports
  `Client.stream()`.

## Migration path

1. **v1.1.0** (this ADR): SSE endpoint shipped, opt-in via
   `--transport sse`. Long-poll remains the default.
2. **v1.1.x**: operators flip their daemons to `--transport sse`. Soak
   reports include the SSE timing metric.
3. **v1.2.0**: default flips to `'sse'`. `tools/sm_consumer.py` emits a
   deprecation warning when `--transport long-poll` is passed.
4. **v1.3.0** (or v1.2.x if no v1.0 stragglers remain): `/api/commands/pending`
   removed; the long-poll branch in `CommandConsumer` removed.

## References

- `docs/sync-comms-qa.md` OQ4 — original long-poll lock (now partially
  superseded).
- `docs/v1.1-task-plan.md` Task K — implementation scope.
- `dashboard/server.py` — `/api/commands/stream` handler.
- `src/stream_manager/desktop_command_consumer.py` — `CommandConsumer`
  with `transport=` parameter and `_run_sse` / `_consume_sse_stream`
  methods.
- `tests/test_desktop_command_sse.py` — coverage.

## v1.2 status: long-poll removed

In v1.2 (Task D, branch `feat/v1.2-longpoll-removal`) the deprecation
window closed and the legacy long-poll path was removed:

- `GET /api/commands/pending` — deleted. The endpoint now 404s.
- `CommandConsumer.run_forever` long-poll branch — deleted. The
  surviving body unconditionally calls `_run_sse()`.
- `CommandConsumer(transport='long-poll')` — raises `ValueError` with a
  migration message pointing at `CHANGELOG.md` (the v1.2 Removed entry).
- `tools/sm_consumer.py --transport` — accepts only `sse`; the default
  flipped from `long-poll` to `sse`.
- `--poll-interval` flag and the `poll_interval` ctor kwarg were
  removed (they were only consulted on the deleted long-poll branch).

The migration path in this ADR's "v1.3.0 (or v1.2.x …)" bullet
collapsed to v1.2.0; see `CHANGELOG.md` for the operator-facing entry.

This ADR is **kept as the historical record** of the SSE design and the
long-poll deprecation window. It is not superseded.
