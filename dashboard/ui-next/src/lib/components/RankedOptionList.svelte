<!--
  RankedOptionList.svelte -- the FR-UI-5 ranked OVERRIDE picker (part of M6).

  CONTRACT (MUST M6 -- the OVERRIDE affordance):
    - When the operator chooses OVERRIDE on a pending HITL row, they pick from a
      RANKED list of suggested alternatives OR type free text. This leaf owns
      that picker. The ranked options are rendered FROM DATA (the row's ranked
      suggestions / FR-UI-5 alternatives), highest-rank first; it hard-codes no
      option vocabulary (M16 -- domain-agnostic).
    - Exactly one selection is active at a time: a native radio group (one
      ranked option per radio, plus a final "free text" radio). Choosing the
      free-text radio reveals a textarea; its value becomes the resolution.
    - The component is CONTROLLED via two-way `selected` (the chosen value) so
      the parent (HitlPendingRow) can persist the operator's pick keyed to the
      message hash for reinforcement (M6). It emits `change` on every edit so
      the parent can enable/disable its commit affordance.
    - Pure input leaf: it performs NO network I/O and resolves nothing itself
      (M18). The HITL gate stays with the parent row -- this only gathers intent.

  ACCESSIBILITY (M17):
    - A real <fieldset>/<legend> radiogroup; each option is a native
      <input type="radio"> with an associated <label>, so keyboard arrow-key
      navigation + screen-reader semantics come for free. Focus rings are the
      global 2px #d97706 contract (focus.css) -- this leaf adds none of its own.
    - The free-text <textarea> has an explicit <label>; its accessible name is
      never empty.

  CRAFT (calm-ambient spine, KingMode): the ranked list reads as a quiet,
  numbered ladder -- rank is encoded as a small ordinal glyph + variable type
  weight (the top-ranked option sits a touch heavier), not as colored chrome.
  The resting state is still; selection is a calm accent-edge shift, never a
  flash. Density is tight but every row clears the NFR-UI-2 legibility floor.

  This component depends only on theme/calm tokens + its props. It is
  file-disjoint and consumes no endpoints.
-->
<script context="module">
  // Sentinel value identifying the free-text choice within the radio group.
  // Namespaced so it can never collide with a real option value coming from
  // data (M16: option values are arbitrary governed strings).
  export const FREE_TEXT_VALUE = '__sm_free_text__';

  /**
   * Normalise an arbitrary options prop into a stable ranked descriptor list.
   * Accepts:
   *   - ['a','b']                      -> ranked by array order
   *   - [{value,label,rank}, ...]      -> explicit ranks honored, then array order
   * Highest-rank-first; ties keep input order (stable). Blank/duplicate values
   * are dropped so the radio group never has an empty or ambiguous value.
   * @param {Array<string|{value?:string,label?:string,rank?:number}>} raw
   * @returns {Array<{value:string,label:string,rank:number}>}
   */
  export function normaliseOptions(raw) {
    if (!Array.isArray(raw)) return [];
    const seen = new Set();
    const out = [];
    raw.forEach((o, i) => {
      let value;
      let label;
      let rank;
      if (o && typeof o === 'object') {
        value = o.value != null ? String(o.value) : (o.label != null ? String(o.label) : '');
        label = o.label != null ? String(o.label) : value;
        rank = Number.isFinite(Number(o.rank)) ? Number(o.rank) : i;
      } else {
        value = o == null ? '' : String(o);
        label = value;
        rank = i;
      }
      value = value.trim();
      if (value === '' || seen.has(value)) return; // drop blanks/dupes
      seen.add(value);
      out.push({ value, label: label.trim() || value, rank, _order: i });
    });
    // Lower rank number == higher priority (rank 0 is top). Stable on ties.
    out.sort((a, b) => (a.rank - b.rank) || (a._order - b._order));
    return out.map(({ value, label, rank }) => ({ value, label, rank }));
  }
</script>

