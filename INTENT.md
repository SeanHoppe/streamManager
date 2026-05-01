# StreamManager — Intent

> This file is intentionally short. It exists so that StreamManager's own
> governance engine can dogfood project-context loading on its own repo.
> If the file is missing, governance falls back to README/CONTRIBUTING/manifests.

## What this project is

A governance and adaptive-learning bridge between Claude Desktop sub-agent
orchestration and a Claude CLI executor. SM is the **project manager layer**:
it reads the full set of `*.md` files from the governed project, discovers the
Desktop's sub-agent topology (Prompt Constructor, Developer, Code Reviewer,
Tester, and others) via hybrid metadata + pattern inference, and governs each
agent independently per its role scope.

SM enforces two things beyond raw safety: **plan alignment** (does this
orchestration prompt move toward stated requirements?) and **cadence**
(is the session making forward progress?). Pipeline ordering remains with
Desktop orchestration. SM governs messages, not transitions.

## Safety priorities (highest first)

1. **No silent forwarding of destructive shell** — `rm -rf /`, `rm -rf ~`,
   `dd if=… of=/dev/…`, `DROP DATABASE/TABLE` must always block, regardless
   of mode.
2. **No force-push to protected branches** — `git push --force` (or `-f`)
   targeting `main` / `master` / `production` is an INTERVENE.
3. **No code-injection patterns** — `eval(`, `exec(` in untrusted message
   bodies are an INTERVENE.
4. **No credential exfiltration** — content matching obvious token / API-key
   shapes is BLOCK.
5. **API timeouts must never block forwarding.** A governance API failure
   degrades to OBSERVE; it does not stall the bridge.

## Out of scope (do not auto-allow these without scrutiny)

- Network-side modifications to `transport/` (GPL-isolated; not present here
  but stated for posterity).
- Session-token storage in plaintext anywhere on disk.
- Any operation that exfiltrates the SQLite bus DB outside the local host.

## Hot zones

- `src/stream_manager/governance.py` — the decision engine. Changes here
  affect every message.
- `src/stream_manager/message_bus.py` — the WAL bus. Schema changes need
  a migration story.
- `src/stream_manager/project_context.py` — defines what "intent" means
  for governed repos.

## Sub-agent governance principles

- Each sub-agent is governed **independently** by its role profile.
- SM MUST NOT gate one agent based on another's completion state.
- Reviewer agents: SUGGEST scope only; direct CLI execution from a reviewer → BLOCK.
- Developer agents near protected files (auth, bus schema, governance core): GUIDE → INTERVENE.
- Unknown agents: treated as `unknown` role under standard engine rules until pattern inference resolves their profile.
- Agent profiles that repeatedly exceed scope MUST escalate governance mode for that agent specifically.

## Project context loading

- All `*.md` files in the governed project root are loaded, ranked by governance relevance.
- Rank order: INTENT > REQUIREMENTS > CLAUDE.md > README > others.
- Context refreshes mid-session (10 s debounce) when any monitored file changes.
- The 400-token budget for alignment checks is consumed by ranked excerpts, not full file dumps.

## What governance should learn from this project

- `pip install -e ".[dev]"`, `pytest`, `ruff check`, and `mypy` are routine
  development commands and should promote to ALLOW patterns quickly.
- File edits under `src/stream_manager/**` are routine.
- File edits under `spikes/**` are throwaway and lower-stakes.
- Commits to feature branches are routine; force-push to `main` is not.

## Intentional non-goals (v1)

- Multi-tenant cloud deployment.
- Replacing Claude Code's own permission model.
- Acting as a general-purpose IDE or terminal multiplexer.
- Supporting non-Claude CLI tools (architecture allows but v1 doesn't).
