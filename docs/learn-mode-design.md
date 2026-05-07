# Learn Mode Design (v1.3)

**Status:** Design accepted (P5a).
**Slot:** v1.3, after v1.2 Tier 3 soak runs.
**Source of truth for locked decisions:** memory note `project_learn_mode.md` (locked 2026-05-03). An earlier seed referenced `smartai.md` at the repo root; that file does not exist. Treat this document as the on-disk authoritative spec; treat the memory note as the historical seed it captures.
**Authors:** SeanHoppe.
**Last updated:** 2026-05-04.

---

## 1. Summary

Learn Mode is the v1.3 marquee feature for streamManager. It extends the existing JSONL-tail ingest path so SM can observe the **Desktop ↔ user dialogue** (not just the Desktop ↔ CLI tool stream), categorize recurring user preferences with an out-of-band Sonnet worker, and surface those patterns as **advisory bias** on the next governance decision. The bias never overrides HITL gating and never overrides the absolute safety priorities listed in `INTENT.md` §"Safety priorities".

Why it is worth shipping: it adds agency uplift (SM begins to learn the operator's individual style) without introducing a new safety surface. It rides the existing patterns L1–L4 ladder and the existing HITL-gated cross-session learning flag (Q3 OQ5). The dialogue signal is purely advisory.

---

## 2. Locked decisions (verbatim from memory note)

The following decisions are locked for v1.3. Any change requires a new ADR.

### 2.1 Ingest

- Extend the existing Phase 1 JSONL tailer (`src/stream_manager/jsonl_tail.py`) to extract:
  - `assistant` text turns → `messages.type='desktop_prompt'`
  - `user` text turns → `messages.type='user_reply'`
- Pair the two via the existing `parentUuid` chain already populated by the tailer.
- **No new Desktop hook surface.** Claude Desktop does not expose a chat-text hook. The JSONL transcript is the only signal source.

### 2.2 Scope

- Desktop **orchestrator** turns only.
- SM's own HITL prompts are excluded from ingest. This enforces the no-self-monitor rule at the ingest layer (memory note `feedback_no_self_monitor.md`): governance subject ≠ governance system. SM HITL prompts/decisions feeding back into SM's own categorizer would inflate the action distribution and corrupt the mode-promotion ladder.

### 2.3 Auto-resolve

- v1.3 **pre-fills** the HITL prompt with the categorizer-suggested action only.
- v1.3 does **not** silently skip the HITL gate, even at high confidence.
- Auto-resolve (silent skip at high confidence) is explicitly deferred to v1.4+.

### 2.4 Categorizer

- Sonnet, run as an **out-of-band worker** off the verdict hot path.
- Off the hot path → ADR-5 latency budget (NFR-P2: p50 ≤ 7 s, p95 ≤ 15 s, hard timeout 25 s) is unaffected.
- Backend conforms to the project default of CLI subprocess over Anthropic SDK (memory note `feedback_cli_over_sdk.md`): use `claude -p <prompt> --output-format json --model <id>` as the worker invocation. No API key path.

### 2.5 Decay

- Time-based step-demote ladder: **30 / 60 / 90 / 120 days** without reinforcement → step demote one rung on the L1–L4 ladder per interval.
- **Reinforcement reset** — any same-direction observation resets the decay clock.
- **Contradiction snap-demote** — an opposite-direction observation snaps the pattern down one rung immediately, regardless of where it sits in the decay window.

### 2.6 UX

- Pattern application records a **silent audit row** on the dashboard decisions feed.
- **No toast.** **No undo card.** The advisory nature plus the HITL gate is the safety net.

### 2.7 Multi-user

- Single-user assumed for v1.3.
- No `owner_user` tag on patterns. Multi-user disambiguation is out of scope and left for a later cycle.

### 2.8 Safety (non-negotiable)

`INTENT.md` §"Safety priorities" remains **absolute**. The following classes can never be auto-allowed by a learned preference, regardless of pattern strength, frequency, or operator history:

1. Destructive shell verbs — `rm -rf /`, `rm -rf ~`, `dd if=… of=/dev/…`, `DROP DATABASE/TABLE`.
2. Force-push to protected branches — `git push --force` (or `-f`) targeting `main`/`master`/`production`.
3. Code-injection patterns — `eval(`, `exec(` in untrusted message bodies.
4. Credential exfiltration — content matching obvious token / API-key shapes.

The categorizer MUST short-circuit on any of the above and emit no advisory bias. The verdict path remains the single authoritative gate for these classes.

---

## 3. Architecture

### 3.1 Data flow

```
Desktop JSONL transcript
        │
        ▼
jsonl_tail.py  ──►  bus: messages(type=desktop_prompt | user_reply)
        │                      │
        │                      ▼
        │            categorizer-worker (Sonnet, out-of-band)
        │                      │
        │                      ▼
        │            patterns table  (decay clock + L1–L4 rung)
        │                      │
        ▼                      ▼
   verdict path  ◄── advisory bias (read-only at decide time)
        │
        ▼
   decision row + silent audit row on dashboard
```

### 3.2 Components

| Component | Path (proposed) | Responsibility |
|---|---|---|
| Tail extension | `src/stream_manager/jsonl_tail.py` | Emit `desktop_prompt` / `user_reply` rows; pair via `parentUuid`; exclude SM-self transcripts (per `feedback_no_self_monitor.md` filter list). |
| Categorizer worker | `src/stream_manager/learn_mode/categorizer.py` | Drain `desktop_prompt`/`user_reply` pairs, run Sonnet via `claude -p`, write to `patterns` (audit log) and project into the canonical table via `consolidate_patterns`. Off the hot path. See `docs/adr/ADR-19-learn-patterns-canonical-split.md` for the audit/canonical two-table split rationale. |
| Decay scheduler | `src/stream_manager/learn_mode/decay.py` | Apply the 30/60/90/120 ladder + reinforcement reset + contradiction snap-demote. |
| Bias reader | inside existing verdict path | Read top-N matching patterns at decide time, attach as advisory context only. Never gates the decision. |
| UX | dashboard decisions feed | Render the silent audit row when a pattern was used; no toast, no undo. |

### 3.3 Off the hot path

The categorizer is a separate worker process. The verdict path reads patterns; it does not invoke the categorizer synchronously. This is what keeps ADR-5 latency budgets clean: a Sonnet round-trip never blocks a verdict.

---

## 4. Out of scope (v1.3)

- Auto-resolve (silent HITL skip).
- Multi-user disambiguation / `owner_user` pattern scoping.
- Toast or undo affordances.
- Learning from SM's own HITL prompts.
- Any change to the absolute safety priorities in `INTENT.md`.

---

## 5. Open questions for v1.4+

- Auto-resolve at high confidence (with what floor, what audit?).
- Multi-user signal (does any operator other than SeanHoppe touch this surface?).
- Cross-session pattern propagation under the existing HITL-gated cross-session flag (Q3 OQ5).

---

## 6. References

- `INTENT.md` §"Safety priorities" — absolute safety invariants.
- `REQUIREMENTS.md` §4.12 FR-LM-1..6 — functional requirements (added in this same revision).
- `docs/v1.3-task-plan.md` §"PHASE P5" — orchestration plan; sub-phases P5b–P5e.
- Memory: `project_learn_mode.md` — locked Q&A 2026-05-03.
- Memory: `feedback_no_self_monitor.md` — no-self-monitor rule.
- Memory: `feedback_cli_over_sdk.md` — CLI subprocess as the LLM backend.
- ADR-5 — governance latency budget (must remain unaffected).
- ADR-9 — HITL as a switchable mode (Learn Mode bias never bypasses it).

---

## 7. `learn_sources` config (v1.9 P3 — append-only)

v1.3's ingest pipeline was hard-wired to the Desktop session JSONL. The
v1.9 P3 expansion adds a configurable list of *external* JSONL sources
so SM can learn from oversight-agent dialogue (certPortal Dave / Jen /
Jason / Matt / Oliver / Michael) without polluting Desktop-attributed
patterns. The advisory bias surface (§"Bias reader") is unchanged —
this is a write-side extension only.

### 7.1 Format

A list of `{path_glob, label}` dicts, one entry per labelled source.
Loaded from the `BRIDGE_LEARN_SOURCES` env var (JSON-encoded). Default
is the empty list — opt-in per source. When unset or empty, no
`learn_mode.py` workers spin up and the existing Desktop session ingest
path runs unchanged.

```json
[
  {"path_glob": "/path/to/oversight/sessions/*.jsonl",
   "label": "certportal-oversight"}
]
```

| Field | Type | Notes |
|---|---|---|
| `path_glob` | str | Resolved with `pathlib.Path.glob`. Absolute or relative. |
| `label` | str | Attribution tag (used as `metadata.source_label` and on `hitl_overrides.source_label`). |

### 7.2 Self-monitor guard

Every glob expansion (not just at config load time) is filtered through
two checks per memory note `feedback_no_self_monitor.md`:

1. **Exact-path match** — paths resolving to
   `~/.claude/sessions/<SM_OWN_SESSION_ID>.jsonl` are rejected.
2. **Path-segment match** — paths whose resolved components contain
   `stream_manager` (case-insensitive) are rejected.

A rejected path is logged at WARNING level with the
`learn_sources: rejecting path …` prefix. The guard never raises —
other sources in the same config are unaffected, and a single bad
source cannot interrupt the ingest loop. The check runs at every
expansion so a self-monitor file appearing under a watched glob *after*
config load is still rejected.

### 7.3 Label propagation

Each emitted envelope (`desktop_prompt` / `user_reply`) carries
`metadata.source_label = <label>`. The categoriser is unchanged — the
label is metadata, not a routing modifier. When an override is recorded
for a tagged turn via `learn_mode.record_override_with_source_label`,
the label lands on the new nullable `hitl_overrides.source_label`
column (additive migration, idempotent).

Desktop session turns continue to use `MessageBus.annotate_decision`
directly; their `source_label` stays NULL. Existing `hitl_overrides`
rows are unaffected by the migration.

### 7.4 Source isolation

Each configured source runs on its own tail thread with an independent
envelope queue. The categoriser processes one turn at a time regardless
of source — there is no cross-source biasing. Sources A and B can carry
different labels into the same `hitl_overrides` table without
contaminating each other's categorisation outcomes.

### 7.5 No new bus envelope types

P3 does not introduce any new envelope `type=`. Source turns ride the
existing `desktop_prompt` / `user_reply` types with the new
`source_label` metadata field. Cassette + soak machinery is unaffected
(memory: `feedback_cassette_must_cover_new_envelopes.md`).

### 7.6 References

- `src/stream_manager/learn_mode.py` — implementation.
- `tests/test_learn_mode_sources.py` — eight scenarios covering empty
  default, label tagging, self-monitor guard (path + segment + no-raise),
  two-source isolation, column migration, Desktop NULL invariant.
- `docs/use-cases/uc-01-external-session-monitoring.md` §AC-2 —
  acceptance criteria.
- Memory: `feedback_no_self_monitor.md`,
  `feedback_cassette_must_cover_new_envelopes.md`.
