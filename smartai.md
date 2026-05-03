# SmartAI — SM Learn Mode Design

> Working doc. Captures Q&A and initial design for an SM "learn mode" that
> watches Desktop ↔ user dialogue, aggregates/synthesizes/categorizes the
> exchange, and uses the result to strengthen SM's autonomous decision agency.
> Source conversation date: 2026-05-03.

---

## Context

SM today governs **machine-side traffic**: `tool_call` / `tool_result` rows on
the WAL bus, plus HITL overrides keyed off engine evaluations. It does **not**
currently capture:

- Desktop's natural-language prompts to the human ("should I proceed?", "which
  approach do you want?", "I see two options …")
- Human typed replies in the Desktop chat surface

Learn mode = a new ingest path that turns that dialogue into structured
training signal for SM's pattern engine.

Existing primitives we can lean on:

- `messages` table (WAL bus) — already has `type` discriminator, easy to add
  `desktop_prompt` / `user_reply` kinds
- `patterns` table with L1–L4 ladder + cross-session flag (Q3 locked)
- `hitl_overrides` table — already encodes "human picked X over engine
  default Y"
- Session Mirror frame (Q2 v1.0) — already streams governed-session activity
- Per-session isolated brains (Q3) — learn signal stays per-session unless
  HITL-promoted

---

## Q&A Log

### Q1 (2026-05-03)
> Walk me thru a scenario where SM has a 'learn' mode. Learn mode watches
> desktop prompts and the end-user's responses. SM aggregates, synthesizes,
> and categorizes that data. Goal: stronger agency when SM next makes
> decisions. Is this possible?

**A (short):** Yes — feasible as an additive layer on top of the existing
pattern engine + HITL infra. No new storage tech needed; reuses SQLite WAL bus
+ `patterns` ladder. Net-new work is (a) ingest of dialogue text, (b) a
synthesis/categorization step, and (c) an "advisory" injection point in the
engine so accumulated learning shapes future verdicts.

**Walkthrough — happy path:**

1. **Capture.** Desktop hook posts every outbound prompt to user as
   `messages.type='desktop_prompt'`; user reply posted as
   `messages.type='user_reply'`. Both rows carry `session_id`,
   `correlation_id` (prompt↔reply pair), and raw text.
2. **Pair + window.** Learn-mode worker reads the pair, plus a small context
   window (last N tool_calls + last engine verdict) so the reply has
   situational meaning.
3. **Categorize.** Each pair is tagged with intent labels:
   `approval | denial | redirect | clarify | preference | scope_change | …`.
   Tagger = small Haiku call (cheap, L0/L1 routed) with deterministic schema.
4. **Synthesize.** Aggregator rolls categorized pairs into patterns:
   "When SM proposed Y in context X, user redirected to Z N times" →
   becomes a candidate pattern row.
5. **Promote.** Candidate pattern climbs the existing L1→L4 ladder using the
   same evidence-count + HITL-confirm gates already in place. L3 + cross-session
   HITL approval = promoted to advisory for new sessions (per Q3 OQ5).
6. **Apply.** Engine evaluation reads the user's accumulated preferences as
   an **advisory bias**, not a hard rule:
   - Same context recurs → engine surfaces the historical preference
   - High-confidence (L4) preference → engine can auto-resolve without
     prompting (only if HITL mode allows)
   - Low-confidence → engine still asks, but pre-fills the option the user
     historically picked.

**Walkthrough — agency uplift:** After enough volume, SM stops asking
"approve this commit message?" for the 50th time and just picks the format
the user has consistently picked, surfacing a one-line audit row instead of
a HITL gate. Friction drops; auditability stays intact via WAL.

---

## Initial Design — Learn Mode

### Data model additions

```
messages.type ∈ { ..., 'desktop_prompt', 'user_reply' }
    + correlation_id  TEXT  -- pairs prompt↔reply

learn_pairs  (new view OR materialized table)
    pair_id, session_id, prompt_msg_id, reply_msg_id,
    context_window_json, captured_at

learn_categories  (new table)
    pair_id, label, confidence, tagger_model, tagged_at

patterns
    + source ∈ {'tool_call','dialogue'}   -- discriminator
    + dialogue_template  TEXT NULL        -- canonical "context Y" string
```

