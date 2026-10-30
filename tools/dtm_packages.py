"""One ZPS month per district: CURRENT's snapshot, otherwise the newest local month (#113)."""
from dataclasses import dataclass
import glob
import json
import logging
from pathlib import Path
import re

DTM = {  # lines whose builds include surveyed streets
    "17": ["500054", "500089", "500119", "500186", "500208", "547107", "547174"],
    "22": ["500089", "500224"],
}
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
