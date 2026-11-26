"""States = the 22 counties and cities (縣市): the same economic profile as a city, ranks, and a label anchor.

Also land-cover shares over the county's hexes and the MW of the power plants mapped in resources.json
(only the sites above each type's threshold, so not the county's total capacity).

Ranks are among the 22 counties (1 = largest). The label anchor is the county's "pole of inaccessibility" on the
hex map (the hex farthest from the border, by hex steps, or one nearly as deep that fits a bigger name), turned
along the county's long axis when that helps, and sized to fit the run of the county's own hexes through the
anchor. Sizes are in map units (a hex has radius 25); `size` assumes ~1 em per (CJK) character, so for small cities
(嘉義市, 新竹市) the minimum can exceed the county and the frontend should clamp or hide those labels.
"""

from __future__ import annotations

import json
import math
from collections import deque

from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web
from .growth import Growth
from .yields import YIELDS, economy

REQUIRES = ["_world", "tw_boundaries", "ris_population", "dgbas_labor", "ics_census"]
PRODUCES = ["states.json"]

MIN_LABEL_KM, MAX_LABEL_KM = 14.0, 110.0  # suggested font height range, map units (hex radius = 25)


def label_anchor(grid: HexGrid, owner: list[int], s: int, name: str) -> dict | None:
    """{x, y, angle, size} for state index `s`, or None if it owns no hex (e.g. DC).

    angle: degrees, clockwise on screen (y down), in (-90, 90]. size: suggested font height in map km.
    """
    cells = [i for i, o in enumerate(owner) if o == s]
    if not cells:
        return None
    # Multi-source BFS from the border hexes inward.
    dist = {}
    queue = deque()
    for c in cells:
        nb = grid.neighbours(c)
        if len(nb) < 6 or any(owner[n] != s for n in nb):
            dist[c] = 0
            queue.append(c)
    while queue:
        c = queue.popleft()
        for n in grid.neighbours(c):
            if owner[n] == s and n not in dist:
                dist[n] = dist[c] + 1
                queue.append(n)
    pts = {c: grid.center(*grid.col_row(c)) for c in cells}
    mx = sum(p[0] for p in pts.values()) / len(cells)
    my = sum(p[1] for p in pts.values()) / len(cells)

    # Principal axis of the hex centres. Labels stay horizontal unless tilting them
    # along a clearly elongated state (at most 45°) allows a much bigger name.
    sxx = sum((p[0] - mx) ** 2 for p in pts.values())
    syy = sum((p[1] - my) ** 2 for p in pts.values())
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts.values())
    theta = 0.5 * math.atan2(2 * sxy, sxx - syy)  # (-90°, 90°], clockwise on screen
    angles = [0.0] + ([theta] if 1 <= abs(math.degrees(theta)) <= 45 else [])
    step = grid.radius / 4

    def reach(x: float, y: float, ux: float, uy: float) -> float:
        """Distance (km) from (x, y) along (ux, uy) before leaving the state's hexes."""
        t = 0.0
        while True:
            c = grid.cell_at(x + (t + step) * ux, y + (t + step) * uy)
            if c < 0 or owner[c] != s:
                return t + step / 2
            t += step

    def fit(c: int, t: float) -> float:
        """Font height (km) for a label centred on hex c at angle t: ~0.6 em per character
        over 90% of the local run through c, and no taller than 80% of the local breadth.
        The run is then re-measured along the label's top and bottom edges (twice), so the
        whole box, not just its centre line, stays inside the state."""
        (x, y), ux, uy = pts[c], math.cos(t), math.sin(t)
        across = 2 * min(reach(x, y, -uy, ux), reach(x, y, uy, -ux))
        h, offsets = 0.8 * across, [0.0]
        for _ in range(3):
            along = min(
                2 * min(reach(x - o * uy, y + o * ux, ux, uy), reach(x - o * uy, y + o * ux, -ux, -uy))
                for o in offsets
            )
            h = min(h, 0.9 * along / (1.0 * max(len(name), 3)))  # CJK glyphs are ~1 em wide
            offsets = [0.0, h / 2, -h / 2]
        return h

    # Candidates: the pole of inaccessibility and hexes nearly as deep; pick the one (and angle)
    # that fits the biggest label, a tilted label only if it is 25% bigger than a flat one.
    far = max(dist.values())
    best = None
    for c in cells:
        if dist[c] < far - 1:
            continue
        for t in angles:
            size = fit(c, t) / (1.25 if t else 1.0)
            score = (round(size), -math.hypot(pts[c][0] - mx, pts[c][1] - my))
            if best is None or score > best[0]:
                best = (score, c, t, size * (1.25 if t else 1.0))
    _, pole, angle, size = best
    px, py = pts[pole]
    return {
        "x": round(px, 1),
        "y": round(py, 1),
        "angle": round(math.degrees(angle), 1),
        "size": round(max(MIN_LABEL_KM, min(MAX_LABEL_KM, size)), 1),
    }


