"""Player feedback (#350): python -I tools/feedback.py [--site NAME] [--kind K] [--line N] [--all] [--perf]

Lists the notes in <feedback>/<site>/ (pulled from a host by tools/deploy.py --pull, or written by tools/serve.py
as site "local"; <feedback> is beside the data cache, _dest()), newest first, grouped by kind. Reads only: a note becomes an issue when
someone decides so. --all also lists notes marked done (a "done" file beside the note: <id>.done).
--perf: how the game runs per machine, from the shifts' summaries (kind perf) and the performance tests
(perftest): runs, frames per second and the share of frames over 33 ms, medians.
save() is the one writer of a note: the screenshot goes beside it as <id>.jpg.
"""
import argparse
import base64
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _dest():
    """Where the notes live: $TRAM_FEEDBACK, else beside the machine's data cache ($TRAMDATA_CACHE/../feedback), so
    every checkout and worktree on the machine reads the same notes and the deploy checkout's pulls reach them;
    else reports/feedback/ of this checkout. Never in git: a tester's note is theirs, not the public repo's."""
    if os.environ.get("TRAM_FEEDBACK"):
        return os.environ["TRAM_FEEDBACK"]
    if os.environ.get("TRAMDATA_CACHE"):
        return os.path.join(os.path.dirname(os.path.abspath(os.environ["TRAMDATA_CACHE"])), "feedback")
    return os.path.join(ROOT, "reports", "feedback")


DEST = _dest()
ID = re.compile(r"fb-\d{8}-\d{6}-[0-9a-f]{8}")
JPEG = "data:image/jpeg;base64,"
# (the caps of tools/feedback.php, which tools/serve.py applies to the notes it takes locally: change both)
MAX_BODY, MAX_NOTE = 2_000_000, 5000


def invalid(rec):
    """What makes a posted note unacceptable (as feedback.php decides), or None."""
    if not isinstance(rec, dict):
        return "json"
    if not isinstance(rec.get("note"), str) or len(rec["note"]) > MAX_NOTE:
        return "note"
    if rec.get("shot") is not None and not (isinstance(rec["shot"], str) and rec["shot"].startswith(JPEG)):
        return "shot"
    return None


def new_id():
    import datetime
    import secrets
    return f"fb-{datetime.datetime.now(datetime.timezone.utc):%Y%m%d-%H%M%S}-{secrets.token_hex(4)}"


def save(site_dir, rec):
    """A note (as feedback.php stores it, with its id) into site_dir: <id>.json and the screenshot as <id>.jpg.
    Returns the note's path, or None for a note without a valid id."""
    nid = rec.get("id") if isinstance(rec, dict) else None
    if not isinstance(nid, str) or not ID.fullmatch(nid):
        return None
    os.makedirs(site_dir, exist_ok=True)
    shot = rec.get("shot")
    if isinstance(shot, str) and shot.startswith(JPEG):
        with open(os.path.join(site_dir, nid + ".jpg"), "wb") as fh:
            fh.write(base64.b64decode(shot[len(JPEG):]))
        rec = {**rec, "shot": nid + ".jpg"}
    path = os.path.join(site_dir, nid + ".json")
    with open(path + ".tmp", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)
    return path


def notes(dest=None, site=None, everything=False):
    """[(site, note)] newest first."""
    dest, out = dest or DEST, []
    for s in sorted(os.listdir(dest)) if os.path.isdir(dest) else []:
        d = os.path.join(dest, s)
        if not os.path.isdir(d) or (site and s != site):
            continue
        for f in os.listdir(d):
            if not (f.endswith(".json") and ID.fullmatch(f[:-5])):
                continue
            if not everything and os.path.exists(os.path.join(d, f[:-5] + ".done")):
                continue
            try:
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    out.append((s, json.load(fh)))
            except ValueError:
                print(f"{s}/{f}: not JSON, skipped", file=sys.stderr)
    return sorted(out, key=lambda sn: sn[1].get("id", ""), reverse=True)


def machine(n):
    """A short name of the machine: the GPU where the note has it, else the browser's platform."""
    m = n.get("machine") or {}
    if m.get("gpu"):
        return m["gpu"]
    ua = n.get("ua") or ""
    for k in ("Android", "iPhone", "iPad", "Windows", "Mac OS", "Linux"):
        if k in ua:
            return k
    return "?"


def perf_table(got):
    """Lines of the per-machine table: the performance tests and the shifts' summaries apart."""
    rows = {}
    for _, n in got:
        p = n.get("perftest") if n.get("kind") == "perftest" else n.get("perf") if n.get("kind") == "perf" else None
        if p and p.get("frames"):
            rows.setdefault((machine(n), n["kind"]), []).append(p)
    med = lambda xs: sorted(xs)[len(xs) // 2]  # noqa: E731
    out = [f"{'machine':60} {'kind':8} {'runs':>4} {'fps':>6} {'>33 ms':>7} {'GPU ms':>7}"]
    for (m, k), ps in sorted(rows.items()):
        gpu = [p["gpuMs"] for p in ps if p.get("gpuMs") is not None]
        out.append(f"{m[:60]:60} {k:8} {len(ps):>4} {med([p['fps'] for p in ps]):>6} "
                   f"{med([p['over']['33'] for p in ps]):>6}% {med(gpu) if gpu else '-':>7}")
    return out


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--site", help="one site's notes (alpha, test, local)")
    ap.add_argument("--kind", help="one kind")
    ap.add_argument("--line", help="one line")
    ap.add_argument("--all", action="store_true", help="also the notes marked done")
    ap.add_argument("--perf", action="store_true", help="the per-machine performance table")
    args = ap.parse_args(argv)
    got = [(s, n) for s, n in notes(site=args.site, everything=args.all)
           if (not args.kind or n.get("kind") == args.kind) and (not args.line or str(n.get("line")) == args.line)]
    if not got:
        print("no notes")
        return
    if args.perf:
        print("\n".join(perf_table(got)))
        return
    kinds = {}
    for s, n in got:
        kinds.setdefault(n.get("kind") or "other", []).append((s, n))
    for k in sorted(kinds, key=lambda k: -len(kinds[k])):
        print(f"\n{k} ({len(kinds[k])})")
        for s, n in kinds[k]:
            ver = (n.get("version") or {}).get("commit", "")[:7] or "?"
            where = f"line {n.get('line')}" + (f" s {n['tram']['s']}" if isinstance(n.get("tram"), dict) else "")
            note = " ".join((n.get("note") or "").split())
            errs = f", {len(n['errors'])} errors" if n.get("errors") else ""
            p = n.get("perftest") or (n.get("perf") if n.get("kind") == "perf" else None)
            if p and not note:
                note = f"{p.get('fps')} fps, {p.get('over', {}).get('33')} % over 33 ms, {p.get('seconds')} s"
            print(f"  {n.get('id')} [{s}] {ver} {where}, {machine(n)}{errs}{', shot' if n.get('shot') else ''}")
            if note:
                print(f"    {note[:300]}")
    print(f"\n{len(got)} notes in {DEST}")


if __name__ == "__main__":
    main()
