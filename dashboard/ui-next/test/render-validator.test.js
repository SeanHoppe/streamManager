/**
 * render-validator.test.js -- the S2 CANONICAL DASHBOARD REGRESSION CONTRACT.
 *
 * This is the single source of truth that the KingMode UI still honours the
 * four load-bearing render MUSTs after any change to the ui-next spike:
 *
 *   M1  Three-frame presence at load. Frame A (Interactive REPL/Sessions),
 *       Frame B (Sub-Agents), Frame C (Background Jobs) all present at page
 *       load; arrangement is free, presence is not; a corrupt persisted layout
 *       is HEALED back to all three.
 *
 *   M4  Paired label+color badges ALWAYS -- color alone is NEVER a signal.
 *       Every badge carries a TEXT label (one of the six canonical labels) plus
 *       a title/aria-label = trigger reason. The ACTION REQUIRED palette is the
 *       frozen amber #d97706 on #fef3c7 / 2px amber border. There is NO
 *       color-without-text code path (the Badge primitive throws on a blank
 *       label at construction).
 *
 *   M6  HITL ON renders the ranked APPROVE / OVERRIDE / DISMISS list. OVERRIDE
 *       expands a RANKED option list (highest-rank-first) or free text; the
 *       options are rendered FROM DATA (M16), never hard-coded.
 *
 *   M2  Escalation-only foreground. ONLY the three foreground-eligible triggers
 *       {desktop_pause, governance_negative_regression, static-rule} may expand
 *       the EscalationRail. The other three {new_pattern, low_confidence,
 *       governance_variance_alert} -- plus any unknown signal and any plain
 *       decision row -- flag IN PLACE only and never steal focus.
 *
 * THE M2 ORACLE is the data-driven allow-list table in
 *   src/lib/escalation.js
 * (owned by u-selfexclude / u-escalation). M2 is therefore one auditable table
 * + one function call, not scattered conditionals -- which is exactly what
 * makes this validator trivial: it reads ONE frozen object, not the diff of
 * every SSE callback.
 *
 * --------------------------------------------------------------------------
 * HOW TO RUN (no new dependency; uses the Node built-in test runner):
 *
 *     node --test dashboard/ui-next/test/
 *
 * Requires Node >= 18 (node:test + node:assert/strict are built in). This file
 * adds NO npm dependency and runs no build -- it is a pure static + pure-logic
 * contract check, deliberately decoupled from the Vite/axe pipeline (which is
 * the separate MAIN-THREAD M17 gate, never run from a workflow).
 *
 * --------------------------------------------------------------------------
 * WHAT IT ASSERTS AGAINST:
 *
 *   - PURE LOGIC (imported directly, no compiler): the M2 allow-list table and
 *     classifier in escalation.js; the M1 layout presence-heal in
 *     stores/layout.js; the M15 self-exclude predicate in selfExclude.js.
 *
 *   - RENDER CONTRACT (asserted from .svelte SOURCE): Svelte components cannot
 *     be imported by plain Node without the Svelte compiler, so the four
 *     render MUSTs that live in markup (M1 frame presence, M4 paired badges,
 *     M6 ranked HITL list, M2 rail wiring) are asserted by structural source
 *     inspection of the canonical components. This is the documented seam: the
 *     full DOM render is exercised by the separate MAIN-THREAD axe gate (M17);
 *     this validator is the cheap, dependency-free regression net that runs in
 *     CI / pre-merge and fails LOUD the instant a contract marker disappears.
 *
 * File-disjoint: this test owns only itself + contract-fixtures.js. It imports
 * production modules read-only and mutates nothing.
 *
 * @module test/render-validator
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

// -- M2 oracle: the data-driven escalation allow-list (imported directly) ----
import {
  ESCALATION_TABLE,
  FOREGROUND_ELIGIBLE,
  BADGE_IN_PLACE_TYPES as IMPL_BADGE_IN_PLACE,
  ESCALATION_DISPOSITION,
  classify,
  isForegroundEligible,
  describe,
  escalationContract,
} from '../src/lib/escalation.js';

// -- M1 oracle: the layout presence-heal --------------------------------------
// NOTE: stores/layout.js imports `svelte/store`, which is unavailable until the
// MAIN-THREAD `npm install` gate has run. So the validator stays dependency-
// free (runnable pre-install in CI / pre-merge) by LIFTING layout.js's pure
// presence-heal helpers (defaultLayout / sanitise / FRAME_KEYS / FRAME_META)
// from source -- see loadLayoutInternals() below -- rather than importing the
// svelte-coupled module. escalation.js and selfExclude.js are pure (no svelte
// import) and are imported directly above/below.

// -- M15 oracle: the self-exclude predicate (imported directly) --------------
import { makeSelfExcludeFilter, excludeSelfRows } from '../src/lib/selfExclude.js';

// -- The synthetic, domain-agnostic contract fixtures ------------------------
import {
  SELF_SESSION_ID,
  FOREGROUND_ELIGIBLE_TYPES,
  BADGE_IN_PLACE_TYPES,
  FOREGROUND_EVENTS,
  STATIC_RULE_ALIAS_EVENT,
  BADGE_IN_PLACE_EVENTS,
  NON_FOREGROUND_OTHER,
  SELF_FOREGROUND_EVENT,
  CANONICAL_BADGE_LABELS,
  ACTION_REQUIRED_PALETTE,
  COLOR_PAIRED_WITH_TEXT,
  HITL_AFFORDANCES,
  HITL_PENDING_RANKED,
  HITL_PENDING_RANKED_EXPLICIT,
  HITL_RANKED_EXPLICIT_EXPECTED_ORDER,
  HITL_PENDING_SELF,
  REQUIRED_FRAME_KEYS,
  CORRUPT_LAYOUTS,
  CONTAMINATION_SENTINELS,
  JOB_ID_PATTERN,
} from './contract-fixtures.js';

// ===========================================================================
// Source-inspection helpers (the render-contract seam)
// ===========================================================================

const HERE = dirname(fileURLToPath(import.meta.url));
const UI_NEXT_ROOT = resolve(HERE, '..');
const COMPONENTS = resolve(UI_NEXT_ROOT, 'src', 'lib', 'components');

/** Read a ui-next source file as UTF-8. Throws loud if the file is missing. */
function readSource(...parts) {
  const path = resolve(UI_NEXT_ROOT, ...parts);
  return readFileSync(path, 'utf8');
}

