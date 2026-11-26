// Shared building blocks for the city and state panels (both render into #city-panel).
import { compact, dollars, esc, hasCJK, int, money, pct, yieldValue } from "../format.js";
import { icon, glyph } from "./icon.js";

// Industry → a "district" glyph: SVG icons i-<key> from icons.js; these emoji are only the fallback.
export const DISTRICT_ICON = {
  agriculture: "🌾", mining: "⛏️", construction: "🏗️", manufacturing: "🏭", wholesale: "📦", retail: "🛍️",
  transportation: "🚢", utilities: "⚡", information: "📡", finance: "🏦", real_estate: "🏘️", professional: "🔬",
  management: "🏢", admin: "🗂️", education: "🎓", health: "🏥", arts: "🎭", accommodation: "🍽️", other: "🔧",
  public_admin: "🏛️",
};

const panelEl = () => document.getElementById("city-panel");

// What the `gdp` field (and the gold yield, which is the same number) is called: 生產毛額 (Taiwan has no official
// GDP by 縣市; the field is the census's gross value added, see nation.json gdp_vintage and the gold yield's
// description). nation.json may name it itself with an optional `gdp_label`.
export const gdpLabel = (nation) => nation?.gdp_label || "生產毛額";
// The gold yield's full name: its label from nation.json plus what it measures ("金（生產毛額）"), never the same word twice.
export const goldName = (nation, y) => {
  const g = gdpLabel(nation);
  return String(y.label ?? "").includes(g) ? String(y.label) : `${y.label}（${g}）`;
};

// Yield tiles; `ranks` (optional) adds "第 3/22 名" under each (the tile is narrow; its tooltip spells the rank out).
export function yieldGrid(nation, yields, ranks = null, rankOf = 0) {
  return nation.yields
    .map((y) => {
      const v = yields?.[y.key];
      const r = ranks?.[y.key];
      const label = y.key === "gold" ? gdpLabel(nation) : y.label;
      return `<div class="yield-tile" title="${esc(y.key === "gold" ? goldName(nation, y) : y.label)}：${esc(y.description || "")}">
        <div class="ico" style="color:${esc(y.color)}">${glyph(y, 20)}</div>
        <div class="val" style="color:${esc(y.color)}">${yieldValue(y, v)}</div>
        <div class="lbl">${esc(label)}</div>
        ${r ? `<div class="rank" title="在地圖上 ${rankOf} 個縣市中排第 ${r} 名（第 1 名最大）">第 ${r}/${rankOf} 名</div>` : ""}</div>`;
    })
    .join("");
}

// One "value ▲ national value" row. higherIsGood: true / false / null (neutral).
export function statRow(ic, fallback, label, v, nv, fmt, higherIsGood) {
  let cmp = "";
  if (v != null && nv != null && nv !== 0) {
    const ratio = v / nv;
    const cls = Math.abs(ratio - 1) < 0.03 || higherIsGood == null ? "" : (higherIsGood ? ratio >= 1 : ratio <= 1) ? "good" : "bad";
    // Within 3% of the national value reads as level: no arrow, no colour (the colour uses the same band).
    const arrow = Math.abs(ratio - 1) < 0.03 ? "≈" : ratio > 1 ? "▲" : "▼";
    cmp = `<span class="cmp ${cls}">${arrow} 全國 ${fmt(nv)}</span>`;
  }
  return `<div class="stat-row"><span class="sl">${icon(ic, fallback, { size: 14 })}${esc(label)}</span><span><b>${fmt(v)}</b>${cmp}</span></div>`;
}

