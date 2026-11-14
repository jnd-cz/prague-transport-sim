# SPDX-License-Identifier: AGPL-3.0-or-later
"""The sound events, loops and parameters (#528) from src/audio.js into docs/vehicles.md, so the docs cannot drift.

    python -I tools/sound_lists.py           # write the lists between the markers in docs/vehicles.md
    python -I tools/sound_lists.py --check   # exit 1 when the docs' lists differ from the code's

Reads `EVENTS`, `LOOPS` and `PARAMS` in src/audio.js (one `'name': 'what',` entry a line) and writes them between
`<!-- sound-lists -->` and `<!-- /sound-lists -->`. tools/test_vehicles.py reads the same lists to check the packs.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO = os.path.join(ROOT, "src", "audio.js")
DOC = os.path.join(ROOT, "docs", "vehicles.md")
START, END = "<!-- sound-lists -->", "<!-- /sound-lists -->"


def lists(src=None):
    """{'EVENTS': [(name, what)], 'LOOPS': [...], 'PARAMS': [...]} from src/audio.js."""
    s = src if src is not None else open(AUDIO, encoding="utf-8").read()
    out = {}
    for key in ("EVENTS", "LOOPS", "PARAMS"):
        m = re.search(r"export const " + key + r" = \{\n(.*?)\n\};", s, re.S)
        out[key] = [(a, b.replace("\\'", "'")) for a, b in re.findall(r"^\s*'([^']+)': '((?:[^'\\]|\\.)*)',?\s*$", m.group(1), re.M)] if m else []
    return out


def section(ls):
    rows = ["| event | when |", "|---|---|", *[f"| `{a}` | {b} |" for a, b in ls["EVENTS"]], "",
            "| loop | what |", "|---|---|", *[f"| `{a}` | {b} |" for a, b in ls["LOOPS"]], "",
            "| parameter | unit |", "|---|---|", *[f"| `{a}` | {b} |" for a, b in ls["PARAMS"]]]
    return "\n".join([START, "(written by `tools/sound_lists.py` from `src/audio.js`)", "", *rows, END])


def main():
    doc = open(DOC, encoding="utf-8", newline="").read()
    if START not in doc or END not in doc:
        print(f"no {START} … {END} in docs/vehicles.md")
        return 1
    new = doc[:doc.index(START)] + section(lists()) + doc[doc.index(END) + len(END):]
    if "--check" in sys.argv:
        if new != doc:
            print("docs/vehicles.md's sound lists differ from src/audio.js: python -I tools/sound_lists.py")
            return 1
        print("sound lists: docs/vehicles.md as src/audio.js")
        return 0
    if new != doc:
        open(DOC, "w", encoding="utf-8", newline="").write(new)
    print("docs/vehicles.md: the sound lists written" if new != doc else "docs/vehicles.md: the sound lists as they were")
    return 0


if __name__ == "__main__":
    sys.exit(main())
