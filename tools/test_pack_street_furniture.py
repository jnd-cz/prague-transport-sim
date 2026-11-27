# SPDX-License-Identifier: AGPL-3.0-or-later
"""Check the game pack's glTF scenes, geometry budgets and placement metadata."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edit_t3h_glb import read  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LEVELS = ("near", "middle", "far")
TRIANGLES = {
    "bin-large": (452, 196, 100),
    "bin-small-canopied": (580, 296, 140),
    "bin-recycling": (728, 392, 280),
    "cycle-stand": (344, 104, 64),
    "bollard": (152, 56, 40),
    "railing-bars": (448, 128, 80),
    "railing-glass": (450, 130, 82),
}
PASSES = dict(zip(TRIANGLES, (2, 2, 3, 1, 1, 1, 2), strict=True))


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
                    self.assertAlmostEqual(low, -.1 if kind == "bin-small-canopied" else 0, places=2)
                    self.assertGreater(high, .85)


if __name__ == "__main__":
    unittest.main()
