"""Land use of every township from the national Land Use Investigation (國土利用現況調查), level-3 classes.

One CSV row per township with the area in hectares of each of the 93 level-3 classes of the 2019 (108年版)
classification. A class code has six digits: the first two are the level-1 class (01 agriculture, 02 forest,
03 transport, 04 water, 05 built-up, 06 public facilities, 07 recreation, 08 mining and salt, 09 other).
"""

from __future__ import annotations

import csv
import json
import re

from ..core.source import Source, SourceInfo
from ._tw_towns import TownIndex

DATASET = 178038  # data.gov.tw: 113-114年國土利用現況調查成果鄉鎮市區統計資料 (3級分類)
META = f"https://data.gov.tw/api/v2/rest/dataset/{DATASET}"
META_FILE = f"dataset_{DATASET}.json"
FILE = "landuse_township_113_114.csv"
CLASS = re.compile(r"^(.+?)(\d{6})用地面積$")


class NlscLanduse(Source):
    info = SourceInfo(
        id="nlsc_landuse",
        title="Land Use Investigation 2024-2025, township statistics (113-114年國土利用現況調查成果鄉鎮市區統計資料)",
        publisher="Ministry of the Interior, National Land Surveying and Mapping Center (內政部國土測繪中心)",
        homepage=f"https://data.gov.tw/dataset/{DATASET}",
        license="Government Open Data License v1.0",
        description="Area of each of the 93 level-3 land-use classes in every township, from the national Land Use "
        "Investigation surveyed in 2024-2025 (2019 classification). The shares of forest, farmland and built-up "
        "land of each township are computed from it, as shares of the township's whole surveyed area.",
        used_for=["Forest share", "Farmland share", "Built-up share"],
    )

    def fetch(self, force=False):
        self.download(META, META_FILE, force=force)
        meta = json.loads((self.raw_dir / META_FILE).read_text(encoding="utf-8"))
        urls = [d["resourceDownloadUrl"] for d in meta["result"]["distribution"] if (d.get("resourceFormat") or "").upper() == "CSV"]
        if not urls:
            raise ValueError(f"data.gov.tw dataset {DATASET}: no CSV resource")
        self.download(urls[0], FILE, force=force)

    def process(self):
        towns = TownIndex()
        out, unmatched, classes = {}, [], {}
        with open(self.raw_dir / FILE, newline="", encoding="utf-8-sig") as f:
            rows = csv.reader(f)
            header = next(rows)
            cols = []
            for i, h in enumerate(header):
                m = CLASS.match(h.strip())
                if m:
                    cols.append((i, m.group(2)))
                    classes[m.group(2)] = m.group(1)
            unit_col = header.index("面積單位")
            for r in rows:
                if len(r) < len(header):
                    continue
                if r[unit_col].strip() != "公頃":
                    raise ValueError(f"unexpected area unit {r[unit_col]!r}")
                g = towns.town(r[0], r[1])
                if g is None:
                    unmatched.append(r[0] + r[1])
                    continue
                out[g] = {code: float(r[i] or 0) for i, code in cols}
        print(f"    {len(out)} of {len(towns.codes)} townships, {len(classes)} classes" + (f"; unmatched {unmatched}" if unmatched else ""))
        return {
            "vintage": "Land Use Investigation 2024-2025 (ROC 113-114)",
            "_files": [META_FILE, FILE],
            "unit": "ha",
            "classes": classes,  # six-digit code → class name
            "towns": out,  # TOWNCODE → {code: hectares}
            "unmatched": unmatched,
        }
