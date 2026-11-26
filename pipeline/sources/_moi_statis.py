"""Helpers for the Ministry of the Interior statistics query system (內政統計查詢網, statis.moi.gov.tw).

Not a source itself (no Source subclass), so the registry ignores it. The system answers one GET per table and
period with a UTF-8 CSV whose first column is "<ROC year>年[ <month>月]/ <category>[/ <sub-category>]" and whose
empty cells are printed as "-".
"""

from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

BASE = "https://statis.moi.gov.tw/micst/webMain.aspx"


def url(funid: str, *, cycle: int, fields: int, codes: int, ym: str, ymt: str, extra: str = "") -> str:
    """The CSV export of table `funid`: `fields` value columns, the first `codes` categories, period ym..ymt
    (ROC year + month, month 00 = the whole year). cycle 4 = yearly, 41 = yearly plus its months."""
    return (f"{BASE}?sys=220&kind=21&type=1&funid={funid}&cycle={cycle}&outmode=12&utf=1&compmode=0&outkind=3"
            f"&fldspc=0,{fields},&codspc0=0,{codes},{extra}&ym={ym}&ymt={ymt}")


def roc_year_now() -> int:
    return date.today().year - 1911


def number(text: str) -> float | None:
    """A cell as a number; "-" (the publisher's mark for no figure) and blanks are None."""
    t = (text or "").replace(",", "").strip()
    if t in ("", "-", "…", "..."):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def rows(path: Path) -> tuple[list[str], list[dict]]:
    """(header, rows). Each row: {"line": 1-based line in the file, "roc": year, "month": int | None,
    "parts": the label after the period split on "/", "values": numbers or None}."""
    out = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        for line, r in enumerate(reader, 2):
            if not r or not r[0].strip():
                continue
            parts = [p.strip() for p in r[0].split("/")]
            m = re.match(r"(\d+)年(?:\s*(\d+)月)?$", parts[0])
            if not m:
                continue
            out.append({"line": line, "roc": int(m.group(1)), "month": int(m.group(2)) if m.group(2) else None,
                        "parts": parts[1:], "values": [number(v) for v in r[1:]]})
    return header, out
