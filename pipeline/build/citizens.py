"""Citizens: each city's (縣市) mix of people for the City View's person icons.

Three rows have a Taiwanese source:

* workforce: employed people by occupation, Manpower Survey annual report table 34 (dgbas_occupation). The report
  has seven occupation groups per county, in thousands rounded to the nearest thousand, counted where people live;
  Kinmen and Lienchiang are not in the survey, so their row is null. Only two groups mean the same as a category of
  the original (US) build, and keep its key: `executive` and `farmer`. The other five get keys of their own.
* age and education: household registration at the end of the year (ris_demographics), township values summed over
  the city's member townships (cities.json `counties`). The interim carries three age bands (0-14, 15-64, 65+) and,
  for residents aged 15 and over, how many hold a university degree; so the age row has three categories, the
  education row two, and the city's median age is null (it cannot be computed without the single-year table).

The other two rows of the original have no source here and are null in every city, with no `groups` entry (the City
View leaves out a row type that has none): `commute` (the transport ministry's travel survey, data.gov.tw dataset
6248, points to a query page of statis.motc.gov.tw rather than a file with a stable URL the pipeline can download,
and its county table counts trips of everyone going out, not workers) and `nativity` (no place-of-birth source by
county has been adopted in this build).

Icon counts (`figures`) use largest-remainder rounding, so each row's figures add up exactly to its icon count.
`specialists` lists the categories whose share is at least SPECIALIST_HIGH or at most SPECIALIST_LOW times the
national share (up to MAX_HIGH over-represented, strongest first, then up to MAX_LOW under-represented); a category
counting fewer than MIN_COUNT people in the city is never a specialist, because the survey's cells are rounded to
the thousand and small counties' ratios are noise. The national workforce row is the survey's Taiwan area (20
counties); the national age and education rows add up all 22 counties.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from ..core.paths import WEB_DATA
from ..core.store import load_interim, load_interim_payload, write_web

REQUIRES = ["dgbas_occupation", "ris_demographics", "cities.json"]
PRODUCES = ["citizens.json"]

FIGURES = {"workforce": 20, "age": 10, "commute": 10}
SPECIALIST_HIGH = 1.5
SPECIALIST_LOW = 0.67
MIN_SHARE = 0.01
MIN_COUNT = 5000  # a category with fewer people than this in the city is never a specialist
MAX_HIGH, MAX_LOW = 4, 2  # specialists kept: the strongest over- and under-represented categories
NO_SOURCE = ["commute", "nativity"]  # rows of the original with no Taiwanese county source: null everywhere


def _g(key, label, short, icon, lines, plus, minus=()):
    """A category: `plus` / `minus` = the source fields it adds / subtracts. label None = the source's own name."""
    return {"key": key, "label": label, "short": short, "icon": icon, "lines": lines,
            "_plus": list(plus), "_minus": list(minus)}


def _occ(key, short, icon, field):
    return _g(key, None, short, icon, None, [field])


# Workforce fields are dgbas_occupation's group keys (labels and `lines` are filled from that interim's own names);
# age and education fields are ris_demographics township fields.
GROUPS = {
    "workforce": [
        _occ("executive", "主管經理", "c-executive", "managers"),
        _occ("professional", "專業人員", "c-scholar", "professionals"),
        _occ("technician", "技術員", "c-engineer", "technicians"),
        _occ("clerical", "事務人員", "c-clerk", "clerical"),
        _occ("service_sales", "服務銷售", "c-service", "service_sales"),
        _occ("farmer", "農林漁牧", "c-farmer", "agricultural"),
        _occ("manual", "技藝、操作及勞力", "c-maker", "craft_operators_labourers"),
    ],
    "age": [
        _g("child", "幼年（0–14 歲）", "0–14 歲", "c-child", "ODRP014 單一年齡人口 0–14 歲，男女合計", ["age_0_14"]),
        _g("working_age", "青壯年（15–64 歲）", "15–64 歲", "c-midlife", "ODRP014 單一年齡人口 15–64 歲，男女合計",
           ["age_15_64"]),
        _g("elder", "高齡（65 歲以上）", "65 歲以上", "c-elder", "ODRP014 單一年齡人口 65 歲以上，男女合計", ["age_65_up"]),
    ],
    "education": [
        _g("no_degree", "沒有大學學位（專科以下，或大學肄業）", "無大學學位", "c-edu1",
           "ODRP020 15 歲以上人口總計 − 大學畢業及研究所", ["pop15"], ["degree"]),
        _g("degree", "大學畢業，或曾就讀碩、博士班", "大學以上", "c-edu3",
           "ODRP020 大學畢業＋碩士班（畢業、肄業）＋博士班（畢業、肄業），男女合計", ["degree"]),
    ],
}
TOTALS = {"workforce": "employed", "age": "pop", "education": "pop15"}
ROW_LABELS = {
    "workforce": "就業者的職業別（人力資源調查，依居住縣市計）",
    "age": "戶籍人口的年齡層",
    "education": "15 歲以上戶籍人口的教育程度",
}
TOWN_FIELDS = sorted({f for name in ("age", "education") for g in GROUPS[name] for f in g["_plus"] + g["_minus"]}
                     | {TOTALS["age"], TOTALS["education"]})


