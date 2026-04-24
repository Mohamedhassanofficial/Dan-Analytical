/** Formatters shared across charts and tables. */

export const fmtPct = (x: number, digits = 2): string =>
  `${(x * 100).toFixed(digits)}%`;

export const fmtNum = (x: number, digits = 3): string => x.toFixed(digits);

export function fmtDateTime(iso: string, locale: string): string {
  try {
    return new Intl.DateTimeFormat(locale === "ar" ? "ar-SA" : "en-GB", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

/**
 * Chart palette — blue-only per the spec. 10 shades ordered from darkest
 * to lightest so segments are distinguishable by brightness alone. No
 * teal / amber / orange / green / red accents anywhere.
 */
export const chartPalette = [
  "#0a1a3d", // brand-900 (navy)
  "#152f66", // brand-800
  "#1f4583", // brand-700
  "#305d9a", // brand-600
  "#4a7ab3", // brand-500
  "#7099ca", // brand-400
  "#9bb8dd", // brand-300
  "#c0d4ec", // brand-200
  "#4a6487", // steel
  "#a8bfdc", // mist
];

export const colorFor = (i: number): string =>
  chartPalette[i % chartPalette.length];
