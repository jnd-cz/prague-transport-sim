# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/sound_encode.py (#636): its Ogg pages, and WAVs encoded to Ogg Opus and decoded back in headless Chromium.

Usage: python -P -E tools/test_sound_encode.py

A browser test (the encoder starts Chromium through sync_playwright). The muxer: packets of 0 to 600 bytes come back
from their page as they went in, a changed byte fails the checksum, the head and tags have pages of their own, the
granules grow and the last one is pre-skip + the audio's samples. The encoder, on a generated pack (a stereo 16-bit
WAV of a tone and clicks over noise, a mono 32-bit float WAV as the user's recorder writes them): both encoded with
their length to the sample, no shift, their envelopes matching, the manifest naming the .ogg files with their WAVs
as fallbacks, at most a fifth of the WAVs' size; --check passes, then fails on a changed .ogg; a file compared with
another file's master fails. The shipped pack (assets/jnd.t2r6004) passes --check.
"""
import faulthandler
import json
import math
import os
import random
import shutil
import struct
import sys
import tempfile
import unittest
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))  # (python -P leaves it out)
import sound_encode as se  # noqa: E402
from sound_encode import read  # noqa: E402

RATE = 44100


def signal(n, seed):
    """A tone that fades in and out, two clicks, and steady noise at -40 dB."""
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        t = i / RATE
        x = 0.4 * math.sin(2 * math.pi * 440 * t) * min(1, t / 0.05, max(0, 0.45 - t) / 0.05) if t < 0.45 else 0
        for c in (0.7, 0.95):
            if c <= t < c + 0.02:
                x += 0.6 * math.exp(-(t - c) / 0.004) * math.sin(2 * math.pi * 2500 * (t - c))
        out.append(x + 0.01 * (rnd.random() * 2 - 1))
    return out


def pcm16(path, channels):
    n = int(1.3 * RATE)
    chans = [signal(n, s) for s in range(channels)]
    with wave.open(path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<" + "h" * channels, *(int(c[i] * 32767) for c in chans)) for i in range(n)))


def float32(path):
    """A mono IEEE float WAV (format 3): Python's wave module writes none."""
    data = struct.pack(f"<{int(1.1 * RATE)}f", *signal(int(1.1 * RATE), 7))
    fmt = struct.pack("<HHIIHH", 3, 1, RATE, RATE * 4, 4, 32)
    with open(path, "wb") as fh:
        fh.write(b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(data)) + b"WAVE")
        fh.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data)


class Muxer(unittest.TestCase):
    def test_pages(self):
        packets = [b"", bytes(range(254)), bytes(255), bytes(510), os.urandom(600)]
        raw = se.page(7, 3, 12345, packets, 0)
        [(flags, granule, serial, seq, back)] = se.pages(raw)
        self.assertEqual((flags, granule, serial, seq, back), (0, 12345, 7, 3, packets))
        bad = bytearray(raw)
        bad[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "checksum"):
            se.pages(bytes(bad))

    def test_opus_stream(self):
        head = se.opus_head(2, 312, RATE)
        self.assertEqual(len(head), 19)
        packets = [(bytes([i]) * (100 + i), 960) for i in range(10)]
        data = se.ogg_opus(head, packets, 9000, 99, ["TITLE=x"], per_page=3)
        ps = se.pages(data)
        self.assertEqual([p[0] for p in ps], [2, 0, 0, 0, 0, 4])
        self.assertEqual(ps[0][4], [head])
        self.assertTrue(ps[1][4][0].startswith(b"OpusTags"))
        # (a page's granule counts every sample decoded by its end, the pre-skip's too; the last one trims the end)
        self.assertEqual([p[1] for p in ps[2:]], [2880, 5760, 8640, 312 + 9000])
        self.assertEqual([q for p in ps[2:] for q in p[4]], [p for p, _ in packets])
        self.assertEqual({p[2] for p in ps}, {99})
        self.assertEqual([p[3] for p in ps], list(range(6)))
        with self.assertRaisesRegex(ValueError, "fewer than"):
            se.ogg_opus(head, packets, 9600, 99)


