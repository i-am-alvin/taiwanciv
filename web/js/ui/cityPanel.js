import { css } from "../color.js";
import { esc } from "../format.js";
import { isCapital } from "../world.js";
import { yieldGrid, amenities, industries, gdpRow, gdpLabel, popLine, growthSpan, showPanel, hidePanel } from "./infoPanel.js";

/**
 * ctx: {w, nation, onClose, onPedia, onState(stateIndex)}
 */
export function openCityPanel(city, ctx) {
  const { w, nation } = ctx;
  const n = nation.nation;
  const owner = city.cell != null ? w.raw.owner[city.cell] : -1;
  const col = css(w.stateColor[owner] || [190, 190, 190]);

  // The city's states as links to their state panels, by name (the ISO code means little to a reader). In Taiwan a
  // city's only state is the 縣市 itself: that chip reads 縣市面板 instead of repeating the city's own name.
  const own = (s) => s.name === city.name || s.name === city.full || (s.fips != null && String(s.fips) === String(city.id));
  const states = (city.states || [])
    .map((abbr) => ({ abbr, i: w.raw.states.findIndex((s) => s.abbr === abbr) }))
    .map(({ abbr, i }) => {
      const s = i >= 0 ? w.raw.states[i] : null;
      if (s && own(s)) return ctx.onState ? `<button class="chip" data-state="${i}" title="開啟${esc(s.name)}的縣市面板">縣市面板 ›</button>` : "";
      return s && ctx.onState
        ? `<button class="chip" data-state="${i}" title="開啟${esc(s.name)}">${esc(s.name)}</button>`
        : `<span class="chip">${esc(s?.name || abbr)}</span>`;
    })
    .join("");
  // Under the title: what `full` adds to the name (新北市 New Taipei City → New Taipei City) and the seat, if given.
  const full = String(city.full || "");
  const extra = full.startsWith(city.name) ? full.slice(String(city.name).length).trim() : full;
  const sub = [extra || (city.name_en && city.name_en !== city.name ? city.name_en : ""), city.seat ? `城市標示於${city.seat}（人口最多的鄉鎮市區）` : ""].filter(Boolean).map(esc).join(" · ");

  const growth = growthSpan(city, n);
  const living = (amenities(city, n, nation) + gdpRow(city, nation)).trim();

  showPanel({
    kind: "city",
    stripe: col,
    title: city.name,
    titleHtml: `${isCapital(city) ? `<span class="cap" title="首都">★</span> ` : ""}${esc(city.name)}`,
    sub: `${sub}${states ? `<div class="chips">${states}</div>` : ""}`,
    headExtra: popLine(city, growth),
    sections: [
      { title: "產出", html: `<div class="yield-grid">${yieldGrid(nation, city.yields)}</div>` },
      living && { title: "宜居度與住房", html: living },
      { title: "產業 · 就業分布", html: industries(city, nation) },
    ],
    foot: `資料來源：${esc(nation.vintage || "")}${nation.gdp_vintage ? `；${esc(gdpLabel(nation))}：${esc(nation.gdp_vintage)}` : ""}。
      綠色的 ×N 表示這個產業的就業占比是全國的 N 倍。`,
    onClose: ctx.onClose,
    onPedia: ctx.onPedia,
    wire(panel) {
      panel.querySelectorAll("[data-state]").forEach((b) => (b.onclick = () => ctx.onState(+b.dataset.state)));
    },
  });
}

export const closeCityPanel = hidePanel;
