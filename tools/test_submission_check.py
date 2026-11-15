# SPDX-License-Identifier: AGPL-3.0-or-later
"""Submitting a vehicle package (#580) end to end in headless Chromium, against tools/serve.py on a free port.

Usage: python -P -E tools/test_submission_check.py [--line 17]

1. The Vehicles... page sends tools/test_packages.py's sample bundle as a .zip (the hosting box ticked), and its
   vehicle as an address (a package.json on an author's host, answered by the test browser). Both land in
   <submissions>/local/ with the check's report; the game is as it was after the check (nothing installed).
2. A package the check refuses (a wrong hash) cannot be sent: the page says why and nothing lands.
3. tools/submissions.py --check installs the zip's packages in a fresh browser and pictures its vehicle.
4. --accept puts it in a catalogue, hosted; the game lists it and installs it from there.
Needs the line's data (python -I tools/snapshot.py data-fetch); skips without it.
"""
import argparse
import faulthandler
import io
import json
import os
import shutil
import sys
import tempfile
import threading
from contextlib import redirect_stdout
from unittest import mock

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))  # (python -P leaves it out)
import gpu  # noqa: E402
import serve  # noqa: E402
import submission_check  # noqa: E402
import submissions  # noqa: E402
from test_packages import VID, samples, vehicle  # noqa: E402

AUTHOR = "https://author.example.org/box"


