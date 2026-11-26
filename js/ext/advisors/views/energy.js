// Energy & Resources advisor: the mapped power sites, mines and oil & gas plays.
// Type names, units, thresholds and sources all come from resources.json; a build without mines or plays simply has
// no such group. Sites carry their 縣市 as an ISO code (item.state): the UI shows the 縣市 name.
import { esc, fin } from "../core/util.js";
import { fmtValue, mw, int, count3 } from "../core/fmt.js";
import { barList, shareBar, stackedBars, sizeLegend } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { section, tiles, chips, sourcesHtml } from "../core/view.js";
import { frameBox, focusPoint } from "../core/frame.js";
import { glyph } from "../../../ui/icon.js";

const GROUPS = [
  { id: "thermal", label: "發電廠", types: ["nuclear", "coal_plant", "gas_plant", "oil_plant", "geothermal"] },
  { id: "water", label: "水力", types: ["hydro", "pumped_storage"] },
  { id: "renew", label: "風力、太陽能與儲能", types: ["wind", "solar", "battery"] },
  { id: "mines", label: "礦場", types: ["coal_mine", "gold", "copper", "iron", "silver", "platinum", "molybdenum", "lead_zinc", "rare_earths", "uranium"] },
  { id: "plays", label: "油氣田", types: ["oil", "gas"] },
];
const typeLabel = (ty) => String(ty?.name || ty?.id || "").replace(/ \(shale play\)/, "");

