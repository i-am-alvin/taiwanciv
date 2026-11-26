"""Trade routes: the largest truck freight flows between counties, as caravan routes between cities.

The truck freight survey (`motc_freight` interim) estimates the tonnes carried by truck in a year from each county
to each county. Here:

* A zone is one county or city of the survey (20: Taiwan and Penghu). Kinmen and Lienchiang are outside the survey,
  so they are not zones.
* A route is a pair of different counties; both directions are summed. Freight that starts and ends in one county
  is not a route (it is the zone's `within` total).
* The TOP_N largest pairs by tonnes are kept. There is no minimum distance: in Taiwan the largest flows are between
  neighbouring counties.
* The survey has tonnes only. It gives no money value of the goods, no tonne-kilometres by county pair and no
  commodity by county pair, so `value_musd`, `tmiles_m` and `top_commodity` are null, and so are the money keys
  `national_musd`, `totals_musd` and the money-valued `partners`. The tonnage equivalents are under
  `national_tons_k`, `totals_tons_k` and `partners_tons_k`.
* The survey is of trucks, so every route's mode is `truck`: rail, sea and air freight are not in it.

Each zone is anchored on its city's banner cell (cities.json; in this build a city is a county). Each route has a
`path` of neighbouring cells along the road links in infrastructure.json (freeways preferred, a cross-country step
where no road joins): the survey says where freight starts and ends, not which way it went, so the path is a
drawing aid, not data.
"""

from __future__ import annotations

import heapq
import json
import math
from pathlib import Path

from ..core.geo import SCALE
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, load_interim_payload, write_web

REQUIRES = ["_world", "motc_freight", "tw_boundaries", "cities.json", "infrastructure.json"]
PRODUCES = ["trade.json"]

TOP_N = 40
PARTNERS = 5
MODES = [("truck", "汽車貨運")]
# Path costs per hex step: freeway or expressway, provincial highway, rail-only, cross-country land, water.
STEP_COST = {"interstate": 1.0, "major": 1.4, "rail": 1.8, "land": 4.0, "water": 10.0}

RULE = (f"汽車貨運量最大的 {TOP_N} 組縣市配對：兩個不同縣市之間以貨車運送的貨物噸數，雙向合計。"
        "起訖都在同一縣市的貨運不算路線。資料為交通部「汽車貨運調查」的抽樣推估值，單位為公噸；"
        "只有公路貨車（不含鐵路、海運、空運），調查沒有貨物金額，也不含金門縣、連江縣。")
PATH_NOTE = ("調查只記錄貨物的起點與終點縣市，不含實際路徑：兩個縣市之間畫的線僅為示意，不是貨物走的路。")


# ------------------------------------------------------------------ paths (as in the US build)


def road_graph(infra: dict | None) -> dict:
    cost = {}
    if not infra:
        return cost
    classes = [c["id"] for c in infra.get("road_classes", [])]
    for a, b, *_ in infra.get("rail", []):
        cost[(a, b)] = STEP_COST["rail"]
    for a, b, cls, *_ in infra.get("roads", []):
        cost[(a, b)] = min(cost.get((a, b), 99), STEP_COST.get(classes[cls] if cls < len(classes) else "major", 1.4))
    return cost


def shortest_path(grid: HexGrid, owner: list, links: dict, src: int, dst: int) -> list[int]:
    """Cheapest chain of neighbouring cells from src to dst (Dijkstra with an A* bound)."""
    def h(c):
        x0, y0 = grid.center(*grid.col_row(c))
        x1, y1 = grid.center(*grid.col_row(dst))
        return math.hypot(x1 - x0, y1 - y0) / (math.sqrt(3) * grid.radius) * STEP_COST["interstate"]

    best = {src: 0.0}
    prev = {}
    heap = [(h(src), 0.0, src)]
    while heap:
        _, d, c = heapq.heappop(heap)
        if c == dst:
            break
        if d > best.get(c, math.inf):
            continue
        for n in grid.neighbours(c):
            key = (c, n) if c < n else (n, c)
            step = links.get(key)
            if step is None:
                step = STEP_COST["land"] if owner[n] >= 0 else STEP_COST["water"]
            nd = d + step
            if nd < best.get(n, math.inf):
                best[n] = nd
                prev[n] = c
                heapq.heappush(heap, (nd + h(n), nd, n))
    if dst not in best:
        return [src, dst] if src == dst else []
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    return path[::-1]


# ------------------------------------------------------------------ zones and flows


def _k(tonnes: int | float | None) -> float | None:
    """Tonnes as thousand tonnes."""
    return None if tonnes is None else round(tonnes / 1000, 1)


