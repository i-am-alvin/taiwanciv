// Keyboard & mouse cheat-sheet.
import { icon } from "../ui/icon.js";

const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");
const MOD = isMac ? "⌘" : "Ctrl";
const SOURCE_URL = "https://github.com/i-am-alvin/taiwanciv";
const UPSTREAM_URL = "https://karpathy.ai/usaciv/"; // the original this site is ported from

const ROWS = [
  ["移動與縮放", [
    [["拖曳", "←↑→↓", "WASD"], "平移地圖"],
    [["滾輪", "+", "–"], "放大與縮小"],
    [["雙擊"], "放大該處"],
    [["雙指"], "捏合縮放、拖曳平移（觸控）"],
    [["小地圖"], "點擊或拖曳以快速跳轉"],
  ]],
  ["探索", [
    [["點擊城市"], "開啟城市檢視"],
    [["點擊陸地"], "開啟該縣市"],
    [["/", `${MOD} K`], "搜尋縣市與鄉鎮市區"],
    [["L", "Shift L"], "下一個／上一個濾鏡"],
    [["圖例"], "滑鼠移到色階上或拖曳，只顯示該區間"],
    [["R"], "顯示或隱藏資源"],
  ]],
  ["面板", [
    [["?"], "開啟本說明"],
    [["Esc"], "依序關閉說明、搜尋、資料年鑑與面板"],
  ]],
];

export function initHelp() {
  const modal = document.getElementById("help");
  if (!modal) return { open() {}, close() {}, get isOpen() { return false; } };
  const card = modal.querySelector(".help-card");
  let restore = null;
  card.innerHTML = `
    <button class="icon-btn help-close" data-close aria-label="關閉說明">${icon("close", "✕", { size: 13 })}</button>
    <h2 id="help-title">${icon("help", "?", { size: 22 })}<span>操作說明</span></h2>
    <div class="help-cols">${ROWS.map(([title, rows]) => `
      <section><h3>${title}</h3>${rows.map(([keys, what]) => `
        <div class="help-row"><span class="keys">${keys.map((k) => `<kbd>${k}</kbd>`).join("")}</span><span>${what}</span></div>`).join("")}
      </section>`).join("")}</div>
    <p class="help-foot">每個數字都來自公開資料：開啟<b>資料年鑑</b>可查閱來源。
      網址列的連結隨時能重新開啟目前這個畫面。
      原始碼：<a href="${SOURCE_URL}" target="_blank" rel="noopener">github.com/i-am-alvin/taiwanciv</a>（MIT 授權）。
      改編自 Andrej Karpathy 的 <a href="${UPSTREAM_URL}" target="_blank" rel="noopener">usaciv</a>（MIT 授權）。</p>`;

  const close = () => {
    if (modal.hidden) return;
    modal.hidden = true;
    if (restore && document.contains(restore)) restore.focus();
    restore = null;
  };
  modal.addEventListener("click", (e) => {
    if (e.target === modal || e.target.closest("[data-close]")) close();
  });
  modal.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    e.preventDefault(); // keep the focus inside the card: the close button and the two links in the footer
    const stops = [...card.querySelectorAll("[data-close], a[href]")];
    const k = stops.indexOf(document.activeElement);
    stops[(k + (e.shiftKey ? -1 : 1) + stops.length) % stops.length]?.focus();
  });

  return {
    open() {
      if (!modal.hidden) return;
      restore = document.activeElement;
      modal.hidden = false;
      card.querySelector("[data-close]").focus();
    },
    close,
    toggle() { modal.hidden ? this.open() : close(); },
    get isOpen() { return !modal.hidden; },
  };
}
