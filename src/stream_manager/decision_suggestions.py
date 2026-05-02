"""FR-UI-5: ranked decision-suggestion candidates.

Returns a ranked list of candidate actions for a given decision row, blending
four sources weighted by `.sm-context.yaml` `decision_suggestion_weights`:

    graph_pattern   — match against the persisted decision_graph patterns
    hitl_override   — recency-decayed historical operator overrides
    static_rule     — governance.fast_precheck destructive-rule hits
    project_context — project_context.fast_precheck hint (intent/static)

Hard-fail on weight validation: load_weights raises ValueError if the weights
do not sum to 1.0 (±0.001), any weight is outside [0,1], or the half-life is
non-positive. The dashboard endpoint surfaces this as HTTP 500 (no silent
fallback) per the FR-UI-5 contract.
"""

from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


# ── Weights config ────────────────────────────────────────────────────


@dataclass(frozen=True)
class SuggestionWeights:
    graph_match: float = 0.40
    hitl_override: float = 0.35
    static_rule: float = 0.15
    project_context: float = 0.10
    recency_half_life_days: float = 14.0


_DEFAULT_WEIGHTS = SuggestionWeights()


def _validate(w: SuggestionWeights) -> None:
    items = (
        ("graph_match", w.graph_match),
        ("hitl_override", w.hitl_override),
        ("static_rule", w.static_rule),
        ("project_context", w.project_context),
    )
    for name, val in items:
        if not isinstance(val, (int, float)):
            raise ValueError(f"decision_suggestion_weights.{name} must be a number")
        if val < 0.0 or val > 1.0:
            raise ValueError(
                f"decision_suggestion_weights.{name}={val} out of range [0,1]"
            )
    total = sum(v for _, v in items)
    if abs(total - 1.0) > 0.001:
        raise ValueError(
            f"decision_suggestion_weights must sum to 1.0 (got {total:.4f})"
        )
    if w.recency_half_life_days <= 0:
        raise ValueError(
            "decision_suggestion_weights.recency_half_life_days must be > 0"
        )


def load_weights(yaml_path: Path | None) -> SuggestionWeights:
    """Load + validate weights from `.sm-context.yaml`. Defaults if missing.

    Raises ValueError if the file is present but contains an invalid
    `decision_suggestion_weights` block (sum != 1.0, weight out of range,
    half-life <= 0). Callers must NOT silently swallow this — FR-UI-5
    requires hard-fail surfacing.
    """
    if yaml_path is None or not Path(yaml_path).exists():
        _validate(_DEFAULT_WEIGHTS)
        return _DEFAULT_WEIGHTS

    raw: dict | None = None
    p = Path(yaml_path)
    suffix = p.suffix.lower()
    try:
        if suffix in (".yaml", ".yml"):
            try:
                import yaml  # type: ignore[import-untyped]
            except Exception as exc:
                # Fall back to bundled defaults if PyYAML missing.
                log.warning("PyYAML missing; using default suggestion weights")
                _validate(_DEFAULT_WEIGHTS)
                return _DEFAULT_WEIGHTS
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        elif suffix == ".toml":
            import tomllib

            raw = tomllib.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        raise
    except Exception as exc:
        log.warning("failed to parse %s for weights: %s", yaml_path, exc)
        _validate(_DEFAULT_WEIGHTS)
        return _DEFAULT_WEIGHTS

    if not isinstance(raw, dict):
        _validate(_DEFAULT_WEIGHTS)
        return _DEFAULT_WEIGHTS

    block = raw.get("decision_suggestion_weights")
    if not isinstance(block, dict):
        _validate(_DEFAULT_WEIGHTS)
        return _DEFAULT_WEIGHTS

    weights = SuggestionWeights(
        graph_match=float(block.get("graph_match", _DEFAULT_WEIGHTS.graph_match)),
        hitl_override=float(
            block.get("hitl_override", _DEFAULT_WEIGHTS.hitl_override)
        ),
        static_rule=float(block.get("static_rule", _DEFAULT_WEIGHTS.static_rule)),
        project_context=float(
            block.get("project_context", _DEFAULT_WEIGHTS.project_context)
        ),
        recency_half_life_days=float(
            block.get(
                "recency_half_life_days",
                _DEFAULT_WEIGHTS.recency_half_life_days,
            )
        ),
    )
    _validate(weights)
    return weights


