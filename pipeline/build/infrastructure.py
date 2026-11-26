"""Tile improvements: freeways, expressways, provincial highways and railways rasterised onto hex links, plus the
commercial ports and the civil airports.

Lines are never shipped as polylines. OpenStreetMap cuts a road into many short ways, one per carriageway, so the
source first stitches the ways of one route into long lines. Each line is then sampled every SAMPLE_KM along its
length, each sample is mapped to its hex, repeats in a row are dropped, a cell whose neighbours on the line already
touch is dropped (the line only clipped its corner; this keeps a road along a row boundary from zigzagging), and
every step between two cells becomes a link between neighbouring cells (a step that skips cells is filled with a hex
line walk). The second carriageway (or track) of a route is snapped onto the hexes its first one already uses where
the two run in neighbouring hexes, so a divided road is one line of links, not a ladder. The browser draws a link as
a road or rail segment from hex centre to hex centre.

Road classes follow OpenStreetMap's highway tag: class 0 is highway=motorway (國道) and highway=trunk (快速公路),
class 1 is highway=primary (省道). A class-1 link that already carries a class-0 road is dropped. Rail is
railway=rail without yards, sidings, spurs and crossovers: tier 0 is usage=main (the High Speed Rail and Taiwan
Railway's trunk lines), tier 1 is usage=branch. A link needs one end on Taiwan's land and no end on foreign land,
which drops the Fujian roads that the download window also holds.

Ports: the seven international commercial ports with Taiwan International Ports' cargo throughput, placed at the
centre of the OpenStreetMap harbour area of the same name. Airports: every airport in the Civil Aviation
Administration's table with passengers or cargo in the year, placed at the OpenStreetMap aerodrome with its IATA
code. A site's `cell` is the land cell at its point, or the nearest one up to SITE_RINGS hexes away (a harbour's
centre is on water); x/y stay the true position.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from ..core.geo import SCALE, MapProjection, Shape, ShapeIndex
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, write_web

REQUIRES = ["_world", "tw_boundaries", "osm_tw_transport", "tipc_ports", "caa_airports"]
PRODUCES = ["infrastructure.json"]

SAMPLE_KM = 0.5  # real km between samples along a line (a hex is 3.5 km across)
SAMPLE = SAMPLE_KM * SCALE  # the same in map units
SITE_RINGS = 2
ROAD_CLASSES = [{"id": "interstate", "name": "國道與快速公路"}, {"id": "major", "name": "省道"}]
RAIL_TIERS = [{"id": "main", "name": "高鐵與臺鐵幹線"}, {"id": "secondary", "name": "鐵路支線"}]
ROAD_CLASS_OF = {"motorway": 0, "trunk": 0, "primary": 1}  # OSM highway tag → class index
RAIL_TIER_OF = {"main": 0, "branch": 1}  # OSM usage tag → tier index

# Airport hub classes: the FAA's share rule, applied to the Civil Aviation Administration's passenger counts.
HUB_SHARE = {"L": 0.01, "M": 0.0025, "S": 0.0005}  # share of all passengers at Taiwan's airports in the year
HUB_MIN_PASSENGERS = 10_000  # class N: below the small-hub share but at least this many passengers
HUBS = {"L": "大型樞紐機場", "M": "中型樞紐機場", "S": "小型樞紐機場", "N": "一般客運機場"}

# Which OpenStreetMap aerodrome is each airport of the CAA table: CAA's name → IATA code. Only the choice of the
# element is fixed here; names, positions and every figure are read from the downloaded files. (OSM names differ from
# CAA's: 臺東豐年機場, 嘉義水上機場, 臺中清泉崗機場, 金門尚義機場, 空軍新竹基地.)
AIRPORT_IATA = {
    "臺灣桃園國際機場": "TPE", "高雄國際機場": "KHH", "臺北松山國際機場": "TSA", "花蓮機場": "HUN", "臺東機場": "TTT",
    "澎湖機場": "MZG", "臺中國際機場": "RMQ", "臺南機場": "TNN", "嘉義機場": "CYI", "七美機場": "CMJ", "望安機場": "WOT",
    "蘭嶼機場": "KYD", "綠島機場": "GNI", "金門機場": "KNH", "馬祖北竿機場": "MFK", "屏東機場": "PIF", "新竹機場": "HSZ",
    "馬祖南竿機場": "LZN", "恆春機場": "HCN",
}

UNITS = {"tons": "公噸", "enplanements": "人次", "cargo_lbs": "公噸"}
RULES = {
    "roads": "OpenStreetMap 的道路線形，每 0.5 公里取樣一次後接到相鄰六角格的中心。第 0 級：國道（highway=motorway）與"
             "快速公路（highway=trunk，含省道快速公路與都會區快速道路）。第 1 級：省道（highway=primary），同一對六角格"
             "已有第 0 級道路時不重複畫。路線名稱取自 OSM 的 ref：國道 1 號、台 61 線；多條路線共用一段時取編號最小者。"
             "OSM 沒有車流量資料，道路僅為地圖示意。",
    "rail": "OpenStreetMap 的鐵路（railway=rail），不含調車場、側線與岔道，每 0.5 公里取樣一次後接到相鄰六角格的中心。"
            "第 0 級：幹線（usage=main，台灣高鐵與臺鐵各幹線）；第 1 級：支線（usage=branch）。捷運、輕軌與森林鐵路不在內。",
    "ports": "臺灣港務公司管理的七個國際商港，依全年貨物吞吐量（公噸）排名；進口加出口為國際貨，另列國內貨。位置取"
             "OpenStreetMap 同名港區（landuse=harbour）的中心點。麥寮、和平兩個工業專用港與離島的國內商港不在這份統計內。",
    "airports": "民航局統計表中當年有旅客或貨運的民用機場，位置取 OpenStreetMap 上相同 IATA 代碼的機場。旅客人數是"
                "進出該機場的人次（到站加離站，含過境），不是登機人次；貨運量單位為公噸。機場分級比照美國 FAA 的占比規則，"
                "但以全國機場旅客人次為分母：占 1% 以上為大型樞紐，0.25% 以上為中型，0.05% 以上為小型，"
                "其餘滿 10,000 人次者為一般客運機場，未滿者不分級。",
}


# ------------------------------------------------------------------ hex helpers


def _axial(grid: HexGrid, cell: int) -> tuple[int, int]:
    col, row = grid.col_row(cell)
    return col - (row - (row & 1)) // 2, row


def _from_axial(grid: HexGrid, q: int, r: int) -> int:
    col = q + (r - (r & 1)) // 2
    if 0 <= col < grid.cols and 0 <= r < grid.rows:
        return grid.index(col, r)
    return -1


def hex_distance(grid: HexGrid, a: int, b: int) -> int:
    (q1, r1), (q2, r2) = _axial(grid, a), _axial(grid, b)
    return (abs(q1 - q2) + abs(r1 - r2) + abs((q1 + r1) - (q2 + r2))) // 2


def hex_walk(grid: HexGrid, a: int, b: int) -> list[int]:
    """Cells on the hex line from a to b, both included (cube lerp with a tiny nudge to break ties)."""
    n = hex_distance(grid, a, b)
    if n <= 1:
        return [a, b] if a != b else [a]
    (q1, r1), (q2, r2) = _axial(grid, a), _axial(grid, b)
    out = []
    for i in range(n + 1):
        t = i / n
        x = q1 + (q2 - q1) * t + 1e-6
        z = r1 + (r2 - r1) * t + 1e-6
        y = -x - z
        rx, ry, rz = round(x), round(y), round(z)
        dx, dy, dz = abs(rx - x), abs(ry - y), abs(rz - z)
        if dx > dy and dx > dz:
            rx = -ry - rz
        elif dy <= dz:
            rz = -rx - ry
        c = _from_axial(grid, rx, rz)
        if c >= 0 and (not out or out[-1] != c):
            out.append(c)
    return out


def sample_cells(grid: HexGrid, pts: list[tuple[float, float]], keep=None) -> list[list[int]]:
    """Runs of distinct consecutive cells along a projected line, sampled every SAMPLE map units. `keep(x, y)` False
    breaks the run (the sample is dropped)."""
    runs, run = [], []

    def add(x, y):
        nonlocal run
        if keep is not None and not keep(x, y):
            if len(run) > 1:
                runs.append(run)
            run = []
            return
        c = grid.cell_at(x, y)
        if c < 0:
            return
        if not run or run[-1] != c:
            run.append(c)

    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        steps = max(1, math.ceil(math.hypot(x1 - x0, y1 - y0) / SAMPLE))
        for i in range(steps):
            t = i / steps
            add(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
    if pts:
        add(*pts[-1])
    if len(run) > 1:
        runs.append(run)
    return runs


def straighten(grid: HexGrid, run: list[int]) -> list[int]:
    """Drop detour cells: where the cells before and after a cell are neighbours themselves, the line only clipped
    that cell's corner. Without this, a road running along a row boundary zigzags between two rows."""
    out = []
    for c in run:
        while len(out) >= 2 and c in grid.neighbours(out[-2]):
            out.pop()
        if not out or out[-1] != c:
            out.append(c)
    return out