/** Read a component source by bare filename (under src/lib/components). */
function readComponent(name) {
  return readFileSync(join(COMPONENTS, name), 'utf8');
}

/**
 * Strip HTML/JS comments + <style> blocks so a contract assertion checks the
 * LIVE render path, not a marker that only survives inside a comment or a CSS
 * selector. Conservative: removes block comments, line comments, HTML comments,
 * and <style>...</style> bodies. Used only to harden the structural asserts.
 */
function strippedForRender(src) {
  return src
    .replace(/<!--[\s\S]*?-->/g, ' ') // HTML comments
    .replace(/<style[\s\S]*?<\/style>/gi, ' ') // CSS bodies
    .replace(/\/\*[\s\S]*?\*\//g, ' ') // JS block comments
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1 '); // JS line comments (not URLs)
}

/**
 * Brace-match a `{ ... }` block starting at the first '{' at or after `from`.
 * Returns the block text INCLUDING the braces. Used to lift a pure function
 * body or a frozen object literal out of source we cannot import (because the
 * module is svelte-coupled or lives in a .svelte module-context block).
 *
 * @param {string} src
 * @param {number} from index to start scanning from
 * @returns {string} the balanced { ... } block
 */
function braceBlockFrom(src, from) {
  const open = src.indexOf('{', from);
  assert.ok(open !== -1, 'expected a { to brace-match from');
  let depth = 0;
  for (let i = open; i < src.length; i += 1) {
    const c = src[i];
    if (c === '{') depth += 1;
    else if (c === '}') {
      depth -= 1;
      if (depth === 0) return src.slice(open, i + 1);
    }
  }
  throw new Error('unbalanced braces while lifting a source block');
}

/**
 * Lift the M1 presence-heal helpers from stores/layout.js SOURCE so the
 * validator never has to import the svelte-coupled module. Reconstructs
 * FRAME_KEYS, FRAME_META, defaultLayout(), and sanitise() in an isolated scope.
 * These functions use only standard JS (Array/Set/Number/Object) -- no svelte
 * API inside their bodies -- so evaluating the lifted source is safe.
 *
 * @returns {{ FRAME_KEYS: string[], FRAME_META: object,
 *             defaultLayout: () => any, sanitise: (raw:any) => any }}
 */
function loadLayoutInternals() {
  const src = readSource('src', 'lib', 'stores', 'layout.js');

  // FRAME_KEYS = Object.freeze([...])
  const keysIdx = src.indexOf('export const FRAME_KEYS');
  assert.ok(keysIdx !== -1, 'M1: layout.js must export FRAME_KEYS.');
  const keysArr = src.slice(src.indexOf('[', keysIdx), src.indexOf(']', keysIdx) + 1);
  // eslint-disable-next-line no-new-func
  const FRAME_KEYS = new Function(`return ${keysArr};`)();

  // FRAME_META = Object.freeze({ ... })
  const metaIdx = src.indexOf('export const FRAME_META');
  assert.ok(metaIdx !== -1, 'M1: layout.js must export FRAME_META.');
  const metaBlock = braceBlockFrom(src, metaIdx);
  // The block is the Object.freeze argument; nested Object.freeze calls are fine.
  // eslint-disable-next-line no-new-func
  const FRAME_META = new Function('Object', `return Object.freeze(${metaBlock});`)(Object);

  // defaultLayout() and sanitise() -- lift each function body verbatim. They
  // both close over FRAME_KEYS, so inject it into the evaluation scope.
  const defBodyStart = src.indexOf('function defaultLayout');
  assert.ok(defBodyStart !== -1, 'M1: layout.js must define defaultLayout().');
  const defBody = braceBlockFrom(src, defBodyStart);

  const sanBodyStart = src.indexOf('function sanitise');
  assert.ok(sanBodyStart !== -1, 'M1: layout.js must define sanitise().');
  const sanBody = braceBlockFrom(src, sanBodyStart);

  // eslint-disable-next-line no-new-func
  const factory = new Function(
    'FRAME_KEYS',
    `
      function defaultLayout() ${defBody}
      function sanitise(raw) ${sanBody}
      return { defaultLayout, sanitise };
    `,
  );
  const { defaultLayout, sanitise } = factory(FRAME_KEYS);
  return { FRAME_KEYS, FRAME_META, defaultLayout, sanitise };
}

/** Recursively collect every source file under ui-next, excluding artifacts. */
function collectSourceFiles(root) {
  const out = [];
  const SKIP_DIRS = new Set(['node_modules', 'dist', '.git']);
  const SOURCE_EXT = /\.(js|mjs|cjs|ts|svelte|html|css|json|md)$/i;
  (function walk(dir) {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      let st;
      try {
        st = statSync(full);
      } catch {
        continue;
      }
      if (st.isDirectory()) {
        if (!SKIP_DIRS.has(entry)) walk(full);
      } else if (SOURCE_EXT.test(entry)) {
        out.push(full);
      }
    }
  })(root);
  return out;
}

