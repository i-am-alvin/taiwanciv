"""Ports and airports: cargo through the international commercial ports (Taiwan International Ports Corporation)
and traffic at every civil airport (Civil Aviation Administration).

Neither file has coordinates: the builder places each port and airport with OpenStreetMap (``osm_tw_transport``).
"""

from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict

from ..core.source import Source, SourceInfo

# ------------------------------------------------------------------ ports

PORTS_URL = "https://www.twport.com.tw/fapi/opendata?id=13875"
PORTS_FILE = "port_cargo_throughput.csv"
ALL_PORTS = "國際商港"  # the file's own total row


class TipcPorts(Source):
    info = SourceInfo(
        id="tipc_ports",
        title="Cargo throughput of the international commercial ports (臺灣地區國際商港貨物吞吐量)",
        publisher="Taiwan International Ports Corporation (臺灣港務股份有限公司)",
        homepage="https://data.gov.tw/dataset/8369",
        license="Government Open Data License v1.0",
        description="Monthly cargo throughput in metric tons (公噸) of the seven international commercial ports "
        "(Keelung, Taipei, Su'ao, Taichung, Kaohsiung, Anping, Hualien), split into import, export and domestic "
        "cargo, since 2001. The newest calendar year with all twelve months is summed. Industrial ports (Mailiao, "
        "Heping) and the domestic ports of the outlying islands are not in this file.",
        used_for=["Ports: cargo tonnage, imports, exports, domestic cargo"],
    )

    def fetch(self, force=False):
        self.download(PORTS_URL, PORTS_FILE, force=force)

    def process(self):
        months = defaultdict(lambda: defaultdict(dict))  # year → port → month → row
        with open(self.raw_dir / PORTS_FILE, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                ym = row["年月"].strip()
                months[int(ym[:4])][row["港口別"].strip()][int(ym[4:])] = row
        year = max(y for y, ports in months.items() if all(len(m) == 12 for m in ports.values()))

        def total(port, col):
            return sum(int(r[col]) for r in months[year][port].values())

        ports = []
        for name in months[year]:
            imports, exports, domestic = (total(name, c) for c in ("進口貨", "出口貨", "國內貨物"))
            ports.append({"name": name, "tons": total(name, "總計"), "imports": imports, "exports": exports,
                          "domestic": domestic, "foreign": imports + exports})
        nation = next(p for p in ports if p["name"] == ALL_PORTS)
        ports = sorted((p for p in ports if p["name"] != ALL_PORTS), key=lambda p: -p["tons"])
        if sum(p["tons"] for p in ports) != nation["tons"]:
            raise ValueError(f"ports sum to {sum(p['tons'] for p in ports)}, the file's total row says {nation['tons']}")
        for rank, p in enumerate(ports, 1):
            p["rank"] = rank
        print(f"    {year}: {len(ports)} ports, {nation['tons']:,} t; #1 {ports[0]['name']} {ports[0]['tons']:,} t")
        return {"vintage": f"臺灣港務公司 國際商港貨物吞吐量，{year} 年", "_files": [PORTS_FILE], "year": year,
                "unit": "公噸", "total": nation, "ports": ports}


# ------------------------------------------------------------------ airports

CAA_INDEX_URL = "https://www.caa.gov.tw/FileAtt.ashx?lang=1&id=30683"  # data.gov.tw 31915: a one-row CSV naming the file
CAA_INDEX = "index.csv"
_T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_O = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
_P = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}p"


def ods_rows(path) -> list[list[tuple[float | None, str]]]:
    """Rows of the first sheet of an OpenDocument spreadsheet as (number or None, text) cells."""
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("content.xml"))
    sheet = next(root.iter(_T + "table"))
    rows = []
    for tr in sheet.iter(_T + "table-row"):
        row = []
        for tc in tr:
            if tc.tag not in (_T + "table-cell", _T + "covered-table-cell"):
                continue
            rep = min(int(tc.get(_T + "number-columns-repeated", "1")), 200)
            val = tc.get(_O + "value")
            text = "".join("".join(p.itertext()) for p in tc.iter(_P)).strip()
            row.extend([(float(val) if val is not None else None, text)] * rep)
        while row and row[-1] == (None, ""):
            row.pop()
        rows.extend([row] * min(int(tr.get(_T + "number-rows-repeated", "1")), 2))
    return rows