def links_of(grid: HexGrid, run: list[int]) -> list[tuple[int, int]]:
    out = []
    run = straighten(grid, [c for path in ([run[0]], *(hex_walk(grid, a, b)[1:] for a, b in zip(run, run[1:])))
                            for c in path])
    for a, b in zip(run, run[1:]):
        path = hex_walk(grid, a, b)
        for u, v in zip(path, path[1:]):
            if u != v:
                out.append((u, v) if u < v else (v, u))
    return out


# ------------------------------------------------------------------ roads and rail


def _route_name(highway: str | None, ref: str | None, name: str | None = None) -> str | None:
    """'國道1號' for a freeway, '台61線' for a numbered expressway or provincial highway, else the ref or the name."""
    ref = (ref or "").strip()
    if ref:
        if not ref[0].isdigit():
            return ref  # a county or city route (e.g. 北100)
        if highway == "motorway":
            return f"國道{ref}號" if ref.isdigit() else f"國道{ref}"
        return f"台{ref}線"
    return (name or "").strip() or None


def _route_key(name: str) -> tuple:
    """Sort key that puts the lowest route number first, and a freeway before a provincial highway of that number."""
    digits = ""
    for ch in name:
        if ch.isdigit():
            digits += ch
        elif digits:
            break
    return (0 if digits else 1, int(digits) if digits else 0, 0 if name.startswith("國道") else 1, name)


