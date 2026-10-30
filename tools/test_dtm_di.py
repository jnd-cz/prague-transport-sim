"""Check the DI report's units, missing heights and layer separation.

    python -P -E tools/test_dtm_di.py
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dtm_di
import snapshot


def record(coords, incomplete='true', crs='EPSG:5514'):
    return f'''<r:ZaznamObjektu><atr:NeuplnaData>{incomplete}</atr:NeuplnaData>
        <atr:TridaPresnostiPoloha>3</atr:TridaPresnostiPoloha>
        <gml:LineString srsName="{crs}" srsDimension="3"><gml:posList>{coords}</gml:posList>
        </gml:LineString></r:ZaznamObjektu>'''


class Report(unittest.TestCase):
    def package(self, folder, tracks, axes=''):
        path = Path(folder) / 'DI.jvf.zip'
        xml = f'''<obj:JVFDTM xmlns:obj="objtyp" xmlns:r="track" xmlns:atr="atr"
            xmlns:cmn="cmn" xmlns:di="dopinf" xmlns:gml="http://www.opengis.net/gml/3.2">
            <cmn:VerzeJVFDTM>1.4.3</cmn:VerzeJVFDTM><di:TypDatoveSady>7</di:TypDatoveSady>
            <di:DatumPlatnosti>2026-09-30T00:00:00</di:DatumPlatnosti>
            <obj:OsaKolejeTramvajoveDrahy>{tracks}</obj:OsaKolejeTramvajoveDrahy>
            <obj:OsaTramvajoveDrahy>{axes}</obj:OsaTramvajoveDrahy></obj:JVFDTM>'''
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('DI.jvf.xml', xml)
        return path

    def test_features_not_vertices_and_distinct_track_and_alignment_layers(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.package(folder, record('1 2 0 3 4 0') + record('1 2 200 3 4 201', 'false')
                                + record('1 2 0 3 4 210'), record('1 2 999 3 4 999'))
            report = dtm_di.package_report(path)
        tracks = report['layers']['OsaKolejeTramvajoveDrahy']
        self.assertEqual(tracks['features'], 3)
        self.assertEqual(tracks['z'], {'zero': 1, 'numeric': 1, 'mixed': 1})
        self.assertEqual(tracks['flags']['NeuplnaData'], {'true': 2, 'false': 1})
        self.assertEqual(report['layers']['OsaTramvajoveDrahy']['features'], 1)

    def test_unknown_height_does_not_become_numeric(self):
        for values in ([], [float('nan')], [float('inf'), 0]):
            self.assertEqual(dtm_di.classify_z(values), 'missing_or_nonfinite')
        with tempfile.TemporaryDirectory() as folder:
            report = dtm_di.package_report(self.package(folder, '<r:ZaznamObjektu/>'))
        tracks = report['layers']['OsaKolejeTramvajoveDrahy']
        self.assertEqual(tracks['z'], {'missing_or_nonfinite': 1})
        self.assertEqual(tracks['flags']['NeuplnaData'], {'missing': 1})

    def test_rejects_unexpected_crs_and_empty_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'EPSG:5514'):
                dtm_di.package_report(self.package(folder, record('1 2 3', crs='EPSG:4326')))
            with self.assertRaisesRegex(ValueError, 'schema'):
                dtm_di.package_report(self.package(folder, ''))

    def test_snapshot_keeps_zips_and_provenance_without_unpacking(self):
        with tempfile.TemporaryDirectory() as folder:
            raw = Path(folder) / 'raw' / 'dtm-di'
            raw.mkdir(parents=True)
            (raw / 'example.jvf.zip').write_bytes(b'package')
            (raw / 'provenance.json').write_text(json.dumps({'packages': []}))
            (raw / 'terms.pdf').write_bytes(b'terms')
            (raw / 'access.html').write_text('access')
            with patch.object(snapshot, 'ROOT', folder):
                group = next(g for g in snapshot.scan_sources() if g['name'] == 'dtm-di')
            self.assertEqual(len(group['files']), 4)
            self.assertFalse(group['unzip'])
            self.assertTrue(all(len(f['sha256']) == 64 for f in group['files']))


if __name__ == '__main__':
    unittest.main()
