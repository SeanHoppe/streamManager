// audit-roundtrip.spec.mjs -- live FR-PPP provenance-audit round-trip check.
//
// Closes the M11/M12 verification deferral: the render-validator + axe gates
// only exercise AuditDock at the build / static-contract / empty-state level.
// This spec drives the REAL server SSE transport end-to-end and asserts the
// AuditDock DOM transitions through the full FR-PPP flow:
//
//   audit.probe                 -> AuditProbeRow radio candidate list + "none of
//                                  the above" + SIGN affordance
//   audit.canary_emit           -> CanaryEchoRow pending: nonce + countdown
//   audit.canary_observed       -> CanaryEchoRow flips to observed (confirmed)
//   audit.hallucination_detected-> HallucinationAlert "HALLUCINATION DETECTED"
//                                  + operator-dismiss removes the card
//
// It is an INTEGRATION spec, not part of `npm test` (which is the fast static
// render-validator). Run explicitly:  node test/audit-roundtrip.spec.mjs
//
// Orchestration (self-contained): spawns the in-process server+driver harness
// (tools/audit_ui_roundtrip_harness.py) and the vite dev server (which proxies
// /api + /events to the harness), runs puppeteer against 127.0.0.1:4317, then
// tears the whole process tree down. Exit 0 = all transitions verified.
//
// M16: every literal here is generic UI/protocol vocabulary -- no
// monitored-project names, no JOB ids.

import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdir } from 'node:fs/promises';

import puppeteer from 'puppeteer';

const __dirname = dirname(fileURLToPath(import.meta.url));
const UI = resolve(__dirname, '..'); // dashboard/ui-next
const ROOT = resolve(UI, '..', '..'); // repo root
const URL = 'http://127.0.0.1:4317/';
const SERVER = 'http://127.0.0.1:8765/api/hitl/pending';
const IS_WIN = process.platform === 'win32';

/** @type {import('node:child_process').ChildProcess[]} */
const children = [];

function spawnChild(label, cmd, args, opts = {}) {
  // Windows: Node's CVE-2024-27980 fix throws EINVAL when spawning a `.cmd`
  // shim (npm.cmd) without a shell. shell:true routes through cmd.exe.
  const child = spawn(cmd, args, { stdio: ['ignore', 'pipe', 'pipe'], shell: IS_WIN, ...opts });
  children.push(child);
  const pipe = (stream, tag) => {
    stream.setEncoding('utf8');
    let buf = '';
    stream.on('data', (d) => {
      buf += d;
      let i;
      while ((i = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, i);
        buf = buf.slice(i + 1);
        if (line.trim()) console.log(`  [${label}${tag}] ${line}`);
      }
    });
  };
  pipe(child.stdout, '');
  pipe(child.stderr, ':err');
  child.on('error', (e) => console.log(`  [${label}] spawn error: ${e.message}`));
  return child;
}

function killTree(child) {
  if (!child || child.killed || child.exitCode != null) return;
  try {
    if (IS_WIN && child.pid != null) {
      spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
    } else {
      child.kill('SIGTERM');
    }
  } catch {
    /* best-effort */
  }
}

function killAll() {
  for (const c of children) killTree(c);
}

async function waitHttp(url, ms, label) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url, { method: 'GET' });
      if (res.status < 500) return true;
    } catch {
      /* not up yet */
    }
    await sleep(400);
  }
  throw new Error(`${label} did not come up at ${url} within ${ms}ms`);
}

