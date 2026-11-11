"""The ✉ Feedback button in a shift (src/report.js, #138, #350): python -P -E tools/test_report.py [--line 17]
(tools/serve.py's handler on a free port, the notes in a temp folder). Starts a shift, opens the form with
F9, checks it in Czech too, sends a note and checks the stored note: the note, the state, the errors met,
a JPEG screenshot beside it."""
import argparse
import json
import os
import shutil
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feedback  # noqa: E402
import serve  # noqa: E402
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)


class Quiet(serve.NoCache):
    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    args = ap.parse_args()
    tmp = tempfile.mkdtemp()
    feedback.DEST = tmp
    server = serve.Server(('127.0.0.1', 0), lambda *a, **k: Quiet(*a, directory=serve.ROOT, **k))
    server.identity, server.rate, server.lan = None, 0, False
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fails = []
    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]
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
            # (an empty note is not sent; an error met before it goes with the note)
            page.click("#rpSend")
            empty = page.text_content("#rpMsg")
            page.evaluate("setTimeout(() => { throw new Error('a test error'); })")
            page.wait_for_timeout(200)
            cs = page.evaluate("(async () => { const m = await import('./src/i18n.js'); m.setLang('cs'); const t = document.getElementById('rpTitle').textContent; m.setLang('en'); return t; })()")
            page.fill("#rpNote", "the kerb floats here")
            page.select_option("#rpKind", "city")
            page.click("#rpSend")
            page.wait_for_function("document.getElementById('rpMsg').textContent.includes('Sent as')", timeout=20000)
            msg = page.text_content("#rpMsg")
            page.wait_for_function("!document.getElementById('rpBox').classList.contains('show')", timeout=8000)
            after = page.evaluate("window.game.paused")
            browser.close()
    finally:
        server.shutdown()
    local = os.path.join(tmp, "local")
    files = sorted(os.listdir(local)) if os.path.isdir(local) else []
    notes = [f for f in files if f.endswith(".json")]
    rec, jpg = None, b""
    if len(notes) == 1:
        rec = json.load(open(os.path.join(local, notes[0]), encoding="utf-8"))
        if os.path.exists(os.path.join(local, notes[0][:-5] + ".jpg")):
            jpg = open(os.path.join(local, notes[0][:-5] + ".jpg"), "rb").read()
    shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps({"button": btn, "paused": paused, "after": after, "msg": msg, "empty": empty, "cs": cs, "files": files, "rec": rec},
                     ensure_ascii=False)[:1500])
    if not btn:
        fails.append("no ✉ Feedback button in the shift")
    if empty != "Write a note first.":
        fails.append(f"an empty note: {empty!r}")
    if cs != "Napište nám":
        fails.append(f"the form in Czech: {cs!r}")
    if not paused or after:
        fails.append(f"the game is not paused while reporting (paused {paused}, after {after})")
    if not rec:
        fails.append(f"no single note stored: {files}")
    else:
        if rec.get("note") != "the kerb floats here" or rec.get("kind") != "city":
            fails.append("the note or kind is not stored")
        if not any("a test error" in e.get("msg", "") for e in rec.get("errors") or []):
            fails.append(f"the error met is not in the note: {rec.get('errors')}")
        if not (rec.get("tram") or {}).get("x") or not rec.get("lat") or "review&at=" not in rec.get("review", ""):
            fails.append("the state (tram place, lat/lon, review link) is missing")
        if rec.get("shot") != notes[0][:-5] + ".jpg" or jpg[:2] != b"\xff\xd8":
            fails.append("no JPEG screenshot beside the note")
        elif all(c == jpg[600] for c in jpg[600:4000]):
            fails.append("the screenshot is blank")
        if notes[0][:-5] not in (msg or ""):
            fails.append("the id shown is not the stored one")
    if fails:
        sys.exit("; ".join(fails))
    print("feedback: button, F9, Czech, empty refused, paused, note + state + errors + screenshot stored, id shown, resumed: pass")


if __name__ == "__main__":
    main()
