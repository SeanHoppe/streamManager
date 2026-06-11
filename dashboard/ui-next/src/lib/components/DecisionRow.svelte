<script context="module">
  // DecisionRow.svelte -- one calm verdict line in the REPL/decision stream.
  //
  // CONTRACT (frozen behavioural layer, re-formed craft layer):
  //  - M4: the row's actionability is shown with a PAIRED label+color Badge
  //    (the shared Badge primitive). Color is never the only signal -- the
  //    Badge enforces a text label structurally. The action verdict
  //    (ALLOW/SUGGEST/GUIDE/INTERVENE/BLOCK) is ALSO rendered as text, never
  //    color-only, mirroring the live feed's `badge-<ACTION>` contract.
  //  - M7 (HITL OFF = read-only + opt-in): a row whose session is in HITL OFF
  //    renders read-only with an OBSERVING badge PLUS an explicit "Take action"
  //    affordance. Clicking it does NOT itself flip state here (this is a view
  //    leaf); it dispatches `takeaction` up to u-hitl-core, which performs the
  //    promotion to HITL ON SYNC, persists, and emits hitl_mode_promoted.
  //  - M8 (advisory chip): a Learn-Mode bias is rendered ONLY as a dashed,
  //    non-verdict informational chip with the exact advisory title. It sits
  //    ABOVE any action affordance, never replaces the operator gate, never
  //    toasts, never offers undo. (The pending HITL ranked-list itself is owned
  //    by u-hitl-core; this leaf only renders the read-only decision + the
  //    advisory chip + the opt-in hook.)
  //  - M16 (domain-agnostic): every governed identifier (session_id, agent
  //    profile slug, model id, content) is rendered from the row DATA. No
  //    monitored-project vocabulary is hard-coded.
  //  - M18: pure presentation. No fetch, no verdict-path work.
  //
  // CRAFT (calm-ambient spine): the resting row is still water -- OBSERVING is
  // a quiet slate badge, no border, no motion. Severity is carried by variable
  // TYPE WEIGHT (monitor-first graft) on the action token, not by chrome. Only
  // a true escalation (a static-rule BLOCK, the M2 allow-list member) earns a
  // louder edge; everything else stays calm.

  /** Canonical governance action verdicts (frozen contract order). */
  export const ACTION_ORDER = Object.freeze([
    'ALLOW',
    'SUGGEST',
    'GUIDE',
    'INTERVENE',
    'BLOCK',
  ]);

  /**
   * Map a governance action verdict to its M4 paired-badge variant. The BLOCK
   * verdict pairs with the BLOCKED badge; everything else is a quiet
   * OBSERVING/DECIDED reading at rest -- color is always accompanied by the
   * action TEXT token below, so this mapping never makes color a sole signal.
   * @param {string} action
   * @returns {'blocked'|'decided'|'observing'}
   */
  function badgeVariantForAction(action) {
    if (action === 'BLOCK') return 'blocked';
    if (action === 'INTERVENE') return 'decided';
    return 'observing';
  }

  /** Severity weight by action -- type emphasis only (never the foreground gate). */
  function weightForAction(action) {
    switch (action) {
      case 'BLOCK':
        return 'urgent';
      case 'INTERVENE':
        return 'signal';
      case 'GUIDE':
        return 'notice';
      default:
        return 'calm';
    }
  }
</script>