def _length(pts: list[tuple[float, float]]) -> float:
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def snap(grid: HexGrid, run: list[int], used: set[int]) -> list[int]:
    """Move the cells of a run onto the route's already-used hexes where they are neighbours: the second
    carriageway of a divided road (or the second track) then follows the first instead of drawing a ladder."""
    out: list[int] = []
    for c in run:
        if c not in used:
            near = [n for n in grid.neighbours(c) if n in used]
            if near:
                c = min(near, key=lambda n: hex_distance(grid, n, out[-1])) if out else near[0]
        if not out or out[-1] != c:
            out.append(c)
    return out


def route_links(grid, proj, owner, lines) -> set[tuple[int, int]]:
    """Hex links of one route: its lines, longest first, each snapped onto the hexes the earlier ones use."""
    links: set[tuple[int, int]] = set()
    used: set[int] = set()
    projected = sorted(([proj(lon, lat) for lon, lat in line] for line in lines), key=_length, reverse=True)
    for pts in projected:
        cells: set[int] = set()
        for run in sample_cells(grid, pts):
            run = snap(grid, run, used)
            if len(run) < 2:
                continue
            for a, b in links_of(grid, run):
                cells.update((a, b))
                if owner[a] < 0 and owner[b] < 0:
                    continue  # open water
                if owner[a] == -2 or owner[b] == -2:
                    continue  # the Fujian coast
                links.add((a, b))
        used |= cells
    return links


def build_roads(grid, proj, owner, osm):
    cls_of = defaultdict(lambda: 9)
    names = defaultdict(set)
    for f in osm["roads"]:
        cls = ROAD_CLASS_OF.get(f["highway"])
        if cls is None:
            continue
        name = _route_name(f["highway"], f.get("ref"), f.get("name"))
        for a, b in route_links(grid, proj, owner, f["lines"]):
            if cls < cls_of[(a, b)]:
                cls_of[(a, b)] = cls
                names[(a, b)].clear()
            if cls == cls_of[(a, b)] and name:
                names[(a, b)].add(name)
    roads = []
    for (a, b), cls in sorted(cls_of.items()):
        nm = min(names[(a, b)], key=_route_key) if names[(a, b)] else None
        roads.append([a, b, cls, nm])
    return roads


