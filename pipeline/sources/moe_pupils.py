"""Children of new immigrants (新住民子女) among elementary-school pupils, by township (教育部統計處).

Taiwan publishes no nationwide count of foreign-born residents by township. The Ministry of Education does count,
for every township, the pupils with one parent who came from abroad or from mainland China, Hong Kong or Macao.
The denominator is the pupils of all elementary schools in the township, from the school-by-school file.
Both files name townships, which are mapped through tw_boundaries.
"""

from __future__ import annotations

import csv

from ..core.source import Source, SourceInfo
from ._tw_towns import TownIndex

YEAR = 114  # school year 2025-26 (ROC 114學年度)
NI_URL = f"https://stats.moe.gov.tw/files/opendata/{YEAR}son_of_foreign.csv"
SCHOOL_URL = f"https://stats.moe.gov.tw/files/detail/{YEAR}/{YEAR}_basec.csv"
NI_FILE, SCHOOL_FILE = f"{YEAR}son_of_foreign.csv", f"{YEAR}_basec.csv"


def _int(v: str) -> int:
    return int((v or "0").replace(",", "").strip() or 0)


class MoePupils(Source):
    info = SourceInfo(
        id="moe_pupils",
        title="Children of new immigrants in elementary and junior high schools by township; elementary schools",
        publisher="Ministry of Education, Department of Statistics (教育部統計處)",
        homepage="https://data.gov.tw/dataset/146649",
        license="Government Open Data License v1.0",
        description="Pupils of elementary and junior high schools who have a parent from abroad or from mainland "
        "China, Hong Kong or Macao (新住民子女), by the township of the school, and the pupils of every "
        f"elementary school, school year {YEAR + 1911}-{(YEAR + 1912) % 100}. The share of elementary pupils with a "
        "new-immigrant parent stands in for a foreign-born share, which is not published by township.",
        used_for=["Pupils with a new-immigrant parent"],
    )

    def fetch(self, force=False):
        self.download(NI_URL, NI_FILE, force=force)
        self.download(SCHOOL_URL, SCHOOL_FILE, force=force)

    def process(self):
        towns = TownIndex()
        out: dict[str, dict] = {}
        unmatched = set()
        with open(self.raw_dir / NI_FILE, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                g = towns.town(r["縣市別"], r["鄉鎮市區別"])
                if g is None:
                    unmatched.add(r["縣市別"] + r["鄉鎮市區別"])
                    continue
                out[g] = {"ni_elementary": _int(r["國小小計"]), "ni_junior": _int(r["國中小計"]), "elementary_pupils": 0, "schools": 0}
        with open(self.raw_dir / SCHOOL_FILE, newline="", encoding="utf-8-sig") as f:
            rows = csv.reader(f)
            header = next(rows)
            pupil_cols = [i for i, h in enumerate(header) if "學生數" in h]
            ci, ti = header.index("縣市名稱"), header.index("鄉鎮市區")
            for r in rows:
                if len(r) < len(header):
                    continue
                g = towns.town(r[ci], r[ti])
                if g is None:
                    unmatched.add(r[ci] + r[ti])
                    continue
                t = out.setdefault(g, {"ni_elementary": None, "ni_junior": None, "elementary_pupils": 0, "schools": 0})
                t["elementary_pupils"] += sum(_int(r[i]) for i in pupil_cols)
                t["schools"] += 1
        ni = sum(t["ni_elementary"] or 0 for t in out.values())
        pupils = sum(t["elementary_pupils"] for t in out.values())
        print(f"    {len(out)} of {len(towns.codes)} townships; {ni:,} of {pupils:,} elementary pupils have a new-immigrant parent"
              + (f"; unmatched {sorted(unmatched)}" if unmatched else ""))
        return {
            "vintage": f"School year {YEAR + 1911}-{(YEAR + 1912) % 100} (ROC {YEAR})",
            "_files": [NI_FILE, SCHOOL_FILE],
            "school_year": YEAR + 1911,
            "towns": out,
            "unmatched": sorted(unmatched),
        }
