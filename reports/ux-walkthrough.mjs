// Main-thread operator UX walkthrough of the ui-next spike (directive #3).
// Drives the LIVE preview (http://localhost:4317) via Playwright, AS IF the operator (Sean):
// glance at the monitor, read decisions, inspect frames, try HITL, toggle settings, switch themes.
// Captures structured observations + screenshots. READ-ONLY against the UI (no destructive POSTs).
// Run from the main thread (G7): node reports/ux-walkthrough.mjs   (headless, < 5 min).
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const PW = 'C:/Users/SeanHoppe/AppData/Local/npm-cache/_npx/e41f203b7505f1fb/node_modules/playwright';
const { chromium } = require(PW);
import { writeFileSync } from 'fs';

const BASE = process.env.UX_BASE || 'http://localhost:4318/';
const SHOT = (n) => `reports/ux-${n}.png`;
const obs = [];
const note = (route, flow, observation, friction, shot) =>
  obs.push({ route, flow, observation, friction: friction || '', shot: shot || '' });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
page.setDefaultTimeout(8000);

async function snap(name) { try { await page.screenshot({ path: SHOT(name), fullPage: false }); return SHOT(name); } catch { return ''; } }

try {
  // ---- Flow 1: cold load -- does the monitor read at a glance? ----
  await page.goto(BASE, { waitUntil: 'networkidle' }).catch(() => {});
  await page.waitForTimeout(2500); // let SSE + pollers populate
  const framesPresent = await page.evaluate(() => ({
    A: !!document.querySelector('#frameA'), B: !!document.querySelector('#frameB'), C: !!document.querySelector('#frameC'),
    title: document.title,
  }));
  await snap('01-load');
  note('/', 'cold-load', `frames A=${framesPresent.A} B=${framesPresent.B} C=${framesPresent.C}; tab title="${framesPresent.title}"`,
    (!framesPresent.A || !framesPresent.B || !framesPresent.C) ? 'A required 3-frame is missing at load (M1 risk)' : '', SHOT('01-load'));

  // ---- Structured DOM scrape: what is rendered, what is empty ----
  const scrape = await page.evaluate(() => {
    const txt = (el) => (el && el.textContent || '').replace(/\s+/g, ' ').trim();
    const pick = (sel) => Array.from(document.querySelectorAll(sel));
    const frameSummary = (id) => {
      const f = document.querySelector(id);
      if (!f) return { id, present: false };
      const head = txt(f.querySelector('h1,h2,h3,[role=heading],header'));
      const rows = f.querySelectorAll('[data-row],li,tr,article').length;
      const empty = /no |empty|nothing|0 /i.test(txt(f)) && rows < 2;
      return { id, present: true, header: head.slice(0, 80), rowish: rows, looksEmpty: empty, sampleText: txt(f).slice(0, 240) };
    };
    const badges = pick('[class*=badge],[data-badge],[aria-label*=ACTION],[aria-label*=OBSERV]').slice(0, 30)
      .map((b) => ({ text: txt(b).slice(0, 40), aria: b.getAttribute('aria-label') || '', color: getComputedStyle(b).color, bg: getComputedStyle(b).backgroundColor }));
    const buttons = pick('button,[role=button]').slice(0, 60).map((b) => txt(b).slice(0, 30)).filter(Boolean);
    const selects = pick('select,[role=listbox],[data-session-picker],[class*=picker]').slice(0, 6).map((s) => txt(s).slice(0, 80));
    const colorOnly = badges.filter((b) => !b.text && !b.aria).length; // badge with no label = M4 violation candidate
    return {
      frames: ['#frameA', '#frameB', '#frameC'].map(frameSummary),
      badgeCount: badges.length, badgesSample: badges.slice(0, 12), colorOnlyBadges: colorOnly,
      buttonCount: buttons.length, buttonsSample: buttons.slice(0, 30),
      pickers: selects, bodyTextLen: (document.body.textContent || '').length,
    };
  });
  note('/', 'dom-scrape', JSON.stringify(scrape).slice(0, 1800),
    scrape.colorOnlyBadges > 0 ? `${scrape.colorOnlyBadges} badge(s) with no text/aria -- color-only signal (M4 violation)` : '', '');
  for (const fr of scrape.frames) {
    if (fr.present && fr.looksEmpty) note('/', 'frame-empty', `${fr.id} renders but looks empty (rowish=${fr.rowish})`, `${fr.id} empty -- does it add value with no data, or is it noise?`, '');
  }

  // ---- Flow 2: session picker -- can the operator triage many sessions at a glance? ----
  try {
    const picker = await page.$('select, [data-session-picker], [class*=picker] button, header select');
    if (picker) {
      await picker.click({ timeout: 4000 }).catch(() => {});
      await page.waitForTimeout(800);
      await snap('02-picker');
      const opts = await page.evaluate(() => Array.from(document.querySelectorAll('option,[role=option],[data-session]')).map((o) => (o.textContent || '').trim()).filter(Boolean).slice(0, 20));
      note('header', 'session-picker', `picker options: ${JSON.stringify(opts)}`, opts.length === 0 ? 'session picker present but no options -- operator cannot switch sessions' : '', SHOT('02-picker'));
    } else {
      note('header', 'session-picker', 'no session picker control found', 'monitor-first multi-session triage relies on a picker; not found in DOM scrape', '');
    }
  } catch (e) { note('header', 'session-picker', `picker interaction error: ${String(e).slice(0, 120)}`, '', ''); }

  // ---- Flow 3: HITL dock -- is the human-in-the-loop action obvious? ----
  const hitl = await page.evaluate(() => {
    const t = (document.body.textContent || '');
    const pendingish = /APPROVE|OVERRIDE|DISMISS|pending|ACTION REQUIRED/i.test(t);
    const dock = document.querySelector('[class*=hitl],[data-hitl],[id*=hitl]');
    return { hasHitlSurface: !!dock, mentionsActions: pendingish };
  });
  await snap('03-hitl');
  note('/', 'hitl-dock', `hitl surface=${hitl.hasHitlSurface}; action words present=${hitl.mentionsActions}`,
    !hitl.hasHitlSurface ? 'no HITL dock surface located -- core value (operator decision) may be buried' : '', SHOT('03-hitl'));

  // ---- Flow 4: settings drawer -- can the operator tune without leaving the monitor? ----
  try {
    const settingsBtn = await page.$('button[aria-label*=etting], button[title*=etting], [data-settings], button:has-text("Settings")');
    if (settingsBtn) {
      await settingsBtn.click({ timeout: 4000 }).catch(() => {});
      await page.waitForTimeout(700);
      await snap('04-settings');
      const fields = await page.evaluate(() => Array.from(document.querySelectorAll('input,select,[role=switch],[type=checkbox],[type=range]')).slice(0, 30).map((f) => f.getAttribute('aria-label') || f.getAttribute('name') || f.type || 'field'));
      note('settings', 'settings-drawer', `settings fields: ${JSON.stringify(fields)}`, fields.length === 0 ? 'settings opened but no fields -- dead drawer?' : '', SHOT('04-settings'));
    } else {
      note('settings', 'settings-drawer', 'no settings button found', 'FR-UI-9 settings are a contract surface; control not located', '');
    }
  } catch (e) { note('settings', 'settings-drawer', `settings error: ${String(e).slice(0, 120)}`, '', ''); }

  // ---- Flow 5: theme switch -- the 3 themes (obsidian/phosphor/paper); paper contrast is a known deliverable ----
  for (const theme of ['phosphor', 'paper', 'obsidian']) {
    await page.evaluate((t) => document.documentElement.setAttribute('data-theme', t), theme);
    await page.waitForTimeout(500);
    await snap(`05-theme-${theme}`);
  }
  const paperContrast = await page.evaluate(() => {
    document.documentElement.setAttribute('data-theme', 'paper');
    const dim = document.querySelector('[class*=dim],[class*=muted],small,.text-dim');
    if (!dim) return null;
    const cs = getComputedStyle(dim);
    return { color: cs.color, bg: getComputedStyle(document.body).backgroundColor };
  });
  note('/', 'theme-switch', `cycled phosphor/paper/obsidian; paper dim-text sample=${JSON.stringify(paperContrast)}`, '', SHOT('05-theme-paper'));

  // ---- Flow 6: keyboard-only path -- monitor-first operators value no-mouse operation ----
  await page.evaluate((t) => document.documentElement.setAttribute('data-theme', t), 'obsidian');
  await page.keyboard.press('Tab'); await page.keyboard.press('Tab'); await page.keyboard.press('Tab');
  const focusVisible = await page.evaluate(() => {
    const el = document.activeElement;
    if (!el || el === document.body) return { focusable: false };
    const cs = getComputedStyle(el);
    return { focusable: true, tag: el.tagName, outline: cs.outlineWidth, outlineStyle: cs.outlineStyle };
  });
  note('/', 'keyboard-nav', `after 3x Tab: ${JSON.stringify(focusVisible)}`,
    (!focusVisible.focusable || focusVisible.outlineStyle === 'none') ? 'keyboard focus path weak / no visible focus ring (a11y + operator-comfort)' : '', '');
} catch (err) {
  note('GLOBAL', 'fatal', `walkthrough error: ${String(err).slice(0, 300)}`, 'walkthrough did not complete', '');
} finally {
  await browser.close().catch(() => {});
  writeFileSync('reports/ui-next-walkthrough.json', JSON.stringify({ base: BASE, tool: 'playwright', observations: obs }, null, 2));
  console.log(`WALKTHROUGH DONE: ${obs.length} observations`);
  console.log(JSON.stringify(obs.map((o) => ({ flow: o.flow, friction: o.friction })), null, 1));
}