def build_rail(grid, proj, owner, osm):
    tier_of = {}
    for f in osm["rail"]:
        tier = RAIL_TIER_OF.get(f["usage"])
        if tier is None:
            continue
        for link in route_links(grid, proj, owner, f["lines"]):
            tier_of[link] = min(tier, tier_of.get(link, 9))
    return [[a, b, t] for (a, b), t in sorted(tier_of.items())]


# ------------------------------------------------------------------ sites


def official(name: str | None) -> str:
    return (name or "").replace("台", "臺").strip()


class Locator:
    """lon/lat → the site fields: x, y, land cell, township (`county`), county code (`cbsa`), ISO code (`state`)."""

    def __init__(self, world, grid, proj):
        self.grid, self.proj, self.world = grid, proj, world
        self.owner, self.county, self.geoids = world["owner"], world["county"], world["counties"]
        bounds = load_interim("tw_boundaries")
        abbr_of = {s["fips"]: s["abbr"] for s in bounds["states"]}
        self.abbrs = [abbr_of.get(f) for f in world["states"]]
        self.town_name = {c["geoid"]: c["name"] for c in bounds["counties"]}
        self._towns = [c["geoid"] for c in bounds["counties"]]
        self._town_index = ShapeIndex([Shape(c["rings"]) for c in bounds["counties"]], cell_km=0.25)  # degrees

    def township(self, lon, lat, fallback: str | None = None) -> str | None:
        """Name of the township holding the point itself (the simplified outline can miss a coastal point: then
        the township of the site's hex)."""
        k = self._town_index.locate(lon, lat)
        return self.town_name.get(self._towns[k] if k >= 0 else fallback)

    def land_cell(self, x, y, rings=SITE_RINGS) -> int:
        grid, owner = self.grid, self.owner
        cell = grid.cell_at(x, y)
        if cell < 0:
            return -1
        if owner[cell] >= 0:
            return cell
        seen, frontier = {cell}, [cell]
        for _ in range(rings):
            ring = [n for c in frontier for n in grid.neighbours(c) if n not in seen]
            ring = list(dict.fromkeys(ring))
            seen.update(ring)
            land = [n for n in ring if owner[n] >= 0]
            if land:
                return min(land, key=lambda n: math.dist(grid.center(*grid.col_row(n)), (x, y)))
            frontier = ring
        return -1

    def place(self, lon, lat) -> dict | None:
        if lon is None or lat is None:
            return None
        x, y = self.proj(lon, lat)
        cell = self.land_cell(x, y)
        if cell < 0:
            return None
        ci = self.county[cell]
        geoid = self.geoids[ci] if ci >= 0 else None
        return {"x": round(x, 1), "y": round(y, 1), "cell": cell, "county": geoid,
                "cbsa": self.world["states"][self.owner[cell]], "state": self.abbrs[self.owner[cell]]}


def build_ports(loc: Locator, tipc: dict, harbours: list[dict]) -> tuple[list[dict], list[str]]:
    by_name = defaultdict(list)
    for h in harbours:
        by_name[official(h["name"])].append(h)
    out, unplaced = [], []
    for p in tipc["ports"]:
        found = by_name.get(official(p["name"]), [])
        at = loc.place(found[0]["lon"], found[0]["lat"]) if len(found) == 1 else None
        if at is None:
            unplaced.append(p["name"])
            continue
        out.append({"id": official(p["name"]), "name": official(p["name"]), "name_en": found[0].get("name_en"),
                    "type": "coastal", "rank": p["rank"], "tons": p["tons"], "domestic": p["domestic"],
                    "foreign": p["foreign"], "imports": p["imports"], "exports": p["exports"], "year": tipc["year"],
                    **at})
    out.sort(key=lambda p: p["rank"])
    return out, unplaced


def hub_class(passengers, total) -> str | None:
    if not passengers or not total:
        return None
    share = passengers / total
    for hub, least in HUB_SHARE.items():
        if share >= least:
            return hub
    return "N" if passengers >= HUB_MIN_PASSENGERS else None


