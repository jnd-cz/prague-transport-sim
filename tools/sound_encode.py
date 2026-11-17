# SPDX-License-Identifier: AGPL-3.0-or-later
"""A sound pack's playback files in Ogg Opus (#636): each event's and loop's WAV or MP3 encoded beside it as an
.ogg, which the manifest then names, the original staying among its files as the .ogg's `fallback` (a browser that
cannot decode Opus plays it: docs/vehicles.md, Sound packs).

Usage: python -P -E tools/sound_encode.py assets/<id> [--kbps 64] [--check]

The encoder is Chromium's WebCodecs AudioEncoder (headless, Playwright, as the tests): the master decoded and
resampled to Opus's 48 kHz by the browser, encoded in 20 ms frames, and written here into Ogg pages (RFC 7845) with
the encoder's pre-skip and an end granule that trims its padding. Every file is decoded back in the browser and
compared with its master: the length within one frame, no shift over 1 ms, the loudness envelope (10 ms windows)
correlated at 0.98 and the peak within 1.5 dB; a file that fails is not written. The manifest (`sounds.json`, else
`package.json`) gets the .ogg names in `events` and `loops` and each file's `bytes` and `sha256`.

--kbps: the bitrate of a mono file (default 64); a stereo one gets 1.5 times it. --check: writes nothing; checks
that every .ogg the manifest names decodes as its fallback sounds and has the size and hash the manifest says.
Exit code 1 on a failure.
"""
import argparse
import base64
import faulthandler
import hashlib
import json
import os
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))  # (python -P leaves it out)
from atomic import replacing  # noqa: E402

FRAME = 960          # samples at 48 kHz: one 20 ms Opus frame
LIMITS = {"frames": 1, "shift_ms": 1.0, "envelope": 0.98, "peak_db": 1.5}
VENDOR = b"libopus (Chromium WebCodecs), tools/sound_encode.py"


# --- Ogg (RFC 3533) and Ogg Opus (RFC 7845) ---------------------------------------------------------------------

def _table():
    out = []
    for i in range(256):
        r = i << 24
        for _ in range(8):
            r = ((r << 1) ^ 0x04C11DB7) if r & 0x80000000 else r << 1
        out.append(r & 0xFFFFFFFF)
    return out


CRC = _table()


def crc32(data):
    """Ogg's CRC: polynomial 0x04C11DB7, not reflected, starting at 0 (not zlib's)."""
    c = 0
    for b in data:
        c = ((c << 8) & 0xFFFFFFFF) ^ CRC[(c >> 24) ^ b]
    return c


