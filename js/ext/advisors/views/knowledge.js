// Knowledge advisor: degrees, broadband and the Science yield.
// County (鄉鎮市區) sections need their counties.json column to have values: a build without broadband or income
// hides those charts, and the distribution chart then shows degrees instead of broadband. Each column is labelled
// and formatted by its own field metadata (label, unit, format): the ids are inherited from the US build, and in
// the Taiwan build `broadband` is a mobile download speed in Mbps, not a share of households.
import { esc, fin, ratio, colorScale, robustDomain, RAMPS } from "../core/util.js";
import { pct, int, compact, count3, fmtShort, fmtCell } from "../core/fmt.js";
import { barList, histogram, rampLegend } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { createScatter } from "../core/scatter.js";
import { section, tiles, segmented, mapPicker, frameBtn, sourcesHtml, topBy } from "../core/view.js";
import { rowsHighlight } from "../core/data.js";
import { scienceLens } from "../core/lenses.js";
import { hasCJK, CURRENCY } from "../../../format.js";

const METRO_MIN = 100000; // Taiwan: every 縣市 but 連江 (1.4萬人)
const LEVEL_NAME = { counties: "鄉鎮市區", metros: "城市" };
// City income when the data gives the measure no Chinese label: the median total income per tax unit on filed returns.
const INCOME_ZH = "申報戶所得中位數";

