// City View "Citizens" rows: the city's people as rows of small figures (citizens.json).
//
//   citizensHtml(m, data) → HTML      the rows (placeholders for the figure canvases)
//   mountCitizens(host, m, data)       paints the figures and wires the hover / focus read-out
//
// Each row: N figures (from the file's `figures`, or rounded here with the same largest-remainder method), a caption
// ("每個人像 ≈ 7.2萬 位就業者"), a read-out line that a hovered or focused figure fills ("新北市的就業者中，每 7 位約有 1 位
// 屬於「…」（全國：每 14 位約有 1 位）") and a thin national bar for comparison. A row type the file does not have at all
// (no `groups` entry) is left out; a row the source did not publish for this city is said so, never drawn as zeros.
//
// Category names and the row descriptions come from the file (`groups[row][].label` / `.short`, `rows[row]`): the
// pipeline writes them in Chinese and defines what each category covers (age bands, schooling levels), so nothing
// here states a definition of its own.
import { esc, int, pct } from "../../format.js";
import { compact } from "./fmt.js";
import { CATEGORY_COLOR, artKey, figureCanvas, loadPainter } from "./figures.js";

/** groups → (row, key) → the key of the figure and colour that category uses (its own, or the one its icon names). */
function artOf(groups) {
  const map = new Map();
  for (const [r, gs] of Object.entries(groups || {})) for (const g of gs || []) map.set(`${r}|${g.key}`, artKey(r, g.key, g.icon));
  return (r, k) => map.get(`${r}|${k}`) || k;
}

// noun: what one figure counts ("每 7 位就業者"). sub: shown only when the file has no description for the row.
const ROWS = [
  { id: "workforce", title: "職業", sub: "依職業別", noun: "就業者", n: null },
  { id: "age", title: "世代", sub: "依年齡", noun: "居民", n: null },
  { id: "commute", title: "通勤", sub: "就業者上班的交通方式", noun: "就業者", n: null },
  { id: "education", title: "教育程度", sub: "依最高學歷", noun: "人口", n: 10 },
  { id: "nativity", title: "出生地", sub: "居民的出生地", noun: "居民", n: 10 },
];

/**
 * Whom a row counts, for its captions. The education row's base is an age floor that differs by source, so it is
 * read from the file's own description of the row ("15 歲以上戶籍人口的教育程度" → "15 歲以上人口").
 */
function nounOf(rd, data) {
  const m = rd.id === "education" ? /(\d+)\s*歲以上/.exec(data?.rows?.education || "") : null;
  return m ? `${m[1]} 歲以上人口` : rd.noun;
}
const lead = (noun) => (/^\d/.test(noun) ? " " : "") + noun; // a space between Chinese text and a leading number

/** Largest-remainder rounding of counts into n figures (the pipeline's method, for rows without figures). */
export function largestRemainder(counts, keys, n) {
  const tot = keys.reduce((a, k) => a + (counts[k] || 0), 0);
  if (!(tot > 0)) return null;
  const raw = keys.map((k) => ((counts[k] || 0) / tot) * n);
  const out = raw.map(Math.floor);
  let left = n - out.reduce((a, v) => a + v, 0);
  const order = raw.map((v, j) => [v - Math.floor(v), j]).sort((a, b) => b[0] - a[0] || a[1] - b[1]);
  for (let k = 0; k < left; k++) out[order[k][1]]++;
  return Object.fromEntries(keys.map((k, j) => [k, out[j]]));
}

/** "每 7 位約有 1 位", "每 10 位約有 3 位", "不到千分之一", as {text}; null without a share. */
export function oneIn(share) {
  if (share == null || !Number.isFinite(share)) return null;
  if (share <= 0) return { text: "沒有人" };
  if (share < 0.001) return { text: "不到千分之一" };
  if (share >= 0.3) {
    const k = Math.round(share * 10);
    return k >= 10 ? { text: "幾乎全部" } : { text: `每 10 位約有 ${k} 位` };
  }
  const n = Math.round(1 / share);
  return { text: `每 ${int(n)} 位約有 1 位` };
}

