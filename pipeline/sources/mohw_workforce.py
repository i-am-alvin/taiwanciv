"""Doctors and other medical staff practising in the hospitals and clinics of each township (衛生福利部統計處).

Two zips (醫院人力統計, 診所人力統計), each with one CSV of staff counts by 鄉鎮市區碼 and a 欄位說明 table that
names every code ('臺北市松山區'). The code is the Ministry of Health and Welfare's own, not a TOWNCODE, so each
code is mapped by its name through tw_boundaries.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile

from ..core.source import Source, SourceInfo
from ._tw_towns import TownIndex

DATASETS = {"hospital": 6474, "clinic": 6476}  # data.gov.tw: 醫院人力統計, 診所人力統計
META = "https://data.gov.tw/api/v2/rest/dataset/{id}"
YEAR = re.compile(r"^(\d{3})年")
CODE, NAME_NOW = "鄉鎮市區碼", "鄉鎮市區名稱(103年以後適用)"
COUNT = {"hospital": "醫院家數", "clinic": "診所家數"}
STAFF = {"staff": "醫事人員總計", "physicians": "西醫師", "tcm_doctors": "中醫師", "dentists": "牙醫師",
         "nurses": ["護理師", "護士"], "pharmacists": ["藥師", "藥劑生"]}


def _meta_file(kind: str) -> str:
    return f"dataset_{DATASETS[kind]}.json"


class MohwWorkforce(Source):
    info = SourceInfo(
        id="mohw_workforce",
        title="Medical staff of hospitals and clinics by township (醫院人力統計、診所人力統計)",
        publisher="Ministry of Health and Welfare, Department of Statistics (衛生福利部統計處)",
        homepage="https://data.gov.tw/dataset/6474",
        license="Government Open Data License v1.0",
        description="Year-end counts of hospitals and clinics and of the licensed staff practising in them "
        "(physicians, doctors of Chinese medicine, dentists, nurses, pharmacists and others) for every township. "
        "Staff are counted where they practise, not where they live. The newest year of each dataset is used.",
        used_for=["Physicians per 10,000 residents"],
    )

    def _latest(self, kind: str) -> tuple[int, str]:
        meta = json.loads((self.raw_dir / _meta_file(kind)).read_text(encoding="utf-8"))
        years = {}
        for d in meta["result"]["distribution"]:
            m = YEAR.match(d.get("resourceDescription") or "")
            if m and d.get("resourceDownloadUrl"):
                years[int(m.group(1))] = d["resourceDownloadUrl"]
        if not years:
            raise ValueError(f"data.gov.tw dataset {DATASETS[kind]}: no yearly resources")
        y = max(years)
        return y, years[y]

    def fetch(self, force=False):
        for kind, ds in DATASETS.items():
            self.download(META.format(id=ds), _meta_file(kind), force=force)
            y, url = self._latest(kind)
            self.download(url, f"{kind}_personnel_{y}.zip", force=force, expect_binary=True)

    def process(self):
        towns = TownIndex()
        out: dict[str, dict] = {}
        files, years, unmatched = [], {}, set()
        for kind in DATASETS:
            y, _ = self._latest(kind)
            years[kind] = y + 1911
            name = f"{kind}_personnel_{y}.zip"
            files += [_meta_file(kind), name]
            data = codes = None
            with zipfile.ZipFile(self.raw_dir / name) as z:
                for info in z.infolist():
                    rows = list(csv.reader(io.StringIO(z.read(info).decode("utf-8-sig"))))
                    if rows and NAME_NOW in rows[0]:
                        codes = {r[0].strip(): r[rows[0].index(NAME_NOW)] for r in rows[1:] if r}
                    elif rows and rows[0][0].strip() == CODE and COUNT[kind] in rows[0]:
                        data = rows
            if data is None or codes is None:
                raise ValueError(f"{name}: staff table or code table not found")
            geoid = {}
            for code, full in codes.items():
                g = towns.full(full)
                if g is None:
                    unmatched.add(full)
                else:
                    geoid[code] = g
                    # every township in the code table is covered by the statistics: no row means none there
                    t = out.setdefault(g, {"hospitals": 0, "clinics": 0, **{k: 0 for k in STAFF}})
            col = {h.strip(): i for i, h in enumerate(data[0])}
            for r in data[1:]:
                g = geoid.get(r[0].strip()) if r else None
                if g is None:
                    continue
                t = out[g]
                t[kind + "s"] += int(r[col[COUNT[kind]]] or 0)
                for k, names in STAFF.items():
                    t[k] += sum(int(r[col[n]] or 0) for n in ([names] if isinstance(names, str) else names))
        print(f"    {len(out)} of {len(towns.codes)} townships; {sum(t['physicians'] for t in out.values()):,} physicians "
              f"in {sum(t['hospitals'] for t in out.values()):,} hospitals and {sum(t['clinics'] for t in out.values()):,} clinics"
              + (f"; unmatched {sorted(unmatched)}" if unmatched else ""))
        return {
            "vintage": f"End of {years['hospital']} (hospitals) and {years['clinic']} (clinics)",
            "_files": files,
            "years": years,
            "towns": out,
            "unmatched": sorted(unmatched),
        }
