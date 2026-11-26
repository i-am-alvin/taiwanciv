"""Townships (鄉鎮市區): one row per township on the map for the Explorer table (column-oriented).

The metrics are the township values behind the lenses (lenses.township_table, the same formulas), plus the
registered population, area and density, the land-use shares, the cities.json id of the county the township belongs
to and a representative hex.
"""

from __future__ import annotations

import json
import re

from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web
from .lenses import METRIC, MIN_EXPECTED_DEATHS, MIN_SALES, NOTES, lens_meta, representative_cells, township_table

REQUIRES = ["_world", "tw_boundaries", "cities.json", "ris_population", "ris_demographics", "mof_income", "lvr_prices",
            "moe_pupils", "moda_mobile_speed", "moi_telecom_population", "census_housing", "mohw_workforce",
            "nlsc_landuse", "moi_temples", "ardswc_debris_flow"]
PRODUCES = ["counties.json"]

# Output column → lens id (lenses.lens_meta supplies the label, unit and description).
FROM_LENS = {
    "income": "income", "home_value": "home", "poverty": "poverty", "median_age": "age", "foreign_born": "foreign_born",
    "bachelors": "bachelors", "broadband": "broadband", "commute": "commute", "homeownership": "homeownership",
    "uninsured": "uninsured", "forest": "forest", "developed": "developed", "faith": "faith", "amenities": "amenities",
    "disasters": "disasters", "veterans_pct": "veterans", "farmland": "farmland",
}
LAND_TEXT = "國土利用現況調查（內政部國土測繪中心，2024–2025 年調查）：{what}面積 ÷ 該鄉鎮市區全部調查面積。"


def _field(key, label, fmt, unit, higher_is, source, description):
    return {"key": key, "label": label, "format": fmt, "unit": unit, "higher_is": higher_is,
            "source": source, "description": description}


def _township_text(desc: str) -> str:
    """A lens description reworded for a single township (drop the remark about hexes covering several townships)."""
    return re.sub(r"六角格跨多個鄉鎮市區時[^。]*。", "", desc)


def fields(info: dict) -> list[dict]:
    meta = lens_meta(info)
    y = info.get("pop_year")

    def lens(key, label=None):
        m = meta[FROM_LENS[key]]
        note = NOTES.get(FROM_LENS[key])
        return _field(key, label or m["name"], m["format"], m["unit"], m["higher_is"], m["source"],
                      _township_text(m["description"]) + (note or ""))

    cats = "；".join(f"{g['id']} = {g['name']}" for g in info.get("temple_groups") or [])
    return [
        _field("geoid", "代碼", "text", None, "neutral", "tw_boundaries", "鄉鎮市區代碼（TOWNCODE，8 碼；前 5 碼為縣市代碼）。"),
        _field("name", "鄉鎮市區", "text", None, "neutral", "tw_boundaries", "鄉鎮市區名稱。"),
        _field("state", "縣市", "text", None, "neutral", "tw_boundaries", "所屬縣市的代號（ISO 3166-2:TW，如 TPE）。"),
        _field("population", "人口", "int", "人", "neutral", "ris_population", f"{y} 年底戶籍登記人口（內政部戶政司 ODRP048）。"),
        _field("land_km2", "面積", "km2", "平方公里", "neutral", "ris_population", "鄉鎮市區土地面積（內政部戶政司 ODRP048）。"),
        _field("density", "人口密度", "float", "人／平方公里", "neutral", "ris_population", f"{y} 年底戶籍人口 ÷ 土地面積。"),
        lens("income"), lens("home_value"), lens("poverty"), lens("median_age"), lens("foreign_born"), lens("bachelors"),
        lens("broadband"), lens("commute"), lens("homeownership"), lens("uninsured"), lens("forest"),
        _field("crop", "農作地", "pct", "占鄉鎮市區面積的比率", "neutral", "nlsc_landuse",
               LAND_TEXT.format(what="農作使用土地（0101 類：水田、旱田、果園）")),
        _field("pasture", "畜牧地", "pct", "占鄉鎮市區面積的比率", "neutral", "nlsc_landuse",
               LAND_TEXT.format(what="畜牧使用土地（0103 類：畜禽舍、牧場）")),
        lens("developed"),
        _field("cbsa", "所屬縣市", "text", None, "neutral", "tw_boundaries", "所屬縣市在 cities.json 的 id（縣市代碼 COUNTYCODE）。"),
        _field("cell", "地圖六角格", "int", None, "neutral", "tw_boundaries",
               "代表六角格：最接近鄉鎮市區輪廓中心的陸地格（優先取同縣市），面積小於一格的鄉鎮市區與離島也能在地圖上標示。"
               "烏坵鄉本身在地圖上沒有陸地格，取同縣（金門縣）最近的陸地格，距該島約 115 公里。"),
        lens("faith"),
        _field("faith_tradition", "主祀神祇", "text", None, "neutral", "moi_temples",
               f"登記寺廟中主祀神祇最多的一類（{cats}）；「其他」只在沒有具名類別的寺廟時勝出，座數相同時取全國較多者；"
               "沒有登記寺廟者為空值。" + NOTES["faith_tradition"]),
        lens("amenities"), lens("disasters"),
        _field("veterans", "原住民人口", "int", "人", "neutral", "ris_demographics",
               f"{info.get('demo_year')} 年底具原住民身分（平地與山地）的戶籍人口（內政部戶政司 ODRP013）。" + NOTES["veterans"]),
        lens("veterans_pct", "原住民比率"),
        _field("name_en", "英文名稱", "text", None, "neutral", "tw_boundaries", "鄉鎮市區英文名稱（內政部界線資料）。"),
        _field("households", "戶數", "int", "戶", "neutral", "ris_demographics", f"{info.get('demo_year')} 年底戶籍登記戶數（內政部戶政司 ODRP014）。"),
        _field("tax_units", "申報戶數", "int", "戶", "neutral", "mof_income", f"{info.get('income_year')} 年度綜合所得稅申報戶（納稅單位）數。"),
        _field("home_price_m2", "房價單價", "usd", "住宅買賣單價中位數（新臺幣元／平方公尺）", "neutral", "lvr_prices",
               "與「房價」相同的成屋買賣中，每平方公尺單價（實價登錄的單價欄）的中位數。" + NOTES["home"]),
        _field("home_sales", "住宅交易筆數", "int", "筆", "neutral", "lvr_prices",
               f"四季內合格的成屋買賣筆數（不足 {MIN_SALES} 筆者不計算中位數）；新竹市、嘉義市的登錄資料不分區，各區為空值。"),
        _field("physicians", "西醫師數", "int", "人", "neutral", "mohw_workforce", "在該鄉鎮市區醫院與診所執業的西醫師人數（衛生福利部統計處）。"),
        _field("temples", "登記寺廟數", "int", "座", "neutral", "moi_temples", "依地址歸入該鄉鎮市區的登記寺廟座數（內政部全國宗教資訊網）。"),
        _field("smr", "標準化死亡比", "float", "全國＝1", "bad", "ris_demographics",
               "實際死亡人數 ÷ 以全國各性別、單一年齡死亡率計算的預期死亡人數（健康福祉指數的原始值）；"
               f"預期死亡人數不足 {MIN_EXPECTED_DEATHS} 人者為空值。"),
        lens("farmland"),
        _field("aquaculture", "養殖地", "pct", "占鄉鎮市區面積的比率", "neutral", "nlsc_landuse",
               LAND_TEXT.format(what="水產養殖使用土地（0102 類）")),
    ]


