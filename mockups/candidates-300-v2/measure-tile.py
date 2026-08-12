#!/usr/bin/env python3
"""Exact advance-width measurement for the shipped #299 32pt League tile.

Reads the SAME TTFs the app loads (@expo-google-fonts, version-pinned in
mobile/node_modules) so every pt number below is a real font metric, not an
eyeballed em estimate. Round 1 estimated; this measures.
"""
from fontTools.ttLib import TTFont

ROOT = "/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/mobile/node_modules/@expo-google-fonts"
FONTS = {
    "archivo400": f"{ROOT}/archivo/400Regular/Archivo_400Regular.ttf",
    "archivo500": f"{ROOT}/archivo/500Medium/Archivo_500Medium.ttf",
    "archivo600": f"{ROOT}/archivo/600SemiBold/Archivo_600SemiBold.ttf",
    "mono500": f"{ROOT}/ibm-plex-mono/500Medium/IBMPlexMono_500Medium.ttf",
    "mono600": f"{ROOT}/ibm-plex-mono/600SemiBold/IBMPlexMono_600SemiBold.ttf",
}

_cache = {}


def metrics(key):
    if key not in _cache:
        f = TTFont(FONTS[key], lazy=True)
        upem = f["head"].unitsPerEm
        cmap = f.getBestCmap()
        hmtx = f["hmtx"]
        _cache[key] = (upem, cmap, hmtx)
    return _cache[key]


def w(text, key, size, letter_spacing=0.0):
    """Advance width in pt for `text` at `size` px with RN letterSpacing."""
    upem, cmap, hmtx = metrics(key)
    total = 0.0
    for ch in text:
        gid = cmap.get(ord(ch))
        if gid is None:
            gid = cmap.get(ord("?"))
        total += hmtx[gid][0] / upem * size
    # RN letterSpacing is applied after every glyph, including the last.
    total += letter_spacing * len(text)
    return total


def badge(label, size=11, ls=0.88):
    """chalkline Badge: paddingHorizontal 6 x2 + borderWidth 1 x2 + type.label text (UPPERCASE)."""
    return w(label.upper(), "archivo600", size, ls) + 12 + 2


def microtag(label, size=11, ls=0.5):
    """PlayerCard denseTag(+Floor): paddingHorizontal 3 x2 + borderWidth 1 x2."""
    return w(label, "archivo600", size, ls) + 6 + 2


def p(name, val):
    print(f"{name:<58} {val:7.1f}pt")


print("=" * 74)
print("SHIPPED #299 TILE — exact widths (Archivo / IBM Plex Mono real metrics)")
print("=" * 74)

CONTENT = 358.0        # 390 - scroll padding 16 x2
BORDER = 2.0           # tile borderWidth 1 x2
inner = CONTENT - BORDER
p("tile content width (390 - 16x2)", CONTENT)
p("  minus tile border 1x2 -> inner", inner)

# ---- left side, denseMain -------------------------------------------------
LEFT_INSET = 13.0      # denseMain paddingLeft (3px rail + 10 inset)
GAP1 = 6.0             # denseLine1 gap
MAIN_PR = 8.0          # denseMain paddingRight

team = w("ARI", "archivo400", 11)
rk = microtag("RK")
q = microtag("Q")
p("denseMain paddingLeft (rail 3 + inset 10)", LEFT_INSET)
p('team code "ARI" @ Archivo400 11', team)
p('RK micro-tag (11px floor, S2 PRD-04)', rk)
p('injury "Q" micro-tag', q)
p("denseMain paddingRight", MAIN_PR)

# ---- right cluster, denseNumsRow ------------------------------------------
NUMS_GAP = 8.0         # denseNumsRow gap
NUMS_MR = 8.0          # denseNums marginRight

tiers = ["4+ 1sts", "3 1sts", "2 1sts", "1 1st", "2nd", "3rd", "4th", "FA"]
print("\n-- tier badge widths (TierChalkBadge = Badge, type.label uppercase) --")
for t in tiers:
    p(f'  "{t}"  ->  "{t.upper()}"', badge(t))
widest_tier = max(badge(t) for t in tiers)

posrank = w("WR61", "mono600", 14)
p('posRank "WR61" @ IBMPlexMono600 14', posrank)
p("denseNumsRow gap (between badge and posRank)", NUMS_GAP)
p("denseNums marginRight", NUMS_MR)

