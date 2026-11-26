import { esc, int, popShort, compact, hasCJK } from "../format.js";
import { formatLensValue } from "./lenses.js";
import { glyph } from "./icon.js";
import { FOREIGN } from "../world.js";

const el = () => document.getElementById("tooltip");

const nameOf = (table, id) => table.find((t) => t.id === id)?.name;

export function showCellTooltip(mx, my, w, i, lens, showResources = true) {
  const raw = w.raw;
  const lines = [];
  const city = w.cityByCell.get(i);
  if (city) lines.push(`<b>${esc(city.name)}</b> <span class="muted">· 人口 ${popShort(city.population)}</span>`);

  const wt = w.water[i];
  if (wt) {
    const depth = raw.elev[i] < 0 ? ` <span class="muted">· 水深 ${int(-raw.elev[i])} 公尺</span>` : "";
    lines.push(`<b>${esc(nameOf(w.tables.water, wt) || "水域")}</b>${depth}`);
  } else {
    const cover = w.cover[i] > 0 ? nameOf(w.tables.cover, w.cover[i]) : null;
    const relief = w.relief[i] > 0 ? nameOf(w.tables.relief, w.relief[i]) : null;
    const terrain = [cover, relief].filter(Boolean).join(" · ") || (relief ?? "陸地");
    lines.push(`<b>${esc(terrain)}</b> <span class="muted">· 海拔 ${int(raw.elev[i])} 公尺</span>`);
  }
  const o = raw.owner[i];
  if (o >= 0) {
    // 縣市 then 鄉鎮市區, as an address reads (臺北市信義區). A name already on the tooltip is not repeated: under a
    // city's own name line only the 鄉鎮市區 is added.
    const state = raw.states[o].name || "";
    const county = raw.county[i] >= 0 ? raw.counties[raw.county[i]].name || "" : "";
    const stateShown = city && (city.name === state || city.full === state) && county ? "" : state;
    const place = !county || county === stateShown ? stateShown
      : !stateShown ? county : hasCJK(stateShown + county) ? stateShown + county : `${county}, ${stateShown}`;
    if (place) lines.push(esc(place));
    if (lens) lines.push(`${glyph(lens, 13)} ${esc(lens.name)}：<b>${esc(formatLensValue(lens, lens.values[i]))}</b>`);
  } else if (o === FOREIGN) {
    lines.push(`<span class="muted">境外（沒有資料）</span>`);
  }
  const res = showResources && w.resources?.byCell.get(i);
  if (res) {
    for (const it of res.slice(0, 4)) {
      const t = w.resources.typeById.get(it.type);
      const num = it.value == null ? "" : Math.abs(it.value) < 1e6 ? int(it.value) : compact(it.value);
      const val = num ? ` · ${num}${t.unit ? " " + esc(t.unit) : ""}` : "";
      const kind = it.name && it.name !== t.name ? ` <span class="muted">· ${esc(t.name)}${val}</span>` : `<span class="muted">${val}</span>`;
      lines.push(`<span style="color:${esc(t.color || "#efe4c6")}">${glyph(t, 13)}</span> ${esc(it.name || t.name)}${kind}`);
    }
    if (res.length > 4) lines.push(`<span class="muted">另有 ${res.length - 4} 項</span>`);
  }
  if (city) lines.push(`<span class="muted" data-hint="open-city">點擊開啟城市</span>`);
  else if (o >= 0) lines.push(`<span class="muted">點擊開啟${esc(raw.states[o].name)}</span>`);
  show(mx, my, lines.join("<br>"));
}

/**
 * A tooltip with ready-made content: a string is HTML (escape any data yourself with format.js esc), {text} is
 * plain text. Used for registered static layers' tooltip(item).
 */
export function showHtmlTooltip(mx, my, content) {
  if (content == null || content === "") return hideTooltip();
  const html = typeof content === "string" ? content : esc(content.text ?? "");
  show(mx, my, html);
}

export function showCityTooltip(mx, my, city) {
  show(mx, my, `<b>${esc(city.full || city.name)}</b><br><span class="muted" data-hint="open-city">點擊開啟城市</span>`);
}

function show(mx, my, html) {
  const t = el();
  t.innerHTML = html;
  t.hidden = false;
  const r = t.getBoundingClientRect();
  t.style.left = Math.max(4, Math.min(window.innerWidth - r.width - 8, mx + 16)) + "px";
  t.style.top = Math.max(4, Math.min(window.innerHeight - r.height - 8, my + 16)) + "px";
}

export function hideTooltip() {
  el().hidden = true;
}
