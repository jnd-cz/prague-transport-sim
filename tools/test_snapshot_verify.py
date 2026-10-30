"""Test which files verify downloads, without the store: python -I tools/test_snapshot_verify.py."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import snapshot  # noqa: E402


class Store:
    def __init__(self, have):
        self.have, self.got = have, {}

    def listing(self, kind):
        return set(self.have.get(kind, ()))

    def download(self, kind, items, cache=None):
        self.got[kind] = sorted(h for h, _ in items)


def snap(sid, hashes):
    return {"id": sid, "groups": [{"files": [{"path": f"raw/{h}", "size": 1, "sha256": h} for h in hashes]}]}


class Verify(unittest.TestCase):
    def run_verify(self, store, base_manifest):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "snapshots").mkdir()
            (root / "data").mkdir()
            for s in (snap("a", ["s1", "s2"]), snap("b", ["s1", "s2", "s3"])):
                (root / "snapshots" / f"{s['id']}.json").write_text(json.dumps(s), encoding="utf-8")
            manifest = root / "data" / "MANIFEST.json"
            manifest.write_text(json.dumps({"files": {"x": {"sha256": "b1", "size": 1}, "y": {"sha256": "b2", "size": 1}}}), encoding="utf-8")
            git = types.SimpleNamespace(returncode=0, stdout=json.dumps(base_manifest))
            with patch.object(snapshot, "ROOT", str(root)), patch.object(snapshot, "SNAPDIR", str(root / "snapshots")), \
                    patch.object(snapshot, "DATA_MANIFEST", str(manifest)), \
                    patch.object(snapshot.subprocess, "run", return_value=git), \
                    contextlib.redirect_stdout(io.StringIO()):
                snapshot.verify(store, "b")

    def test_downloads_only_new_files(self):
        store = Store({"sources": ["s1", "s2", "s3"], "builds": ["b1", "b2"]})
        self.run_verify(store, {"files": {"x": {"sha256": "b1"}}})
        self.assertEqual(store.got, {"sources": ["s3"], "builds": ["b2"]})

    def test_missing_in_store_fails(self):
        store = Store({"sources": ["s2", "s3"], "builds": ["b1", "b2"]})
        with self.assertRaises(SystemExit):
            self.run_verify(store, {"files": {"x": {"sha256": "b1"}, "y": {"sha256": "b2"}}})
        self.assertEqual(store.got, {"sources": ["s3"]})


if __name__ == "__main__":
    unittest.main()