# ---- baseline: shipped tile, no affordance --------------------------------
fixed_left = LEFT_INSET + GAP1 + team + GAP1 + rk + GAP1 + q + MAIN_PR
right_cluster = widest_tier + NUMS_GAP + posrank + NUMS_MR
name_budget = inner - fixed_left - right_cluster

print("\n" + "=" * 74)
print("BASELINE — shipped tile, worst case (long name + RK + Q + '4+ 1sts')")
print("=" * 74)
p("fixed left cost (inset+gaps+team+RK+Q+pr)", fixed_left)
p("right cluster (widest tier + gap + posRank + margin)", right_cluster)
p("REMAINING FOR THE NAME", name_budget)

NAME = "Marvin Harrison Jr."
name_w = w(NAME, "archivo600", 15)
p(f'"{NAME}" @ Archivo600 15 needs', name_w)
print(f"{'  -> fits?':<58} {'YES' if name_w <= name_budget else 'NO — ELLIPSIS'}")


def chars_that_fit(budget, text=NAME):
    """How many leading chars of `text` fit, allowing for the ellipsis glyph."""
    ell = w("…", "archivo600", 15)
    for i in range(len(text), 0, -1):
        if w(text[:i], "archivo600", 15) <= budget:
            return i, text[:i]
        if w(text[:i], "archivo600", 15) + 0 <= budget:
            pass
    return 0, ""


def truncated(budget, text=NAME):
    ell = w("…", "archivo600", 15)
    if w(text, "archivo600", 15) <= budget:
        return text
    for i in range(len(text), 0, -1):
        if w(text[:i], "archivo600", 15) + ell <= budget:
            return text[:i] + "…"
    return "…"


print(f"{'  -> renders as':<58} {truncated(name_budget)!r}")

# ---- variants -------------------------------------------------------------
print("\n" + "=" * 74)
print("AFFORDANCE VARIANTS — cost against the SHIPPED right cluster")
print("=" * 74)

CHEV = 12.0            # bare chevron glyph (Icon size 12)
LABEL_GAP = 3.0        # gap between word and glyph inside the affordance


def report(title, extra, left_cost=None):
    lc = fixed_left if left_cost is None else left_cost
    rc = right_cluster + extra
    nb = inner - lc - rc
    print(f"\n{title}")
    p("  affordance cost (incl. its leading gap)", extra)
    p("  right cluster total", rc)
    p("  NAME BUDGET", nb)
    print(f"{'  renders as':<58} {truncated(nb)!r}")
    return nb


report("A — bare chevron in the right cluster", NUMS_GAP + CHEV)

offer_word = w("Offer", "archivo600", 11, 0.5)
report("B — visible 'Offer ›' text label", NUMS_GAP + offer_word + LABEL_GAP + CHEV)

target_word = w("Target", "archivo600", 11, 0.5)
report("B' — visible 'Target ›' text label", NUMS_GAP + target_word + LABEL_GAP + CHEV)

# ---- Variant D: drop RK + injury micro-tags -------------------------------
fixed_left_D = LEFT_INSET + GAP1 + team + MAIN_PR
print("\n" + "=" * 74)
print("VARIANT D — micro-tags (RK + injury) removed to pay for a text label")
print("=" * 74)
p("fixed left cost WITHOUT RK/Q tags", fixed_left_D)
p("  freed by dropping both tags", fixed_left - fixed_left_D)
report("D1 — no tags + 'Offer ›' label", NUMS_GAP + offer_word + LABEL_GAP + CHEV, fixed_left_D)
report("D2 — no tags + 'Target ›' label", NUMS_GAP + target_word + LABEL_GAP + CHEV, fixed_left_D)
report("D3 — no tags + bare chevron", NUMS_GAP + CHEV, fixed_left_D)

# outlined pill button variant: border 1x2 + paddingHorizontal 8x2 + word
pill_offer = offer_word + 16 + 2
report("D4 — no tags + outlined ice 'Offer' pill (no chevron)",
       NUMS_GAP + pill_offer, fixed_left_D)

# ---- median divider label -------------------------------------------------
print("\n" + "=" * 74)
print("DIVIDER / STRIP text widths (Direction 2 + Direction 1 strip)")
print("=" * 74)
for s in [
    "League median · a Mid 3rd",
    "LEAGUE MEDIAN",
    "Trade candidates",
    "TRADE CANDIDATES",
    "6 buyers · 5 sellers",
]:
    p(f'"{s}" @ Archivo600 13', w(s, "archivo600", 13))
