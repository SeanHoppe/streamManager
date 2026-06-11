# StreamManager UI -- KingMode spike (dashboard/ui-next)

EXPERIMENTAL re-architecture of the operator console. This is a **form**
redesign (frame geometry, hierarchy, motion, density, typography) of the
existing, feature-complete `dashboard/static/index.html`. The behavioural
contract is FROZEN: every endpoint, SSE event, badge semantic, setting, and
the a11y gate carry over unchanged. Awe lives in the craft layer; the
contract layer does not move.

Stack: **Svelte + Tailwind + Vite**, contained entirely to this directory.

---

## Hard boundaries (do not cross)

- **The live dashboard is untouched.** `dashboard/static/index.html` and
  `dashboard/server.py` and everything under `src/stream_manager/` are NOT
  modified by this spike. The spike consumes the existing server API exactly
  as-is.
- **Domain-agnostic (M16).** No monitored-project vocabulary is hard-coded
  anywhere in this UI. Governed-target identity renders from `/api/sessions`
  data only.
- **Self-exclude (M15, M2 polarity).** StreamManager never presents its own
  session as a governed target. See the meta-tag contract below.

---

## MAIN-THREAD ONLY commands (G7)

The following are long-running or environment-mutating and MUST be run by a
human operator from the main thread -- **never** from inside an automated
workflow or a sub-agent:

```sh
# 1. Install dependencies (writes node_modules/, can exceed 5 min).
npm install

# 2. Production build (writes dist/).
npm run build

# 3. Accessibility gate (M17): launches headless Chromium via puppeteer.
npm run axe
```

A workflow/sub-agent that runs any of these is abandoning a long task. Emit
them as an operator gate instead.

---

## Local development

```sh
npm run dev        # Vite dev server on http://127.0.0.1:4317/
```

The dev server proxies the read-only data transports to the live governance
server so the spike renders against real data without touching `server.py`:

| Path     | Proxied to (default)        | Notes                                  |
| -------- | --------------------------- | -------------------------------------- |
| `/api/*` | `http://127.0.0.1:8765`     | stats, decisions, agents, hitl, etc.   |
| `/events`| `http://127.0.0.1:8765`     | SSE; never buffered                    |

Override the live-server origin with `SM_SERVER_ORIGIN` if it is not on the
default bind:

```sh
SM_SERVER_ORIGIN=http://127.0.0.1:9000 npm run dev
```

`/api/commands/stream` is **deliberately not proxied**. It is the
consumer-only command transport, not a dashboard pane -- do not confuse it
with `/events`.

---

## The M17 accessibility gate

`npm run axe` shells out to the repo-level `tools/axe_audit.mjs`
(axe-core + puppeteer, WCAG 2.1 A + AA). It waits for `#frameA`, `#frameB`,
and `#frameC` (the M1 three frames) before analyzing, and **blocks on any
serious/critical violation** (AAA color-contrast-enhanced is excluded).

Because the audit drives a real browser against a served page, run it
against the built bundle:

```sh
npm run build          # produce dist/
npm run preview        # serve dist/ on http://127.0.0.1:4317/ (strict port)
npm run axe            # in a second terminal: audit that running server
```

The port `4317` is fixed and shared by `dev`, `preview`, and the `axe`
script's `--url`. If you move the port, move it in all three
(`vite.config.js` server + preview, and the `axe` script in
`package.json`).

Reports land in the repo's `reports/` directory (`axe-<ts>.json` +
`axe-latest.md`), same as the live dashboard's audit.

---

## The `sm-own-session-id` meta-tag contract (M15)

`index.html` ships this placeholder in `<head>`:

```html
<meta name="sm-own-session-id" content="" />
```

- **Promotion:** the live server (`dashboard/server.py` `root()`) rewrites
  this exact tag, injecting the real id from the `SM_OWN_SESSION_ID` env var
  by replacing `</head>`.
- **Spike (standalone):** the content stays **empty**. Per M15, an
  empty/missing value means *skip self-filtering*, so the spike never
  wrongly hides rows while running on its own.
- The stores unit reads this at DOM-ready and filters that `session_id` out
  of every decision row + mirror (defense-in-depth -- the server already
  strips these rows on the SSE path).

---

## Theming

Three themes -- `obsidian` (default, dark), `phosphor`, `paper` -- are
driven entirely by CSS custom properties keyed off `<html data-theme="...">`.
A single attribute swap re-skins the whole surface. The `paper` theme's
`--text-dim` contrast against its background is a **named, owned measurement
deliverable** in the theme unit and must be documented at/above the
WCAG-AA ratio before any production promotion.

---

## What this unit (u-config) owns

Build/stack scaffold only -- no UI logic, no component imports:

- `package.json` -- deps + scripts (`dev` / `build` / `preview` / `axe`)
- `vite.config.js` -- Vite + Svelte plugin, dev proxy, fixed port 4317
- `svelte.config.js` -- Svelte preprocess + a11y warnings surfaced
- `tailwind.config.js` -- design tokens (theme vars + fixed M4/M17 constants)
- `postcss.config.js` -- Tailwind v3 + autoprefixer pipeline
- `.gitignore` -- excludes `node_modules/` and `dist/`
- `index.html` -- Vite entry shell with the M15 meta placeholder
- this `README.md`

Build artifacts (`node_modules/`, `dist/`) are git-ignored.
