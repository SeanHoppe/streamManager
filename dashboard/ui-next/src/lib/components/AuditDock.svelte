<!--
  AuditDock.svelte -- the FR-PPP provenance-audit composition root (M11/M12).

  RESPONSIBILITY: this is the one place the provenance-audit leaves are
  assembled. It is the audit peer of HitlDock: where HitlDock owns the generic
  HITL pending queue, AuditDock owns the THREE-LAYER FR-PPP provenance workflow
  that proves a learn-mode parser is bound to the JSONL stream it claims to be
  reading. It seeds the pending audit-probe rows from /api/hitl/pending, keeps
  the audit surface live off the named bus events, and renders -- per the
  arriving envelopes -- attestation rows, canary echoes, and the negative-control
  hallucination alarm.

  MUSTs assembled here (the leaf rows carry the per-row contract; the dock owns
  the seam + the envelope<->pending-row correlation):

    M11 audit-probe ack. A probe is delivered as TWO correlated things:
        - a HITL pending row (trigger_reason="audit_probe", id=hitl_id, the
          message `content` carries the probe_id) -- seeded from
          /api/hitl/pending, the row the operator signs.
        - an `audit.probe` SSE envelope keyed on probe_id, carrying the
          `candidate_streams`.
        The dock correlates the two by probe_id and hands BOTH to AuditProbeRow
        (item=pending row, envelope=audit.probe). The leaf enforces the radio
        candidate list + "none of the above", validates session_id is set, and
        POSTs /api/sm-probe/ack with brain_id+prompt_hash extracted from the
        envelope. AuditDock NEVER fabricates candidates -- a pending row whose
        envelope has not (yet) arrived renders the leaf's "waiting" state.

    M12 canary echo + hallucination alarm.
        - audit.canary_emit  -> a pending canary (nonce + countdown) keyed on
          probe_id; CanaryEchoRow renders it.
        - audit.canary_observed -> the canary flips to observed; the leaf
          auto-clears after a 1.5s confirmation flash (dispatches `clear`).
        - audit.probe_failure -> the canary flips to failed + carries the reason.
        - audit.hallucination_detected -> a negative-control alarm; rendered by
          HallucinationAlert with an EXPLICIT operator-dismiss, NO auto-clear.

    M15 self-exclude: the dock filters the SM's own session_id out of the seeded
        audit-probe pending rows (defense-in-depth; the server already strips
        self). Empty/missing own id => no filtering (documented skip rule). The
        canary/hallucination envelopes are process-scoped (keyed by probe_id, not
        session_id) so they carry no self-target to exclude.

    M16 domain-agnostic: every probe_id, candidate slug, jsonl_path, nonce,
        brain_id, prompt_hash, failure reason and session id is rendered FROM
        DATA (the envelope / the session store). This file hard-codes NO
        monitored-project vocabulary -- the only literals are SM's own bus-event
        names, the "audit_probe" trigger string, and generic UI copy.

    M18 post-hoc: the dock seeds ONCE via a GET and otherwise lives off the SSE
        bus. Its only mutation is the operator-initiated "Run audit probe" POST
        (force=1, never automatic -- an auto-probe on mount would be a probe
        storm). It NEVER opens /api/commands/stream and never sits on the verdict
        hot path.

  CRAFT (calm-ambient spine, KingMode): the audit surface is still water. The
  attestation + canary rows sit in the OBSERVING/notice register -- quiet
  bespoke rails, never the amber ACTION REQUIRED escalation motion (that budget
  is reserved for the lone M2 foreground). The ONE card that legitimately reads
  loud is the hallucination alarm (BLOCKED red, static), and it is rendered
  FIRST so a parser-correctness failure is never buried. The empty state is a
  calm "all clear", not a void.

  FILE-DISJOINT: this host owns only itself. It consumes the api.js wrappers,
  sse.js (onBusEvent), the session store, and the three FR-PPP leaves; it
  performs no list mutation in the leaves and no navigation of its own.
