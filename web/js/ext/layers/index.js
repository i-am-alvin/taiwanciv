// Map-art extension: tile improvements (highways and major roads, railroads, ports, airports), wonders and protected
// land, and freight trade routes, each as a static layer drawn into the cached map (nothing animates; an idle map
// draws no frames), with a switch in the "Map" menu.
//
// Data: infrastructure.json, wonders.json and trade.json (loaded eagerly by main.js right after the first frame;
// app.loadData returns the same promise). A switch exists only while its file is loaded: a file that is missing (null)
// leaves its layers off and takes its switch out of the menu, and the URL forgets the id (`#layers=…`).
// military.json is omitted on purpose in this build (docs/PORTING.md) and is never requested here; its forts and
// restricted ground, and their switch, appear only if the app already holds the data.
// Defaults: roads, rail, ports & airports and wonders on (roads, rail and hubs only from the region view in: see each
// layer's minRpx), trade routes off.
import { createModel } from "./model.js";
import { makeLayers } from "./layers.js";
import { tips } from "./tips.js";

// A file's own words for a tooltip: the names in one of its tables ("國道、省道"), else a general description.
const names = (list, fallback) => (Array.isArray(list) && list.length ? list.map((x) => x?.name).filter(Boolean).join("、") : "") || fallback;
const vintage = (d, ...parts) => {
  const v = d?.vintage;
  const text = typeof v === "object" && v ? parts.map((p) => v[p]).filter(Boolean).join("；") : v;
  return text ? `（${text}）` : "";
};

// `file`: the data file the switch needs. `title(data)` describes the layer from that file.
const TOGGLES = [
  { id: "roads", file: "infrastructure", label: "公路", icon: "t-road", def: true, layers: ["roads"],
    title: (d) => `${names(d?.road_classes, "高速公路與主要公路")}，地圖示意${vintage(d, "roads")}` },
  { id: "rail", file: "infrastructure", label: "鐵路", icon: "t-rail", def: true, layers: ["rail"],
    title: (d) => `${names(d?.rail_tiers, "鐵路幹線與支線")}，地圖示意${vintage(d, "rail")}` },
  { id: "hubs", file: "infrastructure", label: "港口與機場", icon: "d-harbor", def: true, layers: ["hubs"],
    title: (d) => `主要港口與機場${vintage(d, "ports", "airports")}` },
  { id: "military", file: "military", request: false, label: "軍事設施", icon: "m-army", def: true, layers: ["forts", "restricted", "plates"],
    title: () => "軍事設施與管制區" },
  { id: "wonders", file: "wonders", label: "奇觀", icon: "w-landmark", def: true, layers: ["wonders", "protected", "plates"],
    title: (d) => `自然景觀、頂尖大學與精選地標${vintage(d)}` },
  { id: "trade", file: "trade", label: "貿易路線", icon: "t-trade", def: false, layers: ["trade"],
    title: (d) => d?.rule || `區域之間最大的貨運流量，估計值${vintage(d)}` },
];
const FILES = [...new Set(TOGGLES.map((t) => t.file))];

export function install(app) {
  const model = createModel(app.w);
  const on = Object.fromEntries(TOGGLES.map((t) => [t.id, t.def]));
  const layers = makeLayers(model, on, { tips, app });
  for (const l of layers) app.registerStaticLayer(l);

  // Switches: one per toggle whose file is (or may still be) there. `removers` holds the ones in the menu.
  const removers = new Map();
  const addToggle = (t, data) => {
    // Adding an id again replaces its switch in place (same position in the menu, same state).
    removers.set(t.id, app.ui.addMapToggle({
      id: t.id, label: t.label, icon: t.icon, title: t.title(data), default: t.def,
      get: () => on[t.id],
      set: (v) => {
        on[t.id] = !!v;
        app.requestDraw();
      },
    }));
  };
  const dropToggle = (t) => {
    removers.get(t.id)?.();
    removers.delete(t.id);
    app.ui.setMapToggle?.(t.id, null); // the URL forgets a layer this build does not have
  };
  const known = (file) => app.data[file] !== undefined; // loaded already (null = the file does not exist)
  const requested = (file) => TOGGLES.some((t) => t.file === file && t.request !== false);
  for (const t of TOGGLES) {
    // Before its file arrives a switch is shown (so a link's layers= applies at once), unless the file is never asked for.
    if (known(t.file) ? app.data[t.file] : t.request !== false) addToggle(t, app.data[t.file]);
    else dropToggle(t);
  }

  const apply = (name, data) => {
    model.setData(name, data);
    for (const t of TOGGLES) {
      if (t.file !== name) continue;
      if (data) addToggle(t, data); // again, now with the file's own words in the tooltip
      else dropToggle(t);
    }
    app.requestDraw();
  };
  for (const name of FILES) {
    if (known(name)) apply(name, app.data[name]);
    else if (requested(name)) app.loadData(name).then((d) => apply(name, d), (err) => { console.warn(`map layers: ${name} failed to load`, err); apply(name, null); });
  }
  // A file this extension does not ask for (military) still shows up here if something else loads it.
  app.on?.("data", ({ name, data } = {}) => {
    if (FILES.includes(name) && !requested(name) && (model.data[name] ?? null) !== (data || null)) apply(name, data);
  });

  // For debugging and the gallery: the model and switches.
  app.mapArt = { model, on, layers };
}
