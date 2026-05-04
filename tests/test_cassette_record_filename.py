"""P1 / v1.3: cassette recorder filename collision guard.

`tools/cassette_record.py` previously derived the output filename from
`_dt.date.today().isoformat()` only — same-day re-record silently
clobbered the prior cassette in place (M2 had to recover from the
v1.2.0 tag). The hardening adds:

  * Default behaviour: append a UTC HHMMSS suffix so successive runs
    land at distinct paths.
  * `--allow-overwrite`: opt-in legacy filename shape (clobbers in
    place; for operators who genuinely want to refresh today's
    cassette in-place).

These tests exercise the path-resolution helper directly. They do NOT
spawn the recorder subprocess (which requires `claude` on PATH).
"""

from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import cassette_record  # noqa: E402  - script-style import is intentional


def test_default_path_includes_utc_hhmmss_suffix(tmp_path: Path) -> None:
    """Default mode appends a UTC HHMMSS suffix so re-records do not clobber."""
    path = cassette_record._resolve_cassette_path(tmp_path, allow_overwrite=False)
    today = _dt.date.today().isoformat()
    name = path.name
    # Shape: soak_cassette_<YYYY-MM-DD>T<HHMMSS>Z.jsonl
    assert name.startswith(f"soak_cassette_{today}T"), name
    assert name.endswith("Z.jsonl"), name
    # Extract the HHMMSS chunk and assert numeric.
    hhmmss = name[len(f"soak_cassette_{today}T"):-len("Z.jsonl")]
    assert len(hhmmss) == 6, name
    assert hhmmss.isdigit(), name


def test_default_two_calls_yield_distinct_paths_when_seconds_differ(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Same-day re-record at a different second must land at a distinct path."""
    # Real ``datetime`` and ``date`` from stdlib — patch the alias on the
    # cassette_record module to bypass the test rather than fight class-
    # method semantics on the stdlib types.
    fixed_today = _dt.date(2026, 5, 4)
    times = iter([
        _dt.datetime(2026, 5, 4, 12, 0, 0, tzinfo=_dt.timezone.utc),
        _dt.datetime(2026, 5, 4, 12, 0, 1, tzinfo=_dt.timezone.utc),
    ])

    class _FakeDate:
        @staticmethod
        def today():
            return fixed_today

    class _FakeDt:
        timezone = _dt.timezone

        class datetime:  # noqa: N801 - matches stdlib API
            @staticmethod
            def now(tz=None):
                return next(times)

        date = _FakeDate

    monkeypatch.setattr(cassette_record, "_dt", _FakeDt)

    p1 = cassette_record._resolve_cassette_path(tmp_path, allow_overwrite=False)
    p2 = cassette_record._resolve_cassette_path(tmp_path, allow_overwrite=False)
    assert p1 != p2, (p1, p2)
    assert p1.name == "soak_cassette_2026-05-04T120000Z.jsonl", p1
    assert p2.name == "soak_cassette_2026-05-04T120001Z.jsonl", p2


def test_allow_overwrite_uses_legacy_date_only_filename(tmp_path: Path) -> None:
    """`--allow-overwrite` keeps the legacy `<date>.jsonl` shape (clobbers in place)."""
    path = cassette_record._resolve_cassette_path(tmp_path, allow_overwrite=True)
    today = _dt.date.today().isoformat()
    assert path.name == f"soak_cassette_{today}.jsonl", path


def test_allow_overwrite_re_resolves_to_same_path(tmp_path: Path) -> None:
    """Two `--allow-overwrite` resolutions on the same UTC date land at the
    same path — that is the documented in-place clobber semantics.
    """
    p1 = cassette_record._resolve_cassette_path(tmp_path, allow_overwrite=True)
    p2 = cassette_record._resolve_cassette_path(tmp_path, allow_overwrite=True)
    assert p1 == p2


def test_default_collision_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """P1 / v1.3 review fix (Fix A): two recorder runs landing at the same
    UTC second must NOT silently clobber each other. The helper must raise
    ``FileExistsError`` when ``allow_overwrite=False`` and the resolved
    path already exists.

    Patch the recorder's ``_dt`` reference so HHMMSS lands deterministically,
    pre-create the file at the resolved path, then call the helper.
    """
    fixed_today = _dt.date(2026, 5, 4)
    fixed_now = _dt.datetime(2026, 5, 4, 12, 34, 56, tzinfo=_dt.timezone.utc)

    class _FakeDate:
        @staticmethod
        def today():
            return fixed_today

    class _FakeDt:
        timezone = _dt.timezone

        class datetime:  # noqa: N801 - matches stdlib API
            @staticmethod
            def now(tz=None):
                return fixed_now

        date = _FakeDate

    monkeypatch.setattr(cassette_record, "_dt", _FakeDt)

    expected_name = "soak_cassette_2026-05-04T123456Z.jsonl"
    pre_existing = tmp_path / expected_name
    pre_existing.write_text("collision-bait\n", encoding="utf-8")

    with pytest.raises(FileExistsError) as exc_info:
        cassette_record._resolve_cassette_path(tmp_path, allow_overwrite=False)

    msg = str(exc_info.value)
    assert "cassette already exists" in msg
    assert "--allow-overwrite" in msg
    # Pre-existing file must NOT have been clobbered.
    assert pre_existing.read_text(encoding="utf-8") == "collision-bait\n"
