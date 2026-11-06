"""fetch removes what the snapshot replaced, and nothing else (#332): python -I tools/test_snapshot_fetch.py"""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import snapshot  # noqa: E402

OLD, NOW = "2026-01-01", "2026-01-01b"  # (as the real ones: a letter sorts after the day alone)


class Store:
    def __init__(self, fails=False):
        self.fails = fails

    def download(self, kind, need, cache):
        if self.fails:
            raise SystemExit("the store did not answer")


class Fetch(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "snapshots").mkdir()
        for name, value in (("ROOT", self.root), ("SNAPDIR", self.root / "snapshots")):
            p = patch.object(snapshot, name, str(value))
            p.start()
            self.addCleanup(p.stop)

    def file(self, path, data=b"answer"):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return {"path": path, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    def snap(self, sid, *files):
        with open(self.root / "snapshots" / f"{sid}.json", "w", encoding="utf-8") as f:
            json.dump({"id": sid, "groups": [{"name": "any", "files": list(files)}]}, f)

    def fetch(self, sid=NOW, store=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            snapshot.fetch(store or Store(), sid)
        return out.getvalue()

    def there(self, path):
        return (self.root / path).exists()

    def test_what_an_older_snapshot_holds_goes(self):
        old = self.file("raw/geoportal/line9/walls_1_0.json")
        kept = self.file("raw/geoportal/cells/walls_a.json", b"cell")
        self.snap(OLD, old, kept)
        self.snap(NOW, kept)
        out = self.fetch()
        self.assertFalse(self.there(old["path"]))
        self.assertTrue(self.there(kept["path"]))
        self.assertIn("removed from raw/: 1 files", out)
        self.assertEqual(snapshot.raw_drift(NOW), ([], []))  # (data_publish no longer refuses on it)

    def test_a_staged_file_stays_and_still_counts(self):
        kept = self.file("raw/geoportal/cells/walls_a.json")
        self.file("raw/geoportal/cells/walls_new.json", b"staged")
        self.snap(OLD, kept)
        self.snap(NOW, kept)
        out = self.fetch()
        self.assertTrue(self.there("raw/geoportal/cells/walls_new.json"))
        self.assertNotIn("removed", out)
        self.assertEqual(snapshot.raw_drift(NOW), ([], ["raw/geoportal/cells/walls_new.json"]))

    def test_other_bytes_at_an_old_path_stay(self):
        old = self.file("raw/geoportal/line9/walls_1_0.json")
        self.snap(OLD, old)
        self.snap(NOW)
        self.file(old["path"], b"answered again")
        self.fetch()
        self.assertTrue(self.there(old["path"]))
        self.assertEqual(snapshot.raw_drift(NOW)[1], [old["path"]])

    def test_only_an_older_snapshot_counts(self):
        # (fetching an older snapshot on purpose leaves the newer one's files alone)
        newer = self.file("raw/geoportal/cells/walls_a.json")
        self.snap(OLD)
        self.snap(NOW, newer)
        self.fetch(OLD)
        self.assertTrue(self.there(newer["path"]))

    def test_an_old_package_goes_with_what_was_unzipped_from_it(self):
        old = self.file("raw/dtm/praha2_0930_ZPS.zip", b"zip")
        self.file("raw/dtm/praha2_0930_ZPS/ZPS_KR.gpkg", b"unzipped")
        now = self.file("raw/dtm/praha2_1031_ZPS.zip", b"zip now")
        self.file("raw/dtm/praha2_1031_ZPS/ZPS_KR.gpkg", b"unzipped now")
        self.snap(OLD, old)
        self.snap(NOW, now)
        self.fetch()
        self.assertFalse(self.there("raw/dtm/praha2_0930_ZPS"))
        self.assertFalse(self.there(old["path"]))
        self.assertTrue(self.there("raw/dtm/praha2_1031_ZPS/ZPS_KR.gpkg"))

    def test_a_failed_download_removes_nothing(self):
        old = self.file("raw/geoportal/line9/walls_1_0.json")
        self.snap(OLD, old)
        self.snap(NOW)
        with self.assertRaises(SystemExit):
            self.fetch(store=Store(fails=True))
        self.assertTrue(self.there(old["path"]))


if __name__ == "__main__":
    unittest.main()
