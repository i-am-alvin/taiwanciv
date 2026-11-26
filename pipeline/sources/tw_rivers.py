"""Named rivers of Taiwan from OpenStreetMap (river relations with their geometry, via the Overpass API)."""

from __future__ import annotations

import json
import math
import urllib.parse

from ..core.source import Source, SourceInfo

ENDPOINT = "https://overpass.private.coffee/api/interpreter"
BBOX = (21.8, 118.0, 26.5, 122.1)  # south, west, north, east
QUERY = (
    "[out:json][timeout:300];"
    f'relation["waterway"="river"]["name"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});'
    "out geom;"
)
FILE = "rivers_relations.json"
MIN_KM = 15.0  # rivers shorter than this (main stem) are left off the map
# rank like Natural Earth's scalerank (lower = bigger): by main-stem length in km
RANKS = [(150, 1), (100, 2), (70, 3), (50, 4), (35, 5), (25, 6), (MIN_KM, 7)]


def length_km(line: list[tuple[float, float]]) -> float:
    total = 0.0
    for (lo1, la1), (lo2, la2) in zip(line, line[1:]):
        x = math.radians(lo2 - lo1) * math.cos(math.radians((la1 + la2) / 2))
        y = math.radians(la2 - la1)
        total += 6371.0088 * math.hypot(x, y)
    return total


class TwRivers(Source):
    info = SourceInfo(
        id="tw_rivers",
        title="Rivers of Taiwan (OpenStreetMap river relations)",
        publisher="OpenStreetMap contributors, via the Overpass API",
        homepage="https://www.openstreetmap.org/",
        license="Open Database License (ODbL) 1.0. © OpenStreetMap contributors",
        description=f"Every named river relation (waterway=river) in the map window, main stem only. Rivers whose main "
        f"stem is shorter than {MIN_KM:g} km are left out; the rest are ranked by length (rank 1 ≥ 150 km, such as the "
        "Zhuoshui and Gaoping) and drawn thinner as they get shorter.",
        used_for=["Rivers"],
    )

    def fetch(self, force=False):
        url = f"{ENDPOINT}?data={urllib.parse.quote(QUERY)}"
        self.download(url, FILE, force=force)

    def process(self):
        data = json.loads((self.raw_dir / FILE).read_text(encoding="utf-8"))
        rivers = []
        for rel in data.get("elements", []):
            name = rel.get("tags", {}).get("name")
            lines = []
            for m in rel.get("members", []):
                if m.get("type") != "way" or m.get("role", "") not in ("", "main_stream") or not m.get("geometry"):
                    continue
                lines.append([(round(g["lon"], 5), round(g["lat"], 5)) for g in m["geometry"]])
            if not lines:
                continue
            total = sum(length_km(l) for l in lines)
            if total < MIN_KM:
                continue
            rank = next(r for km, r in RANKS if total >= km)
            for line in lines:
                rivers.append({"name": name, "rank": rank, "featurecla": "River", "km": round(total, 1), "line": line})
        names = {r["name"] for r in rivers}
        print(f"    {len(names)} rivers ≥ {MIN_KM:g} km, {len(rivers)} pieces")
        return {
            "vintage": "OpenStreetMap via Overpass (retrieved with the raw file; see manifest)",
            "_files": [FILE],
            "rivers": rivers,
        }
