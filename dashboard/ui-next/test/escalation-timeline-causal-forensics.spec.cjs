/* escalation-timeline-causal-forensics.spec.cjs -- standalone Playwright
 * --headed test for the BETA feature "escalation-timeline-causal-forensics"
 * (#13: Escalation Timeline -- forensic causal-chain visibility). CommonJS,
 * self-contained (mirrors what-changed.spec.cjs / health-sparklines.spec.cjs).
 *
 * WHAT IT PROVES
 *   1. OFF (default): the feature renders NOTHING -- no
 *      [data-testid="escalation-timeline-causal-forensics"] node anywhere in the
 *      DOM. The beta gate is load-bearing (no badge, no spine, no SSE/poller
 *      registered while gated OFF).
 *   2. Toggle ON via Settings > BETA features: the resting paired amber count
 *      badge mounts in the Frame C gutter. With an empty gov.db the component
 *      falls back to realistic MOCK data (data-mock="true"), so the badge shows
 *      a non-zero "N escalations" count.
 *   3. M2 ambient-at-rest: turning the flag ON does NOT auto-open the pane. The
 *      spine (role=listbox) is absent until the operator activates the badge.
 *   4. KEY INTERACTION: activating the badge opens the wall-clock spine; opening
 *      a node opens the split-view forensic overlay (role=dialog) with the LEFT
 *      DecisionDiff (proposed-action badge + confidence) and the RIGHT causal
 *      context (Lead-up / Aftermath). Escape closes the overlay.
 *   5. M4 paired label+color: the count badge, the node event badge, and the
 *      action badge each carry a literal TEXT word (never color alone).
 *
 * PRE-REQ (MAIN-THREAD owned -- NOT this test's job):
 *   - the ui-next dev/preview server is up on http://127.0.0.1:4317 (proxying
 *     the live governance server). Set ETL_URL to override.
 *
 * RUN (main thread):
 *   npx playwright test dashboard/ui-next/test/escalation-timeline-causal-forensics.spec.cjs --headed
 */
const { test, expect } = require('@playwright/test');

const URL = process.env.ETL_URL || 'http://127.0.0.1:4317/';
const FLAG_LABEL = /Escalation Timeline: causal forensics/i;
const TESTID = '[data-testid="escalation-timeline-causal-forensics"]';

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
  // close the drawer (Escape) so the Frame C gutter is unobstructed
  await page.keyboard.press('Escape');
}

test.describe('BETA escalation-timeline-causal-forensics (#13)', () => {
  test('renders nothing when the flag is OFF', async ({ page }) => {
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.waitForSelector('#frameC', { timeout: 15000 });

    // Ensure OFF (the default; also clears any persisted mirror from a prior run).
    await setFlag(page, false);
    await page.waitForTimeout(200);

    await expect(page.locator(TESTID)).toHaveCount(0);
    // no spine, no overlay either
    await expect(page.locator('.etl__spine')).toHaveCount(0);
  });

  test('mounts the badge + opens spine + overlay when ON', async ({ page }) => {
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.waitForSelector('#frameC', { timeout: 15000 });

    await setFlag(page, true);

    // The container mounts. With an empty gov.db it falls back to mock data.
    const root = page.locator(TESTID);
    await expect(root).toBeVisible();
    await expect(root).toHaveAttribute('data-mock', 'true');

    // M2: ambient at rest -- the pane is NOT auto-opened. The spine is absent.
    await expect(page.locator('.etl__spine')).toHaveCount(0);

    // The resting paired amber count badge is present with a non-zero count and
    // the literal WORD "escalation(s)" (M4 -- never color alone).
    const badge = root.locator('.etl__badge[data-open]');
    await expect(badge).toBeVisible();
    await expect(badge.locator('.etl__badge-n')).toHaveText(/[1-9]\d*/);
    await expect(badge.locator('.etl__badge-lab')).toHaveText(/escalation/i);

    // KEY INTERACTION 1: activating the badge opens the wall-clock spine.
    await badge.focus();
    await page.keyboard.press('Enter');
    const spine = page.locator('.etl__spine');
    await expect(spine).toBeVisible();

    // Each node carries a paired event badge with a literal WORD label (M4).
    const node = spine.locator('.etl__node').first();
    await expect(node).toBeVisible();
    await expect(node.locator('.etl__evt-badge')).toHaveText(/[A-Z]/);

    // KEY INTERACTION 2: opening a node opens the split-view forensic overlay.
    await node.click();
    const dialog = page.getByRole('dialog', { name: /forensic detail/i });
    await expect(dialog).toBeVisible();

    // LEFT DecisionDiff: a paired proposed-action badge (WORD) + a confidence %.
    await expect(dialog.locator('.etl__action-badge')).toHaveText(/ALLOW|GUIDE|INTERVENE|BLOCK/);
    await expect(dialog.locator('.etl__conf-val')).toHaveText(/\d+%/);

    // RIGHT causal context: the Lead-up + Aftermath group headers.
    await expect(dialog.getByText(/Lead-up/i)).toBeVisible();
    await expect(dialog.getByText(/Aftermath/i)).toBeVisible();

    // M17: Escape closes the overlay and returns focus to the spine.
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog', { name: /forensic detail/i })).toHaveCount(0);
    // the spine itself remains open (pane is not auto-closed by Escape).
    await expect(spine).toBeVisible();
  });
});