def largest_remainder(values: dict[str, float], n: int) -> dict[str, int]:
    """Integer counts summing exactly to n, proportional to `values` (Hamilton's method).

    Ties in the remainders go to the larger value, then to the earlier key, so the result is deterministic.
    Negative values count as 0. All-zero input → all zeros.
    """
    keys = list(values)
    vals = [max(0.0, float(values[k] or 0)) for k in keys]
    total = sum(vals)
    if total <= 0 or n <= 0:
        return {k: 0 for k in keys}
    quotas = [v * n / total for v in vals]
    base = [math.floor(q) for q in quotas]
    left = n - sum(base)
    order = sorted(range(len(keys)), key=lambda i: (-(quotas[i] - base[i]), -vals[i], i))
    for i in order[:left]:
        base[i] += 1
    return dict(zip(keys, base))


def sum_towns(towns: dict[str, dict], geoids: list[str]) -> dict | None:
    """TOWN_FIELDS added up over townships; None when a township (or one of its fields) is missing."""
    out = dict.fromkeys(TOWN_FIELDS, 0)
    if not geoids:
        return None
    for g in geoids:
        t = towns.get(g)
        if t is None or any(t.get(f) is None for f in TOWN_FIELDS):
            return None
        for f in TOWN_FIELDS:
            out[f] += t[f]
    return out


def record(occupation: dict | None, people: dict | None) -> dict:
    """One flat record of source fields: a dgbas_occupation entry ({employed, occupations}) plus summed townships."""
    rec = dict(people or {})
    if occupation:
        rec["employed"] = occupation.get("employed")
        rec.update(occupation.get("occupations") or {})
    return rec


def row(rec: dict, name: str) -> dict | None:
    total = rec.get(TOTALS[name])
    if not total or total <= 0:
        return None
    counts = {}
    for g in GROUPS[name]:
        vals = [rec.get(f) for f in g["_plus"] + g["_minus"]]
        if any(v is None for v in vals):
            return None
        counts[g["key"]] = round(max(sum(rec[f] for f in g["_plus"]) - sum(rec[f] for f in g["_minus"]), 0))
    out = {"total": round(total), "counts": counts,
           "shares": {k: round(v / total, 3) for k, v in counts.items()}}
    if name in FIGURES:
        out["figures"] = largest_remainder(counts, FIGURES[name])
    if name == "age":
        out["median"] = None  # needs the single-year age table, which the ris_demographics interim does not carry
    if name == "education":
        out["bachelors_plus"] = round(counts["degree"] / total, 4)
    return out


def specialists(r: dict, nat: dict) -> list[dict]:
    hi, lo = [], []
    for name in GROUPS:
        a, b = r.get(name), nat.get(name)
        if not a or not b:
            continue
        for k, n in a["counts"].items():
            s, ns = n / a["total"], b["counts"][k] / b["total"]
            if n < MIN_COUNT or not ns or (s < MIN_SHARE and ns < MIN_SHARE):
                continue
            ratio = s / ns
            item = {"row": name, "key": k, "share": round(s, 3), "national": round(ns, 3), "ratio": round(ratio, 2)}
            if ratio >= SPECIALIST_HIGH:
                hi.append(item)
            elif ratio <= SPECIALIST_LOW:
                lo.append(item)
    hi.sort(key=lambda x: -x["ratio"])
    lo.sort(key=lambda x: x["ratio"])
    return hi[:MAX_HIGH] + lo[:MAX_LOW]


def full_row(rec: dict, nat: dict | None) -> dict | None:
    parts = {name: row(rec, name) for name in GROUPS}
    if all(v is None for v in parts.values()):
        return None
    for name in NO_SOURCE:
        parts[name] = None
    if nat is not None:
        parts["specialists"] = specialists(parts, nat)
        # Every 縣市 is marked reliable: the registry rows are full counts, and the survey's rounding is dealt
        # with by the MIN_COUNT floor on specialists (the original used this flag for small-sample metros).
        parts["reliable"] = True
    return parts


