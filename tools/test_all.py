# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run the tools' tests: every tools/test_*.py, each in its own process, the way it must run.

    python -I tools/test_all.py                  # the tests without a browser (CI runs these)
    python -I tools/test_all.py --browser        # also the ones that drive the game in Playwright
    python -I tools/test_all.py -k track --list  # only names containing "track"; show the plan

Each test runs with `-I` when everything it imports is in the standard library or in tools/, else with
`-P -E` (numpy, shapely, pyproj, pyosmium, Pillow live in the user site packages; AGENTS.md). A test
that starts a browser itself is a browser test. A test whose data is not in this checkout (NEEDS below) is
skipped and says what it needs. Exit code 1 when a test fails.
"""
import argparse
import ast
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")

# tests that read data this checkout may not have (a fresh clone has only data/MANIFEST.json and
# data/truth.json; snapshot.py data-fetch brings data/, fetch brings raw/)
NEEDS = {
    "test_audio_pause.py": "data/line23.json",
    "test_deploy.py": "data/line17.json",  # (deploy refuses unless data/ matches the manifest)
    "test_free_camera.py": "data/line37.json",
    "test_geo_js.py": "raw/proj/cz_cuzk_table_-y-x_3_v1710.tif",
    "test_height_styles.py": "data/line37.json",
    "test_idle.py": "data/line23.json",
    "test_mirror_game.py": "data/line17.json",
    "test_report.py": "data/line17.json",
    "test_review.py": "data/line17.json",
    "test_touch.py": "data/line17.json",
}


def imports(path):
    """Top-level module names a file imports."""
    tree = ast.parse(open(path, encoding="utf-8").read(), path)
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            out.add(n.module.split(".")[0])
    return out


def third_party(test):
    """The non-stdlib modules a test needs, through the tools modules it imports."""
    seen, todo, ext = set(), [test[:-3]], set()
    while todo:
        m = todo.pop()
        if m in seen:
            continue
        seen.add(m)
        for name in imports(os.path.join(TOOLS, m + ".py")):
            if os.path.exists(os.path.join(TOOLS, name + ".py")):
                todo.append(name)
            elif name not in sys.stdlib_module_names:
                ext.add(name)
    return ext


def plan(pattern):
    tests = sorted(f for f in os.listdir(TOOLS) if re.fullmatch(r"test_\w+\.py", f) and f != "test_all.py")
    rows = []
    for t in tests:
        if pattern and pattern not in t:
            continue
        ext = third_party(t)
        launches = re.search(r"sync_playwright|chromium\.launch", open(os.path.join(TOOLS, t), encoding="utf-8").read())
        kind = "browser" if launches else "-P -E" if ext else "-I"
        rows.append((t, kind, sorted(ext)))
    return rows


def kill_tree(p):
    """Stops a test and everything it started."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    else:
        import signal
        os.killpg(p.pid, signal.SIGKILL)


def summary(out):
    """unittest's last lines: 'Ran 12 tests', 'OK (skipped=2)' or 'FAILED (failures=1)'."""
    ran = re.findall(r"^Ran (\d+) tests?", out, re.M)
    end = re.findall(r"^(OK.*|FAILED.*)$", out, re.M)
    return f"{ran[-1]} tests, {end[-1]}" if ran and end else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--browser", action="store_true", help="also run the Playwright tests")
    ap.add_argument("-k", dest="pattern", help="only tests whose file name contains this")
    ap.add_argument("--list", action="store_true", help="show what would run, how, and stop")
    ap.add_argument("--timeout", type=int, default=900, help="seconds per test (default 900)")
    a = ap.parse_args()
    rows = plan(a.pattern)
    if a.list:
        for t, kind, ext in rows:
            need = NEEDS.get(t)
            print(f"{t:40} {kind:8} {', '.join(ext) or '-'}{f'  (needs {need})' if need else ''}")
        return 0
    failed, skipped, t0 = [], [], time.time()
    for t, kind, _ext in rows:
        if kind == "browser" and not a.browser:
            skipped.append((t, "browser test (--browser)"))
            continue
        need = NEEDS.get(t)
        if need and not os.path.exists(os.path.join(ROOT, need)):
            skipped.append((t, f"needs {need} (python -I tools/snapshot.py {'fetch' if need.startswith('raw/') else 'data-fetch'})"))
            continue
        flags = ["-I"] if kind == "-I" else ["-P", "-E"]
        t1 = time.time()
        # (its own process group: on a timeout the servers and browsers it started go with it)
        p = subprocess.Popen([sys.executable, *flags, os.path.join(TOOLS, t)], cwd=ROOT, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                             # (a test that runs a heavy tool's main does not queue behind the real jobs, #280)
                             env={**os.environ, "PYTHONIOENCODING": "utf-8", "TRAM_HEAVY_NOWAIT": "1"},
                             start_new_session=os.name != "nt",
                             creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
        try:
            out, _ = p.communicate(timeout=a.timeout)
            code = p.returncode
        except subprocess.TimeoutExpired:
            kill_tree(p)
            out, _ = p.communicate()
            code, out = "timeout", (out or "") + f"\n(timed out after {a.timeout} s)"
        ok = code == 0
        print(f"{'ok  ' if ok else 'FAIL'} {t:40} {kind:8} {time.time() - t1:6.1f} s  {summary(out)}", flush=True)
        if not ok:
            failed.append(t)
            print("\n".join("     " + ln for ln in out.strip().splitlines()[-25:]), flush=True)
    for t, why in skipped:
        print(f"skip {t:40} {why}")
    print(f"{len(rows) - len(skipped) - len(failed)} passed, {len(failed)} failed, {len(skipped)} skipped"
          f" in {time.time() - t0:.0f} s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
