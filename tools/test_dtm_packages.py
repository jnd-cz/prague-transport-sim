# SPDX-License-Identifier: AGPL-3.0-or-later
"""ZPS month selection and reader integration: python -P -E tools/test_dtm_packages.py."""
import array
import base64
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dtm_packages as packages
import rebuild
from geo import ORIGIN


DISTRICT = '500089'
OLD, NEW = '20260930', '20261031'


def package(root, date, kind, folder=True, district=DISTRICT):
    p = root / 'raw/dtm' / f'VS_CZ010_MOMC_{district}_{date}_ZPS_{kind}.gpkg'
    p.parent.mkdir(parents=True, exist_ok=True)
    if folder:
        p.mkdir(exist_ok=True)
        p /= f'ZPS_{kind}.gpkg'
    return p


def pin(root, dates):
    folder = root / 'snapshots'
    folder.mkdir(exist_ok=True)
    (folder / 'CURRENT').write_text('test\n', encoding='utf-8')
    files = [{'path': f'raw/dtm/VS_CZ010_MOMC_{d}_{date}_ZPS_{kind}.gpkg.zip'}
             for d, date in dates for kind in ('OPL', 'KR')]
    (folder / 'test.json').write_text(json.dumps({'groups': [{'name': 'dtm', 'files': files}]}), encoding='utf-8')


