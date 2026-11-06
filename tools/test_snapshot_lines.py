"""A line file from build_line.py alone is no full build: python -I tools/test_snapshot_lines.py"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import snapshot  # noqa: E402


class Incomplete(unittest.TestCase):
    def write(self, folder, name, **keys):
        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            json.dump(keys, f)

    def test_a_line_without_the_later_steps_is_listed(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(d, "line17.json", path=[1], heights={"a": 1}, platforms=[1], speed=[1])
            self.assertEqual(snapshot.incomplete_lines(d), {"line17.json": ["clearances"]})

    def test_a_full_line_and_a_sidecar_are_not(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(d, "line17.json", heights={"a": 1}, platforms=[1], speed=[1], clearances=[1])
            self.write(d, "line17.geo.json", path=[1])
            self.assertEqual(snapshot.incomplete_lines(d), {})


if __name__ == "__main__":
    unittest.main()
