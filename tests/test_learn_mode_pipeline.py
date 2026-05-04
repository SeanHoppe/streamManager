"""Tests for v1.3 C2 — end-to-end Learn Mode pipeline coherence.

Drives the full pipeline in one process so the seam between sub-phases
is guarded against future drift:

    JSONL tail (P5b)  →  desktop_prompt + user_reply on bus
    Categorizer (P5c) →  learn_patterns (audit log)
                      →  learn_patterns_canonical (UPSERT projection)
    Decay (P5e)       →  consolidate_patterns reinforcement / contradiction
                      →  decay_sweep aging
    Bias reader (P5d, C1) → bias_for reads canonical
    Safety priority (P5d) → _is_safety_priority_content short-circuit

Each sub-phase has its own focused tests. This file is the pipeline
test that fails when the writer/reader seam drifts (e.g. if a future
change accidentally points ``bias_for`` back at the audit log, the
reinforcement / decay / contradiction round-trips here all fail).

Mirrors the harness patterns from:
  - ``tests/test_jsonl_tail_learn_mode.py`` (synthesize JSONL fixture +
    drive ``JsonlTailWorker._process_line`` directly)
  - ``tests/test_learn_categorizer.py::test_worker_writes_one_row_per_pair``
    (drive ``LearnCategorizerWorker.tick`` with a mocked Sonnet runner)
  - ``tests/test_decay.py::test_aged_then_reinforced_round_trip`` and
    ``tests/test_advisory_bias.py`` (``_seed_canonical`` helper).

No subprocess invocation: the categorizer ``runner`` is fully mocked.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from stream_manager import message_bus as _msg_bus
from stream_manager.agent_registry import AgentRegistry
from stream_manager.decay import (
    CONTRADICTION_DEMOTE_STEPS,
    LADDER_FLOOR,
    consolidate_patterns,
    decay_sweep,
)
from stream_manager.governance import GovDecision, GovernanceEngine, Mode
from stream_manager.hitl import HitlQueue
from stream_manager.jsonl_tail import JsonlTailWorker
from stream_manager.learn_categorizer import (
    MIN_BIAS_CONFIDENCE,
    LearnCategorizerWorker,
    bias_for,
    prompt_hash,
)
from stream_manager.project_context import ProjectContextSnapshot


PROFILES_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "stream_manager"
    / "agent_profiles.yaml"
)


# ── fixtures + helpers ──────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _enable_learn_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pipeline tests run with the env gate ON.

    ``bias_for`` early-returns ``None`` when ``SM_LEARN_MODE`` is unset
    (P5d Fix A). Every assertion in this file exercises the post-gate
    code path, so we set the gate for all tests.
    """
    monkeypatch.setenv("SM_LEARN_MODE", "1")


@pytest.fixture
def bus(tmp_path: Path) -> _msg_bus.MessageBus:
    b = _msg_bus.MessageBus(str(tmp_path / "pipeline.db"))
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


def _envelope(category: str, confidence: float, reasoning: str = "") -> str:
    """Build a deterministic Sonnet CLI ``--output-format json`` envelope."""
    inner = {
        "category": category,
        "confidence": confidence,
        "reasoning": reasoning,
    }
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": json.dumps(inner),
        }
    )


class _DeterministicRunner:
    """``subprocess.run`` stand-in. Returns a pinned category/confidence.

    The categorizer worker invokes ``categorize_pair(..., runner=...)``
    which delegates to this object instead of spawning a real ``claude``
    CLI subprocess. CI runs without any network or subprocess work.
    """

    def __init__(self, category: str = "approve", confidence: float = 0.85) -> None:
        self.category = category
        self.confidence = confidence
        self.calls: list[dict[str, Any]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append({"cmd": cmd, "kwargs": kwargs})
        return _CompletedProcess(
            returncode=0,
            stdout=_envelope(self.category, self.confidence),
        )


def _build_jsonl_fixture(tmp_path: Path, prompt: str, reply: str) -> Path:
    """Write a minimal Desktop JSONL with 5 paired turns.

    Five paired turns share the same prompt text (same prompt_hash).
    The categorizer worker dedupes per (rowid > last_id_seen), so each
    pair is categorized once. The first observation INSERTs the
    canonical row at ladder_step=0; the next four reinforce it via
    ``consolidate_patterns`` invoked from the worker's
    ``_categorize_and_record`` tail.
    """
    path = tmp_path / "desktop.jsonl"
    lines: list[str] = []
    base_ts = "2026-05-04T00:00:"
    for i in range(5):
        ts_a = f"{base_ts}{i*2:02d}Z"
        ts_u = f"{base_ts}{i*2+1:02d}Z"
        a_uuid = f"a{i}"
        u_uuid = f"u{i}"
        parent = "" if i == 0 else f"u{i-1}"
        lines.append(json.dumps({
            "type": "assistant",
            "sessionId": "desktop-S1",
            "uuid": a_uuid,
            "parentUuid": parent,
            "timestamp": ts_a,
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": prompt}],
            },
        }))
        lines.append(json.dumps({
            "type": "user",
            "sessionId": "desktop-S1",
            "uuid": u_uuid,
            "parentUuid": a_uuid,
            "timestamp": ts_u,
            "message": {"role": "user", "content": reply},
        }))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _drive_jsonl(worker: JsonlTailWorker, fixture_path: Path) -> None:
    """Replay a fixture JSONL through the tailer's per-line entry point."""
    for line in fixture_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        worker._process_line(line)