def build_airports(loc: Locator, caa: dict, aerodromes: list[dict]) -> tuple[list[dict], list[str]]:
    by_iata = defaultdict(list)
    for a in aerodromes:
        by_iata[a["iata"]].append(a)
    total = caa["total"]["passengers"]
    out, unplaced = [], []
    for a in caa["airports"]:
        if not a["passengers"] and not a["cargo_t"]:
            continue  # no traffic in the year (屏東, 新竹, 恆春)
        found = by_iata.get(AIRPORT_IATA.get(a["name"]), [])
        at = loc.place(found[0]["lon"], found[0]["lat"]) if len(found) == 1 else None
        if at is None:
            unplaced.append(a["name"])
            continue
        out.append({"id": found[0]["iata"], "name": a["name"], "name_en": found[0].get("name_en"),
                    "city": loc.township(found[0]["lon"], found[0]["lat"], at["county"]), "hub": hub_class(a["passengers"], total),
                    "enplanements": _int(a["passengers"]), "enplanements_prev": _int(a["passengers_prev"]),
                    "cargo_lbs": a["cargo_t"] if a["cargo_t"] is None else round(a["cargo_t"], 1),
                    "flights": _int(a["flights"]), "year": caa["year"], **at})
    out.sort(key=lambda a: -(a["enplanements"] or 0))
    return out, unplaced


def _int(v):
    return None if v is None else int(round(v))


# ------------------------------------------------------------------ build


def build() -> None:
    world = load_interim("_world")
    grid, proj, owner = HexGrid(**world["grid"]), MapProjection(**world["projection"]), world["owner"]
    osm_payload = load_interim_payload("osm_tw_transport")
    osm = osm_payload["data"]
    roads = build_roads(grid, proj, owner, osm)
    rail = build_rail(grid, proj, owner, osm)

    loc = Locator(world, grid, proj)
    tipc = load_interim_payload("tipc_ports")
    caa = load_interim_payload("caa_airports")
    ports, lost_ports = build_ports(loc, tipc["data"], osm["harbours"])
    airports, lost_airports = build_airports(loc, caa["data"], osm["airports"])

    doc = {
        "version": 1,
        "vintage": {"roads": osm_payload["vintage"], "rail": osm_payload["vintage"], "ports": tipc["vintage"],
                    "airports": caa["vintage"]},
        "sources": ["osm_tw_transport", "tipc_ports", "caa_airports"],
        "rules": RULES,
        "units": UNITS,
        "road_classes": ROAD_CLASSES,
        "rail_tiers": RAIL_TIERS,
        "hubs": HUBS,
        "roads": roads,
        "rail": rail,
        "ports": ports,
        "airports": airports,
    }
    write_web("infrastructure.json", doc)
    road_cells = {c for a, b, *_ in roads for c in (a, b) if owner[c] >= 0}
    rail_cells = {c for a, b, _ in rail for c in (a, b) if owner[c] >= 0}
    land = sum(1 for o in owner if o >= 0)
    n0 = sum(1 for r in roads if r[2] == 0)
    t0 = sum(1 for r in rail if r[2] == 0)
    print(f"    roads: {n0} freeway/expressway + {len(roads) - n0} provincial links on {len(road_cells)} of {land} "
          f"land hexes; rail: {t0} main + {len(rail) - t0} branch links on {len(rail_cells)} hexes; "
          f"{len(ports)} ports, {len(airports)} airports")
    if lost_ports or lost_airports:
        print(f"    ! not placed (no single OpenStreetMap match on land): ports {lost_ports}, airports {lost_airports}")


# ------------------------------------------------------------------ check


def _neighbours(grid_doc):
    return HexGrid(grid_doc["radius"], grid_doc["cols"], grid_doc["rows"])


