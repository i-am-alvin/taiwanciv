// The city screen: a docked dashboard (a bottom sheet on phones) with the header (and its city-type badge),
// Citizens (figure rows from citizens.json), Districts (districts.json), Economy, Workforce, Resources and Compare.
// Plain HTML strings + inline SVG charts; render(el, model, handlers) fills `el`. The citizens and districts files
// load on demand (h.loadData) and fill their sections when they arrive; a build without districts.json drops that
// section and its tab. On the Taiwan map a city is a 縣市 and its members are 鄉鎮市區 (docs/PORTING.md).
import { dollars, esc, int, pct } from "../../format.js";
import { compact, money, popShort, yieldValue } from "./fmt.js";
import { icon, glyph } from "../../ui/icon.js";
import { css } from "../../color.js";
import { isCapital } from "../../world.js";
import { sparkline, meter, bar } from "./charts.js";
import { popSeries, rankCount, resourceValue, LAND } from "./model.js";
import { citizensHtml, mountCitizens } from "./citizens.js";
import { badgeHtml, cityDistricts, districtsHtml } from "./districts.js";

const TABS = [
  ["citizens", "市民", "pop"],
  ["districts", "特色區域", "l-developed"],
  ["economy", "經濟", "y-gold"],
  ["workforce", "就業", "y-production"],
  ["resources", "資源", "resources"],
  ["compare", "比較", "layers"],
];

const signed = (g, d = 1) => (g == null ? "–" : `${g >= 0 ? "+" : "−"}${Math.abs(g * 100).toFixed(d)}%`);
const rankCache = new WeakMap();
function countOf(cities, key) {
  let m = rankCache.get(cities);
  if (!m) rankCache.set(cities, (m = new Map()));
  if (!m.has(key)) m.set(key, rankCount(cities, key));
  return m.get(key);
}

// Medal colours scale with the number of ranked cities: about the top 1% gold and the top 5% silver on a map with
// hundreds of cities, and never fewer than the top 3 / top 10 (the 22 縣市).
function rankBadge(rank, of, label, tip) {
  if (rank == null) return "";
  const tier = rank <= Math.max(3, Math.round(of / 90)) ? "gold" : rank <= Math.max(10, Math.round(of / 18)) ? "silver" : "bronze";
  return `<div class="cv-rank ${tier}" title="${esc(tip || `${label}：第 ${rank} 名（共 ${of} 個城市，第 1 名最高）`)}">
    <span class="cv-medal">${rank}</span><span class="cv-rank-l">${esc(label)}</span></div>`;
}

function lqBadge(lq) {
  if (lq == null) return "";
  const tip = `區位商數：此占比為全國占比的 ${lq.toFixed(2)} 倍`;
  const cls = lq >= 1.25 ? "hi" : lq <= 0.75 ? "lo" : "mid";
  return `<span class="cv-lq ${cls}" title="${esc(tip)}">×${lq.toFixed(1)}</span>`;
}

function medallion(id, fallback, bg, size = 18) {
  return `<span class="cv-med" style="--bg:${esc(bg)}">${icon(id, fallback, { size })}</span>`;
}

// The "gdp" field is the 生產毛額 (gross value added) the data's gdp_vintage names; Taiwan publishes no official
// GDP by 縣市, so the screen never calls it GDP.
const GDP = "生產毛額";
const GDP_PC = "人均生產毛額";
/** True when sources.json (a list, or {sources: [...]}) has an entry with this id. */
function hasSource(sources, id) {
  const list = Array.isArray(sources) ? sources : Array.isArray(sources?.sources) ? sources.sources : [];
  return list.some((x) => x?.id === id);
}

const sameText = (a, b) => String(a ?? "").trim().replace(/台/g, "臺") === String(b ?? "").trim().replace(/台/g, "臺");
const fmtArea = (a) => (a == null ? "–" : a >= 100 ? compact(a) : a.toFixed(1));
const gw = (mw) => (mw >= 1000 ? `${(mw / 1000).toFixed(1)} GW` : `${Math.round(mw)} MW`);

