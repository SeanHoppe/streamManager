# StreamManager — Viable Product Roadmap

Phases are **strictly linear**. Each phase depends on the previous.
Execute phases one at a time. At each **STOP + VERIFY** checkpoint,
confirm all criteria before proceeding.

## Phase Index

| # | Phase | FR Refs | Gate |
|---|-------|---------|------|
| [0](prompts/phase-0.md) | Land uncommitted changes | — | All prior work on main |
| [1](prompts/phase-1.md) | Agent Registry + JSONL Tail | FR-AR-6, FR-AR-7 | Per-role governance active |
| [2](prompts/phase-2.md) | HITL Core Loop | FR-HITL (§4.9) | Sync/async gating in engine |
| [3](prompts/phase-3.md) | HITL UI | FR-HITL (§4.9) | Dashboard queue + annotate |
| [4](prompts/phase-4.md) | Model Routing | §5.6 NFR-M1–M5 | L0–L4 dispatch wired |
| [5](prompts/phase-5.md) | FR-OG-7 Maturity Ring | FR-OG-7 | certPortal ring governance live |
| [6](prompts/phase-6.md) | Dashboard Completeness | — | Ship gate |

## Minimum Viable Product

Phases 0–3 = **MVP**. SM has role-aware governance + human-in-the-loop control.

Phases 4–6 = **full product**. Cost-optimized routing + certPortal alignment + complete UI.

## Execution Rules

1. Execute one phase prompt at a time — do not skip ahead.
2. At each `STOP + VERIFY` block, pause and audit every criterion.
3. If any criterion fails, fix before moving to next phase.
4. Each phase ends with `git commit + PR + merge to main`.
5. Do not begin a new phase in the same session as the previous unless
   verification is complete and the user confirms.

## Ship Sequence

```
Phase 0  (minutes)     — git hygiene
Phase 1  (2–3 sessions) — agent identity; BLOCKS everything downstream
Phase 2  (2 sessions)   — HITL loop; needs agent identity from Phase 1
Phase 4  (1 session)    — model routing; parallel-safe with Phase 2
Phase 3  (1 session)    — HITL UI; needs Phase 2 API endpoints
Phase 5  (1–2 sessions) — OG-7; needs Phase 1 + project_context
Phase 6  (1 session)    — dashboard polish; integrates all above
```

## Key Files

- `REQUIREMENTS.md` — authoritative spec (v1.6)
- `src/stream_manager/agent_profiles.yaml` — role definitions source of truth
- `src/stream_manager/governance.py` — decision engine (hot zone)
- `src/stream_manager/message_bus.py` — WAL bus + schema
- `dashboard/server.py` — FastAPI dashboard backend
- `dashboard/static/index.html` — dashboard frontend
