// Top-bar search over cities, 縣市 and 鄉鎮市區: prefix matches first, then word-prefix, then substring; ties by
// population. Names are matched in Chinese (台 and 臺 are the same letter here), by English name and by ISO code.
import { esc, popShort } from "../format.js";
import { icon } from "../ui/icon.js";

// NFKC folds full-width letters and digits; every run of non-letters becomes one space, so CJK text survives.
const norm = (s) =>
  String(s || "").normalize("NFKC").replace(/台/g, "臺").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
const MAX = 8;

/**
 * opts: {cities, states (list of {name, abbr, name_en?, population?}),
 *        counties? (list of {name, name_en?, geoid?, state (index into states), population?}),
 *        onPick({kind:'city', city} | {kind:'state', index, county?, geoid?})}
 * A picked 鄉鎮市區 reports its 縣市 (kind 'state', index) plus `county` (its index in opts.counties) and `geoid`.
 */
export function initSearch(opts) {
  const input = document.getElementById("search-input");
  const box = document.getElementById("search-results");
  if (!input || !box) return { focus() {}, close() {}, get isOpen() { return false; } };
  const hasCounties = (opts.counties || []).length > 0;
  // The full placeholder only fits the wide search box; narrower ones say just 搜尋.
  const narrow = matchMedia("(max-width: 1120px)");
  const full = hasCounties ? "搜尋縣市、鄉鎮市區" : "搜尋縣市";
  const setPlaceholder = () => (input.placeholder = narrow.matches ? "搜尋" : full);
  setPlaceholder();
  input.setAttribute("aria-label", `${full}（/ 或 Ctrl K）`);
  narrow.addEventListener?.("change", setPlaceholder);

  // Each entry: n = the normalised name, alt = other normalised keys (full name, English name), abbr = the code.
  const entries = [];
  const alts = (...keys) => keys.map(norm).filter(Boolean);
  for (const c of opts.cities || []) {
    // A city and its 縣市 are the same unit, so the row says only what it opens; a longer official name is shown.
    const long = c.full && norm(c.full) !== norm(c.name) ? c.full : "";
    entries.push({ kind: "city", city: c, n: norm(c.name), alt: alts(c.full, c.name_en), pop: c.population || 0,
      sub: long ? `城市 · ${long}` : "城市", label: c.name });
  }
  (opts.states || []).forEach((s, index) => {
    if (!s) return;
    entries.push({ kind: "state", index, n: norm(s.name), alt: alts(s.name_en), abbr: norm(s.abbr),
      pop: s.population || 0, sub: "縣市", label: s.name });
  });
  (opts.counties || []).forEach((c, county) => {
    if (!c || !(c.state >= 0)) return;
    const st = opts.states?.[c.state];
    const stName = st?.name || "";
    // "臺北市中山區" and "臺北中山" both find 中山區 of 臺北市.
    entries.push({ kind: "county", index: c.state, county, geoid: c.geoid, n: norm(c.name),
      alt: alts(stName + c.name, stName.replace(/[縣市]$/, "") + c.name, c.name_en), pop: c.population || 0,
      sub: stName ? `${stName} · 鄉鎮市區` : "鄉鎮市區", label: c.name });
  });

  let results = [];
  let sel = -1;
  let composing = false; // an input method (注音, 倉頡 …) is still building the text

  function score(e, q) {
    if (e.abbr && e.abbr === q) return 0;
    if (e.n.startsWith(q)) return e.n === q ? 0 : 1;
    if ((" " + e.n).includes(" " + q)) return 2;
    if (e.alt.some((a) => (" " + a).includes(" " + q))) return 3;
    if (e.n.includes(q)) return 4;
    if (e.alt.some((a) => a.includes(q))) return 5;
    return -1;
  }

  function query(q) {
    q = norm(q);
    if (!q) return [];
    const out = [];
    for (const e of entries) {
      const s = score(e, q);
      if (s >= 0) out.push([s, e]);
    }
    out.sort((a, b) => a[0] - b[0] || b[1].pop - a[1].pop);
    return out.slice(0, MAX).map((x) => x[1]);
  }

  function position() {
    const r = input.getBoundingClientRect();
    const width = Math.min(Math.max(r.width, 320), window.innerWidth - 16);
    box.style.top = r.bottom + 6 + "px";
    box.style.left = Math.max(8, Math.min(window.innerWidth - width - 8, r.left)) + "px";
    box.style.width = width + "px";
  }

  function render() {
    if (!results.length) {
      // No "not found" while an input method is composing: its half-typed symbols match nothing yet.
      const text = composing ? "" : input.value.trim();
      box.innerHTML = text ? `<div class="sr-empty">找不到符合「${esc(text)}」的${hasCounties ? "縣市或鄉鎮市區" : "縣市"}</div>` : "";
      box.hidden = !text;
      input.setAttribute("aria-expanded", String(!box.hidden));
      input.removeAttribute("aria-activedescendant");
      if (!box.hidden) position();
      return;
    }
    box.innerHTML = results
      .map((e, i) => `<div class="sr-item ${i === sel ? "sel" : ""}" role="option" id="sr-${i}" aria-selected="${i === sel}" data-i="${i}">
        <span class="sr-ic">${e.kind === "city" ? icon("pop", "🏙️", { size: 16 }) : icon("terrain", "🗺️", { size: 16 })}</span>
        <span class="sr-main"><b>${esc(e.label)}</b><span class="sr-sub">${esc(e.sub)}</span></span>
        <span class="sr-pop">${e.pop ? popShort(e.pop) : ""}</span></div>`)
      .join("");
    box.hidden = false;
    input.setAttribute("aria-expanded", "true");
    if (sel >= 0) input.setAttribute("aria-activedescendant", `sr-${sel}`);
    else input.removeAttribute("aria-activedescendant");
    position();
  }

  function choose(i) {
    const e = results[i];
    if (!e) return;
    close();
    input.value = "";
    input.blur();
    if (e.kind === "city") opts.onPick({ kind: "city", city: e.city });
    else if (e.kind === "county") opts.onPick({ kind: "state", index: e.index, county: e.county, geoid: e.geoid });
    else opts.onPick({ kind: "state", index: e.index });
  }

  function close() {
    box.hidden = true;
    results = [];
    sel = -1;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }

  const refresh = () => {
    results = query(input.value);
    sel = results.length ? 0 : -1;
    render();
  };
  input.addEventListener("compositionstart", () => { composing = true; });
  input.addEventListener("compositionend", () => { composing = false; refresh(); });
  input.addEventListener("input", refresh);
  input.addEventListener("focus", () => {
    if (input.value.trim()) refresh();
  });
  input.addEventListener("keydown", (e) => {
    // Enter and the arrows belong to the input method while it is composing (Enter commits the candidate).
    if (e.isComposing || e.keyCode === 229) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!results.length) return;
      sel = (sel + (e.key === "ArrowDown" ? 1 : -1) + results.length) % results.length;
      render();
      box.querySelector(".sel")?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (results.length) choose(Math.max(0, sel));
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      if (!box.hidden && input.value) { input.value = ""; close(); }
      else { close(); input.blur(); }
    }
  });
  input.addEventListener("blur", () => setTimeout(() => {
    if (document.activeElement !== input) close();
  }, 150));
  box.addEventListener("pointerdown", (e) => e.preventDefault()); // keep focus in the input
  box.addEventListener("click", (e) => {
    const it = e.target.closest(".sr-item");
    if (it) choose(+it.dataset.i);
  });
  box.addEventListener("pointermove", (e) => {
    const it = e.target.closest(".sr-item");
    if (it && +it.dataset.i !== sel) {
      sel = +it.dataset.i;
      box.querySelectorAll(".sr-item").forEach((x, i) => {
        x.classList.toggle("sel", i === sel);
        x.setAttribute("aria-selected", String(i === sel));
      });
    }
  });
  window.addEventListener("resize", () => !box.hidden && position());

  return {
    focus() {
      input.focus();
      input.select();
    },
    close() {
      close();
      input.blur();
    },
    query,
    get isOpen() { return document.activeElement === input || !box.hidden; },
  };
}
