"""Registered temples by township and main deity, from the Ministry of the Interior's national religion register.

The raw file lists every registered temple with its main deity (主祀神祇), religion (教別), address and coordinates.
It also carries the caretaker's name and a phone number: process() reads only the deity, religion, county, address
and coordinates, and returns nothing but counts per township.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ..core.source import Source, SourceInfo
from ._tw_towns import TownIndex

URL = "https://religion.moi.gov.tw/Report/temple.xml"
FILE = "temple.xml"

# Deity groups, tested in this order: a temple belongs to the first group one of whose keywords appears in its
# main deity. This is a classification rule (which names count as the same cult), not data.
DEITY_GROUPS = [
    {"id": "earth_god", "name": "福德正神（土地公）", "name_en": "Earth God", "keywords": ["福德", "土地公", "伯公", "后土"]},
    {"id": "mazu", "name": "天上聖母（媽祖）", "name_en": "Mazu", "keywords": ["天上聖母", "媽祖", "天后"]},
    {"id": "wangye", "name": "王爺／千歲", "name_en": "Wangye (Royal Lords)", "keywords": ["千歲", "王爺", "代天巡狩", "府王"]},
    {"id": "guanyin", "name": "觀音", "name_en": "Guanyin", "keywords": ["觀音", "觀世音"]},
    {"id": "buddha", "name": "釋迦牟尼佛等諸佛", "name_en": "Buddhas (Sakyamuni, Amitabha ...)",
     "keywords": ["釋迦", "阿彌陀", "三寶佛", "西方三聖", "彌勒", "藥師", "地藏", "佛祖"]},
    {"id": "xuantian", "name": "玄天上帝", "name_en": "Xuantian Shangdi (Dark Heavenly Emperor)", "keywords": ["玄天", "真武", "上帝公", "北極大帝"]},
    {"id": "guandi", "name": "關聖帝君", "name_en": "Guan Yu", "keywords": ["關聖", "文衡聖帝", "關帝", "關公", "恩主"]},
    {"id": "baosheng", "name": "保生大帝", "name_en": "Baosheng Dadi", "keywords": ["保生大帝", "大道公", "吳真人"]},
    {"id": "sanshan", "name": "三山國王", "name_en": "Kings of the Three Mountains", "keywords": ["三山國王"]},
    {"id": "nezha", "name": "中壇元帥（太子爺）", "name_en": "Nezha", "keywords": ["中壇元帥", "太子", "哪吒"]},
]
OTHER = {"id": "other", "name": "其他神祇", "name_en": "Other deities"}


def deity_group(deity: str) -> str:
    for g in DEITY_GROUPS:
        if any(k in deity for k in g["keywords"]):
            return g["id"]
    return OTHER["id"]


class MoiTemples(Source):
    info = SourceInfo(
        id="moi_temples",
        title="Registered temples (全國宗教資訊網 寺廟登記資料)",
        publisher="Ministry of the Interior, Department of Religious Affairs (內政部宗教及禮制司)",
        homepage="https://religion.moi.gov.tw/",
        license="Government Open Data License v1.0",
        description="The national register of temples (寺廟): Taoist, Buddhist, I-Kuan Tao and other temples "
        "registered with local governments, each with its main deity. Counted per township, and grouped by main "
        "deity. Churches, mosques and unregistered shrines are not in this register. Names and phone numbers "
        "in the file are not used.",
        used_for=["Temples per 10,000 residents", "Most common main deity"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force)

    def process(self):
        towns = TownIndex()
        out: dict[str, dict] = {}
        by_address = by_point = lost = 0
        national: dict[str, int] = {}
        for _, node in ET.iterparse(self.raw_dir / FILE):
            if node.tag != "OpenData_3":
                continue
            rec = {c.tag: (c.text or "").strip() for c in node}
            node.clear()
            g = towns.in_address(rec.get("地址", ""), rec.get("行政區"))
            if g is not None:
                by_address += 1
            else:
                try:
                    g = towns.locate(float(rec["WGS84X"]), float(rec["WGS84Y"]))
                except (KeyError, ValueError):
                    g = None
                if g is None:
                    lost += 1
                    continue
                by_point += 1
            t = out.setdefault(g, {"temples": 0, "groups": {}, "religion": {}})
            grp = deity_group(rec.get("主祀神祇", ""))
            rel = rec.get("教別") or "未註明"
            t["temples"] += 1
            t["groups"][grp] = t["groups"].get(grp, 0) + 1
            t["religion"][rel] = t["religion"].get(rel, 0) + 1
            national[grp] = national.get(grp, 0) + 1
        total = by_address + by_point
        print(f"    {total:,} temples in {len(out)} townships ({by_address:,} placed by address, {by_point} by coordinates, "
              f"{lost} not placed); groups {dict(sorted(national.items(), key=lambda kv: -kv[1]))}")
        return {
            "vintage": "Temple register as downloaded (see the file's retrieval date)",
            "_files": [FILE],
            "groups": [{k: g[k] for k in ("id", "name", "name_en", "keywords")} for g in DEITY_GROUPS] + [dict(OTHER, keywords=[])],
            "national": national,
            "placed": {"address": by_address, "coordinates": by_point, "not_placed": lost},
            "towns": out,  # TOWNCODE → {temples, groups: {group id: n}, religion: {教別: n}}; no entry = no registered temple
        }
