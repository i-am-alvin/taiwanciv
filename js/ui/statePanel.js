import { css } from "../color.js";
import { esc, popShort } from "../format.js";
import { isCapital } from "../world.js";
import { yieldGrid, amenities, industries, gdpRow, gdpLabel, popLine, growthSpan, showPanel } from "./infoPanel.js";

/**
 * Opens the panel for state `idx` (index into world.json states / states.json).
 * ctx: {w, nation, states (states.json or null), cities, onClose, onPedia, onCity(city)}
 */
export function openStatePanel(idx, ctx) {
  const { w, nation } = ctx;
  const n = nation.nation;
  const geo = w.raw.states[idx] || {};
  // states.json is in the same order as world.json states; fall back to matching by fips.
  let st = ctx.states?.[idx];
  if (st && geo.fips && st.fips && st.fips !== geo.fips) st = ctx.states.find((s) => s.fips === geo.fips);
  st = st || { ...geo };
  const name = st.name || geo.name || "縣市";
  const abbr = st.abbr || geo.abbr || "";
  const count = ctx.states?.length || w.raw.states.length;

  const cities = (ctx.cities || []).filter((c) => (c.states || []).includes(abbr)).slice(0, 8);
  const stateName = (a) => w.raw.states.find((s) => s.abbr === a)?.name || a;
  const cityRows = cities.length
    ? `<div class="city-list">${cities
        .map((c) => {
          const multi = (c.states || []).length > 1 ? `<span class="muted"> · ${esc(c.states.map(stateName).join("、"))}</span>` : "";
          return `<button class="city-row" data-city="${esc(c.id)}" title="${esc(c.full || c.name)}">
            <span class="cr-name">${isCapital(c) ? "★ " : ""}${esc(c.name)}${multi}</span>
            <span class="cr-pop">${popShort(c.population)}</span><span class="cr-go" aria-hidden="true">›</span></button>`;
        })
        .join("")}</div>`
    : `<p class="muted">這個縣市的資料裡沒有城市。</p>`;

  const hasEcon = st.population != null || st.yields;
  const living = hasEcon ? (amenities(st, n, nation) + gdpRow(st, nation)).trim() : "";
  showPanel({
    kind: "state",
    stripe: css(w.stateColor[idx] || [190, 190, 190]),
    title: name,
    sub: [st.name_en || geo.name_en, abbr, geo.fips ? `縣市代碼 ${geo.fips}` : ""].filter(Boolean).map(esc).join(" · "),
    headExtra: hasEcon ? popLine(st, growthSpan(st, n)) : "",
    sections: [
      st.yields && { title: "產出 · 縣市排名", html: `<div class="yield-grid">${yieldGrid(nation, st.yields, st.ranks, count)}</div>` },
      living && { title: "宜居度與住房", html: living },
      st.jobs && { title: "主要產業 · 就業分布", html: industries(st, nation, 8) },
      { title: cities.length > 1 ? "最大的城市" : "城市", html: cityRows },
      !hasEcon && { title: "資料", html: `<p class="muted">這一版資料沒有縣市統計（缺少 states.json）。</p>` },
    ],
    foot: `資料來源：${esc(nation.vintage || "")}${nation.gdp_vintage ? `；${esc(gdpLabel(nation))}：${esc(nation.gdp_vintage)}` : ""}。排名是地圖上 ${count} 個縣市之間的比較（第 1 名最大）。`,
    onClose: ctx.onClose,
    onPedia: ctx.onPedia,
    wire(panel) {
      panel.querySelectorAll("[data-city]").forEach((b) => {
        b.onclick = () => {
          const c = ctx.cities.find((x) => x.id === b.dataset.city);
          if (c) ctx.onCity(c);
        };
      });
    },
  });
}