def rule_text(unit: int) -> str:
    return (
        f"人像數以最大餘數法取整，每一列的加總與人像總數相符。占比至少為全國的 {SPECIALIST_HIGH:g} 倍、或至多為全國的 "
        f"{SPECIALIST_LOW:g} 倍的類別標為特色（本地與全國占比都不到 {MIN_SHARE:.0%} 的類別略過）；"
        f"在本縣市人數不足 {MIN_COUNT:,} 人的類別一律不標：人力資源調查的縣市數字只公布到千人（四捨五入至 {unit:,} 人），"
        f"小縣市的倍數主要是取整誤差。最多列出 {MAX_HIGH} 個偏高與 {MAX_LOW} 個偏低的類別。"
        "職業別為人力資源調查年報表 34 的七個職業大類（技藝有關工作人員、機械設備操作人員與基層技術工及勞力工在年報中合為一欄），"
        "依居住縣市計；因各欄分別取整，各類加總可能與就業者總數略有出入，占比一律以公布的總數為分母。"
        "調查範圍為臺灣地區，不含金門縣與連江縣，這兩縣沒有職業列；全國的職業組成即臺灣地區（20 縣市）。"
        "年齡與教育程度為戶籍登記的年底人數，由所屬鄉鎮市區加總，全國為 22 縣市合計；年齡分三段（0–14、15–64、65 歲以上），"
        "教育程度的分母是 15 歲以上人口，「大學以上」指大學畢業或曾就讀碩、博士班者。"
        "年齡中位數需要單一年齡資料，目前的資料檔沒有，因此留空。"
        "通勤方式沒有列：交通部「民眾日常使用運具狀況調查」的縣市運具市占率公布在統計查詢網的查詢頁上，"
        "本專案的資料流程沒有可固定下載的檔案網址可用，而且該表統計的是所有外出民眾的旅次，不是就業者的通勤方式。"
        "出生地沒有列：本專案沒有採用任何按縣市統計居民出生地的資料來源。"
    )


def build() -> None:
    occ_p = load_interim_payload("dgbas_occupation")
    ris_p = load_interim_payload("ris_demographics")
    occ, ris = occ_p["data"], ris_p["data"]
    cities = json.loads((WEB_DATA / "cities.json").read_text())
    towns = ris["towns"]
    unit = occ["unit"]

    national = full_row(record(occ["nation"], sum_towns(towns, list(towns))), None)
    if national is None or any(national[name] is None for name in GROUPS):
        raise ValueError("no national row for the citizen tables (run: pipeline process dgbas_occupation ris_demographics)")
    national["specialists"] = []
    out = {}
    for c in cities:
        out[c["id"]] = full_row(record(occ["counties"].get(c["id"]), sum_towns(towns, c.get("counties") or [])), national)

    groups = {}
    for name, gs in GROUPS.items():
        groups[name] = []
        for g in gs:
            e = {k: v for k, v in g.items() if not k.startswith("_")}
            if name == "workforce":  # the survey's own name of the occupation group
                zh = occ["groups"][g["_plus"][0]]["zh"]
                e["label"] = zh
                e["lines"] = f"人力資源調查年報表 34「{zh}」合計欄"
            groups[name].append(e)
    doc = {
        "version": 1,
        "vintage": f"人力資源調查 {occ['year']} 年平均（主計總處，職業）；戶籍登記 {ris['year']} 年底（內政部戶政司，年齡與教育程度）",
        "year": occ["year"],
        "sources": ["dgbas_occupation", "ris_demographics"],
        "figures": dict(FIGURES),
        "rows": dict(ROW_LABELS),
        "groups": groups,
        # Published counts are whole multiples of this many people (the survey rounds to the thousand).
        "units": {"workforce": unit, "age": 1, "education": 1},
        "rule": {
            "specialist_high": SPECIALIST_HIGH, "specialist_low": SPECIALIST_LOW, "min_share": MIN_SHARE,
            "min_count": MIN_COUNT, "max_high": MAX_HIGH, "max_low": MAX_LOW,
            "text": rule_text(unit),
        },
        "national": national,
        "cities": out,
    }
    write_web("citizens.json", doc)


# ---------------------------------------------------------------------------------------------- check


