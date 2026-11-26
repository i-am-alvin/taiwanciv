"""Wonders: national parks, research universities and national monuments, each picked by a published rule.

* national_park: every national park and the national nature park on the map, ranked by visits counted at their
  recreation sites (Ministry of the Interior statistics, latest complete year).
* research_university: the universities that received the most project funding from all sponsors (Ministry of
  Education disclosure platform, table 研1), at most two per county.
* landmark: one national monument (國定古蹟) per county that has one, hand-picked from the Bureau of Cultural
  Heritage register and marked curated; positions and designation years come from the register.

The US build's `park_unit` rule (other National Park Service units) has no Taiwanese counterpart and is left out.
Money is New Taiwan dollars: `metrics.rd_usd` / `federal_usd` keep the contract's field names but hold TWD.

Writes web/data/wonders.json (loaded eagerly; a few tens of kB).
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from ..core.geo import MapProjection, Shape, ShapeIndex
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, write_web

REQUIRES = ["_world", "tw_boundaries", "moi_national_parks", "osm_national_parks", "moe_universities",
            "wikidata_universities", "boch_monuments"]
PRODUCES = ["wonders.json"]

N_UNIVERSITIES, PER_COUNTY = 15, 2
MAX_OFFSET_KM = 2.0  # a university's Wikidata point must lie within one hex radius of its registered township

# Curated landmarks: WHICH national monuments appear (Bureau of Cultural Heritage caseId; the comment is only a
# reading aid). One per county that has a national monument (Yilan, Hualien and Taitung have none). Names,
# positions and designation dates are read from the register, never typed here.
LANDMARKS = [
    "19980730000001",  # 臺北市 總統府
    "19831228000002",  # 新北市 淡水紅毛城
    "19831228000001",  # 基隆市 二沙灣砲台
    "19850819000052",  # 桃園市 李騰芳古宅
    "19980623000001",  # 新竹市 新竹火車站
    "19831228000003",  # 新竹縣 金廣福公館
    "19850819000059",  # 苗栗縣 鄭崇和墓
    "19950422000002",  # 臺中市 臺中火車站
    "19831228000005",  # 彰化縣 鹿港龍山寺
    "19870417000001",  # 南投縣 八通關古道
    "19851127000036",  # 雲林縣 北港朝天宮
    "20050526000001",  # 嘉義市 嘉義舊監獄
    "19831228000006",  # 嘉義縣 王得祿墓
    "19831228000008",  # 臺南市 赤嵌樓
    "19850819000083",  # 高雄市 鳳山縣舊城
    "20240318000001",  # 屏東縣 鵝鑾鼻燈塔
    "19831228000013",  # 澎湖縣 澎湖天后宮
    "19850819000092",  # 金門縣 邱良功母節孝坊
    "20160601000001",  # 連江縣 東湧燈塔 (the other one, 東犬燈塔, stands on an island with no land hex)
]
REGISTER_PREFIXES = ("國定古蹟-", "國定古蹟")  # some register names repeat the class in front of the name
PARK_KINDS = ["natural"]
UNIT_TYPE = {False: "國家公園", True: "國家自然公園"}


# --- geography ------------------------------------------------------------------------------


def _d2(a, b) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _seg_dist(p, a, b) -> float:
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    t = 0.0 if not (dx or dy) else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


class Locator:
    """lon/lat → (x, y, Taiwanese land cell) and map units → township (TOWNCODE) / county (COUNTYCODE)."""

    def __init__(self, world: dict, bounds: dict):
        self.world = world
        self.proj = MapProjection(**world["projection"])
        self.grid = HexGrid(**world["grid"])
        self.owner = world["owner"]
        self.town_set = set(world["counties"])
        self.county_of = {t["geoid"]: t["state_fips"] for t in bounds["counties"]}
        self.county_name = {s["fips"]: s["name"] for s in bounds["states"]}
        self.town_ids, shapes = [], []
        for t in bounds["counties"]:
            if t["geoid"] in self.town_set:
                self.town_ids.append(t["geoid"])
                shapes.append(Shape([[self.proj(lon, lat) for lon, lat in ring] for ring in t["rings"]]))
        self.town_shape = dict(zip(self.town_ids, shapes))
        self.town_index = ShapeIndex(shapes, 100.0)

    def land_cell(self, x: float, y: float, rings: int = 1) -> int:
        """The Taiwanese land cell at x/y, else the nearest one within `rings` rings; -1 if none."""
        cell = self.grid.cell_at(x, y)
        if cell < 0:
            return -1
        if self.owner[cell] >= 0:
            return cell
        seen, frontier = {cell}, [cell]
        for _ in range(rings):
            ring = [n for c in frontier for n in self.grid.neighbours(c) if n not in seen]
            seen.update(ring)
            land = [n for n in ring if self.owner[n] >= 0]
            if land:
                return min(land, key=lambda n: _d2(self.grid.center(*self.grid.col_row(n)), (x, y)))
            frontier = ring
        return -1

    def town_at(self, x: float, y: float, cell: int | None = None) -> str | None:
        k = self.town_index.locate(x, y)
        if k >= 0:
            return self.town_ids[k]
        if cell is not None and cell >= 0 and self.world["county"][cell] >= 0:  # just offshore: the hex's township
            return self.world["counties"][self.world["county"][cell]]
        return None

    def town_distance_km(self, geoid: str, x: float, y: float) -> float | None:
        """Real km from a map point to a township's outline (0 inside it)."""
        s = self.town_shape.get(geoid)
        if s is None:
            return None
        if s.contains(x, y):
            return 0.0
        d = min(_seg_dist((x, y), a, b) for r in s.rings for a, b in zip(r, r[1:] + r[:1]))
        return self.proj.km(d)

    def covered_cells(self, shape: Shape) -> list[int]:
        """Taiwanese land cells whose centre lies inside the shape."""
        g, out = self.grid, []
        x0, y0, x1, y1 = shape.bbox
        dy = 1.5 * g.radius
        for row in range(max(0, int(y0 / dy) - 1), min(g.rows, int(y1 / dy) + 2)):
            for col in range(g.cols):
                cx, cy = g.center(col, row)
                if x0 <= cx <= x1 and y0 <= cy <= y1 and shape.contains(cx, cy):
                    idx = g.index(col, row)
                    if self.owner[idx] >= 0:
                        out.append(idx)
        return sorted(out)

    def settle(self, x: float, y: float, cell: int) -> tuple[float, float]:
        """Rounded x/y, moved to the cell centre when the point is not inside its cell (snapped offshore sites)."""
        x, y = round(x, 1), round(y, 1)
        if self.grid.cell_at(x, y) != cell:
            x, y = (round(v, 1) for v in self.grid.center(*self.grid.col_row(cell)))
        return x, y

    def position(self, x: float, y: float, cell: int, town: str | None = None) -> dict | None:
        """The wonder's place fields. `town`: the township the publisher files the site under (wins when on the map)."""
        if cell < 0:
            return None
        if town not in self.town_set:
            town = self.town_at(x, y, cell)
        state = self.county_of.get(town) if town else self.world["states"][self.owner[cell]]
        xs, ys = self.settle(x, y, cell)
        # `cbsa` is the city unit, which in Taiwan is the county itself (docs/PORTING.md).
        return {"x": xs, "y": ys, "cell": cell, "county": town, "cbsa": state, "state": state}

    def place(self, lon: float, lat: float, rings: int = 2, town: str | None = None) -> dict | None:
        x, y = self.proj(lon, lat)
        return self.position(x, y, self.land_cell(x, y, rings), town)


