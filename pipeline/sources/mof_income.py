"""Income reported on individual income tax returns, by township: the Ministry of Finance village table (165-9).

The file lists every village and, for each township, a 合計 (total) row with the number of tax units, their total
income, and the mean, median and quartiles of income per tax unit, in thousands of NT$. Only the 合計 rows are
used: a township's median is the Ministry's own, not a median of village medians.
"""

from __future__ import annotations

import csv
import json
import re

from ..core.source import Source, SourceInfo
from ._tw_towns import TownIndex

DATASET = 103066  # data.gov.tw: 綜稅綜合所得總額全國各縣市鄉鎮村里統計分析表
META = f"https://data.gov.tw/api/v2/rest/dataset/{DATASET}"
META_FILE = f"dataset_{DATASET}.json"
YEAR_IN_URL = re.compile(r"/(\d{3})_165-9\.csv$")
COLUMNS = {"units": "納稅單位(戶)", "total": "綜合所得總額", "mean": "平均數", "median": "中位數",
           "q1": "第一分位數", "q3": "第三分位數"}


class MofIncome(Source):
    info = SourceInfo(
        id="mof_income",
        title="Individual income tax statistics by township and village (綜合所得稅所得總額統計分析表 165-9)",
        publisher="Ministry of Finance, Fiscal Information Agency (財政部財政資訊中心)",
        homepage=f"https://data.gov.tw/dataset/{DATASET}",
        license="Government Open Data License v1.0",
        description="Assessed individual income tax returns by township: number of tax units (a filer with spouse "
        "and dependants), total income, and the mean, median and quartiles of income per tax unit. Income that is "
        "tax-exempt or taxed separately, and government transfers, are not included, and people who need not file "
        "are not counted. The newest income year in the dataset is used.",
        used_for=["Median income", "Lower-quartile income"],
    )

    def _latest(self) -> tuple[int, str]:
        meta = json.loads((self.raw_dir / META_FILE).read_text(encoding="utf-8"))
        years = {}
        for d in meta["result"]["distribution"]:
            m = YEAR_IN_URL.search(d.get("resourceDownloadUrl") or "")
            if m:
                years[int(m.group(1))] = d["resourceDownloadUrl"]
        if not years:
            raise ValueError(f"data.gov.tw dataset {DATASET}: no 165-9 CSV resources")
        y = max(years)
        return y, years[y]

    def fetch(self, force=False):
        self.download(META, META_FILE, force=force)
        y, url = self._latest()
        self.download(url, f"{y}_165-9.csv", force=force)

    def process(self):
        y, _ = self._latest()
        name = f"{y}_165-9.csv"
        towns = TownIndex()
        out, unmatched = {}, []
        with open(self.raw_dir / name, newline="", encoding="utf-8-sig") as f:
            rows = csv.reader(f)
            header = [h.strip().lstrip("﻿") for h in next(rows)]
            col = {k: header.index(v) for k, v in COLUMNS.items()}
            for r in rows:
                if len(r) < len(header) or r[1].strip() != "合計":
                    continue
                g = towns.full(r[0])
                if g is None:
                    unmatched.append(r[0])
                    continue
                rec = {k: float(r[i].replace(",", "")) for k, i in col.items()}
                if not rec["units"]:
                    continue  # no returns: no statistics
                # The file is in thousands of NT$.
                out[g] = {"units": int(rec["units"]), **{k: round(rec[k] * 1000) for k in COLUMNS if k != "units"}}
        print(f"    income year {y + 1911}: {len(out)} of {len(towns.codes)} townships"
              + (f"; unmatched {unmatched}" if unmatched else ""))
        return {
            "vintage": f"Income year {y + 1911} (ROC {y})",
            "_files": [META_FILE, name],
            "year": y + 1911,
            "towns": out,
            "unmatched": unmatched,
        }
