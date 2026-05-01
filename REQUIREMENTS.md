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
Claude Desktop  ←─ws://localhost:8765─→  Stream Manager
                                              │
                                          Governance Engine
                                              │
                                          Message Bus (SQLite WAL)
                                              │
                                          Decision Graph (L0→L4)
                                              │
                                          Project Context (GitHub repo)
                                              │
                                  ←─ws://localhost:8766─→  Claude CLI
```

### 3.1 Subsystem boundaries

| Subsystem | Responsibility | File |
|-----------|----------------|------|
| Message Bus | Persistent SQLite WAL store; pub/sub; pattern persistence | `message_bus.py` |
| Decision Graph | Bottom-up hierarchical pattern learning, L0→L4 promotion | `decision_graph.py` |
| Governance Engine | Mode-managed real-time decision making, static rules, API enrichment | `governance.py` |
| Project Context | GitHub repo loader; intent extraction; precheck rules | `project_context.py` |
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
| OQ-6 | Should the Decision Graph be visualizable in real-time (web UI)? | Product | Stretch goal |
| OQ-7 | Privacy: does the project context loader respect repo `.bridgeignore` if present? | Security | Should add for v1.1 |

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
