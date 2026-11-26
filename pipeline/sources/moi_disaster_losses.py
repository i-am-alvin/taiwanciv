"""Natural-disaster losses by year and kind of disaster, national (內政部統計處, from the National Fire Agency)."""

from __future__ import annotations

from ..core.source import Source, SourceInfo
from . import _moi_statis as statis

TABLE = "c0720101"  # 天然災害損失─按災害別分 (data.gov.tw dataset 14368)
FIRST_ROC = 89  # the table starts in ROC 89 (2000)
TOTAL = "災害別總計"
KINDS = {"風災": "typhoon", "水災": "flood", "震災": "earthquake", "其他": "other"}
# Value columns of the table, in order.
FIELDS = ["events", "houses_destroyed", "houses_damaged", "rescuers", "rescued", "deaths", "missing", "injured"]
LOOKBACK = 4


def _int(v: float | None) -> int | None:
    return int(v) if v is not None else None


class MoiDisasterLosses(Source):
    info = SourceInfo(
        id="moi_disaster_losses",
        title="Natural-disaster losses by kind of disaster (內政統計查詢網 table c0720101)",
        publisher="Ministry of the Interior, Department of Statistics (內政部統計處), from the National Fire Agency",
        homepage="https://data.gov.tw/dataset/14368",
        license="Government Open Data License v1.0",
        description="For each year since 2000 and each kind of natural disaster (typhoons, floods, earthquakes, "
        "other): how many disasters were recorded, people killed, missing and injured, and houses destroyed or "
        "half destroyed. National figures only; the table has no money value and no county breakdown.",
        used_for=["Disasters: national record by year and kind"],
    )

    def _file(self, roc: int) -> str:
        return f"disaster_losses_{FIRST_ROC}_{roc}.csv"

    def _years(self, roc: int) -> dict[int, dict]:
        """year → {"total": row, <kind id>: row} from a cached file, each row {"line", <field>: int | None}."""
        _, rows = statis.rows(self.raw_dir / self._file(roc))
        out: dict[int, dict] = {}
        for r in rows:
            if r["month"] is not None or len(r["parts"]) != 1:
                continue
            key = "total" if r["parts"][0] == TOTAL else KINDS.get(r["parts"][0])
            if key is None:
                continue
            rec = {"line": r["line"], **{f: _int(v) for f, v in zip(FIELDS, r["values"])}}
            out.setdefault(r["roc"] + 1911, {})[key] = rec
        return out

    def fetch(self, force=False):
        if self.offline:
            return
        now = statis.roc_year_now()
        for roc in range(now - 1, now - 1 - LOOKBACK, -1):
            self.download(statis.url(TABLE, cycle=4, fields=8, codes=5, ym=f"{FIRST_ROC}00", ymt=f"{roc}00"),
                          self._file(roc), force=force)
            if (self._years(roc).get(roc + 1911, {}).get("total") or {}).get("events") is not None:
                return
            self.discard(self._file(roc))  # the newest year is not published yet
        raise RuntimeError("no published year of natural-disaster losses found")

    def process(self):
        cached = sorted((int(p.stem.rsplit("_", 1)[1]) for p in self.raw_dir.glob(f"disaster_losses_{FIRST_ROC}_*.csv")),
                        reverse=True)
        if not cached:
            raise FileNotFoundError("no natural-disaster losses file: run fetch moi_disaster_losses")
        roc = cached[0]
        years = {y: v for y, v in self._years(roc).items() if "total" in v}
        return {
            "vintage": f"MOI statistics, natural-disaster losses {min(years)}-{max(years)}",
            "_files": [self._file(roc)],
            "years": [min(years), max(years)],
            "kinds": [{"id": v, "label": k} for k, v in KINDS.items()],
            "fields": FIELDS,
            "by_year": [{"year": y, **years[y]} for y in sorted(years)],
        }
