<!--
  AuditProbeRow.svelte -- FR-PPP audit-probe attestation surface (M11).

  WHAT THIS IS
    A single audit-probe HITL row. The governance bridge periodically asks the
    operator to ATTEST which JSONL stream a governed session is actually
    driving -- a provenance check that a learn-mode parser is bound to the
    right transcript. This leaf renders that prompt as a radio candidate list
    plus an explicit "none of the above" choice, then signs the operator's
    answer back to the server.

  CONTRACT (inviolable MUST M11):
    - Render the probe as a RADIO candidate list (single-select) built from the
      envelope's `candidate_streams`, PLUS an explicit "none of the above"
      option. The probe is a single attestation -- radios, never checkboxes.
    - VALIDATE session_id is set before signing. An audit attestation with no
      session scope is meaningless (and the server rejects it); we refuse to
      POST and surface an inline, accessible error instead of a blind failure.
    - POST /api/sm-probe/ack with brain_id + prompt_hash EXTRACTED FROM THE
      ENVELOPE for the selected candidate (not invented client-side), alongside
      probe_id + hitl_id + session_id + selected_jsonl_path. "none of the above"
      sends an empty selected_jsonl_path with null brain_id/prompt_hash.

  CRAFT (calm-ambient spine, KingMode):
    This is an attestation, not an alarm -- it sits at the OBSERVING /
    sev-notice weight, never the ACTION REQUIRED escalation register (that amber
    pulse is reserved for the lone true M2 foreground escalation). The row is
    still water: a quiet bespoke left rail in --accent-dim, the prompt as real
    prose, candidates as a tight telemetry list with monospaced paths. Severity
    is carried by type weight (sev-notice on the SIGN affordance), never by
    saturation. The radios use the focus.css amber ring; the whole surface
    retints cleanly across obsidian / phosphor / paper via theme tokens.

  M16 (domain-agnostic): NOTHING here hard-codes monitored-project vocabulary.
    Every candidate slug, path, brain_id, prompt_hash, and the session_id all
    come from the envelope / session store as DATA. The only literals are SM's
    own route string and generic UI copy.

  M17 (a11y): the radio group is a real <fieldset>/<legend> with role=radiogroup
    semantics via native inputs; each candidate is a <label>-wrapped radio so
    the path text is the accessible name; the SIGN control is a real <button>;
    focus rings come from focus.css; the inline validation error is wired to the
    fieldset via aria-describedby + role=alert so it is announced.

  M18 (post-hoc): the ONLY network call is the operator-initiated ack POST. No
    polling, no hot-path read, nothing on the verdict path. Eligibility /
    envelope delivery happens upstream (sse.js fan-out + u-hitl-core seed).

  FILE-DISJOINT: this leaf owns only itself. It consumes the api.js wrapper and
  the session store; it emits intent (acked / error) via events -- it performs
  no list mutation or navigation of its own.
