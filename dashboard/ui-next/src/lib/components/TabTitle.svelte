<!--
  TabTitle.svelte -- the browser-tab half of M3. NON-VISUAL: it renders no DOM,
  it only drives document.title.

  CONTRACT (inviolable MUST M3):
    - The browser tab title shows "(N) StreamManager" where N is the TOTAL open
      ACTION REQUIRED count summed across all frames (A/B/C). When N is 0 the
      title is the bare "StreamManager" (no parenthetical) -- matching the live
      dashboard contract exactly (index.html _flushTitle).
    - SSE-driven: N is the same SSE-derived source of truth EscalationRail
      maintains. This component subscribes to the SHARED module-context store
      `tabActionTotal` exported by EscalationRail.svelte -- it never re-derives
      the count from a second SSE socket (single source of truth; file-disjoint:
      both components are this unit's files).
    - ~100ms debounce: the title is flushed at most once per ~100ms, and only
      when the total actually CHANGES, so a burst of SSE events coalesces into a
      single title write (no thrash, no flicker). Mirrors the live dashboard's
      `_titlePending = setTimeout(_flushTitle, 100)` + `total === _titleLastTotal`
      guard precisely.

  CRAFT note: there is no visual craft here by design -- the tab title is a
  glance-readability channel for the operator when the dashboard is in a
  background tab. The "awe" is that it stays perfectly quiet (no churn) until the
  count truly changes. M18: pure post-hoc observability, no network I/O of its
  own, never on the verdict hot path. M16: the only literal is the product name
  "StreamManager" -- no monitored-project vocabulary.

  This component depends only on the shared count store + a debounce timer.
  It consumes no endpoints directly (the SSE socket is owned by EscalationRail).
-->
<script>
  import { onMount, onDestroy } from 'svelte';
  import { tabActionTotal } from './EscalationRail.svelte';

  /**
   * baseTitle: the product name shown when there are no open actions, and the
   * suffix of the "(N) <baseTitle>" form. Defaults to the frozen contract
   * string. Domain-agnostic (M16): this is the SM product name, never a
   * governed-target name.
   */
  export let baseTitle = 'StreamManager';

  /**
   * debounceMs: the title-flush debounce window. ~100ms per M3. Exposed for
   * tests; production uses the contract default.
   */
  export let debounceMs = 100;

  /**
   * apply: when false the component computes but does not write document.title
   * (test seam, or to mount a passive instance).
   *
   * Repair (u-shell M3 BLOCKER -- single-writer): AppShell.svelte is the
   * RUNTIME owner of document.title (it sums the per-frame counts it already
   * holds). TabTitle is the alternative owner via EscalationRail's
   * tabActionTotal store but is NOT mounted today. Default to false so that if
   * TabTitle is later mounted it stays passive unless a caller explicitly opts
   * in -- preventing the double-flush the reviewer flagged. To switch owners,
   * mount <TabTitle apply={true} /> AND delete AppShell's scheduleTitle logic.
   */
  export let apply = false;

  // The last total we actually flushed to the title. -1 is an impossible count
  // (real counts are >= 0) so the FIRST real total always flushes once, exactly
  // like the live dashboard's `_titleLastTotal = -1` sentinel.
  let lastFlushed = -1;
  // The most recent total observed from the store but not yet flushed.
  let pendingTotal = 0;
  /** @type {ReturnType<typeof setTimeout> | null} */
  let timer = null;
  let destroyed = false;

  /**
   * Compose the title per the frozen contract: "(N) <base>" when N > 0, else the
   * bare base. N is clamped to a non-negative integer defensively.
   * @param {number} total
   * @returns {string}
   */
  function compose(total) {
    const n = Math.max(0, Math.floor(Number(total) || 0));
    return n > 0 ? `(${n}) ${baseTitle}` : baseTitle;
  }

  /**
   * The debounced flush. Writes document.title only when the pending total
   * differs from the last flushed total -- so a stable count never re-writes
   * the title (no churn), matching the live `total === _titleLastTotal` guard.
   */
  function flush() {
    timer = null;
    if (destroyed) return;
    if (pendingTotal === lastFlushed) return;
    lastFlushed = pendingTotal;
    if (apply && typeof document !== 'undefined') {
      document.title = compose(pendingTotal);
    }
  }

  /**
   * Schedule a debounced flush. Coalesces a burst of count changes into one
   * title write at most every `debounceMs`. If a flush is already pending we let
   * it ride (the pendingTotal it reads will be the latest), so we never stack
   * timers -- identical to the live dashboard's single-pending-timer guard.
   */
  function scheduleFlush(total) {
    pendingTotal = Math.max(0, Math.floor(Number(total) || 0));
    if (timer !== null) return; // a flush is already queued; it will read latest
    timer = setTimeout(flush, debounceMs);
  }

  // Subscribe to the SHARED SSE-derived total. Every change schedules a
  // debounced flush; the guard inside flush() drops no-op writes.
  const unsub = tabActionTotal.subscribe((total) => {
    scheduleFlush(total);
  });

  onMount(() => {
    // Force an initial flush so the title is correct on first paint even if the
    // count starts at 0 (sets the bare base title and seeds lastFlushed).
    if (timer === null) {
      timer = setTimeout(flush, debounceMs);
    }
  });

  onDestroy(() => {
    destroyed = true;
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    unsub();
  });
</script>

<!-- NON-VISUAL (M3 browser-tab channel): this component renders no DOM. It only
     drives document.title via the debounced flush above. svelte:head is left
     intentionally unused -- the title is set imperatively so the ~100ms
     debounce + change-guard contract is honored exactly (a reactive
     <svelte:head><title> would re-write on every store tick, defeating the
     debounce). -->
