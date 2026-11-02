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


def bar(W, favors, gap, second_in_firsts, them="They", surface="deck", b2=True):
    """One TradeValueBar, W pt of bar, in the surface it sits in: a deck card
    (ink1, 16pt padding), or the League example card's lower half (ink0, 12pt
    padding inside a 1pt ink.line border, the bar under a hairline with 10pt
    above it: LeagueScreen exTrade / exValueBar)."""
    league = surface == "league"
    pad, bg = (12, INK0) if league else (16, INK1)
    edge = 1 if league else 0
    img = Image.new("RGB", ((W + 2 * pad + 2 * edge) * S, 300 * S), bg)
    d = ImageDraw.Draw(img)
    x0, y = (pad + edge) * S, pad * S
    if league:                                            # exValueBar's hairline
        d.rectangle((x0, y, x0 + W * S - 1, y + S - 1), fill=LINE)
        y += S + 10 * S
    firsts = abs(gap["firsts"])
    pick = gap["pick_equivalent"]
    # B2 rule (TradeValueBar `negligible`): under 1 first with no pick label
    # reads Even. b2=False draws #567's head before it.
    even = favors in ("even", None) or (b2 and not pick and firsts < 1)
    you_win = favors == "receive"
    fill_c = ICE if even else POS if you_win else WARN
    frac = 0 if even else min(1, firsts) * (1 if you_win else -1)
    winner = None if even else "You" if you_win else them

    label(d, x0, y, "Dynasty value swing", DIM)
    y += 14 * S + 8 * S                                   # wrap gap space.sm
    y += 4 * S                                            # winner marginTop
    text(d, x0, y, "Even" if even else f"{winner} win", UI_SEMI(16), BASE if even else fill_c, 22)
    y += 22 * S + 8 * S
    x = x0
    if even:
        x += text(d, x, y, "Within a rounding error — ", UI(13), DIM, 18)
        x += text(d, x, y, f"{round(gap['value']):,}", DATA(13), BASE, 18)
        text(d, x, y, " apart" + (f" (≈ {gap['firsts']:.1f} firsts)" if gap["firsts"] else ""), UI(13), DIM, 18)
    else:
        x += text(d, x, y, "by ", UI(13), DIM, 18)
        x += text(d, x, y, ("+" if you_win else "−") + f"{round(gap['value']):,}", DATA(13), fill_c, 18)
        x += text(d, x, y, "  ·  ", UI(13), DIM, 18)
        worth = short_pick(pick["label"]) if pick else f"≈ {firsts:.1f} mid 1sts"
        x += text(d, x, y, worth, UI_SEMI(13), FIRST_1, 18)
        if pick:                                          # worthTail
            text(d, x, y, f" (≈ {firsts:.1f} firsts)", UI(13), DIM, 18)
    y += 18 * S + 8 * S                                   # wrap gap

    y += 8 * S                                            # track marginTop
    tw = W * S
    rail_top = y + 1 * S                                  # 14pt rail centred in 16
    d.rounded_rectangle((x0, rail_top, x0 + tw, rail_top + 14 * S), radius=2 * S, fill=INK3)
    mid = x0 + tw / 2
    if even:                                              # the centred 6pt nub
        d.rounded_rectangle((mid - 3 * S, rail_top, mid + 3 * S, rail_top + 14 * S), radius=2 * S, fill=ICE)
    elif frac > 0:
        d.rounded_rectangle((mid, rail_top, mid + frac * tw / 2, rail_top + 14 * S), radius=2 * S, fill=fill_c)
    else:
        d.rounded_rectangle((mid + frac * tw / 2, rail_top, mid, rail_top + 14 * S), radius=2 * S, fill=fill_c)
    second_pct = 50 - second_in_firsts * 50
    for p in (second_pct, 100 - second_pct):
        tx = x0 + tw * p / 100
        d.rectangle((tx, y - 4 * S, tx + S - 1, y + 20 * S - 1), fill=LINE)
    d.rectangle((mid - S, y - 4 * S, mid - 1, y + 20 * S - 1), fill=LINE_A11Y)
    y += 16 * S + 8 * S + 8 * S                           # wrap gap + scale row marginTop

    scale = DATA(11)
    text(d, x0, y, "−1st", scale, FAINT, 18)
    text(d, x0 + tw - 30 * S, y, "+1st", scale, FAINT, 18)
    frame_x, frame_w = x0 + 30 * S, tw - 60 * S
    for p, s_ in ((second_pct, "−2nd"), (50, "Even"), (100 - second_pct, "+2nd")):
        cx = frame_x + frame_w * p / 100                  # the 12pt middle frame,
        text(d, cx - width(d, s_, scale) / 2, y + 3 * S, s_, scale, FAINT, 18)  # centred in 18
    y += 18 * S + 8 * S + 4 * S                           # wrap gap + end row marginTop
    them_end = f"{them} win"
    label(d, x0, y, them_end, fill_c if winner == them else DIM)
    yw = width(d, "YOU WIN", UI_SEMI(11), 0.88)
    label(d, x0 + tw - yw, y, "You win", fill_c if you_win and not even else DIM)
    y += 14 * S + 8 * S                                   # wrap gap
    wy = y + 9 * S                                        # "Why?" row, minHeight 32
    label(d, x0, wy, "Why?", DIM)
    cx, cy = x0 + tw - 7 * S, wy + 7 * S                  # chevron-down, 14pt
    d.line((cx - 4 * S, cy - 2 * S, cx, cy + 2 * S, cx + 4 * S, cy - 2 * S), fill=DIM, width=round(1.5 * S))
    y += 32 * S + pad * S
    img = img.crop((0, 0, img.width, y + edge * S))
    if league:                                            # the card's border
        d = ImageDraw.Draw(img)
        w_, h_ = img.width, img.height
        d.rounded_rectangle((0, -8 * S, w_ - 1, h_ - 1), radius=8 * S, outline=LINE, width=S)
    return img


