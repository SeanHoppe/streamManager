// _smoke_b3.mjs -- batch-3 live render+interaction smoke (puppeteer).
//
// The canonical per-feature specs are the three *.headed.cjs (@playwright/test)
// siblings. @playwright/test is not installed in this environment (only the
// cached chromium is), so this puppeteer smoke proves the SAME load-bearing
// facts -- each of the 3 batch-3 BETA panes MOUNTS with the flag ON, renders its
// mock fallback (empty gov.db), shows its polarity self-exclusion readout, and
// its key interaction works -- using the engine that IS installed (the same one
// `npm run axe` + audit-roundtrip.spec.mjs use). Run: node test/beta-headed/_smoke_b3.mjs
//
// PRE-REQ (main-thread owned): the ui-next dev server is up on 4317 proxying a
// live governance backend, and the 3 flags are ON (POST /api/beta/flags/<key>).
// M16: every literal here is generic UI/protocol vocabulary.

import puppeteer from 'puppeteer';

const URL = process.env.B3_URL || 'http://127.0.0.1:4317/';
const checks = [];
function record(name, ok, detail = '') {
  checks.push({ name, ok, detail });
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ` -- ${detail}` : ''}`);
}
const txt = (el) => (el ? el.evaluate((n) => n.textContent || '') : Promise.resolve(''));

async function main() {
  console.log('== batch-3 BETA live render+interaction smoke ==');
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  try {
    const page = await browser.newPage();
    page.on('console', (m) => {
      if (m.type() === 'error') console.log(`    [page:error] ${m.text()}`);
    });
    await page.goto(URL, { waitUntil: 'networkidle2', timeout: 30000 });
    await page.waitForSelector('#frameA', { timeout: 20000 });

    // ---- regret-mining-override-loop (Frame A card) ----
    const RMO = '[data-testid="regret-mining-override-loop"]';
    await page.waitForSelector(RMO, { timeout: 20000 });
    const rmoMock = await page.$eval(RMO, (n) => n.getAttribute('data-mock'));
    record('regret: card mounts + falls back to mock', rmoMock === 'true', `data-mock=${rmoMock}`);
    const rmoText = await page.$eval(RMO, (n) => n.textContent || '');
    record('regret: polarity self-exclusion readout', /excluded/i.test(rmoText) && /SM-self/i.test(rmoText));
    const laneCount = await page.$$eval(`${RMO} .rmo__lane`, (e) => e.length);
    record('regret: ranked cluster lanes render', laneCount > 0, `lanes=${laneCount}`);
    // M4 paired label+color on the hottest lane.
    const hotBadge = await page.$eval(`${RMO} .rmo__lane .rmo__ar-badge`, (n) => n.textContent || '').catch(() => '');
    record('regret: M4 paired direction WORD on hot lane', /ESCALATED|DE-ESCALATED/.test(hotBadge), `"${hotBadge.trim()}"`);
    // KEY INTERACTION: open the lane drawer.
    await page.click(`${RMO} .rmo__lane`);
    await page.waitForSelector(`${RMO} .rmo__drawer`, { visible: true, timeout: 8000 });
    record('regret: clicking a lane opens its evidence drawer', true);

    // ---- policy-preview-chip (HitlDock header, advisory note) ----
    const PPC = '.ppc[data-beta="policy-preview-chip"]';
    await page.waitForSelector(PPC, { timeout: 20000 });
    const ppcRole = await page.$eval(PPC, (n) => n.getAttribute('role'));
    record('policy-preview: advisory chip mounts under the toggle', ppcRole === 'note', `role=${ppcRole}`);
    const ppcText = await page.$eval(PPC, (n) => n.textContent || '');
    record('policy-preview: advisory contract + corpus framing', /ADVISORY/i.test(ppcText) && /corpus/i.test(ppcText));
    record('policy-preview: SM-self exclusion shown', /SM-self excluded/i.test(ppcText));

    // ---- confidence-calibration-loop (root launcher chip -> dialog) ----
    const CCL = '.ccl-chip';
    await page.waitForSelector(CCL, { timeout: 20000 });
    const cclLabel = await page.$eval(`${CCL} .ccl-chip__label`, (n) => n.textContent || '').catch(() => '');
    record('calibration: launcher chip mounts', /Confidence calibration/i.test(cclLabel), `"${cclLabel.trim()}"`);
    // KEY INTERACTION: open the reliability-diagram dialog.
    await page.click(CCL);
    await page.waitForSelector('.ccl[role="dialog"]', { visible: true, timeout: 8000 });
    const dlgText = await page.$eval('.ccl[role="dialog"]', (n) => n.textContent || '');
    record('calibration: clicking launcher opens the dialog', true);
    record('calibration: reliability signs render (paired label)', /OVER|UNDER|CALIBRATED/.test(dlgText));
    const hasSvg = (await page.$('.ccl[role="dialog"] svg[role="img"]')) != null;
    record('calibration: reliability diagram svg present', hasSvg);

    const failed = checks.filter((c) => !c.ok);
    if (failed.length) throw new Error(`${failed.length} assertion(s) failed: ${failed.map((c) => c.name).join('; ')}`);
    console.log(`\n== ALL ${checks.length} ASSERTIONS PASSED ==`);
  } finally {
    await browser.close().catch(() => {});
  }
}

main().then(() => process.exit(0)).catch((e) => {
  console.error(`\n!! SMOKE FAILED: ${e && e.message ? e.message : e}`);
  process.exit(1);
});