# --- rules ----------------------------------------------------------------------------------


def _rules(parks_year: int, n_parks: int, off_map: list[str], no_land: list[str], funding_year: int,
           enrol_year: int, n_national: int, no_monument: list[str]) -> list[dict]:
    off = f"{'、'.join(off_map)}位於地圖範圍之外，" if off_map else ""
    off += f"{'、'.join(no_land)}在地圖範圍內，但園區輪廓內與中心點周圍兩格內都沒有陸地六角格可標示，" if no_land else ""
    off += "未列入，但其人次仍計入全國合計。" if off else ""
    none = f"（{'、'.join(no_monument)}沒有國定古蹟）" if no_monument else ""
    return [
        {"id": "national_park", "name": "國家公園", "kind": "natural", "kinds": PARK_KINDS, "year": parks_year,
         "text": f"地圖上的每一座國家公園與國家自然公園（共 {n_parks} 處），依 {parks_year} 年各遊憩據點的遊客人次排名"
                 f"（內政部統計處「國家(自然)公園遊憩據點遊客人次」）。{off}人次是各管理處所報據點的計數，不是不重複的"
                 "遊客數，各園區納入統計的據點數也不同。面積為同一統計的陸域加海域面積；圖上標示的保護範圍依 "
                 "OpenStreetMap 的園區輪廓，並非法定計畫範圍。跨縣市的園區只標在一處：標記放在輪廓中心點（中心點不在園區"
                 "所占的六角格內時，改放最近的一格），所屬縣市與鄉鎮市區取該點所在的行政區。"},
        {"id": "research_university", "name": "大學（承接計畫經費）", "kind": "university", "year": funding_year,
         "text": f"{funding_year} 年承接各類計畫經費最多的 {N_UNIVERSITIES} 所大學：經費來自政府、企業與其他單位，含學術"
                 "研究、產學合作及其他委辦計畫（教育部大專校院校務資訊公開平臺 研1「學校承接各單位資助各類計畫經費」），"
                 f"每個縣市至多 {PER_COUNTY} 所。金額為新臺幣，並列出其中政府部門資助的部分。這是各校填報的承接經費，"
                 "不是研發支出調查；臺灣沒有類似美國卡內基分類的研究型大學名單。"
                 f"學生數為 {enrol_year} 年 10 月 15 日具正式學籍的在學學生（各學制合計）。位置取 Wikidata 座標中最接近"
                 f"登記校址所在鄉鎮市區者（距該鄉鎮市區 {MAX_OFFSET_KM:g} 公里以內）；所屬鄉鎮市區以登記校址為準。"},
        {"id": "landmark", "name": "國定古蹟", "kind": "landmark", "curated": True,
         "text": f"由本專案人工挑選，不依任何數據排名：文化部文化資產局古蹟名錄 {n_national} 處國定古蹟中的 "
                 f"{len(LANDMARKS)} 處，有國定古蹟的縣市各選一處{none}。名稱、位置與指定年份皆取自名錄；年份為名錄所列"
                 "最早一次「指定/登錄」公告的年份。依指定先後排列，不代表重要性。"},
    ]


