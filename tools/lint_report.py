"""Compare lint reports (reports/lineN.json, written by tools/lint.js) with the committed baseline
(reports/baseline/lineN.json): one row per line and check, baseline -> now. A check whose count rose
is a regression (exit code 1). The traffic run's counts move by 10-20 % whenever trajectories change,
so for those a rise counts only beyond a noise band (15 % + 5).

Usage:  python tools/lint_report.py            compare
        python tools/lint_report.py --accept   make the current reports the new baseline
"""
import glob
import json
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUR, BASE = os.path.join(ROOT, "reports"), os.path.join(ROOT, "reports", "baseline")

if "--accept" in sys.argv:
    os.makedirs(BASE, exist_ok=True)
    for f in glob.glob(os.path.join(CUR, "line*.json")):
        shutil.copy(f, BASE)
        print("baseline <-", os.path.basename(f))
    sys.exit(0)

worse = 0
NOISY = {"slide", "jump", "overlap", "walkerHit", "heatingKnobs", "streetBot", "redRuns"}
print(f"{'line':5} {'check':28} {'baseline':>9} {'now':>9}  of")
for f in sorted(glob.glob(os.path.join(CUR, "line*.json"))):
    now = json.load(open(f, encoding="utf-8"))
    bf = os.path.join(BASE, os.path.basename(f))
    base = json.load(open(bf, encoding="utf-8")) if os.path.exists(bf) else {"checks": {}}
    for name, c in now["checks"].items():
        b = base["checks"].get(name, {}).get("count")
        band = b * 0.15 + 5 if name in NOISY and b is not None else 0
        mark = "" if b is None or abs(c["count"] - b) <= band else ("  worse" if c["count"] > b else "  better")
        worse += mark == "  worse"
        print(f"{now['line']:5} {name:28} {'-' if b is None else b:>9} {c['count']:>9}  {c['of']}{mark}")
        for k, v in sorted((c.get("samples") or {}).items()):
            bv = base["checks"].get(name, {}).get("samples", {}).get(k)
            print(f"{'':5}   {k:26} {'-' if bv is None else bv:>9} {v:>9}")
sys.exit(1 if worse else 0)
