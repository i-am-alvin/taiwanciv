// Explorer: the generic slice-and-dice. Pick a level, any columns, filter, sort, plot any X / Y / size / colour,
// brush points onto the map, and show a column as a map lens where one exists.
import { esc, fin, colorScale, robustDomain, extent, RAMPS } from "../core/util.js";
import { fmtValue, fmtShort, fmtCell, parseNum, count3, int, compact } from "../core/fmt.js";
import { rampLegend, swatchLegend } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { createScatter } from "../core/scatter.js";
import { section, segmented, selectBox, sourcesHtml, frameBtn } from "../core/view.js";
import { rowsHighlight, extendData } from "../core/data.js";

// Preferred columns and axes, in order: the first ones the level really has data for are used (a field with no
// value in any row, e.g. incomes in this build, is skipped), topped up with the level's other numeric columns.
const DEFAULT_COLS = {
  states: ["population", "growth", "gdp_pc", "median_income", "unemployment", "density", "employed"],
  metros: ["states", "population", "growth", "gdp_pc", "median_income", "unemployment", "employed"],
  counties: ["population", "density", "income", "poverty"],
};
const N_DEFAULT_COLS = 5;
const DEFAULT_XY = {
  states: { x: ["median_income", "gdp_pc", "density"], y: ["growth", "unemployment"], s: ["population"], c: ["unemployment", "gdp_pc"] },
  metros: { x: ["gdp_pc", "density"], y: ["growth", "unemployment"], s: ["population"], c: ["median_income", "unemployment"] },
  counties: { x: ["income", "density"], y: ["bachelors", "growth"], s: ["population"], c: ["density"] },
};
// Table headers shorter than the field's own label, for the columns core/data.js defines (labels that come from
// the data files are shown as they are).
const SHORT = {
  energy_mw: "電廠容量", median_income: "所得中位數", n_districts: "區域數", qcew_jobs: "產業就業", top_industry: "最專精產業", top_lq: "區位商數",
  cz_median_age: "年齡中位數", cz_specialist: "突出市民", def_per_resident: "人均國防支出", def_pct_gdp: "國防占比",
};
const OPS = { num: [">", "≥", "<", "≤", "="], text: ["=", "contains", "≠"] };
const OP_LABEL = { contains: "包含" };
// Text filters ignore case and the 台 / 臺 spelling difference.
const fold = (s) => String(s ?? "").toLowerCase().replace(/台/g, "臺");

// Remember the explorer's setup per viewer (a convenience; the page works without it).
const STORE = "advisors.explorer.v1";
const load = () => { try { return JSON.parse(localStorage.getItem(STORE) || "null"); } catch { return null; } };
const save = (s) => { try { localStorage.setItem(STORE, JSON.stringify(s)); } catch { /* private mode */ } };