def build_zones(freight: dict, world: dict, bounds: list[dict], cities: list[dict]) -> tuple[dict, dict]:
    """Zones keyed by county code, and the survey's place name → zone id."""
    by_name = {s["name"]: s for s in bounds}
    by_id = {c["id"]: c for c in cities}
    towns = {}  # county code → townships that own a cell
    for i, ci in enumerate(world["county"]):
        if ci >= 0 and world["owner"][i] >= 0:
            towns.setdefault(world["states"][world["owner"][i]], set()).add(ci)
    zones, zone_of = {}, {}
    for name in freight["places"]:
        if name not in by_name:
            raise ValueError(f"the survey's {name} is not a county of tw_boundaries")
        s = by_name[name]
        zid = s["fips"]
        c = by_id.get(zid)
        flows = freight["flows"][name]
        within = flows[name]
        zones[zid] = {
            "id": zid, "faf": [], "name": name, "short": c["name"] if c else name, "kind": "county",
            "states": [s["abbr"]], "cities": [zid] if c else [], "counties": len(towns.get(zid, ())),
            "anchor": {"cell": c["cell"], "x": c["x"], "y": c["y"], "city": zid} if c and c.get("cell") is not None else None,
            "partners": [], "totals_musd": None,
            "totals_tons_k": {
                "within": _k(within),  # starts and ends in the county; null where the report prints its nil mark
                "out": _k(freight["out"][name] - (within or 0)),   # to other counties
                "in": _k(freight["in"][name] - (within or 0)),     # from other counties
            },
        }
        zone_of[name] = zid
    return zones, zone_of


def pair_tonnes(freight: dict, zone_of: dict) -> dict:
    """(zone a, zone b), a < b → tonnes, both directions summed; pairs with no reported flow are absent."""
    flows = freight["flows"]
    pairs = {}
    for o, row in flows.items():
        for d, v in row.items():
            if o == d or v is None:
                continue
            a, b = sorted((zone_of[o], zone_of[d]))
            pairs[(a, b)] = pairs.get((a, b), 0) + v
    return pairs


# ------------------------------------------------------------------ build


def build() -> None:
    world = load_interim("_world")
    grid, owner = HexGrid(**world["grid"]), world["owner"]
    payload = load_interim_payload("motc_freight")
    freight = payload["data"]
    bounds = load_interim("tw_boundaries")["states"]
    cities = json.loads((WEB_DATA / "cities.json").read_text())
    ipath = WEB_DATA / "infrastructure.json"
    infra = json.loads(ipath.read_text()) if ipath.exists() else None

    zones, zone_of = build_zones(freight, world, bounds, cities)
    pairs = pair_tonnes(freight, zone_of)

    cands = [(t, a, b) for (a, b), t in pairs.items() if t > 0 and zones[a]["anchor"] and zones[b]["anchor"]]
    cands.sort(key=lambda c: (-c[0], c[1], c[2]))
    links = road_graph(infra)
    routes = []
    for rank, (tonnes, a, b) in enumerate(cands[:TOP_N], 1):
        za, zb = zones[a]["anchor"], zones[b]["anchor"]
        routes.append({
            "a": a, "b": b, "rank": rank,
            "value_musd": None,       # the survey has no value of goods
            "tons_k": _k(tonnes),
            "tmiles_m": None,         # nor tonne-kilometres by county pair
            "modes": {"truck": 1.0}, "top_mode": "truck", "top_commodity": None,
            "dist_km": round(math.dist((za["x"], za["y"]), (zb["x"], zb["y"])) / SCALE),
            "path": shortest_path(grid, owner, links, za["cell"], zb["cell"]),
        })

    for zid, z in zones.items():
        ps = [[b if a == zid else a, _k(t), "truck"] for (a, b), t in pairs.items() if zid in (a, b) and t > 0]
        ps.sort(key=lambda p: (-p[1], p[0]))
        z["partners_tons_k"] = ps[:PARTNERS]

    within = sum(freight["flows"][p][p] or 0 for p in freight["places"])
    doc = {
        "version": 1,
        "vintage": payload["vintage"],
        "year": freight["year"],
        "sources": ["motc_freight"],
        "rule": RULE,
        "path_note": PATH_NOTE,
        "units": {"value_musd": None, "tons_k": "千公噸", "tmiles_m": None, "dist_km": "公里（兩縣市錨點的直線距離）"},
        "modes": [{"id": m, "name": n} for m, n in MODES],
        "commodities": {},
        "national_musd": None,
        "national_tons_k": {"total": _k(freight["total"]), "within_county": _k(within),
                            "between_counties": _k(sum(pairs.values()))},
        "zones": sorted(zones.values(), key=lambda z: z["id"]),
        "routes": routes,
    }
    write_web("trade.json", doc)
    if routes:
        top = routes[0]
        print(f"    {len(zones)} zones, {len(cands)} county pairs with freight, {len(routes)} routes over "
              f"{len({r['a'] for r in routes} | {r['b'] for r in routes})} zones; top: {zones[top['a']]['short']} – "
              f"{zones[top['b']]['short']} {top['tons_k'] / 1e3:.1f} million tonnes")
    else:
        print("    no routes")


# ------------------------------------------------------------------ check