// ---- assertion helpers -----------------------------------------------------
const checks = [];
function record(name, ok, detail = '') {
  checks.push({ name, ok, detail });
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ` -- ${detail}` : ''}`);
}

async function main() {
  console.log('== FR-PPP audit-surface live round-trip ==');
  await mkdir(resolve(ROOT, 'reports'), { recursive: true });

  // 1) Start the in-process server + envelope driver.
  spawnChild('harness', IS_WIN ? 'python' : 'python3', ['tools/audit_ui_roundtrip_harness.py'], {
    cwd: ROOT,
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
  });

  // 2) Start the vite dev server (proxies /api + /events -> :8765) UNLESS one is
  //    already serving 4317 (a spike dev server may already be up -- reuse it).
  let viteUp = false;
  try {
    const r = await fetch(URL);
    viteUp = r.status < 500;
  } catch {
    /* not up */
  }
  if (viteUp) {
    console.log('  vite already serving on 4317 -- reusing it');
  } else {
    spawnChild('vite', IS_WIN ? 'npm.cmd' : 'npm', ['run', 'dev'], { cwd: UI });
    await waitHttp(URL, 60000, 'vite dev');
  }

  // 3) Wait for the harness transport.
  await waitHttp(SERVER, 60000, 'server (harness)');
  console.log('  both transports up');

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });

  try {
    const page = await browser.newPage();
    page.on('console', (m) => {
      const t = m.type();
      if (t === 'error' || t === 'warning') console.log(`    [page:${t}] ${m.text()}`);
    });
    await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 30000 });

    // AuditDock host present.
    await page.waitForSelector('section.audit', { timeout: 30000 });
    record('AuditDock host mounted', true);

    // --- M11: audit.probe -> AuditProbeRow radio candidate list ---
    await page.waitForSelector('article.probe', { timeout: 30000 });
    // Radios appear only once the audit.probe envelope is cached (candidate
    // list is rendered FROM DATA, never fabricated).
    await page.waitForSelector('article.probe input[type="radio"]', { timeout: 15000 });
    const radioCount = await page.$$eval('article.probe input[type="radio"]', (els) => els.length);
    record(
      'AuditProbeRow radio candidate list (>=3: 2 candidates + none-of-the-above)',
      radioCount >= 3,
      `radios=${radioCount}`,
    );
    const probeText = await page.$eval('article.probe', (el) => el.textContent || '');
    record(
      'AuditProbeRow renders explicit "none of the above"',
      /none of the above/i.test(probeText),
    );
    const hasSign = (await page.$('article.probe button.probe__sign')) != null;
    record('AuditProbeRow exposes SIGN affordance', hasSign);
    // M11 session-validation guard. Under ALL scope (no session selected) the
    // row shows a scope-warning note AND -- this is the load-bearing part --
    // signing is refused at SUBMIT time with an inline validation error instead
    // of POSTing a scopeless (meaningless) attestation. (SIGN is deliberately
    // NOT disabled-by-scope; it is disabled only until the candidate envelope
    // arrives. The guard lives in AuditProbeRow.sign(), which early-returns on
    // sessionMissing before any network call.) Exercise it live:
    const hasScopeWarn = (await page.$('article.probe .probe__scopewarn')) != null;
    record('M11 scope-warning note shown under ALL scope', hasScopeWarn);
    await page.click('article.probe button.probe__sign');
    await page.waitForSelector('article.probe .probe__error', { timeout: 5000 });
    const probeErr = await page.$eval('article.probe .probe__error', (el) => (el.textContent || '').trim());
    record(
      'M11 session guard: SIGN under ALL scope surfaces inline validation (no POST)',
      /select a session/i.test(probeErr),
      `err="${probeErr}"`,
    );

    // --- M12: audit.canary_emit -> CanaryEchoRow pending (nonce + countdown) ---
    await page.waitForSelector('article.canary[data-status="pending"]', { timeout: 30000 });
    const nonceText = await page.$eval('article.canary .canary__nonce', (el) => (el.textContent || '').trim());
    record(
      'CanaryEchoRow pending: nonce rendered from data',
      nonceText.length > 0 && nonceText !== '--',
      `nonce="${nonceText}"`,
    );
    const hasCountdown = (await page.$('article.canary [aria-label="Canary echo countdown"], article.canary .countdown, article.canary [role="progressbar"]')) != null;
    // CountdownBar primitive: tolerate either an explicit label or a progressbar role.
    record('CanaryEchoRow renders a countdown', hasCountdown);

    // --- M12: audit.canary_observed -> flips to observed (binding proven) ---
    await page.waitForSelector('article.canary[data-status="observed"]', { timeout: 30000 });
    const observedText = await page.$eval('article.canary[data-status="observed"]', (el) => el.textContent || '');
    record(
      'CanaryEchoRow observed: CONFIRMED state',
      /confirmed/i.test(observedText),
    );

    // --- M12: audit.hallucination_detected -> HallucinationAlert (dismiss) ---
    await page.waitForSelector('article.halluc', { timeout: 30000 });
    const hallText = await page.$eval('article.halluc', (el) => el.textContent || '');
    record(
      'HallucinationAlert renders literal "HALLUCINATION DETECTED"',
      /HALLUCINATION DETECTED/.test(hallText),
    );
    record(
      'HallucinationAlert shows the decoy path forensic evidence',
      /decoy-negative-control\.jsonl/.test(hallText),
    );
    // role=alert for assistive-tech announcement (M17).
    const hallRole = await page.$eval('article.halluc', (el) => el.getAttribute('role'));
    record('HallucinationAlert is role="alert"', hallRole === 'alert');
    // Operator-dismiss removes the card (UI-only; the WAL row stands).
    await page.click('article.halluc button.halluc__dismiss');
    await page.waitForSelector('article.halluc', { hidden: true, timeout: 10000 });
    record('HallucinationAlert operator-dismiss removes the card', true);

    const failed = checks.filter((c) => !c.ok);
    if (failed.length) {
      await page
        .screenshot({ path: resolve(ROOT, 'reports', 'audit-roundtrip-fail.png'), fullPage: true })
        .catch(() => {});
      throw new Error(`${failed.length} assertion(s) failed: ${failed.map((c) => c.name).join('; ')}`);
    }
    console.log(`\n== ALL ${checks.length} ASSERTIONS PASSED ==`);
  } finally {
    await browser.close().catch(() => {});
  }
}

main()
  .then(() => {
    killAll();
    // Give taskkill a beat, then exit 0.
    setTimeout(() => process.exit(0), 500);
  })
  .catch((err) => {
    console.error(`\n!! ROUND-TRIP FAILED: ${err && err.message ? err.message : err}`);
    killAll();
    setTimeout(() => process.exit(1), 500);
  });
