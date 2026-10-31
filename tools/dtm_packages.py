"""One ZPS month per district: CURRENT's snapshot, otherwise the newest local month (#113).

    python -P -E tools/dtm_packages.py --check     # DTM below against the rule (OSM district boundaries)
    python -I tools/dtm_packages.py --fetch        # missing OPL/KR pairs from the monthly index into raw/dtm/
    python -I tools/dtm_packages.py --fetch --index FILE   # the same from a saved copy of the index
"""
from dataclasses import dataclass
import glob
import json
import logging
from pathlib import Path
import re
import sys
import urllib.request
import zipfile

CORRIDOR = 80.0  # m: the survey a line's build takes, around path and pathBack (tools/dtm.py)
# Districts by rule: every district the line's corridor touches (--check recomputes it). The hand-made
# lists before missed most of line 22 (Praha 1 and 6) and line 17's Troja and Libuš, with Trojský most (#125).
DTM = {
    "9": ["500054", "500089", "500097", "500143", "500208", "500224", "539694", "539899", "547174"],
    "17": ["500054", "500089", "500119", "500186", "500208", "547051", "547107", "547328"],
    "22": ["500054", "500089", "500143", "500178", "500186", "500224", "547174"],
    "23": ["500054", "500089", "500143", "500178", "500186", "500208"],
    "37": ["500097", "500208", "500216", "547361"],
}
INDEX = "https://geoportalpraha.cz/api/get-dtm-download-metadata?code={}"  # sets 02 OPL, 03 KR (DATA.md)
BASE = "https://isdtmk.dtm-praha-sck.cz/api/istem/vydej/download/path/"
NAME = re.compile(r"VS_CZ010_MOMC_(\d{6})_(\d{8})_ZPS_(OPL|KR)\.gpkg(?:\.zip)?$")
LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class Package:
    district: str
    date: str
    opl: Path
    kr: Path

    def path(self, kind):
        return {"OPL": self.opl, "KR": self.kr}[kind]


def snapshot_months(root):
    """A broken existing manifest must not silently become a newest-month fallback."""
    folder = Path(root) / "snapshots"
    current = folder / "CURRENT"
    if not current.exists():
        return {}
    sid = current.read_text(encoding="utf-8").strip()
    snap = json.loads((folder / f"{sid}.json").read_text(encoding="utf-8"))
    months = {}
    for group in snap["groups"]:
        if group["name"] != "dtm":
            continue
        for f in group["files"]:
            match = NAME.fullmatch(Path(f["path"]).name)
            if not match:
                continue
            district, date, _ = match.groups()
            if district in months and months[district] != date:
                raise ValueError(f"DTM district {district}: snapshot {sid} lists several months")
            months[district] = date
    return months


def select_packages(root, districts=None, sources=None):
    """Select OPL/KR pairs; explicit sources choose districts and prefer available snapshot dates.

    Inspect source siblings so a stale shell glob cannot override an available CURRENT pair. During
    a refresh, an unavailable pinned pair may be replaced by the newest local month after it, with a warning.
    Incomplete pairs fail, never mix months. Supports extracted folders and named .gpkg files.
    """
    root = Path(root)
    folders = {root / "raw" / "dtm"}
    if sources is not None:
        requested, folders = set(), set()
        for source in sources:
            pattern = Path(source)
            if not pattern.is_absolute():
                pattern = root / pattern
            paths = glob.glob(str(pattern))
            if not paths:
                raise FileNotFoundError(f"DTM source not found: {source}")
            for name in paths:
                path = Path(name)
                if path.name in ("ZPS_OPL.gpkg", "ZPS_KR.gpkg"):
                    path = path.parent
                match = NAME.fullmatch(path.name)
                if not match or path.suffix != ".gpkg":
                    raise ValueError(f"expected an extracted dated ZPS package: {name}")
                requested.add(match[1])
                folders.add(path.parent)
        if districts is not None:
            requested &= set(districts)
    else:
        requested = None if districts is None else set(districts)

    local = {}
    for folder in sorted(folders):
        for entry in sorted(folder.iterdir()):
            match = NAME.fullmatch(entry.name)
            if not match or entry.suffix != ".gpkg":
                continue
            district, date, kind = match.groups()
            if requested is not None and district not in requested:
                continue
            path = entry / f"ZPS_{kind}.gpkg" if entry.is_dir() else entry
            if not path.is_file():
                continue
            key = (district, date, kind)
            if key in local and local[key] != path:
                raise ValueError(f"ambiguous DTM package: {key}: {local[key]}, {path}")
            local[key] = path

    pinned = snapshot_months(root)
    requested = requested if requested is not None else {d for d, _, _ in local} | set(pinned)
    selected = []
    for district in sorted(requested):
        dates = sorted({date for d, date, _ in local if d == district})
        date = pinned.get(district)
        refresh_from = None
        if date is None:
            if not dates:
                raise FileNotFoundError(f"no extracted DTM packages for district {district}")
            date = dates[-1]
            if len(dates) > 1:
                LOG.warning("DTM district %s: no snapshot month; choosing newest %s from %s",
                            district, date, ", ".join(dates))
        elif not all((district, date, kind) in local for kind in ("OPL", "KR")) and dates and dates[-1] > date:
            # Refreshes rebuild before publish changes CURRENT. Both kinds must come from the new
            # month; never silently use an older local month when the pinned source is missing.
            refresh_from, date = date, dates[-1]
        paths = []
        for kind in ("OPL", "KR"):
            path = local.get((district, date, kind))
            if path is None:
                raise FileNotFoundError(f"DTM district {district}, month {date}: missing ZPS_{kind}; fetch the snapshot")
            paths.append(path)
        if refresh_from is not None:
            sid = (root / "snapshots/CURRENT").read_text(encoding="utf-8").strip()
            LOG.warning("DTM district %s: raw/ is ahead of snapshot %s (%s -> %s); "
                        "using the newer pair; rebuild/check and publish it",
                        district, sid, refresh_from, date)
        selected.append(Package(district, date, *paths))
    return selected


