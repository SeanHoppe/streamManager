# Coverage Analyzer dashboard widget (Frame D sub-section)

**Status:** Proposal (EXPERIMENTAL spike) -- NOT authorized to edit FROZEN surfaces.
**Source:** sm-ux-propose (flywheel) 2026-06-11; idea SOAK-4; boldness SAFE; refute verdict SHIP-PROPOSAL; effort M.
**Scope:** a written proposal only (Rosetta /report-fixes proposal-half). Shipping requires a normal v2.x cycle frame + the noted ADR amendments.

## Problem

Cassette composition is static and never updated to match real operator traffic. If a cassette was tuned to 50 routine + 5 L2/L3 + 5 L4 but real sessions spend 30% time in L4, Tier 1 cassette replay under-tests L4 and misses regressions. Section 5.2 of soak-for-non-sm-sessions.md: 'Polarity in the synthetic + cassette paths is untested by construction.' Operators have no visibility into whether cassette composition still matches their real workload.

## Proposal

Introduce a Coverage Analyzer dashboard widget in Frame D (opt-in visibility sub-section). The analyzer compares two distributions: (A) cassette composition read from tests/fixtures/soak_cassette_*.jsonl, parsed via _KIND_TO_LAYER mapping (cassette_record.py:79), computed as % ALLOW (layer 0), % L2/L3 (layer 2), % L4 (layer 4), % learn_dialogue (layer 0); (B) live non-SM session composition queried from gov.db.decisions, filtered via project_slug NOT IN {streamManager} AND session_id != self (matching server.py:294-308 polarity guard), sampled over rolling window (e.g. last 1000 decisions). Render a side-by-side bar chart (cassette vs live) with absolute deltas highlighted. When cassette-ALLOW is 83% but live-ALLOW is 60%, surface an amber warning: 'Cassette under-represents L2/L3 by 23%. Tier 1 replay may miss regressions in escalation paths. Recommend: update cassette via Tier 2 (cassette_record.py) or upload a live fixture (SOAK-2).' When operators upload live fixtures (SOAK-2 separate), re-bin that fixture and surface 'Fixture Coverage' comparison (cassette vs uploaded fixture). Backend: three new FastAPI GET endpoints (/api/soak/coverage/cassette, /api/soak/coverage/live, /api/soak/coverage/fixture/<id>) with cassette parsed via jsonl read + layer histogram, live parsed via SQL aggregation, fixture via same jsonl path. Frontend: Svelte components (CoverageAnalyzer parent, CoverageComparisonChart bar chart reusing Tailwind, CoverageWarnings amber/red alert block following Frame.svelte flag pattern:96-98 paired color+text). Tool integration: soak_driver.py add --analyze-coverage flag to emit JSON summary of band distribution post-soak for downstream dashboard use (no new bus envelope, reuses existing governance_decision schema). All surfaces domain-agnostic (no project_slug/JOB-ID hardcoding); filtering is data-driven (SQL filter, not vocab).

## Operator value

Operators on monitor-first workflow gain concrete visual signal into cassette decay -- the most common Tier 1 failure mode. Current: run soak_driver.py, see p95 latency, have no way to know if cassette is representative of real workload. Coverage Analyzer surfaces this immediately: 'Cassette ALLOW 83% but live ALLOW 60%' is actionable without manual curation or folk wisdom. For multi-workload projects (certPortal vs pycoreEdi pattern), operators validate each project's fixture independently, preventing silent decay. Amber warnings quantify 'why' for cassette maintenance (not just 'when').

## Surfaces touched / added

- dashboard/server.py:/api/soak/coverage/cassette (GET cassette composition histogram from tests/fixtures/ JSONL)
- dashboard/server.py:/api/soak/coverage/live (GET live non-SM session composition from gov.db, polarity-filtered)
- dashboard/server.py:/api/soak/coverage/fixture/<id> (GET uploaded fixture composition via same histogram logic)
- dashboard/ui-next/src/lib/components/CoverageAnalyzer.svelte (parent widget; Frame D opt-in sub-section)
- dashboard/ui-next/src/lib/components/CoverageComparisonChart.svelte (side-by-side bar chart, cassette vs live, with deltas)
- dashboard/ui-next/src/lib/components/CoverageWarnings.svelte (amber/red alerts following Frame.svelte line 96-98 paired label+color pattern)
- tools/soak_driver.py (--analyze-coverage flag to emit JSON band-distribution summary post-soak)

## Feasibility

