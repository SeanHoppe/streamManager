#!/usr/bin/env node
// tools/axe_audit.mjs
//
// NFR-UI-1 — automated WCAG audit of the live dashboard.
//
// Usage:
//   node tools/axe_audit.mjs [--url http://127.0.0.1:8765/]
//
// Exit code:
//   0  — no `serious` or `critical` violations.
//   1  — at least one `serious` or `critical` violation remaining.
//
// Outputs:
//   reports/axe-{ISO-timestamp}.json  — full axe-core result JSON
//   reports/axe-latest.md             — human-readable summary
//
// AAA-level and color-contrast-only violations are reported but never
// fail the run (out of scope per task-5 spec).

import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import puppeteer from "puppeteer";
import { AxePuppeteer } from "@axe-core/puppeteer";

// ── arg parsing ────────────────────────────────────────────────────────
function parseArgs(argv) {
  const out = { url: "http://127.0.0.1:8765/" };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--url" && argv[i + 1]) {
      out.url = argv[++i];
    } else if (a.startsWith("--url=")) {
      out.url = a.slice("--url=".length);
    }
  }
  return out;
}

const { url } = parseArgs(process.argv);
const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const REPORTS = resolve(ROOT, "reports");

// ── ISO timestamp safe for filenames (YYYYMMDDTHHMMSSZ) ────────────────
function tsName() {
  return new Date().toISOString().replace(/[-:]/g, "").replace(/\..+$/, "");
}

// ── markdown summary builder ───────────────────────────────────────────
function buildMarkdown(result, jsonPath) {
  const counts = { critical: 0, serious: 0, moderate: 0, minor: 0, none: 0 };
  for (const v of result.violations) {
    counts[v.impact ?? "none"] = (counts[v.impact ?? "none"] ?? 0) + 1;
  }
  const lines = [];
  lines.push(`# axe-core audit — ${result.url ?? url}`);
  lines.push("");
  lines.push(`- Timestamp: \`${result.timestamp ?? new Date().toISOString()}\``);
  lines.push(`- axe-core version: \`${result.testEngine?.version ?? "unknown"}\``);
  lines.push(`- Full JSON: \`${jsonPath}\``);
  lines.push("");
  lines.push("## Counts by impact");
  lines.push("");
  lines.push("| impact | count |");
  lines.push("| --- | --- |");
  for (const k of ["critical", "serious", "moderate", "minor"]) {
    lines.push(`| ${k} | ${counts[k] ?? 0} |`);
  }
  lines.push("");
  lines.push(`- passes: ${result.passes.length}`);
  lines.push(`- incomplete: ${result.incomplete.length}`);
  lines.push(`- inapplicable: ${result.inapplicable.length}`);
  lines.push("");
  if (result.violations.length === 0) {
    lines.push("## Violations");
    lines.push("");
    lines.push("_No violations found._");
  } else {
    lines.push("## Violations");
    lines.push("");
    for (const v of result.violations) {
      lines.push(`### [${v.impact}] ${v.id} — ${v.help}`);
      lines.push("");
      lines.push(`- WCAG: ${(v.tags ?? []).join(", ")}`);
      lines.push(`- Help URL: ${v.helpUrl}`);
      lines.push(`- Nodes: ${v.nodes.length}`);
      lines.push("");
      const max = Math.min(v.nodes.length, 5);
      for (let i = 0; i < max; i++) {
        const n = v.nodes[i];
        lines.push(`  ${i + 1}. \`${(n.target ?? []).join(" ")}\``);
        if (n.failureSummary) {
          lines.push(
            "     - " +
              n.failureSummary.split("\n").join(" / ").slice(0, 400),
          );
        }
      }
      if (v.nodes.length > max) {
        lines.push(`  …and ${v.nodes.length - max} more.`);
      }
      lines.push("");
    }
  }
  return lines.join("\n");
}

// ── main ───────────────────────────────────────────────────────────────
async function main() {
  await mkdir(REPORTS, { recursive: true });

  console.log(`[axe] launching headless puppeteer → ${url}`);
  const browser = await puppeteer.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  let exitCode = 0;
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 900 });
    page.on("pageerror", (err) => console.warn(`[axe] pageerror: ${err}`));

    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30_000 });

    // FR-UI three-frame layout: wait for #frameA, #frameB, #frameC.
    await Promise.all([
      page.waitForSelector("#frameA", { timeout: 15_000 }),
      page.waitForSelector("#frameB", { timeout: 15_000 }),
      page.waitForSelector("#frameC", { timeout: 15_000 }),
    ]);
    // Small settle for SSE-driven content to hydrate.
    await new Promise((r) => setTimeout(r, 1500));

    console.log("[axe] running analyze() at WCAG 2.1 A+AA");
    const result = await new AxePuppeteer(page)
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    const ts = tsName();
    const jsonPath = resolve(REPORTS, `axe-${ts}.json`);
    const mdPath = resolve(REPORTS, "axe-latest.md");

    await writeFile(jsonPath, JSON.stringify(result, null, 2), "utf8");
    await writeFile(mdPath, buildMarkdown(result, `reports/axe-${ts}.json`), "utf8");

    console.log(`[axe] wrote ${jsonPath}`);
    console.log(`[axe] wrote ${mdPath}`);

    // task-5 out-of-scope: color-only violations (NFR-UI-6 already pairs
    // labels with non-color affordances) and AAA-level rules.
    const OUT_OF_SCOPE_RULES = new Set(["color-contrast", "color-contrast-enhanced"]);
    const blocking = result.violations.filter(
      (v) =>
        (v.impact === "serious" || v.impact === "critical") &&
        !OUT_OF_SCOPE_RULES.has(v.id),
    );
    if (blocking.length > 0) {
      console.error(
        `[axe] FAIL — ${blocking.length} serious/critical violation(s):`,
      );
      for (const v of blocking) {
        console.error(`  - [${v.impact}] ${v.id} (${v.nodes.length} node(s))`);
      }
      exitCode = 1;
    } else {
      console.log(
        `[axe] OK — 0 serious/critical violations ` +
          `(${result.violations.length} non-blocking violation(s))`,
      );
    }
  } finally {
    await browser.close();
  }
  process.exit(exitCode);
}

main().catch((err) => {
  console.error("[axe] fatal:", err);
  process.exit(2);
});
