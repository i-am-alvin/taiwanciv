"""Tile resources: Taiwan's power plants, dams, pumped-storage plants and wind and solar farms on the hex map.

Like strategic resources on a Civ tile, but only real sites. Capacities come from Taipower's unit list
(`taipower_units`: every unit on the grid with its installed MW, Taipower's own and the independent producers'),
summed per plant. That list has no coordinates, so each plant is placed with the OpenStreetMap power=plant element
named in CROSSWALK (`osm_tw_power`): the crosswalk only says which OSM element a Taipower plant is; the position is
read from the downloaded file and OSM's own capacity tags are never used. A plant without an OSM element is left
out (the build prints them), as are Taipower's unlocated aggregates (其它購電太陽能, 汽電共生, 電池, 小水力 ...).

What is in service is decided by the Taipower list alone: it has no nuclear rows (the last reactor shut down in
2025), so no nuclear plant is drawn. A unit whose capacity Taipower prints as "-" (trial operation, or being
retired) adds nothing to the plant's value and is counted in the item's detail.

Taiwan has no working coal, metal or uranium mines and no shale plays, so the US mineral and oil and gas types are
gone. Offshore wind farms stay on their own sea hex (the US build moved them to the coast); their county is that
of the nearest land hex.

Each item is tagged with its county (`state`: ISO 3166-2:TW code; `cbsa`: the county's COUNTYCODE, the cities.json
id), and `summary` totals the mapped sites per type, for Taiwan and per county.

`types` is listed in rank order (most significant first); the frontend can use that order when only one icon fits
a cell.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, write_web

REQUIRES = ["_world", "tw_boundaries", "taipower_units", "osm_tw_power"]
PRODUCES = ["resources.json"]

# --- thresholds (MW = installed capacity in Taipower's list) -------------------
PLANT_MIN = {"gas": 100, "coal": 100, "oil": 20, "pumped_storage": 100, "hydro": 30, "wind": 20, "solar": 50}
SNAP_RINGS = 2  # a coastal plant whose OSM centre is on a sea hex moves to the nearest land hex this close
OFFSHORE_KM = 60  # an offshore wind farm belongs to the county of the nearest land hex within this distance

ENERGY_SRC = "taipower_units"
# Taipower's fuel class (機組類型) → fuel. Classes not listed (汽電共生, 其它再生能源, 儲能負載) are not mapped.
FUEL_OF = {"燃氣": "gas", "民營電廠-燃氣": "gas", "燃煤": "coal", "民營電廠-燃煤": "coal", "燃料油": "oil", "輕油": "oil",
           "水力": "hydro", "儲能": "pumped_storage", "風力": "wind", "太陽能": "solar"}
FUEL_NAME = {"gas": "燃氣", "coal": "燃煤", "oil": "燃油", "hydro": "水力", "pumped_storage": "抽蓄水力", "wind": "風力",
             "solar": "太陽光電"}
TYPE_OF = {"gas": "gas_plant", "coal": "coal_plant", "oil": "oil_plant"}  # other fuels: the type id is the fuel

# Which OpenStreetMap element is each plant of Taipower's list: Taipower's plant name (the unit name without its
# unit number) → (OSM element, the name it must carry there). Positions come from the downloaded OSM file; an
# element that is missing or renamed is dropped and reported, never guessed. Two Taipower rows that name one site
# (允湖 and 允西, the two halves of the Yunlin offshore farm) share an element and become one item.
CROSSWALK = {
    # gas, coal and oil plants
    "大潭": ("way/661662183", "大潭發電廠"), "通霄": ("way/181171613", "通霄發電廠"),
    "台中": ("way/200691649", "台中火力發電廠"), "興達": ("way/226576525", "興達發電廠"),
    "南部": ("relation/6358152", "南部發電廠"), "大林": ("way/204129566", "大林火力發電廠"),
    "林口": ("way/199146681", "林口火力發電廠"), "協和": ("relation/10757938", "協和發電廠"),
    "海湖": ("way/114411959", "海湖發電廠"), "新桃": ("way/365285231", "新桃電廠"),
    "國光": ("way/538753336", "國光發電廠"), "星彰": ("way/915288818", "彰濱電廠"),
    "星元": ("way/915269327", "星元電廠"), "嘉惠": ("way/507020797", "嘉惠發電廠"),
    "豐德": ("way/151212447", "豐德發電廠"), "和平": ("way/274895730", "和平電廠"),
    "澎湖尖山": ("way/337541593", "尖山發電廠"), "金門塔山": ("relation/13335122", "塔山發電廠"),
    "馬祖珠山": ("way/249855731", "珠山發電廠"),
    # hydro and pumped storage
    "谷關": ("way/513486768", "大甲溪發電廠谷關分廠"), "萬大": ("way/172736809", "萬大發電廠"),
    "大觀一": ("way/976767036", "大觀一廠"), "鉅工": ("way/225470941", "明潭發電廠鉅工分廠"),
    "立霧": ("way/227669295", "東部發電廠立霧機組"), "龍澗": ("way/749133167", "東部發電廠龍澗機組"),
    "碧海": ("relation/7346491", "台電東部發電廠碧海機組"), "翡翠": ("way/497030578", "桂山發電廠翡翠分廠"),
    "石門": ("way/518956917", "石門發電廠石門電廠"), "義興": ("way/507342535", "石門發電廠義興電廠"),
    "曾文": ("way/962954457", "曾文發電廠"), "名間": ("way/519033087", "名間水力發電廠"),
    "大觀二": ("way/1105678337", "大觀二廠"), "明潭": ("way/515759430", "明潭抽蓄水力發電廠"),
    # wind farms
    "台中港": ("relation/13131411", "臺中港風力發電站"), "王功": ("relation/13131410", "王功風力發電站"),
    "雲麥": ("relation/13131409", "雲麥風力發電站"), "四湖": ("relation/13131408", "四湖風力發電站"),
    "海洋竹南": ("relation/13131412", "海洋竹南風力發電場"), "海能風": ("way/1343875947", "Formosa 2 Offshore Wind Farm"),
    "沃一風": ("way/1333770360", "Greater Changhua 1 Offshore Wind"),
    "沃二風": ("way/1459169021", "Greater Changhua 2a Offshore Wind"),
    "允湖": ("way/882630880", "Yunlin Offshore Wind Farm"), "允西": ("way/882630880", "Yunlin Offshore Wind Farm"),
    # solar farms
    "彰濱光": ("way/840955021", "台電彰濱太陽光電廠"), "南鹽光": ("relation/16214521", "台南鹽田光電場"),
    "天篷光": ("relation/15257043", "天篷第一期太陽能電廠"),
}
# Rows of Taipower's list that are sums over many sites, or a class total: they have no place on a map.
AGGREGATE = re.compile(r"其它|小水力|汽電共生|電池|&|、")
_UNIT = re.compile(r"^(.*?)(?:新?CC|GT|Gas)?\s*#?\d*(?:&#?\d+)*$")  # '大潭CC#1' → '大潭', '台中Gas1&2' → '台中'

NO_MW = "台電未列裝置容量的機組（試運轉或停用中，表中為「-」）不計入。"
PLACED = "位置取自 OpenStreetMap 的同一座電廠，OSM 上找不到的電廠不顯示。"
ONE_ICON = "同一廠區有多種燃料時只畫一個圖示，歸在裝置容量最大的燃料，數值為全廠合計。"


def _t(id, name, emoji, color, description, icon=None):
    return {"id": id, "name": name, "category": "energy", "emoji": emoji, "icon": icon or f"r-{id}", "color": color,
            "unit": "MW", "description": description, "source": ENERGY_SRC}


TYPES = [
    _t("gas_plant", "燃氣電廠", "⚡", "#f08a24",
       f"燃氣裝置容量達 {PLANT_MIN['gas']} MW 以上的電廠，含台電與民營電廠（台電各機組裝置容量）。{ONE_ICON}{NO_MW}{PLACED}"),
    _t("coal_plant", "燃煤電廠", "🏭", "#5a5a5a",
       f"燃煤裝置容量達 {PLANT_MIN['coal']} MW 以上的電廠，含台電與民營電廠（台電各機組裝置容量）。{ONE_ICON}{NO_MW}{PLACED}"),
    _t("oil_plant", "燃油電廠", "🛢️", "#3a2f2a",
       f"燃油（重油、柴油）裝置容量達 {PLANT_MIN['oil']} MW 以上的電廠，包括澎湖、金門、馬祖各自獨立電網的主力電廠。"
       f"{NO_MW}{PLACED}", icon="r-oil"),
    _t("pumped_storage", "抽蓄水力電廠", "🔄", "#2f7fb8",
       f"裝置容量達 {PLANT_MIN['pumped_storage']} MW 以上的抽蓄水力電廠：用上下兩座水庫儲電。{PLACED}"),
    _t("hydro", "水力電廠", "💧", "#3fa7d6",
       f"裝置容量達 {PLANT_MIN['hydro']} MW 以上的慣常水力電廠（台電各機組裝置容量，同一電廠的機組合計）。{PLACED}"
       "台電把多座小電廠合併列出的項目（如各區小水力）無法定位，不在圖上。"),
    _t("wind", "風力發電場", "🌬️", "#9fd8cb",
       f"台電機組清單中單獨列名、裝置容量達 {PLANT_MIN['wind']} MW 以上的風場。離岸風場標在實際海域的六角格上，"
       f"縣市取 {OFFSHORE_KM} 公里內最近的陸地。{NO_MW}{PLACED}其餘併計為「其它」的風機不在圖上。"),
    _t("solar", "太陽光電場", "☀️", "#ffc93c",
       f"台電機組清單中單獨列名、裝置容量達 {PLANT_MIN['solar']} MW 以上的太陽光電場。{NO_MW}{PLACED}"
       "全臺絕大多數的太陽光電（屋頂與小型案場）在清單中合併為一筆「其它購電太陽能」，沒有位置，不在圖上。"),
]
RANK = {t["id"]: i for i, t in enumerate(TYPES)}
SUMMARY_NOTE = ("只合計圖上標示的電廠（各類型有裝置容量門檻，且須能在 OpenStreetMap 上定位，見各類型說明），"
                "不是全國或各縣市的總裝置容量。")


def _fmt(n: float) -> str:
    return f"{n:,.1f}".rstrip("0").rstrip(".")


def _cjk(text: str | None) -> bool:
    return bool(text) and any("一" <= ch <= "鿿" for ch in text)


def plant_key(unit_name: str) -> str:
    return _UNIT.match(unit_name).group(1)


class Placer:
    """lon/lat → (x, y, cell). A point on a sea hex snaps to a land hex within `rings`, else keeps its sea hex."""

    def __init__(self, world):
        self.proj = MapProjection(**world["projection"])
        self.grid = HexGrid(**world["grid"])
        self.owner = world["owner"]

    def nearest_land(self, cell: int, x: float, y: float, rings: int) -> int:
        if cell < 0 or self.owner[cell] >= 0:
            return cell
        seen, frontier = {cell}, [cell]
        for _ in range(rings):
            ring = []
            for c in frontier:
                for n in self.grid.neighbours(c):
                    if n not in seen:
                        seen.add(n)
                        ring.append(n)
            land = [n for n in ring if self.owner[n] >= 0]
            if land:
                return min(land, key=lambda n: math.dist(self.grid.center(*self.grid.col_row(n)), (x, y)))
            frontier = ring
        return -1

    def __call__(self, lon, lat):
        x, y = self.proj(lon, lat)
        return x, y, self.grid.cell_at(x, y)


def plants_of(units: list[dict]) -> tuple[dict, list[str]]:
    """Taipower unit rows → {plant key: {fuel: {mw, units, unknown, private}}}, and the unlocated aggregate rows."""
    plants: dict[str, dict] = defaultdict(dict)
    aggregates = []
    for u in units:
        fuel = FUEL_OF.get(u["kind"])
        if fuel is None:
            continue
        key = plant_key(u["name"])
        if AGGREGATE.search(key):
            aggregates.append(f"{u['kind']} {u['name']}")
            continue
        f = plants[key].setdefault(fuel, {"mw": 0.0, "units": 0, "unknown": 0, "private": False,
                                                           "rows": []})
        f["rows"].append(u["name"])
        f["private"] = f["private"] or u["kind"].startswith("民營")
        if u["mw"] is None:
            f["unknown"] += 1
        else:
            f["mw"] += u["mw"]
            f["units"] += 1
    return plants, aggregates


def build_items(place: Placer, taipower: dict, osm: dict) -> tuple[list[dict], dict]:
    plants, aggregates = plants_of(taipower["units"])
    elements = {p["osm"]: p for p in osm["plants"]}
    sites: dict[str, list[str]] = defaultdict(list)  # OSM element → Taipower plant keys
    log = {"aggregates": aggregates, "no_crosswalk": [], "osm_missing": [], "below": [], "off_map": []}
    for key, fuels in plants.items():
        known = sum(f["mw"] for f in fuels.values())
        if key not in CROSSWALK:
            log["no_crosswalk"].append(f"{key} ({'/'.join(FUEL_NAME[k] for k in fuels)} {_fmt(known)} MW)")
            continue
        ref, want = CROSSWALK[key]
        el = elements.get(ref)
        if el is None or want not in (el["name"], el["name_en"]):
            log["osm_missing"].append(f"{key} → {ref} {want}")
            continue
        sites[ref].append(key)

    items = []
    for ref, keys in sites.items():
        el = elements[ref]
        fuels: dict[str, dict] = {}
        for key in keys:
            for fuel, f in plants[key].items():
                acc = fuels.setdefault(fuel, {"mw": 0.0, "units": 0, "unknown": 0, "private": False})
                for k in ("mw", "units", "unknown"):
                    acc[k] += f[k]
                acc["private"] = acc["private"] or f["private"]
        ranked = sorted(fuels.items(), key=lambda kv: -kv[1]["mw"])
        main = next((fuel for fuel, f in ranked if f["mw"] >= PLANT_MIN[fuel]), None)
        label = "、".join(keys)
        if main is None:
            log["below"].append(f"{label} ({_fmt(sum(f['mw'] for f in fuels.values()))} MW)")
            continue
        x, y, cell = place(el["lon"], el["lat"])
        if cell < 0:
            log["off_map"].append(label)
            continue
        offshore = False
        state_cell = cell
        if place.owner[cell] < 0:
            if main == "wind":
                offshore = True
                rings = math.ceil(OFFSHORE_KM * place.proj.scale / (math.sqrt(3) * place.grid.radius))
                state_cell = place.nearest_land(cell, x, y, rings)
            else:
                cell = state_cell = place.nearest_land(cell, x, y, SNAP_RINGS)
                if cell < 0:
                    log["off_map"].append(label)
                    continue
        total = sum(f["mw"] for f in fuels.values())
        unknown = sum(f["unknown"] for f in fuels.values())
        if main in ("wind", "solar"):
            parts = []  # Taipower lists a wind or solar farm as one row, not unit by unit
        elif len(ranked) == 1:
            parts = [f"{ranked[0][1]['units']} 部{FUEL_NAME[main]}機組"]
        else:
            parts = ["、".join(f"{FUEL_NAME[fuel]} {f['units']} 部 {_fmt(f['mw'])} MW" for fuel, f in ranked if f["units"])]
        if main in ("gas", "coal", "oil"):
            parts.append("民營電廠" if any(f["private"] for f in fuels.values()) else "台電")
        if unknown:
            parts.append(f"另有 {unknown} 部機組未列裝置容量，未計入")
        if offshore:
            parts.append("離岸風場，標示於實際海域")
        name = el["name"] if _cjk(el["name"]) else label
        if name != label:
            parts.append(f"台電清單名稱：{label}")
        elif el["name"] or el["name_en"]:
            parts.append(f"OpenStreetMap 名稱：{el['name'] or el['name_en']}")
        items.append({"type": TYPE_OF.get(main, main), "name": name, "x": x, "y": y, "cell": cell,
                      "value": round(total, 1), "detail": "；".join(parts), "_state_cell": state_cell})
    return items, log


def _settle(items: list[dict], grid: HexGrid) -> int:
    """Round x/y, and move any point whose rounded position is not in its cell (a plant snapped from a sea hex
    to the coast) to that cell's centre, so x/y and cell always agree. Returns how many moved."""
    moved = 0
    for it in items:
        x, y = round(it["x"], 1), round(it["y"], 1)
        if grid.cell_at(x, y) != it["cell"]:
            x, y = (round(v, 1) for v in grid.center(*grid.col_row(it["cell"])))
            moved += 1
        it["x"], it["y"] = x, y
    return moved