def _read_messages_by_type(bus: _msg_bus.MessageBus, type_: str) -> list[dict]:
    rows = bus.fetch_rows(
        "SELECT id, type, content, metadata FROM messages "
        "WHERE type=? ORDER BY rowid ASC",
        (type_,),
    )
    out: list[dict] = []
    for r in rows:
        try:
            meta = json.loads(r[3]) if r[3] else {}
        except Exception:
            meta = {}
        out.append({"id": r[0], "type": r[1], "content": r[2], "metadata": meta})
    return out


def _read_audit_rows(bus: _msg_bus.MessageBus, prompt_hash_val: str) -> list[dict]:
    rows = bus.fetch_rows(
        "SELECT id, prompt_hash, category, confidence, ladder_step, "
        "last_reinforced_ts FROM learn_patterns WHERE prompt_hash=? "
        "ORDER BY id ASC",
        (prompt_hash_val,),
    )
    return [
        {
            "id": int(r[0]),
            "prompt_hash": str(r[1]),
            "category": str(r[2]),
            "confidence": float(r[3]),
            "ladder_step": int(r[4]),
            "last_reinforced_ts": float(r[5]),
        }
        for r in rows
    ]


def _read_canonical_row(
    bus: _msg_bus.MessageBus, prompt_hash_val: str
) -> dict | None:
    rows = bus.fetch_rows(
        "SELECT id, prompt_hash, category, confidence, ladder_step, "
        "last_reinforced_ts, contradicted_count "
        "FROM learn_patterns_canonical WHERE prompt_hash=?",
        (prompt_hash_val,),
    )
    if not rows:
        return None
    r = rows[0]
    return {
        "id": int(r[0]),
        "prompt_hash": str(r[1]),
        "category": str(r[2]),
        "confidence": float(r[3]),
        "ladder_step": int(r[4]),
        "last_reinforced_ts": float(r[5]),
        "contradicted_count": int(r[6]),
    }


def _seed_canonical(
    bus: _msg_bus.MessageBus,
    *,
    prompt: str,
    category: str,
    confidence: float,
    ladder_step: int,
    last_reinforced_ts: float | None = None,
) -> int:
    """Plant a row directly in ``learn_patterns_canonical`` (mirrors
    the helper in ``tests/test_advisory_bias.py`` and ``tests/test_decay.py``).
    """
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
    rows = bus.fetch_rows(
        "SELECT id FROM learn_patterns_canonical WHERE prompt_hash=?",
        (prompt_hash(prompt),),
    )
    return int(rows[0][0])


def _build_jsonl_worker(
    bus: _msg_bus.MessageBus, tmp_path: Path
) -> JsonlTailWorker:
    """Construct a JsonlTailWorker wired to the test bus.

    Mirrors ``tests/test_jsonl_tail_learn_mode.py``: install a stable
    sm-side session id and bypass ``start()`` so we can drive
    ``_process_line`` directly without a tail thread.
    """
    registry = AgentRegistry(profiles_path=PROFILES_PATH)
    w = JsonlTailWorker(projects_dir=tmp_path, registry=registry, bus=bus)
    w._session_id = "sm-side-session"
    w._project_slug = "fixture"
    # Disable the SM_OWN_SESSION_ID filter — the synthetic fixture's
    # sessionId is "desktop-S1", not the SM owner. Setting to a
    # different value keeps the filter active without dropping fixtures.
    w._sm_own_session_id = "sm-owner-not-present"
    return w


# ── Case 1: full pipeline + reinforcement → bias hint surfaces ──────