### Wire shape

```
Desktop chat surface
        │
        │ outbound prompt to user  ──→  POST /api/learn/prompt
        │ user reply               ──→  POST /api/learn/reply
        ▼
   SM bus (messages, type=desktop_prompt|user_reply)
        │
        │ async worker pairs + windows
        ▼
   Categorizer (Haiku, L1)  ──→  learn_categories
        │
        │ aggregator (every N pairs OR 60s)
        ▼
   patterns (source='dialogue', L1 advisory)
        │
        │ existing L1→L4 promotion + HITL gates
        ▼
   Engine.evaluate() — reads dialogue patterns as bias signal
```

### Ingest source — three options

| # | Source | Pros | Cons |
|---|--------|------|------|
| A | Desktop hook (PreToolUse-equiv on chat msgs) | Real-time, structured | Needs Desktop-side hook surface; may not exist for chat text |
| B | JSONL tail of Desktop transcript | No hook surface needed | Format churn risk; lag |
| C | User-driven: human pastes / SM reads via screen share | Zero Desktop integration | Manual, low fidelity, breaks "SM never self-monitors" if SM is the Desktop being watched |

Default lean: **A for prompts emitted by sub-agents Desktop already hooks
(PostToolUse-style), B as fallback for free-form chat text.**

### Engine integration

- Add `learning_advisory(context, candidate_action) -> bias` reader
- Bias enters verdict scoring as a **soft signal**, never overrides safety
  priorities (INTENT.md §"Safety priorities (highest first)" stays absolute)
- Hard floor: dialogue-derived patterns can never auto-promote a destructive
  shell verb to ALLOW. Existing static-rule fire wins.

### Effort estimate (rough)

| Piece | Sessions |
|---|---|
| Ingest endpoints + schema migration | ~½ |
| Pair + window worker | ~½ |
| Categorizer (Haiku call + schema) | ~½ |
| Aggregator → pattern rows | ~½ |
| Engine advisory reader | ~½ |
| HITL UI: dialogue-pattern review queue | ~½ |
| Tests (ingest, pairing, promotion gate, no-override-of-safety) | ~1 |
| ADR + REQUIREMENTS.md additions | ~¼ |

**Total:** ~4¼ sessions. Ships as v1.3 candidate (after v1.2 close).

### Constraint check

- ✓ SM-never-self-monitor: ingest filters `session_id != SM_OWN_SESSION_ID`
- ✓ Safety priorities absolute: dialogue bias is advisory, hard rules win
- ✓ Cross-session leakage: rides existing HITL-gated cross-session flag
- ✓ Privacy: raw user text stays in local SQLite; no exfil path added
- ✓ ADR-5 latency: categorizer is **out-of-band** worker; not on verdict
  hot path

---

## Locked Answers (2026-05-03)

| ID | Decision | Notes |
|----|----------|-------|
| LQ1 | **Reuse Phase 1 JSONL tail** (option B-prime) | See rationale below |
| LQ2 | Desktop **orchestrator** scope | Sub-agent prompts in scope by transitive capture; SM's own HITL excluded (self-monitor rule) |
| LQ3 | **Pre-fill only** | No auto-resolve in v1.3. Engine pre-selects historically-picked option, human still confirms. Lower-risk; revisit auto-resolve in v1.4+ |
| LQ4 | **Sonnet** categorizer | Higher label fidelity. Out-of-band worker, off verdict hot path → ADR-5 latency budget unaffected. Cost trade accepted |
| LQ5 | **Yes — decay enabled** | Scheme below |
| LQ6 | **Silent audit row** | One row in WAL + dashboard decisions table. No toast, no undo card. Matches monitor-first UI principle (INTENT §UI/HITL) |
| LQ7 | Single-user assumed | No `owner_user` tag on patterns. Revisit only if multi-tenant non-goal flips |
| LQ8 | **v1.3 scope** | Lands after v1.2 ship-gate Tier 3 soak runs |

---

### LQ1 rationale — recommended ingest

**Pick: extend existing Phase 1 JSONL tailer.**

