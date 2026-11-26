// The trailer's storyboard: shots, camera moves and the words on screen. Every number shown comes from web/data at
// render time (see `facts` below); nothing here is hard-coded data.
//
// To re-render with the site's name, edit CONFIG and press Render again.
export const CONFIG = {
  title: "臺灣",
  subtitle: "畫成策略遊戲地圖，全部取自真實公開資料",
  url: "i-am-alvin.github.io/taiwanciv", // shown big on the end card ("" shows the cta line instead)
  cta: "開放原始碼 · 連結在下方", // shown on the end card instead while url is empty ("" hides the line)
};

import {
  titleCard, endCard, caption, chip, lensLegend, cityPanel, caravans, routeGlow, pulseRing, vignette, darken,
  win, smooth, easeInOut, lerp, clamp01,
} from "./overlays.js";
import { badgeOf, cityDistricts } from "../../js/ext/cityView/districts.js";

export const FPS = 30;
export const W = 1920, H = 1080;
const FADE = 0.45; // crossfade between shots, s

// --- number formatting ------------------------------------------------------------------------------------------
// Money is New Taiwan dollars, counted in 萬 / 億 / 兆 (1e4 / 1e8 / 1e12) as Taiwanese statistics are.
const int = (v) => Math.round(v).toLocaleString("zh-TW");
const money = (v) => {
  if (v >= 1e12) return `新臺幣 ${(v / 1e12).toFixed(2)} 兆元`;
  if (v >= 1e8) return `新臺幣 ${int(v / 1e8)} 億元`;
  return `新臺幣 ${int(v / 1e4)} 萬元`;
};
const moneyShort = (v) => (v >= 1e12 ? `${(v / 1e12).toFixed(2)} 兆` : v >= 1e8 ? `${int(v / 1e8)} 億` : `${int(v / 1e4)} 萬`);
const people = (v) => (v >= 1e4 ? `${int(v / 1e4)} 萬` : int(v));
const peopleShort = (v) => (v >= 1e4 ? `${(v / 1e4).toFixed(1)} 萬` : int(v));
/** Freight in thousand tonnes (trade.json tons_k) → 萬公噸. */
const tons = (k) => `${int(k / 10)} 萬公噸`;
function oneIn(share) {
  if (!(share > 0)) return "無";
  if (share >= 0.3) return `每 10 人有 ${Math.round(share * 10)} 人`;
  return `每 ${Math.round(1 / share)} 人有 1 人`;
}
// drops asides in ASCII or full-width parentheses: "人力資源調查 2025 年平均（主計總處，職業）" → "人力資源調查 2025 年平均"
const stripParen = (s) => String(s || "").replace(/（.*?）/g, "").replace(/\s*\(.*?\)\s*/g, " ").replace(/\s+/g, " ").trim();
// Short on-screen names for a few sources (the full titles are in sources.json and the app's Almanac); the year,
// when the title has one, is read from the title.
const SHORT = { srtm15: "SRTM15+", worldcover: "ESA WorldCover" };
function srcLabel(s) {
  if (!s) return "";
  if (!SHORT[s.id]) return stripParen(s.title);
  const y = /\b(19|20)\d\d\b/.exec(s.title) || /\b(19|20)\d\d\b/.exec(s.vintage || "");
  return SHORT[s.id] + (y ? ` ${y[0]}` : "");
}

// --- camera -----------------------------------------------------------------------------------------------------
/** Interpolate two camera keys: position linearly, zoom geometrically (so a zoom feels even). */
function camAt(a, b, k) {
  return { x: lerp(a.x, b.x, k), y: lerp(a.y, b.y, k), rpx: Math.exp(lerp(Math.log(a.rpx), Math.log(b.rpx), k)) };
}
/** A zoom between two keys that keeps the ground under the moving point steady (no swing): the position follows
 *  1/zoom, not time. */