def check():
    """The table against the rule; prints the right one when they differ."""
    from dtm_di import districts
    rule = {line: [] for line in DTM}
    for d in districts(tuple(int(k) for k in DTM), CORRIDOR):
        for line in d["lines"]:
            rule[str(line)].append(d["code"])
    rule = {k: sorted(v) for k, v in rule.items()}
    if rule != {k: sorted(v) for k, v in DTM.items()}:
        print("DTM differs from the rule; it should be:\n" + json.dumps(rule, indent=1))
        return 1
    print(f"DTM matches the rule: {sum(map(len, DTM.values()))} line districts, {len(set(sum(DTM.values(), [])))} packages")
    return 0


def fetch(root, index=None):
    """Missing OPL/KR pairs of DTM's districts, the index's newest month; each checked against the
    index's size and as a ZIP, written whole, with its URL and state in raw/dtm/provenance.json.
    index: a saved copy, {"02": [format entries], "03": [...]}, for when the API turns scripts away
    (2026-10-31: 502 to scripts for hours while a browser read it)."""
    from atomic import replacing
    root, have = Path(root), {}
    folder = root / "raw" / "dtm"
    for f in folder.glob("*.gpkg.zip"):
        m = NAME.fullmatch(f.name)
        have.setdefault(m[1], set()).add(m[3])
    prov_path = folder / "provenance.json"
    prov = json.loads(prov_path.read_text(encoding="utf-8")) if prov_path.exists() else {"packages": {}}
    need = sorted({d for ds in DTM.values() for d in ds if have.get(d) != {"OPL", "KR"}})
    for code, kind in (("02", "OPL"), ("03", "KR")):
        if index:
            formats = json.loads(Path(index).read_text(encoding="utf-8"))[code]
        else:
            with urllib.request.urlopen(INDEX.format(code), timeout=120) as r:
                formats = [f for row in json.load(r) for f in row["formats"]]
        for district in need:
            if kind in have.get(district, ()):
                continue
            entries = [f for f in formats if f["obec_kod"] == district and f["format"] == "GPKG"]
            if not entries:
                raise ValueError(f"district {district}: no GPKG in index set {code}")
            e = max(entries, key=lambda e: e["platnost"])
            name = e["soubor_nazev"]
            if not (m := NAME.fullmatch(name)) or m[1] != district or m[3] != kind or not name.endswith(".zip"):
                raise ValueError(f"district {district}: unexpected package name {name}")
            url = BASE + e["kod_stazeni"]
            with urllib.request.urlopen(url, timeout=600) as r:
                content = r.read()
            if len(content) != int(e["velikost"]):
                raise ValueError(f"{name}: {len(content)} bytes, the index says {e['velikost']}")
            with replacing(folder / name, "wb") as f:
                f.write(content)
            with zipfile.ZipFile(folder / name) as z:
                if z.testzip():
                    raise ValueError(f"{name}: corrupt ZIP")
            prov["packages"][name] = {"url": url, "index": INDEX.format(code) + (" (saved copy)" if index else ""), "state": e["platnost"],
                                      "size": len(content)}
            print(f"{name}: {len(content):,} bytes", flush=True)
    with replacing(prov_path, "w", encoding="utf-8") as f:
        json.dump(prov, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if "--check" in sys.argv:
        sys.exit(check())
    if "--fetch" in sys.argv:
        fetch(Path(__file__).resolve().parent.parent, sys.argv[sys.argv.index("--index") + 1] if "--index" in sys.argv else None)
    else:
        print(__doc__)
