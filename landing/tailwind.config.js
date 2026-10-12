/** @type {import('tailwindcss').Config} */
const token = (name) => `rgb(var(--c-${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Semantic tokens; values live in src/index.css (shared with the chat app's dark theme).
        bg: token("bg"),
        panel: token("panel"),
        surface: token("surface"),
        "surface-2": token("surface-2"),
        line: token("line"),
        "line-soft": token("line-soft"),
        fg: token("fg"),
        soft: token("soft"),
        muted: token("muted"),
        subtle: token("subtle"),
        brand: token("brand"),
        "on-brand": token("on-brand"),
        ok: token("ok"),
        warn: token("warn"),
        bad: token("bad"),
        info: token("info"),
      },
      fontFamily: {
        sans: ["Geist Variable", "Geist", "system-ui", "sans-serif"],
        mono: ["Geist Mono Variable", "Geist Mono", "ui-monospace", "monospace"],
      },
      maxWidth: {
        page: "75rem",
      },
    },
  },
  plugins: [],
};