def _check_row(cid: str, r: dict, units: dict, bad) -> None:
    for name in list(GROUPS) + NO_SOURCE:
        if name not in r:
            bad(f"{cid}: missing row {name!r}")
    for name in NO_SOURCE:
        if r.get(name) is not None:
            bad(f"{cid}: {name} has no source in this build and must be null")
    for name in GROUPS:
        v = r.get(name)
        if v is None:
            continue
        keys = [g["key"] for g in GROUPS[name]]
        if list(v.get("counts", {})) != keys or list(v.get("shares", {})) != keys:
            bad(f"{cid}: {name} categories differ from groups")
            continue
        if any(x is None or x < 0 for x in v["counts"].values()):
            bad(f"{cid}: {name} has negative or null counts")
        # Each published figure (the categories and the total) is rounded on its own to `unit`, so the sum may
        # be off by half a unit per figure.
        unit = units.get(name) or 1
        tol = max(2, 0.001 * v["total"]) if unit == 1 else unit / 2 * (len(keys) + 1)
        if abs(sum(v["counts"].values()) - v["total"]) > tol:
            bad(f"{cid}: {name} counts sum {sum(v['counts'].values())} != total {v['total']}")
        if name in FIGURES:
            f = v.get("figures") or {}
            if list(f) != keys or sum(f.values()) != FIGURES[name]:
                bad(f"{cid}: {name} figures must cover every category and sum to {FIGURES[name]}")


def check(web_dir: Path) -> list[tuple[str, str]]:
    web_dir = Path(web_dir)
    p = web_dir / "citizens.json"
    if not p.exists():
        return [("NOTE", "citizens.json: missing (optional, skipped)")]
    out: list[tuple[str, str]] = []
    bad = lambda m: out.append(("FAIL", f"citizens.json: {m}"))  # noqa: E731
    try:
        doc = json.loads(p.read_text())
    except ValueError as exc:
        return [("FAIL", f"citizens.json: invalid JSON ({exc})")]
    if not isinstance(doc, dict):
        return [("FAIL", "citizens.json: top level is not an object")]
    for k in ("version", "vintage", "year", "sources", "figures", "groups", "national", "cities"):
        if k not in doc:
            bad(f"missing key {k!r}")
    if out:
        return out
    sp = web_dir / "sources.json"
    if sp.exists() and isinstance(doc["sources"], list):
        try:
            known = {x.get("id") for x in json.loads(sp.read_text()) if isinstance(x, dict)}
        except (ValueError, AttributeError):
            known = None
        if known is not None and set(doc["sources"]) - known:
            out.append(("WARN", f"citizens.json: sources missing from sources.json: {sorted(set(doc['sources']) - known)}"))
    if doc["version"] != 1:
        bad(f"version {doc['version']!r} != 1")
    if doc["figures"] != FIGURES:
        bad(f"figures {doc['figures']} != {FIGURES}")
    if set(doc["groups"]) != set(GROUPS):
        bad(f"groups rows {sorted(doc['groups'])} differ from {sorted(GROUPS)}")
    for name, gs in GROUPS.items():
        got = [g.get("key") for g in doc["groups"].get(name, [])]
        if got != [g["key"] for g in gs]:
            bad(f"groups.{name} keys {got} differ from the contract")
        for g in doc["groups"].get(name, []):
            if not g.get("label") or not g.get("lines"):
                bad(f"groups.{name}.{g.get('key')}: label and lines are required")
    units = doc.get("units") if isinstance(doc.get("units"), dict) else {}
    if not isinstance(doc["national"], dict):
        bad("national row missing")
    else:
        _check_row("national", doc["national"], units, bad)
    cities = doc["cities"] if isinstance(doc["cities"], dict) else {}
    cp = web_dir / "cities.json"
    if cp.exists():
        try:
            ids = {c.get("id") for c in json.loads(cp.read_text()) if isinstance(c, dict)}
        except (ValueError, TypeError, AttributeError):
            ids = None
        if ids is not None:
            if ids - set(cities):
                bad(f"{len(ids - set(cities))} cities.json ids missing, e.g. {sorted(ids - set(cities))[:3]}")
            if set(cities) - ids:
                bad(f"{len(set(cities) - ids)} ids not in cities.json")
    min_count = (doc.get("rule") or {}).get("min_count") or 0
    n_null = 0
    row_null = {name: 0 for name in GROUPS}
    for cid, r in cities.items():
        if r is None:
            n_null += 1
            continue
        _check_row(cid, r, units, bad)
        for name in GROUPS:
            if r.get(name) is None:
                row_null[name] += 1
        if not isinstance(r.get("reliable"), bool):
            bad(f"{cid}: reliable must be a boolean")
        for s in r.get("specialists") or []:
            n = ((r.get(s.get("row")) or {}).get("counts") or {}).get(s.get("key"))
            if n is None or n < min_count:
                bad(f"{cid}: specialist {s.get('row')}.{s.get('key')} has fewer than {min_count} people")
    if any(lv == "FAIL" for lv, _ in out[:50]):
        return out[:50]
    out.append(("PASS", f"citizens.json: {len(cities)} cities, {n_null} with no citizen rows at all"))
    out.append(("NOTE", "citizens.json: cities without a row: "
                + ", ".join(f"{k} {v}" for k, v in row_null.items())
                + "; " + " and ".join(NO_SOURCE) + " have no source (null everywhere)"))
    return out
