"""The game-concept → real-data mapping, in one place.

Each yield is defined once here and exported to the browser, so the UI and the Almanac always describe exactly
what was computed. Gold is value added from the 2021 Industry and Commerce Census (Taiwan has no official GDP by
county); the other yields count employed people by industry where they live (Manpower Survey, table 33).

Industry keys are the original's (NAICS-like) keys so the frontend's icons and colours carry over. Taiwan's
Standard Industrial Classification has 19 sections; they map onto 17 of those keys (wholesale and retail are one
section in Taiwan, there is no "management of companies" section, and the two utility sections are merged).
"""

from __future__ import annotations

# key → (dgbas_labor sections, label shown in the UI)
INDUSTRIES = {
    "agriculture": (["agriculture"], "農、林、漁、牧業"),
    "mining": (["mining"], "礦業及土石採取業"),
    "manufacturing": (["manufacturing"], "製造業"),
    "utilities": (["power", "water"], "電力燃氣及用水供應、污染整治業"),
    "construction": (["construction"], "營建工程業"),
    "retail": (["trade"], "批發及零售業"),
    "transportation": (["transportation"], "運輸及倉儲業"),
    "accommodation": (["accommodation"], "住宿及餐飲業"),
    "information": (["information"], "出版影音及資通訊業"),
    "finance": (["finance"], "金融及保險業"),
    "real_estate": (["real_estate"], "不動產業"),
    "professional": (["professional"], "專業、科學及技術服務業"),
    "admin": (["support"], "支援服務業"),
    "public_admin": (["public_admin"], "公共行政及國防；強制性社會安全"),
    "education": (["education"], "教育業"),
    "health": (["health"], "醫療保健及社會工作服務業"),
    "arts": (["arts"], "藝術、娛樂及休閒服務業"),
    "other": (["other"], "其他服務業"),
}

LABOR_SRC = "人力資源調查 2025 年報表 33（主計總處），依居住縣市計，千人為單位"

YIELDS = [
    {
        "key": "food",
        "icon": "y-food",
        "emoji": "🌾",
        "label": "糧食",
        "color": "#7fbf3f",
        "unit": "workers",
        "industries": ["agriculture"],
        "description": f"農、林、漁、牧業就業人數（{LABOR_SRC}）。",
    },
    {
        "key": "production",
        "icon": "y-production",
        "emoji": "⚙️",
        "label": "生產",
        "color": "#d9823b",
        "unit": "workers",
        "industries": ["manufacturing", "construction", "mining"],
        "description": f"製造業、營建工程業與礦業及土石採取業就業人數（{LABOR_SRC}）。",
    },
    {
        "key": "gold",
        "icon": "y-gold",
        "emoji": "💰",
        "label": "金",
        "color": "#f2c94c",
        "unit": "usd",
        "industries": [],
        "description": "工業及服務業全年生產毛額（附加價值，新臺幣當年價格），110 年工業及服務業普查，依企業單位"
        "登記縣市計。臺灣沒有官方的縣市 GDP，這是最接近的公開數據；兩個限制：不含農業與政府部門，"
        "多據點企業全部算在登記地（例如半導體廠的附加價值歸到總部所在縣市）。",
    },
    {
        "key": "science",
        "icon": "y-science",
        "emoji": "🔬",
        "label": "科學",
        "color": "#4fa3e0",
        "unit": "workers",
        "industries": ["professional", "information"],
        "description": f"專業、科學及技術服務業與出版影音及資通訊業就業人數（{LABOR_SRC}）。",
    },
    {
        "key": "culture",
        "icon": "y-culture",
        "emoji": "🎭",
        "label": "文化",
        "color": "#b07ce0",
        "unit": "workers",
        "industries": ["arts"],
        "description": f"藝術、娛樂及休閒服務業就業人數（{LABOR_SRC}）。",
    },
]


def industries(labor: dict | None) -> dict[str, int | None]:
    """Employed people per industry key from a dgbas_labor record; None where the survey has no figure."""
    jobs = (labor or {}).get("jobs")
    out = {}
    for key, (sections, _) in INDUSTRIES.items():
        vals = [jobs.get(s) for s in sections] if jobs else [None]
        out[key] = None if any(v is None for v in vals) else int(sum(vals))
    return out


def economy(population: int | None, labor: dict | None, census: dict | None, gdp_year: int | None) -> dict:
    """Yields + economic profile of one area (a county, or the nation).

    `labor` is a dgbas_labor record ({employed, jobs, unemployment}) or None (Kinmen, Lienchiang);
    `census` is an ics_census record ({value_added, persons}) or None.
    """
    jobs = industries(labor)
    gdp = (census or {}).get("value_added")
    yields = {}
    for y in YIELDS:
        if y["key"] == "gold":
            yields["gold"] = gdp
        else:
            vals = [jobs[k] for k in y["industries"]]
            yields[y["key"]] = None if any(v is None for v in vals) else sum(vals)
    return {
        "population": population,
        "yields": yields,
        "jobs": jobs,
        "employed": (labor or {}).get("employed"),
        # Taiwan has no public median household income, rent or home value by county on a common basis:
        # left null rather than mixing in averages.
        "median_income": None,
        "median_rent": None,
        "home_value": None,
        "unemployment": (labor or {}).get("unemployment"),
        "rent_burden": None,
        "gdp": gdp,
        "gdp_year": gdp_year if gdp is not None else None,
        "gdp_by_industry": None,
        "gdp_undisclosed": None,
        "gdp_estimated": None,
    }
