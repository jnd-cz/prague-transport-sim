#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which checks a change needs (AGENTS.md, Running and checking; #727): the tier table, once, in code. Reads what the
branch changed and prints each kind of change it holds, the files that make it so, and the commands to run; the
`regress` skill runs them.

    python -I tools/tiers.py                    # this branch against origin/main, uncommitted changes too
    python -I tools/tiers.py --base main        # against another base
    python -I tools/tiers.py --files a.js b.py  # these paths instead of a diff

A change of two kinds runs both. A file in no row is listed as such (tools/test_tiers.py holds every file of src/
to a row): its row is chosen by hand, then added here.
"""
import fnmatch
import json
import os
import re
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)

import ground_rules  # noqa: E402 (which places a ground change is tried on, #865)

SEEDED = "u3,redruns,stops,traffic,lint,giveway"  # (stops rides on the u3 drive, #708; giveway is static, #602)
STATIC = "lint,surfaces,canted,crossing,spacing,heights"
DRAWN = "lint,surfaces,crossing,canted"

# (kind, the paths that make a change that kind (fnmatch), what it runs, what it leaves out). Order: as AGENTS.md's
# table. A path may be of several kinds; "tool" takes the tools of no other kind.
KINDS = [
    ("docs", ("*.md", "docs/*", ".claude/*", ".github/*", "LICENSE", "ruff.toml", "CLAUDE.md"),
     "nothing; the PR says so", "all"),
    ("review", ("src/review.js", "src/reviewFindings.js", "src/reviewIndex.js", "src/verdicts.js",
                "src/trackHeightProfile.js", "reviews.html", "reports/review/*", "tools/test_review.py",
                "src/overview.js", "overview.html", "tools/test_overview_page.py"),  # (the overview counts like reviews.html, #826)
     "tools/test_review.py and tools/test_overview_page.py (phone and desktop sizes)", "headless"),
    ("ground rule", ground_rules.TOOLS,  # (what a place's build runs, #865)
     "the tool's test; tools/ground_place.py --locality (the fixed set with one ring and two) and --rule on the "
     "changed rules' places (tools/ground_rules.py), before → after (a new case becomes a place in data/truth.json "
     "groundPlaces and of its rule); no line rebuilt",
     "--all --rings, the lines' rebuild and their checks: once for the batch (#757)"),
    ("world", ("data/MANIFEST.json", "data/truth.json", "snapshots/*"),  # (and the tools a rebuild runs: world())
     f"the tool's test; the lines rebuilt; --checks {STATIC} on them; tools/datadiff.py or tools/track_moves.py per "
     "line; a smoke drive per line (--checks u3 --seeds 1)", "redruns, traffic, seeds 2-5"),
    ("track heights", ("tools/line_heights.py", "tools/track_profile.py", "tools/track_curve.py"),
     "also heights", ""),
    ("drawn geometry", ("src/terrain.js", "src/world.js", "src/worldMesh.js", "src/groundDraw.js", "src/streets.js",
                        "src/heights.js", "src/platforms.js", "src/pedestrianCrossings.js", "src/structures.js",
                        "src/gameView.js", "src/platformRules.js", "tools/lint.js"),
     f"--checks {DRAWN} on every line; every seedless move needs a reason", "seeded checks"),
    ("drawing", ("src/models.js", "src/buildings.js", "src/trees.js", "src/lamps.js", "src/figures.js", "src/rigged.js",
                 "src/vehicles.js", "src/t3simple.js", "src/t3photo.js", "src/cabframe.js", "src/mirror.js", "src/weather.js",
                 "src/landmarks.js", "src/ledPanels.js", "src/indicators.js", "src/boxes.js", "src/nearbatch.js",
                 "src/benches.js", "src/shelters.js",
                 "src/catenary.js", "src/speedSigns.js", "src/packages.js", "src/packageRules.json", "src/audio.js",
                 "src/perf.js", "src/gfx.js", "src/between.js", "src/groundFile.js", "src/groundWorker.js", "src/loading.js", "src/hud.js",
                 "src/panel.js", "src/panel.css", "src/help.js", "src/i18n.js", "src/touch.js", "src/gamepad.js",
                 "src/localFiles.js", "src/packagesMenu.js", "src/report.js", "src/debugOverlay.js", "src/inspect.js",
                 "src/provenance.js", "src/buildId.js", "src/main.js", "index.html", "app.webmanifest", "assets/*",
                 "src/trafficView.js", "src/cars.js", "src/carTypes.js", "src/passengerView.js", "tools/frametime.py", "tools/shot.py"),
     "screenshots main vs branch (tools/shot.py), tools/frametime.py; for a load cut, the world after load compared "
     "with main's", "seeded checks"),
    ("loading", ("src/groundFile.js", "src/groundWorker.js", "src/world.js", "src/loading.js", "src/localFiles.js"),
     "a smoke drive per line as a player loads it beside the checks' world (--checks u3 --seeds 1 --player): the same "
     "counts, or each move with its heights from the 10 m grid (#710)", ""),
    ("simulation", ("src/traffic.js", "src/waits.js", "src/autopilot.js", "src/tram.js", "src/tr37.js", "src/electric.js",
                    "src/game.js", "src/people.js", "src/streetbot.js", "src/route.js", "src/speedRules.js",
                    "src/consist.js", "src/articulated.js", "src/random.js", "src/geo.js", "src/main.js", "src/run.js",
                    "tools/traffic_lint.js", "tools/autopilot.js", "tools/bench/*", "src/trafficView.js", "src/platformRules.js",
                    "src/carTypes.js", "src/passengers", "src/passengers/*", "src/passengerView.js"),
     f"--checks {SEEDED} on every line, seeds 1-5, --compare; the tram or the autopilot: also test_traction, "
     "test_electric, test_drives", "the geometry checks"),
    ("tool", ("tools/*",), "the changed tools' tests (tools/test_<tool>.py); the whole suite before the PR is ready", ""),
]
TRAM = ("src/tram.js", "src/tr37.js", "src/electric.js", "src/autopilot.js", "src/consist.js", "tools/autopilot.js")


def lines(root=ROOT):
    """The built lines, from the manifest's files (line9.json …)."""
    try:
        files = json.load(open(os.path.join(root, "data", "MANIFEST.json"), encoding="utf-8"))["files"]
    except (OSError, ValueError, KeyError):
        return ["9", "17", "22", "23", "37"]
    return sorted({m[1] for f in files if (m := re.fullmatch(r"line(\d+)\.json", f))}, key=int)


