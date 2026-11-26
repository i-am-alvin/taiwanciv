"""Taipower's list of generating units on the grid (台灣電力公司_各機組發電量), with each unit's installed capacity.

The file is Taipower's 10-minute system snapshot: every unit or unit group the dispatch centre sees, Taipower's own
and the independent producers', with its fuel class, installed capacity (MW), current output and a status note
(歲修 = annual overhaul, 故障 = fault, ...). It is the only open list that is current: it has no nuclear rows since
the last reactor shut down, and it has the units commissioned after Taipower's 2024 plant table
(data.gov.tw 8934, which also lacks the independent producers and wind farms).

Only the installed capacity and the status note are kept; the momentary output is a 10-minute reading, not a
statistic. A capacity printed as "-" (a unit in trial operation, or one being retired) is null.
"""

from __future__ import annotations

import json
import re

from ..core.source import Source, SourceInfo

URL = "https://service.taipower.com.tw/data/opendata/apply/file/d006001/001.json"
FILE = "units.json"
_NOTE = re.compile(r"\(註\d+\)")
_TAG = re.compile(r"<[^>]*>")


def _mw(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


class TaipowerUnits(Source):
    info = SourceInfo(
        id="taipower_units",
        title="Generating units and installed capacity (台灣電力公司_各機組發電量)",
        publisher="Taiwan Power Company (台灣電力公司)",
        homepage="https://data.gov.tw/dataset/8931",
        license="Government Open Data License v1.0",
        description="Taipower's system snapshot: every generating unit or unit group on the grid, by fuel class, "
        "with its installed capacity in MW and a status note, for Taipower's own plants and the independent power "
        "producers. Units are summed per plant to size the power plants, dams and wind farms on the map. The file "
        "has no coordinates (plants are placed with OpenStreetMap) and is a snapshot of the day it was fetched.",
        used_for=["Power plants, dams, pumped storage, wind and solar farms: capacity (MW)"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force)

    def process(self):
        doc = json.loads((self.raw_dir / FILE).read_text(encoding="utf-8-sig"))
        units, subtotals = [], {}
        for row in doc["aaData"]:
            kind = _TAG.sub("", row["機組類型"]).strip()
            name = row["機組名稱"].strip()
            if name.startswith("小計"):
                subtotals[kind] = _mw(row["裝置容量(MW)"].split("(")[0])
                continue
            units.append({
                "kind": kind,
                "name": _NOTE.sub("", name).strip(),
                "raw_name": name,
                "mw": _mw(row["裝置容量(MW)"]),
                "status": row["備註"].strip() or None,
            })
        stamp = doc.get("DateTime", "")
        print(f"    {len(units)} unit rows, {sum(1 for u in units if u['mw'] is None)} without a capacity; snapshot {stamp}")
        return {"vintage": f"Taipower unit list, snapshot {stamp.replace('T', ' ')}", "_files": [FILE],
                "snapshot": stamp, "units": units, "subtotals": subtotals}
