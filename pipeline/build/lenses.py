"""Lenses = per-hex map overlays built from township (鄉鎮市區) statistics.

Each land hex is sampled at 7 points (see world.py). A township's population is spread over the hexes in proportion
to how many of all its sample points fall in each hex, so every township's people are counted exactly once. The six
small townships that no sample point hits (islands and one-hex city districts) are added in full to the hex holding
the centre of their outline, or to the nearest land hex if that centre lies on water. Density = people ÷ the hex's
land area. Every other people lens is the mean of the townships in the hex weighted by those people; the land and
hazard lenses are weighted by the share of the hex each township covers.

`township_table()` computes one value per township and metric; counties.json publishes the same numbers.
"""

from __future__ import annotations

import math
from collections import Counter

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, write_web

REQUIRES = ["_world", "tw_boundaries", "ris_population", "ris_demographics", "mof_income", "lvr_prices", "moe_pupils",
            "moda_mobile_speed", "moi_telecom_population", "census_housing", "mohw_workforce", "nlsc_landuse",
            "moi_temples", "ardswc_debris_flow"]
PRODUCES = ["lenses.json"]

GROUPS = [
    {"id": "people", "name": "人口"},
    {"id": "prosperity", "name": "經濟"},
    {"id": "knowledge", "name": "知識"},
    {"id": "life", "name": "生活"},
    {"id": "faith", "name": "信仰"},
    {"id": "hazards", "name": "災害"},
    {"id": "land", "name": "土地"},
]

MIN_SALES = 5  # a township's home price is shown only with at least this many qualifying sales
MIN_EXPECTED_DEATHS = 20  # the mortality index is shown only where at least this many deaths were expected
# Land Use Investigation: six-digit class codes by prefix (level 1 = first two digits, level 2 = first four).
LAND_CLASSES = {
    "forest": ("02",),            # 森林利用土地
    "farmland": ("01",),          # 農業利用土地: crops, aquaculture, livestock and farm facilities
    "crop": ("0101",),            # 農作: paddies, dry fields, orchards
    "pasture": ("0103",),         # 畜牧: livestock housing and pasture
    "aquaculture": ("0102",),     # 水產養殖: fish ponds
    "developed": ("03", "05", "06"),  # 交通、建築、公共利用土地
}


def nice(v: float, up: bool) -> float:
    """v rounded outward (up or down) to 2 significant digits."""
    if v == 0:
        return 0
    mag = 10 ** (math.floor(math.log10(abs(v))) - 1)
    return round((math.ceil if up else math.floor)(v / mag) * mag, 10)


def percentile_domain(values: list, log: bool) -> list[float] | None:
    """[2nd, 98th] percentile of the non-null hex values, rounded outward; positive values only on a log scale."""
    vals = sorted(v for v in values if v is not None and (v > 0 or not log))
    if not vals:
        return None
    lo, hi = vals[int(0.02 * (len(vals) - 1))], vals[int(0.98 * (len(vals) - 1))]
    lo, hi = nice(lo, False), nice(hi, True)
    return [lo, hi] if hi > lo else [lo, nice(vals[-1], True) if vals[-1] > lo else lo + 1]


DOMAIN_NOTE = "色階範圍取各六角格數值的第 2 至第 98 百分位，超出者以兩端顏色表示。"


def _optional(name: str):
    try:
        return load_interim_payload(name)
    except FileNotFoundError:
        print(f"    ! interim {name} missing: its lenses are skipped (run: uv run python -m pipeline fetch {name} && "
              f"uv run python -m pipeline process {name})")
        return None


def _div(a, b):
    return a / b if a is not None and b else None


# ---------------------------------------------------------------- one value per township


