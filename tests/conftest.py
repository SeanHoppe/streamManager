"""Shared pytest fixtures.

v2.1 P1a (R-conftest): centralize the PPP test setup that was duplicated
across `test_audit_probe_envelope.py`, `test_audit_probe_hitl.py`, and
`test_audit_probe_cassette.py` — namely:
  - set `SM_DESKTOP_SECRET` env BEFORE importing desktop_commands (so
    the module-level secret-load picks up the test secret and does NOT
    write `.bridge/secret` to the repo)
  - drop a stale `stream_manager.desktop_commands` from `sys.modules` so
    a fresh import binds to the test secret

Individual test files still inline `_fresh_desktop_commands(monkeypatch)`
helpers (kept for explicit reload semantics); this fixture is a
project-wide safety net so any new test that imports desktop_commands
without an explicit reload still avoids polluting the repo with a
real `.bridge/secret`.
"""

from __future__ import annotations

import os
import sys

import pytest


@pytest.fixture(autouse=True)
def _ppp_test_secret(monkeypatch):
    """Ensure SM_DESKTOP_SECRET is set before any desktop_commands import.

    Autouse so any test that touches `desktop_commands.sign(...)` (PPP,
    desktop_command_sse, etc.) sees a deterministic secret and never
    writes `.bridge/secret` to the repo. Tests that need a fresh
    `desktop_commands` module reload can still do so explicitly; this
    fixture only guarantees the env var is present at import time.
    """
    monkeypatch.setenv("SM_DESKTOP_SECRET", "ppp-test-secret")
    yield


def pytest_configure(config):
    """Drop any pre-loaded `stream_manager.desktop_commands` so the first
    test-time import picks up the fixture's test secret.

    Without this, a parent process or an earlier conftest-less test
    session could have already cached desktop_commands with the
    production-path secret-load (file-based fallback at
    `.bridge/secret`). Drop-and-reimport is the safest reset.
    """
    os.environ.setdefault("SM_DESKTOP_SECRET", "ppp-test-secret")
    sys.modules.pop("stream_manager.desktop_commands", None)
