"""Age, education, indigenous status and deaths of every township, from the household registration (內政部戶政司).

Village tables (ODRP014 single-year age, ODRP020 education, ODRP013 indigenous status) carry an 11-digit
district_code whose first 8 digits are the TOWNCODE; they are summed to townships on that code. The deaths table
(ODRP031) is by township name and is mapped through tw_boundaries.
"""

from __future__ import annotations

import json

from ..core.source import Source, SourceInfo
from ._tw_towns import TownIndex

URL = "https://www.ris.gov.tw/rs-opendata/api/v1/datastore/{ds}/{period}?page={p}"
YEAR = 114  # ROC year of the year-end tables (2025)
DEATH_YEARS = [112, 113, 114]  # deaths are pooled over three years (2023-2025)
MID_YEAR = 113  # the population exposed to those deaths: year-end of the middle year
# (dataset, period): single-year age at the end of YEAR and of MID_YEAR, education, indigenous status, deaths.
TABLES = (
    [("ODRP014", f"{YEAR}12"), ("ODRP014", f"{MID_YEAR}12"), ("ODRP020", str(YEAR)), ("ODRP013", f"{YEAR}12")]
    + [("ODRP031", str(y)) for y in DEATH_YEARS]
)
AGES = [f"{a:03d}" for a in range(100)] + ["100up"]
# Holding a bachelor's degree or more: university graduates plus everyone who entered a master's or doctoral
# programme (they hold a bachelor's whether or not they finished the higher degree).
DEGREE = ["edu_university_graduated", "edu_master_graduated", "edu_master_ungraduated",
          "edu_doctor_graduated", "edu_doctor_ungraduated"]


def _int(v) -> int:
    return int(str(v).replace(",", "").strip() or 0)


def _death_row(r: dict) -> tuple[str, dict]:
    """(township name, {"m": [101 counts], "f": [...]}) of an ODRP031 row; the API serves two key layouts."""
    if "site_id" in r:
        return r["site_id"], {s: [_int(r[f"death_age_{a}_{s}"]) for a in AGES] for s in "mf"}
    keys = [f"{a}歲" for a in range(100)] + ["100歲以上"]
    return r["區域別"], {s: [_int(r[f"{k}_{z}_人數"]) for k in keys] for s, z in (("m", "男"), ("f", "女"))}


def median_age(hist: list[int]) -> float | None:
    """Median of a single-year age histogram, interpolated inside the median year of age (last bin = 100+)."""
    total = sum(hist)
    if not total:
        return None
    half, run = total / 2, 0
    for age, n in enumerate(hist):
        if n and run + n >= half:
            return age + (half - run) / n
        run += n
    return None


