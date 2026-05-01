# AdaptiveBridge — Requirements & Planning Document

**Document type:** PRD + RFC + ADR hybrid
**Version:** 1.0 (initial)
**Status:** Draft for review
**Owner:** TBD
**Last updated:** 2026-05-01

---

## 1. Executive summary

AdaptiveBridge is a resource-efficient governance and learning layer that sits between **Claude Desktop** and a **Claude CLI session** (typically `claude` / Claude Code), monitoring the bidirectional message stream and adaptively learning project-specific governance rules from observed behaviour.

It solves three problems at once:

1. **Coordination** — letting Claude Desktop direct, instruct, and monitor a remote Claude CLI session over a single shared intermediary.
2. **Safety** — applying static guardrails plus learned project-aware governance so dangerous or out-of-policy commands are flagged, modified, or blocked before they execute.
3. **Adaptive intelligence** — building a bottom-up decision graph (L0 signals → L4 emergent policies) that compresses session history into reusable governance knowledge, also reducing context bloat.

The system runs locally with one dependency (`websockets`), uses SQLite WAL for the shared bus, and adds GitHub repo awareness so the governance engine reasons about *this* project's intent — not generic heuristics.

---

## 2. Vision & goals

### 2.1 Vision
A user can run `claude` on a remote machine, control it from Claude Desktop on their laptop, and trust that an adaptive governance layer is watching, learning, and intervening only when warranted — escalating from passive observation to active governance only as evidence accumulates.

### 2.2 Primary goals
| ID    | Goal | Success measure |
|-------|------|-----------------|
| G1    | Real-time bidirectional Desktop ↔ CLI streaming | <50ms median round-trip overhead per message |
| G2    | Resource-efficient shared intermediary | <25 MB RAM idle; <5% CPU at 100 msg/s |
| G3    | Bottom-up adaptive learning | L4 emergent policies form within 100 messages of typical use |
| G4    | Project-aware governance | Decisions reference repo intent, not generic rules |
| G5    | Context bloat resistance | Per-message context grows ≤ O(log N) with session length |
| G6    | Zero data leakage | No project content sent off-device except the governance API call |

### 2.3 Non-goals (v1)
- Multi-tenant cloud deployment
- Replacing Claude Code's own permission model
- Acting as a general-purpose IDE or terminal multiplexer
- Supporting non-Claude CLI tools (though architecture allows this in v2)

---

## 3. Architecture overview

```
Claude Desktop Orchestration
  ├── Sub-agent: Prompt Constructor  ─┐  metadata: {agent_id, agent_type, phase}
  ├── Sub-agent: Developer           ─┤  (or inferred from pattern when absent)
  ├── Sub-agent: Code Reviewer       ─┤
  ├── Sub-agent: Tester              ─┘
            │
            ▼  ws://localhost:8765
       ┌────────────────────────────────────────────────────┐
       │              Stream Manager                        │
       │  ┌─────────────────────────────────────────────┐  │
       │  │  Project Context Loader                      │  │
       │  │  (all *.md + manifests; live refresh)        │  │
       │  ├─────────────────────────────────────────────┤  │
       │  │  Agent Registry                              │  │
       │  │  (metadata + pattern-inferred profiles)      │  │
       │  ├─────────────────────────────────────────────┤  │
       │  │  Orchestration Governance                    │  │
       │  │  (safety + plan alignment + cadence)         │  │
       │  ├─────────────────────────────────────────────┤  │
       │  │  Governance Engine  ←→  Decision Graph L0→L4│  │
       │  ├─────────────────────────────────────────────┤  │
       │  │  Message Bus (SQLite WAL)                    │  │
       │  └─────────────────────────────────────────────┘  │
       └────────────────────────────────────────────────────┘
            │
            ▼  ws://localhost:8766
       Claude CLI (executor)
```

**Role summary:**
- **Claude Desktop Orchestration** — primary director; owns pipeline order; sub-agents produce orchestration prompts
- **Stream Manager** — governance + PM layer; governs each agent independently per role scope; enforces plan alignment and cadence; does NOT gate agent transitions (pipeline control stays with Desktop)
- **Claude CLI** — executor; trusts only what SM forwards

### 3.1 Subsystem boundaries

| Subsystem | Responsibility | File |
|-----------|----------------|------|
| Message Bus | Persistent SQLite WAL store; pub/sub; pattern persistence | `message_bus.py` |
| Decision Graph | Bottom-up hierarchical pattern learning, L0→L4 promotion | `decision_graph.py` |
| Governance Engine | Mode-managed real-time decision making, static rules, API enrichment | `governance.py` |
| Project Context | Full *.md loader; intent extraction; precheck rules; live refresh | `project_context.py` |
| Agent Registry | Hybrid agent discovery (metadata + pattern); per-agent governance profiles | `agent_registry.py` |
| Orchestration Governance | Plan-alignment evaluation; cadence tracking; pipeline stage inference | `orch_governance.py` |
| Stream Manager | Two WebSocket servers, message routing, governance hookpoint | `stream_manager.py` |
| Configuration | All config dataclasses; env var overrides | `config.py` |
| Orchestrator | Wires everything together, lifecycle, status, maintenance | `__main__.py` |
| CLI Client | Wraps real `claude` subprocess; proxies stdin/stdout | `cli_client.py` |
| Desktop Client | Reference implementation for Desktop-side WS connection | `desktop_client.py` |

