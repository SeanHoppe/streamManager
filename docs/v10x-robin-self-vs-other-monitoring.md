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
| M6 | Parent PID chain inspection (`Get-Process`/`psutil`) | LOW | HIGH — Windows reparents orphaned children; certPortal chain uses `bash → bash → claude.exe` (see `feedback_monitoring_live_sessions.md` process tree); not reliable for self-vs-other | inferred from process tree in memory doc |
| M7 | `$TEMP/claude/<cwd-slug>/<sessionId>/tasks/<token>.output` presence | MED (existence proves the session is or was alive) | does NOT identify which session is self — only proves the sessionId is live | live: `…Temp/claude/…quirky-northcutt-464565/265471e8-…/tasks/` directory exists |
| M8 | `CLAUDE_SESSION_ID` / `CLAUDE_PROJECT_DIR` env vars exported by the harness | **NOT AVAILABLE** | N/A | grep across worktree returns zero references; the harness does **not** export these |
| M9 | Path containing `streamManager` in JSONL location | MED | MED — distinguishes "SM project" from "governed project" (the existing `feedback_no_self_monitor.md` guard) but cannot pick the right SM session among multiple | `feedback_no_self_monitor.md` §"How to apply" |

**Headline:** Robin has TWO independent HIGH-reliability handles (M1 inside a hook context, M2 from outside it) plus ONE HIGH guard (M3). M5 alone is insufficient — two interactive sessions can share a cwd. M8 is a documentation-trap: the env vars do not exist.

## 3. Recommended self-detection algorithm

Robin runs **outside** any PreToolUse hook (it is a Task subagent, not a hook process). Use M2 + M3 in tandem; never trust a single handle.

```python
def resolve_self_session_ids() -> set[str]:
    """Return the set of session IDs that Robin must treat as 'self'."""
    self_ids: set[str] = set()

    # (A) Explicit operator-set guard (existing convention).
    sm_self = (os.environ.get("BRIDGE_SM_SELF_SESSION_ID") or "").strip()
    if sm_self:
        self_ids.add(sm_self)

    # (B) Scan ~/.claude/sessions/*.json. Every entry whose `cwd` is
    #     under the streamManager tree AND whose pid is still alive
    #     is a *candidate* self-or-sibling. Treat ALL of them as self
    #     (conservative — never tail any SM-cwd interactive session).
    sessions_dir = Path.home() / ".claude" / "sessions"
    for f in sessions_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        pid_in_file = int(data.get("pid", -1))
        cwd = (data.get("cwd") or "").lower().replace("\\", "/")
        if "streammanager" not in cwd:
            continue                          # not an SM session at all
        if not _pid_alive(pid_in_file):
            continue                          # stale session JSON
        if int(f.stem) != pid_in_file:
            continue                          # filename↔pid mismatch (skip)
        sid = data.get("sessionId")
        if sid:
            self_ids.add(sid)

    return self_ids

def is_self(session_id: str) -> bool:
    return session_id in resolve_self_session_ids()
```

Rationale: this is *conservative-bias* — Robin refuses anything rooted in the SM worktree tree even if it's a *sibling* SM session, because feedback_no_self_monitor.md applies to SM-as-a-class, not just one PID. Other-project sessions (certPortal, oversight, pycoreEdi) are unaffected.

## 4. Other-session monitoring protocol

1. **Targets are explicit, never inferred.** Main thread supplies Robin with a list of `(sessionId, logPath)` pairs to monitor — e.g. `[("9ed7b041-…", "oversight/logs/matt-2026-05-06.log")]`. Robin never auto-picks "most recent active" (banned by `feedback_no_self_monitor.md` §"When auto-picking…").
2. **Refusal gate.** For each target `sid`, call `is_self(sid)`; if true, abort with a FAIL row in the verdict report. Do not silently skip.
3. **Allowlist by project root.** A target's session JSON `cwd` MUST start with `C:/Users/SeanHoppe/VS/certPortal` or another non-SM governed root. Robin refuses any target whose `cwd` contains `streamManager` (matches `feedback_no_self_monitor.md` §"exclude any path under `~/.claude/projects/C--Users-SeanHoppe-VS-streamManager*`").
4. **Tailing follows the Monitor template** in `feedback_monitoring_live_sessions.md` §"Monitor command template" — log file + bg-task `.output` + `kill -0 $TARGET_PID` watcher. No new mechanism needed.
5. **DB writes still pass through `EpisodeLogger.record_decision`** — which already re-checks M3 (`rl/episode_logger.py:88-90`). Defence in depth: Robin's allowlist is layer 1, the logger is layer 2.
6. **Reading SM session prompts/transcripts is allowed** (per carve-out in `feedback_no_self_monitor.md:17`) *only* for processing-verification readouts; never as DB inserts.