function camZoom(a, b, k) {
  const rpx = Math.exp(lerp(Math.log(a.rpx), Math.log(b.rpx), k));
  const u = Math.abs(1 / b.rpx - 1 / a.rpx) < 1e-9 ? k : (1 / rpx - 1 / a.rpx) / (1 / b.rpx - 1 / a.rpx);
  return { x: lerp(a.x, b.x, u), y: lerp(a.y, b.y, u), rpx };
}
/** A flight between two far-apart keys: it rises (zooms out by up to 1 + h) mid-way, so the ground never streaks. */
function camFly(a, b, k, h = 4) {
  const c = camAt(a, b, k);
  return { ...c, rpx: c.rpx / (1 + h * Math.sin(Math.PI * k)) };
}
/** Slow-in, mostly constant speed, slow-out: for drifts that should never look parked. */
/** Quintic smootherstep: an even softer start and stop than smooth(). */
const smoother = (k) => { k = clamp01(k); return k * k * k * (k * (6 * k - 15) + 10); };
const glide = (k) => 0.35 * clamp01(k) + 0.65 * smooth(k);
/** Gentle start, peak speed early, then a long settle to rest (quartic ease-out of k^1.3). */
const easeOutQ = (k) => 1 - (1 - clamp01(k) ** 1.3) ** 4;

/** Everything the storyboard reads from the data, gathered once (so the words are checkable in one place). */
function gatherFacts(stage) {
  const { data, w } = stage;
  const g = w.grid;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (let i = 0; i < g.size; i++) {
    if (w.raw.owner[i] < 0) continue;
    const x = g.cx(i), y = g.cy(i);
    x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
  }
  const land = { x0, y0, x1, y1, cx: (x0 + x1) / 2, cy: (y0 + y1) / 2 };
  // whole-map zoom: the land fills the 1280×720 css frame with a little margin
  const css = { w: W / stage.dpr, h: H / stage.dpr };
  const homeRpx = Math.min((css.w * 0.94) / (x1 - x0 + 2 * g.R), (css.h * 0.9) / (y1 - y0 + 2 * g.R)) * g.R;
  const src = new Map(data.sources.map((s) => [s.id, s]));
  const city = (name) => data.cities.find((c) => c.name === name && c.metro);
  return { land, homeRpx, src, city, css };
}

/**
 * Build the shot list. Each shot: {id, t0, t1, render(sec) → [{view, alpha}] (map layers to blend, in order),
 * overlay(ctx, sec, frame)} where sec is the shot's local time and frame = {toScreen(x, y) → output px}.
 */
