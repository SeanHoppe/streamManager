# UC-01 — External session monitoring

**Status:** Lessons-learned capture (2026-05-06)
**Source incident:** certPortal oversight session, Matt QA agent, JOB-5593 auth.prod_ready 40→60
**Drives backlog items:** v1.9 items 4–6 (external session registry, Learn Mode JSONL expansion, bg task token bus events)

---

## What happened

certPortal oversight runs a multi-agent pipeline as isolated `claude -p` subprocesses:
Dave (impl) → Jen (review) → Jason (FLAG audit) → Matt (QA) → Oliver (AAR) → Michael (escalation).

On 2026-05-06, Matt's QA subprocess had been running for >1h17m with no visible output. The operator observed session state `"Standing by for b1bu59d1l"` but had no SM visibility into what that meant or whether the job was healthy.

**Manual triage required:**
1. `ls ~/.claude/sessions/` — discover active PIDs (4 files; had to cross-check which was certPortal)
2. `ps -p <pid>` — validate `status:"busy"` was stale on the originally-suspect PID (18600)
3. Grep session JSONLs for `b1bu59d1l` — find token was a background Bash task ID
4. Locate task output file in `$TEMP/claude/<cwd-slug>/<sessionId>/tasks/<token>.output` — found 0 bytes
5. Realise 0 bytes ≠ hung — actual output routes via `tee` to `oversight/logs/matt-2026-05-06.log`
6. Tail log — confirmed Matt alive, running JOB-5593, 8 prior jobs all PASS
7. Arm Monitor manually with compound shell script covering PID exit + log grep + task file read

**Total manual steps to answer "is Matt healthy?": 7.** SM had zero visibility.

---

## Data sources that already exist (no new infra needed to read)

| Source | Location | Contains |
|--------|----------|----------|
| Session registry | `~/.claude/sessions/<pid>.json` | pid, sessionId, cwd, status, entrypoint, version |
| Session JSONL | `~/.claude/projects/<cwd-slug>/<sessionId>.jsonl` | Full turn history, bg task token registrations, assistant output |
| Agent log | `<cwd>/oversight/logs/<agent>-<date>.log` | Timestamped job verdicts, retries, chain events |
| Task output file | `$TEMP/claude/<cwd-slug>/<sessionId>/tasks/<token>.output` | Pipeline tail output (populated on process exit only) |
| Process tree | OS process list | PID liveness, parent chain, entrypoint args |

---

## What SM currently cannot do

| Gap | Impact |
|-----|--------|
| No external session discovery | SM doesn't know certPortal oversight PIDs exist until manually told |
| Learn Mode ingests Desktop JSONL only | Rich oversight agent dialogue (QA verdicts, PASS/FAIL reasoning, retry patterns) never reaches SM's learning pipeline |
| No bg task token registry | SM has no record of b1bu59d1l-style tokens — no dashboard visibility, no timeout alerting |
| No cross-session health signal | SM cannot answer "is the certPortal oversight pipeline healthy right now?" |

---

## Desired SM behaviour (acceptance criteria)

### AC-1: Session registry
- SM discovers `~/.claude/sessions/*.json` on startup and on file-change (inotify/poll)
- Registers external sessions with: pid, sessionId, cwd, entrypoint, is_alive (ps -p)
- Exposes via bus envelope `external_session_registered` / `external_session_exited`
- Dashboard shows active external sessions with liveness indicator

### AC-2: Learn Mode JSONL ingestion from external sessions
- Learn Mode accepts a configurable list of JSONL paths (or cwd globs) beyond the Desktop session
- certPortal oversight JSONLs are ingested as a separate named source (`certportal-oversight`)
- Categoriser tags oversight-agent turns with source label so SM learning is not polluted with governance-of-governance patterns
- Opt-in per source; default off

### AC-3: Background task token tracking
- When SM or an external session registers a bg task token, SM records: token ID, output file path, originating session, start time
- SM polls output file size; emits `bg_task_output_ready` bus event when size changes from 0
- Dashboard shows pending bg tokens with age, path, and file size
- Operator can trigger a Monitor on any registered token from the dashboard

---

## Process tree for certPortal oversight (reference)

```
bash -c "eval '... && bash scripts/matt-run.sh 2>&1 | tail -30'"  ← bg task shell (b1bu59d1l owner)
  └─ bash scripts/matt-run.sh
       └─ bash scripts/claude-run.sh --agent matt --step inbox-run --log oversight/logs/matt-<date>.log
            ├─ claude.exe --model claude-opus-4-7 --effort medium -p "You are Matt..."
            └─ tee -a oversight/logs/matt-<date>.log
```

**Key invariant:** task output file (`b1bu59d1l.output`) is populated only when the entire chain exits (`tail -30` of final stdout). During execution, live output goes exclusively to the tee log. 0-byte task file does NOT indicate a hung process.

---

## Monitor pattern derived from this incident

```bash
LOG="<cwd>/oversight/logs/<agent>-<date>.log"
OUT="$TEMP/claude/<cwd-slug>/<sessionId>/tasks/<token>.output"
TARGET_PID=<pid>

tail -n 0 -f "$LOG" | grep -E --line-buffered \
  "PASS|FAIL|HALT|panic|[Ee]rror|<JOB-ID>|Chaining|Found.*pending|Retry" &
GREP_PID=$!

while kill -0 $TARGET_PID 2>/dev/null; do sleep 10; done
echo "PID $TARGET_PID dead"
kill $GREP_PID 2>/dev/null
sleep 2
echo "=== task output ===" && cat "$OUT" 2>/dev/null || echo "(empty)"
echo "=== log tail ===" && tail -5 "$LOG"
```

grep alternation must cover ALL terminal states — silence is indistinguishable from "still running."

---

## Stale process accumulation (side finding)

~15 `tail -F` processes from 2026-05-04 still running on 2026-05-06. These are orphaned watchers from old oversight sessions whose parent process died without sending SIGTERM to child watchers. No impact on correctness but wastes file descriptors. Periodic cleanup or explicit trap/kill in `claude-run.sh` teardown warranted.