def township_table(geoids: list[str]) -> dict:
    """Every township metric behind the lenses and counties.json.

    Returns {"values": {metric: [one value per geoid, None = no data]}, "trad": [per geoid {group id: temples} or
    None], "info": {...vintages, counts and reference statistics for the texts...}}."""
    n = len(geoids)
    v: dict[str, list] = {}
    info: dict = {}

    def col(key, fn, towns):
        v[key] = [fn(towns[g]) if g in towns else None for g in geoids]

    pop_payload = load_interim_payload("ris_population")
    rp = pop_payload["data"]
    info["pop_year"] = rp["years"][-1]
    info["pop_vintage"] = pop_payload["vintage"]
    v["population"] = [rp["towns"][g]["pop"][-1] if g in rp["towns"] else None for g in geoids]
    v["land_km2"] = [rp["towns"][g]["area_km2"] if g in rp["towns"] else None for g in geoids]
    pop = v["population"]

    demo = _optional("ris_demographics")
    if demo:
        d = demo["data"]
        t = d["towns"]
        info["demo_year"], info["death_years"] = d["year"], d["death_years"]
        info["deaths_missing"] = d.get("deaths_missing") or {}
        col("median_age", lambda r: r["median_age"], t)
        col("households", lambda r: r["households"], t)
        col("bachelors", lambda r: _div(r["degree"], r["pop15"]), t)
        col("veterans", lambda r: r["indigenous_plain"] + r["indigenous_mountain"], t)
        col("veterans_pct", lambda r: _div(r["indigenous_plain"] + r["indigenous_mountain"], r["indigenous_pop"]), t)
        col("smr", lambda r: r["deaths"] / r["deaths_expected"] if r["deaths_expected"] >= MIN_EXPECTED_DEATHS else None, t)
        smr = [x for x in v["smr"] if x is not None]
        mean = sum(smr) / len(smr)
        sd = math.sqrt(sum((x - mean) ** 2 for x in smr) / len(smr))
        info["smr_mean"], info["smr_sd"], info["smr_n"] = mean, sd, len(smr)
        v["amenities"] = [None if x is None else 100 - 10 * (x - mean) / sd for x in v["smr"]]

    inc = _optional("mof_income")
    if inc:
        info["income_year"] = inc["data"]["year"]
        col("income", lambda r: r["median"], inc["data"]["towns"])
        col("poverty", lambda r: r["q1"], inc["data"]["towns"])
        col("tax_units", lambda r: r["units"], inc["data"]["towns"])

    lvr = _optional("lvr_prices")
    if lvr:
        d = lvr["data"]
        info["lvr_seasons"], info["lvr_vintage"] = d["seasons"], lvr["vintage"]
        # 新竹市 and 嘉義市 register sales for the whole city without the district (interim "citywide"): a city
        # median is not a district's value, so their districts stay null, like every township below MIN_SALES.
        nodistrict = set(d.get("citywide") or {})

        def sale(g):
            r = d["towns"].get(g)
            return r if r and r["sales"] >= MIN_SALES else None

        v["home_value"] = [(sale(g) or {}).get("median_total") for g in geoids]
        v["home_price_m2"] = [(sale(g) or {}).get("median_per_m2") for g in geoids]
        v["home_sales"] = [None if g[:5] in nodistrict else d["towns"].get(g, {}).get("sales", 0) for g in geoids]

    moe = _optional("moe_pupils")
    if moe:
        info["school_year"] = moe["data"]["school_year"]
        col("foreign_born", lambda r: _div(r["ni_elementary"], r["elementary_pupils"]), moe["data"]["towns"])

    speed = _optional("moda_mobile_speed")
    if speed:
        info["speed_year"], info["speed_towns"] = speed["data"]["year"], len(speed["data"]["towns"])
        col("broadband", lambda r: r["download_mbps"], speed["data"]["towns"])

    tel = _optional("moi_telecom_population")
    if tel:
        info["telecom_time"] = tel["data"]["data_time"]
        col("commute", lambda r: _div(r.get("day_weekday"), r.get("night_weekday")), tel["data"]["towns"])

    cen = _optional("census_housing")
    if cen:
        col("homeownership", lambda r: _div(r.get("occupied"), r.get("homes")), cen["data"]["towns"])

    med = _optional("mohw_workforce")
    if med:
        info["workforce_years"] = med["data"]["years"]
        mt = med["data"]["towns"]
        # the staffing statistics cover every township in their code table: all 368 here
        v["physicians"] = [mt[g]["physicians"] if g in mt else None for g in geoids]
        v["uninsured"] = [_div(mt[g]["physicians"] * 10000, pop[k]) if g in mt else None for k, g in enumerate(geoids)]

    land = _optional("nlsc_landuse")
    if land:
        lt = land["data"]["towns"]
        for key, prefixes in LAND_CLASSES.items():
            v[key] = [_div(sum(a for c, a in lt[g].items() if c.startswith(prefixes)), sum(lt[g].values())) if g in lt else None
                      for g in geoids]

    trad = [None] * n
    tem = _optional("moi_temples")
    if tem:
        d = tem["data"]
        info["temple_groups"], info["temple_national"] = d["groups"], d["national"]
        info["temples"] = sum(d["national"].values())
        # the register is exhaustive: a township without an entry has no registered temple (a real 0)
        v["temples"] = [d["towns"].get(g, {}).get("temples", 0) for g in geoids]
        v["faith"] = [_div(v["temples"][k] * 10000, pop[k]) for k in range(n)]
        trad = [d["towns"].get(g, {}).get("groups") or {} for g in geoids]
        order = [g["id"] for g in d["groups"]]
        idx = [dominant_group(t, order, d["national"]) for t in trad]
        v["faith_tradition"] = [order[i] if i is not None else None for i in idx]

    deb = _optional("ardswc_debris_flow")
    if deb:
        info["debris_streams"] = deb["data"]["streams"]
        # the list is exhaustive: a township that is not in it has no designated stream (a real 0)
        v["disasters"] = [deb["data"]["towns"].get(g, 0) for g in geoids]

    return {"values": v, "trad": trad, "info": info}