class Selection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for date in (OLD, NEW):
            for kind in ('OPL', 'KR'):
                package(self.root, date, kind).touch()

    def test_snapshot_wins_and_explicit_sources_deduplicate_by_district(self):
        pin(self.root, [(DISTRICT, OLD)])
        sources = list((self.root / 'raw/dtm').iterdir()) * 2
        selected = packages.select_packages(self.root, sources=sources)
        self.assertEqual([(p.district, p.date) for p in selected], [(DISTRICT, OLD)])
        self.assertTrue(all(OLD in str(selected[0].path(k)) for k in ('OPL', 'KR')))

    def test_stale_source_does_not_override_new_snapshot(self):
        pin(self.root, [(DISTRICT, NEW)])
        old = package(self.root, OLD, 'OPL').parent
        self.assertEqual(packages.select_packages(self.root, sources=[old])[0].date, NEW)

    def test_unpinned_newest_month_warns_without_mixing_dates(self):
        for snapshot in (False, True):
            with self.subTest(snapshot=snapshot):
                if snapshot:
                    pin(self.root, [])
                with self.assertLogs('dtm_packages', level='WARNING') as log:
                    selected = packages.select_packages(self.root, districts=[DISTRICT])
                self.assertEqual(selected[0].date, NEW)
                self.assertIn(NEW, log.output[0])
                self.assertIn(OLD, log.output[0])

    def test_missing_halves_cannot_be_paired_across_months(self):
        pin(self.root, [(DISTRICT, OLD)])
        package(self.root, OLD, 'OPL').unlink()
        package(self.root, NEW, 'KR').unlink()
        with self.assertRaisesRegex(FileNotFoundError, f'{NEW}.*ZPS_KR'):
            packages.select_packages(self.root, districts=[DISTRICT])

    def test_refresh_uses_newest_pair_when_snapshot_files_are_removed(self):
        pin(self.root, [(DISTRICT, OLD)])
        for kind in ('OPL', 'KR'):
            package(self.root, OLD, kind).unlink()
        with self.assertLogs('dtm_packages', level='WARNING') as log:
            selected = packages.select_packages(self.root, districts=[DISTRICT])
        self.assertEqual(selected[0].date, NEW)
        self.assertTrue(all(NEW in str(selected[0].path(k)) for k in ('OPL', 'KR')))
        for text in ('snapshot test', OLD, NEW, 'publish'):
            self.assertIn(text, log.output[0])

    def test_refresh_replaces_an_incomplete_pinned_pair_with_a_complete_newer_pair(self):
        pin(self.root, [(DISTRICT, OLD)])
        package(self.root, OLD, 'KR').unlink()
        with self.assertLogs('dtm_packages', level='WARNING'):
            selected = packages.select_packages(self.root, districts=[DISTRICT])
        self.assertTrue(all(NEW in str(selected[0].path(k)) for k in ('OPL', 'KR')))

    def test_missing_snapshot_files_cannot_roll_back_to_an_older_month(self):
        pin(self.root, [(DISTRICT, NEW)])
        for kind in ('OPL', 'KR'):
            package(self.root, NEW, kind).unlink()
        with self.assertRaisesRegex(FileNotFoundError, f'{NEW}.*ZPS_OPL'):
            packages.select_packages(self.root, districts=[DISTRICT])

    def test_each_district_has_its_own_pinned_date(self):
        other = '500054'
        for kind in ('OPL', 'KR'):
            package(self.root, NEW, kind, district=other).touch()
        pin(self.root, [(DISTRICT, OLD), (other, NEW)])
        self.assertEqual([(p.district, p.date) for p in packages.select_packages(self.root)],
                         [(other, NEW), (DISTRICT, OLD)])

    def test_fallback_cannot_pair_new_opl_with_old_kr(self):
        package(self.root, NEW, 'KR').unlink()
        with self.assertLogs('dtm_packages', level='WARNING'):
            with self.assertRaisesRegex(FileNotFoundError, f'{NEW}.*ZPS_KR'):
                packages.select_packages(self.root, districts=[DISTRICT])

    def test_conflicting_snapshot_dates_and_broken_manifest_fail(self):
        pin(self.root, [(DISTRICT, OLD), (DISTRICT, NEW)])
        with self.assertRaisesRegex(ValueError, 'several months'):
            packages.select_packages(self.root)
        (self.root / 'snapshots/test.json').unlink()
        with self.assertRaises(FileNotFoundError):
            packages.select_packages(self.root)

    def test_plain_files_zip_names_and_district_filter(self):
        other = '500054'
        for kind in ('OPL', 'KR'):
            package(self.root, OLD, kind, folder=False, district=other).touch()
        (self.root / 'raw/dtm' / f'VS_CZ010_MOMC_{other}_{NEW}_ZPS_OPL.gpkg.zip').touch()
        pin(self.root, [(other, OLD)])
        selected = packages.select_packages(self.root, districts=[other])
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].date, OLD)
        self.assertEqual(selected[0].opl.name, f'VS_CZ010_MOMC_{other}_{OLD}_ZPS_OPL.gpkg')

    def test_rebuild_uses_one_pinned_month_and_shared_district_list(self):
        pin(self.root, [(DISTRICT, OLD)])
        with patch.object(rebuild, 'ROOT', str(self.root)), patch.dict(packages.DTM, {'17': [DISTRICT]}):
            _, groups = rebuild.steps('17')
        args = next(group[0] for group in groups if group[0][0] == 'dtm.py')
        self.assertEqual(len(args), 4)
        self.assertIn(OLD, args[-1])


def gpkg(path, kind, count, z):
    table = 'Dopravni#010000000503_Test' if kind == 'OPL' else 'Hranice_dopravní_stavby_nebo_plochy#010000000503_Test'
    with closing(sqlite3.connect(path)) as db:
        db.executescript('''create table gpkg_contents(table_name text,data_type text);
            create table gpkg_geometry_columns(table_name text,column_name text,geometry_type_name text,z integer);''')
        db.execute('insert into gpkg_contents values(?,?)', (table, 'features'))
        db.execute('insert into gpkg_geometry_columns values(?,?,?,?)',
                   (table, 'shape', 'POLYGON' if kind == 'OPL' else 'LINESTRING', int(kind == 'KR')))
        db.execute(f'create table "{table}" (id integer, shape blob, UrovenUmisteniObjektuZPS integer)')
        for i in range(count):
            e, n = ORIGIN
            pts = [(e+x+i*10, n+y) for x, y in [(0,0),(5,0),(5,5),(0,5),(0,0)]]
            if kind == 'OPL':
                wkb = struct.pack('<BIII', 1, 3, 1, len(pts)) + b''.join(struct.pack('<dd', *p) for p in pts)
            else:
                wkb = struct.pack('<BII', 1, 1002, len(pts)) + b''.join(struct.pack('<ddd', *p, z) for p in pts)
            blob = b'GP\x00\x01' + struct.pack('<i', 5514) + wkb
            db.execute(f'insert into "{table}" values(?,?,0)', (i, blob))
        db.commit()


