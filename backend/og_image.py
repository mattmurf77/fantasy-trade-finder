"""
OG share card image generation (PNG, 1200×630) using Pillow.

Exports:
    render_tier_card(username, pos, scoring_format) -> bytes
    render_trade_card(match_row, *, verdict, as_of, scoring_format,
                      pick_labels) -> (bytes, status)
    render_package_card(short_id, *, verdict, as_of, scoring_format,
                        pick_labels) -> (bytes, status)
    render_expired_trade_card() -> bytes
    render_placeholder_card(title, subtitle) -> bytes

All renderers always return a valid PNG as bytes. They never write
anything to disk and never raise for user-error inputs (unknown user,
missing match, no tiers yet) — instead they produce a graceful
placeholder card.
"""

from __future__ import annotations

import functools
import io
import json
import logging
import re
from typing import Iterable, Optional

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as _imp_err:  # pragma: no cover
    # Keep import-time failures non-fatal so the rest of the backend can still
    # boot. The routes will surface a clean 500 with a helpful message.
    Image = None                                # type: ignore[assignment]
    ImageDraw = None                            # type: ignore[assignment]
    ImageFont = None                            # type: ignore[assignment]
    _PIL_IMPORT_ERROR = _imp_err
else:
    _PIL_IMPORT_ERROR = None

log = logging.getLogger("trade_finder")

# ---------------------------------------------------------------------------
# Canvas and palette
# ---------------------------------------------------------------------------

CARD_W = 1200
CARD_H = 630

BG_TOP       = (15,  19,  34)     # deep navy
BG_BOT       = (28,  37,  66)
TEXT_PRIMARY = (245, 247, 252)
TEXT_MUTED   = (160, 174, 200)
ACCENT       = (110, 180, 255)
DIVIDER      = (60,  72, 105)

# Canonical position hexes: docs/cross-client-invariants.md § Position color
# tokens. Chip labels on them are ink-0 (12, 14, 17); white fails contrast.
POS_COLORS = {
    "QB": (249, 115, 22),
    "RB": (34,  197, 94),
    "WR": (59,  130, 246),
    "TE": (168, 85,  247),
}

# Matches ranking_service.ORDERED_TIERS ordering (best → worst) — the
# 8-tier pick-value ladder (2026-07-12, docs/cross-client-invariants.md).
TIER_ORDER = ["firsts_4plus", "firsts_3", "firsts_2", "first_1",
              "second", "third", "fourth", "waivers"]
TIER_LABELS = {
    "firsts_4plus": "4+ 1sts",
    "firsts_3":     "3 1sts",
    "firsts_2":     "2 1sts",
    "first_1":      "1 1st",
    "second":       "2nd",
    "third":        "3rd",
    "fourth":       "4th",
    "waivers":      "FA",
}
TIER_TINTS = {
    # translucent band fill (R, G, B, A) — canonical tier hexes from
    # docs/cross-client-invariants.md at og-card alphas.
    "firsts_4plus": (248, 113, 113, 245),
    "firsts_3":     (232, 121, 249, 235),
    "firsts_2":     (251, 191, 36,  225),
    "first_1":      (45,  212, 191, 215),
    "second":       (56,  189, 248, 210),
    "third":        (244, 114, 182, 205),
    "fourth":       (163, 230, 53,  200),
    "waivers":      (122, 127, 150, 190),
}

FORMAT_LABELS = {
    "1qb_ppr": "1QB PPR",
    "sf_tep":  "SF TEP",
}

# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------

_FONT_CANDIDATES = [
    # macOS / Linux common paths — first hit wins; fall back to PIL default.
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
]


def _load_font(size: int, bold: bool = False):
    """Load a TrueType font at the requested size, falling back to PIL's
    bundled default bitmap font if no system font is available."""
    if ImageFont is None:
        return None
    # Prefer a bold-looking candidate when bold=True
    if bold:
        ordered = [p for p in _FONT_CANDIDATES if "Bold" in p or "bold" in p] \
                  + [p for p in _FONT_CANDIDATES if "Bold" not in p and "bold" not in p]
    else:
        ordered = list(_FONT_CANDIDATES)
    for path in ordered:
        try:
            return ImageFont.truetype(path, size=size)
        except (OSError, IOError):
            continue
    # Absolute fallback — bitmap font, not scalable, but always works.
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def _text_width(draw, text: str, font) -> int:
    if font is None or not text:
        return 0
    try:
        # Pillow >= 8
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]
    except Exception:
        try:
            return int(draw.textlength(text, font=font))
        except Exception:
            return len(text) * 8


