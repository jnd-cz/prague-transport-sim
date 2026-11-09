"""tools/gpu.py: WebGL on the GPU where there is one, else SwiftShader: python -P -E tools/test_gpu.py."""
import faulthandler
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gpu  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


class Launch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        faulthandler.dump_traceback_later(300, exit=True)
        cls.pw = sync_playwright().start()

    @classmethod
    def tearDownClass(cls):
        cls.pw.stop()
        faulthandler.cancel_dump_traceback_later()

    def test_software_is_swiftshader(self):
        browser, name = gpu.launch(self.pw, gpu=False)
        browser.close()
        self.assertIn("SwiftShader", name)

    def test_gpu_or_the_software_fallback_has_webgl(self):
        browser, name = gpu.launch(self.pw, quiet=True)
        try:
            self.assertIsNotNone(name)
            # (on a machine with a GPU, Windows: a real adapter, e.g. ANGLE (Intel, Intel(R) Arc(TM) A770 ... D3D11))
            print(f"\n    WebGL: {name}")
        finally:
            browser.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
