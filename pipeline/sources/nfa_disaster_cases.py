"""Disaster case reports filed while the Central Emergency Operation Center was open (內政部消防署, EMIC)."""

from __future__ import annotations

import csv
import json
from collections import Counter

from ..core import fetch
from ..core.source import Source, SourceInfo
from ._tw_towns import TownIndex

# One data.gov.tw dataset per ROC year: 「<年>年中央災害應變中心開設期間災情案件資料」.
DATASETS = {111: 173934, 112: 173935, 113: 173936}
META_URL = "https://data.gov.tw/api/v2/rest/dataset/{id}"
COLS = ["災害名稱", "發生時間", "縣市", "鄉鎮市區", "災情類別"]

# Hazard of an activation, read from its name (軒嵐諾颱風, 0403花蓮地震 …): (type id, the word looked for).
HAZARD_WORDS = [("typhoon", "颱風"), ("earthquake", "地震"), ("flood", "豪雨"), ("flood", "水災")]


def hazard(name: str) -> tuple[str, str]:
    """(type id, the word in the name that decided it); ("other", "") when no word matches."""
    for type_id, word in HAZARD_WORDS:
        if word in name:
            return type_id, word
    return "other", ""


def iso_date(text: str) -> str | None:
    """'2024/4/3 08:00' → '2024-04-03'."""
    try:
        y, m, d = text.split()[0].split("/")
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    except (ValueError, IndexError):
        return None


class NfaDisasterCases(Source):
    info = SourceInfo(
        id="nfa_disaster_cases",
        title="Disaster case reports during Central Emergency Operation Center activations, 2022-2024",
        publisher="Ministry of the Interior, National Fire Agency (內政部消防署), Emergency Management Information Cloud",
        homepage="https://data.gov.tw/dataset/173936",
        license="Government Open Data License v1.0",
        description="Every disaster case that local governments filed in the national emergency information system "
        "(EMIC) while the Central Emergency Operation Center was open for a named typhoon or earthquake: the "
        "activation, the time, the county, the township and the kind of damage (fallen trees, power cuts, flooding, "
        "damaged buildings, landslides ...). A case is a report, not a measure of damage, and how readily cases are "
        "filed differs between local governments.",
        used_for=["Disasters: activations with reported cases, by township and county"],
    )

    def _meta(self, roc: int) -> str:
        return f"dataset_{DATASETS[roc]}.json"

    def _cases(self, roc: int) -> str:
        return f"cases_{roc}.csv"

    def fetch(self, force=False):
        for roc, ds in DATASETS.items():
            if (self.raw_dir / self._cases(roc)).exists() and not force:
                continue
            meta = self.download(META_URL.format(id=ds), self._meta(roc), force=force)
            dist = json.loads(meta.read_text(encoding="utf-8"))["result"]["distribution"]
            url = next(d["resourceDownloadUrl"] for d in dist if (d.get("resourceFormat") or "").upper() == "CSV")
            self.download(url, self._cases(roc), force=force)

    def process(self):
        towns = TownIndex()
        # Identical rows that two yearly files both carry (an activation spanning the files) count once.
        merged: Counter = Counter()
        rows_read = {}
        for roc in DATASETS:
            per_file: Counter = Counter()
            with open(self.raw_dir / self._cases(roc), encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    per_file[tuple((r.get(c) or "").strip() for c in COLS)] += 1
            rows_read[self._cases(roc)] = sum(per_file.values())
            for key, n in per_file.items():
                merged[key] = max(merged[key], n)

        events: dict[str, dict] = {}
        unmatched: Counter = Counter()
        undated = 0
        for (name, when, county, town, kind), n in merged.items():
            day = iso_date(when)
            if not name or day is None:
                undated += n
                continue
            type_id, word = hazard(name)
            e = events.setdefault(name, {"name": name, "type": type_id, "hazard_word": word, "first": day, "last": day,
                                         "cases": 0, "towns": {}, "counties": {}, "town_last": {}, "kinds": Counter()})
            e["first"], e["last"] = min(e["first"], day), max(e["last"], day)
            e["cases"] += n
            e["kinds"][kind.split("-")[0]] += n
            ccode = towns.county(county)
            if ccode is None:
                unmatched[f"{county}"] += n
                continue
            e["counties"][ccode] = e["counties"].get(ccode, 0) + n
            geoid = towns.town(county, town)
            if geoid is None:
                unmatched[f"{county}{town}"] += n
                continue
            e["towns"][geoid] = e["towns"].get(geoid, 0) + n
            e["town_last"][geoid] = max(e["town_last"].get(geoid, day), day)

        ordered = sorted(events.values(), key=lambda e: (e["first"], e["name"]))
        seq: Counter = Counter()
        out = {}
        for e in ordered:
            year = int(e["first"][:4])
            seq[year] += 1
            e["kinds"] = dict(e["kinds"].most_common())
            out[str(year * 100 + seq[year])] = e
        retrieved = max((m.get("retrieved", "")[:10] for m in fetch.read_manifest(self.id).values()), default=None)
        return {
            "vintage": f"NFA EMIC disaster case reports, activations {ordered[0]['first'][:4]}-{ordered[-1]['last'][:4]}",
            "_files": [self._cases(roc) for roc in DATASETS] + [self._meta(roc) for roc in DATASETS
                                                                 if (self.raw_dir / self._meta(roc)).exists()],
            "window_start": min(e["first"] for e in ordered),
            "window_end": max(e["last"] for e in ordered),
            "as_of": retrieved,
            "rows_read": rows_read,
            "cases": sum(e["cases"] for e in ordered),
            "undated_rows": undated,
            "unmatched": dict(unmatched.most_common()),
            "events": out,
        }
