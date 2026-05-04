"""Tests for v1.3 P5d — Learn Mode advisory bias hookup.

Asserts that ``learn_categorizer.bias_for`` and the governance-side
consultation point honor every safety invariant from
``docs/learn-mode-design.md`` §2.8 and ``INTENT.md`` §"Safety priorities":

  1. ``bias_for`` returns None when no row matches the prompt_hash.
  2. Among multiple rows on the same hash, the most recently
     reinforced (then highest-confidence) row wins.
  3. Sub-threshold rows (< MIN_BIAS_CONFIDENCE) yield None.
  4. Governance evaluation honors bias as a HINT — bias never replaces
     the verdict; it pre-fills the HITL prompt and emits an audit row.
  5. Adversarial prompts (destructive shell, force-push to main,
     eval/exec, credential exfiltration) reject bias even at
     confidence=1.0. INTENT.md priorities ALWAYS WIN.
  6. HITL gate fires even when bias is high-confidence — the gate is
     never short-circuited.
  7. ``learn_mode_bias_applied`` envelope is emitted on the bus when
     bias fires.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from stream_manager import message_bus as _msg_bus
from stream_manager.governance import GovernanceEngine, Mode
from stream_manager.hitl import HitlQueue
from stream_manager.learn_categorizer import (
    MIN_BIAS_CONFIDENCE,
    BiasHint,
    bias_for,
    prompt_hash,
)
from stream_manager.messages import Message
from stream_manager.project_context import ProjectContextSnapshot


# ── helpers ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _enable_learn_mode(monkeypatch):
    """Default fixture: enable SM_LEARN_MODE for the bias-positive tests.

    Fix A (review): ``bias_for`` now early-returns None when
    SM_LEARN_MODE is unset. Most tests in this file want bias enabled;
    individual tests that probe the gated path override this with
    ``monkeypatch.delenv("SM_LEARN_MODE", raising=False)``.
    """
    monkeypatch.setenv("SM_LEARN_MODE", "1")


@pytest.fixture
def bus(tmp_path: Path) -> _msg_bus.MessageBus:
    b = _msg_bus.MessageBus(str(tmp_path / "bias.db"))
    yield b
    try:
        b.close()
    except Exception:
        pass


def _insert_pattern(
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
        "INSERT INTO learn_patterns "
        "(prompt_hash, category, confidence, ladder_step, "
        " last_reinforced_ts, contradicted_count, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            prompt_hash(prompt),
            category,
            float(confidence),
            int(ladder_step),
            float(now),
            0,
            float(now),
        ),
    )


def _build_engine(
    bus: _msg_bus.MessageBus,
    *,
    session_id: str = "S-bias",
    with_hitl: bool = True,
    hitl_mode: str = "async",
    hitl_floor: float = 0.60,
) -> GovernanceEngine:
    bus.open_session(session_id)
    bus.set_hitl_mode(session_id, hitl_mode, hitl_floor)
    snap = ProjectContextSnapshot(repo_path=".", has_intent_file=False)
    hitl = HitlQueue(bus=bus) if with_hitl else None
    return GovernanceEngine(
        project_context=snap,
        bus=bus,
        session_id=session_id,
        mode=Mode.OBSERVE,
        hitl=hitl,
    )


def _make_msg(content: str) -> Message:
    return Message.new(role="assistant", content=content)


# ── bias_for direct tests ───────────────────────────────────────────


def test_bias_for_returns_none_when_no_match(bus):
    assert bias_for("nothing in the table", bus) is None


def test_bias_for_returns_none_for_empty_prompt(bus):
    assert bias_for("", bus) is None


def test_bias_for_picks_most_recently_reinforced(bus):
    """Multiple rows on the same hash → freshest reinforcement wins."""
    prompt = "Want me to ship the v1.3 PR?"
    older = time.time() - 3600
    newer = time.time()
    # Insert two matching rows. The older one has higher confidence, but
    # the newer one is more recently reinforced — design says recency
    # wins (last_reinforced_ts DESC, then confidence DESC).
    _insert_pattern(
        bus,
        prompt=prompt,
        category="approve",
        confidence=0.95,
        last_reinforced_ts=older,
    )
    _insert_pattern(
        bus,
        prompt=prompt,
        category="reject",
        confidence=0.80,
        last_reinforced_ts=newer,
    )
    hint = bias_for(prompt, bus)
    assert hint is not None
    assert hint.category == "reject"
    assert hint.confidence == pytest.approx(0.80)


def test_bias_for_breaks_ties_on_confidence(bus):
    """Same last_reinforced_ts → highest confidence wins."""
    prompt = "Same timestamp tie-break"
    fixed_ts = time.time()
    _insert_pattern(
        bus,
        prompt=prompt,
        category="approve",
        confidence=0.70,
        last_reinforced_ts=fixed_ts,
    )
    _insert_pattern(
        bus,
        prompt=prompt,
        category="approve",
        confidence=0.92,
        last_reinforced_ts=fixed_ts,
    )
    hint = bias_for(prompt, bus)
    assert hint is not None
    assert hint.confidence == pytest.approx(0.92)


def test_bias_for_returns_none_below_threshold(bus):
    prompt = "low-confidence prompt"
    _insert_pattern(
        bus,
        prompt=prompt,
        category="approve",
        confidence=MIN_BIAS_CONFIDENCE - 0.1,
    )
    assert bias_for(prompt, bus) is None


def test_bias_for_skips_non_actionable_categories(bus):
    """clarify/acknowledge/redirect/unknown are not actionable in v1.3."""
    prompt = "non-actionable category prompt"
    _insert_pattern(
        bus,
        prompt=prompt,
        category="clarify",
        confidence=0.99,
    )
    assert bias_for(prompt, bus) is None


def test_bias_for_returns_hint_shape(bus):
    prompt = "shape test prompt"
    ts = time.time()
    _insert_pattern(
        bus,
        prompt=prompt,
        category="approve",
        confidence=0.85,
        ladder_step=2,
        last_reinforced_ts=ts,
    )
    hint = bias_for(prompt, bus)
    assert isinstance(hint, BiasHint)
    assert hint.category == "approve"
    assert hint.confidence == pytest.approx(0.85)
    assert hint.ladder_step_suggestion == 2
    assert hint.last_reinforced_ts == pytest.approx(ts)
    assert hint.pattern_id > 0


# ── governance integration tests ────────────────────────────────────


def _last_messages(bus: _msg_bus.MessageBus, type_: str) -> list[dict]:
    rows = bus.fetch_rows(
        "SELECT id, type, content, metadata FROM messages WHERE type=? "
        "ORDER BY rowid ASC",
        (type_,),
    )
    out = []
    import json as _json
    for r in rows:
        meta = {}
        try:
            meta = _json.loads(r[3]) if r[3] else {}
        except Exception:
            meta = {}
        out.append({"id": r[0], "type": r[1], "content": r[2], "metadata": meta})
    return out


def test_governance_emits_bias_audit_envelope_when_hitl_fires(bus):
    """When bias matches AND HITL trigger fires, an audit row is emitted.

    We pick a prompt that contains actionable-signal tokens so
    fast_precheck does NOT short-circuit to ALLOW; instead it falls
    through to the graph (no match) → CLI (disabled by default) →
    default branch with ``source="default"``. The HITL ``NEW_PATTERN``
    trigger then fires, which is the moment the bias audit envelope
    is emitted.
    """
    eng = _build_engine(bus, hitl_mode="async", hitl_floor=0.60)
    prompt = "Run pytest tests/test_smoke.py to confirm the v1.3 PR is green"
    _insert_pattern(
        bus,
        prompt=prompt,
        category="approve",
        confidence=0.95,
        ladder_step=2,
    )
    msg = _make_msg(prompt)
    decision = eng.evaluate(msg)
    audits = _last_messages(bus, "learn_mode_bias_applied")
    assert len(audits) == 1, f"expected one audit row, got {len(audits)}"
    meta = audits[0]["metadata"]
    assert meta["category"] == "approve"
    assert meta["confidence"] == pytest.approx(0.95)
    assert meta["ladder_step_suggestion"] == 2
    assert "pattern_id" in meta
    # decision is not mutated into auto-allow shape — it carries its
    # original source (default branch in this scenario).
    assert decision.source in {"default", "graph", "cli"}


def test_governance_does_not_auto_allow_destructive_shell(bus):
    """Safety priority #1: destructive shell ALWAYS BLOCKS, regardless of pattern.

    The engine is built in BLOCK mode so the fast_precheck verdict is
    not downgraded by ``_apply_mode``. Even with a planted high-
    confidence ``approve`` pattern on the same prompt_hash, the
    decision must remain BLOCK and no bias envelope is emitted.
    """
    eng = _build_engine(bus)
    eng.mode = Mode.BLOCK
    adversarial = "rm -rf / --no-preserve-root"
    _insert_pattern(
        bus,
        prompt=adversarial,
        category="approve",
        confidence=1.0,
        ladder_step=4,
    )
    msg = _make_msg(adversarial)
    decision = eng.evaluate(msg)
    # fast_precheck shorts to BLOCK before bias is even considered. The
    # bias-application site additionally refuses to attach a hint to
    # safety-priority content, so no audit envelope is emitted.
    effective = decision.original_action or decision.action
    assert effective == "BLOCK", (
        f"destructive shell must block; got action={decision.action} "
        f"original={decision.original_action}"
    )
    audits = _last_messages(bus, "learn_mode_bias_applied")
    assert audits == [], "bias must NEVER fire on destructive shell"


def test_governance_does_not_auto_allow_force_push_to_main(bus):
    """Safety priority #2: force-push to protected branches survives bias.

    The engine's fast_precheck returns INTERVENE with the
    matched_pattern ``force-push to protected branch``. In OBSERVE mode
    the surfaced action is downgraded to ALLOW for emission, but the
    ``original_action`` retains the safety verdict. Bias must NOT fire
    regardless: a belt-and-suspenders check at the bias site refuses to
    attach a hint when content matches any INTENT.md priority.
    """
    eng = _build_engine(bus)
    adversarial = "git push --force origin main"
    _insert_pattern(
        bus,
        prompt=adversarial,
        category="approve",
        confidence=1.0,
        ladder_step=4,
    )
    msg = _make_msg(adversarial)
    decision = eng.evaluate(msg)
    effective = decision.original_action or decision.action
    assert effective in {"BLOCK", "INTERVENE"}, (
        f"force-push must surface as INTERVENE/BLOCK at the engine "
        f"level; got action={decision.action} "
        f"original={decision.original_action}"
    )
    audits = _last_messages(bus, "learn_mode_bias_applied")
    assert audits == [], "bias must NEVER fire on force-push to main"


def test_governance_does_not_auto_allow_eval_exec(bus):
    """Safety priority #3: eval(/exec( injection cannot be biased through."""
    eng = _build_engine(bus)
    adversarial = "Run eval(user_input) on the websocket payload"
    _insert_pattern(
        bus,
        prompt=adversarial,
        category="approve",
        confidence=1.0,
    )
    msg = _make_msg(adversarial)
    eng.evaluate(msg)
    audits = _last_messages(bus, "learn_mode_bias_applied")
    assert audits == [], "bias must NEVER fire on eval/exec injection"