# --- parks ----------------------------------------------------------------------------------


def parks(loc: Locator, moi: dict, osm: dict):
    outlines = {p["name"]: p for p in osm["parks"]}
    out, off_map, no_land, no_outline = [], [], [], []
    rank = 0
    for p in moi["parks"]:  # most visits first
        if not p["visits"]:
            continue
        o = outlines.get(p["name"])
        if o is None:
            no_outline.append(p["name"])
            continue
        shape = Shape([[loc.proj(lon, lat) for lon, lat in r] for r in o["rings"]])
        cells = loc.covered_cells(shape)
        x, y = loc.proj(o["lon"], o["lat"])
        if cells:
            # The outline's centre, or the covered hex nearest to it when the centre is at sea or in a hole.
            cell = loc.grid.cell_at(x, y)
            if cell not in cells:
                cell = min(cells, key=lambda c: _d2(loc.grid.center(*loc.grid.col_row(c)), (x, y)))
        else:
            cell = loc.land_cell(x, y, 2)
        pos = loc.position(x, y, cell)
        if not pos:  # outside the map window, or inside it with no land hex within two rings of the centre
            (off_map if loc.grid.cell_at(x, y) < 0 else no_land).append(p["name"])
            continue
        rank += 1
        out.append({"id": f"np-{o['osm_id']}", "name": p["name"], "name_en": o.get("name_en"), "short": p["label"].split("(")[0],
                    "kind": "natural", "rule": "national_park", "rank": rank,
                    "metrics": {"visits": p["visits"], "year": moi["year"], "area_km2": p["area_km2"],
                                "land_km2": p["land_km2"], "sea_km2": p["sea_km2"], "sites": p["sites"],
                                "unit_type": UNIT_TYPE[bool(p["nature_park"])]},
                    **pos, "cells": cells or None, "curated": False})
    return out, off_map, no_land, no_outline


