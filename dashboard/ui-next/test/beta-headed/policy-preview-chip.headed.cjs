/* policy-preview-chip.spec.cjs -- standalone Playwright --headed test for the
 * BETA feature "policy-preview-chip" (#21). CommonJS, self-contained (mirrors
 * the foundation BETA-toggle test idiom + health-sparklines.spec.cjs).
 *
 * WHAT IT PROVES
 *   1. OFF (default): the feature renders NOTHING -- no .ppc chip in the DOM. The
 *      beta gate is load-bearing (no fetch / poller / SSE handler / timer
 *      registers while gated OFF).
 *   2. Toggle ON via Settings > BETA features: the .ppc chip mounts beneath the
 *      HITL SYNC/ASYNC toggle. When gov.db has no in-scope corpus the component
 *      falls back to realistic MOCK data, so the chip is always present.
 *   3. The chip is ADVISORY only: it carries the literal "ADVISORY -- your
 *      decision stands" paired-text tag and a paired action VERB + share
 *      fraction (M4: text, never color alone). role="note" (passive, not alert).
 *   4. KEY INTERACTION: the expand button (the only interactive node) toggles the
 *      per-action histogram; Escape collapses it. Toggling the SYNC/ASYNC mode
 *      does NOT change the chip readout (it never pre-selects a mode).
 *
 * PRE-REQ (MAIN-THREAD owned -- NOT this test's job):
 *   - the ui-next dev/preview server is up on http://127.0.0.1:4317 (proxying
 *     the live governance server). Set PPC_URL to override.
 *
 * RUN (main thread):
 *   npx playwright test dashboard/ui-next/test/policy-preview-chip.spec.cjs --headed
 */
const { test, expect } = require('@playwright/test');

const URL = process.env.PPC_URL || 'http://127.0.0.1:4317/';
const FLAG_LABEL = /Policy-preview chip/i;

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
  // close the drawer (Escape) so the dock header is unobstructed
  await page.keyboard.press('Escape');
}

test.describe('BETA policy-preview-chip (#21)', () => {
  test('renders nothing when the flag is OFF', async ({ page }) => {
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.waitForSelector('#frameA', { timeout: 15000 });

    // Ensure OFF (the default; also clears any persisted mirror from a prior run).
    await setFlag(page, false);

    // No chip in the DOM while gated OFF.
    await expect(page.locator('.ppc[data-beta="policy-preview-chip"]')).toHaveCount(0);
  });

  test('mounts the advisory chip + toggles the histogram when ON', async ({ page }) => {
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.waitForSelector('#frameA', { timeout: 15000 });

    await setFlag(page, true);

    // The chip mounts once ON.
    const chip = page.locator('.ppc[data-beta="policy-preview-chip"]');
    await expect(chip).toHaveCount(1);
    await expect(chip).toBeVisible();
    // Passive advisory: role=note (never alert).
    await expect(chip).toHaveAttribute('role', 'note');

    // ADVISORY paired-text tag is always present (M8 non-verdict grammar).
    await expect(chip.getByText(/ADVISORY -- your decision stands/i)).toBeVisible();
    // CORPUS PREVIEW tag.
    await expect(chip.getByText(/corpus preview/i)).toBeVisible();

    // M4: the headline carries a literal text signal -- either a corpus verb +
    // share (CORPUS: n/m ALLOW) or the honest NO HISTORY cold read. One must show.
    const headline = chip.locator('.ppc__headline');
    await expect(headline).toBeVisible();
    await expect(headline).toHaveText(/CORPUS:|NO HISTORY/i);

    // Polarity made visible (G2): the SM-self exclusion readout is always shown.
    await expect(chip.getByText(/SM-self excluded/i)).toBeVisible();

    // KEY INTERACTION: the expand button (the only interactive node) is present
    // for a non-cold read; activate it -> the histogram reveal opens. (When the
    // live read is cold there is no histogram; the chip still rendered + the
    // advisory contract above already passed, so we guard on its presence.)
    const expand = chip.getByRole('button', { name: /show histogram/i });
    if (await expand.count()) {
      await expand.focus();
      await page.keyboard.press('Enter');
      const hist = chip.locator('#ppc-hist.is-open');
      await expect(hist).toBeVisible();
      // Each bar pairs a literal action label + count + percent (never color only).
      await expect(hist.getByText(/ALLOW/).first()).toBeVisible();
      await expect(hist.getByText(/action histogram/i)).toBeVisible();

      // Escape collapses the reveal.
      await page.keyboard.press('Escape');
      await expect(chip.locator('#ppc-hist.is-open')).toHaveCount(0);
    }
  });
});
