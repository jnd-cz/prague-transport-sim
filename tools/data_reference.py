"""Read-only published data and temporary git references for shot.py and datadiff.py (#158)."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def git(root, *args):
    try:
        return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.PIPE).decode('utf-8').strip()
    except subprocess.CalledProcessError as e:
        raise ValueError(e.stderr.decode('utf-8', errors='replace').strip()) from None


def manifest(root, ref=None):
    if ref and not Path(ref).is_dir():
        rev = git(root, 'rev-parse', '--verify', ref + '^{commit}')
        return json.loads(git(root, 'show', f'{rev}:data/MANIFEST.json'))
    return json.loads((Path(ref or root) / 'data/MANIFEST.json').read_text(encoding='utf-8'))


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def published(root, name, man, cache=None, other=None):
    """Never restore over a working file; a matching local copy is also a verified reference."""
    if Path(name).name != name:
        raise ValueError(f'not a data filename: {name}')
    meta = man['files'].get(name)
    if meta is None:
        raise FileNotFoundError(f'{name} is not in the reference manifest')
    cache = cache or os.environ.get('TRAMDATA_CACHE')
    paths = ([Path(cache).expanduser() / 'builds' / meta['sha256']] if cache else [])
    paths += [Path(r) / 'data' / name for r in (other, root) if r]
    for path in paths:
        if path.is_file() and path.stat().st_size == meta['size'] and digest(path) == meta['sha256']:
            return path
    raise FileNotFoundError(f"published {name} ({meta['sha256']}) not available; populate TRAMDATA_CACHE "
                            'with snapshot.py data-fetch in a separate checkout of the reference')


@contextmanager
def checkout(root, ref, cache=None):
    """A directory is used as-is; a git revision is exported, with its own verified published data."""
    if Path(ref).is_dir():
        yield Path(ref).resolve()
        return
    rev = git(root, 'rev-parse', '--verify', ref + '^{commit}')
    with tempfile.TemporaryDirectory(prefix='tram-shot-') as tmp:
        folder = Path(tmp)
        archive = folder / 'reference.tar'
        git(root, 'archive', '--format=tar', '-o', str(archive), rev)
        target = folder / 'checkout'
        target.mkdir()
        with tarfile.open(archive) as tar:
            tar.extractall(target, filter='data')
        man = manifest(target)
        for name in man['files']:
            src = published(root, name, man, cache)
            dst = target / 'data' / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            # Read-only consumers: copying also works across the temp/cache volumes.
            shutil.copyfile(src, dst)
        yield target
