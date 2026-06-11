# Sonification as Derived Escalation Confirmation Layer

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea WILDCARD-5; boldness STRETCH; refute verdict CONSTRAIN; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

The HITL pending badge pulses visually, but in a busy environment (multiple monitors, terminal running in background), an operator might miss a visual pulse. Worst case: a high-severity escalation (negative regression, static-rule fire, governance variance alert) auto-foregrounds a frame, but the operator doesn't notice because they're looking at another screen. The current audible-cue toggle (FR-UI-9) is on/off binary; there is no auditory grammar that distinguishes 'advisory HITL' from 'blocker fire' from 'variance alert'. Operators have to learn the UI badge color, but in a high-stress incident, muscle-memory is everything.

## Proposal

Wire a presentation-layer sonification controller that emits distinctly-designed sounds **only when a badge from the ESCALATION_TABLE appears** (never as a standalone signal path). The sound grammar is keyed 1:1 to existing escalation types in escalation.js:

- **new_pattern / low_confidence (badge-in-place):** gentle rising tone (2-note major third, 200ms), repeats every 8s until dismissed.
- **governance_variance_alert (badge-in-place):** three-note warning arpeggio (minor 6th, falling, 300ms), repeats every 4s.
- **desktop_pause (foreground):** double-tap rhythm (two staccato tones, 100ms each, 150ms apart), repeats every 3s until acknowledged.
- **governance_negative_regression / static-rule (foreground):** sustained bass tone (sub-100Hz rumble + mid-frequency chirp, 1s), repeats every 3s until acknowledged.

Sounds are driven by the existing SSE escalation event handler in sse.js: when an escalation event arrives and passes the badge/foreground gate, SonificationController is invoked to play the corresponding sound. Sound emission is **coupled to badge visibility**--if the badge has been cleared, sound stops. This preserves M5 (paired label+color; sound is confirmation, not signal). Volume is configurable per escalation type (settings panel toggle). Operators can upload custom sound packs (YAML config + audio files), but defaults ship pre-tuned. This is a **premium UX feature** that turns escalation into a multisensory signal without bending the MUST constraint that visual badges remain the primary governance signal.

## Operator value

Eliminates missed escalations due to visual inattention; builds muscle-memory responses (operator hears the bass rumble, verifies the CRITICAL badge, instantly knows 'regression hit'); transforms dashboard from a silent web app into a multi-sensory command center with **sound as confirmation, not as signal**; strong premium operator workflow signal.

## Surfaces touched / added

- dashboard/ui-next/src/lib/components/SonificationController.svelte (new; manages sound playback, reactively subscribed to ESCALATION_STORE, emits sounds only when badges are visible)
- dashboard/ui-next/src/lib/stores/sonificationState.ts (new store: volume levels per escalation type, mute state, custom sound pack path, per-escalation toggle, UI-side only)
- dashboard/ui-next/public/sounds/ (new dir: audio files for each escalation level; .mp3 or .ogg, ~200-500ms each, pre-tuned sonically coherent defaults)
- dashboard/ui-next/src/lib/config/sonification-defaults.yaml (new; sound-pack definition: maps escalation.js trigger type -> sound file + volume + repeat interval)
- dashboard/ui-next/src/lib/sse.js (additive wiring in SSE handler: when ESCALATION_STORE emits a new badge, invoke SonificationController.play(escalation_type); no logic change to escalation gates)
- dashboard/ui-next/src/App.svelte (wire SonificationController into the root layout as a subscriber to ESCALATION_STORE)
- docs/ui-next-sonification-spec.md (new; design spec: sound grammar, M5 compliance statement, cassette coverage rationale)

## Feasibility

High. The sonification layer is a pure presentation overlay on top of the existing ESCALATION_TABLE contract. It requires no new bus envelopes, no new governance flags, and no changes to escalation.js or sse.js logic -- only additive wiring in the existing SSE event handler. Sound files are static assets; a browser Web Audio API or &lt;audio&gt; tag playback suffices. No latency-critical path touched. The hard dependency is that SonificationController is reactive to the ESCALATION_STORE (Svelte store) -- when an escalation enters, sound plays; when it's dismissed, sound stops. This is deterministic and auditable: the sonification timeline can be cassette-recorded if needed for debugging.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- sonification controller is dashboard ui-next EXPERIMENTAL spike only; zero certPortal coupling.
- **Polarity (G2):** PASS -- SM does not monitor its own session (project_slug NOT IN {streamManager} AND session_id != self); sonification applies to monitored non-SM sessions only.
- **ADR-18 MUST floor:** HARD CONSTRAINT MET (ADR-18 M5 compliance). Sonification is keyed entirely to escalation.js ESCALATION_TABLE and emits *only when* a badge appears. Sound is a **derived presentation layer** (confirmation), never an independent signal path. The escalation badge remains the visual primary; sound reinforces badge presence without enabling an operator to rely on sound alone. This is architecturally distinct from the original proposal (which mapped escalation_type -> sound directly as independent signals). Post-constraint: sounds are keyed to escalation.js trigger types, not new envelope kinds. The M5 guarantee (paired label+color badge is always the primary) is preserved -- sound plays *when the badge is visible* and stops *when the badge clears*.
- **Frozen-surface note:** Zero FROZEN surfaces touched. escalation.js (FROZEN per ADR-18) is read-only; SonificationController wires into the existing SSE handler (EVOLVING per sse.js status) as an additive subscriber pattern. No governance.py, message_bus.py, cli_governance.py, model_router.py, or cli_pool.py modifications.
- **New-envelope note:** No new bus envelope kind introduced. Sonification events (sound-emitted timestamps, volume levels) are **presentation-only** and do not traverse the message bus. If future audit or compliance requires recording when sounds were emitted, that is a cassette-recorder enhancement on the browser-side SonificationController store (additive, not a new envelope schema). No soak_driver.py or cassette_record.py changes required at ship; future coverage is advisory.

## Grounding

- C:\Users\SeanHoppe\vs\streamManager\docs\adr\ADR-18-mvp-surface-freeze.md (L41-L72 FROZEN/EVOLVING/EXPERIMENTAL classification, L62 metadata-only extensions, Amendment E context; refuter constraint rooted here)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\ui-next\src\lib\escalation.js (L69-L120 ESCALATION_TABLE, FOREGROUND_ELIGIBLE, BADGE_IN_PLACE_TYPES; sonification keyed to these types only)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\ui-next\src\lib\sse.js (L44-L100 ESCALATION_ALLOWLIST, M2 foreground gate, existing SSE handler pattern; where sonification subscriber wires in)
