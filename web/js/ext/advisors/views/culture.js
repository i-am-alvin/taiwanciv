// Culture advisor ("Keeper of Wonders"): wonders by published rule (wonders.json), the Faith and Amenities lenses with
// their caveats (counties.json columns), and disasters (disasters.json: events by area and type, and the record by year).
// Every block is optional: a missing file, lens or column hides its part, and wording comes from the data (lens names,
// units, notes, rule texts) so the view describes whatever the build measures.
import { esc, fin, el as mk, colorScale } from "../core/util.js";
import { int, money, compact, count3, fmtValue, fmtCell } from "../core/fmt.js";
import { barList, shareBar, histogram } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { section, tiles, segmented, mapPicker, sourcesHtml } from "../core/view.js";
import { rowsHighlight, placeLabel } from "../core/data.js";
import { frameBox, focusPoint } from "../core/frame.js";

const KIND = {
  natural: { label: "自然", color: "#6aa84f" },
  recreation: { label: "遊憩區", color: "#8fbf6a" },
  coastal: { label: "海岸", color: "#4fb0a8" },
  monument: { label: "紀念地", color: "#b9a06a" },
  university: { label: "大學", color: "#4a86d6" },
  landmark: { label: "地標", color: "#e0b54c" },
};
// Fallback titles for the rule ids of wonders.json; a `name` / `title` on the rule itself wins.
const RULE_TITLE = { national_park: "國家公園", park_unit: "其他公園", research_university: "研究型大學", landmark: "地標" };
const DIS_COLOR = { hurricane: "#4f9ad6", typhoon: "#4f9ad6", flood: "#2fa4b8", fire: "#e8774a", earthquake: "#b98a5a", severe_storm: "#9a7bc9", winter: "#c9dcef", other: "#9a9aa8" };
const AMEN_MIN_POP = 50000; // the Amenities table lists areas of at least this many people (small ones swing widely)

const hasCJK = (s) => /[㐀-鿿豈-﫿]/.test(String(s ?? ""));
const kindOf = (k) => KIND[k] || { label: String(k ?? ""), color: "#cccccc" };
const ruleTitle = (rule, id) => rule?.name || rule?.title || RULE_TITLE[rule?.id ?? id] || String(rule?.id ?? id ?? "");
const uniq = (list) => [...new Set(list.filter(Boolean))];

