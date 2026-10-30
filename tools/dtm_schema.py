"""Inspect and compare DTM download schemas without changing the sources (#63).

    python -I tools/dtm_schema.py raw/dtm/*500089*.gpkg.zip
    python -I tools/dtm_schema.py OLD.gpkg.zip NEW.gpkg.zip --compare
    python -I tools/dtm_schema.py PACKAGE.jvf.zip --output reports/jvf-schema.json

Inputs: GPKG, XML, ZIPs containing either, or their extracted directories. --compare requires two
inputs and exits 1 for schema differences (2 for invalid input). Data dates and source hashes are
reported but not treated as schema changes. GPKG format version is not a JVF exchange version.
"""
import argparse
from contextlib import closing
import glob
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def ident(name):
    return '"' + name.replace('"', '""') + '"'


def gpkg_schema(path):
    # A missing or unsupported package must fail, never create a new empty SQLite file.
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('pragma query_only=on')
        tables = {r[0] for r in db.execute("select name from sqlite_master where type='table'")}
        if not {'gpkg_contents', 'gpkg_geometry_columns', 'gpkg_spatial_ref_sys'} <= tables:
            raise ValueError(f'{path}: missing required GeoPackage metadata tables')
        geometry = {}
        used_crs = set()
        for table, column, kind, srs, z, m in db.execute(
                'select table_name,column_name,geometry_type_name,srs_id,z,m from gpkg_geometry_columns'):
            geometry.setdefault(table, {})[column] = {'type': kind, 'srs_id': srs, 'z': z, 'm': m}
            used_crs.add(srs)
        layers = {}
        for table, data_type, srs in db.execute('select table_name,data_type,srs_id from gpkg_contents order by table_name'):
            if data_type != 'features':
                continue
            if table not in geometry:
                raise ValueError(f'{path}: feature table {table} has no geometry metadata')
            match = re.search(r'#(\d{12})(?:_|$)', table)
            columns = {}
            for _, name, sql_type, not_null, default, pk in db.execute(f'pragma table_info({ident(table)})'):
                columns[name] = {'type': sql_type, 'not_null': bool(not_null), 'default': default, 'primary_key': pk}
            layers[table] = {'type_code': match.group(1) if match else None,
                             'dtm_class_key': table.split('#')[-1].split('_')[0],
                             'contents_srs_id': srs, 'geometry': geometry[table], 'columns': columns}
        crs = {}
        for name, srs, org, code, definition in db.execute(
                'select srs_name,srs_id,organization,organization_coordsys_id,definition from gpkg_spatial_ref_sys'):
            if srs in used_crs:
                crs[str(srs)] = {'name': name, 'organization': org, 'code': code, 'definition': definition}
        return {'format': 'gpkg', 'application_id': db.execute('pragma application_id').fetchone()[0],
                'gpkg_user_version': db.execute('pragma user_version').fetchone()[0],
                'crs': crs, 'layers': layers}


def xml_schema(path):
    root_tag, root_attributes = None, None
    values = {}
    wanted = {'VerzeJVFDTM', 'DatumZapisu', 'DatumPlatnosti', 'TypDatoveSady'}
    for event, node in ET.iterparse(path, events=('start', 'end')):
        if root_tag is None:
            root_tag, root_attributes = node.tag, dict(node.attrib)
        if event == 'end':
            name = node.tag.split('}')[-1]
            if name in wanted and node.text:
                values.setdefault(name, set()).add(node.text.strip())
            node.clear()
    versions = sorted(values.get('VerzeJVFDTM', ()))
    if not versions:
        raise ValueError(f'{path}: XML has no explicit VerzeJVFDTM header')
    return {'format': 'jvf', 'root': root_tag, 'root_attributes': root_attributes,
            'jvf_versions': versions,
            'data_headers': {k: sorted(v) for k, v in values.items() if k != 'VerzeJVFDTM'}}


