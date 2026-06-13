# Quick-Filter Presets: Named Settings Shortcuts for FR-UI-9

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (ux) 2026-06-11; idea COMFORTS-2; boldness STRETCH; refute verdict SHIP-PROPOSAL; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Operators manually adjust the confidence-floor slider (0.0--1.0), toggle HITL mode (SYNC/ASYNC), and configure sync_timeout and pause_detection every time they switch operational phases (paranoid code-review vs. daily monitoring). No persistence across browser-tab close; no discoverable named presets like 'code-review mode' (high confidence 0.95, SYNC on) or 'training wheels' (low confidence 0.35, ASYNC on). Slider is granular but not learnable; operators repeat the same dial turns session after session.

## Proposal

Add a preset carousel in the FR-UI-9 settings panel exposing four pre-baked presets (PARANOID=0.95 confidence+SYNC+120s timeout+pause ON, STANDARD=0.60+SYNC+60s+ON, TRUST=0.35+ASYNC+30s+OFF, AUDIT=0.99+SYNC+300s+ON) plus custom-preset support. Operators click a preset button; all 4 settings apply instantly, persist to the session WAL record via the existing `/api/sessions/{session_id}/settings` POST endpoint, and emit `dashboard_settings_changed` for audit. Custom presets: operator adjusts sliders manually, clicks 'Save as preset', types a name (e.g. 'my-strict-ml-review'), and it's persisted in a new `settings_presets` table (session_id, preset_name, config_json, created_at). Presets are per-session-lineage (keyed on project_slug+session_id so they persist across multiple runs on the same project). Bonus: a header pill shows the active preset name (or 'custom' if hand-tuned). No preset constrains operator freedom; sliders remain fully mutable, presets are navigation shortcuts only. Implementation spans: (1) new `settings_presets` table in message_bus.py schema, (2) new load_presets() / save_preset() / apply_preset() methods on MessageBus, (3) new POST/GET `/api/sessions/{session_id}/presets` endpoints in dashboard/server.py, (4) preset carousel UI component + state management + click handlers in dashboard/ui-next (Svelte). Keyboard shortcuts possible in v2 (Alt+1=PARANOID, Alt+2=STANDARD, etc.).

## Operator value

Operators stop mid-session slider fiddling and mode-toggling; they click a 4-letter preset matching the current phase (code-review = PARANOID, daily triage = STANDARD, fast prototyping = TRUST, pre-ship audit = AUDIT). Dramatic speed-up for multi-session workflow context-switching. Custom presets encode team or project norms ('certPortal strict mode' = illustration example only; preset_name is operator-supplied text, never hard-coded vocabulary). Keyboard shortcuts in v2 unlock power-user velocity. Immediate payoff on pair-programming and audit-before-ship workflows.

## Surfaces touched / added

- src/stream_manager/message_bus.py (new CREATE TABLE settings_presets schema: session_id, preset_name, config_json, created_at; new load_presets(session_id) / save_preset(session_id, preset_name, config_json) / apply_preset_values() helper methods)
- dashboard/server.py (new GET /api/sessions/{session_id}/presets endpoint returning list of {preset_name, config_json}; new POST /api/sessions/{session_id}/presets endpoint accepting {preset_name, config_json} to persist custom preset; wiring into apply_preset handler that calls bus.apply_preset_values and reloads settings)
- dashboard/ui-next/src/lib/stores/settings.js (preset context: track active_preset_name, expose applyPreset(name) function to patch all 4 settings + emit dashboard_settings_changed with preset metadata)
- dashboard/ui-next/src/lib/components/SettingsPanel.svelte (new preset carousel or radio-group showing [PARANOID, STANDARD, TRUST, AUDIT] + custom presets loaded from /api/sessions/{session_id}/presets; 'Save as preset' button + text input modal; preset click handler invokes applyPreset + reloads UI)
- dashboard/ui-next/src/lib/components/HeaderBar.svelte (optional: header pill shows active preset name or 'custom' if hand-tuned; derived from settings.active_preset_name store)

## Feasibility

