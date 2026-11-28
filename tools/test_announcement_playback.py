# SPDX-License-Identifier: AGPL-3.0-or-later
"""Browser smoke checks for #894, including a seeded autopilot approach on line 17."""
import faulthandler
import json
from pathlib import Path
import sys
import unittest
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from announcements import OUTPUT, ROOT  # noqa: E402
from headless import serve, stop_server  # noqa: E402
import gpu  # noqa: E402

FIXTURE = """<!doctype html><html lang="en"><button id="start">Start</button>
<select id="selLine"><option>17</option></select>
<label hidden><span></span><select id="optAnnouncementVoice"></select></label>
<label hidden><span></span><select id="optAnnouncementDistance"></select></label>
<label hidden><span></span><input id="optAnnouncementVolume" type="range" min="0" max="100" step="5"><output></output></label>
<script type="module">
import { TramAudio, initAnnouncementMenu } from '/src/audio.js';
initAnnouncementMenu(() => 'en', () => {});
window.audio = new TramAudio();
document.querySelector('#start').onclick = () => {
  audio.start();
  audio.setActive(true);
};
</script>"""

SPEECH_FIXTURE = """() => {
  const synth = new EventTarget();
  let voices = [];
  window.spoken = [];
  window.setVoices = list => { voices = list; synth.dispatchEvent(new Event('voiceschanged')); };
  synth.getVoices = () => voices;
  synth.speak = utterance => spoken.push(utterance);
  synth.cancel = () => spoken.at(-1)?.onerror();
  Object.defineProperty(window, 'speechSynthesis', {value: synth});
  window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
}"""

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
        cls.lines = json.loads((OUTPUT / "manifest.json").read_text(encoding="utf-8"))["lines"]
        cls.stops = cls.lines["17"]

    def test_browser_czech_voice(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.add_init_script(f"({SPEECH_FIXTURE})()")
            path = "/announcement-browser-voice"
            page.route(self.url + path, lambda route: route.fulfill(body=FIXTURE, content_type="text/html"))
            mp3 = []
            page.on("request", lambda request: mp3.append(request.url) if urlsplit(request.url).path.endswith(".mp3") else None)
            page.goto(self.url + path)
            page.wait_for_function("window.audio")
            option = page.locator('#optAnnouncementVoice option[value="browser"]')
            self.assertEqual(option.count(), 0)
            page.evaluate("""setVoices([
                {name: 'English', lang: 'en-GB', default: true},
                {name: 'Online Czech', lang: 'cs-CZ'},
                {name: 'Local Czech', lang: 'cs-CZ', localService: true},
            ])""")
            self.assertEqual(option.text_content(), "Browser Czech voice (Local Czech)")
            page.select_option("#optAnnouncementVoice", "browser")
            page.click("#start")
            page.evaluate("stops => audio.announcements.prepareRun('17', stops, 24)", self.stops)
            page.wait_for_function("spoken.length === 1")
            self.assertEqual(page.evaluate("[spoken[0].text, spoken[0].voice.name, spoken[0].rate, spoken[0].volume]"),
                             ["Čechův most. Příští zastávka... Štrosmajerovo náměstí.", "Local Czech", 0.85, 1])
            page.evaluate("audio.setActive(false)")
            self.assertTrue(page.evaluate("!audio.announcements.utterance"))
            page.locator("#optAnnouncementVolume").evaluate("el => { el.value = '45'; el.dispatchEvent(new Event('input')); }")
            page.evaluate("audio.setActive(true)")
            self.assertEqual(page.evaluate("spoken.length"), 2)
            self.assertEqual(page.evaluate("spoken.at(-1).volume"), 0.45)
            page.evaluate("""() => {
                spoken.at(-1).onend();
                audio.announcements.preload(26);
                audio.announcements.approach(25, 99, false);
            }""")
            self.assertTrue(page.evaluate("spoken.at(-1).text.startsWith('Štrosmajerovo náměstí.')"))
            page.evaluate("audio.setMuted(true)")
            self.assertTrue(page.evaluate("!audio.announcements.utterance"))
            page.evaluate("audio.announcements.approach(26, 99, false); audio.setMuted(false)")
            self.assertEqual(page.evaluate("spoken.length"), 3)
            self.assertEqual(mp3, [])
            page.evaluate("setVoices([{name: 'English', lang: 'en-GB'}])")
            self.assertEqual(option.count(), 0)
            browser.close()

    def test_shared_cache_and_changed_itinerary(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            path = "/announcement-cache"
            page.route(self.url + path, lambda route: route.fulfill(body=FIXTURE, content_type="text/html"))
            page.goto(self.url + path)
            page.wait_for_function("window.audio")
            page.click("#start")
            for number, stops in self.lines.items():
                page.evaluate("([number, stops]) => audio.announcements.prepareRun(number, stops, stops.length - 2)",
                              [number, stops])
                page.wait_for_function("audio.announcements.source")
                self.assertEqual(page.evaluate("audio.announcements.run.calls.at(-1).at(-1)"), "terminus")
                page.wait_for_function("""async () => {
                    const run = audio.announcements.run;
                    const cache = await run.cache;
                    if (!cache) return false;
                    const keys = new Set((await cache.keys()).map(request => new URL(request.url).pathname));
                    return [...run.segments.keys()].every(path => keys.has('/assets/announcements/' + path));
                }""")
            page.reload()
            page.wait_for_function("window.audio")
            page.click("#start")
            mp3 = []
            page.on("request", lambda request: mp3.append(request.url) if urlsplit(request.url).path.endswith(".mp3") else None)
            page.evaluate("stops => audio.announcements.prepareRun('diversion', stops, 0)", self.stops[-2:])
            page.wait_for_function("audio.announcements.source")
            self.assertEqual(page.evaluate("audio.announcements.run.calls[0].includes('next')"), True)
            self.assertEqual(mp3, [])
            browser.close()

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
            page.wait_for_function("audio.announcements.current?.i === 1 && audio.announcements.source")
            page.evaluate("""async () => {
                const a = audio.announcements;
                a.preload(3);  // reached stop 2's platform
                await Promise.all([...a.run.preloads.get(2).values(), ...a.run.preloads.get(3).values()]);
                const prepared = await a.run.preloads.get(3).get('Algieba');
                if (prepared.length !== a.run.calls[3].length) throw new Error('Incomplete preload');
            }""")
            requests = []
            page.on("request", lambda request: requests.append(request.url) if urlsplit(request.url).path.endswith(".mp3") else None)
            page.context.set_offline(True)
            page.evaluate("""() => {
                for (const [i, distance] of [[1, 0], [2, 115], [2, 99], [2, 95]]) {
                    audio.announcements.approach(i, distance, distance === 0);
                }
            }""")
            self.assertEqual(page.evaluate("""() => {
                const a = audio.announcements;
                return [a.current.i, a.current.voice, [...a.run.seen]];
            }"""), [1, "Aoede", [1, 2]])
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
            self.assertEqual(page.evaluate("[...audio.announcements.run.seen]"), [1, 2, 3])
            page.wait_for_function("audio.announcements.current?.voice === 'Algieba' && audio.announcements.source")
            self.assertEqual(page.evaluate("audio.announcements.current.i"), 3)
            self.assertEqual(requests, [])
            page.context.set_offline(False)
            page.select_option("#optAnnouncementVoice", "Sulafat")
            page.evaluate("stops => audio.announcements.prepareRun('17', stops, stops.length - 2)", self.stops)
            page.wait_for_function("audio.announcements.source")
            last = len(self.stops) - 1
            page.evaluate("i => audio.announcements.approach(i, 0, true)", last)
            page.evaluate("audio.setActive(false, true)")
            page.wait_for_function("i => audio.announcements.current?.i === i && audio.announcements.source", arg=last)
            page.wait_for_function("!audio.announcements.current", timeout=20000)
            page.evaluate("""() => {
                audio.announcements.prepareRun('unknown', [{name: 'Uncatalogued stop'}], 0);
                audio.setActive(true);
            }""")
            page.wait_for_function("audio.announcements.run?.pack")
            self.assertTrue(page.evaluate("!audio.announcements.source && !audio.announcements.run.calls[0].length"))
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
            page.wait_for_function("game.audio.announcements.current?.i === 27 && game.audio.announcements.source")
            seen_at = page.evaluate(APPROACH, 28)
            self.assertEqual(seen_at["name"], "Nádraží Holešovice")
            self.assertEqual(seen_at["seen"], [27, 28])
            self.assertGreater(seen_at["distance"], 99)
            self.assertLessEqual(seen_at["distance"], 100)
            page.wait_for_function("game.audio.announcements.current?.i === 28 && game.audio.announcements.source")
            page.evaluate("""async () => {
                for (let n = 0; n < 9000 && !game.stops[28].arrived; n++) run.step(1 / 30, null, null, false);
                const voices = game.audio.announcements.run.preloads.get(29);
                if (!voices || !(await Promise.all(voices.values())).every(Boolean)) {
                  throw new Error('Arrival at the previous stop did not preload the next announcement');
                }
            }""")
            page.context.set_offline(True)
            page.evaluate("""() => {
                const timing = document.querySelector('#optAnnouncementDistance');
                timing.value = '50';
                timing.dispatchEvent(new Event('change'));
            }""")
            ordinary = page.evaluate(APPROACH, 29)
            self.assertEqual(ordinary["name"], "Trojská")
            self.assertEqual(ordinary["seen"], [27, 28, 29])
            self.assertGreater(ordinary["distance"], 49)
            self.assertLessEqual(ordinary["distance"], 50)
            page.wait_for_function("game.audio.announcements.current?.i === 29 && game.audio.announcements.source")
            page.context.set_offline(False)
            page.evaluate("""async () => {
                const timing = document.querySelector('#optAnnouncementDistance');
                timing.value = '0';
                timing.dispatchEvent(new Event('change'));
                await window.startRun({ startStop: 35, autopilot: true, seed: 894 });
                game.audio.setActive(true);
            }""")
            terminus = page.evaluate(APPROACH, 36)
            self.assertEqual(terminus["name"], "Vozovna Kobylisy")
            self.assertEqual(terminus["seen"], [35, 36])
            self.assertTrue(page.evaluate("game.stops[36].arrived"))
            page.evaluate("game.audio.setActive(false, true)")
            page.wait_for_function("game.audio.announcements.current?.i === 36 && game.audio.announcements.source")
            print(f"Seed 894 trigger distances: transfer {seen_at['distance']:.1f} m, "
                  f"ordinary {ordinary['distance']:.1f} m, terminus on arrival ({terminus['distance']:.1f} m).")
            browser.close()


if __name__ == "__main__":
    faulthandler.dump_traceback_later(360, exit=True)
    unittest.main(verbosity=2)
