"""Measured mobile broadband speed by township (數位發展部 行動通訊速率量測, fixed-point measurements)."""

from __future__ import annotations

import csv

from ..core.source import Source, SourceInfo
from ._tw_towns import TownIndex

YEAR = 112  # ROC year of the newest township measurement in the dataset (2023)
URL = "https://www-api.moda.gov.tw/OpenData/Files/14088"  # data.gov.tw 161791: 112年定點量測各業者各鄉鎮速率結果
FILE = f"mobile_speed_township_{YEAR}.csv"
DOWN, UP = "下載速率(Mbps)", "上傳速率(Mbps)"


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


class ModaMobileSpeed(Source):
    info = SourceInfo(
        id="moda_mobile_speed",
        title="Mobile broadband speed measurements by township (行動通訊速率量測)",
        publisher="Ministry of Digital Affairs (數位發展部)",
        homepage="https://data.gov.tw/dataset/161791",
        license="CC0 1.0 (public domain dedication)",
        description=f"Download and upload speeds of each mobile operator measured at fixed points in {YEAR + 1911}, "
        "averaged per township by the Ministry. The lens shows the mean download speed over the operators measured "
        "in a township. Townships without measurement points are not in the file.",
        used_for=["Mobile download speed"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force)

    def process(self):
        towns = TownIndex()
        out, unmatched = {}, []
        with open(self.raw_dir / FILE, newline="", encoding="utf-8-sig") as f:
            rows = csv.reader(f)
            header = next(rows)
            down = [i for i, h in enumerate(header) if h.endswith(DOWN)]
            up = [i for i, h in enumerate(header) if h.endswith(UP)]
            for r in rows:
                if len(r) < len(header):
                    continue
                g = towns.town(r[0], r[1])
                if g is None:
                    unmatched.append(r[0] + r[1])
                    continue

                def vals(cols):
                    out_ = []
                    for i in cols:
                        try:
                            out_.append(float(r[i]))
                        except ValueError:
                            pass
                    return out_

                d = vals(down)
                out[g] = {"download_mbps": _mean(d), "upload_mbps": _mean(vals(up)), "operators": len(d)}
        print(f"    {len(out)} of {len(towns.codes)} townships measured" + (f"; unmatched {unmatched}" if unmatched else ""))
        return {
            "vintage": f"Fixed-point measurements, {YEAR + 1911}",
            "_files": [FILE],
            "year": YEAR + 1911,
            "operators": [h[: -len(DOWN)] for h in header if h.endswith(DOWN)],
            "towns": out,
            "unmatched": unmatched,
        }