PCT_KEYS = ["forest", "crop", "pasture", "grass", "shrub", "wetland", "developed"]
ENERGY_NOTE = "只計入資源圖層上標示的發電廠與風電、光電聚落（各類型有門檻，見圖層說明），不是該縣市的總裝置容量。"


def land_shares(world: dict, s: int) -> dict | None:
    """Mean world `pct` (0..100) over the state's cells with land-cover samples, as 0..1 fractions."""
    pct, cover, owner = world.get("pct"), world.get("cover"), world["owner"]
    if not pct or not cover:
        return None
    cells = [i for i, o in enumerate(owner) if o == s and cover[i]]
    if not cells:
        return None
    return {k: round(sum(pct[k][i] for i in cells) / len(cells) / 100, 3) for k in PCT_KEYS}


def energy_by_state() -> dict[str, dict] | None:
    """abbr → {unit, total, by_type, sites, note} summed from resources.json items of every MW type
    (counties without a mapped site get zeros under "", the default row); None if resources.json is not built."""
    path = WEB_DATA / "resources.json"
    if not path.exists():
        return None
    res = json.loads(path.read_text())
    mw_types = [t["id"] for t in res["types"] if t["unit"] == "MW"]
    mw: dict[str, dict] = {}
    sites: dict[str, dict] = {}
    for it in res["items"]:
        if it["type"] in mw_types and it.get("state"):
            mw.setdefault(it["state"], dict.fromkeys(mw_types, 0))[it["type"]] += it["value"] or 0
            sites.setdefault(it["state"], dict.fromkeys(mw_types, 0))[it["type"]] += 1
    out = {}
    for abbr in ["", *mw]:
        by_type = {k: round(v) for k, v in mw.get(abbr, dict.fromkeys(mw_types, 0)).items()}
        out[abbr] = {"unit": "MW", "total": sum(by_type.values()), "by_type": by_type,
                     "sites": sites.get(abbr, dict.fromkeys(mw_types, 0)), "note": ENERGY_NOTE}
    return out


def build() -> None:
    world = load_interim("_world")
    bounds = load_interim("tw_boundaries")
    ris = load_interim("ris_population")
    labor = load_interim("dgbas_labor")
    census = load_interim("ics_census")
    growth = Growth(ris)
    grid = HexGrid(**world["grid"])
    owner = world["owner"]
    names = {s["fips"]: s for s in bounds["states"]}

    energy = energy_by_state()
    if energy is None:
        print("    resources.json not built yet: energy left null")
    states = []
    for i, fips in enumerate(world["states"]):
        meta = names[fips]
        econ = economy(growth.population(fips), labor["counties"].get(fips), census["counties"].get(fips),
                       census["year"])
        states.append(
            {
                "fips": fips,
                "abbr": meta["abbr"],
                "name": meta["name"],
                "name_en": meta["name_en"],
                **econ,
                "growth": growth.county(fips),
                "growth_years": growth.years,
                "pop_series": growth.series(ris["counties"].get(fips)),
                "ranks": {},
                "label": label_anchor(grid, owner, i, meta["name"]),
                "land": land_shares(world, i),
                "energy": dict(energy.get(meta["abbr"]) or energy[""]) if energy is not None else None,
            }
        )
    for y in YIELDS:
        key = y["key"]
        ranked = sorted((s for s in states if s["yields"][key] is not None), key=lambda s: -s["yields"][key])
        for r, s in enumerate(ranked, 1):
            s["ranks"][key] = r
        for s in states:
            s["ranks"].setdefault(key, None)
    write_web("states.json", states)
    no_label = [s["abbr"] for s in states if not s["label"]]
    print(f"    {len(states)} counties" + (f"; no hexes (no label anchor): {', '.join(no_label)}" if no_label else ""))
