"""Agent Registry — FR-AR-6.

Loads agent governance profiles from `agent_profiles.yaml` and resolves
attribution metadata (from JSONL tail or pattern inference) to a profile.

Resolution priority:
    1. exact `example_agents` name match against `attribution_plugin`
    2. `is_sidechain=True` -> `sub_agent` profile
    3. fall back to `unknown`

Active-profile bookkeeping is per-session: a single SM instance can govern
multiple sessions in parallel, each with its own most-recently-identified
agent.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

import yaml  # type: ignore[import-untyped]

DEFAULT_PROFILE_SLUG = "unknown"
SIDECHAIN_PROFILE_SLUG = "sub_agent"


@dataclass(frozen=True)
class AgentProfile:
    slug: str
    default_action: str
    allowed_ops: list[str]
    restricted_ops: list[str]
    blocked_ops: list[str]
    escalate_to: str
    confidence_floor: float
    example_agents: list[str]


_VALID_OVERRIDE_MODES: frozenset[str] = frozenset(
    {"OBSERVE", "SUGGEST", "GUIDE", "INTERVENE", "BLOCK"}
)


@dataclass
class AgentRegistry:
    profiles_path: Path
    _profiles: dict[str, AgentProfile] = field(default_factory=dict)
    _by_example: dict[str, AgentProfile] = field(default_factory=dict)
    _active: dict[str, AgentProfile] = field(default_factory=dict)
    # Phase 6 follow-up: per-agent mode override storage.
    # session_id -> agent_id -> mode_str. Override applies to default_action
    # only; profile blocked_ops/restricted_ops still fire (safety floor).
    _overrides: dict[str, dict[str, str]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self._load()

    def _load(self) -> None:
        raw = yaml.safe_load(self.profiles_path.read_text(encoding="utf-8")) or {}
        profiles_block = raw.get("profiles", {}) if isinstance(raw, dict) else {}
        profiles: dict[str, AgentProfile] = {}
        by_example: dict[str, AgentProfile] = {}
        for slug, body in profiles_block.items():
            if not isinstance(body, dict):
                continue
            profile = AgentProfile(
                slug=str(slug),
                default_action=str(body.get("default_action", "GUIDE")),
                allowed_ops=list(body.get("allowed_ops") or []),
                restricted_ops=list(body.get("restricted_ops") or []),
                blocked_ops=list(body.get("blocked_ops") or []),
                escalate_to=str(body.get("escalate_to", "INTERVENE")),
                confidence_floor=float(body.get("confidence_floor", 0.0)),
                example_agents=list(body.get("example_agents") or []),
            )
            profiles[profile.slug] = profile
            for name in profile.example_agents:
                by_example[str(name)] = profile
        # Ensure baseline profiles exist even if YAML is missing them.
        if DEFAULT_PROFILE_SLUG not in profiles:
            profiles[DEFAULT_PROFILE_SLUG] = AgentProfile(
                slug=DEFAULT_PROFILE_SLUG,
                default_action="GUIDE",
                allowed_ops=["file_read"],
                restricted_ops=["file_edit", "shell_command", "tool_execution"],
                blocked_ops=[
                    "destructive_shell",
                    "force_push_protected",
                    "credential_exfiltration",
                ],
                escalate_to="INTERVENE",
                confidence_floor=0.60,
                example_agents=[],
            )
        if SIDECHAIN_PROFILE_SLUG not in profiles:
            profiles[SIDECHAIN_PROFILE_SLUG] = AgentProfile(
                slug=SIDECHAIN_PROFILE_SLUG,
                default_action="ALLOW",
                allowed_ops=[],
                restricted_ops=[],
                blocked_ops=[
                    "any_op_outside_declared_task_type",
                    "destructive_shell",
                    "credential_exfiltration",
                ],
                escalate_to="BLOCK",
                confidence_floor=0.90,
                example_agents=[],
            )
        self._profiles = profiles
        self._by_example = by_example

    @property
    def profiles(self) -> dict[str, AgentProfile]:
        return dict(self._profiles)

    def get(self, slug: str) -> AgentProfile | None:
        return self._profiles.get(slug)

    def resolve(
        self,
        attribution_plugin: str,
        attribution_skill: str,
        is_sidechain: bool,
    ) -> AgentProfile:
        # Priority 1: exact example_agents name match on attribution_plugin.
        if attribution_plugin:
            hit = self._by_example.get(attribution_plugin)
            if hit is not None:
                return hit
        # Priority 1b: also try attribution_skill (e.g. when plugin is generic
        # but the skill name maps directly to a known role).
        if attribution_skill:
            hit = self._by_example.get(attribution_skill)
            if hit is not None:
                return hit
        # Priority 2: sidechain -> sub_agent profile.
        if is_sidechain:
            sub = self._profiles.get(SIDECHAIN_PROFILE_SLUG)
            if sub is not None:
                return sub
        # Priority 3: unknown fallback.
        unknown = self._profiles.get(DEFAULT_PROFILE_SLUG)
        assert unknown is not None  # _load guarantees this exists
        return unknown

    def active_profile(self, session_id: str) -> AgentProfile | None:
        with self._lock:
            return self._active.get(session_id)

    def update_active(self, session_id: str, profile: AgentProfile) -> None:
        with self._lock:
            self._active[session_id] = profile

    def all_active(self) -> dict[str, AgentProfile]:
        with self._lock:
            return dict(self._active)

    # ── Phase 6 follow-up: per-agent mode override API ─────────────────
    #
    # Override applies to ``profile.default_action`` only. Profile
    # ``blocked_ops`` / ``restricted_ops`` still fire — operators cannot
    # downgrade safety constraints by setting OBSERVE. Storage is in-memory;
    # writes take the registry lock, single-key reads are GIL-safe.

    def set_mode_override(
        self,
        session_id: str,
        agent_id: str,
        mode: str | None,
    ) -> None:
        """Set or clear a per-agent governance mode override.

        ``mode=None`` removes the override (revert to profile default).
        Any other value must be one of OBSERVE/SUGGEST/GUIDE/INTERVENE/BLOCK
        — otherwise raises ``ValueError``.
        """
        if mode is not None and mode not in _VALID_OVERRIDE_MODES:
            raise ValueError(
                f"mode must be one of {sorted(_VALID_OVERRIDE_MODES)} or None"
            )
        with self._lock:
            if mode is None:
                sess_map = self._overrides.get(session_id)
                if sess_map and agent_id in sess_map:
                    del sess_map[agent_id]
                    if not sess_map:
                        self._overrides.pop(session_id, None)
                return
            self._overrides.setdefault(session_id, {})[agent_id] = mode

    def get_mode_override(
        self, session_id: str, agent_id: str
    ) -> str | None:
        """Return the active mode override for (session, agent), or None."""
        sess_map = self._overrides.get(session_id)
        if not sess_map:
            return None
        return sess_map.get(agent_id)

    def get_session_overrides(self, session_id: str) -> dict[str, str]:
        """Return a copy of {agent_id: mode} for the session."""
        sess_map = self._overrides.get(session_id)
        if not sess_map:
            return {}
        with self._lock:
            return dict(sess_map)

    def clear_session_overrides(self, session_id: str) -> None:
        """Drop all overrides for ``session_id`` (convenience for teardown)."""
        with self._lock:
            self._overrides.pop(session_id, None)
