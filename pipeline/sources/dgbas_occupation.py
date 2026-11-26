"""Employed people by occupation in each county, from the Manpower Survey (人力資源調查) annual report, table 34.

Table 34 (就業者之職業) counts employed people, in thousands, in seven occupation groups of the Standard
Occupational Classification: the report merges major groups 7, 8 and 9 (craft workers, machine operators and
labourers) into one column, so there are seven columns, not nine. The survey covers the Taiwan area (Taiwan and
Penghu); Kinmen and Lienchiang are not sampled.

Rows are identified by their English name (the "District ( or Region )" column), matched to the `name_en` of the
tw_boundaries interim: the Chinese names are spaced out and some editions of the sheet cut them short, which makes
新竹市 / 新竹縣 and 嘉義市 / 嘉義縣 read the same.
"""

from __future__ import annotations

import re

from ..core.source import Source, SourceInfo
from ..core.store import load_interim
from ._resource_util import xlsx_rows

ROC_YEAR = 114  # 2025 annual averages
REPORT = "https://www.stat.gov.tw/News_Content.aspx?n=4001&s=236078"
URL = "https://ws.dgbas.gov.tw/001/Upload/463/relfile/11516/236078/table34.xlsx"
FILE = "table34.xlsx"
NAME_HEAD = "District(orRegion)"  # head of the English-name column, whitespace removed
TOTAL_HEAD = "總計"
NATION_EN = "Taiwan Area"

# Occupation groups as table 34 heads them (whitespace removed) → key. The order is the table's.
GROUPS = {
    "民意代表、主管及經理人員": "managers",
    "專業人員": "professionals",
    "技術員及助理專業人員": "technicians",
    "事務支援人員": "clerical",
    "服務及銷售工作人員": "service_sales",
    "農、林、漁、牧業生產人員": "agricultural",
    "技藝有關工作人員、機械設備操作及勞力工": "craft_operators_labourers",
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _value(text: str) -> float | None:
    """DGBAS notation: '-' = none (0), '…' = not available."""
    t = (text or "").strip()
    if t in ("-", "－"):
        return 0.0
    try:
        return float(t)
    except ValueError:
        return None


class DgbasOccupation(Source):
    info = SourceInfo(
        id="dgbas_occupation",
        title=f"Manpower Survey, {ROC_YEAR + 1911} annual report: employed people by occupation and county",
        publisher="Directorate-General of Budget, Accounting and Statistics (主計總處), Executive Yuan",
        homepage=REPORT,
        license="Government Open Data License v1.0",
        description=f"Annual averages for {ROC_YEAR + 1911}: employed people (thousands, rounded to the nearest "
        "thousand) in seven occupation groups, counted where they live (table 34), for the 20 counties and cities "
        "of the Taiwan area. Craft workers, machine operators and labourers are one column in the report. Kinmen "
        "and Lienchiang are not covered by the survey.",
        used_for=["Citizens: workforce by occupation"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        b = load_interim("tw_boundaries")
        fips_of = {_clean(s["name_en"]).lower(): s["fips"] for s in b["states"]}
        name_col = total_col = None
        cols: dict[str, str] = {}   # group key → column of its 合計 (the first column under the group's head)
        labels: dict[str, dict] = {}
        counties: dict[str, dict] = {}
        nation = None
        for row in xlsx_rows(self.raw_dir / FILE):
            if name_col is None:
                # The head row: the group names, the total and the English-name column.
                heads = {col: _clean(text) for col, text in row.items()}
                if NAME_HEAD not in heads.values():
                    continue
                name_col = next(c for c, t in heads.items() if t == NAME_HEAD)
                total_col = next((c for c, t in heads.items() if t == TOTAL_HEAD), None)
                for col, t in heads.items():
                    for zh, key in GROUPS.items():
                        if t == _clean(zh):
                            cols[key] = col
                            labels[key] = {"zh": zh}
                if total_col is None or len(cols) != len(GROUPS):
                    raise ValueError(f"table 34 layout changed: found {sorted(cols)} and total {total_col}")
                continue
            if "en" not in next(iter(labels.values())):
                # The row under the head carries the English group names in the same columns.
                if all(row.get(c) for c in cols.values()):
                    for key, c in cols.items():
                        labels[key]["en"] = re.sub(r"\s+", " ", row[c]).strip()
                continue
            if any("續" in v for v in row.values()):
                break  # the second block repeats the table as percentages
            name = re.sub(r"\s+", " ", row.get(name_col, "")).strip()
            if not name:
                continue
            rec = {
                "employed": None if (t := _value(row.get(total_col, ""))) is None else round(t * 1000),
                "occupations": {k: (None if (v := _value(row.get(c, ""))) is None else round(v * 1000))
                                for k, c in cols.items()},
            }
            if name == NATION_EN:
                nation = rec
            elif _clean(name).lower() in fips_of:
                counties[fips_of[_clean(name).lower()]] = rec
            # other rows are the four regions (Northern Region, ...)
        if nation is None or len(counties) != 20:
            raise ValueError(f"table 34: expected the Taiwan area and 20 counties, got {len(counties)}")
        print(f"    {len(counties)} counties; Taiwan area employed {nation['employed']:,} in {len(cols)} occupation groups")
        return {
            "vintage": f"Manpower Survey {ROC_YEAR + 1911} annual averages (DGBAS), table 34",
            "_files": [FILE],
            "year": ROC_YEAR + 1911,
            "unit": 1000,  # every published figure is a whole number of thousands
            "groups": labels,
            "nation": nation,
            "counties": counties,
        }