// --- header --------------------------------------------------------------------------------------------------------
function header(m) {
  const c = m.city, n = m.nation.nation;
  const cities = m.cityList;
  const col = css(m.stateRGB);
  // The chip opens the 縣市 panel. A city that is its own 縣市 gets a plain "縣市資料" chip (its name is already the
  // title); another 縣市 is named in full (three-letter ISO codes mean little to readers).
  const chips = m.states.map((s) => {
    const label = s.self ? "縣市資料" : s.name;
    return s.index >= 0
      ? `<button class="chip" data-state="${s.index}" title="${esc(`開啟縣市面板：${s.name}`)}">${esc(label)}</button>`
      : s.self ? "" : `<span class="chip">${esc(label)}</span>`;
  }).join("");
  const g = Number.isFinite(c.growth) ? c.growth : null;
  const yrs = Array.isArray(c.growth_years) ? c.growth_years : null;
  const growth = g == null ? "" : `<span class="cv-growth ${g >= 0 ? "good" : "bad"}" title="${yrs ? `${yrs[0]}–${yrs[1]} 年` : ""}人口變化（年底戶籍登記人口）${n.growth != null ? `；全國 ${signed(n.growth)}` : ""}">${g >= 0 ? "▲" : "▼"} ${Math.abs(g * 100).toFixed(1)}%${yrs ? ` <small>自 ${yrs[0]} 年</small>` : ""}</span>`;
  const perCap = c.gdp != null && c.population ? c.gdp / c.population : null;
  const r = c.ranks || {};
  const N = (k) => countOf(cities, k);
  // The line under the title: only what `full` adds to the name (臺北市 Taipei City → Taipei City), never the name twice.
  const fullRaw = c.full && !sameText(c.full, c.name) ? String(c.full) : "";
  const full = fullRaw.startsWith(String(c.name)) ? fullRaw.slice(String(c.name).length).trim() : fullRaw;
  return `
  <div class="sheet-grip cv-grip" aria-hidden="true"></div>
  <header class="cv-head" style="--sc:${col}">
    <div class="cv-ribbon" aria-hidden="true"></div>
    <button class="icon-btn cv-close" data-close aria-label="關閉城市檢視 (Esc)" title="返回地圖 (Esc)">${icon("close", "✕", { size: 13 })}</button>
    <div class="cv-kind">城市檢視</div>
    <div class="cv-title">
      <div class="cv-crest" aria-hidden="true"><span>${esc(popShort(c.population))}</span></div>
      <div class="cv-tt">
        <h2 class="cv-name" tabindex="-1">${isCapital(c) ? `<span class="cv-cap" title="中央政府所在地">★</span> ` : ""}${esc(c.name)}</h2>
        ${full ? `<div class="cv-full">${esc(full)}</div>` : ""}
        <div class="cv-typeslot" data-ctype></div>
        ${chips ? `<div class="chips">${chips}</div>` : ""}
      </div>
    </div>
    <div class="cv-headline">
      <div class="cv-big"><span class="lbl">${icon("pop", "👥", { size: 13 })} 人口</span><b>${int(c.population)}</b>${growth}</div>
      <div class="cv-big"><span class="lbl">${icon("y-gold", "💰", { size: 13 })} ${GDP}${c.gdp_year ? `（${c.gdp_year}）` : ""}</span><b>${money(c.gdp)}</b>${
        perCap != null ? `<span class="cv-sub">人均 ${money(perCap)}</span>` : ""}</div>
    </div>
    <div class="cv-ranks" aria-label="在 ${cities.length} 個城市中的排名">
      ${rankBadge(r.population, N("population"), "人口")}
      ${rankBadge(r.gdp, N("gdp"), GDP)}
      ${rankBadge(r.gdp_per_capita, N("gdp_per_capita"), GDP_PC)}
      ${rankBadge(r.growth, N("growth"), "人口成長", r.growth != null ? `人口成長：第 ${r.growth} 名（共 ${N("growth")} 個城市，第 1 名成長最快）` : "")}
    </div>
  </header>
  <nav class="cv-tabs" aria-label="城市檢視分頁">
    ${TABS.map(([id, label, ic]) => `<button type="button" data-tab="${id}">${icon(ic, "•", { size: 14 })}<span>${label}</span></button>`).join("")}
  </nav>`;
}