// ===========================================================================
// M2 -- ESCALATION-ONLY FOREGROUND (the spine; oracle = escalation.js table)
// ===========================================================================

test('M2: the foreground-eligible set is EXACTLY the three allow-list triggers', () => {
  const impl = Array.from(FOREGROUND_ELIGIBLE).sort();
  const expected = [...FOREGROUND_ELIGIBLE_TYPES].sort();
  assert.deepEqual(
    impl,
    expected,
    'M2 VIOLATION: the escalation allow-list foreground set must be exactly ' +
      `{${expected.join(', ')}} -- got {${impl.join(', ')}}. Any drift means a ` +
      'signal can wrongly steal focus or a hard trigger was demoted.',
  );
});

test('M2: each foreground-eligible trigger classifies as FOREGROUND', () => {
  for (const type of FOREGROUND_ELIGIBLE_TYPES) {
    assert.equal(
      classify(type),
      ESCALATION_DISPOSITION.FOREGROUND,
      `M2 VIOLATION: "${type}" must be FOREGROUND-eligible.`,
    );
    assert.equal(isForegroundEligible(type), true, `M2: "${type}" must foreground.`);
    const d = describe(type);
    assert.ok(d && d.foreground === true, `M2: describe("${type}").foreground must be true.`);
    // M4 pairing: a foreground trigger must carry a non-empty human reason for
    // the badge title / aria-label (color is never the sole signal).
    assert.ok(
      d && typeof d.reason === 'string' && d.reason.trim() !== '',
      `M2/M4: "${type}" must carry a non-empty trigger reason.`,
    );
  }
});

test('M2: each foreground EVENT object foregrounds (event_type read from data)', () => {
  for (const ev of FOREGROUND_EVENTS) {
    assert.equal(
      isForegroundEligible(ev),
      true,
      `M2 VIOLATION: bus event "${ev.event_type}" must be foreground-eligible.`,
    );
  }
});

test('M2: the static-rule underscore alias still foregrounds (no silent demotion)', () => {
  assert.equal(
    isForegroundEligible(STATIC_RULE_ALIAS_EVENT),
    true,
    'M2 VIOLATION: "static_rule" (underscore spelling) must normalize to the ' +
      '"static-rule" hard trigger -- a spelling drift must never demote it to ' +
      'badge-in-place.',
  );
  const d = describe(STATIC_RULE_ALIAS_EVENT);
  assert.equal(d.type, 'static-rule', 'alias must canonicalize to static-rule');
});

test('M2: every badge-in-place signal flags IN PLACE and NEVER foregrounds', () => {
  // The implementation set and the fixture set must agree, and none of them
  // may be foreground-eligible.
  const implBip = Array.from(IMPL_BADGE_IN_PLACE).sort();
  assert.deepEqual(
    implBip,
    [...BADGE_IN_PLACE_TYPES].sort(),
    'M2 VIOLATION: the badge-in-place set drifted from the contract.',
  );
  for (const ev of BADGE_IN_PLACE_EVENTS) {
    assert.equal(
      isForegroundEligible(ev),
      false,
      `M2 VIOLATION: "${ev.event_type}" must flag in place, NEVER foreground.`,
    );
    assert.equal(
      classify(ev),
      ESCALATION_DISPOSITION.BADGE_IN_PLACE,
      `M2: "${ev.event_type}" must classify as BADGE_IN_PLACE.`,
    );
  }
});

test('M2: unknown signals and bare decision rows never foreground (closed-world)', () => {
  for (const ev of NON_FOREGROUND_OTHER) {
    assert.equal(
      isForegroundEligible(ev),
      false,
      'M2 VIOLATION: an unknown signal / plain decision row must default to ' +
        'badge-in-place (closed-world safe default) -- it must never foreground.',
    );
  }
});

test('M2: the foreground and badge-in-place partitions are disjoint and total', () => {
  const fg = new Set(FOREGROUND_ELIGIBLE);
  const bip = new Set(IMPL_BADGE_IN_PLACE);
  // Disjoint.
  for (const t of fg) {
    assert.equal(bip.has(t), false, `M2: "${t}" cannot be in BOTH partitions.`);
  }
  // Total over the known table: every table key is in exactly one partition.
  for (const key of Object.keys(ESCALATION_TABLE)) {
    const inFg = fg.has(key);
    const inBip = bip.has(key);
    assert.equal(
      inFg !== inBip,
      true,
      `M2: table key "${key}" must be in exactly one partition (fg XOR bip).`,
    );
  }
});

