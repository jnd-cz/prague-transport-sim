"""Deploy each new main to the test host (#131): python -I tools/autodeploy.py [--install [MIN] | --uninstall]

Runs in a checkout kept for deploys (a worktree with deploy.local.json and its HEAD detached, as
../tg-deploy): fetches origin/main and, when it moved since the last deploy, checks it out, fetches
the data its manifest names (tools/snapshot.py data-fetch) and runs tools/deploy.py. Without a new
commit it only fetches. A failed deploy is retried after an hour, not on every run (the host bans
repeated failed logins). The password comes from ~/.netrc (machine <host> login <user> password …)
or TRAM_DEPLOY_PASSWORD: there is nobody to ask.

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
    new, st = git("rev-parse", "origin/main"), load_state()
    if new == st.get("deployed"):
        return 0
    if new == st.get("failed") and time.time() - st.get("failed_at", 0) < RETRY:
        return 0
    print(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {new[:7]} {git('log', '-1', '--format=%s', new)}", file=log)
    ok = (run(log, "git", "checkout", "-q", "--detach", new) == 0
          and run(log, python(), "-I", "tools/snapshot.py", "data-fetch") == 0
          and run(log, python(), "-I", "tools/deploy.py") == 0)
    if ok:
        st = {"deployed": new, "at": time.time()}
    else:
        st.update(failed=new, failed_at=time.time())
        print(f"deploy of {new[:7]} failed; next try in {RETRY // 60} min", file=log)
    save_state(st)
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