---

## 4. Functional requirements

### 4.1 Message Bus (FR-MB)

**FR-MB-1** — The bus MUST provide an append-only message log persisted in SQLite with WAL mode enabled, supporting concurrent readers and writers without lock contention.

**FR-MB-2** — Each message MUST carry: `id`, `type`, `direction`, `content`, `context`, `timestamp`, `session_id`, `sequence`, `metadata`.

**FR-MB-3** — The bus MUST support both pub/sub callbacks (for synchronous in-process subscribers) and pull-based consumption (for cross-process consumers).

**FR-MB-4** — The bus MUST expose three additional tables: `decisions` (governance decision log), `patterns` (learned pattern store), and `sessions` (session lifecycle).

**FR-MB-5** — The bus MUST support TTL-based purging of processed messages older than `message_ttl_seconds` (default 1 hour) without affecting decisions or patterns.

**FR-MB-6** — Sequence numbers MUST be monotonic per session and assigned atomically at publish time.

### 4.2 Decision Graph (FR-DG)

**FR-DG-1** — The graph MUST organize patterns into 5 levels (L0 Signal, L1 Action, L2 Sequence, L3 Context Cluster, L4 Policy) with automatic promotion based on configurable thresholds.

**FR-DG-2** — Promotion thresholds (default): L0→L1 at 3 occurrences; L1→L2 at 5; L2→L3 at 10; L3→L4 at 20. All thresholds MUST also require `success_rate ≥ 0.55`.

**FR-DG-3** — Feature extraction MUST NOT require external ML libraries; a 64-dim hashed token projection plus structural signals is sufficient.

**FR-DG-4** — Pattern matching MUST use cosine similarity with a configurable threshold (default 0.72).

**FR-DG-5** — Feedback signals MUST propagate from a node to its higher-level parents at half the learning rate.

**FR-DG-6** — Patterns MUST persist across sessions when `session_persist=true`, allowing cross-session learning.

### 4.3 Governance Engine (FR-GE)

**FR-GE-1** — The engine MUST operate in five modes: `OBSERVE`, `SUGGEST`, `GUIDE`, `INTERVENE`, `BLOCK`, with automatic promotion/demotion based on rolling 10-decision accuracy.

**FR-GE-2** — Static safety rules (rm -rf /, DROP DATABASE, hardcoded credentials, etc.) MUST always fire regardless of mode.

**FR-GE-3** — Mode promotion MUST require accuracy ≥ 0.75; demotion MUST trigger at accuracy ≤ 0.40.

**FR-GE-4** — The engine MUST evaluate every message synchronously before forwarding, returning a `GovDecision` with `action`, `confidence`, `reasoning`, and `matched_hash`.

**FR-GE-5** — The engine MUST record every decision to the bus's `decisions` table for replay and audit.

**FR-GE-6** — Rate limiting MUST cap interventions at `max_interventions_per_minute` (default 10) to prevent governance loops.

**FR-GE-7** — When a `ProjectContext` is provided, the engine MUST run `fast_precheck()` before any API call to catch project-specific rule violations locally.

### 4.4 Project Context (FR-PC)

**FR-PC-1** — The loader MUST fetch and parse repo metadata, README, CONTRIBUTING, SECURITY, CODEOWNERS, and dependency manifests at session start.

**FR-PC-2** — Supported manifest formats: `package.json`, `pyproject.toml`, `requirements.txt`, `Cargo.toml`, `go.mod`. (v2: `pom.xml`, `Gemfile`, `composer.json`)

**FR-PC-3** — The loader MUST gracefully degrade: missing files are logged but do not abort loading.

**FR-PC-4** — Loaded context MUST be injected into every governance API call as a concise prompt section under 600 tokens.

**FR-PC-5** — `fast_precheck()` MUST return a decision in <1ms with no external calls.

**FR-PC-6** — Authentication via `GITHUB_TOKEN` env var; public repos MUST work without authentication.

**FR-PC-7** — The loader MUST discover and load `*.md` files using a three-tier strategy:

1. **Root glob** — always load `*.md` from the project repository root.
2. **Spotlight paths** — an explicit list of high-value paths outside the root (e.g. `oversight/OVERSIGHT-BLUEPRINT.md`, `oversight/shared/*.md`). Configurable per project via `.sm-context.yaml`.
3. **Exclude patterns** — glob patterns of paths to skip even if matched by root or spotlight (e.g. `oversight/agents/**`, `**/*-memory-*.md`, `**/archive/**`). Operational / ephemeral files MUST be excluded to protect the 400-token alignment budget.

Files are ranked by governance relevance: INTENT > REQUIREMENTS > CLAUDE > README > spotlight > others.

**FR-PC-8** — Project context MUST refresh mid-session when any monitored `*.md` file changes on disk, with a minimum debounce of 10 seconds. Stale context MUST NOT be used after a refresh completes.

**FR-PC-9** — The governance engine MUST use the full `*.md` project context for orchestration-prompt alignment checks (see FR-OG) in addition to static safety checks. The context budget for alignment checks is 400 tokens (ranked excerpts, not full file dumps).

