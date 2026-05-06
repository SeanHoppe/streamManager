# Learn Mode

Learn Mode (shipped v1.3) lets SM observe your Desktop ↔ user dialogue, detect recurring preferences, and surface them as advisory bias on future governance decisions.

---

## How it starts

Learn Mode starts automatically with uvicorn. No separate command.

```powershell
uvicorn dashboard.server:app --port 8765 --reload
# categorizer worker starts on the same server process
```

The categorizer runs on a background thread and is off the governance verdict hot path — it never adds latency to L0–L4 evaluation.

---

## What it observes

SM tails the Claude Desktop JSONL transcript and extracts:

- **Desktop orchestrator turns** (`desktop_prompt`) — what the orchestrator asked
- **User reply turns** (`user_reply`) — how you responded

SM's own HITL prompts and decisions are intentionally excluded — SM never learns from its own governance output (no feedback loop into the decision engine).

---

## What it does with observations

1. Pairs each `desktop_prompt` with its `user_reply` (via `parentUuid` chain)
2. Runs a Sonnet categorizer out-of-band (`claude -p`, CLI subprocess, not SDK)
3. Writes a categorized row to `learn_patterns` table in `gov.db`
4. At verdict time, the verdict path reads top-N matching patterns and attaches them as advisory context

The bias is **read-only advisory** at decision time. It never overrides the verdict engine. It never bypasses the HITL gate.

---

## How you see it working

On the dashboard decisions feed, a silent audit row appears when a pattern was applied to a verdict. No toast. No undo card. Look for the pattern-badge on the decision row.

When HITL fires, the prompt is pre-filled with the categorizer's suggested action. You still confirm — Learn Mode never auto-resolves (as of v1.3).

---

## Pattern decay

Patterns weaken over time if not reinforced:

| Interval without reinforcement | Effect |
|---|---|
| 30 days | Step-demote one rung on L1–L4 ladder |
| 60 days | Step-demote again |
| 90 days | Step-demote again |
| 120 days | Step-demote again (pattern approaches dormant) |

**Reinforcement reset** — any same-direction observation resets the decay clock.

**Contradiction snap-demote** — an opposite-direction observation immediately demotes the pattern one rung, regardless of decay window position.

---

## Safety hard limits

Learn Mode cannot auto-allow any of the following, regardless of pattern strength, frequency, or operator history:

1. Destructive shell verbs — `rm -rf /`, `rm -rf ~`, `dd if=… of=/dev/…`, `DROP DATABASE/TABLE`
2. Force-push to protected branches — `git push --force` (or `-f`) targeting `main`/`master`/`production`
3. Code-injection patterns — `eval(`, `exec(` in untrusted message bodies
4. Credential exfiltration — content matching obvious token / API-key shapes

The categorizer short-circuits on any of the above and emits no advisory bias. The verdict path remains the single authoritative gate.

---

## Scope limits (v1.3)

| Not in scope | Deferred to |
|---|---|
| Auto-resolve (silent HITL skip at high confidence) | v1.4+ |
| Multi-user pattern disambiguation | Later cycle |
| Toast / undo affordances | Later cycle |
| Cross-session pattern propagation | v1.4+ (HITL-gated) |
| Learning from SM's own HITL prompts | Never (by design) |

---

## Design reference

Full spec: [`docs/learn-mode-design.md`](../docs/learn-mode-design.md)

Key components:

| Component | Path | Role |
|---|---|---|
| Tail extension | `src/stream_manager/jsonl_tail.py` | Emits `desktop_prompt` / `user_reply` pairs |
| Categorizer worker | `src/stream_manager/learn_categorizer.py` | Runs Sonnet via `claude -p`; writes `learn_patterns` |
| Decay scheduler | `src/stream_manager/decay.py` | Applies 30/60/90/120-day ladder |
| Bias reader | inside `governance.py` verdict path | Reads top-N patterns at decide time |
