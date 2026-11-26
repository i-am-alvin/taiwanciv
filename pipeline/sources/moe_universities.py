"""Universities and colleges: sponsored-project funding, enrolment and registered address (教育部)."""

from __future__ import annotations

import csv
import re
import urllib.parse
from datetime import date

from ..core.source import Source, SourceInfo
from ._resource_util import download_checked
from ._tw_towns import TownIndex

# 大專校院校務資訊公開平臺, table 研1: project funding each school received from all sponsors, by year.
FUNDING_TABLE = "研1.學校承接各單位資助「各類計畫經費」及其每師平均承接金額-以「校」統計.csv"
FUNDING_URL = "https://udb.moe.edu.tw/download/udata/static_file/{edition}/" + urllib.parse.quote(FUNDING_TABLE)
STUDENTS_URL = "https://stats.moe.gov.tw/files/opendata/student.csv"  # data.gov.tw dataset 6231
DIRECTORY_URL = "https://stats.moe.gov.tw/files/opendata/u1_new.csv"  # data.gov.tw dataset 6091
STUDENTS, DIRECTORY = "student.csv", "u1_new.csv"
LOOKBACK = 4

F_YEAR, F_CODE, F_NAME = "年度", "學校統計處代碼", "學校名稱"
F_TOTAL, F_GOV = "學校承接計畫經費-小計", "學校承接計畫經費-政府部門資助"
F_BUSINESS, F_OTHER = "學校承接計畫經費-企業部門資助", "學校承接計畫經費-其他單位資助"
F_TEACHERS, F_KIND, F_OWNER = "專任教師數", "學校類別", "設立別"


def _code(text: str) -> str:
    return text.strip().zfill(4)


def _num(text: str) -> float | None:
    try:
        return float(text.replace(",", ""))
    except (AttributeError, ValueError):
        return None


def _unbracket(text: str) -> str:
    """'[38]臺北市' → '臺北市'; '[116]臺北市文山區…' → '臺北市文山區…'."""
    return re.sub(r"^\[[^\]]*\]", "", (text or "").strip())


def _read(path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [dict(r, _line=n) for n, r in enumerate(csv.DictReader(f), 2)]


class MoeUniversities(Source):
    info = SourceInfo(
        id="moe_universities",
        title="University project funding (校務資訊公開平臺 研1), enrolment and directory",
        publisher="Ministry of Education (教育部): Department of Higher Education and Department of Statistics",
        homepage="https://udb.moe.edu.tw/udata/DetailReportList/研究類",
        license="Government Open Data License v1.0",
        description="For every university and college: the project funding it received in a year from all sponsors "
        "(government, business and others: research, industry cooperation and other commissioned projects, in "
        "New Taiwan dollars), students with formal enrolment on 15 October (all levels, day and evening), and its "
        "registered address. Project funding is what schools report to the ministry's disclosure platform; it is "
        "not a survey of R&D spending.",
        used_for=["University wonders: ranking, funding, enrolment, township"],
    )

    def _funding_files(self) -> list[str]:
        return sorted((p.name for p in self.raw_dir.glob("project_funding_*.csv")), reverse=True)

    def fetch(self, force=False):
        self.download(STUDENTS_URL, STUDENTS, force=force)
        self.download(DIRECTORY_URL, DIRECTORY, force=force)
        if self.offline:
            return
        now = date.today().year - 1911
        for edition in range(now, now - LOOKBACK, -1):  # the platform files its tables under the ROC year it publishes them
            name = f"project_funding_{edition}.csv"
            path = download_checked(self, FUNDING_URL.format(edition=edition), name, force=force, binary=True)
            if path is None:
                continue
            with open(path, encoding="utf-8-sig") as f:
                if F_TOTAL in f.readline():
                    return
            self.discard(name)  # an error page served as a file
        raise RuntimeError("the 研1 project-funding table was not found on udb.moe.edu.tw")

    def process(self):
        funding_file = next(iter(self._funding_files()), None)
        if funding_file is None:
            raise FileNotFoundError("no project-funding file: run fetch moe_universities")
        towns = TownIndex()

        rows = _read(self.raw_dir / funding_file)
        roc = max(int(r[F_YEAR]) for r in rows)
        funding = {_code(r[F_CODE]): r for r in rows if int(r[F_YEAR]) == roc}

        students = _read(self.raw_dir / STUDENTS)
        s_roc = max(int(r["學年度"]) for r in students)
        enrol: dict[str, int] = {}
        for r in students:
            n = _num(r["總計"])
            if int(r["學年度"]) == s_roc and n is not None:
                enrol[_code(r["學校代碼"])] = enrol.get(_code(r["學校代碼"]), 0) + int(n)

        directory = _read(self.raw_dir / DIRECTORY)
        d_roc = max(int(r["學年度"]) for r in directory)
        address = {_code(r["代碼"]): r for r in directory if int(r["學年度"]) == d_roc}

        out, no_town = [], []
        for code, r in funding.items():
            d = address.get(code)
            county = town = addr = None
            if d:
                addr = _unbracket(d["地址"])
                county = towns.county(_unbracket(d["縣市名稱"]))
                town = towns.in_address(addr, _unbracket(d["縣市名稱"]))
            if town is None:
                no_town.append(r[F_NAME])
            teachers = _num(r[F_TEACHERS])
            out.append({
                "code": code, "name": r[F_NAME].strip(), "kind": r[F_KIND], "owner": r[F_OWNER],
                "funding_twd": _num(r[F_TOTAL]), "government_twd": _num(r[F_GOV]),
                "business_twd": _num(r[F_BUSINESS]), "other_twd": _num(r[F_OTHER]),
                "teachers": int(teachers) if teachers is not None else None,
                "enrollment": enrol.get(code), "county": county, "town": town, "address": addr,
                "funding_line": r["_line"], "directory_line": d["_line"] if d else None,
            })
        out.sort(key=lambda u: -(u["funding_twd"] or 0))
        return {
            "vintage": f"MOE 校務資訊公開平臺 研1, year {roc + 1911} (ROC {roc}); enrolment academic year {s_roc + 1911} "
                       f"(ROC {s_roc}); directory {d_roc + 1911}",
            "_files": [funding_file, STUDENTS, DIRECTORY],
            "year": roc + 1911, "roc_year": roc,
            "enrollment_year": s_roc + 1911, "directory_year": d_roc + 1911,
            "funding_file": funding_file,
            "no_township": no_town,
            "institutions": out,
        }