def dominant_group(counts: dict, order: list[str], national: dict) -> int | None:
    """Index into `order` of the deity group with the most temples; None if there are no temples.

    'other' (the last group, a mix of hundreds of deities) only wins when no named group has a temple. Ties go to
    the group with more temples nationwide."""
    named = [i for i, gid in enumerate(order[:-1]) if counts.get(gid, 0) > 0]
    if named:
        return max(named, key=lambda i: (counts[order[i]], national.get(order[i], 0)))
    return len(order) - 1 if counts.get(order[-1], 0) > 0 else None


# ---------------------------------------------------------------- lens metadata

RAMP = {
    "density": ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"],
    "income": ["#3a1c0b", "#7a4413", "#b8781f", "#e3b23c", "#f6e27f", "#fffbe0"],
    "home": ["#0b2a2e", "#165a5c", "#2f8f83", "#7cc29a", "#d4ecb0", "#ffffe0"],
    "poverty": ["#faebdd", "#f69c73", "#e83f3f", "#a11a5b", "#4c1d4b", "#03051a"],  # low income = bright
    "age": ["#00224e", "#35456c", "#666970", "#948e77", "#c8b866", "#fee838"],
    "foreign_born": ["#0b0405", "#382a54", "#395d9c", "#3497a9", "#60ceac", "#def5e5"],
    "bachelors": ["#08203e", "#0f4c81", "#2a7fc1", "#5fa8e0", "#a6d1f2", "#eaf5ff"],
    "broadband": ["#1a0a2e", "#3f1d6b", "#6a3fa0", "#9a72c9", "#c9a9e6", "#f3e8ff"],
    "commute": ["#2b0b1e", "#5e1742", "#93275f", "#c84f7c", "#ea8fa8", "#fbd9e1"],
    "homeownership": ["#1c1a05", "#45410f", "#76701d", "#a8a033", "#d4ce62", "#f8f6c4"],
    "uninsured": ["#1a0505", "#4a0f0f", "#80201a", "#b8452b", "#e07b54", "#f9c9a8"],
    "forest": ["#0b1f0f", "#14401c", "#1f6b2b", "#3a9443", "#7fc07a", "#d5efcd"],
    "farmland": ["#141d05", "#2f4510", "#557019", "#84a02a", "#b8cf55", "#eef7b8"],
    "developed": ["#121218", "#2c2c3c", "#4b4b66", "#727294", "#a3a3c2", "#e2e2f0"],
    "faith": ["#1a1033", "#3d2466", "#6b3d8f", "#a5649c", "#d99a8f", "#f7dca0"],
    "amenities": ["#3b0a1e", "#7a1f3d", "#b9534f", "#e3a35c", "#c9d97a", "#7ecf8e"],
    "disasters": ["#14161f", "#2e2a4a", "#5b3466", "#93405f", "#cf6a4a", "#f4b860"],
    "veterans": ["#0d1a12", "#1f3d2a", "#3b6340", "#6b8a4e", "#a9b46a", "#ece2a6"],
}
GROUP_COLOR = {"earth_god": "#c9a227", "mazu": "#d1495b", "wangye": "#3d7ea6", "guanyin": "#e8e2d0", "buddha": "#e08a3c",
               "xuantian": "#3a3f58", "guandi": "#8f2d2d", "baosheng": "#4f9d69", "sanshan": "#7d5ba6", "nezha": "#e36bae",
               "other": "#9a9aa8"}