### 4.5 Stream Manager (FR-SM)

**FR-SM-1** — Two independent WebSocket servers MUST run concurrently: Desktop on port 8765, CLI on port 8766 (configurable).

**FR-SM-2** — Every inbound message MUST pass through `governance.evaluate()` before being forwarded.

**FR-SM-3** — Governance interventions MUST be visible to the originating side via a `governance_notification` message.

**FR-SM-4** — Blocked messages MUST NOT reach the destination; both sides MUST receive a `governance_block` notification.

**FR-SM-5** — Multiple Desktop clients per CLI session MUST be supported (broadcast); multiple CLI clients per Desktop session is not required for v1.

**FR-SM-6** — Heartbeat / keep-alive MUST be sent every `ping_interval` seconds (default 20).

### 4.6 CLI client (FR-CC)

**FR-CC-1** — The client MUST be capable of wrapping a real subprocess (`claude --no-browser`), proxying its stdin/stdout through the bridge.

**FR-CC-2** — ANSI escape sequences and progress spinners MUST be stripped from CLI output before forwarding (otherwise the governance engine sees garbled text).

**FR-CC-3** — When wrapping `claude`, the client SHOULD pass `--output-format json` or equivalent flag to ensure parseable output.

**FR-CC-4** — The client MUST send explicit feedback signals to the bridge when a governance suggestion was followed/ignored, enabling reinforcement.

### 4.7 Agent Registry (FR-AR)

**FR-AR-1** — SM MUST support hybrid agent identification: (a) explicit metadata in message envelope (`agent_id`, `agent_type`, `agent_role`, `phase` fields), and (b) pattern inference via the L0→L4 decision graph when metadata is absent. Metadata takes precedence when present.

**FR-AR-2** — Each discovered agent MUST be assigned a governance profile specifying: allowed action scope, confidence thresholds, escalation policy, and plan-alignment weight. Profiles are initialized from defaults and refined via pattern learning.

**FR-AR-3** — Agent profiles MUST persist to the WAL bus `agent_profiles` table and survive session and process restarts.

**FR-AR-4** — SM MUST govern each agent **independently** based on its profile. SM MUST NOT gate one agent's messages based on another agent's completion state — pipeline ordering is the Desktop orchestration's responsibility.

**FR-AR-5** — SM MUST provide a **controlled test mode** (`BRIDGE_AGENT_TEST=true`) that emits agent discovery events to the monitoring bus in real-time, enabling external observation of how agent profiles are built and refined.

**FR-AR-6** — The governance profile for known agent roles MUST enforce appropriate scope by default:

| Agent role | Default scope |
|------------|---------------|
| `prompt_constructor` | ALLOW (composition only; no tool execution) |
| `developer` | GUIDE (file edits + shell; destructive ops → INTERVENE) |
| `frontend_architect` | GUIDE (frontend file edits + shell; backend or schema changes → INTERVENE) |
| `code_reviewer` | SUGGEST (annotations only; direct CLI execution → BLOCK) |
| `tester` | ALLOW (read + test runner commands) |
| `researcher` | ALLOW (read + synthesis only; any write op or code execution → BLOCK) |
| `strategic_advisor` | OBSERVE (read + recommendations only; any direct execution → BLOCK) |
| `health_monitor` | OBSERVE (read + status reporting only; any write op → BLOCK) |
| `sub_agent` | ALLOW scoped to declared task type only; any action outside declared task type → BLOCK |
| `unknown` | Governed by standard engine rules |

**FR-AR-7** — SM MUST tail the governed project's active JSONL session log (`~/.claude/projects/{slug}/*.jsonl`, newest file) in parallel with WebSocket message interception. JSONL attribution fields MUST take precedence over all pattern inference:

| JSONL field | SM action |
|-------------|-----------|
| `attributionPlugin` present | Assign agent identity directly; skip L1–L3 inference |
| `attributionSkill` present | Record active skill; refine role profile accordingly |
| `isSidechain=true` + `sourceToolAssistantUUID` | Assign `sub_agent` profile immediately; link to parent agent UUID |
| `stopReason=end_turn` | Primary signal for FR-HITL-2 desktop_pause detection (preferred over text heuristic) |
| `preventedContinuation=true` | Emit `governance_external_block` bus event; record in decisions |

JSONL tail MUST be non-blocking: a lag or parse failure in the tail MUST NOT delay WebSocket message forwarding.

### 4.8 Orchestration Governance (FR-OG)

**FR-OG-1** — SM MUST evaluate orchestration prompts for **project-plan alignment** in addition to safety. Alignment checks ask: does this prompt move work toward stated requirements and current sprint goals, or does it contradict or drift from them?

**FR-OG-2** — Alignment evaluation MUST reference the full ranked `*.md` project context (FR-PC-7/9). Contradictions with INTENT.md or REQUIREMENTS.md MUST produce at minimum a GUIDE decision; contradictions with a frozen component or explicit constraint MUST produce INTERVENE.

**FR-OG-3** — SM MUST infer the **current pipeline stage** from observed agent activity patterns (e.g., sustained Reviewer activity → code-review stage). This stage is used to contextualise governance decisions but does not gate agent transitions.