// --- citizens ------------------------------------------------------------------------------------------------------
function citizens(m) {
  const c = m.city, n = m.nation.nation;
  const series = popSeries(c);
  const ch = series.length >= 2 ? series.at(-1).value / series[0].value - 1 : null;
  // sub: the small line beside the value; by default the national value, left out when there is none. A measure
  // the city has no value for (the build does not carry it, or not for this city) gets no row at all.
  const row = (ic, fb, label, v, us, fmt, better, max, sub = us != null ? `全國 ${fmt(us)}` : "", tick = us) => (v == null ? "" : `
    <div class="cv-stat">
      <div class="cv-stat-top"><span class="sl">${icon(ic, fb, { size: 14 })}${esc(label)}</span>
        <span class="sv"><b>${v == null ? "–" : fmt(v)}</b>${sub ? `<small>${sub}</small>` : ""}</span></div>
      ${meter(v, tick, max ?? Math.max(v || 0, us || 0) * 1.35, better)}
    </div>`);
  // Employed residents: no national figure to set beside a count, so the share of residents (and the national share).
  const empShare = c.employed != null && c.population > 0 ? c.employed / c.population : null;
  const usEmpShare = n.employed != null && n.population > 0 ? n.employed / n.population : null;
  const empSub = empShare == null ? ""
    : `占居民 ${pct(empShare)}${usEmpShare != null ? ` · 全國 ${pct(usEmpShare)}` : ""}`;
  const multi = m.tiles.length > 1;
  // Residents per hex need the population-density lens; without it the hexes show their land use only.
  const hasRes = m.tiles.some((t) => t.residents != null);
  const tilesNote = !multi ? `本城市位於單一六角格內（約 ${fmtArea(m.hexArea)} km²），與城市圖示一併顯示。`
    : hasRes ? `地圖上，本城市的每個六角格顯示<b>≈ 居民數</b>（鄉鎮市區人口密度 × 六角格面積，為估計值）與<b>主要土地利用</b>（占該格土地的比例）${
      m.residentsSum > 0 ? `。依此估計，${m.tiles.length} 個六角格合計約 ${compact(m.residentsSum)} 人` : ""}。`
      : `地圖上，本城市的每個六角格顯示其<b>主要土地利用</b>（占該格土地的比例）。`;
  return `
  <section class="cv-sec" id="cv-citizens" data-sec="citizens" aria-labelledby="cv-h-citizens">
    <h3 id="cv-h-citizens">${icon("pop", "👥", { size: 15 })}市民</h3>
    <div class="cv-citizens" data-citizens>${citizensHtml(m, undefined)}</div>
    <h4 class="cv-h4">人口</h4>
    <div class="cv-card">
      <div class="cv-card-h"><span>人口 ${series.length ? `${series[0].year}–${series.at(-1).year}` : ""}</span>${
        ch != null ? `<span class="${ch >= 0 ? "good" : "bad"}">${signed(ch)}</span>` : ""}</div>
      ${sparkline(series, { fmt: (v) => popShort(v), title: `${c.name}歷年人口` })}
      ${series.length >= 2 ? `<p class="cv-note">各年為年底戶籍登記人口${
        hasSource(m.sources, "ris_population") ? "（內政部戶政司）" : ""}，各年以相同的鄉鎮市區範圍統計。</p>` : ""}
    </div>
    <div class="cv-stats">
      ${row("pop", "👥", "就業人口", c.employed, null, int, null, c.population, empSub, usEmpShare != null ? usEmpShare * c.population : null)}
      ${row("unemployment", "😐", "失業率", c.unemployment, n.unemployment, (x) => pct(x), "low")}
      ${row("l-income", "💵", `申報戶所得中位數${m.nation.income_year ? `（${m.nation.income_year} 年度）` : ""}`, c.median_income, n.median_income, dollars, "high")}
      ${row("l-homeownership", "🔑", "月租金中位數", c.median_rent, n.median_rent, dollars, null)}
      ${row("l-home", "🏠", "房價中位數", c.home_value, n.home_value, dollars, null)}
      ${row(null, "⚖️", "租金負擔（租金 ÷ 所得）", c.rent_burden, n.rent_burden, (x) => pct(x), "low")}
    </div>
    <div class="cv-legend-tiles">${tileLegend(m)}<p>${tilesNote}</p></div>
    <h4 class="cv-h4">轄下鄉鎮市區 <span class="muted">(${(c.counties || []).length})</span></h4>
    <div class="cv-counties" data-counties><p class="muted cv-note">鄉鎮市區資料載入中…</p></div>
  </section>`;
}

function tileLegend(m) {
  const counts = new Map();
  for (const t of m.tiles) if (t.land) counts.set(t.land.key, (counts.get(t.land.key) || 0) + 1);
  return `<div class="cv-tl">${LAND.filter((g) => counts.has(g.key)).map((g) =>
    `<span class="cv-tl-i"><i style="background:${esc(m.landColor(g.key))}"></i>${esc(g.label)} <small>${counts.get(g.key)}</small></span>`).join("")}</div>`;
}

const COUNTY_ROWS = 12; // rows of the member table shown before "另有 N 個"

/**
 * A value of a counties.json column, formatted by the column's own field metadata (`format`), compactly: the member
 * table's columns are narrow, so money drops its NT$ prefix (the header carries it) and large counts use 萬 / 億.
 */
function fieldCell(f, v) {
  if (v == null || (typeof v === "number" && !Number.isFinite(v))) return "–";
  if (typeof v !== "number") return esc(v);
  switch (f?.format) {
    case "pct": return pct(v);
    case "usd": return compact(v);
    case "years": return v.toFixed(1);
    case "float": return Math.abs(v) >= 100 ? int(v) : v.toFixed(1);
    default: return Math.abs(v) >= 1e5 ? compact(v) : int(v);
  }
}

