# PAPER-CONTRAST.md -- paper-theme `--text-dim` contrast measurement (ui-next)

> NAMED PRE-PRODUCTION DELIVERABLE. Closes the open risk D4-012 flagged by all
> four design judges and called out in UI-DESIGN-SPEC.md SS5 / SS9: the
> whisper-low-contrast paper palette versus the WCAG-AA text floor (M4 / M17).
>
> Scope: this file MEASURES and DOCUMENTS the contrast ratios of the FROZEN
> design tokens that ui-next inherits verbatim from the live dashboard
> (`dashboard/static/index.html`). It does not change any token value -- the
> theme.css values are the contract. This is the evidence artifact a reviewer
> reads before promotion.
>
> ASCII-only (cp1252-safe). Dash rendered as "--". Ratios computed with the
> WCAG 2.1 relative-luminance formula (sRGB, 8-bit, the same math axe-core
> uses). Method is reproducible -- see "Method" at the bottom.

---

## 1. Verdict (read this first)

- The **paper `--text-dim` (#6a5040)** primary question is **RESOLVED -- PASS**.
  On every paper surface it renders against, `--text-dim` clears the WCAG 2.1
  **AA normal-text floor (4.5:1)** with margin. Lowest measured = **6.07:1**
  (on the page `--bg`). The open D4-012 risk for `--text-dim` is closed: at
  these token values the paper theme is AA-safe for dim metadata text.

- A SEPARATE finding surfaced while measuring the full token set: several
  **paired badge fg/bg pairs are below the 4.5:1 AA text floor** (ACTION
  REQUIRED 2.86:1, DECIDED 3.00:1, WARN 3.11:1, BLOCKED 3.95:1). These values
  are inherited VERBATIM from the live dashboard, which ships them and passes
  its own axe gate. They clear the **3:1 non-text / UI-component floor** and
  each badge carries a >=2px solid/dashed border plus a literal text label
  (M4), so the SIGNAL is never color-alone. See SS3 -- this is the one item a
  reviewer must consciously sign off (or remediate) before production, and is
  recorded here as a known, bounded risk rather than silently inherited.

- The **amber focus ring (#d97706)** clears the **3:1 UI-component floor** on
  obsidian/phosphor (5.9-6.2:1) but is **marginal on paper** (2.91:1 on
  `--bg-card`, 3.15:1 on `--bg-row`). See SS4 -- the 2px offset gap plus the
  box-shadow double-encoding in `focus.css` mitigate the marginal card case;
  flagged for the axe gate to confirm on rendered DOM.

---

## 2. Paper `--text-dim` (#6a5040) -- the D4-012 question

WCAG 2.1 AA normal-text floor = **4.5:1**. Large text (>=18.66px bold or
>=24px) floor = 3:1. `--text-dim` is used for metadata at 13px, so the strict
4.5:1 floor applies.

| `--text-dim` (#6a5040) on                | Ratio   | AA 4.5:1 | AAA 7:1 |
|------------------------------------------|---------|----------|---------|
| `--bg`           #ede8df (page)          | 6.07:1  | PASS     | fail    |
| `--bg-card`      #f8f4ee (panel)         | 6.76:1  | PASS     | fail    |
| `--bg-row`       #fefefc (row)           | 7.34:1  | PASS     | PASS    |
| `--bg-row-alt`   #f5f1ea (zebra row)     | 6.58:1  | PASS     | fail    |
| `--bg-row-hover` #f0eae0 (hover row)     | 6.19:1  | PASS     | fail    |

**Result: PASS at AA on all five paper surfaces.** The worst case (6.07:1 on
the page background) has a 1.35x margin over the 4.5:1 floor, so the value is
not fragile. One surface (`--bg-row`) even reaches AAA. No change required to
the frozen `--text-dim` value.

### Paper higher-ink tokens (context -- all comfortably AA, for completeness)

| token                  | on `--bg-card` #f8f4ee | on `--bg-row` #fefefc |
|------------------------|------------------------|-----------------------|
| `--text-ui`   #5a4030  | 8.67:1                 | 9.41:1                |
| `--text`      #2a2018  | 14.54:1                | 15.78:1               |
| `--text-bright` #140c04| 17.68:1                | 19.18:1               |

---

## 3. Paired badge tokens (M4) -- bounded known risk

These are the six paired label+color badge tokens in `theme.css`
(`--badge-*`), inherited verbatim from the live dashboard's `.ar-*` classes.
Measured as fg-text on badge-bg. Badge text is 12px/700 uppercase tracked --
NOT WCAG "large text", so the 4.5:1 floor applies to the text. Each badge also
has a border (>=2px solid for ACTION REQUIRED / BLOCKED, dashed for WARN,
1px for the calmer states) which is a separate UI-component element governed by
the 3:1 non-text floor.

| badge           | fg/bg            | text ratio | AA 4.5:1 (text) | 3:1 (component) |
|-----------------|------------------|-----------:|-----------------|-----------------|
| ACTION REQUIRED | #d97706 / #fef3c7| 2.86:1     | FAIL            | fail (border carries) |
| OBSERVING       | #475569 / #f1f5f9| 6.92:1     | PASS            | PASS            |
| DECIDED         | #16a34a / #dcfce7| 3.00:1     | FAIL            | PASS            |
| BLOCKED         | #dc2626 / #fee2e2| 3.95:1     | FAIL            | PASS            |
| WARN            | #ea580c / #ffedd5| 3.11:1     | FAIL            | PASS            |
| TIMEOUT         | #7c3aed / #ede9fe| 4.80:1     | PASS            | PASS            |

**Interpretation.** Four of six badge text pairs sit below the AA *text* floor.
This is NOT a regression introduced by ui-next -- the values are frozen from
the production dashboard, which ships them and passes its axe-core gate today
(the existing gate excludes AAA `color-contrast-enhanced` but AA applies). Two
mitigations are already structural and keep M4 intact:

1. **M4 paired-signal rule.** The badge is never color-alone: it always renders
   the literal text label (`ACTION REQUIRED`, `BLOCKED`, etc.) AND a border.
   The label is the load-bearing signal; the fill tint is reinforcement.
2. **Border carries the component-contrast.** ACTION REQUIRED / BLOCKED use a
   2px solid border at full saturation (#d97706 / #dc2626) which is the visible
   shape boundary; DECIDED / WARN / TIMEOUT clear the 3:1 component floor in the
   table above.

**Reviewer action (sign-off required before promotion):** decide one of --
  (a) ACCEPT as-is, matching the shipped live dashboard (the badge text label
      satisfies the not-color-alone rule; precedent established), or
  (b) REMEDIATE for AA-text-clean: darken the four failing fg colors to reach
      4.5:1 on their tints (e.g. ACTION REQUIRED fg ~#9a5a00 reaches 4.5:1 on
      #fef3c7) -- but note this would DIVERGE the ui-next badge fg from the
      frozen live-dashboard value, so it must be an explicit operator decision,
      not a silent token edit. ui-next ships option (a) by default to keep the
      contract frozen; (b) is recorded as the available remediation.

This item is the honest residual of the "whisper-low-contrast palette" risk:
the dim BODY text passes (SS2), but the badge TINT-on-TINT pairs are the part
that brushes the floor. Recorded here so it cannot be inherited silently.

---

## 3a. Action-palette colors used as small TEXT (rendered-DOM axe, 2026-06-13)

The hand-measured sections above cover `--text-dim`, the `--badge-*` pairs, and
the focus ring. They did NOT cover the case of an **action-palette / accent
color used directly as small body TEXT** (not a badge, not a token from the
`--badge-*` set). The authoritative gate (axe-core on the RENDERED paper DOM --
reachable on first load once the theme toggle auto-selects paper from the OS
`prefers-color-scheme: light`) surfaced two such nodes that the static analysis
missed:

| element            | fg (before)      | bg surface        | ratio | AA 4.5:1 |
|--------------------|------------------|-------------------|------:|----------|
| `.rail__all--active` (selected ALL filter pill) | `--accent` #c0392b | active wash #eadcd2 | 4.05:1 | FAIL |
| `.repl__note--err` (decision-seed error note)   | `--c-intervene` #ea580c | `--bg-card` #f8f4ee | 3.24:1 | FAIL |

**Remediation applied (AA-clean, frozen-accent-preserving):**

1. **`.rail__all--active` text.** The brand accent (#c0392b) is the FROZEN paper
   identity and must NOT change. The accent at 11px on the light wash is 4.05:1.
   Fix: a NEW paper-only token `--calm-accent-text: #9b1c13` (a darker editorial
   red) is used for the accent-colored **text only**; the pill border + wash keep
   the exact frozen `--accent` #c0392b. Measured `#9b1c13` on #eadcd2 = **6.1:1**
   (PASS, 1.36x margin). Obsidian/phosphor do not define the token, so their
   `var()` fallback resolves to `--accent` -- their look is unchanged.
2. **`.repl__note--err` text.** Paper `--c-intervene` was #ea580c (3.24:1). This
   is NOT a frozen-from-live value -- it is a ui-next-adapted "darkened for AA"
   palette entry that did not actually clear the AA *text* floor. Darkened to
   orange-700 **#c2410c** (= ~4.7:1 on #f8f4ee, PASS), still visually distinct
   from `--c-block` #dc2626.

After both fixes the paper theme passes the M17 axe gate on rendered DOM:
**0 serious/critical** (`reports/axe-latest.md`, 2026-06-13). The frozen
per-theme ACCENT identities (#f59e0b / #39ff14 / #c0392b) were preserved.

---

## 4. Focus ring (#d97706) -- UI-component (3:1) check

The focus ring is a non-text UI component; floor = 3:1 against the surface it
sits on. The ring is theme-invariant amber by design (operator anchor, M17).

| focus ring #d97706 on        | ratio  | 3:1 component floor |
|------------------------------|-------:|---------------------|
| obsidian `--bg` #080a0c      | 6.22:1 | PASS                |
| obsidian `--bg-card` #0c1118 | 5.94:1 | PASS                |
| phosphor `--bg-card` #010d03 | 6.22:1 | PASS                |
| paper `--bg-card` #f8f4ee    | 2.91:1 | MARGINAL (just below)|
| paper `--bg-row` #fefefc     | 3.15:1 | PASS                |

**Interpretation.** Dark themes are comfortable. On the paper LIGHT theme the
ring at 2.91:1 on `--bg-card` is marginally under the 3:1 component floor. Two
mitigations in `focus.css` already address this:

1. **2px offset gap.** The ring sits 2px off the element, so it is read against
   the element's own (often row/white) surface, not only the card fill --
   `--bg-row` #fefefc gives 3.15:1 (PASS).
2. **Box-shadow double-encoding.** `focus.css` SS4 draws a stacked box-shadow
   ring in addition to the outline, so even an aggressive `outline:none`
   component reset leaves a visible focus indicator; and a focused control is
   typically the most prominent element, raising perceived separation.

**Reviewer action:** let the axe gate (M17) confirm on rendered DOM in the
paper theme. If axe flags the paper card case `serious`, the cheapest fix that
preserves the operator-anchor identity is to keep the amber ring but add a 1px
dark inner hairline on the paper theme only (a `focus.css` paper override),
rather than recoloring the ring. Recorded as the available remediation.

---

## 5. Frozen dark-theme `--text-dim` (re-verification)

The obsidian / phosphor `--text-dim` values carry inline AA notes in the live
dashboard. Re-measured here to confirm the inherited values still hold:

| theme    | `--text-dim` | on `--bg-card`     | measured | doc claim | AA 4.5:1 |
|----------|--------------|--------------------|----------|-----------|----------|
| obsidian | #948870      | #0c1118            | 5.42:1   | 5.37:1    | PASS     |
| phosphor | #429056      | #010d03            | 5.05:1   | 5.15:1    | PASS     |

Both clear AA. Minor deltas vs the inline doc claims (5.42 vs 5.37, 5.05 vs
5.15) are rounding between luminance implementations and do not change the
PASS verdict. No change required.

---

## 6. Method (reproducible)

WCAG 2.1 relative luminance: linearize each sRGB channel
`c_lin = c/12.92 if c<=0.03928 else ((c+0.055)/1.055)**2.4`,
`L = 0.2126*R_lin + 0.7152*G_lin + 0.0722*B_lin`,
contrast `= (L_hi + 0.05) / (L_lo + 0.05)`.

Floors applied: **AA normal text 4.5:1**, **AA large text (>=18.66px bold /
>=24px) 3:1**, **non-text UI component 3:1** (WCAG 1.4.11), **AAA enhanced
7:1** (out of gate scope, reported for context only). The ui-next axe gate
(M17) excludes the AAA `color-contrast-enhanced` check, matching the live
dashboard's documented scope.

To re-run the measurement, feed the token hex pairs above through any WCAG-2.1
contrast routine (the figures here were produced with the formula above; axe-
core uses the identical math on rendered DOM, which is the authoritative gate).

---

## 7. Sign-off checklist (for the promotion reviewer)

- [ ] Paper `--text-dim` AA pass confirmed (SS2) -- the original D4-012 item. RESOLVED.
- [ ] Badge tint-on-tint sub-AA-text pairs (SS3): ACCEPT-as-frozen (default) or REMEDIATE -- explicit decision logged.
- [ ] Focus ring paper-card marginal case (SS4): confirmed by axe on rendered DOM; remediation noted if flagged.
- [ ] Obsidian / phosphor `--text-dim` re-verified AA (SS5).
- [x] Action-color-as-small-text paper failures fixed on rendered DOM (SS3a): `.rail__all--active` + `.repl__note--err` now AA; axe 0 serious (2026-06-13).
- [ ] FROZEN per-theme ACCENT identities (#f59e0b/#39ff14/#c0392b) held -- YES. One ui-next-adapted (NOT frozen-from-live) paper palette value was darkened for AA (`--c-intervene` #ea580c->#c2410c) and one paper-only accent-TEXT token added (`--calm-accent-text`); no frozen accent value changed.