export function mount(ctx) {
  const { app, data, el, link } = ctx;
  const res = app.data.resources;
  if (!res) {
    el.innerHTML = `<p class="adv-empty pad">尚未建置 resources.json，這裡沒有可顯示的內容。</p>`;
    return {};
  }
  const types = res.types || [];
  const typeById = new Map(types.map((t) => [t.id, t]));
  const items = (res.items || []).map((it, i) => ({ ...it, idx: i, key: String(i) }));
  const nat = res.summary?.national || {};
  const isMW = (t) => typeById.get(t)?.unit === "MW";
  const mwTypes = types.filter((t) => t.unit === "MW");
  const otherTypes = types.filter((t) => t.unit !== "MW");
  const states = app.data.states || [];
  const stateIdx = new Map(states.map((s, i) => [s.abbr, i]));
  const stateName = (abbr) => (abbr ? states[stateIdx.get(abbr)]?.name || abbr : "");
  // Draw groups in GROUPS order, plus any type the groups do not list.
  const listed = new Set(GROUPS.flatMap((g) => g.types));
  const groups = GROUPS.map((g) => ({ ...g, types: g.types.filter((t) => typeById.has(t)) })).filter((g) => g.types.length);
  const extra = types.filter((t) => !listed.has(t.id)).map((t) => t.id);
  if (extra.length) groups.push({ id: "other", label: "其他", types: extra });
  const groupCount = (id) => groups.find((g) => g.id === id)?.types.reduce((a, t) => a + (nat[t]?.count || 0), 0);

  const st = { on: new Set(types.map((t) => t.id)), min: 0, state: null };
  ctx.setShowResources(true);

  // --- headline -------------------------------------------------------------------------------------------------
  const totalMW = mwTypes.reduce((a, t) => a + (nat[t.id]?.value || 0), 0);
  const sites = mwTypes.reduce((a, t) => a + (nat[t.id]?.count || 0), 0);
  const mwItems = items.filter((it) => isMW(it.type) && fin(it.value));
  const maxMW = Math.max(1, ...mwItems.map((it) => it.value));
  const biggest = mwItems.reduce((b, it) => (!b || it.value > b.value ? it : b), null);
  const top = el.appendChild(document.createElement("div"));
  top.innerHTML = tiles([
    { label: "地圖電廠容量", value: mw(totalMW), sub: `${int(sites)} 處` },
    // Mines and oil & gas plays where the build maps them; otherwise the number of power types and the largest site.
    groupCount("mines") != null
      ? { label: "礦場", value: int(groupCount("mines")), sub: "達到規模門檻" }
      : { label: "發電類型", value: int(mwTypes.length), sub: "各有標示門檻" },
    groupCount("plays") != null
      ? { label: "油氣田", value: int(groupCount("plays")), sub: "油氣六角格" }
      : { label: "最大電廠", value: biggest ? mw(biggest.value) : "–", sub: biggest ? biggest.name : "" },
  ]) + `<p class="adv-callout">${esc(res.summary?.note || "只計入地圖上標示的場址。")}</p>`;

  // --- national mix ---------------------------------------------------------------------------------------------
  const mixBody = section(el, { title: "全國電力結構", kicker: "達到門檻的地圖場址", note: "地圖上各類發電設施的裝置容量。小型電廠沒有標示，所以這<b>不是</b>全國的總裝置容量：它呈現大型場址在哪裡、靠什麼發電。" });
  const mixParts = mwTypes.map((t) => ({ key: t.id, label: t.name, value: nat[t.id]?.value || 0, color: t.color, text: mw(nat[t.id]?.value), icon: glyph(t, 14) })).sort((a, b) => b.value - a.value);
  const mixHover = (p) => {
    if (!p) { link.hover(null); bubbles.setSelected(null); return; }
    const set = new Set(visible().filter((it) => it.type === p.key).map((it) => it.idx));
    link.hover({ resources: set, dimOthers: true });
    bubbles.setSelected(new Set(visible().filter((it) => it.type === p.key).map((it) => it.key)));
  };
  const solo = (typeId) => {
    const only = st.on.size === 1 && st.on.has(typeId);
    st.on = only ? new Set(types.map((t) => t.id)) : new Set([typeId]);
    typeChips.set(st.on);
    apply();
  };
  shareBar(mixBody, { parts: mixParts, legend: false, onHover: mixHover, onClick: (p) => solo(p.key) });
  const mixBars = barList(mixBody, {
    rows: mixParts.map((p) => ({ ...p, sub: `${int(nat[p.key]?.count || 0)} 處` })),
    onHover: mixHover, onClick: (p) => solo(p.key), ariaLabel: "各類型的地圖裝置容量",
  });

  // --- filters --------------------------------------------------------------------------------------------------
  const fBody = section(el, { title: "篩選地圖", note: "切換類型（按住 Alt 點擊可只顯示一種）。地圖會把地形調暗，並把每座發電設施畫成依容量縮放的圓圈。" });
  const typeChips = chips(fBody, {
    label: "資源類型",
    items: groups.flatMap((g) => g.types.map((t) => {
      const ty = typeById.get(t);
      return { key: t, label: typeLabel(ty), color: ty.color, icon: glyph(ty, 13), count: nat[t]?.count ?? null };
    })),
    onChange: (on) => { st.on = on; apply(); },
  });
  const quick = document.createElement("div");
  quick.className = "adv-row";
  quick.innerHTML = groups.map((g) => `<button type="button" class="adv-mini" data-g="${g.id}">${esc(g.label)}</button>`).join("") +
    `<button type="button" class="adv-mini" data-g="all">全部</button><button type="button" class="adv-mini" data-g="none">全不選</button>`;
  fBody.appendChild(quick);
  quick.addEventListener("click", (e) => {
    const g = e.target.closest("[data-g]")?.dataset.g;
    if (!g) return;
    st.on = g === "all" ? new Set(types.map((t) => t.id)) : g === "none" ? new Set() : new Set(groups.find((x) => x.id === g).types);
    typeChips.set(st.on);
    apply();
  });
  // The slider runs up to 3,000 MW, or to the largest mapped site when that is smaller.
  const sliderMax = Math.min(3000, Math.max(100, Math.floor(maxMW / 100) * 100));
  const slider = document.createElement("div");
  slider.className = "adv-slider";
  slider.innerHTML = `<label><span>最小規模</span><input type="range" min="0" max="${sliderMax}" step="100" value="0" aria-label="發電設施的最小容量（MW）"><b>不限</b></label>
    <p class="adv-note adv-min-note" hidden>設定最小規模時，不以 MW 計量的類型會隱藏。</p>`;
  fBody.appendChild(slider);
  const range = slider.querySelector("input");
  range.addEventListener("input", () => {
    st.min = +range.value;
    slider.querySelector("b").textContent = st.min ? `≥ ${int(st.min)} MW` : "不限";
    slider.querySelector(".adv-min-note").hidden = !st.min || !otherTypes.length;
    apply();
  });
  const stateChip = document.createElement("div");
  stateChip.className = "adv-row adv-filterbar";
  fBody.appendChild(stateChip);
  stateChip.addEventListener("click", (e) => { if (e.target.closest("[data-clear-state]")) setState(null); });
  const legendBox = document.createElement("div");
  fBody.appendChild(legendBox);

  // --- top sites ------------------------------------------------------------------------------------------------
  const tBody = section(el, { title: "場址", note: "通過篩選的所有地圖場址。將游標移到列上可在地圖上找到它；點擊則飛到該處。" });
  const sizeSort = (r) => (isMW(r.type) && fin(r.value) ? r.value : null);
  const table = createTable(tBody, {
    caption: "地圖上的資源場址",
    search: "搜尋場址、縣市、營運者",
    searchText: (r) => `${r.name} ${stateName(r.state)} ${r.state || ""} ${r.detail || ""} ${typeById.get(r.type)?.name || ""}`,
    rank: true,
    columns: [
      { key: "name", label: "場址", align: "l", width: "minmax(0,1.7fr)", value: (r) => r.name, html: (r) => `<span class="ic">${glyph(typeById.get(r.type), 13)}</span>${esc(r.name)}` },
      { key: "type", label: "類型", align: "l", width: "minmax(0,1fr)", value: (r) => typeById.get(r.type)?.name, text: (r) => typeLabel(typeById.get(r.type)) || r.type },
      { key: "state", label: "縣市", align: "l", width: "minmax(0,.7fr)", value: (r) => stateName(r.state), text: (r) => stateName(r.state) || "–" },
      { key: "value", label: "規模", width: "minmax(0,.95fr)", value: sizeSort, text: (r) => sizeText(r), title: "依容量排序（MW；其他單位排在最後）" },
    ],
    rows: [],
    sort: { key: "value", dir: "desc" },
    maxHeight: 300,
    onHover: (r) => {
      link.hover(r ? { resources: new Set([r.idx]), dimOthers: true, label: r.name } : null);
      bubbles.setHot(r ? r.key : null);
    },
    onClick: (r) => flyTo(r),
  });
  function sizeText(r) {
    const t = typeById.get(r.type);
    if (!fin(r.value)) return "–";
    if (t?.unit === "MW") return mw(r.value);
    if (t?.unit === "employees") return `${int(r.value)} 人`;
    if (/tons/.test(t?.unit || "")) return `${count3(r.value)} 公噸／年`;
    if (/km/.test(t?.unit || "")) return `${count3(r.value)} km²`;
    return `${fmtValue("float", r.value)}${t?.unit ? ` ${t.unit}` : ""}`;
  }
  function flyTo(r) {
    focusPoint(app, r.x, r.y, Math.min(app.cam.maxScale, Math.max(app.cam.scale, (app.cam.fitScale || 1) * 3.2)));
  }

  // --- per state ------------------------------------------------------------------------------------------------
  // A 縣市's mapped capacity: states.json `energy` when the build has it, else the totals in resources.json
  // (summary.states[abbr][type] = {count, value}).
  const sumStates = res.summary?.states || {};
  const energyOf = (s) => {
    if (s.energy) return { total: s.energy.total || 0, by_type: s.energy.by_type || {} };
    const b = sumStates[s.abbr];
    if (!b) return { total: 0, by_type: {} };
    const by_type = Object.fromEntries(mwTypes.filter((t) => fin(b[t.id]?.value)).map((t) => [t.id, b[t.id].value]));
    return { total: Object.values(by_type).reduce((a, v) => a + v, 0), by_type };
  };
  const stateRows = states
    .map((s, i) => { const e = energyOf(s); return { key: s.abbr, label: s.name, idx: i, parts: e.by_type, total: e.total, text: mw(e.total) }; })
    .filter((r) => r.total > 0)
    .sort((a, b) => b.total - a.total);
  let stacks = null;
  if (stateRows.length) {
    const sBody = section(el, { title: "各縣市的電力", note: "各縣市在地圖上的裝置容量，依類型區分。點擊某個縣市，可把所有內容篩選到該縣市；再點一次取消。" });
    stacks = stackedBars(sBody, {
      rows: stateRows, keys: mwTypes.map((t) => ({ key: t.id, label: t.name, color: t.color })), fmt: (v) => mw(v),
      ariaLabel: "各縣市的地圖裝置容量",
      onHover: (x) => {
        if (!x) return link.hover(null);
        const sIdx = x.row.idx;
        const set = x.part ? new Set(items.filter((it) => it.state === x.row.key && it.type === x.part).map((it) => it.idx)) : undefined;
        link.hover({ states: new Set([sIdx]), resources: set, dimOthers: true, label: x.part ? `${x.row.label}：${typeById.get(x.part)?.name || x.part}` : x.row.label });
      },
      onClick: (x) => setState(st.state === x.row.key ? null : x.row.key, true),
    });
    const noPower = states.filter((s) => !(energyOf(s).total > 0)).map((s) => s.name);
    if (noPower.length) sBody.insertAdjacentHTML("beforeend", `<p class="adv-note">沒有地圖電廠的縣市：${esc(noPower.join("、"))}。</p>`);
  }

  // --- explainer ------------------------------------------------------------------------------------------------
  const eBody = section(el, { title: "符號的意義", note: "各資源類型、場址要達到才會標示的門檻，以及資料的出處。" });
  eBody.innerHTML = groups.map((g) => `<h4 class="adv-h4">${esc(g.label)}</h4>${g.types.map((t) => {
    const ty = typeById.get(t);
    const s = nat[t] || {};
    const src = data.source(ty.source);
    const total = fin(s.value) ? (ty.unit === "MW" ? mw(s.value) : `${count3(s.value)} ${ty.unit}`) : /km/.test(ty.unit || "") ? "面積不可加總" : "";
    return `<div class="adv-explain" style="--cc:${esc(ty.color)}"><span class="ic">${glyph(ty, 22)}</span><div>
      <b>${esc(ty.name)}</b> <span class="sub">地圖上 ${int(s.count || 0)} 處${total ? ` · ${esc(total)}` : ""} · 單位：${esc(ty.unit)}</span>
      <p>${esc(ty.description || "")}</p>${src ? `<span class="src">資料來源：${esc(`${src.title}${src.vintage || src.publisher ? `（${src.vintage || src.publisher}）` : ""}`)}</span>` : ""}</div></div>`;
  }).join("")}`).join("");

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, [...types.map((t) => t.source), ...(Array.isArray(res.sources) ? res.sources : [])], [
    "只有達到各類型門檻的場址才會標示（門檻見上方各類型的說明），所以總和<b>不是</b>縣市或全國的裝置容量。",
    "容量是裝置容量（MW），不是實際發電量：同樣 1,000 MW，太陽光電一年的發電量遠少於火力電廠。",
    ...(otherTypes.length ? [`${esc(otherTypes.map((t) => typeLabel(t)).join("、"))}不以 MW 計量，數值不能和 MW 相加。`] : []),
    "場址依資料登記的縣市計算；少數位於交界的場址，所在的六角格可能屬於鄰近縣市。",
  ]));

  // --- map ------------------------------------------------------------------------------------------------------
  const bubbles = ctx.bubbles("sites", {
    rMax: 24,
    tip: (b) => {
      const it = b.it, t = typeById.get(it.type);
      return `<b>${esc(it.name)}</b><br>${esc(t.name)} · <b>${esc(mw(it.value))}</b>${it.state ? ` · ${esc(stateName(it.state))}` : ""}${it.detail ? `<br><span class="sub">${esc(it.detail)}</span>` : ""}`;
    },
    onHover: (b) => table.setHot(b ? b.key : null),
    onClick: (b) => { table.setHot(b.key); flyTo(b.it); },
  });

  function visible() {
    return items.filter((it) => st.on.has(it.type) && (!st.min || (isMW(it.type) && fin(it.value) && it.value >= st.min)) && (!st.state || it.state === st.state));
  }

  function setState(abbr, fly = false) {
    st.state = abbr;
    stacks?.setSelected(abbr);
    apply();
    if (abbr && fly) {
      const b = app.highlightBounds({ states: new Set([stateIdx.get(abbr)]) });
      if (b) frameBox(app, b, { pad: 30, maxScale: 2.6 });
    }
  }

  function apply() {
    const typesOn = st.min ? new Set([...st.on].filter(isMW)) : st.on;
    const all = typesOn.size === types.length && !st.min;
    ctx.setResourceFilter(all ? null : { types: new Set(typesOn), minValue: st.min || undefined });
    const vis = visible();
    table.setRows(vis);
    const mwVis = vis.filter((it) => isMW(it.type) && fin(it.value));
    const vMax = maxMW;
    bubbles.set(mwVis.map((it) => ({ key: it.key, x: it.x, y: it.y, value: it.value, color: typeById.get(it.type).color, it })), { vMax });
    const sIdx = st.state ? stateIdx.get(st.state) : null;
    link.base({ dimOthers: true, states: sIdx != null ? new Set([sIdx]) : undefined });
    stateChip.innerHTML = st.state
      ? `<span class="adv-fchip">縣市：<b>${esc(stateName(st.state))}</b> · ${int(vis.length)} 處<button type="button" data-clear-state aria-label="清除縣市篩選">✕</button></span>`
      : "";
    const r = (v) => 24 * Math.sqrt(v / vMax);
    legendBox.innerHTML = sizeLegend([250, 1000, 4000].filter((v) => v <= vMax * 1.2), r, (v) => `${int(v)} MW`, "圓圈面積 = 裝置容量");
    mixBars.setSelected(st.on.size === 1 ? [...st.on][0] : null);
  }
  apply();

  return {
    onMapHover(h) {
      if (h.resource) {
        const it = items[res.items.indexOf(h.resource)];
        if (it) table.setHot(it.key);
      }
    },
    onEscape() {
      if (st.state) { setState(null); return true; }
      return false;
    },
    destroy() {},
  };
}