**FR-OG-4** — SM MUST track a **cadence signal** per session: rate of forward progress relative to stated project goals. A stalling or drifting session (no plan-aligned decisions in configurable window, default 10 minutes) MUST emit a `governance_cadence_warning` bus event.

**FR-OG-5** — SM MUST NOT compose or inject its own prompts into the governed session. Orchestration authorship remains with the Desktop sub-agents; SM's role is evaluation and governance, not generation.

**FR-OG-6** — All alignment and cadence decisions MUST be recorded to the `decisions` table with `source="orch_governance"` for audit and replay.

### 4.9 Human-in-the-Loop (FR-HITL)

**FR-HITL-1** — SM MUST support two HITL operating modes, switchable at runtime via the dashboard UI:
- **Sync mode** — SM holds matching messages in a pending queue and waits for human approval before forwarding. The mode switch persists to the session record in the WAL bus.
- **Async mode** — SM decides and forwards immediately; human reviews decisions after the fact and annotates with override + notes. Notes apply to future similar decisions, not the current one.

**FR-HITL-2** — In **sync mode**, a message MUST be queued for human approval when ANY of the following triggers fires:
1. **New pattern** — decision hash not found in the decision graph (SM has no learned precedent).
2. **Low confidence** — decision confidence falls below a configurable floor (default `0.60`; adjustable per session in dashboard settings).
3. **Desktop pause signal** — Desktop orchestration has paused. Detection priority:
   - **Primary (JSONL):** `stopReason=end_turn` record observed in JSONL tail for the active session.
   - **Fallback (text heuristic, used only when JSONL tail unavailable or >2 s lagging):** message ends with `?`, or contains phrases like "what would you like", "should I", "please confirm", "done", "complete", "task complete", "all tasks finished".

**FR-HITL-3** — SM MUST expose a `hitl_pending` queue in the WAL bus. Each pending entry records: `message_id`, `proposed_action`, `proposed_confidence`, `trigger_reason` (new_pattern | low_confidence | desktop_pause), `queued_at`, `resolved_at`, `resolution` (approved | overridden | timeout).

**FR-HITL-4** — The dashboard MUST display a **HITL Queue panel** showing all pending messages. For each entry the human can:
- **Approve** — forward with SM's proposed action.
- **Override** — select a different action (ALLOW / GUIDE / SUGGEST / INTERVENE / BLOCK) and optionally enter a free-text note explaining the decision.
- **Dismiss** — mark as not requiring action (equivalent to ALLOW with no note).

**FR-HITL-5** — Sync mode MUST have a configurable timeout (default `60 s`). On timeout, SM falls back to its proposed decision, records `resolution=timeout` in `hitl_pending`, and emits a `hitl_timeout` bus event. A timed-out decision MUST NOT be silently dropped.

**FR-HITL-6** — In **async mode**, every decision row in the dashboard feed MUST expose an **Annotate** affordance. The human can set an override action and add a note at any time after the decision was made. Async annotations MUST be stored as a `hitl_override` record linked to the original `decisions` row.

**FR-HITL-7** — **Feedback loop**: SM MUST read `hitl_override` records when evaluating future messages. Specifically:
- If a past HITL override changed action for a given hash pattern, SM MUST adjust its confidence toward the human-preferred action for that hash on subsequent encounters (reinforcement signal).
- Free-text notes from overrides MUST be stored and, when the same hash pattern recurs, injected as a short context hint (≤ 50 tokens) into the governance alignment prompt.
- Override records accumulate per hash; the most recent `N` overrides (default `N=5`) are retained as active context; older ones are archived in the WAL bus but not injected.

**FR-HITL-8** — WAL bus schema additions:

```sql
CREATE TABLE IF NOT EXISTS hitl_pending (
    id           INTEGER PRIMARY KEY,
    message_id   INTEGER NOT NULL REFERENCES messages(id),
    proposed_action     TEXT NOT NULL,
    proposed_confidence REAL NOT NULL,
    trigger_reason      TEXT NOT NULL,   -- new_pattern | low_confidence | desktop_pause
    queued_at    TEXT NOT NULL,
    resolved_at  TEXT,
    resolution   TEXT                    -- approved | overridden | timeout | dismissed
);

CREATE TABLE IF NOT EXISTS hitl_overrides (
    id              INTEGER PRIMARY KEY,
    decision_id     INTEGER NOT NULL REFERENCES decisions(id),
    original_action TEXT NOT NULL,
    override_action TEXT NOT NULL,
    note            TEXT,
    mode            TEXT NOT NULL,       -- sync | async
    timestamp       TEXT NOT NULL
);
```

**FR-HITL-9** — Dashboard MUST expose configurable HITL settings per session:
- Sync/async mode toggle (persisted to session record).
- Confidence floor slider (0.0–1.0, default 0.60).
- Sync timeout (seconds, default 60).
- Desktop pause detection on/off toggle.

**FR-HITL-10** — All HITL interactions (approvals, overrides, timeouts, annotations) MUST be recorded with timestamp and source `"hitl"` in the bus for full audit replay.

---

## 5. Non-functional requirements