class Quiet(serve.NoCache):
    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.exists(os.path.join(ROOT, "data", f"line{args.line}.json")):
        print(f"skipped: no data/line{args.line}.json (python -I tools/snapshot.py data-fetch)")
        return 0
    faulthandler.dump_traceback_later(900, exit=True)  # the whole test: page.evaluate has no time limit
    tmp = tempfile.mkdtemp()
    fails = []

    def need(ok, why):
        if not ok:
            fails.append(why)
            print("FAIL", why)

    good, broken, _ = samples()
    vm, vf = vehicle()
    author = {f"{AUTHOR}/package.json": json.dumps(vm).encode(), **{f"{AUTHOR}/{k}": v for k, v in vf.items()}}
    local = os.path.join(tmp, "local")
    p = mock.patch.object(submissions, "DEST", tmp)
    p.start()
    server = serve.Server(("127.0.0.1", 0), lambda *a, **k: Quiet(*a, directory=ROOT, **k))
    server.identity, server.rate, server.lan = None, 0, False
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as pw:
            browser = gpu.launch(pw)[0]
            page = browser.new_context(viewport={"width": 1100, "height": 900}).new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(f"{AUTHOR}/**", lambda route: route.fulfill(status=200, body=author[route.request.url]) if route.request.url in author
                       else route.fulfill(status=404))
            page.goto(f"{base}/?line={args.line}", timeout=300000)
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
            page.click("#btnVehicles")

            def send(zip_bytes=None, url=None, host=False):
                if zip_bytes is not None:
                    page.set_input_files("#subZip", files=[{"name": "pack.zip", "mimeType": "application/zip", "buffer": zip_bytes}])
                if url:
                    page.fill("#subUrl", url)
                page.fill("#subContact", "author@example.org")
                if host != page.is_checked("#subHost"):
                    page.click("#subHost")
                if not page.is_checked("#subLicence"):
                    page.click("#subLicence")
                before = page.evaluate("document.getElementById('subReport').innerText")
                page.click("#subSend")
                page.wait_for_function("(b) => { const r = document.getElementById('subReport'); return r && r.innerText !== b"
                                       " && !document.getElementById('subSend').disabled; }", arg=before, timeout=120000)
                return page.evaluate("""() => ({ text: document.getElementById('subReport').innerText,
                  id: document.querySelector('#subReport [data-id]')?.dataset.id || null })""")

            r = send(good, host=True)
            print("zip:", r["text"].replace("\n", " | "))
            zid = r["id"]
            need(zid and submissions.ID.fullmatch(zid), f"the .zip: wants a submission id, got {r}")
            if zid:
                m = submissions.load(os.path.join(local, zid, "meta.json"))
                need(sorted(x["id"] for x in m["packages"]) == sorted([VID, "sample.box-sounds", "sample.box-fleet"]) and m["host"] is True
                     and m["contact"] == "author@example.org" and os.path.isfile(os.path.join(local, zid, "pack.zip")),
                     f"the .zip's submission: {m}")
            state = page.evaluate("""async () => { const p = await import('/src/packages.js'), v = await import('/src/vehicles.js');
              return { installed: p.state.size, registered: v.byId.has('sample.box-tram') }; }""")
            need(state == {"installed": 0, "registered": False}, f"after the check the game is as it was: {state}")
            page.click("#btnPkgClose")
            page.click("#btnVehicles")   # (a fresh form: the zip picked is gone)
            r = send(url=f"{AUTHOR}/package.json")
            print("address:", r["text"].replace("\n", " | "))
            if r["id"]:
                m = submissions.load(os.path.join(local, r["id"], "meta.json"))
                need(m["url"] == f"{AUTHOR}/package.json" and not os.path.exists(os.path.join(local, r["id"], "pack.zip")) and m["host"] is False,
                     f"the address's submission: {m}")
            else:
                need(False, f"the address: wants a submission id, got {r}")
            page.click("#btnPkgClose")
            page.click("#btnVehicles")
            n = len(os.listdir(local))
            r = send(broken["wrong hash"][0])
            print("broken:", r["text"].replace("\n", " | "))
            need(not r["id"] and "sha256" in r["text"] and len(os.listdir(local)) == n, f"a refused package is not sent: {r}")
            need(not errors, f"page errors: {errors}")
            browser.close()
        # the review
        out = os.path.join(tmp, "check")
        if zid:
            with redirect_stdout(io.StringIO()) as said:
                code = submission_check.run(submissions.find(zid, tmp), out)
            print(said.getvalue().strip())
            rep = submissions.load(os.path.join(out, "report.json"))
            need(code == 0 and len(rep["packages"]) == 3 and all(x["ok"] for x in rep["packages"]), f"--check: {rep}")
            need(os.path.isfile(os.path.join(out, f"{VID}-side.png")) and os.path.isfile(os.path.join(out, "compare-side.png")),
                 f"--check pictures: {sorted(os.listdir(out))[:8]}")
            cat = os.path.join(tmp, "catalogue.json")
            with open(cat, "w", encoding="utf-8") as f:
                json.dump({"packages": []}, f)
            e = submissions.accept(zid, catalogue=cat, dest=tmp)
            need(e["url"] == f"hosted/{VID}-1.0.0.zip" and sorted(e["packages"]) == sorted([VID, "sample.box-sounds", "sample.box-fleet"]), f"--accept: {e}")
            hosted = open(os.path.join(tmp, "hosted", f"{VID}-1.0.0.zip"), "rb").read()
            with sync_playwright() as pw:
                browser = gpu.launch(pw)[0]
                page = browser.new_context(viewport={"width": 1100, "height": 900}).new_page()
                page.route("**/assets/catalogue.json", lambda route: route.fulfill(status=200, path=cat))
                page.route(f"**/{e['url']}", lambda route: route.fulfill(status=200, body=hosted, content_type="application/zip"))
                page.goto(f"{base}/?line={args.line}", timeout=300000)
                page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
                page.click("#btnVehicles")
                page.wait_for_selector("#pkgCatalogue button:not([disabled])", timeout=60000)
                page.click("#pkgCatalogue button")
                page.wait_for_selector(f".pkgRow[data-id='{VID}']", timeout=120000)
                got = page.evaluate("async () => [...(await import('/src/packages.js')).state.keys()].sort()")
                need(got == sorted([VID, "sample.box-sounds", "sample.box-fleet"]), f"installed from the catalogue: {got}")
                browser.close()
    finally:
        server.shutdown()
        p.stop()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"submitting a package: a .zip and an address sent, a refused one not, checked and pictured, accepted and installed from the list: "
          f"{'pass' if not fails else 'FAIL'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