test('M2: escalationContract() snapshot matches the contract (auditable surface)', () => {
  const snap = escalationContract();
  assert.deepEqual(snap.foregroundEligible, [...FOREGROUND_ELIGIBLE_TYPES].sort());
  assert.deepEqual(snap.badgeInPlace, [...BADGE_IN_PLACE_TYPES].sort());
  // The snapshot's arrays must be FRESH copies (a caller can't mutate the
  // frozen sets through them).
  snap.foregroundEligible.push('__tamper__');
  const snap2 = escalationContract();
  assert.equal(
    snap2.foregroundEligible.includes('__tamper__'),
    false,
    'M2: escalationContract() must return fresh arrays each call.',
  );
});

test('M2: EscalationRail wires foreground through the allow-list, not local logic', () => {
  const src = strippedForRender(readComponent('EscalationRail.svelte'));
  // The rail's foreground gate must route through the escalation.js oracle.
  assert.ok(
    /isForegroundEligible\s*\(/.test(src),
    'M2 VIOLATION: EscalationRail must gate foreground via isForegroundEligible() ' +
      'from the single allow-list table -- not via a scattered conditional.',
  );
  // It must reflect the M2 state on a stable, validator-readable hook so the
  // foreground/rest state is structurally observable.
  assert.ok(
    /data-foreground=/.test(src),
    'M2: the rail must expose data-foreground for the validator/operator.',
  );
  // And it must NOT subscribe to the consumer-only command transport (M18 seam).
  assert.ok(
    !/\/api\/commands\/stream/.test(src),
    'M18/M2: the rail must consume /events, never /api/commands/stream.',
  );
});

// ===========================================================================
// M1 -- THREE-FRAME PRESENCE AT LOAD (oracle = layout.js presence-heal)
// ===========================================================================

test('M1: the canonical frame set is exactly {A, B, C}', () => {
  const { FRAME_KEYS, FRAME_META } = loadLayoutInternals();
  assert.deepEqual([...FRAME_KEYS], [...REQUIRED_FRAME_KEYS], 'M1: frame set must be A/B/C.');
  // Each frame must have domain-agnostic identity metadata (M16) -- title/hint.
  for (const k of REQUIRED_FRAME_KEYS) {
    const meta = FRAME_META[k];
    assert.ok(meta && typeof meta.title === 'string' && meta.title.trim() !== '',
      `M1: frame ${k} must have a non-empty title.`);
  }
});

test('M1: the default layout materializes all three frames in canonical order', () => {
  const { defaultLayout } = loadLayoutInternals();
  const def = defaultLayout();
  assert.deepEqual(def.order, [...REQUIRED_FRAME_KEYS], 'M1: default order must be A,B,C.');
  for (const k of REQUIRED_FRAME_KEYS) {
    assert.ok(k in def.scroll, `M1: default scroll must include frame ${k}.`);
  }
});

test('M1: a corrupt persisted layout is HEALED back to all three frames', () => {
  const { sanitise } = loadLayoutInternals();
  for (const blob of CORRUPT_LAYOUTS) {
    const healed = sanitise(blob);
    const got = [...healed.order].sort();
    assert.deepEqual(
      got,
      [...REQUIRED_FRAME_KEYS].sort(),
      'M1 VIOLATION: sanitise() must heal every persisted blob back to the full ' +
        `{A,B,C} set -- a frame can NEVER vanish. Offending input: ${JSON.stringify(blob)}.`,
    );
    // No duplicates -- each frame present exactly once.
    assert.equal(
      new Set(healed.order).size,
      REQUIRED_FRAME_KEYS.length,
      'M1: a healed layout must contain each frame exactly once (no dupes).',
    );
  }
});

test('M1: AppShell renders all three frames structurally (presence, not arrangement)', () => {
  const src = strippedForRender(readComponent('AppShell.svelte'));
  // The shell iterates the persisted order but falls back to the full key set,
  // so the rendered SET can never shrink below {A,B,C}. Assert the fallback.
  assert.ok(
    /FRAME_KEYS/.test(src),
    'M1: AppShell must fall back to FRAME_KEYS so a malformed store cannot drop a frame.',
  );
  // The three named content slots (one per guaranteed frame) must all exist.
  for (const slot of ['frameA', 'frameB', 'frameC']) {
    assert.ok(
      new RegExp(`slot=["']?${slot}["']?`).test(src) || new RegExp(`key === '${slot.slice(-1)}'`).test(src),
      `M1: AppShell must provide a content slot for ${slot}.`,
    );
  }
  // A Reset control is part of the M1 contract (layout persisted + reset).
  assert.ok(
    /reset/i.test(src),
    'M1: AppShell must expose a layout Reset control.',
  );
});

test('M1: each Frame body is an INDEPENDENT scroll container', () => {
  const src = readComponent('Frame.svelte');
  // The scroll-isolation boundary: overflow-y:auto + min-height:0 on the body.
  assert.ok(/overflow-y:\s*auto/i.test(src), 'M1: frame body must scroll independently (overflow-y:auto).');
  assert.ok(/min-height:\s*0/i.test(src), 'M1: frame body needs min-height:0 to own its scroll.');
  assert.ok(/overscroll-behavior:\s*contain/i.test(src),
    'M1: frame body should contain overscroll so it never chains to siblings/page.');
});

// ===========================================================================
// M4 -- PAIRED LABEL+COLOR BADGES (oracle = Badge.svelte variant table)
// ===========================================================================

/**
 * Extract the BADGE_VARIANTS label set from Badge.svelte SOURCE. The module
 * lives inside a <script context="module"> in a .svelte file, which plain Node
 * cannot import; we parse the canonical label literals from the source so the
 * validator still asserts against the real table, not a copy.
 */
function badgeLabelsFromSource() {
  const src = readComponent('Badge.svelte');
  // Pull the BADGE_VARIANTS object body and harvest every `label: '...'`.
  const start = src.indexOf('BADGE_VARIANTS');
  assert.ok(start !== -1, 'M4: Badge.svelte must define BADGE_VARIANTS.');
  const tail = src.slice(start, start + 1200);
  const labels = [];
  const re = /label:\s*'([^']+)'/g;
  let m;
  while ((m = re.exec(tail)) !== null) labels.push(m[1]);
  return labels;
}

