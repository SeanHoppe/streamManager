"""Tests for stream_manager.wirecli (Task N, v1.1)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any

import pytest

from stream_manager.cli_client import cli_transport
from stream_manager.wirecli import (
    WIRE_SCHEMA_VERSION,
    WireProtocolError,
    WireRequest,
    WireResponse,
    WireSchemaVersionError,
    WireTransportError,
    call,
    call_from_string,
    parse_envelope,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _CompletedProcess:
    returncode: int
    stdout: str
    stderr: str = ""


def _envelope(inner_obj: dict[str, Any] | str) -> str:
    """Build a CLI-shaped envelope around an inner result payload."""
    if isinstance(inner_obj, dict):
        result = json.dumps(inner_obj)
    else:
        result = inner_obj
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": result,
        }
    )


def _make_runner(
    *,
    stdout: str = "",
    returncode: int = 0,
    raise_exc: BaseException | None = None,
):
    calls: list[dict[str, Any]] = []

    def runner(cmd, **kwargs):
        calls.append({"cmd": cmd, "kwargs": kwargs})
        if raise_exc is not None:
            raise raise_exc
        return _CompletedProcess(returncode=returncode, stdout=stdout)

    runner.calls = calls  # type: ignore[attr-defined]
    return runner


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_round_trip_returns_typed_response() -> None:
    payload = {
        "schema_version": WIRE_SCHEMA_VERSION,
        "action": "INTERVENE",
        "confidence": 0.82,
        "reasoning": "force-push to main is destructive",
    }
    runner = _make_runner(stdout=_envelope(payload))

    resp = call(WireRequest(content="git push --force"), runner=runner)

    assert isinstance(resp, WireResponse)
    assert resp.action == "INTERVENE"
    assert resp.confidence == pytest.approx(0.82)
    assert resp.reasoning == "force-push to main is destructive"
    assert resp.schema_version == WIRE_SCHEMA_VERSION


def test_round_trip_uses_injected_model_and_intent() -> None:
    payload = {
        "schema_version": WIRE_SCHEMA_VERSION,
        "action": "ALLOW",
        "confidence": 0.9,
        "reasoning": "ok",
    }
    runner = _make_runner(stdout=_envelope(payload))

    req = WireRequest(
        content="ls",
        intent="No force-push to main.",
        model="claude-sonnet-4-5",
    )
    call(req, runner=runner)

    assert len(runner.calls) == 1  # type: ignore[attr-defined]
    cmd = runner.calls[0]["cmd"]  # type: ignore[attr-defined]
    assert cmd[0] == "claude"
    assert "--model" in cmd
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-4-5"
    sysprompt_idx = cmd.index("--system-prompt") + 1
    assert "No force-push to main." in cmd[sysprompt_idx]
    # Schema version is pinned in the system prompt so the model
    # learns which protocol to emit.
    assert WIRE_SCHEMA_VERSION in cmd[sysprompt_idx]


def test_call_from_string_parses_pre_captured_stdout() -> None:
    """The pool path captures stdout itself; call_from_string skips
    the spawn and just validates."""
    payload = {
        "schema_version": WIRE_SCHEMA_VERSION,
        "action": "ALLOW",
        "confidence": 0.5,
        "reasoning": "narration",
    }
    resp = call_from_string(_envelope(payload))
    assert resp.action == "ALLOW"


def test_inner_result_can_be_a_dict_not_just_string() -> None:
    """Newer CLIs may emit envelope.result already-parsed."""
    inner = {
        "schema_version": WIRE_SCHEMA_VERSION,
        "action": "GUIDE",
        "confidence": 0.7,
        "reasoning": "redirect",
    }
    envelope = json.dumps(
        {
            "type": "result",
            "is_error": False,
            "result": inner,  # dict, not string
        }
    )
    resp = parse_envelope(envelope)
    assert resp.action == "GUIDE"


# ---------------------------------------------------------------------------
# Malformed-response → typed exception (NOT silent ALLOW)
# ---------------------------------------------------------------------------


def test_malformed_outer_envelope_raises_protocol_error() -> None:
    runner = _make_runner(stdout="not json at all")
    with pytest.raises(WireProtocolError, match="outer JSON parse failed"):
        call(WireRequest(content="x"), runner=runner)


def test_malformed_inner_payload_raises_protocol_error() -> None:
    """Legacy degrade path: model returns prose. WireCLI must raise,
    not silently return ALLOW."""
    runner = _make_runner(stdout=_envelope("I cannot evaluate this safely."))
    with pytest.raises(WireProtocolError, match="inner JSON parse failed"):
        call(WireRequest(content="x"), runner=runner)


def test_envelope_is_error_raises_protocol_error() -> None:
    err_envelope = json.dumps(
        {"type": "result", "is_error": True, "result": "{}"}
    )
    runner = _make_runner(stdout=err_envelope)
    with pytest.raises(WireProtocolError, match="is_error=true"):
        call(WireRequest(content="x"), runner=runner)


def test_invalid_action_enum_raises_protocol_error() -> None:
    payload = {
        "schema_version": WIRE_SCHEMA_VERSION,
        "action": "MAYBE",  # not in valid set
        "confidence": 0.5,
        "reasoning": "",
    }
    runner = _make_runner(stdout=_envelope(payload))
    with pytest.raises(WireProtocolError, match="action must be one of"):
        call(WireRequest(content="x"), runner=runner)


def test_confidence_out_of_range_raises_protocol_error() -> None:
    payload = {
        "schema_version": WIRE_SCHEMA_VERSION,
        "action": "ALLOW",
        "confidence": 1.5,
        "reasoning": "",
    }
    runner = _make_runner(stdout=_envelope(payload))
    with pytest.raises(WireProtocolError, match="confidence out of range"):
        call(WireRequest(content="x"), runner=runner)


def test_confidence_wrong_type_raises_protocol_error() -> None:
    payload = {
        "schema_version": WIRE_SCHEMA_VERSION,
        "action": "ALLOW",
        "confidence": "high",
        "reasoning": "",
    }
    runner = _make_runner(stdout=_envelope(payload))
    with pytest.raises(WireProtocolError, match="confidence must be number"):
        call(WireRequest(content="x"), runner=runner)


def test_missing_schema_version_raises_protocol_error() -> None:
    payload = {
        "action": "ALLOW",
        "confidence": 0.5,
        "reasoning": "",
    }
    runner = _make_runner(stdout=_envelope(payload))
    with pytest.raises(WireProtocolError, match="schema_version"):
        call(WireRequest(content="x"), runner=runner)


# ---------------------------------------------------------------------------
# Schema-version drift
# ---------------------------------------------------------------------------


def test_schema_version_mismatch_raises_typed_error() -> None:
    payload = {
        "schema_version": "999",  # future revision
        "action": "ALLOW",
        "confidence": 0.5,
        "reasoning": "",
    }
    runner = _make_runner(stdout=_envelope(payload))
    with pytest.raises(WireSchemaVersionError, match="schema_version mismatch"):
        call(WireRequest(content="x"), runner=runner)


def test_schema_version_present_in_response() -> None:
    """Round-tripped schema_version is exposed on the response so
    callers can audit drift even when parse succeeds."""
    payload = {
        "schema_version": WIRE_SCHEMA_VERSION,
        "action": "ALLOW",
        "confidence": 0.5,
        "reasoning": "",
    }
    resp = call_from_string(_envelope(payload))
    assert resp.schema_version == WIRE_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Fence handling
# ---------------------------------------------------------------------------


def test_fenced_inner_is_tolerated_in_permissive_mode() -> None:
    payload_json = json.dumps(
        {
            "schema_version": WIRE_SCHEMA_VERSION,
            "action": "ALLOW",
            "confidence": 0.5,
            "reasoning": "",
        }
    )
    fenced = f"```json\n{payload_json}\n```"
    runner = _make_runner(stdout=_envelope(fenced))
    resp = call(WireRequest(content="x"), runner=runner)
    assert resp.action == "ALLOW"


def test_fenced_inner_rejected_in_strict_mode() -> None:
    payload_json = json.dumps(
        {
            "schema_version": WIRE_SCHEMA_VERSION,
            "action": "ALLOW",
            "confidence": 0.5,
            "reasoning": "",
        }
    )
    fenced = f"```json\n{payload_json}\n```"
    runner = _make_runner(stdout=_envelope(fenced))
    with pytest.raises(WireProtocolError, match="strict mode"):
        call(WireRequest(content="x", strict_fence=True), runner=runner)


# ---------------------------------------------------------------------------
# Transport-layer (subprocess) errors
# ---------------------------------------------------------------------------


def test_cli_not_found_raises_transport_error() -> None:
    runner = _make_runner(raise_exc=FileNotFoundError("no claude"))
    with pytest.raises(WireTransportError, match="not found"):
        call(WireRequest(content="x"), runner=runner)


def test_cli_timeout_raises_transport_error() -> None:
    runner = _make_runner(
        raise_exc=subprocess.TimeoutExpired(cmd=["claude"], timeout=1.0)
    )
    with pytest.raises(WireTransportError, match="timed out"):
        call(WireRequest(content="x"), runner=runner)


def test_cli_nonzero_exit_raises_transport_error() -> None:
    runner = _make_runner(stdout="", returncode=2)
    with pytest.raises(WireTransportError, match="exited with code 2"):
        call(WireRequest(content="x"), runner=runner)


# ---------------------------------------------------------------------------
# cli_client.cli_transport selector
# ---------------------------------------------------------------------------


def test_cli_transport_default_is_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BRIDGE_CLI_TRANSPORT", raising=False)
    assert cli_transport() == "json"


def test_cli_transport_explicit_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_CLI_TRANSPORT", "wirecli")
    assert cli_transport("json") == "json"


def test_cli_transport_env_selects_wirecli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRIDGE_CLI_TRANSPORT", "wirecli")
    assert cli_transport() == "wirecli"


def test_cli_transport_unknown_value_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BRIDGE_CLI_TRANSPORT", raising=False)
    with pytest.raises(ValueError, match="unknown cli transport"):
        cli_transport("grpc")
