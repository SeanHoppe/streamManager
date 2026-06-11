<!--
  AgentRoster.svelte -- M13 / M16 the per-agent roster body for Frame B.

  CONTRACT (MUST M13):
    - Renders ONE row per governed sub-agent, keyed by the agent's role/identity
      from /api/agents data. Each row shows:
        * a RoleBadge (the fixed domain-agnostic role schema, M16);
        * the agent's display identity (verbatim from data -- profile_slug, or
          the attribution_plugin / session-scoped id fallback, NEVER a
          hard-coded monitored-project name, M16);
        * chronological event chips drawn from the agent's OWN /api/agents row
          (skill attribution, sidechain marker, mode-override, first/last seen)
          -- ordered oldest -> newest, the activity trail for that agent.
    - ACTIVE-IN-WINDOW agents are PINNED TO TOP: an agent whose last_seen is
      within the operator's activity window (settings.activityWindowSec) sorts
      ahead of idle agents; within each group, most-recently-seen first.
    - NO inter-agent blocking is shown or enforced. There is no edge, lock, or
      "waiting on" relationship between rows; the roster is a flat, independent
      list of observed agents. (M13 + M19 non-goal: not a terminal multiplexer.)

  CRAFT (calm-ambient + monitor-first variable-weight severity):
    at rest the roster is still water -- dim ink, hairline separators. The only
    earned emphasis is the ACTIVE pin (a quiet "live" marker + slightly heavier
    identity type), and the health_monitor role's warmer chip. Nothing here
    pulses or auto-foregrounds: M2 escalation is owned by u-escalation, not by
    agent activity. Idle agents fade (lower opacity) but are never dropped.

  M16 enforcement: this component hard-codes NO governed-target vocabulary. The
  ONLY literals are the generic role schema (in RoleBadge) and SM's own UI
  copy. Every agent identity + event token is carried through from server data.

  M18: presentation-only. The roster does not fetch; the parent supplies the
  already-session-scoped agent rows (from the 8s /api/agents poller in
  u-stores) plus the activity window. Off the verdict hot path.

  File-disjoint: theme tokens + RoleBadge.svelte (sibling leaf) only.