export function countiesTable(m, data) {
  const c = m.city;
  if (!data || !Array.isArray(data.rows)) return `<p class="muted cv-note">無鄉鎮市區資料。</p>`;
  const col = Object.fromEntries(data.columns.map((k, j) => [k, j]));
  const want = new Set(c.counties || []);
  const rows = data.rows.filter((r) => want.has(r[col.geoid])).sort((a, b) => (b[col.population] || 0) - (a[col.population] || 0));
  if (!rows.length) return `<p class="muted cv-note">本城市沒有鄉鎮市區資料。</p>`;
  const maxPop = rows[0][col.population] || 1;
  const show = rows.slice(0, COUNTY_ROWS);
  const vint = data.vintage ? `（${esc(data.vintage)}）` : "";
  // A member's 縣市 is named only when it is not the city itself (never on the Taiwan map, where they are one unit).
  const other = (r) => (col.state == null ? "" : m.otherStates?.(c, [r[col.state]])[0] || "");
  // Labels, units and formats of the three value columns come from the file's own field metadata (data.fields), so
  // a column says what the build put in it; the Chinese names here stand in only when a field has no label.
  const field = (k) => (data.fields || []).find((f) => f.key === k) || null;
  const COLS = [["population", "人口"], ["density", "人口密度"], ["income", "所得"]].map(([k, fb]) => ({ k, f: field(k), fb }));
  const head = ({ f, fb }) => `<span role="columnheader" title="${esc([f?.unit, f?.description].filter(Boolean).join("："))}">${
    esc(f?.label || fb)}${f?.format === "usd" ? " NT$" : ""}</span>`;
  const cell = ({ k, f }, r) => {
    const v = col[k] == null ? null : r[col[k]];
    const full = v != null && f?.format === "usd" ? dollars(v) : "";
    return `<span role="cell"${full ? ` title="${esc(full)}"` : ""}>${fieldCell(f, v)}</span>`;
  };
  return `<div class="cv-ctable" role="table" aria-label="轄下鄉鎮市區">
    <div class="cv-cr cv-cr-h" role="row"><span role="columnheader">${esc(field("name")?.label || "鄉鎮市區")}</span>${COLS.map(head).join("")}</div>
    ${show.map((r) => `<div class="cv-cr" role="row">
      <span role="cell" class="cv-cn">${esc(r[col.name])}${other(r) ? ` <small>${esc(other(r))}</small>` : ""}${bar(r[col.population] / maxPop, "var(--sc, #c9a45c)")}</span>
      ${COLS.map((c2) => cell(c2, r)).join("")}</div>`).join("")}
    ${rows.length > show.length ? `<p class="muted cv-note">另有 ${rows.length - show.length} 個鄉鎮市區。</p>` : ""}
    <p class="cv-note">鄉鎮市區統計${vint}。</p>
  </div>`;
}

// --- districts -----------------------------------------------------------------------------------------------------
function districts(m) {
  return `
  <section class="cv-sec" id="cv-districts" data-sec="districts" aria-labelledby="cv-h-districts">
    <h3 id="cv-h-districts">${icon("l-developed", "🏙", { size: 15 })}特色區域</h3>
    <div data-districts>${districtsHtml(m, undefined, null)}</div>
  </section>`;
}