<script>
  import { createEventDispatcher } from 'svelte';

  /**
   * options: the ranked alternatives, FROM DATA (M16). String[] or
   * {value,label,rank}[] -- see normaliseOptions. Highest-rank first.
   * @type {Array<string|{value?:string,label?:string,rank?:number}>}
   */
  export let options = [];

  /**
   * selected: the currently chosen resolution value (two-way bindable). When it
   * equals FREE_TEXT_VALUE the free-text branch is active and `freeText` carries
   * the actual resolution. The parent persists this for reinforcement (M6).
   * @type {string|null}
   */
  export let selected = null;

  /**
   * freeText: the operator's typed override (two-way bindable). Only meaningful
   * when `selected === FREE_TEXT_VALUE`. The parent reads `resolutionValue()` to
   * get the effective resolution regardless of branch.
   * @type {string}
   */
  export let freeText = '';

  /**
   * groupName: a unique radio-group name so multiple RankedOptionLists on the
   * page (one per pending row) do not bleed selections into one another.
   * REQUIRED for correctness when more than one row is expanded.
   * @type {string}
   */
  export let groupName = 'sm-ranked';

  /** disabled: lock the whole picker (e.g. while a resolve POST is in flight). */
  export let disabled = false;

  const dispatch = createEventDispatcher();

  $: ranked = normaliseOptions(options);

  // The effective resolution string the parent will POST as `resolution` (M6).
  // For a ranked pick it is the option value; for free text it is the trimmed
  // textarea contents. Exposed as a method-style derived so the parent can read
  // it without re-deriving the branch logic.
  export function resolutionValue() {
    if (selected === FREE_TEXT_VALUE) return freeText.trim();
    return selected == null ? '' : String(selected);
  }

  // True once the operator has made a committable choice (a ranked option, or
  // free text with non-blank content). The parent uses this to gate its commit.
  export function isComplete() {
    if (selected == null) return false;
    if (selected === FREE_TEXT_VALUE) return freeText.trim() !== '';
    return true;
  }

  function onPick(value) {
    selected = value;
    dispatch('change', { selected, value: resolutionValue(), complete: isComplete() });
  }

  function onFreeTextInput() {
    // Selecting free text implicitly when the operator types into it.
    if (selected !== FREE_TEXT_VALUE) selected = FREE_TEXT_VALUE;
    dispatch('change', { selected, value: resolutionValue(), complete: isComplete() });
  }
</script>