def _round(x, fmt):
    if x is None or isinstance(x, str):
        return x
    if fmt == "pct":
        return round(x, 4)
    if fmt in ("int", "usd"):
        return int(round(x))
    return round(x, 2) if abs(x) < 1000 else round(x)


def build() -> None:
    world = load_interim("_world")
    boundaries = load_interim("tw_boundaries")
    geoids = world["counties"]
    town = {t["geoid"]: t for t in boundaries["counties"]}
    abbr = {s["fips"]: s["abbr"] for s in boundaries["states"]}
    city_ids = {c["id"] for c in json.loads((WEB_DATA / "cities.json").read_text())}
    table = township_table(geoids)
    v, info = table["values"], table["info"]
    cells = representative_cells(world, boundaries, far=True)

    fs = fields(info)
    columns = [f["key"] for f in fs]
    fmt = {f["key"]: f["format"] for f in fs}
    rows = []
    for k, g in enumerate(geoids):
        t = town[g]
        pop, area = v["population"][k], v["land_km2"][k]
        row = {
            "geoid": g, "name": t["name"], "state": abbr.get(t["state_fips"]), "name_en": t.get("name_en"),
            "density": pop / area if pop is not None and area else None,
            "cbsa": t["state_fips"] if t["state_fips"] in city_ids else None,
            "cell": cells[k],
        }
        for key in columns:
            if key not in row:
                row[key] = v[key][k] if key in v else None  # a column whose source interim is missing is all null
        rows.append([_round(row[c], fmt[c]) for c in columns])

    write_web("counties.json", {"vintage": f"戶籍登記 {info['pop_year']} 年底；各欄年份見說明", "fields": fs, "columns": columns, "rows": rows})
    in_city = sum(1 for r in rows if r[columns.index("cbsa")])
    no_cell = [r[columns.index("name")] for r in rows if r[columns.index("cell")] is None]
    print(f"    {len(rows)} townships × {len(columns)} columns, {in_city} in a cities.json county"
          + (f"; no land hex for {', '.join(no_cell)}" if no_cell else ""))
    for j, c in enumerate(columns):
        n = sum(1 for r in rows if r[j] is not None)
        if n < len(rows):
            print(f"      {c}: {n}/{len(rows)}")


def check(web_dir) -> list[tuple[str, str]]:
    """counties.json: township codes, the lens-shared columns and their coverage."""
    from pathlib import Path

    path = Path(web_dir) / "counties.json"
    if not path.exists():
        return [("NOTE", "counties.json missing (optional)")]
    doc = json.loads(path.read_text())
    cols, rows = doc.get("columns") or [], doc.get("rows") or []
    out = []
    missing = [c for c in list(METRIC.values()) + ["faith_tradition", "cbsa", "cell"] if c not in cols]
    if missing:  # a NOTE, not a FAIL: a column whose source was not built is left out or null by design
        out.append(("NOTE", f"counties.json: without the lens columns {missing}"))
    rows = [r for r in rows if isinstance(r, list) and len(r) == len(cols)]
    gi = cols.index("geoid") if "geoid" in cols else None
    if gi is not None and rows and all(isinstance(r[gi], str) and len(r[gi]) == 8 for r in rows):
        out.append(("PASS", f"counties.json: {len(rows)} townships keyed by 8-digit TOWNCODE"))
    elif gi is not None and rows:
        out.append(("NOTE", "counties.json: geoids are not 8-digit TOWNCODEs (a non-Taiwan dataset?)"))
    partial = {c: sum(1 for r in rows if r[j] is not None) for j, c in enumerate(cols)}
    low = ", ".join(f"{c} {n}" for c, n in partial.items() if n < len(rows))
    out.append(("PASS" if rows else "NOTE", f"counties.json: columns with nulls (of {len(rows)}): {low or 'none'}"))
    return out