/** The read-out sentence, built from the category's own label (no per-category wording to keep in step with the data). */
function sentence(label, share, natShare, cityName, noun) {
  const a = oneIn(share);
  if (!a) return "";
  const us = oneIn(natShare);
  return `${cityName}的${lead(noun)}中，${a.text}屬於「${label}」${us ? `（全國：${us.text}）` : ""}`;
}

function rowModel(rowDef, row, nat, groups, figuresN) {
  const keys = (groups[rowDef.id] || []).map((g) => g.key);
  const n = figuresN[rowDef.id] ?? rowDef.n ?? 10;
  const figs = row.figures || largestRemainder(row.counts || {}, keys, n);
  const natFigs = nat?.figures || (nat ? largestRemainder(nat.counts || {}, keys, n) : null);
  return { keys, n, figs, natFigs };
}

// Specialists by row/key from the file (ratios from unrounded shares).
function specMap(city) {
  const m = new Map();
  for (const s of city?.specialists || []) m.set(`${s.row}|${s.key}`, s);
  return m;
}

/** The Citizens rows. data = citizens.json (or null / undefined while loading). */
export function citizensHtml(m, data) {
  const c = m.city;
  if (data === undefined) return `<p class="muted cv-note">市民組成載入中…</p>`;
  if (!data || !data.cities) return `<p class="muted cv-note">無市民組成資料。</p>`;
  const row0 = data.cities[c.id];
  if (!row0) {
    return `<p class="muted cv-note">資料來源沒有${esc(c.name)}的市民組成統計，因此這裡沒有市民人像。</p>`;
  }
  const nat = data.national || {};
  const groups = data.groups || {};
  const specs = specMap(row0);
  const art = artOf(groups);
  const colorOf = (r, k, fallback) => CATEGORY_COLOR[r]?.[art(r, k)] || fallback;
  const label = Object.fromEntries(Object.entries(groups).map(([r, gs]) => [r, Object.fromEntries(gs.map((g) => [g.key, g.label || g.key]))]));
  // Legend labels: the file's short form when it has one, else its label.
  const short = Object.fromEntries(Object.entries(groups).map(([r, gs]) => [r, Object.fromEntries(gs.map((g) => [g.key, g.short || g.label || g.key]))]));
  const hi = data.rule?.specialist_high ?? 1.5, lo = data.rule?.specialist_low ?? 0.67;

  // Headline: median age, degrees, foreign-born, and the "great person" call-out (the strongest specialist).
  const med = row0.age?.median, usMed = nat.age?.median;
  const ba = row0.education?.bachelors_plus, usBa = nat.education?.bachelors_plus;
  const fb = row0.nativity?.foreign_born ?? row0.nativity?.shares?.foreign_born;
  const usFb = nat.nativity?.foreign_born ?? nat.nativity?.shares?.foreign_born;
  const chip = (v, us, fmt, lbl, tip) => (v == null ? "" : `<div class="cv-cz-chip" title="${esc(tip)}"><b>${fmt(v)}</b><span>${esc(lbl)}</span>${us != null ? `<small>全國 ${fmt(us)}</small>` : ""}</div>`);
  const top = (row0.specialists || []).find((s) => s.ratio >= hi);
  const topRow = ROWS.find((r) => r.id === top?.row);
  const great = top && topRow ? `<div class="cv-great" style="--fc:${esc(colorOf(top.row, top.key, "#c9a45c"))}">
      <span class="cv-great-fig" data-great="${esc(top.row)}|${esc(top.key)}" aria-hidden="true"></span>
      <div><small>代表性市民</small><b>${esc(label[top.row]?.[top.key] || top.key)}</b>
      <span>占本城市${esc(lead(nounOf(topRow, data)))}的 ${pct(top.share, 1)}，全國為 ${pct(top.national, 1)}：是全國占比的 ${top.ratio.toFixed(1)} 倍。</span></div></div>` : "";

  // Only the row types this build has (a `groups` entry); the others are not part of the data at all.
  const rows = ROWS.filter((rd) => Array.isArray(groups[rd.id]) && groups[rd.id].length).map((rd) => {
    const row = row0[rd.id];
    const head = `<div class="cv-cz-h"><b>${esc(rd.title)}</b><span>${esc(data.rows?.[rd.id] || rd.sub)}</span></div>`;
    if (!row) {
      return `<div class="cv-cz-row missing" data-row="${rd.id}">${head}
        <p class="muted cv-note">資料來源沒有${esc(c.name)}的這項統計，因此不顯示此列。</p></div>`;
    }
    const { keys, n, figs, natFigs } = rowModel(rd, row, nat[rd.id], groups, data.figures || {});
    if (!figs) return `<div class="cv-cz-row missing" data-row="${rd.id}">${head}<p class="muted cv-note">此列無資料。</p></div>`;
    const per = row.total / n;
    const cells = [];
    for (const k of keys) {
      for (let j = 0; j < (figs[k] || 0); j++) {
        const sp = specs.get(`${rd.id}|${k}`);
        const mark = sp ? (sp.ratio >= 1 ? "up" : "down") : "";
        // One tab stop per category (its first figure), not one per figure.
        cells.push(`<span class="cv-fig${mark ? ` ${mark}` : ""}" tabindex="${j ? -1 : 0}" role="img" data-k="${esc(k)}" aria-label="${esc(label[rd.id]?.[k] || k)}"></span>`);
      }
    }
    // Legend: every category, with its share, the national share and a chevron for specialists. Categories that
    // round to no figure are still listed (greyed), so nothing silently disappears.
    const legend = keys.map((k) => {
      const sh = row.shares?.[k], us = nat[rd.id]?.shares?.[k];
      const sp = specs.get(`${rd.id}|${k}`);
      const chev = sp ? `<em class="${sp.ratio >= 1 ? "up" : "down"}" title="是全國占比的 ${sp.ratio.toFixed(1)} 倍">${sp.ratio >= 1 ? "▲" : "▼"}</em>` : "";
      return `<span class="cv-cz-k${figs[k] ? "" : " zero"}" data-k="${esc(k)}" title="${esc(label[rd.id]?.[k] || k)}：${sh != null ? pct(sh, 1) : "–"}${us != null ? `（全國 ${pct(us, 1)}）` : ""}${figs[k] ? "" : "。取整後不足一個人像。"}"><i style="background:${esc(colorOf(rd.id, k, "#888"))}"></i>${esc(short[rd.id]?.[k] || k)} <small>${sh != null ? pct(sh, 0) : "–"}</small>${chev}</span>`;
    }).join("");
    // National comparison bar (shares), aligned with the figures' order.
    const usBar = nat[rd.id]?.shares ? `<div class="cv-cz-us" title="全國組成（順序相同）"><span>全國</span><div>${keys.map((k) => {
      const s = nat[rd.id].shares[k] || 0;
      return s > 0 ? `<i style="flex:${s};background:${esc(colorOf(rd.id, k, "#888"))}" title="${esc(short[rd.id]?.[k] || k)}：全國 ${pct(s, 1)}"></i>` : "";
    }).join("")}</div></div>` : "";
    const cap = `每個人像 ≈ ${compact(per)} 人 · 共 ${compact(row.total)} 人（${nounOf(rd, data)}）${rd.n && !row.figures ? " · 於此處取整" : ""}`;
    const extra = rd.id === "age" && med != null ? ` · 年齡中位數 ${med.toFixed(1)} 歲${usMed != null ? `（全國 ${usMed.toFixed(1)} 歲）` : ""}` : "";
    return `<div class="cv-cz-row" data-row="${rd.id}" style="--n:${n}">${head}
      <div class="cv-figs" role="group" aria-label="${esc(rd.title)}：${esc(keys.filter((k) => figs[k]).map((k) => `${short[rd.id]?.[k] || k} ${figs[k]}/${n}`).join("、"))}">${cells.join("")}</div>
      ${usBar}
      <div class="cv-cz-out" aria-live="polite" data-default="${esc(cap + extra)}">${esc(cap + extra)}</div>
      <div class="cv-cz-legend">${legend}</div>
    </div>`;
  }).join("");

  const unreliable = row0.reliable === false
    ? `<p class="cv-warn">這裡的樣本較小、誤差較大，以下數字僅供參考。</p>` : "";
  return `
    <div class="cv-cz-top">
      ${chip(med, usMed, (v) => `${v.toFixed(1)} 歲`, "年齡中位數", "居民的年齡中位數")}
      ${chip(ba, usBa, (v) => pct(v, 0), "大學以上學歷", "具大學（學士）以上學歷者的占比")}
      ${chip(fb, usFb, (v) => pct(v, 0), "外國出生", "在其他國家出生的居民占比")}
    </div>
    ${great}
    ${unreliable}
    <div class="cv-cz${row0.reliable === false ? " unreliable" : ""}">${rows}</div>
    <p class="cv-note">${data.vintage ? `資料來源：${esc(data.vintage)}。` : ""}人像數以最大餘數法取整，每一列的加總與人像總數相符；將游標移到人像上或點按一下，可看該類別的占比。▲▼ = 占比至少是全國的 ${hi} 倍，或至多是全國的 ${lo} 倍${
      Number.isFinite(data.rule?.min_count) ? `；在本城市不足 ${int(data.rule.min_count)} 人的類別不標` : ""}。</p>`;
}

/** Paint the figure canvases and wire the read-outs. */
export function mountCitizens(host, m, data) {
  if (!host || !data?.cities?.[m.city.id]) return;
  const row0 = data.cities[m.city.id];
  const nat = data.national || {};
  const labelOf = (rid, k) => (data.groups?.[rid] || []).find((g) => g.key === k)?.label || k;
  const dpr = Math.min(3, Math.max(1, Math.round((devicePixelRatio || 1) * 2) / 2));
  const art = artOf(data.groups);
  const paintAll = () => {
    host.querySelectorAll(".cv-cz-row[data-row]").forEach((rowEl) => {
      const rid = rowEl.dataset.row;
      rowEl.querySelectorAll(".cv-fig").forEach((el) => {
        const src = figureCanvas(rid, art(rid, el.dataset.k), 36, dpr);
        const cv = document.createElement("canvas");
        cv.width = src.width;
        cv.height = src.height;
        cv.getContext("2d").drawImage(src, 0, 0);
        el.replaceChildren(cv);
      });
    });
    const g = host.querySelector("[data-great]");
    if (g) {
      const [rid, k] = g.dataset.great.split("|");
      const src = figureCanvas(rid, art(rid, k), 36, dpr);
      const cv = document.createElement("canvas");
      cv.width = src.width;
      cv.height = src.height;
      cv.getContext("2d").drawImage(src, 0, 0);
      g.replaceChildren(cv);
    }
  };
  paintAll();
  // Once the citizen painter (render/art/people.js) loads, repaint the figures.
  loadPainter().then(() => { if (host.isConnected) paintAll(); });

  host.querySelectorAll(".cv-cz-row[data-row]").forEach((rowEl) => {
    const rid = rowEl.dataset.row;
    const rd = ROWS.find((r) => r.id === rid);
    const row = row0[rid];
    const out = rowEl.querySelector(".cv-cz-out");
    if (!row || !out) return;
    const show = (k) => {
      rowEl.querySelectorAll("[data-k]").forEach((el) => el.classList.toggle("lit", el.dataset.k === k));
      rowEl.classList.toggle("focus", !!k);
      if (!k) {
        out.textContent = out.dataset.default;
        out.classList.remove("on");
        return;
      }
      const sh = row.shares?.[k], us = nat[rid]?.shares?.[k];
      out.innerHTML = `${esc(sentence(labelOf(rid, k), sh, us, m.city.name, nounOf(rd, data)))}<small>本城市 ${sh != null ? pct(sh, 1) : "–"}${us != null ? ` · 全國 ${pct(us, 1)}` : ""}${row.counts?.[k] != null ? ` · ≈${compact(row.counts[k])} 人` : ""}</small>`;
      out.classList.add("on");
    };
    let pinned = null;
    rowEl.addEventListener("pointerover", (e) => {
      const el = e.target.closest("[data-k]");
      if (el && rowEl.contains(el)) show(el.dataset.k);
    });
    rowEl.addEventListener("pointerleave", () => show(pinned));
    rowEl.addEventListener("focusin", (e) => {
      const el = e.target.closest("[data-k]");
      if (el) show(el.dataset.k);
    });
    rowEl.addEventListener("focusout", () => show(pinned));
    // A tap pins the category (phones have no hover); another tap on it lets go.
    rowEl.addEventListener("click", (e) => {
      const el = e.target.closest("[data-k]");
      if (!el) return;
      pinned = pinned === el.dataset.k ? null : el.dataset.k;
      show(pinned);
    });
  });
}
