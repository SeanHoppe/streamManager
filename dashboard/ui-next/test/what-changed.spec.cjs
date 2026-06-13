/* what-changed.spec.cjs -- standalone Playwright --headed test for the BETA
 * feature "what-changed" (#49: What Changed Digest -- page-focus synthesis
 * overlay). CommonJS, self-contained (mirrors the foundation BETA-toggle test
 * idiom + health-sparklines.spec.cjs / decision-oracle.spec.cjs).
 *
 * WHAT IT PROVES
 *   1. OFF (default): the feature renders NOTHING -- no .wc-digest banner in the
 *      DOM, and firing the documented test bridge `what-changed:open` is a true
 *      no-op (no listener is attached while gated OFF, so no banner appears).
 *      The beta gate is load-bearing (no Page Visibility listener / store reads /
 *      window bridge register when OFF).
 *   2. Toggle ON via Settings > BETA features: triggering the digest (via the
 *      documented `what-changed:open` bridge with detail.mock=true so the run is
 *      deterministic and does not race real Page Visibility timing) mounts the
 *      .wc-digest banner. With an empty gov.db the component falls back to
 *      realistic MOCK data, so the six paired label+count badges are present.
 *   3. M4 paired label+color: every section badge carries a literal TEXT label
 *      AND a TEXT count (never color alone). The confidence section carries a
 *      "v"/"^"/"-" arrow glyph + a signed number, not hue.
 *   4. KEY INTERACTION: a non-zero section badge is a real <button> (keyboard-
 *      operable). Activating it via Enter expands its inline detail panel
 *      (aria-expanded flips true; the panel mounts). The banner never
 *      auto-foregrounds a frame (M2): showing it is a data signal, not an
 *      escalation.
 *   5. Escape dismisses the banner (writes the localStorage watermark) and the
 *      digest leaves the DOM.
 *
 * PRE-REQ (MAIN-THREAD owned -- NOT this test's job):
 *   - the ui-next dev/preview server is up on http://127.0.0.1:4317 (proxying
 *     the live governance server). Set WC_URL to override.
 *
 * RUN (main thread):
 *   npx playwright test dashboard/ui-next/test/what-changed.spec.cjs --headed
 */
const { test, expect } = require('@playwright/test');

const URL = process.env.WC_URL || 'http://127.0.0.1:4317/';
const FLAG_LABEL = /What Changed digest/i;

// Flip the BETA flag from the Settings drawer. The footer "Settings" button
// opens the drawer; the BETA panel renders one checkbox per registry feature
// with aria-label `${label} (currently ON|OFF)`.
async function setFlag(page, on) {
  await page.getByRole('button', { name: /Open operator settings/i }).click();
  const toggle = page.getByRole('checkbox', { name: FLAG_LABEL });
  await toggle.waitFor({ state: 'visible' });
  const checked = await toggle.isChecked();
  if (checked !== on) await toggle.click();
  await expect(toggle).toBeChecked({ checked: on });
  // close the drawer (Escape) so the Frame B banner is unobstructed
  await page.keyboard.press('Escape');
}

// Fire the documented test bridge so the digest renders deterministically
// (detail.mock=true forces the realistic mock data path -- no race with the
// real Page Visibility timing). When the flag is OFF no listener is attached,
// so this is a no-op and the banner never appears.
async function fireBridge(page) {
  await page.evaluate(() => {
    window.dispatchEvent(
      new CustomEvent('what-changed:open', { detail: { mock: true } }),
    );
  });
}

test.describe('BETA what-changed (#49)', () => {
  test('renders nothing when the flag is OFF', async ({ page }) => {
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.waitForSelector('#frameB', { timeout: 15000 });

    // Ensure OFF (the default; also clears any persisted mirror from a prior run).
    await setFlag(page, false);

    // Even firing the bridge does nothing while gated OFF -- no listener exists.
    await fireBridge(page);
    await page.waitForTimeout(250);

    await expect(page.locator('.wc-digest')).toHaveCount(0);
    await expect(page.locator('[data-testid="what-changed-digest"]')).toHaveCount(0);
  });

  test('mounts the digest banner + expands a section when ON', async ({ page }) => {
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.waitForSelector('#frameB', { timeout: 15000 });

    await setFlag(page, true);

    // Trigger the digest deterministically via the documented bridge (mock path).
    await fireBridge(page);

    // The banner mounts once ON + triggered. With an empty gov.db it falls back
    // to mock data (data-mock="true"), so the banner is always present.
    const banner = page.locator('[data-testid="what-changed-digest"]');
    await expect(banner).toBeVisible();
    await expect(banner).toHaveAttribute('data-mock', 'true');

    // The away eyebrow + BETA annotation chip are present.
    await expect(banner.getByText(/SINCE YOU LEFT/i)).toBeVisible();
    await expect(banner.getByText(/default OFF, toggled in Settings/i)).toBeVisible();

    // M4: every section badge carries a literal TEXT label AND a TEXT count
    // (never color alone). At least the six mockup sections render.
    const badges = page.locator('.wc-badge');
    expect(await badges.count()).toBeGreaterThanOrEqual(6);
    // The "New agents" section is non-zero in the mock; assert its paired text.
    const newAgents = page.locator('.wc-badge[data-section="newAgents"]');
    await expect(newAgents.locator('.wc-badge__label')).toHaveText(/New agents/i);
    await expect(newAgents.locator('.wc-badge__count')).toHaveText(/\d/);

    // The confidence section carries an arrow glyph (v / ^ / -) + a signed number
    // -- the trend is NOT carried by hue alone (M4).
    const conf = page.locator('.wc-badge[data-section="conf"]');
    await expect(conf.locator('.wc-conf-arrow')).toHaveText(/[v^-]/);
    await expect(conf.locator('.wc-badge__count')).toHaveText(/[+-]?\d/);

    // KEY INTERACTION: a non-zero badge is a real <button>, keyboard-operable.
    // Focus it + press Enter -> its inline detail panel expands (accordion).
    await newAgents.focus();
    await expect(newAgents).toHaveAttribute('aria-expanded', 'false');
    await page.keyboard.press('Enter');
    await expect(newAgents).toHaveAttribute('aria-expanded', 'true');

    // The expanded panel mounts inline (not a modal, not a new frame -- M1).
    const panel = page.locator('#wc-panel-newAgents');
    await expect(panel).toBeVisible();
    await expect(panel.getByText(/first seen while away/i)).toBeVisible();

    // M2: the banner does NOT auto-foreground a frame. Frame B is not escalated.
    await expect(page.locator('#frameB.frame--escalated')).toHaveCount(0);

    // Escape dismisses the banner (writes the watermark) -> it leaves the DOM.
    await page.keyboard.press('Escape');
    await expect(page.locator('[data-testid="what-changed-digest"]')).toHaveCount(0);
  });
});
