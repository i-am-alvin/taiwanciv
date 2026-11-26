// Land advisor: national land cover, where each cover dominates, the states' (縣市) make-up and who works the land.
import { esc, fin, ratio } from "../core/util.js";
import { pct, int, compact, count3 } from "../core/fmt.js";
import { shareBar, barList, donut, smallMultiples } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { section, tiles, segmented, lensButton, sourcesHtml, topBy, frameBtn } from "../core/view.js";
import { LAND_KEYS, LAND_LABEL, LAND_COLOR, rowsHighlight } from "../core/data.js";

const LENS_OF = { forest: "forest", crop: "farmland", pasture: "farmland", developed: "developed" };
const FOOD_MIN = 100000; // cities in the farm-worker ranking

export function mount(ctx) {
  const { app, data, el, link } = ctx;
  const w = app.w;
  const P = w.raw.pct;
  const owner = w.raw.owner;
  const { states } = data.levels;
  if (!P) {
    el.innerHTML = `<p class="adv-empty pad">world.json 沒有地表覆蓋比例。</p>`;
    return {};
  }
  // The land-cover source as the data names it (sources.json), for the notes below.
  const landSrcId = states.field(`land_${LAND_KEYS[0]}`)?.source || app.lensById?.get("forest")?.source || "";
  const landSrc = data.source(landSrcId);
  const landSrcText = landSrc?.title || "";

  // --- national shares and dominant cover per hex ---------------------------------------------------------------
  const sums = Object.fromEntries(LAND_KEYS.map((k) => [k, 0]));
  const dominant = new Map(LAND_KEYS.map((k) => [k, []]));
  let cells = 0;
  for (let i = 0; i < w.grid.size; i++) {
    if (!(owner[i] >= 0)) continue;
    let tot = 0, best = null, bv = 0;
    for (const k of LAND_KEYS) {
      const v = P[k]?.[i] || 0;
      tot += v;
      if (v > bv) { bv = v; best = k; }
    }
    if (tot <= 0) continue; // no land-cover samples
    cells++;
    for (const k of LAND_KEYS) sums[k] += P[k]?.[i] || 0;
    dominant.get(best).push(i);
  }
  const share = Object.fromEntries(LAND_KEYS.map((k) => [k, cells ? sums[k] / (cells * 100) : 0]));
  const other = Math.max(0, 1 - LAND_KEYS.reduce((a, k) => a + share[k], 0));

  el.insertAdjacentHTML("beforeend", tiles([
    { label: LAND_LABEL.forest, value: pct(share.forest, 0), sub: "占全國土地", color: LAND_COLOR.forest },
    { label: "農牧用地", value: pct(share.crop + share.pasture, 0), sub: `${LAND_LABEL.crop}＋${LAND_LABEL.pasture}`, color: LAND_COLOR.crop },
    { label: LAND_LABEL.developed, value: pct(share.developed, 1), sub: "已開發土地", color: LAND_COLOR.developed },
  ]));

  // --- composition ----------------------------------------------------------------------------------------------
  const cBody = section(el, { title: "這片土地上有什麼", kicker: "全國", note: `各類地表覆蓋占土地的比例（${landSrcText ? `${esc(landSrcText)}；` : ""}所有六角格的平均）。將游標移到某一類上，會點亮以它為最大宗的六角格；點擊可保持點亮。` });
  let pinned = null;
  const parts = [...LAND_KEYS.map((k) => ({ key: k, label: LAND_LABEL[k], value: share[k], color: LAND_COLOR[k], text: pct(share[k]) })), { key: "other", label: "其他（裸露地等）", value: other, color: "#6c6358", text: pct(other) }].sort((a, b) => (a.key === "other") - (b.key === "other") || b.value - a.value);
  const domHighlight = (k, dim = true) => (dominant.has(k) ? { cells: new Set(dominant.get(k)), dimOthers: dim, color: LAND_COLOR[k] } : null);
  const sb = shareBar(cBody, {
    parts,
    onHover: (p) => link.hover(p && p.key !== "other" ? { ...domHighlight(p.key), color: "#fff3c4" } : null),
    onClick: (p) => pin(p.key === "other" || pinned === p.key ? null : p.key),
  });
  const pinInfo = document.createElement("div");
  pinInfo.className = "adv-brushinfo";
  cBody.appendChild(pinInfo);
  const lensRow = document.createElement("div");
  lensRow.className = "adv-row";
  // The lens buttons carry the lens's own name: its numbers may come from another source than the hex land cover.
  const lensIds = ["forest", "farmland", "developed"].filter((id) => app.lensById?.has(id));
  for (const id of lensIds) {
    const b = lensButton(app, id, `${app.lensById.get(id).name}濾鏡`);
    if (b) lensRow.appendChild(b);
  }
  const lensSrc = [...new Set(lensIds.map((id) => app.lensById.get(id).source).filter((s) => s && s !== landSrcId))];
  cBody.appendChild(lensRow);
  function pin(k) {
    pinned = k;
    sb.setSelected(k);
    link.base(k ? domHighlight(k) : null, { frame: true });
    if (!k) { pinInfo.innerHTML = ""; return; }
    const n = dominant.get(k).length;
    const lens = LENS_OF[k] && app.lensById?.get(LENS_OF[k]);
    pinInfo.innerHTML = `<b>${esc(LAND_LABEL[k])}</b>是 <b>${int(n)}</b> 個六角格上面積最大的覆蓋類型（占陸地六角格的 ${pct(n / cells, 0)}），並覆蓋全部土地的 ${pct(share[k])}。
      ${lens ? `<button type="button" class="adv-mini" data-lens="${lens.id}">顯示「${esc(lens.name)}」濾鏡</button>` : ""}${frameBtn()}<button type="button" class="adv-mini" data-clear>清除</button>`;
  }
  pinInfo.addEventListener("click", (e) => {
    if (e.target.closest("[data-clear]")) pin(null);
    const l = e.target.closest("[data-lens]")?.dataset.lens;
    if (l) app.setLens(l);
  });

  // --- per state ------------------------------------------------------------------------------------------------
  const sBody = section(el, { title: "各縣市的土地組成", note: "各縣市的土地依覆蓋類型劃分。可依任一類型排序；將游標移到縣市上可圈出它，點擊則開啟該縣市。" });
  const stRows = states.rows.filter((r) => LAND_KEYS.some((k) => fin(r.v[`land_${k}`])));
  const comp = (r) => `<span class="adv-minibar">${LAND_KEYS.map((k) => {
    const v = r.v[`land_${k}`];
    return fin(v) && v > 0 ? `<i style="width:${(v * 100).toFixed(2)}%;background:${LAND_COLOR[k]}" title="${esc(`${LAND_LABEL[k]} ${pct(v)}`)}"></i>` : "";
  }).join("")}</span>`;
  const domOf = (r) => LAND_KEYS.reduce((b, k) => ((r.v[`land_${k}`] ?? -1) > (r.v[`land_${b}`] ?? -1) ? k : b), LAND_KEYS[0]);
  let sortKey = "forest";
  const colsFor = (k) => [
    { key: "name", label: "縣市", align: "l", width: "minmax(0,1.1fr)", value: (r) => r.name, text: (r) => r.name },
    { key: "comp", label: "土地組成", align: "l", width: "minmax(0,1.6fr)", value: (r) => r.v[`land_${k}`], html: comp, title: `依${LAND_LABEL[k]}排序` },
    { key: "share", label: LAND_LABEL[k], value: (r) => r.v[`land_${k}`], html: (r) => `<span class="dot" style="background:${LAND_COLOR[k]}"></span>${pct(r.v[`land_${k}`], 0)}` },
    { key: "dom", label: "最大宗", align: "l", width: "minmax(0,.9fr)", value: (r) => LAND_LABEL[domOf(r)], text: (r) => LAND_LABEL[domOf(r)] },
  ];
  const sortSeg = document.createElement("div");
  sortSeg.className = "adv-row";
  sBody.appendChild(sortSeg);
  segmented(sortSeg, {
    label: "排序依據", value: sortKey,
    options: LAND_KEYS.map((k) => ({ value: k, label: LAND_LABEL[k] })),
    onChange: (k) => { sortKey = k; table.setColumns(colsFor(k), { key: "share", dir: "desc" }); drawShape(); },
  });
  let shape = "table";
  segmented(sortSeg, { label: "顯示方式", value: shape, options: [{ value: "table", label: "表格" }, { value: "grid", label: "圓環圖" }], onChange: (v) => { shape = v; drawShape(); } });
  const tableHost = document.createElement("div");
  const gridHost = document.createElement("div");
  sBody.append(tableHost, gridHost);
  const table = createTable(tableHost, {
    caption: "各縣市的地表覆蓋", rank: true, maxHeight: 320, rows: stRows, columns: colsFor(sortKey), sort: { key: "share", dir: "desc" },
    onHover: (r) => link.hover(r ? rowsHighlight(states, [r]) : null),
    onClick: (r) => states.focus(r),
  });
  // Small multiples: one donut per state, sorted by the chosen cover. The tile carries the 縣市 name (three
  // characters), which reads better than its ISO code.
  let grid = null;
  function drawShape() {
    tableHost.hidden = shape !== "table";
    gridHost.hidden = shape !== "grid";
    if (shape !== "grid") return;
    gridHost.innerHTML = "";
    const sorted = [...stRows].sort((a, b) => (b.v[`land_${sortKey}`] ?? -1) - (a.v[`land_${sortKey}`] ?? -1));
    grid = smallMultiples(gridHost, {
      min: 92,
      items: sorted.map((r) => ({ key: r.key, label: r.name || r.v.abbr || r.key, sub: pct(r.v[`land_${sortKey}`], 0), row: r })),
      render: (cell, it) => donut(cell, {
        interactive: false, size: 62, thickness: 12,
        parts: LAND_KEYS.map((k) => ({ key: k, label: LAND_LABEL[k], value: it.row.v[`land_${k}`], color: LAND_COLOR[k] })),
        center: { big: pct(it.row.v[`land_${sortKey}`], 0), small: "" },
        ariaLabel: `${it.row.name}：${LAND_KEYS.map((k) => `${LAND_LABEL[k]} ${pct(it.row.v[`land_${k}`], 0)}`).join("、")}`,
      }),
      onHover: (it) => link.hover(it ? rowsHighlight(states, [it.row]) : null),
      onClick: (it) => states.focus(it.row),
    });
  }
  drawShape();

  // --- who works the land ---------------------------------------------------------------------------------------
  const food = app.data.nation.yields?.find((y) => y.key === "food");
  const foodDesc = food?.description || "農、林、漁、牧業的就業人口。";
  const fBody = section(el, { title: "誰在耕作這片土地", note: `${esc(foodDesc)}${/[。！？；）]$/.test(foodDesc) ? "" : " "}依占就業人口的比例排名。` });
  const fHost = document.createElement("div");
  let fLevel = "states";
  segmented(fBody, { label: "範圍", value: fLevel, options: [{ value: "states", label: "縣市" }, { value: "metros", label: "城市" }], onChange: (v) => { fLevel = v; drawFood(); } });
  fBody.appendChild(fHost);
  function drawFood() {
    fHost.innerHTML = "";
    const lv = data.levels[fLevel];
    const list = topBy(lv.rows, (r) => ratio(r.v.y_food, r.v.employed), { n: 10, min: fLevel === "metros" ? FOOD_MIN : 0 });
    if (!list.length) { fHost.innerHTML = `<p class="adv-empty">無資料</p>`; return; }
    barList(fHost, {
      rank: true, ariaLabel: "農林漁牧就業人口",
      rows: list.map((x) => ({ key: x.r.key, label: x.r.name, sub: `${count3(x.r.v.y_food)}人`, value: x.v, text: pct(x.v), color: food?.color, row: x.r })),
      onHover: (r) => link.hover(r ? rowsHighlight(lv, [r.row]) : null),
      onClick: (r) => lv.focus(r.row),
    });
    if (fLevel === "metros") fHost.insertAdjacentHTML("beforeend", `<p class="adv-note">只列人口 ${compact(FOOD_MIN)}以上的城市。</p>`);
  }
  drawFood();

  // A hex's width in km: grid units ÷ the projection's units per km (world.json projection.scale; 1 when absent).
  const hexKm = (2 * w.grid.R) / (w.raw.projection?.scale || 1);
  el.insertAdjacentHTML("beforeend", sourcesHtml(data, [landSrcId, ...lensSrc, data.levels.metros.field("y_food")?.source, states.field("employed")?.source], [
    `地表覆蓋${landSrcText ? `（${esc(landSrcText)}）` : ""}重新取樣到六角格（對角約 ${+hexKm.toFixed(1)} 公里），因此小範圍的地物（河谷裡的農田、小聚落）會融入周圍的地表。`,
    "「最大宗」指六角格內占比最高的覆蓋類型，不代表整格都是這一類。",
    ...(lensSrc.length ? [`濾鏡按鈕開啟的是另一份資料（${lensSrc.map((s) => esc(data.source(s)?.title || s)).join("、")}），分類與年份都和這裡的六角格地表覆蓋不同，數字不會一致。`] : []),
    "沒有就業人數的縣市不列入農林漁牧就業排名。",
  ]));

  return {
    onMapHover(h) {
      const r = h.cell >= 0 ? states.rowAtCell(h.cell) : null;
      table.setHot(r ? r.key : null);
      if (shape === "grid") grid?.setHot(r ? r.key : null);
      if (h.cell >= 0 && owner[h.cell] >= 0) {
        let best = null, bv = 0;
        for (const k of LAND_KEYS) { const v = P[k]?.[h.cell] || 0; if (v > bv) { bv = v; best = k; } }
        sb.setHot(best);
      } else sb.setHot(null);
    },
    onEscape() {
      if (pinned) { pin(null); return true; }
      return false;
    },
  };
}