TICK_COLS = [("Before (main): ±2nd tick at 0.57", 0.57, True),
             ("After (#567): ±2nd tick at 0.287", 0.287, True)]


def sheet(name, W, cases, them="They", surface="deck", cols=TICK_COLS):
    """Rows of cases, a before and an after column each (title, tick, B2 rule)."""
    tiles = [[bar(W, favors, gap_b if i == 0 else gap_a, second, them, surface, b2)
              for i, (_, second, b2) in enumerate(cols)]
             for _, favors, gap_b, gap_a in cases]
    m, top, gap_x, row_h = 16 * S, 34 * S, 32 * S, 26 * S
    tw, th = tiles[0][0].width, max(t.height for row in tiles for t in row)
    out = Image.new("RGB", (2 * m + 2 * tw + gap_x, top + len(cases) * (th + row_h) + 22 * S), INK0)
    d = ImageDraw.Draw(out)
    for i, (title, *_) in enumerate(cols):
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
# A deck card on a 375pt phone (317pt of bar; TradeCard passes the partner's
# handle as themLabel). The calculator's bar is 309pt, the same drawing.
even = {**gap_for(250), "pick_equivalent": None}
sheet("before-after-317.png", 317, [
    ("You win by an Early 2nd: the fill ends past the +2nd tick (it stopped short of it before)",
     "receive", gap_for(early_2nd), gap_for(early_2nd)),
    ("@mike_dynasty wins by a Mid 2nd: the fill ends on the −2nd tick",
     "give", gap_for(mid_2nd), gap_for(mid_2nd)),
    ("Even (250 apart): the centred nub, unchanged; only the ticks move",
     "even", even, even),
], them="@mike_dynasty")
# The League "Works right now" example card (283pt of bar): main's fixture
# (380, 0.6 firsts, "a Mid 2nd") before, today's Mid 2nd after (P2-1).
old_example = {"value": 380, "firsts": 0.6,
               "pick_equivalent": {"label": "Mid 2nd Round Pick", "value": 380}}
new_example = {"value": 607, "firsts": 0.29,
               "pick_equivalent": {"label": "Mid 2nd Round Pick", "value": 606.5}}
sheet("before-after-283.png", 283, [
    ("League \"Works right now\" example: \"a Mid 2nd\", ending on the +2nd tick after",
     "receive", old_example, new_example),
], surface="league")
# B2 rule (Product P112, 11-02): a lean with no pick label shows "≈ N mid
# 1sts" only at a gap of at least one first; under that it reads Even.
mid_1st = elo_to_value(GENERIC_PICK_SEEDS[(1, "Mid")])
tiny = {"value": 40, "firsts": round(40 / mid_1st, 2), "pick_equivalent": None}
# Past 1.25x the largest generic pick, _pick_gap_equivalent has no label.
big = gap_for(round(1.3 * max(elo_to_value(v) for v in GENERIC_PICK_SEEDS.values())))
assert big["pick_equivalent"] is None and abs(big["firsts"]) >= 1
sheet("before-after-b2-317.png", 317, [
    ("A low-value trade 40 apart (no pick label: under half the smallest pick)",
     "receive", tiny, tiny),
    (f"@mike_dynasty wins by {big['firsts']:.1f} firsts (no single pick fits): unchanged",
     "give", big, big),
    ("You win by a Mid 2nd (a pick label): unchanged",
     "receive", gap_for(mid_2nd), gap_for(mid_2nd)),
], them="@mike_dynasty", cols=[
    ("Before (#567 @ e70ad147): a lean, \"≈ 0.0 mid 1sts\"", 0.287, False),
    ("After (B2 rule): under 1 first, no pick label → Even", 0.287, True),
])
print("ok")
