# v10.x DRAFT — Robin self-vs-other CLI session monitoring

**Status:** DRAFT proposal, no code change yet. Read-only investigation.
**Author note:** Caveman-terse. Operator review required before any landing.

## 1. Problem

streamManager governance runs many concurrent `claude` CLI subprocesses: the operator's interactive session (the "self" main thread), Task-spawned subagents, certPortal oversight chain (dave→jen→matt→oliver→jeanluc) via `claude -p`, `cli_soak.py` pool workers, and the v10 Robin test agent. Two memory rules pull in opposite directions: `feedback_no_self_monitor.md` (never govern self) vs. `feedback_monitoring_live_sessions.md` (do monitor live `claude -p` subprocesses). Robin needs a deterministic algorithm to reliably distinguish "self" (forbidden) from "other" (allowed) at PID / sessionId / filesystem-artifact level, so it can tail other-session JSONL/log files without ever ingesting self traffic into `rl_episodes.db`.

## 2. Self-identification mechanisms inventory

| # | Mechanism | Reliability | False-positive risk | Citation / evidence |
|---|---|---|---|---|
| M1 | PreToolUse hook payload `session_id` field on stdin JSON | **HIGH** | None — harness-supplied, authoritative for the executing process | `tools/hook_evaluate.py:4`, `tools/hook_evaluate.py:68` |
| M2 | `~/.claude/sessions/<pid>.json` self-file with matching `os.getpid()` | **HIGH** | LOW — file written by harness; one per live PID; cross-validate with `pid` field inside the JSON | live sample: `~/.claude/sessions/4000.json` content `{"pid":4000,"sessionId":"265471e8-…","cwd":"…quirky-northcutt-464565","kind":"interactive","entrypoint":"claude-desktop"}` |
| M3 | `BRIDGE_SM_SELF_SESSION_ID` env var (when set by operator) compared against envelope/session_id | **HIGH** when set; **N/A** when unset | LOW — exact-match guard; already enforced in code | `rl/episode_logger.py:88-90`, `rl/corpus_augment.py:74`, `tools/rl_test_helper/db_summary.py:46` |
| M4 | `entrypoint` field in `~/.claude/sessions/<pid>.json` (`claude-desktop` / `cli` / `sdk-cli`) + `kind` (`interactive` / `bg`) | MED (typing of session) | MED — distinguishes class of session, not specific identity; multiple `claude-desktop` interactives can coexist | live samples show `entrypoint` ∈ {`claude-desktop`, `cli`, `sdk-cli`} and `kind` ∈ {`interactive`, `bg`}; e.g. PID 4228 `entrypoint:sdk-cli`, PID 23312 `kind:bg` |
| M5 | `cwd` field in `~/.claude/sessions/<pid>.json` matches `Path.cwd()` of caller | MED | MED — two sessions can share a cwd (e.g. two `claude-desktop` instances in same worktree, see PID 32284 + 6048 both rooted at `funny-hofstadter-0e2f7a`) | live: two coexistent interactive sessions on `funny-hofstadter-0e2f7a` |
| M6 | _(dropped)_ Parent-PID chain inspection — removed from inventory per review L31. No live PID evidence captured; Windows reparenting + `bash → bash → claude.exe` indirection in certPortal chain make the handle structurally LOW reliability. If revived, add a captured process-tree sample as evidence. | — | — | — |
| M7 | `$TEMP/claude/<cwd-slug>/<sessionId>/tasks/<token>.output` presence | MED (existence proves the session is or was alive) | does NOT identify which session is self — only proves the sessionId is live | live: `…Temp/claude/…quirky-northcutt-464565/265471e8-…/tasks/` directory exists |
| M8 | `CLAUDE_SESSION_ID` / `CLAUDE_PROJECT_DIR` env vars exported by the harness | **NOT AVAILABLE** | N/A | grep across worktree returns zero references; the harness does **not** export these |
| M9 | Path matches a slug in `STREAM_MANAGER_PROJECT_SLUGS` (default `{"streamManager"}`, override via `BRIDGE_SM_PROJECT_SLUGS` env per `CLAUDE.md §"Session-source exception rule"` + `rl/episode_logger.py:45`) | MED | MED — distinguishes "SM project" from "governed project" (the existing `feedback_no_self_monitor.md` guard) but cannot pick the right SM session among multiple | `feedback_no_self_monitor.md` §"How to apply"; slug set authoritative via `rl/episode_logger.py:45` |

