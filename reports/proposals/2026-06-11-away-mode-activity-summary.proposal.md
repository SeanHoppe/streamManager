# Away/Calm Mode + Activity Summary Replay for SSE Operators

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (flywheel) 2026-06-11; idea COMFORTS-4; boldness STRETCH; refute verdict SHIP-PROPOSAL; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Operator steps away (15--60 min) during a live governance-monitoring session. Dashboard continues to receive SSE events and HITL rows queue up silently. When operator returns, Frame A (Interactive Sessions feed, dashboard/static/index.html:2306) has scrolled off-screen; Frame B agents are no longer pinned. Operator has no summary of what happened during absence; must scroll through event log to reconstruct. Real escalations (governance_negative_regression, desktop_pause, static_rule_fire) that fired during absence are lost or buried. The ambient monitoring experience is the goal (INTENT.md:79), but the UI lacks an Away posture that decouples presence from session continuity.

## Proposal

Introduce optional Away/Calm mode toggle (pill, header, alongside Learn Mode toggle at dashboard/static/index.html:2248) that persists to localStorage under key sm.away-mode:{sessionId}. When enabled: (1) SSE event stream (dashboard/server.py /events endpoint) continues; client-side buffering stores incoming events in AWAY_BUFFER array; event counter badge shows "X new events" in muted gray instead of rendering live. (2) HITL pending rows (dashboard/static/index.html:3192+) render in OBSERVING mode (slate palette, no pulsing border) by default, even when HITL is ON (FR-UI-6 permits this). Rows are queued but visually demoted. (3) New Activity Summary modal/overlay template (dashboard/static/index.html modal stack) pops on first interaction after Away mode was on; displays: timeline of escalation events (action IN [BLOCK, INTERVENE] or escalation_type field set) from past 60 min, list of new agents (first_seen during Away period), count of HITL pending rows queued, timestamp of Away period start/end. Two buttons: "Catch Up" (dismisses summary, clears buffer, resumes live) and "Review Pending" (jump to HITL queue frame). Keyboard: Escape dismisses. (4) If any escalation event (EVENT_FOREGROUND_TYPES at dashboard/static/index.html:4267) fired during Away mode, summary auto-shows on return; real escalations break through calm posture. Activity Summary filter logic is domain-agnostic: uses generic escalation classification (action field BLOCK/INTERVENE or escalation_type presence), NOT hard-coded envelope kind names, to preserve monitoring posture across future envelope schema extensions (constraint binding per adversarial gate). No new bus envelope schema required; leverages existing decision + bus event structure. No changes to FROZEN surfaces (governance.py, message_bus.py, cli_governance.py, model_router.py, cli_pool.py).

## Operator value

Solves the "step away and come back to chaos" problem without disrupting the calm-monitor goal. Operator regains context without scrolling or reconstructing. Auto-escalation-on-return ensures true alarms are never missed. Reduces context-loss anxiety in long sessions. Improves UX for operators juggling multiple tasks (laptop-monitor-first workflow). Accelerates re-onboarding after pause; pending count + escalation timeline + new-agent roster == situational awareness in one glance.

## Surfaces touched / added

- dashboard/static/index.html -- new Away/Calm toggle pill in header (id=awayBtn, alongside lmToggle at line 2248), in-memory AWAY_BUFFER array populated when Away mode on, render event counter badge (X new in muted color), new Activity Summary modal template (escalation timeline, new agents list, pending count), keyboard listener Escape-to-dismiss, logic to auto-show summary if escalation event was buffered during Away
- dashboard/server.py -- no new endpoints needed; existing /events SSE stream continues; client-side buffering only (future: optional /api/sessions/{id}/activity-summary?since=<timestamp> endpoint to backfill replay for sessions restarted mid-away, but not required v1)
- localStorage -- persist Away mode state per session under key sm.away-mode:{sessionId} (pattern matches existing Learn Mode persist at dashboard/static/index.html:5155)