NOTES = {
    "density": "戶籍登記人口，不等於實際居住人口。",
    "income": "報稅資料：以申報戶（納稅單位）為單位、依戶籍地統計，不含免稅所得、分離課稅所得與政府移轉收入，不是家戶所得調查。",
    "home": "只計有登錄的成屋買賣，交易少的鄉鎮市區中位數起伏大；新竹市、嘉義市的登錄資料不分區，無法歸入各區，故無資料。",
    "poverty": "臺灣沒有公開的全國鄉鎮市區低收入戶統計，本圖層以申報所得的第一四分位數代替貧窮率：數值愈低，低所得申報戶愈多。",
    "foreign_born": "臺灣未公布各鄉鎮市區的新住民或外國出生人口數，本圖層以國小學生中父或母為新住民者的比率代替，依學校所在地統計。",
    "bachelors": "依戶籍登記的教育程度，畢業後未申請變更者不會更新；統計對象為 15 歲以上人口。",
    "broadband": "臺灣沒有鄉鎮市區別的家戶寬頻訂閱率，本圖層改用行動網路定點實測的下載速率；沒有量測點的鄉鎮市區無資料。",
    "commute": "臺灣沒有鄉鎮市區別的通勤時間統計，本圖層改用電信信令推估的日夜人口比；資料時間為 2020 年 11 月。",
    "homeownership": "臺灣沒有鄉鎮市區別的住宅自有率，本圖層改用 2020 年人口及住宅普查中有人經常居住的住宅比率。",
    "uninsured": "臺灣實施全民健保，沒有「未納保率」可比，本圖層改用每萬人口執業西醫師數；醫師依執業場所計算，設有大型醫院的地方特別高。",
    "faith": "只計向政府登記的寺廟（道教、佛教、一貫道等），不含教會、清真寺與未登記的宮壇、小祠；寺廟數不等於信徒人數。",
    "faith_tradition": "只計向政府登記的寺廟（道教、佛教、一貫道等），不含教會、清真寺與未登記的宮壇、小祠；「最多」可能只是少數幾座寺廟中的相對多數。",
    "amenities": "只由死亡登記算出（年齡標準化死亡比），不是幸福感調查；人口少的鄉鎮市區數值起伏大。",
    "disasters": "土石流潛勢溪流是主管機關公告的危險區位，不是實際發生的災害次數。",
    "veterans": "臺灣沒有鄉鎮市區別的退伍軍人統計，本圖層改為具原住民身分者占戶籍人口的比率。",
}