-->
<script>
  import { createEventDispatcher } from 'svelte';
  import { postProbeAck } from '../api.js';
  import { selectedSessionId } from '../stores/session.js';

  /**
   * item: the audit-probe HITL pending row (from /api/hitl/pending seed or the
   * hitl bus). The probe_id is carried in `content` (mirrors the live dashboard
   * `buildAuditProbeRow` contract); `id` is the hitl pending id signed on ack.
   * @type {{ id:string|number, content?:string, queued_at?:number,
   *          trigger_reason?:string } & Record<string, any>}
   */
  export let item;

  /**
   * envelope: the matching `audit.probe` envelope delivered over SSE, cached by
   * the audit store keyed on probe_id. Carries `candidate_streams`, each shaped
   * { jsonl_path, slug?, brain_id?, prompt_hash? }. When the row renders before
   * its envelope has arrived (race), we show a quiet "waiting for envelope"
   * state and disable SIGN -- we never fabricate candidates (M16).
   * @type {{ probe_id?:string,
   *          candidate_streams?:Array<{ jsonl_path?:string, slug?:string,
   *            brain_id?:string, prompt_hash?:string }> } | null}
   */
  export let envelope = null;

  const dispatch = createEventDispatcher();

  // probe_id: prefer the envelope's own id, fall back to the hitl row's
  // `content` (the live-dashboard carrier). Data-only (M16).
  $: probeId = (envelope && envelope.probe_id) || (item && item.content ? String(item.content) : '');

  // hitl pending id signed on ack.
  $: hitlId = item ? item.id : undefined;

  // Candidate streams strictly from the envelope -- never invented (M16).
  $: candidates =
    envelope && Array.isArray(envelope.candidate_streams) ? envelope.candidate_streams : [];

  $: hasEnvelope = candidates.length > 0;

  // A stable radio-group name so the native single-select semantics hold even
  // when several probe rows coexist.
  $: groupName = `probe-${probeId || (item && item.id) || 'x'}`;

  // The sentinel value for "none of the above". Empty string => null on ack
  // (mirrors the live dashboard: empty selected_jsonl_path = none-of-above).
  const NONE = '';

  // Operator selection. Default to the first candidate once the envelope lands
  // (matches the live default-checked behavior) so the common path is one tap.
  let selected = undefined;
  $: if (selected === undefined && hasEnvelope) {
    selected = candidates[0].jsonl_path || NONE;
  }

  // Inline validation / submission state.
  let error = '';
  let submitting = false;

  // M11: session scope is mandatory. We read the operator's selected session as
  // the attestation scope. ALL (null) is NOT a valid attestation scope -- a
  // probe attests ONE session's stream binding.
  $: sessionId = $selectedSessionId;
  $: sessionMissing = sessionId === null || sessionId === undefined || sessionId === '';

  /**
   * Resolve brain_id + prompt_hash for the chosen candidate FROM THE ENVELOPE
   * (M11). "none of the above" => both null. A path with no matching candidate
   * (shouldn't happen, but defensive) => both null.
   * @param {string} jsonlPath
   * @returns {{ brain_id:string|null, prompt_hash:string|null }}
   */
  function provenanceFor(jsonlPath) {
    if (!jsonlPath) return { brain_id: null, prompt_hash: null };
    const match = candidates.find((c) => c && c.jsonl_path === jsonlPath);
    return {
      brain_id: (match && match.brain_id) || null,
      prompt_hash: (match && match.prompt_hash) || null,
    };
  }

  async function sign() {
    error = '';

    if (!hasEnvelope) {
      // Nothing to attest to yet; should be unreachable (SIGN is disabled) but
      // guard so a fast keyboard activation cannot POST an empty attestation.
      error = 'Probe envelope not yet received -- wait for the candidate list.';
      return;
    }

    // M11: validate session_id is set BEFORE any POST.
    if (sessionMissing) {
      error = 'Select a session before signing this probe.';
      return;
    }

    if (selected === undefined) {
      error = 'Choose a candidate stream, or "none of the above".';
      return;
    }

    const selectedPath = selected === NONE ? '' : selected;
    const { brain_id, prompt_hash } = provenanceFor(selectedPath);

    submitting = true;
    try {
      await postProbeAck({
        probe_id: probeId,
        hitl_id: typeof hitlId === 'number' ? hitlId : Number(hitlId),
        session_id: sessionId,
        selected_jsonl_path: selectedPath, // '' => none-of-the-above
        brain_id, // extracted from the envelope (M11)
        prompt_hash, // extracted from the envelope (M11)
      });
      // Tell the parent list to drop this row (optimistic resolve lives in the
      // hitl-core list; this leaf only emits the success intent + payload so the
      // list can also clear the cached envelope keyed on probe_id).
      dispatch('acked', { hitlId, probeId, selectedPath, brain_id, prompt_hash });
    } catch (e) {
      // Surface inline (accessible, role=alert) rather than a blocking dialog.
      error = `Audit probe ack failed: ${e && e.message ? e.message : 'unknown error'}`;
      dispatch('error', { hitlId, probeId, message: error });
    } finally {
      submitting = false;
    }
  }

  // Accessible names assembled from data only (M16).
  $: legendText = 'Which JSONL stream is this session driving?';
  $: signLabel = sessionMissing
    ? 'Select a session before signing this audit probe'
    : 'Sign this audit-probe attestation';
</script>

<article
  class="probe"
  data-probe-id={probeId}
  data-hitl-id={hitlId}
  aria-label="Audit probe attestation"
