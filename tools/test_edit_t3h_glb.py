# SPDX-License-Identifier: AGPL-3.0-or-later
"""Check the hybrid's GLB editor (#525): python -I tools/test_edit_t3h_glb.py.

Edits the model as it was before #525 (from git, commit BEFORE) and compares: the old buffer is the new one's start,
every old accessor, view, material and transform unchanged, the named parts where the rig roles had them, the saloon's
parts those the loader's old rule picked in the body; the shipped model is that edit's output, and a second run
leaves it alone.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import edit_t3h_glb as e  # noqa: E402

BEFORE = "28ea29b"  # main before #525: the model as the asset lab left it
GLB = "assets/t3h/tatra-t3-hybrid-nc.glb"


def old_model(tmp):
    data = subprocess.run(["git", "show", f"{BEFORE}:{GLB}"], cwd=e.ROOT, capture_output=True, check=True).stdout
    path = Path(tmp) / "before.glb"
    path.write_bytes(data)
    return path


class EditHybrid(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.before = old_model(cls.tmp.name)
        cls.after = Path(cls.tmp.name) / "after.glb"
        run = subprocess.run([sys.executable, "-I", str(Path(e.__file__)), "--model", str(cls.before), "--out", str(cls.after)],
                             capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        cls.old, cls.old_bin = e.read(cls.before)
        cls.new, cls.new_bin = e.read(cls.after)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def node(self, name):
        found = [n for n in self.new["nodes"] if n.get("name") == name]
        self.assertEqual(len(found), 1, name)
        return found[0]

    def test_nothing_old_moves(self):
        self.assertEqual(self.new_bin[:len(self.old_bin)], self.old_bin)
        for key in ("accessors", "bufferViews", "materials", "animations", "textures", "images", "samplers", "skins"):
            self.assertEqual(self.new.get(key, [])[:len(self.old.get(key, []))], self.old.get(key, []), key)
        for a, b in zip(self.old["nodes"], self.new["nodes"]):
            for k in ("translation", "rotation", "scale", "matrix", "mesh"):
                self.assertEqual(a.get(k), b.get(k), a.get("name"))

    def test_parts_named_where_the_roles_had_them(self):
        for old, new in e.RENAME.items():
            i = next(k for k, n in enumerate(self.old["nodes"]) if n.get("name") == old)
            self.assertEqual(self.new["nodes"][i]["name"], new)
        # (left is -Z: the shoes on the -Z side are the left ones)
        for name in ("Track_Brake_Shoe_Rear_Left", "Track_Brake_Shoe_Front_Left"):
            lo, hi = e.box(self.new, self.node(name)["mesh"], e.IDENTITY)
            self.assertLess(hi[2], 0, name)
        for name, at in e.HEADLIGHTS.items():
            self.assertEqual(self.node(name)["translation"], at)
        for name, at in e.TAILS.items():
            self.assertEqual(self.node(name)["translation"], at)
            glow = self.node(f"{name}_Glow")
            lo, hi = e.box(self.new, glow["mesh"], e.IDENTITY)
            self.assertAlmostEqual(lo[0], -e.TAIL_SIZE[0] / 2)  # (the outer face, rearwards)
            self.assertEqual(self.new["materials"][self.new["meshes"][glow["mesh"]]["primitives"][0]["material"]]["name"], e.GLOW)

    def test_saloon_is_the_old_rule_in_the_body(self):
        base = json.loads(e.BASE_RIG.read_bytes())
        names = [n.get("name") for n in self.old["nodes"]]
        body = names.index("Body")
        picked = {names[i] for i in e.saloon_parts(self.old, base) if i in self.old["nodes"][body]["children"]}
        grouped = {self.new["nodes"][i]["name"] for i in self.node("Saloon")["children"]}
        self.assertEqual(grouped, picked)
        self.assertEqual(len(grouped), 125)

    def test_shipped_model_is_the_edit(self):
        shipped, shipped_bin = e.read(e.MODEL)
        self.assertEqual(shipped, self.new)
        self.assertEqual(bytes(shipped_bin), bytes(self.new_bin))

    def test_second_run_is_a_no_op(self):
        run = subprocess.run([sys.executable, "-I", str(Path(e.__file__)), "--model", str(self.after)],
                             capture_output=True, text=True, check=True)
        self.assertIn("already edited", run.stdout)
        self.assertEqual(e.read(self.after)[0], self.new)


if __name__ == "__main__":
    unittest.main(verbosity=2)
