# axe-core audit — http://127.0.0.1:8765/

- Timestamp: `2026-05-02T13:31:44.963Z`
- axe-core version: `4.10.3`
- Full JSON: `reports/axe-20260502T133145.json`

## Counts by impact

| impact | count |
| --- | --- |
| critical | 0 |
| serious | 1 |
| moderate | 0 |
| minor | 0 |

- passes: 24
- incomplete: 2
- inapplicable: 37

## Violations

### [serious] color-contrast — Elements must meet minimum color contrast ratio thresholds

- WCAG: cat.color, wcag2aa, wcag143, TTv5, TT13.c, EN-301-549, EN-9.1.4.3, ACT
- Help URL: https://dequeuniversity.com/rules/axe/4.10/color-contrast?application=axe-puppeteer
- Nodes: 152

  1. `.repl-line[data-dir="inbound"]:nth-child(1) > .repl-ts`
     - Fix any of the following: /   Element has insufficient color contrast of 3.86 (foreground color: #7a7058, background color: #0c1118, font size: 9.8pt (13px), font weight: normal). Expected contrast ratio of 4.5:1
  2. `.repl-line[data-dir="inbound"]:nth-child(2) > .repl-ts`
     - Fix any of the following: /   Element has insufficient color contrast of 3.86 (foreground color: #7a7058, background color: #0c1118, font size: 9.8pt (13px), font weight: normal). Expected contrast ratio of 4.5:1
  3. `.repl-line[data-dir="inbound"]:nth-child(3) > .repl-ts`
     - Fix any of the following: /   Element has insufficient color contrast of 3.86 (foreground color: #7a7058, background color: #0c1118, font size: 9.8pt (13px), font weight: normal). Expected contrast ratio of 4.5:1
  4. `.repl-line[data-dir="inbound"]:nth-child(4) > .repl-ts`
     - Fix any of the following: /   Element has insufficient color contrast of 3.86 (foreground color: #7a7058, background color: #0c1118, font size: 9.8pt (13px), font weight: normal). Expected contrast ratio of 4.5:1
  5. `.repl-line[data-dir="inbound"]:nth-child(5) > .repl-ts`
     - Fix any of the following: /   Element has insufficient color contrast of 3.86 (foreground color: #7a7058, background color: #0c1118, font size: 9.8pt (13px), font weight: normal). Expected contrast ratio of 4.5:1
  …and 147 more.
