# Proposal: clarify CLAUDE.md L35-42 to document the dual-key write-time / read-time split

- **Finding:** F-POLARITY-Q (cavecrew review, 2026-06-11) — the read-side polarity filter in `rl/ope.py` (`load_episodes_from_db`) and `rl/corpus_augment.py` (`_load_real_from_db`) applies **only** the `project_slug` half of CLAUDE.md L42's dual self-exclusion key. Severity ❓ (confirm-intentional).
- **Disposition:** PROPOSAL (governance-doc change) → **REVISE: keep the direction, fix the wording before relying on it.** Verified research (workflow `w7npngehj`, 2026-06-11) confirms the split is sound BUT the recommended CLAUDE.md text and the already-applied in-code comments are **overstated** ("session_id meaningless at read / inert-to-harmful") — live read-time session filters exist in the *same* modules, and two real gaps were found. See **Verified-research update** at the bottom. NB: the rec was already landed in CLAUDE.md at `e713b12` with the overstated wording — it needs softening.

## Problem

CLAUDE.md "Session-source exception rule (polarity-flip)" states the inclusion predicate as a **dual key, both halves at the SQL WHERE**:

```
INCLUDE iff session.project_slug NOT IN (STREAM_MANAGER_PROJECT_SLUGS)
        AND session_id != BRIDGE_SM_SELF_SESSION_ID
...
Filter at SQL WHERE, not post-hoc Python.
```

The implementation's read-side SQL WHERE carries only the `project_slug` term:

```sql
WHERE source IN (...) AND (project_slug IS NULL OR project_slug NOT IN (?, ...))
```

There is no `session_id != BRIDGE_SM_SELF_SESSION_ID` term at read time. Read literally, the code diverges from the documented rule — which is exactly what the ❓ finding flagged, and what an adversarial reviewer escalated to a REFUTE on the grounds that "CLAUDE.md L42 mandates *Filter at SQL WHERE* for the dual key."

## Root cause

The dual-key **invariant** ("no SM-self session contributes a row to the corpus") is upheld, but the **mechanism is split across two times**, not applied twice at read time:

- **`session_id` half — enforced at WRITE time.** `rl/episode_logger.py` raises `SelfMonitorRefusal` when `session_id == BRIDGE_SM_SELF_SESSION_ID`, so an SM-self session never writes an episode row in the first place. (Verified: `episode_logger` checks `session_id` against the self-session env var and raises before insert.)
- **`project_slug` half — enforced at READ time.** The read-side WHERE default-excludes the SM slug set, so any historical row carrying an SM `project_slug` is filtered on the way out.

Applying the `session_id` half at **read** time would be inert-to-harmful: `BRIDGE_SM_SELF_SESSION_ID` names the **current** session, which has no meaningful relationship to the `session_id` stored on a **historical** episode row. Filtering historical rows by the current session id excludes nothing useful (no historical row carries the current session id) and risks confusing future readers into thinking read-time session filtering is load-bearing. So `project_slug` is the only **durable** read-side key — precisely the conclusion the finding's author reached.

## Recommended change (CLAUDE.md, governance doc)

Amend the "Session-source exception rule (polarity-flip)" section so the doc states the invariant **and its split enforcement**, e.g. append after the code block:

> **Enforcement is split by time, not duplicated at read time.** The `session_id != BRIDGE_SM_SELF_SESSION_ID` half is enforced at **write** time (`episode_logger` raises `SelfMonitorRefusal`); `BRIDGE_SM_SELF_SESSION_ID` names the *current* session and is meaningless against historical rows, so it is **not** added to the read-side WHERE. The `project_slug NOT IN (STREAM_MANAGER_PROJECT_SLUGS)` half is the durable read-side key and is the term that appears in the read-side SQL WHERE. "Filter at SQL WHERE" governs the `project_slug` half; the `session_id` half is a write-time gate.

This makes the doc and the implementation agree, and pre-empts the next reviewer who reads L42 literally.

## In-code change already applied (this cycle)

The read-side comment in both `rl/ope.py` and `rl/corpus_augment.py` was updated to frame the divergence as compliance-via-split:

```
# CLAUDE.md L42's dual-key self-exclusion is upheld via a write-time /
# read-time SPLIT, not by dropping half the rule: the
# session_id != BRIDGE_SM_SELF_SESSION_ID half is enforced at WRITE time
# (episode_logger raises SelfMonitorRefusal) because that env var names
# the *current* session and is meaningless against historical rows; only
# the project_slug half is durable at read time, so the read-side SQL
# WHERE carries it alone.
```

## Evidence

- `rl/ope.py` `load_episodes_from_db` — read-side SQL WHERE: `project_slug`-only.
- `rl/corpus_augment.py` `_load_real_from_db` — read-side SQL WHERE: `project_slug`-only.
- `rl/episode_logger.py` — `SelfMonitorRefusal` raised on `session_id == BRIDGE_SM_SELF_SESSION_ID` (write-time session gate), verified by the Partition-B invariant reviewer.
- CLAUDE.md "Session-source exception rule (polarity-flip)" — the dual-key text + "Filter at SQL WHERE".
- `feedback_no_self_monitor.md` §"Polarity flip" (cross-ref in CLAUDE.md).

---

