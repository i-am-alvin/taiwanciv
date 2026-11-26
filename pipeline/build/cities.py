"""Cities = the 22 counties and cities (縣市), placed at their most populous township.

Taiwan's economic statistics (jobs by industry, unemployment, census value added) stop at the county level, so the
county plays the role of a US metro area. Each city keeps a true position (x, y): the centroid of its most populous
township (household registration, end of the latest year), and gets one land cell for its banner, snapped to the
nearest own land cell when that is water, and nudged up to 2 rings away when a bigger city already holds it.
Gold is the census value added of the county (see yields.py). Population growth compares year-end registered
populations (see growth.py). For the City view each city also gets its member townships, a hex footprint (cells
where most township samples are member townships), its yearly population series, ranks and its 5 nearest peers by
population (see docs/DATA_CONTRACTS.md).
"""

from __future__ import annotations

import math

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, write_web
from .growth import Growth
from .yields import INDUSTRIES, YIELDS, economy

REQUIRES = ["_world", "tw_boundaries", "ris_population", "dgbas_labor", "ics_census"]
PRODUCES = ["cities.json", "nation.json"]

CAPITAL = "63000"  # 臺北市, seat of the central government


def ring_search(grid: HexGrid, start: int, max_rings: int):
    """Yield (ring, cell) for every cell within `max_rings` steps of `start`, nearest rings first."""
    seen = {start}
    frontier = [start]
    yield 0, start
    for ring in range(1, max_rings + 1):
        nxt = []
        for c in frontier:
            for n in grid.neighbours(c):
                if n not in seen:
                    seen.add(n)
                    nxt.append(n)
                    yield ring, n
        frontier = nxt


def nearest_land(grid: HexGrid, owner: list[int], cell: int, x: float, y: float, state: int, max_rings=8):
    """Nearest Taiwan land cell to (x, y), preferring `state`: the first ring with land, plus one more."""
    found_ring = None
    best = None
    for ring, c in ring_search(grid, cell, max_rings):
        if found_ring is not None and ring > found_ring + 1:
            break
        if owner[c] < 0:
            continue
        found_ring = ring if found_ring is None else found_ring
        cx, cy = grid.center(*grid.col_row(c))
        score = (owner[c] != state, math.hypot(cx - x, cy - y))
        if best is None or score < best[0]:
            best = (score, c)
    return best[1] if best else -1


def free_cell(grid: HexGrid, owner, taken: set, cell: int, x: float, y: float, state: int, max_rings=2):
    """Nearest untaken land cell within `max_rings`, preferring `state`; None if there is none."""
    best = None
    for ring, c in ring_search(grid, cell, max_rings):
        if owner[c] < 0 or c in taken:
            continue
        cx, cy = grid.center(*grid.col_row(c))
        score = (owner[c] != state, math.hypot(cx - x, cy - y))
        if best is None or score < best[0]:
            best = (score, c)
    return best[1] if best else None


def ring_centroid(rings: list[list[tuple[float, float]]]) -> tuple[float, float]:
    """Area-weighted centroid (lon, lat) of a township's largest ring (its main island or main piece)."""
    def area_c(r):
        a = cx = cy = 0.0
        for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1]):
            f = x0 * y1 - x1 * y0
            a += f
            cx += (x0 + x1) * f
            cy += (y0 + y1) * f
        return a / 2, cx, cy
    best = max(rings, key=lambda r: abs(area_c(r)[0]))
    a, cx, cy = area_c(best)
    if a == 0:
        return best[0]
    return cx / (6 * a), cy / (6 * a)


FOOTPRINT_MAJORITY = 4  # of a cell's 7 township samples
PEERS = 5
RANK_KEYS = ["population", "gdp", "gdp_per_capita", "growth"] + [y["key"] for y in YIELDS]


def footprints(world: dict, members: dict[str, list[str]]) -> dict[str, set[int]]:
    """City id → land cells where at least FOOTPRINT_MAJORITY of the 7 township samples are member townships."""
    city_of = {g: code for code, geoids in members.items() for g in geoids}
    by_index = [city_of.get(g) for g in world["counties"]]
    out: dict[str, set[int]] = {}
    for cell, s in enumerate(world["county_samples"]):
        if not s or world["owner"][cell] < 0:
            continue
        votes: dict[str, int] = {}
        for k in s:
            code = by_index[k] if k >= 0 else None
            if code:
                votes[code] = votes.get(code, 0) + 1
        for code, n in votes.items():
            if n >= FOOTPRINT_MAJORITY:
                out.setdefault(code, set()).add(cell)
    return out


