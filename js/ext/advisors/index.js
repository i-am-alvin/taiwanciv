// Advisors: Civ-style exploration dashboards docked beside the map, linked both ways with it.
//
//   app mode "advisor", params {id, ...}  (id = an advisor id, or none for the council picker)
//   URL hash: #advisor=<id> ("council" for the picker)
//   top-bar button "顧問團"
// An advisor with `needs: "<file>"` is about an optional data file: it is offered (tab, council card, deep link)
// only while app.data has that file. military.json is left out of the Taiwan build on purpose, so that advisor
// never shows.
// Each advisor is a module in views/ exporting mount(ctx) → {onMapHover?, onMapClick?, onEscape?, destroy?}.
// ctx = {app, data, el, link, params, on(name, fn), bubbles(id, opts), tip, setResourceFilter, setShowResources,
//        switchTo(id, params)} — everything registered through ctx is undone when the view goes away.
import { buildData } from "./core/data.js";
import { createLinker, createBubbles, createMapTip } from "./core/link.js";
import { emblem } from "./core/emblems.js";
import { frameNation } from "./core/frame.js";
import { esc, el } from "./core/util.js";
import { icon } from "../../ui/icon.js";

export const ADVISORS = [
  { id: "energy", name: "能源與資源", role: "能源大臣", color: "#d98a2b", dark: "#3a1f08", blurb: "電力從哪裡來：各類電廠的位置與裝置容量。", load: () => import("./views/energy.js") },
  { id: "economy", name: "經濟", role: "財政大臣", color: "#c9a43a", dark: "#3a2c08", blurb: "各縣市的生產毛額與產業結構，以及領先的城市。", load: () => import("./views/economy.js") },
  { id: "people", name: "人口", role: "戶政總管", color: "#c46a4f", dark: "#3a140c", blurb: "人住在哪裡、往哪裡移動，各地的年齡結構又是如何。", load: () => import("./views/people.js") },
  { id: "prosperity", name: "所得與住房", role: "民生總管", color: "#3f9c82", dark: "#082a22", blurb: "所得、房價與失業，以及過得比較辛苦的地方。", load: () => import("./views/prosperity.js") },
  { id: "knowledge", name: "知識", role: "首席學者", color: "#4a86d6", dark: "#0a1c3a", blurb: "學歷與科研人力的分布。", load: () => import("./views/knowledge.js") },
  { id: "land", name: "土地", role: "測繪總長", color: "#6e9a3c", dark: "#18280a", blurb: "森林、農地與城市：這片土地上覆蓋著什麼。", load: () => import("./views/land.js") },
  { id: "military", needs: "military", name: "軍事", role: "將軍", color: "#8796ab", dark: "#141b26", blurb: "基地與訓練場、各縣市的兵力與國防支出，以及退伍軍人的分布。", load: () => import("./views/military.js") },
  { id: "commerce", name: "商貿", role: "貿易大臣", color: "#2fa4b8", dark: "#062630", blurb: "城市之間的主要貨運路線，以及最繁忙的港口與機場。", load: () => import("./views/commerce.js") },
  { id: "culture", name: "文化", role: "奇觀守護者", color: "#c25b9a", dark: "#2e0c22", blurb: "這片土地上的奇觀，以及各地的文化與生活面貌。", load: () => import("./views/culture.js") },
  { id: "explorer", name: "資料探索", role: "製圖師", color: "#9a7bc9", dark: "#1e1236", blurb: "自由切換層級、欄位與圖表，交叉比對每一項數字。", load: () => import("./views/explorer.js") },
];
const byId = new Map(ADVISORS.map((a) => [a.id, a]));
// The council picker groups its advisors (any advisor not listed here is added to the last group).
const COUNCIL = (() => {
  const g = [
    { label: "財富與工作", ids: ["economy", "prosperity", "commerce", "energy"] },
    { label: "人口與土地", ids: ["people", "knowledge", "culture", "land"] },
    { label: "國防", ids: ["military"] },
    { label: "自由探索", ids: ["explorer"] },
  ];
  const listed = new Set(g.flatMap((x) => x.ids));
  g[g.length - 1].ids.push(...ADVISORS.filter((a) => !listed.has(a.id)).map((a) => a.id));
  return g;
})();
// 460 px, narrower below 1200 px wide so the whole country still fits beside the dock (matches advisors.css).
const dockW = () => (innerWidth >= 1200 ? 460 : Math.round(Math.min(460, Math.max(340, innerWidth * 0.38))));