export function mount(ctx) {
  const { app, data, el, link } = ctx;
  const n = data.nat;
  const nation = app.data.nation;
  const { metros, counties } = data.levels;
  const INCOME = ((l) => (l && hasCJK(l) ? l : INCOME_ZH))(metros.field("median_income")?.label);
  const sci = nation.yields?.find((y) => y.key === "science");
  const sciName = sci?.label || "科研";
  const usSci = n.yields?.science;
  const usShare = ratio(usSci, n.employed);
  const has = (k) => !!counties && counties.rows.some((r) => fin(r.v[k]));
  const hasLens = (id) => !!app.lensById?.has(id);
  // A column's own label from counties.json when it is Chinese, else ours.
  const lab = (k, zh) => { const l = counties?.field(k)?.label; return l && hasCJK(l) ? l : zh; };
  const degLabel = lab("bachelors", "大學以上學歷"), bbLabel = lab("broadband", "寬頻上網");
  const fmtOf = (k) => counties?.field(k)?.format || "pct";
  // A short unit to print after a value that is not a share: the field's unit when brief, or its trailing
  // parenthesis ("行動網路平均下載速率（Mbps）" → Mbps).
  const unitOf = (k) => {
    if (fmtOf(k) === "pct") return "";
    const u = String(counties?.field(k)?.unit || ""), m = /（([^（）]{1,8})）$/.exec(u);
    return u.length <= 8 ? u : m ? m[1] : "";
  };
  const cell = (k, v) => (fin(v) ? `${fmtCell(fmtOf(k), v)}${unitOf(k) ? ` ${unitOf(k)}` : ""}` : "–");
  // The 縣市 a 鄉鎮市區 belongs to, by name; a city row needs no such suffix.
  const stName = new Map((app.w.raw.states || []).flatMap((s) => [[s.abbr, s.name], [s.fips, s.name]]));
  const parentOf = (r) => (r.level === "counties" ? stName.get(r.v.state) || stName.get(String(r.key).slice(0, 5)) || "" : "");
  const wavg = (k) => {
    if (!counties) return null;
    let a = 0, w = 0;
    for (const r of counties.rows) if (fin(r.v[k]) && fin(r.v.population)) { a += r.v[k] * r.v.population; w += r.v.population; }
    return w ? a / w : null;
  };

  el.insertAdjacentHTML("beforeend", tiles([
    { label: `${sciName}就業人口`, value: count3(usSci), sub: fin(usShare) ? `占就業人口 ${pct(usShare)}` : "", color: sci?.color },
    ...(has("bachelors") ? [{ label: degLabel, value: cell("bachelors", wavg("bachelors")), sub: "鄉鎮市區人口加權平均" }] : []),
    ...(has("broadband") ? [{ label: bbLabel, value: cell("broadband", wavg("broadband")), sub: "鄉鎮市區人口加權平均" }] : []),
  ]));

  // --- the map: degrees by default (the scatter's x axis), or the Science yield's share by city -----------------
  const mapRow = document.createElement("div");
  mapRow.className = "adv-sec adv-mapsec";
  el.appendChild(mapRow);
  const degLens = !!counties && hasLens("bachelors"), bbLens = !!counties && hasLens("broadband");
  const picker = mapPicker(ctx, mapRow, {
    value: degLens ? "bachelors" : "science", label: "地圖",
    options: [
      ...(degLens ? [{ value: "bachelors", label: degLabel, lens: () => "bachelors" }] : []),
      { value: "science", label: `${sciName}就業`, lens: () => scienceLens(data) },
      ...(bbLens ? [{ value: "broadband", label: bbLabel, lens: () => "broadband" }] : []),
      { value: "terrain", label: "地形", lens: () => null },
    ],
  });

  // --- science yield --------------------------------------------------------------------------------------------
  // A description from the data, followed by a space unless it already ends in Chinese punctuation.
  const lead = (d) => (d ? esc(d) + (/[。！？；）]$/.test(d) ? "" : " ") : "");
  const sBody = section(el, { title: `${sciName}產出`, note: `${lead(sci?.description)}占比排名只列人口 ${compact(METRO_MIN)}以上的城市。` });
  const sHost = document.createElement("div");
  let mode = "share";
  segmented(sBody, { label: "排序依據", value: mode, options: [{ value: "share", label: "就業占比" }, { value: "abs", label: "人數最多" }], onChange: (v) => { mode = v; drawSci(); } });
  const sMap = document.createElement("button");
  sMap.type = "button";
  sMap.className = "adv-mini";
  sMap.textContent = `以${sciName}就業為地圖上色`;
  sMap.addEventListener("click", () => picker.set("science"));
  sBody.querySelector(".adv-seg")?.after(sMap);
  sBody.appendChild(sHost);
  const share = (r) => ratio(r.v.y_science, r.v.employed);
  function drawSci() {
    sHost.innerHTML = "";
    const list = mode === "abs" ? topBy(metros.rows, (r) => r.v.y_science, { n: 12 }) : topBy(metros.rows, share, { n: 12, min: METRO_MIN });
    if (!list.length) { sHost.innerHTML = `<p class="adv-empty">無資料</p>`; return; }
    const vsNation = (r) => (fin(share(r)) && usShare > 0 ? `全國的 ${(share(r) / usShare).toFixed(2)} 倍` : "");
    barList(sHost, {
      rank: true, ariaLabel: `${sciName}就業排名`,
      rows: list.map((x) => ({ key: x.r.key, label: x.r.name, sub: mode === "abs" ? (fin(share(x.r)) ? pct(share(x.r)) : "") : vsNation(x.r), value: x.v, text: mode === "abs" ? count3(x.v) : pct(x.v), color: sci?.color, row: x.r })),
      onHover: (r) => link.hover(r ? rowsHighlight(metros, [r.row]) : null),
      onClick: (r) => metros.focus(r.row),
    });
  }
  drawSci();

  const sciSrc = [metros.field("y_science")?.source, metros.field("employed")?.source];
  if (!counties) {
    el.insertAdjacentHTML("beforeend", `<p class="adv-empty pad">尚未建置 counties.json，因此沒有鄉鎮市區圖表。</p>`);
    el.insertAdjacentHTML("beforeend", sourcesHtml(data, sciSrc, []));
    return {};
  }

  // --- degrees vs income ----------------------------------------------------------------------------------------
  const incOf = (r) => (r.level === "counties" ? r.v.income : r.v.median_income);
  const degLevels = ["counties", "metros"].filter((k) => data.levels[k].rows.some((r) => fin(r.v.bachelors) && fin(incOf(r))));
  let level = degLevels[0] || "counties";
  const lv = () => data.levels[level];
  let scatter = null;
  const selInfo = document.createElement("div");
  selInfo.className = "adv-brushinfo";
  const clearSel = () => { scatter?.setSelected(null); link.base(null); selInfo.innerHTML = ""; };
  const bbOn = has("broadband");
  const incLabelOf = (k) => (k === "counties" ? lab("income", "所得") : INCOME);
  if (degLevels.length) {
    const dBody = section(el, { title: "學歷與所得", note: `${esc(degLabel)}對所得${bbOn ? `；顏色為${esc(bbLabel)}` : ""}。拖曳可選取；將游標移到地圖上，可在圖中找到對應的地區。` });
    const dCtl = document.createElement("div");
    dCtl.className = "adv-row";
    dBody.appendChild(dCtl);
    if (degLevels.length > 1) segmented(dCtl, { label: "地區", value: level, options: degLevels.map((k) => ({ value: k, label: LEVEL_NAME[k] })), onChange: (v) => { level = v; drawDeg(); } });
    const bbDom = robustDomain(counties.rows.map((r) => r.v.broadband), 0.02) || [0, 1];
    const bbColor = colorScale({ type: "seq", domain: bbDom, ramp: RAMPS.seq });
    scatter = createScatter(dBody, {
      height: 300, points: [],
      x: { label: degLabel, fmt: (v) => fmtShort(fmtOf("bachelors"), v) },
      y: { label: `${incLabelOf(level)}（${CURRENCY}）`, fmt: compact, log: true },
      size: { label: "人口", fmt: count3, max: 14, min: 1.4 },
      ...(bbOn ? { color: (c) => bbColor(c), colorLabel: bbLabel, colorFmt: (v) => cell("broadband", +v) } : {}),
      onHover: (p) => link.hover(p ? rowsHighlight(lv(), [p.row]) : null),
      onClick: (p) => lv().focus(p.row),
      onBrush: (set) => {
        const sel = set ? lv().rows.filter((r) => set.has(r.key)) : [];
        link.base(sel.length ? rowsHighlight(lv(), sel, { dim: true }) : null, { frame: sel.length > 1 });
        selInfo.innerHTML = sel.length ? `已選取 <b>${int(sel.length)}</b> 個${LEVEL_NAME[level]} · 人口 ${count3(sel.reduce((a, r) => a + (r.v.population || 0), 0))} ${frameBtn()}<button type="button" class="adv-mini" data-clear>清除</button>` : "";
      },
    });
    if (bbOn) dBody.insertAdjacentHTML("beforeend", rampLegend({ ramp: RAMPS.seq, domain: bbDom, fmt: (v) => fmtShort(fmtOf("broadband"), v), label: `${bbLabel}${unitOf("broadband") ? `（${unitOf("broadband")}）` : ""}` }));
    dBody.appendChild(selInfo);
    selInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) clearSel(); });
    drawDeg();
  }
  function drawDeg() {
    clearSel();
    const rows = lv().rows;
    scatter.update({
      y: { label: `${incLabelOf(level)}（${CURRENCY}）`, fmt: compact, log: true },
      points: rows.map((r) => ({ key: r.key, x: r.v.bachelors, y: incOf(r), s: r.v.population, c: r.v.broadband, label: r.name, sub: parentOf(r), row: r })),
      labels: topBy(rows, (r) => r.v.population, { n: 6 }).map((x) => x.r.key),
    });
  }

  // --- distribution: broadband, or degrees when the build has no broadband column --------------------------------
  const distKey = bbOn ? "broadband" : has("bachelors") ? "bachelors" : null;
  let distHist = null;
  if (distKey) {
    const isBb = distKey === "broadband";
    const distLabel = isBb ? bbLabel : degLabel;
    const desc = counties.field(distKey)?.description;
    const distFmt = fmtOf(distKey), distUnit = unitOf(distKey);
    const bBody = section(el, { title: `${distLabel}的分布`, note: `各鄉鎮市區的${esc(distLabel)}${distUnit ? `（${esc(distUnit)}）` : ""}。${desc && hasCJK(desc) ? lead(desc) : ""}將游標移到長條上可圈出這些鄉鎮市區。` });
    const bHost = document.createElement("div");
    bBody.appendChild(bHost);
    // The axis spans the data; a share is widened to whole 5% steps.
    const vals = counties.rows.map((r) => r.v[distKey]).filter(fin);
    const dom = distFmt === "pct"
      ? [Math.max(0, Math.floor(Math.min(...vals) * 20) / 20), Math.min(1, Math.max(0.05, Math.ceil(Math.max(...vals) * 20) / 20))]
      : [Math.min(...vals), Math.max(...vals)];
    if (dom[1] <= dom[0]) dom[1] = dom[0] + (distFmt === "pct" ? 0.05 : 1);
    distHist = histogram(bHost, {
      values: counties.rows.map((r) => ({ key: r.key, v: r.v[distKey] })), bins: 30, domain: dom, height: 120,
      fmt: (v) => fmtShort(distFmt, v), unitLabel: "個鄉鎮市區", label: `鄉鎮市區${distLabel}直方圖`,
      colorOf: (_, t) => colorScale({ type: "seq", domain: [0, 1], ramp: RAMPS.seq })(t),
      onHover: (bin) => link.hover(bin ? rowsHighlight(counties, bin.keys.map((k) => counties.byKey.get(k)), { dim: true }) : null),
    });
    createTable(bBody, {
      caption: `鄉鎮市區${distLabel}`, rank: true, maxHeight: 240, search: "搜尋鄉鎮市區",
      rows: counties.rows.filter((r) => fin(r.v[distKey])),
      columns: [
        { key: "name", label: "鄉鎮市區", align: "l", value: (r) => r.name, html: (r) => `${esc(r.name)}${parentOf(r) ? ` <span class="sub">${esc(parentOf(r))}</span>` : ""}` },
        { key: "population", label: "人口", value: (r) => r.v.population, text: (r) => count3(r.v.population) },
        { key: distKey, label: distLabel, value: (r) => r.v[distKey], text: (r) => cell(distKey, r.v[distKey]), bar: { max: dom[1], color: "rgba(74,134,214,.4)" } },
        ...(isBb && has("bachelors") ? [{ key: "bachelors", label: degLabel, value: (r) => r.v.bachelors, text: (r) => cell("bachelors", r.v.bachelors) }] : []),
      ],
      sort: { key: distKey, dir: isBb ? "asc" : "desc" },
      onHover: (r) => link.hover(r ? rowsHighlight(counties, [r]) : null),
      onClick: (r) => counties.focus(r),
    });
  }

  const countySrc = ["bachelors", "broadband", ...(degLevels.length ? ["income"] : [])].filter(has).map((k) => counties.field(k)?.source);
  el.insertAdjacentHTML("beforeend", sourcesHtml(data, [...sciSrc, ...countySrc, ...(degLevels.includes("metros") ? [metros.field("median_income")?.source] : [])], [
    `${esc(sciName)}就業地圖只為各城市的範圍上色（灰色六角格不屬於任何城市）。`,
    ...(distKey || degLevels.length ? [`${esc(degLabel)}${bbOn ? `與${esc(bbLabel)}` : ""}是鄉鎮市區的數字（${esc(data.countyVintage)}）${degLevels.includes("metros") ? "；這裡的城市數值由所屬鄉鎮市區按人口加權彙總而得，是近似值" : ""}。`] : []),
    ...(!degLevels.length && has("bachelors") ? ["這份資料沒有所得數值，因此沒有「學歷與所得」的對照圖。"] : []),
    ...(data.countiesOffMap ? [`有 ${int(data.countiesOffMap)} 個最小的鄉鎮市區不足一個六角格，選取它們時地圖上不會圈出任何範圍。`] : []),
  ]));

  return {
    onMapHover(h) {
      if (scatter) {
        const r = h.cell >= 0 ? lv().rowAtCell(h.cell) : null;
        scatter.setHot(r ? r.key : null);
      }
      if (distHist) {
        const c = h.cell >= 0 ? counties.rowAtCell(h.cell) : null;
        distHist.setHot(c ? distHist.binOf(c.v[distKey])?.i ?? null : null);
      }
    },
    onEscape() {
      if (scatter?.selected) { clearSel(); return true; }
      return false;
    },
  };
}