# --- universities ---------------------------------------------------------------------------


def _norm(name: str) -> str:
    return "".join((name or "").split()).replace("台", "臺")


def _plain_name(name: str) -> str:
    """'淡江大學學校財團法人淡江大學' → '淡江大學' (private schools are registered with their foundation in front)."""
    return name.split("財團法人")[-1]


def _short_univ(name: str) -> str:
    plain = _plain_name(name)
    return plain[2:] if plain.startswith("國立") else plain


def universities(loc: Locator, moe: dict, wd: dict):
    by_name: dict[str, dict] = {}
    for it in wd["institutions"]:
        for n in it["names"]:
            by_name.setdefault(_norm(n), it)
    out, per_county, capped, unplaced = [], Counter(), [], []
    rank = 0
    for u in moe["institutions"]:  # most project funding first
        if rank == N_UNIVERSITIES:
            break
        if not u["funding_twd"]:
            continue
        if u["county"] and per_county[u["county"]] >= PER_COUNTY:
            capped.append(u["name"])
            continue
        it = by_name.get(_norm(u["name"])) or by_name.get(_norm(_plain_name(u["name"])))
        best = None
        if it and u["town"] in loc.town_set:
            for lon, lat in it["coords"]:
                x, y = loc.proj(lon, lat)
                d = loc.town_distance_km(u["town"], x, y)
                if d is not None and d <= MAX_OFFSET_KM and (best is None or d < best[0]):
                    best = (d, x, y)
        pos = loc.position(best[1], best[2], loc.land_cell(best[1], best[2], 1), u["town"]) if best else None
        if not pos:
            unplaced.append(u["name"])
            continue
        per_county[u["county"]] += 1
        rank += 1
        gov = u["government_twd"]
        out.append({"id": f"univ-{u['code']}", "name": _plain_name(u["name"]), "name_en": it.get("name_en"),
                    "short": _short_univ(u["name"]), "kind": "university", "rule": "research_university", "rank": rank,
                    "metrics": {"rd_usd": round(u["funding_twd"]), "federal_usd": round(gov) if gov else None,
                                "business_twd": round(u["business_twd"]) if u["business_twd"] else None,
                                "year": moe["year"], "enrollment": u["enrollment"],
                                "enrollment_year": moe["enrollment_year"], "teachers": u["teachers"],
                                "r1": None, "med_school": None, "wikidata": it["qid"]},
                    **pos, "cells": None, "curated": False})
    return out, capped, unplaced


# --- landmarks ------------------------------------------------------------------------------


def _monument_name(name: str) -> str:
    for p in REGISTER_PREFIXES:
        if name.startswith(p):
            return name[len(p):]
    return name


def _short_monument(name: str) -> str:
    for ch in "(（〈—":
        name = name.split(ch)[0]
    return name