function injectCss() {
  if (document.getElementById("advisors-css")) return;
  const l = document.createElement("link");
  l.id = "advisors-css";
  l.rel = "stylesheet";
  l.href = new URL("../../../css/advisors.css", import.meta.url).href;
  document.head.appendChild(l);
}

export function install(app) {
  injectCss();
  let data = null, dataP = null;
  let dock = null;
  let active = null; // {adv, api, cleanup: [fn], bubbles: [b], token}
  let current = null; // advisor id or "council"
  let pendingTeardown = false;
  let token = 0;
  let lastId = null;
  let framedFor = null; // the advisor the map was last framed for
  let prevCam = null; // the camera when the advisors opened
  const link = createLinker(app);
  const tip = createMapTip();
  const canvas = document.getElementById("map");

  const ensureData = () => (dataP ??= app.loadCounties().catch(() => null).then(() => (data = buildData(app))));
  // Advisors on offer: all of them, except one whose optional data file is not loaded (see `needs` above).
  const available = (a) => !!a && (!a.needs || app.data?.[a.needs] != null);
  const offered = () => ADVISORS.filter(available);

  // --- top-bar button ---------------------------------------------------------------------------------------------
  const btn = app.ui.addTopButton({
    id: "btn-advisors", icon: "g-people", label: "顧問團", title: "顧問團：探索地圖背後的數據",
    onClick: () => (app.mode === "advisor" ? app.setMode(null) : app.setMode("advisor", { id: lastId })),
  });
  if (btn) {
    btn.innerHTML = `<svg class="icon" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 2.5 3 7v2h18V7z" fill="currentColor"/><path d="M5 10.5h2.6v7H5zM10.7 10.5h2.6v7h-2.6zM16.4 10.5H19v7h-2.6zM3.5 19h17v2.5h-17z" fill="currentColor"/></svg><span class="lbl">顧問團</span>`;
    btn.setAttribute("aria-pressed", "false");
  }
  app.on("mode", ({ name }) => btn?.setAttribute("aria-pressed", String(name === "advisor")));

  // --- dock shell -------------------------------------------------------------------------------------------------
  const tabsHtml = () => offered().map((a) => `<button type="button" role="tab" data-adv="${a.id}" aria-selected="false" title="${esc(`${a.name}：${a.role}`)}" style="--adv:${a.color}">${emblem(a, 30)}<span class="sr-only">${esc(a.name)}</span></button>`).join("");
  /** Mark the current advisor's tab (and keep exactly one tab in the focus order). */
  function syncTabs(root) {
    const tabs = [...root.querySelectorAll(".adv-tabs [role=tab]")];
    const any = tabs.some((b) => b.dataset.adv === current);
    tabs.forEach((b, i) => {
      const on = b.dataset.adv === current;
      b.setAttribute("aria-selected", String(on));
      b.tabIndex = on || (!any && i === 0) ? 0 : -1;
    });
  }
  function shell() {
    dock = app.ui.dock("left", { width: dockW(), label: "顧問團" });
    if (dock.querySelector(".adv-root")) return dock.querySelector(".adv-root");
    dock.innerHTML = "";
    dock.classList.add("adv-dock");
    const root = el("div", "adv-root");
    root.innerHTML = `
      <div class="adv-grip" aria-hidden="true"></div>
      <header class="adv-head">
        <button type="button" class="adv-council-btn" data-adv="council" title="所有顧問">${icon("g-people", "👥", { size: 14 })}<span>顧問總覽</span></button>
        <nav class="adv-tabs" role="tablist" aria-label="顧問團">${tabsHtml()}</nav>
        <button type="button" class="icon-btn adv-close" aria-label="關閉顧問團（Esc）" title="關閉（Esc）">${icon("close", "✕", { size: 12 })}</button>
      </header>
      <div class="adv-main" tabindex="-1"></div>`;
    dock.appendChild(root);
    root.addEventListener("click", (e) => {
      const t = e.target.closest("button");
      if (!t) return;
      if (t.classList.contains("adv-close")) return app.setMode(null);
      if (t.dataset.adv) return switchTo(t.dataset.adv === "council" ? null : t.dataset.adv);
      if (t.dataset.pedia) return app.pedia?.open?.(t.dataset.pedia);
      if (t.hasAttribute("data-frame")) return link.frame() || frameNation(app);
    });
    root.querySelector(".adv-tabs").addEventListener("keydown", (e) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
      const tabs = [...root.querySelectorAll(".adv-tabs [role=tab]")];
      let i = tabs.indexOf(document.activeElement);
      i = e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
      e.preventDefault();
      tabs[i].focus();
      switchTo(tabs[i].dataset.adv);
    });
    return root;
  }

  function switchTo(id, params = {}) {
    if (app.mode === "advisor" && (id || "council") === current && !Object.keys(params).length) return;
    app.setMode("advisor", { ...params, id: id || null });
  }

  // --- views ------------------------------------------------------------------------------------------------------
  function teardownView() {
    if (!active) return;
    const a = active;
    active = null;
    try { a.api?.destroy?.(); } catch (err) { console.error("advisor destroy failed", err); }
    dispose(a);
    link.clear();
    tip.hide();
  }
  // Run (and forget) a view's cleanups and bubbles; safe to call again for anything registered later.
  function dispose(a) {
    const fns = a.cleanup.splice(0).reverse(), bs = a.bubbles.splice(0);
    for (const f of fns) { try { f(); } catch (err) { console.error(err); } }
    for (const b of bs) b.destroy();
  }

  async function show(id, params) {
    const my = ++token;
    const root = shell();
    let adv = id ? byId.get(id) : null;
    // An advisor about an optional file that is not there (or not there yet) falls back to the council.
    if (adv && !available(adv)) adv = null;
    current = adv ? adv.id : "council";
    if (adv) lastId = adv.id;
    root.style.setProperty("--adv", adv?.color || "#c9a45c");
    syncTabs(root);
    root.querySelector(".adv-council-btn").setAttribute("aria-pressed", String(!adv));
    teardownView();
    // Every advisor is national in scope: frame the whole country beside the dock when one opens (or the council
    // first appears), not when the same advisor is re-shown with new parameters.
    if (current !== framedFor) {
      framedFor = current;
      requestAnimationFrame(() => { if (my === token && app.mode === "advisor") frameNation(app); });
    }
    const main = root.querySelector(".adv-main");
    main.scrollTop = 0;
    dock.scrollTop = 0;
    if (!adv) {
      main.innerHTML = councilHtml();
      main.querySelectorAll(".adv-card").forEach((c) => c.addEventListener("click", () => switchTo(c.dataset.adv)));
      return;
    }
    main.innerHTML = `${titleHtml(adv)}<div class="adv-body"><div class="adv-loading">${esc(adv.role)}正在彙整數據…</div></div>`;
    let mod;
    try {
      [mod] = await Promise.all([adv.load(), ensureData()]);
    } catch (err) {
      console.error(err);
      if (my === token) main.querySelector(".adv-body").innerHTML = `<p class="adv-empty pad">這位顧問的面板無法載入（${esc(err.message || err)}）。</p>`;
      return;
    }
    if (my !== token || app.mode !== "advisor") return;
    const body = main.querySelector(".adv-body");
    // The loading line stays while an advisor that awaits its own files mounts; it is removed once the view is up.
    const loading = body.querySelector(".adv-loading");
    body.replaceChildren(...(loading ? [loading] : []));
    const a = { adv, api: null, cleanup: [], bubbles: [], token: my };
    active = a;
    const ctx = {
      app, data, el: body, link, tip, params: params || {}, advisor: adv,
      on(name, fn) { const off = app.on(name, fn); a.cleanup.push(off); return off; },
      bubbles(id, opts = {}) {
        const b = createBubbles(app, `adv-${adv.id}-${id}`, opts);
        b.handlers = opts;
        a.bubbles.push(b);
        return b;
      },
      setResourceFilter(f) {
        if (!a.savedFilter) { a.savedFilter = { f: app.state.resourceFilter }; a.cleanup.push(() => app.setResourceFilter(a.savedFilter.f)); }
        app.setResourceFilter(f);
      },
      setShowResources(on) {
        if (!a.savedShow) { a.savedShow = { v: app.state.showResources }; a.cleanup.push(() => app.setShowResources(a.savedShow.v)); }
        app.setShowResources(on);
      },
      /** Colour the map with a lens (a lenses.json id, a lens object, or null) while this view is open. The lens the
       *  viewer had is restored on exit, unless they have picked another one themselves since. */
      setLens(ref) {
        if (!a.lensSaved) {
          a.lensSaved = { lens: app.state.lens, ours: new Set() };
          a.cleanup.push(() => {
            const cur = app.state.lens;
            if (cur === a.lensSaved.lens || (cur && !a.lensSaved.ours.has(cur))) return;
            app.setLens(a.lensSaved.lens || null);
          });
        }
        app.setLens(ref);
        if (app.state.lens) a.lensSaved.ours.add(app.state.lens);
      },
      switchTo,
      cleanup: (fn) => a.cleanup.push(fn),
    };
    try {
      a.api = (await mod.mount(ctx)) || {};
    } catch (err) {
      console.error(`advisor "${adv.id}" failed`, err);
      body.insertAdjacentHTML("beforeend", `<p class="adv-empty pad">繪製這位顧問的面板時發生錯誤。</p>`);
      a.api = {};
    }
    loading?.remove();
    // The view may have been switched away while it awaited its files: undo what it registered.
    if (active !== a) {
      try { a.api?.destroy?.(); } catch (err) { console.error(err); }
      dispose(a);
      return;
    }
    // Map hover → dashboard, only while a view that wants it is open (the app skips hover work without listeners).
    if (a.api.onMapHover && active === a) {
      a.cleanup.push(app.on("hover", (h) => {
        try { a.api.onMapHover(h); } catch (err) { console.error(err); }
      }));
    }
  }

  function titleHtml(adv) {
    return `<div class="adv-title" style="--adv:${adv.color}">
      ${emblem(adv, 64)}
      <div class="adv-titles"><div class="adv-kind">${esc(adv.role)}</div><h2>${esc(adv.name)}</h2><p>${esc(adv.blurb)}</p></div>
    </div>`;
  }

  function councilHtml() {
    // The publishers are read from sources.json, so the line always matches the data that was really built.
    const pubs = [...new Set((app.data?.sources || []).map((s) => s?.publisher).filter(Boolean))];
    const groups = COUNCIL.map((g) => ({ label: g.label, list: g.ids.map((id) => byId.get(id)).filter(available) })).filter((g) => g.list.length);
    return `<div class="adv-title council"><div class="adv-titles"><div class="adv-kind">你的顧問團</div><h2>顧問團</h2>
      <p>每位顧問各自掌管真實經濟的一個面向。將游標移到任何項目上，地圖會標出它的位置；將游標移到地圖上，圖表也會跟著標示；點擊可深入檢視。</p></div></div>
      ${groups.map((g) => `<h4 class="adv-council-h">${esc(g.label)}</h4><div class="adv-council">${g.list.map((a) => `<button type="button" class="adv-card" data-adv="${a.id}" style="--adv:${a.color}">
        ${emblem(a, 48)}<span class="t"><span class="r">${esc(a.role)}</span><b>${esc(a.name)}</b><span class="d">${esc(a.blurb)}</span></span></button>`).join("")}</div>`).join("")}
      <p class="adv-note pad">所有數字都來自公開資料${pubs.length ? `：${esc(pubs.join("、"))}` : ""}。每個面板的底部都列出資料來源與解讀時的注意事項。</p>`;
  }

  // An optional file an advisor needs has arrived (or turned out to be missing): offer exactly the advisors that
  // have their data, on the tab strip and on the council page.
  app.on("data", ({ name }) => {
    if (!ADVISORS.some((a) => a.needs === name)) return;
    const root = dock?.querySelector(".adv-root");
    if (!root || app.mode !== "advisor") return;
    root.querySelector(".adv-tabs").innerHTML = tabsHtml();
    syncTabs(root);
    if (current === "council") {
      const main = root.querySelector(".adv-main");
      main.innerHTML = councilHtml();
      main.querySelectorAll(".adv-card").forEach((c) => c.addEventListener("click", () => switchTo(c.dataset.adv)));
    }
  });

  // --- map → dashboard --------------------------------------------------------------------------------------------
  let lastBubble = null;
  canvas?.addEventListener("pointermove", (e) => {
    if (app.mode !== "advisor" || !active || e.pointerType !== "mouse" || e.buttons) return;
    let hit = null, owner = null;
    for (const b of active.bubbles) {
      hit = b.hit(e.clientX, e.clientY);
      if (hit) { owner = b; break; }
    }
    if (hit !== lastBubble) {
      for (const b of active.bubbles) b.setHot(b === owner ? hit.key : null);
      lastBubble = hit;
      link.fromMap(() => {
        owner?.handlers.onHover?.(hit);
        if (!hit) for (const b of active.bubbles) b.handlers.onHover?.(null);
      });
    }
    if (hit && owner.handlers.tip) tip.show(e.clientX, e.clientY, owner.handlers.tip(hit));
    else tip.hide();
  });
  canvas?.addEventListener("pointerleave", () => {
    if (!lastBubble || !active) return;
    link.fromMap(() => { for (const b of active.bubbles) { b.setHot(null); b.handlers.onHover?.(null); } });
    lastBubble = null;
    tip.hide();
  });
  app.on("mapclick", (ev) => {
    if (app.mode !== "advisor" || !active) return false;
    for (const b of active.bubbles) {
      const hit = b.hit(ev.x, ev.y);
      if (hit && b.handlers.onClick) { b.handlers.onClick(hit); return true; }
    }
    return active.api?.onMapClick?.(ev) === true;
  });

  // --- mode -------------------------------------------------------------------------------------------------------
  app.registerMode("advisor", {
    enter(params) {
      // Remember where the camera was when the advisors opened (not on a switch between advisors), to fly back on exit.
      if (!pendingTeardown && !current) prevCam = { x: app.cam.x, y: app.cam.y, scale: app.cam.scale };
      pendingTeardown = false;
      show(params?.id && available(byId.get(params.id)) ? params.id : null, params);
    },
    exit() {
      // A switch between advisors is exit() + enter() in one go: keep the dock and only rebuild its content.
      pendingTeardown = true;
      token++;
      queueMicrotask(() => {
        if (!pendingTeardown) return;
        pendingTeardown = false;
        teardownView();
        current = null;
        framedFor = null;
        // Back to the view the advisors were opened from (unless another mode, e.g. the City view, took over).
        const p = prevCam;
        prevCam = null;
        if (p && app.mode == null) {
          const fs = app.cam.fitScale;
          if (fs > 0 && Math.abs(p.scale / fs - 1) < 0.03) app.home();
          else { app.cam.flyTo(p.x, p.y, p.scale, 650); app.requestDraw(); }
        }
        // Leave the left dock alone if another mode has already put its own content there.
        const d = dock, root = d?.querySelector(".adv-root");
        dock = null;
        if (!d || !root) return;
        root.remove();
        d.classList.remove("adv-dock");
        if (!d.children.length) app.ui.undock("left");
      });
    },
    onEscape() {
      if (active?.api?.onEscape?.() === true) return true;
      return false;
    },
  });

  app.hash.register("advisor", {
    get: () => (app.mode === "advisor" ? current || "council" : null),
    set(v) {
      if (v) {
        const id = available(byId.get(v)) ? v : null; // #advisor=military opens the council when there is no such data
        if (app.mode !== "advisor" || (id || "council") !== current) app.setMode("advisor", { id });
      } else if (app.mode === "advisor") app.setMode(null);
    },
  });

  app.advisors = { get list() { return offered(); }, open: (id, params) => switchTo(id, params), get current() { return current; }, data: () => data, ensureData };
}
