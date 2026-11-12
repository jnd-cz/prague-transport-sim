"""The site's icons (#485): python -P -E tools/make_icons.py [--out DIR]

The T3's face: a cream band on top, the red below with two round headlights in dark rings, a cream "T3" between
them, and the bumper's polished aluminium strip with its two red lines (after the user's photo of car 7000,
2026-11-11). Drawn at 512 px and scaled down to 192 and 180 (the web manifest, the iPhone's home screen) and 32
(the browsers' tab). Writes assets/icons/icon-{32,180,192,512}.png, or into DIR.
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZES = (512, 192, 180, 32)
N = 512
DARK, CREAM, RED = (29, 37, 32), (233, 228, 212), (176, 26, 30)  # (index.html's --panel-edge; the T3's livery)
# a bold sans with the letters' shapes as committed (Arial Bold); the others only where it is missing
FONTS = ("C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def font(size):
    for f in FONTS:
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    sys.exit(f"no bold font found among {', '.join(FONTS)}")


def draw():
    """The icon at N px."""
    im = Image.new("RGB", (N, N), DARK)
    d = ImageDraw.Draw(im)
    # the body: cream on top, the red below with a straight edge between, as on the car
    d.rounded_rectangle((56, 56, N - 56, N - 56), radius=64, fill=CREAM)
    d.rounded_rectangle((56, 150, N - 56, N - 56), radius=64, fill=RED)
    d.rectangle((56, 150, N - 56, 250), fill=RED)
    # the bumper: polished aluminium, bright along its top edge (a rounded rail catching the light), two red lines
    x0, x1, y0, y1 = 56, N - 56, 364, 408
    for y in range(y0, y1):
        g = int(235 - 95 * abs((y - y0) / (y1 - y0) - 0.3) ** 0.8)
        d.line((x0, y, x1 - 1, y), fill=(g, g, min(255, g + 6)))
    for ya, yb in ((372, 377), (397, 401)):
        d.rectangle((x0, ya, x1 - 1, yb), fill=RED)
    d.line((x0, y0, x1 - 1, y0), fill=(60, 60, 64), width=2)
    d.line((x0, y1, x1 - 1, y1), fill=(60, 60, 64), width=2)
    # the headlights: a lens bright towards the upper left with a glint, in a dark ring
    for cx in (130, N - 130):
        cy = 262
        d.ellipse((cx - 46, cy - 46, cx + 46, cy + 46), fill=(28, 26, 26))
        for r in range(35, 0, -1):
            g = int(150 + 100 * (1 - r / 35) ** 0.7)
            o = int((35 - r) * 0.35)
            d.ellipse((cx - r - o, cy - r - o, cx + r - o, cy + r - o), fill=(g, g, min(255, g + 8)))
        d.ellipse((cx - 19, cy - 22, cx - 7, cy - 10), fill=(255, 255, 255))
    d.text((N / 2, 266), "T3", font=font(92), fill=CREAM, anchor="mm")
    return im


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "assets", "icons"))
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    im = draw()
    for s in SIZES:
        p = os.path.join(a.out, f"icon-{s}.png")
        im.resize((s, s), Image.LANCZOS).save(p, optimize=True)
        print(p)


if __name__ == "__main__":
    main()