FEASIBLE on existing `sessions` table + `set_session_settings()` WAL mechanics + `/api/hitl/settings` endpoint family. The new `settings_presets` table is a simple append-only schema (4 columns: session_id, preset_name, config_json, created_at) with no foreign-key enforcement needed (presets are advisory shortcuts, not constraints). MessageBus.load_presets() is a standard SELECT by session_id; save_preset() is INSERT + return; apply_preset_values() is a JSON-merge helper that coerces the preset config and patches the settings store (identical to existing manual slider adjustments). Dashboard endpoints are standard CRUD on the new table. Frontend patches happen inside existing settings.js store and SettingsPanel.svelte component -- no structural rearchitecture. Cascading delete on session close is optional (presets can accumulate; they are rows only, not memory). Zero impact on existing settings flow or HITL queue.

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- Presets are domain-agnostic 4-tuples (confidence_floor, hitl_mode, sync_timeout_sec, pause_detection) keyed on session_id + project_slug. No certPortal vocabulary baked in. The custom preset naming example 'certPortal strict mode' is documentation illustration only; preset_name is operator-supplied free text, never hard-coded monitored-project identity.
- **Polarity (G2):** PASS -- Session_id-keyed presets do not enable SM self-monitoring. Presets stored in the same WAL bus as all other session state, scoped to individual sessions. Cleanup logic (if added later) MUST exclude the SM-self session (session_id != self) per the existing SM-non-SM partition discipline.
- **ADR-18 MUST floor:** PASS -- ADR-18 UI MUSTs inviolate: (1) 3-frame presence: presets are in the settings panel (Frame B), no escalation rendering; (2) escalation-only foreground: header pill is ambient, never red/urgent; (3) paired label+color badges: preset buttons are plain text labels (no color-alone signals), 'Save as preset' modal is labeled; (4) HITL gate absolute: presets do not bypass the existing HITL SYNC/ASYNC gate, they just set the mode value; (5) domain-agnostic: 4-tuple is pure operators settings, no project vocab; (6) a11y axe gate: preset buttons are semantic <button> with aria-label, custom-preset modal has <label> + text input with proper focus mgmt, keyboard tab-order flows through carousel; (7) latency budget: load_presets() is a single SELECT by session_id with index, apply_preset_values() is a JSON merge (sub-millisecond), no new polling or async wait; (8) non-goals preserved: presets are NOT an IDE, NOT multi-tenant, NOT a multiplexer, NOT persisting across browser tabs (within same session only).
- **Frozen-surface note:** No FROZEN surface touched. governance.py, message_bus.py (beyond additive schema line), cli_governance.py, model_router.py, cli_pool.py remain untouched. The settings_presets table is an additive extension to the message_bus schema, not a modification of existing tables. Existing `get_session_settings()` and `set_session_settings()` methods remain unchanged; presets call them internally and are composable with manual slider adjustments.
- **New-envelope note:** No new bus envelope kind introduced. Presets emit the existing `dashboard_settings_changed` event (already wired in dashboard/ui-next and message_bus.py). When a preset is applied, the apply_preset_values handler calls set_session_settings() internally, which already emits dashboard_settings_changed on the message_bus. No cassette_record.py or soak_driver.py changes required -- presets are session state, not governance decisions, not RL episodes.

## Grounding

- C:\Users\SeanHoppe\vs\streamManager\src\stream_manager\message_bus.py:52-58 (existing sessions table schema; presets table modeled identically)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\server.py:2210-2259 (existing /api/sessions/{session_id}/settings GET/POST endpoints; presets endpoints follow same pattern)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\ui-next\src\lib\stores\settings.js:1-196 (existing FR-UI-9 settings store; preset state management integrates via patch() function)
- C:\Users\SeanHoppe\vs\streamManager\docs\adr\ADR-18-mvp-surface-freeze.md:41-95 (ADR-18 MUST-floor constraints verified; no FROZEN surface demotion required)
- C:\Users\SeanHoppe\vs\streamManager\docs\KingModePrompt.txt:1-40 (persona: bespoke, asymmetric, anti-generic design)