## 5. Required hooks / settings changes

Current `.claude/settings.json` (`/.claude/settings.json:1-15`) wires `tools/hook_evaluate.py` on Bash PreToolUse but has no path-deny rule. Proposed **additive** changes (no FROZEN-list impact — settings.json is not on the surface freeze):

- **PreToolUse `Read` matcher** — new hook script `tools/hook_deny_self_jsonl.py` (to be authored P-future, not now) that exits 2 if `tool_input.file_path` resolves under `~/.claude/projects/C--Users-SeanHoppe-VS-streamManager*` AND the path's basename matches a sessionId in `resolve_self_session_ids()`. Read-only inspection of *prompts* (which live elsewhere) is unaffected.
- **PreToolUse `Bash` matcher (additive in hook_evaluate.py)** — extend `_content_from_payload` (`tools/hook_evaluate.py:38-53`) to flag commands matching `tail .*\.claude/projects/.*streamManager.*\.jsonl` and route to BLOCK band. Cheaper than a separate hook; reuses existing engine.
- **Settings-layer sqlite deny** — already implied by `robin.md:19` ("Direct sqlite3 mutation against either DB is denied at the settings layer"). Confirm/extend that deny to cover `sqlite3 rl_episodes.db` write modes; current settings.json does not show such a rule, so this may be missing or live in user-global settings. **Open question — see §6.**

None of the above are landed in this DRAFT. They are the proposed minimal surface for a follow-up PR.

## 6. Open questions (caveman)

- **Q1.** Settings.json deny rules for sqlite mutation — where? `.claude/settings.json:1-15` shows only the Bash PreToolUse hook. `robin.md:19` claims a settings-layer deny exists. Live? Stale doc?
- **Q2.** Multi-self in same worktree — sessions `32284.json` + `6048.json` both `cwd:funny-hofstadter-0e2f7a`, both `interactive`/`claude-desktop`. Algorithm §3 treats both as self. Operator OK with that, or want one designated "primary"?
- **Q3.** `entrypoint:sdk-cli` (PID 4228) — is that a soak worker, a CLI-pool worker, or something else? If soak-pool, the pool is launched FROM main thread; its sessionId is *not* self but IS in-family. Govern as other or as self?
- **Q4.** ~~`BRIDGE_SM_SELF_SESSION_ID` is operator-set, not auto-derived. Should the hook (`hook_evaluate.py:78`) auto-export it from the harness-supplied `payload["session_id"]` to subprocesses it spawns?~~ **DECIDED 2026-05-12 by operator: YES.** Auto-export from harness payload `session_id` into spawned subprocess env. Every Task subagent + Bash subprocess inherits a correct self-id for free. Tracked as GH issue (filed alongside this DRAFT PR). Implementation lands as a follow-up; this DRAFT does not modify `hook_evaluate.py`.
- **Q5.** Robin is `tools: Read, Glob, Grep, Bash, Write` (`.claude/agents/robin.md:4`) — does that need narrowing once §5 hooks land? E.g. drop `Bash` and force tailing via a dedicated MCP/script wrapper that enforces the allowlist in-band.
- **Q6.** No `CLAUDE_SESSION_ID` env var exists today (M8). Is that worth filing upstream as a feature request, or is M1 (hook payload) the canonical sanctioned channel?
- **Q7.** Carve-out scope creep risk — `feedback_no_self_monitor.md:17` (2026-05-07) lets the rl-test-orchestrator subagent read SM session prompts. Robin inherits that. Should DRAFT propose a written audit trail (e.g. Robin emits a `self-session-read` envelope per read) so the carve-out remains observable?

## 7. Falsifiable claims in this doc