class CaaAirports(Source):
    info = SourceInfo(
        id="caa_airports",
        title="Airport traffic by airport (民航運輸各機場營運量－按機場分)",
        publisher="Civil Aviation Administration, MOTC (交通部民用航空局)",
        homepage="https://data.gov.tw/dataset/31915",
        license="Government Open Data License v1.0",
        description="Aircraft movements, passengers (人次: arriving plus departing, transit included) and cargo "
        "in metric tons at each civil airport, by year since 1952 and by month for the current year (CAA civil "
        "aviation statistics, table 3). The newest complete calendar year and the year before it are used.",
        used_for=["Airports: passengers, cargo tonnage, hub class"],
    )

    def _table(self) -> tuple[str, str]:
        with open(self.raw_dir / CAA_INDEX, encoding="utf-8-sig", newline="") as f:
            row = next(csv.DictReader(f))
        return row["路徑"].strip(), row["版本"].strip()

    def fetch(self, force=False):
        cached = sorted(self.raw_dir.glob("table3_*.ods"))
        if self.offline and cached:
            return
        self.download(CAA_INDEX_URL, CAA_INDEX, force=True)  # tiny, names the month's file
        url, version = self._table()
        self.download(url, f"table3_{version}.ods", force=force, expect_binary=True)

    def process(self):
        _, version = self._table()
        rel = f"table3_{version}.ods"
        rows = ods_rows(self.raw_dir / rel)
        text = lambda r: [t for _, t in r]  # noqa: E731
        title = next(t for r in rows for t in text(r) if "起至" in t)
        last_year, last_month = (int(v) for v in re.search(r"起至(\d+)年(\d+)月", title).groups())
        head = next(i for i, r in enumerate(rows) if any(re.match(r"1\.", t) for t in text(r)))
        names, labels = text(rows[head]), text(rows[head + 1])
        starts = [(c, re.sub(r"^\d+\.", "", t)) for c, t in enumerate(names) if t == "總計" or re.match(r"\d+\.", t)]
        groups = []
        for k, (c0, name) in enumerate(starts):
            c1 = starts[k + 1][0] if k + 1 < len(starts) else len(labels)
            cols = {}
            for c in range(c0, c1):
                lab = labels[c] if c < len(labels) else ""
                for key, word in (("flights", "起降架次"), ("passengers", "旅客人數"), ("cargo_t", "貨運噸數")):
                    if word in lab and key not in cols:
                        cols[key] = c
            groups.append((name, cols))

        years = {}
        for r in rows[head + 2:]:
            m = re.fullmatch(r"(\d+)年", r[0][1]) if r else None
            if m:
                years[int(m.group(1))] = r
        year = last_year if last_month == 12 else last_year - 1  # the newest complete calendar year (ROC)

        def read(roc):
            row = years[roc]
            return {name: {k: (row[c][0] if c < len(row) else None) for k, c in cols.items()} for name, cols in groups}

        now, prev = read(year), read(year - 1)
        airports = []
        for name, _ in groups:
            if name == "總計":
                continue
            a = now[name]
            airports.append({"name": name, "flights": a["flights"], "passengers": a["passengers"],
                             "passengers_prev": prev[name]["passengers"], "cargo_t": a["cargo_t"],
                             "cargo_t_prev": prev[name]["cargo_t"]})
        total = now["總計"]
        got = sum(a["passengers"] or 0 for a in airports)
        if abs(got - total["passengers"]) > 0.5:
            raise ValueError(f"airports sum to {got} passengers, the table's total says {total['passengers']}")
        ad = year + 1911
        print(f"    {ad}: {len(airports)} airports, {total['passengers']:,.0f} passengers, {total['cargo_t']:,.0f} t "
              f"(file through {last_year}年{last_month}月)")
        return {"vintage": f"交通部民用航空局 民航運輸各機場營運量，{ad} 年", "_files": [CAA_INDEX, rel], "year": ad,
                "through": f"{last_year}年{last_month}月", "total": total, "total_prev": prev["總計"],
                "airports": airports}