def inspect(path):
    path = Path(path)
    components = {}

    def add(local, name):
        if local.suffix.lower() == '.gpkg':
            key, result = 'gpkg:' + Path(name).name, gpkg_schema(local)
        elif local.suffix.lower() == '.xml':
            key, result = 'jvf:' + str(sum(k.startswith('jvf:') for k in components)), xml_schema(local)
        else:
            return
        if key in components:
            raise ValueError(f'{path}: duplicate component {key}')
        components[key] = result

    if path.is_dir():
        for file in sorted(path.iterdir()):
            if file.is_file():
                add(file, file.name)
        source_hash = None
    elif zipfile.is_zipfile(path):
        with tempfile.TemporaryDirectory(prefix='dtm-schema-') as tmp:
            with zipfile.ZipFile(path) as archive:
                for i, name in enumerate(sorted(archive.namelist())):
                    if Path(name).suffix.lower() not in ('.gpkg', '.xml'):
                        continue
                    # Never extract a source-controlled archive member path directly.
                    local = Path(tmp) / (str(i) + Path(name).suffix.lower())
                    with archive.open(name) as src, local.open('wb') as dst:
                        shutil.copyfileobj(src, dst)
                    add(local, name)
        source_hash = digest(path)
    else:
        add(path, path.name)
        source_hash = digest(path)
    if not components:
        raise ValueError(f'{path}: no GPKG or JVF XML component')
    return {'path': str(path), 'sha256': source_hash, 'components': components}


def schema_only(report):
    # Monthly feature counts, extents, timestamps and hashes are not a schema migration.
    return {key: {k: v for k, v in component.items() if k != 'data_headers'}
            for key, component in report['components'].items()}


def differences(before, after, path='schema'):
    if isinstance(before, dict) and isinstance(after, dict):
        out = []
        for key in sorted(before.keys() | after.keys()):
            here = f'{path}/{key}'
            if key not in before:
                out.append({'path': here, 'before': None, 'after': after[key], 'change': 'added'})
            elif key not in after:
                out.append({'path': here, 'before': before[key], 'after': None, 'change': 'removed'})
            else:
                out.extend(differences(before[key], after[key], here))
        return out
    return [] if before == after else [{'path': path, 'before': before, 'after': after, 'change': 'changed'}]


def display(report):
    print(f"Package: {report['path']}")
    print(f"SHA256: {report['sha256'] or 'directory (inspect each archive for a hash)'}")
    for key, component in report['components'].items():
        print(f'  Component: {key}')
        if component['format'] == 'jvf':
            print('  JVF header version: ' + ', '.join(component['jvf_versions']))
            print('  Data headers: ' + json.dumps(component['data_headers'], ensure_ascii=False, sort_keys=True))
            continue
        print(f"  GPKG user_version: {component['gpkg_user_version']} (not a JVF version)")
        print('  JVF header version: not present in this GPKG input')
        print(f"  Feature layers: {len(component['layers'])}; CRS: " + json.dumps(component['crs'], ensure_ascii=False, sort_keys=True))
        sets = {}
        for table, layer in component['layers'].items():
            signature = tuple(sorted((k, v['type']) for k, v in layer['columns'].items()))
            group = sets.setdefault(signature, len(sets) + 1)
            print(f"  {table} | code={layer['type_code']} | geometry={json.dumps(layer['geometry'], sort_keys=True)} | attributes=A{group}")
        for columns, number in sets.items():
            print(f"  A{number}: " + ', '.join(f'{name}:{kind}' for name, kind in columns))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packages', nargs='+')
    parser.add_argument('--compare', action='store_true')
    parser.add_argument('--output', type=Path, help='save full JSON schemas and comparison')
    args = parser.parse_args()
    paths = [Path(p) for pattern in args.packages for p in (sorted(glob.glob(pattern)) or [pattern])]
    if args.compare and len(paths) != 2:
        parser.error('--compare requires exactly two packages')
    reports = [inspect(p) for p in paths]
    for report in reports:
        display(report)
    result = {'inputs': reports}
    changed = differences(schema_only(reports[0]), schema_only(reports[1])) if args.compare else []
    if args.compare:
        result['differences'] = changed
        print(f'Schema differences: {len(changed)}')
        for item in changed:
            print(json.dumps(item, ensure_ascii=False, sort_keys=True))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with replacing(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write('\n')
    return 1 if changed else 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        raise SystemExit(main())
    except (OSError, ValueError, sqlite3.Error, zipfile.BadZipFile, ET.ParseError) as error:
        print(f'dtm_schema: {error}', file=sys.stderr)
        raise SystemExit(2)
