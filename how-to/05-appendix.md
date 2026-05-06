# Appendix — Future Additions

Planned and backlogged features as of v1.8. Severity follows the convention in `docs/v1.9-backlog.md`.

---

## v1.9 backlog (active)

### 🟡 Haiku fastpath confidence floor

**Status:** Investigation item. Lever wired (v1.8) but dormant under production load.

**Background:** v1.8 wired content-detection (`is_ambiguous_block` / `is_hitl_synthesis`) at the pre-routing call site. Haiku is correctly invoked first on L4 ambiguous-block content. However, Haiku consistently returns confidence ≥ 0.70 even on destructive-content prompts — so `BRIDGE_L4_FALLBACK_CONFIDENCE` floor (0.70) is never crossed. Sonnet retry fire rate = 0% in ship-gate soak.

**Options under investigation:**

| Option | Description | Risk |
|---|---|---|
| Lower floor to ~0.50 | Reduce `BRIDGE_L4_FALLBACK_CONFIDENCE` | May always-fallback if Haiku returns 0.50–0.70 uniformly |
| HITL-synthesis-only Haiku path | Restrict ambiguous-block detection to HITL trigger (more deterministic than content heuristic) | Narrower coverage |
| Verdict-based fallback | If Haiku returns BLOCK on ambiguous-block, auto-retry Sonnet for second opinion | More predictable trigger |
| Expand heuristic | Broaden `is_ambiguous_block` to content Haiku genuinely finds borderline | Requires empirical confidence-distribution study |

**Files:** `src/stream_manager/cli_governance.py` (floor constant), `src/stream_manager/governance.py` (heuristic), `tools/soak_driver.py` (corpus). Alignment-eval `--ci-gate` re-run required after any change.

---

### 🟢 CLI pool sizing >2

**Status:** Carry-forward. Not promoted in v1.7 or v1.8. Deferred pending confidence-floor investigation result.

**Background:** Current default `--cli-pool-size 2` covers all tested load. Higher pool sizes may reduce burst-latency under concurrent session load. No production evidence yet.

---

### 🟢 PPP audit harness (Provenance Probe Protocol)

**Status:** Carry-forward. Blocked pending sync-comms v1.0 HITL panel landing.

**Background:** Audit harness to trace governance decision provenance through the full Desktop → SM → CLI chain. Useful for post-hoc review of INTERVENE and BLOCK decisions.

---

## Near-term design extensions

### Learn Mode v1.4+

Items deferred out of v1.3 scope:

| Feature | Notes |
|---|---|
| Auto-resolve (silent HITL skip at high confidence) | Requires confidence floor + audit strategy decision |
| Multi-user disambiguation | `owner_user` scoping per pattern; requires multi-user signal |
| Cross-session pattern propagation | Under existing HITL-gated cross-session flag (Q3 OQ5) |
| Toast / undo affordances | UX: operator opt-in card for pattern visibility |

### Sync-comms v1.0

Gate-and-wait verdict + full bidirectional `desktop_command` (HMAC-signed) + Session Mirror frame + N isolated session brains with HITL-gated cross-session learning. Design frozen. Implementation carries into v1.9+.

### Agent registry expansion

- Richer role profiles beyond Developer / Reviewer / Tester / Unknown
- Confidence-weighted pattern inference for faster role resolution on new agents
- Per-agent scope escalation history persistent across sessions

### Multi-project governance

- SM currently governs one project repo (the Desktop's active project context)
- Multi-project: separate `gov.db` per project, shared agent registry across projects

---

## Architecture extension points

| Layer | Extension hook |
|---|---|
| L0 static rules | `src/stream_manager/decision_graph.py` — add new hardcoded rule |
| L1–L3 patterns | `src/stream_manager/governance.py` — add pattern to evaluation pass |
| L4 routing | `src/stream_manager/model_router.py` — change Haiku/Sonnet routing logic |
| Learn Mode categorizer | `src/stream_manager/learn_categorizer.py` — swap Sonnet for different model |
| Decay ladder | `src/stream_manager/decay.py` — adjust day thresholds or demotion behavior |
| Dashboard | `dashboard/server.py` — add new SSE event type or REST endpoint |
| Bus schema | `src/stream_manager/message_bus.py` — schema changes require a migration story |

---

## ADR index

| ADR | Topic |
|---|---|
| ADR-5 | Governance latency budget (p50/p95/hard-timeout across all versions) |
| ADR-9 | HITL as a switchable mode |
| ADR-14 | CliPool (Task J) design |
| ADR-15 | WireCLI integration |
| ADR-17 | Sync-comms gate-and-wait design |
| ADR-19 | Learn patterns audit/canonical two-table split |

Full ADRs in [`docs/adr/`](../docs/adr/).
