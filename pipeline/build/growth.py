"""Population growth from the household registration (ris_population), one consistent series.

Helper module (no build()): used by cities.py and states.py.

growth = population(end) / population(BASELINE_YEAR) - 1, over growth_years = [BASELINE_YEAR, end], where both are
year-end registered populations of the same 368 townships (every yearly file uses today's township list;
ris_population fails if one does not), so every area is compared like for like. `end` is the latest year fetched (nation.json "year").

growth is null (never a guess) when a population is missing or |growth| > MAX_GROWTH (a last sanity check).
"""

from __future__ import annotations

MAX_GROWTH = 0.25
BASELINE_YEAR = 2021


def rate(latest: float | None, earlier: float | None) -> float | None:
    """latest / earlier - 1, rounded; None if either is missing or |rate| > MAX_GROWTH."""
    if not latest or not earlier:
        return None
    g = latest / earlier - 1
    return round(g, 4) if abs(g) <= MAX_GROWTH else None


class Growth:
    """Growth rates and yearly series from the ris_population interim."""

    def __init__(self, ris: dict):
        self.ris = ris
        years = ris["years"]
        self.end = max(years)
        self.years = [BASELINE_YEAR, self.end] if BASELINE_YEAR in years and self.end > BASELINE_YEAR else None
        self._i = (years.index(BASELINE_YEAR), years.index(self.end)) if self.years else None

    def _window(self, pops: list | None) -> float | None:
        if not pops or not self._i:
            return None
        return rate(pops[self._i[1]], pops[self._i[0]])

    def series(self, pops: list | None) -> dict | None:
        return {str(y): v for y, v in zip(self.ris["years"], pops)} if pops else None

    def nation(self) -> float | None:
        return self._window(self.ris["nation"])

    def county(self, fips: str) -> float | None:
        return self._window(self.ris["counties"].get(fips))

    def population(self, fips: str | None = None) -> int | None:
        pops = self.ris["nation"] if fips is None else self.ris["counties"].get(fips)
        return pops[-1] if pops else None