def locate(items: list[dict], world: dict) -> None:
    """Set each item's `state` (ISO 3166-2:TW code of the county owning its hex, or for an offshore wind farm the
    nearest land hex) and `cbsa` (that county's COUNTYCODE, its cities.json id); both None if no land is near."""
    abbr_of = {s["fips"]: s["abbr"] for s in load_interim("tw_boundaries")["states"]}
    owner = world["owner"]
    for it in items:
        c = it.pop("_state_cell")
        code = world["states"][owner[c]] if c >= 0 and owner[c] >= 0 else None
        it["state"] = abbr_of.get(code) if code else None
        it["cbsa"] = code


def summarize(items: list[dict], types: list[dict]) -> dict:
    """National and per-county {type: {count, value, unit}} over the mapped items."""
    def blank(t):
        return {"count": 0, "value": 0, "unit": t["unit"]}

    by_id = {t["id"]: t for t in types}
    national = {t["id"]: blank(t) for t in types}
    states: dict[str, dict] = {}
    for it in items:
        t = by_id[it["type"]]
        rows = [national[t["id"]]]
        if it["state"]:
            rows.append(states.setdefault(it["state"], {}).setdefault(t["id"], blank(t)))
        for row in rows:
            row["count"] += 1
            if it["value"] is not None:
                row["value"] += it["value"]
    for row in [*national.values(), *(r for st in states.values() for r in st.values())]:
        row["value"] = round(row["value"])
    return {"note": SUMMARY_NOTE, "national": national, "states": dict(sorted(states.items()))}