**Headline:** Robin has TWO independent HIGH-reliability handles (M1 inside a hook context, M2 from outside it) plus ONE HIGH guard (M3). M5 alone is insufficient — two interactive sessions can share a cwd. M8 is a documentation-trap: the env vars do not exist.

## 3. Recommended self-detection algorithm

Robin runs **outside** any PreToolUse hook (it is a Task subagent, not a hook process). Use M2 + M3 in tandem; never trust a single handle.

**Slug match (M9), not substring.** Algorithm matches project slug against `STREAM_MANAGER_PROJECT_SLUGS` (default `{"streamManager"}`, override via `BRIDGE_SM_PROJECT_SLUGS` env, per CLAUDE.md §"Session-source exception rule" and `rl/episode_logger.py:45`). Substring matching against `"streammanager"` is REJECTED: it breaks on worktree slug renames, lowercase variants, and accidental collisions.

**Entrypoint typing is observational, not load-bearing.** The algorithm decides on `cwd` + `pid-liveness` + `sessionId`. `entrypoint` ∈ {`claude-desktop`, `cli`, `sdk-cli`} (M4) is recorded for diagnostics only — all three classes get the same self/other classification based on cwd. This resolves the Q3 sdk-cli (PID 4228) ambiguity at the algorithm layer: if its `cwd` lives under an SM slug it is self; if not, it is a candidate monitoring target requiring an explicit `(sessionId, logPath)` entry from main thread (see §4).

```python
import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

_DEFAULT_SM_SLUGS = "streamManager"


def _sm_project_slugs() -> set[str]:
    """Authoritative SM-self slug set. Cross-ref CLAUDE.md §'Session-source exception rule'."""
    raw = os.environ.get("BRIDGE_SM_PROJECT_SLUGS", _DEFAULT_SM_SLUGS)
    return {s.strip() for s in raw.split(",") if s.strip()}


def _pid_alive(pid: int) -> bool:
    """Cross-platform liveness probe. Returns True iff `pid` is a running process.

    Windows: ``OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`` via ctypes; falls back
    to ``psutil.pid_exists`` if available. POSIX: ``os.kill(pid, 0)`` (signal 0 = probe).
    """
    if pid <= 0:
        return False
    try:
        import psutil  # type: ignore

        return psutil.pid_exists(pid)
    except ImportError:
        pass
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except (OSError, PermissionError):
        return False


def _cwd_matches_sm_slug(cwd: str, slugs: set[str]) -> bool:
    """True iff any segment of `cwd` equals a member of `slugs`.

    Uses path-segment equality (not substring) so 'streamManager-foo' does NOT match
    'streamManager'. Case-insensitive on Windows by lowercasing both sides.
    """
    if not cwd:
        return False
    parts = {p.lower() for p in cwd.replace("\\", "/").split("/") if p}
    return any(s.lower() in parts for s in slugs)


def resolve_self_session_ids() -> set[str]:
    """Return the set of session IDs that Robin must treat as 'self'.

    Precedence (matches §8 T-11): the operator-set ``BRIDGE_SM_SELF_SESSION_ID``
    value is added FIRST. Auto-discovered M2 IDs are added via set-union; the
    operator value never gets overwritten or removed by discovery. Order of insert
    is irrelevant for set membership, but the set-union (not setdefault dict) is
    the precedence carrier — auto-export cannot demote an operator-set ID.
    """
    self_ids: set[str] = set()

    # (A) Explicit operator-set guard (existing convention, layer-1 precedence).
    sm_self = (os.environ.get("BRIDGE_SM_SELF_SESSION_ID") or "").strip()
    if sm_self:
        self_ids.add(sm_self)

    # (B) Scan ~/.claude/sessions/*.json (M2). Every entry whose `cwd` matches
    #     an SM slug AND whose pid is still alive is a candidate self-or-sibling.
    #     Treat ALL of them as self (conservative — never tail any SM-cwd session).
    sessions_dir = Path.home() / ".claude" / "sessions"
    slugs = _sm_project_slugs()
    for f in sessions_dir.glob("*.json"):
        try:
            stem_pid = int(f.stem)
        except ValueError:
            log.debug("skip non-numeric session filename: %s", f.name)
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("skip unreadable session file %s: %s", f.name, exc)
            continue
        try:
            pid_in_file = int(data.get("pid", -1))
        except (TypeError, ValueError):
            log.warning("skip session file %s: pid field non-int", f.name)
            continue
        cwd = (data.get("cwd") or "")
        if not _cwd_matches_sm_slug(cwd, slugs):
            continue                                  # not an SM session at all
        if not _pid_alive(pid_in_file):
            continue                                  # stale session JSON
        if stem_pid != pid_in_file:
            continue                                  # filename↔pid mismatch (skip)
        sid = data.get("sessionId")
        if not sid:
            log.warning(
                "session file %s has SM cwd + live pid but empty sessionId; skipping",
                f.name,
            )
            continue
        self_ids.add(sid)

    return self_ids


def is_self(session_id: str) -> bool:
    return session_id in resolve_self_session_ids()
```