// A measure the area has no value for gets no row (the Taiwan build has no rent or home-value medians for 縣市), rather
// than a row of "–". Returns "" when nothing is left, so the caller can drop the whole section.
// median_income is the median total income per tax unit on filed income-tax returns, of nation.json `income_year`.
export function amenities(o, n, nation = null) {
  const incomeYear = nation?.income_year ? `（${nation.income_year}）` : "";
  const row = (ic, fallback, label, key, fmt, higherIsGood) =>
    o[key] == null ? "" : statRow(ic, fallback, label, o[key], n?.[key], fmt, higherIsGood);
  return [
    row("unemployment", "😐", "失業率", "unemployment", (x) => pct(x), false),
    row("l-income", "💵", `申報戶所得中位數${incomeYear}`, "median_income", dollars, true),
    row("l-home", "🏠", "房價中位數", "home_value", dollars, null),
    row("l-homeownership", "🔑", "每月租金中位數", "median_rent", dollars, false),
    row(null, "⚖️", "租金 ÷ 所得", "rent_burden", (x) => pct(x), false),
  ].filter(Boolean).join("\n");
}

// Workforce by industry with location quotients vs. the nation ("specialisation"). limit = max rows (0 = all).
export function industries(o, nation, limit = 0) {
  const n = nation.nation;
  const total = o.employed || 1;
  const nTotal = n.employed || 1;
  let rows = Object.entries(o.jobs || {})
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1]);
  if (limit) rows = rows.slice(0, limit);
  if (!rows.length) return `<p class="muted">沒有產業資料。</p>`;
  const maxShare = rows[0][1] / total;
  return rows
    .map(([k, v]) => {
      const share = v / total;
      const nShare = (n.jobs?.[k] || 0) / nTotal;
      const lq = nShare > 0 ? share / nShare : 1;
      const tip = `就業占比是全國占比的 ${lq.toFixed(1)} 倍`;
      const badge = lq >= 1.3 ? `<span class="lq hi" title="${tip}">×${lq.toFixed(1)}</span>`
        : lq <= 0.6 ? `<span class="lq lo" title="${tip}">×${lq.toFixed(1)}</span>` : "";
      return `<div class="ind"><span aria-hidden="true">${icon(`i-${k}`, DISTRICT_ICON[k] || "•")}</span>
        <span>${esc(nation.industries?.[k] || k)}${badge}</span><span class="n">${compact(v)} · ${pct(share, 0)}</span>
        <div class="bar"><i style="width:${(share / maxShare) * 100}%;background:${lq >= 1.3 ? "#9fd76a" : "#c9a45c"}"></i></div></div>`;
    })
    .join("");
}

export const gdpRow = (o, nation = null) =>
  o.gdp != null
    ? `<div class="stat-row"><span class="sl">${icon("y-gold", "💰", { size: 14 })}${esc(gdpLabel(nation))}${o.gdp_year ? `（${esc(o.gdp_year)}）` : ""}</span><span><b>${money(o.gdp)}</b>${
        o.population ? `<span class="cmp">人均 ${money(o.gdp / o.population)}</span>` : ""}</span></div>`
    : "";

// Where the population-change figures come from: the title of sources.json `ris_population` once useSources() has
// seen the file (pedia.js and yieldReport.js pass it on) and when that title is written in Chinese, else the plain
// Chinese name of that source (an English title would read oddly inside a Chinese tooltip).
let growthSource = "戶籍登記年底人口（內政部戶政司）";
export const growthSourceName = () => growthSource;
export function useSources(sources) {
  const s = Array.isArray(sources) ? sources.find((x) => x?.id === "ris_population") : null;
  if (s?.title && hasCJK(s.title)) growthSource = s.title;
}

// " · ▲ 3.4% 自 2021 年" from growth / growth_years (cities and states), compared with the nation in the tooltip.
// Empty when growth is missing (null means "not measured", never zero).
export function growthSpan(o, n = null) {
  if (!Number.isFinite(o?.growth)) return "";
  const yrs = Array.isArray(o.growth_years) && o.growth_years.length === 2 ? o.growth_years : null;
  const p = (g) => `${g >= 0 ? "+" : "−"}${Math.abs(g * 100).toFixed(1)}%`;
  const period = yrs ? `${yrs[0]}–${yrs[1]} 年` : "近幾年";
  const nat = Number.isFinite(n?.growth) ? `（全國 ${p(n.growth)}）` : "";
  const tip = `${period}人口變化：${p(o.growth)}${nat} · ${growthSource}`;
  const cls = o.growth >= 0 ? "good" : "bad";
  return ` · <span class="growth ${cls}" title="${esc(tip)}">${o.growth >= 0 ? "▲" : "▼"} ${Math.abs(o.growth * 100).toFixed(1)}%${
    yrs ? ` <span class="since">自 ${yrs[0]} 年</span>` : ""}</span>`;
}