// --- economy -------------------------------------------------------------------------------------------------------
function economy(m) {
  const c = m.city, nat = m.nation, n = nat.nation;
  const r = c.ranks || {};
  const cities = m.cityList;
  const perCap = c.gdp != null && c.population ? c.gdp / c.population : null;
  const usPerCap = n.gdp && n.population ? n.gdp / n.population : null;
  const yields = nat.yields.map((y) => {
    const v = c.yields?.[y.key];
    const rk = r[y.key];
    // The gold yield is labelled 生產毛額 when it is the city's gdp figure itself; otherwise it keeps the data's label.
    const lbl = y.key === "gold" && c.gdp != null && v === c.gdp ? GDP : y.label;
    return `<div class="cv-yield" style="--yc:${esc(y.color)}" title="${esc(y.label)}：${esc(y.description || "")}">
      <div class="ico">${glyph(y, 20)}</div><div class="val">${yieldValue(y, v)}</div>
      <div class="lbl">${esc(lbl)}</div>
      ${rk != null ? `<div class="rk" title="第 ${rk} 名（共 ${countOf(cities, y.key)} 個城市）">第 ${rk} 名 <small>／${countOf(cities, y.key)}</small></div>` : ""}</div>`;
  }).join("");
  const gi = m.gdpInds;
  const maxShare = gi.length ? Math.max(...gi.map((d) => Math.max(d.share, d.natShare))) : 1;
  const gdpRow = (d) => d.undisclosed
    ? `<div class="cv-ind und" title="部分產業的數值未公開：${esc(d.missing.map((k) => nat.industries?.[k] || k).join("、") || "數個產業")}。此列為本城市${GDP}減去所有已公開產業後的餘額。">
      <span class="cv-ind-ic" style="--bg:${esc(d.color)}">${icon(d.icon, "?", { size: 13 })}</span>
      <span class="cv-ind-n">${esc(d.short)}</span>
      <span class="cv-ind-v">${money(d.value)} <small>${pct(d.share, 0)}</small></span>
      ${bar(d.share / maxShare, "#7c8494", 0)}
    </div>`
    : `<div class="cv-ind" title="${esc(d.label)}：${money(d.value)}（占本城市${GDP} ${pct(d.share)}；全國 ${pct(d.natShare)}）${d.estimated ? "。含未公開數值的估計。" : ""}">
      <span class="cv-ind-ic" style="--bg:${esc(d.color)}">${icon(d.icon, "•", { size: 13 })}</span>
      <span class="cv-ind-n">${esc(d.short)}${lqBadge(d.lq)}</span>
      <span class="cv-ind-v">${d.estimated ? "≈" : ""}${money(d.value)} <small>${pct(d.share, 0)}</small></span>
      ${bar(d.share / maxShare, d.lq != null && d.lq >= 1.25 ? "#9fd76a" : "#c9a45c", d.natShare / maxShare)}
    </div>`;
  return `
  <section class="cv-sec" id="cv-economy" data-sec="economy" aria-labelledby="cv-h-economy">
    <h3 id="cv-h-economy">${icon("y-gold", "💰", { size: 15 })}經濟</h3>
    <div class="cv-gdp">
      <div><span class="lbl">${GDP}${c.gdp_year ? `（${c.gdp_year}）` : ""}</span><b>${money(c.gdp)}</b>${r.gdp != null ? `<small>第 ${r.gdp} 名／${countOf(cities, "gdp")}</small>` : ""}</div>
      <div><span class="lbl">${GDP_PC}</span><b>${money(perCap)}</b>${
        usPerCap && perCap != null ? `<small class="${perCap >= usPerCap ? "good" : "bad"}">全國 ${money(usPerCap)}</small>` : ""}</div>
      <div><span class="lbl">占全國${GDP}</span><b>${c.gdp != null && n.gdp ? pct(c.gdp / n.gdp, 2) : "–"}</b>${
        c.population && n.population ? `<small>人口占 ${pct(c.population / n.population, 2)}</small>` : ""}</div>
    </div>
    <h4 class="cv-h4">產出 <span class="muted">城市間排名</span></h4>
    <div class="cv-yields">${yields}</div>
    ${gi.length ? `<h4 class="cv-h4">各產業${GDP} <span class="muted">刻度 = 全國占比</span></h4>
      <div class="cv-inds">${gi.slice(0, 8).map(gdpRow).join("")}</div>
      ${gi.length > 8 ? `<details class="cv-more"><summary>全部 ${gi.length} 個產業</summary><div class="cv-inds">${gi.slice(8).map(gdpRow).join("")}</div></details>` : ""}`
      : ""}
    <p class="cv-note">${GDP}：${nat.gdp_vintage ? `${esc(nat.gdp_vintage)}，` : ""}以當年價格計（新臺幣）${gi.length ? `；占比以本城市${GDP}總額為分母。×N = 該產業占本城市${GDP}的比例相對於全國占比的倍數` : ""}。${
      gi.some((d) => d.estimated) ? "≈ 表示含未公開數值的估計。" : ""}${
      gi.some((d) => d.undisclosed) ? `「未公開」= 因保密而未公開的${GDP}。` : ""}</p>
  </section>`;
}

// --- workforce -----------------------------------------------------------------------------------------------------
function workforce(m) {
  const cards = m.inds.map((d) => {
    const spec = d.lq != null && d.lq >= 1.25;
    return `<div class="cv-bld${spec ? " spec" : ""}" title="${esc(d.label)}：${int(d.jobs)} 人（占 ${pct(d.share)}；全國 ${pct(d.natShare)}）">
      ${medallion(d.icon, "•", d.color, 17)}
      <div class="cv-bld-t"><span class="cv-bld-n">${esc(d.short)}</span>
        <span class="cv-bld-v">${compact(d.jobs)} <small>${pct(d.share, 1)}</small></span></div>
      ${lqBadge(d.lq)}
    </div>`;
  }).join("");
  return `
  <section class="cv-sec" id="cv-workforce" data-sec="workforce" aria-labelledby="cv-h-workforce">
    <h3 id="cv-h-workforce">${icon("y-production", "⚙️", { size: 15 })}就業</h3>
    ${cards ? `<p class="cv-lead">本城市${m.city.employed != null ? ` ${int(m.city.employed)} 位` : ""}就業人口的產業分布。<span class="cv-lq hi">×N</span> 為該產業就業占比相對於全國占比的倍數。</p>
    <div class="cv-blds">${cards}</div>` : `<p class="muted cv-note">本城市無產業別就業資料。</p>`}
    <p class="cv-note">資料來源：${esc(m.nation.vintage || "見資料年鑑")}。<span data-dnote>地圖上的特色區域另以各產業的區位商數判定，見「特色區域」。</span></p>
  </section>`;
}

