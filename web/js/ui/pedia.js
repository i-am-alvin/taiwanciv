// The Almanac (資料年鑑): what every number means and exactly where it comes from.
// Page ids stay English (main.js and the City View open pages by id, e.g. pedia.open("Yields")); `title` is what the
// reader sees. Everything about sources and vintages is read from the data files, never written here.
import { resolveTables } from "../terrain.js";
import { esc } from "../format.js";
import { parseHex, luminance } from "../color.js";
import { icon, glyph } from "./icon.js";
import { gdpLabel, useSources } from "./infoPanel.js";

const COVER_ICON = { forest_deciduous: "l-forest", forest_evergreen: "l-forest", forest_mixed: "l-forest", cropland: "l-farmland", pasture: "l-farmland", urban: "l-developed" };
// Glyph colour that reads on a resource medallion (dark on light faces such as nuclear yellow or silver).
const inkOn = (hex) => {
  try { return /^#[0-9a-f]{6}$/i.test(hex || "") && luminance(parseHex(hex)) > 0.4 ? "#1c1710" : "#f8f0d8"; } catch { return "#f8f0d8"; }
};
const CATEGORY = { energy: "能源", mineral: "礦產", agri: "農業", other: "其他" };
const SCALE_NAME = { log: "對數", linear: "線性" };
const SOURCE_URL = "https://github.com/i-am-alvin/taiwanciv";
const UPSTREAM_URL = "https://karpathy.ai/usaciv/"; // the original's own address (its index.html canonical)
const DEFAULT_PAGE = "About this map";
const num = (v) => (Number.isFinite(v) ? v.toLocaleString("zh-TW") : "–");

export function initPedia(data) {
  const modal = document.getElementById("pedia");
  const card = modal.querySelector(".modal-card");
  const nav = document.getElementById("pedia-nav");
  const body = document.getElementById("pedia-body");
  const srcName = (id) => data.sources?.find((s) => s.id === id)?.title || id || "";
  useSources(data.sources); // the panels name the population-change source by its sources.json title
  let restoreFocus = null;

  const h2 = (ic, fb, text) => `<h2>${icon(ic, fb, { size: 24 })}<span>${esc(text)}</span></h2>`;
  // world.json grid units are map units, not km: projection.scale = map units per km (docs/PORTING.md).
  const hexKm = () => {
    const scale = data.world.projection?.scale > 0 ? data.world.projection.scale : 1;
    return +((data.world.grid.radius * 2) / scale).toFixed(1);
  };
  const stateCount = () => (data.states?.length || data.world.states?.length || 0);
  const vintageLine = () => [data.nation.vintage, data.nation.gdp_vintage ? `${gdpLabel(data.nation)}：${data.nation.gdp_vintage}` : ""].filter(Boolean).map(esc).join("；");

  const pages = [
    { id: "About this map", title: "關於本地圖", html: () => `
      ${h2("pedia", "📖", "關於本地圖")}
      <p>這是用策略遊戲的畫法呈現的真實臺灣。地圖上沒有任何虛構的內容：每一個地塊、每一座城市、每一個數字都來自公開資料，
      清單見「資料來源」。</p>
      <h4>地圖怎麼做出來的</h4>
      <p>臺灣本島、澎湖、金門與馬祖以臺灣為中心的 Albers 等積投影展開，切成 ${data.world.grid.cols}×${data.world.grid.rows}
      個六角格，每格對角約 ${hexKm()} 公里。每個六角格歸屬於它所在的縣市與鄉鎮市區，地形則取自格內的高程取樣。
      東沙群島與南沙群島在地圖範圍之外。</p>
      <p><b>城市</b>就是各個縣市${stateCount() ? `（共 ${stateCount()} 個）` : ""}：每個縣市有一面城市橫幅，數字涵蓋整個縣市，而不只是市區。</p>
      <h4>操作方式</h4>
      <p>拖曳或按方向鍵／WASD 平移 · 滾輪、+/– 或點兩下縮放 · 點擊城市或縣市開啟面板 ·
      / 或 ⌘K 搜尋 · L 切換濾鏡 · R 顯示或隱藏資源 · ? 查看所有快捷鍵 · Esc 關閉。</p>
      <p>網址列隨時保存目前畫面的連結（濾鏡、選取對象與視角）；按「分享」可以複製連結或下載圖片。</p>
      <h4>原始碼與致謝</h4>
      <p>taiwanciv 改編自 Andrej Karpathy 的 <a href="${UPSTREAM_URL}" target="_blank" rel="noopener">usaciv</a>（MIT 授權），
      把同一套地圖引擎搬到臺灣的公開資料上。原始碼：
      <a href="${SOURCE_URL}" target="_blank" rel="noopener">${esc(SOURCE_URL.replace(/^https:\/\//, ""))}</a></p>` },
    { id: "Yields", title: "產出", html: () => {
      const gold = gdpLabel(data.nation);
      return `
      ${h2("y-production", "⚙️", "產出")}
      <p>把策略遊戲的產出對應到真實的統計指標。以人數計的產出，數的是從事相關行業的就業人口；以金額計的產出，單位是新臺幣。
      每一項的定義如下：</p>
      <table>${data.nation.yields.map((y) => `<tr><td class="ic" style="color:${esc(y.color)}">${glyph(y, 26)}</td><td><b style="color:${esc(y.color)}">${esc(y.label)}${
        y.key === "gold" && !String(y.label).includes(gold) ? `（${esc(gold)}）` : ""}</b><br>${esc(y.description || "")}</td></tr>`).join("")}</table>
      <h4>宜居度與住房</h4>
      <p>失業率＝失業人口 ÷ 勞動力。${data.nation.nation?.rent_burden != null ? `租金 ÷ 所得＝每月租金中位數 × 12 ÷ 申報戶所得中位數：這只是粗略的負擔指標，
      不是個別家戶實際的負擔率。` : ""}這一版資料沒有的項目（數值為空）不會出現在面板上。</p>`;
    } },
    { id: "States", title: "縣市", html: () => `
      ${h2("terrain", "🗺️", "縣市")}
      <p>點擊任何沒有城市橫幅的陸地六角格，就會開啟它所屬縣市的面板${vintageLine() ? `（${vintageLine()}）` : ""}。</p>
      <p><b>排名</b>（例如「第 3/${stateCount() || "N"} 名」）是地圖上${stateCount() ? ` ${stateCount()} 個` : "所有"}縣市之間的比較，第 1 名最大。</p>
      <p>在臺灣，城市與縣市是同一個統計單位：城市面板與縣市面板呈現的是同一個縣市。</p>
      ${data.states ? "" : `<p class="muted">這一版資料沒有 states.json，所以縣市面板只顯示名稱與城市。</p>`}` },
    { id: "Terrain", title: "地形", html: () => {
      const t = data.w?.tables || resolveTables(data.world.tables);
      const hasCover = Array.isArray(data.world.cover);
      const row = (x) => `<tr><td class="nm">${x.color ? `<span class="swatch" style="background:${esc(x.color)}"></span>` : ""}${
        COVER_ICON[x.key] ? icon(COVER_ICON[x.key], "", { size: 15 }) + " " : ""}<b>${esc(x.name)}</b></td><td>${esc(x.rule || "")}</td></tr>`;
      return `
      ${h2("terrain", "🗺️", "地形")}
      <p>每個六角格取格內高程取樣的平均值。起伏的分級看這些取樣的平均高程與粗糙度（標準差）；
      陰影來自與相鄰六角格的高程差，光從西北方打來。</p>
      <h4>${icon("l-forest", "🌲", { size: 16 })} 地表覆蓋</h4>
      ${hasCover
        ? `<p>每個六角格的底色是它最主要的地表覆蓋類別，也就是格內陸地取樣中占比最大的一類。
           小圖示表現混合的情形：樹木的多寡隨森林占比增減，田畦、蘆葦、灌叢與草叢則分別標示農地、濕地、灌叢地與草地。</p>
           <table>${t.cover.filter((x) => x.id > 0).map(row).join("")}</table>`
        : `<p class="muted">這一版資料還沒有地表覆蓋圖層，陸地依高程上色。</p>`}
      <h4>地勢起伏</h4>
      <table>${t.relief.map(row).join("")}</table>
      <h4>${icon("r-hydro", "💧", { size: 16 })} 水域</h4>
      <table>${t.water.filter((x) => x.id > 0).map(row).join("")}</table>
      <h4>境外</h4>
      <p class="muted">地圖範圍內的境外陸地（例如金門、馬祖鄰近的對岸沿海）罩著一層薄霧：只作為背景，沒有細部資料。</p>`;
    } },
    { id: "Lenses", title: "濾鏡", html: () => `
      ${h2("layers", "▤", "濾鏡")}
      <p>濾鏡用單一指標替地圖重新上色，數值來自鄉鎮市區的資料${data.lenses.vintage ? `（${esc(data.lenses.vintage)}）` : ""}，
      各濾鏡的算法寫在它的說明裡。</p>
      <p>圖例會顯示每個數值區間有多少六角格。把游標移到圖例上或在上面拖曳，地圖就只顯示那個區間。</p>
      ${data.lenses.lenses?.length ? "" : `<p class="muted">這一版資料沒有濾鏡。</p>`}
      ${(data.lenses.groups?.length ? data.lenses.groups : [{ id: null, name: "" }]).map((g) => {
        const ls = (data.lenses.lenses || []).filter((l) => !g.id || l.group === g.id);
        if (!ls.length) return "";
        return `${g.name ? `<h3 class="grp">${icon(`g-${g.id}`, "", { size: 16 })} ${esc(g.name)}</h3>` : ""}${ls.map((l) => `
          <div class="lens-entry"><div class="le-ic">${glyph(l, 26)}</div><div>
          <h4>${esc(l.name)}</h4><p>${esc(l.description || "")}<br>
          <i class="le-ramp" style="background:linear-gradient(90deg, ${(l.ramp || []).map(esc).join(",")})"></i>
          <span class="muted">${Array.isArray(l.domain) ? `色階：${esc(SCALE_NAME[l.scale] || l.scale || "")}，${num(l.domain[0])}–${num(l.domain[1])} ${esc(l.unit || "")}` : esc(l.unit || "")}${
            l.higher_is === "good" ? " · 越高越好" : l.higher_is === "bad" ? " · 越高越差" : ""}${l.source ? " · " + esc(srcName(l.source)) : ""}</span></p></div></div>`).join("")}`;
      }).join("")}` },
    { id: "Resources", title: "資源", html: () => {
      const r = data.resources;
      if (!r?.types?.length) return `${h2("resources", "⛏️", "資源")}<p class="muted">這一版資料沒有資源圖層。</p>`;
      const count = new Map();
      for (const it of r.items || []) count.set(it.type, (count.get(it.type) || 0) + 1);
      const cats = [...new Set(r.types.map((t) => t.category || "other"))];
      return `
      ${h2("resources", "⛏️", "資源")}
      <p>資源把全國主要的資源據點標在它們所在的地塊上，類型見下表。只收錄具代表性的據點，各類型的門檻寫在它的說明裡。
      地圖縮小時，每個六角格只顯示排名最高的一項資源；放大可以看到更多。按 <b>R</b> 顯示或隱藏。</p>
      ${cats.map((c) => `<h4>${esc(CATEGORY[c] || c)}</h4><table class="res-table">
        <tr><th></th><th>類型</th><th>收錄標準</th><th>據點數</th></tr>
        ${r.types.filter((t) => (t.category || "other") === c).map((t) => `<tr>
          <td class="ic"><span class="res-ic" style="background:${esc(t.color || "#24384f")};color:${inkOn(t.color)}">${glyph(t, 20)}</span></td>
          <td class="nm"><b>${esc(t.name)}</b>${t.unit ? `<br><span class="muted">數值單位：${esc(t.unit)}</span>` : ""}</td>
          <td>${esc(t.description || "")}${t.source ? `<br><span class="muted">資料來源：${esc(srcName(t.source))}</span>` : ""}</td>
          <td class="num">${count.get(t.id) || 0}</td></tr>`).join("")}</table>`).join("")}`;
    } },
    { id: "Sources", title: "資料來源", html: () => `
      ${h2("pedia", "📖", "資料來源")}
      ${data.sources?.length ? "" : `<p class="muted">這一版資料沒有 sources.json。</p>`}
      ${(data.sources || []).map((s) => `
        <h4>${esc(s.title || s.id || "")}</h4>
        <p>${esc(s.description || "")}<br>
        <span class="muted">${[s.publisher, s.license, s.vintage].filter(Boolean).map(esc).join(" · ")}${
          s.homepage ? ` · <a href="${esc(s.homepage)}" target="_blank" rel="noopener">官方網站</a>` : ""}</span></p>
        <table>${(s.files || []).map((f) => `<tr><td><code>${esc(f.url || "")}</code></td><td class="muted" style="white-space:nowrap">${esc((f.retrieved || "").slice(0, 10))}<br>${((f.bytes || 0) / 1e6).toFixed(1)} MB</td></tr>`).join("")}</table>`).join("")}
      <p class="muted">地圖引擎改編自 Andrej Karpathy 的 <a href="${UPSTREAM_URL}" target="_blank" rel="noopener">usaciv</a>（MIT 授權）；
      本站原始碼：<a href="${SOURCE_URL}" target="_blank" rel="noopener">${esc(SOURCE_URL.replace(/^https:\/\//, ""))}</a></p>` },
  ];
  const pageById = new Map(pages.map((p) => [p.id, p]));
  // A caller may pass the id or the Chinese title.
  const resolve = (name) => pageById.get(name) || pages.find((p) => p.title === name) || pageById.get(DEFAULT_PAGE);

  const show = (name) => {
    const page = resolve(name);
    body.innerHTML = page.html();
    body.scrollTop = 0;
    nav.querySelectorAll("button").forEach((b) => {
      const on = b.dataset.page === page.id;
      b.classList.toggle("active", on);
      b.setAttribute("aria-current", on ? "page" : "false");
    });
  };
  nav.innerHTML = `<div class="hd">資料年鑑</div>` + pages.map((p) => `<button data-page="${esc(p.id)}">${esc(p.title)}</button>`).join("");
  nav.onclick = (e) => {
    const b = e.target.closest("button[data-page]");
    if (b) show(b.dataset.page);
  };
  const close = () => {
    if (modal.hidden) return;
    modal.hidden = true;
    if (restoreFocus && document.contains(restoreFocus)) restoreFocus.focus();
    restoreFocus = null;
  };
  modal.onclick = (e) => {
    if (e.target === modal || e.target.closest("[data-close]")) close();
  };
  // Keep Tab inside the dialog.
  modal.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    const f = [...card.querySelectorAll("button, a[href], [tabindex]:not([tabindex='-1'])")].filter((x) => x.offsetParent);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  return {
    open(page = DEFAULT_PAGE) {
      if (modal.hidden) restoreFocus = document.activeElement;
      show(page);
      modal.hidden = false;
      (nav.querySelector("button.active") || card.querySelector("[data-close]"))?.focus();
    },
    close,
    get isOpen() {
      return !modal.hidden;
    },
  };
}
