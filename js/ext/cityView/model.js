// City View data model: everything the city screen and its map layer show, derived from cities.json,
// nation.json, lenses.json, world.json and resources.json. Pure functions over app.data / app.w (no DOM).

// Industry → district colour (the medallion behind its icon) and icon id (icons.js i-<key>). The label comes from
// nation.json `industries` (the pipeline writes the official names in Chinese); `short` is only the fallback for a
// key the data does not name. The keys are whatever the data has: none of them is assumed to exist.
export const INDUSTRY = {
  agriculture: { short: "農林漁牧業", color: "#4f7a2a" },
  mining: { short: "礦業", color: "#6a5038" },
  construction: { short: "營建工程業", color: "#8a5426" },
  manufacturing: { short: "製造業", color: "#9a5a22" },
  wholesale: { short: "批發業", color: "#7a6420" },
  retail: { short: "批發及零售業", color: "#8a6a1e" },
  transportation: { short: "運輸及倉儲業", color: "#3d5f73" },
  utilities: { short: "電力、燃氣及用水", color: "#2a5f86" },
  information: { short: "資訊及通訊傳播業", color: "#25557e" },
  finance: { short: "金融及保險業", color: "#7a6420" },
  real_estate: { short: "不動產業", color: "#6b4a2f" },
  professional: { short: "專業及科技服務業", color: "#2b4f8a" },
  management: { short: "企業管理", color: "#4a4a7a" },
  admin: { short: "支援服務業", color: "#4b5a68" },
  education: { short: "教育業", color: "#2a3f7a" },
  health: { short: "醫療保健業", color: "#7a2f2f" },
  arts: { short: "藝術及娛樂業", color: "#5b3a7e" },
  accommodation: { short: "住宿及餐飲業", color: "#6e3a5e" },
  other: { short: "其他服務業", color: "#4b4b4b" },
  public_admin: { short: "公共行政", color: "#3a5a4a" },
  government: { short: "公共行政", color: "#3a5a4a" },
};
export const industryIcon = (k) => `i-${k === "government" ? "public_admin" : k}`;
/** An industry's display name: the data's own (nation.json industries), else the fallback above, else the key. */
export const industryName = (nation, key) => nation?.industries?.[key] || INDUSTRY[key]?.short || key;

// Land-use groups shown as a hex's "tile yield" (world.json pct keys → group). Cover ids give the map colour.
export const LAND = [
  { key: "built", label: "建成區", icon: "l-developed", cover: 9, keys: ["developed"] },
  { key: "farm", label: "農地", icon: "l-farmland", cover: 7, keys: ["crop", "pasture"] },
  { key: "forest", label: "森林", icon: "l-forest", cover: 3, keys: ["forest"] },
  { key: "open", label: "開闊地", icon: null, cover: 4, keys: ["grass", "shrub", "wetland"] },
];

const sum = (o) => Object.values(o || {}).reduce((a, v) => a + (Number.isFinite(v) ? v : 0), 0);
// km² of one hex. The grid radius is in map units; world.json `projection.scale` says how many map units make a
// km (12.5 on the Taiwan map; absent on a map whose units are km).
const HEX_AREA = (R, scale = 1) => (3 * Math.sqrt(3) / 2) * (R / scale) * (R / scale);
export const mapScale = (w) => {
  const s = w?.raw?.projection?.scale;
  return Number.isFinite(s) && s > 0 ? s : 1;
};
// Names differ only by 台 / 臺 or surrounding space when they mean the same 縣市.
const sameName = (a, b) => !!a && !!b && String(a).trim().replace(/台/g, "臺") === String(b).trim().replace(/台/g, "臺");

/** Industries by jobs (where residents work) with location quotients vs the nation. */
export function jobIndustries(city, nation) {
  const n = nation.nation;
  const total = city.employed || sum(city.jobs) || 1;
  const nTotal = n.employed || sum(n.jobs) || 1;
  return Object.entries(city.jobs || {})
    .filter(([, v]) => Number.isFinite(v) && v > 0)
    .map(([key, jobs]) => {
      const share = jobs / total;
      const natShare = (n.jobs?.[key] || 0) / nTotal;
      return {
        key, jobs, share, natShare, lq: natShare > 0 ? share / natShare : null,
        label: industryName(nation, key), short: industryName(nation, key),
        color: INDUSTRY[key]?.color || "#3a4a5e", icon: industryIcon(key),
      };
    })
    .sort((a, b) => b.jobs - a.jobs);
}

