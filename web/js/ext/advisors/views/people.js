// People advisor: population, growth, density, age and immigration.
// Levels: states = 縣市, metros = the cities of cities.json (the same 22 縣市), counties = 鄉鎮市區. County sections
// appear only when counties.json has the column with at least one value (a Taiwan build may lack some).
import { esc, fin, colorScale, robustDomain, RAMPS } from "../core/util.js";
import { pct, int, compact, signedPct, count3, fmtShort, fmtValue } from "../core/fmt.js";
import { barList, histogram, rampLegend } from "../core/charts.js";
import { createScatter } from "../core/scatter.js";
import { section, tiles, segmented, mapPicker, frameBtn, sourcesHtml, topBy } from "../core/view.js";
import { rowsHighlight } from "../core/data.js";
import { growthLens } from "../core/lenses.js";
import { hasCJK } from "../../../format.js";

const METRO_MIN = 100000; // Taiwan: every 縣市 but 連江 (1.4萬人)

export function mount(ctx) {
  const { app, data, el, link } = ctx;
  const n = data.nat;
  const { states, metros, counties } = data.levels;
  const yrs = n.growth_years || [];
  const minPop = compact(METRO_MIN);
  const has = (k) => !!counties && counties.rows.some((r) => fin(r.v[k]));
  const hasLens = (id) => !!app.lensById?.has(id);
  // A column's own label from counties.json when it is Chinese, else ours.
  const lab = (k, zh) => { const l = counties?.field(k)?.label; return l && hasCJK(l) ? l : zh; };
  // The 縣市 a 鄉鎮市區 belongs to, by name (several 縣市 have an 東區 or a 中正區).
  const stName = new Map((app.w.raw.states || []).flatMap((s) => [[s.abbr, s.name], [s.fips, s.name]]));
  const parentOf = (r) => (r.level === "counties" ? stName.get(r.v.state) || stName.get(String(r.key).slice(0, 5)) || "" : "");

  el.insertAdjacentHTML("beforeend", tiles([
    { label: "人口", value: count3(n.population), sub: data.vintage },
    { label: `人口成長 ${yrs.join("–")}`.trim(), value: signedPct(n.growth, 2), sub: "戶籍登記年底人口" },
    { label: "行政區", value: `${int(states.rows.length || metros.rows.length)} 個縣市`, sub: counties ? `${int(counties.rows.length)} 個鄉鎮市區` : "" },
  ]));

  // --- the map: growth by default, so the map tells the same story as the first chart ---------------------------
  let gLevel = "metros";
  const mapRow = document.createElement("div");
  mapRow.className = "adv-sec adv-mapsec";
  el.appendChild(mapRow);
  // A lens is offered under its own name from lenses.json when that is Chinese.
  const lensOpt = (value, label, id) => { const nm = app.lensById?.get(id)?.name; return hasLens(id) ? [{ value, label: nm && hasCJK(nm) ? nm : label, lens: () => id }] : []; };
  const picker = mapPicker(ctx, mapRow, {
    value: "growth", label: "地圖",
    options: [
      { value: "growth", label: "人口成長", lens: () => growthLens(data, gLevel) },
      ...(counties ? [...lensOpt("density", "人口密度", "density"), ...lensOpt("age", "年齡", "age"), ...lensOpt("foreign_born", lab("foreign_born", "境外出生"), "foreign_born")] : []),
      { value: "terrain", label: "地形", lens: () => null },
    ],
  });

  // --- growth ---------------------------------------------------------------------------------------------------
  const gBody = section(el, { title: "誰在成長，誰在流失", note: `${yrs.length ? `${yrs.join("–")} 年的戶籍登記年底人口變化` : "戶籍登記年底人口變化"}（內政部戶政司），兩個年度的行政區相同。城市只列人口 ${minPop}以上者。` });
  const gHost = document.createElement("div");
  segmented(gBody, { label: "範圍", value: gLevel, options: [{ value: "metros", label: "城市" }, { value: "states", label: "縣市" }], onChange: (v) => { gLevel = v; drawGrowth(); if (picker.value === "growth") picker.refresh(); } });
  gBody.appendChild(gHost);
  function drawGrowth() {
    gHost.innerHTML = "";
    const lv = gLevel === "metros" ? metros : states;
    const min = gLevel === "metros" ? METRO_MIN : 0;
    const fast = topBy(lv.rows, (r) => r.v.growth, { n: 8, min });
    const slow = topBy(lv.rows, (r) => r.v.growth, { n: 8, min, asc: true });
    if (!fast.length) { gHost.innerHTML = `<p class="adv-empty">無資料</p>`; return; }
    const max = Math.max(...[...fast, ...slow].map((x) => Math.abs(x.v)));
    const mk = (list) => list.map((x) => ({ key: x.r.key, label: x.r.name, sub: "", value: x.v, text: signedPct(x.v), tone: x.v >= 0 ? "good" : "bad", row: x.r }));
    const opts = {
      diverging: true, max,
      onHover: (r) => link.hover(r ? rowsHighlight(lv, [r.row]) : null),
      onClick: (r) => lv.focus(r.row),
    };
    const slowTitle = slow.every((x) => x.v < 0) ? "人口減少" : "成長最慢";
    gHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">成長最快</h4>`);
    barList(gHost, { ...opts, rows: mk(fast), ariaLabel: "成長最快" });
    gHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">${slowTitle}</h4>`);
    barList(gHost, { ...opts, rows: mk(slow), ariaLabel: slowTitle });
  }
  drawGrowth();

  const baseSrc = ["ris_population", metros.field("population")?.source, states.field("population")?.source];
  if (!counties) {
    el.insertAdjacentHTML("beforeend", `<p class="adv-empty pad">尚未建置 counties.json，因此沒有鄉鎮市區圖表。</p>`);
    el.insertAdjacentHTML("beforeend", sourcesHtml(data, baseSrc, []));
    return {};
  }

  // --- density --------------------------------------------------------------------------------------------------
  const cByKey = counties.byKey;
  let hist = null, pinnedBin = null;
  const binInfo = document.createElement("div");
  binInfo.className = "adv-brushinfo";
  if (has("density")) {
    const dBody = section(el, { title: "有多擁擠", note: "各鄉鎮市區每平方公里的人口（對數尺度）。切換為「人口」可改按人口加權：多數人住在高密度的那一端。將游標移到長條上可查看這些鄉鎮市區；點擊可保持圈選。" });
    const dCtl = document.createElement("div");
    dCtl.className = "adv-row";
    dBody.appendChild(dCtl);
    let weighted = false;
    segmented(dCtl, { label: "計數方式", value: "counties", options: [{ value: "counties", label: "鄉鎮市區" }, { value: "people", label: "人口" }], onChange: (v) => { weighted = v === "people"; drawHist(); } });
    if (hasLens("density")) {
      const dLens = document.createElement("button");
      dLens.type = "button";
      dLens.className = "adv-mini";
      dLens.textContent = "以人口密度為地圖上色";
      dLens.addEventListener("click", () => picker.set("density"));
      dCtl.appendChild(dLens);
    }
    const histHost = document.createElement("div");
    dBody.appendChild(histHost);
    dBody.appendChild(binInfo);
    const popSum = counties.rows.reduce((a, r) => a + (r.v.population || 0), 0);
    const landSum = counties.rows.reduce((a, r) => a + (r.v.land_km2 || 0), 0);
    const avgDensity = landSum > 0 ? popSum / landSum : null;
    // The histogram spans the data (a little beyond the sparsest and densest 鄉鎮市區).
    const dVals = counties.rows.map((r) => r.v.density).filter((v) => fin(v) && v > 0);
    const dom = dVals.length ? [Math.min(...dVals) * 0.8, Math.max(...dVals) * 1.25] : [0.3, 30000];
    const densRamp = RAMPS.heat;
    const drawHist = () => {
      histHost.innerHTML = "";
      const vals = counties.rows.map((r) => ({ key: r.key, v: r.v.density, w: r.v.population }));
      hist = histogram(histHost, {
        values: vals, log: true, bins: 30, domain: dom, weighted, height: 130,
        fmt: (v) => fmtShort("float", v), unitLabel: "個鄉鎮市區", weightFmt: (w) => `人口 ${count3(w)}`,
        label: "鄉鎮市區人口密度直方圖",
        colorOf: (_, t) => colorScale({ type: "seq", domain: [0, 1], ramp: densRamp })(t),
        markers: fin(avgDensity) ? [{ v: avgDensity, label: "全國平均" }] : [],
        onHover: (bin) => link.hover(bin ? rowsHighlight(counties, bin.keys.map((k) => cByKey.get(k)), { dim: true }) : null),
        onClick: (bin) => {
          pinnedBin = pinnedBin === bin.i ? null : bin.i;
          const rows = pinnedBin != null ? bin.keys.map((k) => cByKey.get(k)) : [];
          link.base(rows.length ? rowsHighlight(counties, rows, { dim: true }) : null, { frame: rows.length > 1 });
          binInfo.innerHTML = rows.length ? `<b>${int(rows.length)}</b> 個鄉鎮市區，${fmtShort("float", bin.x0)}–${fmtShort("float", bin.x1)} 人/km² · 人口 ${count3(rows.reduce((a, r) => a + (r.v.population || 0), 0))} ${frameBtn()}<button type="button" class="adv-mini" data-clear>清除</button>` : "";
        },
      });
    };
    binInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) { pinnedBin = null; link.base(null); binInfo.innerHTML = ""; } });
    drawHist();
  }

  // --- age and foreign-born -------------------------------------------------------------------------------------
  let scatter = null;
  const selInfo = document.createElement("div");
  selInfo.className = "adv-brushinfo";
  const hasAge = has("median_age") && has("foreign_born");
  if (hasAge) {
    const ageLabel = lab("median_age", "年齡中位數"), fbLabel = lab("foreign_born", "境外出生");
    const colourNote = has("density") ? "，顏色為人口密度" : "";
    const fbFmt = counties.field("foreign_born")?.format || "pct";
    const aBody = section(el, { title: `年齡與${fbLabel}`, note: `每個點代表一個鄉鎮市區：橫軸為${esc(ageLabel)}，縱軸為${esc(fbLabel)}，大小為人口${colourNote}。拖曳出矩形可選取鄉鎮市區，並在地圖上標示。將游標移到地圖上，可在圖中找到對應的鄉鎮市區。` });
    const mapBtns = [["age", ageLabel], ["foreign_born", fbLabel]].filter(([id]) => hasLens(id));
    if (mapBtns.length) {
      const aCtl = document.createElement("div");
      aCtl.className = "adv-row";
      aBody.appendChild(aCtl);
      aCtl.innerHTML = `<span class="adv-note">地圖上色依據</span>${mapBtns.map(([id, label]) => `<button type="button" class="adv-mini" data-map="${id}">${esc(label)}</button>`).join("")}`;
      aCtl.addEventListener("click", (e) => { const v = e.target.closest("[data-map]")?.dataset.map; if (v) picker.set(v); });
    }
    const dDom = robustDomain(counties.rows.map((r) => r.v.density), 0.02, true) || [1, 2000];
    const dColor = colorScale({ type: "seq", domain: dDom, log: true, ramp: RAMPS.heat });
    const big = topBy(counties.rows, (r) => r.v.population, { n: 6 }).map((x) => x.r.key);
    const medAge = medianOf(counties.rows, "median_age");
    scatter = createScatter(aBody, {
      height: 310,
      points: counties.rows.map((r) => ({ key: r.key, x: r.v.median_age, y: r.v.foreign_born, s: r.v.population, c: r.v.density, label: r.name, sub: parentOf(r), row: r })),
      x: { label: ageLabel, fmt: (v) => String(+v.toFixed(0)) },
      y: { label: fbLabel, fmt: (v) => fmtShort(fbFmt, v) },
      size: { label: "人口", fmt: count3, max: 14, min: 1.4 },
      ...(has("density") ? { color: (c) => dColor(c), colorLabel: "人口密度", colorFmt: (v) => `${fmtValue("float", v)} 人/km²` } : {}),
      labels: big,
      refX: fin(medAge) ? [{ v: medAge, label: "鄉鎮市區中位數" }] : [],
      onHover: (p) => link.hover(p ? rowsHighlight(counties, [p.row]) : null),
      onClick: (p) => counties.focus(p.row),
      onBrush: (set) => {
        const sel = set ? counties.rows.filter((r) => set.has(r.key)) : [];
        link.base(sel.length ? rowsHighlight(counties, sel, { dim: true }) : null, { frame: sel.length > 1 });
        selInfo.innerHTML = sel.length ? selSummary(sel) : "";
      },
    });
    if (has("density")) aBody.insertAdjacentHTML("beforeend", rampLegend({ ramp: RAMPS.heat, domain: dDom, log: true, fmt: (v) => fmtShort("float", v), label: "每平方公里人口" }));
    aBody.appendChild(selInfo);
    selInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) { scatter.setSelected(null); link.base(null); selInfo.innerHTML = ""; } });
  }
  function selSummary(sel) {
    const pop = sel.reduce((a, r) => a + (r.v.population || 0), 0);
    const top = [...sel].sort((a, b) => (b.v.population || 0) - (a.v.population || 0)).slice(0, 5);
    return `<b>${int(sel.length)}</b> 個鄉鎮市區 · 人口 ${count3(pop)}${fin(n.population) && n.population > 0 ? `（占全國 ${pct(pop / n.population)}）` : ""}<br><span class="sub">人口最多：${top.map((r) => `${esc(parentOf(r))}${esc(r.name)}`).join(" · ")}</span> ${frameBtn()}<button type="button" class="adv-mini" data-clear>清除</button>`;
  }

  const countySrc = ["population", "land_km2", "density", "median_age", "foreign_born"].map((k) => counties.field(k)?.source);
  el.insertAdjacentHTML("beforeend", sourcesHtml(data, [...baseSrc, ...countySrc], [
    "人口成長地圖依各城市本身的人口變化上色；灰色六角格不屬於任何城市。把圖表切換為「縣市」，每個六角格就會依所屬縣市上色。",
    "人口成長以戶籍登記的年底人口計算（內政部戶政司），兩個年度採用相同的行政區。",
    `鄉鎮市區的數字為「${esc(data.countyVintage)}」，年份可能與縣市、城市的數字不同。`,
    ...(hasAge ? ["點的位置是該鄉鎮市區自己的年齡中位數；一群鄉鎮市區合起來的中位數，並不等於各自中位數的平均。"] : []),
    ...(data.countiesOffMap ? [`有 ${int(data.countiesOffMap)} 個最小的鄉鎮市區不足一個六角格，選取它們時地圖上不會圈出任何範圍。`] : []),
  ]));

  return {
    onMapHover(h) {
      const r = h.cell >= 0 ? counties.rowAtCell(h.cell) : null;
      scatter?.setHot(r ? r.key : null);
      hist?.setHot(r ? hist.binOf(r.v.density)?.i ?? null : null);
    },
    onEscape() {
      if (scatter?.selected || pinnedBin != null) {
        scatter?.setSelected(null); pinnedBin = null; link.base(null); selInfo.innerHTML = ""; binInfo.innerHTML = "";
        return true;
      }
      return false;
    },
  };
}

function medianOf(rows, k) {
  const s = rows.map((r) => r.v[k]).filter(fin).sort((a, b) => a - b);
  return s.length ? s[Math.floor(s.length / 2)] : null;
}
