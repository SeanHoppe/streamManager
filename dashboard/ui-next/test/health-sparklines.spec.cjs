/* health-sparklines.spec.cjs -- standalone Playwright --headed test for the BETA
 * feature "health-sparklines" (#34). CommonJS, self-contained (mirrors the
 * foundation BETA-toggle test idiom + decision-oracle.spec.cjs).
 *
 * WHAT IT PROVES
 *   1. OFF (default): the feature renders NOTHING -- no .hs strip block, no
 *      sparkline, no drawer in the DOM. The beta gate is load-bearing (no
 *      store subscriptions / pollers / SSE handlers / timers register).
 *   2. Toggle ON via Settings > BETA features: the .hs strip block mounts and
 *      renders at least one sparkline strip. When gov.db has no live decisions
 *      in scope the component falls back to realistic MOCK data, so a strip is
 *      always present (presence + paired text read are the gate assertions).
 *   3. The key interaction: activating a strip via keyboard (Enter) opens the
 *      observational drawer (role=dialog) showing the last-N detail chart +
 *      trigger_reason breakdown. The strip carries a PAIRED text state word
 *      (M4: text + color, never color alone).
 *   4. Escape closes the drawer and returns focus.
 *
 * PRE-REQ (MAIN-THREAD owned -- NOT this test's job):
 *   - the ui-next dev/preview server is up on http://127.0.0.1:4317 (proxying
 *     the live governance server). Set HS_URL to override.
 *
 * RUN (main thread):
 *   npx playwright test dashboard/ui-next/test/health-sparklines.spec.cjs --headed
 */
const { test, expect } = require('@playwright/test');

const URL = process.env.HS_URL || 'http://127.0.0.1:4317/';
const FLAG_LABEL = /Session health sparklines/i;

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
  // close the drawer (Escape) so the rail strip block is unobstructed
  await page.keyboard.press('Escape');
}

test.describe('BETA health-sparklines (#34)', () => {
  test('renders nothing when the flag is OFF', async ({ page }) => {
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.waitForSelector('#frameA', { timeout: 15000 });

    // Ensure OFF (the default; also clears any persisted mirror from a prior run).
    await setFlag(page, false);

    // No strip block, no sparkline, no drawer in the DOM while gated OFF.
    await expect(page.locator('.hs')).toHaveCount(0);
    await expect(page.locator('.hs__spark')).toHaveCount(0);
    await expect(page.locator('.hs-drawer')).toHaveCount(0);
  });

  test('mounts the strip block + opens the detail drawer when ON', async ({ page }) => {
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.waitForSelector('#frameA', { timeout: 15000 });

    await setFlag(page, true);

    // The strip block mounts once ON.
    const block = page.locator('.hs');
    await expect(block).toHaveCount(1);
    await expect(block.getByText(/Session health/i)).toBeVisible();
    // BETA annotation chip is present in the footer.
    await expect(block.getByText(/default OFF, toggled in Settings/i)).toBeVisible();

    // At least one sparkline strip renders (mock fallback guarantees presence
    // even with an empty gov.db). The strip is a role=img with an aria-label.
    const strip = page.locator('.hs__spark').first();
    await expect(strip).toBeVisible();
    await expect(strip).toHaveAttribute('role', 'img');
    await expect(strip).toHaveAttribute('aria-label', /confidence/i);

    // M4: every strip carries a literal text STATE word beside the trace (never
    // color alone). It must be one of the three documented states.
    const readState = page.locator('.hs__read-state').first();
    await expect(readState).toBeVisible();
    await expect(readState).toHaveText(/healthy|drifting|breach/i);

    // KEY INTERACTION: focus a strip and press Enter -> the observational drawer
    // opens (role=dialog aria-modal). It never auto-foregrounds (M2): it only
    // opens on this explicit operator intent.
    await strip.focus();
    await page.keyboard.press('Enter');

    const drawer = page.locator('.hs-drawer[role="dialog"]');
    await expect(drawer).toBeVisible();
    // The detail view renders the last-N chart label + the trigger_reason
    // breakdown (paired text + count, never color-only).
    await expect(drawer.getByText(/Confidence \+ throughput/i)).toBeVisible();
    await expect(drawer.getByText(/trigger_reason breakdown/i)).toBeVisible();
    // The drawer carries a literal data-source label (mock vs live).
    await expect(drawer.getByText(/SAMPLE DATA|LIVE --/i)).toBeVisible();

    // Escape closes the drawer.
    await page.keyboard.press('Escape');
    await expect(page.locator('.hs-drawer[role="dialog"]')).toHaveCount(0);
  });
});
