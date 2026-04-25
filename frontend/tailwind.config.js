/** @type {import('tailwindcss').Config} */
/**
 * BLUE-ONLY PALETTE (per the client's explicit request: ~15 shades of blue,
 * no orange / teal / amber / green mixed in).
 *
 * Usage guidance:
 *   - Page background:        brand-ice / brand-50
 *   - Card background:        white or brand-50
 *   - Borders / separators:   brand-200
 *   - Body text:              brand-800 / ink
 *   - Headings / titles:      brand-900 / navy
 *   - Primary buttons:        brand-700 (hover brand-800)
 *   - Secondary buttons:      white + brand-300 border
 *   - Links / accents:        brand-600
 *   - Error / destructive:    brand-900 background + white text (dark-contrast only)
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // 10-stop primary scale + 5 semantic aliases = 15 distinct blue shades
        brand: {
          50:  "#f0f6fd",
          100: "#dfeaf7",
          200: "#c0d4ec",
          300: "#9bb8dd",
          400: "#7099ca",
          500: "#4a7ab3",
          600: "#305d9a",
          700: "#1f4583",
          800: "#152f66",
          900: "#0a1a3d",
        },
        // Semantic aliases — still blue, just named for layout intent
        ice:      "#f8fbff",
        frost:    "#e8f0fb",
        mist:     "#a8bfdc",
        steel:    "#4a6487",
        midnight: "#061229",

        // Layout aliases (resolve to the palette above)
        ink:     "#0a1a3d",    // body text (near-black)
        navy:    "#152f66",    // primary headings + sidebar
        muted:   "#4a6487",    // secondary text
        border:  "#c0d4ec",
        surface: "#f8fbff",
        card:    "#ffffff",

        // ── Financial signal accents ─────────────────────────────────
        // The blue-only rule has TWO carved-out exceptions, both authorized
        // by Loay's PPTX/Excel reference for risk and accountant signals.
        //
        // 1. `danger` — used for negative/zero numeric values per the
        //    accountant rule, AND for the "Very Aggressive" Risk Ranking.
        // 2. The `risk-*` palette below mirrors the Excel ranking colors
        //    EXACTLY (slide 91 says "تضليل ألوان المخاطر يجب أن تكون نفس
        //    ما هو مذكور في ملف اكسل").
        // Errors stay blue (bg-brand-900 text-white) — these tokens are
        // strictly for risk-rank badges and negative-number highlights.
        danger:   "#c0392b",
        "danger-bg": "#fde4e2",   // light pink for negative cell background
        risk: {
          conservative:    "#bbf7d0",  // green-200 — Conservative
          conservativeFg:  "#15803d",  // green-700
          moderate:        "#fde68a",  // amber-200 — Moderately Conservative (yellow per Excel)
          moderateFg:      "#92400e",  // amber-800
          aggressive:      "#fecaca",  // red-200 — Aggressive (orange/pink per Excel)
          aggressiveFg:    "#991b1b",  // red-800
          veryAggressive:  "#dc2626",  // red-600 — Very Aggressive (solid red)
          veryAggressiveFg:"#ffffff",  // white text
        },
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "system-ui", "sans-serif"],
        arabic: ["IBM Plex Sans Arabic", "Tajawal", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card:  "0 1px 3px rgba(10, 26, 61, 0.06), 0 1px 2px rgba(10, 26, 61, 0.04)",
        focus: "0 0 0 3px rgba(74, 122, 179, 0.28)",
      },
    },
  },
  plugins: [],
};
