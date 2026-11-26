"""disasters.json – Central Emergency Operation Center activations with reported disaster cases, by township and
county (National Fire Agency), and the national natural-disaster record by year (Ministry of the Interior
statistics). Lazy-loaded by the Disasters advisor and the City View; see docs/DATA_CONTRACTS.md.

The file keeps the US contract's two blocks and their field names, so the same frontend reads it:

* `fema`  (US: FEMA major-disaster declarations by county) → named activations of the Central Emergency Operation
  Center in which a township filed at least one disaster case. `counties` rows are townships (TOWNCODE), `states`
  keys are counties (COUNTYCODE).
* `noaa`  (US: NOAA billion-dollar disasters by state) → natural disasters recorded nationally per year, by kind,
  with deaths. The source has no money value and no county breakdown: every `cost_usd` is null and `states` is {}.

Also the shared helper `county_declarations()`, for a Disasters lens and a counties.json column, so all three count
activations the same way.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from ..core.store import load_interim, load_interim_payload, write_web
from ..sources.nfa_disaster_cases import HAZARD_WORDS

REQUIRES = ["_world", "tw_boundaries", "nfa_disaster_cases", "moi_disaster_losses"]
PRODUCES = ["disasters.json"]

TYPE_NAMES = {"typhoon": "颱風", "earthquake": "地震", "flood": "豪雨與水災"}
# `incident_types`: the words in an activation's name that put it in the type (other = no word matched).
FEMA_TYPES = [{"id": t, "name": n, "incident_types": [w for tid, w in HAZARD_WORDS if tid == t]} for t, n in TYPE_NAMES.items()]
FEMA_TYPES.append({"id": "other", "name": "其他", "incident_types": []})
TYPE_IDS = [t["id"] for t in FEMA_TYPES]
RECENT_DAYS = 365
FEMA_TITLE = "中央災害應變中心開設期間有災情通報的事件"
NOAA_TITLE = "全國天然災害紀錄"
NOAA_UNIT = "新臺幣（來源未公布損失金額）"
FEMA_RULE = ("{start} 至 {end} 間中央災害應變中心開設的具名事件中，該鄉鎮市區在內政部消防署應變管理資訊雲端服務"
             "（EMIC）至少通報一件災情者，每個事件計一次；類型依事件名稱中的字詞判定（颱風、地震、豪雨／水災）。"
             "縣市只要轄內有任何一件通報即計一次，所以各縣市的數字彼此重疊，不可加總為全國數。"
             "災情案件是通報紀錄（路樹倒塌、停電、道路積淹水、建物受損等），不是損失的量度，各地方政府通報的習慣也"
             "不同。{cases} 件案件中有 {unmatched} 件的鄉鎮市區無法對應到地圖，只計入所屬縣市。資料公布至 {end}，"
             "下載日為 {as_of}，所以「近 {days} 天」的清單可能是空的。臺灣沒有美國 FEMA 那種以縣為單位的災害宣告，"
             "這裡改用應變中心開設期間的災情通報。")
NOAA_RULE = ("內政部消防署登錄的歷年天然災害，依災害別（風災、水災、震災、其他）列出發生次數，以及死亡、失蹤、受傷"
             "人數與房屋全倒、半倒戶數（內政部統計處「天然災害損失─按災害別分」）。只有全國數：該表沒有金額，也沒有"
             "縣市別，所以沒有損失金額，也沒有縣市分項。表中印「-」之處（無數值，多半是當年沒有該類災害）"
             "視為無資料，加總時略過。臺灣沒有相當於美國 NOAA「十億美元級災害」的統計，這裡改用內政統計的全國天然災害紀錄。")


def incident_type(event: dict) -> str:
    return event["type"] if event["type"] in TYPE_IDS else "other"


def county_declarations(cases: dict, counties: list[str]) -> dict[str, dict]:
    """TOWNCODE → {"total", <type id>: n, "last_date"} for every township on the map: the number of activations
    with at least one case filed in the township (0 = none in the window, a real zero), by type, and the date of
    its latest case. `cases` is the `nfa_disaster_cases` interim."""
    out = {g: {"total": 0, **{t: 0 for t in TYPE_IDS}, "last_date": None} for g in counties}
    for e in cases["events"].values():
        t = incident_type(e)
        for g in e["towns"]:
            rec = out.get(g)
            if rec is None:
                continue
            rec["total"] += 1
            rec[t] += 1
            last = e["town_last"].get(g)
            if last and (rec["last_date"] is None or last > rec["last_date"]):
                rec["last_date"] = last
    return out


def _sum(values) -> int | None:
    """Sum that skips nulls; None when every value is null."""
    vals = [v for v in values if v is not None]
    return sum(vals) if vals else None


def build() -> None:
    world = load_interim("_world")
    bounds = load_interim("tw_boundaries")
    cases_payload = load_interim_payload("nfa_disaster_cases")
    cases = cases_payload["data"]
    losses_payload = load_interim_payload("moi_disaster_losses")
    losses = losses_payload["data"]
    towns = world["counties"]
    county_of = {t["geoid"]: t["state_fips"] for t in bounds["counties"]}
    events = cases["events"]

    per = county_declarations(cases, towns)
    cols = ["geoid", "total", *TYPE_IDS, "last_date"]
    rows = [[g, *(per[g][c] for c in cols[1:])] for g in towns]

    # Counties: every county on the map, activations with at least one case filed in it.
    states = {c: {"total": 0, "statewide": None, "by_type": {t: 0 for t in TYPE_IDS}, "cases": 0} for c in world["states"]}
    national = {"events": len(events), "cases": cases["cases"], "by_type": {t: 0 for t in TYPE_IDS}}
    event_list = []
    for num, e in events.items():
        t = incident_type(e)
        national["by_type"][t] += 1
        for c, n in e["counties"].items():
            if c in states:
                states[c]["total"] += 1
                states[c]["by_type"][t] += 1
                states[c]["cases"] += n
        event_list.append({"disaster": int(num), "name": e["name"], "type": t, "incident_type": e["hazard_word"] or None,
                           "first": e["first"], "last": e["last"], "cases": e["cases"],
                           "counties": len(e["counties"]), "townships": len(e["towns"]), "kinds": e["kinds"]})

    # Activations whose latest case falls within RECENT_DAYS of the day the files were fetched, one row per
    # activation and county (the shape of a US declaration: one disaster, one state, its counties).
    as_of = cases["as_of"] or cases["window_end"]
    cutoff = (date.fromisoformat(as_of) - timedelta(days=RECENT_DAYS)).isoformat()
    recent = []
    state_index = {c: k for k, c in enumerate(world["states"], 1)}
    for num, e in events.items():
        if e["last"] < cutoff:
            continue
        for c in e["counties"]:
            if c not in state_index:
                continue
            mapped = sorted(g for g in e["towns"] if county_of.get(g) == c)
            recent.append({"disaster": int(num) * 100 + state_index[c], "event": int(num), "type": incident_type(e),
                           "incident_type": e["hazard_word"] or None, "title": e["name"], "date": e["last"], "state": c,
                           "counties": mapped, "statewide": False, "areas": len(mapped)})
    recent.sort(key=lambda r: (r["date"], r["disaster"]), reverse=True)

    y0, y1 = losses["years"]
    by_year = []
    for y in losses["by_year"]:
        tot = y["total"]
        by_year.append({"year": y["year"], "events": tot["events"], "cost_usd": None, "deaths": tot["deaths"],
                        "missing": tot["missing"], "injured": tot["injured"],
                        "houses_destroyed": tot["houses_destroyed"], "houses_damaged": tot["houses_damaged"],
                        "by_type": {k["id"]: (y.get(k["id"]) or {}).get("events") for k in losses["kinds"]}})
    noaa_out = {
        "years": [y0, y1], "final": False,
        "unit": NOAA_UNIT,
        "rule": NOAA_RULE,
        "types": [{"id": k["id"], "name": k["label"]} for k in losses["kinds"]],  # names as the table prints them
        "states": {},
        "national": {
            "events": _sum(y["events"] for y in by_year), "cost_usd": None,
            "deaths": _sum(y["deaths"] for y in by_year), "missing": _sum(y["missing"] for y in by_year),
            "injured": _sum(y["injured"] for y in by_year),
            "by_type": {k["id"]: _sum(y["by_type"][k["id"]] for y in by_year) for k in losses["kinds"]},
            "by_year": by_year,
            "costliest": [],
        },
    }

    unmatched = sum(cases["unmatched"].values())
    write_web("disasters.json", {
        "version": 1,
        "vintage": {"fema": cases_payload["vintage"], "noaa": losses_payload["vintage"]},
        "sources": ["nfa_disaster_cases", "moi_disaster_losses"],
        "fema": {
            "title": FEMA_TITLE,
            "window": [cases["window_start"], cases["window_end"]], "as_of": as_of,
            "rule": FEMA_RULE.format(start=cases["window_start"], end=cases["window_end"], unmatched=unmatched,
                                     cases=cases["cases"], as_of=as_of, days=RECENT_DAYS),
            "types": FEMA_TYPES,
            "counties": {"columns": cols, "rows": rows},
            "states": states,
            "national": national,
            "events": event_list,
            "recent_days": RECENT_DAYS,
            "recent": recent,
        },
        "noaa": {"title": NOAA_TITLE, **noaa_out},
    })
    hit = sum(1 for r in rows if r[1])
    top = max(rows, key=lambda r: r[1])
    print(f"    {len(events)} activations, {cases['cases']} cases; {hit} of {len(rows)} townships filed at least one "
          f"(most: {top[0]} with {top[1]}); {len(recent)} county rows in the last {RECENT_DAYS} days; "
          f"{unmatched} cases without a mapped township; national record {y0}-{y1}: "
          f"{noaa_out['national']['events']} disasters, {noaa_out['national']['deaths']} deaths")


# ---------------------------------------------------------------- check


def check(web_dir) -> list[tuple[str, str]]:
    web_dir = Path(web_dir)
    path = web_dir / "disasters.json"
    if not path.exists():
        return [("NOTE", "disasters.json not built (optional; run: uv run python -m pipeline build disasters --deps)")]
    out = []
    fail = lambda m: out.append(("FAIL", f"disasters.json: {m}"))
    doc = json.loads(path.read_text())
    for k in ("version", "vintage", "sources", "fema", "noaa"):
        if k not in doc:
            fail(f"missing key {k!r}")
    if any(lv == "FAIL" for lv, _ in out):
        return out
    fema, noaa = doc["fema"], doc["noaa"]
    try:
        world = json.loads((web_dir / "world.json").read_text())
        geoids = [c.get("geoid") if isinstance(c, dict) else c for c in world.get("counties") or []] or None
        fips = {s.get("fips") for s in world.get("states") or []} or None
    except (OSError, ValueError):
        geoids = fips = None
    cols = fema.get("counties", {}).get("columns")
    rows = fema.get("counties", {}).get("rows")
    type_ids = [t.get("id") for t in fema.get("types", [])]
    if cols != ["geoid", "total", *type_ids, "last_date"]:
        fail(f"fema.counties.columns {cols} do not match the types")
    elif not isinstance(rows, list):
        fail("fema.counties.rows missing")
    else:
        if isinstance(geoids, list) and [r[0] for r in rows] != geoids:
            fail("fema.counties rows are not in world.json counties order")
        bad = [r[0] for r in rows if len(r) != len(cols) or not all(isinstance(v, int) and v >= 0 for v in r[1:-1])
               or sum(r[2:-1]) != r[1] or (r[-1] is not None and not isinstance(r[-1], str))
               or (r[1] > 0) != (r[-1] is not None)]
        if bad:
            fail(f"{len(bad)} township rows malformed or with types not summing to total (e.g. {bad[:3]})")
        else:
            hit = sum(1 for r in rows if r[1])
            out.append(("PASS", f"fema: {len(rows)} townships, {hit} with at least one activation, window "
                                f"{fema.get('window')}, {len(fema.get('recent', []))} recent rows"))
    for st, v in (fema.get("states") or {}).items():
        if sum(v.get("by_type", {}).values()) != v.get("total"):
            fail(f"fema.states.{st}: by_type does not sum to total")
            break
        if fips and st not in fips:
            fail(f"fema.states.{st}: not a COUNTYCODE of world.json")
            break
    nat_f = fema.get("national") or {}
    if sum((nat_f.get("by_type") or {}).values()) != nat_f.get("events"):
        fail("fema.national.by_type does not sum to national.events")
    recent = fema.get("recent", [])
    if [r.get("date") for r in recent] != sorted((r.get("date") for r in recent), reverse=True):
        fail("fema.recent is not newest first")
    nat = noaa.get("national", {})
    # noaa.states is {} on purpose: the national record has no county breakdown (see noaa.rule).
    if not isinstance(noaa.get("states"), dict) or not nat.get("by_year"):
        fail("noaa.states or noaa.national.by_year missing")
    elif sum(y["events"] for y in nat["by_year"] if y["events"] is not None) != nat.get("events"):
        fail("noaa.national.by_year events do not sum to national.events")
    elif any(y.get("cost_usd") is not None for y in nat["by_year"]) or nat.get("cost_usd") is not None:
        fail("noaa cost fields must be null (the source has no money value)")
    else:
        out.append(("PASS", f"noaa: national record {noaa.get('years')}, {nat['events']} disasters, "
                            f"{nat.get('deaths')} deaths, no cost published (null)"))
    size = path.stat().st_size
    out.append(("PASS" if size < 600_000 else "NOTE", f"disasters.json is {size / 1e3:.0f} kB (lazy-loaded)"))
    return out
