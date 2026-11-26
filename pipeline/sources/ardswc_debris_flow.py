"""Debris-flow potential streams (土石流潛勢溪流) per township, from the Agency of Rural Development and Soil and Water Conservation.

The list gives every designated stream with the county, township and village it mainly lies in. Its AreaCode column
still uses the codes from before the 2010 city-county mergers (臺中市北屯區 = 10019080), so the township is taken
from the county and township names through tw_boundaries.
"""

from __future__ import annotations

import json

from ..core.source import Source, SourceInfo
from ._tw_towns import TownIndex

URL = "https://data.moa.gov.tw/Service/OpenData/FromM/GetDebrisVillInfo.aspx?IsTransData=1&UnitId=019"  # data.gov.tw 7279
FILE = "debris_flow_streams.json"


class ArdswcDebrisFlow(Source):
    info = SourceInfo(
        id="ardswc_debris_flow",
        title="Debris-flow potential streams (土石流潛勢溪流資料)",
        publisher="Ministry of Agriculture, Agency of Rural Development and Soil and Water Conservation (農業部農村發展及水土保持署)",
        homepage="https://data.gov.tw/dataset/7279",
        license="Government Open Data License v1.0",
        description="The official list of streams designated as debris-flow potential streams, each with the "
        "county, township and village it mainly lies in. Counted per township. A township that is not in the list "
        "has no designated stream.",
        used_for=["Debris-flow potential streams per township"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force)

    def process(self):
        towns = TownIndex()
        rows = json.loads((self.raw_dir / FILE).read_text(encoding="utf-8-sig"))
        streams: dict[str, set] = {}
        unmatched = set()
        for r in rows:
            g = towns.town(r.get("County", ""), r.get("Town", ""))
            if g is None:
                unmatched.add((r.get("County") or "") + (r.get("Town") or ""))
                continue
            streams.setdefault(g, set()).add(r["Debrisno"])
        out = {g: len(s) for g, s in streams.items()}
        print(f"    {sum(out.values()):,} streams ({len(rows):,} rows) in {len(out)} townships"
              + (f"; unmatched {sorted(unmatched)}" if unmatched else ""))
        return {
            "vintage": f"{sum(out.values()):,} designated streams, list as downloaded",
            "_files": [FILE],
            "streams": sum(out.values()),
            "towns": out,  # TOWNCODE → number of streams; no entry = none
            "unmatched": sorted(unmatched),
        }