Why:
- Phase 1 already ships `src/stream_manager/jsonl_tail.py` — background thread
  tails `~/.claude/projects/{slug}/*.jsonl` for every governed session
- JSONL format already contains `assistant` and `user` turn objects with
  `content` blocks — same rows that carry `attributionPlugin` /
  `attributionSkill` fields used by Agent Registry
- Zero new hook surface required on Desktop side. Desktop **does not** expose
  a chat-text hook today (only PreToolUse / PostToolUse on tool calls).
  Building one would be Desktop-side work outside SM's scope
- Latency: JSONL writes are append-only with <1s lag in practice — fine for
  out-of-band worker
- Format-fragility risk already accepted by Phase 1; learn mode rides the
  same coupling, no new risk surface

**Implementation delta vs option A (hook-based):**
- Add text-block extractor to existing tailer:
  - `assistant` turn `content[*].type=='text'` → `messages.type='desktop_prompt'`
  - `user` turn `content[*].type=='text'` → `messages.type='user_reply'`
- Pair via `parentUuid` chain already present in JSONL (no new
  `correlation_id` column needed — reuse existing thread linkage)
- Filter `session_id != SM_OWN_SESSION_ID` (self-monitor rule)
- Filter out HITL responses (LQ2 scope) by tagging SM-issued prompt UUIDs

**Effort revision:** ingest piece drops from ~½ session to **~¼ session**
because tailer infra exists. Total estimate slides ~4¼ → **~4 sessions**.

---

### LQ5 — Decay scheme proposal

Three mechanisms stacked. Goal: stay current with shifting user preference
without throwing away long-stable patterns.

**1. Time-based step demote (slow)**
| Inactivity | Action |
|---|---|
| 30 days unobserved | L4 → L3 |
| 60 days | L3 → L2 |
| 90 days | L2 → L1 |
| 120 days | prune row (or archive to `patterns_archive`) |

Cadence: nightly gc job. Reuses existing `last_seen` TTL machinery from
Q3 OQ6.

**2. Reinforcement reset (fast bump)**
- Any new observation matching pattern → `last_seen = now()`, decay clock
  restarts
- Optional: N consecutive reinforcements within window W → confidence bump
  (e.g., 5 hits in 7 days → next-level promotion candidate)

**3. Contradiction snap-demote (fastest)**
- User picks **opposite** of pre-filled option → pattern drops one level
  immediately, bypasses time decay
- Two contradictions inside 14 days → drop two levels (signals real
  preference shift, not a one-off)
- Surfaces in HITL review queue with `trigger_reason=contradiction_demote`
  so user can confirm "yes I changed my mind" vs "no, that was a mistake"

**Knobs (env-tunable, defaults shown):**
```
SM_LEARN_DECAY_DAYS_L4_L3=30
SM_LEARN_DECAY_DAYS_L3_L2=60
SM_LEARN_DECAY_DAYS_L2_L1=90
SM_LEARN_DECAY_DAYS_PRUNE=120
SM_LEARN_REINFORCE_BUMP_HITS=5
SM_LEARN_REINFORCE_BUMP_WINDOW_DAYS=7
SM_LEARN_CONTRADICTION_FAST_DEMOTE=true
```

Trade-off: more knobs = more complexity. Could ship with hardcoded values
in v1.3, expose env knobs in v1.4 if real-world data demands tuning.

---

## Next steps

1. ✅ All LQ1–LQ8 locked.
2. Spin out `docs/learn-mode-design.md` ADR-style sibling to `docs/sync-comms-qa.md` — copy the locked sections from this doc as the source of truth.
3. Add REQUIREMENTS.md §4.x stub: FR-LM-1 (JSONL ingest), FR-LM-2 (Sonnet categorizer), FR-LM-3 (advisory bias, never overrides safety), FR-LM-4 (decay scheme), FR-LM-5 (silent audit row UX), FR-LM-6 (self-monitor exclusion).
4. Add to `docs/v1.3-scope.md` (new) — slot after v1.2 Tier 3 soak.
5. Capture decisions to `memory/project_learn_mode.md` per decision-capture workflow.
