# SPDX-License-Identifier: AGPL-3.0-or-later
"""Vehicle packages their authors submitted through the game's website (#580):

    python -I tools/submissions.py [--site NAME] [--all]              # list them, newest first
    python -P -E tools/submissions.py --check ID                       # the game's check, headless, and its pictures
    python -I tools/submissions.py --accept ID [--url URL] [--home URL]
    python -I tools/submissions.py --reject ID "why"
    python -I tools/submissions.py --delete ID                         # once its author has the verdict

The Vehicles... page (src/packagesMenu.js) checks a package as the game does and sends it, or its address, to the
host's submit.php (tools/submit.php; tools/serve.py takes them locally as site "local"); tools/deploy.py --pull moves
them into <submissions>/<site>/<id>/ (meta.json, pack.zip), beside the data cache like the feedback (DEST), never
into git: an author's contact is theirs.

--accept adds one entry to assets/catalogue.json (--catalogue for another). Where the author ticked "the project may
host these files" the pack goes to <submissions>/hosted/<id>-<version>.zip, which deploy uploads as hosted/..., and
the entry's url is that; otherwise the url is the author's address (the submitted one, or --url) and the upload is
deleted. --reject records why and deletes the upload. A verdict stays beside meta.json (verdict.json) until --delete.
"""
import argparse
import datetime
import json
import os
import re
import secrets
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atomic import replacing  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.path.join(ROOT, "src", "packageRules.json")
CATALOGUE = os.path.join(ROOT, "assets", "catalogue.json")


def _dest():
    """$TRAM_SUBMISSIONS, else beside the machine's data cache (as tools/feedback.py's notes), else reports/submissions/."""
    if os.environ.get("TRAM_SUBMISSIONS"):
        return os.environ["TRAM_SUBMISSIONS"]
    if os.environ.get("TRAMDATA_CACHE"):
        return os.path.join(os.path.dirname(os.path.abspath(os.environ["TRAMDATA_CACHE"])), "submissions")
    return os.path.join(ROOT, "reports", "submissions")


DEST = _dest()
HOSTED = os.path.join(DEST, "hosted")   # accepted packs the project hosts: deploy uploads them as hosted/<name>
ID = re.compile(r"sub-\d{8}-\d{6}-[0-9a-f]{8}")
VERSION = re.compile(r"\d+\.\d+\.\d+")   # (a package's: major.minor.patch, src/packages.js manifestProblems)
# (the caps of tools/submit.php, which tools/serve.py applies locally: change both. The user, 2026-11-15, #580: "these
# sound like reasonable limits for now": 10 an hour from everyone together, 64 MB each, 2 GB kept until a pull)
MAX_META = 65536          # bytes of the meta field
MAX_CONTACT = 200         # characters: an email or a Discord name
MAX_NOTE = 2000
MAX_URL = 500
MAX_ENTRIES = 1000        # files in one zip
PER_HOUR = 10
MAX_KEPT = 200            # submissions kept until a pull
MAX_BYTES = 2_000_000_000
URL = re.compile(r"https://[^\s\"'<>]+?(\.zip|/package\.json)(\?[^\s\"'<>]*)?")


def rules():
    with open(RULES, encoding="utf-8") as f:
        return json.load(f)


def meta_problem(meta, has_pack):
    """What makes a submission's meta unacceptable (as submit.php decides), or None."""
    if not isinstance(meta, dict):
        return "meta"
    for key, cap in (("contact", MAX_CONTACT), ("note", MAX_NOTE)):
        if meta.get(key) is not None and (not isinstance(meta[key], str) or len(meta[key]) > cap):
            return key
    if not isinstance(meta.get("host"), bool):
        return "host"
    if meta.get("licence") is not True:
        return "licence"   # (the author confirms the licences in it)
    url = meta.get("url")
    if url is not None and not (isinstance(url, str) and len(url) <= MAX_URL and URL.fullmatch(url)):
        return "url"
    if (url is None) == (not has_pack):
        return "pack or url"   # (one of them: the archive, or its address)
    if not isinstance(meta.get("packages"), list) or not meta["packages"] or len(meta["packages"]) > 50:
        return "packages"
    r = rules()
    if not all(package_ok(p, r) for p in meta["packages"]):
        return "packages"
    return None


def package_ok(p, r=None):
    """A submission's package names itself as the game's check passes it (src/packageRules.json `id`, a version of
    three numbers). The page sends only checked packages; the two become a hosted file's name and a catalogue entry
    (accept), so they are held here too."""
    r = r or rules()
    return (isinstance(p, dict) and isinstance(p.get("id"), str) and re.fullmatch(r["id"], p["id"]) is not None
            and p["id"] not in r.get("reserved", ())
            and isinstance(p.get("version"), str) and VERSION.fullmatch(p["version"]) is not None)


