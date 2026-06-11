// dashboard/ui-next/svelte.config.js
//
// Svelte compiler config for the EXPERIMENTAL KingMode UI spike.
// Plain Svelte (not SvelteKit) -- this is a single-page operator console
// served as a static bundle from the existing governance server.
//
// vitePreprocess gives us PostCSS/Tailwind processing inside <style> blocks
// and lets components opt into TypeScript-style type comments without a
// separate toolchain.

import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

export default {
  preprocess: vitePreprocess(),
  // Surface a11y hints at compile time. The M17 axe gate is the hard gate;
  // these warnings are the cheap first line of defence so accessibility
  // regressions show up during `vite build`, not only at the axe step.
  onwarn: (warning, handler) => {
    // Keep every a11y-* warning visible; never silence them in the spike.
    handler(warning);
  },
};
