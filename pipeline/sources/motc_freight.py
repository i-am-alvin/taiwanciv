"""Truck freight between counties: the origin-destination table of the Ministry of Transportation and
Communications' truck freight survey (汽車貨運調查報告).

The survey publishes its tables only as a typeset PDF report (the survey's data files are released on application,
not as open data), so the table is read out of the PDF's text with ``_pdf_text``. Every label (the county names of
the rows and columns, the unit, the year) is read from the page, and the table's own total row and total column
must be reproduced by the parsed cells, or processing stops.
"""

from __future__ import annotations

import csv
import re

from ..core.source import Source, SourceInfo
from ._pdf_text import Pdf

# data.gov.tw dataset 6307: one row per survey year with the address of that year's report
INDEX_URL = "https://www.motc.gov.tw/uploaddowndoc?file=datagov/1507218406636523520.csv&flag=doc"
INDEX_FILE = "index.csv"
TABLE = "表5汽車貨運貨物流動"     # the left page's title; the facing page carries on: 概況─按起訖縣市分
TABLE_RIGHT = "按起訖縣市分"
TOTAL = "總計"
NIL = "－"                          # the report's mark for a cell with nothing to report
TOTAL_TOL = 1e-6                    # share of the grand total the totals line may miss it by (rounding)
ROW_TOL = 2.0                       # page units: text origins this close in height are one table row
_NUMBER = re.compile(r"^\d{1,3}(,\d{3})*$")
_BLANK = re.compile(r"[\s　]+")


def report_file(year: int) -> str:
    return f"truck_freight_survey_{year}.pdf"


def _compact(text: str) -> str:
    return _BLANK.sub("", text)


def _rows(runs: list[tuple[float, float, str]]) -> list[tuple[float, list[tuple[float, str]]]]:
    """Text runs grouped into rows (top first), each row's cells left to right. Runs written at one origin are
    one cell (a label set in several pieces)."""
    cells: list[list] = []
    for x, y, text in runs:
        if cells and cells[-1][0] == x and cells[-1][1] == y:
            cells[-1][2] += text
        else:
            cells.append([x, y, text])
    rows: list[tuple[float, list]] = []
    for x, y, text in sorted(cells, key=lambda c: -c[1]):
        if rows and abs(rows[-1][0] - y) <= ROW_TOL:
            rows[-1][1].append((x, _compact(text)))
        else:
            rows.append((y, [(x, _compact(text))]))
    return [(y, sorted(c for c in cs if c[1])) for y, cs in rows]


def _is_place(label: str) -> bool:
    return label == TOTAL or (len(label) == 3 and label[-1] in "市縣")


def read_page(runs) -> dict:
    """One page of the table: its column labels and, per table row, (height, row label or None, values)."""
    rows = _rows(runs)
    head = next((cs for _, cs in rows if len(cs) >= 2 and all(_is_place(t) for _, t in cs)), None)
    if head is None:
        raise ValueError("no row of county names found for the table's columns")
    columns = [t for _, t in head]
    body = []
    for y, cs in rows:
        values = [t for _, t in cs if _NUMBER.match(t) or t == NIL]
        if not values:
            continue
        label = "".join(t for _, t in cs if not (_NUMBER.match(t) or t == NIL)) or None
        if len(values) != len(columns):
            raise ValueError(f"row {label or y}: {len(values)} values under {len(columns)} columns")
        body.append((y, label, [None if v == NIL else int(v.replace(",", "")) for v in values]))
    return {"columns": columns, "rows": body}


def read_table(pdf: Pdf) -> dict:
    """The whole origin-destination table: {'year', 'unit', 'pages', 'origins', 'destinations', 'cells'} with
    cells[origin][destination] in the table's unit (None where the report prints its nil mark)."""
    cells: dict[str, dict[str, int | None]] = {}
    destinations: list[str] = []
    origins: list[str] = []
    used, year, unit = [], None, None
    pages = pdf.pages()
    for i, num in enumerate(pages[:-1]):
        left_runs = pdf.page_text(num)
        text = _compact("".join(t for _, _, t in left_runs))
        if TABLE not in text or "訖點" not in text:
            continue
        right_runs = pdf.page_text(pages[i + 1])
        right_text = _compact("".join(t for _, _, t in right_runs))
        if TABLE_RIGHT not in right_text:
            raise ValueError(f"page {i + 2} does not carry on the table of page {i + 1}")
        line = next(("".join(t for _, t in cs) for _, cs in _rows(right_runs) if any("單位" in t for _, t in cs)), "")
        m = re.fullmatch(r"(\d{2,3})年單位[:：](.+)", line)
        if not m:
            raise ValueError(f"page {i + 2}: no year and unit line")
        if (year, unit) not in ((None, None), (int(m.group(1)), m.group(2))):
            raise ValueError("the table's pages disagree on year or unit")
        year, unit = int(m.group(1)), m.group(2)
        left, right = read_page(left_runs), read_page(right_runs)
        if len(left["rows"]) != len(right["rows"]):
            raise ValueError(f"pages {i + 1} and {i + 2} have different numbers of rows")
        labels = []
        for (y, label, values), (y2, label2, values2) in zip(left["rows"], right["rows"]):
            if label is None or not _is_place(label) or label2 is not None or abs(y - y2) > ROW_TOL:
                raise ValueError(f"pages {i + 1} and {i + 2}: row {label!r} does not line up")
            labels.append(label)
            row = cells.setdefault(label, {})
            for dest, v in zip(left["columns"] + right["columns"], values + values2):
                if dest in row:
                    raise ValueError(f"column {dest} appears twice")
                row[dest] = v
        if origins and labels != origins:
            raise ValueError("the table's pages list different rows")
        origins = labels
        destinations += left["columns"] + right["columns"]
        used += [i + 1, i + 2]
    if not used:
        raise ValueError("origin-destination table not found in the report")
    return {"year": year, "unit": unit, "pages": used, "origins": origins, "destinations": destinations,
            "cells": cells}


