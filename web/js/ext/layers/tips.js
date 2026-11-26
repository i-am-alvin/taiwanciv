// Hover tooltips for the map-art layers (HTML strings; every data value is escaped). Each says where the number comes
// from and the caveat that matters for it (trade values are model estimates; the trade arc is a drawing aid; curated
// landmarks are an editorial pick). Sources are quoted from the files themselves (their `vintage`, `rules`, `units`
// and name tables), never hardcoded here.
import { esc, compact, int, pct, money } from "../../format.js";
import { FORT_KINDS, fortKind, WONDER_KINDS } from "../../render/art/sites.js";
import { MODE_STYLE } from "../../render/art/improvements.js";

const muted = (s) => `<span class="muted">${s}</span>`;
const num = (n) => (n == null || !Number.isFinite(n) ? "–" : compact(n));
const sign = (x) => (x > 0 ? "+" : x < 0 ? "−" : "±");
/** A compact number with its unit: "1.2億公噸", "8,500 公噸" (a space only after a digit). */
const qty = (n, unit) => {
  const s = num(n);
  return `${s}${/\d$/.test(s) ? " " : ""}${esc(unit)}`;
};
const has = (v) => v != null && v !== "";

/** The 縣市 name for a state code (ISO codes mean little to readers); the code itself when it is not on the map. */
const stateName = (m, ref) => m?.w?.raw?.states?.find((s) => s.abbr === ref || s.fips === ref)?.name || ref || ""; // abbr (TPE) or COUNTYCODE (63000)
/** "臺北市" once, not "臺北市 · 臺北市", when a site's city and 縣市 are the same place. */
const place = (...parts) => [...new Set(parts.filter(has).map(String))].join(" · ");
/** A file's vintage for one part ("ports"), as a muted source line; "" when the file has none. */
function sourceLine(file, part, extra = "") {
  const v = file?.vintage;
  const text = typeof v === "object" && v ? v[part] : v;
  return [has(text) ? `資料：${esc(text)}。` : "", extra].filter(Boolean).join("");
}

const HUB_NAME = { L: "大型樞紐機場", M: "中型樞紐機場", S: "小型樞紐機場", N: "一般客運機場" };
const PORT_TYPE = { coastal: "海港", great_lakes: "湖港", inland: "內河港" };