// --- resources -----------------------------------------------------------------------------------------------------
function resources(m) {
  const list = m.sites.map((s, k) => {
    const t = s.type;
    const val = resourceValue(s.item, t, compact);
    // The site's 縣市, only when it is not the city itself (a site filed under a neighbour).
    const where = s.item.state ? m.otherStates?.(m.city, [s.item.state])[0] || "" : "";
    return `<button type="button" class="cv-site" data-site="${k}" title="飛到 ${esc(s.item.name)}">
      <span class="cv-med" style="--bg:${esc(t?.color || "#3a4a5e")}">${glyph(t, 16)}</span>
      <span class="cv-site-t"><b>${esc(s.item.name)}</b><small>${esc(t?.name || s.item.type)}${where ? ` · ${esc(where)}` : ""}</small>
        ${s.item.detail ? `<small class="cv-site-d">${esc(s.item.detail)}</small>` : ""}</span>
      <span class="cv-site-v">${esc(val)}<i aria-hidden="true">›</i></span>
    </button>`;
  }).join("");
  const mw = m.sites.filter((s) => s.type?.unit === "MW").reduce((a, s) => a + (s.item.value || 0), 0);
  const summary = m.sites.length
    ? `<p class="cv-lead">${m.sites.length} 處已標示的資源點${mw ? ` · 已標示的發電裝置容量 ${gw(mw)}` : ""}。點擊即可飛到該處。</p>`
    : `<p class="muted cv-note">本城市內沒有已標示的資源點。地圖只標示規模較大者（各類型有其門檻）。</p>`;
  return `
  <section class="cv-sec" id="cv-resources" data-sec="resources" aria-labelledby="cv-h-resources">
    <h3 id="cv-h-resources">${icon("resources", "⛏️", { size: 15 })}資源</h3>
    ${summary}
    <div class="cv-sites">${list}</div>
    ${m.sites.length ? `<p class="cv-note">所在六角格中心落在本城市轄下鄉鎮市區內的資源點。僅含已標示者，並非本城市的全部容量。</p>` : ""}
  </section>`;
}

// --- compare -------------------------------------------------------------------------------------------------------
const COMPARE = {
  size: { label: "規模與財富", cols: [
    ["人口", (c) => c.population, (v) => popShort(v)],
    [GDP_PC, (c) => (c.gdp != null && c.population ? c.gdp / c.population : null), money],
    ["申報戶所得", (c) => c.median_income, money],
    ["人口成長", (c) => (Number.isFinite(c.growth) ? c.growth : null), (v) => signed(v)],
  ] },
  housing: { label: "住房與就業", cols: [
    ["房價", (c) => c.home_value, money],
    ["月租金", (c) => c.median_rent, (v) => dollars(v)],
    ["租金負擔", (c) => c.rent_burden, (v) => pct(v, 0)],
    ["失業率", (c) => c.unemployment, (v) => pct(v)],
  ] },
};

/**
 * The metric sets to offer: a column that is null for the city and every peer is dropped (a build without income,
 * rent or home values), and when a set is left with a single column the sets are folded into one table.
 */
export function compareSets(m) {
  const rows = [m.city, ...m.peers];
  const sets = Object.entries(COMPARE)
    .map(([id, s]) => ({ id, label: s.label, cols: s.cols.filter(([, f]) => rows.some((c) => f(c) != null)) }))
    .filter((s) => s.cols.length);
  const all = sets.flatMap((s) => s.cols);
  if (sets.length > 1 && all.length <= 5 && sets.some((s) => s.cols.length < 2)) return [{ id: sets[0].id, label: "", cols: all }];
  return sets;
}