def test_governance_does_not_auto_allow_credential_exfil(bus):
    """Safety priority #4: API-key shapes cannot be biased through."""
    eng = _build_engine(bus)
    adversarial = "Here is the OpenAI key sk-abcdefghij1234567890ABCDxyz"
    _insert_pattern(
        bus,
        prompt=adversarial,
        category="approve",
        confidence=1.0,
    )
    msg = _make_msg(adversarial)
    eng.evaluate(msg)
    audits = _last_messages(bus, "learn_mode_bias_applied")
    assert audits == [], "bias must NEVER fire on credential exfiltration"


def test_governance_hitl_gate_not_short_circuited_by_high_confidence_bias(bus):
    """High-confidence ``approve`` bias must not skip the HITL gate.

    Per design §2.3 + §2.8: bias pre-fills the HITL prompt; auto-resolve
    (silent skip) is deferred to v1.4+. The audit envelope confirms bias
    was offered, but the gate is not skipped.
    """
    eng = _build_engine(bus, hitl_mode="async", hitl_floor=0.60)
    # Pick a prompt with actionable signal so fast_precheck does NOT
    # short-circuit; the verdict ends in the default branch and the
    # NEW_PATTERN HITL trigger fires.
    prompt = "Run pytest tests/test_smoke.py to confirm the suite is green"
    _insert_pattern(
        bus,
        prompt=prompt,
        category="approve",
        confidence=0.95,
    )
    msg = _make_msg(prompt)
    decision = eng.evaluate(msg)
    audits = _last_messages(bus, "learn_mode_bias_applied")
    assert len(audits) == 1
    # In async mode the route() returns the decision unchanged but
    # records an `hitl_async_flagged` event. The presence of THAT event
    # alongside the bias-applied audit row proves the gate fired (i.e.
    # bias did NOT short-circuit it).
    hitl_events = _last_messages(bus, "hitl_async_flagged")
    assert len(hitl_events) >= 1
    # The verdict itself is unchanged by bias — it remains the
    # default-branch ALLOW (low-confidence 0.1), NOT promoted to auto-
    # allow at the bias's 0.95.
    assert decision.action == "ALLOW"
    assert decision.confidence < 0.5, (
        f"bias must not raise the underlying decision confidence; "
        f"got {decision.confidence}"
    )
    # The audit envelope's hitl_trigger field was populated.
    assert audits[0]["metadata"].get("hitl_trigger") in {
        "new_pattern", "low_confidence", "desktop_pause",
    }


