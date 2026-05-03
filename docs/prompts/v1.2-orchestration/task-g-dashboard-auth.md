You are implementing **Task G — Browser dashboard auth** from the streamManager v1.2 ship cycle.

## ⚠️ P3 conditional — only run this task if its trigger fires

This task is P3 conditional, mirroring how v1.1 Tasks O and P were gated.

**ONLY run this task if a remote-access signal has arrived** — i.e. the user has explicitly requested that the dashboard be reachable from any host other than localhost, OR a deployment plan has been written that requires non-loopback binding.

Verify before starting:

1. Ask the user (in chat) to confirm: "Is the dashboard intended to bind to a non-loopback interface in v1.2, or otherwise be reached from a remote host?"
2. If the answer is "no" or "stay local-only": STOP, do not implement. Tell the user the trigger has not fired.
3. If the answer is "yes" with a concrete deployment context: proceed.

Also check for prior signal:

```
grep -rn 'remote.*dashboard\|bind.*0\.0\.0\.0\|public_dashboard' docs/ src/ dashboard/
```

If nothing surfaces and the user hasn't given a clear "yes" to the question above, do not proceed.

## Branch + base
- Base your work on `ship/v1.2-scope` (NOT main, NOT ship/v1.1-scope).
- Open PR targeting `ship/v1.2-scope`.
- If `ship/v1.2-scope` does not yet exist, ABORT and tell the user to cut it from `main`.

## ⚠️ CRITICAL: Do-not-touch guard

v1.1.0 was tagged on 2026-05-03 and contains shipped work you MUST NOT revert. The following symbols are load-bearing — verify they exist on your branch before any edit, and do not modify them:

| From task | File | Symbols/sections |
|-----------|------|------------------|
| I | `src/stream_manager/governance.py` | `_install_lazy_hydrator`, `GovernanceEngine.hydrated` field |
| I | `tools/perf_probe.py` | entire file (durable artifact) |
| J | `src/stream_manager/cli_pool.py` | `CliPool`, `CliWorker`, PID file `.bridge/cli-pool.pids` |
| J | `src/stream_manager/governance.py` | `GovernanceEngine.cli_pool` field |
| J | `dashboard/server.py` | cli_pool lifecycle (boot init, shutdown) |
| K | `src/stream_manager/desktop_command_consumer.py` | `transport` kwarg, `_run_sse`, `_consume_sse_stream` |
| K | `dashboard/server.py` | `/api/commands/stream` SSE endpoint |
| L | `src/stream_manager/message_bus.py` | `hitl_pending.matched_hash` column + idempotent backfill |
| L | `src/stream_manager/hitl.py` | `dispatch_resolution` reads `matched_hash` w/ legacy split-on-colon fallback |
| M | `src/stream_manager/governance.py` | `EngineRegistry.start_refresh/stop_refresh/refresh_all/refresh_status`, `last_refresh_ts`, `_refresh_timer` |
| M | `dashboard/server.py` | refresh start/stop hooks, `/api/registry/active` payload |
| N | `src/stream_manager/wirecli.py` | entire module — `WireProtocolError`, `WireSchemaVersionError`, `WireTransportError` |
| N | `src/stream_manager/cli_client.py` | `transport` kwarg, `cli_transport()` resolver |

All symbols above must be preserved by this task. Auth should layer on top of existing routes via middleware, not modify route handlers.

Before editing any of `governance.py`, `dashboard/server.py`, `message_bus.py`, `hitl.py`, `desktop_command_consumer.py`, `cli_client.py`, `wirecli.py`, run:

```
grep -nE 'cli_pool|_install_lazy_hydrator|matched_hash|_run_sse|start_refresh|stop_refresh|WireProtocolError' src/stream_manager/governance.py src/stream_manager/message_bus.py src/stream_manager/hitl.py src/stream_manager/desktop_command_consumer.py dashboard/server.py src/stream_manager/cli_client.py src/stream_manager/wirecli.py
```

…and confirm the symbols exist. If any are missing, STOP and report — do not proceed. Likely silent-revert trap.

## Task brief

Add authentication to the browser dashboard so it is safe to expose on a non-loopback interface.

Scope:
- **Auth model**: bearer token, generated at first boot and persisted under `.bridge/dashboard-token` (mode 0600). Single-tenant — operator copies token from local file into browser. No password DB, no user accounts.
- **Middleware**: a single auth middleware in `dashboard/server.py` that wraps every route EXCEPT a small login page that accepts the token and sets a session cookie. Both the `/events` SSE stream and `/api/commands/stream` SSE endpoint (Task K — DO NOT modify the endpoint itself) get auth via the middleware layer.
- **Login flow**: `GET /login` renders a token-input page; `POST /login` validates the token and sets an HttpOnly + SameSite=Strict cookie; subsequent requests carry the cookie.
- **Logout**: `POST /logout` clears the cookie.
- **Bind hardening**: when auth is enabled, the dashboard MAY bind to a non-loopback interface; when auth is disabled, refuse to bind to anything other than `127.0.0.1` (fail fast with a clear error on startup).
- **CLI override**: `--insecure-no-auth` flag for explicit local-only operation. Without auth, only loopback binding is permitted.
- **Constant-time comparison** for token check (`hmac.compare_digest`).
- **CHANGELOG** entry: "Browser dashboard auth (bearer token via HttpOnly cookie). Required when binding non-loopback."

Out of scope (defer to later):
- Multi-user / RBAC.
- OAuth / SSO.
- HTTPS termination (operator's responsibility — document putting a TLS reverse proxy in front).

## DOD

- [ ] Fresh boot generates `.bridge/dashboard-token` with mode 0600.
- [ ] Unauthenticated request to any non-`/login` route returns 401 (or redirect to `/login`) when auth is enabled.
- [ ] Authenticated request (valid cookie) succeeds against `/events`, `/api/registry/active`, `/api/commands/stream`, dashboard static assets.
- [ ] Wrong token on `POST /login` returns 401 and does NOT set a cookie.
- [ ] Token comparison uses `hmac.compare_digest`.
- [ ] Without `--insecure-no-auth`, attempting to bind non-loopback without auth fails fast with a clear error.
- [ ] `tests/test_dashboard_auth.py` (new) covers: token generation, login success, login failure, protected-route 401, protected-route 200 with cookie, logout clears.
- [ ] CHANGELOG updated. Documentation updated with operator setup steps and the "put TLS in front" note.
- [ ] No changes to v1.1.0 do-not-touch symbols. SSE endpoints continue to function under auth via middleware only.
- [ ] `pytest -q` passes end-to-end.

## Final verification before opening PR

```
git --no-pager diff origin/ship/v1.2-scope..HEAD --stat
```

Diff stat MUST show only the files you intentionally added/modified for this task. Expected files:
- `dashboard/server.py` (modified — middleware + login/logout routes; do NOT touch `cli_pool` lifecycle, `/api/commands/stream` endpoint internals, refresh hooks, or `/api/registry/active` payload)
- `dashboard/static/login.html` (new)
- `tests/test_dashboard_auth.py` (new)
- `CHANGELOG.md` (modified)
- documentation (modified)

If the diff stat shows ANY change to symbols in the do-not-touch table above, STOP, report which files, do not open PR. Likely silent-revert.

Run `pytest -q` end-to-end. Paste tail in PR body.

Report back when PR is open with: PR URL, diff stat, pytest tail.
