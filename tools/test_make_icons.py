# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/make_icons.py draws the committed icons: python -P -E tools/test_make_icons.py"""
import contextlib
import io
import os
import sys
import tempfile
import unittest

from PIL import Image, ImageChops

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_icons  # noqa: E402

COMMITTED = os.path.join(make_icons.ROOT, "assets", "icons")


class Icons(unittest.TestCase):
    def test_sizes_and_the_committed_pixels(self):
        with tempfile.TemporaryDirectory() as out:
            with contextlib.redirect_stdout(io.StringIO()):
                make_icons.main(["--out", out])
            for s in make_icons.SIZES:
                new = Image.open(os.path.join(out, f"icon-{s}.png")).convert("RGB")
                self.assertEqual(new.size, (s, s))
                if not os.path.exists(make_icons.FONTS[0]):
                    continue  # (another font draws other letters: the sizes only)
                old = Image.open(os.path.join(COMMITTED, f"icon-{s}.png")).convert("RGB")
                self.assertIsNone(ImageChops.difference(new, old).getbbox(), f"icon-{s}.png differs from the committed one")


if __name__ == "__main__":
    unittest.main(verbosity=2)