def _truncate(draw, text: str, font, max_width: int) -> str:
    if _text_width(draw, text, font) <= max_width:
        return text
    ellipsis = "…"
    s = text
    while s and _text_width(draw, s + ellipsis, font) > max_width:
        s = s[:-1]
    return (s + ellipsis) if s else ellipsis


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

def _new_canvas() -> "Image.Image":
    """Create a 1200x630 canvas with a vertical gradient + subtle grid."""
    img = Image.new("RGB", (CARD_W, CARD_H), BG_TOP)
    # Vertical gradient
    px = img.load()
    for y in range(CARD_H):
        t = y / (CARD_H - 1)
        r = int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t)
        for x in range(CARD_W):
            px[x, y] = (r, g, b)
    return img


def _draw_footer(draw, font_small) -> None:
    footer = "Fleeced: Dynasty Trade Finder · fantasy-trade-finder.onrender.com"
    draw.line([(60, CARD_H - 70), (CARD_W - 60, CARD_H - 70)], fill=DIVIDER, width=2)
    draw.text((60, CARD_H - 50), footer, font=font_small, fill=TEXT_MUTED)


def _to_png_bytes(img: "Image.Image") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Placeholder card (used for errors / empty states)
# ---------------------------------------------------------------------------

def render_placeholder_card(title: str, subtitle: str = "", *,
                            shrink_to_fit: bool = False) -> bytes:
    """Render a simple centered placeholder card — used for unknown users,
    missing tiers, or bad match ids. Always returns a valid PNG.

    `shrink_to_fit` steps the title font down (to 40px at the smallest)
    before truncating, for a fixed sentence that must read in full whatever
    font the host has (the expired-trade card)."""
    if _PIL_IMPORT_ERROR is not None:
        raise RuntimeError(
            "Pillow is not installed. Run: pip install Pillow>=10.0"
        ) from _PIL_IMPORT_ERROR

    img = _new_canvas()
    draw = ImageDraw.Draw(img)
    font_big = _load_font(72, bold=True)
    font_mid = _load_font(34, bold=False)
    font_small = _load_font(22)

    if shrink_to_fit:
        size = 72
        while size > 40 and _text_width(draw, title, font_big) > CARD_W - 120:
            size -= 4
            font_big = _load_font(size, bold=True)
    title = _truncate(draw, title, font_big, CARD_W - 120)
    tw = _text_width(draw, title, font_big)
    draw.text(((CARD_W - tw) // 2, 220), title, font=font_big, fill=TEXT_PRIMARY)

    if subtitle:
        subtitle = _truncate(draw, subtitle, font_mid, CARD_W - 160)
        sw = _text_width(draw, subtitle, font_mid)
        draw.text(((CARD_W - sw) // 2, 330), subtitle, font=font_mid, fill=TEXT_MUTED)

    _draw_footer(draw, font_small)
    return _to_png_bytes(img)


# ---------------------------------------------------------------------------
# Tier snapshot card
# ---------------------------------------------------------------------------

def _compute_tier_assignments(
    overrides: dict[str, float],
    players_by_id: dict[str, dict],
    position: str,
    scoring_format: str,
) -> dict[str, list[dict]]:
    """
    Map saved tier-override ELOs back to tier buckets.

    Delegates to the canonical RankingService.tier_for_elo band walk
    (tier_config.json) so the round-trip matches what the tiers UI shows —
    the previous inline band tables here had drifted from the config.
    """
    from .ranking_service import RankingService as _RS

    buckets: dict[str, list[tuple[float, dict]]] = {t: [] for t in TIER_ORDER}

    for pid, elo in overrides.items():
        player = players_by_id.get(str(pid))
        if not player:
            continue
        if (player.get("position") or "").upper() != position.upper():
            continue
        try:
            elo_f = float(elo)
        except (TypeError, ValueError):
            continue
        tier_name = _RS.tier_for_elo(elo_f, position.upper(), scoring_format)
        if tier_name in buckets:
            buckets[tier_name].append((elo_f, player))

    # Sort descending by elo within each bucket and strip elo
    sorted_buckets: dict[str, list[dict]] = {}
    for t in TIER_ORDER:
        buckets[t].sort(key=lambda pe: pe[0], reverse=True)
        sorted_buckets[t] = [p for _, p in buckets[t]]
    return sorted_buckets


def _resolve_user_by_username(username: str) -> Optional[dict]:
    """Look up a user row by (case-insensitive) username. Returns dict with
    sleeper_user_id, username, display_name, avatar — or None."""
    try:
        from .database import engine, users_table
        from sqlalchemy import select, func
    except Exception as e:
        log.error("og_image: could not import database: %s", e)
        return None

    if not username:
        return None
    try:
        with engine.connect() as conn:
            row = conn.execute(
                select(users_table).where(
                    func.lower(users_table.c.username) == username.lower()
                )
            ).fetchone()
    except Exception as e:
        log.error("og_image: user lookup failed for %s: %s", username, e)
        return None
    if not row:
        return None
    return {
        "sleeper_user_id": row.sleeper_user_id,
        "username":        row.username,
        "display_name":    row.display_name,
        "avatar":          row.avatar,
    }


def render_tier_card(
    username: str,
    pos: str,
    scoring_format: str = "1qb_ppr",
) -> tuple[bytes, int]:
    """
    Render a user's current tier assignments for a single position.

    Returns (png_bytes, http_status_code). Status is 200 for success,
    404 for an unknown username (still returns a valid placeholder PNG).
    """
    if _PIL_IMPORT_ERROR is not None:
        raise RuntimeError(
            "Pillow is not installed. Run: pip install Pillow>=10.0"
        ) from _PIL_IMPORT_ERROR

    pos_u = (pos or "").upper()
    if pos_u not in ("QB", "RB", "WR", "TE"):
        return render_placeholder_card(
            "Invalid position",
            f"Unknown position: {pos!r}",
        ), 404

    user = _resolve_user_by_username(username)
    if not user:
        return render_placeholder_card(
            "User not found",
            f"@{username}",
        ), 404

    # Pull tier overrides for this user + format
    try:
        from .database import load_tier_overrides, load_players_by_ids
    except Exception as e:
        log.error("og_image: import failed: %s", e)
        return render_placeholder_card("Unavailable", "Data service offline"), 500

    overrides = load_tier_overrides(user["sleeper_user_id"], scoring_format)
    if not overrides:
        return _render_tier_card_empty(user, pos_u, scoring_format), 200

    players_by_id = load_players_by_ids(list(overrides.keys()))
    buckets = _compute_tier_assignments(overrides, players_by_id, pos_u, scoring_format)

    if not any(buckets[t] for t in TIER_ORDER):
        return _render_tier_card_empty(user, pos_u, scoring_format), 200

    return _render_tier_card_filled(user, pos_u, scoring_format, buckets), 200


def _render_tier_card_empty(user: dict, pos: str, scoring_format: str) -> bytes:
    display = user.get("display_name") or user.get("username") or "Player"
    fmt_label = FORMAT_LABELS.get(scoring_format, scoring_format)
    return render_placeholder_card(
        f"No {pos} tiers yet",
        f"@{user.get('username','')} · {fmt_label} · come rank!",
    )


def _render_tier_card_filled(
    user: dict,
    pos: str,
    scoring_format: str,
    buckets: dict[str, list[dict]],
) -> bytes:
    img = _new_canvas()
    draw = ImageDraw.Draw(img)

    font_title   = _load_font(58, bold=True)
    font_sub     = _load_font(28)
    font_tier    = _load_font(28, bold=True)
    font_players = _load_font(24)
    font_small   = _load_font(22)

    # Header
    pos_color = POS_COLORS.get(pos, ACCENT)
    # Position chip
    chip_x, chip_y = 60, 50
    chip_w, chip_h = 90, 64
    draw.rounded_rectangle(
        [chip_x, chip_y, chip_x + chip_w, chip_y + chip_h],
        radius=14, fill=pos_color,
    )
    pos_w = _text_width(draw, pos, font_title)
    draw.text(
        (chip_x + (chip_w - pos_w) // 2, chip_y + 2),
        pos, font=font_title, fill=(12, 14, 17),
    )

    title = f"My {pos} Tiers"
    draw.text((chip_x + chip_w + 24, 50), title, font=font_title, fill=TEXT_PRIMARY)

    username = user.get("username") or ""
    display = user.get("display_name") or username or "player"
    fmt_label = FORMAT_LABELS.get(scoring_format, scoring_format)
    sub = f"@{username} · {fmt_label}" if username else f"{display} · {fmt_label}"
    sub = _truncate(draw, sub, font_sub, CARD_W - 120)
    draw.text((60, 130), sub, font=font_sub, fill=TEXT_MUTED)

    # Body: one horizontal band per tier (len(TIER_ORDER))
    body_top = 185
    body_bot = CARD_H - 90
    n = len(TIER_ORDER)
    gap = 8
    band_h = (body_bot - body_top - gap * (n - 1)) // n

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    for i, tier_name in enumerate(TIER_ORDER):
        y0 = body_top + i * (band_h + gap)
        y1 = y0 + band_h
        tint = TIER_TINTS[tier_name]
        odraw.rounded_rectangle(
            [60, y0, CARD_W - 60, y1],
            radius=14,
            fill=tint,
        )

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    for i, tier_name in enumerate(TIER_ORDER):
        y0 = body_top + i * (band_h + gap)
        y1 = y0 + band_h
        label = TIER_LABELS[tier_name]
        draw.text((80, y0 + (band_h - 32) // 2), label, font=font_tier,
                  fill=(15, 19, 34))

        players = buckets.get(tier_name, [])[:4]
        if players:
            names = [_player_display_name(p) for p in players]
            line = "  ·  ".join(names)
            line = _truncate(draw, line, font_players, CARD_W - 320)
            draw.text((240, y0 + (band_h - 30) // 2), line,
                      font=font_players, fill=(20, 24, 40))
        else:
            draw.text((240, y0 + (band_h - 30) // 2), "—",
                      font=font_players, fill=(60, 72, 105))

    _draw_footer(draw, font_small)
    return _to_png_bytes(img)


def _player_display_name(player: dict) -> str:
    full = player.get("full_name") or ""
    if full:
        return full
    first = player.get("first_name") or ""
    last = player.get("last_name") or ""
    return f"{first} {last}".strip() or "Unknown"


# ---------------------------------------------------------------------------
# Trade give/get card (no fairness number: models-lead I6, Product 2026-10-31)
# ---------------------------------------------------------------------------

def render_trade_card(match: dict, *, verdict: Optional[dict] = None,
                      as_of: Optional[str] = None,
                      scoring_format: Optional[str] = None,
                      pick_labels: Optional[dict] = None) -> tuple[bytes, int]:
    """
    Render a trade give/get card for ONE resolved trade_matches row (a
    dict; only user_a_give / user_a_receive are read).

    `verdict` ({favors, gap, second_in_firsts}), `as_of` ("Mon D, YYYY")
    and `scoring_format` draw the value bar; the server reads all three from
    the share's stored value snapshot (server._value_bar_from_snapshot).
    With no verdict the card is the no-bar card, byte for byte.
    `pick_labels` ({pick_id: label}) names draft picks, which aren't
    players rows. The server computes all of them: og_image never imports
    server.

    The caller resolves the row through trade_share_tokens (build O8). This
    function never looks a match up by a value taken from a URL: the old
    int(match_id) lookup is what let anyone walk the sequential ids.

    Returns (png_bytes, http_status_code): 200 on success, 500 when the
    player lookup is unavailable (still a valid placeholder PNG).
    """
    if _PIL_IMPORT_ERROR is not None:
        raise RuntimeError(
            "Pillow is not installed. Run: pip install Pillow>=10.0"
        ) from _PIL_IMPORT_ERROR

    try:
        from .database import load_players_by_ids
    except Exception as e:
        log.error("og_image: import failed: %s", e)
        return render_placeholder_card("Unavailable", "Data service offline"), 500

    try:
        a_give    = json.loads(match.get("user_a_give"))    if match.get("user_a_give")    else []
        a_receive = json.loads(match.get("user_a_receive")) if match.get("user_a_receive") else []
    except (json.JSONDecodeError, TypeError):
        a_give, a_receive = [], []

    all_ids = [str(x) for x in (a_give + a_receive)]
    players_by_id = load_players_by_ids(all_ids) if all_ids else {}

    return _render_trade_card_png(
        give_ids=a_give,
        receive_ids=a_receive,
        players_by_id=players_by_id,
        verdict=verdict, as_of=as_of, scoring_format=scoring_format,
        pick_labels=pick_labels,
    ), 200


# The ONE place the "expired trade link" words live — the /s/trade miss page
# (server.share_trade_page) and the PNG below both read them. Proposed copy
# (build O8); marketing-lead's wording replaces it here when it lands.
TRADE_LINK_EXPIRED_TITLE = "This trade link has expired."
TRADE_LINK_EXPIRED_BODY = "Open Fleeced to see your trades."


@functools.lru_cache(maxsize=1)
def render_expired_trade_card() -> bytes:
    """The generic card every /og/trade miss returns (numeric id, unknown,
    revoked or malformed token, orphaned match). Takes no input, so it
    reveals nothing about the miss; cached once per process, so every miss
    is byte-identical. lru_cache is thread-safe and never caches the
    Pillow-unavailable RuntimeError, which still raises on every call."""
    return render_placeholder_card(TRADE_LINK_EXPIRED_TITLE, TRADE_LINK_EXPIRED_BODY,
                                   shrink_to_fit=True)


def render_package_card(short_id, *, verdict: Optional[dict] = None,
                        as_of: Optional[str] = None,
                        scoring_format: Optional[str] = None,
                        pick_labels: Optional[dict] = None) -> tuple[bytes, int]:
    """
    Render an arbitrary shared package (shared_packages row) as an OG card
    — the /s/p/<short_id> landing (teardown S7 PRD-01, flag
    `growth.share_landing`). Same layout as the trade-match card; sides
    come from the sharer's snapshot rather than a trade_matches row.
    `verdict`, `as_of`, `scoring_format` and `pick_labels` are as for
    render_trade_card (a package draws its bar only when it was shared
    with a scoring format, so a value snapshot was stored).

    Returns (png_bytes, http_status_code): 200 on success, 404 for an
    unknown short_id (placeholder PNG body).
    """
    if _PIL_IMPORT_ERROR is not None:
        raise RuntimeError(
            "Pillow is not installed. Run: pip install Pillow>=10.0"
        ) from _PIL_IMPORT_ERROR

    try:
        from .database import load_shared_package, load_players_by_ids
    except Exception as e:
        log.error("og_image: import failed: %s", e)
        return render_placeholder_card("Unavailable", "Data service offline"), 500

    try:
        pkg = load_shared_package(str(short_id))
    except Exception as e:
        log.error("og_image: package lookup failed for %s: %s", short_id, e)
        return render_placeholder_card("Unavailable", "Data service offline"), 500
    if pkg is None:
        return render_placeholder_card("Package not found", f"id={short_id!r}"), 404

    give = [str(x) for x in pkg.get("give_ids") or []]
    receive = [str(x) for x in pkg.get("receive_ids") or []]
    all_ids = give + receive
    players_by_id = load_players_by_ids(all_ids) if all_ids else {}

    return _render_trade_card_png(
        give_ids=give,
        receive_ids=receive,
        players_by_id=players_by_id,
        title="Trade Package",
        verdict=verdict, as_of=as_of, scoring_format=scoring_format,
        pick_labels=pick_labels,
    ), 200


def _render_trade_card_png(
    give_ids: list[str],
    receive_ids: list[str],
    players_by_id: dict[str, dict],
    title: str = "Trade Match",
    *,
    verdict: Optional[dict] = None,
    as_of: Optional[str] = None,
    scoring_format: Optional[str] = None,
    pick_labels: Optional[dict] = None,
) -> bytes:
    pick_labels = pick_labels or {}
    # The bar needs all four: the basis line names the format and the date
    # (legal R28.24 #1), and the +/-2nd ticks need the snapshot's
    # `second_in_firsts`. There is no default fraction: a verdict without a
    # valid one draws no bar, never a tick from a stale constant.
    second_in_firsts = (verdict or {}).get("second_in_firsts")
    bar = (verdict is not None and bool(as_of) and bool(scoring_format)
           and valid_second_in_firsts(second_in_firsts))
    img = _new_canvas()
    draw = ImageDraw.Draw(img)

    font_title   = _load_font(48, bold=True)
    font_side    = _load_font(30, bold=True)
    font_player  = _load_font(28)
    font_pos     = _load_font(20, bold=True)
    font_small   = _load_font(22)

    # Header. With the value bar the block moves up to free y 375-560
    # (design-lead); without it the layout is the recentred #511 card.
    draw.text((60, 45 if bar else 85), title, font=font_title, fill=TEXT_PRIMARY)

    # Two sides
    col_w = 470
    left_x = 60
    right_x = CARD_W - 60 - col_w
    col_top = 125 if bar else 175
    col_bot = 375 if bar else 455

    # Column backgrounds
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rounded_rectangle(
        [left_x, col_top, left_x + col_w, col_bot],
        radius=18, fill=(255, 255, 255, 18),
    )
    odraw.rounded_rectangle(
        [right_x, col_top, right_x + col_w, col_bot],
        radius=18, fill=(255, 255, 255, 18),
    )
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Side headers
    draw.text((left_x + 24, col_top + 18), "YOU GIVE",
              font=font_side, fill=ACCENT)
    draw.text((right_x + 24, col_top + 18), "YOU GET",
              font=font_side, fill=ACCENT)

    def render_side(x0: int, y0: int, ids: list[str]):
        if not ids:
            draw.text((x0 + 24, y0 + 80), "—", font=font_player, fill=TEXT_MUTED)
            return
        # Over 3 players: 2 names, then "+N more" in the third row's slot.
        shown = ids if len(ids) <= 3 else ids[:2]
        for i, pid in enumerate(shown):
            p = players_by_id.get(str(pid))
            pick_label = pick_labels.get(str(pid))
            if pick_label:
                # A draft pick: a neutral "PK" chip, never a position hex
                # (docs/cross-client-invariants.md § Position color tokens).
                name = pick_label
                pos = PICK_CHIP_LABEL
            elif p:
                name = _player_display_name(p)
                pos = (p.get("position") or "").upper()
            else:
                name = "Unknown player"
                pos = ""
            row_y = y0 + 70 + i * 66
            # Position chip
            if pos:
                chip_w, chip_h = 56, 32
                color = (PICK_CHIP_FILL if pick_label
                         else POS_COLORS.get(pos, (120, 144, 156)))
                draw.rounded_rectangle(
                    [x0 + 24, row_y + 4, x0 + 24 + chip_w, row_y + 4 + chip_h],
                    radius=8, fill=color,
                )
                cw = _text_width(draw, pos, font_pos)
                draw.text(
                    (x0 + 24 + (chip_w - cw) // 2, row_y + 10),
                    pos, font=font_pos, fill=(12, 14, 17),
                )
                text_x = x0 + 24 + chip_w + 14
            else:
                text_x = x0 + 24
            # Player name (truncated to column)
            name = _truncate(draw, name, font_player, (x0 + col_w - 20) - text_x)
            draw.text((text_x, row_y + 6), name, font=font_player, fill=TEXT_PRIMARY)
        if len(ids) > 3:
            draw.text((x0 + 24, y0 + 70 + 2 * 66 + 6), f"+{len(ids) - 2} more",
                      font=font_player, fill=TEXT_MUTED)

    render_side(left_x, col_top, give_ids)
    render_side(right_x, col_top, receive_ids)

    if bar:
        _draw_value_bar(draw, verdict, as_of, scoring_format, second_in_firsts)

    _draw_footer(draw, font_small)
    return _to_png_bytes(img)


# ---------------------------------------------------------------------------
# The value bar (docs/plans/share-card-value-bar/scope.md)
#
# The app's TradeValueBar (mobile/src/components/TradeValueBar.tsx) on the
# public card: a diverging bar centred on even, half-scale = one generic Mid
# 1st, so the fill length IS |gap.firsts| (clamped at the ends), with +/-2nd
# landmark ticks where a Mid 2nd sits today (`second_in_firsts`, computed
# by the server from the current generic-pick values). Geometry and colour:
# design-lead's spec (v2, 2026-11-01). Words: marketing addendum 14 part B
# (legal R28.24, models-lead K): they describe the trade's SIDES, never
# people, and never say who comes out ahead; the lean points at the column
# with more value. The fill takes the app's colours exactly (operator,
# 2026-11-01: "Green and amber"): green toward YOU GET, amber toward YOU
# GIVE, the ice nub when even. No "win", "You"/"They", value numbers,
# "fair", percentages, heading or end labels.
# ---------------------------------------------------------------------------

PICK_CHIP_LABEL = "PK"
PICK_CHIP_FILL = (151, 161, 174)    # chalk-dim: neutral, never a position hex

VB_X0, VB_X1 = 60, CARD_W - 60      # track x 60-1140
VB_MID = (VB_X0 + VB_X1) // 2       # 600: even
VB_HALF = (VB_X1 - VB_X0) // 2      # 540: one Mid 1st
VB_TRACK_Y0, VB_TRACK_Y1 = 452, 470
VB_TICK_OVERHANG = 8                # ticks run 8px above and below the track
VB_LABEL_Y = 398                    # the pick / "About even" label line
VB_SCALE_Y = 488                    # 1st · 2nd · Even · 2nd · 1st
VB_BASIS_Y = 518                    # the basis and date line, its own row
VB_NUB_W = 12                       # the even nub

VB_TRACK  = (35, 40, 51)            # ink-3
# The fill: TradeValueBar.tsx:87 `fillColor = even ? ice.base : youWin ?
# semantic.pos : semantic.warn` (youWin = favors 'receive', :81), with the
# token values from mobile/src/theme/chalkline.ts. Named after the tokens so
# the card and the app can't drift; test_share_card_value_bar pins both.
SEMANTIC_POS  = (34, 197, 94)       # semantic.pos  '#22C55E', chalkline.ts:58
SEMANTIC_WARN = (245, 158, 11)      # semantic.warn '#F59E0B', chalkline.ts:60
ICE_BASE      = (86, 217, 236)      # ice.base      '#56D9EC', chalkline.ts:44
VB_TICK   = (61, 70, 84)            # ink.lineStrong (raised from ink.line to read at card scale)
VB_CENTER = (89, 100, 122)          # ink.lineStrongA11y
VB_PICK   = (45, 212, 191)          # tier first_1, the app's pick-label colour
VB_DIM    = (151, 161, 174)         # chalk-dim
VB_CHALK  = (236, 239, 244)         # chalk

VB_SCALE_LABELS = ("1st", "2nd", "Even", "2nd", "1st")   # no signs (B6)

# B4 (MUST) and its SHOULD form; the long form is used when it fits on one
# line at its size.
VB_BASIS_LONG = ("Estimate from consensus dynasty values, not a guarantee"
                 " · {format} · {date}")
VB_BASIS = "Estimate from consensus dynasty values · {format} · {date}"


def _short_pick(label: str) -> str:
    """TradeValueBar.tsx's shortPick: "Mid 2nd Round Pick" -> "a Mid 2nd"
    (article by first-letter vowel)."""
    core = re.sub(r"\s*Round Pick$", "", label, flags=re.I).strip()
    return ("an " if re.match(r"[AEIOU]", core, re.I) else "a ") + core


def value_bar_is_even(verdict: dict) -> bool:
    """Even per B3: `favors` is even (or missing), or the gap rounds to
    0.0 firsts. The bar then draws the centred nub, never a sliver."""
    if verdict.get("favors") not in ("give", "receive"):
        return True
    return round(abs(float(verdict["gap"]["firsts"])), 1) == 0.0


def value_bar_label(verdict: dict) -> tuple[str, str, str]:
    """(lead, emphasis, tail) of the label line, marketing addendum 14:
    B1 "≈ a Mid 2nd in value", B2 "≈ 1.4 Mid 1sts in value",
    B3 "About even in value"."""
    if value_bar_is_even(verdict):
        return "", "About even", " in value"
    gap = verdict["gap"]
    pick = gap.get("pick_equivalent")
    if pick:
        return "≈ ", _short_pick(pick["label"]), " in value"
    return "≈ ", f"{abs(float(gap['firsts'])):.1f} Mid 1sts", " in value"


def value_bar_alt(verdict: Optional[dict], as_of: Optional[str] = None,
                  scoring_format: Optional[str] = None) -> str:
    """The card's alt text (B8), for the share page's og:image:alt."""
    if verdict is None or not as_of or not scoring_format:
        return "Trade card: the give/get breakdown."
    tail = (" Estimate from consensus dynasty values, "
            f"{FORMAT_LABELS.get(scoring_format, scoring_format)}, {as_of}.")
    if value_bar_is_even(verdict):
        return ("Trade card: the give/get breakdown and a value bar, "
                "about even in value." + tail)
    side = "get" if verdict["favors"] == "receive" else "give"
    lead, emph, rest = value_bar_label(verdict)
    return ("Trade card: the give/get breakdown and a value bar leaning to "
            f"the {side} side, {lead}{emph}{rest}." + tail)


def _draw_runs(draw, x: int, y: int, runs) -> int:
    """Draw [(text, font, fill), ...] left to right; returns the end x."""
    for text, font, fill in runs:
        if text:
            draw.text((x, y), text, font=font, fill=fill)
            x += _text_width(draw, text, font)
    return x


def _basis_line(draw, font, scoring_format: str, as_of: str) -> str:
    """B4-long when it fits within the track width (1080px) at the font
    actually loaded, else B4."""
    fmt_label = FORMAT_LABELS.get(scoring_format, scoring_format)
    basis = VB_BASIS_LONG.format(format=fmt_label, date=as_of)
    if _text_width(draw, basis, font) > VB_X1 - VB_X0:
        basis = VB_BASIS.format(format=fmt_label, date=as_of)
    return basis


def valid_second_in_firsts(value) -> bool:
    """A usable +/-2nd tick fraction: a real number with 0 < value < 1."""
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and 0 < value < 1)


def _draw_value_bar(draw, verdict: dict, as_of: str, scoring_format: str,
                    second_in_firsts: float) -> None:
    """The bar in the band between the panels (bottom y=375 with the bar)
    and the footer rule (y=560): label line y=398, track y 452-470, scale
    labels y=488, basis and date line y=518. `second_in_firsts` (required,
    from the snapshot) places the +/-2nd ticks."""
    f_label = _load_font(30, bold=True)
    f_basis = _load_font(20)
    f_scale = _load_font(18)

    even = value_bar_is_even(verdict)
    leans_get = verdict.get("favors") == "receive"

    # Label line (B1-B3), left: the pick phrase in the app's pick teal, the
    # rest in chalk; "About even in value" all chalk.
    lead, emph, tail = value_bar_label(verdict)
    _draw_runs(draw, VB_X0, VB_LABEL_Y, [
        (lead, f_label, VB_CHALK),
        (emph, f_label, VB_CHALK if even else VB_PICK),
        (tail, f_label, VB_CHALK),
    ])

    # The diverging bar: track, fill (or the even nub), ticks, centre line.
    ty0, ty1 = VB_TRACK_Y0, VB_TRACK_Y1
    draw.rounded_rectangle([VB_X0, ty0, VB_X1, ty1], radius=3, fill=VB_TRACK)
    if even:
        half_nub = VB_NUB_W // 2
        draw.rounded_rectangle([VB_MID - half_nub, ty0, VB_MID + half_nub, ty1],
                               radius=3, fill=ICE_BASE)
    else:
        # Clamped at one Mid 1st (the end of the track).
        length = round(min(1.0, abs(float(verdict["gap"]["firsts"]))) * VB_HALF)
        if leans_get:       # more value on the YOU GET side: lean right
            box = [VB_MID, ty0, VB_MID + length, ty1]
        else:               # more value on the YOU GIVE side: lean left
            box = [VB_MID - length, ty0, VB_MID, ty1]
        draw.rounded_rectangle(box, radius=3,
                               fill=SEMANTIC_POS if leans_get else SEMANTIC_WARN)
    sec = round(second_in_firsts * VB_HALF)
    for tx in (VB_MID - sec, VB_MID + sec):
        draw.rectangle([tx - 1, ty0 - VB_TICK_OVERHANG, tx, ty1 + VB_TICK_OVERHANG],
                       fill=VB_TICK)
    draw.rectangle([VB_MID - 1, ty0 - VB_TICK_OVERHANG, VB_MID, ty1 + VB_TICK_OVERHANG],
                   fill=VB_CENTER)

    # Landmark labels: 1st · 2nd · Even · 2nd · 1st
    for text, cx, align in zip(VB_SCALE_LABELS,
                               (VB_X0, VB_MID - sec, VB_MID, VB_MID + sec, VB_X1),
                               ("l", "c", "c", "c", "r")):
        w = _text_width(draw, text, f_scale)
        tx = cx if align == "l" else (cx - w if align == "r" else cx - w // 2)
        draw.text((tx, VB_SCALE_Y), text, font=f_scale, fill=VB_DIM)

    # B4 / B4-long: basis, format and date, always on its own row.
    draw.text((VB_X0, VB_BASIS_Y), _basis_line(draw, f_basis, scoring_format, as_of),
              font=f_basis, fill=VB_DIM)