def lens_meta(info: dict) -> dict[str, dict]:
    """id → lens metadata (everything but `values` and `domain`), in display order. Texts describe the Taiwan data."""
    y = info.get("pop_year")
    dy = info.get("death_years") or [None, None]
    missing = "；".join(f"{yr} 年缺 {'、'.join(names)}" for yr, names in (info.get("deaths_missing") or {}).items())
    seasons = info.get("lvr_seasons") or ["", ""]
    wf = info.get("workforce_years") or {}
    groups = "、".join(g["name"] for g in info.get("temple_groups") or [])
    m = {}

    def add(lid, group, name, icon, emoji, unit, fmt, scale, higher_is, source, description, weight="pop"):
        m[lid] = {"group": group, "name": name, "icon": icon, "emoji": emoji, "unit": unit, "format": fmt, "scale": scale,
                  "higher_is": higher_is, "ramp": RAMP.get(lid), "source": source, "description": description,
                  **({"note": NOTES[lid]} if lid in NOTES else {}), "_weight": weight}

    add("density", "people", "人口密度", "l-people", "👥", "人／平方公里", "int", "log", "neutral", "ris_population",
        f"每平方公里陸地的戶籍人口。各鄉鎮市區 {y} 年底的戶籍登記人口（內政部戶政司 ODRP048）依六角格涵蓋該鄉鎮市區的"
        "比例分配到各格，再除以該格的陸地面積。")
    add("income", "prosperity", "所得", "l-income", "💵", "每申報戶綜合所得總額中位數（新臺幣元）", "usd", "linear", "good", "mof_income",
        f"{info.get('income_year')} 年度綜合所得稅申報核定資料中，各鄉鎮市區申報戶（納稅單位：本人、配偶及受扶養親屬）綜合所得總額的"
        "中位數，取財政部統計表各鄉鎮市區「合計」列的中位數（原表單位為千元），不是各村里中位數的中位數。六角格跨多個鄉鎮市區時"
        "依人口加權平均。")
    add("home", "prosperity", "房價", "l-home", "🏠", "住宅買賣總價中位數（新臺幣元）", "usd", "log", "neutral", "lvr_prices",
        f"實價登錄 {seasons[0]} 至 {seasons[-1]} 四季（民國年與季別）成屋買賣的總價中位數。計入條件：交易標的含建物、主要用途為住家用、"
        "建物型態為公寓、華廈、住宅大樓、透天厝或套房、總價大於 0，且備註未註記為親友、員工、共有人等特殊關係間交易；"
        f"預售屋、純土地與純車位交易不計。合格交易不足 {MIN_SALES} 筆的鄉鎮市區不顯示。六角格跨多個鄉鎮市區時依人口加權平均。")
    add("poverty", "prosperity", "低所得", "l-poverty", "🥣", "每申報戶綜合所得總額第一四分位數（新臺幣元）", "usd", "linear", "good", "mof_income",
        f"{info.get('income_year')} 年度綜合所得稅申報核定資料中，各鄉鎮市區申報戶綜合所得總額的第一四分位數（財政部統計表「合計」列）："
        "該鄉鎮市區有四分之一的申報戶所得低於此數。數值愈低（顏色愈亮），低所得申報戶愈多。六角格跨多個鄉鎮市區時依人口加權平均。")
    add("age", "people", "年齡中位數", "l-age", "🎂", "歲", "years", "linear", "neutral", "ris_demographics",
        f"{info.get('demo_year')} 年底戶籍人口的年齡中位數，由各村里單一年齡人口（內政部戶政司 ODRP014）加總到鄉鎮市區後計算。"
        "六角格跨多個鄉鎮市區時顯示各中位數的人口加權平均，為近似值。")
    add("foreign_born", "people", "新住民子女", "l-foreign-born", "🌍", "國小學生中新住民子女的比率", "pct", "linear", "neutral", "moe_pupils",
        f"{info.get('school_year')} 學年度各鄉鎮市區國小的新住民子女學生數（教育部統計處）÷ 該鄉鎮市區所有國小的學生數（國民小學校別資料加總）。"
        "新住民子女指父或母一方為外國人、大陸地區人民或港澳居民的在學學生。六角格跨多個鄉鎮市區時依人口加權平均。")
    add("bachelors", "knowledge", "大學學歷", "l-degrees", "🎓", "15 歲以上人口具大學以上學歷的比率", "pct", "linear", "good", "ris_demographics",
        f"{info.get('demo_year')} 年底 15 歲以上戶籍人口中，教育程度為大學畢業、碩士（畢業或肄業）或博士（畢業或肄業）者的比率"
        "（內政部戶政司 ODRP020）；碩、博士肄業者已具學士學位，故計入。專科與大學肄業不計。六角格跨多個鄉鎮市區時依人口加權平均。")
    add("broadband", "knowledge", "行動網速", "l-broadband", "📡", "行動網路平均下載速率（Mbps）", "float", "linear", "good", "moda_mobile_speed",
        f"數位發展部 {info.get('speed_year')} 年行動通訊速率定點量測：各鄉鎮市區各電信業者下載速率的平均。"
        f"共 {info.get('speed_towns')} 個鄉鎮市區有量測結果，其餘無資料。六角格跨多個鄉鎮市區時依人口加權平均。")
    add("commute", "life", "日夜人口比", "l-commute", "🚗", "平日日間活動人口 ÷ 平日夜間停留人口", "float", "linear", "neutral", "moi_telecom_population",
        "內政部統計處以電信信令推估的各鄉鎮市區平日日間（7 至 19 時）活動人口，除以平日夜間停留人口。大於 1 表示白天有人口移入"
        "（工作、就學或觀光地），小於 1 表示白天人口外流（住宅區）。六角格跨多個鄉鎮市區時依人口加權平均。")
    add("homeownership", "life", "住宅使用率", "l-homeownership", "🔑", "有人經常居住的住宅比率", "pct", "linear", "neutral", "census_housing",
        "2020 年人口及住宅普查（主計總處）：各鄉鎮市區有人經常居住的住宅 ÷ 全部住宅。其餘為偶爾自住、作辦公室或倉庫等其他用途，"
        "或目前沒有使用的住宅。六角格跨多個鄉鎮市區時依人口加權平均。")
    add("uninsured", "life", "醫師密度", "l-uninsured", "🩺", "每萬人口執業西醫師數", "float", "linear", "good", "mohw_workforce",
        f"各鄉鎮市區醫院（{wf.get('hospital')} 年底）與診所（{wf.get('clinic')} 年底）執業西醫師數（衛生福利部統計處）÷ {y} 年底戶籍人口 × 10,000。"
        "沒有醫院或診所的鄉鎮市區為 0。六角格跨多個鄉鎮市區時依人口加權平均。")
    land = ("國土利用現況調查（內政部國土測繪中心，2024–2025 年調查，108 年版分類）各鄉鎮市區統計：{what}面積 ÷ 該鄉鎮市區全部調查面積"
            "（含水利與其他用地）。六角格跨多個鄉鎮市區時依各鄉鎮市區占該格的比例加權平均。")
    add("forest", "land", "森林", "l-forest", "🌲", "占鄉鎮市區面積的比率", "pct", "linear", "neutral", "nlsc_landuse",
        land.format(what="森林利用土地（02 類：針葉林、闊葉林、竹林、混淆林、灌木林等）"), "area")
    add("farmland", "land", "農地", "l-farmland", "🚜", "占鄉鎮市區面積的比率", "pct", "linear", "neutral", "nlsc_landuse",
        land.format(what="農業利用土地（01 類：水田、旱田、果園、水產養殖、畜牧與農業設施）"), "area")
    add("developed", "land", "建成地", "l-developed", "🏙️", "占鄉鎮市區面積的比率", "pct", "linear", "neutral", "nlsc_landuse",
        land.format(what="交通、建築與公共利用土地（03、05、06 類）"), "area")
    add("faith", "faith", "寺廟密度", "l-faith", "🕍", "每萬人口登記寺廟數", "float", "linear", "neutral", "moi_temples",
        f"內政部全國宗教資訊網登記寺廟（共 {info.get('temples'):,} 座）依地址歸入鄉鎮市區後的座數 ÷ {y} 年底戶籍人口 × 10,000。"
        "沒有登記寺廟的鄉鎮市區為 0。六角格跨多個鄉鎮市區時依人口加權平均。" if info.get("temples") else "")
    add("faith_tradition", "faith", "主祀神祇", "l-faith-tradition", "⛪", "最多登記寺廟主祀的神祇", "category", "linear", "neutral", "moi_temples",
        f"各鄉鎮市區登記寺廟中，主祀神祇最多的一類。神祇依名稱關鍵字歸為：{groups}。「其他神祇」為數百種神祇的合計，"
        "只有在沒有任何具名類別的寺廟時才會勝出；座數相同時取全國寺廟數較多的類別。六角格跨多個鄉鎮市區時，依各鄉鎮市區在該格的"
        "人口比例加總各類寺廟數後取最多者。沒有登記寺廟的地方無資料。")
    add("amenities", "life", "健康福祉", "l-amenities", "🎭", "指數（100＝各鄉鎮市區平均）", "float", "linear", "good", "ris_demographics",
        f"以死亡登記計算的健康指數（對應原版的 Wellbeing／Amenities）。先算標準化死亡比（SMR）：{dy[0]}–{dy[-1]} 年各鄉鎮市區的死亡人數，"
        "除以「以全國各性別、單一年齡死亡率套用在該鄉鎮市區期中人口」所得的預期死亡人數（內政部戶政司 ODRP031、ODRP014）；"
        f"再換算為指數 100 − 10 × z，z 為 SMR 相對於 {info.get('smr_n')} 個鄉鎮市區未加權平均 {info.get('smr_mean', 0):.3f}、"
        f"標準差 {info.get('smr_sd', 0):.3f} 的標準分數。110 表示死亡率比平均低一個標準差。預期死亡人數不足 {MIN_EXPECTED_DEATHS} 人的"
        "鄉鎮市區不計算。" + (f"來源資料{missing}，該年不計入該區。" if missing else "") + "六角格跨多個鄉鎮市區時依人口加權平均。")
    add("disasters", "hazards", "土石流潛勢", "l-disasters", "🌪️", "土石流潛勢溪流條數", "int", "linear", "bad", "ardswc_debris_flow",
        f"農業部農村發展及水土保持署公告的土石流潛勢溪流（共 {info.get('debris_streams', 0):,} 條）依主要所在鄉鎮市區計數；未列入者為 0 條。"
        "六角格跨多個鄉鎮市區時依各鄉鎮市區占該格的比例加權平均後取整數。", "area")
    add("veterans", "people", "原住民", "l-veterans", "🎖️", "原住民占戶籍人口的比率", "pct", "linear", "neutral", "ris_demographics",
        f"{info.get('demo_year')} 年底各鄉鎮市區具原住民身分（平地原住民與山地原住民）的戶籍人口 ÷ 戶籍總人口（內政部戶政司 ODRP013）。"
        "六角格跨多個鄉鎮市區時依人口加權平均。")
    return m


