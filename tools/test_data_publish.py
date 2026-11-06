"""Test manifest replacement without contacting the store: python -I tools/test_data_publish.py."""
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
from atomic import replacing  # noqa: E402
import snapshot  # noqa: E402


LINE = json.dumps({k: [1] for k in snapshot.LINE_STEPS})   # (a full build: data_publish refuses less)


class Store:
    def listing(self, kind):
        return set()

    def upload(self, kind, files):
        self.files = files


class Publish(unittest.TestCase):
    def test_manifest_replacement_preserves_hard_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / 'data'
            data.mkdir()
            with replacing(data / 'line9.json', 'w', encoding='utf-8') as f:
                f.write(LINE)
            original = root / 'original.json'
            original.write_text('old manifest', encoding='utf-8')
            manifest = data / 'MANIFEST.json'
            os.link(original, manifest)
            store = Store()
            with patch.object(snapshot, 'ROOT', str(root)), patch.object(snapshot, 'DATA_MANIFEST', str(manifest)), \
                    patch.object(snapshot.subprocess, 'run', return_value=types.SimpleNamespace(stdout='abc123\n')), \
                    patch.object(snapshot, 'raw_drift', return_value=([], [])), \
                    contextlib.redirect_stdout(io.StringIO()):
                snapshot.data_publish(store, 'test', sid='snapshot')
            self.assertEqual(original.read_text(encoding='utf-8'), 'old manifest')
            result = json.loads(manifest.read_text(encoding='utf-8'))
            self.assertEqual(result['snapshot'], 'snapshot')
            self.assertEqual(result['built_at_commit'], 'abc123')
            self.assertEqual(result['files']['line9.json']['size'], len(LINE))
            self.assertEqual(len(store.files), 1)


    def publish_with_drift(self, drift, **kw):
        """data_publish in a temporary checkout whose raw/ differs from the snapshot by `drift`."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            (root / 'data' / 'line9.json').write_text(LINE, encoding='utf-8')
            manifest = root / 'data' / 'MANIFEST.json'
            store = Store()
            with patch.object(snapshot, 'ROOT', str(root)), patch.object(snapshot, 'DATA_MANIFEST', str(manifest)), \
                    patch.object(snapshot.subprocess, 'run', return_value=types.SimpleNamespace(stdout='abc123\n')), \
                    patch.object(snapshot, 'raw_drift', return_value=drift), \
                    contextlib.redirect_stdout(io.StringIO()):
                snapshot.data_publish(store, 'line 9', sid='snapshot', **kw)
            return json.loads(manifest.read_text(encoding='utf-8')), store

    def test_a_build_from_files_outside_the_snapshot_is_refused(self):
        # (#223: a cache miss had downloaded tiles that were in no snapshot)
        for drift in (([('changed', 'raw/dem/1_2.tif')], []), ([], ['raw/dem/3_4.tif'])):
            with self.assertRaises(SystemExit) as e:
                self.publish_with_drift(drift)
            self.assertIn('raw/dem/', str(e.exception))
            self.assertIn('--allow-drift', str(e.exception))

    def test_drift_allowed_on_purpose_is_written_into_the_note(self):
        man, store = self.publish_with_drift(([], ['raw/dem/3_4.tif']), allow_drift=True)
        self.assertEqual(man['note'], 'line 9 [raw/ differs from snapshot snapshot: 1 files]')
        self.assertEqual(len(store.files), 1)

    def test_snapshot_files_missing_here_do_not_block(self):
        # (a checkout that rebuilt one line need not hold the other lines' inputs)
        man, _ = self.publish_with_drift(([('missing', 'raw/line22/x.json')], []))
        self.assertEqual(man['note'], 'line 9')


if __name__ == '__main__':
    unittest.main()