# ── Candidate dataclass ───────────────────────────────────────────────


@dataclass
class Candidate:
    action: str
    confidence: float
    historical_precedent_count: int
    sourced_from: list[str]
    rationale: str
    matched_hash: str
    score: float = 0.0

    def to_json(self) -> dict[str, object]:
        return {
            "action": self.action,
            "confidence": round(float(self.confidence), 4),
            "historical_precedent_count": int(self.historical_precedent_count),
            "sourced_from": list(self.sourced_from),
            "rationale": self.rationale[:140],
            "matched_hash": self.matched_hash,
        }


# ── Helpers ───────────────────────────────────────────────────────────


def _parse_iso(ts: str | None) -> float | None:
    """Parse ISO-8601 to epoch seconds. Tolerant of trailing Z and naïve."""
    if not ts:
        return None
    try:
        s = str(ts)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _recency_weight(age_days: float, half_life_days: float) -> float:
    if half_life_days <= 0:
        return 1.0
    if age_days < 0:
        age_days = 0.0
    return math.exp(-math.log(2.0) * age_days / half_life_days)


def _now_epoch() -> float:
    return datetime.now(timezone.utc).timestamp()


_VALID_ACTIONS = {"ALLOW", "GUIDE", "SUGGEST", "INTERVENE", "BLOCK"}


# Static rule patterns — mirrors project_context._DESTRUCTIVE plus a few
# governance.py shell-hint patterns. Inlined here to avoid coupling on
# private symbols.
_STATIC_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\brm\s+-rf\s+/(?!\w)"), "BLOCK", "destructive root rm"),
    (re.compile(r"\brm\s+-rf\s+~"), "BLOCK", "destructive home rm"),
    (re.compile(r"\bdd\s+if=.*\bof=/dev/"), "BLOCK", "dd to raw device"),
    (
        re.compile(r"\bDROP\s+(DATABASE|TABLE)\b", re.IGNORECASE),
        "BLOCK",
        "DB drop",
    ),
    (re.compile(r"\bmkfs(\.\w+)?\b"), "BLOCK", "filesystem format"),
    (
        re.compile(
            r"git\s+push\s+(--force|-f)\b[^\n]*\b(main|master|production)\b"
        ),
        "INTERVENE",
        "force-push to protected branch",
    ),
    (re.compile(r"\b(eval|exec)\s*\("), "INTERVENE", "code-injection risk"),
    (
        re.compile(
            r"\b(aws_secret_access_key|api[_-]?key|"
            r"bearer\s+[A-Za-z0-9_\-\.]{16,})\b",
            re.IGNORECASE,
        ),
        "BLOCK",
        "credential-shaped content",
    ),
]


def _match_static_rule(content: str) -> tuple[str, str] | None:
    if not content:
        return None
    for pat, action, reason in _STATIC_RULES:
        if pat.search(content):
            return (action, reason)
    return None


# ── Source extractors ─────────────────────────────────────────────────


