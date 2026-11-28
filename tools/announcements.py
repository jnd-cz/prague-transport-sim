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
PHRASES = {**CLAUSES, "request": "Zastávka na znamení.", "next": "Příští zastávka...",
           "next-request": "Příští zastávka je na znamení.",
           "terminus": "Konečná zastávka, prosíme vystupte."}


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


def timetable_pattern(archive, names, timetable):
    """Require every playable trip to agree on platform IDs, transfers and request stops."""
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
                                    re.findall(r"[A-Z][a-z]", row["stop_icons"]) if icon in ICONS),
                                    "3" in (row["pickup_type"], row["drop_off_type"])) for row in trip))
    if matched != expected_times or len(patterns) != 1:
        raise ValueError(f"Line {LINE}: {len(matched)}/{len(expected_times)} trips match, {len(patterns)} announcement patterns")
    return patterns.pop()


def announcement_plan(names, pattern, stop_facts, pronunciations):
    clips = dict(PHRASES)
    spoken = {}
    name_ids = {}
    for name, (stop_id, _, _) in zip(names, pattern, strict=True):
        key = name_ids.setdefault(name, f"stop-{stop_id}")
        clips[key] = name + "."
        if name in pronunciations:
            spoken[key] = pronunciations[name]["spoken"] + "."

    entries = []
    for index, (name, (stop_id, modes, request)) in enumerate(zip(names, pattern, strict=True)):
        next_name = names[index + 1] if index + 1 < len(names) else None
        kinds = set(modes)
        # Use the same directional stop facts as tools/lint.js stopFacts.
        if any(fact["name"] == name and fact["type"] == "street" and
               (fact.get("towards") == "*" or fact.get("from") in names[:index] or
                fact.get("towards") in names[index + 1:])
               for fact in stop_facts):
            kinds.add("road")
        segments = [name_ids[name]]
        if request:
            segments.append("request")
        segments.extend(kind for kind in CLAUSES if kind in kinds)
        if next_name:
            segments.extend(("next", name_ids[next_name]))
            if pattern[index + 1][2]:
                segments.append("next-request")
        else:
            segments.append("terminus")
        entries.append({"id": stop_id, "name": name, "request": request, "segments": segments})
    used = {key for stop in entries for key in stop["segments"]}
    segments = {key: {"text": text, "clips": {v: f"{v.lower()}/{key}.mp3" for v in VOICES}}
                for key, text in clips.items() if key in used}
    for key, text in spoken.items():
        segments[key]["spoken"] = text
    return entries, segments


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
    pattern = timetable_pattern(archive, names, data["timetable"])
    if [r for _, _, r in pattern] != [bool(s.get("request")) for s in data["stops"]]:
        raise ValueError("PID request flags differ from the built route")
    entries, segments = announcement_plan(names, pattern, truth["stops"], truth["announcementPronunciations"])
    manifest = {
        "line": LINE, "voices": list(VOICES), "speakingRate": RATE,
        "source": {"snapshot": snapshot, "gtfsSha256": source_hash,
                   "timetable": "https://pid.cz/en/opendata/",
                   "roadway": "data/truth.json stops (maintainer, 2026-10-23 and 2026-11-28)",
                   "pronunciations": "data/truth.json announcementPronunciations (maintainer, 2026-11-28)"},
        "synthesis": "Google Cloud Czech Chirp 3 HD",
        "outputTerms": "https://cloud.google.com/text-to-speech/docs/basics",
        "stops": entries,
        "segments": segments,
    }
    target = OUTPUT / "manifest.json"
    old = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    cached = {path: s.get("spoken", s["text"]) for s in old.get("segments", {}).values() for path in s["clips"].values()}
    pending = [(voice, s.get("spoken", s["text"]), OUTPUT / path)
               for s in segments.values() for voice, path in s["clips"].items()
               if not (OUTPUT / path).is_file() or cached.get(path) != s.get("spoken", s["text"])
               or old.get("speakingRate") != RATE]
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
    print(f"Line {LINE}: {len(entries)} announcements, {len(segments)} segments × {len(VOICES)} voices; "
          f"synthesized {len(pending)} clips.")


if __name__ == "__main__":
    main()
