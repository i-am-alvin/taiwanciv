// Economy advisor: GDP by industry, city GDP on the map, leaders, specialisation and growth vs output.
// "Metros" are the cities of cities.json: in the Taiwan build the 22 縣市 (docs/PORTING.md).
import { esc, fin, ratio, colorScale, robustDomain, RAMPS } from "../core/util.js";
import { money, dollars, pct, compact, signedPct, count3, fmtShort } from "../core/fmt.js";
import { barList, rampLegend, sizeLegend } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { createScatter } from "../core/scatter.js";
import { section, tiles, segmented, selectBox, sourcesHtml, frameBtn } from "../core/view.js";
import { rowsHighlight } from "../core/data.js";
import { icon } from "../../../ui/icon.js";
import { hasIcon } from "../../../icons.js";
import { hasCJK } from "../../../format.js";

export const METRO_MIN = 250000;
// City income when the data gives the measure no Chinese label: the median total income per tax unit on filed returns.
const INCOME_ZH = "申報戶所得中位數";
const short = (s) => String(s || "").replace(/\s*[（(].*[）)]\s*$/, "");
const indIcon = (k) => (hasIcon(`i-${k}`) ? icon(`i-${k}`, "•", { size: 14 }) : k === "government" ? icon("i-public_admin", "🏛", { size: 14 }) : "");