test('M4: the badge variant table exposes EXACTLY the six canonical labels', () => {
  const labels = badgeLabelsFromSource().sort();
  const expected = [...CANONICAL_BADGE_LABELS].sort();
  assert.deepEqual(
    labels,
    expected,
    'M4 VIOLATION: the badge labels must be exactly the six canonical M4 labels ' +
      `{${expected.join(', ')}}. Drift means a badge could render color without ` +
      'the agreed text, or a label was renamed out of contract.',
  );
});

test('M4: there is NO color-without-text path -- Badge throws on a blank label', () => {
  const src = strippedForRender(readComponent('Badge.svelte'));
  // The structural M4 guard: an unknown/blank variant throws at construction,
  // and a blank label override throws -- so color can never render without text.
  assert.ok(
    /throw new Error/.test(src),
    'M4 VIOLATION: Badge must THROW on an unknown/blank variant or blank label ' +
      '-- the color-without-text path must be impossible by construction.',
  );
  // The visible text node must always render the label.
  assert.ok(
    /\{displayText\}/.test(src),
    'M4: Badge must always render the text label ({displayText}).',
  );
  // Title + aria-label = the trigger reason (reachable by hover AND assistive tech).
  assert.ok(
    /title=\{accessibleReason\}/.test(src) && /aria-label=\{accessibleReason\}/.test(src),
    'M4: every badge must carry title + aria-label = the trigger reason.',
  );
});

test('M4: the ACTION REQUIRED palette is the frozen amber contract', () => {
  // Badge.svelte and the escalation hero both carry the load-bearing literals.
  const badge = readComponent('Badge.svelte');
  const hero = readComponent('AmberActionCard.svelte');
  for (const [name, src] of [['Badge', badge], ['AmberActionCard', hero]]) {
    assert.ok(
      src.includes(ACTION_REQUIRED_PALETTE.fg),
      `M4: ${name} must use the amber foreground ${ACTION_REQUIRED_PALETTE.fg}.`,
    );
    assert.ok(
      src.includes(ACTION_REQUIRED_PALETTE.bg),
      `M4: ${name} must use the amber wash background ${ACTION_REQUIRED_PALETTE.bg}.`,
    );
  }
  // The 2px solid amber pulsing border on ACTION REQUIRED.
  assert.ok(
    new RegExp(`border:\\s*2px solid ${ACTION_REQUIRED_PALETTE.fg}`).test(badge),
    'M4: ACTION REQUIRED must carry a 2px solid amber border.',
  );
  assert.ok(
    /animation:\s*pulseAR/.test(badge),
    'M4: ACTION REQUIRED must carry the pulsing border treatment.',
  );
  // The literal label text must be present in the hero (never an icon-only signal).
  assert.ok(
    hero.includes('ACTION REQUIRED'),
    'M4: the escalation hero must render the literal text "ACTION REQUIRED".',
  );
});

test('M4: every paired color is accompanied by its text label in the badge source', () => {
  const src = readComponent('Badge.svelte');
  for (const pair of COLOR_PAIRED_WITH_TEXT) {
    // The variant class carrying the color must exist...
    assert.ok(
      src.includes(`.ar-${pair.variant}`),
      `M4: badge variant ".ar-${pair.variant}" must exist.`,
    );
    assert.ok(
      src.includes(pair.color),
      `M4: variant "${pair.variant}" must carry its color token ${pair.color}.`,
    );
    // ...and its canonical TEXT label must exist in the variant table.
    assert.ok(
      src.includes(`'${pair.label}'`),
      `M4 VIOLATION: variant "${pair.variant}" color ${pair.color} must be paired ` +
        `with the text label "${pair.label}" -- color is never the sole signal.`,
    );
  }
});

test('M4: the role="status" semantic is on the badge (announced, not silent color)', () => {
  const src = strippedForRender(readComponent('Badge.svelte'));
  assert.ok(/role="status"/.test(src), 'M4/M17: the badge must carry role="status".');
});

// ===========================================================================
// M6 -- HITL ON RANKED APPROVE / OVERRIDE / DISMISS LIST
// ===========================================================================

test('M6: the HITL pending row renders APPROVE / OVERRIDE / DISMISS', () => {
  const src = strippedForRender(readComponent('HitlPendingRow.svelte'));
  for (const affordance of HITL_AFFORDANCES) {
    assert.ok(
      new RegExp(`>\\s*${affordance}`, 'i').test(src) ||
        new RegExp(`${affordance}`, 'i').test(src),
      `M6 VIOLATION: the HITL-ON pending row must render the "${affordance}" affordance.`,
    );
  }
  // All three handlers must be wired.
  assert.ok(/onApprove/.test(src), 'M6: APPROVE must be wired to a handler.');
  assert.ok(/onOverride/.test(src), 'M6: OVERRIDE must be wired to a handler.');
  assert.ok(/onDismiss/.test(src), 'M6: DISMISS must be wired to a handler.');
  // OVERRIDE expands the ranked picker (FR-UI-5 ranked list | free text).
  assert.ok(
    /RankedOptionList/.test(src),
    'M6: OVERRIDE must reveal a RankedOptionList (ranked alternatives | free text).',
  );
  // The pick is persisted KEYED TO THE MESSAGE HASH for reinforcement (M6).
  assert.ok(
    /messageHash/.test(src) && /persistPick/.test(src),
    'M6: the operator pick must be persisted keyed to the message hash for reinforcement.',
  );
});

