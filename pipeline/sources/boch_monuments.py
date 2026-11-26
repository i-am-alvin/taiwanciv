"""National monuments (國定古蹟) from the Bureau of Cultural Heritage's open data (文化部文化資產局)."""

from __future__ import annotations

import json

from ..core import fetch
from ..core.source import Source, SourceInfo


def _retrieved(source_id: str) -> str:
    """The day the raw file was downloaded (from the manifest); the publisher dates nothing itself."""
    return max((m.get("retrieved", "")[:10] for m in fetch.read_manifest(source_id).values()), default="") or "date unknown"


URL = "https://data.boch.gov.tw/opendata/v2/assetsCase/1.1.json"  # 古蹟 (monuments), data.gov.tw dataset 6246
FILE = "monuments.json"
NATIONAL = "國定古蹟"
DESIGNATION = "指定/登錄"  # the kind of announcement that designates a monument (others amend or revoke)


def _f(text) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


class BochMonuments(Source):
    info = SourceInfo(
        id="boch_monuments",
        title="Monuments register (文資局古蹟), national monuments",
        publisher="Ministry of Culture, Bureau of Cultural Heritage (文化部文化資產局)",
        homepage="https://data.gov.tw/dataset/6246",
        license="Government Open Data License v1.0",
        description="The national register of monuments (古蹟) designated under the Cultural Heritage Preservation "
        "Act, with each site's coordinates, address and announcements. Only the national monuments (國定古蹟, "
        "designated by the Ministry of Culture) are kept; a monument's designation year is the year of its earliest "
        "designation announcement in the register.",
        used_for=["Landmark wonders: position, name, designation year"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        doc = json.loads((self.raw_dir / FILE).read_text(encoding="utf-8"))
        out = []
        for k, c in enumerate(doc):
            if c.get("assetsClassifyName") != NATIONAL:
                continue
            dates = sorted(a["registerDate"][:10] for a in c.get("announcementList") or []
                           if a.get("classification") == DESIGNATION and a.get("registerDate"))
            addr = (c.get("addresses") or [{}])[0]
            out.append({
                "case_id": c["caseId"], "name": (c.get("caseName") or "").strip(), "index": k,
                "lon": _f(c.get("longitude")), "lat": _f(c.get("latitude")),
                "designated": dates[0] if dates else None,
                "types": [t.get("name") for t in c.get("assetsTypes") or [] if t.get("name")],
                "city": addr.get("cityName"), "district": addr.get("distName"),
                "authority": c.get("govInstitutionName"), "url": c.get("caseUrl"),
            })
        if not out:
            raise ValueError("no national monuments in the register file")
        return {
            "vintage": f"BOCH monuments register, retrieved {_retrieved(self.id)}",
            "_files": [FILE],
            "registered": len(doc),
            "monuments": sorted(out, key=lambda m: m["case_id"]),
        }
