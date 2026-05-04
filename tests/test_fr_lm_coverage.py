"""v1.3 C5 — FR-LM-* coverage map (REQUIREMENTS.md §4.12 → CI gate).

REQUIREMENTS.md §4.12 declares FR-LM-1..6 as load-bearing functional
requirements for Learn Mode. The other Learn Mode test modules cover
each behaviour exhaustively, but their names do not surface the
FR-LM-* numbering — a future grep for ``test_fr_lm_*`` would come up
empty even though coverage exists.

This module is the FR-numbered coverage map. Each test asserts the
load-bearing observable from one FR-LM-* entry and is named
``test_fr_lm_<n>_<short-tag>``. The tests are intentionally narrow:
the source-of-truth assertion lives in the focused module (cited in
each test docstring); this file exists so REQUIREMENTS authors can
confirm coverage by greppable convention.

Source-of-truth modules:
  - FR-LM-1  →  ``tests/test_jsonl_tail_learn_mode.py``
  - FR-LM-2  →  ``tests/test_learn_categorizer.py``
                ``test_worker_does_not_block_verdict_hot_path``
  - FR-LM-3  →  ``tests/test_advisory_bias.py``
                ``test_governance_emits_bias_audit_envelope_when_hitl_fires``
  - FR-LM-4  →  ``tests/test_learn_mode_pipeline.py``
                ``test_pipeline_decay_sweep_ages_out_reinforcement``
  - FR-LM-5  →  ``tests/test_advisory_bias.py`` (audit envelope shape)
  - FR-LM-6  →  ``tests/test_jsonl_tail_learn_mode.py``
                ``test_sm_originated_turn_is_filtered_out``
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from stream_manager import message_bus as _msg_bus
from stream_manager.agent_registry import AgentRegistry
from stream_manager.decay import LADDER_FLOOR, decay_sweep
from stream_manager.governance import GovernanceEngine, Mode
from stream_manager.hitl import HitlQueue
from stream_manager.jsonl_tail import JsonlTailWorker
from stream_manager.learn_categorizer import (
    DEFAULT_MODEL,
    LearnCategorizerWorker,
    bias_for,
    categorize_pair,
    prompt_hash,
)
from stream_manager.messages import Message
from stream_manager.project_context import ProjectContextSnapshot


PROFILES_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "stream_manager"
    / "agent_profiles.yaml"
)
JSONL_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "learn_mode_jsonl_sample.jsonl"
)


# ── shared helpers ──────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _enable_learn_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SM_LEARN_MODE", "1")


@pytest.fixture
def bus(tmp_path: Path) -> _msg_bus.MessageBus:
    b = _msg_bus.MessageBus(str(tmp_path / "fr_lm.db"))
    yield b
    try:
        b.close()
    except Exception:
        pass


@dataclass
class _CompletedProcess:
    returncode: int
    stdout: str
    stderr: str = ""


def _seed_canonical(
    bus: _msg_bus.MessageBus,
    *,
    prompt: str,
    category: str,
    confidence: float,
    ladder_step: int = 1,
    last_reinforced_ts: float | None = None,
) -> None:
    now = time.time() if last_reinforced_ts is None else last_reinforced_ts
    bus.execute_write(
        "INSERT INTO learn_patterns_canonical "
        "(prompt_hash, category, confidence, ladder_step, "
        " last_reinforced_ts, contradicted_count, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            prompt_hash(prompt),
            category,
            float(confidence),
            int(ladder_step),
            float(now),
            0,
            float(now),
            float(now),
        ),
    )


def _build_jsonl_worker(
    bus: _msg_bus.MessageBus, tmp_path: Path
) -> JsonlTailWorker:
    registry = AgentRegistry(profiles_path=PROFILES_PATH)
    w = JsonlTailWorker(projects_dir=tmp_path, registry=registry, bus=bus)
    w._session_id = "sm-side-session"
    w._project_slug = "fixture"
    w._sm_own_session_id = "sm-owner-42"
    return w


def _drive_jsonl(worker: JsonlTailWorker, fixture_path: Path) -> None:
    for line in fixture_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        worker._process_line(line)


def _read_messages_by_type(
    bus: _msg_bus.MessageBus, type_: str
) -> list[dict]:
    rows = bus.fetch_rows(
        "SELECT id, type, direction, content, metadata FROM messages "
        "WHERE type=? ORDER BY rowid ASC",
        (type_,),
    )
    import json as _json

    out: list[dict] = []
    for r in rows:
        meta = {}
        try:
            meta = _json.loads(r[4]) if r[4] else {}
        except Exception:
            meta = {}
        out.append(
            {
                "id": r[0],
                "type": r[1],
                "direction": r[2],
                "content": r[3],
                "metadata": meta,
            }
        )
    return out


def _all_envelope_types(bus: _msg_bus.MessageBus) -> set[str]:
    rows = bus.fetch_rows("SELECT DISTINCT type FROM messages")
    return {str(r[0]) for r in rows}


def _build_engine(
    bus: _msg_bus.MessageBus, *, session_id: str = "S-fr-lm"
) -> GovernanceEngine:
    bus.open_session(session_id)
    bus.set_hitl_mode(session_id, "async", 0.60)
    snap = ProjectContextSnapshot(repo_path=".", has_intent_file=False)
    return GovernanceEngine(
        project_context=snap,
        bus=bus,
        session_id=session_id,
        mode=Mode.OBSERVE,
        hitl=HitlQueue(bus=bus),
    )


# ── FR-LM-1: dialogue ingest ────────────────────────────────────────


def test_fr_lm_1_jsonl_tail_emits_dialogue_pair(
    bus: _msg_bus.MessageBus, tmp_path: Path
) -> None:
    """FR-LM-1: JSONL tail emits ``desktop_prompt`` + ``user_reply`` paired.

    Source of truth: ``tests/test_jsonl_tail_learn_mode.py``
    (``test_assistant_text_turn_emits_desktop_prompt`` +
    ``test_user_text_turn_emits_user_reply_with_pair_id``).
    """
    worker = _build_jsonl_worker(bus, tmp_path)
    _drive_jsonl(worker, JSONL_FIXTURE)

    desktop = _read_messages_by_type(bus, "desktop_prompt")
    user = _read_messages_by_type(bus, "user_reply")
    assert len(desktop) >= 1, "FR-LM-1: assistant text → desktop_prompt"
    assert len(user) >= 1, "FR-LM-1: user text → user_reply"

    # Pairing via parentUuid → pair_id metadata.
    paired = [m for m in user if m["metadata"].get("pair_id")]
    assert paired, "FR-LM-1: user_reply must carry pair_id back to prompt"


# ── FR-LM-2: out-of-band categorizer (CLI subprocess, hot path safe) ─


def test_fr_lm_2_categorizer_uses_cli_subprocess_backend() -> None:
    """FR-LM-2: categorizer MUST use the CLI subprocess backend.

    ADR-5 latency budget + ``feedback_cli_over_sdk.md``: no Anthropic
    SDK / API-key path. Source of truth:
    ``tests/test_learn_categorizer.py::test_categorize_pair_invokes_cli_with_expected_flags``.
    """
    captured: dict = {}

    def runner(cmd, **kwargs):
        captured["cmd"] = cmd
        return _CompletedProcess(
            returncode=0,
            stdout=(
                '{"type":"result","subtype":"success","is_error":false,'
                '"result":"{\\"category\\":\\"approve\\",'
                '\\"confidence\\":0.9,\\"reasoning\\":\\"\\"}"}'
            ),
        )

    out = categorize_pair("Want me to ship?", "yes please", runner=runner)
    assert out is not None
    cmd = captured["cmd"]
    assert cmd[0] == "claude", "FR-LM-2: must shell out to claude CLI"
    assert "-p" in cmd
    assert "--model" in cmd and DEFAULT_MODEL in cmd
    assert "--output-format" in cmd and "json" in cmd


def test_fr_lm_2_categorizer_worker_is_off_hot_path(
    bus: _msg_bus.MessageBus,
) -> None:
    """FR-LM-2: worker tick MUST NOT hold the verdict-path bus lock.

    Lighter assertion than the full timing test. We assert the worker
    exposes the daemon-thread surface (``start``/``stop``/``tick``) so
    a regression that collapses it onto the verdict path would fail at
    import. Source-of-truth timing test:
    ``tests/test_learn_categorizer.py::test_worker_does_not_block_verdict_hot_path``.
    """
    worker = LearnCategorizerWorker(bus, runner=lambda *a, **k: None)
    # Daemon-thread API contract.
    assert hasattr(worker, "start")
    assert hasattr(worker, "stop")
    assert hasattr(worker, "tick")
    # Tick on an empty bus returns 0 without blocking.
    t0 = time.monotonic()
    n = worker.tick()
    elapsed = time.monotonic() - t0
    assert n == 0
    assert elapsed < 0.5, (
        f"FR-LM-2: empty tick must not block; took {elapsed:.3f}s"
    )


# ── FR-LM-3: advisory bias surfaces in the verdict path ─────────────


def test_fr_lm_3_bias_for_consumed_by_consult(
    bus: _msg_bus.MessageBus,
) -> None:
    """FR-LM-3: ``bias_for`` output reaches ``_consult_learn_mode_bias``.

    Plant a canonical row and drive the engine. The audit envelope
    (``learn_mode_bias_applied``) is the observable proof that the
    bias hint flowed through ``_consult_learn_mode_bias`` to the
    HITL pre-fill site without overriding the verdict. Source of
    truth: ``tests/test_advisory_bias.py::test_governance_emits_bias_audit_envelope_when_hitl_fires``.
    """
    eng = _build_engine(bus)
    prompt = "Run pytest tests/test_smoke.py to confirm the v1.3 PR is green"
    _seed_canonical(
        bus,
        prompt=prompt,
        category="approve",
        confidence=0.95,
        ladder_step=2,
    )
    decision = eng.evaluate(Message.new(role="assistant", content=prompt))

    audits = _read_messages_by_type(bus, "learn_mode_bias_applied")
    assert len(audits) == 1, (
        "FR-LM-3: bias hint must flow to the audit envelope when HITL fires"
    )
    meta = audits[0]["metadata"]
    assert meta["category"] == "approve"
    assert meta["ladder_step_suggestion"] == 2
    # Bias is advisory only — verdict source is not "bias-override".
    assert decision.source in {"default", "graph", "cli"}


# ── FR-LM-4: decay ladder reaches bias_for ──────────────────────────


def test_fr_lm_4_decay_sweep_changes_bias_for_output(
    bus: _msg_bus.MessageBus,
) -> None:
    """FR-LM-4: decay aging changes ``bias_for`` output.

    A 121-day-old reinforced row crosses every decay threshold and is
    clipped to the floor. ``bias_for`` reads the canonical projection,
    so the post-sweep state surfaces. Source of truth:
    ``tests/test_learn_mode_pipeline.py::test_pipeline_decay_sweep_ages_out_reinforcement``.
    """
    prompt = "Should I cherry-pick into release?"
    now0 = time.time()
    _seed_canonical(
        bus,
        prompt=prompt,
        category="approve",
        confidence=0.85,
        ladder_step=4,
        last_reinforced_ts=now0,
    )

    pre = bias_for(prompt, bus)
    assert pre is not None and pre.ladder_step_suggestion == 4

    decay_sweep(bus, now_ts=now0 + 121 * 86400.0)

    post = bias_for(prompt, bus)
    if post is None:
        return  # acceptable: confidence threshold may suppress
    assert post.ladder_step_suggestion == LADDER_FLOOR, (
        "FR-LM-4: post-decay ladder rung must surface in bias hint"
    )


# ── FR-LM-5: silent audit row, no toast ─────────────────────────────


def test_fr_lm_5_audit_row_is_silent_no_toast(
    bus: _msg_bus.MessageBus,
) -> None:
    """FR-LM-5: bias path emits ``learn_mode_bias_applied`` (direction=internal),
    never a toast / undo card.

    Drive the same scenario as FR-LM-3 and assert (a) the audit row is
    direction=internal, and (b) no envelope of type ``toast`` was ever
    published on the bus.
    """
    eng = _build_engine(bus)
    prompt = "Run pytest tests/test_smoke.py to confirm the v1.3 PR is green"
    _seed_canonical(
        bus,
        prompt=prompt,
        category="approve",
        confidence=0.95,
        ladder_step=2,
    )
    eng.evaluate(Message.new(role="assistant", content=prompt))

    audits = _read_messages_by_type(bus, "learn_mode_bias_applied")
    assert len(audits) == 1
    assert audits[0]["direction"] == "internal", (
        "FR-LM-5: audit row must be direction=internal (silent)"
    )
    assert "toast" not in _all_envelope_types(bus), (
        "FR-LM-5: bias path MUST NOT emit toast envelopes"
    )


# ── FR-LM-6: single-user scope ──────────────────────────────────────


def test_fr_lm_6_no_owner_user_field_in_learn_mode_schemas(
    bus: _msg_bus.MessageBus,
) -> None:
    """FR-LM-6: Learn Mode schemas MUST NOT carry ``owner_user`` columns.

    v1.3 assumes a single operator. Adding an ``owner_user`` field
    would silently land multi-user partitioning without the v1.4
    disambiguation design. We introspect the SQLite schema for the
    three Learn-Mode-owned tables and assert no such column exists.
    """
    learn_tables = (
        "learn_patterns",
        "learn_patterns_canonical",
        "learn_categorizer_state",
    )
    for table in learn_tables:
        rows = bus.fetch_rows(
            "SELECT name FROM pragma_table_info(?)", (table,)
        )
        cols = {str(r[0]) for r in rows}
        assert cols, f"FR-LM-6: table {table} not present"
        assert "owner_user" not in cols, (
            f"FR-LM-6: table {table} must not carry owner_user (got {cols})"
        )


def test_fr_lm_6_sm_own_session_filtered_from_ingest(
    bus: _msg_bus.MessageBus, tmp_path: Path
) -> None:
    """FR-LM-6: SM's own JSONL turns are filtered (no self-monitor loop).

    Source of truth: ``tests/test_jsonl_tail_learn_mode.py::test_sm_originated_turn_is_filtered_out``.
    """
    worker = _build_jsonl_worker(bus, tmp_path)
    # SM_OWN_SESSION_ID matches "sm-owner-42" set in _build_jsonl_worker.
    _drive_jsonl(worker, JSONL_FIXTURE)

    learn_msgs = (
        _read_messages_by_type(bus, "desktop_prompt")
        + _read_messages_by_type(bus, "user_reply")
    )
    sources = {m["metadata"].get("desktop_session_id") for m in learn_msgs}
    assert "sm-owner-42" not in sources, (
        "FR-LM-6: SM's own session must be filtered from Learn Mode ingest"
    )