/**
 * Extract + evaluate the normaliseOptions() ranking function from
 * RankedOptionList.svelte SOURCE. It is exported from a <script
 * context="module"> (uncompilable by plain Node), so we lift the pure function
 * body and run it in an isolated scope to assert the M6 ranked ordering FROM
 * DATA. Pure JS, no Svelte API used inside the function -- safe to evaluate.
 */
function loadNormaliseOptions() {
  const src = readComponent('RankedOptionList.svelte');
  const start = src.indexOf('export function normaliseOptions');
  assert.ok(start !== -1, 'M6: RankedOptionList must export normaliseOptions().');
  const body = braceBlockFrom(src, start);
  // Reconstruct a callable from the lifted body. The function uses only
  // standard JS (Array, Set, Number) -- no Svelte imports -- so it is safe.
  // eslint-disable-next-line no-new-func
  return new Function(`return (function normaliseOptions(raw) ${body});`)();
}

test('M6: ranked OVERRIDE options are normalized highest-rank-first FROM DATA', () => {
  const normalise = loadNormaliseOptions();

  // String form -> ranked by array order (top-ranked first).
  const stringRanked = normalise(HITL_PENDING_RANKED.options);
  assert.equal(stringRanked.length, 3, 'M6: all three ranked options must survive.');
  assert.equal(
    stringRanked[0].value,
    HITL_PENDING_RANKED.options[0],
    'M6: the first array option is the top-ranked (highest priority first).',
  );

  // Explicit object ranks given OUT of array order -> honour `rank`, not order.
  const explicit = normalise(HITL_PENDING_RANKED_EXPLICIT.options);
  const order = explicit.map((o) => o.value);
  assert.deepEqual(
    order,
    [...HITL_RANKED_EXPLICIT_EXPECTED_ORDER],
    'M6 VIOLATION: explicit ranks must be honoured (lower rank number = higher ' +
      'priority), proving the list is ranked FROM DATA, not merely array order.',
  );
});

