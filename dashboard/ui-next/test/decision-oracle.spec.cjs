/* decision-oracle.spec.cjs -- standalone Playwright --headed test for the BETA
 * feature "decision-oracle" (#12). CommonJS, self-contained (mirrors the
 * foundation BETA-toggle test idiom).
 *
 * WHAT IT PROVES
 *   1. OFF (default): the feature renders NOTHING -- no launcher rail, no whisper
 *      pane in the DOM. (Beta gate is load-bearing: no listeners/timers either.)
 *   2. Toggle ON via Settings > BETA features: the launcher rail mounts.
 *   3. The key interaction: opening the whisper pane (driven via the documented
 *      `decision-oracle:open` window bridge so the test is independent of live
 *      gov.db state -- the component fetches, 404s/empties, and falls back to
 *      realistic MOCK data) renders Layer 1 with the paired "L2 -- CURRENT" rung
 *      badge (M4: text + color, never color alone) and the OVERFIT? advisory.
 *   4. Escape closes the pane.
 *
 * PRE-REQ (MAIN-THREAD owned -- NOT this test's job):
 *   - the ui-next dev/preview server is up on http://127.0.0.1:4317 (proxying the
 *     live governance server). Set ORACLE_URL to override.
 *
 * RUN (main thread):
 *   npx playwright test dashboard/ui-next/test/decision-oracle.spec.cjs --headed
 */
const { test, expect } = require('@playwright/test');

const URL = process.env.ORACLE_URL || 'http://127.0.0.1:4317/';
const FLAG_LABEL = /Decision Oracle pedigree/i;

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
  // close the drawer (Escape) so the launcher rail is unobstructed
  await page.keyboard.press('Escape');
}

test.describe('BETA decision-oracle (#12)', () => {
  test('renders nothing when the flag is OFF', async ({ page }) => {
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.waitForSelector('#frameA', { timeout: 15000 });

    // Ensure OFF (the default; also clears any persisted mirror from a prior run).
    await setFlag(page, false);

    // No launcher rail, no whisper pane in the DOM while gated OFF.
    await expect(page.locator('.do-launcher')).toHaveCount(0);
    await expect(page.locator('.whisper')).toHaveCount(0);

    // The bridge event is a no-op when OFF (component not mounted -> no listener).
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent('decision-oracle:open', { detail: { hash: 'deadbeefcafef00d' } }));
    });
    await page.waitForTimeout(300);
    await expect(page.locator('.whisper.is-open')).toHaveCount(0);
  });

  test('mounts + opens the pedigree whisper pane when ON', async ({ page }) => {
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.waitForSelector('#frameA', { timeout: 15000 });

    await setFlag(page, true);

    // Launcher rail is present once ON (its content may be empty if no governed
    // pattern is in scope -- presence, not population, is the gate assertion).
    await expect(page.locator('.do-launcher')).toHaveCount(1);
    await expect(page.locator('.do-launcher__eyebrow')).toHaveText(/Decision Oracle/i);

    // Drive the pane via the documented bridge so the test does not depend on
    // live gov.db rows: the component fetches, the hash 404s/empties, and it
    // falls back to realistic MOCK pedigree data.
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent('decision-oracle:open', { detail: { hash: '9f2c1a77b4e03d56' } }));
    });

    const pane = page.locator('.whisper.is-open');
    await expect(pane).toHaveCount(1);

    // Layer 1: the CURRENT rung carries a PAIRED text badge (M4 -- never color
    // alone). The mock fixture is L2.
    await expect(pane.getByText(/L2 -- CURRENT/)).toBeVisible();

    // The promotion meter renders paired TEXT ("X / N toward L3"), not a bare bar.
    await expect(pane.getByText(/toward L3/i)).toBeVisible();

    // The OVERFIT? advisory chip renders the literal word (M8 dashed advisory).
    await expect(pane.getByText('OVERFIT?')).toBeVisible();

    // Layer 2 collapsible: expand it, then the read-only scrubber + a timeline
    // node are present.
    await pane.getByRole('button', { name: /Layer 2 -- ancestral replay|ancestral replay/i }).click();
    await expect(pane.locator('.scrubber')).toBeVisible();
    await expect(pane.locator('.tnode').first()).toBeVisible();

    // Escape closes the pane.
    await page.keyboard.press('Escape');
    await expect(page.locator('.whisper.is-open')).toHaveCount(0);
  });
});
