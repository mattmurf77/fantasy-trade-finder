"""Before/after mocks of ShareTradeImage's card for the operator's design OK
(C2, #566). Pillow draws the card's layout from the code, in the Chalkline
tokens and the card's own fonts; it is not a device capture (D-056).

What it mirrors, by file:
- ShareTradeImage.tsx: the card (360 wide, ink0, a 1px ink.line border,
  padding space.lg, gap space.md); caption and side titles in type.label;
  rows of PositionChip, name (type.bodySm in chalk.base) and either the
  TierBadge or a pick's value (type.data); the divider; the verdict line
  (type.title, centred); the footer (wordmark, then the URL, 11/14 Archivo
  SemiBold in chalk.faint, gap 2, the URL shrunk to fit down to 0.8).
  Main's card adds each side's TOTAL row (a hairline, then TOTAL in
  type.label chalk.dim and the figure in type.data). That figure is the
  evaluation's give_value / receive_value, the package value after its
  adjustments, not the rows' sum: drawn here from the backend's own
  trade_optimizer._consensus_packages over the mock's values, as
  /api/trade/evaluate computes it; main's calculator verdict likewise comes
  from _fairness_v3 ("even" at a ratio of 0.95 or more, else "fair" or
  "unfair") and the favoured side.
- TierBadge.tsx / PositionChip.tsx, size sm: a 1px border in the tier's or
  position's colour (a pick's: ink.lineStrong), padding 4 by 1, radius xs,
  the label in type.label (uppercase, tracked) in chalk.base. Tier labels
  are the pick-value ladder's ("2 1sts", "1 1st", ...).
- Picks, as each host builds them:
  - the live calculator's are the pool's generic rungs from
    /api/trade/values: a year-less name ("Late 1st Round Pick",
    pick_values.generic_pick_label), a stand-in position (_PICK_POS: a 1st
    is "RB") and a ladder tier, so the card draws an RB chip and a tier
    badge (TradeCalculatorScreen's tierFor is null only for pos "PICK");
  - the in-league calculator's are the user's owned league picks
    ("2027 2nd", server._owned_pick_label), pos "PICK" and no tier, so the
    card draws a PICK chip and the pick's number. A package holding one
    skips the mint (hasPickAssets), so its URL is the ?ref= rung.
- theme/chalkline.ts and theme/colors.ts: every colour and type size.

Run from the repo root (fonts from the shared mobile deps):
  python3 docs/plans/share-text-c2/renders/render.py
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from backend.trade_optimizer import _consensus_packages, _fairness_v3  # noqa: E402

FONTS = Path("/Users/teresadickens/ftf-worktrees/mobile-deps/mobile/node_modules/@expo-google-fonts")
OUT = Path(__file__).resolve().parent
S = 2  # drawn at 2x

INK0, INK1, LINE, LINE_STRONG = "#0C0E11", "#13161B", "#262C35", "#3D4654"
BASE, DIM, FAINT = "#ECEFF4", "#97A1AE", "#626C79"
POSITION = {"QB": "#f97316", "RB": "#22c55e", "WR": "#3b82f6", "TE": "#a855f7"}
TIER = {"firsts_4plus": "#f87171", "firsts_3": "#e879f9", "firsts_2": "#fbbf24",
        "first_1": "#2dd4bf", "second": "#38bdf8", "third": "#f472b6",
        "fourth": "#a3e635", "waivers": "#7a7f96"}
TIER_LABEL = {"firsts_4plus": "4+ 1sts", "firsts_3": "3 1sts", "firsts_2": "2 1sts",
              "first_1": "1 1st", "second": "2nd", "third": "3rd", "fourth": "4th",
              "waivers": "FA"}


def font(family, weight, size):
    name = family.replace("-", " ").title().replace(" ", "")
    return ImageFont.truetype(str(FONTS / family / weight / f"{name}_{weight}.ttf"), size * S)


# type.* (size, line height, letter spacing, uppercase)
LABEL = (lambda: font("archivo", "600SemiBold", 11), 14, 0.88, True)
BODY_SM = (lambda: font("archivo", "400Regular", 13), 18, 0, False)
DATA = (lambda: font("ibm-plex-mono", "500Medium", 13), 18, 0, False)
TITLE = (lambda: font("archivo", "600SemiBold", 16), 22, 0, False)
FOOTER = (lambda: font("archivo", "600SemiBold", 11), 14, 0, False)
WORDMARK = (lambda: font("archivo", "600SemiBold", 11), 14, 0.8, False)


def width(d, text, style, scale=1.0):
    f, _, ls, upper = style
    text = text.upper() if upper else text
    fnt = f() if scale == 1.0 else font("archivo", "600SemiBold", 11 * scale)
    return d.textlength(text, font=fnt) + ls * S * max(len(text) - 1, 0)


def draw_text(d, x, y, text, style, fill, scale=1.0):
    """Top-left at (x, y) of a line box of the style's line height; letter
    spacing drawn per character, as RN applies it."""
    f, lh, ls, upper = style
    text = text.upper() if upper else text
    fnt = f() if scale == 1.0 else font("archivo", "600SemiBold", 11 * scale)
    asc, desc = fnt.getmetrics()
    ty = y + (lh * S - (asc + desc)) / 2
    for ch in text if ls else [text]:
        d.text((x, ty), ch, font=fnt, fill=fill)
        x += d.textlength(ch, font=fnt) + ls * S


def outlined_label(d, x_right, y_mid, text, border):
    """TierBadge / PositionChip at size sm, right-aligned when x_right is a
    right edge, else left-aligned at -x_right."""
    w = width(d, text, LABEL) + 2 * 4 * S + 2 * S
    h = (14 + 2 * 1) * S + 2 * S
    x0 = x_right - w if x_right > 0 else -x_right
    y0 = y_mid - h / 2
    d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=2 * S, outline=border, width=S)
    draw_text(d, x0 + 5 * S, y0 + 2 * S, text, LABEL, BASE)
    return x0, w


def card(caption, sides, verdict, url, totals=None):
    W, pad, gap = 360 * S, 16 * S, 12 * S
    img = Image.new("RGB", (W, 1000 * S), INK0)
    d = ImageDraw.Draw(img)
    y = pad
    draw_text(d, pad, y, caption, LABEL, DIM)
    y += 14 * S + gap
    for i, (title, assets) in enumerate(sides):
        if i:
            d.rectangle((pad, y, W - pad - 1, y + S - 1), fill=LINE)
            y += S + gap
        draw_text(d, pad, y, title, LABEL, BASE)
        y += 14 * S
        for pos, asset_id, tier in assets:
            name = NAMES[asset_id]
            y += 4 * S                                   # side gap space.xs
            row_h = 20 * S                               # the chip's height sets the row
            mid = y + row_h / 2
            chip_x, chip_w = outlined_label(d, -pad, mid, pos, POSITION.get(pos, LINE_STRONG))
            name_x = chip_x + chip_w + 8 * S
            draw_text(d, name_x, mid - 9 * S, name, BODY_SM, BASE)
            if tier:
                outlined_label(d, W - pad, mid, TIER_LABEL[tier], TIER[tier])
            else:
                value = f"{round(VALUES[asset_id]):,}"   # Math.round(a.value).toLocaleString()
                draw_text(d, W - pad - width(d, value, DATA), mid - 9 * S, value, DATA, BASE)
            y += row_h
        if totals:
            y += 4 * S
            d.rectangle((pad, y, W - pad - 1, y + S - 1), fill=LINE)
            y += S + 4 * S                               # paddingTop space.xs
            total = f"{round(totals[i]):,}"
            draw_text(d, pad, y + 2 * S, "TOTAL", LABEL, DIM)
            draw_text(d, W - pad - width(d, total, DATA), y, total, DATA, BASE)
            y += 18 * S
        y += gap
    lines, cur = [], ""
    for word in verdict.split(" "):                      # the centred Text wraps
        trial = (cur + " " + word).strip()
        if width(d, trial, TITLE) > W - 2 * pad and cur:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    lines.append(cur)
    for line in lines:
        draw_text(d, (W - width(d, line, TITLE)) / 2, y, line, TITLE, BASE)
        y += 22 * S
    y += gap
    mark = "Dynasty Trade Finder"
    draw_text(d, (W - width(d, mark, WORDMARK)) / 2, y, mark, WORDMARK, FAINT)
    y += 14 * S + 2 * S
    scale = 1.0                                          # adjustsFontSizeToFit, min 0.8
    while width(d, url, FOOTER, scale) > W - 2 * pad and scale > 0.8:
        scale = round(scale - 0.02, 2)
    draw_text(d, (W - width(d, url, FOOTER, scale)) / 2, y, url, FOOTER, FAINT, scale)
    y += 14 * S + pad
    img = img.crop((0, 0, W, y))
    framed = Image.new("RGB", (W + 2 * S, y + 2 * S), LINE)
    framed.paste(img, (S, S))
    return framed


def pair(name, left_label, before, right_label, after):
    gap, top, margin = 40 * S, 36 * S, 16 * S
    H = max(before.height, after.height) + top + 30 * S
    W = before.width + after.width + gap + 2 * margin
    out = Image.new("RGB", (W, H), INK1)
    d = ImageDraw.Draw(out)
    draw_text(d, margin, 12 * S, left_label, LABEL, DIM)
    draw_text(d, margin + before.width + gap, 12 * S, right_label, LABEL, DIM)
    out.paste(before, (margin, top))
    out.paste(after, (margin + before.width + gap, top))
    note = ("Mock of ShareTradeImage's layout from the code (Chalkline tokens, the card's fonts); "
            "not a device capture (D-056)")
    d.text((margin, H - 20 * S), note, font=font("archivo", "400Regular", 10), fill=FAINT)
    out.save(OUT / name)


# Each asset by a real-shaped id, because the backend's package math decides
# by the id's shape: a generic rung's `generic_pick_1_*` id gets #427's
# first-round exemption (trade_service.first_round_pick_mask), which a display
# name would not (release-lead's #566 re-check P2-1). Players carry
# Sleeper-shaped ids; an owned league pick is `<league>_<season>_<round>_<roster>`.
# Values are on the elo_to_value scale and illustrative for players. The Late
# 1st is the generic rung at its seed (elo_to_value(1580), first_1 for an RB).
# The league pick is today's DynastyProcess SF TEP price for a 2027 2nd, the
# pool_value the in-league card draws (_priced_pick_value).
NAMES = {"8146": "Garrett Wilson", "8155": "Breece Hall", "6904": "Jalen Hurts",
         "generic_pick_1_late": "Late 1st Round Pick", "9484": "Sam LaPorta",
         "9758": "C.J. Stroud", "1048123456789012345_2027_2_4": "2027 2nd"}
VALUES = {"8146": 4630, "8155": 5210, "6904": 6400, "generic_pick_1_late": 1491.8,
          "9484": 2450, "9758": 6500, "1048123456789012345_2027_2_4": 434.1}


def evaluation(sides):
    """Main's TOTALs and the calculator's verdict, as /api/trade/evaluate
    computes them (server.py: _consensus_packages, _fairness_v3 at the 0.75
    default, _value_verdict_payload's favours)."""
    give, recv = ([aid for _, aid, _ in assets] for _, assets in sides)
    value = VALUES.__getitem__
    gv, rv = _consensus_packages(give, recv, value)
    fairness, ratio, *_ = _fairness_v3(give, recv, value, None, 0.75)
    even = ratio >= 0.95
    verdict = "even" if even else "fair" if fairness is not None else "unfair"
    favors = "even" if even else "receive" if rv > gv else "give"
    return (round(gv, 1), round(rv, 1)), verdict, favors


calc = [("Side A sends", [("WR", "8146", "firsts_2"), ("RB", "8155", "firsts_2")]),
        ("Side B sends", [("QB", "6904", "firsts_3"), ("RB", "generic_pick_1_late", "first_1")])]
calc_totals, verdict, favors = evaluation(calc)
calc_line = f"Verdict: {verdict}" + {"give": " · Side A sends more",
                                      "receive": " · Side B sends more"}.get(favors, "")
calc_url = "fantasy-trade-finder.onrender.com/s/p/Hk3x9Q2a?ref=yourname"
pair("calculator-before-after.png",
     "Before (main)",
     card("Trade idea · 1QB PPR", calc, calc_line, calc_url, calc_totals),
     "After (#566)",
     card("Trade idea · 1QB PPR", calc, "Package value", calc_url))

league = [("You send", [("WR", "8146", "firsts_2"), ("TE", "9484", "first_1")]),
          ("You receive", [("QB", "9758", "firsts_3"), ("PICK", "1048123456789012345_2027_2_4", None)])]
league_totals, _, _ = evaluation(league)
league_url = "fantasy-trade-finder.onrender.com/?ref=yourname"   # a pick: no mint
pair("in-league-before-after.png",
     "Before (main), the opponent's board diverges",
     card("vs @mike_dynasty · SF TEP", league,
          "Wins by my board — @mike_dynasty likely disagrees", league_url, league_totals),
     "After (#566)",
     card("vs @mike_dynasty · SF TEP", league, "Package value", league_url))
print("ok")