>
  <!-- Quiet bespoke left rail -- attestation register, NOT the amber escalation
       rail. Decorative; the text below carries the signal (M4 discipline). -->
  <span class="probe__rail" aria-hidden="true"></span>

  <div class="probe__body">
    <header class="probe__head">
      <!-- Paired label+text: the kind is named in words, never color alone. The
           OBSERVING-register tag keeps this in the calm band, distinct from the
           ACTION REQUIRED escalation surface. -->
      <span class="probe__kind sev-notice">
        <span class="probe__dot" aria-hidden="true"></span>
        AUDIT PROBE
      </span>
      <span class="probe__sub">provenance attestation</span>
    </header>

    <fieldset
      class="probe__choices"
      aria-describedby={error ? `probe-err-${groupName}` : undefined}
    >
      <legend class="probe__prompt">{legendText}</legend>

      {#if hasEnvelope}
        {#each candidates as cand, i (cand.jsonl_path || i)}
          <label class="probe__choice">
            <input
              type="radio"
              name={groupName}
              value={cand.jsonl_path || NONE}
              bind:group={selected}
              disabled={submitting}
            />
            <span class="probe__choice-text">
              <span class="probe__slug">{cand.slug || 'stream'}</span>
              <code class="probe__path" title={cand.jsonl_path || ''}>{cand.jsonl_path || '(no path)'}</code>
            </span>
          </label>
        {/each}

        <!-- Explicit none-of-the-above (M11): an empty value => null provenance. -->
        <label class="probe__choice probe__choice--none">
          <input
            type="radio"
            name={groupName}
            value={NONE}
            bind:group={selected}
            disabled={submitting}
          />
          <span class="probe__choice-text">
            <span class="probe__slug">none of the above</span>
            <span class="probe__none-hint">no candidate stream matches this session</span>
          </span>
        </label>
      {:else}
        <p class="probe__waiting" aria-live="polite">
          Waiting for the probe envelope over the live stream...
        </p>
      {/if}
    </fieldset>

    {#if error}
      <p class="probe__error" id={`probe-err-${groupName}`} role="alert">{error}</p>
    {/if}

    <div class="probe__actions">
      <button
        type="button"
        class="probe__sign"
        on:click={sign}
        disabled={!hasEnvelope || submitting}
        aria-label={signLabel}
      >
        {submitting ? 'Signing...' : 'Sign attestation'}
      </button>

      {#if sessionMissing}
        <!-- Paired text guidance, not a color-only block (M4 discipline). -->
        <span class="probe__scopewarn sev-notice" role="note">
          Select a session to enable signing
        </span>
      {/if}
    </div>
  </div>
</article>

<style>
  .probe {
    position: relative;
    display: flex;
    align-items: stretch;
    gap: 0;
    background: var(--calm-surface-raised, #0c1118);
    border: var(--hairline, 1px) solid var(--calm-hairline, #192030);
    border-radius: var(--radius-soft, 4px);
    overflow: hidden;
  }

  /* Attestation rail -- accent-dim, NOT the saturated escalation amber. Keeps
     the probe firmly in the calm register (the lone foreground escalation owns
     the only saturated rail in the product). */
  .probe__rail {
    flex: 0 0 3px;
    background: var(--calm-accent-wash, rgba(245, 158, 11, 0.09));
    align-self: stretch;
  }

  .probe__body {
    flex: 1 1 auto;
    min-width: 0;
    padding: var(--space-4, 10px) var(--space-5, 14px);
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 6px);
  }

  .probe__head {
    display: flex;
    align-items: baseline;
    gap: var(--space-3, 6px);
    flex-wrap: wrap;
  }

  /* Paired label: text + a small dot. The dot is decorative; the words carry
     the signal (M4). sev-notice keeps it in the in-place register. */
  .probe__kind {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: var(--ff-system);
    font-size: var(--fs-chrome, 11px);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--calm-ink-loud, #e8e0cc);
  }

  .probe__dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--calm-accent, #f59e0b);
    flex: 0 0 auto;
  }

  .probe__sub {
    font-family: var(--ff-system);
    font-size: var(--fs-chrome, 11px);
    letter-spacing: 0.04em;
    color: var(--calm-ink-quiet, #948870);
  }

  /* The radio group as a real fieldset -- no chrome border (we draw our own
     calm hairlines), legend carries the prompt as accessible label. */
  .probe__choices {
    margin: 0;
    padding: 0;
    border: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-1, 2px);
  }

  .probe__prompt {
    padding: 0;
    margin: 0 0 var(--space-2, 4px) 0;
    font-family: var(--ff-system);
    font-size: var(--fs-meta, 13px);
    font-weight: 600;
    line-height: var(--lh-tight, 1.25);
    color: var(--calm-ink, #b8b098);
  }

  .probe__choice {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3, 6px);
    padding: var(--space-2, 4px) var(--space-3, 6px);
    border-radius: var(--radius-sharp, 2px);
    cursor: pointer;
    transition: background var(--t-calm, 180ms ease);
  }

  .probe__choice:hover {
    background: var(--calm-surface-hover, #131c2a);
  }

  .probe__choice input[type='radio'] {
    margin-top: 2px;
    accent-color: var(--calm-accent, #f59e0b);
    flex: 0 0 auto;
    cursor: pointer;
  }

  .probe__choice-text {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
  }

  .probe__slug {
    font-family: var(--ff-system);
    font-size: var(--fs-meta, 13px);
    font-weight: 500;
    color: var(--calm-ink, #b8b098);
  }

  /* Monospaced path -- telemetry-grade, truncates rather than wraps so the
     candidate list stays a tight scannable column. Title carries the full
     path for hover + a11y. */
  .probe__path {
    font-family: var(--ff-mono);
    font-size: var(--fs-chrome, 11px);
    letter-spacing: 0.01em;
    color: var(--calm-ink-quiet, #948870);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
    max-width: 100%;
  }

  .probe__choice--none .probe__slug {
    font-style: italic;
    color: var(--calm-ink-chrome, #8a8068);
  }

  .probe__none-hint {
    font-family: var(--ff-system);
    font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink-quiet, #948870);
  }

  .probe__waiting {
    margin: 0;
    font-family: var(--ff-system);
    font-size: var(--fs-meta, 13px);
    font-style: italic;
    color: var(--calm-ink-quiet, #948870);
  }

  /* Inline validation -- WARN register (paired text, never color alone). Uses
     the WARN token family so it reads as "review advised", not an alarm. */
  .probe__error {
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

  .probe__actions {
    display: flex;
    align-items: center;
    gap: var(--space-4, 10px);
    margin-top: var(--space-2, 4px);
    flex-wrap: wrap;
  }

  /* SIGN: a quiet, deliberate affordance -- this is an attestation, not an
     escalation, so it is NOT the amber hero button. Outlined accent, calm. */
  .probe__sign {
    appearance: none;
    font-family: var(--ff-system);
    font-size: var(--fs-meta, 13px);
    font-weight: 650;
    letter-spacing: 0.02em;
    line-height: 1;
    padding: 7px 14px;
    border-radius: var(--radius-sharp, 2px);
    cursor: pointer;
    color: var(--calm-accent, #f59e0b);
    background: var(--calm-accent-wash, rgba(245, 158, 11, 0.09));
    border: 1px solid var(--calm-accent, #f59e0b);
    transition: background var(--t-calm, 180ms ease), color var(--t-calm, 180ms ease);
  }

  .probe__sign:hover:not(:disabled) {
    background: var(--calm-accent, #f59e0b);
    color: var(--calm-surface, #080a0c);
  }

  .probe__sign:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* M17: explicit focus ring on the SIGN button (focus.css also enforces this
     globally; restated locally so a component reset can never erase it). */
  .probe__sign:focus-visible {
    outline: var(--focus-ring-width, 2px) var(--focus-ring-style, solid)
      var(--focus-ring-color, #d97706);
    outline-offset: var(--focus-ring-offset, 2px);
  }

  .probe__scopewarn {
    font-family: var(--ff-system);
    font-size: var(--fs-chrome, 11px);
    letter-spacing: 0.04em;
    color: var(--badge-warn-fg, #ea580c);
  }
</style>