class RisDemographics(Source):
    info = SourceInfo(
        id="ris_demographics",
        title="Age, education, indigenous status and deaths by township (ODRP014, ODRP020, ODRP013, ODRP031)",
        publisher="Ministry of the Interior, Department of Household Registration (內政部戶政司)",
        homepage="https://www.ris.gov.tw/rs-opendata/api/Main/docs/v1",
        license="Government Open Data License v1.0",
        description="Household registration tables: residents by single year of age and sex for every village, "
        f"registered education of residents aged 15 and over, indigenous status (all at the end of {YEAR + 1911}), "
        f"and deaths by single year of age and sex for every township in {DEATH_YEARS[0] + 1911}-"
        f"{DEATH_YEARS[-1] + 1911}. Villages are summed to their township. The median age, the share with a "
        "university degree, the indigenous share and an age-standardised mortality ratio are computed from them.",
        used_for=["Median age", "University degrees", "Indigenous share", "Wellbeing (standardised mortality)", "Households"],
    )

    def _file(self, ds: str, period: str, p: int) -> str:
        return f"{ds}_{period}_p{p}.json"

    def fetch(self, force=False):
        for ds, period in TABLES:
            p = 1
            while True:
                path = self.download(URL.format(ds=ds, period=period, p=p), self._file(ds, period, p), force=force)
                head = json.loads(path.read_text(encoding="utf-8"))
                if "responseData" not in head:
                    self.discard(self._file(ds, period, p))
                    raise RuntimeError(f"{ds}/{period} page {p}: {head.get('responseMessage')}")
                if p >= int(head.get("totalPage") or 1):
                    break
                p += 1

    def _rows(self, ds: str, period: str, files: list[str]):
        p = 1
        while (self.raw_dir / self._file(ds, period, p)).exists():
            files.append(self._file(ds, period, p))
            yield from json.loads((self.raw_dir / self._file(ds, period, p)).read_text(encoding="utf-8"))["responseData"]
            p += 1

    def _age_table(self, period: str, towns: TownIndex, files: list[str]) -> dict[str, dict]:
        """TOWNCODE → {"m": [101 counts], "f": [...], "households": n} from the village single-year age table."""
        out = {g: {"m": [0] * len(AGES), "f": [0] * len(AGES), "households": 0} for g in towns.codes}
        for r in self._rows("ODRP014", period, files):
            t = out.get(r["district_code"][:8])
            if t is None:
                continue  # Pratas and the Spratlys are not on the map
            t["households"] += _int(r["household_no"])
            for i, a in enumerate(AGES):
                t["m"][i] += _int(r[f"people_age_{a}_m"])
                t["f"][i] += _int(r[f"people_age_{a}_f"])
        return out

    def process(self):
        towns = TownIndex()
        files: list[str] = []
        now = self._age_table(f"{YEAR}12", towns, files)
        mid = self._age_table(f"{MID_YEAR}12", towns, files)
        empty = [g for g in towns.codes if not sum(now[g]["m"]) + sum(now[g]["f"])]
        if empty:
            raise ValueError(f"{len(empty)} townships have no residents in ODRP014/{YEAR}12: {empty[:5]}")

        edu = {g: {"pop15": 0, "degree": 0} for g in towns.codes}
        for r in self._rows("ODRP020", str(YEAR), files):
            t = edu.get(r["district_code"][:8])
            if t is not None:
                t["pop15"] += _int(r["edu_age_15up_total"])
                t["degree"] += sum(_int(r[f"{k}_{s}"]) for k in DEGREE for s in "mf")

        ind = {g: {"pop": 0, "plain": 0, "mountain": 0} for g in towns.codes}
        for r in self._rows("ODRP013", f"{YEAR}12", files):
            t = ind.get(r["district_code"][:8])
            if t is not None:
                t["pop"] += _int(r["people_total"])
                t["plain"] += _int(r["indigenous_plain_total_m"]) + _int(r["indigenous_plain_total_f"])
                t["mountain"] += _int(r["indigenous_mountain_total_m"]) + _int(r["indigenous_mountain_total_f"])

        # Deaths, year by year. The national death rate of each sex and single year of age (all townships with a
        # row that year together) applied to a township's own mid-period population gives its expected deaths
        # (indirect standardisation). A township missing from a year's table is left out of that year on both
        # sides (ODRP031/113 has no row for 新北市板橋區).
        observed = {g: 0 for g in towns.codes}
        expected = {g: 0.0 for g in towns.codes}
        death_years = {g: 0 for g in towns.codes}
        unmatched, missing = set(), {}
        for y in DEATH_YEARS:
            year: dict[str, dict] = {}
            for r in self._rows("ODRP031", str(y), files):
                site, d = _death_row(r)
                g = towns.full(site)
                if g is None:
                    unmatched.add(site)
                else:
                    year[g] = d
            if len(year) != len(towns.codes):
                missing[str(y + 1911)] = sorted(towns.county_name[towns.county_of[g]] + towns.name[g]
                                                for g in towns.codes if g not in year)
            for s in "mf":
                rate = []
                for i in range(len(AGES)):
                    exposed = sum(mid[g][s][i] for g in year)
                    rate.append(sum(d[s][i] for d in year.values()) / exposed if exposed else 0.0)
                for g, d in year.items():
                    observed[g] += sum(d[s])
                    expected[g] += sum(rate[i] * mid[g][s][i] for i in range(len(AGES)))
            for g in year:
                death_years[g] += 1
        if any(len(v) > 5 for v in missing.values()):
            raise ValueError(f"ODRP031: too many townships without a row: { {y: len(v) for y, v in missing.items()} }")

        out = {}
        for g in towns.codes:
            hist = [m + f for m, f in zip(now[g]["m"], now[g]["f"])]
            pop = sum(hist)
            out[g] = {
                "pop": pop,
                "households": now[g]["households"],
                "median_age": round(median_age(hist), 2),
                "age_0_14": sum(hist[:15]), "age_15_64": sum(hist[15:65]), "age_65_up": sum(hist[65:]),
                "pop15": edu[g]["pop15"], "degree": edu[g]["degree"],
                "indigenous_pop": ind[g]["pop"], "indigenous_plain": ind[g]["plain"], "indigenous_mountain": ind[g]["mountain"],
                "deaths": observed[g], "deaths_expected": round(expected[g], 2), "death_years": death_years[g],
            }
        total = sum(t["pop"] for t in out.values())
        print(f"    {len(out)} townships; {total:,} residents at the end of {YEAR + 1911}; "
              f"{sum(t['deaths'] for t in out.values()):,} deaths {DEATH_YEARS[0] + 1911}-{DEATH_YEARS[-1] + 1911}"
              + (f"; unmatched death rows: {sorted(unmatched)}" if unmatched else "")
              + (f"; no deaths row: {missing}" if missing else ""))
        return {
            "vintage": f"Household registration, end of {YEAR + 1911}; deaths {DEATH_YEARS[0] + 1911}-{DEATH_YEARS[-1] + 1911}",
            "_files": files,
            "year": YEAR + 1911,
            "death_years": [y + 1911 for y in DEATH_YEARS],
            "deaths_missing": missing,
            "towns": out,
        }
