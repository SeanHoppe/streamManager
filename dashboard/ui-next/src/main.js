// main.js -- mount the still-water shell into the page.
//
// Entry point for the EXPERIMENTAL ui-next spike. Mounts App.svelte onto the
// #app root. This file does NOT touch the live dashboard (dashboard/static/
// index.html) or the server -- it is the Vite entry for the contained spike
// build only.
//
// Svelte 4 mount idiom (new App({ target })). If the spike is later moved to
// Svelte 5, swap to `mount(App, { target })`; the rest of the unit is
// version-agnostic Svelte component code.

// Global tokens + base reset from the theme unit (u-theme), imported here in
// strict cascade order (theme tokens -> calm semantic layer -> focus contract)
// so the single entry owns load order; Vite/PostCSS process them via the JS
// import graph. (Repair: the file-disjoint build left these CSS files written
// but UNIMPORTED -- u-theme review BLOCK. Wiring them at the entry is the
// single-owner fix.)
import './styles/theme.css';
import './styles/calm.css';
import './styles/focus.css';

import App from './App.svelte';

function mount() {
  const target = document.getElementById('app');
  if (!target) {
    // Fail loud in dev, never silently render nothing.
    throw new Error('[ui-next] mount target #app not found in document.');
  }
  return new App({ target });
}

const app = mount();

export default app;
