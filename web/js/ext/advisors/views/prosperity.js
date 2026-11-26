// Prosperity & Housing advisor: income vs home values, poverty, rents and unemployment.
// Every tile, chart and table needs its measure to have a value somewhere (in the Taiwan build cities and 縣市 have
// no home value or rent), so those parts stay hidden and the advisor says which are missing. A 鄉鎮市區 column is
// labelled, formatted and ordered by its own field metadata in counties.json (label, unit, format, higher_is): the
// column ids are inherited from the US build and do not say what the Taiwan numbers mean.
import { esc, fin, colorScale, RAMPS } from "../core/util.js";
import { money, dollars, pct, int, compact, count3, fmtShort, fmtCell } from "../core/fmt.js";
import { barList, histogram, rampLegend } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { createScatter } from "../core/scatter.js";
import { section, tiles, segmented, lensButton, sourcesHtml, topBy, frameBtn } from "../core/view.js";
import { rowsHighlight } from "../core/data.js";
import { hasCJK, CURRENCY } from "../../../format.js";

const METRO_MIN = 100000; // Taiwan: every 縣市 but 連江 (1.4萬人)
const BIG_METRO = 100000; // Taiwan: same floor as METRO_MIN
const LEVEL_NAME = { counties: "鄉鎮市區", metros: "城市", states: "縣市" };
// City income when the data gives the measure no Chinese label: the median total income per tax unit on filed returns.
const INCOME_ZH = "申報戶所得中位數";

