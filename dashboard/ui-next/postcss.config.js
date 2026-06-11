// dashboard/ui-next/postcss.config.js
//
// PostCSS pipeline for the KingMode UI spike: Tailwind v3 + autoprefixer.
// Tailwind v3 ships its own PostCSS plugin under the `tailwindcss` package
// (do NOT swap in @tailwindcss/postcss -- that is the v4 plugin and would
// mismatch the v3 pin in package.json).

export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
