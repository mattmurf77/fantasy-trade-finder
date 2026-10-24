"""Render the two static OG cards from og.html with headless Chrome.

    python3 -I docs/design/og/source/render.py

Writes docs/design/og/og-invite-1200x630.png and og-trade-expired-1200x630.png:
1200x630, RGB, no alpha, sRGB. Offline: fonts and the ram sprite load from disk.
Set CHROME to override the browser path.
"""
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, PngImagePlugin

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
TEMPLATE = HERE / "og.html"
CHROME = os.environ.get(
    "CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)
W, H = 1200, 630
INK_0 = (0x0C, 0x0E, 0x11)
GUTTER = 48  # min space between the text column and the ram box
CARDS = {
    "invite": OUT / "og-invite-1200x630.png",
    "expired": OUT / "og-trade-expired-1200x630.png",
}


def chrome(profile, *args):
    cmd = [
        CHROME,
        "--headless",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        "--force-color-profile=srgb",
        f"--window-size={W},{H}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--virtual-time-budget=10000",
        *args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)


def check_layout(profile, url):
    dom = chrome(profile, "--dump-dom", url).stdout
    m = re.search(r'data-report="([^"]*)"', dom)
    assert m, "layout self-check did not run"
    r = json.loads(html.unescape(m.group(1)))
    assert r["faces"] and all(f.endswith(":loaded") for f in r["faces"]), r["faces"]
    assert r["lineRects"] == 1 and not r["lineOverflow"], ("line wrapped or clipped", r)
    assert r["lineTextRight"] <= r["box"][0] - GUTTER, ("line runs into the ram box gutter", r)
    assert r["logoTextRight"] <= r["box"][0] - GUTTER, ("logotype runs into the ram box gutter", r)
    assert r["lineBottom"] < r["ruleTop"] and r["box"][3] < r["ruleTop"], ("collides with rule", r)
    assert r["box"][2] - r["box"][0] == 384 and r["box"][3] - r["box"][1] == 384, r["box"]
    return r


def flatten(src, dst):
    im = Image.open(src)
    im.load()
    assert im.size == (W, H), im.size
    bg = Image.new("RGB", im.size, INK_0)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg.paste(im, mask=im.split()[3])
    else:
        bg.paste(im.convert("RGB"))
    info = PngImagePlugin.PngInfo()
    info.add(b"sRGB", b"\x00")  # pixels are already sRGB (--force-color-profile=srgb)
    bg.save(dst, "PNG", pnginfo=info, optimize=True)
    out = Image.open(dst)
    assert out.size == (W, H) and out.mode == "RGB", (out.size, out.mode)
    assert out.getpixel((4, 4)) == INK_0, out.getpixel((4, 4))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        profile = Path(tmp) / "profile"
        for card, dst in CARDS.items():
            url = TEMPLATE.as_uri() + f"?card={card}"
            r = check_layout(profile, url)
            shot = Path(tmp) / f"{card}.png"
            chrome(profile, f"--screenshot={shot}", url)
            flatten(shot, dst)
            print(
                f"{dst.relative_to(OUT.parent.parent.parent)}  "
                f"logotype {r['logoFontPx']:g}px, line {r['lineFontPx']:g}px, "
                f"line ends x={r['lineTextRight']:.0f} (box at x={r['box'][0]:.0f})"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