def test_pipeline_round_trip_reinforcement_surfaces_ladder_step(
    bus: _msg_bus.MessageBus, tmp_path: Path
) -> None:
    """End-to-end: ingest 5 paired turns → categorize → consolidate ×3 → bias.

    1. ``JsonlTailWorker._process_line`` ingests 5 paired Desktop turns
       and emits 5 ``desktop_prompt`` + 5 ``user_reply`` envelopes.
    2. ``LearnCategorizerWorker.tick`` drains the 5 pairs with a mocked
       Sonnet runner and writes one row per pair to BOTH
       ``learn_patterns`` (audit log, P5c) AND ``learn_patterns_canonical``
       (UPSERT projection, P5e).
    3. After 5 reinforcements the canonical ladder_step sits at
       ``min(LADDER_MAX, 4)`` (first INSERT at step=0, four
       reinforcements bump to 4).
    4. We then explicitly call ``consolidate_patterns`` 3× more on top
       to assert ``bias_for`` reflects the canonical ladder rung — the
       point of C1's wire-up.

    This is the seam check: a regression that points ``bias_for`` back
    at the append-only audit log would always return
    ``ladder_step_suggestion == 0`` (the audit-log default) and break
    the assertion below.
    """
    prompt = "Want me to ship the v1.3 PR?"
    reply = "yes please, ship it"
    fixture = _build_jsonl_fixture(tmp_path, prompt, reply)

    # Step 1 — JSONL ingest.
    tailer = _build_jsonl_worker(bus, tmp_path)
    _drive_jsonl(tailer, fixture)

    desktop_msgs = _read_messages_by_type(bus, "desktop_prompt")
    user_msgs = _read_messages_by_type(bus, "user_reply")
    assert len(desktop_msgs) == 5, (
        f"expected 5 desktop_prompt envelopes; got {len(desktop_msgs)}"
    )
    assert len(user_msgs) == 5, (
        f"expected 5 user_reply envelopes; got {len(user_msgs)}"
    )
    # Each user_reply has metadata.pair_id pointing at the matching
    # desktop_prompt — the link the categorizer worker follows.
    assert all(m["metadata"].get("pair_id") for m in user_msgs)

    # Step 2 — categorizer drains all 5 pairs synchronously.
    runner = _DeterministicRunner(category="approve", confidence=0.85)
    cat_worker = LearnCategorizerWorker(bus, runner=runner)
    n = cat_worker.tick()
    assert n == 5, f"categorizer should drain 5 pairs in one tick; got {n}"

    h = prompt_hash(prompt)
    audit_rows = _read_audit_rows(bus, h)
    assert len(audit_rows) == 5, (
        f"audit log should hold 5 rows (one per pair); got {len(audit_rows)}"
    )
    assert all(r["category"] == "approve" for r in audit_rows)

    canonical = _read_canonical_row(bus, h)
    assert canonical is not None, (
        "canonical row must exist after categorizer consolidates"
    )
    # First pair: INSERT at ladder_step=0. Four follow-up reinforcements
    # bump to LADDER_MAX (4).
    assert canonical["ladder_step"] == 4, (
        f"after 5 same-category obs ladder_step should saturate at "
        f"LADDER_MAX=4; got {canonical['ladder_step']}"
    )

    # Step 3 — explicitly drive ``consolidate_patterns`` to demonstrate
    # the seam test the corrective plan calls for. (After 5 obs we're
    # already at the cap, so add 3 more reinforcements on a fresh hash
    # to assert the ``ladder_step == 3`` round-trip per plan §8.)
    fresh_prompt = "Should I rebase before merging?"
    fresh_h = prompt_hash(fresh_prompt)
    for _ in range(3):
        consolidate_patterns(bus, fresh_h, "approve", 0.85)
    fresh_row = _read_canonical_row(bus, fresh_h)
    assert fresh_row is not None
    # First call INSERTs at step=0; next two reinforcements bump to 2.
    # ladder_step after N consolidate calls: 0 → 1 → 2.
    assert fresh_row["ladder_step"] == 2

    # Plant a third reinforcement to land at exactly the plan-specified
    # ``ladder_step_suggestion == 3`` value.
    consolidate_patterns(bus, fresh_h, "approve", 0.85)
    fresh_row = _read_canonical_row(bus, fresh_h)
    assert fresh_row["ladder_step"] == 3

    hint = bias_for(fresh_prompt, bus)
    # Note: ``isinstance(hint, BiasHint)`` is fragile here — other tests
    # in the suite (e.g. ``test_advisory_bias::test_bias_floor_env_override``)
    # invoke ``importlib.reload(stream_manager.learn_categorizer)`` which
    # rebinds ``BiasHint`` to a new class object. Compare by attribute
    # presence + class name instead so this test is robust to module
    # reloads anywhere else in the suite.
    assert hint is not None, (
        "bias_for must return a hint after canonical reinforcement; "
        "if this fails, bias_for is reading the wrong table"
    )
    assert type(hint).__name__ == "BiasHint"
    assert hint.category == "approve"
    assert hint.ladder_step_suggestion == 3, (
        f"canonical ladder rung must surface in BiasHint; got "
        f"{hint.ladder_step_suggestion}. If this is 0, bias_for is "
        f"reading the append-only audit log, not the canonical "
        f"projection — C1's wire-up has regressed."
    )
    assert hint.confidence >= MIN_BIAS_CONFIDENCE


