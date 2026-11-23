# SPDX-License-Identifier: AGPL-3.0-or-later
"""A build step's input that may be missing (#701).

A step run alone reads an optional input where it is there: a line without surveyed streets has no
data/lineN.dtm.json, and placement, the track styles, the structures and the cross level go on without it.
tools/rebuild.py names the inputs a line's later steps need (NEEDS, paths relative to the checkout, comma-separated):
there a missing one stops the step and names the file. Placement read the survey while dtm.py wrote it, and on a first
build of a line decided its stop types from the previous build's survey, a half-written one or none (#701)."""
import os
import sys

NEEDS = "TRAM_STEP_NEEDS"


def there(path, root):
    """Whether the input at `path` is there; one that tools/rebuild.py needs (NEEDS) and is not stops the step."""
    if os.path.exists(path):
        return True
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    if rel in os.environ.get(NEEDS, "").split(","):
        sys.exit(f"{rel}: missing, and tools/rebuild.py needs it here (the step that writes it failed or did not run, #701)")
    return False
