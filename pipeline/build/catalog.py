"""sources.json – the Almanac's bibliography, generated from the registry + manifests.

Each source cites only the raw files its latest process() used (interim "files"),
or every manifest entry if it did not say.
"""

from ..core.fetch import read_manifest
from ..core.store import load_interim_payload, write_web
from ..sources import SOURCES
from .catalog_zh import LICENSES, ZH

REQUIRES: list[str] = []
PRODUCES = ["sources.json"]
RUN_LAST = True
CORE = ["ris_population", "dgbas_labor", "ics_census", "mof_county_income", "tw_boundaries", "srtm15", "worldcover",
        "natural_earth"]


def build() -> None:
    out = []
    for s in SOURCES:
        try:
            payload = load_interim_payload(s.id)
        except FileNotFoundError:
            payload = {}
        manifest = read_manifest(s.id)
        used = payload.get("files")  # raw files the latest process() said it used, else cite them all
        names = sorted(manifest) if used is None else [f for f in sorted(used) if f in manifest]
        if used is not None and len(names) < len(used):
            print(f"    ! {s.id}: {len(used) - len(names)} used file(s) missing from manifest")
        files = [
            {"file": name, "url": m["url"], "retrieved": m["retrieved"], "sha256": m["sha256"], "bytes": m["bytes"]}
            for name in names
            for m in [manifest[name]]
        ]
        vintage = payload.get("vintage")
        info = s.info.to_dict()
        zh = ZH.get(s.id)
        if zh is None:
            print(f"    ! {s.id}: no 繁中 entry in catalog_zh.py, shown in English")
        else:
            info.update({k: zh[k] for k in ("title", "publisher", "description", "used_for") if k in zh})
            vintage = zh.get("vintage", {}).get(vintage, vintage)  # a refreshed (changed) vintage stays English
        info["license"] = LICENSES.get(info["license"], info["license"])
        out.append({**info, "vintage": vintage, "files": files})
    # The core sources lead (the Almanac lists them in this order and the share image credits the first publishers);
    # the rest keep registry order.
    rank = {sid: i for i, sid in enumerate(CORE)}
    out.sort(key=lambda s: rank.get(s["id"], len(CORE)))
    write_web("sources.json", out)
