# SPDX-License-Identifier: AGPL-3.0-or-later
"""A submitted package checked as the game checks it, and pictured (#580): tools/submissions.py --check ID.

Usage: python -P -E tools/submissions.py --check ID [--out DIR]

Its pack (pack.zip, or the files at its address, fetched here and kept as pack.zip beside its meta.json so an accepted
one can be hosted) is installed in a fresh headless Chromium through the page's own code (src/packages.js install),
and each vehicle in it is pictured from the fixed views of tools/test_t3simple.py --shots, beside the hybrid
for scale. Writes DIR/report.json (each package's problems, warnings and measures) and DIR/*.png. Exit code 1 when
the check refuses a package. Needs data/line17.json (python -I tools/snapshot.py data-fetch).
"""
import functools
import http.server
import io
import json
import os
import sys
import threading
import urllib.parse
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))  # (python -P leaves it out)
import submissions  # noqa: E402

ADDRESS = "/__submission.zip"   # where the page reads the pack (a route of the test browser, not a file)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def get(url, cap):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "prague-transport-sim review"}), timeout=60) as r:
        data = r.read(cap + 1)
    if len(data) > cap:
        raise SystemExit(f"submission_check: {url} is over the package cap")
    return data


def fetch_pack(url, r):
    """The files at a submission's address as a .zip: the .zip itself, or the package.json and the files it lists."""
    cap = r["caps"]["package"]
    if urllib.parse.urlsplit(url).path.endswith(".zip"):
        return get(url, cap)
    text = get(url, r["caps"]["data"])
    man = json.loads(text)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("package.json", text)
        for f in man.get("files", []):
            path = f.get("path", "")
            if path.startswith("/") or ".." in path.split("/") or "\\" in path:
                continue
            z.writestr(path, get(urllib.parse.urljoin(url, path), cap))
    return buf.getvalue()


INSTALL = r"""async (address) => {
  const p = await import('/src/packages.js');
  const reports = await p.install(await p.fetchEntries(address), 'review');
  return reports.map((r) => ({ id: r.id, ok: r.ok, problems: r.problems || [], warnings: r.warnings || [], fit: r.fit || null,
    kind: p.state.get(r.id)?.manifest?.kind ?? null }));
}"""


def run(row, out):
    from playwright.sync_api import sync_playwright
    import gpu
    from test_t3simple import SHOTS, montage
    site, folder, meta, _ = row
    if not os.path.exists(os.path.join(ROOT, "data", "line17.json")):
        raise SystemExit("submission_check: no data/line17.json (python -I tools/snapshot.py data-fetch)")
    r = submissions.rules()
    path = os.path.join(folder, "pack.zip")
    if os.path.isfile(path):
        pack = open(path, "rb").read()
    else:
        pack = fetch_pack(meta["url"], r)
        with open(path, "wb") as f:
            f.write(pack)
    why = submissions.zip_problem(pack, r)
    os.makedirs(out, exist_ok=True)
    report = {"id": meta["id"], "site": site, "submitted": meta.get("packages"), "zip": why, "packages": []}
    if not why:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = gpu.launch(p)[0]
                page = browser.new_context(viewport={"width": 1100, "height": 700}).new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route(f"**{ADDRESS}", lambda route: route.fulfill(status=200, body=pack, content_type="application/zip"))
                page.goto(f"http://127.0.0.1:{server.server_port}/?line=17", timeout=300000)
                page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
                report["packages"] = page.evaluate(INSTALL, ADDRESS)
                kinds = [x["id"] for x in report["packages"] if x["ok"] and x["kind"] == "vehicle"]
                if kinds:
                    shots = page.evaluate(SHOTS, {"kinds": ["hybrid", *kinds]})
                    import base64
                    for k, v in shots.items():
                        if not k.endswith("-kind"):
                            open(os.path.join(out, f"{k}.png"), "wb").write(base64.b64decode(v.split(",", 1)[1]))
                    montage(out, ["hybrid", *kinds], sorted({k.split("-", 1)[1] for k in shots if k.startswith("hybrid-") and not k.endswith("-kind")}))
                report["errors"] = errors[:5]
                browser.close()
        finally:
            server.shutdown()
    with open(os.path.join(out, "report.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    ok = not why and report["packages"] and all(x["ok"] for x in report["packages"])
    for x in report["packages"]:
        print(f"{x['id']}: {'passes' if x['ok'] else 'refused'}" + "".join(f"\n    {m}" for m in x["problems"] + x["warnings"]))
    if why:
        print(f"{meta['id']}: its zip is refused ({why})")
    print(f"{os.path.relpath(out, ROOT)}: report.json and the pictures (compare-*.png: the hybrid above, for scale)")
    return 0 if ok else 1