# lens id → township_table() metric
METRIC = {"income": "income", "home": "home_value", "poverty": "poverty", "age": "median_age", "foreign_born": "foreign_born",
          "bachelors": "bachelors", "broadband": "broadband", "commute": "commute", "homeownership": "homeownership",
          "uninsured": "uninsured", "forest": "forest", "farmland": "farmland", "developed": "developed", "faith": "faith",
          "amenities": "amenities", "disasters": "disasters", "veterans": "veterans_pct"}
DIGITS = {"pct": 4, "years": 1, "float": 2, "minutes": 1}


# ---------------------------------------------------------------- hexes


def ring_centre(rings: list) -> tuple[float, float] | None:
    """Centroid (lon, lat) of the largest ring of an outline."""
    best = None
    for r in rings:
        a = cx = cy = 0.0
        for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1]):
            f = x0 * y1 - x1 * y0
            a += f
            cx += (x0 + x1) * f
            cy += (y0 + y1) * f
        if a and (best is None or abs(a) > best[0]):
            best = (abs(a), cx / (3 * a), cy / (3 * a))
    return (best[1], best[2]) if best else None


def nearest_land(grid: HexGrid, owner: list[int], cell: int, x: float, y: float, state: int, max_rings: int = 8) -> int:
    """Nearest land cell to (x, y) within `max_rings` of `cell`, preferring cells of `state`; -1 if none."""
    seen, ring, found = {cell}, [cell], None
    best = None
    for depth in range(max_rings + 1):
        for c in ring:
            if owner[c] < 0:
                continue
            found = depth if found is None else found
            cx, cy = grid.center(*grid.col_row(c))
            score = (owner[c] != state, math.hypot(cx - x, cy - y))
            if best is None or score < best[0]:
                best = (score, c)
        if found is not None and depth > found:
            break
        ring = [nb for c in ring for nb in grid.neighbours(c) if nb not in seen and not seen.add(nb)]
    return best[1] if best else -1


