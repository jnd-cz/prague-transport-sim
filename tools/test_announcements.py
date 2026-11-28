# SPDX-License-Identifier: AGPL-3.0-or-later
"""Check the announcement text rules and the compiled line 17 voice pack."""
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
        self.assertEqual(first["segments"], ["stop-s1", "next", "stop-s2", "next-request"])
        self.assertEqual(transfer["segments"], ["stop-s2", "request", "metro", "train", "road", "next", "stop-s3"])
        self.assertEqual(last["segments"], ["stop-s3", "terminus"])
        self.assertEqual(clips["stop-s2"]["text"], "Transfer.")
        self.assertEqual(clips["stop-s2"]["spoken"], "Spoken.")
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
        self.assertEqual(pack["line"], "17")
        self.assertEqual(tuple(pack["voices"]), VOICES)
        self.assertEqual(pack["speakingRate"], 0.85)
        by_name = {s["name"]: s for s in pack["stops"]}
        self.assertEqual(by_name["Nádraží Holešovice"]["segments"][1:3], ["metro", "train"])
        self.assertNotIn("road", by_name["Březiněveská"]["segments"])
        key = by_name["Strossmayerovo náměstí"]["segments"][0]
        self.assertEqual(pack["segments"][key]["text"], "Strossmayerovo náměstí.")
        self.assertEqual(pack["segments"][key]["spoken"], "Štrosmajerovo náměstí.")
        self.assertEqual(by_name["Modřanská rokle"]["segments"][-1], "next-request")
        self.assertEqual(by_name["U Libušského potoka"]["segments"][1], "request")
        self.assertEqual(pack["stops"][-1]["segments"][-1], "terminus")
        if (ROOT / "data/line17.json").exists():
            line = json.loads((ROOT / "data/line17.json").read_text(encoding="utf-8"))
            self.assertEqual([(s["name"], s["request"]) for s in pack["stops"]],
                             [(s["name"], s["request"]) for s in line["stops"]])
        self.assertEqual({key for s in pack["stops"] for key in s["segments"]}, set(pack["segments"]))
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
