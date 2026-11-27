# SPDX-License-Identifier: AGPL-3.0-or-later
"""Check the announcement text rules and the compiled line 17 voice pack."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from announcements import OUTPUT, ROOT, VOICES, stop_entries  # noqa: E402


class AnnouncementPack(unittest.TestCase):
    def test_sentence_order_and_terminus(self):
        names = ["First", "Transfer", "Last"]
        facts = [{"name": "Transfer", "type": "street", "from": "First"}]
        pattern = [("s1", set()), ("s2", {"metro", "train"}), ("s3", set())]
        first, transfer, last = stop_entries(names, pattern, facts)
        self.assertEqual(first["text"], "First. Příští zastávka... Transfer.")
        self.assertEqual(transfer["text"], "Transfer. Přestup na metro. Přestup na vlak. "
                                          "Výstup do vozovky. Příští zastávka... Last.")
        self.assertEqual(last["text"], "Last. Konečná zastávka, prosíme vystupte.")
        self.assertIsNone(last["next"])

    def test_reverse_stop_fact_does_not_apply(self):
        pattern = [("s3", set()), ("s2", set()), ("s1", set())]
        facts = [{"name": "Transfer", "type": "street", "from": "First"}]
        self.assertEqual(list(stop_entries(["Last", "Transfer", "First"], pattern, facts))[1]["clauses"], [])

    def test_compiled_assets(self):
        pack = json.loads((OUTPUT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(pack["line"], "17")
        self.assertEqual(tuple(pack["voices"]), VOICES)
        self.assertEqual(pack["speakingRate"], 0.85)
        by_name = {s["name"]: s for s in pack["stops"]}
        self.assertEqual(by_name["Nádraží Holešovice"]["clauses"], ["Přestup na metro.", "Přestup na vlak."])
        self.assertEqual(by_name["Březiněveská"]["clauses"], ["Výstup do vozovky."])
        self.assertIsNone(pack["stops"][-1]["next"])
        if (ROOT / "data/line17.json").exists():
            line = json.loads((ROOT / "data/line17.json").read_text(encoding="utf-8"))
            self.assertEqual([s["name"] for s in pack["stops"]], [s["name"] for s in line["stops"]])
        for stop in pack["stops"]:
            self.assertEqual(tuple(stop["clips"]), VOICES)
            for path in stop["clips"].values():
                self.assertGreater((OUTPUT / path).stat().st_size, 1000, path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
