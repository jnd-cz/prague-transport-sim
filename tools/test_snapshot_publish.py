"""A snapshot's id is a date (and a letter), and --help is help: python -I tools/test_snapshot_publish.py (#424)"""
import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import snapshot  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class NoStore:
    """A store that fails the test if publish reaches it."""

    def __getattr__(self, name):
        raise AssertionError(f"publish reached the store ({name}) with a bad id")


class Publish(unittest.TestCase):
    def test_dates_are_ids(self):
        for sid in ("2026-11-09", "2026-11-09r", "2026-10-30"):
            self.assertTrue(snapshot.SNAPSHOT_ID.fullmatch(sid), sid)

    def test_other_words_are_refused_before_the_store(self):
        for sid in ("--help", "-h", "latest", "2026-11-9", "2026-11-09rr", "2026-11-09 "):
            with self.assertRaises(SystemExit, msg=sid) as e:
                snapshot.publish(NoStore(), sid, "")
            self.assertIn("snapshot id", str(e.exception))

    def test_help_writes_nothing(self):
        before = sorted(os.listdir(ROOT / "snapshots"))
        current = (ROOT / "snapshots" / "CURRENT").read_bytes()
        for args in (["publish", "--help"], ["fetch", "-h"], ["--help"]):
            r = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "snapshot.py"), *args], capture_output=True, text=True,
                               timeout=60, env={**os.environ, "TRAMDATA_STORE": "nowhere:none"})
            self.assertEqual(r.returncode, 0, args)
            self.assertIn("Usage", r.stdout, args)
        self.assertEqual(sorted(os.listdir(ROOT / "snapshots")), before)
        self.assertEqual((ROOT / "snapshots" / "CURRENT").read_bytes(), current)


if __name__ == "__main__":
    unittest.main()