def world_tools(root=ROOT):
    """The tools a rebuild runs, and what they import, but the queue's and the cache's (board.build_tools)."""
    import board
    return board.build_tools(os.path.join(root, "tools"))


def kinds(paths, build=None):
    """{kind: [paths]} for the changed paths, plus "unplaced" for those of no row (a src/ file, a top-level file)."""
    build = world_tools() if build is None else build
    out = {}
    for p in sorted(set(paths)):
        got = [k for k, pats, *_ in KINDS[:-1] if any(fnmatch.fnmatch(p, pat) for pat in pats)]
        if p in build and "ground rule" not in got:
            got.append("world")
        if not got and p.startswith("tools/") and not p.startswith("tools/bench/"):
            got = ["tool"]
        for k in got or ["unplaced"]:
            out.setdefault(k, []).append(p)
    if "docs" in out and len(out) > 1:
        del out["docs"]  # (docs beside code: the code's checks)
    return {k: out[k] for k in [k for k, *_ in KINDS] + ["unplaced"] if k in out}


def rebuilt_lines(base, root=ROOT):
    """The lines whose files the branch's manifest changed against base's ([]: none rebuilt)."""
    def files(text):
        try:
            return json.loads(text)["files"]
        except (ValueError, KeyError, TypeError):
            return {}
    was = files(git("show", f"{base}:data/MANIFEST.json", root=root))
    try:
        now = files(open(os.path.join(root, "data", "MANIFEST.json"), encoding="utf-8").read())
    except OSError:
        now = {}
    moved = {f for f in set(was) | set(now) if was.get(f) != now.get(f)}
    return sorted({m[1] for f in moved if (m := re.match(r"line(\d+)\.", f))}, key=int)


def tests_of(paths, root=ROOT):
    """tools/test_<tool>.py of each changed tool that has one (a changed test is itself)."""
    out = []
    for p in paths:
        n = os.path.basename(p)
        if not p.startswith("tools/") or "/" in p[6:] or not n.endswith(".py"):
            continue
        t = n if n.startswith("test_") else f"test_{n}"
        if os.path.exists(os.path.join(root, "tools", t)) and t not in out:
            out.append(t)
    return out


