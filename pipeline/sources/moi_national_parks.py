"""Visits to, and the area of, each national park and national nature park (內政部統計處, 內政統計查詢網)."""

from __future__ import annotations

from ..core.source import Source, SourceInfo
from . import _moi_statis as statis

VISITS = "c0820401"  # 國家(自然)公園遊憩據點遊客人次及車輛次─按國家公園別分 (data.gov.tw dataset 13476)
AREA = "c0820101"  # 國家(自然)公園面積─按國家公園別及海陸域別分 (data.gov.tw dataset 13479)
TOTAL = "國家公園總計"
NATURE_PARK = "(國家自然公園)"
LOOKBACK = 4  # how many years back to look for the newest complete year


def full_name(label: str) -> str:
    """The table's short label → the park's name: 墾丁 → 墾丁國家公園, 壽山(國家自然公園) → 壽山國家自然公園."""
    if label.endswith(NATURE_PARK):
        return label[: -len(NATURE_PARK)] + "國家自然公園"
    return label + "國家公園"


class MoiNationalParks(Source):
    info = SourceInfo(
        id="moi_national_parks",
        title="National park visits and area (內政統計查詢網 tables c0820401, c0820101)",
        publisher="Ministry of the Interior, Department of Statistics (內政部統計處), from the National Park Service",
        homepage="https://data.gov.tw/dataset/13476",
        license="Government Open Data License v1.0",
        description="Visitors counted at the recreation sites of each national park and of the Shoushan National "
        "Nature Park in the newest complete year, and each park's land and sea area. Visits are head counts at the "
        "sites each park headquarters reports (1 to 15 sites per park), not unique visitors, so a park with more "
        "counted sites or with city streets inside it counts more.",
        used_for=["National-park wonders: visits and area"],
    )

    def _visits_file(self, roc: int) -> str:
        return f"park_visits_{roc}.csv"

    def _area_file(self, roc: int) -> str:
        return f"park_area_{roc}.csv"

    def _complete(self, roc: int) -> bool:
        """True if the cached visits file has the year's total and its December total."""
        path = self.raw_dir / self._visits_file(roc)
        if not path.exists():
            return False
        _, rows = statis.rows(path)
        tot = [r for r in rows if r["roc"] == roc and r["parts"] == [TOTAL]]
        year = any(r["month"] is None and r["values"][1] for r in tot)
        december = any(r["month"] == 12 and r["values"][1] for r in tot)
        return year and december

    def fetch(self, force=False):
        if self.offline:
            return
        now = statis.roc_year_now()
        for roc in range(now - 1, now - 1 - LOOKBACK, -1):
            ym = f"{roc}00"
            self.download(statis.url(VISITS, cycle=41, fields=7, codes=20, ym=ym, ymt=ym), self._visits_file(roc),
                          force=force)
            if not self._complete(roc):
                self.discard(self._visits_file(roc))  # the year is not complete yet: try the one before
                continue
            self.download(statis.url(AREA, cycle=4, fields=6, codes=20, ym=ym, ymt=ym, extra="&codlst1=111"),
                          self._area_file(roc), force=force)
            return
        raise RuntimeError("no complete year of national-park visits found")

    def process(self):
        years = sorted((int(p.stem.rsplit("_", 1)[1]) for p in self.raw_dir.glob("park_visits_*.csv")), reverse=True)
        roc = next((y for y in years if self._complete(y)), None)
        if roc is None:
            raise FileNotFoundError("no complete national-park visits file: run fetch moi_national_parks")
        _, rows = statis.rows(self.raw_dir / self._visits_file(roc))
        parks: dict[str, dict] = {}
        total = None
        for r in rows:
            if r["roc"] != roc or r["month"] is not None or len(r["parts"]) != 1:
                continue
            sites, visits = r["values"][0], r["values"][1]
            rec = {"label": r["parts"][0], "sites": int(sites) if sites is not None else None,
                   "visits": int(visits) if visits is not None else None, "visits_line": r["line"]}
            if r["parts"][0] == TOTAL:
                total = rec
            else:
                name = full_name(r["parts"][0])
                parks[name] = {"name": name, **rec, "nature_park": r["parts"][0].endswith(NATURE_PARK),
                               "land_km2": None, "sea_km2": None, "area_km2": None, "area_line": None}
        files = [self._visits_file(roc)]
        area_path = self.raw_dir / self._area_file(roc)
        if area_path.exists():
            files.append(self._area_file(roc))
            _, arows = statis.rows(area_path)
            for r in arows:
                if r["roc"] != roc or len(r["parts"]) != 2 or r["parts"][0] == TOTAL:
                    continue
                p = parks.get(full_name(r["parts"][0]))
                key = {"陸域": "land_km2", "海域": "sea_km2"}.get(r["parts"][1])
                if p is None or key is None or r["values"][0] is None:
                    continue
                p[key] = round(r["values"][0] / 100, 2)  # the table is in hectares
                if key == "land_km2":
                    p["area_line"] = r["line"]
            for p in parks.values():
                # "-" in the sea column of an inland park means it has no sea area; the total is then its land.
                if p["land_km2"] is not None:
                    p["area_km2"] = round(p["land_km2"] + (p["sea_km2"] or 0), 2)
        year = roc + 1911
        return {
            "vintage": f"MOI statistics, national park visits {year} (ROC {roc})",
            "_files": files,
            "year": year,
            "roc_year": roc,
            "total": total,
            "parks": sorted(parks.values(), key=lambda p: -(p["visits"] or 0)),
        }
