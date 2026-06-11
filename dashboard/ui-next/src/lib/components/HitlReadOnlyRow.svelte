<!--
  HitlReadOnlyRow.svelte -- the HITL-OFF read-only decision row (opt-in surface).

  CONTRACT (inviolable MUST M7):
    - When HITL is OFF, a decision renders READ-ONLY: no Approve/Override/Dismiss
      affordances, only an OBSERVING badge (M4 paired label+color) and an
      explicit "Take action" affordance.
    - Activating "Take action" FLIPS the session to HITL ON SYNC: it POSTs
      /api/hitl/mode {session_id, mode:'sync'} (the SERVER emits
      hitl_mode_promoted), then asks the parent to surface the ranked list for
      this row (dispatch `take-action` -> HitlDock promotes the row to a pending
      HitlPendingRow). The opt-in is persisted so the same recurring message
      pre-resolves to the ON path next time (reinforcement, M6/M7).
    - It NEVER mutates the governance verdict directly -- it only requests the
      mode promotion + surfaces the ranked picker. The gate stays absolute.

    M4  The status indicator is the paired OBSERVING badge (slate, no border) --
        color alone is never a signal; the aria-label = the trigger reason.

    M8  If the envelope carries a Learn-Mode bias, the AdvisoryChip renders it as
        a dashed NON-VERDICT chip ABOVE the (single) Take-action affordance. It
        never bypasses the gate, never toasts, never offers undo.

    M15 Self-exclude is upstream (HitlDock filters the SM's own session). This
        row renders governed-target identity FROM DATA only (M16).

    M18 Post-hoc: the only network call is the operator-initiated mode POST.

  CRAFT (calm-ambient spine, KingMode): a read-only row is pure still water --
  slate OBSERVING badge, quiet ink, no motion, no amber. The single "Take
  action" affordance is a calm, low-emphasis text button: the operator CAN lean
  in, but the resting state never nags. This is the discipline of M7 made
  visual: OFF is genuinely calm, not a muted alarm.
-->
<script>
  import { createEventDispatcher } from 'svelte';
  import Badge from './Badge.svelte';
  import AdvisoryChip from './AdvisoryChip.svelte';
  import { postHitlMode } from '../api.js';

  /**
   * decision: one read-only decision envelope (FROM DATA -- M16). Tolerant shape:
   *   { id|decision_id, message_hash|matched_hash|message_id, session_id,
   *     reason|reasoning, action, layer, confidence,
   *     advisory|learn_mode_bias, advisory_confidence }
   * @type {Record<string, any>}
   */
  export let decision = {};

  /**
   * sessionLabel: governed-target identity for attribution, FROM DATA (M16).
   * Optional; absent => no attribution line.
   * @type {string}
   */
  export let sessionLabel = '';

  const dispatch = createEventDispatcher();

  // -- Envelope field resolution (tolerant; domain-agnostic, M16) ------------
  $: decisionId = decision?.id ?? decision?.decision_id ?? decision?.pending_id ?? null;
  $: messageHash =
    (decision?.message_hash ?? decision?.matched_hash ?? decision?.message_id ?? '')
      .toString()
      .trim();
  $: sessionId = decision?.session_id ?? null;
  $: reasonText = (() => {
    const r = (decision?.reason ?? decision?.reasoning ?? '').toString().trim();
    return r !== '' ? r : 'Observing -- no action required';
  })();
  $: advisoryBias = (decision?.advisory ?? decision?.learn_mode_bias ?? decision?.bias ?? '')
    .toString();
  $: advisoryConfidence = decision?.advisory_confidence ?? decision?.bias_confidence ?? null;
  $: hasSession = typeof sessionId === 'string' && sessionId.trim() !== '';

  // Persisted opt-in (M7 reinforcement): once an operator takes action on a
  // message hash, remember it so the recurring message routes to the ON path.
  const LS_OPTIN_PREFIX = 'sm.next.hitlOptIn.';
  function persistOptIn(hash) {
    if (!hash || typeof localStorage === 'undefined') return;
    try {
      localStorage.setItem(LS_OPTIN_PREFIX + hash, '1');
    } catch {
      /* private-mode / quota -- non-fatal */
    }
  }

  let promoting = false; // in-flight guard for the mode POST

  /**
   * M7: flip the session to HITL ON SYNC, then surface the ranked list. We POST
   * /api/hitl/mode {mode:'sync'} (server emits hitl_mode_promoted), persist the
   * opt-in keyed to the message hash, and ask the parent to promote this row to
   * an editable pending row. On failure we roll back the in-flight state and
   * tell the parent the promotion did not take (no toast, no error chrome).
   */
  async function takeAction() {
    if (promoting) return;
    if (!hasSession) {
      // Cannot promote a mode against "no session"; signal intent without POST
      // so the parent can decide (it should not render this affordance without
      // a session, but we guard anyway).
      dispatch('take-action-blocked', { decisionId, reason: 'missing session_id' });
      return;
    }
    promoting = true;
    persistOptIn(messageHash); // reinforcement (M7)
    try {
      await postHitlMode({ session_id: sessionId, mode: 'sync' });
      // The server has (or will) emit hitl_mode_promoted. Ask the parent to
      // surface the ranked list for this row (promote OFF row -> ON pending).
      dispatch('take-action', {
        decisionId,
        sessionId,
        messageHash,
        decision,
        mode: 'sync',
      });
    } catch (err) {
      dispatch('take-action-failed', { decisionId, sessionId, decision, error: err });
    } finally {
      promoting = false;
    }
  }
</script>

<article
  class="hror"
  data-decision-id={decisionId ?? ''}
  data-hitl-mode="off"
>
  <!-- HEADER: paired OBSERVING badge (M4, slate, no border) + governed-target
       attribution rendered FROM DATA (M16). aria-label = the trigger reason. -->
  <header class="hror__head">
    <Badge variant="observing" reason={reasonText} />
    {#if sessionLabel}
      <span class="hror__attr" title={sessionLabel}>
        <span class="hror__attr-tag" aria-hidden="true">session</span>
        <span class="hror__attr-val">{sessionLabel}</span>
      </span>
    {/if}
  </header>

  <!-- The recorded decision as read-only prose -- the operator-facing "why".
       No editable affordance: HITL OFF rows are observational (M7). -->
  <p class="hror__reason sev-quiet">{reasonText}</p>

  <!-- M8: Learn-Mode advisory chip ABOVE the Take-action affordance. Non-verdict,
       dashed, never bypasses the gate. Renders only when a bias is present. -->
  <AdvisoryChip bias={advisoryBias} confidence={advisoryConfidence} />

  <!-- M7: the single opt-in affordance. Calm, low-emphasis text button. The OFF
       row never nags; the operator CAN lean in. Only rendered with a session. -->
  {#if hasSession}
    <div class="hror__actions">
      <button
        type="button"
        class="hror__take"
        on:click={takeAction}
        disabled={promoting}
        aria-label={`Take action (switch to HITL SYNC and decide): ${reasonText}`}
      >
        {promoting ? 'Switching to SYNC...' : 'Take action'}
      </button>
      <span class="hror__take-hint sev-quiet" aria-hidden="true">
        switches this session to HITL SYNC
      </span>
    </div>
  {/if}
</article>

<style>
  /* Pure still water: slate OBSERVING resting state, quiet ink, no amber, no
     motion. The discipline of M7 made visual -- OFF is genuinely calm. */
  .hror {
    display: flex;
    flex-direction: column;
    gap: var(--space-2, 4px);
    padding: var(--space-4, 10px) var(--space-5, 14px);
    background: var(--calm-surface-row, #0e141e);
    border: 1px solid var(--calm-hairline, #cbd5e1);
    /* Slate left rail (NOT amber) -- this row carries no escalation. */
    border-left: 3px solid var(--badge-obs-border, #cbd5e1);
    border-radius: var(--radius-soft, 4px);
  }

  .hror__head {
    display: flex;
    align-items: center;
    gap: var(--space-4, 10px);
    flex-wrap: wrap;
    min-width: 0;
  }

  .hror__attr {
    display: inline-flex;
    align-items: baseline;
    gap: var(--space-2, 4px);
    min-width: 0;
  }
  .hror__attr-tag {
    font-size: var(--fs-chrome, 11px);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--calm-ink-quiet, #64748b);
  }
  .hror__attr-val {
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink-chrome, #8a8068);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 24ch;
  }

  .hror__reason {
    margin: 0;
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: var(--fs-meta, 13px);
    line-height: var(--lh-body, 1.5);
    color: var(--calm-ink-quiet, #64748b);
    overflow-wrap: anywhere;
  }

  .hror__actions {
    display: flex;
    align-items: center;
    gap: var(--space-3, 6px);
    flex-wrap: wrap;
    margin-top: var(--space-1, 2px);
  }

  /* The opt-in affordance: a calm, low-emphasis text button. Quiet at rest;
     gains a slate underline-ish edge on hover. Never amber (no escalation). */
  .hror__take {
    appearance: none;
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: var(--fs-meta, 13px);
    font-weight: 600;
    line-height: 1;
    padding: 6px 12px;
    border-radius: var(--radius-sharp, 2px);
    background: transparent;
    color: var(--calm-ink, #b8b098);
    border: 1px solid var(--calm-hairline, #cbd5e1);
    cursor: pointer;
    transition: background var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease),
      color var(--t-calm, 180ms ease);
  }
  .hror__take:hover:not(:disabled) {
    background: var(--calm-surface-hover, #131c2a);
    border-color: var(--calm-ink-chrome, #8a8068);
    color: var(--calm-ink-loud, #e8e0cc);
  }
  .hror__take:disabled {
    cursor: default;
    opacity: 0.6;
  }

  .hror__take-hint {
    font-size: var(--fs-chrome, 11px);
    color: var(--calm-ink-quiet, #64748b);
    font-style: italic;
  }
</style>