# ── Case 2: decay sweep ages out reinforcement ──────────────────────


def test_pipeline_decay_sweep_ages_out_reinforcement(
    bus: _msg_bus.MessageBus,
) -> None:
    """A 121-day-old reinforced row drops to the decay floor → bias = None.

    Per ``DECAY_THRESHOLDS_S`` (30/60/90/120 days), a row aged 121 days
    has crossed every threshold, so ``decay_sweep`` clips the canonical
    row's ``ladder_step`` to the floor (0). The resulting bias hint
    either has ``ladder_step_suggestion == 0`` (if confidence still
    clears the floor) or is ``None`` (if confidence sits below
    ``MIN_BIAS_CONFIDENCE``).

    This is the load-bearing assertion that ``decay_sweep``'s output
    actually reaches ``bias_for``: pre-C1 the sweep wrote canonical
    rows that ``bias_for`` never read, so this test would have been
    impossible to satisfy.
    """
    prompt = "Should I cherry-pick into release?"
    h = prompt_hash(prompt)
    now0 = time.time()

    # Plant a fresh, well-reinforced canonical row.
    _seed_canonical(
        bus,
        prompt=prompt,
        category="approve",
        confidence=0.85,
        ladder_step=4,
        last_reinforced_ts=now0,
    )

    # Sanity: pre-decay, bias_for surfaces ladder_step=4.
    pre = bias_for(prompt, bus)
    assert pre is not None
    assert pre.ladder_step_suggestion == 4

    # Run the decay sweep 121 days in the future. All 4 thresholds
    # crossed → ladder_step clipped to LADDER_FLOOR (0).
    decay_sweep(bus, now_ts=now0 + 121 * 86400.0)

    canonical = _read_canonical_row(bus, h)
    assert canonical is not None
    assert canonical["ladder_step"] == LADDER_FLOOR, (
        f"121-day-old row must be clipped to floor; got "
        f"{canonical['ladder_step']}"
    )

    # Bias output reflects the post-decay state. Confidence (0.85)
    # still clears MIN_BIAS_CONFIDENCE so the hint surfaces with
    # ladder_step_suggestion == 0.
    post = bias_for(prompt, bus)
    if post is None:
        # Acceptable: future change to MIN_BIAS_CONFIDENCE could make
        # the hint suppress entirely; the plan accepts either outcome.
        return
    assert post.ladder_step_suggestion == 0, (
        f"after decay, ladder_step_suggestion must be 0; got "
        f"{post.ladder_step_suggestion}. If this is non-zero, "
        f"decay_sweep's writes are not reaching bias_for — the seam "
        f"between P5e and P5d is broken."
    )


# ── Case 3: contradiction snap-demote ───────────────────────────────


