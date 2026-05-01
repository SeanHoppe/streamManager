# Phase 1 — Agent Registry + JSONL Tail

**Sequence:** Second. Requires Phase 0 complete.
**Estimated time:** 2–3 sessions.
**FR refs:** FR-AR-6 (role profiles), FR-AR-7 (JSONL log tail).

**BLOCKING:** Every downstream phase (HITL, model routing, OG-7) depends on
agent identity being resolved at runtime. Do not skip or partial-ship this phase.

---

## Context

The governance engine (`src/stream_manager/governance.py`) is currently role-blind.
Every message receives the same evaluation regardless of whether the sender is
Dave (developer, GUIDE default) or Jen (code_reviewer, SUGGEST default, write-blocked).

Agent profiles already exist as a YAML spec (`src/stream_manager/agent_profiles.yaml`).
The JSONL files at `~/.claude/projects/{slug}/*.jsonl` contain `attributionPlugin`
and `attributionSkill` fields that directly identify the sending agent without inference.

This phase wires those two sources together into a runtime Agent Registry and
plumbs agent identity into every governance decision.

---

## Deliverables

### New files

| File | Purpose |
|------|---------|
| `src/stream_manager/agent_registry.py` | Loads agent_profiles.yaml; resolves agent identity → profile |
| `src/stream_manager/jsonl_tail.py` | Background thread; tails ~/.claude/projects/{slug}/*.jsonl |

### Modified files

| File | Changes |
|------|---------|
| `src/stream_manager/message_bus.py` | Add `agents` table to `_SCHEMA` |
| `src/stream_manager/governance.py` | Accept `AgentRegistry`; scope evaluation per active agent profile |
| `dashboard/server.py` | Expose `GET /api/agents` endpoint |
| `dashboard/static/index.html` | Add agent column to decisions table; active-agent badge in session panel |

---

## Prompt

```
Implement Phase 1 of the StreamManager viable product roadmap.
Reference: REQUIREMENTS.md §FR-AR-6 and §FR-AR-7, src/stream_manager/agent_profiles.yaml.

### 1. agent_registry.py

Create src/stream_manager/agent_registry.py with:

class AgentProfile:
    slug: str                    # e.g. "developer", "code_reviewer"
    default_action: str          # "ALLOW" | "GUIDE" | "SUGGEST" | "OBSERVE" | "BLOCK"
    allowed_ops: list[str]
    restricted_ops: list[str]
    blocked_ops: list[str]
    escalate_to: str
    confidence_floor: float
    example_agents: list[str]

class AgentRegistry:
    - __init__(profiles_path: Path): load agent_profiles.yaml on init
    - resolve(attribution_plugin: str, attribution_skill: str,
               is_sidechain: bool) -> AgentProfile
        Priority: exact example_agents name match → is_sidechain → "unknown"
    - active_profile(session_id: str) -> AgentProfile | None
    - update_active(session_id: str, profile: AgentProfile) -> None
    - all_active() -> dict[str, AgentProfile]  # session_id → profile

### 2. WAL schema — agents table

Add to message_bus.py _SCHEMA (after existing CREATE TABLE blocks):

    CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        attribution_plugin TEXT NOT NULL DEFAULT '',
        attribution_skill TEXT NOT NULL DEFAULT '',
        is_sidechain INTEGER NOT NULL DEFAULT 0,
        profile_slug TEXT NOT NULL DEFAULT 'unknown',
        first_seen REAL NOT NULL,
        last_seen REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_agents_session ON agents(session_id);

Also add to MessageBus class:
    def upsert_agent(self, session_id: str, attribution_plugin: str,
                     attribution_skill: str, is_sidechain: bool,
                     profile_slug: str) -> None

### 3. jsonl_tail.py

Create src/stream_manager/jsonl_tail.py with:

class JsonlTailWorker:
    - __init__(projects_dir: Path, registry: AgentRegistry, bus: MessageBus)
    - start(session_id: str, project_slug: str) -> None
        Finds ~/.claude/projects/{project_slug}/*.jsonl
        Tails in background thread (seek to end on open, poll every 0.5s)
    - stop() -> None

For each new JSONL line, parse as JSON and extract:
    attribution_plugin  = record.get("attributionPlugin", "")
    attribution_skill   = record.get("attributionSkill", "")
    is_sidechain        = bool(record.get("isSidechain", False))
    stop_reason         = record.get("stopReason", "")
    session_id_jsonl    = record.get("sessionId", "")

On any attribution_plugin change:
    1. Call registry.resolve(attribution_plugin, attribution_skill, is_sidechain)
    2. Call registry.update_active(session_id, profile)
    3. Call bus.upsert_agent(...)
    4. Emit bus event type="agent_identified", content=attribution_plugin,
       metadata={"profile_slug": profile.slug, "is_sidechain": is_sidechain}

On stopReason == "end_turn":
    Emit bus event type="desktop_pause", content="end_turn",
    metadata={"session_id": session_id_jsonl}

### 4. Wire AgentRegistry into GovernanceEngine

Modify src/stream_manager/governance.py:

    @dataclass
    class GovernanceEngine:
        ...
        registry: AgentRegistry | None = None   # add this field

In _evaluate_inner(msg):
    - Before precheck, call:
        profile = self.registry.active_profile(self.session_id) if self.registry else None
    - If profile is not None:
        - If msg operation maps to profile.blocked_ops → return BLOCK (confidence=1.0)
        - If msg operation maps to profile.restricted_ops → cap max action at profile.escalate_to
        - Apply profile.confidence_floor: if final confidence < floor → escalate to GUIDE minimum
    - Annotate GovDecision with source="agent_profile:{profile.slug}" when profile applied

Operation mapping (classify msg.content against ops):
    shell_command     — contains shell metacharacters or command patterns
    file_write        — "write", "create file", "save to"
    file_edit         — "edit", "modify", "update" + file path
    file_read         — "read", "open", "show me"
    destructive_shell — rm -rf, DROP TABLE, dd if=, truncate
    force_push_protected — "git push" + ("--force" or "-f") + ("main" or "master" or "production")
    credential_exfiltration — token/API-key shape in outbound content

### 5. Dashboard additions

In dashboard/server.py add:
    GET /api/agents  →  list active agents for current session
    Response: [{"session_id", "attribution_plugin", "profile_slug", "is_sidechain", "last_seen"}]

In dashboard/static/index.html:
    - Add "Agent" column to decisions table (show profile_slug chip)
    - Add active-agent badge panel below session stats: shows current attribution_plugin
      and profile_slug for the most recently active agent in the session

### 6. Tests

Add tests/test_agent_registry.py covering:
    - resolve() returns correct profile for known example_agents name
    - resolve() returns sub_agent profile when is_sidechain=True
    - resolve() falls back to "unknown" profile for unrecognized names
    - blocked_ops check returns BLOCK in governance evaluate()
    - restricted_ops check caps action at escalate_to value

Run: pytest tests/test_agent_registry.py -v
All tests must pass before committing.
```

---

## STOP + VERIFY

Before marking Phase 1 complete, confirm **all** of the following:

**agent_registry.py**
- [ ] File exists at `src/stream_manager/agent_registry.py`
- [ ] `AgentProfile` dataclass has all 8 fields from agent_profiles.yaml
- [ ] `AgentRegistry.resolve()` priority: name match → sidechain → unknown
- [ ] `AgentRegistry` loads from `agent_profiles.yaml` (not hardcoded)

**WAL schema**
- [ ] `agents` table in `message_bus.py _SCHEMA`
- [ ] `upsert_agent()` method on `MessageBus`
- [ ] Schema migration is additive — existing DB rows unaffected

**jsonl_tail.py**
- [ ] File exists at `src/stream_manager/jsonl_tail.py`
- [ ] Tails `~/.claude/projects/{slug}/*.jsonl` (not hardcoded path)
- [ ] Emits `agent_identified` bus event on attribution change
- [ ] Emits `desktop_pause` event on `stopReason=end_turn`
- [ ] Background thread stops cleanly on `stop()`

**governance.py**
- [ ] `GovernanceEngine` has `registry: AgentRegistry | None` field
- [ ] blocked_ops → BLOCK with confidence=1.0 (unconditional)
- [ ] restricted_ops → action capped at `escalate_to` value
- [ ] confidence_floor applied after all other routing
- [ ] GovDecision `source` field reflects `"agent_profile:{slug}"` when profile active
- [ ] Existing behavior unchanged when `registry=None`

**dashboard**
- [ ] `GET /api/agents` endpoint returns agent list
- [ ] Agent column visible in decisions table
- [ ] Active-agent badge shows in session panel

**tests**
- [ ] `tests/test_agent_registry.py` exists
- [ ] All 5 test cases present
- [ ] `pytest tests/test_agent_registry.py -v` passes with zero failures

**integration**
- [ ] `ruff check src/` passes (no lint errors)
- [ ] `mypy src/stream_manager/` passes (or pre-existing errors only)

**If any check fails:** fix before committing. Do not carry lint/type errors forward.

---

## Definition of Done

Every message through `GovernanceEngine.evaluate()` has an associated agent profile
(even if "unknown"). The JSONL tail worker is live and updates the registry as
Claude Desktop switches agents. The dashboard shows which agent sent each decision.

Commit message:
```
feat(agent-registry): FR-AR-6/7 — agent registry + JSONL tail + per-role governance
```
