/* confidence-calibration-loop.spec.cjs -- standalone Playwright --headed test for
 * the BETA feature "confidence-calibration-loop" (#8). CommonJS, self-contained
 * (mirrors the foundation BETA-toggle + decision-oracle test idiom).
 *
 * WHAT IT PROVES
 *   1. OFF (default): the feature renders NOTHING -- no launcher chip, no drawer
 *      in the DOM. The documented open bridge is a no-op when OFF (component not
 *      mounted -> no listener), which proves the gate is load-bearing.
 *   2. Toggle ON via Settings > BETA features: the launcher chip mounts.
 *   3. The key interaction: opening the drawer (via the documented
 *      `confidence-calibration-loop:open` window bridge so the test is
 *      independent of live gov.db state -- the component fetches, the endpoint
 *      empties on a fresh DB, and it falls back to realistic MOCK data) renders
 *      the reliability diagram + the decile rail with PAIRED sign badges
 *      (M4: text + shape + color, never color alone), and a decile row opens the
 *      detail tray.
 *   4. The opt-in advisory transform toggle is DEFAULT OFF and flips on click.
 *   5. Escape closes the tray, then the drawer.
 *
 * PRE-REQ (MAIN-THREAD owned -- NOT this test's job):
 *   - the ui-next dev/preview server is up on http://127.0.0.1:4317 (proxying the
 *     live governance server). Set CCL_URL to override.
 *
 * RUN (main thread):
 *   npx playwright test dashboard/ui-next/test/confidence-calibration-loop.spec.cjs --headed
 */
const { test, expect } = require('@playwright/test');

const URL = process.env.CCL_URL || 'http://127.0.0.1:4317/';
const FLAG_LABEL = /Confidence calibration loop/i;

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
  // close the drawer (Escape) so the launcher chip is unobstructed
  await page.keyboard.press('Escape');
}

test.describe('BETA confidence-calibration-loop (#8)', () => {
  test('renders nothing when the flag is OFF', async ({ page }) => {
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.waitForSelector('#frameA', { timeout: 15000 });

    // Ensure OFF (the default; also clears any persisted mirror from a prior run).
    await setFlag(page, false);

    // No launcher chip, no drawer in the DOM while gated OFF.
    await expect(page.locator('.ccl-chip')).toHaveCount(0);
    await expect(page.locator('.ccl[role="dialog"]')).toHaveCount(0);

    // The bridge event is a no-op when OFF (component not mounted -> no listener).
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent('confidence-calibration-loop:open'));
    });
    await page.waitForTimeout(300);
    await expect(page.locator('.ccl[role="dialog"]')).toHaveCount(0);
  });

  test('mounts + opens the reliability diagram drawer when ON', async ({ page }) => {
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.waitForSelector('#frameA', { timeout: 15000 });

    await setFlag(page, true);

    // Launcher chip is present once ON.
    const chip = page.locator('.ccl-chip');
    await expect(chip).toHaveCount(1);
    await expect(chip.locator('.ccl-chip__label')).toHaveText(/Confidence calibration/i);

    // Drive the drawer via the documented bridge so the test does not depend on
    // live gov.db rows: the component fetches, the endpoint empties on a fresh
    // DB, and it falls back to realistic MOCK calibration data.
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent('confidence-calibration-loop:open'));
    });

    const dialog = page.locator('.ccl[role="dialog"]');
    await expect(dialog).toHaveCount(1);

    // The "Sample data" chip shows because the mock fixture was used.
    await expect(dialog.getByText('Sample data')).toBeVisible();

    // The reliability diagram is a role=img with a headline aria-label.
    await expect(dialog.locator('svg[role="img"]')).toBeVisible();

    // The decile rail renders PAIRED sign badges -- the literal SIGN word, never
    // color alone (M4). The mock fixture carries OVER + CALIBRATED + UNDER bands.
    await expect(dialog.locator('.rail .sign').first()).toBeVisible();
    await expect(dialog.getByText('OVER', { exact: true }).first()).toBeVisible();
    await expect(dialog.getByText('CALIBRATED', { exact: true }).first()).toBeVisible();

    // Activate a decile row -> the detail tray opens with the paired reading.
    await dialog.locator('.rrow').first().click();
    const tray = dialog.locator('.tray[role="region"]');
    await expect(tray).toBeVisible();
    await expect(tray.locator('.tray__words')).toBeVisible();

    // The opt-in advisory transform is DEFAULT OFF and flips on click (M13).
    const optin = dialog.locator('.switch[role="switch"]');
    await expect(optin).toHaveAttribute('aria-checked', 'false');
    await expect(dialog.locator('.optin__state')).toHaveText('OFF');
    await optin.click();
    await expect(optin).toHaveAttribute('aria-checked', 'true');
    await expect(dialog.locator('.optin__state')).toHaveText('ON');

    // Escape closes the tray first, then the drawer.
    await dialog.locator('.rrow').first().focus();
    await page.keyboard.press('Escape');
    await expect(tray).toHaveCount(0);
    await page.keyboard.press('Escape');
    await expect(page.locator('.ccl[role="dialog"]')).toHaveCount(0);
  });
});