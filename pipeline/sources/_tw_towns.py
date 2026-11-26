"""Township names → TOWNCODE, for sources whose files only carry names (not a source itself: no Source subclass).

Everything is matched inside its county (東區, 中山區, 信義區 ... repeat across counties), after normalising 台→臺 and
a few variant characters. The names and outlines come from the `tw_boundaries` interim.
"""

from __future__ import annotations

import re

from ..core.geo import Shape, ShapeIndex
from ..core.store import load_interim

# Variant characters seen in government files → the form the Ministry of the Interior boundary file uses.
VARIANTS = str.maketrans({"台": "臺", "塩": "鹽", "峯": "峰", "双": "雙", "舘": "館", "脚": "腳", "　": "", " ": ""})
SUFFIX = "鄉鎮市區"


def norm(text: str | None) -> str:
    return (text or "").strip().translate(VARIANTS)


def _boundaries() -> dict:
    """The tw_boundaries interim, or the same data straight from its raw file when it has not been processed yet
    (`process` runs sources in id order, and most of the name-keyed sources sort before tw_boundaries)."""
    try:
        return load_interim("tw_boundaries")
    except FileNotFoundError:
        from .tw_boundaries import TwBoundaries

        return TwBoundaries().process()


class TownIndex:
    """Lookups over the 368 townships of the `tw_boundaries` interim."""

    def __init__(self, boundaries: dict | None = None):
        b = boundaries or _boundaries()
        self.county_name = {s["fips"]: norm(s["name"]) for s in b["states"]}
        self.county_code = {v: k for k, v in self.county_name.items()}
        self.codes = [t["geoid"] for t in b["counties"]]
        self.county_of = {t["geoid"]: t["state_fips"] for t in b["counties"]}
        self.name = {t["geoid"]: norm(t["name"]) for t in b["counties"]}
        self._towns: dict[str, dict[str, str]] = {c: {} for c in self.county_name}  # county code → town name → geoid
        for t in b["counties"]:
            self._towns[t["state_fips"]][norm(t["name"])] = t["geoid"]
        self._full = {self.county_name[self.county_of[g]] + self.name[g]: g for g in self.codes}
        self._shapes = ShapeIndex([Shape([[tuple(p) for p in r] for r in t["rings"]]) for t in b["counties"]], 0.25)

    def county(self, name: str) -> str | None:
        """COUNTYCODE of a county name; a renamed county (桃園縣 → 桃園市) matches on its stem."""
        n = norm(name)
        if n in self.county_code:
            return self.county_code[n]
        hits = [c for c, cn in self.county_name.items() if n and cn[:-1] == n[:-1]]
        return hits[0] if len(hits) == 1 else None

    def town(self, county: str, town: str) -> str | None:
        """TOWNCODE of (county name, town name); a township whose suffix changed (員林鎮 → 員林市) matches on its stem."""
        c = self.county(county)
        if c is None:
            return None
        towns, n = self._towns[c], norm(town)
        if n in towns:
            return towns[n]
        if len(n) >= 3 and n[-1] in SUFFIX:
            hits = [g for name, g in towns.items() if name[:-1] == n[:-1]]
            if len(hits) == 1:
                return hits[0]
        return None

    def full(self, name: str) -> str | None:
        """TOWNCODE of a 'county + township' string such as 新北市板橋區."""
        n = norm(name)
        if n in self._full:
            return self._full[n]
        return self.town(n[:3], n[3:]) if len(n) > 3 else None

    def in_address(self, address: str, county: str | None = None) -> str | None:
        """TOWNCODE of the township an address starts with (after an optional postal code and the county name)."""
        a = re.sub(r"^[\d\-\s]+", "", norm(address))
        c = self.county(a[:3]) if len(a) >= 3 else None
        if c is not None:
            a = a[3:]
        else:
            c = self.county(county) if county else None
        if c is None:
            return None
        towns = self._towns[c]
        for n in (4, 3, 2):  # township names are 2-4 characters with their suffix
            if a[:n] in towns:
                return towns[a[:n]]
        for n in (4, 3):  # same stem, other suffix (桃園縣中壢市 → 中壢區)
            if len(a) >= n and a[n - 1] in SUFFIX:
                hits = [g for name, g in towns.items() if name[:-1] == a[: n - 1]]
                if len(hits) == 1:
                    return hits[0]
        return None

    def locate(self, lon: float, lat: float) -> str | None:
        """TOWNCODE of the township outline containing a WGS84 point."""
        k = self._shapes.locate(lon, lat)
        return self.codes[k] if k >= 0 else None
