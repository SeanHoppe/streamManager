"""v2.1 P3 (FR-PPP-14) — self-monitor hard-guard graduation.

P1a `sm_brain_id` was an optional kwarg (defense-in-depth). P3
graduates it to MANDATORY:

  - Missing/empty `sm_brain_id` raises `RuntimeError` at the call site
    (loud failure mode per `feedback_no_self_monitor.md`).
  - Passing a matching `sessionId` still drops the candidate row
    (existing P1a behaviour preserved).
  - Calling `build_audit_probe_candidates()` without the kwarg raises
    `TypeError` (mandatory keyword-only argument).

This is the load-bearing graduation: the failure mode flips from
silent ("filter not applied") to loud (immediate exception) — see
`docs/v2.1-p3-scope.md` §4 site #4.
"""

from __future__ import annotations

import datetime as _dt

import pytest

from stream_manager.session_watcher import SessionRecord, SessionWatcher


def _make_watcher(tmp_path) -> SessionWatcher:
    return SessionWatcher(
        bus=object(),
        sessions_dir=tmp_path / "sessions",
        sm_cwd=str(tmp_path / "sm-cwd"),
        sm_session_id="sm-self",
    )


def _record(sid: str, cwd: str) -> SessionRecord:
    now = _dt.datetime.now(_dt.UTC).isoformat()
    return SessionRecord(
        sessionId=sid, pid=12345, cwd=cwd,
        entrypoint="claude", registered_at=now, last_seen=now,
        state="active",
    )


def test_missing_sm_brain_id_kwarg_raises_type_error(tmp_path):
    """The kwarg has no default ⇒ calling without it is a TypeError."""
    w = _make_watcher(tmp_path)
    w._sessions["proj-a"] = _record("proj-a", "C:/u/proj-a")
    with pytest.raises(TypeError):
        w.build_audit_probe_candidates()  # type: ignore[call-arg]


def test_empty_string_sm_brain_id_raises_runtime_error(tmp_path):
    """Empty `sm_brain_id` is treated as "env var unset" ⇒ loud raise."""
    w = _make_watcher(tmp_path)
    w._sessions["proj-a"] = _record("proj-a", "C:/u/proj-a")
    with pytest.raises(RuntimeError, match="SM_OWN_SESSION_ID required"):
        w.build_audit_probe_candidates(sm_brain_id="")


def test_matching_sm_brain_id_still_drops_row(tmp_path):
    """P1a defense-in-depth behaviour preserved: passing the SM brain_id
    still excludes the matching row from the candidate list."""
    w = _make_watcher(tmp_path)
    w._sessions["sm-self"] = _record("sm-self", "C:/u/sm")
    w._sessions["proj-a"] = _record("proj-a", "C:/u/proj-a")
    cands = w.build_audit_probe_candidates(sm_brain_id="sm-self")
    ids = [c.brain_id for c in cands]
    assert "sm-self" not in ids
    assert "proj-a" in ids


def test_non_matching_sm_brain_id_drops_nothing(tmp_path):
    """If no row matches sm_brain_id, all active rows are kept."""
    w = _make_watcher(tmp_path)
    w._sessions["proj-a"] = _record("proj-a", "C:/u/proj-a")
    w._sessions["proj-b"] = _record("proj-b", "C:/u/proj-b")
    cands = w.build_audit_probe_candidates(sm_brain_id="never-matches")
    ids = sorted(c.brain_id for c in cands)
    assert ids == ["proj-a", "proj-b"]


def test_brain_id_filter_still_works_with_mandatory_sm_brain_id(tmp_path):
    """The optional prefix-include filter coexists with the mandatory
    `sm_brain_id` kwarg."""
    w = _make_watcher(tmp_path)
    w._sessions["proj-a-1"] = _record("proj-a-1", "C:/u/proj-a")
    w._sessions["proj-b-1"] = _record("proj-b-1", "C:/u/proj-b")
    cands = w.build_audit_probe_candidates(
        sm_brain_id="sm-self", brain_id_filter="proj-a",
    )
    ids = [c.brain_id for c in cands]
    assert ids == ["proj-a-1"]