export const tips = {
  port(p, m) {
    const inf = m.data.infrastructure;
    const unit = inf?.units?.tons || "公噸";
    const lines = [`<b>${esc(p.name)}</b> ${muted(esc(place(PORT_TYPE[p.type] || (has(p.type) && /[^\x00-\x7f]/.test(p.type) ? p.type : "港口"), stateName(m, p.state))))}`];
    const rank = has(p.rank) ? `貨物吞吐量第 ${esc(p.rank)} 名 · ` : "";
    if (p.tons != null) lines.push(`${rank}<b>${qty(p.tons, unit)}</b>${has(p.year) ? `（${esc(p.year)} 年）` : ""}`);
    if (p.foreign != null || p.domestic != null) lines.push(`國際 ${num(p.foreign)} · 國內 ${num(p.domestic)}`);
    if (p.imports != null || p.exports != null) lines.push(`進口 ${num(p.imports)} · 出口 ${num(p.exports)}`);
    lines.push(muted(sourceLine(inf, "ports", "圖示標在港區中心，狹長的港區僅為概略位置。")));
    return lines.join("<br>");
  },
  airport(a, m) {
    const inf = m.data.infrastructure;
    const title = [a.id, a.name].filter(has).map(esc).join(" · ");
    const lines = [`<b>${title}</b> ${muted(esc(place(a.city, stateName(m, a.state))))}`];
    if (a.hub) lines.push(esc(inf?.hubs?.[a.hub] || HUB_NAME[a.hub] || a.hub));
    else if (a.enplanements == null && a.cargo_lbs != null) lines.push("貨運機場（未列入客運統計）");
    if (a.enplanements != null) {
      let ch = "";
      if (a.enplanements_prev > 0 && Number.isFinite(+a.year)) {
        const r = a.enplanements / a.enplanements_prev - 1;
        ch = `（較 ${a.year - 1} 年 ${sign(r)}${Math.abs(r * 100).toFixed(1)}%）`;
      }
      lines.push(`${has(a.year) ? `${esc(a.year)} 年` : ""}旅客 <b>${qty(a.enplanements, inf?.units?.enplanements || "人次")}</b>${ch}`);
    }
    // The contract's key is cargo_lbs (pounds): the unit shown is the file's own when it states one.
    if (a.cargo_lbs != null) lines.push(`貨運量 ${qty(a.cargo_lbs, inf?.units?.cargo_lbs || inf?.units?.cargo || "磅")}`);
    const src = sourceLine(inf, "airports");
    if (src) lines.push(muted(src));
    return lines.join("<br>");
  },
  fort(f, m) {
    const mil = m.data.military;
    const comp = mil?.components?.find((c) => c.id === f.component);
    const name = comp?.name || FORT_KINDS[fortKind(f.component)]?.name || "軍事設施";
    const tier = { major: "主要基地", base: "基地", site: "據點" }[f.tier] || "";
    const status = { act: "", semi: " · 部分使用", care: " · 維管狀態" }[f.status] ?? "";
    const lines = [
      `<b>${esc(f.name)}</b> ${muted(esc(stateName(m, f.state)))}`,
      `${esc(name)}${f.joint ? " · 聯合基地" : ""}${tier ? ` · ${esc(tier)}` : ""}${esc(status)}`,
    ];
    if (f.area_km2 != null) lines.push(`範圍 ${int(f.area_km2)} km²`);
    lines.push(muted(sourceLine(mil, "installations", "圖示大小依範圍面積，不代表駐軍人數。")));
    return lines.join("<br>");
  },
  range(r, m) {
    const mil = m.data.military;
    const comp = mil?.components?.find((c) => c.id === r.component);
    return [
      `<b>${esc(r.name)}</b> ${muted(esc(stateName(m, r.state)))}`,
      ["管制區", comp?.name, r.area_km2 != null ? `${int(r.area_km2)} km²` : ""].filter(has).map(esc).join(" · "),
      muted(mil?.rules?.ranges ? esc(mil.rules.ranges) : "畫在其範圍涵蓋的六角格上。"),
    ].join("<br>");
  },
  wonder(x, m) {
    const k = WONDER_KINDS[x.kind]?.name || "奇觀";
    const rule = m.data.wonders?.rules?.find((r) => r.id === x.rule);
    const mt = x.metrics || {};
    const year = (y) => (has(y) ? `（${esc(y)} 年）` : "");
    const lines = [`<b>${esc(x.name)}</b> ${muted(esc(stateName(m, x.state)))}`];
    if (x.kind === "university") {
      lines.push(`${esc(k)}${has(x.rank) ? ` · 計畫經費第 ${esc(x.rank)} 名` : ""}`);
      if (mt.rd_usd != null) lines.push(`計畫經費 ${money(mt.rd_usd)}${year(mt.year)}${mt.federal_usd != null && mt.rd_usd > 0 ? `，其中 ${pct(mt.federal_usd / mt.rd_usd, 0)} 來自政府部門` : ""}`);
      if (mt.enrollment != null) lines.push(`學生 ${int(mt.enrollment)} 人${year(mt.enrollment_year)}`);
    } else if (x.curated) {
      lines.push(`${esc(k)} · 人工精選（非依數據排名）`);
      if (mt.visits != null) lines.push(`${qty(mt.visits, "人次")}造訪${year(mt.year)}`);
      if (mt.designated) lines.push(`${esc(mt.designated)} 年指定`);
    } else {
      lines.push(`${esc(k)}${has(x.rank) ? ` · 造訪人次第 ${esc(x.rank)} 名` : ""}${mt.unit_type ? `（${esc(mt.unit_type)}）` : ""}`);
      if (mt.visits != null) lines.push(`<b>${qty(mt.visits, "人次")}</b>造訪${year(mt.year)}${mt.visits_of ? ` ${muted(`（${esc(mt.visits_of)}）`)}` : ""}`);
      if (mt.area_km2 != null) lines.push(`${int(mt.area_km2)} km²`);
    }
    if (rule?.text) lines.push(muted(esc(rule.text)));
    return lines.join("<br>");
  },
  route(rt, m) {
    const r = rt.route;
    const t = m.data.trade || {};
    const a = rt.a?.short || rt.a?.name || r.a, b = rt.b?.short || rt.b?.name || r.b;
    const modeName = (k) => t.modes?.find?.((x) => x.id === k)?.name || MODE_STYLE[k]?.label || k;
    const modes = Object.entries(r.modes || {}).filter(([, v]) => v >= 0.05).sort((p, q) => q[1] - p[1])
      .map(([k, v]) => `${esc(modeName(k))} ${Math.round(v * 100)}%`).join(" · ");
    const com = t.commodities?.[r.top_commodity];
    const when = t.vintage || t.year;
    const lines = [
      `<b>${esc(a)} ⇄ ${esc(b)}</b> ${muted(has(r.rank) ? `貿易路線第 ${esc(r.rank)} 名` : "貿易路線")}`,
      // Money when the file has it, with the weight after it; weight alone when it has no money.
      `每年貨運 ${r.value_musd != null ? `<b>${money(r.value_musd * 1e6)}</b>${r.tons_k != null ? `，${qty(r.tons_k * 1e3, "公噸")}` : ""}` : r.tons_k != null ? `<b>${qty(r.tons_k * 1e3, "公噸")}</b>` : "<b>–</b>"}（${has(when) ? `${esc(when)}，` : ""}估計值）`,
    ];
    if (modes) lines.push(modes);
    if (com) lines.push(`主要貨品：${esc(com)}`);
    lines.push(muted(t.path_note ? esc(t.path_note) : "雙向合計。弧線連接兩區最大的城市，僅為示意：資料只記錄貨物的起點與終點，不含實際路徑。"));
    return lines.join("<br>");
  },
};
