"""v2.1 P1a (P3 preview) — self-monitor candidate-list filter.

Defense-in-depth test: `session_watcher.build_audit_probe_candidates`
MUST drop any active session whose `sessionId` matches the
``sm_brain_id`` argument (SM's own brain_id). Per
`feedback_no_self_monitor.md`, the primary guard is the
registration-time `_is_self_session` check; this candidate-list filter
is the last-line drop so the operator never sees SM's own JSONL in the
disambiguation prompt.

Also covers:
  - rows with empty `slug` (cwd unparseable) are skipped — operator
    would otherwise see a broken `~/.claude/projects//<sid>.jsonl`
    path with a double-slash.
  - `brain_id_filter` (prefix-include) trims the list for the
    self-monitor test scenarios in P3.

P3 elevates this from defense-in-depth to a hard guard. P1a covers
the filter itself; P3 will add the negative-control synthetic stream
+ hallucination detector.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

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


def test_sm_brain_id_dropped(tmp_path):
    """Candidate list MUST exclude any session whose id == sm_brain_id."""
    w = _make_watcher(tmp_path)
    w._sessions["sm-self"] = _record("sm-self", "C:/Users/sm/repo")
    w._sessions["proj-a"] = _record("proj-a", "C:/Users/u/proj-a")
    cands = w.build_audit_probe_candidates(sm_brain_id="sm-self")
    ids = [c.brain_id for c in cands]
    assert "sm-self" not in ids
    assert "proj-a" in ids


def test_empty_slug_row_skipped(tmp_path):
    """A row whose `cwd` produces an empty `slug` MUST be skipped (would
    resolve to `~/.claude/projects//<sid>.jsonl` — broken path)."""
    w = _make_watcher(tmp_path)
    w._sessions["proj-a"] = _record("proj-a", "C:/Users/u/proj-a")
    # `cwd=""` and `cwd="/"` both produce empty slug after strip("-").
    w._sessions["bad-empty"] = _record("bad-empty", "")
    w._sessions["bad-slash"] = _record("bad-slash", "/")
    # v2.1 P3 hard guard: sm_brain_id is mandatory; pass the watcher's
    # own session id as the sentinel (no row matches it here).
    cands = w.build_audit_probe_candidates(sm_brain_id="sm-self")
    ids = [c.brain_id for c in cands]
    assert "proj-a" in ids
    assert "bad-empty" not in ids
    assert "bad-slash" not in ids


def test_brain_id_filter_prefix_include(tmp_path):
    """`brain_id_filter` keeps only rows whose sessionId startswith it."""
    w = _make_watcher(tmp_path)
    w._sessions["proj-a-1"] = _record("proj-a-1", "C:/u/proj-a")
    w._sessions["proj-b-1"] = _record("proj-b-1", "C:/u/proj-b")
    cands = w.build_audit_probe_candidates(
        sm_brain_id="sm-self", brain_id_filter="proj-a",
    )
    ids = [c.brain_id for c in cands]
    assert ids == ["proj-a-1"]


def test_inactive_sessions_skipped(tmp_path):
    """Only `state="active"` rows appear in the candidate list."""
    w = _make_watcher(tmp_path)
    active = _record("alive", "C:/u/alive")
    exited = _record("dead", "C:/u/dead")
    exited.state = "exited"
    w._sessions["alive"] = active
    w._sessions["dead"] = exited
    cands = w.build_audit_probe_candidates(sm_brain_id="sm-self")
    ids = [c.brain_id for c in cands]
    assert ids == ["alive"]


def test_candidate_path_under_claude_projects(tmp_path):
    """Built jsonl_path MUST be under `~/.claude/projects/<slug>/`."""
    w = _make_watcher(tmp_path)
    w._sessions["s1"] = _record("s1", "C:/Users/u/proj-a")
    cands = w.build_audit_probe_candidates(sm_brain_id="sm-self")
    assert len(cands) == 1
    c = cands[0]
    expected_prefix = str(Path.home() / ".claude" / "projects")
    assert c.jsonl_path.startswith(expected_prefix)
    assert c.jsonl_path.endswith("s1.jsonl")
    assert c.slug  # non-empty
