"""OpenStreetMap extracts for Taiwan through the Overpass API: freeways, expressways, provincial highways and
railways as line work; airports and commercial harbours as points; power plants as points.

Two sources share this module so the map's roads do not depend on the power-plant query and vice versa:

* ``osm_tw_transport``: ways tagged highway=motorway|trunk|primary and railway=rail, plus the centre points of
  aerodromes that carry an IATA code and of named landuse=harbour areas.
* ``osm_tw_power``: the centre point and name of every power=plant element. OSM's own capacity tags are never read:
  capacities come from Taipower (see ``taipower.py``), OSM only says where a plant is.

Overpass mirrors are flaky, so each query walks a list of mirrors: a mirror is probed first (its /status page), and a
reply without elements or with a ``remark`` (Overpass answers a server-side timeout with HTTP 200) is discarded.
The manifest records the mirror that answered. The window is the map's (Taiwan, Penghu, Kinmen, Matsu); it also
holds the Fujian coast, which the builders drop (their hexes are foreign land).
"""

from __future__ import annotations

import http.client
import json
import math
import urllib.error
import urllib.parse
from collections import Counter, defaultdict

from ..core import fetch
from ..core.source import Source, SourceInfo

BBOX = "21.6,117.8,26.6,122.4"  # south, west, north, east: the map window of tw_boundaries
MIRRORS = [
    "https://maps.mail.ru/osm/tools/overpass/api",
    "https://overpass.private.coffee/api",
    "https://overpass.kumi.systems/api",
    "https://overpass-api.de/api",
]
PASSES = 2  # times the mirror list is walked before giving up
MIN_STEP = 0.0003  # degrees (~30 m): line points closer than this to the last kept point are dropped

LICENSE = "Open Database License (ODbL) 1.0, © OpenStreetMap contributors"


def overpass(source: Source, query: str, rel_path: str, force: bool = False) -> None:
    """Download one Overpass query to data/raw/<id>/<rel_path>, trying each mirror in turn."""
    if (source.raw_dir / rel_path).exists() and not force:
        return
    data = urllib.parse.quote(query)
    if fetch.OFFLINE:
        source.download(f"{MIRRORS[0]}/interpreter?data={data}", rel_path)  # raises OfflineError
        return
    last: Exception | None = None
    for _ in range(PASSES):
        for base in MIRRORS:
            try:
                if not fetch.url_exists(f"{base}/status", timeout=20):
                    raise RuntimeError("status page did not answer")
                source.download(f"{base}/interpreter?data={data}", rel_path, force=force, expect_binary=True)
                doc = json.loads((source.raw_dir / rel_path).read_text(encoding="utf-8"))
                if doc.get("remark") or not doc.get("elements"):
                    raise ValueError(doc.get("remark") or "no elements")
                return
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, ValueError,
                    KeyError, RuntimeError) as exc:
                print(f"      {base}: {exc}")
                source.discard(rel_path)
                last = exc
    raise RuntimeError(f"no Overpass mirror answered: {last}")


def _load(source: Source, rel_path: str) -> tuple[list[dict], str]:
    doc = json.loads((source.raw_dir / rel_path).read_text(encoding="utf-8"))
    return doc["elements"], doc.get("osm3s", {}).get("timestamp_osm_base", "")


def _point(el: dict) -> tuple[float, float] | None:
    c = el if "lat" in el else el.get("center")
    return (round(c["lon"], 5), round(c["lat"], 5)) if c else None


