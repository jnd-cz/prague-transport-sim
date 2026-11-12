# SPDX-License-Identifier: AGPL-3.0-or-later
"""Check the hybrid rig exporter with the shipped GLB: python -I tools/test_export_t3h_rig.py."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_t3h_rig import ASSET, ROLES, export_rig, read_glb  # noqa: E402


class ExportHybridRig(unittest.TestCase):
    def setUp(self):
        self.glb = read_glb(ASSET / "tatra-t3-hybrid-nc.glb")
        self.base = json.loads((ASSET / "rig.json").read_bytes())
        self.roles = json.loads(ROLES.read_bytes())

    def test_exports_all_roles_and_preserves_base_bindings(self):
        self.base["handWritten"] = {"fields": ["couplers"]}
        original = json.dumps(self.base)
        rig = export_rig(self.glb, self.base, self.roles)
        self.assertEqual(rig["revision"], 6)
        self.assertNotIn("handWritten", rig)
        self.assertEqual(rig["bogies"], self.base["bogies"])
        self.assertEqual(rig["infoPlates"], self.base["infoPlates"])
        self.assertEqual(rig["pantograph"]["clip"], "Pantograph_Lower")
        self.assertEqual([d["clip"] for d in rig["doors"]],
                         ["Door_Middle_Open", "Door_Rear_Open", "Door_Front_Open"])
        for key in ("saloon", "shoes", "couplers", "beams", "tailLamps", "fleetDigits"):
            self.assertEqual(rig[key], self.roles[key])
        self.assertEqual(json.dumps(self.base), original)

    def test_rejects_valid_clip_on_wrong_door(self):
        self.roles["doorClips"]["Front"] = "Door_Rear_Open"
        with self.assertRaisesRegex(ValueError, "door Front.*targets the wrong nodes"):
            export_rig(self.glb, self.base, self.roles)

    def test_rejects_shoe_under_wrong_bogie(self):
        self.roles["shoes"]["Bogie_Front"][0] = "Black_Metal_116"
        with self.assertRaisesRegex(ValueError, "shoe under Bogie_Front.*Black_Metal_116"):
            export_rig(self.glb, self.base, self.roles)

    def test_cli_is_repeatable_and_leaves_output_on_failure(self):
        tool = Path(__file__).with_name("export_t3h_rig.py")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "rig.json"
            cmd = [sys.executable, "-I", str(tool), "--out", str(out)]
            subprocess.run(cmd, check=True, capture_output=True)
            first = out.read_bytes()
            subprocess.run(cmd, check=True, capture_output=True)
            self.assertEqual(first, out.read_bytes())
            self.roles["couplers"]["front"] = ["Removed_Coupler"]
            roles = Path(tmp) / "roles.json"
            roles.write_text(json.dumps(self.roles), encoding="utf-8")
            fail = subprocess.run([*cmd, "--roles", str(roles)], capture_output=True)
            self.assertNotEqual(fail.returncode, 0)
            self.assertIn(b"Removed_Coupler", fail.stderr)
            self.assertEqual(first, out.read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
