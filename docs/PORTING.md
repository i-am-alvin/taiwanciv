# Porting usaciv to Taiwan: conventions

This repo started as Karpathy's usaciv (MIT, commit `ebfe42c` is the untouched import). The goal is a 1:1 Taiwan
version: same frontend, same data contracts (`docs/DATA_CONTRACTS.md`), every number from a public Taiwanese (or
global) source that the pipeline downloads itself.

## Units of the map

| US concept | Taiwan | id |
|---|---|---|
| state | 縣市 (22) | `fips` = COUNTYCODE (5 digits, e.g. `63000`, `09020`), `abbr` = ISO 3166-2:TW (`TPE`, `KIN`) |
| county | 鄉鎮市區 (368) | `geoid` = TOWNCODE (8 digits, e.g. `63000010`) |
| city / metro (CBSA) | 縣市 (22) | `id` = COUNTYCODE; member `counties` = its townships |
| nation | 臺灣 (Taiwan, Penghu, Kinmen, Matsu) | |

* Names are official Traditional Chinese with 臺 (not 台): `pipeline/sources/tw_boundaries.official()`. Keep an
  English name in `name_en` where a file has names.
* Join tables on codes, never on names. When a source only has names, map them through the `tw_boundaries` interim
  (normalise 台→臺 first).
* Money is New Taiwan dollars (TWD), current prices. Yield / field units that say `usd` in the US build are TWD here;
  the frontend formats them as NT$.

## Map space

* `pipeline/core/geo.py`: Albers equal-area centred on Taiwan (`TW_ALBERS`), magnified by `SCALE` = 12.5 map units
  per real km. Hex radius is 25 map units = 2.0 km. Everything in `_world` / web JSON is in map units.
* Real distances and areas: divide map lengths by `SCALE` (areas by `SCALE**2`). `MapProjection.km()` helps.
* `_world` interim (from `build/world.py`): `grid`, `projection`, `owner` (cell → index into `states`, -1 water,
  -2 foreign), `county` (cell → index into `counties`), `county_samples`, `states` (COUNTYCODEs), `counties`
  (TOWNCODEs), `water`, `cover`, `pct`.
* Pratas and the Spratlys are outside the map window (as the original leaves out Alaska and Hawaii).

## Sources and builders

* One module per source in `pipeline/sources/` (`fetch` + `process`, standard library only). See
  `tw_boundaries.py`, `srtm15.py`, `worldcover.py`. Use `self.download(...)` so every raw file lands in
  `data/raw/<id>/` with its URL and sha256 in the manifest.
* **No data literals in code.** Every value comes from a downloaded file. A curated list is allowed only for
  *which* items to show (e.g. a wonder list), never for their numbers or positions; cite the rule in the output.
  If something cannot be fetched, the field is `null` (never `0`, never an estimate) or the layer is omitted.
* Builders live in `pipeline/build/`. The US versions are parked in `pipeline/build_us/` for reference: port one by
  copying it back to `pipeline/build/`, changing its `REQUIRES` to Taiwan sources, and keeping its output contract.
  `git show ebfe42c:pipeline/sources/<name>.py` shows any original US source.
* Rule and note texts (`rule`, `note`, `description`, Almanac text) must describe what the Taiwan code does.
* Run: `uv run python -m pipeline fetch <src>`, `process <src>`, `build <builder> --force`.

## Omitted on purpose

* Military (`military.json`): bases are not open data in Taiwan and mapping them is sensitive.
