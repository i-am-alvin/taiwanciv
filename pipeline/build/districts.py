"""Districts: real industry specialisation of each city (縣市) as strategy-game districts.

The only county × industry employment Taiwan publishes every year is the Manpower Survey's table 33 (dgbas_labor):
employed people in the 19 sections of the Standard Industrial Classification, in thousands rounded to the nearest
thousand, counted **where people live** (not where the employer is). That cannot reproduce the original's 4-digit
catalog, so a district of the original is kept only where a whole section maps onto it, districts have no
specialities (`sub` is empty, the `sub*` fields are null), and there is no pay, no year-on-year change and no
township level (`avg_pay`, `oty_pct` null; top-level `counties` null). Aerodrome and Encampment have no section of
their own and are left out. Kinmen and Lienchiang are not in the survey: their entry is null.

Location quotient (LQ) = (city's employed in the district's sections ÷ city's employed in all industries) ÷ (the
same ratio for the Taiwan area, the survey's national total).

The rule (published in the file as `rule`):
* A district **appears** when its LQ is at least MIN_LQ, its sections add up to at least MIN_JOBS employed people,
  and none of its section cells is under MIN_CELL (a cell of 0-2 thousand is mostly rounding).
* Districts are ranked by strength = people above the national norm (emp - emp / LQ); up to MAX_PER_CITY are kept.
  The harbour district also needs a footprint hex on or next to water, or on a mapped river.
* The city type `badge` comes from the strongest district, unless another listed district is extreme (LQ >= BADGE_LQ
  and >= BADGE_SHARE of the city's employed), in which case the strongest such district wins. A Government plaza
  badge in the national capital (cities.json `capital`) is labelled as the capital. The original's 'Seat of
  government' label is not used: every 縣市 is the seat of its own government. No district → no badge.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, load_interim_payload, write_web

REQUIRES = ["dgbas_labor", "_world", "cities.json", "world.json"]
PRODUCES = ["districts.json"]

MIN_LQ = 1.25
MIN_JOBS = 10_000   # a district's sections together
MIN_CELL = 3_000    # every section cell of a district (and every row of `top`): the survey rounds to the thousand
MAX_PER_CITY = 5
TOP_INDUSTRIES = 8
BADGE_LQ = 6.0
BADGE_SHARE = 0.03
BASIS = "labor_survey"

RULE_TEXT = (
    f"特色區域依人力資源調查的行業別就業人數選出：就業者依「居住」縣市計（不是依工作地點），縣市數字只公布到千人。"
    f"區位商數＝本縣市就業者在該區域所含行業的占比 ÷ 臺灣地區的同一占比。"
    f"一個特色區域必須同時符合三個條件才會出現：區位商數至少 {MIN_LQ:g}；所含行業合計至少 {MIN_JOBS:,} 人；"
    f"而且所含的每一個行業都至少 {MIN_CELL:,} 人（不足 {MIN_CELL // 1000} 千人的格子多半是取整誤差；"
    f"「最專精的產業」表也只列至少 {MIN_CELL:,} 人的行業，最多 {TOP_INDUSTRIES} 個）。"
    f"特色區域依「高於全國水準的就業人數」（就業人數 − 就業人數 ÷ 區位商數）排序，每個縣市最多 {MAX_PER_CITY} 個。"
    f"港埠運輸區另外要求轄區內有臨水、或有河流通過的六角格。"
    f"城市類型以最強的特色區域命名；若另有特色區域的區位商數至少 {BADGE_LQ:g} 且占本縣市就業至少 {BADGE_SHARE:.0%}，"
    f"則以其中最強者命名。政府廣場為最強區域的中央政府所在地稱為「首都」；每個縣市都是自己的縣市政府所在地，"
    f"所以不另設「政府所在地」稱號。調查只有 19 個行業大類，因此沒有更細的專業項目，也沒有薪資與年增率；"
    f"調查範圍不含金門縣與連江縣，這兩縣沒有特色區域與城市類型。"
)
NOTE = (
    "金門縣與連江縣不在人力資源調查的範圍內，沒有行業別就業人數，因此沒有特色區域，也沒有城市類型。"
    "其他縣市的數字是住在該縣市的就業者，跨縣市通勤者算在居住地。"
)
COUNTY_NOTE = "人力資源調查沒有鄉鎮市區的行業別就業人數，因此沒有鄉鎮市區層級的特色區域。"


def _d(id, name, color, sections, badge, description, caveat=None):
    """A district: `sections` = the dgbas_labor section keys it adds up (in the contract's `naics` field)."""
    return {
        "id": id, "name": name, "icon": "d-" + id.replace("_", "-"), "color": color, "naics": sections, "own": [],
        "sub": {}, "badge": {"id": badge[0], "label": badge[1], "labels": {}},
        "description": description, "caveat": caveat,
    }


# The original's ids, icons and colours, in the original's order, for the districts a whole section maps onto.
CATALOG = [
    _d("campus", "學院", "#4a7bd0", ["professional", "information"], ("scientific", "知識城市"),
       "知識與科技：專業、科學及技術服務業（研發、設計、法律、會計、顧問）與出版影音及資通訊業（軟體、電信、資料處理、出版傳播）。",
       "不含大專校院：教育業涵蓋各級學校與補習班，無法單獨分出大學。"),
    _d("commercial_hub", "商業中心", "#d0a23a", ["finance"], ("commercial", "金融城市"),
       "金融及保險業：銀行、證券期貨、保險。"),
    _d("industrial_zone", "工業區", "#c2643a", ["manufacturing"], ("industrial", "工業城市"),
       "製造業。", "不含礦業及土石採取業：每個所含行業都必須達到最低人數，把它併入會讓這個區域在該行業人數很少的縣市無法成立。"),
    _d("harbor", "港埠運輸區", "#2f8fb0", ["transportation"], ("maritime", "港埠運輸城市"),
       "運輸及倉儲業：海運與港埠、陸上運輸、航空、倉儲、郵政及快遞。",
       "這是運輸及倉儲業的整體，無法單獨分出港埠（例如機場所在的縣市也會偏高）；只有轄區臨水或有河流通過的縣市才會出現。"),
    _d("theater_square", "藝文休閒區", "#a15bc4", ["arts"], ("cultural", "藝文城市"),
       "藝術、娛樂及休閒服務業：表演藝術、博物館、運動、遊樂與休閒場所。",
       "影視、廣播與出版屬於出版影音及資通訊業，不在此列。"),
    _d("entertainment_complex", "餐旅區", "#d0508a", ["accommodation"], ("entertainment", "餐旅城市"),
       "住宿及餐飲業：旅館、民宿、餐廳、飲料店。", "這是住宿與餐飲的合計，數字本身分不出旅館與餐飲。"),
    _d("government_plaza", "政府廣場", "#8a9a5b", ["public_admin"], ("governmental", "公務城市"),
       "公共行政及國防；強制性社會安全：中央與地方政府機關、國防事務、社會保險機構。",
       "含各縣市都有的地方政府；公立學校與公立醫院分屬教育業與醫療保健業。人力資源調查不含現役軍人。"),
    _d("aqueduct", "水電公用事業", "#3aa0a0", ["power", "water"], ("utility", "公用事業城市"),
       "電力及燃氣供應業與用水供應及污染整治業：發電、輸配電、瓦斯、自來水、污水與廢棄物處理。",
       "用水供應及污染整治業也包含廢棄物清除處理與資源回收，無法單獨分出自來水。"),
]
BY_ID = {d["id"]: d for d in CATALOG}
IDS = [d["id"] for d in CATALOG]
CAPITAL_LABEL = "首都"


def _r(x, nd=3):
    return None if x is None else round(x, nd)


def lq(emp, total, nat_emp, nat_total):
    if emp is None or not total or not nat_emp or not nat_total:
        return None
    return (emp / total) / (nat_emp / nat_total)


def excess(emp, q) -> float:
    """People above the national norm: emp - emp / LQ (0 when LQ <= 1)."""
    return emp * (1 - 1 / q) if emp and q and q > 1 else 0.0


def section_sum(jobs: dict, sections: list[str]) -> int | None:
    """Employed people in the sections together; None when the survey has no figure for one of them."""
    vals = [jobs.get(s) for s in sections]
    return None if any(v is None for v in vals) else sum(vals)


def evaluate(rec: dict, nation: dict, wet: bool = True) -> list[dict]:
    """Every district that passes the rule for one county's dgbas_labor record, strongest first."""
    out = []
    total, jobs = rec.get("employed"), rec.get("jobs") or {}
    if not total:
        return out
    for d in CATALOG:
        if d["id"] == "harbor" and not wet:
            continue
        emp = section_sum(jobs, d["naics"])
        if emp is None or emp < MIN_JOBS or any(jobs[s] < MIN_CELL for s in d["naics"]):
            continue
        dlq = lq(emp, total, section_sum(nation["jobs"], d["naics"]), nation["employed"])
        if dlq is None or dlq < MIN_LQ:
            continue
        out.append({
            "id": d["id"], "lq": _r(dlq, 2), "emp": emp, "share": _r(emp / total, 4), "avg_pay": None,
            "sub": None, "sub_lq": None, "sub_emp": None, "sub_lower_bound": None,
            "via": "broad", "strength": round(excess(emp, dlq)),
            "suppressed": 0, "lower_bound": False,
        })
    out.sort(key=lambda r: -r["strength"])
    return out[:MAX_PER_CITY]


def top_industries(rec: dict, nation: dict) -> list[dict]:
    """The sections with the highest LQ (cells of at least MIN_CELL only)."""
    top = []
    total = rec.get("employed")
    for key, emp in (rec.get("jobs") or {}).items():
        if emp is None or emp < MIN_CELL:
            continue
        q = lq(emp, total, nation["jobs"].get(key), nation["employed"])
        if q is None:
            continue
        top.append({"naics": key, "emp": emp, "lq": _r(q, 2), "avg_pay": None, "oty_pct": None,
                    "suppressed": 0, "lower_bound": False})
    top.sort(key=lambda r: -r["lq"])
    return top[:TOP_INDUSTRIES]


def badge_district(dists: list[dict]) -> dict | None:
    """The district the city type is named after: the strongest, unless a listed district is extreme."""
    if not dists:
        return None
    extreme = [d for d in dists if d["lq"] is not None and d["lq"] >= BADGE_LQ and (d["share"] or 0) >= BADGE_SHARE]
    return max(extreme, key=lambda d: d["strength"]) if extreme else dists[0]


def badge_for(best: dict | None, capital: bool = False) -> dict | None:
    if not best:
        return None
    d = BY_ID[best["id"]]
    label = CAPITAL_LABEL if capital and d["id"] == "government_plaza" else d["badge"]["label"]
    return {"id": d["badge"]["id"], "label": label, "district": d["id"],
            "text": f"{d['name']}：就業占比為全國的 {best['lq']:.1f} 倍", "basis": BASIS}


def wet_cities(cities: list[dict], world_i: dict, world: dict) -> set[str]:
    """Ids of cities with a footprint hex on or next to water, or on a mapped river."""
    grid = HexGrid(**world_i["grid"])
    water = world_i["water"]
    river_cells = set()
    for r in world.get("rivers") or []:
        pts = r.get("pts") or []
        for i in range(0, len(pts) - 2, 2):
            x0, y0, x1, y1 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
            n = max(1, int(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 / 4))
            for k in range(n + 1):
                c = grid.cell_at(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n)
                if c is not None and 0 <= c < len(water):
                    river_cells.add(c)
    out = set()
    for c in cities:
        cells = c.get("footprint") or ([c["cell"]] if c.get("cell") is not None else [])
        for cell in cells:
            if cell in river_cells or any(water[n] > 0 for n in [cell, *grid.neighbours(cell)]):
                out.add(c["id"])
                break
    return out


def build() -> None:
    payload = load_interim_payload("dgbas_labor")
    q = payload["data"]
    world_i = load_interim("_world")
    cities = json.loads((WEB_DATA / "cities.json").read_text())
    world = json.loads((WEB_DATA / "world.json").read_text())
    nation = q["nation"]
    wet = wet_cities(cities, world_i, world)

    industries = {key: {"title": s["zh"], "us_emp": nation["jobs"].get(key)} for key, s in q["sections"].items()}
    missing = [s for d in CATALOG for s in d["naics"] if s not in industries]
    if missing:
        raise ValueError(f"dgbas_labor has no section {missing}")

    out_cities: dict[str, dict | None] = {}
    for c in cities:
        rec = q["counties"].get(c["id"])
        if not rec or not rec.get("employed"):
            out_cities[c["id"]] = None  # Kinmen, Lienchiang: not in the survey
            continue
        dists = evaluate(rec, nation, c["id"] in wet)
        out_cities[c["id"]] = {
            "emp": rec["employed"], "avg_pay": None,
            "counties": None,  # the survey is by county: nothing is summed from townships
            "top": top_industries(rec, nation),
            "districts": dists,
            "badge": badge_for(badge_district(dists), bool(c.get("capital"))),
        }

    doc = {
        "version": 1,
        "vintage": f"人力資源調查 {q['year']} 年平均（主計總處，年報表 33），依居住縣市計",
        "year": q["year"],
        "sources": ["dgbas_labor"],
        "rule": {"min_lq": MIN_LQ, "min_jobs": MIN_JOBS, "min_cell": MIN_CELL, "min_share": None,
                 "specialty_lq": None, "specialty_jobs": None, "specialty_share": None,
                 "max_per_city": MAX_PER_CITY, "harbor_needs_water": True, "badge_lq": BADGE_LQ,
                 "badge_share": BADGE_SHARE, "college_share": None, "text": RULE_TEXT,
                 "county_note": COUNTY_NOTE},
        "note": NOTE,
        "catalog": [dict(d, naics=list(d["naics"])) for d in CATALOG],
        "industries": industries,
        "national": {"emp": nation["employed"], "avg_pay": None},
        "cities": out_cities,
        "counties": None,  # the survey has no township figures (frontend skips the township columns on null)
    }
    write_web("districts.json", doc)


# ---------------------------------------------------------------------------------------------- check


def check(web_dir: Path) -> list[tuple[str, str]]:
    web_dir = Path(web_dir)
    p = web_dir / "districts.json"
    if not p.exists():
        return [("NOTE", "districts.json: missing (optional, skipped)")]
    out: list[tuple[str, str]] = []
    bad = lambda m: out.append(("FAIL", f"districts.json: {m}"))  # noqa: E731
    try:
        doc = json.loads(p.read_text())
    except ValueError as exc:
        return [("FAIL", f"districts.json: invalid JSON ({exc})")]
    if not isinstance(doc, dict):
        return [("FAIL", "districts.json: top level is not an object")]
    for k in ("version", "vintage", "year", "sources", "rule", "catalog", "industries", "national", "cities", "counties"):
        if k not in doc:
            bad(f"missing key {k!r}")
    if out:
        return out
    sp = web_dir / "sources.json"
    if sp.exists() and isinstance(doc["sources"], list):
        try:
            known = {x.get("id") for x in json.loads(sp.read_text()) if isinstance(x, dict)}
        except (ValueError, AttributeError):
            known = None
        if known is not None and set(doc["sources"]) - known:
            out.append(("WARN", f"districts.json: sources missing from sources.json: {sorted(set(doc['sources']) - known)}"))
    if doc["version"] != 1:
        bad(f"version {doc['version']!r} != 1")
    if not isinstance(doc["sources"], list) or not doc["sources"]:
        bad("sources must be a non-empty list")
    if not isinstance(doc["rule"], dict) or not isinstance(doc["rule"].get("text"), str):
        bad("rule.text missing")
    rule = doc["rule"] if isinstance(doc["rule"], dict) else {}
    cat = doc["catalog"]
    ids = [d.get("id") for d in cat] if isinstance(cat, list) else []
    if ids != IDS:
        bad(f"catalog ids {ids} != {IDS}")
    industries = doc["industries"] if isinstance(doc["industries"], dict) else {}
    sections = {}
    for d in cat if isinstance(cat, list) else []:
        for k in ("name", "icon", "color", "naics", "own", "sub", "badge", "description"):
            if k not in d:
                bad(f"catalog {d.get('id')}: missing {k!r}")
        sections[d.get("id")] = d.get("naics") or []
        for s in d.get("naics") or []:
            if s not in industries:
                bad(f"catalog {d.get('id')}: section {s!r} not in industries")
    cities_path = web_dir / "cities.json"
    city_ids = None
    if cities_path.exists():
        try:
            city_ids = {c.get("id") for c in json.loads(cities_path.read_text()) if isinstance(c, dict)}
        except (ValueError, TypeError, AttributeError):
            city_ids = None
    cities = doc["cities"] if isinstance(doc["cities"], dict) else {}
    if city_ids is not None:
        missing = city_ids - set(cities)
        extra = set(cities) - city_ids
        if missing:
            bad(f"{len(missing)} cities.json ids missing, e.g. {sorted(missing)[:3]}")
        if extra:
            bad(f"{len(extra)} ids not in cities.json, e.g. {sorted(extra)[:3]}")
    n_null = n_badge = 0
    counts = {i: 0 for i in IDS}
    for cid, row in cities.items():
        if row is None:
            n_null += 1
            continue
        if not isinstance(row.get("emp"), (int, float)) or row["emp"] <= 0:
            bad(f"city {cid}: emp must be a positive number")
        dl = row.get("districts")
        if not isinstance(dl, list) or len(dl) > MAX_PER_CITY:
            bad(f"city {cid}: districts must be a list of at most {MAX_PER_CITY}")
            continue
        for d in dl:
            if d.get("id") not in counts:
                bad(f"city {cid}: unknown district {d.get('id')!r}")
                continue
            counts[d["id"]] += 1
            if d.get("emp") is None or d["emp"] <= 0:
                bad(f"city {cid}: district {d['id']} without jobs")
            elif d["emp"] < (rule.get("min_jobs") or 0) or d.get("lq") is None or d["lq"] < (rule.get("min_lq") or 0) - 0.005:
                bad(f"city {cid}: district {d['id']} does not pass the published rule")
            if d.get("lower_bound") != (d.get("suppressed", 0) > 0):
                bad(f"city {cid}: district {d['id']} lower_bound disagrees with suppressed")
        for t in row.get("top") or []:
            if t.get("naics") not in industries:
                bad(f"city {cid}: top industry {t.get('naics')!r} not in industries")
            elif (t.get("emp") or 0) < (rule.get("min_cell") or 0):
                bad(f"city {cid}: top industry {t.get('naics')!r} is under the minimum cell size")
        b = row.get("badge")
        if b is not None:
            n_badge += 1
            if not dl or b.get("district") not in {d.get("id") for d in dl}:
                bad(f"city {cid}: badge does not name one of its districts")
        elif dl:
            bad(f"city {cid}: districts but no badge")
    if any(lv == "FAIL" for lv, _ in out):
        return out
    out.append(("PASS", f"districts.json: {len(cities)} cities ({n_null} not in the Manpower Survey), {n_badge} with a "
                        f"city type, no township rows (survey is by county)"))
    out.append(("NOTE", "districts.json: cities per district: " + ", ".join(f"{k} {v}" for k, v in counts.items())))
    return out