def check(web_dir: Path) -> list[tuple[str, str]]:
    path = Path(web_dir) / "trade.json"
    if not path.exists():
        return [("NOTE", "trade.json not built (optional; run: build trade --deps)")]
    out = []
    doc = json.loads(path.read_text())
    for k in ("version", "vintage", "year", "sources", "rule", "modes", "commodities", "zones", "routes"):
        if k not in doc:
            out.append(("FAIL", f"trade.json lacks '{k}'"))
    if out:
        return out
    if doc["version"] != 1:
        out.append(("FAIL", f"trade.json version {doc['version']!r} (expected 1)"))
    wpath = Path(web_dir) / "world.json"
    world = json.loads(wpath.read_text()) if wpath.exists() else None
    grid = HexGrid(world["grid"]["radius"], world["grid"]["cols"], world["grid"]["rows"]) if world and "grid" in world else None
    owner = (world or {}).get("owner") or []
    cpath = Path(web_dir) / "cities.json"
    city_ids = {c["id"] for c in json.loads(cpath.read_text())} if cpath.exists() else None

    zones = {}
    probs = []
    for z in doc["zones"]:
        for k in ("id", "faf", "name", "short", "kind", "states", "cities", "anchor"):
            if k not in z:
                probs.append(f"zone {z.get('id')} lacks {k}")
        zones[z.get("id")] = z
        if z.get("kind") != "county":
            probs.append(f"zone {z.get('id')} kind {z.get('kind')!r}")
        a = z.get("anchor")
        if a is not None and grid is not None:
            c = a.get("cell")
            if not isinstance(c, int) or not 0 <= c < grid.size or (owner and owner[c] < 0):
                probs.append(f"zone {z.get('id')} anchor cell {c!r} is not a land cell of the map")
        if city_ids is not None and any(c not in city_ids for c in z.get("cities") or []):
            probs.append(f"zone {z.get('id')} lists unknown cities")
    if len(zones) != len(doc["zones"]):
        probs.append("duplicate zone ids")
    if probs:
        out.append(("FAIL", f"trade.json zones: {len(probs)} problems, e.g. {probs[:3]}"))
    else:
        out.append(("PASS", f"trade.json zones: {len(zones)} zones, {sum(1 for z in zones.values() if z['anchor'])} anchored"))

    mode_ids = {m["id"] for m in doc["modes"]}
    probs, ranks, pairs = [], [], set()
    for r in doc["routes"]:
        a, b = zones.get(r.get("a")), zones.get(r.get("b"))
        if a is None or b is None or r.get("a") == r.get("b"):
            probs.append(f"route {r.get('rank')}: unknown zone, or the same zone twice")
            continue
        pairs.add(tuple(sorted((r["a"], r["b"]))))
        ranks.append(r.get("rank"))
        if not isinstance(r.get("tons_k"), (int, float)) or r["tons_k"] <= 0:
            probs.append(f"route {r['rank']}: tons_k {r.get('tons_k')!r} must be positive")
        if not isinstance(r.get("dist_km"), (int, float)) or r["dist_km"] < 0:
            probs.append(f"route {r['rank']}: dist_km {r.get('dist_km')!r}")
        if r.get("value_musd") is not None:  # the survey has tonnes only: a value here would be made up
            probs.append(f"route {r['rank']}: value_musd {r['value_musd']!r} but the source has no value of goods")
        if r.get("top_mode") not in mode_ids or set(r.get("modes", {})) - mode_ids:
            probs.append(f"route {r['rank']}: unknown mode")
        shares = list(r.get("modes", {}).values())
        if shares and abs(sum(shares) - 1) > 0.01:
            probs.append(f"route {r['rank']}: mode shares sum to {sum(shares):.3f}")
        if r.get("top_commodity") is not None and r["top_commodity"] not in doc["commodities"]:
            probs.append(f"route {r['rank']}: commodity {r['top_commodity']} not named")
        p = r.get("path")
        if p is not None and grid is not None:
            if not p or (a["anchor"] and p[0] != a["anchor"]["cell"]) or (b["anchor"] and p[-1] != b["anchor"]["cell"]):
                probs.append(f"route {r['rank']}: path does not join the anchors")
            elif any(v not in grid.neighbours(u) for u, v in zip(p, p[1:])):
                probs.append(f"route {r['rank']}: path steps are not neighbours")
    if ranks != list(range(1, len(ranks) + 1)):
        probs.append("ranks are not 1..N in order")
    vals = [r["tons_k"] for r in doc["routes"] if isinstance(r.get("tons_k"), (int, float))]
    if vals != sorted(vals, reverse=True):
        probs.append("routes are not sorted by tonnage")
    if len(pairs) != len(doc["routes"]):
        probs.append("duplicate zone pairs")
    if probs:
        out.append(("FAIL", f"trade.json routes: {len(probs)} problems, e.g. {probs[:3]}"))
    elif doc["routes"]:
        top = doc["routes"][0]
        out.append(("PASS", f"trade.json routes: {len(doc['routes'])} routes, {sum(vals) / 1e3:,.0f} million tonnes in "
                            f"all; #1 {zones[top['a']]['short']} – {zones[top['b']]['short']} "
                            f"{top['tons_k'] / 1e3:,.1f} million tonnes"))
    else:
        out.append(("WARN", "trade.json has no routes"))
    size = path.stat().st_size
    if size > 300_000:
        out.append(("WARN", f"trade.json is {size / 1e3:.0f} kB (eager files should stay under ~300 kB)"))
    return out
