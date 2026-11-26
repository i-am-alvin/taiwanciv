// Font stacks for canvas text; css/style.css defines the same two as --serif and --sans. System fonts only: a web
// font arriving late would leave the cached measureText() widths of banners and labels wrong.
// The Latin faces come first and have no CJK glyphs, so Chinese falls through to a named Traditional Chinese face
// (macOS / iOS: Songti TC, PingFang TC; Windows: Microsoft JhengHei; Android / Linux: Noto). A generic family
// (system-ui, serif) goes last because it brings its own CJK fallback, which can pick Simplified or Japanese glyph shapes.
export const SERIF =
  '"Palatino Linotype", Palatino, "Book Antiqua", Georgia, "Songti TC", "Noto Serif TC", "Noto Serif CJK TC", "Source Han Serif TC", "PingFang TC", "Microsoft JhengHei", serif';
export const SANS =
  '"Helvetica Neue", "Segoe UI", Roboto, "PingFang TC", "Noto Sans TC", "Noto Sans CJK TC", "Microsoft JhengHei", system-ui, sans-serif';
// Small map text (banner names, plaques, tabs): Latin serif capitals as in the original, Chinese in a sans (黑體) face,
// which stays readable at 9-13 px where a 宋體 / 明體 face turns thin and grey.
export const LABEL =
  '"Palatino Linotype", Palatino, "Book Antiqua", Georgia, "PingFang TC", "Noto Sans TC", "Noto Sans CJK TC", "Microsoft JhengHei", sans-serif';

/** True for a string with Chinese (or other CJK) characters: such text takes no uppercase, small caps or Latin tracking. */
export const isCJK = (s) => /[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef]/.test(String(s ?? ""));
