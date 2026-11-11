"""Help in the game's menu (#330): python -P -E tools/test_help.py [--line 37] [--shots DIR]
The real game on a phone and a desktop page, Czech and English: the entry opens the player's guide in the
language of the setting, the language can change while it is open, nothing runs off the side, Esc and the
button close it. The renderer alone runs without data; the game's part skips without data/."""
import argparse
import faulthandler
import functools
import http.server
import os
import re
import sys
import threading
import unittest

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves tools/ out)
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE, SHOTS = "37", None


def table_rows(readme):
    """The body rows of the guide's tables (the help shows them all): its table lines less a header and a separator each."""
    lines = [x for x in open(os.path.join(ROOT, readme), encoding="utf-8").read().split("\n") if x.startswith("|")]
    return len(lines) - 2 * sum(1 for x in lines if re.match(r"^\|[\s:|-]+\|\s*$", x))


SIZES = {"phone": ((390, 844), True), "desktop": ((1280, 800), False)}
WORDS = {"cs": ("Vaše směna", "Zavřít"), "en": ("Your shift", "Close")}


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class Help(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        faulthandler.dump_traceback_later(600, exit=True)
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.pw = sync_playwright().start()
        cls.browser = gpu.launch(cls.pw)[0]

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        faulthandler.cancel_dump_traceback_later()

    def test_renderer(self):
        page = self.browser.new_page()
        page.goto(f"{self.url}/README.md")
        html = page.evaluate("""async () => {
          const { renderMarkdown, helpPart } = await import('/src/help.js');
          return { part: helpPart('out <!-' + '- help -' + '-> in <!-' + '- /help -' + '-> out'), none: helpPart('nothing'),
            md: renderMarkdown('## A *b*\\n\\ntext **bold** `k*e*y` <script>\\nmore [x](https://e.cz/a) [y](DEV.md#z)\\n\\n- one\\n  two\\n- three\\n\\n- four\\n  - sub\\n    more\\n  - **sub2**\\n\\n| a | b |\\n|---|---|\\n| `c` | d |\\n') };
        }""")
        self.assertEqual((html["part"], html["none"]), ("in", ""))
        md = html["md"]
        self.assertIn("<h2>A <i>b</i></h2>", md)
        self.assertIn("<b>bold</b> <kbd>k*e*y</kbd> &lt;script&gt; more", md)
        self.assertIn('<a href="https://e.cz/a" target="_blank" rel="noopener">x</a> y</p>', md)
        self.assertIn("<ul><li>one two</li><li>three</li></ul>", md)
        self.assertIn("<li>four<ul><li>sub more</li><li><b>sub2</b></li></ul></li>", md)
        self.assertIn("<th>a</th>", md)
        self.assertIn("<td><kbd>c</kbd></td><td>d</td>", md)
        self.assertNotIn("---", md)
        page.close()

    @unittest.skipUnless(os.path.exists(os.path.join(ROOT, "data", f"line{LINE}.json")), "needs data/: snapshot.py data-fetch")
    def test_in_the_game(self):
        for name, ((w, h), touch) in SIZES.items():
            with self.subTest(size=name):
                ctx = self.browser.new_context(viewport={"width": w, "height": h}, is_mobile=touch, has_touch=touch, locale="cs-CZ")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", functools.partial(lambda out, e: out.append(str(e)), errors))
                page.goto(f"{self.url}/index.html?line={LINE}")
                page.wait_for_selector("#btnHelp:visible", timeout=240000)
                self.assertEqual(page.inner_text("#btnHelp"), "Nápověda")
                page.click("#btnHelp")
                for lang in ("cs", "en"):
                    word, close = WORDS[lang]
                    if lang == "en":
                        # (the language changes under the panel: a setting by another tab or a test)
                        page.evaluate("import('/src/i18n.js').then((m) => m.setLang('en'))")
                    page.wait_for_function("w => document.querySelector('#helpBody').textContent.includes(w)", arg=word, timeout=15000)
                    self.assertEqual(page.inner_text("#btnHelpClose"), close)
                    r = page.evaluate("""() => { const b = document.querySelector('#helpPanel .card'), t = document.querySelector('#helpBody');
                      return { over: b.scrollWidth - b.clientWidth, scrolls: b.scrollHeight > b.clientHeight, rows: t.querySelectorAll('tbody tr').length, nested: t.querySelectorAll('li li').length,
                        heads: t.querySelectorAll('h3').length, raw: /<!--|\\*\\*|^##/m.test(t.textContent), run: t.textContent.includes('serve.py') }; }""")
                    self.assertLessEqual(r["over"], 0, f"{name} {lang}: wider than its card")
                    self.assertTrue(r["scrolls"])
                    self.assertEqual(r["rows"], table_rows("README.md" if lang == "cs" else "README.en.md"))
                    self.assertEqual(r["nested"], 3)
                    self.assertGreater(r["heads"], 8)
                    self.assertFalse(r["raw"], "Markdown left in the text")
                    self.assertFalse(r["run"], "the developer's part in the help")
                    if SHOTS:
                        os.makedirs(SHOTS, exist_ok=True)
                        page.screenshot(path=os.path.join(SHOTS, f"help-{name}-{lang}.png"))
                page.evaluate("document.querySelector('#helpPanel .card').scrollTop = 900")
                self.assertTrue(page.is_visible("#btnHelpClose"))
                page.keyboard.press("Escape")
                self.assertFalse(page.is_visible("#helpPanel"))
                page.click("#btnHelp")
                self.assertEqual(page.evaluate("document.querySelector('#helpPanel .card').scrollTop"), 0)
                page.click("#btnHelpClose")
                self.assertFalse(page.is_visible("#helpPanel"))
                self.assertTrue(page.is_visible("#menu"))
                self.assertEqual(errors, [])
                ctx.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default=LINE)
    ap.add_argument("--shots")
    args, rest = ap.parse_known_args()
    LINE, SHOTS = args.line, args.shots
    unittest.main(argv=[sys.argv[0], *rest])
