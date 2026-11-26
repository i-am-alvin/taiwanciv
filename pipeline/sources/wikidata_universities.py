"""Coordinates of Taiwan's higher-education institutions, from Wikidata (the ministry's directory has addresses only)."""

from __future__ import annotations

import json
import re
import urllib.parse

from ..core import fetch
from ..core.source import Source, SourceInfo


def _retrieved(source_id: str) -> str:
    """The day the raw file was downloaded (from the manifest); the publisher dates nothing itself."""
    return max((m.get("retrieved", "")[:10] for m in fetch.read_manifest(source_id).values()), default="") or "date unknown"


# Every item in Taiwan (P17 = Q865) that is a kind of higher-education institution (Q38723) and has coordinates.
QUERY = """SELECT ?item ?coord ?zhtw ?zhhant ?zh ?official ?en WHERE {
  ?item wdt:P17 wd:Q865; wdt:P31/wdt:P279* wd:Q38723; wdt:P625 ?coord.
  OPTIONAL { ?item rdfs:label ?zhtw FILTER(LANG(?zhtw) = "zh-tw") }
  OPTIONAL { ?item rdfs:label ?zhhant FILTER(LANG(?zhhant) = "zh-hant") }
  OPTIONAL { ?item rdfs:label ?zh FILTER(LANG(?zh) = "zh") }
  OPTIONAL { ?item wdt:P1448 ?official }
  OPTIONAL { ?item rdfs:label ?en FILTER(LANG(?en) = "en") }
}"""
URL = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(QUERY)
FILE = "universities.json"


class WikidataUniversities(Source):
    info = SourceInfo(
        id="wikidata_universities",
        title="Coordinates of universities and colleges in Taiwan (Wikidata)",
        publisher="Wikidata (Wikimedia Foundation)",
        homepage="https://www.wikidata.org/",
        license="CC0 1.0 (public domain dedication)",
        description="Latitude and longitude (property P625) of each higher-education institution in Taiwan, with its "
        "Chinese names. The Ministry of Education's directory gives addresses but no coordinates, so a school is "
        "placed at its Wikidata point nearest the township of its registered address; a school with several "
        "campuses has several points.",
        used_for=["University wonders: position on the map"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        doc = json.loads((self.raw_dir / FILE).read_text(encoding="utf-8"))
        items: dict[str, dict] = {}
        for b in doc["results"]["bindings"]:
            qid = b["item"]["value"].rsplit("/", 1)[1]
            it = items.setdefault(qid, {"qid": qid, "names": [], "name_en": None, "coords": []})
            m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", b["coord"]["value"])
            if m:
                pt = [round(float(m.group(1)), 6), round(float(m.group(2)), 6)]
                if pt not in it["coords"]:
                    it["coords"].append(pt)
            for k in ("zhtw", "zhhant", "official", "zh"):
                if k in b and b[k]["value"] not in it["names"]:
                    it["names"].append(b[k]["value"])
            if "en" in b:
                it["name_en"] = b["en"]["value"]
        return {
            "vintage": f"Wikidata query service, retrieved {_retrieved(self.id)}",
            "_files": [FILE],
            "institutions": sorted(items.values(), key=lambda i: int(i["qid"][1:])),
        }
