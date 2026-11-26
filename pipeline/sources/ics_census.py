"""Value added of industry and services by county, from the 2021 Industry and Commerce Census (110年工業及服務業普查).

Taiwan publishes no official GDP by county. The census is the closest public measure: 全年生產毛額 (gross value
added at producer prices, the census twin of GDP) of every enterprise in industry and services. Two caveats the
data itself imposes: an enterprise is counted in the county where it is registered, so a firm with plants in
several counties counts wholly at its seat; and the census leaves out agriculture and government.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from ..core.source import Source, SourceInfo
from ..core.store import load_interim
from .tw_boundaries import official

YEAR = 2021
URL = "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/233406/mp02057a110.xml"  # data.gov.tw dataset 111594
FILE = "mp02057a110.xml"
VALUE_ADDED = "全年生產毛額"
PERSONS = "年底從業員工人數"


def _num(text: str | None) -> float | None:
    try:
        return float((text or "").replace(",", ""))
    except ValueError:
        return None


class IcsCensus(Source):
    info = SourceInfo(
        id="ics_census",
        title=f"Industry and Commerce Census {YEAR}: enterprise units by county",
        publisher="Directorate-General of Budget, Accounting and Statistics (主計總處), Executive Yuan",
        homepage="https://data.gov.tw/dataset/111594",
        license="Government Open Data License v1.0",
        description=f"Gross value added (全年生產毛額, NT$) in {YEAR} of all industry and service enterprises, by the "
        "county where each enterprise is registered. Used as Gold because Taiwan has no official county GDP. It "
        "leaves out agriculture and government, and a firm with sites in several counties counts at its seat.",
        used_for=["Gold (value added by county)"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=False)

    def process(self):
        b = load_interim("tw_boundaries")
        fips_of = {s["name"]: s["fips"] for s in b["states"]}
        root = ET.fromstring((self.raw_dir / FILE).read_bytes())
        counties, nation = {}, None
        for rec in root:
            fields = {c.tag: (c.text or "").strip() for c in rec}
            name = official(re.sub(r"\s|　", "", fields.get("項目別", "")))
            va = next((_num(v) for k, v in fields.items() if k.startswith(VALUE_ADDED)), None)
            persons = next((_num(v) for k, v in fields.items() if k.startswith(PERSONS)), None)
            row = {"value_added": round(va * 1000) if va is not None else None,
                   "persons": round(persons) if persons is not None else None}
            if name == "總計":
                nation = row
            elif name in fips_of:
                counties[fips_of[name]] = row
        if nation is None or len(counties) != 22:
            raise ValueError(f"expected a total and 22 counties, got {len(counties)}")
        s = sum(r["value_added"] for r in counties.values())
        print(f"    22 counties; value added NT${nation['value_added'] / 1e12:.2f} trillion "
              f"(counties sum to {s / nation['value_added']:.4f} of the total)")
        return {
            "vintage": f"Industry and Commerce Census {YEAR} (DGBAS), enterprise units",
            "_files": [FILE],
            "year": YEAR,
            "nation": nation,
            "counties": counties,
        }