test('M6: the ranked picker hard-codes NO option vocabulary (M16 data-driven)', () => {
  const src = strippedForRender(readComponent('RankedOptionList.svelte'));
  // Options are iterated from the `options` prop; the only literal "option-like"
  // string is the free-text branch + its sentinel, which are UI chrome, not a
  // governed option value.
  assert.ok(
    /\{#each ranked as opt/.test(src),
    'M6/M16: options must be rendered by iterating the data-driven `ranked` list.',
  );
  assert.ok(
    /FREE_TEXT_VALUE/.test(src),
    'M6: a free-text branch must exist alongside the ranked list.',
  );
  // A real radiogroup (one selection at a time) -- accessible by construction.
  assert.ok(
    /role="radiogroup"/.test(src) && /type="radio"/.test(src),
    'M6/M17: the ranked list must be a native radio group (one selection at a time).',
  );
});

test('M6: HITL ON renders the M4 ACTION REQUIRED badge with the trigger reason', () => {
  const src = strippedForRender(readComponent('HitlPendingRow.svelte'));
  assert.ok(
    /variant="action-required"/.test(src) && /reason=\{reasonText\}/.test(src),
    'M6/M4: a pending row must carry the ACTION REQUIRED badge whose aria-label ' +
      '= the trigger reason.',
  );
});

// ===========================================================================
// M15 -- SELF-EXCLUDE (polarity G2): SM never appears as a governed target.
//        Folded into the render-validator because M2 (foreground) and M6
//        (pending) both depend on the self-session being filtered FIRST.
// ===========================================================================

test('M15: the self-exclude predicate drops the SM own session from rows', () => {
  const keep = makeSelfExcludeFilter(SELF_SESSION_ID);
  // A foreground-eligible trigger on the SELF session must be dropped BEFORE M2.
  assert.equal(
    keep(SELF_FOREGROUND_EVENT),
    false,
    'M15 VIOLATION: a row on the SM own session must be dropped (never a target).',
  );
  // A pending envelope on the SELF session must be dropped too.
  assert.equal(keep(HITL_PENDING_SELF), false, 'M15: self pending row must be excluded.');
  // Non-self governed rows are KEPT.
  for (const ev of FOREGROUND_EVENTS) {
    assert.equal(keep(ev), true, 'M15: a non-self governed row must be kept.');
  }
});

test('M15: missing/empty self id => SKIP filtering (loud-fail-safe, never hide all)', () => {
  const keepAll = makeSelfExcludeFilter('');
  for (const ev of [...FOREGROUND_EVENTS, SELF_FOREGROUND_EVENT, HITL_PENDING_SELF]) {
    assert.equal(
      keepAll(ev),
      true,
      'M15 VIOLATION: with no self id the predicate must keep EVERYTHING (an ' +
        'empty over-filter that hides all rows is an invisible failure).',
    );
  }
});

test('M15: excludeSelfRows strips exactly the self rows from a mixed array', () => {
  const mixed = [...FOREGROUND_EVENTS, SELF_FOREGROUND_EVENT];
  const kept = excludeSelfRows(mixed, SELF_SESSION_ID);
  assert.equal(kept.length, FOREGROUND_EVENTS.length, 'M15: only the self row is dropped.');
  for (const row of kept) {
    assert.notEqual(row.session_id, SELF_SESSION_ID, 'M15: no self row may survive.');
  }
});

// ===========================================================================
// M16 -- ZERO MONITORED-PROJECT VOCABULARY ANYWHERE IN THE SPIKE
// ===========================================================================

test('M16: no monitored-project vocabulary appears in any ui-next source file', () => {
  const files = collectSourceFiles(UI_NEXT_ROOT);
  assert.ok(files.length > 0, 'M16: expected to scan ui-next source files.');
  // The two files that DEFINE the sentinels (this validator + its fixtures)
  // necessarily contain those strings literally, so excluding them is required
  // to avoid a self-trip. Nothing else under the spike is exempt.
  const SELF_DEFINING = new Set(['render-validator.test.js', 'contract-fixtures.js']);
  const offenders = [];
  for (const file of files) {
    if (SELF_DEFINING.has(file.split(/[\\/]/).pop())) continue;
    const raw = readFileSync(file, 'utf8');
    const text = raw.toLowerCase();
    for (const sentinel of CONTAMINATION_SENTINELS) {
      if (text.includes(sentinel)) {
        offenders.push(`${file} :: contains "${sentinel}"`);
      }
    }
    // Monitored-project JOB-id LITERAL shape (e.g. "JOB-1234"). Governance code
    // renders ids FROM DATA, never as a hard-coded literal. This is the precise
    // token shape -- it deliberately does NOT match the generic, domain-agnostic
    // lifecycle field `job_id` / `data-job-id` (M14 renders a job's id from data).
    if (JOB_ID_PATTERN.test(raw)) {
      offenders.push(`${file} :: matches JOB-id literal pattern`);
    }
  }
  assert.deepEqual(
    offenders,
    [],
    'M16 VIOLATION: monitored-project vocabulary / JOB-id literals leaked into ' +
      `the domain-agnostic UI:\n  ${offenders.join('\n  ')}`,
  );
});

// ===========================================================================
// M11 / M12 -- FR-PPP PROVENANCE AUDIT SURFACE (oracle = the leaf contracts +
//        the AuditDock composition seam). The probe/canary/hallucination leaves
//        are presentational; AuditDock is the one host that subscribes to the
//        audit.* bus events, correlates the audit_probe pending rows with their
//        audit.probe envelopes, and renders the three leaves. These asserts pin
//        BOTH the leaf MUSTs and the host wiring so the surface cannot silently
//        un-mount or drop a layer.
// ===========================================================================

test('M11: AuditProbeRow renders a radio candidate list + explicit none-of-the-above', () => {
  const src = strippedForRender(readComponent('AuditProbeRow.svelte'));
  // The probe is a single attestation -> RADIOS, never checkboxes.
  assert.ok(
    /type="radio"/.test(src) && !/type="checkbox"/.test(src),
    'M11 VIOLATION: the probe must be a radio candidate list (single attestation), never checkboxes.',
  );
  // An explicit "none of the above" choice (empty value => null provenance).
  assert.ok(
    /none of the above/i.test(src),
    'M11 VIOLATION: the probe must render an explicit "none of the above" option.',
  );
  // Candidates are iterated FROM DATA (the envelope), never hard-coded (M16).
  assert.ok(
    /\{#each candidates as/.test(src),
    'M11/M16: candidate streams must be iterated from the envelope data, not hard-coded.',
  );
});

test('M11: AuditProbeRow validates session_id before signing + acks with envelope provenance', () => {
  const src = strippedForRender(readComponent('AuditProbeRow.svelte'));
  // M11: a probe with no session scope is meaningless -> validate before POST.
  assert.ok(
    /sessionMissing/.test(src),
    'M11 VIOLATION: the probe must validate session_id is set before signing.',
  );
  // The ack POST flows through the api wrapper with brain_id + prompt_hash that
  // were EXTRACTED FROM THE ENVELOPE (never invented client-side).
  assert.ok(
    /postProbeAck\s*\(/.test(src),
    'M11: the probe must ack via postProbeAck (POST /api/sm-probe/ack).',
  );
  assert.ok(
    /brain_id/.test(src) && /prompt_hash/.test(src),
    'M11 VIOLATION: the ack must carry brain_id + prompt_hash extracted from the envelope.',
  );
  // M18 seam: the leaf must never reach the consumer-only command transport.
  assert.ok(
    !/\/api\/commands\/stream/.test(src),
    'M18: the probe leaf must consume /events + the REST acks, never /api/commands/stream.',
  );
});

test('M12: CanaryEchoRow renders the nonce + a shared countdown and runs the M12 state machine', () => {
  const src = strippedForRender(readComponent('CanaryEchoRow.svelte'));
  // The nonce is the hero of the row (rendered from data).
  assert.ok(/\{nonce/.test(src), 'M12: the canary must render the nonce FROM DATA.');
  // Countdown via the SHARED M9 primitive (not a re-implemented timer).
  assert.ok(
    /CountdownBar/.test(src),
    'M12: the canary countdown must reuse the shared CountdownBar primitive (M9 contract).',
  );
  // The three M12 transitions must be present: pending -> observed (auto-clear
  // after a 1.5s flash) and pending -> failed (with the reason).
  assert.ok(
    /observed/.test(src) && /1500/.test(src),
    'M12 VIOLATION: pending -> observed must auto-clear after a 1.5s (1500ms) confirmation flash.',
  );
  assert.ok(
    /failure_reason|failureReason/.test(src),
    'M12 VIOLATION: pending -> failed must carry + render the failure reason.',
  );
  // M17: state transitions are announced (aria-live), not signalled by color alone.
  assert.ok(/aria-live/.test(src), 'M12/M17: canary state changes must be announced via aria-live.');
});

test('M12: HallucinationAlert is an operator-dismiss alarm with NO auto-clear / NO countdown', () => {
  const src = strippedForRender(readComponent('HallucinationAlert.svelte'));
  // The literal load-bearing headline (M4 paired label, never color alone).
  assert.ok(
    /HALLUCINATION DETECTED/.test(src),
    'M12/M4: the alarm must render the literal headline "HALLUCINATION DETECTED".',
  );
  // EXPLICIT operator-dismiss.
  assert.ok(
    /dispatch\('dismiss'|on:click=\{dismiss\}/.test(src),
    'M12 VIOLATION: the hallucination alarm must have an explicit operator-dismiss.',
  );
  // M12: it is a correctness alarm -> NO auto-clear, NO countdown (unlike canary).
  assert.ok(
    !/CountdownBar/.test(src) && !/setTimeout/.test(src),
    'M12 VIOLATION: the hallucination alarm must NOT auto-clear or run a countdown ' +
      '-- it stays until the operator acknowledges it.',
  );
  // M17: announced assertively when it lands.
  assert.ok(/role="alert"/.test(src), 'M12/M17: the alarm must carry role="alert".');
});

test('M11/M12: AuditDock subscribes to ALL FIVE audit.* bus events and renders the three leaves', () => {
  const src = strippedForRender(readComponent('AuditDock.svelte'));
  const events = [
    'audit.probe',
    'audit.canary_emit',
    'audit.canary_observed',
    'audit.probe_failure',
    'audit.hallucination_detected',
  ];
  for (const ev of events) {
    assert.ok(
      new RegExp(`onBusEvent\\(\\s*['"]${ev.replace('.', '\\.')}['"]`).test(src),
      `M11/M12 VIOLATION: AuditDock must subscribe to the "${ev}" named bus event.`,
    );
  }
  for (const leaf of ['AuditProbeRow', 'CanaryEchoRow', 'HallucinationAlert']) {
    assert.ok(
      new RegExp(`<${leaf}\\b`).test(src),
      `M11/M12 VIOLATION: AuditDock must render <${leaf}> (the surface cannot drop a layer).`,
    );
  }
});

test('M11/M12: AuditDock seeds the audit-probe pending rows post-hoc and never the command transport', () => {
  const src = strippedForRender(readComponent('AuditDock.svelte'));
  // It correlates the Layer-1 attestation rows by the audit_probe trigger.
  assert.ok(
    /audit_probe/.test(src) && /getHitlPending\s*\(/.test(src),
    'M11: AuditDock must seed /api/hitl/pending and correlate the audit_probe-kind rows.',
  );
  // M15 self-exclude is applied to the seeded rows (defense-in-depth).
  assert.ok(
    /getOwnSessionId|isSelf/.test(src),
    'M15: AuditDock must self-exclude the SM own session from the seeded probe rows.',
  );
  // M18: post-hoc only -- never the consumer-only command transport.
  assert.ok(
    !/\/api\/commands\/stream/.test(src),
    'M18: AuditDock must be post-hoc (/events + REST), never /api/commands/stream.',
  );
});

test('M11: HitlDock excludes audit_probe rows so the probe surface renders in exactly one place', () => {
  const src = strippedForRender(readComponent('HitlDock.svelte'));
  // The generic HITL dock must NOT also render the audit_probe rows (AuditDock
  // owns them) -- otherwise a probe double-renders.
  assert.ok(
    /audit_probe/.test(src) && /trigger_reason\s*!==/.test(src),
    'M11 VIOLATION: HitlDock must exclude trigger_reason==="audit_probe" rows ' +
      '(AuditDock renders them as AuditProbeRow) to avoid a double-render.',
  );
});

// ===========================================================================
// SELF-CHECK -- the validator's own oracles must be wired correctly.
// ===========================================================================

test('self-check: the contract fixtures and the implementation agree on the M2 sets', () => {
  // Guard against a fixture rotting out of sync with the implementation: the
  // fixture's foreground/badge sets must equal the implementation's. If a future
  // edit changes ONE without the other, this fires before the M2 tests give a
  // confusing partial signal.
  assert.deepEqual(
    [...FOREGROUND_ELIGIBLE_TYPES].sort(),
    Array.from(FOREGROUND_ELIGIBLE).sort(),
    'self-check: fixture foreground set must match escalation.js.',
  );
  assert.deepEqual(
    [...BADGE_IN_PLACE_TYPES].sort(),
    Array.from(IMPL_BADGE_IN_PLACE).sort(),
    'self-check: fixture badge-in-place set must match escalation.js.',
  );
});
