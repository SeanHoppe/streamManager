<!--
  RoleBadge.svelte -- M13 / M16 per-agent role chip (leaf).

  CONTRACT (MUST M13 + M16):
    - Renders ONE agent's role as a paired TEXT label + color chip. Color is
      never alone: the role token text is the load-bearing signal and is always
      present (a blank role coerces to the generic "unknown" schema member, so
      there is no text-less chip code path). Mirrors the M4 paired-signal
      discipline at the role grain.
    - The role vocabulary is the FIXED, DOMAIN-AGNOSTIC schema (M16):
        prompt_constructor, developer, code_reviewer, tester,
        frontend_architect, researcher, strategic_advisor, health_monitor,
        sub_agent, unknown
      NO monitored-project vocabulary is hard-coded here. The agent's identity
      (display name) is supplied by the parent verbatim from /api/agents data;
      this leaf only classifies the generic ROLE token. Any role string the
      server emits that is NOT a known schema member is normalised to a single
      generic bucket and rendered as-is in a neutral chip -- it is never
      dropped, and it never gains a privileged colour.
    - NO inter-agent blocking is shown or implied. A role chip is a label, not
      a gate; there is no "blocks"/"blocked-by" relationship in this surface.

  CRAFT (calm-ambient spine + monitor-first variable-weight severity):
    severity here is editorial, not chromatic -- the generic-schema roles sit
    in slate-calm at rest, and only the operational-attention roles
    (health_monitor) carry a slightly warmer, heavier token. No role chip ever
    pulses or escalates: escalation is reserved for the M2 allow-list elsewhere.

  File-disjoint: theme tokens + self-contained styles only. Consumes no
  endpoints and imports no sibling module.
-->
<script context="module">
  /**
   * The frozen, domain-agnostic role schema (M16). Order is the canonical
   * display/legend order. Each entry maps a schema member to:
   *   - tone:  a NON-chromatic severity class (calm | watch | muted) chosen so
   *            colour is editorial, never the sole signal (the text label is).
   *   - hint:  a plain-English, domain-agnostic description for title/aria.
   * NOTE: these descriptions describe GENERIC software-agent roles only -- no
   * monitored-project vocabulary appears here (M16).
   * @type {Readonly<Record<string,{tone:string,hint:string}>>}
   */
  export const ROLE_SCHEMA = Object.freeze({
    prompt_constructor: { tone: 'calm',  hint: 'Constructs prompts / task framing' },
    developer:          { tone: 'calm',  hint: 'Writes or edits code' },
    code_reviewer:      { tone: 'calm',  hint: 'Reviews proposed code changes' },
    tester:             { tone: 'calm',  hint: 'Runs or authors tests' },
    frontend_architect: { tone: 'calm',  hint: 'Designs UI / frontend structure' },
    researcher:         { tone: 'calm',  hint: 'Investigates / gathers context' },
    strategic_advisor:  { tone: 'calm',  hint: 'Advises on strategy / direction' },
    health_monitor:     { tone: 'watch', hint: 'Monitors run health / signals' },
    sub_agent:          { tone: 'muted', hint: 'Generic spawned sub-agent' },
    unknown:            { tone: 'muted', hint: 'Role not attributed' },
  });

  /** The canonical ordered list of schema keys (legend / sort order). */
  export const ROLE_ORDER = Object.freeze(Object.keys(ROLE_SCHEMA));

  /**
   * Normalise an arbitrary server-supplied role token into a known schema
   * member when possible, WITHOUT losing the original string. Returns the
   * matched schema key, or null when the token is not a recognised member.
   * Recognises exact, case-insensitive, and separator-variant spellings
   * (e.g. "Frontend-Architect" / "frontend architect" -> frontend_architect).
   * @param {unknown} role
   * @returns {string|null}
   */
  export function resolveRole(role) {
    if (role == null) return null;
    const raw = String(role).trim();
    if (raw === '') return null;
    if (raw in ROLE_SCHEMA) return raw;
    const norm = raw.toLowerCase().replace(/[\s.-]+/g, '_');
    if (norm in ROLE_SCHEMA) return norm;
    return null;
  }
</script>