def representative_cells(world: dict, boundaries: dict, far: bool = False) -> list[int | None]:
    """For each township: the land cell nearest the centre of its outline, in its own county where possible.

    The search stops 8 rings out (about 28 km). With `far`, a township with no land hex that near (烏坵鄉, an islet
    115 km from the rest of 金門縣) gets the nearest land hex of its own county however far it is; without it, None."""
    proj, grid, owner = MapProjection(**world["projection"]), HexGrid(**world["grid"]), world["owner"]
    state_idx = {fips: k for k, fips in enumerate(world["states"])}
    rings = {t["geoid"]: t["rings"] for t in boundaries["counties"]}
    county = {t["geoid"]: t["state_fips"] for t in boundaries["counties"]}
    out = []
    for g in world["counties"]:
        c = ring_centre(rings.get(g) or [])
        if c is None:
            out.append(None)
            continue
        x, y = proj(*c)
        st = state_idx.get(county.get(g), -9)
        cell = nearest_land(grid, owner, max(grid.cell_at(x, y), 0), x, y, st)
        if cell < 0 and far:
            cands = [i for i, o in enumerate(owner) if o == st] or [i for i, o in enumerate(owner) if o >= 0]
            cell = min(cands, key=lambda i: math.hypot(grid.center(*grid.col_row(i))[0] - x, grid.center(*grid.col_row(i))[1] - y), default=-1)
        out.append(cell if cell >= 0 else None)
    return out


def hex_weights(world: dict, pop: list, rep_cells: list) -> tuple[list, list, list, dict]:
    """Per cell: residents, [(township index, residents)] parts, [(township index, sample hits)] area parts."""
    samples = world["county_samples"]
    total_hits = Counter(k for s in samples for k in s if k >= 0)
    small_by_cell: dict[int, list[int]] = {}
    placed, lost = [], []
    for k, p in enumerate(pop):
        if p is None or total_hits[k]:
            continue
        if rep_cells[k] is None:
            lost.append(k)
            continue
        small_by_cell.setdefault(rep_cells[k], []).append(k)
        placed.append(k)
    people = [None] * len(samples)
    weights: list[list[tuple[int, float]]] = [[] for _ in samples]
    area: list[list[tuple[int, float]]] = [[] for _ in samples]
    for i, s in enumerate(samples):
        if not s:
            continue
        hits = Counter(x for x in s if x >= 0)
        parts = [(k, pop[k] * h / total_hits[k]) for k, h in hits.items() if pop[k] is not None]
        parts += [(k, pop[k]) for k in small_by_cell.get(i, [])]
        weights[i] = parts
        area[i] = [(k, h) for k, h in hits.items()] or [(k, 1) for k in small_by_cell.get(i, [])]
        if parts:
            people[i] = sum(p for _, p in parts)
    return people, weights, area, {"placed": placed, "lost": lost}


def spread(weights, tvals: list, digits: int) -> list:
    """Weighted mean of the township values over each hex's parts (None where no part has a value)."""
    out = [None] * len(weights)
    for i, parts in enumerate(weights):
        vals = [(tvals[k], p) for k, p in parts if tvals[k] is not None]
        wsum = sum(p for _, p in vals)
        if wsum:
            out[i] = round(sum(v * p for v, p in vals) / wsum, digits)
    return out