export function buildStoryboard(stage, cfg = CONFIG) {
  const { data } = stage;
  const F = gatherFacts(stage);
  const { land, homeRpx, src } = F;
  const shots = [];
  const shot = (s) => { shots.push(s); return s; };
  const WIDE = { banners: false, resources: false, labels: false }; // whole-map look: no banners or state names

  // Transitions (`trans` on the incoming shot): "dip" = through dark (only out of the title), "punch" = a quick
  // zoom-through cut between places far apart, "cut" = the camera carries on from the previous shot's last frame
  // (one continuous move across the shot boundary). Times are absolute seconds.
  const T_TERRAIN = 3.1, T_TPE = 5.8, T_LENS = 9.8, T_IMP = 15.3, T_CITY = 19.9, T_TRADE = 24.6, T_END = 27.4, T_OUT = 30;

  // 1. Title over the whole map, slow push-in. The map is already half lit on frame 0. --------------------------
  shot({
    id: "title", t0: 0, t1: T_TERRAIN + 0.2,
    render: (t) => [{ view: { ...camAt({ x: land.cx, y: land.cy, rpx: homeRpx * 0.98 }, { x: land.cx + 40, y: land.cy - 10, rpx: homeRpx * 1.1 }, t / 3.3), ...WIDE } }],
    overlay(ctx, t) {
      darken(ctx, W, H, 0.42);
      vignette(ctx, W, H, 0.85);
      titleCard(ctx, W, H, cfg, win(t, -0.5, T_TERRAIN + 0.15, 0.9, 0.4), clamp01((t + 0.4) / 1.6));
    },
  });

  // 2. Terrain: south along the Central Mountain Range, from 合歡山 toward 玉山 (a slow drift and push, ~150-200 px/s).
  const dem = src.get("srtm15"), cover = src.get("worldcover");
  const TERRAIN_T = T_TPE - T_TERRAIN;
  shot({
    id: "terrain", t0: T_TERRAIN, trans: "dip", t1: T_TPE,
    render: (t) => [{ view: camAt({ x: 3990, y: 3350, rpx: 30 }, { x: 3860, y: 3560, rpx: 37 }, glide(t / (TERRAIN_T + 0.2))) }],
    overlay(ctx, t) {
      caption(ctx, W, H, {
        kicker: "地形",
        title: "每一格都來自真實資料",
        sub: "高程與地表覆蓋畫出整張地圖",
        source: [dem, cover].filter(Boolean).map(srcLabel).join(" · "),
      }, win(t, 0.45, TERRAIN_T + 0.05, 0.45, 0.3), clamp01((t - 0.45) / 0.6));
    },
  });

  // 3. Cities: up the northwest coast from 桃園 into 臺北市, which ends on the right third, vertically centred. ---------
  const tpe = F.city("臺北市");
  const TPE_T = T_LENS - T_TPE;
  const tpeEnd = { x: tpe.x - 60, y: tpe.y + 10, rpx: 62 };
  // a slow westward drift (km/s) under the whole 臺北市 move, so the camera never parks before the pull-out
  const TPE_DRIFT = -24;
  const tpeCam = (t) => { const c = camAt({ x: tpe.x - 380, y: tpe.y + 300, rpx: 28 }, tpeEnd, smooth(t / TPE_T)); return { ...c, x: c.x + TPE_DRIFT * (t - TPE_T) }; };
  shot({
    id: "cities", t0: T_TPE, trans: "punch", t1: T_LENS,
    render: (t) => [{ view: tpeCam(t) }],
    overlay(ctx, t, frame) {
      const a = win(t, 1.3, TPE_T - 0.05, 0.5, 0.4);
      const [sx, sy] = frame.toScreen(tpe.x, tpe.y);
      pulseRing(ctx, sx, sy, frame.cam.scale * stage.R * 1.5 * 2.2, a, t);
      caption(ctx, W, H, {
        kicker: "城市",
        title: tpe.name,
        sub: `生產毛額 ${money(tpe.gdp)} · 人口 ${people(tpe.population)}`,
        source: `生產毛額：${stripParen(data.nation.gdp_vintage)} · 人口：${String(data.nation.vintage).split("；")[0]}`,
      }, a, clamp01((t - 1.3) / 0.6));
    },
  });

  // 4. Lenses: pull out of 臺北市 to the whole map as the income lens washes in, then two more lenses while the
  // camera drifts west to east. ------------------------------------------------------------------------------------
  const LENSES = ["income", "bachelors", "density"].map((id) => stage.lensById.get(id)).filter(Boolean);
  const nLens = data.lenses.lenses.length;
  const lensFmt = stage.formatLensTick;
  const legendOf = (l) => ({ name: l.name, unit: l.unit, icon: l.icon, ramp: l.ramp, lo: lensFmt(l, 0, 0), hi: lensFmt(l, 1, 4) });
  const LENS_T = T_IMP - T_LENS, ZO = 1.0, LD = (LENS_T - ZO) / LENSES.length, LK = 0.4;
  const lensA = { x: land.cx - 150, y: land.cy + 20, rpx: homeRpx * 1.04 };
  const lensB = { x: land.cx + 150, y: land.cy, rpx: homeRpx * 1.14 };
  // the pull-out starts with 臺北市's drift and hands it over to the zoom
  const lensCam = (t) => {
    if (t >= ZO) return camAt(lensA, lensB, clamp01((t - ZO) / (LENS_T - ZO)));
    const c = camZoom(tpeEnd, lensA, smooth(t / ZO));
    return { ...c, x: c.x + TPE_DRIFT * t * (1 - smooth(t / ZO)) };
  };
  // which lens is up at shot time t, and how far the change to the next one has got (0..1)
  const lensAt = (t) => {
    const u = Math.max(0, t - ZO);
    const i = Math.min(LENSES.length - 1, Math.floor(u / LD));
    const k = i < LENSES.length - 1 ? smooth((u - (i + 1) * LD + LK) / LK) : 0;
    return { i, k };
  };
  shot({
    id: "lenses", t0: T_LENS, trans: "cut", t1: T_IMP,
    // musical cues (shot-local seconds, read by score.js): each new lens
    cues: LENSES.map((l, i) => (i === 0 ? 0.1 : ZO + i * LD - LK / 2)),
    render(t) {
      const cam = lensCam(t);
      if (t < ZO) {
        return [
          { view: { ...cam } },
          { view: { ...cam, lens: LENSES[0].id, ...WIDE }, alpha: smooth((t - 0.1) / (ZO - 0.2)) },
        ];
      }
      const { i, k } = lensAt(t);
      const out = [{ view: { ...cam, lens: LENSES[i].id, ...WIDE } }];
      if (k > 0) out.push({ view: { ...cam, lens: LENSES[i + 1].id, ...WIDE }, alpha: k });
      return out;
    },
    overlay(ctx, t) {
      vignette(ctx, W, H, 0.5 * smooth(t / ZO)); // carried on (fading) by the next shot
      const { i, k } = lensAt(t);
      const whole = win(t, 0.55, LENS_T - 0.05, 0.4, 0.3);
      lensLegend(ctx, W, H, legendOf(LENSES[i]), whole, k > 0 ? legendOf(LENSES[i + 1]) : null, k);
      const cur = LENSES[k > 0.5 ? i + 1 : i];
      const s = src.get(cur.source);
      caption(ctx, W, H, {
        kicker: "濾鏡",
        title: `${nLens} 種濾鏡`,
        sub: "依所得、學歷、網速、信仰……為地圖著色",
        source: `${cur.name}：${s ? srcLabel(s) : cur.source}`,
      }, whole, clamp01((t - 0.55) / 0.6));
    },
  });

  // 5. Tile improvements: dive from the whole map into the Port of Kaohsiung, then the layers come in one by one. ----
  // (The Taiwan build has no military layer: docs/PORTING.md.)
  const khh = F.city("高雄市");
  const infra = data.infrastructure, won = data.wonders;
  const IMP_T = T_CITY - T_IMP, ZI = 1.0;
  const STAGES = [
    { at: 1.05, on: { roads: true, rail: true }, chip: { icon: "t-road", label: "國道、公路與鐵路", sub: stripParen(infra.vintage.roads) } },
    { at: 1.9, on: { hubs: true }, chip: { icon: "d-harbor", label: `全臺 ${infra.ports.length} 個國際商港 · ${infra.airports.length} 座機場`, sub: "依貨物吞吐量與旅客人次排名" } },
    { at: 2.75, on: { wonders: true }, chip: { icon: "w-landmark", label: `全臺 ${won.wonders.length} 處奇觀`, sub: "國家公園、承接計畫經費最多的大學、國定古蹟" } },
  ];
  const layersAt = (n) => Object.assign({}, ...STAGES.slice(0, n).map((s) => s.on));
  // 高雄市's anchor is its seat (鳳山區); the harbour lies ~8 km west of it
  const harA = { x: khh.x - 95, y: khh.y + 5, rpx: 62 };
  const harB = { x: khh.x - 85, y: khh.y - 5, rpx: 72 };
  const lensV = { x: (lensB.x - lensA.x) / (LENS_T - ZO), y: (lensB.y - lensA.y) / (LENS_T - ZO) }; // the lens drift, km/s
  const impCam = (t) => {
    if (t >= ZI) return camAt(harA, harB, glide((t - ZI) / (IMP_T - ZI + 0.35)));
    const c = camZoom(lensB, harA, smooth(t / ZI)), d = t * (1 - smooth(t / ZI));
    return { ...c, x: c.x + lensV.x * d, y: c.y + lensV.y * d };
  };
  shot({
    id: "improvements", t0: T_IMP, trans: "cut", t1: T_CITY,
    cues: STAGES.map((s) => s.at + 0.1), // each map layer appearing (score.js rings a bell)
    render(t) {
      const cam = impCam(t);
      if (t < ZI) {
        return [
          { view: { ...cam } },
          { view: { ...cam, lens: LENSES[LENSES.length - 1].id, ...WIDE }, alpha: 1 - smooth((t - 0.15) / (ZI - 0.3)) },
        ];
      }
      let n = 0;
      while (n < STAGES.length && t >= STAGES[n].at + 0.45) n++;
      const out = [{ view: { ...cam, layers: layersAt(n) } }];
      if (n < STAGES.length && t > STAGES[n].at) out.push({ view: { ...cam, layers: layersAt(n + 1) }, alpha: smooth((t - STAGES[n].at) / 0.45) });
      return out;
    },
    overlay(ctx, t) {
      vignette(ctx, W, H, 0.5 * (1 - smooth(t / (ZI * 0.8))));
      let y = 70;
      for (const s of STAGES) {
        const a = win(t, s.at, IMP_T - 0.1, 0.4, 0.3);
        if (a > 0) chip(ctx, 80 - (1 - smooth((t - s.at) / 0.4)) * 40, y, s.chip, a, { size: 0.9 });
        y += 86;
      }
    },
  });

  // 6. A city screen: fly up the island to 新竹市 and open its City View. ------------------------------------------
  const hc = F.city("新竹市");
  const cv = stage.cityView(hc.id);
  const bb = cv.model.bbox;
  const cit = data.citizens.cities[hc.id];
  const natW = data.citizens.national.workforce;
  const groups = data.citizens.groups.workforce;
  const figs = (fig) => groups.flatMap((g) => Array(fig[g.key] || 0).fill(g.key));
  const spec = (cit.specialists || []).find((s) => s.row === "workforce" && s.ratio > 1) || null;
  const specLabel = spec ? groups.find((g) => g.key === spec.key)?.label : null;
  const badge = badgeOf(data.districts, hc.id);
  const dists = cityDistricts(data.districts, data.military, hc.id).slice(0, 2);
  // The district's own location quotient: the same number its map plaque shows (≥ when suppressed counties make
  // it a lower bound), and the leading industry inside it by name.
  const lqLine = (d) => {
    if (d.lq == null) return d.subName || "";
    const lead = d.subName ? ` · 以${d.subName}為首` : "";
    return `就業占比為全國的 ${d.lower_bound ? "≥" : ""}${d.lq.toFixed(1)} 倍${lead}`;
  };
  const panel = {
    name: hc.name,
    full: hc.full,
    badge: badge && badge.district ? { label: badge.label, color: badge.color, icon: badge.icon } : null,
    stats: [[peopleShort(hc.population), "人口"], [moneyShort(hc.gdp), `生產毛額 ${hc.gdp_year}`], [int(hc.median_income), "每戶所得中位數（元）"]],
    highlight: spec ? `亮起：${specLabel}` : "",
    rows: [
      { label: hc.name, figs: figs(cit.workforce.figures), hi: spec?.key, ratio: spec ? oneIn(spec.share) : "" },
      { label: "全國", figs: figs(natW.figures), hi: spec?.key, ratio: spec ? oneIn(spec.national) : "" },
    ],
    districts: dists.map((d) => ({ icon: d.icon, name: d.name, line: lqLine(d) })),
    source: `${stripParen(data.citizens.vintage)} · ${stripParen(data.nation.gdp_vintage)}`,
  };
  const CITY_T = T_TRADE - T_CITY, FLY = 1.7, CITY_IN = 0.6;
  // frame: the metro in the left part of the frame (the panel covers the right 45%)
  const mapW = (W - 820 - 56) / stage.dpr; // css px of open map on the left
  const fitRpx = Math.min((mapW * 0.8) / (bb.x1 - bb.x0), (F.css.h * 0.7) / (bb.y1 - bb.y0)) * stage.R;
  const cityCam = (rpx) => {
    const s = rpx / stage.R;
    const cx = (bb.x0 + bb.x1) / 2, cy = (bb.y0 + bb.y1) / 2;
    return { x: cx + (F.css.w / 2 - mapW / 2) / s, y: cy + 10 / s, rpx };
  };
  const hcA = cityCam(fitRpx * 0.95), hcB = cityCam(fitRpx * 1.07);
  // the flight bows inland (map units east at mid-way), so the western foothills fill the frame rather than the strait
  const inland = (c, k) => ({ ...c, x: c.x + 400 * Math.sin(Math.PI * k) });
  shot({
    id: "city", t0: T_CITY, trans: "cut", t1: T_TRADE,
    cues: [FLY - CITY_IN, 1.3], // the city screen opening, the panel coming up
    render(t) {
      // after the flight the camera keeps pushing in, gathering speed into the cut
      const cam = t < FLY ? inland(camFly(impCam(IMP_T), hcA, smoother(t / FLY), 4), smoother(t / FLY)) : camAt(hcA, hcB, ((u) => 0.5 * u + 0.5 * u * u)(clamp01((t - FLY) / (CITY_T - FLY))));
      const on = smooth((t - (FLY - CITY_IN)) / CITY_IN);
      const cityAnimMs = Math.max(0, t - (FLY - CITY_IN)) * 1000;
      if (on >= 1) return [{ view: { ...cam, city: hc.id, cityAnimMs } }];
      // the Kaohsiung layers (roads, ports, …) carry over the cut and fade during the climb
      // (state names stay off during the climb: at mid-height they would fill the frame)
      const out = [{ view: { ...cam, layers: layersAt(STAGES.length) } }];
      const noNames = smooth(t / 0.35); // the state names fade out over the first frames (no pop at the cut)
      if (noNames < 1) out.push({ view: { ...cam, labels: false, layers: layersAt(STAGES.length) }, alpha: noNames });
      else out[0].view.labels = false;
      const plain = smooth((t - 0.1) / 0.6);
      if (plain > 0) out.push({ view: { ...cam, labels: false }, alpha: plain });
      if (on > 0) out.push({ view: { ...cam, city: hc.id, cityAnimMs }, alpha: on });
      return out;
    },
    overlay(ctx, t) {
      cityPanel(ctx, W, H, panel, win(t, 1.3, CITY_T + 0.3, 0.3, 0.4), clamp01((t - 1.3) / 0.7), t - 0.8);
    },
  });

  // 7. Trade routes: start on the #1 flow (高雄市 ↔ 臺南市 in the 2024 survey), pull out to all of them. ---------------
  const trade = data.trade;
  const zone = new Map(trade.zones.map((z) => [z.id, z]));
  const top = trade.routes[0];
  const topRt = stage.model.routes.find((r) => r.route === top);
  const TRADE_T = T_END - T_TRADE;
  const za = zone.get(top.a), zb = zone.get(top.b);
  const topMid = topRt ? { x: (topRt.pts[0] + topRt.pts[topRt.pts.length - 2]) / 2, y: (topRt.pts[1] + topRt.pts[topRt.pts.length - 1]) / 2 } : { x: tpe.x, y: tpe.y };
  const trA = { x: topMid.x - 40, y: topMid.y + 25, rpx: 30 };
  const endB = { x: land.cx + 10, y: land.cy + 5, rpx: homeRpx * 0.98 };
  // one pull-out from the #1 route to the whole map, decelerating all the way through the end card (no stop at the cut)
  const tradeCam = (t) => {
    const k = easeOutQ(t / (T_OUT - T_TRADE)), z = camZoom(trA, endB, k), l = camAt(trA, endB, k);
    return { x: (z.x + l.x) / 2, y: (z.y + l.y) / 2, rpx: z.rpx }; // half anchored on the route, half straight to the centre
  };
  shot({
    id: "trade", t0: T_TRADE, trans: "punch", t1: T_END,
    render(t) {
      const cam = tradeCam(t);
      return [
        { view: { ...cam, resources: false } },
        { view: { ...cam, resources: false, layers: { trade: true } }, alpha: smooth((t - 0.1) / 0.4) },
        { view: { ...cam, ...WIDE, layers: { trade: true } }, alpha: smooth((t - 0.6) / 0.45) },
      ];
    },
    overlay(ctx, t, frame) {
      caravans(ctx, stage.model.routes, frame.toScreen, t, smooth((t - 0.4) / 0.5), 1.3);
      routeGlow(ctx, topRt, frame.toScreen, t, win(t, 0.25, TRADE_T, 0.4, 0.4), 7);
      caption(ctx, W, H, {
        kicker: "貿易路線",
        title: `${trade.routes.length} 條最大的縣市間公路貨運`,
        // the survey has tonnage but no value (trade.json units.value_musd is null)
        sub: `第 1 名：${za?.short} ↔ ${zb?.short}（${int(top.dist_km)} 公里），每年 ${top.value_musd != null ? money(top.value_musd * 1e6) : tons(top.tons_k)}`,
        source: `貨車貨運噸數，雙向合計 · ${stripParen(src.get("motc_freight")?.title?.split("：")[0] || "汽車貨運調查")} ${trade.year} 年`,
      }, win(t, 0.45, TRADE_T - 0.05, 0.45, 0.3), clamp01((t - 0.45) / 0.6));
    },
  });

  // 8. End card: the camera keeps settling on the whole map as the trade arcs fade and the card comes up. ---------
    shot({
    id: "end", t0: T_END, trans: "cut", t1: T_OUT,
    render(t) {
      const cam = tradeCam(TRADE_T + t);
      return [
        { view: { ...cam, ...WIDE } },
        // the routes stay faintly lit under the card
        { view: { ...cam, ...WIDE, layers: { trade: true } }, alpha: 1 - 0.6 * smooth(t / 0.9) },
      ];
    },
    overlay(ctx, t, frame) {
      caravans(ctx, stage.model.routes, frame.toScreen, t + TRADE_T, 1 - 0.7 * smooth(t / 0.7), 1.3);
      darken(ctx, W, H, 0.55 * smooth(t / 0.5));
      vignette(ctx, W, H, 0.9 * smooth(t / 0.5));
      endCard(ctx, W, H, cfg, { facts: `${data.sources.length} 個公開資料來源 · 每個數字都查得到出處`, fallback: cfg.cta },
        smooth((t - 0.1) / 0.5), clamp01((t - 0.15) / 0.6));
    },
  });

  const duration = T_OUT;
  return { shots, duration, fps: FPS, frames: Math.round(duration * FPS), fade: FADE, cfg, facts: F, panel };
}