## Verified-research update (2026-06-11, workflow `w7npngehj`, adversarially verified — `holds=true`, REVISE)

**The split direction is sound — keep it. The wording is overstated and two real gaps were found. Do NOT rely on the wording as shipped.**

**Why the direction is sound (verified):** there is exactly **one** production `INSERT INTO episodes` — `rl/episode_logger.py:137-164` — and the live→DB path funnels through it (`rl/bus_subscriber.py:73`). So the write-time gate is a genuine single chokepoint, and durable `project_slug` (persisted at `:159-163`) is the correct read-side key.

**Why the wording is FALSE as written (all lenses converge):**
- The read side is **not** purely "project_slug-only / session_id meaningless at read." Live **read-time** session filters exist: `rl/corpus_augment.py:93-97` `_filter_self_monitor` (wired into the build path at `:160-163` over real + synthetic + extra episodes) and `rl/cli/train.py:74-76` (wired at `:112`). The narrow claim "not in the read-side **SQL WHERE**" is literally true (no `session_id` term at `ope.py:182-188` / `corpus_augment.py:62-67`), but "meaningless / inert-to-harmful" is contradicted by code ~45 lines from the comment. Correct framing: session_id is a **defence-in-depth backstop on an ephemeral key**, not the durable selector.

**Two real gaps the wording papers over (verified):**
1. **Env-conditional no-op.** The write-time session gate short-circuits when `BRIDGE_SM_SELF_SESSION_ID` is unset (`rl/episode_logger.py:105-106`), and the read-time Python filters do too (`corpus_augment.py:95`). That env var is documented **UNSET** in a real operator shell (`reports/poc-live-monitor-dryrun-2026-05-22T18-09-10Z.md:33,46`, OP-2c NOT-MET). With it unset, an SM-self session writing a NULL/empty/non-SM `project_slug` passes the write gate, persists `project_slug=NULL` (`:162`), and the read side **retains** NULL-slug rows (`ope.py:179`, `corpus_augment.py:56`) → **leak**. No read-side test covers the NULL-slug + SM-self class (`tests/test_rl_corpus_augment.py:147-173` injects only an explicit `"streamManager"` slug).
2. **File-mediated synthetic path bypasses BOTH gates.** `corpus_augment._load_synthetic` (`:100-109`) → `rl/sources/cassette.py:26` (`session_id="cassette-<tag>"`, **no** slug) and `rl/sources/probe.py:40` (`session_id="probe-<stamp>"`, no slug); `Episode.project_slug` defaults None. These never call `record_decision` and never hit the read SQL — their *only* guard is the post-hoc Python session filter (no-op when env unset, no slug check). Real but **operator-triggered** (only test callers wire `cassette_paths`/`probe_paths`; no production CLI auto-ingests synthetic files) — a real-but-conditional hole, not an active live leak.

**Recommended changes (doc + code):**
1. **Soften the CLAUDE.md rec** (landed at `e713b12`) from "meaningless at read / inert-to-harmful — do NOT" to: *"the `session_id` half is the load-bearing **write-time** gate and is **not** the durable read-side key, so it is not in the read-side **SQL WHERE**. Cheap read-time `session_id` filters MAY still exist in Python as defence-in-depth (`corpus_augment._filter_self_monitor`, `rl/cli/train._filter_self_monitor`) — belt-and-suspenders on an ephemeral key. `project_slug NOT IN (...)` is the durable read-side key."*
2. **Soften the in-code comments** at `rl/ope.py:167-173` and `rl/corpus_augment.py:46-52` the same way.
3. **Scope the "enforced at write time" claim to DB-mediated writers**, and flag the file-mediated synthetic path has no write-time gate.
4. **Add the NULL-slug justification + its caveat** (retained because screened by the write refusal — *if* the env was set at write).

**must_fix (gate before relying on the split):**
- **Resolve the two-reader inconsistency:** `ope.py` DROPS the read-time session filter; `corpus_augment.py` + `train.py` KEEP it — yet `ope.py` and `corpus_augment.py` got the *identical* "carries it alone" comment. Recommended: KEEP the cheap read-time session backstop as defence-in-depth and **align `ope.py` to match**; then make CLAUDE.md describe whichever is actually true.
- **Harden the env precondition:** make `BRIDGE_SM_SELF_SESSION_ID` a fail-loud precondition on ingest/corpus paths so the session half is never a silent no-op (note: conflicts with documented operator state where it ships unset — needs a decision).
- **Add the missing read-side test:** prove an SM-self `session_id` row with NULL `project_slug` is excluded at read.
- **Optional scope-completeness:** `rl/shadow.py` `ShadowRecorder._is_sm_self` (~`:157-167`) applies BOTH halves live at env-time — the one seam where the session check IS load-bearing (shadowed session is current). Consider adding the `ope.py` + `corpus_augment.py` + `train.py` read paths to `feedback_no_self_monitor.md`'s bind-site list.

**Open questions (operator):** (a) two-reader policy — keep the read-time session backstop everywhere (incl. add to `ope.py`), or remove it for a uniform pure-split? CLAUDE.md wording can't finalize until chosen. (b) make `BRIDGE_SM_SELF_SESSION_ID` fail-loud despite the POC shipping it unset? (c) require cassette/probe sources to stamp a non-SM `project_slug` (structural slug guard for the synthetic path)?
