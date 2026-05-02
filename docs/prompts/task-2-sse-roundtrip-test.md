# Task 2 — SSE round-trip live test for `hitl_mode_promoted`

**Branch:** `claude/hopeful-sutherland-89389d`
**Base PR:** #16
**Spec ref:** FR-HITL-1 / FR-UI-4 / FR-UI-8 (own ask: live wire test)
**Status:** Indirect coverage only via `direction='internal'` forwarder

## Goal

Add an asyncio integration test that POSTs `/api/hitl/mode` and verifies a `hitl_mode_promoted` SSE event arrives at a connected client within 2 s. Currently covered only indirectly via the `direction='internal'` forwarder; we need an end-to-end live wire test.

## File to create

`tests/test_hitl_mode_sse_roundtrip.py`

## Approach

- Use `httpx.AsyncClient` with the existing FastAPI `app` from `dashboard.server`.
- Use `ASGITransport(app=app)` so we don't need a real port.
- Open a streaming `GET /events` in a background task; concurrently POST `/api/hitl/mode` with `mode="sync"` and `reason="take_action"`.
- Parse SSE frames (split on `\n\n`, find `data:` lines, `json.loads`).
- Assert: within 2 s, a frame arrives whose `type` is `hitl_mode_promoted` AND `metadata.mode == "sync"` AND `metadata.reason == "take_action"` AND `metadata.session_id` matches the POST body.
- Use a temp `gov.db` (`tmp_path` fixture, set `GOV_DB` env var or whatever the server reads).
- Mark the test `@pytest.mark.asyncio`. If `pytest-asyncio` not installed, add to dev extras + `setup.cfg` / `pyproject.toml`.

## Existing tests to mimic

`tests/test_hitl_mode_persist.py` (already does the POST, just doesn't tail SSE).

## Run

```bash
pip install -e . --no-deps && pytest tests/test_hitl_mode_sse_roundtrip.py -x -v
```

Confirm pass; full suite to ensure no regression.

## Out of scope

Testing other SSE events (only `hitl_mode_promoted` for this task).

## When done

Commit, push, report under 150 words.