/** Shots visible at absolute time T, each with its transition progress `alpha` (0..1 over the incoming shot's fade).
 * A shot stays on screen until the next one is fully in (whatever its own t1 says), and everything under a fully
 * opaque shot is dropped. Transitions (`trans` on the incoming shot): undefined = crossfade (FADE s); "dip" = through
 * dark (DIP s); "punch" = zoom-through cut (PUNCH s; main.js draws it); "cut" = none (the camera carries on). */
const DIP = 0.6, PUNCH = 0.4;
export const fadeOf = (sb, s) => s.fade ?? ({ dip: DIP, punch: PUNCH, cut: 0 }[s.trans] ?? sb.fade);
export function activeShots(sb, T) {
  const out = [];
  sb.shots.forEach((s, i) => {
    const next = sb.shots[i + 1];
    const end = next ? Math.max(s.t1, next.t0 + fadeOf(sb, next)) : s.t1;
    if (T < s.t0 || T >= end) return;
    const f = fadeOf(sb, s);
    const alpha = i === 0 || f <= 0 ? 1 : clamp01((T - s.t0) / f);
    out.push({ shot: s, alpha: s.trans ? alpha : smooth(alpha), sec: T - s.t0 });
  });
  let k = out.length - 1;
  while (k > 0 && out[k].alpha < 1) k--;
  return out.slice(k);
}