def check(web_dir: Path) -> list[tuple[str, str]]:
    path = Path(web_dir) / "infrastructure.json"
    if not path.exists():
        return [("NOTE", "infrastructure.json not built (optional; run: build infrastructure --deps)")]
    out = []
    doc = json.loads(path.read_text())
    for k in ("version", "vintage", "sources", "road_classes", "roads", "rail", "ports", "airports"):
        if k not in doc:
            out.append(("FAIL", f"infrastructure.json lacks '{k}'"))
    if any(lv == "FAIL" for lv, _ in out):
        return out
    if doc["version"] != 1:
        out.append(("FAIL", f"infrastructure.json version {doc['version']!r} (expected 1)"))
    wpath = Path(web_dir) / "world.json"
    world = json.loads(wpath.read_text()) if wpath.exists() else None
    if not world or "grid" not in world:
        return out + [("NOTE", "infrastructure.json: world.json unavailable, cell checks skipped")]
    grid = _neighbours(world["grid"])
    owner = world.get("owner") or []
    n = grid.size
    county_ids = {c["geoid"] for c in world.get("counties", [])}
    cpath = Path(web_dir) / "cities.json"
    city_ids = {c["id"] for c in json.loads(cpath.read_text())} if cpath.exists() else None
    spath = Path(web_dir) / "sources.json"
    if spath.exists():
        src = json.loads(spath.read_text())
        ids = {s["id"] for s in (src.get("sources", src) if isinstance(src, dict) else src) if isinstance(s, dict)}
        miss = [s for s in doc["sources"] if s not in ids]
        if ids and miss:
            out.append(("WARN", f"infrastructure.json cites sources missing from sources.json: {miss}"))

    def bad_link(link, ncls):
        if not isinstance(link, list) or len(link) < 3:
            return "shape"
        a, b, c = link[:3]
        if not all(isinstance(v, int) for v in (a, b, c)):
            return "types"
        if not (0 <= a < b < n):
            return "order/range"
        if b not in grid.neighbours(a):
            return "not neighbours"
        if len(owner) == n and owner[a] < 0 and owner[b] < 0:
            return "no land end"
        if not 0 <= c < ncls:
            return "class"
        return None

    for key, ncls in (("roads", len(doc["road_classes"])), ("rail", len(doc.get("rail_tiers") or [0, 1]))):
        links = doc[key]
        bad = [(l, why) for l in links if (why := bad_link(l, ncls))]
        pairs = [tuple(l[:2]) for l in links if isinstance(l, list)]
        dup = len(pairs) - len(set(pairs))
        if bad or dup:
            out.append(("FAIL", f"infrastructure.json {key}: {len(bad)} bad links (e.g. {bad[:2]}), {dup} duplicates"))
        else:
            cells = {c for l in links for c in l[:2]}
            out.append(("PASS", f"infrastructure.json {key}: {len(links)} neighbour links on {len(cells)} hexes"))
    if any(not (r[3] is None or isinstance(r[3], str)) for r in doc["roads"] if len(r) > 3):
        out.append(("FAIL", "infrastructure.json roads: route name must be a string or null"))

    def check_sites(key, num_keys):
        probs = []
        for s in doc[key]:
            c = s.get("cell")
            if not isinstance(c, int) or not 0 <= c < n or (len(owner) == n and owner[c] < 0):
                probs.append(f"{s.get('id')}: cell {c!r} is not land")
                continue
            if any(s.get(k) is not None and not isinstance(s.get(k), (int, float)) for k in num_keys):
                probs.append(f"{s.get('id')}: non-numeric value")
            cx, cy = grid.center(*grid.col_row(c))
            if not all(isinstance(s.get(k), (int, float)) for k in ("x", "y")) or \
                    math.dist((cx, cy), (s["x"], s["y"])) > (SITE_RINGS + 1) * world["grid"]["radius"] * 2:
                probs.append(f"{s.get('id')}: x/y far from its cell")
            if s.get("county") is not None and county_ids and s["county"] not in county_ids:
                probs.append(f"{s.get('id')}: unknown county {s['county']}")
            if s.get("cbsa") is not None and city_ids is not None and s["cbsa"] not in city_ids:
                probs.append(f"{s.get('id')}: unknown cbsa {s['cbsa']}")
        ids = [s.get("id") for s in doc[key]]
        if len(ids) != len(set(ids)):
            probs.append("duplicate ids")
        return probs

    for key, nums in (("ports", ("tons", "domestic", "foreign", "imports", "exports", "rank")),
                      ("airports", ("enplanements", "enplanements_prev", "cargo_lbs", "flights"))):
        probs = check_sites(key, nums)
        if probs:
            out.append(("FAIL", f"infrastructure.json {key}: {len(probs)} problems, e.g. {probs[:3]}"))
        else:
            metro = sum(1 for s in doc[key] if s.get("cbsa"))
            out.append(("PASS", f"infrastructure.json {key}: {len(doc[key])} sites, {metro} with a county id"))
    hubs = Counter(a.get("hub") for a in doc["airports"])
    out.append(("NOTE", "infrastructure.json airports by hub: " + ", ".join(f"{k or 'no class'} {v}" for k, v in
                                                                         sorted(hubs.items(), key=lambda kv: str(kv[0])))))
    size = path.stat().st_size
    if size > 300_000:
        out.append(("WARN", f"infrastructure.json is {size / 1e3:.0f} kB (eager files should stay under ~300 kB)"))
    return out
