"""The ⚑ Report button in a shift (src/report.js, #138): python -P -E tools/test_report.py [--line 17]
(tools/serve.py's handler on a free port, the reports in a temp folder). Starts a shift, opens the
report with F9, sends a note and checks the stored record: the note, the state, a JPEG screenshot."""
import argparse
import base64
import json
import os
import shutil
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serve  # noqa: E402


class Quiet(serve.NoCache):
    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    args = ap.parse_args()
    tmp = tempfile.mkdtemp()
    serve.REVIEWS = tmp
    server = serve.Server(('127.0.0.1', 0), lambda *a, **k: Quiet(*a, directory=serve.ROOT, **k))
    server.identity, server.rate, server.lan = None, 0, False
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fails = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(f"http://127.0.0.1:{server.server_port}/?line={args.line}", timeout=180000)
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=180000)
            page.click("#btnStart")
            page.wait_for_function("window.game && document.body.classList.contains('shift')", timeout=60000)
            page.wait_for_timeout(1500)
            btn = page.is_visible("#rpBtn")
            page.keyboard.press("F9")
            page.wait_for_selector("#rpBox.show", timeout=5000)
            paused = page.evaluate("window.game.paused")
            page.fill("#rpNote", "the kerb floats here")
            page.select_option("#rpKind", "streets / kerbs")
            page.click("#rpSend")
            page.wait_for_function("document.getElementById('rpMsg').textContent.includes('Sent as')", timeout=20000)
            msg = page.text_content("#rpMsg")
            page.wait_for_function("!document.getElementById('rpBox').classList.contains('show')", timeout=8000)
            after = page.evaluate("window.game.paused")
            browser.close()
    finally:
        server.shutdown()
    files = [f for f in os.listdir(tmp) if f.startswith("report-")]
    rec = None
    if len(files) == 1:
        rec = next(iter(json.load(open(os.path.join(tmp, files[0]), encoding="utf-8"))["items"].values()))
    shutil.rmtree(tmp, ignore_errors=True)
    short = {k: v for k, v in (rec or {}).items() if k != "shot"}
    print(json.dumps({"button": btn, "paused": paused, "after": after, "msg": msg, "files": files, "rec": short}, ensure_ascii=False)[:1500])
    if not btn:
        fails.append("no ⚑ Report button in the shift")
    if not paused or after:
        fails.append(f"the game is not paused while reporting (paused {paused}, after {after})")
    if not rec:
        fails.append(f"no single report stored: {files}")
    else:
        if rec.get("note") != "the kerb floats here" or rec.get("kind") != "streets / kerbs":
            fails.append("the note or kind is not stored")
        if not (rec.get("tram") or {}).get("x") or not rec.get("lat") or "review&at=" not in rec.get("review", ""):
            fails.append("the state (tram place, lat/lon, review link) is missing")
        shot = rec.get("shot") or ""
        if not shot.startswith("data:image/jpeg;base64,") or base64.b64decode(shot.split(",", 1)[1])[:2] != b"\xff\xd8":
            fails.append("no JPEG screenshot")
        elif all(c == shot[40] for c in shot[40:4000]):
            fails.append("the screenshot is blank")
        if files[0][:-5] not in (msg or ""):
            fails.append("the id shown is not the stored one")
    if fails:
        sys.exit("; ".join(fails))
    print("report: button, F9, paused, note + state + screenshot stored, id shown, resumed: pass")


if __name__ == "__main__":
    main()
