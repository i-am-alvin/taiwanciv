"""Population of every township (鄉鎮市區) at the end of each year, from the household registration (內政部戶政司)."""

from __future__ import annotations

import json

from ..core.source import Source, SourceInfo
from ..core.store import load_interim
from .tw_boundaries import official

DATASET = "ODRP048"  # 人口密度: year-end population and land area of each township
ROC_YEARS = list(range(109, 115))  # 2020 … 2025
URL = "https://www.ris.gov.tw/rs-opendata/api/v1/datastore/{ds}/{y}?page={p}"
OUTSIDE_MAP = {"東沙群島", "南沙群島"}  # listed on their own; outside the map window (see tw_boundaries)


def _int(text: str) -> int | None:
    try:
        return int(text.replace(",", ""))
    except (AttributeError, ValueError):
        return None


class RisPopulation(Source):
    info = SourceInfo(
        id="ris_population",
        title="Population and land area of each township, year-end (ODRP048)",
        publisher="Ministry of the Interior, Department of Household Registration (內政部戶政司)",
        homepage="https://www.ris.gov.tw/app/portal/346",
        license="Government Open Data License v1.0",
        description="Registered population at the end of each year (2020-2025) and land area for the 368 townships "
        "and districts (鄉鎮市區). City and county totals are sums of their townships; growth compares the "
        "end of 2021 with the end of 2025 on today's boundaries.",
        used_for=["City and county population", "Population growth 2021-2025", "Township population and area"],
    )

    def _file(self, y: int, p: int) -> str:
        return f"{DATASET}_{y}_p{p}.json"

    def fetch(self, force=False):
        for y in ROC_YEARS:
            p = 1
            while True:
                path = self.download(URL.format(ds=DATASET, y=y, p=p), self._file(y, p), force=force)
                head = json.loads(path.read_text(encoding="utf-8"))
                if p >= int(head.get("totalPage") or 1):
                    break
                p += 1

    def process(self):
        b = load_interim("tw_boundaries")
        county_name = {s["fips"]: s["name"] for s in b["states"]}
        code_of = {county_name[t["state_fips"]] + t["name"]: t["geoid"] for t in b["counties"]}
        years = [y + 1911 for y in ROC_YEARS]
        towns: dict[str, dict] = {g: {"pop": [None] * len(years), "area_km2": None} for g in code_of.values()}
        files = []
        for k, y in enumerate(ROC_YEARS):
            p = 1
            while (self.raw_dir / self._file(y, p)).exists():
                files.append(self._file(y, p))
                data = json.loads((self.raw_dir / self._file(y, p)).read_text(encoding="utf-8"))
                for r in data.get("responseData", []):
                    site = official(r["site_id"].strip())
                    if site in OUTSIDE_MAP:
                        continue
                    geoid = code_of.get(site)
                    if geoid is None:
                        raise ValueError(f"ROC {y}: township {site!r} not in tw_boundaries")
                    towns[geoid]["pop"][k] = _int(r["people_total"])
                    if k == len(ROC_YEARS) - 1:
                        try:
                            towns[geoid]["area_km2"] = round(float(r["area"]), 4)
                        except ValueError:
                            pass
                p += 1
        missing = [g for g, t in towns.items() if t["pop"][-1] is None]
        if missing:
            raise ValueError(f"{len(missing)} townships without a {years[-1]} population: {missing[:5]}")

        def total(geoids):
            return [None if any(towns[g]["pop"][k] is None for g in geoids) else sum(towns[g]["pop"][k] for g in geoids)
                    for k in range(len(years))]

        counties = {fips: total([t["geoid"] for t in b["counties"] if t["state_fips"] == fips]) for fips in county_name}
        nation = total(list(towns))
        print(f"    {len(towns)} townships; {years[-1]} total {nation[-1]:,}")
        return {
            "vintage": f"Household registration, year-end {years[0]}-{years[-1]} ({DATASET})",
            "_files": files,
            "years": years,
            "towns": towns,
            "counties": counties,
            "nation": nation,
        }
