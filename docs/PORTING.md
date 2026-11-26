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
* `web/dev/` (art gallery, trailer maker) is not ported: its titles and the trailer storyboard still describe the US
  build. It is not part of the published site (`pipeline package` skips it, and so does the gh-pages deploy).

## Ids kept, meanings changed

`docs/DATA_CONTRACTS.md` still describes the US meaning of some fields. The ids stay (the frontend links to them);
in Taiwan they mean the following. Each replaced lens carries a `note` in lenses.json saying so.

| id | Taiwan meaning | source |
|---|---|---|
| `median_income` (cities, states, nation) | median total income per tax unit on filed returns, NT$ (not household income) | `mof_county_income` |
| `median_rent`, `home_value`, `rent_burden` (cities, states) | null: no county figure on a common basis | |
| `gdp` / Gold | census value added of industry and services, by the county where the firm is registered | `ics_census` |
| lens `income` | median 綜合所得總額 per tax unit, by township | `mof_income` |
| lens `poverty` | first-quartile income per tax unit (higher is better) | `mof_income` |
| lens `foreign_born` | share of elementary pupils with a new-immigrant parent | `moe_pupils` |
| lens `broadband` | mean mobile download speed, Mbps | `moda_mobile_speed` |
| lens `commute` | weekday daytime ÷ night-time population | `moi_telecom_population` |
| lens `homeownership` | share of homes usually lived in | `census_housing` |
| lens `uninsured` | physicians per 10,000 residents | `mohw_workforce` |
| lens `amenities` | health index from the standardised mortality ratio | `ris_demographics` |
| lens `disasters` | debris-flow potential streams | `ardswc_debris_flow` |
| lens `veterans` | indigenous share of registered population | `ris_demographics` |
| counties `cbsa` | the township's COUNTYCODE (= its city id) | |
| industry `retail` / `utilities` / `admin` | 批發及零售業 / 電力燃氣 + 用水供應及污染整治 / 支援服務業 | `dgbas_labor` |
