"""Outlines of the national parks and the national nature park, from OpenStreetMap (OSM API)."""

from __future__ import annotations

import json
import math
import re

from ..core import fetch
from ..core.source import Source, SourceInfo

# Which relations: every OpenStreetMap relation tagged boundary=national_park whose name ends in 國家公園 or
# 國家自然公園 inside 20.0-26.6 N, 116.0-122.5 E (found with that Overpass query on 2026-11-26; the public
# Overpass servers were too unreliable to keep in the pipeline, so the ids are listed and each relation is read
# from the OpenStreetMap API). process() checks both tags, so a relation that stops being a park fails loudly.
# The numbers are OSM relation ids, not data: names, outlines and everything else come from the downloads.
RELATIONS = [3507503, 3518719, 3898969, 4074850, 4091639, 4129686, 5240045, 7014272, 7030137, 7042792]
URL = "https://api.openstreetmap.org/api/0.6/relation/{id}/full.json"
NAME = re.compile(r"國家(自然)?公園$")
MIN_STEP = 0.0003  # degrees (~30 m): outline points closer than this to the last kept point are dropped


def _file(rel: int) -> str:
    return f"relation_{rel}.json"


def _stitch(ways: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """Join member ways end to end into closed rings; pieces that never close are dropped."""
    ways = [w for w in ways if len(w) >= 2]
    rings = []
    while ways:
        ring = list(ways.pop())
        while ring[0] != ring[-1]:
            for k, w in enumerate(ways):
                if w[0] == ring[-1]:
                    ring.extend(w[1:])
                elif w[-1] == ring[-1]:
                    ring.extend(w[-2::-1])
                else:
                    continue
                ways.pop(k)
                break
            else:
                break
        if ring[0] == ring[-1] and len(ring) >= 4:
            rings.append(ring)
    return rings


def _thin(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out = [ring[0]]
    for p in ring[1:-1]:
        if math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) >= MIN_STEP:
            out.append(p)
    out.append(ring[-1])
    return out if len(out) >= 4 else ring


def _area_centroid(ring: list[tuple[float, float]]) -> tuple[float, float, float]:
    """(signed area, centroid lon, centroid lat) of a closed ring, in degrees (shoelace)."""
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    if not a:
        return 0.0, ring[0][0], ring[0][1]
    return a / 2, cx / (3 * a), cy / (3 * a)


class OsmNationalParks(Source):
    info = SourceInfo(
        id="osm_national_parks",
        title="National park outlines (OpenStreetMap boundary=national_park relations)",
        publisher="OpenStreetMap contributors, via the OpenStreetMap API",
        homepage="https://www.openstreetmap.org/",
        license="Open Database License (ODbL) 1.0, © OpenStreetMap contributors",
        description="Outlines of Taiwan's nine national parks and the Shoushan National Nature Park as mapped in "
        "OpenStreetMap. Used for the hexes each park covers and for its centre point. The National Park Service "
        "publishes each park's plan boundary separately (some as archives a standard-library reader cannot open, "
        "some without a coordinate system), so one consistent open outline is used instead; it is not the legal "
        "boundary.",
        used_for=["National-park wonders: position and protected hexes"],
    )

    def fetch(self, force=False):
        for rel in RELATIONS:
            self.download(URL.format(id=rel), _file(rel), force=force, expect_binary=True)

    def process(self):
        parks = []
        for rel in RELATIONS:
            doc = json.loads((self.raw_dir / _file(rel)).read_text(encoding="utf-8"))
            nodes = {e["id"]: (round(e["lon"], 6), round(e["lat"], 6)) for e in doc["elements"] if e["type"] == "node"}
            ways = {e["id"]: [nodes[n] for n in e["nodes"]] for e in doc["elements"] if e["type"] == "way"}
            el = next(e for e in doc["elements"] if e["type"] == "relation" and e["id"] == rel)
            tags = el.get("tags", {})
            if tags.get("boundary") != "national_park" or not NAME.search(tags.get("name", "")):
                raise ValueError(f"OSM relation {rel} is no longer tagged as a national park: {tags.get('name')!r}")
            by_role: dict[str, list] = {"outer": [], "inner": []}
            for m in el.get("members", []):
                role = m.get("role") or "outer"  # subarea members (the park's zones) are not outline
                if m.get("type") == "way" and m.get("ref") in ways and role in by_role:
                    by_role[role].append(ways[m["ref"]])
            outer, inner = _stitch(by_role["outer"]), _stitch(by_role["inner"])
            if not outer:
                raise ValueError(f"OSM relation {rel} ({tags.get('name')}) has no closed outer ring")
            # Centre: the area-weighted centroid of the outer rings (holes ignored).
            parts = [_area_centroid(r) for r in outer]
            total = sum(abs(a) for a, _, _ in parts)
            lon = sum(abs(a) * x for a, x, _ in parts) / total if total else parts[0][1]
            lat = sum(abs(a) * y for a, _, y in parts) / total if total else parts[0][2]
            parks.append({
                "osm_id": rel, "name": tags.get("name"), "name_en": tags.get("name:en"),
                "wikidata": tags.get("wikidata"), "lon": round(lon, 5), "lat": round(lat, 5),
                "edited": el.get("timestamp", "")[:10] or None, "file": _file(rel),
                "outer_ways": len(by_role["outer"]), "outer_rings": len(outer), "inner_rings": len(inner),
                "rings": [_thin(r) for r in outer + inner],  # even-odd: inner rings are holes
            })
        retrieved = max((m.get("retrieved", "")[:10] for m in fetch.read_manifest(self.id).values()), default="")
        return {
            "vintage": f"OpenStreetMap as retrieved {retrieved}" if retrieved else "OpenStreetMap",
            "_files": [_file(rel) for rel in RELATIONS],
            "osm_base": retrieved or None,
            "parks": sorted(parks, key=lambda p: p["name"] or ""),
        }