def page(serial, seq, granule, packets, flags=0):
    """One Ogg page holding whole packets: their lacing values (255s and a remainder under 255, a 0 after a packet
    of a multiple of 255 bytes), the granule position at the end of the last one, the checksum over it all."""
    lacing = []
    for p in packets:
        lacing += [255] * (len(p) // 255) + [len(p) % 255]
    if len(lacing) > 255:
        raise ValueError("more than 255 lacing values on one page")
    head = struct.pack("<4sBBqIIIB", b"OggS", 0, flags, granule, serial, seq, 0, len(lacing)) + bytes(lacing)
    body = b"".join(packets)
    c = crc32(head + body)
    return head[:22] + struct.pack("<I", c) + head[26:] + body


def opus_head(channels, pre_skip, rate):
    """The identification header (RFC 7845, 5.1): version 1, mapping family 0 (mono or stereo)."""
    return struct.pack("<8sBBHIhB", b"OpusHead", 1, channels, pre_skip, rate, 0, 0)


def opus_tags(comments=()):
    out = b"OpusTags" + struct.pack("<I", len(VENDOR)) + VENDOR + struct.pack("<I", len(comments))
    for c in comments:
        c = c.encode()
        out += struct.pack("<I", len(c)) + c
    return out


def ogg_opus(head, packets, total, serial, comments=(), per_page=50):
    """The file: head and tags each on a page of their own, then the audio packets (bytes, samples at 48 kHz) about
    a second to a page. The last page's granule is pre-skip + total, the audio's own samples at 48 kHz: fewer than
    the packets hold, so the decoder drops the encoder's padding at the end (RFC 7845, 4.4)."""
    pre = struct.unpack_from("<H", head, 10)[0]
    if pre + total > sum(n for _, n in packets):
        raise ValueError(f"the packets hold {sum(n for _, n in packets)} samples, fewer than pre-skip {pre} + {total}")
    serial &= 0xFFFFFFFF
    out = [page(serial, 0, 0, [head], 0x02), page(serial, 1, 0, [opus_tags(comments)])]
    seq, granule, i = 2, 0, 0
    while i < len(packets):
        group, lacing = [], 0
        while i < len(packets) and len(group) < per_page and lacing + len(packets[i][0]) // 255 + 1 <= 255:
            group.append(packets[i][0])
            lacing += len(packets[i][0]) // 255 + 1
            granule += packets[i][1]
            i += 1
        last = i == len(packets)
        out.append(page(serial, seq, pre + total if last else granule, group, 0x04 if last else 0))
        seq += 1
    return b"".join(out)


def pages(data):
    """[(flags, granule, serial, seq, [packets])] of an Ogg stream whose pages each end on a packet; raises on a bad
    capture pattern or checksum (the tests read the files back with it)."""
    out, at = [], 0
    while at < len(data):
        if data[at:at + 4] != b"OggS":
            raise ValueError(f"no page at byte {at}")
        _, flags, granule, serial, seq, crc, n = struct.unpack_from("<BBqIIIB", data, at + 4)
        lacing = data[at + 27:at + 27 + n]
        size = 27 + n + sum(lacing)
        raw = bytearray(data[at:at + size])
        raw[22:26] = b"\0\0\0\0"
        if crc32(raw) != crc:
            raise ValueError(f"page {seq}: checksum")
        packets, cur, body = [], b"", at + 27 + n
        for v in lacing:
            cur += data[body:body + v]
            body += v
            if v < 255:
                packets.append(cur)
                cur = b""
        if cur:
            raise ValueError(f"page {seq}: a packet continues on the next page")
        out.append((flags, granule, serial, seq, packets))
        at += size
    return out


def wav_rate(data):
    """A WAV's sample rate from its fmt chunk (for the head's informational input rate), else 0 (unspecified)."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return 0
    at = 12
    while at + 8 <= len(data):
        cid, size = data[at:at + 4], struct.unpack_from("<I", data, at + 4)[0]
        if cid == b"fmt " and size >= 8:
            return struct.unpack_from("<I", data, at + 12)[0]
        at += 8 + size + (size & 1)
    return 0


# --- the browser ---------------------------------------------------------------------------------------------------

JS = r"""
const bytes = (b64) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
const b64 = (u8) => { let s = ''; for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode(...u8.subarray(i, i + 0x8000)); return btoa(s); };
const decode = (b) => new OfflineAudioContext(1, 1, 48000).decodeAudioData(bytes(b).buffer);
window.encode = async ({ master, kbps }) => {
  const buf = await decode(master), ch = buf.numberOfChannels, n = buf.length;
  const data = new Float32Array(n * ch);
  for (let c = 0; c < ch; c++) data.set(buf.getChannelData(c), c * n);
  const config = { codec: 'opus', sampleRate: 48000, numberOfChannels: ch, bitrate: Math.round(kbps * 1000 * (ch > 1 ? 1.5 : 1)),
    opus: { frameDuration: 20000, complexity: 10 } };
  if (!(await AudioEncoder.isConfigSupported(config)).supported) throw Error('this Chromium encodes no Opus: ' + JSON.stringify(config));
  const packets = []; let head = null, err = null;
  const enc = new AudioEncoder({
    output: (chunk, meta) => {
      const b = new Uint8Array(chunk.byteLength); chunk.copyTo(b);
      packets.push([b64(b), Math.round(chunk.duration * 48000 / 1e6)]);
      if (meta?.decoderConfig?.description) { const d = meta.decoderConfig.description; head = b64(new Uint8Array(d.buffer ?? d, d.byteOffset ?? 0, d.byteLength)); }
    },
    error: (e) => { err = String(e); } });
  enc.configure(config);
  enc.encode(new AudioData({ format: 'f32-planar', sampleRate: 48000, numberOfFrames: n, numberOfChannels: ch, timestamp: 0, data }));
  await enc.flush(); enc.close();
  if (err) throw Error(err);
  return { n, ch, head, packets };
};
// the encoded file against its master, both decoded at 48 kHz and mixed to mono: lengths, the shift of the best
// match within 5 ms, the 10 ms loudness envelopes' correlation at that shift, the peaks
window.compare = async ({ ogg, master }) => {
  const mono = (b) => { const o = new Float32Array(b.length); for (let c = 0; c < b.numberOfChannels; c++) { const d = b.getChannelData(c); for (let i = 0; i < o.length; i++) o[i] += d[i] / b.numberOfChannels; } return o; };
  const a = mono(await decode(master)), b = mono(await decode(ogg)), n = Math.min(a.length, b.length);
  let lag = 0, best = -Infinity;
  for (let k = -240; k <= 240; k++) {
    let s = 0;
    for (let i = Math.max(0, -k); i < n - Math.max(0, k); i++) s += a[i] * b[i + k];
    if (s > best) { best = s; lag = k; }
  }
  const env = (x, off) => { const o = []; for (let i = Math.max(0, off); i + 480 <= n + Math.min(0, off); i += 480) { let s = 0; for (let j = i; j < i + 480; j++) s += x[j] * x[j]; o.push(Math.sqrt(s / 480)); } return o; };
  const ea = env(a, 0), eb = env(b, lag), m = Math.min(ea.length, eb.length);
  const mean = (x) => x.slice(0, m).reduce((p, q) => p + q, 0) / m, ma = mean(ea), mb = mean(eb);
  let sab = 0, saa = 0, sbb = 0;
  for (let i = 0; i < m; i++) { sab += (ea[i] - ma) * (eb[i] - mb); saa += (ea[i] - ma) ** 2; sbb += (eb[i] - mb) ** 2; }
  const peak = (x) => 20 * Math.log10(x.reduce((p, q) => Math.max(p, Math.abs(q)), 0) || 1e-9);
  return { master: a.length, ogg: b.length, lag, envelope: sab / Math.sqrt(saa * sbb || 1), peakMaster: peak(a), peakOgg: peak(b) };
};
"""


class Browser:
    """Headless Chromium on a page of its own origin (WebCodecs wants a secure context: localhost is one)."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        import gpu
        self.pw = sync_playwright().start()
        self.browser = gpu.launch(self.pw, gpu=False, quiet=True)[0]
        self.page = self.browser.new_page()
        self.page.route("http://localhost/__sound_encode.html",
                        lambda r: r.fulfill(content_type="text/html", body=f"<!doctype html><script>{JS}</script>"))
        self.page.goto("http://localhost/__sound_encode.html")
        return self

    def encode(self, master, kbps):
        return self.page.evaluate("(a) => encode(a)", {"master": base64.b64encode(master).decode(), "kbps": kbps})

    def compare(self, ogg, master):
        return self.page.evaluate("(a) => compare(a)", {"ogg": base64.b64encode(ogg).decode(), "master": base64.b64encode(master).decode()})

    def __exit__(self, *exc):
        self.browser.close()
        self.pw.stop()


def judge(c):
    """The comparison's failures (LIMITS), [] when the file sounds as its master."""
    bad = []
    if abs(c["ogg"] - c["master"]) > LIMITS["frames"] * FRAME:
        bad.append(f"{c['ogg']} samples against the master's {c['master']}")
    if abs(c["lag"]) / 48 > LIMITS["shift_ms"]:
        bad.append(f"shifted {c['lag'] / 48:.2f} ms")
    if c["envelope"] < LIMITS["envelope"]:
        bad.append(f"envelope correlation {c['envelope']:.3f}")
    if abs(c["peakOgg"] - c["peakMaster"]) > LIMITS["peak_db"]:
        bad.append(f"peak {c['peakOgg']:.1f} dB against {c['peakMaster']:.1f}")
    return bad


def encode(b, master, kbps, name):
    """(the Ogg Opus bytes, how it compares with the master) of one master file."""
    r = b.encode(master, kbps)
    pre = 312
    head = base64.b64decode(r["head"]) if r["head"] else b""
    if head[:8] == b"OpusHead":
        pre = struct.unpack_from("<H", head, 10)[0]
    head = opus_head(r["ch"], pre, wav_rate(master) or 48000)
    packets = [(base64.b64decode(p), n) for p, n in r["packets"]]
    ogg = ogg_opus(head, packets, r["n"], zlib.crc32(name.encode()), [f"TITLE={name}"])
    return ogg, b.compare(ogg, master)


def manifest_path(folder):
    for name in ("sounds.json", "package.json"):
        if os.path.isfile(os.path.join(folder, name)):
            return os.path.join(folder, name)
    raise SystemExit(f"{folder}: no sounds.json or package.json")


def named(m):
    """The files the pack plays: its events' and loops' (in the manifest's order, each once)."""
    out = []
    for f in m.get("events", {}).values():
        out += f if isinstance(f, list) else [f]
    out += [lp["file"] for lp in m.get("loops", {}).values()]
    return list(dict.fromkeys(out))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


def run(folder, kbps=64, check=False, log=print):
    """Encode (or --check) the pack in folder; returns the failures."""
    path = manifest_path(folder)
    m = json.loads(read(path))
    entries = {f["path"]: f for f in m.get("files", [])}
    fails, done = [], {}
    with Browser() as b:
        for f in named(m):
            if f.lower().endswith(".ogg"):
                fb = entries.get(f, {}).get("fallback")
                if not fb:
                    fails.append(f"{f}: no fallback to encode from or compare with")
                    continue
                master_name, target = fb, f
            elif check:
                fails.append(f"{f}: not encoded (the manifest names the master)")
                continue
            else:
                master_name, target = f, os.path.splitext(f)[0] + ".ogg"
            master = read(os.path.join(folder, master_name))
            if check:
                ogg = read(os.path.join(folder, target))
                c = b.compare(ogg, master)
            else:
                ogg, c = encode(b, master, kbps, target)
            bad = judge(c)
            log(f"{target}: {len(ogg)} bytes from {master_name} ({len(master)}), {c['ogg'] / 48000:.3f} s, shift {c['lag'] / 48:.2f} ms, "
                f"envelope {c['envelope']:.4f}, peak {c['peakOgg']:.1f}/{c['peakMaster']:.1f} dB" + (f": {'; '.join(bad)}" if bad else ""))
            fails += [f"{target}: {x}" for x in bad]
            done[f] = (target, master_name, ogg)
    if check:
        for e in m.get("files", []):
            q = os.path.join(folder, e["path"])
            data = read(q) if os.path.isfile(q) else None
            if data is None or e.get("bytes", len(data)) != len(data) or e.get("sha256", sha(data)) != sha(data):
                fails.append(f"{e['path']}: missing, or its size or hash is not the manifest's")
        return list(dict.fromkeys(fails))
    if fails:
        return fails
    for f, (target, master_name, ogg) in done.items():
        with replacing(os.path.join(folder, target), "wb") as fh:
            fh.write(ogg)
    rename = {f: target for f, (target, _, _) in done.items()}
    m["events"] = {e: [rename.get(x, x) for x in v] if isinstance(v, list) else rename.get(v, v) for e, v in m.get("events", {}).items()}
    for lp in m.get("loops", {}).values():
        lp["file"] = rename.get(lp["file"], lp["file"])
    files = []
    oggs = {target: (master_name, ogg) for target, master_name, ogg in done.values()}
    for e in m.get("files", []):
        if e["path"] in oggs:
            continue
        files.append(e)
        for target, (master_name, ogg) in oggs.items():
            if master_name == e["path"]:
                files.append({"path": target, "bytes": len(ogg), "sha256": sha(ogg), "fallback": master_name})
    # (every file's size and hash as it is now: the pack's other files may have changed with it)
    for e in files:
        data = read(os.path.join(folder, e["path"]))
        e["bytes"], e["sha256"] = len(data), sha(data)
    m["files"] = files
    with replacing(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(m, ensure_ascii=False, indent=2) + "\n")
    total = sum(len(ogg) for _, _, ogg in done.values())
    log(f"{path}: {len(done)} files in Ogg Opus, {total} bytes together")
    return []


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder")
    ap.add_argument("--kbps", type=float, default=64)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    faulthandler.dump_traceback_later(300, exit=True)  # page.evaluate has no time limit
    fails = run(args.folder, args.kbps, args.check)
    for f in fails:
        print("FAIL", f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