def build() -> None:
    world = load_interim("_world")
    boundaries = load_interim("tw_boundaries")
    geoids = world["counties"]
    proj, grid = MapProjection(**world["projection"]), HexGrid(**world["grid"])
    samples = world["county_samples"]
    table = township_table(geoids)
    v, info = table["values"], table["info"]
    pop = v["population"]
    rep = representative_cells(world, boundaries)
    people, weights, area, notes = hex_weights(world, pop, rep)

    hex_km2 = 1.5 * math.sqrt(3) * proj.km(grid.radius) ** 2  # real km², not map units
    density = [None] * grid.size
    for i, s in enumerate(samples):
        if s and people[i] is not None:
            land = sum(1 for x in s if x >= 0) or 1  # a hex whose samples all miss townships still counts its centre
            density[i] = round(people[i] / (hex_km2 * land / len(s)), 2)

    total = sum(p for p in pop if p is not None)
    on_hexes = sum(p for p in people if p)
    names = {t["geoid"]: t["name"] for t in boundaries["counties"]}
    print(f"    population on hexes {on_hexes:,.0f} of {total:,.0f} ({on_hexes / total:.4%})")
    if notes["placed"]:
        print(f"    {len(notes['placed'])} unsampled townships placed by their centre: {', '.join(names[geoids[k]] for k in notes['placed'])}")
    if notes["lost"]:
        print(f"    {len(notes['lost'])} townships not placed: {', '.join(geoids[k] for k in notes['lost'])}")

    meta = lens_meta(info)
    lenses = []
    for lid, m in meta.items():
        m = dict(m)
        w = area if m.pop("_weight") == "area" else weights
        if lid == "density":
            values = density
        elif lid == "faith_tradition":
            if "faith_tradition" not in v:
                continue
            order = [g["id"] for g in info["temple_groups"]]
            values = []
            for parts in weights:
                tot = Counter()
                for k, p in parts:
                    if table["trad"][k] and pop[k]:
                        for gid, n in table["trad"][k].items():
                            tot[gid] += n * p / pop[k]
                values.append(dominant_group(tot, order, info["temple_national"]) if tot else None)
            cats = [{"id": g["id"], "name": g["name"], "color": GROUP_COLOR[g["id"]],
                     "description": ("主祀神祇名稱含：" + "、".join(g["keywords"])) if g["keywords"] else "未歸入以上各類的其他主祀神祇。"}
                    for g in info["temple_groups"]]
            m.update(categories=cats, ramp=[c["color"] for c in cats], domain=[0, len(cats) - 1])
        else:
            key = METRIC[lid]
            if key not in v:
                print(f"    lens {lid} skipped: no data")
                continue
            if m["format"] == "int":
                values = [None if x is None else int(round(x)) for x in spread(w, v[key], 3)]
            elif m["format"] == "usd":
                values = [None if x is None else int(round(x)) for x in spread(w, v[key], 0)]
            else:
                values = spread(w, v[key], DIGITS[m["format"]])
        if "domain" not in m:
            m["domain"] = percentile_domain(values, m["scale"] == "log")
            m["description"] += DOMAIN_NOTE
        lenses.append({"id": lid, **m, "values": values})
        if lid in METRIC:
            have = sum(1 for x in v[METRIC[lid]] if x is not None)
            print(f"    {lid:16s} townships {have}/{len(geoids)}  hexes {sum(1 for x in values if x is not None)}  domain {m['domain']}")

    groups = [g for g in GROUPS if any(l["group"] == g["id"] for l in lenses)]
    vintage = f"戶籍登記 {info['pop_year']} 年底；各圖層年份見說明"
    write_web("lenses.json", {"vintage": vintage, "groups": groups, "lenses": lenses})


# The replaced lenses must say in their legend what they stand in for.
NOTE_REQUIRED = ["poverty", "foreign_born", "broadband", "commute", "homeownership", "uninsured", "faith", "faith_tradition",
                 "amenities", "disasters", "veterans"]
EXPECTED = ["density", "income", "home", "poverty", "age", "foreign_born", "bachelors", "broadband", "commute",
            "homeownership", "uninsured", "forest", "farmland", "developed", "faith", "faith_tradition", "amenities",
            "disasters", "veterans"]


def check(web_dir) -> list[tuple[str, str]]:
    """Taiwan lenses: presence, required legend caveats, category shape and coverage (pipeline.check validates the general shape)."""
    import json
    from pathlib import Path

    path = Path(web_dir) / "lenses.json"
    if not path.exists():
        return [("NOTE", "lenses.json missing (pipeline.check reports it)")]
    doc = json.loads(path.read_text())
    by_id = {l.get("id"): l for l in doc.get("lenses", []) if isinstance(l, dict)}
    out = []
    for lid in EXPECTED:
        lens = by_id.get(lid)
        if lens is None:
            out.append(("NOTE", f"lens {lid} not built (its source interim is missing)"))
            continue
        vals = lens.get("values") or []
        n = sum(1 for x in vals if x is not None)
        if lid in NOTE_REQUIRED and not lens.get("note"):
            out.append(("FAIL", f"lens {lid}: the legend caveat (note) is required"))
        if lid == "faith_tradition":
            cats = lens.get("categories") or []
            counts = Counter(x for x in vals if x is not None)
            mix = ", ".join(f"{cats[i]['id']} {c}" for i, c in counts.most_common() if i < len(cats))
            out.append(("PASS", f"lens {lid}: {n} hexes; {mix}"))
        else:
            nums = sorted(x for x in vals if x is not None)
            if nums:
                out.append(("PASS", f"lens {lid}: {n} hexes, median {nums[len(nums) // 2]}, range {nums[0]}…{nums[-1]}"))
    return out