<script>
  /**
   * role: the agent's role token (typically /api/agents profile_slug). May be
   * any string the server emits; unknown tokens render in a neutral chip with
   * the raw text preserved (never dropped). Defaults to the schema 'unknown'
   * member so there is never a text-less chip.
   * @type {string|null|undefined}
   */
  export let role = undefined;

  /**
   * sidechain: M13 -- a sidechain agent is a spawned sub-agent. When true the
   * chip carries a paired, TEXT "side" marker (never colour alone). Mirrors the
   * live dashboard `[side]` suffix without implying any blocking relationship.
   */
  export let sidechain = false;

  /**
   * size: 'sm' (default, in-roster) | 'xs' (dense legend). Visual only.
   */
  export let size = 'sm';

  // --- Resolve the role to a known schema member (or a preserved raw token). ---
  $: matched = resolveRole(role);

  // The text that renders in the chip. ALWAYS non-empty (M16 + paired-signal):
  //  - a recognised member renders its canonical schema key;
  //  - an unrecognised non-empty token renders verbatim (lowercased for calm
  //    typographic consistency, but never dropped);
  //  - a blank/absent role renders the generic 'unknown' schema member.
  $: rawToken = role == null ? '' : String(role).trim();
  $: displayRole = matched ?? (rawToken === '' ? 'unknown' : rawToken.toLowerCase());

  // Tone is non-chromatic severity. Unrecognised tokens get the muted bucket so
  // an unknown role can never accidentally inherit a privileged colour (M16:
  // governed-target identity is data, not vocabulary -- it earns no signal).
  $: tone = matched ? ROLE_SCHEMA[matched].tone : 'muted';

  // Accessible name: the role + a plain-English, domain-agnostic hint, plus the
  // explicit sidechain note when present. Never empty.
  $: hint = matched ? ROLE_SCHEMA[matched].hint : 'Role outside the known schema';
  $: accessibleName = `Role: ${displayRole}` +
    (sidechain ? ' (spawned sub-agent)' : '') +
    ` -- ${hint}`;
</script>

<span
  class="role-badge role-badge--{tone} role-badge--{size}"
  class:role-badge--unmatched={!matched}
  data-role={displayRole}
  title={accessibleName}
  aria-label={accessibleName}
  role="img"
>
  <!-- decorative tone dot; the text token below is the real, load-bearing signal -->
  <span class="role-badge__dot" aria-hidden="true"></span>
  <span class="role-badge__text">{displayRole}</span>
  {#if sidechain}
    <!-- paired TEXT marker (never colour alone): identifies a spawned sub-agent.
         Purely descriptive; implies NO inter-agent blocking (M13). -->
    <span class="role-badge__side" title="Spawned sub-agent">side</span>
  {/if}
</span>

<style>
  .role-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    max-width: 100%;
    font-family: var(--sm-font-mono, var(--ff-mono, ui-monospace, 'SFMono-Regular', monospace));
    font-weight: 600;
    letter-spacing: 0.02em;
    line-height: 1;
    border-radius: 2px;
    border: 1px solid var(--sm-border, rgba(148, 163, 184, 0.22));
    background: var(--sm-chip-bg, rgba(148, 163, 184, 0.08));
    color: var(--sm-text, #cbd5e1);
    white-space: nowrap;
  }

  .role-badge--sm {
    font-size: 11px;
    padding: 3px 8px;
  }
  .role-badge--xs {
    font-size: 10px;
    padding: 2px 6px;
    gap: 4px;
  }

  .role-badge__dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: currentColor;
    flex: 0 0 auto;
    opacity: 0.85;
  }

  /* The token text is the load-bearing signal: it truncates but is never
     hidden, and always retains an accessible name via title/aria-label. */
  .role-badge__text {
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .role-badge__side {
    font-size: 0.82em;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 1px 4px;
    border-radius: 2px;
    color: var(--sm-text-dim, #94a3b8);
    background: var(--sm-side-bg, rgba(148, 163, 184, 0.16));
    flex: 0 0 auto;
  }

  /* --- Non-chromatic severity tones (calm-ambient + monitor-first). At rest
     the generic schema sits slate-calm; only the operational-attention role
     warms. No tone pulses or escalates (M2 escalation lives elsewhere). --- */

  /* calm: the resting generic-software roles. Slate ink on a hairline chip. */
  .role-badge--calm {
    color: var(--sm-role-calm-fg, #93a4bd);
    border-color: var(--sm-role-calm-bd, rgba(148, 163, 184, 0.26));
    background: var(--sm-role-calm-bg, rgba(148, 163, 184, 0.07));
  }

  /* watch: operational-attention role (health_monitor). Warmer + heavier, but
     still NOT an escalation -- it never pulses. */
  .role-badge--watch {
    color: var(--sm-role-watch-fg, #c9a227);
    border-color: var(--sm-role-watch-bd, rgba(202, 138, 4, 0.4));
    background: var(--sm-role-watch-bg, rgba(202, 138, 4, 0.1));
    font-weight: 700;
  }

  /* muted: sub_agent / unknown / unrecognised tokens. Dimmest weight: present,
     legible, but visually deferential. */
  .role-badge--muted {
    color: var(--sm-text-dim, #94a3b8);
    border-color: var(--sm-border, rgba(148, 163, 184, 0.18));
    background: var(--sm-chip-bg, rgba(148, 163, 184, 0.05));
    font-weight: 500;
  }

  /* PAPER theme: the calm/watch role inks (#93a4bd / #c9a227) are AA on the dark
     themes but fall below AA on the paper light chip. Darken on paper only; the
     paired role text label is unchanged. */
  :global([data-theme='paper']) .role-badge--calm {
    color: #475569;
  }
  :global([data-theme='paper']) .role-badge--watch {
    color: #92620a;
  }

  /* An unrecognised token is rendered verbatim but visually marked as outside
     the known schema with a dashed edge -- the TEXT still carries the signal. */
  .role-badge--unmatched {
    border-style: dashed;
  }
</style>