FEASIBLE. All surfaces implementable within existing api (FastAPI) + ui-next (Svelte/Tailwind) stack. Cassette histogram logic reuses _KIND_TO_LAYER from cassette_record.py:79 (4-line dict). Live SQL is CPU-light (~30ms for 1000-row aggregation, fits sub-budget per ADR-5). Svelte components: CoverageAnalyzer (~80 LOC parent), CoverageComparisonChart (~120 LOC bar chart, no charting lib needed), CoverageWarnings (~60 LOC reusing Frame.svelte flag CSS). Total new code: ~200 backend LOC (server.py endpoints) + ~260 frontend LOC (Svelte) + ~30 LOC soak_driver integration. No new dependencies. No database schema changes. No new bus envelopes (reuses governance_decision). Latency: bar-chart render sub-30ms on cached data; SQL aggregation sub-30ms (histogram on ~1000 rows).

## Compliance (adversarial-refute floor)

- **Firewall (G1):** PASS -- Zero new references to certPortal or monitored-project vocabulary. CoverageAnalyzer widget analyzes band distributions (% ALLOW, % L2/L3, % L4, % learn_dialogue) without naming specific projects. Cassette composition read from tests/fixtures/soak_cassette_*.jsonl (path-driven, no hardcoded project identity). Live decision composition queried via generic SQL filter: project_slug NOT IN {streamManager} AND session_id != self (polarity-aware). Fixture comparison uses uploaded fixture identity (<id>), not project slug. No coupling to FR-OG, MVP-100-PLAN, or maturity-dashboard artifacts.
- **Polarity (G2):** PASS -- SM does NOT monitor its own session. Live composition endpoint explicitly filters project_slug NOT IN {streamManager} (hard wire-site guard matching server.py:294-308). Session self-exclusion uses session_id != self (two-layer defense). Dashboard is read-only observer of gov.db; does NOT ingest or analyze SM's own governance traffic. Fixture upload scoped to non-SM projects only (same filtering at endpoint). No sweep or cleanup logic -- analyzer surfaces under-representation visually only; operator decides remediation.
- **ADR-18 MUST floor:** PASS -- Proposal bends no ADR-18 MUSTs. (1) model_router.py band priority + RoutingDecision field set FROZEN: analyzer reads layer/band data from cassette + live decisions but does NOT modify model_router.py or field schemas. (2) bus envelope schemas FROZEN: analyzer consumes existing governance_decision envelope (FROZEN as of 2026-05-12 per ADR-18 Amendment 2), does NOT introduce new envelopes. (3) Three-frame presence (M1 M2 M3) per ADR-18: Frame D is not guaranteed by ADR-18 (which ships A/B/C: Sessions, SubAgents, Jobs). Coverage Analyzer widget is opt-in sub-section within a frame (widget, not top-level frame), orthogonal to three-frame contract. (4) Escalation-only foreground, paired label+color badges, domain-agnostic, absolute HITL gate, a11y axe gate, latency budget, non-goals: analyzer is read-only data dashboard, NOT escalation channel. Surfaces amber/red alerts but does NOT feed HITL or governance decisions. Amber/red uses paired (color + text label, never color alone) reusing Frame.svelte:96-98 pattern. Widget can be hidden via opt-in flag; renders sub-30ms. No IDE/multiplexer/multi-tenant scope creep.
- **Frozen-surface note:** No frozen-surface amendments required. Proposal reads from FROZEN surfaces (model_router._KIND_TO_LAYER implicitly via cassette_record.py, RoutingDecision.layer, governance_decision bus envelope) but does NOT modify them. If Frame D were to be promoted from opt-in sub-section to a guaranteed fourth top-level frame (matching M1 M2 M3 contract), that would require an ADR-18 amendment authorizing a new frame layer; current proposal does NOT claim that authority.
- **New-envelope note:** No new bus envelope introduced. The --analyze-coverage flag in soak_driver.py emits a JSON summary (band distribution histogram) to stdout/disk, not to the bus. If future phases wire this summary into a new envelope kind, that phase MUST update cassette_record.py + soak_driver.py coverage per the NEW BUS ENVELOPE RULE (feedback_cassette_must_cover_new_envelopes). Current proposal is safe -- it reuses the existing governance_decision schema for all analysis.

## Grounding

- C:\Users\SeanHoppe\vs\streamManager\tools\cassette_record.py:79 (_KIND_TO_LAYER dict)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\server.py:294-308 (polarity-flip wire-site refusal + project_slug filtering)
- C:\Users\SeanHoppe\vs\streamManager\dashboard\ui-next\src\lib\components\Frame.svelte:96-98 (paired flag label+color pattern for reuse)
- C:\Users\SeanHoppe\vs\streamManager\docs\adr\ADR-18-mvp-surface-freeze.md (FROZEN surface classification + Rule 2 falsify-before-extend)
- C:\Users\SeanHoppe\vs\streamManager\tests\fixtures\soak_cassette_latest.jsonl (cassette fixture format: 70 envelopes, 50 routine + 5 l2_l3 + 5 l4 + 10 learn_dialogue)