-->
<script>
  import RoleBadge from './RoleBadge.svelte';

  /**
   * agents: the session-scoped /api/agents rows (the poller already filters to
   * the selected session in u-stores). Each row carries:
   *   session_id, profile_slug, attribution_plugin, attribution_skill,
   *   is_sidechain, first_seen, last_seen, mode_override.
   * The ONLY identity source (M16). Defaults to [].
   * @type {Array<Record<string, any>>}
   */
  export let agents = [];

  /**
   * activityWindowSec: the "active in window" span in seconds (FR-UI-9,
   * settings.activityWindowSec). An agent seen within this window is pinned to
   * top + marked live. Clamped defensively to [1, 600] so a malformed setting
   * can never disable the pin logic. Defaults to 10s.
   */
  export let activityWindowSec = 10;

  /**
   * nowMs: injectable clock (test seam). The parent ticks this every second so
   * the active/idle partition re-evaluates without each row owning a timer.
   * Defaults to Date.now() at construction; the parent keeps it live.
   */
  export let nowMs = Date.now();

  // --- Defensive window clamp (mirrors the live dashboard FR-UI-9 clamp). ---
  $: winMs = Math.max(1, Math.min(600, Number(activityWindowSec) || 10)) * 1000;

  /**
   * Parse a server timestamp into epoch-ms. Tolerates:
   *   - epoch seconds (10-digit) / epoch ms (13-digit) numbers or numeric str;
   *   - ISO-8601 strings.
   * Returns NaN when unparseable (=> treated as idle, never crashes the sort).
   * @param {unknown} ts
   * @returns {number}
   */
  function toMs(ts) {
    if (ts == null || ts === '') return NaN;
    if (typeof ts === 'number') return ts < 1e12 ? ts * 1000 : ts;
    const n = Number(ts);
    if (Number.isFinite(n)) return n < 1e12 ? n * 1000 : n;
    const p = Date.parse(String(ts));
    return Number.isFinite(p) ? p : NaN;
  }

  /**
   * Stable agent identity (M16): NEVER a hard-coded name. Prefer the role/skill
   * attribution, fall back to a session-scoped synthetic key so two unattributed
   * agents in different sessions never collapse into one row.
   * @param {Record<string, any>} a
   * @param {number} i
   * @returns {string}
   */
  function agentKey(a, i) {
    const slug = a.profile_slug || a.attribution_plugin || a.agent_id;
    if (slug) return `${a.session_id || 'sess'}::${slug}`;
    return `${a.session_id || 'sess'}::idx${i}`;
  }

  /**
   * The display identity shown next to the role badge. Domain-agnostic (M16):
   * the raw governed identity from data, never a monitored-project literal.
   * @param {Record<string, any>} a
   * @returns {string}
   */
  function displayName(a) {
    return String(a.profile_slug || a.attribution_plugin || a.agent_id || 'unknown');
  }

  /**
   * Build the chronological event-chip trail for ONE agent, oldest -> newest,
   * entirely from that agent's OWN /api/agents row (M13: chronological event
   * chips; M16: data only). Each chip is a paired TEXT label (never colour
   * alone). We never synthesise cross-agent relationships (M13: no blocking).
   *
   * The trail reads as the agent's lifecycle on this row:
   *   [first seen] -> [skill attribution?] -> [mode override?] -> [last seen]
   * Times render relative to the injected clock so the trail stays glanceable.
   * @param {Record<string, any>} a
   * @returns {Array<{ id:string, kind:string, text:string, title:string }>}
   */
  function eventChips(a) {
    /** @type {Array<{ id:string, kind:string, text:string, title:string }>} */
    const chips = [];
    const first = toMs(a.first_seen);
    const last = toMs(a.last_seen);

    if (Number.isFinite(first)) {
      chips.push({
        id: 'first',
        kind: 'seen',
        text: `seen ${relTime(first)}`,
        title: `First seen ${absTime(first)}`,
      });
    }
    // Attribution skill is the closest thing /api/agents carries to a discrete
    // activity token; surface it verbatim (M16) when present.
    if (a.attribution_skill) {
      chips.push({
        id: 'skill',
        kind: 'skill',
        text: String(a.attribution_skill),
        title: `Attributed skill: ${a.attribution_skill}`,
      });
    }
    // A per-agent mode override is an operator/governance annotation on this
    // agent -- shown as a descriptive chip, NOT a control (M13: read-only here).
    if (a.mode_override) {
      chips.push({
        id: 'mode',
        kind: 'mode',
        text: `mode: ${a.mode_override}`,
        title: `Active per-agent mode override: ${a.mode_override}`,
      });
    }
    if (Number.isFinite(last) && (!Number.isFinite(first) || last !== first)) {
      chips.push({
        id: 'last',
        kind: 'active',
        text: `active ${relTime(last)}`,
        title: `Last seen ${absTime(last)}`,
      });
    }
    return chips;
  }

  /**
   * Compact relative time vs the injected clock (e.g. "3s", "2m", "1h").
   * @param {number} ms epoch-ms
   * @returns {string}
   */
  function relTime(ms) {
    const d = Math.max(0, nowMs - ms);
    if (d < 1000) return 'now';
    const s = Math.floor(d / 1000);
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h`;
    return `${Math.floor(h / 24)}d`;
  }

  /**
   * Absolute local time string for titles (a11y -- the chip text is relative
   * but the precise time is reachable on hover / by assistive tech).
   * @param {number} ms epoch-ms
   * @returns {string}
   */
  function absTime(ms) {
    try {
      return new Date(ms).toLocaleString();
    } catch {
      return String(ms);
    }
  }

  // --- Partition + sort (M13: active-in-window pinned to top). ------------
  // Reactive over agents / window / clock. We derive an enriched, sorted list:
  // active agents first (most-recently-seen first), then idle (same order).
  // The sort is a pure projection -- no mutation of the source rows.
  $: enriched = (Array.isArray(agents) ? agents : []).map((a, i) => {
    const last = toMs(a.last_seen);
    const isActive = Number.isFinite(last) && nowMs - last < winMs;
    return {
      key: agentKey(a, i),
      raw: a,
      name: displayName(a),
      role: a.profile_slug ?? null,
      sidechain: Boolean(a.is_sidechain),
      lastMs: Number.isFinite(last) ? last : -Infinity,
      isActive,
      chips: eventChips(a),
    };
  });

  $: sorted = enriched.slice().sort((x, y) => {
    if (x.isActive !== y.isActive) return x.isActive ? -1 : 1; // active pinned top
    return y.lastMs - x.lastMs;                                // newest-seen first
  });

  $: activeCount = sorted.filter((r) => r.isActive).length;
</script>

<!-- role="list" only when there ARE rows: an empty list with no `listitem`
     child trips axe aria-required-children. The empty-state paragraph is not a
     list item, so the wrapper drops the list role while empty. -->
<div class="roster" role={sorted.length === 0 ? undefined : 'list'} aria-label="Sub-agent roster">
  {#if sorted.length === 0}
    <p class="roster__empty">
      Still water. No sub-agents observed for this session yet.
    </p>
  {:else}
    {#if activeCount > 0}
      <!-- A quiet, TEXT divider marking the pinned active group (M13). Paired
           label + count, never colour alone. Screen-reader friendly. -->
      <div class="roster__group" role="presentation">
        <span class="roster__group-dot roster__group-dot--live" aria-hidden="true"></span>
        <span class="roster__group-label">Active in window</span>
        <span class="roster__group-count" aria-label={`${activeCount} active`}>{activeCount}</span>
      </div>
    {/if}

    {#each sorted as a, i (a.key)}
      {#if i === activeCount && activeCount > 0 && activeCount < sorted.length}
        <!-- divider before the first idle agent -->
        <div class="roster__group roster__group--idle" role="presentation">
          <span class="roster__group-dot" aria-hidden="true"></span>
          <span class="roster__group-label">Idle</span>
          <span class="roster__group-count">{sorted.length - activeCount}</span>
        </div>
      {/if}

      <div
        class="agent-row"
        class:agent-row--active={a.isActive}
        class:agent-row--idle={!a.isActive}
        role="listitem"
        aria-label={`Sub-agent ${a.name}${a.isActive ? ' (active)' : ' (idle)'}`}
      >
        <div class="agent-row__lead">
          <RoleBadge role={a.role} sidechain={a.sidechain} />
          <span class="agent-row__name" title={a.name}>{a.name}</span>
          {#if a.isActive}
            <!-- paired TEXT "live" marker (never colour alone). Indicates the
                 agent is active in the operator's window; NOT an escalation. -->
            <span class="agent-row__live" title="Active within the activity window">
              <span class="agent-row__live-dot" aria-hidden="true"></span>live
            </span>
          {/if}
        </div>

        {#if a.chips.length > 0}
          <!-- M13: chronological event chips for THIS agent only (oldest ->
               newest). No inter-agent relationship is drawn. -->
          <div class="agent-row__events" aria-label="Activity trail">
            {#each a.chips as chip (chip.id)}
              <span class="event-chip event-chip--{chip.kind}" title={chip.title}>{chip.text}</span>
            {/each}
          </div>
        {/if}
      </div>
    {/each}
  {/if}
</div>

<style>
  .roster {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .roster__empty {
    margin: 0;
    color: var(--sm-text-dim, #94a3b8);
    font-size: 0.82rem;
    font-style: italic;
    /* No opacity drag: --sm-text-dim is the AA-documented dim token; compositing
       opacity on top pushed it under WCAG AA (axe color-contrast FAIL). The
       italic + dim color carry the quiet affordance without it. */
  }

  /* Group divider (active / idle). TEXT-led, hairline, calm. */
  .roster__group {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.5rem 0.1rem 0.3rem;
    font-size: 0.66rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--sm-text-dim, #94a3b8);
  }
  .roster__group--idle {
    margin-top: 0.35rem;
    border-top: 1px dashed var(--sm-border, rgba(148, 163, 184, 0.16));
    padding-top: 0.55rem;
  }
  .roster__group-dot {
    width: 0.42rem;
    height: 0.42rem;
    border-radius: 50%;
    background: var(--sm-text-dim, #94a3b8);
    flex: 0 0 auto;
    opacity: 0.7;
  }
  .roster__group-dot--live {
    background: var(--sm-live-fg, #22c55e);
    opacity: 1;
  }
  .roster__group-label {
    flex: 1 1 auto;
  }
  .roster__group-count {
    font-variant-numeric: tabular-nums;
    color: var(--sm-text, #cbd5e1);
  }

  /* One agent row. Calm at rest; active rows earn a quiet left accent + heavier
     identity type (monitor-first variable-weight severity). No blocking chrome. */
  .agent-row {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    padding: 0.5rem 0.6rem;
    border-radius: 6px;
    border: 1px solid transparent;
    transition: background-color 0.2s ease, opacity 0.2s ease, border-color 0.2s ease;
  }

  .agent-row--active {
    background: var(--sm-row-active-bg, rgba(148, 163, 184, 0.07));
    border-color: var(--sm-border, rgba(148, 163, 184, 0.16));
    position: relative;
  }
  .agent-row--active::before {
    content: '';
    position: absolute;
    inset: 0.4rem auto 0.4rem 0;
    width: 2px;
    border-radius: 2px;
    background: var(--sm-live-fg, #22c55e);
    opacity: 0.7;
  }

  /* Idle agents fade but are NEVER dropped (M13: chronological roster, full). */
  .agent-row--idle {
    opacity: 0.62;
  }

  .agent-row__lead {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    min-width: 0;
  }

  .agent-row__name {
    font-family: var(--sm-font-mono, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.78rem;
    font-weight: 500;
    color: var(--sm-text, #cbd5e1);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
    flex: 1 1 auto;
  }
  /* Active rows lift the identity weight slightly -- type carries severity. */
  .agent-row--active .agent-row__name {
    font-weight: 700;
    color: var(--sm-text-strong, #e2e8f0);
  }

  .agent-row__live {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    flex: 0 0 auto;
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--sm-live-fg, #16a34a);
  }
  .agent-row__live-dot {
    width: 0.4rem;
    height: 0.4rem;
    border-radius: 50%;
    background: currentColor;
  }

  .agent-row__events {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    padding-left: 0.1rem;
  }

  .event-chip {
    font-family: var(--sm-font-mono, var(--ff-mono, ui-monospace, monospace));
    font-size: 0.66rem;
    line-height: 1;
    padding: 3px 6px;
    border-radius: 3px;
    color: var(--sm-text-dim, #94a3b8);
    background: var(--sm-chip-bg, rgba(148, 163, 184, 0.08));
    border: 1px solid var(--sm-border, rgba(148, 163, 184, 0.14));
    white-space: nowrap;
  }
  /* Editorial, non-chromatic distinction between trail token kinds. The TEXT is
     always the signal; these are subtle tints, never the sole meaning. */
  .event-chip--active {
    color: var(--sm-live-fg, #16a34a);
    border-color: var(--sm-live-bd, rgba(34, 197, 94, 0.3));
  }
  .event-chip--mode {
    color: var(--sm-warn-fg, #ca8a04);
    border-color: var(--sm-warn-bd, rgba(202, 138, 4, 0.3));
  }

  @media (prefers-reduced-motion: reduce) {
    :global(html:not([data-motion='allow'])) .agent-row {
      transition: none;
    }
  }
</style>
