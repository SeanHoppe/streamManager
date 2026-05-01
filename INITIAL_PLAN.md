# StreamManager — Framework Plan & POC Strategy

## Context

A new project, **StreamManager** (PascalCase, reframed from the requirements doc's "AdaptiveBridge"), to sit between Claude Desktop and a Claude CLI session as a resource-efficient governance + adaptive-learning bridge. Per the requirements at [StreamManager-REQUIREMENTS.md](instructions/StreamManager-REQUIREMENTS.md), it monitors bidirectional traffic, applies static + learned guardrails, builds a bottom-up L0→L4 decision graph, and hooks into the governed project's repo so decisions reference *that* project's intent rather than generic heuristics.

This plan covers two deliverables only: (a) the framework skeleton — modules, interfaces, hard invariants — and (b) a three-spike POC strategy to surface the riskiest unknowns cheaply before hardening. **No final solution is designed here.**

> **Zero-code-in-certPortal guarantee:** All Python, tests, dependencies, and POC work happen inside `C:\Users\SeanHoppe\VS\streamManager`. The certPortal repo gets no `streamManager/` directory, no new imports, no new dependencies, and no source files. The `streamManager` git branch on certPortal exists only as the entry point that hosted the requirements doc — once the new repo is initialized and the doc is copied over, this branch can be retired.

### Decisions confirmed this session
- **Codebase home:** `github.com/SeanHoppe/streamManager` (separate repo). **Local clone path: `C:\Users\SeanHoppe\VS\streamManager`** — a sibling of `C:\Users\SeanHoppe\VS\certPortal`, not nested inside it. The current `streamManager` branch in certPortal is a planning/requirements branch only.
- **Project name:** `StreamManager` (PascalCase). Full project scope = stream management; governance + adaptive learning are subsystems.
- **POC approach:** Three throwaway spikes, ~1 day each, then commit hardening effort to whichever spike surfaced the most surprise.
- **Anthropic API in POC:** Hybrid — deterministic stub by default, real call gated behind `BRIDGE_API_GOV=true` (matches doc §7.5).
- **New requirement raised in this session:** StreamManager must hook into the repo it's governing to understand its true *intent*, not just file metadata. This elevates `project_context.py` from a metadata loader to an intent-comprehension subsystem.

---

## Framework — module skeleton

Following the requirements doc §3.1, with annotations for which spike exercises each module.

| Module | Purpose | First touched in |
|---|---|---|
| `config.py` | Dataclasses + env-var overrides; feature flags (BRIDGE_INIT_MODE, BRIDGE_PROJECT_CTX, BRIDGE_API_GOV, BRIDGE_LEARN) | All spikes |
| `message_bus.py` | SQLite WAL append-only log; pub/sub + pull; 4 tables: `messages` / `decisions` / `patterns` / `sessions` | Spike A |
| `stream_manager.py` | Two WS servers (8765 Desktop, 8766 CLI); governance hookpoint sits between inbound parse and outbound forward | Spike A |
| `governance.py` | Mode ladder OBSERVE→SUGGEST→GUIDE→INTERVENE→BLOCK; static safety rules; `fast_precheck`; API enrichment | Spike B |
| `decision_graph.py` | L0–L4 hierarchical pattern store; 64-dim hashed projection; cosine similarity; promotion thresholds | Spike B |
| `project_context.py` | **Repo-intent loader** (README/CONTRIBUTING/SECURITY/CODEOWNERS + manifests + INTENT.md); precheck fast path; cached static prefix | Lightly in A; deeply in B |
| `cli_client.py` | Wraps real `claude` subprocess; ANSI/spinner strip; stdin/stdout proxy; explicit feedback signals | Spike C |
| `desktop_client.py` | Reference Desktop-side WS client (also serves as smoke-rig stand-in for the real MCP integration) | Spike C |
| `__main__.py` | Orchestrator; lifecycle; status logger; maintenance loop | Spike A |

### Interface sketches (intentionally not signatures)
- **Bus:** `publish(msg) → seq` (atomic monotonic per session) · `subscribe(callback)` · `pull(since_seq, limit)` · `purge(older_than)`
- **Governance:** `evaluate(msg, context) → GovDecision{action, confidence, reasoning, matched_hash}` · `feedback(decision_id, signal)`
- **ProjectContext:** `load(repo_ref) → ProjectContextSnapshot` (cached) · `fast_precheck(msg) → DecisionOrNone` (≤1 ms, no network) · `intent_summary() → str` (≤600 tokens)
- **DecisionGraph:** `observe(msg, outcome)` · `match(msg) → [Pattern]` · `summarize(window) → str` (the cold-channel compressor for §8 context budget)

### Hard invariants (must survive every refactor)
- **localhost-only** bind by default; remote requires explicit `BRIDGE_HOST` override (NFR-S1)
- **Static safety rules ALWAYS fire** regardless of mode (FR-GE-2). Mode ladder cannot disable them.
- **API timeout never blocks forwarding** — fall back to OBSERVE on Anthropic API failure (NFR-R5)
- **Decisions table append-only** — no deletion API exposed (NFR-S4)
- **GitHub token env-only** — never persisted, never logged (NFR-S2)
- **Per-message context grows ≤ O(log N)** — enforced at prompt-construction layer via the §8.7 hard ceiling (1500 tokens, pattern summary trims first)
- **No cross-codebase imports** — StreamManager never imports certPortal; certPortal never imports StreamManager. (The two projects coexist conceptually but not in code.)

---

## POC strategy — three throwaway spikes

Each spike is a separate branch in `github.com/SeanHoppe/streamManager`, scoped to ~1 day. The deliverable from each is **measured signal**, not production code. After all three, pick the spike that surfaced the most surprise and harden THAT one as v0.1.

### Spike A — "Prove the pipe"  *(branch: `poc/pipe`)*
**What:** Real WAL bus + two WS servers + two dummy echo clients + no-op governance that only logs.

**Measures:**
- End-to-end median round-trip latency (target NFR-P1 ≤ 50 ms)
- Bus throughput under concurrent producers (target NFR-P3 ≥ 500 msg/s)
- WAL durability — `kill -9` mid-write, restart, verify no message loss (NFR-R4)
- Idle RAM (target NFR-R1 ≤ 25 MB)

**De-risks:** SQLite WAL as cross-process IPC store, the WS server pair, the latency budget.

### Spike B — "Prove the brain"  *(branch: `poc/brain`)*
**What:** Replay a captured Claude CLI session log through `governance.evaluate` + `decision_graph.observe`. In-memory only — no WS, no persistence. Stub Anthropic API. **Crucially: load a real `ProjectContext` (the StreamManager repo itself, dogfooded) including INTENT.md if present.**

**Measures:**
- L0→L4 promotion behavior on real-shape data — do the doc's thresholds (3 / 5 / 10 / 20) make sense?
- Mode-promotion math — does the accuracy 0.75 / 0.40 boundary actually trip on a 200-msg session?
- `fast_precheck` latency budget (target ≤ 1 ms, FR-PC-5)
- Pattern-count growth rate — does it stay sub-linear?
- **Intent signal value:** A/B with INTENT.md present vs absent — does decision quality measurably improve? This is the load-bearing experiment for the "hook-in to governed repo" requirement.

**De-risks:** The adaptive-learning math, the threshold defaults, and most importantly the *value of project intent ingest*.

### Spike C — "Prove the wire"  *(branch: `poc/wire`)*
**What:** Wrap a real `claude` subprocess via `cli_client.py`; proxy its stdin/stdout to a WS server; minimal Desktop-side client. No governance, no bus.

**Measures:**
- Does `--output-format json` produce parseable output? (FR-CC-3)
- Are there ANSI escapes / spinners that need stripping? (FR-CC-2)
- Subprocess lifecycle — does `claude` exit cleanly on WS disconnect?
- Multi-Desktop broadcast actually works (FR-SM-5)

**De-risks:** The IPC story with the real `claude` binary — likely the most "unknown unknowns" piece.

### Synthesis step (after all three)
- Compare the surprise yield from each spike. Hardening goes to the spike that surfaced the most.
- Spike B's recorded session log becomes the standing test fixture for v0.1 governance integration tests, regardless of which spike wins.
- The other two spikes' code is deleted; their findings are written up in the streamManager repo as `POC_FINDINGS.md`.

---

## Open questions worth answering before hardening

- **OQ-A — Anthropic model:** Which model for governance calls? `claude-haiku-4-5-20251001` is the obvious fit for the NFR-P2 ≤ 2 s p95 budget; sonnet/opus likely too slow. Confirm during Spike B.
- **OQ-B — INTENT.md schema:** Does StreamManager require a specific shape (sections, frontmatter), or free-form summarize whatever's there? Schema gives stronger signal but adds friction for governed repos.
- **OQ-C — Recursive dogfooding precedence:** When StreamManager governs *itself* (per doc §7.1), what wins — its own `INTENT.md` or `CLAUDE.md`? Need a rule.
- **OQ-D — Doc's OQ-1 (block-by-default vs warn-and-allow):** Pick a default for Spike B. Recommendation: warn-and-allow during POC; promotion to block-by-default earns its way via accuracy data.
- **OQ-E — GitHub auth:** PAT vs GitHub App for the intent fetcher? PAT fastest for Spike B; App better long-term for org-wide governance.
- **OQ-F — Bus path scoping:** Should the SQLite bus path be per-governed-project (`bus_<repo>.db`) so multiple StreamManager sessions don't collide? Probably yes; trivial to add.
- **OQ-G — Repo discovery:** When wrapping a CLI session, how does StreamManager discover *which* repo to load? Candidates: cwd of `claude` subprocess; explicit `--repo` arg; `.git/config` inspection. Likely all three with precedence.

---

## Scope of this `streamManager` branch in certPortal

The actual codebase lives at `github.com/SeanHoppe/streamManager`, cloned locally to `C:\Users\SeanHoppe\VS\streamManager` (sibling of `C:\Users\SeanHoppe\VS\certPortal`). This certPortal branch is **entry point only** — it currently hosts the requirements doc at [StreamManager-REQUIREMENTS.md](instructions/StreamManager-REQUIREMENTS.md), and that's the entirety of its remaining purpose.

**Recommended next step on this branch:** copy the requirements doc and this plan into the new `C:\Users\SeanHoppe\VS\streamManager` repo, then retire the certPortal `streamManager` branch (delete locally and on origin). After that, certPortal has no further connection to the project.

**Hard rules:**
- No code, no Python files, no dependencies, no `streamManager/` directory ever land in certPortal.
- The two repos sit side-by-side under `C:\Users\SeanHoppe\VS\` and never import each other in either direction.
- Anything that would otherwise tempt scaffolding here (CI helpers, shared utilities, scripts) goes in the StreamManager repo, not certPortal.

---

## Verification

This plan is the deliverable. No code is written. Verification = sign-off that:
- (a) the framework skeleton matches the doc's intent, with the intent-ingest elevation captured;
- (b) the three-spike POC strategy is the right shape and ~1 day per spike is the right budget;
- (c) the open questions are the right ones to surface before hardening.

---

## Critical file references

- [instructions/StreamManager-REQUIREMENTS.md](instructions/StreamManager-REQUIREMENTS.md) — the spec
- `communityCode/lifecycle_hub/persistence/db.py` — existing WAL pattern in this repo (reference only; do **not** import — separate codebase)
- `pyproject.toml` — confirms Python ≥ 3.11, `anthropic==0.84.0`, `httpx==0.27.2` already pinned. The new repo will need to add `websockets` (no current dep).
- [CLAUDE.md](CLAUDE.md) — isolation invariants; survey confirmed StreamManager-as-separate-repo has no conflicts with INV-01 / INV-07 / TRANS-INV-01 / REACT-INV-01.
