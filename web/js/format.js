// Number formatting, Taiwan style: Chinese large-number units (萬 = 1e4, 億 = 1e8, 兆 = 1e12), zh-TW digit grouping,
// and New Taiwan dollars. Yield / field units that say "usd" in the data contracts are TWD here (docs/PORTING.md).
const UNITS = [[1e12, "兆"], [1e8, "億"], [1e4, "萬"]];
const LOCALE = "zh-TW";

export const CURRENCY = "NT$";
export const hasCJK = (s) => /[\u3400-\u9fff\uf900-\ufaff]/.test(String(s ?? ""));

/** |n| in the unit at UNITS[i]: 2 decimals under 10 兆, 1 decimal under 100 萬 / 億, none above; ".0" is dropped. */
function inUnit(a, i) {
  const q = a / UNITS[i][0];
  const d = i === 0 ? (q >= 10 ? 1 : 2) : q >= 100 ? 0 : 1;
  return q.toFixed(d).replace(/\.0+$/, "");
}

export function compact(n) {
  if (n == null || Number.isNaN(n)) return "–";
  const a = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  let i = UNITS.findIndex(([d]) => a >= d);
  if (i < 0) {
    if (Math.round(a) < 1e4) return Math.round(n).toLocaleString(LOCALE);
    i = UNITS.length - 1; // 9,999.6 rounds up into 萬
  }
  let s = inUnit(a, i);
  if (i > 0 && Number(s) >= 1e4) s = inUnit(a, --i); // 9999.6萬 reads 1億, never 10000萬
  return sign + s + UNITS[i][1];
}

export const money = (n) => (n == null || Number.isNaN(n) ? "–" : (n < 0 ? "-" : "") + CURRENCY + compact(Math.abs(n)));
export const dollars = (n) =>
  n == null || Number.isNaN(n) ? "–" : (n < 0 ? "-" : "") + CURRENCY + Math.round(Math.abs(n)).toLocaleString(LOCALE);
export const int = (n) => (n == null ? "–" : Math.round(n).toLocaleString(LOCALE));
export const pct = (x, d = 1) => (x == null ? "–" : (x * 100).toFixed(d) + "%");

export function yieldValue(y, v) {
  return y.unit === "usd" ? money(v) : compact(v);
}

/** Population on a banner: 2340萬, 12.3萬, 8,500. */
export const popShort = (n) => compact(n);

export const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