def zip_problem(data, r=None):
    """What makes an uploaded pack unacceptable (as submit.php decides: a zip within the package cap whose every entry
    is of a type packageRules.json allows), or None. Reads the central directory only."""
    r = r or rules()
    if len(data) > r["caps"]["package"]:
        return "size"
    if data[:4] != b"PK\x03\x04":
        return "zip"
    at = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
    if at < 0 or at + 22 > len(data):
        return "zip"
    count, size, start = struct.unpack_from("<HII", data, at + 10)
    if count > MAX_ENTRIES or start + size > at:
        return "zip"
    p = start
    for _ in range(count):
        if data[p:p + 4] != b"PK\x01\x02":
            return "zip"
        n, x, c = struct.unpack_from("<HHH", data, p + 28)
        name = data[p + 46:p + 46 + n].decode("utf-8", "replace")
        p += 46 + n + x + c
        if name.endswith("/"):
            continue
        if not name or name.startswith("/") or "\\" in name or ".." in name.split("/"):
            return "path"
        ext = name.rsplit(".", 1)[-1].lower() if "." in name.rsplit("/", 1)[-1] else ""
        if ext not in r["types"]:
            return "type"
    return None


def new_id():
    return f"sub-{datetime.datetime.now(datetime.timezone.utc):%Y%m%d-%H%M%S}-{secrets.token_hex(4)}"