def landmarks(loc: Locator, register: dict):
    by_id = {m["case_id"]: m for m in register["monuments"]}
    picked, missing = [], []
    for case_id in LANDMARKS:
        m = by_id.get(case_id)
        pos = loc.place(m["lon"], m["lat"]) if m and m["lon"] is not None and m["lat"] is not None else None
        if not pos:
            missing.append(case_id)
            continue
        name = _monument_name(m["name"])
        picked.append({"id": f"boch-{case_id}", "name": name, "name_en": None,  # the register has no English name
                       "short": _short_monument(name), "kind": "landmark",
                       "rule": "landmark", "rank": None,
                       "metrics": {"designated": int(m["designated"][:4]) if m["designated"] else None,
                                   "designated_date": m["designated"], "nhl_ref": case_id, "class": "國定古蹟",
                                   "types": m["types"]},
                       **pos, "cells": None, "curated": True, "listed_as": m["name"]})
    picked.sort(key=lambda w: (w["metrics"]["designated_date"] or "9999", w["id"]))
    for k, w in enumerate(picked, 1):
        w["rank"] = k
    return picked, missing


def _counties_without_monument(loc: Locator, register: dict) -> list[str]:
    """Names of the counties on the map in which no national monument of the register stands."""
    have = set()
    for m in register["monuments"]:
        pos = loc.place(m["lon"], m["lat"]) if m["lon"] is not None and m["lat"] is not None else None
        if pos:
            have.add(pos["state"])
    return [loc.county_name[c] for c in loc.world["states"] if c not in have]


# --- build ----------------------------------------------------------------------------------


def build() -> None:
    world = load_interim("_world")
    loc = Locator(world, load_interim("tw_boundaries"))
    moi_p, osm_p, moe_p, wd_p, boch_p = (load_interim_payload(n) for n in REQUIRES[2:])
    moi, moe, register = moi_p["data"], moe_p["data"], boch_p["data"]

    w, off_map, no_land, no_outline = parks(loc, moi, osm_p["data"])
    unis, capped, unplaced = universities(loc, moe, wd_p["data"])
    w += unis
    lm, missing = landmarks(loc, register)
    w += lm
    doc = {
        "version": 1,
        "vintage": {"parks": moi_p.get("vintage"), "boundaries": osm_p.get("vintage"),
                    "universities": f"{moe_p.get('vintage')}; positions: {wd_p.get('vintage')}",
                    "landmarks": boch_p.get("vintage")},
        "sources": REQUIRES[2:],
        "currency": "TWD",
        "rules": _rules(moi["year"], sum(1 for x in w if x["rule"] == "national_park"), off_map, no_land, moe["year"],
                        moe["enrollment_year"], len(register["monuments"]), _counties_without_monument(loc, register)),
        # park_visits: every national (nature) park, including any left off the map. r1_universities: no such
        # classification exists in Taiwan (null).
        "national": {"park_visits": (moi["total"] or {}).get("visits"), "park_visits_year": moi["year"],
                     "r1_universities": None, "national_monuments": len(register["monuments"]),
                     "universities_reporting": sum(1 for u in moe["institutions"] if u["funding_twd"])},
        "wonders": w,
    }
    write_web("wonders.json", doc)
    kinds = Counter(x["rule"] for x in w)
    print(f"    {len(w)} wonders: {dict(kinds)}; parks off the map: {off_map}; parks with no land hex: {no_land}; parks without an outline: {no_outline}; "
          f"universities skipped by the per-county cap: {capped}; universities without a usable point: {unplaced}"
          + (f"; landmarks not found: {missing}" if missing else ""))


# --- check --------------------------------------------------------------------------------

KINDS = {"natural", "recreation", "coastal", "monument", "university", "landmark"}


