// dashboard/ui-next/tailwind.config.js
//
// Tailwind theme tokens for the KingMode UI spike.
//
// THEME CONTRACT (preserved from the live dashboard): the three themes
// (obsidian / phosphor / paper) are driven by CSS custom properties keyed
// off <html data-theme="...">. Tailwind colors therefore resolve to
// `var(--token)` rather than literal hex, so a single `data-theme` swap
// re-skins the whole surface with no class churn. The CSS vars themselves
// live in the theme unit (u-theme), NOT here -- this file only NAMES the
// tokens and the fixed badge/signal constants that are theme-invariant.
//
// M4 (paired label+color badges) and M17 (focus ring) constants are FIXED
// hex, not theme vars: the amber ACTION-REQUIRED signal and the 2px amber
// focus ring are governance-critical and must read identically in every
// theme. Color is never the only signal (paired text label is mandatory),
// but where color IS used it must be deterministic.

/** @type {import('tailwindcss').Config} */
export default {
  // Component units add their own .svelte files under src/. Scan the entry
  // shell and the whole src tree so utility classes survive purge.
  content: ["./index.html", "./src/**/*.{svelte,js,ts,html}"],
  // data-theme drives theming, not Tailwind's class/media dark mode.
  darkMode: ["selector", '[data-theme="obsidian"]'],
  theme: {
    extend: {
      colors: {
        // -- Surface tokens (resolved per-theme via CSS custom properties) --
        bg: "var(--bg)",
        "bg-card": "var(--bg-card)",
        "bg-row": "var(--bg-row)",
        "bg-row-alt": "var(--bg-row-alt)",
        "bg-row-hover": "var(--bg-row-hover)",
        "bg-row-flash": "var(--bg-row-flash)",
        border: "var(--border)",
        text: "var(--text)",
        "text-dim": "var(--text-dim)",
        "text-mute": "var(--text-mute)",
        accent: "var(--accent)",

        // -- M4 fixed badge constants (theme-invariant governance signals) --
        // ACTION REQUIRED = amber on cream with a pulsing amber border.
        "badge-action": "#d97706",
        "badge-action-bg": "#fef3c7",
        // OBSERVING = slate, no border.
        "badge-observing": "#64748b",
        // Severity family for label+color pairs (text label ALWAYS present).
        "sig-blocked": "#b91c1c",
        "sig-warn": "#b45309",
        "sig-timeout": "#6b7280",
        "sig-decided": "#475569",

        // -- M17 focus ring (2px solid #d97706 + 2px offset everywhere) --
        focus: "#d97706",
      },
      borderColor: {
        // M4: ACTION REQUIRED carries a 2px solid amber border.
        "badge-action": "#d97706",
      },
      ringColor: {
        focus: "#d97706",
      },
      ringWidth: {
        // M17 focus ring is exactly 2px.
        focus: "2px",
      },
      ringOffsetWidth: {
        focus: "2px",
      },
      fontFamily: {
        // System-font stacks (mirrors live NFR-UI-3): no web-font FOIT,
        // calm/legible at rest. Mono for hashes, REPL lines, JSON dumps.
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "SF Mono",
          "Consolas",
          "Liberation Mono",
          "Menlo",
          "monospace",
        ],
      },
      // monitor-first-elevated graft: variable-weight typographic severity
      // scale -- signal severity is encoded as TYPE EMPHASIS, not chrome.
      // Component units consume these named weights instead of raw numbers.
      fontWeight: {
        calm: "400",
        notice: "500",
        signal: "600",
        urgent: "700",
      },
      keyframes: {
        // M4: ACTION REQUIRED 2px amber border pulses to draw the eye.
        // Reserved for the lone true M2 escalation surfaces -- calm at rest.
        "action-pulse": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(217,119,6,0.55)" },
          "50%": { boxShadow: "0 0 0 3px rgba(217,119,6,0.0)" },
        },
        // M9: subtle 1s countdown tick affordance.
        "tick-fade": {
          "0%": { opacity: "0.85" },
          "100%": { opacity: "1" },
        },
      },
      animation: {
        // prefers-reduced-motion / the FR-UI-9 reduced-motion setting must be
        // able to disable these (handled in the theme/settings units via a
        // [data-reduced-motion] gate). The animation token only NAMES them.
        "action-pulse": "action-pulse 1.6s ease-in-out infinite",
        "tick-fade": "tick-fade 1s linear",
      },
    },
  },
  plugins: [],
};