class Encoder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="sound-encode-")
        pcm16(os.path.join(cls.dir, "stereo.wav"), 2)
        float32(os.path.join(cls.dir, "mono-float.wav"))
        cls.manifest = {"schema": 1, "kind": "sounds", "id": "test.pack", "requires": {"t3h": ">=1"},
                        "events": {"bell": "mono-float.wav", "lineContactor.close": ["stereo.wav", "mono-float.wav"]},
                        "files": [{"path": "stereo.wav"}, {"path": "mono-float.wav"}]}
        with open(os.path.join(cls.dir, "sounds.json"), "w", encoding="utf-8") as fh:
            json.dump(cls.manifest, fh)
        cls.log = []
        cls.fails = se.run(cls.dir, log=cls.log.append)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_encoded(self):
        self.assertEqual(self.fails, [], self.log)
        m = json.loads(read(os.path.join(self.dir, "sounds.json")))
        self.assertEqual(m["events"], {"bell": "mono-float.ogg", "lineContactor.close": ["stereo.ogg", "mono-float.ogg"]})
        by = {f["path"]: f for f in m["files"]}
        self.assertEqual([f["path"] for f in m["files"]], ["stereo.wav", "stereo.ogg", "mono-float.wav", "mono-float.ogg"])
        for name in ("stereo", "mono-float"):
            ogg, wav = by[name + ".ogg"], by[name + ".wav"]
            self.assertEqual(ogg["fallback"], name + ".wav")
            self.assertEqual(ogg["bytes"], os.path.getsize(os.path.join(self.dir, name + ".ogg")))
            self.assertLess(ogg["bytes"], wav["bytes"] / 5, self.log)
            ps = se.pages(read(os.path.join(self.dir, name + ".ogg")))
            head = ps[0][4][0]
            self.assertEqual(head[9], 2 if name == "stereo" else 1)
            pre, rate = struct.unpack_from("<HI", head, 10)
            self.assertEqual(rate, RATE)
            seconds = 1.3 if name == "stereo" else 1.1
            self.assertEqual(ps[-1][1] - pre, round(seconds * RATE) * 48000 // RATE, "the last granule: the audio's samples at 48 kHz")
        # (each line: its length to the sample, the shift, the envelope)
        for line in self.log[:2]:
            self.assertIn("shift 0.00 ms", line)

    def test_check(self):
        self.assertEqual(se.run(self.dir, check=True, log=lambda s: None), [])
        path = os.path.join(self.dir, "stereo.ogg")
        keep = read(path)
        try:
            with open(path, "wb") as fh:
                fh.write(keep[:-1] + bytes([keep[-1] ^ 1]))
            fails = se.run(self.dir, check=True, log=lambda s: None)
            self.assertTrue(any(f.startswith("stereo.ogg") and "hash" in f for f in fails), fails)
        finally:
            with open(path, "wb") as fh:
                fh.write(keep)

    def test_other_master_fails(self):
        with se.Browser() as b:
            c = b.compare(read(os.path.join(self.dir, "mono-float.ogg")), read(os.path.join(self.dir, "stereo.wav")))
        self.assertTrue(se.judge(c), c)


class Shipped(unittest.TestCase):
    def test_shipped_pack(self):
        folder = os.path.join(ROOT, "assets", "jnd.t2r6004")
        if not os.path.isdir(folder):
            self.skipTest("no assets/jnd.t2r6004")
        log = []
        self.assertEqual(se.run(folder, check=True, log=log.append), [], log)
        total = sum(os.path.getsize(os.path.join(folder, f)) for f in os.listdir(folder) if f.endswith(".ogg"))
        self.assertLess(total, 150_000)


if __name__ == "__main__":
    faulthandler.dump_traceback_later(600, exit=True)  # the whole test: page.evaluate has no time limit
    unittest.main()