Rationale: this is *conservative-bias* — Robin refuses anything rooted under an SM slug even if it's a *sibling* SM session, because `feedback_no_self_monitor.md` applies to SM-as-a-class, not just one PID. Other-project sessions (certPortal, oversight, pycoreEdi) are unaffected.

## 3a. Decided open questions (closed, moved out of §6)

- **D-Q4** — auto-export `BRIDGE_SM_SELF_SESSION_ID` from harness payload `session_id` into spawned subprocess env. **DECIDED 2026-05-12 by operator: YES.** Every Task subagent + Bash subprocess inherits a correct self-id for free. Tracked as GH issue (filed alongside this DRAFT PR). Implementation lands as a follow-up; this DRAFT does not modify `hook_evaluate.py`. Implementation MUST use `setdefault`-style insertion (skip-if-already-set) so an operator-provided value beats the auto-export (cross-ref §8 T-11; §3 algorithm `resolve_self_session_ids` precedence comment).

## 4. Other-session monitoring protocol

1. **Targets are explicit, never inferred.** Main thread supplies Robin with a list of `(sessionId, logPath)` pairs to monitor — e.g. `[("9ed7b041-…", "oversight/logs/matt-2026-05-06.log")]`. Robin never auto-picks "most recent active" (banned by `feedback_no_self_monitor.md` §"When auto-picking…").
2. **Refusal gate.** For each target `sid`, call `is_self(sid)`; if true, abort with a FAIL row in the verdict report. Do not silently skip.
3. **Allowlist by project root.** A target's session JSON `cwd` MUST start with `C:/Users/SeanHoppe/VS/certPortal` or another non-SM governed root. Robin refuses any target whose `cwd` matches an SM slug (per `_cwd_matches_sm_slug` in §3, against `STREAM_MANAGER_PROJECT_SLUGS`).
4. **Tailing follows the Monitor template** in `feedback_monitoring_live_sessions.md` §"Monitor command template" — log file + bg-task `.output` + `kill -0 $TARGET_PID` watcher. No new mechanism needed.
5. **DB writes still pass through `EpisodeLogger.record_decision`** — which already re-checks M3 (`rl/episode_logger.py:88-90`). Defence in depth: Robin's allowlist is layer 1, the logger is layer 2.
6. **Reading SM session prompts/transcripts is allowed** (per carve-out in `feedback_no_self_monitor.md:17`) *only* for processing-verification readouts; never as DB inserts.

### 4a. `monitor()` interface contract

Cited by §8 T-7/T-8. Spec is binding — implementation in follow-up PR.

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