-->
<script>
  import { onMount, onDestroy } from 'svelte';
  import Badge from './Badge.svelte';
  import AuditProbeRow from './AuditProbeRow.svelte';
  import CanaryEchoRow from './CanaryEchoRow.svelte';
  import HallucinationAlert from './HallucinationAlert.svelte';
  import { getHitlPending, getProbe } from '../api.js';
  import { onBusEvent } from '../sse.js';
  import {
    selectedSessionId,
    getOwnSessionId,
    scopeParam,
  } from '../stores/session.js';

  // The trigger_reason that marks a HITL pending row as a Layer-1 audit probe
  // (governance.emit_audit_probe queues the row with this exact reason; the
  // server projects it on /api/hitl/pending). This is SM's own protocol token,
  // NOT monitored-project vocabulary (M16). HitlDock excludes the same token so
  // an audit-probe row renders ONLY here, never twice.
  const AUDIT_PROBE_REASON = 'audit_probe';

  // -- Layer-1: pending audit-probe rows (the rows the operator signs) --------
  // Each entry is the raw /api/hitl/pending row whose trigger_reason is
  // audit_probe. Self-excluded (M15) + scope-filtered to match the rest of the
  // panes. `content` carries the probe_id; `id` is the hitl_id signed on ack.
  /** @type {Array<Record<string, any>>} */
  let pendingProbes = [];

  // probe_id -> the matching `audit.probe` envelope (carries candidate_streams).
  // A plain object so a fresh reference on every update drives Svelte reactivity
  // (Map mutation would not). AuditProbeRow renders "waiting" until its
  // envelope lands here (we never fabricate candidates -- M16).
  /** @type {Record<string, Record<string, any>>} */
  let probeEnvelopes = {};

  // -- Layer-2: canary echoes, keyed by probe_id --------------------------------
  // Each entry: { probe_id, nonce, jsonl_path?, issued_at?, timeout_s?, status,
  // failure_reason? }. status is 'pending' | 'observed' | 'failed'. Rendered as
  // a list; CanaryEchoRow flips its own presentation from the status we pass.
  /** @type {Array<Record<string, any>>} */
  let canaries = [];

  // -- Layer-3: hallucination alarms (negative-control). No auto-clear; the
  // operator dismisses each card explicitly (the WAL row is the durable record).
  //
  // SCOPE NOTE (process-global by design): the canary + hallucination envelopes
  // carry probe_id + jsonl_path but NO session_id (see the server dataclasses),
  // so they are NOT session-attributable and are deliberately NOT narrowed by
  // the operator's selected-session scope. This is correct, not a leak: a
  // Layer-3 parser-correctness alarm (or an in-flight Layer-2 proof) must NEVER
  // be hidden because the operator happened to narrow their glance to another
  // lane. Only the Layer-1 attestation ROWS are session-scoped (they carry
  // session_id). openCount therefore = scoped probes + these global signals,
  // which is exactly what renders below (count == on-screen), and the badge
  // reason names all three kinds so the mix is transparent.
  /** @type {Array<Record<string, any>>} */
  let hallucinations = [];

  let loading = true;
  let loadError = false;
  // Monotonic seed sequence: a slower earlier getHitlPending must never clobber
  // a fresher later one (bus re-seeds + scope-change + runProbe can overlap).
  let _seedSeq = 0;
  // After the first seed, bus-driven reconciliation seeds run QUIET (they do not
  // toggle the loading state) so normal live SSE traffic never flickers the
  // pane's empty/loading line (M18: seeds once, then lives off the bus).
  let _seededOnce = false;

  // -- Self-exclude (M15) ----------------------------------------------------
  /** @param {Record<string, any>} row */
  function isSelf(row) {
    const own = getOwnSessionId();
    return !!own && row && row.session_id === own;
  }

  // -- Session-scope filter (mirrors the api session_id param + HitlDock) -----
  $: scopedSessionId = $selectedSessionId; // null == ALL governed sessions
  /** @param {Record<string, any>} row */
  function inScope(row) {
    if (scopedSessionId == null) return true; // ALL
    return row && row.session_id === scopedSessionId;
  }

  /** The probe_id a pending audit-probe row attests to (carried in `content`). */
  function probeIdOf(row) {
    return row && row.content != null ? String(row.content) : '';
  }

  // The visible probe rows = audit_probe-kind + self-excluded + scope-filtered.
  $: visibleProbes = pendingProbes.filter(
    (r) => r && r.trigger_reason === AUDIT_PROBE_REASON && !isSelf(r) && inScope(r),
  );

  // The paired open-audit count for the header badge (M4): pending attestations
  // + live canaries + un-dismissed alarms. A glance number, always with a label.
  $: openCount = visibleProbes.length + canaries.length + hallucinations.length;

  // -- Operator "Run audit probe" (the ONLY mutation; never automatic) -------
  // The probe endpoint requires a concrete session_id (force=1, operator-
  // initiated) -- it cannot probe "ALL" sessions at once. Disabled in the ALL
  // scope. A successful call re-emits BOTH the HITL row and the audit.probe
  // envelope; the SSE fan-out + the next seed surface them here.
  let probing = false;
  let probeError = '';
  $: canRunProbe = scopedSessionId != null && !probing;

  async function runProbe() {
    probeError = '';
    if (scopedSessionId == null) {
      probeError = 'Select a session before running an audit probe.';
      return;
    }
    probing = true;
    try {
      // GET /api/sm-probe?session_id&force=1. The endpoint is GET-only (force=1
      // is the operator-initiated guard); a POST to it would 405. On success the
      // fresh HITL row + audit.probe envelope arrive over SSE; reconcile the
      // pending list (quiet) so the new row surfaces immediately.
      await getProbe({ session_id: scopedSessionId, force: true });
      await seed({ quiet: true });
    } catch (e) {
      const msg = e && e.message ? e.message : 'unknown error';
      // The server answers "no envelope subscribers" with HTTP 503, which the
      // api wrapper throws. The probe still fired server-side -- surface it
      // calmly (not as an alarm) rather than as a thrown wall.
      probeError = /\b503\b/.test(msg)
        ? 'Probe issued but not delivered (no live subscriber). Retry once the stream is connected.'
        : `Audit probe failed: ${msg}`;
    } finally {
      probing = false;
    }
  }

  // -- Seed (M18: one GET) ---------------------------------------------------
  // Read the unresolved HITL rows for the active scope and keep only the
  // audit_probe-kind ones (HitlDock owns the rest). Self-excluded.
  //
  // opts.quiet (after the first seed): reconcile WITHOUT toggling `loading`, so
  // a bus-driven re-seed never flickers the empty/loading line. The seq guard
  // makes the LATEST seed authoritative -- an earlier, slower getHitlPending
  // that resolves out of order is dropped instead of clobbering fresher rows.
  /** @param {{ quiet?:boolean }} [opts] */
  async function seed(opts = {}) {
    const quiet = opts.quiet === true && _seededOnce;
    const seq = ++_seedSeq;
    if (!quiet) loading = true;
    loadError = false;
    try {
      const rows = await getHitlPending({ session_id: scopeParam() });
      if (seq !== _seedSeq) return; // superseded by a newer seed -> drop
      pendingProbes = (Array.isArray(rows) ? rows : []).filter(
        (r) => r && r.trigger_reason === AUDIT_PROBE_REASON && !isSelf(r),
      );
    } catch {
      if (seq !== _seedSeq) return;
      pendingProbes = [];
      loadError = true;
    } finally {
      if (seq === _seedSeq) {
        loading = false;
        _seededOnce = true;
      }
    }
  }

  // Re-seed on scope change so the dock matches the rest of the panes.
  let _lastScope = scopedSessionId;
  $: if (scopedSessionId !== _lastScope) {
    _lastScope = scopedSessionId;
    seed();
  }

  // -- Live updates via the named bus events (M18: off the hot path) ---------
  /** @type {Array<()=>void>} */
  let unsubs = [];

  /** audit.probe -> cache the envelope by probe_id (carries candidate_streams). */
  function onProbe(env) {
    if (!env || !env.probe_id) return;
    const pid = String(env.probe_id);
    probeEnvelopes = { ...probeEnvelopes, [pid]: env };
    // A probe envelope can arrive slightly before its pending row is queryable.
    // Only reconcile when we do NOT already hold the correlated row -- otherwise
    // the cached envelope alone re-renders that row and a GET would be wasted
    // (one getHitlPending per envelope under a fan-out). Quiet: no loading flash.
    const known = pendingProbes.some((r) => probeIdOf(r) === pid);
    if (!known) seed({ quiet: true });
  }

  /**
   * hitl_sync_queued -> a bus-driven backstop for newly queued audit-probe rows
   * (peer to HitlDock.onSyncQueued). If the matching audit.probe envelope is
   * missed (fired during a reconnect gap, before this listener bound), the
   * pending row would otherwise surface only on the next scope change / manual
   * probe. We reconcile here too. Non-audit_probe rows are HitlDock's; ignore.
   */
  function onHitlQueued(payload) {
    if (!payload || isSelf(payload)) return; // M15
    if (payload.trigger_reason !== AUDIT_PROBE_REASON) return;
    seed({ quiet: true });
  }

  /** audit.canary_emit -> arm a pending canary keyed on probe_id. */
  function onCanaryEmit(env) {
    if (!env || !env.probe_id) return;
    upsertCanary({
      probe_id: String(env.probe_id),
      nonce: env.nonce,
      jsonl_path: env.jsonl_path,
      issued_at: env.issued_at,
      timeout_s: env.timeout_s,
      status: 'pending',
    });
  }

  /** audit.canary_observed -> flip the canary to observed (the leaf auto-clears). */
  function onCanaryObserved(env) {
    if (!env || !env.probe_id) return;
    const pid = String(env.probe_id);
    const cur = canaries.find((c) => c.probe_id === pid);
    if (!cur) return; // observed for a canary we never armed -> ignore
    upsertCanary({ ...cur, status: 'observed' });
  }

  /** audit.probe_failure -> flip the canary to failed + carry the reason. */
  function onProbeFailure(env) {
    if (!env || !env.probe_id) return;
    const pid = String(env.probe_id);
    const cur = canaries.find((c) => c.probe_id === pid) || { probe_id: pid };
    upsertCanary({ ...cur, status: 'failed', failure_reason: env.reason || 'unknown' });
  }

  /** audit.hallucination_detected -> a negative-control alarm (no auto-clear). */
  function onHallucination(env) {
    if (!env || !env.probe_id) return;
    const key = `${env.probe_id}::${env.jsonl_path || ''}`;
    // De-dupe: the same decoy path can be re-reported; keep ONE card per
    // (probe_id, path) so the keyed {#each} never sees a duplicate key.
    if (hallucinations.some((a) => `${a.probe_id}::${a.jsonl_path || ''}` === key)) return;
    hallucinations = [
      { probe_id: String(env.probe_id), jsonl_path: env.jsonl_path, detected_at: env.detected_at },
      ...hallucinations,
    ];
  }

  /** Insert-or-replace a canary by probe_id, always producing a fresh array. */
  function upsertCanary(next) {
    const rest = canaries.filter((c) => c.probe_id !== next.probe_id);
    canaries = [next, ...rest];
  }

  // -- Leaf intents ----------------------------------------------------------
  /** AuditProbeRow signed -> drop the pending row + release its cached envelope. */
  function onProbeAcked(e) {
    const probeId = e.detail && e.detail.probeId ? String(e.detail.probeId) : '';
    const hitlId = e.detail && e.detail.hitlId;
    pendingProbes = pendingProbes.filter((r) => r.id !== hitlId);
    if (probeId && probeId in probeEnvelopes) {
      const { [probeId]: _drop, ...rest } = probeEnvelopes;
      probeEnvelopes = rest;
    }
  }

  /** AuditProbeRow ack failed -> the leaf surfaced it inline; keep the row. */
  function onProbeError() {}

  /** CanaryEchoRow cleared (observed auto-clear, failed dismiss, or manual). */
  function onCanaryClear(e) {
    const probeId = e.detail && e.detail.probeId ? String(e.detail.probeId) : '';
    if (!probeId) return;
    canaries = canaries.filter((c) => c.probe_id !== probeId);
  }

  /** HallucinationAlert dismissed -> remove the surfaced card (WAL row stands). */
  function onHallucinationDismiss(e) {
    const probeId = e.detail && e.detail.probeId ? String(e.detail.probeId) : '';
    if (!probeId) return;
    // Remove every surfaced alarm for this probe (a probe has one decoy path).
    hallucinations = hallucinations.filter((a) => a.probe_id !== probeId);
  }

  onMount(() => {
    seed();
    unsubs.push(onBusEvent('audit.probe', onProbe));
    unsubs.push(onBusEvent('audit.canary_emit', onCanaryEmit));
    unsubs.push(onBusEvent('audit.canary_observed', onCanaryObserved));
    unsubs.push(onBusEvent('audit.probe_failure', onProbeFailure));
    unsubs.push(onBusEvent('audit.hallucination_detected', onHallucination));
    // Bus-driven backstop for newly queued audit-probe pending rows.
    unsubs.push(onBusEvent('hitl_sync_queued', onHitlQueued));
  });

  onDestroy(() => {
    for (const u of unsubs) {
      try {
        u();
      } catch {
        /* noop */
      }
    }
    unsubs = [];
  });