/** GDP by industry with shares and location quotients vs the national GDP shares. */
export function gdpIndustries(city, nation) {
  const g = city.gdp_by_industry;
  const ng = nation.nation.gdp_by_industry || {};
  if (!g) return [];
  // Shares of the metro's whole GDP (not of the disclosed industries only), so a withheld sector cannot inflate
  // the others.
  const total = Number.isFinite(city.gdp) && city.gdp > 0 ? city.gdp : sum(g) || 1;
  const nTotal = Number.isFinite(nation.nation.gdp) && nation.nation.gdp > 0 ? nation.nation.gdp : sum(ng) || 1;
  const est = new Set(city.gdp_estimated || []);
  const rows = Object.entries(g)
    .filter(([, v]) => Number.isFinite(v) && v > 0)
    .map(([key, value]) => {
      const share = value / total, natShare = (ng[key] || 0) / nTotal;
      return {
        key, value, share, natShare, lq: natShare > 0 ? share / natShare : null, estimated: est.has(key),
        label: industryName(nation, key), short: industryName(nation, key),
        color: INDUSTRY[key]?.color || "#3a4a5e", icon: industryIcon(key),
      };
    })
    .sort((a, b) => b.value - a.value);
  // What the source still withholds after recovery, as its own grey row.
  const und = Number.isFinite(city.gdp_undisclosed) ? city.gdp_undisclosed
    : Object.values(g).some((v) => v == null) && Number.isFinite(city.gdp) ? Math.max(0, city.gdp - sum(g)) : 0;
  if (und > 0) {
    const missing = Object.entries(g).filter(([, v]) => v == null).map(([k]) => k);
    rows.push({
      key: "undisclosed", value: und, share: und / total, natShare: 0, lq: null, undisclosed: true, missing,
      label: "未公開", short: "未公開", color: "#4a5260", icon: "lock",
    });
  }
  return rows;
}

function landOf(w, cell) {
  if (!w.pct) return null;
  let best = null, tot = 0;
  for (const g of LAND) {
    const v = g.keys.reduce((a, k) => a + (w.pct[k]?.[cell] || 0), 0);
    tot += v;
    if (!best || v > best.share) best = { ...g, share: v };
  }
  if (!best || tot <= 0) return null;
  return { ...best, share: best.share / 100 };
}

/**
 * Everything the City View shows for one city.
 * Per footprint hex: estimated residents (lens "density" value × hex area: an estimate, not a count) and the
 * dominant land-use group with its share of the hex's land.
 */
