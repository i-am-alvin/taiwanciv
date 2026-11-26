"""Income on individual income tax returns by county (綜稅總所得各縣市申報統計分析表, table 8-1).

The county twin of mof_income (which is by township). Note the base differs: this table counts the total income
(總所得) of filed returns, the township table the 綜合所得總額 of all tax units with income records, so the two medians
do not reconcile and are never mixed in one view.
"""

from __future__ import annotations

import csv
import json
import re

from ..core.source import Source, SourceInfo
from ..core.store import load_interim
from .tw_boundaries import official

DATASET = 17963
META = f"https://data.gov.tw/api/v2/rest/dataset/{DATASET}"
META_FILE = f"dataset_{DATASET}.json"
YEAR_IN_URL = re.compile(r"/(\d{3})_8-1\.csv$")


class MofCountyIncome(Source):
    info = SourceInfo(
        id="mof_county_income",
        title="Income tax returns by county: median income per tax unit (綜稅總所得各縣市申報統計分析表)",
        publisher="Ministry of Finance, Fiscal Information Agency (財政部財政資訊中心)",
        homepage=f"https://data.gov.tw/dataset/{DATASET}",
        license="Government Open Data License v1.0",
        description="Median total income (總所得) per tax unit (a filer with spouse and dependants) on the income tax "
        "returns filed in each county, the newest income year in the dataset. Not household income: tax-exempt "
        "income and government transfers are not included, and people who need not file are not counted.",
        used_for=["Median income of cities, counties and the nation"],
    )

    def _latest(self) -> tuple[int, str]:
        meta = json.loads((self.raw_dir / META_FILE).read_text(encoding="utf-8"))
        years = {int(m.group(1)): d["resourceDownloadUrl"] for d in meta["result"]["distribution"]
                 if (m := YEAR_IN_URL.search(d.get("resourceDownloadUrl") or ""))}
        if not years:
            raise ValueError(f"data.gov.tw dataset {DATASET}: no 8-1 CSV resources")
        y = max(years)
        return y, years[y]

    def fetch(self, force=False):
        self.download(META, META_FILE, force=force)
        y, url = self._latest()
        self.download(url, f"{y}_8-1.csv", force=force)

    def process(self):
        y, _ = self._latest()
        name = f"{y}_8-1.csv"
        fips_of = {s["name"]: s["fips"] for s in load_interim("tw_boundaries")["states"]}
        counties, nation, other = {}, None, []
        with open(self.raw_dir / name, newline="", encoding="utf-8-sig") as f:
            rows = csv.reader(f)
            header = [h.strip().lstrip("﻿") for h in next(rows)]
            i_name, i_units, i_med = header.index("縣市別"), header.index("納稅單位(戶)"), header.index("中位數")
            for r in rows:
                if len(r) <= i_med:
                    continue
                area = official(r[i_name].strip())
                rec = {"units": int(r[i_units].replace(",", "")), "median": round(float(r[i_med].replace(",", "")) * 1000)}
                if area in fips_of:
                    counties[fips_of[area]] = rec
                elif area in ("全國", "總計", "合計"):
                    nation = rec
                else:
                    other.append(area)
        if len(counties) != 22:
            raise ValueError(f"expected 22 counties, got {len(counties)} (unmatched {other})")
        print(f"    income year {y + 1911}: 22 counties; nation median "
              f"{nation['median'] if nation else None}" + (f"; other rows {other}" if other else ""))
        return {
            "vintage": f"Income year {y + 1911} (ROC {y})",
            "_files": [META_FILE, name],
            "year": y + 1911,
            "nation": nation,
            "counties": counties,
        }
