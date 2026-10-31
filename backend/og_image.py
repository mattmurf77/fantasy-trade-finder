"""
OG share card image generation (PNG, 1200×630) using Pillow.

Exports:
    render_tier_card(username, pos, scoring_format) -> bytes
    render_trade_card(match_row) -> (bytes, status)
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
# Trade fairness card
# ---------------------------------------------------------------------------

def _compute_fairness(
    give_ids: list[str],
    receive_ids: list[str],
    players_by_id: dict[str, dict],
) -> int:
    """
    Produce a 0–100 fairness score from the two sides' player data.

    We don't have persisted composite scores on the match record, so this
    derives a rough fairness from search_rank symmetry: the closer the
    sides' average search_rank, the higher the fairness score. This is
    purely cosmetic for the share card — the authoritative fairness
    stays inside trade_service.
    """
    def avg_rank(ids: list[str]) -> float:
        ranks = []
        for pid in ids:
            p = players_by_id.get(str(pid))
            if not p:
                continue
            r = p.get("search_rank")
            if r is None:
                continue
            ranks.append(float(r))
        if not ranks:
            return 500.0
        return sum(ranks) / len(ranks)

    a = avg_rank(give_ids)
    b = avg_rank(receive_ids)
    if a <= 0 and b <= 0:
        return 50
    denom = max(a, b) or 1.0
    ratio = min(a, b) / denom  # 0..1 — closer to 1 means more even
    # Map ratio 0..1 → 40..98 so trades always look like they're in range
    score = 40 + ratio * 58
    return int(round(max(0, min(100, score))))


def _fairness_color(score: int) -> tuple[int, int, int]:
    if score >= 85:
        return (76,  175, 80)     # green
    if score >= 65:
        return (255, 193, 7)      # amber
    return (244, 67, 54)          # red


def render_trade_card(match: dict) -> tuple[bytes, int]:
    """
    Render a trade give/get card with fairness verdict for ONE resolved
    trade_matches row (a dict; only user_a_give / user_a_receive are read).

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

    fairness = _compute_fairness(a_give, a_receive, players_by_id)

    return _render_trade_card_png(
        give_ids=a_give,
        receive_ids=a_receive,
        players_by_id=players_by_id,
        fairness=fairness,
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


def render_package_card(short_id) -> tuple[bytes, int]:
    """
    Render an arbitrary shared package (shared_packages row) as an OG card
    — the /s/p/<short_id> landing (teardown S7 PRD-01, flag
    `growth.share_landing`). Same layout as the trade-match card; sides
    come from the sharer's snapshot rather than a trade_matches row.

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
    fairness = _compute_fairness(give, receive, players_by_id)

    return _render_trade_card_png(
        give_ids=give,
        receive_ids=receive,
        players_by_id=players_by_id,
        fairness=fairness,
        title="Trade Package",
    ), 200


def _render_trade_card_png(
    give_ids: list[str],
    receive_ids: list[str],
    players_by_id: dict[str, dict],
    fairness: int,
    title: str = "Trade Match",
) -> bytes:
    img = _new_canvas()
    draw = ImageDraw.Draw(img)

    font_title   = _load_font(48, bold=True)
    font_side    = _load_font(30, bold=True)
    font_player  = _load_font(28)
    font_pos     = _load_font(20, bold=True)
    font_score   = _load_font(72, bold=True)
    font_small   = _load_font(22)

    # Header
    draw.text((60, 45), title, font=font_title, fill=TEXT_PRIMARY)

    # Two sides
    col_w = 470
    left_x = 60
    right_x = CARD_W - 60 - col_w
    col_top = 135
    col_bot = 415

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
        for i, pid in enumerate(ids[:3]):
            p = players_by_id.get(str(pid))
            if p:
                name = _player_display_name(p)
                pos = (p.get("position") or "").upper()
            else:
                name = "Unknown player"
                pos = ""
            row_y = y0 + 70 + i * 66
            # Position chip
            if pos:
                chip_w, chip_h = 56, 32
                color = POS_COLORS.get(pos, (120, 144, 156))
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

    render_side(left_x, col_top, give_ids)
    render_side(right_x, col_top, receive_ids)

    # Fairness verdict
    verdict_y = 428
    label = f"{fairness}% fair"
    lw = _text_width(draw, label, font_score)
    color = _fairness_color(fairness)
    draw.text(
        ((CARD_W - lw) // 2, verdict_y),
        label, font=font_score, fill=color,
    )

    # Progress bar
    bar_x0 = 200
    bar_x1 = CARD_W - 200
    bar_y0 = CARD_H - 115
    bar_y1 = bar_y0 + 14
    draw.rounded_rectangle(
        [bar_x0, bar_y0, bar_x1, bar_y1],
        radius=7, fill=DIVIDER,
    )
    fill_x = bar_x0 + int((bar_x1 - bar_x0) * (max(0, min(100, fairness)) / 100.0))
    if fill_x > bar_x0 + 1:
        draw.rounded_rectangle(
            [bar_x0, bar_y0, fill_x, bar_y1],
            radius=7, fill=color,
        )

    _draw_footer(draw, font_small)
    return _to_png_bytes(img)