### 5.1 Performance
- **NFR-P1** — Median message latency through the bridge ≤ 50 ms (excluding governance API call).
- **NFR-P2** — Governance API call latency ≤ 2 s p95 (depends on Anthropic API).
- **NFR-P3** — Bus throughput ≥ 500 messages/sec on commodity hardware.
- **NFR-P4** — `fast_precheck()` ≤ 1 ms; cosine similarity match ≤ 5 ms over 1000 patterns.

### 5.2 Resource consumption
- **NFR-R1** — Idle RAM ≤ 25 MB, active ≤ 50 MB at sustained 100 msg/s.
- **NFR-R2** — Idle CPU ≤ 1%; active CPU ≤ 5% at 100 msg/s.
- **NFR-R3** — Disk growth ≤ 10 MB/hour at typical use; TTL purge keeps DB bounded.

### 5.3 Reliability
- **NFR-R4** — Bus writes MUST be durable (WAL fsync); a process crash MUST NOT lose published messages.
- **NFR-R5** — Subsystem failures MUST be isolated: a governance API timeout MUST NOT block message forwarding (fall back to OBSERVE).
- **NFR-R6** — Subscriber callback exceptions MUST NOT crash the bus.

### 5.4 Security
- **NFR-S1** — All network bindings MUST default to `localhost`; remote access requires explicit `BRIDGE_HOST` override.
- **NFR-S2** — The GitHub token MUST be read from env vars only, never logged or persisted.
- **NFR-S3** — Static rules MUST cover at minimum: destructive rm, format, dd to disk, DB drops, hardcoded credentials, eval/exec injection.
- **NFR-S4** — Decision records MUST be append-only; no API exposes message deletion.

### 5.5 Observability
- **NFR-O1** — All subsystems MUST emit structured logs with consistent format and configurable level.
- **NFR-O2** — A periodic status logger MUST emit governance mode, intervention count, and pattern counts every 30 s.
- **NFR-O3** — A `--status` CLI flag MUST print current bus statistics and exit.

### 5.6 Model routing
- **NFR-M1** — SM MUST route governance LLM calls by decision layer; calling a more expensive model than the layer requires is a defect.

  | Layer | Trigger | Model |
  |-------|---------|-------|
  | L0 | Regex / static rule match | No LLM |
  | L1 | Decision graph hash match, confidence ≥ 0.85 | No LLM |
  | L2 | Decision graph hash match, confidence 0.60–0.84 | `haiku-4-5` |
  | L3 | No graph match; pattern inference fallback | `haiku-4-5` |
  | L4 | FR-OG alignment check; ambiguous INTERVENE/BLOCK; HITL note synthesis | `sonnet` (minimum) |

- **NFR-M2** — Model selection MUST be driven by `--model` flag on the `claude -p` subprocess call. No SDK model override. Valid values read from `BRIDGE_L2_MODEL` (default `claude-haiku-4-5-20251001`) and `BRIDGE_L4_MODEL` (default `claude-sonnet-4-6`) env vars.

- **NFR-M3** — Haiku (`claude-haiku-4-5`) MUST NOT be used for: FR-OG alignment checks, any decision that produces INTERVENE or BLOCK on a previously-unseen pattern, or HITL note synthesis. Violations are a correctness defect.

- **NFR-M4** — At steady state (post-pattern-convergence), ≥ 80% of decisions MUST resolve at L0–L1 (no LLM). L4 call rate > 20% of decisions is a signal that pattern learning is not converging and MUST trigger an `nfr_model_routing_alert` bus event.

- **NFR-M5** — Model routing decisions MUST be logged per-decision (`model_used`, `layer`) in the `decisions` table for cost and convergence analysis.

---

## 6. Architecture decision records

### ADR-1 — SQLite WAL as the shared intermediary
**Context:** Need a low-resource shared message store that supports concurrent readers/writers across processes without a separate daemon.
**Decision:** Use SQLite in WAL mode with per-thread connections.
**Alternatives considered:** Redis (heavier, separate process), NATS (overkill), filesystem polling (high latency, OS-specific).
**Consequences:** No external services needed. WAL gives concurrent reads. One file = one bus. Schema migrations are slightly trickier than Redis. Acceptable.

### ADR-2 — Bottom-up 5-level decision graph
**Context:** Need an adaptive learning model that doesn't require ML libraries, runs in-process, and produces interpretable patterns.
**Decision:** Hierarchical pattern graph promoted automatically from L0 (signal) through L4 (policy) based on occurrence + success thresholds.
**Alternatives considered:** Pretrained embeddings (heavy), online clustering (less interpretable), rule-based-only (no adaptation).
**Consequences:** No GPU/torch dependency. Patterns are inspectable as text. Cosine similarity + hashed projection is approximate but sufficient for sub-100k patterns.

### ADR-3 — Mode ladder for governance escalation
**Context:** A binary block/allow governance is too coarse and erodes user trust quickly.
**Decision:** Five-step mode ladder with automatic accuracy-driven promotion/demotion.
**Alternatives considered:** Confidence threshold per message (no global state), user-toggled mode (no adaptation).
**Consequences:** System defaults to permissive, earns intervention rights through accuracy. Requires feedback signals to drive adaptation. Mode is global per session, not per-pattern (simpler, slight loss of granularity).

