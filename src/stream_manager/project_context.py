from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

INTENT_FILES: tuple[str, ...] = ("INTENT.md",)
DOC_FILES: tuple[str, ...] = ("README.md", "CONTRIBUTING.md", "SECURITY.md", "CODEOWNERS")
MANIFEST_FILES: tuple[str, ...] = (
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
)


_META_CONTENT: list[tuple[re.Pattern[str], str]] = [
    # Claude chain-of-thought / extended thinking blocks
    (re.compile(r"</?thinking[\s>]"), "claude-thinking-block"),
    # Claude Code CLI internal metadata tags (local-command-caveat, slash-command XML)
    (
        re.compile(
            r"<(?:local-command-caveat|command-name|command-message|command-args|local-command-stdout)[\s>]"
        ),
        "claude-cli-metadata",
    ),
    # Tool-use XML parameter tags
    (re.compile(r"<parameter\s+name="), "tool-use-xml"),
    # Plugin mode switches (caveman, etc.) — conversational UI state, not code actions
    (
        re.compile(
            r"\bCAVEMAN\s+MODE\s+ACTIVE\b|\bcaveman\s+(?:mode\s+)?(?:ultra|full|lite)\b",
            re.IGNORECASE,
        ),
        "plugin-mode-switch",
    ),
]

_HAS_SHELL_SYNTAX = re.compile(
    r'[|&;$`]|\b(?:rm|git|mv|cp|curl|wget|ssh|sudo|chmod|chown|kill|'
    r'python3?|node|npm|pip|docker|kubectl|make|bash|sh|eval|exec)\b'
)

_CONVERSATIONAL_ONLY = re.compile(
    r"^(?:go|yes|ok|okay|sure|continue|proceed|done|thanks|thank\s+you|good|great|"
    r"perfect|sounds\s+good|got\s+it|understood|acknowledged|noted)\s*[.!]?\s*$",
    re.IGNORECASE,
)

# Patterns that indicate governable content — shell ops, file paths, URLs, DB commands.
# Content with NONE of these signals is conversational/explanatory and safe to ALLOW
# without spending a CLI escalation (avoids "inner JSON parse failed" degradations).
_ACTIONABLE_SIGNAL = re.compile(
    r'[|&;$`]'
    r'|\b(?:rm|git|mv|cp|curl|wget|ssh|sudo|chmod|chown|kill|'
    r'python3?|node|npm|pip|docker|kubectl|make|bash|sh|eval|exec|'
    r'SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)\b'
    r'|https?://|file://'
    r'|\b\w+\.(?:py|js|ts|jsx|tsx|json|yaml|yml|toml|sh|sql|md|db|env)\b'
    r'|(?:token|secret|api[_\-]?key|password|passwd|credential)\s*=',
    re.IGNORECASE,
)


_DESTRUCTIVE: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\brm\s+-rf\s+/(?!\w)"), "BLOCK", "destructive root rm"),
    (re.compile(r"\brm\s+-rf\s+~"), "BLOCK", "destructive home rm"),
    (re.compile(r"\bdd\s+if=.*\bof=/dev/"), "BLOCK", "dd to raw device"),
    (re.compile(r"\bDROP\s+(DATABASE|TABLE)\b", re.IGNORECASE), "BLOCK", "DB drop"),
    (re.compile(r"\bmkfs(\.\w+)?\b"), "BLOCK", "filesystem format"),
    (
        re.compile(r"git\s+push\s+(--force|-f)\b[^\n]*\b(main|master|production)\b"),
        "INTERVENE",
        "force-push to protected branch",
    ),
    (re.compile(r"\b(eval|exec)\s*\("), "INTERVENE", "code-injection risk"),
    (
        re.compile(r"\b(aws_secret_access_key|api[_-]?key|bearer\s+[A-Za-z0-9_\-\.]{16,})\b", re.IGNORECASE),
        "BLOCK",
        "credential-shaped content",
    ),
]


@dataclass(frozen=True)
class FastPrecheckDecision:
    action: str
    reasoning: str
    matched_pattern: str = ""


@dataclass
class ProjectContextSnapshot:
    repo_path: str
    intent_text: str = ""
    has_intent_file: bool = False
    docs: dict[str, str] = field(default_factory=dict)
    manifests: dict[str, str] = field(default_factory=dict)

    def intent_summary(self, max_tokens: int = 600) -> str:
        max_chars = max_tokens * 4
        parts: list[str] = []
        if self.intent_text:
            parts.append(f"## Intent\n{self.intent_text}")
        if "README.md" in self.docs:
            parts.append(f"## README\n{self.docs['README.md']}")
        if "SECURITY.md" in self.docs:
            parts.append(f"## Security\n{self.docs['SECURITY.md']}")
        return "\n\n".join(parts)[:max_chars]


def load(repo_path: str | Path, ignore_intent: bool = False) -> ProjectContextSnapshot:
    """Local-only repo context loader. No GitHub API for Spike B.

    `ignore_intent=True` skips INTENT.md ingestion — used by the A/B
    experiment to measure whether the intent file actually changes
    decisions.
    """
    p = Path(repo_path)
    snap = ProjectContextSnapshot(repo_path=str(p))
    if not p.is_dir():
        return snap

    if not ignore_intent:
        for f in INTENT_FILES:
            fp = p / f
            if fp.exists():
                snap.intent_text = _safe_read(fp)
                snap.has_intent_file = True
                break

    for f in DOC_FILES:
        fp = p / f
        if fp.exists():
            snap.docs[f] = _safe_read(fp)

    for f in MANIFEST_FILES:
        fp = p / f
        if fp.exists():
            snap.manifests[f] = _safe_read(fp)

    return snap