class Readers(unittest.TestCase):
    def test_an_area_listed_twice_is_one_area(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = root / 'tools'
            tools.mkdir()
            for name in ('dtm.py','registration.py','dtm_packages.py','gpkg.py','geo.py','atomic.py','sources.py','kerbs.py',
                         'zps_ground.py','survey_ground_answers.py','dmr5g.py','zps_decks.py','mosty3d.py','zps_inside.py','zps_outline.py'):
                shutil.copyfile(Path(__file__).parent / name, tools / name)
            (tools / 'ipr_dtm.py').write_text('import numpy as np\n\n\nclass IprDtm:\n'
                                              '    def sample(self, E, N):\n        return np.full(np.shape(E), 200.0)\n',
                                              encoding='utf-8')
            (root / 'data').mkdir()
            line = {'path': [[0,0],[20,0]], 'terrain': {'data': base64.b64encode(array.array('h',[0]*4)).decode(),
                    'base':200,'scale':1,'x0':-10,'y0':-10,'dx':40,'dy':40,'nx':2,'ny':2}}
            (root / 'data/line17.json').write_text(json.dumps(line), encoding='utf-8')
            for kind in ('OPL','KR'):
                gpkg(package(root,OLD,kind), kind, 1, 200)
            pin(root, [(DISTRICT,OLD)])
            with closing(sqlite3.connect(package(root,OLD,'OPL'))) as db:  # (the same outline again, as a border area is)
                db.execute('insert into "Dopravni#010000000503_Test" select id+1, shape, UrovenUmisteniObjektuZPS from "Dopravni#010000000503_Test"')
                db.commit()
            sources = [str(p) for p in (root / 'raw/dtm').iterdir()]
            r = subprocess.run([sys.executable,'-P','-E','tools/dtm.py','--line','17',*sources],
                               cwd=root,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(len(json.loads((root / 'data/line17.dtm.json').read_text(encoding='utf-8'))['areas']),1)
            self.assertIn('1 copies of an area',r.stdout)

    def test_two_months_both_readers_take_only_snapshot_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = root / 'tools'
            tools.mkdir()
            for name in ('dtm.py','registration.py','dtm_packages.py','gpkg.py','geo.py','atomic.py','sources.py','kerbs.py',
                         'zps_ground.py','survey_ground_answers.py','dmr5g.py','zps_decks.py','mosty3d.py','zps_inside.py','zps_outline.py'):
                shutil.copyfile(Path(__file__).parent / name, tools / name)
            # (the IPR terrain is a 2 GB raster: a flat stand-in at the test's 200 m)
            (tools / 'ipr_dtm.py').write_text('import numpy as np\n\n\nclass IprDtm:\n'
                                              '    def sample(self, E, N):\n        return np.full(np.shape(E), 200.0)\n',
                                              encoding='utf-8')
            (root / 'data').mkdir()
            line = {'path': [[0,0],[20,0]], 'terrain': {'data': base64.b64encode(array.array('h',[0]*4)).decode(),
                    'base':200,'scale':1,'x0':-10,'y0':-10,'dx':40,'dy':40,'nx':2,'ny':2}}
            (root / 'data/line17.json').write_text(json.dumps(line), encoding='utf-8')
            for date, count, z in [(OLD,1,200), (NEW,2,201)]:
                for kind in ('OPL','KR'):
                    gpkg(package(root,date,kind), kind, count, z)
            pin(root, [(DISTRICT,OLD)])
            # The real registration survey() must not read 1 + 2 features from both dates.
            script = ("import runpy; d=runpy.run_path('tools/registration.py'); "
                      "d['DTM']['17']=['500089']; "
                      "print('features',len(d['survey']('OPL','010000000503')),len(d['survey']('KR','010000000503')))")
            r = subprocess.run([sys.executable,'-P','-E','-c',script], cwd=root, capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertIn('features 1 1',r.stdout)
            # The real importer must keep both area and height inputs on the pinned date.
            sources = [str(p) for p in (root / 'raw/dtm').iterdir()]
            r = subprocess.run([sys.executable,'-P','-E','tools/dtm.py','--line','17',*sources],
                               cwd=root,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(r.returncode,0,r.stderr)
            result = json.loads((root / 'data/line17.dtm.json').read_text(encoding='utf-8'))
            self.assertEqual(len(result['areas']),1)
            # (the outline heights from the pinned month only; the height cloud `z` is gone since #128)
            self.assertEqual({p[2] for p in result['areas'][0]['r']},{200})
            self.assertIn(OLD,r.stdout)
            self.assertNotIn(NEW,r.stdout)
            # Refresh rebuild/check comes before publish: CURRENT still names OLD, but its files
            # have been replaced. Both real readers must now use NEW, with the same warning.
            for kind in ('OPL', 'KR'):
                package(root,OLD,kind).unlink()
            r = subprocess.run([sys.executable,'-P','-E','-c',script], cwd=root,capture_output=True,
                               text=True,encoding='utf-8')
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertIn('features 2 2',r.stdout)
            for text in ('snapshot test',OLD,NEW,'publish'):
                self.assertIn(text,r.stderr)
            r = subprocess.run([sys.executable,'-P','-E','tools/dtm.py','--line','17',*sources],
                               cwd=root,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(r.returncode,0,r.stderr)
            for text in ('snapshot test',OLD,NEW,'publish'):
                self.assertIn(text,r.stderr)
            result = json.loads((root / 'data/line17.dtm.json').read_text(encoding='utf-8'))
            self.assertEqual(len(result['areas']),2)
            self.assertEqual({p[2] for a in result['areas'] for p in a['r']},{201})
            with patch.object(rebuild, 'ROOT', str(root)), patch.dict(packages.DTM, {'17':[DISTRICT]}):
                with self.assertLogs('dtm_packages',level='WARNING'):
                    _, groups = rebuild.steps('17')
            args = next(g[0] for g in groups if g[0][0]=='dtm.py')
            self.assertEqual(len(args),4)
            self.assertIn(NEW,args[-1])


def zipped(kind):
    import io
    import zipfile
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        z.writestr(f'ZPS_{kind}.gpkg', f'{kind} survey')
    return b.getvalue()


class Fetch(unittest.TestCase):
    """--fetch --refresh: the index's newer month replaces the older pair in raw/dtm/ (#63)."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / 'raw/dtm'
        self.folder.mkdir(parents=True)
        prov = {'packages': {}}
        for kind in ('OPL', 'KR'):
            self.local(OLD, kind)
            prov['packages'][f'VS_CZ010_MOMC_{DISTRICT}_{OLD}_ZPS_{kind}.gpkg.zip'] = {'state': OLD}
        (self.folder / 'provenance.json').write_text(json.dumps(prov), encoding='utf-8')
        patcher = patch.object(packages, 'DTM', {'17': [DISTRICT]})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.downloads = []

    def local(self, date, kind):
        name = f'VS_CZ010_MOMC_{DISTRICT}_{date}_ZPS_{kind}.gpkg'
        (self.folder / f'{name}.zip').write_bytes(zipped(kind))
        package(self.root, date, kind).write_text('unzipped', encoding='utf-8')

    def opener(self, months):
        """An index listing months[kind] for the district, and its downloads."""
        import io
        def entry(kind, date):
            name = f'VS_CZ010_MOMC_{DISTRICT}_{date}_ZPS_{kind}.gpkg.zip'
            return {'obec_kod': DISTRICT, 'format': 'GPKG', 'platnost': f'{date[:4]}-{date[4:6]}-{date[6:]}T00:00',
                    'soubor_nazev': name, 'kod_stazeni': f'uuid/{name}', 'velikost': len(zipped(kind))}
        def open_(url, timeout=None):
            if 'get-dtm-download-metadata' in url:
                kind = 'OPL' if url.endswith('02') else 'KR'
                return io.BytesIO(json.dumps([{'formats': [entry(kind, d) for d in months[kind]]}]).encode())
            self.downloads.append(url.rsplit('/', 1)[1])
            return io.BytesIO(zipped('OPL' if '_OPL' in url else 'KR'))
        return open_

    def names(self):
        return sorted(p.name for p in self.folder.iterdir() if p.name != 'provenance.json')

    def provenance(self):
        return sorted(json.loads((self.folder / 'provenance.json').read_text(encoding='utf-8'))['packages'])

    def fetch(self, months, refresh):
        with patch('builtins.print'):
            packages.fetch(self.root, refresh=refresh, opener=self.opener(months))

    def test_without_refresh_a_complete_older_pair_stays(self):
        self.fetch({'OPL': [OLD, NEW], 'KR': [OLD, NEW]}, refresh=False)
        self.assertEqual(self.downloads, [])
        self.assertTrue(all(OLD in n for n in self.names()))

    def test_refresh_replaces_the_older_pair_with_the_newer(self):
        self.fetch({'OPL': [OLD, NEW], 'KR': [OLD, NEW]}, refresh=True)
        self.assertEqual(sorted(self.downloads), [f'VS_CZ010_MOMC_{DISTRICT}_{NEW}_ZPS_{k}.gpkg.zip' for k in ('KR', 'OPL')])
        self.assertEqual(self.names(), [f'VS_CZ010_MOMC_{DISTRICT}_{NEW}_ZPS_{k}.gpkg.zip' for k in ('KR', 'OPL')])
        self.assertEqual(self.provenance(), self.names())  # (snapshot.py fetch unzips them after the publish)

    def test_an_incomplete_newer_pair_leaves_the_older_one(self):
        self.fetch({'OPL': [OLD, NEW], 'KR': [OLD]}, refresh=True)
        self.assertEqual(self.downloads, [f'VS_CZ010_MOMC_{DISTRICT}_{NEW}_ZPS_OPL.gpkg.zip'])
        self.assertIn(f'VS_CZ010_MOMC_{DISTRICT}_{OLD}_ZPS_OPL.gpkg.zip', self.names())
        self.assertIn(f'VS_CZ010_MOMC_{DISTRICT}_{OLD}_ZPS_KR.gpkg.zip', self.names())

    def test_a_run_the_server_stops_keeps_what_it_fetched_and_a_rerun_records_it(self):
        import urllib.error
        months = {'OPL': [OLD, NEW], 'KR': [OLD, NEW]}
        good = self.opener(months)

        def refusing(url, timeout=None):  # (the server refused the 28th of 34 downloads, 2026-11-05)
            if '_KR' in url and 'get-dtm' not in url:
                raise urllib.error.URLError('refused')
            return good(url, timeout)
        with patch('builtins.print'), self.assertRaises(urllib.error.URLError):
            packages.fetch(self.root, refresh=True, opener=refusing)
        new_opl = f'VS_CZ010_MOMC_{DISTRICT}_{NEW}_ZPS_OPL.gpkg.zip'
        self.assertIn(new_opl, self.provenance())
        self.downloads.clear()
        (self.folder / 'provenance.json').write_text(json.dumps({'packages': {}}), encoding='utf-8')  # (as the old code left it)
        self.fetch(months, refresh=True)
        self.assertEqual(self.downloads, [f'VS_CZ010_MOMC_{DISTRICT}_{NEW}_ZPS_KR.gpkg.zip'])
        self.assertEqual(self.provenance(), self.names())

    def test_refresh_never_goes_back_to_an_older_month(self):
        for kind in ('OPL', 'KR'):
            self.local(NEW, kind)
        self.fetch({'OPL': [OLD], 'KR': [OLD]}, refresh=True)
        self.assertEqual(self.downloads, [])
        self.assertEqual(len(self.names()), 8)  # (both months' ZIPs and unzipped packages stay)


if __name__ == '__main__':
    unittest.main(verbosity=2)