def _graph_candidate(
    db_conn: sqlite3.Connection, content: str, weights: SuggestionWeights
) -> Candidate | None:
    """Look up a graph-pattern match for the decision content.

    Reads the persisted graph_patterns table directly so we don't need a
    live DecisionGraph instance. Returns None if no row exceeds the
    similarity threshold.
    """
    try:
        rows = db_conn.execute(
            "SELECT hash, level, vector, canonical_text, occurrences, "
            "successes, last_seen FROM graph_patterns"
        ).fetchall()
    except Exception:
        return None
    if not rows:
        return None

    # Reuse decision_graph projection so cosine math matches the engine.
    try:
        from stream_manager.decision_graph import (
            SIMILARITY_THRESHOLD,
            cosine,
            project,
        )
    except Exception:
        return None

    vec = project(content or "")
    best_hash = ""
    best_sim = 0.0
    best_succ = 0.0
    best_occ = 0
    for r in rows:
        try:
            pv = json.loads(r["vector"])
        except Exception:
            continue
        sim = cosine(vec, pv)
        if sim > best_sim:
            best_sim = sim
            best_hash = str(r["hash"])
            occ = int(r["occurrences"] or 0)
            succ = int(r["successes"] or 0)
            best_occ = occ
            best_succ = (succ / occ) if occ > 0 else 0.0

    if best_sim < SIMILARITY_THRESHOLD or not best_hash:
        return None

    confidence = max(0.0, min(1.0, best_succ if best_succ > 0 else 0.5))
    score = weights.graph_match * confidence
    return Candidate(
        action="ALLOW",
        confidence=confidence,
        historical_precedent_count=best_occ,
        sourced_from=["graph_pattern"],
        rationale=(
            f"graph match (n={best_occ}, succ={best_succ:.2f})"
        ),
        matched_hash=best_hash,
        score=score,
    )


def _hitl_override_candidates(
    db_conn: sqlite3.Connection,
    matched_hash: str,
    weights: SuggestionWeights,
    now: float | None = None,
) -> list[Candidate]:
    """Group hitl_overrides by override_action and weight by recency."""
    if not matched_hash:
        return []
    try:
        rows = db_conn.execute(
            "SELECT ho.override_action, ho.timestamp "
            "FROM hitl_overrides ho "
            "JOIN decisions d ON ho.decision_id = d.id "
            "WHERE d.matched_hash = ?",
            (matched_hash,),
        ).fetchall()
    except Exception:
        return []
    if not rows:
        return []

    now_ts = now if now is not None else _now_epoch()
    half = weights.recency_half_life_days
    grouped: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    for r in rows:
        action = str(r[0] or "").upper()
        if action not in _VALID_ACTIONS:
            continue
        ts = _parse_iso(str(r[1])) if r[1] else None
        if ts is None:
            age_days = 0.0
        else:
            age_days = max(0.0, (now_ts - ts) / 86400.0)
        rw = _recency_weight(age_days, half)
        grouped.setdefault(action, []).append(rw)
        counts[action] = counts.get(action, 0) + 1

    out: list[Candidate] = []
    for action, weights_list in grouped.items():
        total_recency = sum(weights_list)
        # Normalize the recency aggregate so a single fresh override yields
        # ~1.0 and old/sparse overrides yield <1.0. We saturate at the
        # number of overrides so 5 fresh overrides ≈ 1.0 contribution.
        n = len(weights_list)
        normalized = min(1.0, total_recency / max(1, n))
        score = weights.hitl_override * normalized
        out.append(
            Candidate(
                action=action,
                confidence=normalized,
                historical_precedent_count=counts[action],
                sourced_from=["hitl_override"],
                rationale=f"{counts[action]} prior override(s) ({action})",
                matched_hash=matched_hash,
                score=score,
            )
        )
    return out


def _static_rule_candidate(
    content: str, matched_hash: str, weights: SuggestionWeights
) -> Candidate | None:
    hit = _match_static_rule(content or "")
    if hit is None:
        return None
    action, reason = hit
    score = weights.static_rule * 1.0
    return Candidate(
        action=action,
        confidence=1.0,
        historical_precedent_count=0,
        sourced_from=["static_rule"],
        rationale=f"static rule: {reason}",
        matched_hash=matched_hash,
        score=score,
    )


