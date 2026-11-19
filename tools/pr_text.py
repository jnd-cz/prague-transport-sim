#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A pull request names its issue (AGENTS.md, Branch, PR, merge; #727): its title ends with `(#N)` and its text says
`Closes #N` or `Part of #N`, so the squash's title links the issue and a reader sees whether the issue is done.

    python -I tools/pr_text.py                      # in CI: the pull request of the event (GITHUB_EVENT_PATH)
    python -I tools/pr_text.py "title" body.md      # by hand: a title and a file with the text

The last 60 pull requests before this check all passed it (2026-11-19). Exit code 1 with what is missing. Stdlib only;
the title and the text are read from the event's file, never from a command line a workflow builds.
"""
import json
import os
import re
import sys

TITLE = re.compile(r"\(#(\d+)\)$")
KEYWORD = re.compile(r"\b(Closes|Part of) #(\d+)")


def problems(title, body):
    """What a pull request's title and text lack, as sentences; [] when it names its issue both ways."""
    out, title, body = [], (title or "").strip(), body or ""
    t, k = TITLE.search(title), KEYWORD.findall(body)
    if not t:
        out.append("the title does not end with its issue, `(#N)`")
    if not k:
        out.append("the text says neither `Closes #N` nor `Part of #N`")
    if t and k and t.group(1) not in {n for _, n in k}:
        out.append(f"the title names #{t.group(1)}, the text {', '.join(f'{w} #{n}' for w, n in k)}")
    return out


def main(argv):
    if len(argv) == 2:
        with open(argv[1], encoding="utf-8") as f:
            title, body = argv[0], f.read()
    elif not argv and os.environ.get("GITHUB_EVENT_PATH"):
        with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
            pr = json.load(f).get("pull_request") or {}
        title, body = pr.get("title"), pr.get("body")
    else:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    bad = problems(title, body)
    for b in bad:
        print(f"pull request: {b} (AGENTS.md, Branch, PR, merge)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
