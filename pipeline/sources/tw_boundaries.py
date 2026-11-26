"""County (縣市) and township (鄉鎮市區) outlines from the Ministry of the Interior, via the taiwan-atlas package."""

from __future__ import annotations

import json

from ..core.source import Source, SourceInfo

VERSION = "2021.9.20"
BASE = f"https://cdn.jsdelivr.net/npm/taiwan-atlas@{VERSION}"
FILE = "towns-10t.json"

# The map window: Taiwan, Penghu, Kinmen and Matsu. Rings wholly outside it (Pratas and the Spratlys, which
# belong to Kaohsiung's Cijin District) are dropped, as the original leaves out Alaska and Hawaii.
BBOX = (117.8, 21.6, 122.4, 26.6)

# ISO 3166-2:TW codes, used as the short id of each county (the role a US state abbreviation plays).
ISO = {
    "63000": "TPE", "65000": "NWT", "68000": "TAO", "66000": "TXG", "67000": "TNN", "64000": "KHH",
    "10017": "KEE", "10018": "HSZ", "10004": "HSQ", "10005": "MIA", "10007": "CHA", "10008": "NAN",
    "10009": "YUN", "10020": "CYI", "10010": "CYQ", "10013": "PIF", "10002": "ILA", "10015": "HUA",
    "10014": "TTT", "10016": "PEN", "09020": "KIN", "09007": "LIE",
}


def official(name: str) -> str:
    """taiwan-atlas writes 台; official names (and the household registry) use 臺."""
    return name.replace("台", "臺")


def decode_topojson(topo: dict, obj: str) -> list[tuple[dict, list[list[tuple[float, float]]]]]:
    """(properties, rings) for each geometry of a quantized TopoJSON object."""
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)

    def ring(idx: list[int]) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for a in idx:
            pts = arcs[a] if a >= 0 else arcs[~a][::-1]
            out.extend(pts if not out else pts[1:])
        return out

    out = []
    for g in topo["objects"][obj]["geometries"]:
        polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]] if g["type"] == "Polygon" else []
        rings = [ring(r) for poly in polys for r in poly]
        out.append((g.get("properties") or {}, rings))
    return out


def in_window(r: list[tuple[float, float]]) -> bool:
    x0, y0, x1, y1 = BBOX
    return any(x0 <= lon <= x1 and y0 <= lat <= y1 for lon, lat in r)


class TwBoundaries(Source):
    info = SourceInfo(
        id="tw_boundaries",
        title="County and township boundaries (TopoJSON)",
        publisher="Ministry of the Interior, National Land Surveying and Mapping Center (packaged by taiwan-atlas)",
        homepage="https://github.com/dkaoster/taiwan-atlas",
        license="Government Open Data License v1.0 (MOI); taiwan-atlas packaging MIT",
        description="Outlines of the 22 counties and cities (縣市) and 368 townships and districts (鄉鎮市區), "
        "simplified TopoJSON built from the National Land Surveying and Mapping Center's boundary files. "
        "Decide which county and township each hex belongs to. Pratas and the Spratlys are outside the map.",
        used_for=["County and township of each hex", "County borders"],
    )

    def fetch(self, force=False):
        self.download(f"{BASE}/{FILE}", FILE, force=force)

    def process(self):
        topo = json.loads((self.raw_dir / FILE).read_text(encoding="utf-8"))
        states = []
        for props, rings in decode_topojson(topo, "counties"):
            code = props["COUNTYCODE"]
            states.append({
                "fips": code, "abbr": ISO[code], "name": official(props["COUNTYNAME"]),
                "name_en": props["COUNTYENG"], "rings": [r for r in rings if in_window(r)],
            })
        counties = []
        for props, rings in decode_topojson(topo, "towns"):
            counties.append({
                "geoid": props["TOWNCODE"], "state_fips": props["COUNTYCODE"],
                "name": official(props["TOWNNAME"]), "name_en": props["TOWNENG"],
                "rings": [r for r in rings if in_window(r)],
            })
        if len(states) != 22 or len(counties) != 368:
            raise ValueError(f"expected 22 counties and 368 townships, got {len(states)} and {len(counties)}")
        return {
            "vintage": f"taiwan-atlas {VERSION} (MOI boundaries)",
            "_files": [FILE],
            "states": states,
            "counties": counties,
        }