def _project_context_candidate(
    content: str,
    matched_hash: str,
    weights: SuggestionWeights,
    project_root: Path | None = None,
) -> Candidate | None:
    """Use project_context.fast_precheck when available."""
    if not content:
        return None
    try:
        from stream_manager.project_context import (
            ProjectContextSnapshot,
            fast_precheck,
            load,
        )
    except Exception:
        return None
    try:
        if project_root is not None and Path(project_root).is_dir():
            snap = load(project_root)
        else:
            snap = ProjectContextSnapshot(repo_path="")
        pre = fast_precheck(content, snap)
    except Exception:
        return None
    if pre is None:
        return None
    confidence = 0.95
    score = weights.project_context * confidence
    return Candidate(
        action=pre.action,
        confidence=confidence,
        historical_precedent_count=0,
        sourced_from=["project_context"],
        rationale=f"project_context: {pre.reasoning}"[:140],
        matched_hash=matched_hash,
        score=score,
    )


# ── Top-level ranker ──────────────────────────────────────────────────


def rank_candidates(
    decision_row: dict,
    db_conn: sqlite3.Connection,
    weights: SuggestionWeights,
    now: float | None = None,
    project_root: Path | None = None,
) -> list[Candidate]:
    """Build, score, and merge candidate actions for a decision.

    `decision_row` must include keys ``action``, ``confidence``, ``content``,
    and ``matched_hash``. Returns a list sorted by descending blended score.
    Always returns at least one candidate (engine-proposal fallback).
    """
    content = str(decision_row.get("content") or "")
    matched_hash = str(decision_row.get("matched_hash") or "")
    engine_action = str(decision_row.get("action") or "ALLOW")
    engine_conf = float(decision_row.get("confidence") or 0.0)

    candidates: list[Candidate] = []

    g = _graph_candidate(db_conn, content, weights)
    if g is not None:
        candidates.append(g)
        if not matched_hash:
            matched_hash = g.matched_hash

    candidates.extend(
        _hitl_override_candidates(db_conn, matched_hash, weights, now=now)
    )

    s = _static_rule_candidate(content, matched_hash, weights)
    if s is not None:
        candidates.append(s)

    pc = _project_context_candidate(content, matched_hash, weights, project_root)
    if pc is not None:
        candidates.append(pc)

    # Merge candidates that target the same action: sum scores, union sources,
    # sum precedent counts, take max confidence, and stitch rationales.
    merged: dict[str, Candidate] = {}
    for c in candidates:
        cur = merged.get(c.action)
        if cur is None:
            merged[c.action] = Candidate(
                action=c.action,
                confidence=c.confidence,
                historical_precedent_count=c.historical_precedent_count,
                sourced_from=list(c.sourced_from),
                rationale=c.rationale,
                matched_hash=c.matched_hash or matched_hash,
                score=c.score,
            )
            continue
        cur.score += c.score
        cur.confidence = max(cur.confidence, c.confidence)
        cur.historical_precedent_count += c.historical_precedent_count
        for src in c.sourced_from:
            if src not in cur.sourced_from:
                cur.sourced_from.append(src)
        # Append rationale, capped at 140 chars.
        joined = f"{cur.rationale} + {c.rationale}"
        cur.rationale = joined[:140]

    # Recompute precedent count from hitl_overrides for each action so it
    # reflects history regardless of which sources contributed.
    if matched_hash:
        try:
            rows = db_conn.execute(
                "SELECT ho.override_action, COUNT(*) "
                "FROM hitl_overrides ho "
                "JOIN decisions d ON ho.decision_id = d.id "
                "WHERE d.matched_hash = ? GROUP BY ho.override_action",
                (matched_hash,),
            ).fetchall()
            counts = {str(r[0]).upper(): int(r[1]) for r in rows if r[0]}
            for act, c in merged.items():
                hist = counts.get(act, 0)
                if hist > c.historical_precedent_count:
                    c.historical_precedent_count = hist
        except Exception:
            pass

    if not merged:
        # Fallback to the engine's existing proposal — at least one
        # candidate must always be returned.
        fallback = Candidate(
            action=engine_action,
            confidence=engine_conf,
            historical_precedent_count=0,
            sourced_from=["graph_pattern"],
            rationale="engine proposal (no source matched)",
            matched_hash=matched_hash,
            score=weights.graph_match * max(0.0, min(1.0, engine_conf)),
        )
        return [fallback]

    out = sorted(merged.values(), key=lambda c: c.score, reverse=True)
    return out
