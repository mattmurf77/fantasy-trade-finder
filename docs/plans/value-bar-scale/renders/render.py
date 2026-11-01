"""Before/after mocks of TradeValueBar for the operator's design OK (#567).
Pillow draws the component from its own styles (mobile/src/components/
TradeValueBar.tsx) in the Chalkline tokens and the app's fonts, collapsed
("Why?" closed), as every mount starts. Not a device capture (D-056).

What it mirrors, by style:
- wrap gap space.sm; the head in type.label; the winner in type.title in the
  fill colour (semantic.pos when you win, semantic.warn when they win);
  the margin line in type.bodySm chalk.dim with the value in type.data and
  the pick in Archivo SemiBold, tier first_1;
- the track: a 14pt ink3 rail, the fill from the centre by gap.firsts
  (clamped to 1) of the half-width, the ±2nd ticks (1pt, ink.line, 24pt
  tall) at 50 ∓ SECOND_IN_FIRSTS × 50 % of the track, the centre line in
  ink.lineStrongA11y;
- the scale row: the end labels in a 30pt box each, and the −2nd / Even /
  +2nd labels positioned by the same percentages but inside the row's
  middle frame (the track minus the two 30pt boxes), 11pt IBM Plex Mono
  in chalk.faint. So each ±2nd label's centre sits 30 − 60 × 0.357 ≈ 8.6pt
  inboard of its tick, as on device (release-lead's #567 QA P3, a follow-up);
- the end row in type.label, the winner's side in the fill colour; the
  collapsed "Why?" row.

Each case's gap is the server's own (_pick_gap_equivalent), so the copy and
the fill are what the app would show for that value. Run from the repo root:
  python3 docs/plans/value-bar-scale/renders/render.py
"""
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FTF_DISABLE_CLEANUP_LOOP", "1")
from backend.pick_values import GENERIC_PICK_SEEDS, generic_pick_label  # noqa: E402
from backend.trade_service import elo_to_value  # noqa: E402

FONTS = Path("/Users/teresadickens/ftf-worktrees/mobile-deps/mobile/node_modules/@expo-google-fonts")
OUT = Path(__file__).resolve().parent
S = 2  # drawn at 2x

INK0, INK1, INK3, LINE = "#0C0E11", "#13161B", "#232833", "#262C35"
LINE_A11Y = "#59647A"
BASE, DIM, FAINT = "#ECEFF4", "#97A1AE", "#626C79"
POS, WARN, ICE = "#22C55E", "#F59E0B", "#56D9EC"
FIRST_1 = "#2dd4bf"


def font(family, weight, size):
    name = family.replace("-", " ").title().replace(" ", "")
    return ImageFont.truetype(str(FONTS / family / weight / f"{name}_{weight}.ttf"), round(size * S))


UI = lambda n: font("archivo", "400Regular", n)          # noqa: E731
UI_SEMI = lambda n: font("archivo", "600SemiBold", n)    # noqa: E731
DATA = lambda n: font("ibm-plex-mono", "500Medium", n)   # noqa: E731


def text(d, x, y, s, fnt, fill, line_h, tracking=0.0):
    """Top-left at (x, y) of a line box `line_h` pt tall; returns the width."""
    asc, desc = fnt.getmetrics()
    ty = y + (line_h * S - (asc + desc)) / 2
    if not tracking:
        d.text((x, ty), s, font=fnt, fill=fill)
        return d.textlength(s, font=fnt)
    x0 = x
    for ch in s:
        d.text((x, ty), ch, font=fnt, fill=fill)
        x += d.textlength(ch, font=fnt) + tracking * S
    return x - x0 - tracking * S


def width(d, s, fnt, tracking=0.0):
    return d.textlength(s, font=fnt) + (tracking * S * (len(s) - 1) if tracking else 0)


def label(d, x, y, s, fill):
    """type.label: Archivo SemiBold 11/14, uppercase, tracked 0.88."""
    return text(d, x, y, s.upper(), UI_SEMI(11), fill, 14, 0.88)


def gap_for(value):
    """server._pick_gap_equivalent: firsts in Mid 1sts, the nearest rung."""
    values = {k: elo_to_value(v) for k, v in GENERIC_PICK_SEEDS.items()}
    firsts = round(value / values[(1, "Mid")], 2)
    pick = None
    if min(values.values()) * 0.5 <= value <= max(values.values()) * 1.25:
        (rnd, tier), v = min(values.items(), key=lambda kv: abs(kv[1] - value))
        pick = {"label": generic_pick_label(rnd, tier), "value": round(v, 1)}
    return {"value": value, "firsts": firsts, "pick_equivalent": pick}


def short_pick(label_):
    core = label_.removesuffix(" Round Pick").strip()
    return ("an " if core[0] in "AEIOU" else "a ") + core


