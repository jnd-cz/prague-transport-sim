# SPDX-License-Identifier: AGPL-3.0-or-later
"""Check announcement wording, route coverage and the shared recordings."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from announcements import OUTPUT, ROOT, VOICES, announcement_plan  # noqa: E402


class AnnouncementPack(unittest.TestCase):
    def test_sentence_order_and_terminus(self):
        names = ["First", "Transfer", "Last"]
        facts = [{"name": "Transfer", "type": "street", "from": "First"}]
        pattern = [("s1", set(), False), ("s2", {"metro", "train"}, True), ("s3", set(), False)]
        pronunciations = {"Transfer": {"spoken": "Spoken"}}
        (first, transfer, last), clips = announcement_plan(names, pattern, facts, pronunciations)
        a, b, c = (s["segments"][0] for s in (first, transfer, last))
        self.assertEqual(first["segments"], [a, "next", b, "next-request"])
        self.assertEqual(transfer["segments"], [b, "request", "metro", "train", "road", "next", c])
        self.assertEqual(last["segments"], [c, "terminus"])
        self.assertEqual(clips[b]["text"], "Transfer.")
        self.assertEqual(clips[b]["spoken"], "Spoken.")
        self.assertEqual(clips["next-request"]["text"], "Příští zastávka je na znamení.")
        self.assertEqual(clips["request"]["text"], "Zastávka na znamení.")

    def test_reverse_stop_fact_does_not_apply(self):
        pattern = [("s1", set(), False), ("s2", set(), False), ("s3", set(), False)]
        truth = json.loads((ROOT / "data/truth.json").read_text(encoding="utf-8"))
        names = ["Kobylisy", "Březiněveská", "Líbeznická"]
        entries, clips = announcement_plan(names, pattern, truth["stops"], {})
        self.assertNotIn("road", entries[1]["segments"])
        self.assertNotIn("road", clips)
        entries, clips = announcement_plan(names[::-1], pattern[::-1], truth["stops"], {})
        self.assertIn("road", entries[1]["segments"])
        self.assertEqual(clips["road"]["text"], "Výstup do vozovky.")

    def test_compiled_assets(self):
        pack = json.loads((OUTPUT / "manifest.json").read_text(encoding="utf-8"))
        lines = pack["lines"]
        self.assertEqual(set(lines), {"9", "17", "22", "23", "37"})
        self.assertEqual(tuple(pack["voices"]), VOICES)
        self.assertEqual(pack["speakingRate"], 0.85)
        by_name = {s["name"]: s for s in lines["17"]}
        self.assertEqual(by_name["Nádraží Holešovice"]["segments"][1:3], ["metro", "train"])
        self.assertNotIn("road", by_name["Březiněveská"]["segments"])
        key = by_name["Strossmayerovo náměstí"]["segments"][0]
        self.assertEqual(pack["segments"][key]["text"], "Strossmayerovo náměstí.")
        self.assertEqual(pack["segments"][key]["spoken"], "Štrosmajerovo náměstí.")
        self.assertEqual(by_name["Modřanská rokle"]["segments"][-1], "next-request")
        self.assertEqual(by_name["U Libušského potoka"]["segments"][1], "request")
        self.assertEqual(lines["9"][29]["name"], "Nákladové nádraží Žižkov")
        self.assertIn("next", lines["9"][29]["segments"])
        used, names = set(), {}
        for number, stops in lines.items():
            self.assertEqual(stops[-1]["segments"][-1], "terminus")
            path = ROOT / f"data/line{number}.json"
            if path.exists():
                line = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual([(s["name"], s["request"]) for s in stops],
                                 [(s["name"], s["request"]) for s in line["stops"]])
            for stop in stops:
                key = stop["segments"][0]
                self.assertEqual(names.setdefault(stop["name"], key), key)
                used.update(stop["segments"])
        self.assertEqual(used, set(pack["segments"]))
        paths = set()
        for segment in pack["segments"].values():
            self.assertEqual(tuple(segment["clips"]), VOICES)
            for path in segment["clips"].values():
                self.assertNotIn(path, paths)
                self.assertGreater((OUTPUT / path).stat().st_size, 1000, path)
                paths.add(path)
        self.assertEqual(paths, {p.relative_to(OUTPUT).as_posix() for p in OUTPUT.rglob("*.mp3")})


if __name__ == "__main__":
    unittest.main(verbosity=2)