def _load(web_dir, name: str):
    p = Path(web_dir) / name
    return json.loads(p.read_text()) if p.exists() else None


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check(web_dir) -> list[tuple[str, str]]:
    path = Path(web_dir) / "wonders.json"
    if not path.exists():
        return [("NOTE", "wonders.json not built (optional)")]
    d = json.loads(path.read_text())
    world = _load(web_dir, "world.json") or {}
    cities = _load(web_dir, "cities.json") or []
    g = world.get("grid") or {}
    n_cells = (g.get("cols") or 0) * (g.get("rows") or 0)
    owner = world.get("owner") or []
    counties = {c["geoid"] for c in world.get("counties") or []}
    states = {s["fips"] for s in world.get("states") or []}
    city_ids = {c["id"] for c in cities}

    def cell_ok(c):
        return isinstance(c, int) and not isinstance(c, bool) and (not n_cells or 0 <= c < n_cells) and \
            (not owner or (c < len(owner) and owner[c] >= 0))

    bad = []
    if d.get("version") != 1:
        bad.append("version must be 1")
    if not isinstance(d.get("sources"), list) or not d.get("sources"):
        bad.append("sources must be a non-empty list")
    rules = {r.get("id"): r for r in d.get("rules") or []}
    if not rules or not all(isinstance(r.get("text"), str) and r.get("kind") in KINDS
                            and set(r.get("kinds") or [r.get("kind")]) <= KINDS for r in rules.values()):
        bad.append("rules must each have an id, a kind (and optional kinds) and text")
    ids, ranks = set(), Counter()
    for x in d.get("wonders") or []:
        tag = f"wonder {x.get('id')!r}"
        if not isinstance(x.get("id"), str) or x["id"] in ids:
            bad.append(f"{tag}: missing or duplicate id")
        ids.add(x.get("id"))
        r = rules.get(x.get("rule"))
        if r is None or x.get("kind") not in (r.get("kinds") or [r.get("kind")]):
            bad.append(f"{tag}: unknown rule or kind not allowed by its rule")
        if not isinstance(x.get("rank"), int) or x["rank"] < 1:
            bad.append(f"{tag}: rank must be an int >= 1")
        ranks[(x.get("rule"), x.get("rank"))] += 1
        if not isinstance(x.get("name"), str) or not isinstance(x.get("short"), str):
            bad.append(f"{tag}: name/short missing")
        if not isinstance(x.get("metrics"), dict):
            bad.append(f"{tag}: metrics must be an object")
        if not cell_ok(x.get("cell")) or not _is_num(x.get("x")) or not _is_num(x.get("y")):
            bad.append(f"{tag}: bad cell/x/y")
        if x.get("cells") is not None and (not x["cells"] or not all(cell_ok(c) for c in x["cells"])):
            bad.append(f"{tag}: cells must be null or a non-empty list of Taiwanese land cells")
        if x.get("county") is not None and counties and x["county"] not in counties:
            bad.append(f"{tag}: county is not a TOWNCODE of world.json")
        if x.get("state") is not None and states and x["state"] not in states:
            bad.append(f"{tag}: state is not a COUNTYCODE of world.json")
        if x.get("cbsa") is not None and city_ids and x["cbsa"] not in city_ids:
            bad.append(f"{tag}: cbsa not in cities.json")
        if not isinstance(x.get("curated"), bool) or x.get("curated") != bool(rules.get(x.get("rule"), {}).get("curated")):
            bad.append(f"{tag}: curated must match its rule")
        m = x.get("metrics") or {}
        for k in ("visits", "rd_usd", "federal_usd", "enrollment"):
            if m.get(k) is not None and not (_is_num(m[k]) and m[k] > 0):
                bad.append(f"{tag}: metrics.{k} must be > 0 or null")
    dup = [k for k, v in ranks.items() if v > 1]
    if dup:
        bad.append(f"duplicate ranks within a rule: {dup[:3]}")
    out = [("FAIL", f"wonders.json: {m}") for m in bad[:12]]
    if len(bad) > 12:
        out.append(("FAIL", f"wonders.json: … and {len(bad) - 12} more problems"))
    size = path.stat().st_size
    out.append(("WARN" if size > 300_000 else "PASS", f"wonders.json {size / 1e3:.0f} kB (eager budget ~300 kB)"))
    n = len(d.get("wonders") or [])
    by_rule = Counter(x.get("rule") for x in d.get("wonders") or [])
    if not bad:
        out.append(("PASS", f"wonders.json: {n} wonders ({', '.join(f'{v} {k}' for k, v in by_rule.items())})"))
    if not 30 <= n <= 60:
        out.append(("WARN", f"wonders.json: {n} wonders (expected about 30-60)"))
    return out