def bar(W, favors, gap, second_in_firsts):
    """One TradeValueBar, W pt wide, on the ink1 card it sits in (16pt pad)."""
    pad = 16
    img = Image.new("RGB", ((W + 2 * pad) * S, 260 * S), INK1)
    d = ImageDraw.Draw(img)
    x0, y = pad * S, pad * S
    you_win = favors == "receive"
    fill_c = POS if you_win else WARN
    firsts = abs(gap["firsts"])
    frac = min(1, firsts) * (1 if you_win else -1)
    pick = gap["pick_equivalent"]

    label(d, x0, y, "Dynasty value swing", DIM)
    y += 14 * S + 8 * S                                   # gap space.sm
    y += 4 * S                                            # winner marginTop
    text(d, x0, y, ("You" if you_win else "They") + " win", UI_SEMI(16), fill_c, 22)
    y += 22 * S + 8 * S
    x = x0
    x += text(d, x, y, "by ", UI(13), DIM, 18)
    x += text(d, x, y, ("+" if you_win else "−") + f"{round(gap['value']):,}", DATA(13), fill_c, 18)
    x += text(d, x, y, "  ·  ", UI(13), DIM, 18)
    x += text(d, x, y, short_pick(pick["label"]), UI_SEMI(13), FIRST_1, 18)
    text(d, x, y, f" (≈ {firsts:.1f} firsts)", UI(13), DIM, 18)
    y += 18 * S + 8 * S

    y += 8 * S                                            # track marginTop
    tw = W * S
    rail_top = y + 1 * S
    d.rounded_rectangle((x0, rail_top, x0 + tw, rail_top + 14 * S), radius=2 * S, fill=INK3)
    mid = x0 + tw / 2
    if frac > 0:
        d.rounded_rectangle((mid, rail_top, mid + frac * tw / 2, rail_top + 14 * S), radius=2 * S, fill=fill_c)
    else:
        d.rounded_rectangle((mid + frac * tw / 2, rail_top, mid, rail_top + 14 * S), radius=2 * S, fill=fill_c)
    second_pct = 50 - second_in_firsts * 50
    for p in (second_pct, 100 - second_pct):
        tx = x0 + tw * p / 100
        d.rectangle((tx, y - 4 * S, tx + S - 1, y + 20 * S - 1), fill=LINE)
    d.rectangle((mid - S, y - 4 * S, mid - 1, y + 20 * S - 1), fill=LINE_A11Y)
    y += 16 * S + 8 * S                                   # scale row marginTop

    scale = DATA(11)
    text(d, x0, y, "−1st", scale, FAINT, 18)
    text(d, x0 + tw - 30 * S, y, "+1st", scale, FAINT, 18)
    frame_x, frame_w = x0 + 30 * S, tw - 60 * S
    for p, s in ((second_pct, "−2nd"), (50, "Even"), (100 - second_pct, "+2nd")):
        cx = frame_x + frame_w * p / 100
        text(d, cx - width(d, s, scale) / 2, y, s, scale, FAINT, 18)
    y += 18 * S + 4 * S                                   # end row marginTop
    label(d, x0, y, "They win", DIM if you_win else fill_c)
    yw = width(d, "YOU WIN", UI_SEMI(11), 0.88)
    label(d, x0 + tw - yw, y, "You win", fill_c if you_win else DIM)
    y += 14 * S + 8 * S
    wy = y + 9 * S                                        # "Why?" row, minHeight 32
    label(d, x0, wy, "Why?", DIM)
    cx, cy = x0 + tw - 7 * S, wy + 7 * S                  # chevron-down, 14pt
    d.line((cx - 4 * S, cy - 2 * S, cx, cy + 2 * S, cx + 4 * S, cy - 2 * S), fill=DIM, width=round(1.5 * S))
    y += 32 * S + pad * S
    return img.crop((0, 0, img.width, y))


def sheet(name, W, cases):
    """Rows of cases, a before (0.57) and an after (0.287) column each."""
    cols = [("Before (main): ±2nd tick at 0.57", 0.57), ("After (#567): ±2nd tick at 0.287", 0.287)]
    tiles = [[bar(W, favors, gap_b if i == 0 else gap_a, second) for i, (_, second) in enumerate(cols)]
             for _, favors, gap_b, gap_a in cases]
    m, top, gap_x, row_h = 16 * S, 34 * S, 32 * S, 26 * S
    tw, th = tiles[0][0].width, max(t.height for row in tiles for t in row)
    out = Image.new("RGB", (2 * m + 2 * tw + gap_x, top + len(cases) * (th + row_h) + 22 * S), INK0)
    d = ImageDraw.Draw(out)
    for i, (title, _) in enumerate(cols):
        label(d, m + i * (tw + gap_x), 12 * S, title, DIM)
    y = top
    for (caption, *_), row in zip(cases, tiles):
        text(d, m, y, caption, UI(11), FAINT, 16)
        y += row_h - 8 * S
        for i, tile in enumerate(row):
            out.paste(tile, (m + i * (tw + gap_x), y))
        y += th + 8 * S
    text(d, m, out.height - 20 * S,
         f"Mock of TradeValueBar at {W}pt from its styles (Chalkline tokens, the app's fonts); "
         "not a device capture (D-056)", UI(10), FAINT, 14)
    out.save(OUT / name)


mid_2nd = elo_to_value(GENERIC_PICK_SEEDS[(2, "Mid")])
early_2nd = elo_to_value(GENERIC_PICK_SEEDS[(2, "Early")])
# A calculator or deck card on a 375pt phone (317pt of bar).
sheet("before-after-317.png", 317, [
    ("You win by an Early 2nd: the fill ends past the +2nd tick (it stopped short of it before)",
     "receive", gap_for(early_2nd), gap_for(early_2nd)),
    ("They win by a Mid 2nd: the fill ends on the −2nd tick",
     "give", gap_for(mid_2nd), gap_for(mid_2nd)),
])
# The League "Works right now" example card (283pt of bar): main's fixture
# (380, 0.6 firsts, "a Mid 2nd") before, today's Mid 2nd after (P2-1).
old_example = {"value": 380, "firsts": 0.6,
               "pick_equivalent": {"label": "Mid 2nd Round Pick", "value": 380}}
new_example = {"value": 607, "firsts": 0.29,
               "pick_equivalent": {"label": "Mid 2nd Round Pick", "value": 606.5}}
sheet("before-after-283.png", 283, [
    ("League \"Works right now\" example: \"a Mid 2nd\", ending on the +2nd tick after",
     "receive", old_example, new_example),
])
print("ok")
