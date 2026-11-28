# SPDX-License-Identifier: AGPL-3.0-or-later
"""Render announcements for all playable runs from the built routes and pinned PID timetable."""
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
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets/announcements"
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


def read_timetable(archive, lines):
    """Read the pinned stop occurrences once, including both halves of a through run."""
    with zipfile.ZipFile(archive) as z:
        def rows(filename):
            with io.TextIOWrapper(z.open(filename + ".txt"), encoding="utf-8-sig", newline="") as source:
                yield from csv.DictReader(source)

        stop_names = {r["stop_id"]: r["stop_name"] for r in rows("stops")}
        gtfs_routes = {f"L{line}" for line in lines}
        trip_ids = {r["trip_id"]: r for r in rows("trips") if r["route_id"] in gtfs_routes}
        trips = defaultdict(list)
        for row in rows("stop_times"):
            if row["trip_id"] in trip_ids:
                trips[row["trip_id"]].append(row)
    by_line = defaultdict(list)
    for tid, trip in trips.items():
        trip.sort(key=lambda row: int(row["stop_sequence"]))
        by_line[trip_ids[tid]["route_id"][1:]].append((trip_ids[tid], trip))
    return stop_names, by_line


def timetable_pattern(data, stop_names, by_line):
    """Use the common platform transfers across the exact matching timetable trips."""
    line = data["line"]
    names = [s["name"] for s in data["stops"]]
    expected_times = {tuple(trip) for trip in data["timetable"]}
    matched, patterns = set(), set()

    def matching_trips(number, sequence):
        return [(meta, trip) for meta, trip in by_line[number]
                if [stop_names[row["stop_id"]] for row in trip] == sequence]

    def consider(trip):
        times = tuple(seconds(row["departure_time"]) for row in trip)
        if times in expected_times:
            matched.add(times)
            patterns.add(tuple((row["stop_id"], frozenset(ICONS[icon] for icon in
                                re.findall(r"[A-Z][a-z]", row["stop_icons"]) if icon in ICONS),
                                "3" in (row["pickup_type"], row["drop_off_type"])) for row in trip))

    if data.get("segments"):
        first, onward = data["segments"]
        change = onward["from"]
        continuations = defaultdict(list)
        for meta, trip in matching_trips(onward["line"], names[change:]):
            if meta.get("block_id"):
                continuations[(meta["block_id"], trip[0]["stop_id"])].append(trip)
        for meta, trip in matching_trips(first["line"], names[:change + 1]):
            for after in continuations[(meta.get("block_id"), trip[-1]["stop_id"])]:
                consider(trip[:-1] + after)
    else:
        for meta, trip in matching_trips(line, names):
            if meta["direction_id"] == "0":
                consider(trip)
    if matched != expected_times or not patterns:
        raise ValueError(f"Line {line}: {len(matched)}/{len(expected_times)} trips match, {len(patterns)} announcement patterns")
    pattern = []
    varied = 0
    for stop, rows in zip(data["stops"], zip(*patterns, strict=True), strict=True):
        ids, modes, flags = zip(*rows, strict=True)
        request = bool(stop.get("request"))
        if len(set(ids)) != 1 or request not in flags:
            raise ValueError(f"Line {line}, {stop['name']}: PID platforms or request flags differ from the built run")
        common = frozenset.intersection(*modes)
        varied += len(set(modes)) > 1
        pattern.append((ids[0], common, request))
    if varied:
        print(f"Line {line}: {varied} calls have trip-specific transfer icons, kept only shared modes", flush=True)
    return pattern


def announcement_plan(names, pattern, stop_facts, pronunciations):
    clips = dict(PHRASES)
    spoken = {}
    name_ids = {}
    for name in names:
        key = name_ids.setdefault(name, "stop-" + hashlib.sha256(name.encode()).hexdigest()[:16])
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


def assemble(archive, routes, truth):
    numbers = {part["line"] for data in routes for part in data.get("segments", [data])}
    stop_names, timetable = read_timetable(archive, numbers)
    lines, segments = {}, {}
    for data in routes:
        names = [s["name"] for s in data["stops"]]
        pattern = timetable_pattern(data, stop_names, timetable)
        entries, clips = announcement_plan(names, pattern, truth["stops"], truth["announcementPronunciations"])
        lines[data["line"]] = entries
        segments.update(clips)
        print(f"Line {data['line']}: {len(entries)} calls, {len(data['timetable'])} matched trips", flush=True)
    return lines, dict(sorted(segments.items()))


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
    for attempt, delay in enumerate((5, 10, 20, 40, 0)):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return base64.b64decode(json.load(response)["audioContent"], validate=True)
        except urllib.error.HTTPError as error:
            if not delay or error.code not in {429, 500, 502, 503, 504}:
                raise
            if attempt == 0:
                print(f"Chirp returned HTTP {error.code}; retrying after a pause", flush=True)
            time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Google Cloud quota project with Text-to-Speech enabled")
    parser.add_argument("--gcloud", default="gcloud", help="path to the authenticated Google Cloud CLI")
    args = parser.parse_args()
    archive, snapshot, source_hash = pinned_gtfs()
    data_dir = ROOT / "data"
    index = json.loads((data_dir / "lines.json").read_text(encoding="utf-8"))
    routes = [json.loads((data_dir / f"line{item['line']}.json").read_text(encoding="utf-8")) for item in index]
    truth = json.loads((ROOT / "data/truth.json").read_text(encoding="utf-8"))
    lines, segments = assemble(archive, routes, truth)
    manifest = {
        "voices": list(VOICES), "speakingRate": RATE,
        "source": {"snapshot": snapshot, "gtfsSha256": source_hash,
                   "timetable": "https://pid.cz/en/opendata/",
                   "roadway": "data/truth.json stops (maintainer, 2026-10-23 and 2026-11-28)",
                   "pronunciations": "data/truth.json announcementPronunciations (maintainer, 2026-11-28)"},
        "synthesis": "Google Cloud Czech Chirp 3 HD",
        "outputTerms": "https://cloud.google.com/text-to-speech/docs/basics",
        "lines": lines,
        "segments": segments,
    }
    target = OUTPUT / "manifest.json"
    checkpoint = ROOT / "reports/announcement-synthesis.json"
    cached = {}
    for previous in (target, checkpoint):
        if not previous.exists():
            continue
        old = json.loads(previous.read_text(encoding="utf-8"))
        if old["speakingRate"] == RATE and old["synthesis"] == manifest["synthesis"]:
            for segment in old["segments"].values():
                for voice, path in segment["clips"].items():
                    if (OUTPUT / path).is_file():
                        cached[voice, segment.get("spoken", segment["text"])] = OUTPUT / path
    pending = []
    for segment in segments.values():
        text = segment.get("spoken", segment["text"])
        for voice, path in segment["clips"].items():
            dest = OUTPUT / path
            known = cached.get((voice, text))
            if known is None:
                pending.append((voice, text, dest))
            elif known != dest:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with replacing(dest, "wb") as stream, known.open("rb") as source:
                    shutil.copyfileobj(source, stream)
    if pending:
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        with replacing(checkpoint, encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False)
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
    digest = hashlib.sha256()
    for segment in segments.values():
        for path in segment["clips"].values():
            digest.update((OUTPUT / path).read_bytes())
    manifest["audioVersion"] = digest.hexdigest()[:16]
    with replacing(target, encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    checkpoint.unlink(missing_ok=True)
    print(f"{len(lines)} runs, {len(segments)} segments × {len(VOICES)} voices; "
          f"synthesized {len(pending)} clips.")


if __name__ == "__main__":
    main()