export async function mount(ctx) {
  const { app, data, el, link } = ctx;
  const disastersP = app.loadData("disasters").catch(() => null); // lazy: only this advisor needs it
  const won = await app.loadData("wonders").catch(() => null);
  const { states: stLevel, counties } = data.levels;
  const lens = (id, col = id) => { const l = app.lensById?.get(id); return l && counties?.has(col) ? l : null; };
  const lensFaith = lens("faith"), lensTrad = lens("faith_tradition");
  const lensAmen = lens("amenities"), lensDis = lens("disasters");
  const lensFmt = (l) => (v) => fmtValue(l?.format === "category" ? "text" : l?.format || "float", v, l?.unit);

  // A state reference in a data file (code, id or name) as its row / its 縣市 name; unknown values are shown as they are.
  const stIndex = new Map();
  (app.w.raw.states || []).forEach((s, i) => { for (const k of [s?.abbr, s?.fips, s?.name]) if (k != null && !stIndex.has(String(k))) stIndex.set(String(k), i); });
  (app.data.states || []).forEach((s, i) => { for (const k of [s?.abbr, s?.fips, s?.name]) if (k != null && !stIndex.has(String(k))) stIndex.set(String(k), i); });
  const stRowByRef = new Map(stLevel.rows.map((r) => [r.ref, r]));
  const stRow = (ref) => (ref == null ? null : stLevel.byKey.get(ref) || stRowByRef.get(stIndex.get(String(ref))) || null);
  const stName = (ref) => (ref == null || ref === "" ? "" : stRow(ref)?.name || String(ref));

  // --- headline -------------------------------------------------------------------------------------------------
  const wonders = (won?.wonders || []).map((w) => ({ ...w, key: w.id }));
  const rules = won?.rules || [];
  const byKind = (k) => wonders.filter((w) => w.kind === k).length;
  let faithMean = null;
  if (lensFaith) {
    let a = 0, p = 0;
    for (const r of counties.rows) if (fin(r.v.faith) && fin(r.v.population)) { a += r.v.faith * r.v.population; p += r.v.population; }
    faithMean = p ? a / p : null;
  }
  const tileEl = mk("div");
  el.appendChild(tileEl);
  const drawTiles = (dis) => {
    const nat = dis?.noaa?.national, years = (dis?.noaa?.years || []).join("–");
    const list = [
      wonders.length && { label: "奇觀", value: int(wonders.length), sub: rules.map((r) => { const n = wonders.filter((w) => w.rule === r.id).length; return n ? `${ruleTitle(r)} ${int(n)}` : ""; }).filter(Boolean).join(" · ") },
      fin(won?.national?.park_visits) && { label: `${ruleTitle(rules.find((r) => r.id === "national_park"), "national_park")}遊客`, value: `${count3(won.national.park_visits)} 人次`, sub: won.national.park_visits_year ? `${won.national.park_visits_year} 年，全國合計` : "全國合計" },
      fin(nat?.events) && { label: "災害事件", value: int(nat.events), sub: [years ? `${years} 年` : "", fin(nat.cost_usd) ? money(nat.cost_usd) : "", fin(nat.deaths) ? `${int(nat.deaths)} 人死亡` : ""].filter(Boolean).join(" · ") },
      fin(faithMean) && { label: `${lensFaith.name} ≈`, value: lensFmt(lensFaith)(faithMean), sub: [lensFaith.unit, "各鄉鎮市區依人口加權"].filter(Boolean).join(" · ") },
    ].filter(Boolean).slice(0, 3);
    tileEl.innerHTML = list.length ? tiles(list) : "";
  };
  drawTiles(null);

  // --- map colour -----------------------------------------------------------------------------------------------
  const mapOptions = [
    ...(lensFaith ? [{ value: "faith", label: lensFaith.name, lens: () => "faith" }] : []),
    ...(lensTrad ? [{ value: "trad", label: lensTrad.name, lens: () => "faith_tradition" }] : []),
    ...(lensAmen ? [{ value: "amen", label: lensAmen.name, lens: () => "amenities" }] : []),
    ...(lensDis ? [{ value: "dis", label: lensDis.name, lens: () => "disasters" }] : []),
  ];
  let picker = { set() {} };
  if (mapOptions.length) {
    const mapRow = mk("div", "adv-sec adv-mapsec");
    el.appendChild(mapRow);
    picker = mapPicker(ctx, mapRow, { value: "terrain", options: [{ value: "terrain", label: "地形", lens: () => null }, ...mapOptions] });
  }
  let blocks = 0; // sections drawn so far (an empty build gets one line instead of a blank page)

  // --- wonders --------------------------------------------------------------------------------------------------
  let wonderBars = [];
  const bubbles = ctx.bubbles("wonders", {
    rMax: 9, minR: 9, alpha: 0.28,
    tip: (b) => `<b>${esc(b.it.name)}</b><br>${esc(ruleTitle(rules.find((r) => r.id === b.it.rule), b.it.rule) || kindOf(b.it.kind).label)}${fin(b.it.rank) ? ` 第 ${b.it.rank} 名` : ""} · ${esc(metricText(b.it))}${b.it.curated ? `<br><span class="sub">人工挑選，不依數據排名</span>` : ""}`,
    onHover: (b) => { for (const w of wonderBars) w.setHot(b ? b.key : null); },
    onClick: (b) => flyTo(b.it),
  });
  if (wonders.length) {
    blocks++;
    const wBody = section(el, { title: "奇觀", kicker: "各依公布的規則挑選", note: "游標移到奇觀上可在地圖上找到它，點一下就飛到該處。各類的挑選與排名依據寫在各自的規則說明裡。" });
    let kind = "all";
    const kinds = uniq(wonders.map((w) => w.kind));
    if (kinds.length > 1) {
      segmented(wBody, {
        label: "類別", value: kind,
        options: [{ value: "all", label: "全部" }, ...kinds.map((k) => ({ value: k, label: kindOf(k).label }))],
        onChange: (v) => { kind = v; drawWonders(); },
      });
    }
    const wHost = mk("div");
    wBody.appendChild(wHost);
    // Wonders whose rule is not listed in the file still get a list, under their rule id.
    const ruleList = [...rules, ...uniq(wonders.map((w) => w.rule)).filter((id) => !rules.some((r) => r.id === id)).map((id) => ({ id }))];
    function drawWonders() {
      wHost.innerHTML = "";
      wonderBars = [];
      const vis = wonders.filter((w) => kind === "all" || w.kind === kind);
      for (const rule of ruleList) {
        const list = vis.filter((w) => w.rule === rule.id);
        if (!list.length) continue;
        wHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">${esc(ruleTitle(rule))}</h4>${rule.text ? `<p class="adv-note adv-rule">${esc(rule.text)}</p>` : ""}`);
        const host = mk("div");
        wHost.appendChild(host);
        const val = (w) => (w.kind === "university" ? w.metrics?.rd_usd : w.metrics?.visits) ?? null;
        wonderBars.push(barList(host, {
          rank: !rule.curated, compact: true, ariaLabel: ruleTitle(rule),
          rows: list.map((w) => ({ key: w.key, label: w.short || w.name, full: w.name, sub: stName(w.state), value: val(w), text: metricText(w), color: kindOf(w.kind).color })),
          onHover: (r) => {
            const w = r ? wonders.find((x) => x.key === r.key) : null;
            link.hover(w ? { cells: new Set(w.cells && w.cells.length ? w.cells : w.cell != null ? [w.cell] : []), label: w.short || w.name } : null);
            bubbles.setHot(w ? w.key : null);
          },
          onClick: (r) => flyTo(wonders.find((x) => x.key === r.key)),
        }));
      }
      bubbles.set(vis.filter((w) => fin(w.x) && fin(w.y)).map((w) => ({ key: w.key, x: w.x, y: w.y, value: 1, color: kindOf(w.kind).color, it: w })), { vMax: 1 });
    }
    drawWonders();
    wBody.insertAdjacentHTML("beforeend", `<p class="adv-note">地圖標記：${kinds.map((k) => `<i class="dot" style="background:${esc(kindOf(k).color)}"></i>${esc(kindOf(k).label)}`).join(" · ")}</p>`);
  }
  function flyTo(w) {
    if (!w) return;
    if (w.cells && w.cells.length > 2) {
      const b = app.highlightBounds({ cells: new Set(w.cells) });
      if (b) return frameBox(app, b, { pad: 60, maxScale: 3 });
    }
    if (!fin(w.x) || !fin(w.y)) return;
    focusPoint(app, w.x, w.y, Math.min(app.cam.maxScale, Math.max(app.cam.scale, (app.cam.fitScale || 1) * 3.2)));
  }

  // --- faith ----------------------------------------------------------------------------------------------------
  let faithStates = null;
  if (lensFaith || lensTrad) {
    blocks++;
    const fBody = section(el, { title: "信仰", kicker: uniq([lensFaith?.name, lensTrad?.name]).join(" · ") });
    const fNote = lensTrad?.note || lensFaith?.note;
    if (fNote) fBody.insertAdjacentHTML("beforeend", `<p class="adv-callout adv-caveat">${esc(fNote)}</p>`);
    if (lensTrad) {
      const cats = lensTrad.categories || [];
      const catByName = new Map(cats.flatMap((c) => [[c.name, c], [c.id, c]]));
      const popBy = new Map();
      for (const r of counties.rows) {
        const c = catByName.get(r.v.faith_tradition);
        if (c && fin(r.v.population)) popBy.set(c.id, (popBy.get(c.id) || 0) + r.v.population);
      }
      const parts = cats.filter((c) => popBy.get(c.id) > 0);
      if (parts.length) {
        fBody.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">${esc(lensTrad.name)}：各類別所在鄉鎮市區的人口</h4>`);
        const tradRows = (id) => counties.rows.filter((r) => catByName.get(r.v.faith_tradition)?.id === id);
        shareBar(fBody, {
          parts: parts.map((c) => ({ key: c.id, label: c.name, value: popBy.get(c.id), color: c.color, text: `${count3(popBy.get(c.id))} 人` })),
          onHover: (p) => link.hover(p ? rowsHighlight(counties, tradRows(p.key), { dim: true, label: p.label }) : null),
          onClick: () => picker.set("trad"),
        });
        fBody.insertAdjacentHTML("beforeend", `<p class="adv-note">${lensTrad.unit ? `分類依據：${esc(lensTrad.unit)}。` : ""}點一下可讓地圖依此分類上色。</p>`);
      }
    }
    const fRows = lensFaith ? stLevel.rows.filter((r) => fin(r.v.faith)) : [];
    if (fRows.length) {
      let order = "most";
      const fFmt = lensFmt(lensFaith);
      const sRow = mk("div", "adv-row");
      fBody.appendChild(sRow);
      sRow.insertAdjacentHTML("beforeend", `<span class="adv-note" style="margin:0">各縣市${esc(lensFaith.name)}${lensFaith.unit ? `（${esc(lensFaith.unit)}）` : ""} ≈</span>`);
      segmented(sRow, { label: "排序", value: order, options: [{ value: "most", label: "最高" }, { value: "fewest", label: "最低" }], onChange: (v) => { order = v; drawFaith(); } });
      const sHost = mk("div");
      fBody.appendChild(sHost);
      const fMax = Math.max(...fRows.map((r) => r.v.faith), 0) || 1;
      const fColor = colorScale({ type: "seq", domain: lensFaith.domain || [0, fMax], ramp: lensFaith.ramp });
      function drawFaith() {
        sHost.innerHTML = "";
        const list = [...fRows].sort((a, b) => (order === "most" ? b.v.faith - a.v.faith : a.v.faith - b.v.faith)).slice(0, 10);
        faithStates = barList(sHost, {
          rank: true, compact: true, max: fMax, ariaLabel: `各縣市${lensFaith.name}`,
          rows: list.map((r) => ({ key: r.key, label: r.name, value: r.v.faith, text: fFmt(r.v.faith), color: fColor(r.v.faith) })),
          onHover: (x) => link.hover(x ? rowsHighlight(stLevel, [stLevel.byKey.get(x.key)], { dim: true }) : null),
          onClick: (x) => { picker.set("faith"); stLevel.focus(stLevel.byKey.get(x.key)); },
        });
      }
      drawFaith();
      fBody.insertAdjacentHTML("beforeend", `<p class="adv-note">縣市的數字是所屬鄉鎮市區依人口加權的平均（≈），並非該縣市本身的統計數字。</p>`);
    }
  }

  // --- amenities ------------------------------------------------------------------------------------------------
  let amenHist = null, amenTable = null;
  if (lensAmen) {
    const rows = counties.rows.filter((r) => fin(r.v.amenities));
    if (rows.length) {
      blocks++;
      const aBody = section(el, { title: lensAmen.name, kicker: lensAmen.unit || "" });
      aBody.insertAdjacentHTML("beforeend", `${lensAmen.note ? `<p class="adv-callout adv-caveat">${esc(lensAmen.note)}</p>` : ""}${lensAmen.description ? `<p class="adv-note">${esc(lensAmen.description)}</p>` : ""}`);
      const vals = rows.map((r) => r.v.amenities);
      const lo = Math.min(...vals), hi = Math.max(...vals);
      const dom = lensAmen.domain || [lo, hi];
      const padBy = Math.max(1, (dom[1] - dom[0]) * 0.15);
      const mean = vals.reduce((a, v) => a + v, 0) / vals.length;
      const aFmt = lensFmt(lensAmen);
      const aColor = colorScale({ type: "seq", domain: dom, ramp: lensAmen.ramp });
      amenHist = histogram(aBody, {
        values: rows.map((r) => ({ key: r.key, v: r.v.amenities })), bins: 30, domain: [dom[0] - padBy, dom[1] + padBy],
        fmt: (v) => v.toFixed(0), unitLabel: "個鄉鎮市區", label: `各鄉鎮市區「${lensAmen.name}」的直方圖`,
        colorOf: (v) => aColor(v), markers: [{ v: mean, label: "各鄉鎮市區平均" }],
        onHover: (bin) => link.hover(bin ? rowsHighlight(counties, bin.keys.map((k) => counties.byKey.get(k)), { dim: true }) : null),
      });
      const big = rows.filter((r) => (r.v.population || 0) >= AMEN_MIN_POP);
      const tRows = big.length >= 10 ? big : rows;
      // Companion columns, each shown only when counties.json carries it.
      const extra = ["mhlth", "loneliness", "smr"].filter((k) => counties.has(k)).map((k, j) => {
        const f = counties.field(k);
        return { key: k, label: f.label, title: [f.description, f.unit].filter(Boolean).join(" · "), value: (r) => r.v[k], text: (r) => fmtCell(f.format, r.v[k], f.unit), hideBelow: j ? 400 : 0 };
      });
      amenTable = createTable(aBody, {
        caption: `各鄉鎮市區的${lensAmen.name}`, rank: true, maxHeight: 240, search: "搜尋鄉鎮市區",
        rows: tRows,
        columns: [
          { key: "name", label: "鄉鎮市區", align: "l", width: "minmax(0,1.6fr)", value: (r) => r.name, html: (r) => `${esc(r.name)}${r.sub ? ` <span class="sub">${esc(r.sub)}</span>` : ""}` },
          { key: "amenities", label: lensAmen.name, value: (r) => r.v.amenities, text: (r) => aFmt(r.v.amenities), bar: { max: hi, color: "rgba(126,207,142,.3)" }, title: lensAmen.unit || "" },
          ...extra,
        ],
        sort: { key: "amenities", dir: "desc" },
        onHover: (r) => link.hover(r ? rowsHighlight(counties, [r]) : null),
        onClick: (r) => counties.focus(r),
      });
      aBody.insertAdjacentHTML("beforeend", `<p class="adv-note">${tRows === big ? `表中只列人口 ${compact(AMEN_MIN_POP)}人以上的鄉鎮市區；` : ""}沒有數值的地方留白，不以推估補上。</p>`);
    }
  }

  // --- disasters (lazy) -----------------------------------------------------------------------------------------
  const dSec = section(el, { title: "災害" });
  dSec.innerHTML = `<p class="adv-loading">正在讀取災害紀錄…</p>`;
  const srcEl = mk("div");
  el.appendChild(srcEl);
  const drawSources = (dis) => {
    srcEl.innerHTML = sourcesHtml(data, uniq([...(won?.sources || []), lensFaith?.source, lensTrad?.source, lensAmen?.source, ...(dis?.sources || []), lensDis?.source]), [
      ...uniq([lensFaith, lensTrad, lensAmen, lensDis].filter((l) => l?.note).map((l) => `${esc(l.name)}：${esc(l.note)}`)),
      ...(wonders.length ? ["各類奇觀依各自公布的規則挑選與排名，口徑不同，不能跨類別比較；標示為人工挑選的清單不依數據排名。"] : []),
      ...(dis ? ["災害事件的件數反映通報或認定的次數，不等於損失的大小；同一事件可能同時計入多個縣市，各縣市的數字不能直接加總。"] : []),
    ]);
  };
  drawSources(null);
  let dState = null, dCounty = null;
  // The disaster records arrive after the rest of the dashboard is up (the view may be gone by then).
  disastersP.then((dis) => {
    if (!active()) return;
    dSec.innerHTML = "";
    if (dis) drawDisasters(dis);
    // The Disasters lens gets its own list unless the file above already shows the same records.
    if (lensDis && !(dis && (dis.sources || []).includes(lensDis.source))) drawHazardLens();
    if (dSec.childElementCount) blocks++;
    else dSec.closest(".adv-sec")?.remove();
    if (!blocks) srcEl.insertAdjacentHTML("beforebegin", `<p class="adv-empty pad">無資料。</p>`);
    drawTiles(dis);
    drawSources(dis);
  });

  function drawHazardLens() {
    const hFmt = lensFmt(lensDis);
    const list = counties.rows.filter((r) => fin(r.v.disasters) && r.v.disasters > 0).sort((a, b) => b.v.disasters - a.v.disasters).slice(0, 10);
    if (!list.length) return;
    dSec.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">${esc(lensDis.name)}最高的鄉鎮市區${lensDis.unit ? `（${esc(lensDis.unit)}）` : ""}</h4>${lensDis.note ? `<p class="adv-callout adv-caveat">${esc(lensDis.note)}</p>` : ""}`);
    const host = mk("div");
    dSec.appendChild(host);
    const hColor = colorScale({ type: "seq", domain: lensDis.domain || [0, list[0].v.disasters], ramp: lensDis.ramp });
    barList(host, {
      rank: true, compact: true, max: list[0].v.disasters, ariaLabel: `${lensDis.name}最高的鄉鎮市區`,
      rows: list.map((r) => ({ key: r.key, label: placeLabel(r), value: r.v.disasters, text: hFmt(r.v.disasters), color: hColor(r.v.disasters) })),
      onHover: (x) => link.hover(x ? rowsHighlight(counties, [counties.byKey.get(x.key)]) : null),
      onClick: (x) => { picker.set("dis"); counties.focus(counties.byKey.get(x.key)); },
    });
    if (lensDis.description) dSec.insertAdjacentHTML("beforeend", `<p class="adv-note">${esc(lensDis.description)}</p>`);
  }

  function drawDisasters(D) {
    const fema = D.fema || {}, noaa = D.noaa || {};
    const lensShowsIt = !!lensDis && (D.sources || []).includes(lensDis.source);
    const tidy = (s) => (hasCJK(s) ? String(s) : titleCase(s));
    // A block title from the file leads its heading only when it is written in Chinese (the rule text below it
    // says what is counted either way).
    const lead = (t) => (t && hasCJK(t) ? `${esc(t)}：` : "");
    if (fema.rule) dSec.insertAdjacentHTML("beforeend", `<p class="adv-note">${esc(fema.rule)}</p>`);
    // County rows by geoid.
    const cols = fema.counties?.columns || [];
    const ci = Object.fromEntries(cols.map((k, j) => [k, j]));
    const cRows = new Map((fema.counties?.rows || []).map((r) => [r[ci.geoid], r]));
    const types = fema.types || [];
    const typeName = new Map(types.map((t) => [t.id, t.name]));
    // National counts by type: the file's own figure when it has one (areas can overlap), else the sum over states.
    let nat = fema.national?.by_type, natTotal = fema.national?.events ?? fema.national?.total;
    if (!nat) {
      nat = {};
      for (const s of Object.values(fema.states || {})) for (const [k, v] of Object.entries(s.by_type || {})) nat[k] = (nat[k] || 0) + (v || 0);
    }
    if (!fin(natTotal)) natTotal = Object.values(fema.states || {}).reduce((a, s) => a + (s.total || 0), 0);
    const since = (fema.window || [])[0]?.slice(0, 4);
    const parts = types.map((t) => ({ key: t.id, label: t.name, value: nat[t.id] || 0, color: DIS_COLOR[t.id] || "#999", text: int(nat[t.id] || 0) })).filter((p) => p.value > 0);
    if (parts.length) {
      dSec.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">${lead(fema.title) || "災害事件："}${since ? `${esc(since)} 年以來` : ""}共 ${int(natTotal)} 件，依類型</h4>`);
      const typeCounties = (id) => (counties && ci[id] != null ? counties.rows.filter((r) => { const x = cRows.get(r.key); return x && x[ci[id]] > 0; }) : []);
      shareBar(dSec, {
        parts,
        onHover: (p) => { const rows = p ? typeCounties(p.key) : []; link.hover(rows.length ? rowsHighlight(counties, rows, { dim: true, label: `有「${p.label}」事件的鄉鎮市區` }) : null); },
        onClick: () => { if (lensShowsIt) picker.set("dis"); },
      });
    }

    // States: events in each, and the larger record's events and cost where the file has them by state.
    const refs = uniq([...Object.keys(fema.states || {}), ...Object.keys(noaa.states || {})]);
    const sumOf = (o) => Object.values(o || {}).reduce((a, v) => a + (fin(v) ? v : 0), 0);
    const sRows = refs.map((a) => {
      const f = fema.states?.[a], n = noaa.states?.[a], row = stRow(a);
      return { key: row?.key ?? a, name: row?.name || a, row, fema: f?.total ?? null, cases: f?.cases ?? null, nEvents: n ? sumOf(n.count) : null, nCost: n ? sumOf(n.cost_usd) : null };
    });
    const any = (k) => sRows.some((r) => fin(r[k]));
    const years = (noaa.years || []).join("–");
    if (sRows.length) {
      dSec.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">各縣市</h4>`);
      dState = createTable(dSec, {
        caption: "各縣市的災害事件", rank: true, maxHeight: 240, search: "搜尋縣市",
        rows: sRows,
        columns: [
          { key: "name", label: "縣市", align: "l", width: "minmax(0,1.4fr)", value: (r) => r.name, html: (r) => `${esc(r.name)}${r.row ? "" : ` <span class="sub">不在地圖上</span>`}` },
          ...(any("fema") ? [{ key: "fema", label: "事件數", value: (r) => r.fema, text: (r) => (fin(r.fema) ? int(r.fema) : "–"), title: fema.title || "", ...(any("nCost") ? {} : { bar: { max: Math.max(...sRows.map((r) => r.fema || 0), 1), color: "rgba(207,106,74,.3)" } }) }] : []),
          ...(any("cases") ? [{ key: "cases", label: "案件數", value: (r) => r.cases, text: (r) => (fin(r.cases) ? count3(r.cases) : "–"), title: "這些事件中在該縣市通報的案件數" }] : []),
          ...(any("nEvents") ? [{ key: "nEvents", label: "重大災害", short: "重大災害事件", value: (r) => r.nEvents, text: (r) => (fin(r.nEvents) ? int(r.nEvents) : "–"), title: `波及該縣市的重大災害事件數${years ? `，${years} 年` : ""}` }] : []),
          ...(any("nCost") ? [{ key: "nCost", label: "損失", short: "所占損失", value: (r) => r.nCost, text: (r) => money(r.nCost), bar: { max: Math.max(...sRows.map((r) => r.nCost || 0), 1), color: "rgba(232,119,74,.3)" }, title: `該縣市在這些事件損失中所占的部分${noaa.unit ? `（${noaa.unit}）` : ""}` }] : []),
        ],
        sort: { key: any("nCost") ? "nCost" : any("fema") ? "fema" : "name", dir: any("nCost") || any("fema") ? "desc" : "asc" },
        onHover: (r) => link.hover(r?.row ? rowsHighlight(stLevel, [r.row], { dim: true }) : null),
        onClick: (r) => { if (r.row) stLevel.focus(r.row); },
      });
    }

    // Counties with the most events.
    if (counties && cRows.size && ci.total != null) {
      const rows = counties.rows.filter((r) => cRows.has(r.key)).map((r) => ({ ...r, dx: cRows.get(r.key) }));
      const topType = (x) => {
        let best = null, bv = 0;
        for (const t of types) if ((x[ci[t.id]] || 0) > bv) { bv = x[ci[t.id]]; best = t.id; }
        return best;
      };
      const shortType = (id) => { const nm = typeName.get(id); return !nm ? "–" : hasCJK(nm) ? nm : nm.split(/[ ,&]/)[0]; };
      dSec.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">事件最多的鄉鎮市區</h4>`);
      dCounty = createTable(dSec, {
        caption: "各鄉鎮市區的災害事件數", rank: true, maxHeight: 240, search: "搜尋鄉鎮市區", rows,
        columns: [
          { key: "name", label: "鄉鎮市區", align: "l", width: "minmax(0,1.6fr)", value: (r) => r.name, html: (r) => `${esc(r.name)}${r.sub ? ` <span class="sub">${esc(r.sub)}</span>` : ""}` },
          { key: "total", label: "事件數", value: (r) => r.dx[ci.total], text: (r) => int(r.dx[ci.total]), bar: { max: Math.max(...rows.map((r) => r.dx[ci.total] || 0), 1), color: "rgba(207,106,74,.3)" } },
          { key: "top", label: "主要類型", align: "l", width: "minmax(0,1fr)", hideBelow: 380, value: (r) => topType(r.dx), text: (r) => shortType(topType(r.dx)) },
          ...(ci.last_date != null ? [{ key: "last", label: "最近一次", align: "l", width: "82px", value: (r) => r.dx[ci.last_date], text: (r) => r.dx[ci.last_date] || "–" }] : []),
        ],
        sort: { key: "total", dir: "desc" },
        onHover: (r) => link.hover(r ? rowsHighlight(counties, [counties.byKey.get(r.key)]) : null),
        onClick: (r) => counties.focus(counties.byKey.get(r.key)),
      });
    }

    // The most recent events.
    const recent = fema.recent || [];
    if (recent.length) {
      const townRows = (r) => (counties ? (r.counties || []).map((g) => counties.byKey.get(g)).filter(Boolean) : []);
      dSec.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">近 ${Math.round((fema.recent_days || 365) / 30)} 個月的事件${fema.as_of ? `（截至 ${esc(fema.as_of)}）` : ""}</h4>`);
      createTable(dSec, {
        caption: "近期的災害事件", maxHeight: 220, rowKey: (r) => r.disaster,
        rows: recent,
        columns: [
          { key: "date", label: "日期", align: "l", width: "82px", value: (r) => r.date, text: (r) => r.date },
          { key: "state", label: "縣市", align: "l", width: "minmax(0,.7fr)", value: (r) => stName(r.state), text: (r) => stName(r.state) },
          { key: "type", label: "事件", align: "l", width: "minmax(0,1.6fr)", value: (r) => r.title, html: (r) => `<i class="dot" style="background:${DIS_COLOR[r.type] || "#999"}"></i>${esc(tidy(r.title))}`, tip: (r) => uniq([typeName.get(r.type), r.incident_type, tidy(r.title)]).join(" · ") },
          { key: "areas", label: "地區數", value: (r) => r.areas, text: (r) => (r.statewide ? "全縣市" : int(r.areas)), title: "事件涉及的鄉鎮市區等地區數（含不在地圖上者）" },
        ],
        sort: { key: "date", dir: "desc" },
        onHover: (r) => {
          if (!r) return link.hover(null);
          const rows = townRows(r), i = stRow(r.state)?.ref;
          link.hover(rows.length ? rowsHighlight(counties, rows, { dim: true, label: `${tidy(r.title)}（${stName(r.state)}）` }) : i != null ? { states: new Set([i]), dimOthers: true, label: stName(r.state) } : null);
        },
        onClick: (r) => {
          const rows = townRows(r);
          const b = rows.length ? app.highlightBounds(counties.highlight(rows)) : null;
          if (b) frameBox(app, b, { pad: 50, maxScale: 2.6 });
        },
      });
    }

    // The record by year and the costliest events.
    const byYear = (noaa.national?.by_year || []).filter((y) => fin(y.year));
    if (byYear.some((y) => fin(y.events))) {
      const priced = byYear.some((y) => fin(y.cost_usd));
      dSec.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">${lead(noaa.title)}每年災害事件數${years ? `，${esc(years)} 年` : ""}${priced && noaa.unit ? `（${esc(noaa.unit)}）` : ""}</h4>`);
      dSec.appendChild(columnChart(byYear, (y) => (fin(y.events) ? y.events : 0), (y) => `${y.year} 年：${fin(y.events) ? `${int(y.events)} 件` : "無資料"}${fin(y.cost_usd) ? `，${money(y.cost_usd)}` : ""}${fin(y.deaths) ? `，${int(y.deaths)} 人死亡` : ""}`));
    }
    if (noaa.rule || noaa.final) dSec.insertAdjacentHTML("beforeend", `<p class="adv-note">${esc(noaa.rule || "")}${noaa.final ? " 這個系列已停止更新。" : ""}</p>`);
    const worst = noaa.national?.costliest || [];
    if (worst.length) {
      dSec.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">損失最大的事件</h4><ol class="adv-olist">${worst.map((e) => `<li><b>${esc(e.name)}</b> <span class="sub">${[fin(e.cost_usd) ? money(e.cost_usd) : "", fin(e.deaths) ? `${int(e.deaths)} 人死亡` : ""].filter(Boolean).join(" · ")}</span></li>`).join("")}</ol>`);
    }
  }

  const api = {
    onMapHover(h) {
      const owner = h.cell >= 0 ? app.w.raw.owner[h.cell] : -1;
      const sr = owner >= 0 ? stLevel.rows[owner] : null;
      faithStates?.setHot(sr ? sr.key : null);
      dState?.setHot(sr ? sr.key : null, false);
      const c = h.cell >= 0 && counties ? counties.rowAtCell(h.cell) : null;
      amenHist?.setHot(c && amenHist.binOf ? amenHist.binOf(c.v.amenities)?.i ?? null : null);
      amenTable?.setHot(c ? c.key : null, false);
      dCounty?.setHot(c ? c.key : null, false);
      if (h.item?.kind === "wonder") for (const w of wonderBars) w.setHot(h.item.data?.id ?? null);
    },
    onMapClick(ev) {
      if (ev.item?.kind !== "wonder") return false;
      flyTo(wonders.find((w) => w.id === ev.item.data?.id));
      return true;
    },
  };
  return api;

  function active() { return el.isConnected; }
}