export async function mount(ctx) {
  const { app, data, el, link } = ctx;
  // Columns from the optional files (industry districts, citizen mixes): loaded on demand, only when the Explorer
  // opens, and added to the levels once. The military columns are added only when that file is already loaded
  // (it is left out of the Taiwan build, so they never are: no request, no empty columns).
  await extendData(data, [...(app.data.military != null ? ["military"] : []), "districts", "citizens"]);
  const avail = ["states", "metros", "counties"].filter((k) => data.levels[k]);
  const saved = load() || {};
  /** The field `k` of level `lv` when it exists and some row has a value for it. */
  const live = (lv, k) => { const f = lv?.field(k); return f && !f.empty ? f : null; };
  const firstLive = (lv, keys, numericOnly = true) => keys.find((k) => { const f = live(lv, k); return f && (!numericOnly || f.format !== "text"); }) || "";
  const defaultCols = (level) => {
    const lv = data.levels[level];
    const list = DEFAULT_COLS[level].filter((k) => live(lv, k));
    for (const f of lv.fields) {
      if (list.length >= N_DEFAULT_COLS) break;
      if (!f.empty && f.format !== "text" && !list.includes(f.key)) list.push(f.key);
    }
    return list.slice(0, N_DEFAULT_COLS);
  };
  const defaultXY = (level) => {
    const lv = data.levels[level], d = DEFAULT_XY[level];
    const nums = lv.fields.filter((f) => !f.empty && f.format !== "text").map((f) => f.key);
    const x = firstLive(lv, d.x) || nums[0] || "population";
    const y = firstLive(lv, d.y.filter((k) => k !== x)) || nums.find((k) => k !== x) || x;
    return { x, y, s: firstLive(lv, d.s), c: firstLive(lv, d.c.filter((k) => k !== x && k !== y)) };
  };
  const st = {
    level: avail.includes(ctx.params.level) ? ctx.params.level : avail.includes(saved.level) ? saved.level : avail.includes("metros") ? "metros" : avail[0],
    cols: { ...Object.fromEntries(avail.map((k) => [k, defaultCols(k)])), ...(saved.cols || {}) },
    xy: { ...Object.fromEntries(avail.map((k) => [k, defaultXY(k)])), ...(saved.xy || {}) },
    filters: [],
    onlySel: false,
    sel: null,
  };
  const persist = () => save({ level: st.level, cols: st.cols, xy: st.xy });
  const L = () => data.levels[st.level];

  // --- controls -------------------------------------------------------------------------------------------------
  const top = section(el, { title: "探索資料", note: "選擇要比較的對象、加上篩選條件、排序表格，並以任兩個欄位作圖。將游標移到某一列或某個點上，地圖會標出它的位置；在圖表上拖曳可框選一組。" });
  const lvRow = document.createElement("div");
  lvRow.className = "adv-row";
  top.appendChild(lvRow);
  segmented(lvRow, {
    label: "層級", value: st.level,
    options: avail.map((k) => ({ value: k, label: data.levels[k].label })),
    onChange: (v) => { st.level = v; st.filters = st.filters.filter((f) => live(L(), f.key)); st.sel = null; persist(); rebuild(); },
  });
  const colsBox = document.createElement("details");
  colsBox.className = "adv-cols";
  lvRow.appendChild(colsBox);

  const fRow = document.createElement("div");
  fRow.className = "adv-fbuild";
  top.appendChild(fRow);
  const chipsRow = document.createElement("div");
  chipsRow.className = "adv-row adv-filterbar";
  top.appendChild(chipsRow);
  const summary = document.createElement("p");
  summary.className = "adv-note adv-summary";
  top.appendChild(summary);

  // --- table ----------------------------------------------------------------------------------------------------
  const tBody = section(el, { title: "表格" });
  const selRow = document.createElement("div");
  selRow.className = "adv-row";
  tBody.appendChild(selRow);
  const tableHost = document.createElement("div");
  tBody.appendChild(tableHost);
  let table = null;

  // --- chart ----------------------------------------------------------------------------------------------------
  const cBody = section(el, { title: "圖表" });
  const axes = document.createElement("div");
  axes.className = "adv-axes";
  cBody.appendChild(axes);
  const scatterHost = document.createElement("div");
  cBody.appendChild(scatterHost);
  const legendEl = document.createElement("div");
  cBody.appendChild(legendEl);
  const lensRow = document.createElement("div");
  lensRow.className = "adv-row";
  cBody.appendChild(lensRow);
  const fieldInfo = document.createElement("div");
  fieldInfo.className = "adv-fieldinfo";
  cBody.appendChild(fieldInfo);
  const scatter = createScatter(scatterHost, {
    height: 320, points: [],
    onHover: (p) => { link.hover(p ? rowsHighlight(L(), [p.row]) : null); table?.setHot(p ? p.key : null, false); },
    onClick: (p) => L().focus(p.row),
    onBrush: (set) => { st.sel = set; applySelection(); },
  });
  const srcEl = document.createElement("div");
  el.appendChild(srcEl);

  // --- logic ----------------------------------------------------------------------------------------------------
  const fieldOpts = (withNone = false, numeric = true) => {
    const fs = L().fields.filter((f) => !f.empty && (numeric ? f.format !== "text" : f.key !== "name"));
    return [...(withNone ? [{ value: "", label: "無" }] : []), ...fs.map((f) => ({ value: f.key, label: f.label, group: f.group }))];
  };
  const numeric = (f) => f && f.format !== "text";
  const val = (r, k) => r.v[k] ?? null;
  const fmtF = (f, v) => fmtValue(f.format, v, f.unit);

  function passes(r) {
    for (const f of st.filters) {
      const fd = L().field(f.key);
      if (!fd) continue;
      const v = val(r, f.key);
      if (numeric(fd)) {
        if (!fin(v)) return false;
        const t = f.value;
        if (f.op === ">" && !(v > t)) return false;
        if (f.op === "≥" && !(v >= t)) return false;
        if (f.op === "<" && !(v < t)) return false;
        if (f.op === "≤" && !(v <= t)) return false;
        if (f.op === "=" && !(Math.abs(v - t) <= Math.abs(t) * 0.005 + 1e-9)) return false;
      } else {
        const s = fold(v), t = fold(f.value);
        if (f.op === "=" && s !== t) return false;
        if (f.op === "≠" && s === t) return false;
        if (f.op === "contains" && !s.includes(t)) return false;
      }
    }
    return true;
  }
  const filtered = () => L().rows.filter(passes);

  function renderCols() {
    const on = new Set(st.cols[st.level]);
    const groups = new Map();
    for (const f of L().fields) {
      if (f.key === "name" || f.empty) continue; // a column no row has a value for is not offered
      if (!groups.has(f.group)) groups.set(f.group, []);
      groups.get(f.group).push(f);
    }
    colsBox.innerHTML = `<summary class="adv-mini">欄位（${shownCols().length}）</summary><div class="adv-cols-pop">${[...groups].map(([g, list]) => `<fieldset><legend>${esc(g)}</legend>${list.map((f) => `<label title="${esc(f.description)}"><input type="checkbox" value="${esc(f.key)}"${on.has(f.key) ? " checked" : ""}> ${esc(f.label)}</label>`).join("")}</fieldset>`).join("")}</div>`;
  }
  colsBox.addEventListener("change", (e) => {
    const k = e.target.value;
    const list = st.cols[st.level].filter((x) => x !== k);
    if (e.target.checked) list.push(k);
    st.cols = { ...st.cols, [st.level]: list };
    colsBox.querySelector("summary").textContent = `欄位（${shownCols().length}）`;
    persist();
    buildTable();
  });

  function renderFilterBuilder() {
    fRow.innerHTML = "";
    const fs = L().fields.filter((f) => !f.empty);
    if (!fs.length) return;
    // An example of a text value: a real name from the level's own rows.
    const sample = (f) => { const v = L().rows.map((r) => val(r, f.key)).find((x) => x != null && x !== ""); return v != null ? `例如 ${v}` : "文字"; };
    const fsel = selectBox(fRow, { label: "篩選", value: fs.find((f) => f.key === "population")?.key || fs[0].key, options: fs.map((f) => ({ value: f.key, label: f.label, group: f.group })) });
    const ops = document.createElement("select");
    ops.setAttribute("aria-label", "比較方式");
    const valIn = document.createElement("input");
    valIn.type = "text";
    valIn.setAttribute("aria-label", "數值");
    const add = document.createElement("button");
    add.type = "button";
    add.className = "adv-mini";
    add.textContent = "加入";
    const syncOps = () => {
      const f = L().field(fsel.value);
      ops.innerHTML = (numeric(f) ? OPS.num : OPS.text).map((o) => `<option value="${esc(o)}">${esc(OP_LABEL[o] || o)}</option>`).join("");
      valIn.placeholder = numeric(f) ? (f.format === "pct" || f.format === "signed" ? "例如 25%" : f.format === "usd" || f.format === "money" ? "例如 80萬" : "例如 100萬") : sample(f);
    };
    fsel.select.addEventListener("change", syncOps);
    syncOps();
    const submit = () => {
      const f = L().field(fsel.value);
      if (!f || !valIn.value.trim()) return;
      const v = numeric(f) ? parseNum(valIn.value, f.format) : valIn.value.trim();
      if (v == null) { valIn.setCustomValidity("請輸入數字"); valIn.reportValidity(); return; }
      valIn.setCustomValidity("");
      st.filters.push({ key: f.key, op: ops.value, value: v });
      valIn.value = "";
      refresh();
    };
    add.addEventListener("click", submit);
    valIn.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } });
    fRow.append(ops, valIn, add);
    // quick presets
    const presets = document.createElement("span");
    presets.className = "adv-presets";
    const P = (!live(L(), "population") ? [] : st.level === "counties" ? [["population", "≥", 1e5]] : [["population", "≥", 1e6], ["population", "≥", 2.5e5]])
      .filter(([k, , v]) => L().rows.some((r) => val(r, k) >= v)); // a preset no row passes is not offered
    presets.innerHTML = P.map((p, i) => `<button type="button" class="adv-mini" data-preset="${i}">${esc(`${compact(p[2])}人以上`)}</button>`).join("");
    presets.addEventListener("click", (e) => {
      const i = e.target.closest("[data-preset]")?.dataset.preset;
      if (i == null) return;
      const [key, op, value] = P[+i];
      st.filters = st.filters.filter((f) => f.key !== key);
      st.filters.push({ key, op, value });
      refresh();
    });
    fRow.appendChild(presets);
  }

  function renderChips() {
    chipsRow.innerHTML = st.filters.map((f, i) => {
      const fd = L().field(f.key);
      const txt = `${fd?.label || f.key} ${OP_LABEL[f.op] || f.op} ${numeric(fd) ? fmtShort(fd.format, f.value) : f.value}`;
      return `<span class="adv-fchip">${esc(txt)}<button type="button" data-rm="${i}" aria-label="移除篩選條件：${esc(txt)}">✕</button></span>`;
    }).join("") + (st.filters.length > 1 ? `<button type="button" class="adv-mini" data-rm="all">全部清除</button>` : "") + (st.filters.length && filterHighlight() ? frameBtn() : "");
  }
  chipsRow.addEventListener("click", (e) => {
    const i = e.target.closest("[data-rm]")?.dataset.rm;
    if (i == null) return;
    if (i === "all") st.filters = [];
    else st.filters.splice(+i, 1);
    refresh();
  });

  /** The chosen columns the current level has data for. */
  function shownCols() {
    return (st.cols[st.level] || []).filter((k) => live(L(), k));
  }

  function buildTable() {
    const lv = L();
    const keys = shownCols();
    const sortKey = keys.includes("population") ? "population" : keys[0] || "name";
    const maxOf = (k) => { const e = extent(lv.rows.map((r) => val(r, k))); return e ? Math.max(Math.abs(e[0]), Math.abs(e[1])) : 1; };
    const cols = [
      { key: "name", label: lv.field("name")?.label || "名稱", align: "l", width: "minmax(92px,1.7fr)", value: (r) => r.name, html: (r) => `${esc(r.name)}${st.level !== "states" && r.sub ? ` <span class="sub">${esc(r.sub)}</span>` : ""}` },
      ...keys.map((k) => {
        const f = lv.field(k);
        const title = `${f.label}${f.unit ? `（${f.unit}）` : ""}。點擊可排序。`;
        const short = SHORT[k] || (k.startsWith("y_") ? esc(f.label.replace(/就業人口$/, "")) : null);
        // The name column already carries the state as a suffix, so a state column goes first when space is short.
        const isState = k === "state" || k === "states";
        return numeric(f)
          ? { key: k, label: f.label, short, title, value: (r) => val(r, k), text: (r) => fmtCell(f.format, val(r, k), f.unit), tip: (r) => fmtF(f, val(r, k)), bar: k === sortKey ? { max: maxOf(k), color: "rgba(154,123,201,.32)" } : null }
          : { key: k, label: f.label, short, title, align: "l", width: isState ? "minmax(0,.55fr)" : "minmax(0,.8fr)", hideBelow: isState ? 480 : 0, value: (r) => val(r, k), text: (r) => val(r, k) ?? "–" };
      }),
    ];
    if (!table) {
      table = createTable(tableHost, {
        caption: `${lv.label}資料表`, columns: cols, rows: [], sort: { key: sortKey, dir: "desc" }, rank: true, maxHeight: 360,
        search: `搜尋${lv.label}`,
        onHover: (r) => { link.hover(r ? rowsHighlight(L(), [r]) : null); scatter.setHot(r ? r.key : null); },
        onClick: (r) => L().focus(r),
      });
    } else table.setColumns(cols, { key: sortKey, dir: "desc" });
    refreshRows();
  }

  function axisSelects() {
    axes.innerHTML = "";
    // A saved axis the level no longer has data for falls back to the level's default.
    const dxy = defaultXY(st.level);
    const xy = (st.xy[st.level] = { ...dxy, ...(st.xy[st.level] || {}) });
    const fix = (k, fallback) => (live(L(), k) && numeric(L().field(k)) ? k : fallback);
    xy.x = fix(xy.x, dxy.x);
    xy.y = fix(xy.y, dxy.y);
    xy.s = xy.s && live(L(), xy.s) ? xy.s : "";
    xy.c = xy.c && live(L(), xy.c) ? xy.c : "";
    const mk = (key, label, none) => selectBox(axes, {
      label, value: xy[key], options: fieldOpts(none, key !== "c"),
      onChange: (v) => { xy[key] = v; if (key === "x" || key === "y") delete xy[`log${key}`]; persist(); drawScatter(); },
    });
    mk("x", "X", false);
    mk("y", "Y", false);
    mk("s", "大小", true);
    mk("c", "顏色", true);
    const logs = document.createElement("span");
    logs.className = "adv-logs";
    logs.innerHTML = `<label class="adv-check"><input type="checkbox" data-log="x"> X 取對數</label><label class="adv-check"><input type="checkbox" data-log="y"> Y 取對數</label>`;
    axes.appendChild(logs);
    logs.addEventListener("change", (e) => {
      const a = e.target.dataset.log;
      xy[`log${a}`] = e.target.checked;
      persist();
      drawScatter();
    });
  }
  // A skewed, positive column reads better on a log axis.
  const autoLog = (k, rows) => {
    const e = extent(rows.map((r) => val(r, k)), true);
    const all = rows.map((r) => val(r, k)).filter(fin);
    return !!e && all.every((v) => v > 0) && e[1] / e[0] > 60;
  };

  function drawScatter() {
    const lv = L();
    const xy = st.xy[st.level];
    const rows = filtered();
    const fx = lv.field(xy.x), fy = lv.field(xy.y), fs = xy.s ? lv.field(xy.s) : null, fc = xy.c ? lv.field(xy.c) : null;
    if (!fx || !fy) { scatter.update({ points: [] }); lensRow.innerHTML = ""; fieldInfo.innerHTML = `<p class="adv-empty">無資料。</p>`; srcEl.innerHTML = sourcesHtml(data, []); return; }
    const lx = xy.logx ?? autoLog(xy.x, rows), ly = xy.logy ?? autoLog(xy.y, rows);
    axes.querySelector('[data-log="x"]').checked = lx;
    axes.querySelector('[data-log="y"]').checked = ly;
    let color = null;
    legendEl.innerHTML = "";
    if (fc) {
      if (numeric(fc)) {
        const signed = fc.format === "signed";
        const cl = autoLog(fc.key, rows);
        const dom = robustDomain(rows.map((r) => val(r, fc.key)), 0.03, cl) || [0, 1];
        const spec = signed ? { type: "div", domain: dom, mid: 0 } : { type: "seq", domain: dom, log: cl, ramp: fc.higher_is === "bad" ? RAMPS.heat : RAMPS.seq };
        const cs = colorScale(spec);
        color = (c) => cs(c);
        legendEl.innerHTML = rampLegend({ ramp: spec.ramp || RAMPS.div, domain: signed ? [-Math.max(...dom.map(Math.abs)), Math.max(...dom.map(Math.abs))] : dom, log: cl, fmt: (v) => fmtShort(fc.format, v), label: fc.label, mid: signed ? 0 : null });
      } else {
        const cats = [...new Set(rows.map((r) => val(r, fc.key)))].slice(0, 12);
        const pal = ["#e0b54c", "#4a86d6", "#3f9c82", "#c46a4f", "#9a7bc9", "#6e9a3c", "#d98a2b", "#5fbfbf", "#c9a0c0", "#a3a3c2", "#e8774a", "#b9b06a"];
        const m = new Map(cats.map((c, i) => [c, pal[i]]));
        color = (c) => m.get(c) || "#8b8070";
        const more = new Set(rows.map((r) => val(r, fc.key))).size > cats.length;
        legendEl.innerHTML = swatchLegend([...cats.map((c) => ({ label: c ?? "–", color: m.get(c) })), ...(more ? [{ label: "其他", color: "#8b8070" }] : [])], fc.label);
      }
    }
    const big = [...rows].sort((a, b) => (val(b, "population") || 0) - (val(a, "population") || 0)).slice(0, st.level === "states" ? 10 : 6).map((r) => r.key);
    scatter.update({
      points: rows.map((r) => ({ key: r.key, x: val(r, xy.x), y: val(r, xy.y), s: fs ? val(r, xy.s) : null, c: fc ? val(r, xy.c) : null, label: r.name, sub: r.sub, row: r })),
      x: { label: fx.label, fmt: (v) => fmtShort(fx.format, v), log: lx },
      y: { label: fy.label, fmt: (v) => fmtShort(fy.format, v), log: ly },
      size: fs && numeric(fs) ? { label: fs.label, fmt: (v) => fmtF(fs, v), max: st.level === "counties" ? 13 : 15, min: 1.6 } : null,
      radius: st.level === "counties" ? 2.2 : 3.5,
      color, colorLabel: fc?.label, colorFmt: (v) => (fc && numeric(fc) ? fmtF(fc, v) : String(v)),
      labels: big,
      refLines: [], refX: [], refY: [],
    });
    if (st.sel) scatter.setSelected(st.sel);
    // Lens buttons for the plotted columns that have a matching map lens.
    lensRow.innerHTML = "";
    const lensFields = [fc, fy, fx].filter((f, i, a) => f && f.lens && a.findIndex((g) => g && g.lens === f.lens) === i);
    for (const f of lensFields) {
      const lens = app.lensById.get(f.lens);
      if (!lens) continue;
      const b = document.createElement("button");
      b.type = "button";
      b.className = "adv-lensbtn";
      const on = app.state.lens?.id === lens.id;
      b.setAttribute("aria-pressed", String(on));
      b.textContent = on ? `地圖正顯示「${lens.name}」濾鏡` : `在地圖上以濾鏡顯示「${f.label}」`;
      b.addEventListener("click", () => { app.setLens(app.state.lens?.id === lens.id ? null : lens.id); drawScatter(); });
      lensRow.appendChild(b);
    }
    if (!lensFields.length) lensRow.innerHTML = `<span class="adv-note">這些欄位沒有對應的地圖濾鏡：將游標移到圖上或拖曳框選，即可在地圖上看到位置。</span>`;
    fieldInfo.innerHTML = [fx, fy, fs, fc].filter((f, i, a) => f && a.indexOf(f) === i).map((f) => `<p><b>${esc(f.label)}</b>${f.unit ? ` <span class="sub">${esc(f.unit)}</span>` : ""}${f.description ? `：${esc(f.description)}` : ""}</p>`).join("");
    const srcIds = [fx, fy, fs, fc].filter(Boolean).map((f) => f.source).filter(Boolean);
    const gdpVintage = data.nation?.gdp_vintage;
    srcEl.innerHTML = sourcesHtml(data, srcIds, [
      ...(lv.fields.some((f) => !f.empty && f.label.endsWith("≈")) ? ["標有 ≈ 的欄位是鄉鎮市區數值依人口加權的平均：可供參考，但不是該地區本身的統計值。"] : []),
      ...(data.vintage || data.countyVintage ? [`${data.vintage ? `城市與縣市資料：${esc(data.vintage)}。` : ""}${data.countyVintage ? `鄉鎮市區資料：${esc(data.countyVintage)}。` : ""}`] : []),
      ...(gdpVintage && live(lv, "gdp") ? [`生產毛額：${esc(gdpVintage)}，與人口的統計年度不同。`] : []),
      ...(st.level === "counties" && data.countiesOffMap ? [`有 ${int(data.countiesOffMap)} 個鄉鎮市區小於一個六角格：它們仍列在表格與圖表中，但無法在地圖上標出輪廓。`] : []),
    ]);
  }

  function applySelection() {
    const lv = L();
    const sel = st.sel ? lv.rows.filter((r) => st.sel.has(r.key)) : [];
    link.base(sel.length ? rowsHighlight(lv, sel, { dim: true }) : filterHighlight(), { frame: sel.length > 1 || (!sel.length && st.filters.length > 0) });
    table?.setSelected(st.sel);
    selRow.innerHTML = st.sel ? `<span class="adv-fchip">已在圖表上選取 ${int(st.sel.size)} 個<button type="button" data-clear-sel aria-label="清除選取">✕</button></span>${frameBtn()}
      <label class="adv-check"><input type="checkbox" data-only${st.onlySel ? " checked" : ""}> 只顯示選取的項目</label>` : `<span class="adv-note">提示：在下方圖表上拖曳，即可框選一組。</span>`;
    refreshRows();
    updateSummary();
  }
  selRow.addEventListener("click", (e) => { if (e.target.closest("[data-clear-sel]")) { st.sel = null; st.onlySel = false; scatter.setSelected(null); applySelection(); } });
  selRow.addEventListener("change", (e) => { if (e.target.matches("[data-only]")) { st.onlySel = e.target.checked; refreshRows(); } });

  // With filters on, outline the rows that pass (when there are not too many to read).
  function filterHighlight() {
    if (!st.filters.length) return null;
    const rows = filtered();
    if (!rows.length || rows.length > (st.level === "counties" ? 1500 : 300)) return null;
    return rowsHighlight(L(), rows, { dim: true, ringMax: 12 });
  }

  function refreshRows() {
    if (!table) return;
    let rows = filtered();
    if (st.onlySel && st.sel) rows = rows.filter((r) => st.sel.has(r.key));
    table.setRows(rows);
  }
  function updateSummary() {
    const rows = filtered();
    const pop = rows.reduce((a, r) => a + (val(r, "population") || 0), 0);
    summary.innerHTML = `<b>${int(rows.length)}</b> / ${int(L().rows.length)} 個${esc(L().label)}${pop > 0 ? ` · 人口 ${count3(pop)}` : ""}${st.sel ? ` · 已選取 <b>${int(st.sel.size)}</b> 個` : ""}`;
  }
  function refresh() {
    renderChips();
    st.sel = null;
    scatter.setSelected(null);
    refreshRows();
    drawScatter();
    applySelection();
  }
  function rebuild() {
    if (table) { table.destroy(); table = null; }
    renderCols();
    renderFilterBuilder();
    axisSelects();
    buildTable();
    refresh();
  }
  rebuild();

  const hostRowAt = (cell) => (cell >= 0 ? L().rowAtCell(cell) : null);
  return {
    onMapHover(h) {
      const r = hostRowAt(h.cell);
      scatter.setHot(r ? r.key : null);
      table?.setHot(r ? r.key : null);
    },
    onEscape() {
      if (st.sel) { st.sel = null; st.onlySel = false; scatter.setSelected(null); applySelection(); return true; }
      return false;
    },
  };
}
