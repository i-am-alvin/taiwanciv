"""Daytime and night-time population of every township, estimated from mobile-network signalling (電信信令人口).

The Ministry of the Interior's Department of Statistics counted, from anonymised mobile-network signalling data, how
many people are active in each township by day and how many stay there at night, on weekdays and at weekends.
The two files carry TOWNCODEs (written as numbers, so a leading zero is restored).
"""

from __future__ import annotations

import csv

from ..core.source import Source, SourceInfo

BASE = "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset"
# data.gov.tw 162907 (daytime activity; the resource whose fields are documented) and 162908 (night-time stay).
DAY_URL = f"{BASE}/F12D8CDB-7758-40FB-8C27-D19987BA5ECB/resource/8912D1ED-D811-419F-8BB6-BAB47260146E/download"
NIGHT_URL = f"{BASE}/556056F7-2418-493E-B2F8-B94E9F376728/resource/3A0FB7B7-B4DC-4637-9C14-3777E21C3497/download"
DAY_FILE, NIGHT_FILE = "telecom_day_activity.csv", "telecom_night_stay.csv"


def _rows(path):
    """Data rows of a file (rows whose third column is a township code; header and label rows are skipped)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.reader(f):
            if len(r) >= 7 and r[2].strip().isdigit():
                yield [c.strip() for c in r]


class MoiTelecomPopulation(Source):
    info = SourceInfo(
        id="moi_telecom_population",
        title="Daytime and night-time population by township from mobile-network signalling (電信信令人口統計)",
        publisher="Ministry of the Interior, Department of Statistics (內政部統計處)",
        homepage="https://data.gov.tw/dataset/162907",
        license="Government Open Data License v1.0",
        description="Estimates of the people active in each township between 07:00 and 19:00 and of the people "
        "staying there at night, on weekdays and at weekends, modelled from anonymised mobile-network signalling "
        "data of November 2020. The ratio of the weekday daytime to the weekday night-time figure shows where "
        "people travel to by day (above 1) and where they only sleep (below 1).",
        used_for=["Day / night population ratio"],
    )

    def fetch(self, force=False):
        self.download(DAY_URL, DAY_FILE, force=force)
        self.download(NIGHT_URL, NIGHT_FILE, force=force)

    def process(self):
        towns: dict[str, dict] = {}
        times = set()
        for r in _rows(self.raw_dir / DAY_FILE):
            towns.setdefault(r[2].zfill(8), {}).update(day_weekday=int(r[6]), day_weekend=int(r[9]))
            times.add(r[10])
        for r in _rows(self.raw_dir / NIGHT_FILE):
            towns.setdefault(r[2].zfill(8), {}).update(night_weekday=int(r[4]), night_weekend=int(r[5]))
            times.add(r[6])
        print(f"    {len(towns)} townships; data time {sorted(times)}")
        return {
            "vintage": "Mobile-network signalling, " + ", ".join(sorted(times)) + " (ROC year and month)",
            "_files": [DAY_FILE, NIGHT_FILE],
            "data_time": sorted(times),
            "towns": towns,
        }
