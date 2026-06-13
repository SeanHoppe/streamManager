"""Canonical allowlist of FR-PPP envelope kinds the bus may publish.

Scope: kinds passed as the first argument to ``MessageBus.write_envelope``.
This is the outer FR-PPP envelope-type system (audit.probe family,
introduced v2.1 P1–P3). It is distinct from:

* ``KIND_ALLOWLIST`` at ``desktop_commands.py`` — those are
  ``desktop_command`` SUB-kinds (pause / foreground / flash / ...).
* ``Message.type`` strings used by ``bus.publish`` — bus message system,
  written to the messages table.

Adding a new kind requires updating this set AND landing same-PR
coverage in ``tools/cassette_record.py`` (record path) — enforced by
``tests/test_envelope_coverage.py``. Convention historically; rule per
issue #132 / v2.2 standalone hardening.
"""

from __future__ import annotations

ENVELOPE_KINDS: frozenset[str] = frozenset(
    {
        "audit.probe",
        "audit.probe_ack",
        "audit.canary_emit",
        "audit.canary_observed",
        "audit.probe_failure",
        "audit.hallucination_detected",
        # ADR-18 Amendment F: emitted ONCE per graduation event (operator
        # confirm), never on the hot path. Same-PR cassette + soak coverage
        # mandatory (test_envelope_coverage.py enforces).
        "pattern_graduated",
    }
)