export function mount(ctx) {
  const { app, data, el, link, params } = ctx;
  const nation = app.data.nation;
  const n = nation.nation || {};
  const metros = data.levels.metros;
  const rows = metros.rows;
  const INCOME = ((l) => (l && hasCJK(l) ? l : INCOME_ZH))(metros.field("median_income")?.label);
  const gdpInd = n.gdp_by_industry || {};
  const jobInd = Object.keys(nation.industries || {});
  const indName = (k) => short(nation.industries?.[k] || k);
  const minPop = compact(METRO_MIN);

  // --- headline -------------------------------------------------------------------------------------------------
  const topInd = Object.entries(gdpInd).filter(([, v]) => fin(v)).sort((a, b) => b[1] - a[1])[0];
  // Without GDP by industry the third tile shows the biggest employer instead.
  const topJob = Object.entries(n.jobs || {}).filter(([, v]) => fin(v)).sort((a, b) => b[1] - a[1])[0];
  el.insertAdjacentHTML("beforeend", tiles([
    { label: `生產毛額 ${n.gdp_year || ""}`.trim(), value: money(n.gdp), sub: nation.gdp_vintage || "當期價格" },
    { label: "人均生產毛額", value: money(ratio(n.gdp, n.population)), sub: "生產毛額 ÷ 人口" },
    topInd
      ? { label: "最大產業", value: short(nation.gdp_industries?.[topInd[0]] || nation.industries?.[topInd[0]] || topInd[0]), sub: `占生產毛額 ${pct(topInd[1] / n.gdp)}` }
      : { label: "最大就業產業", value: topJob ? indName(topJob[0]) : "–", sub: topJob && fin(ratio(topJob[1], n.employed)) ? `占就業人口 ${pct(topJob[1] / n.employed)}` : "" },
  ]));

  // --- GDP by industry ------------------------------------------------------------------------------------------
  const states = app.data.states || [];
  const indRows = Object.entries(gdpInd).filter(([, v]) => fin(v)).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({
    key: k, label: short(nation.gdp_industries?.[k] || nation.industries?.[k] || k), full: nation.gdp_industries?.[k], value: v, text: money(v), sub: pct(v / n.gdp), icon: indIcon(k),
  }));
  let indBars = null;
  if (indRows.length) {
    const indBody = section(el, { title: "各產業生產毛額", kicker: "全國", note: "各產業的生產毛額。將游標移到產業上，會標示該產業占經濟比重最高的縣市；點擊則列出最專精於該產業的城市。" });
    indBars = barList(indBody, {
      rows: indRows, ariaLabel: "各產業生產毛額",
      onHover: (r) => {
        if (!r) return link.hover(null);
        const top = states.map((s, i) => ({ i, v: ratio(s.gdp_by_industry?.[r.key], s.gdp) })).filter((x) => fin(x.v)).sort((a, b) => b.v - a.v).slice(0, 8);
        link.hover({ states: new Set(top.map((x) => x.i)), dimOthers: true });
      },
      onClick: (r) => {
        const k = r.key === "government" ? "public_admin" : r.key;
        if (!jobInd.includes(k)) return; // no jobs by that industry key: nothing to rank
        setIndustry(k);
        specBody.scrollIntoView({ behavior: "smooth", block: "start" });
      },
    });
  }

  // --- map: city GDP circles ------------------------------------------------------------------------------------
  const mapBody = section(el, { title: "地圖上的城市經濟", note: "每個圓圈代表一座城市：面積為生產毛額，顏色為人均生產毛額。將游標移到圓圈上查看數值，點擊開啟該城市。" });
  const ppDomain = robustDomain(rows.filter((r) => r.v.population >= 100000).map((r) => r.v.gdp_pc), 0.03, true)
    || robustDomain(rows.map((r) => r.v.gdp_pc), 0.03, true) || [1, 10];
  const ppColor = colorScale({ type: "seq", domain: ppDomain, ramp: RAMPS.gold });
  const gMax = Math.max(1, ...rows.map((r) => r.v.gdp || 0));
  const bubbles = ctx.bubbles("gdp", {
    rMax: 30, minR: 1.5, alpha: 0.6,
    tip: (b) => `<b>${esc(b.row.name)}</b><br>生產毛額 <b>${money(b.row.v.gdp)}</b> · 人均 <b>${money(b.row.v.gdp_pc)}</b><br>人口 ${count3(b.row.v.population)}`,
    onHover: (b) => { table.setHot(b ? b.key : null); scatter.setHot(b ? b.key : null); link.hover(b ? rowsHighlight(metros, [b.row]) : null); },
    onClick: (b) => app.selectCity(b.row.ref),
  });
  const bubbleItems = rows.filter((r) => fin(r.v.gdp)).map((r) => ({ key: r.key, x: app.w.grid.cx(r.ref.cell), y: app.w.grid.cy(r.ref.cell), value: r.v.gdp, color: ppColor(r.v.gdp_pc), row: r }));
  bubbles.set(bubbleItems, { vMax: gMax });
  const showBubbles = document.createElement("label");
  showBubbles.className = "adv-check";
  showBubbles.innerHTML = `<input type="checkbox" checked> 顯示生產毛額圓圈`;
  showBubbles.querySelector("input").addEventListener("change", (e) => bubbles.set(e.target.checked ? bubbleItems : [], { vMax: gMax }));
  mapBody.appendChild(showBubbles);
  // Legend circles at the three powers of ten up to the largest GDP on the map, whatever the currency's scale.
  const gTop = 10 ** Math.floor(Math.log10(gMax));
  mapBody.insertAdjacentHTML("beforeend", rampLegend({ ramp: RAMPS.gold, domain: ppDomain, fmt: money, label: "人均生產毛額" })
    + sizeLegend([gTop / 100, gTop / 10, gTop].filter((v) => v >= 1 && v <= gMax), (v) => 30 * Math.sqrt(v / gMax), money, "圓圈面積 = 生產毛額（初始縮放比例下）"));

  // --- leaders --------------------------------------------------------------------------------------------------
  const lBody = section(el, { title: "領先城市", note: `人均生產毛額只排入人口 ${minPop}以上的城市（人口少的地區，數值容易大幅波動）。` });
  const big = rows.filter((r) => (r.v.population || 0) >= METRO_MIN);
  segmented(lBody, {
    label: "排序依據", value: "gdp",
    options: [{ value: "gdp", label: "生產毛額最高" }, { value: "gdp_pc", label: "人均生產毛額" }, { value: "growth", label: "成長最快" }],
    onChange: (v) => { table.setRows(v === "gdp" ? rows : big); table.setColumns(cols, { key: v, dir: "desc" }); },
  });
  // A city and its 縣市 are the same unit here, so the name stands alone (no state code after it).
  const nameCol = { key: "name", label: "城市", align: "l", value: (r) => r.name, html: (r) => esc(r.name) };
  const cols = [
    nameCol,
    { key: "gdp", label: "生產毛額", value: (r) => r.v.gdp, text: (r) => money(r.v.gdp), bar: { max: gMax, color: "rgba(224,181,76,.35)" } },
    { key: "gdp_pc", label: "人均", value: (r) => r.v.gdp_pc, text: (r) => money(r.v.gdp_pc) },
    { key: "growth", label: "人口成長", value: (r) => r.v.growth, text: (r) => signedPct(r.v.growth) },
  ];
  const table = createTable(lBody, {
    caption: "城市生產毛額排名", columns: cols, rows, sort: { key: "gdp", dir: "desc" }, rank: true, maxHeight: 280,
    search: "搜尋城市",
    onHover: (r) => { link.hover(r ? rowsHighlight(metros, [r]) : null); bubbles.setHot(r ? r.key : null); scatter.setHot(r ? r.key : null); },
    onClick: (r) => app.selectCity(r.ref),
  });

  // --- specialisation -------------------------------------------------------------------------------------------
  const specBody = section(el, { title: "誰專精什麼", note: `區位商數（LQ）：城市就業人口中從事該產業的占比 ÷ 全國占比。×2 代表集中程度是全國的兩倍。只列人口 ${minPop}以上的城市；最專精的前 15 名會在地圖上圈出。` });
  if (!jobInd.length) specBody.closest("section").hidden = true; // nation.json has no industries
  let industry = params.industry && jobInd.includes(params.industry) ? params.industry : jobInd.includes("manufacturing") ? "manufacturing" : jobInd[0];
  const indSel = selectBox(specBody, {
    label: "產業", value: industry,
    options: jobInd.map((k) => ({ value: k, label: indName(k) })),
    onChange: (v) => setIndustry(v),
  });
  const specInfo = document.createElement("p");
  specInfo.className = "adv-note";
  specBody.appendChild(specInfo);
  const lq = (r, k = industry) => {
    const o = r.ref;
    const us = ratio(n.jobs?.[k], n.employed);
    return us ? ratio(ratio(o.jobs?.[k], o.employed), us) : null;
  };
  const specCols = (maxLq, alpha) => [
    nameCol,
    { key: "share", label: "就業占比", value: (r) => ratio(r.ref.jobs?.[industry], r.ref.employed), text: (r) => pct(ratio(r.ref.jobs?.[industry], r.ref.employed)) },
    { key: "lq", label: "區位商數", value: (r) => lq(r), text: (r) => (fin(lq(r)) ? `×${lq(r).toFixed(2)}` : "–"), bar: { max: maxLq, color: `rgba(74,134,214,${alpha})` } },
    { key: "workers", label: "就業人口", value: (r) => r.ref.jobs?.[industry], text: (r) => count3(r.ref.jobs?.[industry]) },
  ];
  const specTable = createTable(specBody, {
    caption: "最專精的城市", rank: true, maxHeight: 260, rows: [],
    columns: specCols(1, 0.4),
    sort: { key: "lq", dir: "desc" },
    onHover: (r) => { link.hover(r ? rowsHighlight(metros, [r]) : null); scatter.setHot(r ? r.key : null); bubbles.setHot(r ? r.key : null); },
    onClick: (r) => app.selectCity(r.ref),
  });

  // --- scatter --------------------------------------------------------------------------------------------------
  const scBody = section(el, { title: "成長與產出", note: "每個點代表一座城市：橫軸為人均生產毛額，縱軸為人口成長，大小為人口。拖曳出矩形可選取城市，並在地圖上圈出。" });
  const scCtl = document.createElement("div");
  scCtl.className = "adv-row";
  scBody.appendChild(scCtl);
  let colorBy = jobInd.length ? "lq" : "none", allMetros = false;
  selectBox(scCtl, {
    label: "顏色", value: colorBy,
    // A measure with no value for any city is not offered.
    options: [...(jobInd.length ? [{ value: "lq", label: "產業專精度（所選產業）" }] : []), { value: "unemployment", label: "失業率" }, { value: "median_income", label: INCOME }, { value: "none", label: "無" }]
      .filter((o) => o.value === "lq" || o.value === "none" || rows.some((r) => fin(r.v[o.value]))),
    onChange: (v) => { colorBy = v; drawScatter(); },
  });
  segmented(scCtl, { label: "城市", value: "big", options: [{ value: "big", label: `${minPop}以上` }, { value: "all", label: "全部" }], onChange: (v) => { allMetros = v === "all"; drawScatter(); } });
  const legendEl = document.createElement("div");
  const scatter = createScatter(scBody, {
    points: [], height: 300,
    x: { label: "人均生產毛額", fmt: (v) => money(v), log: true },
    y: { label: "人口成長", fmt: (v) => fmtShort("signed", v) },
    size: { label: "人口", fmt: count3, max: 15, min: 2 },
    refY: [{ v: n.growth ?? 0, label: `全國 ${signedPct(n.growth)}` }],
    onHover: (p) => { link.hover(p ? rowsHighlight(metros, [p.row]) : null); bubbles.setHot(p ? p.key : null); table.setHot(p ? p.key : null, false); },
    onClick: (p) => app.selectCity(p.row.ref),
    onBrush: (set) => {
      const sel = set ? rows.filter((r) => set.has(r.key)) : [];
      link.base(sel.length ? rowsHighlight(metros, sel, { dim: true }) : specHighlight(), { frame: sel.length > 1 });
      bubbles.setSelected(set);
      brushInfo.innerHTML = sel.length ? brushSummary(sel) : "";
    },
  });
  scBody.appendChild(legendEl);
  const brushInfo = document.createElement("div");
  brushInfo.className = "adv-brushinfo";
  scBody.appendChild(brushInfo);
  function brushSummary(sel) {
    const pop = sel.reduce((a, r) => a + (r.v.population || 0), 0);
    const gdp = sel.reduce((a, r) => a + (r.v.gdp || 0), 0);
    return `已選取 <b>${sel.length}</b> 座城市 · 人口 ${count3(pop)} · 生產毛額 ${money(gdp)}${fin(ratio(gdp, n.gdp)) ? `（占全國 ${pct(gdp / n.gdp)}）` : ""} ${frameBtn()}<button type="button" class="adv-mini" data-clear>清除</button>`;
  }
  brushInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) { scatter.setSelected(null); link.base(specHighlight()); bubbles.setSelected(null); brushInfo.innerHTML = ""; } });

  function drawScatter() {
    const list = rows.filter((r) => allMetros || (r.v.population || 0) >= METRO_MIN);
    const cv = (r) => (colorBy === "lq" ? lq(r) : colorBy === "none" ? null : r.v[colorBy]);
    let color = null, legend = "";
    if (colorBy !== "none") {
      const dom = robustDomain(list.map(cv), 0.03, colorBy === "lq") || [0, 1];
      const spec = colorBy === "lq" ? { type: "seq", domain: [Math.max(0.2, dom[0]), Math.max(1.5, dom[1])], log: true, ramp: RAMPS.seq } : { type: "seq", domain: dom, ramp: colorBy === "unemployment" ? RAMPS.heat : RAMPS.gold };
      const cs = colorScale(spec);
      color = (c) => cs(c);
      const f = colorBy === "lq" ? (v) => `×${v.toFixed(1)}` : colorBy === "unemployment" ? (v) => pct(v) : money;
      legend = rampLegend({ ramp: spec.ramp, domain: spec.domain, fmt: f, log: spec.log, label: colorBy === "lq" ? `${indName(industry)}專精度（區位商數）` : colorBy === "unemployment" ? "失業率" : INCOME });
    }
    const labels = [...list].sort((a, b) => (b.v.population || 0) - (a.v.population || 0)).slice(0, 8).map((r) => r.key);
    scatter.update({
      points: list.filter((r) => fin(r.v.gdp_pc) && fin(r.v.growth)).map((r) => ({ key: r.key, x: r.v.gdp_pc, y: r.v.growth, s: r.v.population, c: cv(r), label: r.name, sub: "", row: r })),
      color, labels, colorLabel: colorBy === "none" ? null : colorBy === "lq" ? "區位商數" : colorBy === "unemployment" ? "失業率" : INCOME,
      colorFmt: colorBy === "lq" ? (v) => `×${(+v).toFixed(2)}` : colorBy === "unemployment" ? pct : dollars,
    });
    legendEl.innerHTML = legend;
  }

  let specTop = [];
  const specHighlight = () => (specTop.length ? rowsHighlight(metros, specTop, { ringMax: 15 }) : null);
  function setIndustry(k) {
    industry = k;
    if (k != null) indSel.set(k);
    const list = big.filter((r) => fin(lq(r))).sort((a, b) => lq(b) - lq(a));
    specTop = list.slice(0, 15);
    const maxLq = Math.max(1, ...list.slice(0, 40).map((r) => lq(r)));
    specTable.setColumns(specCols(maxLq, 0.45), { key: "lq", dir: "desc" });
    specTable.setRows(list);
    const us = ratio(n.jobs?.[k], n.employed);
    specInfo.innerHTML = k == null ? "" : `全國：<b>${pct(us)}</b> 的就業人口（${count3(n.jobs?.[k])}）從事${esc(indName(k))}。`;
    if (!scatter.selected) link.base(specHighlight());
    indBars?.setSelected(k === "public_admin" ? "government" : k);
    drawScatter();
  }
  setIndustry(industry);

  // Sources and vintages come from the data (field definitions, nation.json), not from a list written here.
  const srcIds = [...["gdp", "gdp_pc", "population", "employed", "unemployment", "median_income"].filter((k) => rows.some((r) => fin(r.v[k]))).map((k) => metros.field(k)?.source), "ris_population", ...(nation.sources || [])];
  el.insertAdjacentHTML("beforeend", sourcesHtml(data, srcIds, [
    ...(nation.gdp_vintage && nation.vintage && nation.gdp_vintage !== nation.vintage
      ? [`生產毛額取自「${esc(nation.gdp_vintage)}」，人口與就業取自「${esc(nation.vintage)}」：人均數值是兩份不同來源、年份可能不同的數字相除。`] : []),
    "產業專精度（區位商數）以各城市的就業人口結構計算，反映的是就業集中程度，不是產值。",
    `人口未滿 ${minPop}的城市不列入人均生產毛額與專精度排名；選擇「全部」可在散佈圖上看到它們。`,
  ]));

  return {
    onMapHover(h) {
      const r = h.cell >= 0 ? metros.rowAtCell(h.cell) : null;
      scatter.setHot(r ? r.key : null);
      specTable.setHot(r ? r.key : null);
    },
    onEscape() {
      if (scatter.selected) { scatter.setSelected(null); link.base(specHighlight()); bubbles.setSelected(null); brushInfo.innerHTML = ""; return true; }
      return false;
    },
  };
}
