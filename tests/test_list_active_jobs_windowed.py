"""Phase P2 (v1.3): regression test for ``list_active_jobs`` overfetch bug.

The pre-v1.3 implementation overfetched ``limit * 4`` raw lifecycle rows in
ascending timestamp order and reduced them in Python. With >25 lifecycle
event pairs (default ``limit=100``, 2 rows per pair = 50 rows; plus any
unrelated lifecycle traffic) the raw window could exceed the cap and the
oldest open jobs at the tail of the timestamp-ascending scan would never be
returned.

This test synthesises 100 open background jobs (200 raw envelope rows when
combined with completion events for unrelated closed jobs in the same bus)
and asserts that ``list_active_jobs(limit=100)`` returns all 100 open jobs
without tail truncation. The fix replaces the ``LIMIT * 4`` overfetch with
a SQL window function that picks the latest envelope per ``job_id``
directly, so the ``LIMIT`` applies to the deduplicated open-set rather
than to the raw row stream.
"""

from __future__ import annotations

from stream_manager.lifecycle_bridge import LifecycleBridge, list_active_jobs
from stream_manager.message_bus import MessageBus


def test_list_active_jobs_no_tail_truncation_at_100_pairs(tmp_path):
    """100 open jobs (200 raw rows including unrelated closed pairs) all return."""
    db_path = str(tmp_path / "gov.db")
    bus = MessageBus(db_path)
    bridge = LifecycleBridge(bus=bus)

    # Synthesise 100 open BG jobs. Each is a single *_start envelope —
    # no matching *_end yet, so all 100 must be reported as open.
    open_job_ids = [f"open-{i:03d}" for i in range(100)]
    for jid in open_job_ids:
        assert bridge.on_bg_job_start("s1", jid, name=f"job {jid}") is True

    # Pad the bus with 50 fully-closed pairs so the raw row count is
    # 100 (open starts) + 100 (closed pairs) = 200 envelopes. This
    # exercises the historical bug: the old code's ``LIMIT * 4 = 400``
    # overfetch would still return all 200 rows here, but the test is
    # written so any future regression that re-introduces a bounded
    # overfetch < raw_row_count would drop tail rows.
    closed_job_ids = [f"closed-{i:03d}" for i in range(50)]
    for jid in closed_job_ids:
        bridge.on_bg_job_start("s1", jid, name=f"closed {jid}")
        bridge.on_bg_job_end("s1", jid, exit_code=0)

    # Sanity: 100 open starts + (50 starts + 50 ends) = 200 raw rows on the bus.
    raw_count = bus._conn.execute(
        "SELECT COUNT(*) FROM messages WHERE type='lifecycle'"
    ).fetchone()[0]
    assert raw_count == 200

    out = list_active_jobs(db_path, session_id="s1", limit=100)

    # All 100 open jobs returned; no closed jobs leaked through.
    returned_ids = {j["job_id"] for j in out}
    assert len(out) == 100, (
        f"expected 100 open jobs, got {len(out)} — tail truncation regression"
    )
    assert returned_ids == set(open_job_ids)
    for j in out:
        assert j["status"] == "running"
        assert j["kind"] == "bg_job"
        assert j["ended_at"] is None
        assert j["started_at"] is not None
    bus.close()


def test_list_active_jobs_newest_first_ordering(tmp_path):
    """Returned rows are ordered newest-start first (contract preserved)."""
    db_path = str(tmp_path / "gov.db")
    bus = MessageBus(db_path)
    bridge = LifecycleBridge(bus=bus)

    # Publish in order; later starts should appear earlier in the result.
    for i in range(30):
        bridge.on_bg_job_start("s1", f"j-{i:02d}", name=f"job {i}")

    out = list_active_jobs(db_path, session_id="s1", limit=100)
    assert len(out) == 30
    started = [r["started_at"] for r in out]
    assert started == sorted(started, reverse=True), (
        "list_active_jobs must return newest-start first"
    )
    bus.close()


def test_list_active_jobs_limit_applies_to_open_set_not_raw_rows(tmp_path):
    """``limit`` caps the deduplicated open-set, not the raw row scan.

    Pre-v1.3 the limit applied to a raw ``LIMIT * 4`` overfetch from the
    messages table — so a high-traffic session with many closed pairs
    could exhaust the window before any open job at the tail was seen.
    This asserts the post-fix invariant: with 200 closed-pair rows and
    just 5 open jobs, ``limit=5`` still returns all 5.
    """
    db_path = str(tmp_path / "gov.db")
    bus = MessageBus(db_path)
    bridge = LifecycleBridge(bus=bus)

    # 100 closed pairs first (200 rows) — these were the historical
    # tail-truncators when intermixed with the open jobs.
    for i in range(100):
        jid = f"closed-{i:03d}"
        bridge.on_bg_job_start("s1", jid)
        bridge.on_bg_job_end("s1", jid, exit_code=0)

    # 5 open jobs published last. Under the pre-fix code these would
    # have been the newest, so the ASC overfetch would have skipped
    # them. We assert the post-fix code surfaces them regardless.
    open_ids = [f"open-{i}" for i in range(5)]
    for jid in open_ids:
        bridge.on_bg_job_start("s1", jid)

    out = list_active_jobs(db_path, session_id="s1", limit=5)
    assert {j["job_id"] for j in out} == set(open_ids)
    bus.close()
