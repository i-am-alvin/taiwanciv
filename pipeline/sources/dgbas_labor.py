"""Employed people by industry and the unemployment rate of each county, from the Manpower Survey (人力資源調查).

The annual report of the survey has county tables: table 33 (就業者之行業, thousands of people in each of the 19
sections of the Standard Industrial Classification) and table 26 (重要指標, including the unemployment rate). The
survey covers the Taiwan area (Taiwan and Penghu); Kinmen and Lienchiang are not sampled.
"""

from __future__ import annotations

import re

from ..core.source import Source, SourceInfo
from ..core.store import load_interim
from ._resource_util import xlsx_rows
from .tw_boundaries import official

ROC_YEAR = 114  # 2025 annual averages
REPORT = "https://www.stat.gov.tw/News_Content.aspx?n=4001&s=236078"
BASE = "https://ws.dgbas.gov.tw/001/Upload/463/relfile/11516/236078"
TABLES = {"industry": "table33.xlsx", "indicators": "table26.xlsx"}

# Standard Industrial Classification (rev. 11) sections as table 33 heads them (whitespace removed) → key.
SECTIONS = {
    "農、林、漁、牧業": ("agriculture", "Agriculture, forestry, fishing & animal husbandry"),
    "礦業及土石採取業": ("mining", "Mining & quarrying"),
    "製造業": ("manufacturing", "Manufacturing"),
    "電力及燃氣供應業": ("power", "Electricity & gas supply"),
    "用水供應及污染整治業": ("water", "Water supply & remediation"),
    "營建工程業": ("construction", "Construction"),
    "批發及零售業": ("trade", "Wholesale & retail trade"),
    "運輸及倉儲業": ("transportation", "Transportation & storage"),
    "住宿及餐飲業": ("accommodation", "Accommodation & food services"),
    "出版影音及資通訊業": ("information", "Publishing, audiovisual, information & communication"),
    "金融及保險業": ("finance", "Finance & insurance"),
    "不動產業": ("real_estate", "Real estate"),
    "專業、科學及技術服務業": ("professional", "Professional, scientific & technical services"),
    "支援服務業": ("support", "Support services"),
    "公共行政及國防；強制性社會安全": ("public_admin", "Public administration & defence; compulsory social security"),
    "教育業": ("education", "Education"),
    "醫療保健及社會工作服務業": ("health", "Human health & social work"),
    "藝術、娛樂及休閒服務業": ("arts", "Arts, entertainment & recreation"),
    "其他服務業": ("other", "Other services"),
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _value(text: str) -> float | None:
    """DGBAS notation: '-' = none (0), '…' = not available."""
    t = (text or "").strip()
    if t in ("-", "－"):
        return 0.0
    try:
        return float(t)
    except ValueError:
        return None


def _area(cell: str) -> str:
    """'臺北市 Taipei City' → '臺北市'."""
    return official(_clean(cell.split(" ")[0] if " " in cell else re.sub(r"[A-Za-z ,.()-]+$", "", cell)))


class DgbasLabor(Source):
    info = SourceInfo(
        id="dgbas_labor",
        title=f"Manpower Survey, {ROC_YEAR + 1911} annual report: employed people by industry and county",
        publisher="Directorate-General of Budget, Accounting and Statistics (主計總處), Executive Yuan",
        homepage=REPORT,
        license="Government Open Data License v1.0",
        description=f"Annual averages for {ROC_YEAR + 1911}: employed people (thousands) in each of the 19 industry "
        "sections, counted where they live (table 33), and the unemployment rate (table 26), for the 20 counties "
        "and cities of the Taiwan area. Kinmen and Lienchiang are not covered by the survey, so their jobs are null.",
        used_for=["Food, Production, Science and Culture yields (workers by industry)", "Unemployment rate"],
    )

    def fetch(self, force=False):
        for name in TABLES.values():
            self.download(f"{BASE}/{name}", name, force=force, expect_binary=True)

    def _county_rows(self, path):
        """(area name, row) for each data row of the first block (the thousands, before the % repeat)."""
        seen_data = False
        for row in xlsx_rows(path):
            name = row.get("B", "")
            if "續" in name and seen_data:
                break
            if re.match(r"^[一-鿿　 ]+[A-Za-z]", name or "") and any(_value(v) is not None for k, v in row.items() if k != "B"):
                seen_data = True
                yield _area(name), row

    def process(self):
        b = load_interim("tw_boundaries")
        fips_of = {s["name"]: s["fips"] for s in b["states"]}
        ind_path = self.raw_dir / TABLES["industry"]
        # Column of each section: the head row names it once; its first column is the section total.
        cols: dict[str, str] = {}
        total_col = None
        for row in xlsx_rows(ind_path):
            for col, text in row.items():
                t = _clean(text)
                for zh, (key, _) in SECTIONS.items():
                    if t == _clean(zh) or (len(t) >= 8 and _clean(zh).startswith(t)):
                        cols.setdefault(key, col)
                if t == "總計" and total_col is None:
                    total_col = col
            if len(cols) == len(SECTIONS):
                break
        if len(cols) != len(SECTIONS) or total_col is None:
            raise ValueError(f"table 33 layout changed: found {sorted(cols)} and total {total_col}")

        counties: dict[str, dict] = {}
        nation = None
        for area, row in self._county_rows(ind_path):
            jobs = {k: (None if (v := _value(row.get(c, ""))) is None else round(v * 1000)) for k, c in cols.items()}
            rec = {"employed": None if _value(row.get(total_col, "")) is None else round(_value(row[total_col]) * 1000),
                   "jobs": jobs}
            if area == "臺灣地區":
                nation = rec
            elif area in fips_of:
                counties[fips_of[area]] = rec

        ind_path2 = self.raw_dir / TABLES["indicators"]
        unemp_col = None
        for row in xlsx_rows(ind_path2):
            for col, text in row.items():
                if _clean(text).startswith("失業率"):
                    unemp_col = col
                    break
            if unemp_col:
                break
        if unemp_col is None:
            raise ValueError("table 26 layout changed: no 失業率 column")
        for area, row in self._county_rows(ind_path2):
            rate = _value(row.get(unemp_col, ""))
            rate = round(rate / 100, 4) if rate is not None else None
            if area == "臺灣地區" and nation is not None:
                nation["unemployment"] = rate
            elif area in fips_of and fips_of[area] in counties:
                counties[fips_of[area]]["unemployment"] = rate

        if nation is None or len(counties) != 20:
            raise ValueError(f"expected the Taiwan area and 20 counties, got {len(counties)}")
        print(f"    {len(counties)} counties; Taiwan area employed {nation['employed']:,}, "
              f"unemployment {nation.get('unemployment')}")
        return {
            "vintage": f"Manpower Survey {ROC_YEAR + 1911} annual averages (DGBAS)",
            "_files": list(TABLES.values()),
            "year": ROC_YEAR + 1911,
            "sections": {key: {"zh": zh, "en": en} for zh, (key, en) in SECTIONS.items()},
            "nation": nation,
            "counties": counties,
        }