export function mount(ctx) {
  const { app, data, el, link } = ctx;
  const n = data.nat;
  const { states, metros, counties } = data.levels;
  const INCOME = ((l) => (l && hasCJK(l) ? l : INCOME_ZH))(metros.field("median_income")?.label);
  const any = (lv, f) => !!lv && lv.rows.some((r) => fin(f(r)));
  // The 縣市 a 鄉鎮市區 belongs to, by name; a city or 縣市 row needs no such suffix.
  const stName = new Map((app.w.raw.states || []).flatMap((s) => [[s.abbr, s.name], [s.fips, s.name]]));
  const parentOf = (r) => (r.level === "counties" ? stName.get(r.v.state) || stName.get(String(r.key).slice(0, 5)) || "" : "");
  const nameHtml = (r) => `${esc(r.name)}${parentOf(r) ? ` <span class="sub">${esc(parentOf(r))}</span>` : ""}`;
  const missing = []; // measures without a single value, named in the footer
  // A 鄉鎮市區 column's own label and unit from counties.json when they are Chinese.
  const lab = (k, zh) => { const l = counties?.field(k)?.label; return l && hasCJK(l) ? l : zh; };
  // "所得（每申報戶綜合所得總額中位數）": the label with what it measures, taken from the field's unit text.
  const defOf = (k, zh) => {
    const u = String(counties?.field(k)?.unit || "").replace(/（[^（）]*）$/, "");
    return `${lab(k, zh)}${u && hasCJK(u) && u !== lab(k, zh) ? `（${u}）` : ""}`;
  };
  const incYear = app.data.nation.income_year;

  const headline = [
    fin(n.median_income) && { label: INCOME, value: dollars(n.median_income), sub: incYear ? `${incYear} 年度綜合所得稅申報` : "" },
    fin(n.home_value) && { label: "房價中位數", value: money(n.home_value), sub: fin(n.median_income) && n.median_income > 0 ? `所得的 ${(n.home_value / n.median_income).toFixed(1)} 倍` : "" },
    fin(n.unemployment) && { label: "失業率", value: pct(n.unemployment), sub: data.vintage },
  ].filter(Boolean);
  if (headline.length) el.insertAdjacentHTML("beforeend", tiles(headline));

  // --- income vs home value -------------------------------------------------------------------------------------
  const incOf = (r) => (r.level === "counties" ? r.v.income : r.v.median_income);
  const ratioOf = (r) => (fin(r.v.home_value) && fin(incOf(r)) && incOf(r) > 0 ? r.v.home_value / incOf(r) : null);
  const affLevels = ["counties", "metros"].filter((k) => any(data.levels[k], ratioOf));
  let level = affLevels[0] || "metros";
  const lv = () => data.levels[level];
  let scatter = null, affTable = null;
  const selInfo = document.createElement("div");
  selInfo.className = "adv-brushinfo";
  const clearSel = () => { scatter?.setSelected(null); affTable?.setSelected(null); link.base(null); selInfo.innerHTML = ""; };
  const incLabelOf = (k) => (k === "counties" ? lab("income", "所得") : INCOME);
  const homeLabelOf = (k) => (k === "counties" ? lab("home_value", "房價") : "房價中位數");
  if (!affLevels.length) {
    if (![counties, metros].some((l) => any(l, incOf))) missing.push("所得");
    if (![counties, metros].some((l) => any(l, (r) => r.v.home_value))) missing.push("房價");
  } else {
    // Reference lines at whole multiples of income that fall inside the data (up to three), and a colour ramp to match.
    const ratios = affLevels.flatMap((k) => data.levels[k].rows.map(ratioOf)).filter(fin).sort((a, b) => a - b);
    const rLo = ratios[Math.floor(ratios.length * 0.02)], rHi = ratios[Math.ceil(ratios.length * 0.98) - 1];
    const picked = [3, 5, 8, 12, 16, 24, 32].filter((k) => k >= rLo * 0.7 && k <= rHi * 1.3).slice(-3);
    const marks = picked.length ? picked : [3, 5, 8];
    const ratioDomain = rHi > rLo ? [Math.floor(rLo), Math.ceil(rHi)] : [2, 10];
    const ratioColor = colorScale({ type: "seq", domain: ratioDomain, ramp: RAMPS.heat });
    const aBody = section(el, { title: "買一間房要多少年所得", note: `${affLevels.length === 1 && level === "counties" ? `${esc(defOf("home_value", "房價"))}對${esc(defOf("income", "所得"))}` : "房價中位數對所得中位數"}。虛線標示 ${marks.join("、")} 年的所得：越往上，越難負擔。拖曳出矩形可選取地區；將游標移到地圖上，可在圖中找到對應的地區。` });
    const aCtl = document.createElement("div");
    aCtl.className = "adv-row";
    aBody.appendChild(aCtl);
    if (affLevels.length > 1) segmented(aCtl, { label: "地區", value: level, options: affLevels.map((k) => ({ value: k, label: LEVEL_NAME[k] })), onChange: (v) => { level = v; drawAfford(); } });
    for (const id of ["income", "home"]) {
      const b = lensButton(app, id, `${app.lensById?.get(id)?.name || ""}濾鏡`);
      if (b) aCtl.appendChild(b);
    }
    scatter = createScatter(aBody, {
      height: 310, points: [],
      x: { label: incLabelOf(level), fmt: money, log: true },
      y: { label: `${homeLabelOf(level)}（${CURRENCY}）`, fmt: compact, log: true },
      size: { label: "人口", fmt: count3, max: 14, min: 1.4 },
      refLines: marks.map((k) => ({ k, label: `${k}×` })),
      color: (c) => ratioColor(c), colorLabel: "房價 ÷ 所得", colorFmt: (v) => `×${(+v).toFixed(1)}`,
      onHover: (p) => { link.hover(p ? rowsHighlight(lv(), [p.row]) : null); affTable.setHot(p ? p.key : null, false); },
      onClick: (p) => lv().focus(p.row),
      onBrush: (set) => {
        const sel = set ? lv().rows.filter((r) => set.has(r.key)) : [];
        link.base(sel.length ? rowsHighlight(lv(), sel, { dim: true }) : null, { frame: sel.length > 1 });
        affTable.setSelected(set);
        selInfo.innerHTML = sel.length ? `已選取 <b>${int(sel.length)}</b> 個${LEVEL_NAME[level]} · 人口 ${count3(sel.reduce((a, r) => a + (r.v.population || 0), 0))} ${frameBtn()}<button type="button" class="adv-mini" data-clear>清除</button>` : "";
      },
    });
    aBody.insertAdjacentHTML("beforeend", rampLegend({ ramp: RAMPS.heat, domain: ratioDomain, fmt: (v) => `×${v}`, label: "房價 ÷ 所得" }));
    aBody.appendChild(selInfo);
    selInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) clearSel(); });
    aBody.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">負擔能力一覽</h4>`);
    const salesCol = affLevels.length === 1 && level === "counties" && any(counties, (r) => r.v.home_sales);
    affTable = createTable(aBody, {
      caption: "房價與所得", rank: true, maxHeight: 260, rows: [], search: "搜尋地區",
      columns: [
        { key: "name", label: "地區", align: "l", value: (r) => r.name, html: nameHtml },
        { key: "inc", label: "所得", value: incOf, text: (r) => money(incOf(r)) },
        { key: "home", label: "房價", value: (r) => r.v.home_value, text: (r) => money(r.v.home_value) },
        // How many sales the median price rests on, when the data says (a thin sample makes a jumpy median).
        ...(salesCol ? [{ key: "sales", label: lab("home_sales", "交易筆數"), value: (r) => r.v.home_sales, text: (r) => (fin(r.v.home_sales) ? int(r.v.home_sales) : "–") }] : []),
        { key: "ratio", label: "倍數", value: (r) => ratioOf(r), html: (r) => fin(ratioOf(r)) ? `<span class="dot" style="background:${ratioColor(ratioOf(r))}"></span>×${ratioOf(r).toFixed(1)}` : "–" },
      ],
      sort: { key: "ratio", dir: "desc" },
      onHover: (r) => { link.hover(r ? rowsHighlight(lv(), [r]) : null); scatter.setHot(r ? r.key : null); },
      onClick: (r) => lv().focus(r),
    });
    drawAfford();
  }
  function drawAfford() {
    clearSel();
    const rows = lv().rows.filter((r) => fin(ratioOf(r)));
    scatter.update({
      x: { label: incLabelOf(level), fmt: money, log: true },
      y: { label: `${homeLabelOf(level)}（${CURRENCY}）`, fmt: compact, log: true },
      points: rows.map((r) => ({ key: r.key, x: incOf(r), y: r.v.home_value, s: r.v.population, c: ratioOf(r), label: r.name, sub: parentOf(r), row: r })),
      labels: topBy(rows, (r) => r.v.population, { n: 6 }).map((x) => x.r.key),
    });
    affTable.setRows(rows);
  }

  // --- poverty --------------------------------------------------------------------------------------------------
  let povHist = null;
  const hasPoverty = any(counties, (r) => r.v.poverty);
  if (hasPoverty) {
    const povField = counties.field("poverty");
    const povLabel = lab("poverty", "貧窮率");
    const povFmt = povField?.format || "pct";
    const isRate = povFmt === "pct";
    // A rate is worse when high; a low-income threshold (higher_is: good) is worse when low. The worse end sorts
    // first and takes the hot end of the ramp.
    const worseHigh = povField?.higher_is !== "good";
    const pBody = section(el, { title: povLabel, note: `${povField?.description && hasCJK(povField.description) ? esc(povField.description) + (/[。！？；）]$/.test(povField.description) ? "" : " ") : ""}將游標移到長條上可圈出這些鄉鎮市區；下表列出全部。` });
    const pCtl = document.createElement("div");
    pCtl.className = "adv-row";
    pBody.appendChild(pCtl);
    const lb = lensButton(app, "poverty", `${povLabel}濾鏡`);
    if (lb) pCtl.appendChild(lb);
    const pHost = document.createElement("div");
    pBody.appendChild(pHost);
    const avgPov = (() => {
      let a = 0, w = 0;
      for (const r of counties.rows) if (fin(r.v.poverty) && fin(r.v.population)) { a += r.v.poverty * r.v.population; w += r.v.population; }
      return w ? a / w : null;
    })();
    // A rate's axis runs from 0 to just above the highest rate (the next 5%), so low rates still spread over the
    // bins; any other unit spans the data.
    const povVals = counties.rows.map((r) => r.v.poverty).filter(fin);
    const povMax = isRate ? Math.max(0.05, Math.ceil(Math.max(...povVals) * 20) / 20) : Math.max(...povVals);
    const povDom = isRate ? [0, povMax] : [Math.min(...povVals), povMax];
    const hasInc = any(counties, (r) => r.v.income);
    povHist = histogram(pHost, {
      values: counties.rows.map((r) => ({ key: r.key, v: r.v.poverty, w: r.v.population })), bins: 30, domain: povDom, height: 120,
      fmt: (v) => fmtShort(povFmt, v), unitLabel: "個鄉鎮市區", label: `鄉鎮市區${povLabel}直方圖`,
      colorOf: (_, t) => colorScale({ type: "seq", domain: [0, 1], ramp: RAMPS.heat })(worseHigh ? t : 1 - t),
      // The population-weighted mean of a rate is the national rate; of any other measure it is only an average.
      markers: fin(avgPov) ? [{ v: avgPov, label: isRate ? `全國 ${pct(avgPov)}` : `人口加權平均 ${fmtShort(povFmt, avgPov)}` }] : [],
      onHover: (bin) => link.hover(bin ? rowsHighlight(counties, bin.keys.map((k) => counties.byKey.get(k)), { dim: true }) : null),
    });
    const povTable = createTable(pBody, {
      caption: `鄉鎮市區${povLabel}`, rank: true, maxHeight: 240, rows: counties.rows.filter((r) => fin(r.v.poverty)), search: "搜尋鄉鎮市區",
      columns: [
        { key: "name", label: "鄉鎮市區", align: "l", value: (r) => r.name, html: nameHtml },
        { key: "population", label: "人口", value: (r) => r.v.population, text: (r) => count3(r.v.population) },
        { key: "poverty", label: povLabel, value: (r) => r.v.poverty, text: (r) => fmtCell(povFmt, r.v.poverty), bar: { max: povMax, color: "rgba(232,119,74,.4)" } },
        ...(hasInc ? [{ key: "income", label: lab("income", "所得"), value: (r) => r.v.income, text: (r) => fmtCell(counties.field("income")?.format || "usd", r.v.income) }] : []),
      ],
      sort: { key: "poverty", dir: worseHigh ? "desc" : "asc" },
      onHover: (r) => link.hover(r ? rowsHighlight(counties, [r]) : null),
      onClick: (r) => counties.focus(r),
    });
    ctx.cleanup(() => povTable.destroy());
  }

  // --- rent -----------------------------------------------------------------------------------------------------
  const hasRent = any(metros, (r) => r.v.rent_burden);
  if (!hasRent) missing.push("租金");
  else {
    // With no city over the population floor, rank them all rather than none.
    const rMin = topBy(metros.rows, (r) => r.v.rent_burden, { n: 1, min: METRO_MIN }).length ? METRO_MIN : 0;
    const rBody = section(el, { title: "各城市的租金負擔", note: `租金中位數 × 12 ÷ ${INCOME}${rMin ? `，只列人口 ${compact(rMin)}以上的城市` : ""}。這是兩個中位數相除：租屋者的所得通常低於整體的中位數，實際負擔會更重。` });
    const rentRows = (list) => list.map((x) => ({ key: x.r.key, label: x.r.name, sub: fin(x.r.v.median_rent) ? `每月 ${dollars(x.r.v.median_rent)}` : "", value: x.v, text: pct(x.v), row: x.r }));
    const rOpts = { onHover: (r) => link.hover(r ? rowsHighlight(metros, [r.row]) : null), onClick: (r) => metros.focus(r.row) };
    const hi = topBy(metros.rows, (r) => r.v.rent_burden, { n: 10, min: rMin });
    const lo = topBy(metros.rows, (r) => r.v.rent_burden, { n: 5, min: rMin, asc: true });
    const rmax = Math.max(...hi.map((x) => x.v));
    rBody.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">負擔最重</h4>`);
    barList(rBody, { ...rOpts, rows: rentRows(hi), max: rmax, ariaLabel: "租金負擔最重" });
    rBody.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">負擔最輕</h4>`);
    barList(rBody, { ...rOpts, rows: rentRows(lo), max: rmax, ariaLabel: "租金負擔最輕" });
  }

  // --- unemployment ---------------------------------------------------------------------------------------------
  const uLevels = [any(states, (r) => r.v.unemployment) && "states", any(metros, (r) => r.v.unemployment) && "metros"].filter(Boolean);
  if (!uLevels.length) missing.push("失業率");
  else {
    const uBody = section(el, { title: "失業率", note: `失業人口 ÷ 勞動力（${esc(data.vintage)}）。城市只列人口 ${compact(BIG_METRO)}以上者；沒有數值的地區不列入。` });
    const uHost = document.createElement("div");
    let uLevel = uLevels[0];
    if (uLevels.length > 1) segmented(uBody, { label: "範圍", value: uLevel, options: [{ value: "states", label: "縣市" }, { value: "metros", label: "大城市" }], onChange: (v) => { uLevel = v; drawU(); } });
    uBody.appendChild(uHost);
    const drawU = () => {
      uHost.innerHTML = "";
      const lvU = uLevel === "states" ? states : metros;
      const min = uLevel === "states" ? 0 : BIG_METRO;
      const high = topBy(lvU.rows, (r) => r.v.unemployment, { n: 8, min });
      const low = topBy(lvU.rows, (r) => r.v.unemployment, { n: 8, min, asc: true });
      if (!high.length) { uHost.innerHTML = `<p class="adv-empty">無資料</p>`; return; }
      const max = Math.max(...high.map((x) => x.v));
      const tone = (v) => (!fin(n.unemployment) ? null : v > n.unemployment * 1.03 ? "bad" : v < n.unemployment * 0.97 ? "good" : null);
      const mk = (list) => list.map((x) => ({ key: x.r.key, label: x.r.name, sub: "", value: x.v, text: pct(x.v), tone: tone(x.v), row: x.r }));
      const o = { max, onHover: (r) => link.hover(r ? rowsHighlight(lvU, [r.row]) : null), onClick: (r) => lvU.focus(r.row) };
      uHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">最高</h4>`);
      barList(uHost, { ...o, rows: mk(high), ariaLabel: "失業率最高" });
      uHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">最低</h4>`);
      barList(uHost, { ...o, rows: mk(low), ariaLabel: "失業率最低" });
    };
    drawU();
  }

  if (!headline.length && !affLevels.length && !hasPoverty && !hasRent && !uLevels.length) {
    el.insertAdjacentHTML("beforeend", `<p class="adv-empty pad">無資料</p>`);
  }

  const srcIds = [
    ...(fin(n.median_income) ? [metros.field("median_income")?.source] : []),
    ...affLevels.flatMap((k) => (k === "counties" ? [counties.field("income")?.source, counties.field("home_value")?.source] : [metros.field("median_income")?.source, metros.field("home_value")?.source])),
    ...(hasPoverty ? [counties.field("poverty")?.source] : []),
    ...(hasRent ? [metros.field("median_rent")?.source, metros.field("rent_burden")?.source] : []),
    ...(uLevels.length ? [metros.field("unemployment")?.source, states.field("unemployment")?.source] : []),
  ];
  el.insertAdjacentHTML("beforeend", sourcesHtml(data, srcIds, [
    ...(missing.length ? [`這份資料沒有${missing.join("、")}的數值，相關的圖表因此沒有顯示。`] : []),
    ...(affLevels.length ? ["房價 ÷ 所得是兩個中位數相除，兩者的統計對象並不相同：適合比較各地的相對高低，不代表個別家戶實際要花幾年所得買房。"] : []),
    ...(affLevels.length === 1 && affLevels[0] === "counties" ? ["城市與縣市沒有房價數值，房價與所得的對照只有鄉鎮市區。"] : []),
    ...(affLevels.length === 1 && affLevels[0] === "counties" && any(counties, (r) => r.v.home_sales) ? [`${esc(lab("home_sales", "交易筆數"))}少的鄉鎮市區，房價中位數容易被少數幾筆交易左右，倍數僅供參考。`] : []),
    ...(affLevels.includes("counties") && affLevels.includes("metros") ? [`縣市與城市的數字為「${esc(data.vintage)}」；鄉鎮市區的數字為「${esc(data.countyVintage)}」，年份可能不同。`] : []),
    ...(hasRent ? ["租金 ÷ 所得是兩個統計對象不同的中位數相除，只能當作粗略的參考，不是租屋者實際負擔的比例。"] : []),
    ...(uLevels.length && uLevels.some((k) => data.levels[k].rows.some((r) => !fin(r.v.unemployment))) ? ["部分地區沒有失業率數值，排名不包含它們。"] : []),
    ...(data.countiesOffMap && (affLevels.includes("counties") || hasPoverty) ? [`有 ${int(data.countiesOffMap)} 個最小的鄉鎮市區不足一個六角格，選取它們時地圖上不會圈出任何範圍。`] : []),
  ]));

  return {
    onMapHover(h) {
      if (scatter) {
        const r = h.cell >= 0 ? lv().rowAtCell(h.cell) : null;
        scatter.setHot(r ? r.key : null);
        affTable.setHot(r ? r.key : null);
      }
      if (povHist && counties) {
        const c = h.cell >= 0 ? counties.rowAtCell(h.cell) : null;
        povHist.setHot(c ? povHist.binOf(c.v.poverty)?.i ?? null : null);
      }
    },
    onEscape() {
      if (scatter?.selected) { clearSel(); return true; }
      return false;
    },
  };
}