def save(site_dir, meta, pack=None):
    """A submission (with its id, as submit.php stores it) into site_dir/<id>/: meta.json and pack.zip, written whole
    (a folder made beside it and renamed). Returns its folder, or None for a meta without a valid id."""
    sid = meta.get("id") if isinstance(meta, dict) else None
    if not (isinstance(sid, str) and ID.fullmatch(sid)):
        return None
    final = os.path.join(site_dir, sid)
    if os.path.isdir(final):
        return final
    tmp = final + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    with open(os.path.join(tmp, "meta.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    if pack is not None:
        with open(os.path.join(tmp, "pack.zip"), "wb") as f:
            f.write(pack)
    os.replace(tmp, final)
    return final


def take(site_dir, raw, pack=None, r=None, now=None):
    """A submission as submit.php takes it (raw: the meta field's bytes, pack: the .zip's or None): checked, counted
    against the caps and saved. Returns (HTTP status, answer)."""
    if raw is None or len(raw) > MAX_META:
        return 400, {"error": "meta"}
    try:
        meta = json.loads(raw)
    except ValueError:
        return 400, {"error": "meta"}
    why = meta_problem(meta, pack is not None)
    if why:
        return 400, {"error": why}
    if pack is not None:
        why = zip_problem(pack, r)
        if why:
            return (413 if why == "size" else 400), {"error": why}
    now = now or datetime.datetime.now().timestamp()
    n = recent = size = 0
    for sid in os.listdir(site_dir) if os.path.isdir(site_dir) else []:
        f = os.path.join(site_dir, sid)
        if not ID.fullmatch(sid):
            continue
        n += 1
        size += sum(os.path.getsize(os.path.join(f, g)) for g in ("meta.json", "pack.zip") if os.path.isfile(os.path.join(f, g)))
        recent += os.path.getmtime(f) > now - 3600
    if recent >= PER_HOUR:
        return 429, {"error": "busy"}
    if n >= MAX_KEPT or size + len(raw) + len(pack or b"") > MAX_BYTES:
        return 507, {"error": "full"}
    meta["id"] = new_id()
    meta["received"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    save(site_dir, meta, pack)
    return 200, {"ok": True, "id": meta["id"]}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def submissions(dest=None):
    """[(site, folder, meta, verdict or None)], newest first."""
    dest = dest or DEST
    out = []
    for site in sorted(os.listdir(dest)) if os.path.isdir(dest) else []:
        d = os.path.join(dest, site)
        if site == "hosted" or not os.path.isdir(d):
            continue
        for sid in os.listdir(d):
            f = os.path.join(d, sid)
            if not (ID.fullmatch(sid) and os.path.isfile(os.path.join(f, "meta.json"))):
                continue
            v = os.path.join(f, "verdict.json")
            out.append((site, f, load(os.path.join(f, "meta.json")), load(v) if os.path.isfile(v) else None))
    return sorted(out, key=lambda x: x[2].get("id", ""), reverse=True)


def find(sid, dest=None):
    for row in submissions(dest):
        if row[2].get("id") == sid:
            return row
    raise SystemExit(f"submissions: no submission {sid} in {dest or DEST}")


def describe(meta):
    ps = ", ".join(f"{p.get('id')} {p.get('version')} ({p.get('kind')}, {p.get('licence')})" for p in meta.get("packages", []))
    how = f"address {meta['url']}" if meta.get("url") else "a .zip"
    return f"{ps}; {how}; {'may be hosted' if meta.get('host') else 'stays on its author host'}"


def verdict(folder, what, **more):
    with replacing(os.path.join(folder, "verdict.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"verdict": what, "at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), **more}, f,
                  ensure_ascii=False, indent=1)
    pack = os.path.join(folder, "pack.zip")
    if os.path.isfile(pack) and not more.get("keep"):
        os.remove(pack)


def entry(meta, url, home=None):
    """The catalogue entry for a submission: its vehicle package's (else its first package's) id, names and author, the
    licence of each package in it (the strictest first), and where the player installs it from."""
    ps = meta["packages"]
    main = next((p for p in ps if p.get("kind") == "vehicle"), ps[0])
    lics = sorted({p.get("licence") for p in ps if p.get("licence")}, key=lambda s: ("NC" not in s, "SA" not in s, s))
    e = {"id": main["id"], "names": main.get("names") or {}, "author": ", ".join(main.get("authors") or []),
         "licence": lics[0] if lics else None, "url": url, "submission": meta["id"]}
    if len(ps) > 1:
        e["packages"] = [p["id"] for p in ps]
    if home:
        e["home"] = home
    return e


def accept(sid, url=None, home=None, catalogue=CATALOGUE, dest=None):
    dest = dest or DEST
    site, folder, meta, _ = find(sid, dest)
    pack = os.path.join(folder, "pack.zip")
    # (a meta stored before the check held the names, or put there by hand: the names below come from it)
    if not isinstance(meta.get("packages"), list) or not meta["packages"] or not all(package_ok(p) for p in meta["packages"]):
        raise SystemExit(f"submissions: {sid}: a package's id or version is not one the game's check passes; not accepted")
    if meta.get("host"):
        src = pack if os.path.isfile(pack) else None
        if not src:
            raise SystemExit(f"submissions: {sid} may be hosted but its pack is not here (an address: fetch it with --check first)")
        main = next((p for p in meta["packages"] if p.get("kind") == "vehicle"), meta["packages"][0])
        name = f"{main['id']}-{main.get('version', '0')}.zip"
        hosted = os.path.join(dest, "hosted")
        os.makedirs(hosted, exist_ok=True)
        shutil.copyfile(src, os.path.join(hosted, name))
        where = f"hosted/{name}"
    else:
        where = url or meta.get("url")
        if not where:
            raise SystemExit(f"submissions: {sid} stays on its author's host: give its address (--url)")
    cat = load(catalogue)
    new = entry(meta, where, home)
    cat["packages"] = [c for c in cat.get("packages", []) if c.get("id") != new["id"]] + [new]
    with replacing(catalogue, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cat, f, ensure_ascii=False, indent=2)
        f.write("\n")
    verdict(folder, "accepted", url=where)
    return new


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--site", help="only this site's (a deploy target's name, or local)")
    ap.add_argument("--all", action="store_true", help="also those with a verdict")
    ap.add_argument("--check", metavar="ID")
    ap.add_argument("--out", help="--check: where the report and pictures go (default reports/submissions/<id>/)")
    ap.add_argument("--accept", metavar="ID")
    ap.add_argument("--url", help="--accept: the address the players install it from (an author-hosted one)")
    ap.add_argument("--home", help="--accept: the author's page, shown in the list")
    ap.add_argument("--catalogue", default=CATALOGUE)
    ap.add_argument("--reject", nargs=2, metavar=("ID", "WHY"))
    ap.add_argument("--delete", metavar="ID")
    a = ap.parse_args(argv)
    if a.check:
        import submission_check
        return submission_check.run(find(a.check), a.out or os.path.join(ROOT, "reports", "submissions", a.check))
    if a.accept:
        e = accept(a.accept, a.url, a.home, a.catalogue)
        print(f"{os.path.relpath(a.catalogue, ROOT)}: {e['id']} from {e['url']}")
        return 0
    if a.reject:
        site, folder, meta, _ = find(a.reject[0])
        verdict(folder, "rejected", reason=a.reject[1])
        print(f"{a.reject[0]}: rejected; tell its author: {meta.get('contact') or '(no contact)'}")
        return 0
    if a.delete:
        shutil.rmtree(find(a.delete)[1])
        print(f"{a.delete}: deleted")
        return 0
    rows = [r for r in submissions() if (not a.site or r[0] == a.site) and (a.all or not r[3])]
    for site, folder, meta, v in rows:
        state = f" [{v['verdict']}]" if v else ""
        print(f"{meta['id']} ({site}){state}: {describe(meta)}")
        if meta.get("contact"):
            print(f"    contact: {meta['contact']}")
        if meta.get("note"):
            print(f"    note: {' '.join(meta['note'].split())[:200]}")
    print(f"{len(rows)} submissions in {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
