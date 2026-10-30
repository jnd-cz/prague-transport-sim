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
                f.write('new data')
            original = root / 'original.json'
            original.write_text('old manifest', encoding='utf-8')
            manifest = data / 'MANIFEST.json'
            os.link(original, manifest)
            store = Store()
            with patch.object(snapshot, 'ROOT', str(root)), patch.object(snapshot, 'DATA_MANIFEST', str(manifest)), \
                    patch.object(snapshot.subprocess, 'run', return_value=types.SimpleNamespace(stdout='abc123\n')), \
                    contextlib.redirect_stdout(io.StringIO()):
                snapshot.data_publish(store, 'test', sid='snapshot')
            self.assertEqual(original.read_text(encoding='utf-8'), 'old manifest')
            result = json.loads(manifest.read_text(encoding='utf-8'))
            self.assertEqual(result['snapshot'], 'snapshot')
            self.assertEqual(result['built_at_commit'], 'abc123')
            self.assertEqual(result['files']['line9.json']['size'], len('new data'))
            self.assertEqual(len(store.files), 1)


if __name__ == '__main__':
    unittest.main()