def test_pipeline_contradiction_snap_demotes_bias_hint(
    bus: _msg_bus.MessageBus,
) -> None:
    """Reinforce 4× with category A → contradict with category B → bias snaps.

    Per ``decay.consolidate_patterns``, an opposite-category observation
    snaps ``ladder_step`` down by ``CONTRADICTION_DEMOTE_STEPS`` (2 in
    v1.3). Starting peak = 4 → contradiction lands at 2. The bias
    reader must reflect this — that's the seam C2 guards.

    Note: the canonical ``category`` is NOT flipped on a single
    contradiction (per design §2.5). The hint's category remains the
    original 'approve'; only the ladder rung snaps.
    """
    prompt = "Run the soak harness for the patterns probe"
    h = prompt_hash(prompt)

    # Reinforce 4× with 'approve'. The first call INSERTs the canonical
    # row at ladder_step=0; each subsequent reinforcement bumps by 1.
    # So 4 calls land at ladder_step=3 (0 → 1 → 2 → 3). That's the peak
    # we then contradict against. The plan only requires peak >
    # CONTRADICTION_DEMOTE_STEPS (=2 in v1.3); peak=3 satisfies that.
    for _ in range(4):
        consolidate_patterns(bus, h, "approve", 0.9)
    pre = _read_canonical_row(bus, h)
    assert pre is not None
    peak_step = pre["ladder_step"]
    assert peak_step > CONTRADICTION_DEMOTE_STEPS, (
        f"4× reinforcement should produce peak > "
        f"CONTRADICTION_DEMOTE_STEPS({CONTRADICTION_DEMOTE_STEPS}) so the "
        f"snap-demote effect is observable; got peak={peak_step}"
    )
    # Sanity-check the bias hint reads the peak from canonical.
    pre_hint = bias_for(prompt, bus)
    assert pre_hint is not None
    assert pre_hint.ladder_step_suggestion == peak_step

    # Contradict with the opposite actionable category.
    consolidate_patterns(bus, h, "reject", 0.85)

    post = _read_canonical_row(bus, h)
    assert post is not None
    expected_step = max(LADDER_FLOOR, peak_step - CONTRADICTION_DEMOTE_STEPS)
    assert post["ladder_step"] == expected_step
    assert post["contradicted_count"] == 1
    # Canonical category does NOT flip on a single contradiction.
    assert post["category"] == "approve"

    post_hint = bias_for(prompt, bus)
    assert post_hint is not None, (
        "bias_for must still surface the canonical row post-contradiction "
        "(category is unchanged, confidence unchanged)"
    )
    assert post_hint.ladder_step_suggestion == expected_step, (
        f"post-contradiction ladder_step_suggestion must equal "
        f"peak({peak_step}) - CONTRADICTION_DEMOTE_STEPS"
        f"({CONTRADICTION_DEMOTE_STEPS}) = {expected_step}; got "
        f"{post_hint.ladder_step_suggestion}. If this is still "
        f"{peak_step}, the contradiction snap-demote isn't reaching "
        f"the bias reader."
    )


# ── Case 4: safety priority short-circuits canonical bias ───────────


def test_pipeline_safety_priority_short_circuits_canonical(
    bus: _msg_bus.MessageBus, tmp_path: Path
) -> None:
    """Destructive shell prompt → safety priority pre-check rejects bias.

    Per plan §8: even with a 4×-reinforced canonical row, the
    ``_is_safety_priority_content`` pre-check in
    ``GovernanceEngine._consult_learn_mode_bias`` MUST reject the
    content class, returning ``None`` regardless of canonical
    reinforcement state.

    The plan note says: "Read ``_consult_learn_mode_bias`` ... to
    confirm the safety pre-check is the integration site, not
    ``bias_for`` itself — adjust the assertion target accordingly."
    Confirmed: ``bias_for`` does NOT do the safety regex check; the
    integration point is ``GovernanceEngine._consult_learn_mode_bias``
    (governance.py). So the assertion target here is the engine
    consultation method.
    """
    adversarial = "rm -rf / --no-preserve-root"
    h = prompt_hash(adversarial)

    # Plant a 4×-reinforced canonical row. ``bias_for`` alone would
    # return a hint for this row.
    _seed_canonical(
        bus,
        prompt=adversarial,
        category="approve",
        confidence=0.95,
        ladder_step=4,
    )

    # Sanity: the row exists and ``bias_for`` (without the safety
    # gate) does return a hint. This documents that the safety check
    # lives at the integration site, not the bias reader.
    raw_hint = bias_for(adversarial, bus)
    assert raw_hint is not None, (
        "bias_for itself does not safety-check; the integration site "
        "is the GovernanceEngine consultation method"
    )

    # Build the engine and consult bias the way the verdict path does.
    bus.open_session("S-pipeline-safety")
    bus.set_hitl_mode("S-pipeline-safety", "async", 0.60)
    snap = ProjectContextSnapshot(repo_path=".", has_intent_file=False)
    hitl = HitlQueue(bus=bus)
    eng = GovernanceEngine(
        project_context=snap,
        bus=bus,
        session_id="S-pipeline-safety",
        mode=Mode.OBSERVE,
        hitl=hitl,
    )

    # Hand-craft a plain ALLOW decision; the safety check fires on the
    # CONTENT, not the decision shape, so it triggers regardless of
    # how the verdict landed.
    allow_decision = GovDecision(
        action="ALLOW",
        confidence=0.5,
        reasoning="ok",
        mode=Mode.OBSERVE,
        source="default",
    )
    bias = eng._consult_learn_mode_bias(adversarial, allow_decision)
    assert bias is None, (
        "_consult_learn_mode_bias MUST return None for destructive "
        "shell content regardless of canonical reinforcement state. "
        "If this returns a BiasHint, the safety-priority pre-check "
        "has regressed and a high-confidence canonical 'approve' row "
        "would silently bias a destructive operation."
    )