<script>
  import Badge from './Badge.svelte';
  import { createEventDispatcher } from 'svelte';
  import { escalationForDecision } from '../sse.js';

  /**
   * row: the decision record from /api/decisions or an SSE decision payload.
   * Carries (per api.js): id, message_id, action, confidence, reasoning,
   * matched_hash, timestamp, model_used, layer, content, direction,
   * session_id, profile_slug, agent_profile_slug, attribution_plugin.
   * @type {Record<string, any>}
   */
  export let row = {};

  /**
   * hitlOn: whether the selected session is in HITL ON. When false (HITL OFF)
   * the row renders read-only with an OBSERVING badge + a Take-action opt-in
   * (M7). When true, the row is still read-only HERE -- the ranked-list /
   * pending interaction is owned by u-hitl-core; this leaf only shows the
   * decided verdict and the advisory chip.
   */
  export let hitlOn = false;

  /**
   * advisoryBias: optional Learn-Mode advisory pre-fill (M8). When present it
   * renders as a dashed non-verdict chip. Shape is intentionally loose: any
   * object with a human `label`/`text` is accepted; we never treat it as a
   * verdict. null/undefined => no chip.
   * @type {{ label?:string, text?:string, suggested_action?:string }|null}
   */
  export let advisoryBias = null;

  const dispatch = createEventDispatcher();

  // -- Derived display fields (all from DATA -- M16) --------------------------
  $: action = String(row.action || '').toUpperCase() || '?';
  $: knownAction = ACTION_ORDER.includes(action);
  $: badgeVariant = badgeVariantForAction(action);
  $: actionWeight = weightForAction(action);

  // M2: a static-rule BLOCK is the lone foreground-eligible decision. We do NOT
  // foreground from this leaf (that is the shell's job via the escalation
  // store); we only mark the row so its edge reads as the genuine escalation.
  $: isEscalation = !!escalationForDecision(row);

  $: sid = String(row.session_id || '');
  $: sidShort = sid ? sid.slice(0, 8) : '';
  $: profileSlug = row.profile_slug || row.agent_profile_slug || '';
  $: plugin = row.attribution_plugin || '';
  $: agentTitle = plugin
    ? `${plugin} (${profileSlug || 'unknown'})`
    : profileSlug || 'no profile';
  $: agentLabel = profileSlug || '-';
  $: model = (row.model_used || '').toString();
  $: layerNum = row.layer == null ? 0 : Number(row.layer);
  $: layerLbl = `L${Number.isFinite(layerNum) ? layerNum : 0}`;
  $: layerTip = layerNum <= 1 ? 'no LLM' : model || 'no LLM';
  $: confPct = Math.round((Number(row.confidence) || 0) * 100);
  $: content = (row.content || '').toString();
  $: reasoning = (row.reasoning || '').toString();
  $: ts = fmtTs(row.timestamp);

  // The Take-action affordance only exists when the row has a decision id (the
  // suggestions endpoint can't be hit without one -- graceful degrade, mirrors
  // the live feed's FR-UI-4 rule).
  $: canTakeAction = !hitlOn && !!row.id;

  // M8: render the advisory chip only when a bias exists. The displayed text is
  // data-driven; the TITLE is the exact frozen advisory string.
  $: advisoryText = advisoryBias
    ? String(advisoryBias.label || advisoryBias.text || advisoryBias.suggested_action || '')
    : '';
  $: hasAdvisory = advisoryText.trim() !== '';

  // The read-only verdict badge reason (M4 paired aria-label/title): a stable,
  // human, data-derived sentence -- never empty.
  $: badgeReason = isEscalation
    ? `Static-rule ${action} -- hard governance trigger`
    : action === 'BLOCK'
      ? `Message blocked (${confPct}% confidence)`
      : `Observing -- ${action} decision recorded (${confPct}% confidence)`;

  function fmtTs(t) {
    if (!t) return '-';
    const d = new Date(Number(t) * 1000);
    if (Number.isNaN(d.getTime())) return '-';
    const pad = (n) => String(n).padStart(2, '0');
    const ms = String(d.getMilliseconds()).padStart(3, '0');
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${ms}`;
  }

  function onTakeAction() {
    // M7: this leaf NEVER flips HITL state itself. It dispatches the intent up;
    // u-hitl-core promotes to HITL ON SYNC, persists, emits hitl_mode_promoted.
    dispatch('takeaction', {
      decisionId: row.id,
      messageId: row.message_id,
      sessionId: sid,
      messageHash: row.matched_hash || row.message_id || null,
    });
  }
</script>

<article
  class="drow"
  class:drow--escalation={isEscalation}
  data-action={knownAction ? action : ''}
  data-decision-id={row.id || ''}
  data-session={sid}
  aria-label={`${action} decision${sidShort ? ` in session ${sidShort}` : ''}`}
>
  <header class="drow__head">
    <span class="drow__ts" title={ts}>{ts}</span>

    <!-- M4: the action verdict is rendered as TEXT (never color-only). The
         tinted token carries weight (severity-as-type), but the label below it
         is the load-bearing signal. -->
    <span
      class="drow__action drow__action--{knownAction ? action : 'unknown'}"
      data-weight={actionWeight}
      title={`Action: ${action}`}
    >{action}</span>

    <!-- M4 paired Badge: OBSERVING at rest / BLOCKED / DECIDED. The Badge
         primitive throws on a missing label, so color-without-text is
         structurally impossible. -->
    <Badge variant={badgeVariant} reason={badgeReason} />

    <span class="drow__layer" title={layerTip}>{layerLbl}</span>

    <span class="drow__conf" title={`${confPct}% confidence`}>
      <span class="drow__conf-bar" aria-hidden="true">
        <span class="drow__conf-fill" style={`width:${confPct}%`}></span>
      </span>
      <span class="drow__conf-num">{confPct}%</span>
    </span>
  </header>

  <div class="drow__body">
    {#if content}
      <p class="drow__content" title={content}>{content}</p>
    {/if}
    {#if reasoning}
      <p class="drow__reason" title={reasoning}>{reasoning}</p>
    {/if}
  </div>

  <!-- M8: Learn-Mode advisory chip. Dashed, non-verdict, informational ONLY.
       Sits ABOVE any action affordance. Exact frozen title. Never a button,
       never a toast, never offers undo. -->
  {#if hasAdvisory}
    <div
      class="drow__advisory"
      role="note"
      title="advisory only -- operator decision still required"
      aria-label={`Advisory only -- operator decision still required. ${advisoryText}`}
    >
      <span class="drow__advisory-tag">ADVISORY</span>
      <span class="drow__advisory-text">{advisoryText}</span>
    </div>
  {/if}

  <footer class="drow__foot">
    <span class="drow__agent" title={agentTitle}>
      <span class="drow__agent-chip" class:drow__agent-chip--unknown={!profileSlug || profileSlug === 'unknown'}>
        {agentLabel}
      </span>
    </span>
    <span class="drow__sess" title={sid}>{sidShort || '-'}</span>

    <!-- M7: HITL OFF read-only + explicit opt-in. The Take-action button does
         NOT mutate state here; it dispatches up to u-hitl-core. Present only
         when the row carries a decision id (graceful degrade). -->
    {#if canTakeAction}
      <button
        type="button"
        class="drow__take"
        on:click={onTakeAction}
        title="Promote this session to HITL ON sync and open the override list"
        aria-label="Take action: promote to HITL on, sync mode, and open the ranked override list"
      >Take action</button>
    {/if}
  </footer>
</article>

<style>
  /* Calm resting row -- still water. Theme tokens drive every color so the
     three themes (obsidian/phosphor/paper) retint with no class churn. */
  .drow {
    display: grid;
    grid-template-columns: 1fr;
    gap: 0.3rem;
    padding: 0.55rem 0.7rem 0.5rem;
    border: 1px solid var(--border, rgba(148, 163, 184, 0.16));
    border-left-width: 2px;
    border-left-color: transparent;
    border-radius: 7px;
    background: var(--bg-row, rgba(15, 23, 42, 0.35));
    transition: border-color 0.2s ease, background 0.2s ease;
  }
  .drow + :global(.drow) { margin-top: 0.4rem; }
  .drow:hover { background: var(--bg-row-hover, rgba(19, 28, 42, 1)); }

  /* M2 escalation edge: ONLY the static-rule BLOCK earns the louder amber
     edge. calm-ambient thesis -- saturation is spent here, nowhere else. */
  .drow--escalation {
    border-left-color: #d97706;
    background: var(--bg-row-flash, rgba(217, 119, 6, 0.06));
  }

  .drow__head {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.5rem 0.65rem;
    min-width: 0;
  }

  .drow__ts {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.7rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-dim, #94a3b8);
    flex: 0 0 auto;
  }

  /* Variable-weight typographic severity (monitor-first graft): the action
     token's WEIGHT rises with severity. The text label is always present, so
     the color tint below is a SECOND channel, never the sole signal (M4). */
  .drow__action {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.72rem;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    flex: 0 0 auto;
    color: var(--text-dim, #94a3b8);
  }
  .drow__action[data-weight='calm']   { font-weight: 400; }
  .drow__action[data-weight='notice'] { font-weight: 500; }
  .drow__action[data-weight='signal'] { font-weight: 600; }
  .drow__action[data-weight='urgent'] { font-weight: 700; }

  .drow__action--ALLOW     { color: var(--c-allow, #22c55e); }
  .drow__action--SUGGEST   { color: var(--c-suggest, #84cc16); }
  .drow__action--GUIDE     { color: var(--c-guide, #eab308); }
  .drow__action--INTERVENE { color: var(--c-intervene, #f97316); }
  .drow__action--BLOCK     { color: var(--c-block, #ef4444); }
  .drow__action--unknown   { color: var(--text-dim, #94a3b8); }

  .drow__layer {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.66rem;
    letter-spacing: 0.04em;
    color: var(--text-ui, #8a8068);
    border: 1px solid var(--border, rgba(148, 163, 184, 0.25));
    border-radius: 3px;
    padding: 0.05rem 0.3rem;
    flex: 0 0 auto;
  }

  .drow__conf {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    margin-left: auto;
    flex: 0 0 auto;
  }
  .drow__conf-bar {
    width: 3.5rem;
    height: 0.32rem;
    border-radius: 999px;
    background: var(--border, rgba(148, 163, 184, 0.25));
    overflow: hidden;
  }
  .drow__conf-fill {
    display: block;
    height: 100%;
    background: var(--accent, #38bdf8);
    border-radius: 999px;
  }
  .drow__conf-num {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.68rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-dim, #94a3b8);
    min-width: 2.6ch;
    text-align: right;
  }

  .drow__body { min-width: 0; }
  .drow__content {
    margin: 0;
    font-size: 0.82rem;
    line-height: 1.35;
    color: var(--text, #e2e8f0);
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }
  .drow__reason {
    margin: 0.15rem 0 0;
    font-size: 0.72rem;
    line-height: 1.3;
    color: var(--text-dim, #94a3b8);
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 1;
    -webkit-box-orient: vertical;
  }

  /* M8: advisory chip. Dashed, subdued, clearly informational. Visually
     subordinate to any action affordance below. Never reads as a verdict. */
  .drow__advisory {
    display: inline-flex;
    align-items: baseline;
    gap: 0.5rem;
    align-self: start;
    padding: 0.2rem 0.5rem;
    border: 1px dashed var(--text-dim, #94a3b8);
    border-radius: 4px;
    background: transparent;
    max-width: 100%;
  }
  .drow__advisory-tag {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.6rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-ui, #8a8068);
    flex: 0 0 auto;
  }
  .drow__advisory-text {
    font-size: 0.72rem;
    color: var(--text-dim, #94a3b8);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }

  .drow__foot {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    min-width: 0;
  }
  .drow__agent { min-width: 0; flex: 0 1 auto; }
  .drow__agent-chip {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.66rem;
    letter-spacing: 0.03em;
    color: var(--text-ui, #8a8068);
    border: 1px solid var(--border, rgba(148, 163, 184, 0.25));
    border-radius: 3px;
    padding: 0.05rem 0.35rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    display: inline-block;
    max-width: 14ch;
  }
  .drow__agent-chip--unknown { opacity: 0.6; font-style: italic; }

  .drow__sess {
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.66rem;
    color: var(--text-dim, #94a3b8);
    flex: 0 0 auto;
  }

  /* M7 opt-in affordance. Quiet at rest; amber focus ring (M17). */
  .drow__take {
    appearance: none;
    margin-left: auto;
    flex: 0 0 auto;
    border: 1px solid var(--border, rgba(148, 163, 184, 0.3));
    background: transparent;
    color: var(--text-dim, #94a3b8);
    font-family: var(--font-d, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.66rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    padding: 0.22rem 0.55rem;
    border-radius: 5px;
    cursor: pointer;
    transition: color 0.18s ease, border-color 0.18s ease;
  }
  .drow__take:hover {
    color: #d97706;
    border-color: #d97706;
  }
  /* M17: 2px solid amber focus ring + 2px offset on every interactive el. */
  .drow__take:focus-visible {
    outline: 2px solid #d97706;
    outline-offset: 2px;
  }

  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .drow,
    :global(html:not([data-motion='allow'])) .drow__take { transition: none; }
  }
</style>