export function compareTable(m, set = "size") {
  const rows = [m.city, ...m.peers];
  const sets = compareSets(m);
  const cols = (sets.find((s) => s.id === set) || sets[0])?.cols || [];
  if (!cols.length) return `<p class="muted cv-note">無資料。</p>`;
  const grid = `grid-template-columns:minmax(0,1.25fr) repeat(${cols.length},minmax(0,1fr))`;
  const max = cols.map(([, f]) => Math.max(...rows.map((c) => Math.abs(f(c) ?? 0))) || 1);
  // Under a name: its 縣市, when that is another unit than the city itself (never for a city that is a 縣市).
  const where = (c) => (m.otherStates?.(c, c.states) || []).join("、");
  return `<div class="cv-cmp" role="table" aria-label="${esc(m.city.name)}與規模相近的城市">
    <div class="cv-cmp-r cv-cmp-h" role="row" style="${grid}"><span role="columnheader">城市</span>${cols.map(([l]) => `<span role="columnheader">${esc(l)}</span>`).join("")}</div>
    ${rows.map((c, k) => `<div class="cv-cmp-r${k === 0 ? " me" : ""}" role="row" style="${grid}">
      <span role="cell">${k === 0 ? `<b class="cv-cmp-n">${esc(c.name)}</b>` : `<button type="button" class="cv-cmp-n" data-peer="${esc(c.id)}" title="在城市檢視中開啟${esc(c.name)}">${esc(c.name)}</button>`}${where(c) ? `<small>${esc(where(c))}</small>` : ""}</span>
      ${cols.map(([, f, fmt], j) => {
        const v = f(c);
        const col = v != null && v < 0 ? "#f08a6a" : k === 0 ? "#ecd08e" : "#8fa6bd";
        return `<span role="cell"><em>${v == null ? "–" : esc(fmt(v))}</em>${bar(v == null ? 0 : Math.abs(v) / max[j], col)}</span>`;
      }).join("")}
    </div>`).join("")}
  </div>`;
}

function compare(m) {
  const sets = compareSets(m);
  const first = sets[0]?.id || "size";
  return `
  <section class="cv-sec" id="cv-compare" data-sec="compare" aria-labelledby="cv-h-compare">
    <h3 id="cv-h-compare">${icon("layers", "⚖️", { size: 15 })}比較</h3>
    <p class="cv-lead">${m.peers.length ? `人口規模最接近的 ${m.peers.length} 個城市。點擊即可開啟。` : "沒有可比較的城市。"}</p>
    ${sets.length > 1 ? `<div class="cv-seg" role="group" aria-label="指標">
      ${sets.map((s) => `<button type="button" data-set="${s.id}" aria-pressed="${s.id === first}">${esc(s.label)}</button>`).join("")}
    </div>` : ""}
    <div data-compare>${compareTable(m, first)}</div>
  </section>`;
}

function footer(m) {
  const nat = m.nation;
  return `<div class="cv-foot">資料來源：${esc(nat.vintage || "")}${nat.gdp_vintage ? `；${GDP}：${esc(nat.gdp_vintage)}` : ""}。各項資料的來源與年度見資料年鑑；排名範圍為地圖上全部 ${m.cityList.length} 個城市。
    <a href="#" data-pedia>資料年鑑 ›</a></div>`;
}

/**
 * Scrolls the dock to a section (its tab id, e.g. "districts"). Citizens and districts arrive later and change the
 * heights above, so the section is re-aligned as they do, for up to 4 s or until the user scrolls themselves.
 */
export function goToSection(el, id) {
  const sec = el?.querySelector(`[data-sec="${id}"]`);
  if (!sec) return false;
  const align = () => {
    const nav = el.querySelector(".cv-tabs");
    el.scrollTop = Math.max(0, sec.offsetTop - (nav?.offsetHeight || 0) - 4);
    el.onscroll?.(); // the tab spy (a scroll event is not always sent for a programmatic jump)
  };
  align();
  let ro = null;
  const stop = () => {
    ro?.disconnect();
    ro = null;
    for (const t of ["wheel", "touchstart", "keydown", "pointerdown"]) el.removeEventListener(t, stop);
  };
  for (const t of ["wheel", "touchstart", "keydown", "pointerdown"]) el.addEventListener(t, stop, { passive: true });
  if (typeof ResizeObserver === "function") {
    ro = new ResizeObserver(() => { if (sec.isConnected) align(); else stop(); });
    for (const c of el.children) ro.observe(c);
  }
  setTimeout(stop, 4000);
  return true;
}

/**
 * Fill the dock. handlers: {onClose, onState(idx), onPeer(id), onSite(site), onSiteHover(site|null), onPedia,
 * loadCounties() → Promise<counties.json|null>, loadData(name) → Promise<data|null>, onDistricts(list)} (the
 * city's districts once districts.json is in, for the map plaques).
 */