def build() -> None:
    world = load_interim("_world")
    place = Placer(world)
    taipower = load_interim_payload("taipower_units")
    osm = load_interim_payload("osm_tw_power")
    items, log = build_items(place, taipower["data"], osm["data"])
    items.sort(key=lambda it: (RANK[it["type"]], -(it["value"] or 0)))
    moved = _settle(items, place.grid)
    locate(items, world)
    present = {it["type"] for it in items}
    types = [t for t in TYPES if t["id"] in present]
    write_web("resources.json", {
        "vintage": {"capacity": taipower["vintage"], "positions": osm["vintage"]},
        "sources": ["taipower_units", "osm_tw_power"],
        "types": types, "items": items, "summary": summarize(items, types)})
    counts = defaultdict(int)
    for it in items:
        counts[it["type"]] += 1
    print("    " + ", ".join(f"{t['id']} {counts[t['id']]}" for t in TYPES))
    print(f"    {len(items)} items, {sum(it['value'] for it in items):,.0f} MW mapped; {moved} snapped to a coast hex")
    for key, what in (("no_crosswalk", "no OpenStreetMap element in the crosswalk"),
                      ("osm_missing", "crosswalk element missing or renamed in OpenStreetMap"),
                      ("below", "below its type's threshold"), ("off_map", "outside the map"),
                      ("aggregates", "unlocated aggregate rows")):
        if log[key]:
            print(f"    left out, {what} ({len(log[key])}): {'; '.join(log[key])}")
