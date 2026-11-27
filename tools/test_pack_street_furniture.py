# SPDX-License-Identifier: AGPL-3.0-or-later
"""Check the game pack's glTF scenes, geometry budgets and placement metadata."""

from pathlib import Path
from struct import calcsize, unpack_from
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edit_t3h_glb import read  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LEVELS = ("near", "middle", "far")
TRIANGLES = {
    "bin-large": (744, 596, 460),
    "bin-small-canopied": (620, 500, 380),
    "bin-recycling": (790, 636, 494),
    "cycle-stand": (492, 240, 132),
    "bollard": (152, 56, 40),
    "railing-bars": (448, 128, 80),
    "railing-glass": (450, 130, 82),
}
PASSES = dict(zip(TRIANGLES, (2, 2, 2, 1, 1, 1, 2), strict=True))
BINS = {"bin-large": (1.015, 0), "bin-small-canopied": (1.186, .035), "bin-recycling": (1.020, 0)}


def samples(glb, binary, idx, fmt):
    a = glb["accessors"][idx]
    view = glb["bufferViews"][a["bufferView"]]
    start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = view.get("byteStride", calcsize(fmt))
    return [unpack_from(fmt, binary, start + i * stride) for i in range(a["count"])]


def covers(point, triangle):
    sides = [(b[0] - a[0]) * (point[1] - a[2]) - (b[2] - a[2]) * (point[0] - a[0])
             for a, b in zip(triangle, triangle[1:] + triangle[:1], strict=True)]
    return min(sides) >= -1e-7 or max(sides) <= 1e-7


class TestFurniturePack(unittest.TestCase):
    def test_game_pack(self):
        glb, binary = read(ROOT / "assets/furniture/ipr-street.glb")
        self.assertTrue(binary)
        scenes = {glb["nodes"][scene["nodes"][0]]["name"]: scene for scene in glb["scenes"]}
        self.assertEqual(len(glb["scenes"]), len(TRIANGLES) * len(LEVELS))
        self.assertEqual(len(scenes), len(glb["scenes"]))
        for kind, counts in TRIANGLES.items():
            for level, count in zip(LEVELS, counts, strict=True):
                name = f"{kind}--{level}"
                with self.subTest(model=name):
                    scene = scenes[name]
                    self.assertEqual(len(scene["nodes"]), 1)
                    self.assertEqual(scene["extras"]["units"], "metres")
                    self.assertIn("© IPR Praha", scene["extras"]["attribution"])
                    model = glb["nodes"][scene["nodes"][0]]
                    self.assertFalse({"matrix", "rotation", "scale", "translation"} & model.keys())
                    self.assertEqual(model["extras"], {
                        "kind": kind, "level": level, "placement": "ground", "groundY": 0, "up": [0, 1, 0],
                    })
                    triangles, passes, glass = 0, 0, 0
                    low, high = float("inf"), float("-inf")
                    for i in model["children"]:
                        mesh = glb["nodes"][i]
                        offset = mesh["matrix"][13] if "matrix" in mesh else mesh.get("translation", [0, 0, 0])[1]
                        for part in glb["meshes"][mesh["mesh"]]["primitives"]:
                            self.assertEqual(part.get("mode", 4), 4)
                            n = glb["accessors"][part["indices"]]["count"]
                            self.assertEqual(n % 3, 0)
                            triangles += n // 3
                            passes += 1
                            pos = glb["accessors"][part["attributes"]["POSITION"]]
                            low = min(low, pos["min"][1] + offset)
                            high = max(high, pos["max"][1] + offset)
                            mat = glb["materials"][part["material"]]
                            if mat.get("alphaMode") == "BLEND":
                                self.assertTrue(mesh["extras"]["singlePass"] and mat["doubleSided"])
                                glass += 1
                    self.assertEqual((triangles, passes, glass), (count, PASSES[kind], int(kind == "railing-glass")))
                    ground_limit = -.1 if kind == "bin-small-canopied" else 0
                    if kind == "cycle-stand":
                        ground_limit = -.098 if level == "near" else -.08
                        self.assertAlmostEqual(high, .9115, places=3)
                    self.assertAlmostEqual(low, ground_limit, places=2)
                    self.assertGreater(high, .85)
                    if kind in BINS:
                        steel = glb["nodes"][model["children"][0]]
                        part, = glb["meshes"][steel["mesh"]]["primitives"]
                        pos = samples(glb, binary, part["attributes"]["POSITION"], "<3f")
                        self.check_bin(glb, binary, kind, high, pos, part)

    def check_bin(self, glb, binary, kind, high, pos, part):
        height, centre = BINS[kind]
        self.assertAlmostEqual(high, height, places=3)
        cover = [(x, y, z) for x, y, z in pos if y > high - .14]
        front = max(y for _, y, z in cover if z > centre + .13)
        back = max(y for _, y, z in cover if z < centre - .13)
        self.assertGreater(front - back, .075)
        edge = max(abs(x) for x, _, z in cover if abs(z - centre) > .13)
        self.assertLess(edge, max(abs(x) for x, _, _ in cover) - .025)
        if kind == "bin-recycling":
            a = glb["accessors"][part["indices"]]
            fmt = "<I" if a["componentType"] == 5125 else "<H"
            indices = [i for i, in samples(glb, binary, part["indices"], fmt)]
            faces = [[pos[i] for i in indices[j:j + 3]] for j in range(0, len(indices), 3)]
            mouth = [face for face in faces if all(abs(p[1] - .809) < 1e-5 for p in face)]
            for x in [-.318, 0, .318]:
                self.assertFalse(any(covers((x, 0), face) for face in mouth), x)
            self.assertTrue(any(covers((.159, 0), face) for face in mouth))


if __name__ == "__main__":
    unittest.main()