export function render(el, m, h) {
  el.classList.add("cv-dock");
  el.style.setProperty("--sc", css(m.stateRGB));
  el.innerHTML = header(m) + citizens(m) + districts(m) + economy(m) + workforce(m) + resources(m) + compare(m) + footer(m);
  el.scrollTop = 0;

  el.querySelector("[data-close]").onclick = () => h.onClose();
  el.querySelectorAll("[data-state]").forEach((b) => (b.onclick = () => h.onState(+b.dataset.state)));
  el.querySelector("[data-pedia]").onclick = (e) => { e.preventDefault(); h.onPedia(); };

  // Sites: hover lights the hex on the map, click flies there.
  el.querySelectorAll("[data-site]").forEach((b) => {
    const s = m.sites[+b.dataset.site];
    b.onclick = () => h.onSite(s);
    b.onmouseenter = b.onfocus = () => h.onSiteHover(s);
    b.onmouseleave = b.onblur = () => h.onSiteHover(null);
  });

  // Compare: metric sets and peer links (delegated, the table is re-rendered).
  const cmp = el.querySelector("[data-compare]");
  el.querySelectorAll("[data-set]").forEach((b) => (b.onclick = () => {
    el.querySelectorAll("[data-set]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    cmp.innerHTML = compareTable(m, b.dataset.set);
  }));
  cmp.addEventListener("click", (e) => {
    const b = e.target.closest("[data-peer]");
    if (b) h.onPeer(b.dataset.peer);
  });

  // Tabs scroll to their section; the active tab follows the scroll position. A section can leave after the first
  // paint (no districts.json in this build), so the spy only looks at tabs and sections still in the dock.
  const nav = el.querySelector(".cv-tabs");
  const tabs = [...el.querySelectorAll("[data-tab]")];
  const secs = tabs.map((t) => el.querySelector(`[data-sec="${t.dataset.tab}"]`));
  tabs.forEach((t, k) => (t.onclick = () => {
    if (!secs[k]?.isConnected) return;
    const top = secs[k].offsetTop - nav.offsetHeight - 4;
    el.scrollTo({ top, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }));
  const spy = () => {
    const y = el.scrollTop + nav.offsetHeight + 24;
    let k = -1, last = -1;
    secs.forEach((s, j) => {
      if (!s?.isConnected) return;
      if (k < 0 || s.offsetTop <= y) k = j;
      last = j;
    });
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 4) k = last;
    tabs.forEach((t, j) => t.classList.toggle("on", j === k));
  };
  el.onscroll = spy;
  spy();

  // Citizens and districts arrive with their files (each loaded once, on demand). A build without citizens.json
  // has no figure rows: their slot goes, and the section keeps its population chart, stats and member table.
  const czHost = el.querySelector("[data-citizens]");
  Promise.resolve(h.loadData?.("citizens")).then((data) => {
    if (!czHost.isConnected) return;
    if (!data?.cities) { czHost.remove(); return; }
    czHost.innerHTML = citizensHtml(m, data);
    mountCitizens(czHost, m, data);
  }, () => czHost.remove());
  const dHost = el.querySelector("[data-districts]");
  const typeSlot = el.querySelector("[data-ctype]");
  // A build without districts.json has no Districts section at all: the section and its tab go, rather than a tab
  // that only says there is no data.
  const dropDistricts = () => {
    if (!dHost.isConnected) return;
    el.querySelector('[data-sec="districts"]')?.remove();
    el.querySelector('[data-tab="districts"]')?.remove();
    el.querySelectorAll("[data-dnote]").forEach((n) => n.remove()); // text that points at the Districts section
    spy();
  };
  // military.json is omitted on this map (docs/PORTING.md): loadData resolves null without a request, and
  // districts.js then shows no Encampment tier, rule or vintage.
  Promise.all([
    Promise.resolve(h.loadData?.("districts")).catch(() => null),
    Promise.resolve(h.loadData?.("military")).catch(() => null),
  ]).then(([dd, mil]) => {
    if (!dHost.isConnected) return;
    if (!dd) {
      dropDistricts();
      h.onDistricts?.([]);
      return;
    }
    dHost.innerHTML = districtsHtml(m, dd, mil ?? null);
    typeSlot.innerHTML = badgeHtml(m, dd);
    h.onDistricts?.(cityDistricts(dd, mil ?? null, m.city.id));
  }, dropDistricts);

  // Member 鄉鎮市區 arrive with counties.json (loaded once, on demand).
  const host = el.querySelector("[data-counties]");
  Promise.resolve(h.loadCounties()).then((data) => {
    if (host.isConnected) host.innerHTML = countiesTable(m, data);
  }, () => { if (host.isConnected) host.innerHTML = `<p class="muted cv-note">無鄉鎮市區資料。</p>`; });
}