@dataclass(frozen=True)
class MonitorTarget:
    session_id: str        # the candidate other-session sessionId
    log_path: Path         # absolute path to JSONL/log file Robin should tail

@dataclass(frozen=True)
class MonitorRow:
    session_id: str
    status: Literal["PASS", "FAIL"]
    reason: str            # free-form; for FAIL rows MUST cite the refusal layer:
                           # "self-set-hit" (§3 algorithm) or "cwd-slug-hit" (§4 #3)

def monitor(targets: Iterable[MonitorTarget]) -> list[MonitorRow]:
    """Apply the §4 refusal gate + allowlist to each target, in order.

    For each target:
      1. If is_self(target.session_id) -> emit MonitorRow(status="FAIL",
         reason="self-set-hit: <sid>") and continue. Do NOT tail.
      2. Resolve the target's session-JSON cwd (~/.claude/sessions/*.json with
         matching sessionId). If cwd matches an SM slug per
         _cwd_matches_sm_slug, emit MonitorRow(status="FAIL",
         reason="cwd-slug-hit: <cwd>") and continue.
      3. Otherwise, begin tail of target.log_path per the Monitor template
         and emit MonitorRow(status="PASS", reason="tailing: <log_path>").

    Returns one row per input target, preserving input order.
    """
```

The signature + invariants above are what T-7/T-8 assert against. Any deviation requires a doc edit, not a test-only change.

## 5. Required hooks / settings changes

Current `.claude/settings.json:1-25` wires `tools/hook_evaluate.py` on Bash PreToolUse and carries two `permissions.deny` rules covering `sqlite3 *rl_episodes.db*` and `sqlite3 *rl_shadow.db*` (verified at `.claude/settings.json:3-6`). settings.json is **not** in the ADR-18 Rule 1 FROZEN-module table (`docs/adr/ADR-18-mvp-surface-freeze.md` §"Rule 1" L59-72 — settings.json absent from row list), so additive changes here do not invoke the surface-freeze gate. Proposed additive changes:

- **PreToolUse `Read` matcher** — new hook script `tools/hook_deny_self_jsonl.py` (to be authored P-future, not now) that exits 2 if `tool_input.file_path` resolves under the harness JSONL path schema `~/.claude/projects/<slug>/<sessionId>.jsonl` (schema cited at `src/stream_manager/session_watcher.py:693` and `src/stream_manager/transcript_loader.py:3`) AND `<slug>` matches `STREAM_MANAGER_PROJECT_SLUGS` AND the path's `<sessionId>` stem matches a sessionId in `resolve_self_session_ids()`. Read-only inspection of *prompts* (which live elsewhere) is unaffected.
- **PreToolUse `Bash` matcher (additive in hook_evaluate.py)** — extend `_content_from_payload` (`tools/hook_evaluate.py:38-53`) to flag commands matching the same JSONL path schema (per `~/.claude/projects/<slug>/<sessionId>.jsonl` shape, `<slug>` ∈ `STREAM_MANAGER_PROJECT_SLUGS`) and route to BLOCK band. Cheaper than a separate hook; reuses existing engine.
- **Settings-layer sqlite deny — VERIFIED present.** `.claude/settings.json:3-6` carries:
  ```json
  "deny": [
    "Bash(sqlite3 *rl_episodes.db*)",
    "Bash(sqlite3 *rl_shadow.db*)"
  ]
  ```
  Matches `robin.md:19` ("Direct sqlite3 mutation against either DB is denied at the settings layer"). No follow-up needed. (Previously flagged as "may be missing or live in user-global settings" — closed by direct inspection 2026-05-19.)

None of the Read/Bash matcher additions above are landed in this DRAFT. They are the proposed minimal surface for a follow-up PR.

## 6. Open questions (caveman)

Decided questions live in §3a. Only undecided items remain here.

- **Q1 — RESOLVED.** Settings.json sqlite deny — verified live at `.claude/settings.json:3-6` (project-level, not user-global). Was OPEN; closed in this DRAFT, see §5 bullet 3.
- **Q2.** Multi-self in same worktree — sessions `32284.json` + `6048.json` both `cwd:funny-hofstadter-0e2f7a`, both `interactive`/`claude-desktop`. Algorithm §3 treats both as self. Operator OK with that, or want one designated "primary"?
- **Q3.** `entrypoint:sdk-cli` (PID 4228) — is that a soak worker, a CLI-pool worker, or something else? **Algorithm-correctness scope:** §3 already handles it via cwd (entrypoint is observational only, see §3 ¶"Entrypoint typing is observational"). **Operator-classification scope (still open):** for diagnostic clarity in monitor verdict reports, should sdk-cli rows be tagged as `in-family` vs `other` so the operator sees provenance at a glance? Non-blocking for §3 ship; cosmetic.
- **Q5.** Robin frontmatter at `.claude/agents/robin.md:4` declares `tools: Read, Glob, Grep, Bash, Write`. Description says "Read-only against governance + DBs" but `Write` is granted. Two reconciliations possible: (a) narrow tools to `Read, Glob, Grep, Bash` (drop `Write`) — matches read-only claim; (b) keep `Write` and amend description to "Read-only against governance + DBs; may write verdict/report artefacts under `reports/` and prompt-mint files under `docs/prompts/`" — matches actual robin usage (writes ship-gate reports). Operator picks. Plus the §5-overlap question: once hooks land, does `Bash` need narrowing or replacement with an in-band wrapper that enforces the allowlist?
- **Q6.** No `CLAUDE_SESSION_ID` env var exists today (M8). Is that worth filing upstream as a feature request, or is M1 (hook payload) the canonical sanctioned channel?
- **Q7.** Carve-out scope creep risk — `feedback_no_self_monitor.md:17` (2026-05-07) lets the rl-test-orchestrator subagent read SM session prompts. Robin inherits that. Should DRAFT propose a written audit trail (e.g. Robin emits a `self-session-read` envelope per read) so the carve-out remains observable?

**Ship-blockers for un-DRAFT:** Q2 (operator preference on multi-self primary) + Q5 (narrow tools or amend description). Q3/Q6/Q7 are non-blocking for §3 + §4 correctness; can land DRAFT as-is and resolve in follow-up.

## 7. Falsifiable claims in this doc

- **C-1: harness does NOT export `CLAUDE_SESSION_ID`.** Falsify by either (a) running `Get-ChildItem env:CLAUDE_SESSION_ID` (PowerShell) or `printenv CLAUDE_SESSION_ID` (POSIX) at hook fire-time inside a live `claude-desktop` / `claude -p` subprocess and observing a non-empty value, OR (b) `Grep` (pattern: `CLAUDE_SESSION_ID`) against harness-source (`tools/hook_evaluate.py`, any `setenv`/`os.environ[...] = ` call in repo) returning a setter (not just a reader). Filesystem `grep` of `~/.claude` does NOT falsify the claim — env vars live in process memory, not on disk. The prior version of C-1 (filesystem grep) was a wrong falsifier (per review L110); replaced by the runtime/source-setter pair above.
- C-2: PreToolUse hook receives `session_id` field — verified at `tools/hook_evaluate.py:4` and `tools/hook_evaluate.py:68`.
- C-3: every live PID writes `~/.claude/sessions/<pid>.json` with matching `pid` field — verified across 8 live samples (4000, 4016, 4228, 4356, 6048, 23312, 26580, 32284) on 2026-05-12.
- C-4: two concurrent interactive sessions can share a cwd — verified, PIDs 32284 + 6048 both on `funny-hofstadter-0e2f7a`. Means M5 alone is insufficient.
- C-5: `BRIDGE_SM_SELF_SESSION_ID` is enforced at DB-write layer — verified at `rl/episode_logger.py:88-90`.
- C-6: JSONL path schema for governed sessions is `~/.claude/projects/<slug>/<sessionId>.jsonl` — verified at `src/stream_manager/session_watcher.py:693` and `src/stream_manager/transcript_loader.py:3`.
- C-7: settings.json is NOT on the ADR-18 surface freeze — verified by reading `docs/adr/ADR-18-mvp-surface-freeze.md` §"Rule 1" FROZEN-module table (L59-72) and observing absence of any `.claude/settings.json` row.

## 8. Post-development verification test (binding)

When the follow-up PRs land (algorithm §3 + Q4 auto-export + hooks §5), every claim below MUST be a passing automated test. No claim retired by argument; only by green test.

Drop into `tests/test_self_other_session_detection.py` (new file, follow-up PR scope):

| T# | Asserts | Setup | Pass condition |
|---|---|---|---|
| **T-1** | M2 self-detection picks live SM-cwd session | Write tmp `~/.claude/sessions/<fake_pid>.json` with `pid=<live test pid>`, `cwd` containing an SM-slug segment, `sessionId="T1-SID"` | `resolve_self_session_ids()` returns set containing `"T1-SID"` |
| **T-2** | M2 ignores stale (dead-PID) self file | Same as T-1 but `pid` = a known-dead PID | `"T2-SID"` NOT in result |
| **T-3** | M2 ignores filename↔pid mismatch | Filename `99999.json` but inner `pid:88888` | `"T3-SID"` NOT in result |
| **T-4** | M2 ignores non-SM cwd | Session JSON with `cwd: C:/Users/SeanHoppe/vs/certPortal` (no SM-slug segment) | `"T4-SID"` NOT in result (other-project = allowed monitoring target) |
| **T-5** | M3 env-var guard | `BRIDGE_SM_SELF_SESSION_ID=T5-SID`, empty sessions dir | `is_self("T5-SID")` == True |
| **T-6** | Multi-self class-wide rule | Two live SM-cwd sessions present (PID-A, PID-B) | Both sessionIds in result |
| **T-7** | Refusal gate on monitor target | `monitor(targets=[MonitorTarget("T1-SID", Path("/tmp/x.log"))])` invoked while T-1 setup live | Returns `[MonitorRow(session_id="T1-SID", status="FAIL", reason="self-set-hit: T1-SID")]` (per §4a contract) |
| **T-8** | Allowlist refuses SM-cwd target by cwd-slug-hit | Target sessionId NOT in self set but its session JSON `cwd` contains an SM-slug segment | Returns `MonitorRow(status="FAIL", reason="cwd-slug-hit: …")` per §4a |
| **T-9** | DB-write defense-in-depth still holds | Bypass §3 algorithm; call `EpisodeLogger.record_decision` directly with envelope whose `session_id` == `BRIDGE_SM_SELF_SESSION_ID` | `SelfMonitorRefusal` raised at `rl/episode_logger.py:88-90` |
| **T-10** | **D-Q4 auto-export inheritance** | Run a Bash tool call under PreToolUse hook with payload `session_id="T10-SID"`; the spawned subprocess prints `os.environ.get("BRIDGE_SM_SELF_SESSION_ID")` | Subprocess output == `"T10-SID"` |
| **T-11** | D-Q4 idempotent on already-set env (operator override beats auto-export) | Hook fires with payload `session_id="T11-SID"` but env already has `BRIDGE_SM_SELF_SESSION_ID=T11-OVERRIDE` from operator | Operator value wins; subprocess sees `"T11-OVERRIDE"`. Cross-ref §3 algorithm `resolve_self_session_ids` precedence comment + §3a impl note (`setdefault` semantics in auto-export). |
| **T-12** | Live integration | Spawn a real `claude -p` subprocess from a hooked Bash invocation; child reads `BRIDGE_SM_SELF_SESSION_ID` from env | Matches parent's payload `session_id` (proves the auto-export crosses the subprocess boundary in the harness, not just inside Python) |

T-1 through T-9 are landable as soon as §3 algorithm is written. T-10 through T-12 are blocked on **D-Q4 implementation** (the decision itself landed 2026-05-12, see §3a; only the code change is pending follow-up PR — not the question).

**Test runner:** `pytest tests/test_self_other_session_detection.py -v`. Required to pass in CI before any §5 hook lands. Failures = PR blocked.
