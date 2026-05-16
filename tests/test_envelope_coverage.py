"""Cassette CI guard (#132): enforce same-PR cassette coverage for every
FR-PPP envelope kind on the allowlist.

Failure mode protected against: a new ``bus.write_envelope`` kind ships
without cassette coverage, and the soak driver silently never replays
it. Memory: ``feedback_cassette_must_cover_new_envelopes.md`` (v1.3
LM-coverage near-miss). Convention until v2.2 / issue #132; enforced
rule from this test forward.

Scope: cassette RECORD path coverage only. Soak-driver REPLAY coverage
is the second leg of the rule, but the soak driver consumes the
recorded cassette as input — if cassette covers every kind and the
soak driver pipes the cassette through, replay coverage follows. A
separate test could enforce soak-driver code paths; out of scope here
to keep the guard small.
"""

from __future__ import annotations

from pathlib import Path

from stream_manager.envelope_kinds import ENVELOPE_KINDS

ROOT = Path(__file__).resolve().parent.parent
CASSETTE_RECORD = ROOT / "tools" / "cassette_record.py"
BUS_WRITERS = [
    ROOT / "src" / "stream_manager" / "governance.py",
    ROOT / "src" / "stream_manager" / "jsonl_tail.py",
    ROOT / "dashboard" / "server.py",
    ROOT / "tools" / "soak_driver.py",
    ROOT / "tools" / "cassette_record.py",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_cassette_records_every_envelope_kind() -> None:
    src = _read(CASSETTE_RECORD)
    missing = sorted(k for k in ENVELOPE_KINDS if k not in src)
    assert not missing, (
        "new envelope kind missing cassette coverage: "
        f"{missing}. Add a record path to tools/cassette_record.py "
        "in the same PR (per issue #132)."
    )


def test_every_write_envelope_callsite_uses_allowlisted_kind() -> None:
    """Backfill audit. Any ``bus.write_envelope("...")`` literal in the
    repo must reference a kind on the allowlist; otherwise either add
    the kind (intentional new envelope) or fix the callsite (typo).
    """
    import re

    pattern = re.compile(r'write_envelope\(\s*"([^"]+)"')
    found: set[str] = set()
    for path in BUS_WRITERS:
        if not path.exists():
            continue
        for match in pattern.finditer(_read(path)):
            found.add(match.group(1))
    rogue = sorted(found - ENVELOPE_KINDS)
    assert not rogue, (
        f"write_envelope callsite uses kind not on allowlist: {rogue}. "
        "Either add to ENVELOPE_KINDS (intentional) or fix the callsite."
    )