def stitch(ways: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """Join ways that share an end point into longer lines (either direction). OSM cuts a road into many short
    ways; a builder that straightens a line hex by hex needs the long line."""
    ends = defaultdict(list)
    for k, w in enumerate(ways):
        ends[w[0]].append(k)
        ends[w[-1]].append(k)
    used = [False] * len(ways)

    def grow(line: list[tuple[float, float]]) -> list[tuple[float, float]]:
        while True:
            nxt = next((k for k in ends[line[-1]] if not used[k]), None)
            if nxt is None:
                return line
            used[nxt] = True
            w = ways[nxt]
            line.extend(w[1:] if w[0] == line[-1] else w[-2::-1])

    out = []
    for k, w in enumerate(ways):
        if used[k]:
            continue
        used[k] = True
        line = grow(list(w))
        line.reverse()
        out.append(grow(line))
    return out


def thin(line: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out = [line[0]]
    for p in line[1:-1]:
        if math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) >= MIN_STEP:
            out.append(p)
    out.append(line[-1])
    return out


def _geometry(el: dict) -> list[tuple[float, float]]:
    return [(p["lon"], p["lat"]) for p in el.get("geometry") or [] if p]


def _lines(ways: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    return [[(round(x, 5), round(y, 5)) for x, y in thin(ln)] for ln in stitch([w for w in ways if len(w) >= 2])]


class OsmTwTransport(Source):
    info = SourceInfo(
        id="osm_tw_transport",
        title="Freeways, expressways, provincial highways, railways, airports and harbours (OpenStreetMap)",
        publisher="OpenStreetMap contributors, via the Overpass API",
        homepage="https://www.openstreetmap.org/",
        license=LICENSE,
        description="Line work of Taiwan's national freeways (國道, highway=motorway), expressways (快速公路, "
        "highway=trunk) and provincial highways (省道, highway=primary), and of the railways (railway=rail: Taiwan "
        "Railway and the High Speed Rail), as mapped in OpenStreetMap. Also the centre points of airports with an "
        "IATA code and of named harbour areas, used only to place the airports and ports whose traffic figures "
        "come from the Civil Aviation Administration and Taiwan International Ports. Roads and rail are drawn as "
        "map art between hex centres, not as statistics: OSM carries no traffic counts.",
        used_for=["Freeways, expressways and provincial highways on the map", "Railways on the map",
                  "Positions of airports and commercial ports"],
    )

    QUERIES = {
        "expressways.json": f'[out:json][timeout:120];way["highway"~"^(motorway|trunk)$"]({BBOX});out tags geom;',
        "primary.json": f'[out:json][timeout:120];way["highway"="primary"]({BBOX});out tags geom;',
        "rail.json": f'[out:json][timeout:120];way["railway"="rail"]({BBOX});out tags geom;',
        "sites.json": f'[out:json][timeout:120];(nwr["aeroway"="aerodrome"]["iata"]({BBOX});'
                      f'nwr["landuse"="harbour"]["name"]({BBOX}););out tags center;',
    }

    def fetch(self, force=False):
        for rel, query in self.QUERIES.items():
            overpass(self, query, rel, force)

    def process(self):
        stamps = []
        # Roads: one feature per (class, ref or name), its ways stitched into long lines.
        groups: dict[tuple, list] = defaultdict(list)
        names: dict[tuple, Counter] = defaultdict(Counter)
        for rel in ("expressways.json", "primary.json"):
            els, stamp = _load(self, rel)
            stamps.append(stamp)
            for el in els:
                t = el.get("tags", {})
                geom = _geometry(el)
                if len(geom) < 2:
                    continue
                ref = (t.get("ref") or "").split(";")[0].strip() or None
                key = (t["highway"], ref, None if ref else t.get("name"))
                groups[key].append(geom)
                if t.get("name"):
                    names[key][t["name"]] += len(geom)
        roads = []
        for (highway, ref, name), ways in sorted(groups.items(), key=lambda kv: tuple(str(v) for v in kv[0])):
            common = names[(highway, ref, name)].most_common(1)
            roads.append({"highway": highway, "ref": ref, "name": common[0][0] if common else name,
                          "lines": _lines(ways)})

        # Rail: running lines only (no yards, sidings, spurs or crossovers). OSM names a track after its line,
        # bridge or tunnel, so tracks are grouped only by usage and by high-speed or not.
        els, stamp = _load(self, "rail.json")
        stamps.append(stamp)
        rgroups: dict[tuple, list] = defaultdict(list)
        usage_seen = Counter()
        for el in els:
            t = el.get("tags", {})
            usage_seen[t.get("usage")] += 1
            geom = _geometry(el)
            if len(geom) < 2 or t.get("service") or t.get("usage") not in ("main", "branch"):
                continue
            hsr = t.get("highspeed") == "yes" or any("高鐵" in (t.get(k) or "") or "高速鐵路" in (t.get(k) or "")
                                                     for k in ("name", "ref", "network", "operator"))
            rgroups[(t["usage"], hsr)].append(geom)
        rail = [{"usage": usage, "highspeed": hsr, "lines": _lines(ways)}
                for (usage, hsr), ways in sorted(rgroups.items())]

        els, stamp = _load(self, "sites.json")
        stamps.append(stamp)
        airports, harbours = [], []
        for el in els:
            t = el.get("tags", {})
            pt = _point(el)
            if pt is None:
                continue
            rec = {"osm": f"{el['type']}/{el['id']}", "name": t.get("name"), "name_en": t.get("name:en"),
                   "lon": pt[0], "lat": pt[1]}
            if t.get("aeroway") == "aerodrome" and t.get("iata"):
                airports.append({**rec, "iata": t["iata"], "icao": t.get("icao")})
            elif t.get("landuse") == "harbour" and t.get("name"):
                harbours.append({**rec, "operator": t.get("operator")})
        day = max(s for s in stamps if s)[:10] if any(stamps) else "?"
        print(f"    {len(roads)} road routes ({sum(len(r['lines']) for r in roads)} lines), {len(rail)} rail lines "
              f"({sum(len(r['lines']) for r in rail)} lines; usage tags {dict(usage_seen)}), {len(airports)} IATA "
              f"aerodromes, {len(harbours)} named harbours in the window")
        return {
            "vintage": f"OpenStreetMap, {day}",
            "_files": list(self.QUERIES),
            "roads": roads,
            "rail": rail,
            "airports": airports,
            "harbours": harbours,
        }


class OsmTwPower(Source):
    info = SourceInfo(
        id="osm_tw_power",
        title="Power plant positions (OpenStreetMap power=plant)",
        publisher="OpenStreetMap contributors, via the Overpass API",
        homepage="https://www.openstreetmap.org/",
        license=LICENSE,
        description="Name and centre point of every power=plant element around Taiwan in OpenStreetMap. Taipower "
        "publishes each plant's units and capacity but no coordinates, so OSM says where a plant is and nothing "
        "else: the capacities OSM mappers typed in are not read.",
        used_for=["Positions of the power plants, dams and wind farms on the resources layer"],
    )

    FILE = "plants.json"
    QUERY = f'[out:json][timeout:120];nwr["power"="plant"]({BBOX});out tags center;'

    def fetch(self, force=False):
        overpass(self, self.QUERY, self.FILE, force)

    def process(self):
        els, stamp = _load(self, self.FILE)
        plants = []
        for el in els:
            t = el.get("tags", {})
            pt = _point(el)
            if pt is None or not (t.get("name") or t.get("name:en")):
                continue
            plants.append({"osm": f"{el['type']}/{el['id']}", "name": t.get("name"), "name_en": t.get("name:en"),
                           "source": t.get("plant:source"), "operator": t.get("operator"),
                           "lon": pt[0], "lat": pt[1]})
        print(f"    {len(plants)} named power plants in the window (of {len(els)} elements)")
        return {"vintage": f"OpenStreetMap, {stamp[:10] or '?'}", "_files": [self.FILE], "plants": plants}
