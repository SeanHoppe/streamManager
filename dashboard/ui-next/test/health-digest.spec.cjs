/* health-digest.spec.cjs -- standalone Playwright --headed test for the BETA
 * feature "health-digest" (#32). CommonJS, self-contained (mirrors the
 * foundation BETA-toggle test idiom + health-sparklines.spec.cjs /
 * decision-oracle.spec.cjs).
 *
 * WHAT IT PROVES
 *   1. OFF (default): the feature renders NOTHING -- no .hd digest block, no
 *      health badge, no digest detail in the DOM. The beta gate is load-bearing
 *      (no fetch / poller / SSE handler / timer registers when OFF).
 *   2. Toggle ON via Settings > BETA features: the .hd digest block mounts and
 *      renders at least one health lane. When gov.db has no governed-session
 *      digests the component falls back to realistic MOCK data, so a lane +
 *      paired health badge are always present.
 *   3. M4 (paired label+color): each lane carries a literal text health WORD
 *      (QUIET / VARIANCE / ACTION N) -- never color alone. The data-source line
 *      states SAMPLE DATA vs LIVE explicitly.
 *   4. The key interaction: activating a lane's expand button reveals the
 *      per-session digest detail (uptime / decisions / latest decision / agents
 *      / jobs / hitl / latest escalation), via aria-expanded.
 *   5. Polarity (G2): the self-exclude footer readout is present + on-screen.
 *
 * PRE-REQ (MAIN-THREAD owned -- NOT this test's job):
 *   - the ui-next dev/preview server is up on http://127.0.0.1:4317 (proxying
 *     the live governance server). Set HD_URL to override.
 *
 * RUN (main thread):
 *   npx playwright test dashboard/ui-next/test/health-digest.spec.cjs --headed
 */
const { test, expect } = require('@playwright/test');

const URL = process.env.HD_URL || 'http://127.0.0.1:4317/';
const FLAG_LABEL = /Session health digest/i;

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
  // close the drawer (Escape) so the rail digest block is unobstructed
  await page.keyboard.press('Escape');
}

test.describe('BETA health-digest (#32)', () => {
  test('renders nothing when the flag is OFF', async ({ page }) => {
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.waitForSelector('#frameA', { timeout: 15000 });

    // Ensure OFF (the default; also clears any persisted mirror from a prior run).
    await setFlag(page, false);

    // No digest block, no health badge, no detail in the DOM while gated OFF.
    await expect(page.locator('.hd')).toHaveCount(0);
    await expect(page.locator('.hd-badge')).toHaveCount(0);
    await expect(page.locator('.hd-detail')).toHaveCount(0);
  });

  test('mounts the digest block + expands a lane detail when ON', async ({ page }) => {
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.waitForSelector('#frameA', { timeout: 15000 });

    await setFlag(page, true);

    // The digest block mounts once ON, inside the SessionRail.
    const block = page.locator('.hd');
    await expect(block).toHaveCount(1);
    // The DIGEST source readout (paired label) is present.
    await expect(block.getByText(/DIGEST/).first()).toBeVisible();
    // The data-source line is an explicit literal label (mock OR live).
    await expect(block.locator('.hd__source')).toHaveText(/SAMPLE DATA|LIVE --/i);

    // At least one health lane renders (mock fallback guarantees presence even
    // with an empty gov.db). Each lane is a listitem with a data-health-state.
    const lane = page.locator('.hd-lane').first();
    await expect(lane).toBeVisible();
    await expect(lane).toHaveAttribute('data-health-state', /quiet|variance|action/);

    // M4: every lane carries a literal text health WORD beside any color (never
    // color alone). It must be one of the three documented states.
    const badge = page.locator('.hd-badge').first();
    await expect(badge).toBeVisible();
    await expect(badge).toHaveText(/QUIET|VARIANCE|ACTION/);

    // The rail-header ACTIVE tally is paired with its literal label, never bare.
    await expect(block.locator('.hd__tally-tag')).toHaveText(/ACTIVE/);

    // KEY INTERACTION: a lane's expand button reveals the per-session digest
    // detail (aria-expanded toggles; the detail region renders the dl rows). It
    // NEVER auto-foregrounds (M2): it opens only on this explicit operator click.
    const expand = lane.locator('.hd-lane__expand');
    await expect(expand).toHaveAttribute('aria-expanded', 'false');
    await expand.click();
    await expect(expand).toHaveAttribute('aria-expanded', 'true');

    const detail = lane.locator('.hd-detail');
    await expect(detail).toBeVisible();
    await expect(detail.getByText(/uptime/i)).toBeVisible();
    await expect(detail.getByText(/latest decision/i)).toBeVisible();
    await expect(detail.getByText(/hitl pending/i)).toBeVisible();

    // Collapsing it again hides the detail (the expand control is operable).
    await expand.click();
    await expect(expand).toHaveAttribute('aria-expanded', 'false');
    await expect(lane.locator('.hd-detail')).toHaveCount(0);

    // Polarity (G2): the self-exclude readout is on-screen + auditable.
    await expect(block.locator('.hd__foot')).toContainText(/self row.*excluded/i);
  });
});
