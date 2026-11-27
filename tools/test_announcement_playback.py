# SPDX-License-Identifier: AGPL-3.0-or-later
"""Browser smoke checks for #894, including a seeded autopilot approach on line 17."""
import faulthandler
import json
from pathlib import Path
import sys
import unittest

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from announcements import OUTPUT, ROOT  # noqa: E402
from headless import serve, stop_server  # noqa: E402
import gpu  # noqa: E402

FIXTURE = """<!doctype html><html lang="en"><button id="start">Start</button>
<select id="selLine"><option>17</option></select>
<label hidden><span></span><select id="optAnnouncementVoice"></select></label>
<label hidden><span></span><select id="optAnnouncementDistance"></select></label>
<script type="module">
import { TramAudio, initAnnouncementMenu } from '/src/audio.js';
initAnnouncementMenu(() => 'en', () => {});
window.audio = new TramAudio();
document.querySelector('#start').onclick = () => {
  audio.start();
  audio.setActive(true);
};
</script>"""

APPROACH = """i => {
  window.headless = true;
  const stop = game.stops[i];
  const announcements = game.audio.announcements;
  for (let n = 0; n < 9000 && !announcements.run.seen.has(i) && !game.finished; n++) {
    run.step(1 / 30, null, null, false);
  }
  return { name: stop.name, distance: stop.target - game.tram.s, seen: [...announcements.run.seen] };
}"""


class AnnouncementPlayback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.url = serve(0)
        cls.addClassCleanup(stop_server, cls.server)
        cls.stops = json.loads((OUTPUT / "manifest.json").read_text(encoding="utf-8"))["stops"]

    def test_audio_lifecycle_and_settings(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            path = "/announcement-test"
            page.route(self.url + path, lambda route: route.fulfill(body=FIXTURE, content_type="text/html"))
            page.goto(self.url + path)
            page.wait_for_function("window.audio")
            page.click("#start")
            page.evaluate("stops => audio.announcements.prepareRun('17', stops, 1)", self.stops)
            page.evaluate("""() => {
                for (const [i, distance] of [[1, 0], [2, 115], [2, 99], [2, 95]]) {
                    audio.announcements.approach(i, distance, distance === 0);
                }
            }""")
            page.wait_for_function("audio.announcements.source")
            self.assertEqual(page.evaluate("""() => {
                const a = audio.announcements;
                return [a.current.i, a.current.voice, [...a.run.seen]];
            }"""), [2, "Aoede", [2]])
            page.evaluate("audio.setActive(false)")
            self.assertTrue(page.evaluate("!audio.announcements.source && audio.announcements.current.offset >= 0"))
            page.evaluate("audio.setActive(true)")
            page.wait_for_function("audio.announcements.source")
            page.evaluate("audio.setMuted(true)")
            self.assertEqual(page.evaluate("audio.announcements.output.gain.value"), 0)
            page.evaluate("audio.setMuted(false)")
            page.select_option("#optAnnouncementVoice", "Algieba")
            page.select_option("#optAnnouncementDistance", "0")
            page.evaluate("""() => {
                const a = audio.announcements;
                a.approach(3, 10, false);
                if (a.run.seen.has(3)) throw new Error('Early arrival announcement');
                a.approach(3, 0, true);
                a.approach(3, 0, true);
            }""")
            self.assertEqual(page.evaluate("audio.announcements.run.queue.length"), 1)
            page.wait_for_function("audio.announcements.current?.voice === 'Algieba' && audio.announcements.source")
            page.select_option("#optAnnouncementVoice", "Sulafat")
            page.evaluate("i => audio.announcements.approach(i, 0, true)", len(self.stops) - 1)
            page.evaluate("audio.setActive(false, true)")
            page.wait_for_function("audio.announcements.current?.voice === 'Sulafat' && audio.announcements.source")
            page.wait_for_function("!audio.announcements.current", timeout=20000)
            page.evaluate("""stops => {
                audio.announcements.prepareRun('23', stops, 0);
                audio.setActive(true);
                audio.announcements.approach(1, 0, true);
            }""", self.stops)
            self.assertTrue(page.evaluate("!audio.announcements.run && !audio.announcements.source"))
            browser.close()

    @unittest.skipUnless((ROOT / "data/line17.json").exists(), "needs the built line 17 data")
    def test_seeded_transfer_approach(self):
        with sync_playwright() as pw:
            browser = gpu.launch(pw)[0]
            page = browser.new_page(viewport={"width": 960, "height": 600})
            page.goto(self.url + "/?line=17", timeout=120000)
            page.wait_for_selector("#btnStart", state="visible", timeout=120000)
            page.select_option("#selStop", "27")
            page.select_option("#optAnnouncementVoice", "Sulafat")
            page.check("#optAuto")
            page.evaluate("window.runSeed = 894")
            page.click("#btnStart")
            page.wait_for_function("game.autopilot && game.audio.active", timeout=120000)
            seen_at = page.evaluate(APPROACH, 28)
            self.assertEqual(seen_at["name"], "Nádraží Holešovice")
            self.assertEqual(seen_at["seen"], [28])
            self.assertGreater(seen_at["distance"], 99)
            self.assertLessEqual(seen_at["distance"], 100)
            page.wait_for_function("game.audio.announcements.current?.voice === 'Sulafat' && game.audio.announcements.source")
            page.evaluate("""() => {
                const timing = document.querySelector('#optAnnouncementDistance');
                timing.value = '50';
                timing.dispatchEvent(new Event('change'));
            }""")
            ordinary = page.evaluate(APPROACH, 29)
            self.assertEqual(ordinary["name"], "Trojská")
            self.assertEqual(ordinary["seen"], [28, 29])
            self.assertGreater(ordinary["distance"], 49)
            self.assertLessEqual(ordinary["distance"], 50)
            page.evaluate("""async () => {
                const timing = document.querySelector('#optAnnouncementDistance');
                timing.value = '0';
                timing.dispatchEvent(new Event('change'));
                await window.startRun({ startStop: 35, autopilot: true, seed: 894 });
                game.audio.setActive(true);
            }""")
            terminus = page.evaluate(APPROACH, 36)
            self.assertEqual(terminus["name"], "Vozovna Kobylisy")
            self.assertEqual(terminus["seen"], [36])
            self.assertTrue(page.evaluate("game.stops[36].arrived"))
            page.evaluate("game.audio.setActive(false, true)")
            page.wait_for_function("game.audio.announcements.current?.i === 36 && game.audio.announcements.source")
            print(f"Seed 894 trigger distances: transfer {seen_at['distance']:.1f} m, "
                  f"ordinary {ordinary['distance']:.1f} m, terminus on arrival ({terminus['distance']:.1f} m).")
            browser.close()


if __name__ == "__main__":
    faulthandler.dump_traceback_later(360, exit=True)
    unittest.main(verbosity=2)