## Feasibility

FEASIBLE. Builds on existing SSE stream (dashboard/server.py lines 1-16 + /events endpoint), localStorage patterns (dashboard/static/index.html:4858+), modal overlay precedent (Learn Mode + HITL queue modals exist). Trivial in-memory buffering; no FROZEN surface changes required. Activity Summary filter logic is localized client-side JavaScript (no backend schema changes). ADR-18 MUSTs respected: 3-frame presence preserved; escalation-only foreground intact; paired label+color badges (OBSERVING mode uses slate palette + text label); OBSERVING state for HITL rows per FR-UI-6 (example at dashboard/static/index.html:1983, 3246); domain-agnostic filter (generic action/escalation_type, no hardcoded envelope kinds); no new bus envelope kind => no cassette/soak coverage needed.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- no new certPortal coupling, pure client-side feature within dashboard UI spike (ui-next scope)
- **Polarity (G2):** PASS -- targets non-SM sessions only (Away mode filtered by project_slug per sm.away-mode:{sessionId} per-session storage; SM self is excluded by default via INTENT.md session-source exception rule 2, BRIDGE_SM_SELF_SESSION_ID); no self-monitoring of SM
- **ADR-18 MUST floor:** PASS -- respects all ADR-18 MUSTs: 3-frame presence inviolate (Away mode is UI feature, not frame layout); escalation-only foreground (real escalations in EVENT_FOREGROUND_TYPES break through calm at dashboard/static/index.html:4267); paired label+color badges (OBSERVING mode uses slate text-dim/text-ui palette + OBSERVING label); HITL rows render in OBSERVING (FR-UI-6 observing state, not a new mode); domain-agnostic (Activity Summary uses action IN [BLOCK,INTERVENE] or generic escalation_type field, never hardcoded governance_decision or project-specific envelope kinds); no new bus envelope => no cassette/soak coverage needed
- **Frozen-surface note:** Proposal touches NO FROZEN surfaces. Governance.py, message_bus.py, cli_governance.py, model_router.py, cli_pool.py remain untouched. Dashboard/static/index.html and dashboard/server.py are EVOLVING per INTENT.md:128; this proposal adds feature to EXPERIMENTAL ui-next spike surface.
- **New-envelope note:** NONE -- proposal does not introduce a new bus envelope kind. Reuses existing decision + bus event structure (action, escalation_type fields already in rows). No cassette_record.py or soak_driver.py changes required.

## Grounding

- C:/Users/SeanHoppe/vs/streamManager/INTENT.md:79 -- ambient monitoring intent
- C:/Users/SeanHoppe/vs/streamManager/INTENT.md:128 -- hot zones EVOLVING surfaces (dashboard/server.py, dashboard/static/index.html)
- C:/Users/SeanHoppe/vs/streamManager/dashboard/static/index.html:2248 -- Learn Mode toggle precedent (header pill)
- C:/Users/SeanHoppe/vs/streamManager/dashboard/static/index.html:2306 -- Frame A Interactive Sessions title
- C:/Users/SeanHoppe/vs/streamManager/dashboard/static/index.html:4267 -- EVENT_FOREGROUND_TYPES escalation set
- C:/Users/SeanHoppe/vs/streamManager/dashboard/static/index.html:5155 -- Learn Mode localStorage persist pattern (sm.settings key)
- C:/Users/SeanHoppe/vs/streamManager/dashboard/static/index.html:3192 -- HITL.pending array definition
- C:/Users/SeanHoppe/vs/streamManager/dashboard/server.py:1-36 -- FastAPI SSE + WAL bus structure (no new endpoint needed)
- C:/Users/SeanHoppe/vs/streamManager/REQUIREMENTS.md:1 -- project governance architecture (session.project_slug filter)
- C:/Users/SeanHoppe/vs/streamManager/CLAUDE.md:32-44 -- polarity self-exclude rule (session_id + project_slug dual-key read/write split)
