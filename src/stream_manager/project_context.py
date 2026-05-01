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