def commands(found, base="origin/main", root=ROOT, ground=None):
    """The commands for the kinds found, in the order to run them. ground: what the ground tools changed
    ([module.name]; None: read from the diff against base)."""
    every, out = ",".join(lines(root)), []
    tests = tests_of([p for ps in found.values() for p in ps], root)
    out += [f"python -I tools/test_all.py -k {t[:-3]}" for t in tests]  # (-k: one name a run)
    if "review" in found:
        out.append("python -P -E tools/test_review.py")
    if "ground rule" in found:
        out += ground_commands(found["ground rule"], base, root, ground)
    if "world" in found:
        ls = ",".join(rebuilt_lines(base, root)) or every
        if not rebuilt_lines(base, root):
            out.append(f"python -P -E tools/rebuild.py {ls.replace(',', ' ')} --parallel  # (no line rebuilt yet)")
        out.append(f"python -P -E tools/headless.py --lines {ls} --checks {STATIC} --compare")
        out.append(f"python -P -E tools/headless.py --lines {ls} --checks u3 --seeds 1")
        out.append("python -I tools/datadiff.py <line>  # per line, or tools/track_moves.py")
    elif "track heights" in found:
        out.append(f"python -P -E tools/headless.py --lines {every} --checks heights --compare")
    if "drawn geometry" in found:
        out.append(f"python -P -E tools/headless.py --lines {every} --checks {DRAWN} --compare")
    if "loading" in found:
        out.append(f"python -P -E tools/headless.py --lines {every} --checks u3 --seeds 1 --player --gpu")
    if "simulation" in found:
        out.append(f"python -P -E tools/headless.py --lines {every} --checks {SEEDED} --seeds 1-5 --compare")
        if any(p in TRAM for p in found["simulation"]):
            out += [f"python -I tools/test_all.py -k {t}" for t in ("test_traction", "test_electric", "test_drives")]
    if "drawing" in found:
        out.append("python -P -E tools/shot.py ...  # main vs branch; python -P -E tools/frametime.py")
    if "tool" in found or "world" in found or "ground rule" in found:
        out.append("python -I tools/test_all.py  # the whole suite, before the PR is ready")
    return out


def ground_commands(paths, base, root=ROOT, names=None):
    """A ground change's places (#865): the locality set, the changed rules' places, and what changed in no rule."""
    names = ground_rules.diff(paths, base, root) if names is None else names
    out = ["python -P -E tools/ground_place.py --locality  # the fixed set, one ring and two: 0 differing (#865)"]
    rules, none = ground_rules.rules_of(names or [])
    if rules:
        out.append(f"python -P -E tools/ground_place.py --rule {','.join(rules)}  # "
                   f"{len(ground_rules.places_of(rules))} places, before → after")
    if none or names is None:
        what = ", ".join(none[:8]) + (f" and {len(none) - 8} more" if len(none) > 8 else "") if none else "the diff unread"
        out.append(f"# in no rule ({what}): their places by hand (ground_place.py --list), or the code into a rule "
                   "of tools/ground_rules.py")
    return out


def git(*args, root=ROOT):
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8")
    return r.stdout if r.returncode == 0 else ""


def changed(base, root=ROOT):
    """The branch's files against base (merge base), with the uncommitted and untracked ones."""
    out = set(git("diff", "--name-only", f"{base}...HEAD", root=root).split())
    out |= set(git("diff", "--name-only", "HEAD", root=root).split())
    out |= set(git("ls-files", "--others", "--exclude-standard", root=root).split())
    return sorted(out)


def report(paths, base="origin/main", root=ROOT, build=None):
    found = kinds(paths, build)
    if not found:
        return "No change against " + base + "."
    rows = {k: (runs, leaves) for k, _, runs, leaves in KINDS}
    out = []
    for k, ps in found.items():
        shown = ", ".join(ps[:6]) + (f" and {len(ps) - 6} more" if len(ps) > 6 else "")
        if k == "unplaced":
            out.append(f"- **in no row**: {shown}: choose its row by hand (AGENTS.md), then add it to tools/tiers.py")
            continue
        runs, leaves = rows[k]
        out.append(f"- **{k}** ({shown}): runs {runs}" + (f"; leaves out {leaves}" if leaves else ""))
    cmds = commands(found, base, root)
    return "\n".join(out + ([""] + cmds if cmds else []))


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # (a Windows console's code page has no arrow)
    base, files = "origin/main", None
    while argv:
        if argv[0] == "--base" and len(argv) > 1:
            base, argv = argv[1], argv[2:]
        elif argv[0] == "--files":
            files, argv = argv[1:], []
        else:
            print(__doc__, file=sys.stderr)
            return 2
    print(report([f.replace(os.sep, "/") for f in files] if files is not None else changed(base), base))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
