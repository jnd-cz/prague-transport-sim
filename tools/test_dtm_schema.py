"""Schema-migration checks: python -I tools/test_dtm_schema.py."""
import hashlib
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dtm_schema as schema


class Packages(unittest.TestCase):
    def gpkg(self, folder, name='old.gpkg', field='UrovenUmisteniObjektuZPS', crs=5514, z=0,
             table='Dopravni#010000000503_Surface'):
        path = Path(folder) / name
        with closing(sqlite3.connect(path)) as db:
            db.executescript('''
                create table gpkg_contents(table_name text,data_type text,srs_id integer);
                create table gpkg_geometry_columns(table_name text,column_name text,
                    geometry_type_name text,srs_id integer,z integer,m integer);
                create table gpkg_spatial_ref_sys(srs_name text,srs_id integer,organization text,
                    organization_coordsys_id integer,definition text,description text,definition_12_063 text);
            ''')
            db.execute('insert into gpkg_contents values(?,?,?)', (table, 'features', crs))
            db.execute('insert into gpkg_geometry_columns values(?,?,?,?,?,?)',
                       (table, 'shape', 'POLYGON', crs, z, 0))
            db.execute('insert into gpkg_spatial_ref_sys values(?,?,?,?,?,?,?)',
                       ('test CRS', crs, 'EPSG', crs, 'WKT', '', 'optional extension'))
            db.execute(f'create table {schema.ident(table)}(id integer primary key, shape blob, {schema.ident(field)} integer)')
            db.commit()
        return path

    def test_zip_and_extracted_schema_match_without_source_modification(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.gpkg(folder, name='ZPS_OPL.gpkg')
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            archive = Path(folder) / 'package.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.write(source, source.name)
            zipped, unpacked = schema.inspect(archive), schema.inspect(source)
            self.assertEqual(schema.differences(schema.schema_only(zipped), schema.schema_only(unpacked)), [])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
            layer = next(iter(zipped['components']['gpkg:ZPS_OPL.gpkg']['layers'].values()))
            self.assertEqual(layer['type_code'], '010000000503')

    def test_detects_attribute_crs_dimension_and_type_code_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            old = schema.gpkg_schema(self.gpkg(folder))
            new = schema.gpkg_schema(self.gpkg(folder, name='new.gpkg', field='Level', crs=4326, z=1,
                                               table='Dopravni#010000000703_Surface'))
            changes = schema.differences(old, new)
            text = str(changes)
            for expected in ('5514', '4326', '010000000503', '010000000703', 'Level'):
                self.assertIn(expected, text)

    def test_renamed_attribute_is_not_hidden_by_layer_order(self):
        with tempfile.TemporaryDirectory() as folder:
            old = schema.gpkg_schema(self.gpkg(folder))
            new = schema.gpkg_schema(self.gpkg(folder, name='new.gpkg', field='Level'))
            changes = schema.differences(old, new)
            self.assertEqual({c['change'] for c in changes}, {'added', 'removed'})
            self.assertTrue(any(c['path'].endswith('/UrovenUmisteniObjektuZPS') for c in changes))

    def test_same_layer_crs_and_z_changes_are_reported_exactly(self):
        with tempfile.TemporaryDirectory() as folder:
            old = schema.gpkg_schema(self.gpkg(folder))
            new = schema.gpkg_schema(self.gpkg(folder, name='new.gpkg', crs=4326, z=1))
            paths = [d['path'] for d in schema.differences(old, new)]
            self.assertTrue(any(p.endswith('/geometry/shape/srs_id') for p in paths))
            self.assertTrue(any(p.endswith('/geometry/shape/z') for p in paths))

    def test_jvf_dates_do_not_mask_or_invent_a_version_change(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'package.xml'
            def write(version, date):
                path.write_text(f'<JVF><VerzeJVFDTM>{version}</VerzeJVFDTM><DatumZapisu>{date}</DatumZapisu></JVF>')
                return schema.schema_only(schema.inspect(path))
            old = write('1.4.3', '2026-10-01')
            self.assertEqual(schema.differences(old, write('1.4.3', '2026-11-01')), [])
            changes = schema.differences(old, write('1.5.0.2', '2026-12-01'))
            self.assertEqual(len(changes), 1)
            self.assertTrue(changes[0]['path'].endswith('/jvf_versions'))

    def test_invalid_input_never_creates_a_missing_database(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder) / 'missing.gpkg'
            with self.assertRaises(sqlite3.OperationalError):
                schema.inspect(missing)
            self.assertFalse(missing.exists())
            archive = Path(folder) / 'empty.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('readme.txt', 'no schema')
            with self.assertRaisesRegex(ValueError, 'no GPKG'):
                schema.inspect(archive)


if __name__ == '__main__':
    unittest.main()
