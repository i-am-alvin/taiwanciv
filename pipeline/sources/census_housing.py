"""Homes that are lived in and homes that are not, by township, from the 2020 Population and Housing Census."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ..core.source import Source, SourceInfo
from ._tw_towns import TownIndex, norm

URL = "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/231699/mp06235a109.xml"  # data.gov.tw 162052
FILE = "mp06235a109.xml"
# Element name prefix → key. Names are long bilingual labels ending in _宅數.
FIELDS = {
    "按鄉鎮市區別分": "name",
    "總計": "homes",
    "有人經常居住住宅": "occupied",
    "無人經常居住住宅_合計": "unoccupied",
    "無人經常居住住宅_偶爾自住": "occasional",
    "無人經常居住住宅_自住以外用途": "other_use",
    "無人經常居住住宅_目前沒有使用": "not_in_use",
}


class CensusHousing(Source):
    info = SourceInfo(
        id="census_housing",
        title="Use of housing units by township, 2020 Population and Housing Census (各鄉鎮市區住宅使用情形)",
        publisher="Directorate-General of Budget, Accounting and Statistics (主計總處), Executive Yuan",
        homepage="https://data.gov.tw/dataset/162052",
        license="Government Open Data License v1.0",
        description="Housing units in each township at the 2020 census (reference date 8 November 2020): homes "
        "somebody usually lives in, and homes nobody usually lives in (used now and then by the owner, used for "
        "something else such as an office or store room, or not in use). Taiwan publishes no home-ownership rate "
        "by township; the share of homes that are lived in is shown in its place.",
        used_for=["Lived-in homes"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force)

    def process(self):
        towns = TownIndex()
        out, relabelled = {}, []
        county = None
        for rec in ET.parse(self.raw_dir / FILE).getroot():
            row = {}
            for c in rec:
                for prefix, key in FIELDS.items():
                    if c.tag.startswith(prefix):
                        row[key] = (c.text or "").strip()
            label = norm(row.get("name", ""))
            if towns.county(label):
                county = label  # a county total; its townships follow
                continue
            # Township rows read "county + township". The 13 townships of 新竹縣 are printed with the wrong
            # county (宜蘭縣竹北市 ...), so the county comes from the county row above them.
            g = towns.town(county, label[3:]) if county and len(label) > 3 else None
            if g is None:
                continue  # the national total
            if towns.full(label) != g:
                relabelled.append(label)
            out[g] = {k: int(row[k].replace(",", "")) for k in FIELDS.values() if k != "name" and row.get(k, "").replace(",", "").isdigit()}
        print(f"    {len(out)} of {len(towns.codes)} townships; {sum(t.get('homes', 0) for t in out.values()):,} homes"
              + (f"; county taken from the county row for {relabelled}" if relabelled else ""))
        return {
            "vintage": "2020 Population and Housing Census (ROC 109)",
            "_files": [FILE],
            "year": 2020,
            "towns": out,
            "relabelled": relabelled,
        }
