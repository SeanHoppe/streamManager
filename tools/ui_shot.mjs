#!/usr/bin/env node
// tools/ui_shot.mjs -- capture the ui-next spike rendering against the live
// governance server (dev proxy on :4317). Spike-local verification helper for
// the u-compose wiring pass; NOT a production tool.
//
//   node tools/ui_shot.mjs [--url http://127.0.0.1:4317/] [--out reports/ui-next-live]
//
// Waits for the three guaranteed frames (#frameA/#frameB/#frameC) + a settle
// delay so the seeded REST data + first SSE rows land, then screenshots the
// obsidian (default) + paper themes.

import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer";

function arg(name, dflt) {
  const i = process.argv.indexOf(name);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : dflt;
}
const url = arg("--url", "http://127.0.0.1:4317/");
const outBase = arg("--out", "reports/ui-next-live");
const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");

const browser = await puppeteer.launch({ headless: "new", args: ["--no-sandbox"] });
try {
  const page = await browser.newPage();
  page.on("pageerror", (e) => console.log("[shot] pageerror: " + e.message));
  page.on("console", (m) => {
    const t = m.type();
    if (t === "error" || t === "warning") console.log(`[shot] console.${t}: ${m.text()}`);
  });
  await page.setViewport({ width: 1480, height: 940, deviceScaleFactor: 1 });
  await page.goto(url, { waitUntil: "networkidle2", timeout: 30000 });
  await page.waitForSelector("#frameA", { timeout: 15000 });
  await page.waitForSelector("#frameB", { timeout: 15000 });
  await page.waitForSelector("#frameC", { timeout: 15000 });
  // settle for seeded REST + first SSE rows + at least one stats/sessions poll
  // (statsStore polls at 5s, sessions at 5s -- wait past the first cadence).
  await new Promise((r) => setTimeout(r, 6500));

  const obsidian = resolve(ROOT, `${outBase}-obsidian.png`);
  await mkdir(dirname(obsidian), { recursive: true });
  await page.screenshot({ path: obsidian, fullPage: false });
  console.log(`[shot] wrote ${obsidian}`);

  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "paper"));
  await new Promise((r) => setTimeout(r, 800));
  const paper = resolve(ROOT, `${outBase}-paper.png`);
  await page.screenshot({ path: paper, fullPage: false });
  console.log(`[shot] wrote ${paper}`);

  // dump a small live-state readout for the transcript
  const readout = await page.evaluate(() => ({
    title: document.title,
    frameA: !!document.querySelector("#frameA"),
    decisionRows: document.querySelectorAll(".repl__item").length,
    agentRows: document.querySelectorAll(".agent-row").length,
    jobRows: document.querySelectorAll('.lc__row:not(.lc__row--head)').length,
    conn: (document.querySelector(".conn__text") || {}).textContent || "",
    foot: (document.querySelector(".foot__stats") || {}).textContent || "",
    // left command-column (SessionRail) state
    railPresent: !!document.querySelector(".shell__rail .rail"),
    railLanes: document.querySelectorAll(".rail__lanes .lane").length,
    railEmpty: !!document.querySelector(".rail__empty"),
    railTally: (document.querySelector(".rail__tally-num") || {}).textContent || "",
    headerPickerVisible: (() => {
      const el = document.querySelector(".seam--header");
      if (!el) return false;
      return getComputedStyle(el).display !== "none";
    })(),
  }));
  console.log("[shot] live readout: " + JSON.stringify(readout));
} finally {
  await browser.close();
}
