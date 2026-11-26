"""Home sale prices by township, from the actual-price registration of real-estate transactions (實價登錄).

The Ministry of the Interior publishes every registered sale, one zip of CSV files per season (quarter). Each zip has
a manifest naming the county of every file; the sale rows name their township. No address is kept: process() only
counts qualifying sales and takes medians per township.
"""

from __future__ import annotations

import csv
import io
import statistics
import zipfile

from ..core.source import Source, SourceInfo
from ._tw_towns import TownIndex

SEASONS = ["114S4", "115S1", "115S2", "115S3"]  # the four most recent complete seasons: 2025 Q4 - 2026 Q3
URL = "https://plvr.land.moi.gov.tw/DownloadSeason?season={s}&type=zip&fileName=lvr_landcsv.zip"
MAIN_SCHEMA = "schema-main.csv"  # sales of existing property (pre-sale and rental files use other schemas)
SALE_SUFFIX = "不動產買賣"
HOME_TYPES = ("公寓", "華廈", "住宅大樓", "透天厝", "套房")  # walk-up flat, mid-rise, high-rise, townhouse, studio
SPECIAL = "親友、員工、共有人或其他特殊關係"  # the registry's remark for sales between related parties

RULE = ("Sales of existing homes registered in the seasons listed: the transaction includes a building (建物), its "
        "main use is residential (住家用), its type is a walk-up flat, mid-rise or high-rise flat, townhouse or studio, "
        "the total price is above zero, and the registry's remark does not flag a sale between relatives, employees "
        "or co-owners. Pre-sale contracts, land-only and parking-only sales are excluded.")


def _file(season: str) -> str:
    return f"lvr_landcsv_{season}.zip"


class LvrPrices(Source):
    info = SourceInfo(
        id="lvr_prices",
        title="Actual-price registration of real-estate sales (不動產買賣實價登錄批次資料)",
        publisher="Ministry of the Interior, Department of Land Administration (內政部地政司)",
        homepage="https://plvr.land.moi.gov.tw/DownloadOpenData",
        license="Government Open Data License v1.0",
        description="Every registered sale of real estate, published by season. The median total price and the "
        "median price per square metre of home sales in each township over four seasons "
        f"({SEASONS[0]} - {SEASONS[-1]}, ROC year and quarter) are computed from it. " + RULE,
        used_for=["Home sale price"],
    )

    def fetch(self, force=False):
        for s in SEASONS:
            self.download(URL.format(s=s), _file(s), force=force, expect_binary=True)

    def process(self):
        towns = TownIndex()
        totals: dict[str, list[float]] = {}
        units: dict[str, list[float]] = {}
        seen: set[str] = set()
        unmatched: dict[str, int] = {}
        rows_read = 0
        for s in SEASONS:
            with zipfile.ZipFile(self.raw_dir / _file(s)) as z:
                manifest = csv.DictReader(io.StringIO(z.read("manifest.csv").decode("utf-8-sig")))
                for m in manifest:
                    if m["schema"] != MAIN_SCHEMA or not m["description"].endswith(SALE_SUFFIX):
                        continue
                    county = m["description"][: -len(SALE_SUFFIX)]
                    rows = csv.reader(io.StringIO(z.read(m["name"]).decode("utf-8-sig")))
                    col = {h: i for i, h in enumerate(next(rows))}
                    next(rows, None)  # the English header line
                    for r in rows:
                        if len(r) < len(col):
                            continue
                        rows_read += 1
                        if (r[col["編號"]] in seen or "建物" not in r[col["交易標的"]] or r[col["主要用途"]] != "住家用"
                                or not r[col["建物型態"]].startswith(HOME_TYPES) or SPECIAL in r[col["備註"]]):
                            continue
                        try:
                            total = float(r[col["總價元"]])
                        except ValueError:
                            continue
                        if total <= 0:
                            continue
                        seen.add(r[col["編號"]])
                        g = towns.town(county, r[col["鄉鎮市區"]])
                        if g is None and r[col["鄉鎮市區"]] == county and towns.county(county):
                            # 新竹市 and 嘉義市 register sales for the whole city, without the district
                            g = "county:" + towns.county(county)
                        if g is None:
                            key = county + r[col["鄉鎮市區"]]
                            unmatched[key] = unmatched.get(key, 0) + 1
                            continue
                        totals.setdefault(g, []).append(total)
                        try:
                            unit = float(r[col["單價元平方公尺"]])
                        except ValueError:
                            unit = 0
                        if unit > 0:
                            units.setdefault(g, []).append(unit)
        stats = {
            g: {"sales": len(v), "median_total": round(statistics.median(v)),
                "median_per_m2": round(statistics.median(units[g])) if units.get(g) else None}
            for g, v in totals.items()
        }
        out = {g: v for g, v in stats.items() if not g.startswith("county:")}
        citywide = {g.split(":")[1]: v for g, v in stats.items() if g.startswith("county:")}
        print(f"    {rows_read:,} sale rows, {len(seen):,} qualifying home sales in {len(out)} of {len(towns.codes)} townships"
              f" and {len(citywide)} cities registered without districts ({sorted(citywide)})"
              + (f"; unmatched {unmatched}" if unmatched else ""))
        return {
            "vintage": f"Registered sales, seasons {SEASONS[0]} - {SEASONS[-1]} (2025 Q4 - 2026 Q3)",
            "_files": [_file(s) for s in SEASONS],
            "seasons": SEASONS,
            "rule": RULE,
            "towns": out,
            "citywide": citywide,  # COUNTYCODE → the same statistics for cities whose sales carry no district
            "unmatched": unmatched,
        }
