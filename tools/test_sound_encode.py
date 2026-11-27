# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/sound_encode.py (#636): its Ogg pages and MP3 info frames, and WAVs encoded to Ogg Opus and MP3 and decoded
back in headless Chromium.

Usage: python -P -E tools/test_sound_encode.py

A browser test (the encoder starts Chromium through sync_playwright; the MP3s need lameenc). The muxer: packets of 0
to 600 bytes come back from their page as they went in, a changed byte fails the checksum, the head and tags have
pages of their own, the granules grow and the last one is pre-skip + the audio's samples. The MP3 info frame: the
CRC-16 of its checksums, the frames of a stream counted, the frame count, encoder delay and padding read back, a
changed byte failing its checksum, a stream too short for its master refused. The encoder, on a generated pack (a
stereo 16-bit WAV of a tone and clicks over noise, a mono 32-bit float WAV as the maintainer's recorder writes them): both
encoded in Ogg Opus and MP3 that decode to their master's length to the sample, no shift, their envelopes matching;
the manifest naming the .ogg files, each with its MP3 as fallback and its WAV as master; the .ogg files at most a
fifth of the WAVs' size, the MP3s a third; a second run writes the same bytes; --check passes, then fails on a
changed .ogg or .mp3 and on an .ogg whose fallback is its WAV; a file compared with another file's master fails. The
shipped pack (assets/jnd.t2r6004) passes --check, and in Playwright's Firefox its Ogg Opus files and MP3 fallbacks
decode as their masters, to the sample (skipped where Firefox is not installed: docs/knowledge.md, Environment).
"""
import faulthandler
import importlib.util
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


class Mp3(unittest.TestCase):
    """The info frame on a made-up stream: ten MPEG-1 Layer III frames at 128 kbit/s, 44.1 kHz, mono, silent."""
    AUDIO = b"".join(bytes.fromhex("fffb90c0") + bytes([i]) * 413 for i in range(10))

    def test_crc16(self):
        self.assertEqual(se.crc16(b"123456789"), 0xBB3D)  # (CRC-16/ARC's check value)

    def test_frames(self):
        self.assertEqual(se.mp3_frames(self.AUDIO), [(417 * i, 417) for i in range(10)])
        with self.assertRaisesRegex(ValueError, "cut short"):
            se.mp3_frames(self.AUDIO[:-1])
        with self.assertRaisesRegex(ValueError, "no MPEG-1 Layer III frame at byte 417"):
            se.mp3_frames(self.AUDIO[:417] + b"ID3" + self.AUDIO[420:])

    def test_info(self):
        n = 10 * 1152 - 576 - 1000
        info = se.lame_info(self.AUDIO, n)
        self.assertEqual(len(info), 417)
        self.assertEqual(se.mp3_frames(info + self.AUDIO)[0], (0, 417))
        self.assertEqual(se.lame_tag(info + self.AUDIO), (10, 576, 1000))
        self.assertEqual(info[21:25], b"Xing")
        self.assertEqual(struct.unpack_from(">I", info, 33)[0], 417 + len(self.AUDIO))
        bad = bytearray(info)
        bad[160] ^= 1
        with self.assertRaisesRegex(ValueError, "checksum"):
            se.lame_tag(bytes(bad))
        with self.assertRaisesRegex(ValueError, "do not hold"):
            se.lame_info(self.AUDIO, 10 * 1152)


class Encoder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if importlib.util.find_spec("lameenc") is None:
            raise unittest.SkipTest("no lameenc: python -m pip install --user lameenc")
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
        self.assertEqual([f["path"] for f in m["files"]],
                         ["stereo.wav", "stereo.ogg", "stereo.mp3", "mono-float.wav", "mono-float.ogg", "mono-float.mp3"])
        for name in ("stereo", "mono-float"):
            ogg, mp3, wav = by[name + ".ogg"], by[name + ".mp3"], by[name + ".wav"]
            self.assertEqual((ogg["fallback"], ogg["master"], mp3["master"]), (name + ".mp3", name + ".wav", name + ".wav"))
            self.assertNotIn("fallback", mp3)
            for e in (ogg, mp3):
                self.assertEqual(e["bytes"], os.path.getsize(os.path.join(self.dir, e["path"])))
            self.assertLess(ogg["bytes"], wav["bytes"] / 5, self.log)
            self.assertLess(mp3["bytes"], wav["bytes"] / 3, self.log)
            ps = se.pages(read(os.path.join(self.dir, name + ".ogg")))
            head = ps[0][4][0]
            self.assertEqual(head[9], 2 if name == "stereo" else 1)
            pre, rate = struct.unpack_from("<HI", head, 10)
            self.assertEqual(rate, RATE)
            samples = round((1.3 if name == "stereo" else 1.1) * RATE)
            self.assertEqual(ps[-1][1] - pre, samples * 48000 // RATE, "the last granule: the audio's samples at 48 kHz")
            frames, delay, pad = se.lame_tag(read(os.path.join(self.dir, name + ".mp3")))
            self.assertEqual((delay, frames * 1152 - delay - pad), (576, samples), "the info frame: the master's samples")
        # (each line: its length, the shift, the envelope)
        self.assertEqual(len(self.log), 5, self.log)
        for line in self.log[:4]:
            self.assertIn("shift 0.00 ms", line)

    def test_lengths(self):
        """Each file decodes to its master's length to the sample (at 48 kHz), the MP3s too: the info frame's trim."""
        with se.Browser() as b:
            for name in ("stereo.ogg", "stereo.mp3", "mono-float.ogg", "mono-float.mp3"):
                c = b.compare(read(os.path.join(self.dir, name)), read(os.path.join(self.dir, name.split(".")[0] + ".wav")))
                self.assertEqual((c["file"], c["lag"]), (c["master"], 0), (name, c))

    def test_same_bytes(self):
        """A second run writes the same files."""
        names = ("sounds.json", "stereo.ogg", "stereo.mp3", "mono-float.ogg", "mono-float.mp3")
        before = [read(os.path.join(self.dir, x)) for x in names]
        self.assertEqual(se.run(self.dir, log=lambda s: None), [])
        self.assertEqual([read(os.path.join(self.dir, x)) for x in names], before)

    def test_check(self):
        self.assertEqual(se.run(self.dir, check=True, log=lambda s: None), [])
        for name in ("stereo.ogg", "mono-float.mp3"):
            path = os.path.join(self.dir, name)
            keep = read(path)
            try:
                with open(path, "wb") as fh:
                    fh.write(keep[:-1] + bytes([keep[-1] ^ 1]))
                fails = se.run(self.dir, check=True, log=lambda s: None)
                self.assertTrue(any(f.startswith(name) and "hash" in f for f in fails), fails)
            finally:
                with open(path, "wb") as fh:
                    fh.write(keep)
        path = os.path.join(self.dir, "sounds.json")
        keep = read(path)
        try:
            m = json.loads(keep)
            next(f for f in m["files"] if f["path"] == "stereo.ogg")["fallback"] = "stereo.wav"
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(m, fh)
            fails = se.run(self.dir, check=True, log=lambda s: None)
            self.assertIn("stereo.ogg: its fallback stereo.wav is not an MP3", fails)
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
        size = {k: sum(os.path.getsize(os.path.join(folder, f)) for f in os.listdir(folder) if f.endswith(k)) for k in (".ogg", ".mp3")}
        self.assertLess(size[".ogg"], 80_000)
        self.assertLess(size[".mp3"], 150_000)

    def test_shipped_pack_in_firefox(self):
        folder = os.path.join(ROOT, "assets", "jnd.t2r6004")
        if not os.path.isdir(folder):
            self.skipTest("no assets/jnd.t2r6004")
        m = json.loads(read(os.path.join(folder, "sounds.json")))
        oggs = [f for f in m["files"] if f["path"].endswith(".ogg")]
        try:
            b = se.Browser("firefox").__enter__()
        except Exception as e:
            if "Executable doesn't exist" in str(e):
                self.skipTest("no Playwright Firefox: python -m playwright install firefox")
            raise
        try:
            for f in oggs:
                master = read(os.path.join(folder, f["master"]))
                for name in (f["path"], f["fallback"]):
                    c = b.compare(read(os.path.join(folder, name)), master)
                    # (at 48 kHz: a 44.1 kHz master resampled may round to one sample more than the Opus)
                    self.assertEqual((se.judge(c), c["lag"]), ([], 0), (name, c))
                    self.assertLessEqual(abs(c["file"] - c["master"]), 1, (name, c))
        finally:
            b.__exit__(None, None, None)
        self.assertEqual(len(oggs), 5)


if __name__ == "__main__":
    faulthandler.dump_traceback_later(600, exit=True)  # the whole test: page.evaluate has no time limit
    unittest.main()
