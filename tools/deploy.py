"""Upload the game to the web host over FTPS (#131): python -I tools/deploy.py [--dry-run] [--reports]

Config (git-ignored, in the checkout's root): deploy.local.json
    {"host": "<FTP host>", "user": "<FTP user>", "dir": "/httpdocs", "url": "https://testing.pipethebytes.com/"}
Password: TRAM_DEPLOY_PASSWORD, else ~/.netrc (machine <host>), else asked; never stored by this tool.
Access protection is the web host's (Plesk: Password-Protected Directories); after a deploy the URL is
checked to answer 401 without a login.

What goes up: tools/make_dist.py's files, plus version.json (commit, data snapshot, date) and an
.htaccess (compression, revalidation). The server keeps .deploy-manifest.json (path -> sha256): only
changed files are uploaded (each to a .part name, then renamed), files no longer in the site are
deleted, the manifest is written last. A rollback is a deploy from the older commit.
--reports also uploads reports/headless/*.json (for ?review=reports/headless/line17-lint.json).
Review verdicts (#136): tools/review.php goes up as review.php and stores them in reviews/ (no direct
access); --pull-reviews only fetches reviews/*.json into reports/reviews/, merged with what is there.
"""
import argparse
import base64
import datetime
import ftplib
import getpass
import hashlib
import io
import json
import netrc
import os
import subprocess
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reviews  # noqa: E402
from make_dist import ROOT, files  # noqa: E402

CONFIG = os.path.join(ROOT, "deploy.local.json")
MANIFEST = ".deploy-manifest.json"
HTACCESS = """# tools/deploy.py: compressed transfers; the files keep their names between deploys, so revalidate
<IfModule mod_mime.c>
  AddType text/javascript .js
  AddType application/json .json
  AddType model/gltf+json .gltf
  AddType application/octet-stream .bin
</IfModule>
<IfModule mod_deflate.c>
  AddOutputFilterByType DEFLATE text/html text/css text/javascript application/json model/gltf+json application/octet-stream
</IfModule>
<IfModule mod_headers.c>
  Header set Cache-Control "no-cache"
</IfModule>
<Files ".deploy-manifest.json">
  Require all denied
</Files>
"""


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def checks(allow_dirty):
    """The commit to deploy; stops on uncommitted changes or data that differs from the manifest."""
    if not allow_dirty and git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("uncommitted changes: commit them, or --dirty for a test deploy")
    st = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "snapshot.py"), "status"], cwd=ROOT,
                        capture_output=True, text=True)
    if "0 differences to data/MANIFEST.json" not in st.stdout:
        raise SystemExit("data/ differs from data/MANIFEST.json: python -I tools/snapshot.py data-fetch")
    return git("rev-parse", "HEAD")


def site(commit, reports=False):
    """{path: bytes or a local file path} of everything that goes up."""
    out = {rel: os.path.join(ROOT, rel) for rel in files()}
    if reports:
        d = os.path.join(ROOT, "reports", "headless")
        for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if f.endswith(".json"):
                out[f"reports/headless/{f}"] = os.path.join(d, f)
    with open(os.path.join(ROOT, "data", "MANIFEST.json"), encoding="utf-8") as fh:
        man = json.load(fh)
    version = {"commit": commit, "subject": git("log", "-1", "--format=%s", commit),
               "data": {k: man[k] for k in ("snapshot", "built_at_commit", "published", "note") if k in man},
               "deployed": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
               "by": git("config", "user.name")}
    out["version.json"] = json.dumps(version, ensure_ascii=False, indent=1).encode()
    out["review.php"] = os.path.join(ROOT, "tools", "review.php")
    out["reviews/.htaccess"] = b"Require all denied\n"
    out[".htaccess"] = HTACCESS.encode()
    return out


def digest(v):
    h = hashlib.sha256()
    if isinstance(v, bytes):
        h.update(v)
    else:
        with open(v, "rb") as fh:
            while b := fh.read(1 << 20):
                h.update(b)
    return h.hexdigest()


def order(rel):
    """Data and assets first, the code after them, the page and its version last: a visitor during the
    upload gets the old page or a complete new one, apart from the files of one part."""
    top = rel.split("/")[0]
    return ({"data": 0, "assets": 1, "reports": 2, "src": 3}.get(top, 4), rel in ("index.html", "version.json"), rel)


def plan(local, remote):
    """(paths to upload, paths to delete) from {path: sha256} here and on the server."""
    up = sorted((r for r, h in local.items() if remote.get(r) != h), key=order)
    gone = sorted(r for r in remote if r not in local)
    return up, gone


def password(cfg):
    if os.environ.get("TRAM_DEPLOY_PASSWORD"):
        return os.environ["TRAM_DEPLOY_PASSWORD"]
    try:
        auth = netrc.netrc().authenticators(cfg["host"])
        if auth and auth[0] in (None, "", cfg["user"]) and auth[2]:
            return auth[2]
    except (FileNotFoundError, netrc.NetrcParseError):
        pass
    if not sys.stdin or not sys.stdin.isatty():
        raise SystemExit(f"no password for {cfg['host']}: TRAM_DEPLOY_PASSWORD or ~/.netrc (nobody to ask)")
    return getpass.getpass(f"FTP password for {cfg['user']}@{cfg['host']}: ")


def connect(cfg, pw):
    ftp = ftplib.FTP_TLS(cfg["host"], timeout=60)
    ftp.login(cfg["user"], pw)
    ftp.prot_p()  # (the data connection encrypted too, not only the login)
    ftp.cwd(cfg.get("dir", "/"))
    return ftp