export function buildModel(app, city) {
  const { w } = app;
  const { nation, cities, resources, lenses } = app.data;
  const grid = w.grid;
  const N = cities.length;
  const owner = w.raw.owner;
  const stateIdx = city.cell != null ? owner[city.cell] : -1;
  const stateRGB = w.stateColor[stateIdx] || [201, 164, 92];

  const footprint = (Array.isArray(city.footprint) && city.footprint.length ? city.footprint : [city.cell])
    .filter((c) => c != null && c >= 0);
  const mask = new Set(footprint);

  // Resource sites of the metro (resources.json items tagged with this cbsa), biggest first per type.
  const items = resources?.items || [];
  const typeById = new Map((resources?.types || []).map((t) => [t.id, t]));
  const sites = [];
  items.forEach((it, index) => {
    if (it.cbsa === city.id) sites.push({ item: it, index, type: typeById.get(it.type) || null });
  });
  const catRank = { energy: 0, mineral: 1, agri: 2 };
  sites.sort((a, b) => (catRank[a.type?.category] ?? 3) - (catRank[b.type?.category] ?? 3)
    || (b.item.value ?? 0) - (a.item.value ?? 0));
  const siteCells = new Map(); // cell -> [site]
  for (const s of sites) {
    if (s.item.cell == null) continue;
    if (!siteCells.has(s.item.cell)) siteCells.set(s.item.cell, []);
    siteCells.get(s.item.cell).push(s);
  }

  // Per-hex tile yields.
  const density = lenses?.lenses?.find((l) => l.id === "density");
  const area = HEX_AREA(grid.R, mapScale(w)); // km², so density (people / km²) × area = residents
  const tiles = footprint.map((cell) => {
    const d = density?.values?.[cell];
    return {
      cell, x: grid.cx(cell), y: grid.cy(cell),
      residents: Number.isFinite(d) ? d * area : null,
      land: landOf(w, cell),
      isCity: cell === city.cell,
    };
  });

  // Industries by jobs and GDP by industry. The map's districts are the real ones from districts.json, placed by
  // placeDistricts() once that file arrives; until then (or when the build has no such file) there are none.
  const inds = jobIndustries(city, nation);
  const gdpInds = gdpIndustries(city, nation);
  // District plaques go on footprint hexes near the centre that have no resource site and no other city; the rest
  // (small metros) sit in a row inside the city's own hex.
  const cx = grid.cx(city.cell), cy = grid.cy(city.cell);
  // The city's banner stands over the hexes just north of it, so those come after the other near hexes.
  const R = grid.R;
  const cost = (c) => {
    const dx = grid.cx(c) - cx, dy = grid.cy(c) - cy;
    return Math.hypot(dx, dy) + (dy < -0.5 * R && dy > -3.2 * R && Math.abs(dx) < 3 * R ? 3 * R : 0);
  };
  const free = footprint
    .filter((c) => c !== city.cell && !siteCells.has(c) && !w.cityByCell.has(c))
    .sort((a, b) => cost(a) - cost(b) || a - b);

  // Bounding box of the footprint (map units).
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const c of footprint) {
    const x = grid.cx(c), y = grid.cy(c);
    x0 = Math.min(x0, x - grid.R); x1 = Math.max(x1, x + grid.R);
    y0 = Math.min(y0, y - grid.R); y1 = Math.max(y1, y + grid.R);
  }

  const peers = (city.peers || []).map((id) => app.cityById.get(id)).filter(Boolean);
  // A 縣市 is both the city and its "state": `self` marks the state that is the city itself (same code or same
  // name), so the screen never prints the name twice. Abbreviations are 3-letter ISO codes; names read better.
  const stateName = (abbr) => {
    const i = w.raw.states.findIndex((s) => s.abbr === abbr);
    return i >= 0 ? (app.data.states?.[i]?.name || w.raw.states[i].name) : abbr;
  };
  const isSelf = (c, i, name) => (i >= 0 && w.raw.states[i].fips === c.id) || sameName(name, c.name) || sameName(name, c.full);
  const states = (city.states || []).map((abbr) => {
    const i = w.raw.states.findIndex((s) => s.abbr === abbr);
    const name = stateName(abbr);
    return { abbr, index: i, name, self: isSelf(city, i, name) };
  });
  /** Names of the 縣市 behind these abbreviations that are not the city `c` itself ([] for a city that is its own 縣市). */
  const otherStates = (c, abbrs) => (abbrs || []).filter(Boolean).map((abbr) => {
    const i = w.raw.states.findIndex((s) => s.abbr === abbr);
    const name = stateName(abbr);
    return isSelf(c, i, name) ? null : name;
  }).filter(Boolean);
  const residentsSum = tiles.reduce((a, t) => a + (t.residents || 0), 0);

  return {
    city, N, nation, stateIdx, hexArea: area, stateRGB, states, stateName, otherStates, footprint, mask, tiles, residentsSum,
    sites, siteCells, inds, gdpInds, free, districts: [], placed: [], inCity: [],
    bbox: Number.isFinite(x0) ? { x0, y0, x1, y1 } : null,
    peers,
  };
}

/**
 * Put the metro's districts on the map (schematic positions): the first ones on the free footprint hexes nearest
 * the city, the rest in a row inside the city's own hex. list = [{id, short, mapLq, color, icon, …}] (districts.js
 * cityDistricts). Sets m.districts, m.placed and m.inCity; the map layer reads them on its next frame.
 */
export function placeDistricts(m, list) {
  const ds = (list || []).map((d) => ({ ...d, lq: d.mapLq ?? null }));
  m.districts = ds;
  m.placed = [];
  m.inCity = [];
  ds.forEach((d, k) => {
    if (k < m.free.length) m.placed.push({ ...d, cell: m.free[k] });
    else m.inCity.push(d);
  });
}

/** Population series [{year, value}] from pop_series (null years dropped). */
export function popSeries(city) {
  const s = city.pop_series;
  if (!s || typeof s !== "object") return [];
  return Object.entries(s)
    .filter(([, v]) => Number.isFinite(v))
    .map(([y, v]) => ({ year: +y, value: v }))
    .sort((a, b) => a.year - b.year);
}

/** How many cities have a non-null rank for this key (the "of N"). */
export function rankCount(cities, key) {
  let n = 0;
  for (const c of cities) if (c.ranks?.[key] != null) n++;
  return n;
}

/** A resource value with its unit, short ("3.9 GW", "878 人"). */
export function resourceValue(item, type, compact) {
  const v = item.value;
  if (!Number.isFinite(v)) return "";
  const u = type?.unit || "";
  if (u === "MW") return v >= 1000 ? `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)} GW` : `${Math.round(v)} MW`;
  if (u === "employees") return `${compact(v)} 人`;
  if (/tons/.test(u)) return `${compact(v)} 公噸/年`;
  if (/km²/.test(u)) return `${compact(v)} km²`;
  return `${compact(v)} ${u}`.trim();
}
