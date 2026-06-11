# What Changed Digest: page-focus synthesis overlay

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (flywheel) 2026-06-11; idea MONITOR-3; boldness SAFE; refute verdict SHIP-PROPOSAL; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Operator returns from 5 min backgrounding. They scan Frame A (decision feed, max 300 rows). Did something subtle shift? Agent profile change? Confidence trending? Learn-mode bias activated? The feed is a firehose; glance-readability is zero. A passive monitor cannot synthesize "here's the story since you left."

## Proposal

On dashboard page-focus (operator tabs back to SM window), emit a one-time "What Changed" digest card at the top of Frame B (Sub-Agents) as a collapsible banner. Synthesized from SSE events already received while backgrounded. Content sections: (a) New agents (role badge + first activity timestamp). (b) Agent scope changes (e.g., developer GUIDE->INTERVENE; before/after scope box). (c) Confidence delta (rolling mean confidence 5min ago vs. now; compact sparkline). (d) Learn-Mode activations (N patterns applied as pre-fill bias; pattern hash + rationale). (e) HITL override tally (N new human overrides; tally by action type, pie chart). (f) Escalation summary (N new escalations; pie of types). Each section expands inline or opens detail tray on click. Dismissing the banner updates localStorage timestamp `dashboard_last_digest_shown`. Token budget: <= 200. No new API endpoint. No new bus envelope. Synthesizes from governance_decision envelopes + eventsStore + localStorage-tracked timestamps already available in Svelte stores.

## Operator value

Operator catches up in 3 seconds instead of 3 minutes. Passive monitoring becomes intentional: they see async signal, then actively drill if something looks off. Eliminates manual "what did I miss?" re-scan (reported gap: 3 seconds glance vs 3 minutes async catch-up browsing). Fits monitor-first laptop UX (calm-tech discipline: signal is async, foreground is escalation-only per ADR-18 M2).

## Surfaces touched / added

- dashboard/ui-next/src/lib/components/WhatChangedDigest.svelte (new component; renders on page-focus with synthesized stats from already-received SSE events + localStorage timestamps)
- dashboard/ui-next/src/App.svelte (track page backgrounding via visibility API; emit internal store action on focus-return; import WhatChangedDigest and mount in Frame B template)
- dashboard/ui-next/src/lib/sse.js (no change -- uses existing governance_decision envelopes + named bus events already fan-outted via busEvents)
- dashboard/ui-next/src/lib/pollers.js (no change -- agents poller already feeds agentsStore with role + scope data)
- dashboard/ui-next/src/lib/stores/session.js (optional: add internal digest-tracking store if explicit fine-grained timestamp tracking needed; baseline = localStorage-only)
- dashboard/server.py NO CHANGE (digest synthesizes from already-received SSE events + localStorage-tracked timestamps; no new endpoint needed)
- dashboard/ui-next/src/lib/components/FrameB_SubAgents.svelte (import and render WhatChangedDigest banner if digest store indicates new data)

## Feasibility

HIGH. SSE contract delivers governance_decision envelopes (decisions + patterns parsed into Svelte stores via sse.js). Named bus events (hitl_sync_queued, governance_variance_alert, etc.) already fan-out via busEvents. Learn-Mode pattern activation counts available from eventsStore (marked with event_type; pattern hashes in matching_hash). HITL override pattern = decision rows with confidence > 0.75 + promoted action vs baseline mode (readable from decisions store). Visibility API (document.hidden, visibilitychange) is standard browser API; localStorage is standard Web Storage. Token constraint (<=200) is achievable: hash(6) + count(2-digit) + sparkline(emoji, ~10 chars) + section headers(~50 chars) = well under budget. localStorage update on dismiss (dashboard_last_digest_shown) is trivial atomic write.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS (proposal introduces zero new certPortal coupling; digest UI-next is domain-agnostic; all content derives from /api/agents, SSE streams, and localStorage timestamps; no monitored-project vocabulary baked in)
- **Polarity (G2):** PASS (digest does not make SM monitor/govern its own session; it operates client-side on localStorage + page-visibility API, synthesizing from SSE buffers already scoped to NON-self sessions upstream, per M15 in FrameB_SubAgents.svelte + App.svelte defaults; no new endpoint required; no SM-self sweep risk)
- **ADR-18 MUST floor:** PASS (M1: digest is collapsible banner in Frame B; all three frames remain present, calm. M2: page-focus event triggers banner show, not escalation store entry; no auto-foreground (visibility API is a data signal, not a foreground rule). M3: uses existing role badge + pattern hash/rationale + action-type tally -- paired label+color per Frame B contract. M13-M16: content derives from /api/agents, SSE streams, localStorage; no role literals beyond generic schema. M17: zero-latency synthesis (in-memory Svelte store reads, timestamps written during SSE ingestion). No new query window; no API call)
- **Frozen-surface note:** NONE. Proposal does not touch FROZEN surfaces (governance.py, message_bus.py, cli_governance.py, model_router.py, cli_pool.py). Uses existing governance_decision envelope (FROZEN per ADR-18 Amendment B L286-341, minted v10 P4 B' 2026-05-12). No new envelope kind introduced; no amendment required.
- **New-envelope note:** NONE. Digest synthesizes from already-received SSE events (governance_decision envelopes + named bus events); no new envelope kind created. Existing cassette_record.py + soak_driver.py coverage of governance_decision + audit.* + governance_variance_alert envelopes is sufficient (no cassette extension required).

## Grounding

- INTENT.md L75-87 (UI/HITL principles: monitor-first, escalation-only foreground, paired label+color badges)
- ADR-18-mvp-surface-freeze.md L1-100 (FROZEN surface classification, Rule 1 MVP freeze)
- ADR-18-mvp-surface-freeze.md L286-341 (Amendment B: governance_decision FROZEN envelope)
- dashboard/ui-next/src/App.svelte L1-100 (M1-M18 governance invariants; M15 self-exclude, M2 escalation discipline, M18 post-hoc observability)
- dashboard/ui-next/src/lib/components/FrameB_SubAgents.svelte L1-50 (Frame B contract: M13 domain-agnostic, M16 no monitored-project vocab, M2 no auto-foreground)
- dashboard/ui-next/src/lib/sse.js L1-150 (ESCALATION_ALLOWLIST, M2 foreground eligibility, governance_decision envelope subscription)
- docs/adr/ADR-18-mvp-surface-freeze.md amendment 2026-05-12 (governance_decision envelope FROZEN with BRIDGE_RL_LOGGER_ENABLED opt-in; zero-cost without subscribers)