def remote_manifest(ftp):
    buf = io.BytesIO()
    try:
        ftp.retrbinary(f"RETR {MANIFEST}", buf.write)
    except ftplib.error_perm:
        return {}  # (a first deploy)
    return json.loads(buf.getvalue() or b"{}")


def upload(ftp, rel, value, made):
    parts = rel.split("/")
    for i in range(1, len(parts)):
        d = "/".join(parts[:i])
        if d not in made:
            try:
                ftp.mkd(d)
            except ftplib.error_perm:
                pass  # (exists)
            made.add(d)
    src = io.BytesIO(value) if isinstance(value, bytes) else open(value, "rb")
    with src:
        ftp.storbinary(f"STOR {rel}.part", src)
    try:
        ftp.delete(rel)
    except ftplib.error_perm:
        pass  # (new)
    ftp.rename(f"{rel}.part", rel)


def pull_reviews(ftp, dest=os.path.join(ROOT, "reports", "reviews")):
    """reviews/*.json from the host merged into dest; prints the files that changed. A report (src/report.js,
    written once) is fetched once, its screenshot saved beside it as report-….jpg."""
    try:
        names = [n.rsplit("/", 1)[-1] for n in ftp.nlst("reviews")]
    except ftplib.error_perm:
        return  # (nothing reviewed yet)
    for n in sorted(names):
        if not n.endswith(".json") or not reviews.NAME.fullmatch(n[:-5]):
            continue
        path = os.path.join(dest, n)
        if n.startswith("report-") and os.path.exists(path):
            continue
        buf = io.BytesIO()
        ftp.retrbinary(f"RETR reviews/{n}", buf.write)
        try:
            new = json.loads(buf.getvalue() or b"{}")
        except ValueError:
            print(f"reviews/{n}: not JSON, skipped")
            continue
        if n.startswith("report-") and isinstance(new, dict):
            for rec in (new.get("items") or {}).values():
                shot = rec.get("shot") if isinstance(rec, dict) else None
                if isinstance(shot, str) and shot.startswith("data:image/jpeg;base64,"):
                    os.makedirs(dest, exist_ok=True)
                    with open(os.path.join(dest, n[:-5] + ".jpg"), "wb") as fh:
                        fh.write(base64.b64decode(shot.split(",", 1)[1]))
                    rec["shot"] = n[:-5] + ".jpg"
            reviews.save(path, new)
            for rec in (new.get("items") or {}).values():
                print(f"{os.path.relpath(path, ROOT)}: {rec.get('kind')}, line {rec.get('line')}: {rec.get('note', '')[:80]}")
            continue
        cur = reviews.load(path)
        out = reviews.merge(cur, new if isinstance(new, dict) else {})
        if out != cur:
            reviews.save(path, out)
            done = sum(1 for v in out["items"].values() if v.get("v"))
            print(f"{os.path.relpath(path, ROOT)}: {len(out['items'])} findings, {done} with a verdict")


def protected(url):
    """The HTTP status of version.json without a login: 401 when the host protects the site."""
    try:
        return urllib.request.urlopen(url.rstrip("/") + "/version.json", timeout=20).status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError as e:
        return f"unreachable ({e})"


def main(argv=None, connect=connect):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="list what would change, write nothing")
    ap.add_argument("--reports", action="store_true", help="also upload reports/headless/*.json")
    ap.add_argument("--dirty", action="store_true", help="deploy with uncommitted changes (a test)")
    ap.add_argument("--pull-reviews", action="store_true", help="only fetch the review verdicts from the host")
    args = ap.parse_args(argv)
    if not os.path.exists(CONFIG):
        raise SystemExit(f"no {os.path.basename(CONFIG)}: see the usage at the top of tools/deploy.py")
    with open(CONFIG, encoding="utf-8") as fh:
        cfg = json.load(fh)
    if args.pull_reviews:
        ftp = connect(cfg, password(cfg))
        try:
            pull_reviews(ftp)
        finally:
            ftp.quit()
        return
    commit = checks(args.dirty)
    local = site(commit, args.reports)
    hashes = {r: digest(v) for r, v in local.items()}
    ftp = connect(cfg, password(cfg))
    try:
        remote = remote_manifest(ftp)
        # (version.json changes every time; it goes up whenever anything else does)
        up, gone = plan({r: h for r, h in hashes.items() if r != "version.json"}, remote)
        size = sum(len(local[r]) if isinstance(local[r], bytes) else os.path.getsize(local[r]) for r in up)
        print(f"{commit[:7]}: {len(up)} files to upload ({size / 1e6:.1f} MB), {len(gone)} to delete, "
              f"{len(hashes) - 1 - len(up)} unchanged")
        if args.dry_run:
            for r in up:
                print("  up ", r)
            for r in gone:
                print("  del", r)
            return
        made = set()
        for i, r in enumerate(up + ["version.json"], 1):
            upload(ftp, r, local[r], made)
            print(f"  [{i}/{len(up) + 1}] {r}", flush=True)
        for r in gone:
            try:
                ftp.delete(r)
            except ftplib.error_perm:
                pass
        upload(ftp, MANIFEST, json.dumps(hashes, indent=0).encode(), made)
    finally:
        try:
            ftp.quit()
        except (ftplib.Error, OSError):
            pass
    if cfg.get("url"):
        code = protected(cfg["url"])
        note = "protected" if code == 401 else "NOT PROTECTED: set a password in Plesk (Password-Protected Directories)" if code == 200 else ""
        print(f"{cfg['url']}: version.json without a login answers {code} {note}")


if __name__ == "__main__":
    main()