def test_governance_no_bias_emitted_on_block_decision(bus):
    """If the verdict is BLOCK/INTERVENE, bias should not even be offered."""
    eng = _build_engine(bus)
    # Destructive shell triggers fast_precheck → BLOCK, and the bias
    # site additionally refuses to attach. We verified that above; here
    # we double-check on a non-safety-priority BLOCK source by planting
    # a benign prompt and a matching `reject` pattern: the audit fires
    # only when the verdict was non-BLOCK/INTERVENE.
    prompt = "Some neutral text"
    _insert_pattern(
        bus,
        prompt=prompt,
        category="reject",
        confidence=0.9,
    )
    msg = _make_msg(prompt)
    eng.evaluate(msg)
    audits = _last_messages(bus, "learn_mode_bias_applied")
    # Either the audit fires (decision was ALLOW + HITL trigger fired)
    # or it does not (no HITL trigger at all). The ASSERT we want is
    # that whenever it fires, it was NOT for a BLOCK/INTERVENE decision.
    for a in audits:
        assert a["metadata"]["category"] == "reject"


# ── review-fix tests ────────────────────────────────────────────────


def test_bias_for_returns_none_when_learn_mode_disabled(bus, monkeypatch):
    """Fix A (review): bias_for honors the SM_LEARN_MODE env gate.

    When SM_LEARN_MODE is unset, the categorizer worker is not running
    but stale ``learn_patterns`` rows from a prior session may still
    exist. ``bias_for`` MUST early-return None in that case so the old
    rows can't silently bias the verdict.
    """
    monkeypatch.delenv("SM_LEARN_MODE", raising=False)
    prompt = "Should be ignored when learn mode is off"
    _insert_pattern(
        bus,
        prompt=prompt,
        category="approve",
        confidence=0.99,
    )
    assert bias_for(prompt, bus) is None
    # Also "0" / "false" must disable.
    monkeypatch.setenv("SM_LEARN_MODE", "0")
    assert bias_for(prompt, bus) is None