def verify(table: dict) -> None:
    """The cells must add up to the table's own total row and total column. The report rounds every survey
    estimate to a whole tonne, so a line of n cells may miss its printed total by up to n tonnes; the line of
    totals itself (whose sum the report misses by a few dozen tonnes) is held to TOTAL_TOL of the grand total."""
    cells, origins, dests = table["cells"], table["origins"], table["destinations"]
    if TOTAL not in origins or TOTAL not in dests or sorted(origins) != sorted(dests):
        raise ValueError("the table's rows and columns are not the same places plus a total")
    places = [p for p in origins if p != TOTAL]
    grand = cells[TOTAL][TOTAL]

    def near(what: str, got: int, said: int | None, total_line: bool) -> None:
        if said is None or abs(got - said) > (grand * TOTAL_TOL if total_line else len(places)):
            raise ValueError(f"{what}: cells add to {got}, the table says {said}")

    for o in origins:
        near(f"row {o}", sum(cells[o][d] or 0 for d in places), cells[o][TOTAL], o == TOTAL)
    for d in dests:
        near(f"column {d}", sum(cells[o][d] or 0 for o in places), cells[TOTAL][d], d == TOTAL)


class MotcFreight(Source):
    info = SourceInfo(
        id="motc_freight",
        title="Truck freight survey: freight moved between counties (汽車貨運調查報告 表5)",
        publisher="Ministry of Transportation and Communications, Department of Statistics (交通部統計處)",
        homepage="https://data.gov.tw/dataset/6307",
        license="Government Open Data License v1.0",
        description="Annual sample survey of trucks (business and own-account). Table 5 of the report gives the "
        "tonnes carried by truck in the year from each county to each county (origin by destination), for the 20 "
        "counties and cities of Taiwan and Penghu; Kinmen and Lienchiang are outside the survey. Survey estimates, "
        "in metric tons (公噸); road freight only (no rail, sea or air), and no money value of the goods. The "
        "report is a PDF: the table is read from its text and checked against its own totals.",
        used_for=["Trade routes: truck freight tonnage between counties"],
    )

    def _newest(self) -> tuple[int, str]:
        with open(self.raw_dir / INDEX_FILE, encoding="utf-8-sig", newline="") as f:
            rows = [(int(r["資料年"]), r["路徑"].strip()) for r in csv.DictReader(f) if r.get("路徑")]
        return max(rows)

    def fetch(self, force=False):
        self.download(INDEX_URL, INDEX_FILE, force=force)
        roc, url = self._newest()
        self.download(url, report_file(roc + 1911), force=force, expect_binary=True)

    def process(self):
        roc, url = self._newest()
        name = report_file(roc + 1911)
        table = read_table(Pdf((self.raw_dir / name).read_bytes()))
        verify(table)
        if table["year"] != roc:
            raise ValueError(f"the report's table is for year {table['year']}, the index says {roc}")
        places = [p for p in table["origins"] if p != TOTAL]
        cells = table["cells"]
        return {
            "vintage": f"MOTC truck freight survey {roc + 1911}",
            "_files": [INDEX_FILE, name],
            "year": roc + 1911,
            "unit": table["unit"],
            "report_url": url,
            "pages": table["pages"],
            "places": places,
            "total": cells[TOTAL][TOTAL],
            "cells_sum": sum(cells[o][d] or 0 for o in places for d in places),
            "out": {p: cells[p][TOTAL] for p in places},
            "in": {p: cells[TOTAL][p] for p in places},
            # flows[origin][destination], tonnes; null where the report prints "－"
            "flows": {o: {d: cells[o][d] for d in places} for o in places},
        }