<fieldset class="rol" class:rol--disabled={disabled} {disabled}>
  <legend class="rol__legend sev-quiet">Override -- pick a ranked alternative or type your own</legend>

  <div class="rol__list" role="radiogroup" aria-label="Ranked override options">
    {#each ranked as opt, i (opt.value)}
      <label
        class="rol__opt"
        class:is-selected={selected === opt.value}
        class:is-top={i === 0}
      >
        <input
          class="rol__radio"
          type="radio"
          name={groupName}
          value={opt.value}
          checked={selected === opt.value}
          {disabled}
          on:change={() => onPick(opt.value)}
        />
        <!-- ordinal rank glyph: decorative reinforcement; the text label is the
             real signal. Top-ranked option carries a touch more type weight. -->
        <span class="rol__rank" aria-hidden="true">{i + 1}</span>
        <span class="rol__label" class:sev-notice={i === 0} class:sev-base={i !== 0}>{opt.label}</span>
      </label>
    {/each}

    <!-- The free-text branch: a radio + revealed textarea. The textarea is the
         resolution source when this branch is active (M6 "free text"). -->
    <label class="rol__opt rol__opt--free" class:is-selected={selected === FREE_TEXT_VALUE}>
      <input
        class="rol__radio"
        type="radio"
        name={groupName}
        value={FREE_TEXT_VALUE}
        checked={selected === FREE_TEXT_VALUE}
        {disabled}
        on:change={() => onPick(FREE_TEXT_VALUE)}
      />
      <span class="rol__rank rol__rank--free" aria-hidden="true">+</span>
      <span class="rol__label sev-base">Free text</span>
    </label>

    {#if selected === FREE_TEXT_VALUE}
      <div class="rol__free-wrap">
        <label class="rol__free-label" for={`${groupName}-free`}>Override text</label>
        <textarea
          id={`${groupName}-free`}
          class="rol__textarea"
          bind:value={freeText}
          on:input={onFreeTextInput}
          {disabled}
          rows="2"
          placeholder="Describe the override the executor should apply"
          aria-label="Override text"
        ></textarea>
      </div>
    {/if}
  </div>
</fieldset>

<style>
  .rol {
    border: 1px solid var(--calm-hairline, #cbd5e1);
    border-radius: var(--radius-soft, 4px);
    background: var(--calm-surface-raised, #0c1118);
    margin: 0;
    padding: var(--space-3, 6px) var(--space-4, 10px) var(--space-4, 10px);
    min-width: 0;
  }
  .rol--disabled {
    opacity: 0.55;
  }

  .rol__legend {
    padding: 0 var(--space-2, 4px);
    font-size: var(--fs-chrome, 11px);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--calm-ink-quiet, #64748b);
  }

  .rol__list {
    display: flex;
    flex-direction: column;
    gap: var(--space-1, 2px);
  }

  /* Each option is a calm, full-row click target. Resting state is still; the
     selected state is a quiet accent-edge shift, never a flash. */
  .rol__opt {
    display: flex;
    align-items: center;
    gap: var(--space-3, 6px);
    padding: var(--space-2, 4px) var(--space-3, 6px);
    border-radius: var(--radius-sharp, 2px);
    border: 1px solid transparent;
    cursor: pointer;
    transition: background var(--t-calm, 180ms ease), border-color var(--t-calm, 180ms ease);
  }
  .rol__opt:hover {
    background: var(--calm-surface-hover, #131c2a);
  }
  .rol__opt.is-selected {
    border-color: var(--calm-accent, #d97706);
    background: var(--calm-accent-wash, rgba(217, 119, 6, 0.08));
  }

  .rol__radio {
    flex: 0 0 auto;
    width: 14px;
    height: 14px;
    margin: 0;
    accent-color: var(--calm-accent, #d97706);
    cursor: pointer;
  }

  /* Ordinal rank glyph: a small monospaced numeral, decorative reinforcement of
     the data-driven ordering. The text label carries the real meaning. */
  .rol__rank {
    flex: 0 0 auto;
    min-width: 1.4ch;
    text-align: center;
    font-family: var(--ff-mono, ui-monospace, monospace);
    font-size: var(--fs-chrome, 11px);
    font-weight: 600;
    color: var(--calm-ink-quiet, #64748b);
    font-variant-numeric: tabular-nums;
  }
  .rol__rank--free {
    color: var(--calm-accent, #d97706);
    font-weight: 700;
  }

  .rol__label {
    flex: 1 1 auto;
    min-width: 0;
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: var(--fs-meta, 13px);
    line-height: var(--lh-tight, 1.25);
    color: var(--calm-ink, #b8b098);
    overflow-wrap: anywhere;
  }

  .rol__free-wrap {
    display: flex;
    flex-direction: column;
    gap: var(--space-2, 4px);
    padding: var(--space-2, 4px) var(--space-3, 6px) 0 calc(14px + var(--space-3, 6px) + var(--space-3, 6px));
  }

  .rol__free-label {
    font-size: var(--fs-chrome, 11px);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--calm-ink-quiet, #64748b);
  }

  .rol__textarea {
    width: 100%;
    box-sizing: border-box;
    resize: vertical;
    min-height: 2.4rem;
    font-family: var(--ff-system, system-ui, sans-serif);
    font-size: var(--fs-meta, 13px);
    line-height: var(--lh-body, 1.5);
    color: var(--calm-ink, #b8b098);
    background: var(--calm-surface-row, #0e141e);
    border: 1px solid var(--calm-hairline, #cbd5e1);
    border-radius: var(--radius-sharp, 2px);
    padding: var(--space-2, 4px) var(--space-3, 6px);
  }
  .rol__textarea::placeholder {
    color: var(--calm-ink-quiet, #64748b);
    opacity: 0.8;
  }

  /* Paper theme: the radio accent retints to the editorial-ink fill so the
     selection reads on the warm light ground (mirrors CountdownBar paper rule). */
  :global([data-theme='paper']) .rol {
    background: var(--calm-surface-raised, #f8f4ee);
  }
</style>