function metricText(w) {
  const m = w.metrics || {};
  if (w.kind === "university") return fin(m.rd_usd) ? `${money(m.rd_usd)} 研究經費` : "–";
  if (fin(m.visits)) return `${count3(m.visits)} 人次`;
  if (w.kind === "landmark") return fin(m.designated) ? `${m.designated} 年指定` : kindOf(w.kind).label;
  return "–";
}

// Latin event titles arrive in capitals; Chinese ones are shown as they are.
const titleCase = (s) => String(s || "").toLowerCase().replace(/\b([a-z])/g, (c) => c.toUpperCase()).replace(/\b(And|Of|The|In)\b/g, (w) => w.toLowerCase());

/** A small SVG column chart (one column per item). */
function columnChart(items, val, label) {
  const W = 400, H = 110, m = { l: 4, r: 4, t: 6, b: 18 };
  const max = Math.max(1, ...items.map(val));
  const bw = (W - m.l - m.r) / items.length;
  const div = document.createElement("div");
  div.className = "adv-hist adv-cols-chart";
  const first = items[0]?.year, last = items[items.length - 1]?.year;
  div.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="none" role="img" aria-label="每年事件數">
    ${items.map((it, i) => { const h = (val(it) / max) * (H - m.t - m.b); return `<g class="bin"><rect class="hit" x="${(m.l + i * bw).toFixed(2)}" y="${m.t}" width="${bw.toFixed(2)}" height="${H - m.t - m.b}"/><rect class="bar" x="${(m.l + i * bw + 0.4).toFixed(2)}" y="${(H - m.b - h).toFixed(2)}" width="${Math.max(0.5, bw - 0.8).toFixed(2)}" height="${h.toFixed(2)}" fill="#cf6a4a"/><title>${esc(label(it))}</title></g>`; }).join("")}
    <line x1="${m.l}" x2="${W - m.r}" y1="${H - m.b + 0.5}" y2="${H - m.b + 0.5}" class="axis"/>
    <text x="${m.l}" y="${H - 5}" class="tick">${first ?? ""}</text><text x="${W - m.r}" y="${H - 5}" text-anchor="end" class="tick">${last ?? ""}</text>
    <text x="${m.l + 2}" y="${m.t + 9}" class="tick">最多 ${int(max)}</text>
  </svg>`;
  return div;
}