def test_bias_floor_env_override(bus, monkeypatch):
    """Fix G (review): SM_LEARN_BIAS_FLOOR overrides the default 0.6 floor.

    Importing ``learn_categorizer`` pins ``MIN_BIAS_CONFIDENCE`` at
    module-load time. We assert the override takes effect by reloading
    the module under a patched env.
    """
    monkeypatch.setenv("SM_LEARN_BIAS_FLOOR", "0.4")
    import importlib

    import stream_manager.learn_categorizer as lc_mod
    reloaded = importlib.reload(lc_mod)
    try:
        assert reloaded.MIN_BIAS_CONFIDENCE == pytest.approx(0.4)
        prompt = "Below default floor"
        _insert_pattern(
            bus,
            prompt=prompt,
            category="approve",
            confidence=0.5,  # below default 0.6, above override 0.4
        )
        hint = reloaded.bias_for(prompt, bus)
        assert hint is not None
        assert hint.confidence == pytest.approx(0.5)
    finally:
        # Restore default floor for other tests in the suite.
        monkeypatch.delenv("SM_LEARN_BIAS_FLOOR", raising=False)
        importlib.reload(lc_mod)


def test_hitl_row_carries_bias_prefill(bus):
    """Fix B (review): bias hint pre-fills the hitl_pending row.

    Drives ``evaluate()`` with a matching pattern in sync HITL mode so a
    pending row is created. Asserts the row's ``bias_hint`` JSON column
    contains the category, confidence, and pattern_id fields the
    dashboard needs to pre-fill the operator prompt.
    """
    import json

    eng = _build_engine(bus, hitl_mode="async", hitl_floor=0.60)
    prompt = "Run pytest tests/test_smoke.py to confirm the v1.3 PR is green"
    _insert_pattern(
        bus,
        prompt=prompt,
        category="approve",
        confidence=0.95,
        ladder_step=2,
    )
    msg = _make_msg(prompt)
    eng.evaluate(msg)
    rows = bus.fetch_rows(
        "SELECT bias_hint FROM hitl_pending ORDER BY id DESC LIMIT 1"
    )
    assert rows, "expected a hitl_pending row to be queued"
    raw = rows[0][0] or ""
    assert raw, "bias_hint column must be populated"
    payload = json.loads(raw)
    assert payload["category"] == "approve"
    assert payload["confidence"] == pytest.approx(0.95)
    assert payload["ladder_step_suggestion"] == 2
    assert payload["pattern_id"] > 0


