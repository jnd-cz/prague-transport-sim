# SPDX-License-Identifier: AGPL-3.0-or-later
"""Render the line 17 pilot (#894) from the built run and its pinned PID timetable."""
import argparse
import base64
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets/announcements/17"
LINE = "17"
VOICES = ("Aoede", "Algieba", "Sulafat")
RATE = 0.85
ICONS = {"Ma": "metro", "Mb": "metro", "Mc": "metro", "Md": "metro", "Ra": "train", "Sb": "train"}
CLAUSES = {"metro": "Přestup na metro.", "train": "Přestup na vlak.", "road": "Výstup do vozovky."}


def pinned_gtfs():
    snapshots = ROOT / "snapshots"
    snapshot = (snapshots / "CURRENT").read_text(encoding="utf-8").strip()
    manifest = json.loads((snapshots / f"{snapshot}.json").read_text(encoding="utf-8"))
    entry = next(f for g in manifest["groups"] if g["name"] == "gtfs" for f in g["files"])
    local = ROOT / entry["path"]
    if not local.is_file() and (cache := os.environ.get("TRAMDATA_CACHE")):
        local = Path(cache) / "sources" / entry["sha256"]
    with local.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != entry["sha256"]:
            raise ValueError("PID GTFS does not match snapshots/CURRENT")
    return local, snapshot, entry["sha256"]


def seconds(timestamp):
    h, m, s = map(int, timestamp.split(":"))
    return (h * 60 + m) * 60 + s


def transfers(archive, names, timetable):
    """Require every playable trip to agree on platform IDs and relevant transfer icons."""
    expected_times = {tuple(trip) for trip in timetable}
    matched = set()
    patterns = set()
    with zipfile.ZipFile(archive) as z:
        def rows(filename):
            with io.TextIOWrapper(z.open(filename + ".txt"), encoding="utf-8-sig", newline="") as source:
                yield from csv.DictReader(source)

        stop_names = {r["stop_id"]: r["stop_name"] for r in rows("stops")}
        trip_ids = {r["trip_id"] for r in rows("trips") if r["route_id"] == f"L{LINE}" and r["direction_id"] == "0"}
        trips = defaultdict(list)
        for row in rows("stop_times"):
            if row["trip_id"] in trip_ids:
                trips[row["trip_id"]].append(row)
        for trip in trips.values():
            trip.sort(key=lambda row: int(row["stop_sequence"]))
            if [stop_names[row["stop_id"]] for row in trip] != names:
                continue
            times = tuple(seconds(row["departure_time"]) for row in trip)
            if times in expected_times:
                matched.add(times)
                patterns.add(tuple((row["stop_id"], frozenset(ICONS[icon] for icon in
                                    re.findall(r"[A-Z][a-z]", row["stop_icons"]) if icon in ICONS)) for row in trip))
    if matched != expected_times or len(patterns) != 1:
        raise ValueError(f"Line {LINE}: {len(matched)}/{len(expected_times)} trips match, {len(patterns)} announcement patterns")
    return patterns.pop()


def stop_entries(names, pattern, stop_facts):
    for index, (name, (stop_id, modes)) in enumerate(zip(names, pattern, strict=True)):
        previous = names[index - 1] if index else None
        next_name = names[index + 1] if index + 1 < len(names) else None
        kinds = set(modes)
        # A reported stop type is directional. Apply only the known road-level platform.
        if any(fact["name"] == name and fact["type"] == "street" and
               (fact.get("from") == previous if fact.get("from") else fact.get("towards") in ("*", next_name))
               for fact in stop_facts):
            kinds.add("road")
        clauses = [text for kind, text in CLAUSES.items() if kind in kinds]
        end = f"Příští zastávka... {next_name}." if next_name else "Konečná zastávka, prosíme vystupte."
        clips = {voice: f"{voice.lower()}/{stop_id}.mp3" for voice in VOICES}
        yield {"id": stop_id, "name": name, "next": next_name, "clauses": clauses,
               "text": " ".join([name + ".", *clauses, end]), "clips": clips}


def synthesize(project, token, voice, text):
    body = {
        "input": {"text": text},
        "voice": {"name": f"cs-CZ-Chirp3-HD-{voice}", "languageCode": "cs-CZ"},
        "audioConfig": {"audioEncoding": "MP3", "speakingRate": RATE},
    }
    request = urllib.request.Request("https://texttospeech.googleapis.com/v1/text:synthesize",
                                     data=json.dumps(body).encode("utf-8"), headers={
                                         "Authorization": "Bearer " + token, "x-goog-user-project": project,
                                         "Content-Type": "application/json",
                                     })
    with urllib.request.urlopen(request, timeout=45) as response:
        return base64.b64decode(json.load(response)["audioContent"], validate=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Google Cloud quota project with Text-to-Speech enabled")
    parser.add_argument("--gcloud", default="gcloud", help="path to the authenticated Google Cloud CLI")
    args = parser.parse_args()
    archive, snapshot, source_hash = pinned_gtfs()
    data = json.loads((ROOT / f"data/line{LINE}.json").read_text(encoding="utf-8"))
    truth = json.loads((ROOT / "data/truth.json").read_text(encoding="utf-8"))
    names = [s["name"] for s in data["stops"]]
    entries = list(stop_entries(names, transfers(archive, names, data["timetable"]), truth["stops"]))
    manifest = {
        "line": LINE, "voices": list(VOICES), "speakingRate": RATE,
        "source": {"snapshot": snapshot, "gtfsSha256": source_hash,
                   "transferIcons": "https://pid.cz/en/opendata/",
                   "roadway": "data/truth.json stops (maintainer, 2026-10-23)"},
        "synthesis": "Google Cloud Czech Chirp 3 HD",
        "outputTerms": "https://cloud.google.com/text-to-speech/docs/basics",
        "stops": entries,
    }
    target = OUTPUT / "manifest.json"
    old = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    cached = {path: s["text"] for s in old.get("stops", []) for path in s["clips"].values()}
    pending = [(voice, s["text"], OUTPUT / path) for s in entries for voice, path in s["clips"].items()
               if not (OUTPUT / path).is_file() or cached.get(path) != s["text"] or old.get("speakingRate") != RATE]
    if pending:
        token = subprocess.run([args.gcloud, "auth", "application-default", "print-access-token"],
                               check=True, capture_output=True, text=True).stdout.strip()

        def render(job):
            voice, text, path = job
            audio = synthesize(args.project, token, voice, text)
            if len(audio) < 1000:
                raise ValueError(f"Short audio from Chirp for {path.name}")
            path.parent.mkdir(parents=True, exist_ok=True)
            with replacing(path, "wb") as stream:
                stream.write(audio)

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(render, pending))
    with replacing(target, encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"Line {LINE}: {len(entries)} stops × {len(VOICES)} voices; synthesized {len(pending)} clips.")


if __name__ == "__main__":
    main()
