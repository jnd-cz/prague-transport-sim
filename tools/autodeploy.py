"""Deploy each new main to the test host (#131): python -I tools/autodeploy.py [--install [MIN] | --uninstall]

Runs in a checkout kept for deploys (a worktree with deploy.local.json and its HEAD detached, as
../tg-deploy): fetches origin/main and, when it moved since the last deploy, checks it out, fetches
the data its manifest names (tools/snapshot.py data-fetch) and runs tools/deploy.py. Every run then
pulls the review verdicts from the host into reports/reviews/ (deploy.py --pull-reviews, #136). A failed deploy is retried after an hour, not on every run (the host bans
repeated failed logins). The password comes from ~/.netrc (machine <host> login <user> password …)
or TRAM_DEPLOY_PASSWORD: there is nobody to ask.

At night (NIGHT, local hours) it measures main's regression baseline once per change of what the
checks depend on (tools/baseline_store.py: the game, the checks, the data manifest), with 2 pages at
once, and publishes it to the data store for `headless.py --compare` (#157). Not while another heavy
job runs on this computer (headless.py, rebuild.py) or memory is short; a merge of docs or tools only
costs nothing, and several merges in a day cost one run.

--install registers a Windows scheduled task (every MIN minutes, default 10, while you are logged
on) that runs this with pythonw (no window); --uninstall removes it. Log and state:
reports/autodeploy.log, reports/autodeploy.json (both git-ignored).
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "deploy.local.json")
LOG = os.path.join(ROOT, "reports", "autodeploy.log")
STATE = os.path.join(ROOT, "reports", "autodeploy.json")
TASK = "tram-autodeploy"
RETRY = 3600  # s after a failed deploy of the same commit
NIGHT = range(1, 5)  # local hours in which the nightly baseline may start
LINES, CHECKS = "9,17,22,23,37", "u3,redruns,traffic,lint,surfaces"
# (under pythonw a console child would open a window of its own on every run)
QUIET = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def python():
    """The console interpreter next to this one (pythonw has no stdout for the children)."""
    d, f = os.path.split(sys.executable)
    return os.path.join(d, f.replace("pythonw", "python"))


def run(log, *cmd):
    log.flush()
    return subprocess.run(cmd, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                          text=True, **QUIET).returncode


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          check=True, **QUIET).stdout.strip()


def load_state():
    try:
        with open(STATE, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError):
        return {}


def save_state(st):
    with open(STATE + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=1)
    os.replace(STATE + ".tmp", STATE)


def once(log):
    """One check; returns the exit code (0 also when nothing was new)."""
    if not os.path.exists(CONFIG):
        print(f"no {os.path.basename(CONFIG)} in {ROOT}: not a deploy checkout", file=log)
        return 2
    # (a branch checked out, or changes, mean someone works in this checkout: leave it alone)
    if subprocess.run(["git", "symbolic-ref", "-q", "HEAD"], cwd=ROOT, capture_output=True, **QUIET).returncode == 0:
        print("HEAD is on a branch: the deploy checkout stays detached (git checkout --detach)", file=log)
        return 2
    if git("status", "--porcelain", "--untracked-files=no"):
        print("uncommitted changes in the deploy checkout", file=log)
        return 2
    if run(log, "git", "fetch", "-q", "origin", "main"):
        return 1
    st = load_state()
    code = deploy(log, st)
    if time.time() - st.get("pull_failed_at", 0) >= RETRY:
        if run(log, python(), "-I", "tools/deploy.py", "--pull-reviews"):
            st["pull_failed_at"] = time.time()
            print(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} pulling the reviews failed; next try in {RETRY // 60} min", file=log)
            code = code or 1
        else:
            st.pop("pull_failed_at", None)
    save_state(st)
    if code == 0 and st.get("deployed") == git("rev-parse", "HEAD"):
        code = nightly(log, st)
        save_state(st)
    return code


def nightly(log, st, now=None):
    """Main's baseline measured and published, if it is night and it is not in the store yet."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import baseline_store
    from sysinfo import workers
    now = now or datetime.datetime.now()
    if now.hour not in NIGHT:
        return 0
    k = baseline_store.key(baseline_store.trees("HEAD"))
    if st.get("baseline") == k or st.get("baseline_tried") == [k, f"{now:%Y-%m-%d}"]:
        return 0
    stamp = f"{now:%Y-%m-%d %H:%M:%S}"
    if baseline_store.published(k):
        st["baseline"] = k
        return 0
    if busy := baseline_store.busy():
        print(f"{stamp} nightly baseline waits: {'; '.join(busy)}", file=log)
        return 0
    if workers(4.0) < 2:
        print(f"{stamp} nightly baseline waits: not enough free memory for 2 pages", file=log)
        return 0
    print(f"{stamp} nightly baseline of {git('rev-parse', '--short', 'HEAD')} ({k[:12]})", file=log)
    code = run(log, python(), "-P", "-E", "tools/headless.py", "--lines", LINES, "--checks", CHECKS,
               "--baseline", "--publish", "--jobs", "2", "--port", "0")
    # (the deploy checkout stays as checked out: the files --baseline wrote are only published)
    run(log, "git", "checkout", "-q", "--", "reports/baseline")
    if baseline_store.published(k):
        st["baseline"] = k
        return 0
    print(f"{stamp} nightly baseline not published (exit {code}); next night again", file=log)
    st["baseline_tried"] = [k, f"{now:%Y-%m-%d}"]  # (once a night: not again every 10 minutes)
    return 1


def deploy(log, st):
    """The new main deployed, if there is one; st updated."""
    new = git("rev-parse", "origin/main")
    if new == st.get("deployed"):
        return 0
    if new == st.get("failed") and time.time() - st.get("failed_at", 0) < RETRY:
        return 0
    print(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {new[:7]} {git('log', '-1', '--format=%s', new)}", file=log)
    ok = (run(log, "git", "checkout", "-q", "--detach", new) == 0
          and run(log, python(), "-I", "tools/snapshot.py", "data-fetch") == 0
          and run(log, python(), "-I", "tools/deploy.py") == 0)
    if ok:
        st.update(deployed=new, at=time.time())
        st.pop("failed", None)
        st.pop("failed_at", None)
    else:
        st.update(failed=new, failed_at=time.time())
        print(f"deploy of {new[:7]} failed; next try in {RETRY // 60} min", file=log)
    return 0 if ok else 1


def install(minutes):
    exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    cmd = f'"{exe}" -I "{os.path.abspath(__file__)}"'
    subprocess.run(["schtasks", "/Create", "/F", "/TN", TASK, "/SC", "MINUTE", "/MO", str(minutes), "/TR", cmd],
                   check=True)
    print(f"{TASK}: every {minutes} min, log {LOG}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--install", nargs="?", type=int, const=10, metavar="MIN",
                    help="register the scheduled task (every MIN minutes, default 10)")
    ap.add_argument("--uninstall", action="store_true", help="remove the scheduled task")
    args = ap.parse_args(argv)
    if args.install:
        return install(args.install)
    if args.uninstall:
        return subprocess.run(["schtasks", "/Delete", "/F", "/TN", TASK]).returncode
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as log:
        try:
            return once(log)
        except Exception as e:  # (a scheduled run has nobody watching: the reason goes to the log)
            print(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {type(e).__name__}: {e}", file=log)
            return 1


if __name__ == "__main__":
    sys.exit(main())