- C-1: harness does NOT export `CLAUDE_SESSION_ID` — falsify by `grep -r CLAUDE_SESSION_ID ~/.claude` returning non-empty.
- C-2: PreToolUse hook receives `session_id` field — verified at `tools/hook_evaluate.py:4` and `tools/hook_evaluate.py:68`.
- C-3: every live PID writes `~/.claude/sessions/<pid>.json` with matching `pid` field — verified across 8 live samples (4000, 4016, 4228, 4356, 6048, 23312, 26580, 32284) on 2026-05-12.
- C-4: two concurrent interactive sessions can share a cwd — verified, PIDs 32284 + 6048 both on `funny-hofstadter-0e2f7a`. Means M5 alone is insufficient.
- C-5: `BRIDGE_SM_SELF_SESSION_ID` is enforced at DB-write layer — verified at `rl/episode_logger.py:88-90`.

## 8. Post-development verification test (binding)

When the follow-up PRs land (algorithm §3 + Q4 auto-export + hooks §5), every claim below MUST be a passing automated test. No claim retired by argument; only by green test.

Drop into `tests/test_self_other_session_detection.py` (new file, follow-up PR scope):

| T# | Asserts | Setup | Pass condition |
|---|---|---|---|
| **T-1** | M2 self-detection picks live SM-cwd session | Write tmp `~/.claude/sessions/<fake_pid>.json` with `pid=<live test pid>`, `cwd` containing `streamManager`, `sessionId="T1-SID"` | `resolve_self_session_ids()` returns set containing `"T1-SID"` |
| **T-2** | M2 ignores stale (dead-PID) self file | Same as T-1 but `pid` = a known-dead PID | `"T2-SID"` NOT in result |
| **T-3** | M2 ignores filename↔pid mismatch | Filename `99999.json` but inner `pid:88888` | `"T3-SID"` NOT in result |
| **T-4** | M2 ignores non-SM cwd | Session JSON with `cwd: C:/Users/SeanHoppe/vs/certPortal` | `"T4-SID"` NOT in result (other-project = allowed monitoring target) |
| **T-5** | M3 env-var guard | `BRIDGE_SM_SELF_SESSION_ID=T5-SID`, empty sessions dir | `is_self("T5-SID")` == True |
| **T-6** | Multi-self class-wide rule | Two live SM-cwd sessions present (PID-A, PID-B) | Both sessionIds in result |
| **T-7** | Refusal gate on monitor target | Robin-style `monitor(targets=[("T1-SID", "/tmp/x.log")])` invoked while T-1 setup live | Returns FAIL row (not silent skip) citing `T1-SID` |
| **T-8** | Allowlist refuses SM-cwd target by cwd-string alone | Target sessionId NOT in self set but its session JSON `cwd` contains `streamManager` | Robin returns FAIL row referencing cwd-based refusal |
| **T-9** | DB-write defense-in-depth still holds | Bypass §3 algorithm; call `EpisodeLogger.record_decision` directly with envelope whose `session_id` == `BRIDGE_SM_SELF_SESSION_ID` | `SelfMonitorRefusal` raised at `rl/episode_logger.py:88-90` |
| **T-10** | **Q4 auto-export inheritance** | Run a Bash tool call under PreToolUse hook with payload `session_id="T10-SID"`; the spawned subprocess prints `os.environ.get("BRIDGE_SM_SELF_SESSION_ID")` | Subprocess output == `"T10-SID"` |
| **T-11** | Q4 idempotent on already-set env | Hook fires with payload `session_id="T11-SID"` but env already has `BRIDGE_SM_SELF_SESSION_ID=T11-OVERRIDE` from operator | Operator value wins; subprocess sees `"T11-OVERRIDE"` (operator override must beat auto-export) |
| **T-12** | Live integration | Spawn a real `claude -p` subprocess from a hooked Bash invocation; child reads `BRIDGE_SM_SELF_SESSION_ID` from env | Matches parent's payload `session_id` (proves the auto-export crosses the subprocess boundary in the harness, not just inside Python) |

T-10 through T-12 are blocked on Q4 implementation. T-1 through T-9 are landable as soon as §3 algorithm is written.

**Test runner:** `pytest tests/test_self_other_session_detection.py -v`. Required to pass in CI before any §5 hook lands. Failures = PR blocked.
