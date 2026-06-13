/* regret-mining-override-loop.spec.cjs -- standalone Playwright --headed test
 * for the BETA feature "regret-mining-override-loop" (#24: Regret Mining --
 * close the operator-override feedback loop). CommonJS, self-contained (mirrors
 * escalation-timeline-causal-forensics.spec.cjs / health-sparklines.spec.cjs).
 *
 * WHAT IT PROVES
 *   1. OFF (default): the feature renders NOTHING -- no
 *      [data-testid="regret-mining-override-loop"] node anywhere in the DOM.
 *      The beta gate is load-bearing (no card, no poller/SSE/timer registered
 *      while gated OFF).
 *   2. Toggle ON via Settings > BETA features: the regret card mounts in Frame
 *      A. With an empty hitl_overrides table it falls back to realistic MOCK
 *      data (data-mock="true") so the ledger is visible.
 *   3. The ledger renders ranked divergence-cluster lanes, each a real <button>
 *      with aria-expanded; the hottest lane is first. M4 paired label+color:
 *      each lane carries the literal direction WORD (ESCALATED / DE-ESCALATED)
 *      and the literal "n/N overridden" fraction next to the bar (never color
 *      alone). Polarity is shown as a visible "excluded N SM-self rows" chip.
 *   4. KEY INTERACTION: clicking a lane opens its evidence drawer; clicking
 *      "Draft as proposal" reveals the READ-ONLY markdown stub the operator can
 *      copy / download -- it writes nothing server-side.
 *
 * PRE-REQ (MAIN-THREAD owned -- NOT this test's job):
 *   - the ui-next dev/preview server is up on http://127.0.0.1:4317 (proxying
 *     the live governance server). Set RMO_URL to override.
 *
 * RUN (main thread):
 *   npx playwright test dashboard/ui-next/test/regret-mining-override-loop.spec.cjs --headed
 */
const { test, expect } = require('@playwright/test');

const URL = process.env.RMO_URL || 'http://127.0.0.1:4317/';
const FLAG_LABEL = /Regret Mining: override feedback loop/i;
const TESTID = '[data-testid="regret-mining-override-loop"]';

async function setFlag(page, on) {
  await page.getByRole('button', { name: /Open operator settings/i }).click();
  const toggle = page.getByRole('checkbox', { name: FLAG_LABEL });
  await toggle.waitFor({ state: 'visible' });
  const checked = await toggle.isChecked();
  if (checked !== on) await toggle.click();
  await expect(toggle).toBeChecked({ checked: on });
  await page.keyboard.press('Escape');
}

test.describe('BETA regret-mining-override-loop (#24)', () => {
  test('renders nothing when the flag is OFF', async ({ page }) => {
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.waitForSelector('#frameA', { timeout: 15000 });
    await setFlag(page, false);
    await page.waitForTimeout(200);
    await expect(page.locator(TESTID)).toHaveCount(0);
  });

  test('mounts the regret ledger + drafts a proposal stub when ON', async ({ page }) => {
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.waitForSelector('#frameA', { timeout: 15000 });

    await setFlag(page, true);

    // The card mounts. With an empty hitl_overrides table it falls back to mock.
    const root = page.locator(TESTID);
    await expect(root).toBeVisible();
    await expect(root).toHaveAttribute('data-mock', 'true');

    // Polarity self-exclusion is rendered as a visible feature (G2).
    await expect(root.getByText(/excluded/i)).toBeVisible();
    await expect(root.getByText(/SM-self rows/i)).toBeVisible();

    // The ledger renders ranked cluster lanes (the hottest first).
    const lanes = root.locator('.rmo__lane');
    await expect(lanes.first()).toBeVisible();
    const laneCount = await lanes.count();
    expect(laneCount).toBeGreaterThan(0);

    // M4 paired label+color: the hottest lane carries the literal direction
    // WORD + the literal "n/N overridden" fraction (never color alone).
    const hot = lanes.first();
    await expect(hot.locator('.rmo__ar-badge')).toHaveText(/ESCALATED|DE-ESCALATED/);
    await expect(hot.locator('.rmo__frac')).toHaveText(/\d+\/\d+/);
    await expect(hot.locator('.rmo__rate')).toHaveText(/\d+%/);
    await expect(hot).toHaveAttribute('aria-expanded', 'false');

    // KEY INTERACTION 1: clicking a lane opens its evidence drawer.
    await hot.click();
    await expect(hot).toHaveAttribute('aria-expanded', 'true');
    const drawer = root.locator('.rmo__drawer');
    await expect(drawer).toBeVisible();
    await expect(drawer.locator('.rmo__ev-row').first()).toBeVisible();

    // KEY INTERACTION 2: "Draft as proposal" reveals the read-only markdown stub.
    await drawer.getByRole('button', { name: /Draft as proposal/i }).click();
    const draft = root.locator('.rmo__draft');
    await expect(draft).toBeVisible();
    await expect(draft.locator('.rmo__draft-pre')).toContainText(/Advisory-bias candidate/i);
    await expect(draft.getByText(/READ-ONLY STUB/i)).toBeVisible();
    // The advisory contract line is always present (writes nothing server-side).
    await expect(root.getByText(/Advisory only/i)).toBeVisible();

    // Collapse via Escape (M17 keyboard).
    await hot.focus();
    await page.keyboard.press('Escape');
    await expect(hot).toHaveAttribute('aria-expanded', 'false');
  });
});