### ADR-4 — GitHub repo as the project's "constitution"
**Context:** Generic governance rules over-fire on routine project commands and miss project-specific risk.
**Decision:** Load README, CONTRIBUTING, SECURITY, CODEOWNERS, and manifest files at session start; inject summary into every governance prompt; run `fast_precheck()` locally.
**Alternatives considered:** Manual rule config file (high friction), no project context (lower quality).
**Consequences:** Adds a session-start latency cost (~1-2 s for typical repo). Requires GitHub access. Worth it for the dramatic accuracy uplift on project-aware decisions.

### ADR-5 — Anthropic API as the governance reasoner
**Context:** Pure pattern matching can't generalize to novel commands; full local model would explode resource budget.
**Decision:** Use the Anthropic API for governance reasoning, supplemented by local static rules and project context.
**Alternatives considered:** Local LLM (resource-heavy), pure regex rules (doesn't generalize).
**Consequences:** Adds 200-2000 ms per evaluated message. Adds an external dependency. Mitigation: local `fast_precheck()` short-circuits 60-80% of decisions; degraded mode (fall back to OBSERVE) if API unavailable.

### ADR-6 — WebSockets for stream transport
**Context:** Need bidirectional, low-latency, framed messaging between three processes.
**Decision:** Two WebSocket servers (Desktop + CLI) using `websockets` package.
**Alternatives considered:** Unix sockets (no remote), gRPC (heavy), HTTP polling (latency).
**Consequences:** One Python dependency. Cross-platform. Compatible with browser-based tooling for future visualization.

### ADR-7 — Hybrid agent identification (metadata + pattern inference)
**Context:** Desktop sub-agents may or may not include identifying metadata in message envelopes. Requiring metadata would break compatibility with agents that don't emit it; pure inference is slow to converge.
**Decision:** Support both: explicit `agent_id/agent_type/agent_role` metadata fields take precedence; pattern inference via L0→L4 graph fills the gap when metadata is absent.
**Alternatives considered:** Metadata-only (breaks unannotated agents), inference-only (slow convergence), separate registration handshake (adds protocol complexity).
**Consequences:** Agent profiles converge faster when metadata is present. Inference path reuses existing graph machinery at no extra cost. Hybrid mode degrades gracefully: worst case is treating an unknown agent as `unknown` role with standard governance rules.

### ADR-8 — SM governs per-agent independently; Desktop owns pipeline order
**Context:** Multi-agent orchestration raises the question of whether SM should enforce stage sequencing (block deploy until tests pass) or only govern individual message safety and alignment.
**Decision:** SM governs each agent's messages independently per its profile. Pipeline ordering is Desktop orchestration's responsibility. SM does not gate agent transitions.
**Alternatives considered:** SM as pipeline coordinator (cross-agent gating) — rejected; adds stateful cross-agent coupling that duplicates what Desktop orchestration already manages, and creates a single point of failure for pipeline flow.
**Consequences:** SM remains stateless w.r.t. pipeline order. Desktop retains full control of sequencing. SM's cadence signal (FR-OG-4) flags stalls without blocking agents directly.

### ADR-9 — HITL as a switchable mode, not a separate subsystem
**Context:** HITL could be implemented as an always-on intercept layer, a separate process, or a runtime-switchable mode within the existing engine.
**Decision:** HITL is a runtime-switchable mode controlled by the dashboard. Sync and async modes share the same `hitl_overrides` WAL table and feedback loop; only the intercept timing differs. No separate process. The governance engine gains a `hitl_mode` flag read from the session record at startup and checked per-decision.
**Alternatives considered:** Always-on sync (rejected — eliminates human's ability to run uninterrupted sessions); always async only (rejected — removes real-time control that makes HITL valuable for new-pattern and desktop-pause triggers); separate HITL daemon (rejected — adds IPC complexity with no benefit over a flag in the existing engine).
**Consequences:** Single code path for both modes simplifies testing and reduces engine complexity. The runtime toggle means the human can shift to async for known-stable work and re-engage sync when exploring new territory, without restarting SM.

### ADR-10 — Tiered model routing: Haiku at L2–L3, Sonnet floor at L4
**Context:** SM uses `claude -p` subprocess for LLM governance calls. Running Sonnet for every call is correct but expensive; running Haiku for every call risks reasoning failures on alignment and ambiguous block decisions.
**Decision:** Route by decision layer (NFR-M1). L0–L1 require no LLM. L2–L3 use Haiku — these are confirmation or soft-inference calls on low-confidence graph matches where the cost of a Haiku error is a recoverable GUIDE, not a missed destructive action. L4 uses Sonnet minimum — alignment checks, novel INTERVENE/BLOCK, and HITL note synthesis require multi-document reasoning that Haiku degrades on at the 400-token project context budget.
**Alternatives considered:** Haiku for all LLM calls (rejected — demonstrated reasoning degradation on multi-doc alignment tasks at short token budgets); Sonnet for all LLM calls (correct but ~12× cost of L2–L3 Haiku calls for lower-stakes decisions; unsustainable at high message volume); dynamic model selection per message complexity (rejected — complexity estimation itself requires a model call, defeating the purpose).
**Consequences:** ~80% of decisions at L0–L1 (no cost); L2–L3 Haiku calls ~12× cheaper than Sonnet; L4 Sonnet reserved for decisions where correctness matters most. Model choice exposed via env vars so it can be updated as better/cheaper models ship. NFR-M4 convergence alert prevents silent model-routing budget drift.

---

## 7. Development workflow (Q2 answer)

### 7.1 Recursive development setup
The most natural environment is using Claude Code to build AdaptiveBridge while also using AdaptiveBridge to govern that very development session. This dogfooding is intentional: the project becomes its own first user.

**Recommended layout:**
```
~/projects/adaptive_bridge/        ← the codebase
~/projects/adaptive_bridge/.bridge ← runtime artifacts
   ├── adaptive_bridge.db          (SQLite WAL bus)
   ├── governance.log
   └── patterns_export.json        (periodic snapshot)
```

### 7.2 Smoke test environment

A single tmux session with three panes is the canonical local test rig:

| Pane | Purpose | Command |
|------|---------|---------|
| 1 | Bridge | `python -m adaptive_bridge --mode OBSERVE --log-level INFO` |
| 2 | CLI side | `python cli_client.py --session smoke --subprocess claude --no-browser` |
| 3 | Desktop side | `python desktop_client.py --session smoke` |

This rig validates end-to-end behaviour without needing the actual Claude Desktop MCP integration.

### 7.3 Test pyramid

| Tier | Scope | Tools |
|------|-------|-------|
| Unit | Single class behaviour, deterministic | `pytest`, in-memory SQLite |
| Integration | Subsystem wiring with mocked external calls | `pytest-asyncio`, mocked Anthropic API |
| Smoke | Full local rig (tmux setup above) | manual scripted scenarios |
| E2E | Real Claude Desktop ↔ real Claude CLI | manual or recorded session replay |

### 7.4 Phased rollout

| Phase | Audience | Mode | Duration | Exit criteria |
|-------|----------|------|----------|---------------|
| 0 — Internal dev | 1 user | OBSERVE only | 1 week | No false-positive blocks; bus durability proven |
| 1 — Trusted alpha | 3-5 users | OBSERVE + static rules | 2 weeks | <2% intervention error rate |
| 2 — Beta | 10-25 users | Auto-promote to SUGGEST | 4 weeks | Mode promotion data validates thresholds |
| 3 — General | All | Full ladder enabled | ongoing | Feedback loop tuned |

### 7.5 Feature flags
All non-static governance behaviours MUST be feature-flag-able via env vars:
- `BRIDGE_INIT_MODE` — caps the maximum mode reachable
- `BRIDGE_PROJECT_CTX` — enables/disables repo loading
- `BRIDGE_API_GOV` — enables/disables Anthropic API calls (forces fast_precheck only)
- `BRIDGE_LEARN` — enables/disables decision graph updates

---

## 8. Context management strategy (Q3 answer)

The single biggest long-term risk for this system is context bloat. As messages accumulate, naïve forwarding to the governance API would balloon every prompt to thousands of tokens. The mitigation is a six-layer strategy.

### 8.1 Layer 1 — Sliding window
Only the last `context_window` messages (default 5) are included in any governance evaluation context. Older messages live in the bus but don't reach prompts unless explicitly summoned.

### 8.2 Layer 2 — Semantic deduplication
Before adding a message to the prompt context, hash its feature vector and check against recent context. If similarity ≥ 0.92 to an already-included message, replace with `[duplicate of msg #N]` reference.

### 8.3 Layer 3 — Hierarchical summarization via Decision Graph
The Decision Graph is itself a context compressor. Instead of sending raw history, send the L2/L3 pattern summaries:
> Recent patterns: file-edit-cycle (12 occurrences, 0.91 success), dependency-install (3 occurrences, 1.0 success)

A 50-message session compresses to ~5 lines of pattern summary.

### 8.4 Layer 4 — Two-channel context
Split context into hot and cold channels:
- **Hot channel** (always sent): current message + last 2 messages, full fidelity, ~200 tokens max
- **Cold channel** (referenced): pattern summary + decision graph snapshot, ~300 tokens max
The governance prompt uses both, capped at 500 tokens of context regardless of session length.

### 8.5 Layer 5 — Lazy detail fetching
The governance API call returns a `needs_more_context` flag if the model can't decide with the provided summary. Only on that signal does the bridge attach a wider history window. In typical use, fewer than 5% of evaluations need the deeper context.

### 8.6 Layer 6 — Project context cached once
The `ProjectContext` summary loads once per session and is cached as a static prefix. It does not regrow with conversation length. This is a flat ~400 tokens added to every prompt, not a per-message tax.

### 8.7 Context budget enforcement
A hard ceiling MUST be enforced at the prompt-construction layer:
```
max_governance_prompt_tokens = 1500
  ├── 400 — project context (static)
  ├── 300 — pattern summary (graph snapshot)
  ├── 200 — hot channel (current + 2 prior messages)
  ├── 200 — current message itself
  ├── 200 — fixed instruction header
  └── 200 — buffer for safety
```

If the constructed prompt exceeds 1500 tokens, the pattern summary is the first thing trimmed (pattern info has highest compression ratio).

### 8.8 Long-term: cross-session memory pruning
Patterns with `last_seen > 30 days` AND `occurrences < 5` MUST be candidates for pruning during maintenance. This prevents the pattern store growing unboundedly over multi-month deployments.

---

## 9. Acceptance criteria

### 9.1 v1 release blockers
- [ ] All FR-MB requirements pass automated tests
- [ ] All FR-DG promotion thresholds validated against a recorded 200-message session
- [ ] All FR-GE static rules fire in < 1 ms in benchmark
- [ ] FR-PC loader handles 5 reference repos (1 each: Node, Python, Rust, Go, mixed) without errors
- [ ] FR-SM round-trip latency ≤ 50 ms median in smoke test
- [ ] NFR-R1 RAM ceiling held during a 1-hour soak test at 100 msg/s
- [ ] Context-budget enforcement (Section 8.7) tested with 500-message session

### 9.2 Quality bars
- Test coverage ≥ 80% for `governance.py`, `decision_graph.py`, `project_context.py`
- All public functions documented with type hints
- README updated with installation, quick-start, and Claude Desktop MCP integration
- At least one recorded end-to-end demo

### 9.3 Documentation deliverables
- `README.md` — quick start
- `REQUIREMENTS.md` — this document
- `ARCHITECTURE.md` — diagrams + data flow
- `OPERATIONS.md` — deployment, monitoring, troubleshooting
- `CONTRIBUTING.md` — development workflow

---

## 10. Open questions

| ID | Question | Owner | Status |
|----|----------|-------|--------|
| OQ-1 | Should governance interventions block by default or warn-and-allow? | Product | Pending |
| OQ-2 | What is the right default `mode_promotion_threshold` empirically? | Eng | Needs alpha data |
| OQ-3 | Should project context refresh mid-session if the repo changes? | Eng | Likely yes, with debounce |
| OQ-4 | How do we handle multi-repo projects (monorepo with sub-projects)? | Eng | v2 scope |
| OQ-5 | Is the SQLite bus sufficient for 10+ concurrent CLI sessions or do we need migration to Postgres? | Ops | Profile in Phase 2 |
| OQ-6 | Should the Decision Graph be visualizable in real-time (web UI)? | Product | **Resolved** — FastAPI+SSE dashboard built (`dashboard/`); 3 visual themes |
| OQ-7 | Privacy: does the project context loader respect repo `.bridgeignore` if present? | Security | Should add for v1.1 |
| OQ-8 | What is the convergence time for pattern-inferred agent identification with no metadata? | Eng | Needs controlled-test data (FR-AR-5) |
| OQ-9 | Should per-agent governance profiles be user-editable (YAML/TOML config) or purely learned? | Product | Pending; leaning toward learned-with-defaults |
| OQ-10 | How should SM handle an agent that exceeds its profile scope repeatedly — escalate mode or flag for human review? | Eng | Pending alpha data |

---

## 11. Glossary

| Term | Definition |
|------|------------|
| Bridge | The full AdaptiveBridge process orchestrating bus + governance + stream |
| Bus | The SQLite WAL-based message store and pub/sub layer |
| Pattern | A learned signal/sequence/cluster/policy in the Decision Graph |
| Promotion | Automatic graduation of a pattern from level Lₙ to Lₙ₊₁ |
| Mode | One of OBSERVE/SUGGEST/GUIDE/INTERVENE/BLOCK; governs intervention scope |
| Static rule | A regex-based safety check that always fires, regardless of mode |
| Fast precheck | Local zero-API governance evaluation using project context |
| Hot channel | Recent messages always included in governance prompts |
| Cold channel | Compressed pattern/decision summaries included by reference |
| L0–L4 | The five levels of the Decision Graph hierarchy |

---

## 12. Revision history

| Version | Date | Author | Notes |
|---------|------|--------|-------|
| 1.0 | 2026-05-01 | initial | First complete draft, all sections present |
| 1.1 | 2026-05-01 | SeanHoppe | Add FR-AR (Agent Registry), FR-OG (Orchestration Governance), FR-PC-7/8/9 (full *.md context + live refresh); ADR-7, ADR-8; updated architecture diagram; SM repositioned as governance + PM layer for Desktop sub-agent orchestration |
| 1.2 | 2026-05-01 | SeanHoppe | FR-PC-7: replace naive ALL-*.md with three-tier root/spotlight/exclude strategy; FR-AR-6: add frontend_architect, researcher, strategic_advisor, health_monitor, sub_agent roles from certPortal agent topology recon |
| 1.3 | 2026-05-01 | SeanHoppe | Add FR-HITL (§4.9): hybrid sync/async HITL with mode switch, three sync triggers (new_pattern, low_confidence, desktop_pause), feedback loop via hitl_overrides, WAL schema additions, ADR-9 |
| 1.4 | 2026-05-01 | SeanHoppe | FR-AR-7: JSONL log tail as second signal path; attributionPlugin/attributionSkill eliminate pattern inference; isSidechain→sub_agent; stopReason→primary desktop_pause signal; FR-HITL-2 amended with JSONL-primary/heuristic-fallback detection hierarchy |
| 1.5 | 2026-05-01 | SeanHoppe | §5.6 NFR-M1–M5: tiered model routing (no-LLM L0–L1, Haiku L2–L3, Sonnet-floor L4); ADR-10; model logged per-decision; convergence alert NFR-M4 |