</script>

<section class="audit" aria-label="Provenance audit" data-open-count={openCount}>
  <header class="audit__head">
    <div class="audit__title-wrap">
      <h2 class="audit__title sev-notice">Provenance audit</h2>
      {#if openCount > 0}
        <!-- M4 paired label+count badge: the live open-audit tally. -->
        <Badge
          variant="observing"
          count={openCount}
          reason={`${openCount} provenance ${openCount === 1 ? 'check' : 'checks'} open (attestation / canary / alarm)`}
        />
      {:else}
        <Badge variant="observing" reason="No provenance checks open" />
      {/if}
    </div>

    <!-- The ONE operator mutation (M18): re-issue a Layer-1 probe for the
         selected session. Disabled in the ALL scope (a probe attests ONE
         session's stream binding). Quiet affordance -- NOT the amber hero. -->
    <button
      type="button"
      class="audit__probe-btn"
      on:click={runProbe}
      disabled={!canRunProbe}
      aria-label={scopedSessionId == null
        ? 'Select a session to run an audit probe'
        : 'Run an audit probe for the selected session'}
    >
      {probing ? 'Probing...' : 'Run audit probe'}
    </button>
  </header>

  {#if probeError}
    <p class="audit__error" role="alert">{probeError}</p>
  {/if}

  <div class="audit__body">
    <!-- Layer-3 FIRST: a parser-correctness alarm must never be buried. -->
    {#if hallucinations.length > 0}
      <ul class="audit__list" role="list" aria-label="Hallucination alarms">
        {#each hallucinations as alert (`${alert.probe_id}::${alert.jsonl_path || ''}`)}
          <li class="audit__row">
            <HallucinationAlert {alert} on:dismiss={onHallucinationDismiss} />
          </li>
        {/each}
      </ul>
    {/if}

    <!-- Layer-1: attestation rows. -->
    {#if visibleProbes.length > 0}
      <ul class="audit__list" role="list" aria-label="Audit-probe attestations">
        {#each visibleProbes as row (row.id)}
          <li class="audit__row">
            <AuditProbeRow
              item={row}
              envelope={probeEnvelopes[probeIdOf(row)] || null}
              on:acked={onProbeAcked}
              on:error={onProbeError}
            />
          </li>
        {/each}
      </ul>
    {/if}

    <!-- Layer-2: canary echoes. -->
    {#if canaries.length > 0}
      <ul class="audit__list" role="list" aria-label="Canary echoes">
        {#each canaries as canary (canary.probe_id)}
          <li class="audit__row">
            <CanaryEchoRow {canary} on:clear={onCanaryClear} />
          </li>
        {/each}
      </ul>
    {/if}

    {#if loading}
      <p class="audit__state sev-quiet">Loading provenance audit...</p>
    {:else if openCount === 0}
      <!-- Calm "all clear" empty state -- not a void. -->
      <p class="audit__state sev-quiet">
        {loadError
          ? 'Audit feed unavailable -- monitoring continues.'
          : 'No provenance checks open. Still water.'}
      </p>
    {/if}
  </div>
</section>

<style>
  .audit {
    display: flex;
    flex-direction: column;
    gap: var(--space-4, 10px);
    min-width: 0;
  }

  .audit__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4, 10px);
    flex-wrap: wrap;
    padding-bottom: var(--space-3, 6px);
    border-bottom: 1px solid var(--calm-hairline, #192030);
  }

  .audit__title-wrap {
    display: flex;
    align-items: center;
    gap: var(--space-4, 10px);
    min-width: 0;
  }

  .audit__title {
    margin: 0;
    font-family: var(--font-h, var(--ff-system, system-ui, sans-serif));
    font-size: 15px;
    letter-spacing: 0.04em;
    color: var(--calm-ink-loud, #e8e0cc);
  }

  /* Quiet outlined affordance -- an attestation re-issue, NOT an escalation.
     Mirrors the AuditProbeRow SIGN treatment so the audit surface reads as one
     calm family. */
  .audit__probe-btn {
    appearance: none;
    font-family: var(--ff-system);
    font-size: var(--fs-meta, 13px);
    font-weight: 650;
    letter-spacing: 0.02em;
    line-height: 1;
    padding: 6px 12px;
    border-radius: var(--radius-sharp, 2px);
    cursor: pointer;
    /* D4-012: accent TEXT on the paper cream wash needs the darker AA accent ink
       (--calm-accent-text, paper-only) -- the frozen brand accent at this size
       measures < AA on cream. Obsidian/phosphor fall back to --calm-accent
       (their accent on dark already clears AA). Border/wash keep --calm-accent. */
    color: var(--calm-accent-text, var(--calm-accent, #f59e0b));
    background: var(--calm-accent-wash, rgba(245, 158, 11, 0.09));
    border: 1px solid var(--calm-accent, #f59e0b);
    transition: background var(--t-calm, 180ms ease), color var(--t-calm, 180ms ease);
  }
  .audit__probe-btn:hover:not(:disabled) {
    background: var(--calm-accent, #f59e0b);
    color: var(--calm-surface, #080a0c);
  }
  .audit__probe-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  /* M17: explicit focus ring (focus.css enforces globally; restated locally so
     a component reset can never erase it). */
  .audit__probe-btn:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid)
      var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }

  .audit__body {
    display: flex;
    flex-direction: column;
    gap: var(--space-4, 10px);
    min-width: 0;
  }

  .audit__list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
  }
  .audit__row {
    min-width: 0;
  }

  /* Inline probe error -- WARN register, paired text (never color alone). */
  .audit__error {
    margin: 0;
    padding: var(--space-2, 4px) var(--space-3, 6px);
    font-family: var(--ff-system);
    font-size: var(--fs-meta, 13px);
    font-weight: 600;
    color: var(--badge-warn-fg, #ea580c);
    background: var(--badge-warn-bg, #ffedd5);
    border-left: 2px solid var(--badge-warn-border, #ea580c);
    border-radius: var(--radius-sharp, 2px);
  }

  .audit__state {
    margin: 0;
    padding: var(--space-5, 14px) var(--space-2, 4px);
    font-size: var(--fs-meta, 13px);
    color: var(--calm-ink-quiet, #64748b);
    font-style: italic;
  }
</style>
