"""Review verdicts (#136): one file per review, {"meta": {...}, "items": {finding id: record}}.
src/review.js sends the records it changed; tools/serve.py (reports/reviews/), tools/review.php (on the
host) and tools/deploy.py --pull-reviews merge them by this rule: per finding, the newer "t" wins, so
a phone and a computer can review the same list. Same rule in review.php: change both."""
import json
import os
import re

NAME = re.compile(r"[a-z0-9_-]{1,64}")
MAX = 2_000_000  # bytes of one post


def merge(cur, new):
    """cur updated with new's records where they are newer; new's meta over cur's."""
    items = dict(cur.get("items") or {})
    for k, v in (new.get("items") or {}).items():
        if isinstance(k, str) and isinstance(v, dict) and (k not in items or v.get("t", 0) >= items[k].get("t", 0)):
            items[k] = v
    return {"meta": {**(cur.get("meta") or {}), **(new.get("meta") or {})}, "items": items}


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            v = json.load(fh)
        return v if isinstance(v, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def save(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)