def fast_precheck(content: str, snap: ProjectContextSnapshot) -> FastPrecheckDecision | None:
    """Sub-millisecond static + project-aware safety check. No network."""
    for pat, action, reason in _DESTRUCTIVE:
        m = pat.search(content)
        if m:
            return FastPrecheckDecision(action=action, reasoning=reason, matched_pattern=m.group(0))

    # Known non-actionable content: thinking blocks, CLI metadata tags, plugin mode
    # switches. Short-circuit to ALLOW so CLI escalation budget is not spent on these.
    for pat, reason in _META_CONTENT:
        if pat.search(content):
            return FastPrecheckDecision(action="ALLOW", reasoning=f"meta-content: {reason}")

    stripped = content.strip()
    if stripped and len(stripped) <= 60 and not _HAS_SHELL_SYNTAX.search(stripped):
        if _CONVERSATIONAL_ONLY.match(stripped):
            return FastPrecheckDecision(
                action="ALLOW", reasoning="meta-content: conversational-ack"
            )

    # No actionable signals (shell ops, file paths, URLs, DB commands) → content is
    # conversational or explanatory. ALLOW without CLI escalation to avoid the model
    # returning non-JSON "I cannot evaluate this" responses.
    # Destructive patterns have already run above, so this path is safe.
    if stripped and not _ACTIONABLE_SIGNAL.search(stripped):
        return FastPrecheckDecision(
            action="ALLOW", reasoning="meta-content: no-actionable-signal"
        )

    if snap.has_intent_file and snap.intent_text:
        intent_lower = snap.intent_text.lower()
        if "no force-push" in intent_lower and "git push" in content.lower() and "--force" in content.lower():
            return FastPrecheckDecision(
                action="INTERVENE",
                reasoning="intent forbids force-push",
                matched_pattern="intent:no-force-push",
            )
        if "no plaintext" in intent_lower or "session-token storage in plaintext" in intent_lower:
            if re.search(r"(token|secret|api_key)\s*=\s*['\"]\w", content, re.IGNORECASE):
                return FastPrecheckDecision(
                    action="INTERVENE",
                    reasoning="intent forbids plaintext token storage",
                    matched_pattern="intent:no-plaintext-tokens",
                )

    return None


def _safe_read(fp: Path, max_bytes: int = 64 * 1024) -> str:
    try:
        return fp.read_text(encoding="utf-8", errors="replace")[:max_bytes]
    except OSError:
        return ""


# ── FR-OG-7: .sm-context.yaml loader (Phase 5) ─────────────────────────
#
# When SM governs a project that ships an `.sm-context.yaml`, that file
# declares which artifacts SM should pay attention to (spotlight) and
# the path to a structured maturity artifact (e.g. certPortal's
# maturity.yaml). The loader is intentionally tolerant: missing files
# return None so callers can dormant-skip the FR-OG-7 codepath without
# an exception path.


# Module-level guard: emit `og7_unconfigured` exactly once per project_root
# per Python process. Tracks resolved string paths.
_OG7_UNCONFIGURED_EMITTED: set[str] = set()


def _emit_og7_unconfigured(bus: object, session_id: str, project_root: Path, expected_path: Path) -> None:
    """Loud-degrade signal: SM dashboard renders a banner when FR-OG-7 is
    dormant because `.sm-context.yaml` is missing. Idempotent per
    project_root for the lifetime of this process.
    """
    key = str(Path(project_root).resolve())
    if key in _OG7_UNCONFIGURED_EMITTED:
        return
    _OG7_UNCONFIGURED_EMITTED.add(key)
    if bus is None:
        return
    try:
        from stream_manager import message_bus as _msg_bus

        bus.publish(  # type: ignore[attr-defined]
            _msg_bus.Message.new(
                session_id=session_id or "sm-system",
                type="og7_unconfigured",
                direction="internal",
                content="FR-OG-7 inactive: .sm-context.yaml missing",
                metadata={
                    "project_root": str(project_root),
                    "expected_path": str(expected_path),
                },
            )
        )
    except Exception:
        # Never let observability emit break the load() contract.
        pass


def load_sm_context(
    project_root: Path,
    bus: object | None = None,
    session_id: str = "sm-system",
) -> dict[str, object] | None:
    """Load `.sm-context.yaml` from project root. Returns None if absent
    or unparseable. Never raises.

    When ``bus`` is supplied and the file is absent, emits a one-shot
    ``og7_unconfigured`` bus event per ``project_root`` so the dashboard
    can surface a loud-degrade banner instead of silently no-op'ing.
    """
    path = Path(project_root) / ".sm-context.yaml"
    if not path.exists():
        _emit_og7_unconfigured(bus, session_id, Path(project_root), path)
        return None
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def get_maturity_artifact_path(
    sm_context: dict[str, object], project_root: Path
) -> Path | None:
    """Extract `maturity.artifact_path` from `.sm-context.yaml` config and
    resolve it relative to `project_root`. Returns None when the field is
    missing, the value is malformed, or the resolved path does not exist.
    """
    maturity = sm_context.get("maturity")
    if not isinstance(maturity, dict):
        return None
    rel = maturity.get("artifact_path")
    if not isinstance(rel, str) or not rel:
        return None
    p = Path(project_root) / rel
    return p if p.exists() else None
