"""The player's guide in two languages stays in step (#330): python -I tools/test_readme.py
Same headings by level and count, the same help markers, the same key table, and every file a link in
README.md, README.en.md or DEVELOPING.md names exists, with the heading its #anchor names. It cannot see a
changed sentence: AGENTS.md's rule asks a change to change both."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = ["README.md", "README.en.md", "DEVELOPING.md"]


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def without_code(text):
    return re.sub(r"^```.*?^```", "", text, flags=re.M | re.S)


def headings(text):
    return re.findall(r"^(#+) (.+)$", without_code(text), flags=re.M)


def anchor(title):
    """GitHub's id of a heading."""
    title = re.sub(r"[`*]", "", title.strip().lower())
    return re.sub(r"[^\w\- ]", "", title).replace(" ", "-")


class Guide(unittest.TestCase):
    def setUp(self):
        self.cs, self.en = read("README.md"), read("README.en.md")

    def test_same_headings_in_the_same_order(self):
        self.assertEqual([h[0] for h in headings(self.cs)], [h[0] for h in headings(self.en)])

    def test_each_has_one_help_part_holding_the_same_headings(self):
        for text in (self.cs, self.en):
            self.assertEqual((text.count("<!-- help -->"), text.count("<!-- /help -->")), (1, 1))
        part = lambda t: t[t.index("<!-- help -->"):t.index("<!-- /help -->")]  # noqa: E731
        self.assertEqual(len(headings(part(self.cs))), len(headings(part(self.en))))
        self.assertGreater(len(headings(part(self.en))), 3)

    def test_the_same_keys_in_the_same_order(self):
        keys = lambda t: re.findall(r"^\| `([^`]+)`", t, flags=re.M)  # noqa: E731
        en, cs = keys(self.en), keys(self.cs)
        self.assertEqual(len(en), len(cs))
        self.assertEqual([k for k in en if k != "Space"], [k for k in cs if k != "Mezerník"])

    def test_links_lead_somewhere(self):
        for name in DOCS:
            for target in re.findall(r"\]\(([^)\s]+)\)", without_code(read(name))):
                if target.startswith("http"):
                    continue
                path, _, frag = target.partition("#")
                full = os.path.join(ROOT, path) if path else os.path.join(ROOT, name)
                self.assertTrue(os.path.exists(full), f"{name}: {target}")
                if frag:
                    self.assertIn(frag, [anchor(h[1]) for h in headings(read(path or name))], f"{name}: {target}")


if __name__ == "__main__":
    unittest.main()