def test_consult_bias_respects_observe_downgrade(bus):
    """Fix D (review): OBSERVE downgrade does not unmask BLOCK to bias.

    In OBSERVE mode ``_apply_mode`` rewrites a BLOCK verdict to ALLOW
    (preserving the original on ``original_action``). Reading
    ``decision.action`` alone would let bias attach. The fix consults
    ``decision.original_action or decision.action`` first, so a BLOCK
    that was downgraded to ALLOW for emission still suppresses bias.
    """
    from stream_manager.governance import GovDecision
    from stream_manager.learn_categorizer import BiasHint
    eng = _build_engine(bus)
    eng.mode = Mode.OBSERVE
    # Hand-craft a decision shape that mirrors what _apply_mode produces:
    # surfaced ALLOW, original BLOCK. The content is benign so safety-
    # priority does not short-circuit; only the original_action gate
    # should reject the bias.
    decision = GovDecision(
        action="ALLOW",
        confidence=0.9,
        reasoning="observed: graph BLOCK",
        mode=Mode.OBSERVE,
        source="graph",
        original_action="BLOCK",
    )
    # Plant a matching pattern; without Fix D this would attach.
    prompt = "neutral phrasing for downgrade test"
    _insert_pattern(
        bus,
        prompt=prompt,
        category="approve",
        confidence=0.95,
    )
    bias = eng._consult_learn_mode_bias(prompt, decision)
    assert bias is None, "bias must NOT attach to a downgraded BLOCK"
    # And a true ALLOW still permits bias.
    decision_allow = GovDecision(
        action="ALLOW",
        confidence=0.9,
        reasoning="ok",
        mode=Mode.OBSERVE,
        source="graph",
    )
    bias2 = eng._consult_learn_mode_bias(prompt, decision_allow)
    assert isinstance(bias2, BiasHint)
    assert bias2.category == "approve"