export const popLine = (o, extra = "") =>
  `<div class="cp-pop">${icon("pop", "👥", { size: 16 })} <b>${int(o.population)}</b> 人${o.employed != null ? ` · 就業 ${int(o.employed)} 人` : ""}${extra}</div>`;

/**
 * Fill and show the panel.
 * spec: {kind: "city"|"state", stripe, title, sub, headExtra, sections: [{title, html}], foot, onClose, onPedia, wire(panel)}
 */
export function showPanel(spec) {
  const panel = panelEl();
  panel.dataset.kind = spec.kind;
  panel.setAttribute("aria-label", `${spec.kind === "state" ? "縣市" : "城市"}：${spec.title}`);
  panel.innerHTML = `
    <div class="sheet-grip" aria-hidden="true"></div>
    <div class="cp-head">
      <div class="stripe" style="background:${spec.stripe}"></div>
      <button class="icon-btn cp-close" aria-label="關閉面板（Esc）" title="關閉（Esc）">${icon("close", "✕", { size: 13 })}</button>
      <div class="cp-kind">${spec.kind === "state" ? "縣市" : "城市"}</div>
      <h2 class="cp-name">${spec.titleHtml ?? esc(spec.title)}</h2>
      ${spec.sub ? `<div class="cp-full">${spec.sub}</div>` : ""}
      ${spec.headExtra || ""}
    </div>
    ${spec.sections.filter(Boolean).map((s) => `<section class="cp-section"><h3>${s.title}</h3>${s.html}</section>`).join("")}
    <div class="cp-foot">${spec.foot || ""} <a href="#" data-pedia>資料年鑑 ›</a></div>`;
  panel.hidden = false;
  panel.scrollTop = 0;
  panel.classList.remove("dragging-sheet");
  panel.style.transform = "";
  document.body.classList.add("panel-open");
  panel.querySelector(".cp-close").onclick = spec.onClose;
  panel.querySelector("[data-pedia]").onclick = (e) => {
    e.preventDefault();
    spec.onPedia?.();
  };
  spec.wire?.(panel);
}

export function hidePanel() {
  const panel = panelEl();
  panel.hidden = true;
  panel.innerHTML = "";
  delete panel.dataset.kind;
  document.body.classList.remove("panel-open");
}

// Bottom-sheet swipe-down to close (mobile). Installed once.
export function installSheetSwipe(onClose) {
  const panel = panelEl();
  let start = null;
  panel.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" || !matchMedia("(max-width: 700px)").matches) return;
    // Only from the grip/head, or anywhere while the sheet is scrolled to the top.
    const fromHead = e.target.closest(".sheet-grip, .cp-head");
    if (!fromHead && panel.scrollTop > 0) return;
    if (e.target.closest("button, a, input")) return;
    start = { y: e.clientY, id: e.pointerId, dy: 0, head: !!fromHead };
  });
  panel.addEventListener("pointermove", (e) => {
    if (!start || e.pointerId !== start.id) return;
    start.dy = Math.max(0, e.clientY - start.y);
    if (start.dy > 6 && (start.head || panel.scrollTop <= 0)) {
      panel.classList.add("dragging-sheet");
      panel.style.transform = `translateY(${start.dy}px)`;
    }
  });
  const end = (e) => {
    if (!start || e.pointerId !== start.id) return;
    const dy = start.dy;
    start = null;
    panel.classList.remove("dragging-sheet");
    panel.style.transform = "";
    if (dy > 80) onClose();
  };
  panel.addEventListener("pointerup", end);
  panel.addEventListener("pointercancel", end);
}
