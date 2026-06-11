// dashboard/ui-next/vite.config.js
//
// EXPERIMENTAL spike build config (KingMode UI re-architecture).
// The spike consumes the EXISTING StreamManager server API unchanged
// (see dashboard/server.py). It does NOT bundle or modify the server.
//
// Port 4317 is fixed and shared by `dev`, `preview`, and the M17 axe gate
// (package.json `axe` -> tools/axe_audit.mjs --url http://127.0.0.1:4317/).
// Keep these three in lockstep: if the port moves, move it in all three.
//
// During local development the dev server proxies the read-only data
// transports (/api, /events, /) to the live governance server so the
// spike renders against real data without touching server.py.

import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// Live StreamManager server (dashboard/server.py default bind). Override
// with SM_SERVER_ORIGIN for non-default deployments. Spike-local only --
// the production promotion path serves the built bundle from the server
// itself, so no proxy is involved post-promotion.
const SM_SERVER_ORIGIN = process.env.SM_SERVER_ORIGIN || "http://127.0.0.1:8765";

// SSE endpoints MUST NOT be buffered by the proxy or the live decision
// stream stalls. `/events` is the dashboard transport (decisions + named
// bus events). `/api/commands/stream` is deliberately NOT proxied here --
// it is the consumer-only command transport and is not a dashboard pane.
const proxyCommon = {
  target: SM_SERVER_ORIGIN,
  changeOrigin: true,
};

export default defineConfig({
  plugins: [svelte()],
  // Server-relative API base. The spike's stores call e.g. fetch('/api/stats')
  // and new EventSource('/events'); the proxy below routes them in dev, and
  // same-origin serving routes them post-promotion. No absolute origin is
  // ever hard-coded in UI code.
  base: "./",
  server: {
    host: "127.0.0.1",
    port: 4317,
    strictPort: true,
    proxy: {
      "/api": proxyCommon,
      "/events": {
        ...proxyCommon,
        // Server-Sent Events: never buffer, keep the connection open.
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq) => {
            proxyReq.setHeader("Accept", "text/event-stream");
            proxyReq.setHeader("Cache-Control", "no-cache");
          });
        },
      },
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4317,
    strictPort: true,
  },
  build: {
    // Build artifacts are git-ignored (see .gitignore). Output stays inside
    // the spike dir; promotion copies/serves this, never the reverse.
    outDir: "dist",
    emptyOutDir: true,
    target: "es2022",
    sourcemap: true,
  },
});