def add_ranks(cities: list[dict]) -> None:
    """ranks: 1 = highest among all cities, null where the value is null (cities are sorted by population,
    so ties keep population order). peers: the PEERS cities closest in population (by ratio)."""
    def value(c, key):
        if key == "gdp_per_capita":
            return c["gdp"] / c["population"] if c.get("gdp") is not None and c.get("population") else None
        if key in ("population", "gdp", "growth"):
            return c.get(key)
        return c["yields"].get(key)

    for c in cities:
        c["ranks"] = {}
    for key in RANK_KEYS:
        have = [c for c in cities if value(c, key) is not None]
        have.sort(key=lambda c: -value(c, key))
        for r, c in enumerate(have, 1):
            c["ranks"][key] = r
        for c in cities:
            c["ranks"].setdefault(key, None)
    for i, c in enumerate(cities):
        lp = math.log(c["population"])
        near = sorted((abs(math.log(o["population"]) - lp), j) for j, o in enumerate(cities) if j != i)
        c["peers"] = [cities[j]["id"] for _, j in near[:PEERS]]


def build() -> None:
    world = load_interim("_world")
    bounds = load_interim("tw_boundaries")
    ris_payload = load_interim_payload("ris_population")
    ris = ris_payload["data"]
    labor_payload = load_interim_payload("dgbas_labor")
    labor = labor_payload["data"]
    census_payload = load_interim_payload("ics_census")
    census = census_payload["data"]
    proj = MapProjection(**world["projection"])
    grid = HexGrid(**world["grid"])
    owner = world["owner"]
    growth = Growth(ris)

    state_index = {fips: i for i, fips in enumerate(world["states"])}
    towns_of: dict[str, list[dict]] = {}
    for t in bounds["counties"]:
        towns_of.setdefault(t["state_fips"], []).append(t)

    cities = []
    for s in bounds["states"]:
        fips = s["fips"]
        towns = towns_of[fips]
        seat = max(towns, key=lambda t: ris["towns"][t["geoid"]]["pop"][-1] or 0)
        lon, lat = ring_centroid(seat["rings"])
        x, y = proj(lon, lat)
        econ = economy(growth.population(fips), labor["counties"].get(fips), census["counties"].get(fips),
                       census["year"])
        cities.append({
            "id": fips,
            "name": s["name"],
            "full": f"{s['name']} {s['name_en']}",
            "name_en": s["name_en"],
            "seat": seat["name"],
            "states": [s["abbr"]],
            "metro": True,
            "capital": fips == CAPITAL,
            "x": round(x, 1),
            "y": round(y, 1),
            "cell": grid.cell_at(x, y),
            **econ,
            "growth": growth.county(fips),
            "growth_years": growth.years,
            "counties": sorted(t["geoid"] for t in towns),
            "pop_series": growth.series(ris["counties"].get(fips)),
        })
    cities.sort(key=lambda c: -c["population"])

    taken: set[int] = set()
    snapped, moved, shared = [], [], []
    for c in cities:
        state = state_index[c["id"]]
        cell = c["cell"]
        if cell < 0 or owner[cell] != state:
            cell = nearest_land(grid, owner, max(cell, 0), c["x"], c["y"], state)
            snapped.append(c["name"])
        if cell in taken:
            alt = free_cell(grid, owner, taken, cell, c["x"], c["y"], state)
            if alt is None:
                shared.append(c["name"])
            else:
                cell = alt
                moved.append(c["name"])
        taken.add(cell)
        c["cell"] = cell

    feet = footprints(world, {c["id"]: c["counties"] for c in cities})
    own_only = []
    for c in cities:
        cells = feet.get(c["id"], set())
        if c["cell"] not in cells:
            if not cells:
                own_only.append(c["name"])
            cells = cells | {c["cell"]}
        c["footprint"] = sorted(cells)
    add_ranks(cities)

    print(f"    {len(cities)} cities, placed at their most populous township")
    for c in cities:
        print(f"      {c['name']}: {c['seat']}, pop {c['population']:,}, footprint {len(c['footprint'])}")
    for label, items in (
        ("snapped onto their own land", snapped),
        ("moved to a free neighbouring cell", moved),
        ("still sharing a cell", shared),
        ("with a one-hex footprint", own_only),
        ("without jobs (not in the Manpower Survey)", [c["name"] for c in cities if c["employed"] is None]),
    ):
        if items:
            print(f"    {len(items)} {label}: {', '.join(items)}")

    nation = economy(growth.population(), labor["nation"], census["nation"], census["year"])
    # The Manpower Survey's national figures cover the Taiwan area (without Kinmen and Lienchiang).
    nation["growth"] = growth.nation()
    nation["growth_years"] = growth.years
    nation["pop_series"] = growth.series(ris["nation"])
    write_web("cities.json", cities)
    write_web(
        "nation.json",
        {
            "vintage": f"戶籍人口 {growth.end} 年底；人力資源調查 {labor['year']} 年平均",
            "year": growth.end,
            "gdp_vintage": f"{census['year']} 年工業及服務業普查（生產毛額）",
            "nation": nation,
            "yields": YIELDS,
            "industries": {k: label for k, (_, label) in INDUSTRIES.items()},
            "gdp_industries": {},
            "currency": "TWD",
            "country": {"name": "臺灣", "name_en": "Taiwan", "abbr": "TW"},
        },
    )
