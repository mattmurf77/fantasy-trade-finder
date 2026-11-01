"""Share links unfurl into previews (Product pre-launch review, item C6).

Two things kept `/s/*` links from unfurling in iMessage / Slack / X / Discord:
  1. `og:image` / `twitter:image` were root-relative ("/og/p/<id>.png").
     Unfurlers need an absolute URL. Deployed envs are forced to https
     (Render terminates TLS; no ProxyFix, so request.scheme reads "http").
  2. `web/robots.txt` disallowed `/s/` and `/og/`, so robots-honouring
     unfurlers (Twitterbot, Slackbot) never fetched the page or the card.

Opening the paths to crawlers is only safe with `noindex` on both the
landing (meta + X-Robots-Tag) and the PNG (X-Robots-Tag), pinned here.
The JSON contract of POST /api/share/package (relative url/og_image) is
pinned separately in test_share_package.py and must not change.

Trade links are token-only since #362 (build O8): section 4 covers a live
/s/trade/<token> page, the expired page every miss gets, and both PNGs,
minting tokens with test_trade_share_tokens.py's fixture and helpers.

Section 5 pins legal R13 on every /s/* page: a Privacy link, the Fleeced
brand (no "Fantasy Trade Finder"), tokens.css, and the og PNG footer.

Section 6 pins the og trade card fixes on a real render: no fairness number
or meter (models-lead I6 replaced B1), no missing-glyph box or centre disc,
and the position chips use the cross-client position colours with ink-0
labels.

Section 7 pins the same ink-0 label on the tier card's position chip
(/og/tiers/<pos>/<username>.png, dark behind growth.tier_board_share).

Section 8 pins the recentred trade card layout and the "+N more" row for a
side with more than 3 players.

Section 9 pins the live /s/trade and /s/p descriptions to marketing's
fallback lines (addendum 14 Part A): with the card's fairness number gone,
no page promises one, and "fair" appears nowhere on either page.
"""
import io
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db_module
import backend.server as server
from backend import og_image
from backend.database import metadata
from backend.tests.test_trade_share_tokens import (  # noqa: F401  (env is a fixture)
    SHARE_ON, USER_A, _add_match, _mint, env,
)

SID = "pkgPreview1"
ROBOTS_TXT = Path(__file__).resolve().parents[2] / "web" / "robots.txt"
INVARIANTS_MD = Path(__file__).resolve().parents[2] / "docs" / "cross-client-invariants.md"


def _flags(*enabled):
    on = set(enabled)
    return lambda k: k in on


ALL_SHARE_FLAGS = _flags("growth.share_landing", "growth.tier_board_share")


@pytest.fixture()
def client():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", ALL_SHARE_FLAGS):
        assert db_module.create_shared_package(SID, "888888888800000002",
                                               ["4034"], ["7564"])
        yield server.app.test_client()


def _meta(html: str, attr: str, name: str) -> str:
    m = re.search(rf'<meta {attr}="{re.escape(name)}" content="([^"]*)">', html)
    assert m, f"no <meta {attr}={name!r}> in page"
    return m.group(1)


# ---------------------------------------------------------------------------
# 1. og:image / twitter:image are absolute; path unchanged
# ---------------------------------------------------------------------------

# /s/trade/<token> is in section 4 (token-only since #362).
ORIGINS = [
    (False, "http://localhost"),
    (True, "https://localhost"),
]


@pytest.mark.parametrize("page, image_path", [
    (f"/s/p/{SID}", f"/og/p/{SID}.png"),
])
@pytest.mark.parametrize("is_prod, origin", ORIGINS)
def test_og_and_twitter_image_are_absolute(client, page, image_path,
                                           is_prod, origin):
    with patch.object(server, "_IS_PROD_ENV", is_prod):
        r = client.get(page)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert _meta(html, "property", "og:image") == origin + image_path
    assert _meta(html, "name", "twitter:image") == origin + image_path


# ---------------------------------------------------------------------------
# 2. noindex: meta + header on /s/*, header on /og/*.png
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("page", [
    f"/s/p/{SID}",
    "/s/tiers/qb/someuser",
])
def test_share_pages_are_noindex(client, page):
    r = client.get(page)
    assert r.status_code == 200
    assert _meta(r.get_data(as_text=True), "name", "robots") == "noindex"
    assert r.headers.get("X-Robots-Tag") == "noindex"
    assert r.headers["Cache-Control"] == "public, max-age=300"


class _StubRenderer:
    """Stand-in for backend.og_image — the header is the subject, not Pillow."""
    PNG = b"\x89PNG\r\n\x1a\nstub"

    def render_package_card(self, *_a):
        return self.PNG, 200

    def render_trade_card(self, *_a):
        return self.PNG, 200

    def render_tier_card(self, *_a):
        return self.PNG, 200


@pytest.mark.parametrize("path", [
    f"/og/p/{SID}.png",
    "/og/tiers/qb/someuser.png",
])
def test_og_cards_carry_noindex_header(client, path):
    with patch.object(server, "_og_image", _StubRenderer()):
        r = client.get(path)
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "image/png"
    assert r.headers.get("X-Robots-Tag") == "noindex"
    assert r.headers["Cache-Control"] == "public, max-age=300"


# ---------------------------------------------------------------------------
# 3. robots.txt lets unfurlers in, keeps every other rule
# ---------------------------------------------------------------------------

def _disallows() -> list[str]:
    return [line.split(":", 1)[1].strip()
            for line in ROBOTS_TXT.read_text().splitlines()
            if line.lower().startswith("disallow:")]


def test_robots_txt_does_not_block_share_paths():
    for rule in _disallows():
        for path in (f"/s/p/{SID}", "/s/trade/m123", f"/og/p/{SID}.png"):
            assert not (rule and path.startswith(rule)), \
                f"robots.txt 'Disallow: {rule}' blocks {path}"


def test_robots_txt_keeps_other_disallows():
    expected = {
        "/admin/",
        "/style-guide.html",
        "/color-lab.html",
        "/color-lab-2.html",
        "/calculator.html",
        "/league-rankings.html",
        "/player.html",
        "/profile.html",
        "/404.html",
    }
    assert expected <= set(_disallows())


# ---------------------------------------------------------------------------
# 4. Token-only trade links (#362, build O8): live page, expired page, PNGs
# ---------------------------------------------------------------------------

UNKNOWN_TOKEN = "A" * 22


def _live_token(c) -> str:
    """Mint a real share token for a fresh mutual match, as USER_A."""
    with patch.object(server, "is_enabled", SHARE_ON):
        r = _mint(c, USER_A, _add_match())
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["token"]


def _miss(c, kind: str) -> str:
    if kind == "numeric_id":     # the id of a match that has a live share
        mid = _add_match()
        with patch.object(server, "is_enabled", SHARE_ON):
            assert _mint(c, USER_A, mid).status_code == 200
        return str(mid)
    if kind == "unknown_token":
        return UNKNOWN_TOKEN
    raise AssertionError(kind)


def _assert_unfurlable_noindex(r, image_url: str) -> str:
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert _meta(html, "property", "og:image") == image_url
    assert _meta(html, "name", "twitter:image") == image_url
    assert len(re.findall(r'<meta name="robots"', html)) == 1
    assert _meta(html, "name", "robots") == "noindex"
    assert r.headers.get("X-Robots-Tag") == "noindex"
    return html


@pytest.mark.parametrize("is_prod, origin", ORIGINS)
def test_live_trade_page_is_absolute_and_noindex(env, is_prod, origin):
    tok = _live_token(env)
    with patch.object(server, "_IS_PROD_ENV", is_prod):
        r = env.get(f"/s/trade/{tok}")
    html = _assert_unfurlable_noindex(r, f"{origin}/og/trade/{tok}.png")
    assert "Trade Match" in html                      # the hit, not the miss
    assert f'<img src="/og/trade/{tok}.png"' in html  # visible <img> stays relative


@pytest.mark.parametrize("kind", ["numeric_id", "unknown_token"])
@pytest.mark.parametrize("is_prod, origin", ORIGINS)
def test_expired_trade_page_is_absolute_and_noindex(env, kind, is_prod, origin):
    key = _miss(env, kind)
    with patch.object(server, "_IS_PROD_ENV", is_prod):
        r = env.get(f"/s/trade/{key}")
    html = _assert_unfurlable_noindex(r, f"{origin}/og/trade/expired.png")
    assert og_image.TRADE_LINK_EXPIRED_TITLE in html
    assert "Trade Match" not in html


@pytest.mark.parametrize("kind", ["live", "numeric_id", "unknown_token", "expired"])
def test_trade_cards_carry_noindex_header(env, kind):
    if kind == "live":
        key = _live_token(env)
    elif kind == "expired":          # the expired page's own og:image
        key = "expired"
    else:
        key = _miss(env, kind)
    r = env.get(f"/og/trade/{key}.png")
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "image/png"
    assert r.headers.get("X-Robots-Tag") == "noindex"
    assert r.headers["Cache-Control"] == "public, max-age=300"
    is_miss_card = r.data == og_image.render_expired_trade_card()
    assert is_miss_card is (kind != "live")


# ---------------------------------------------------------------------------
# 5. Legal R13: privacy link + Fleeced brand on every /s/* page, og footer
# ---------------------------------------------------------------------------

PRIVACY_LINK = '<a href="/privacy">Privacy</a>'
BRAND_DIV = '<div class="brand">Fleeced: Dynasty Trade Finder</div>'
TOKENS_CSS = '<link rel="stylesheet" href="/css/tokens.css">'
OG_FOOTER = "Fleeced: Dynasty Trade Finder · fantasy-trade-finder.onrender.com"


def _assert_r13(r) -> None:
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert html.count(PRIVACY_LINK) == 1
    assert "Fantasy Trade Finder" not in html
    titles = re.findall(r"<title>[^<]*</title>", html)
    assert len(titles) == 1 and titles[0].endswith(
        " · Fleeced: Dynasty Trade Finder</title>"), titles
    assert html.count(BRAND_DIV) == 1
    # .brand reads var(--chalk-dim) from tokens.css (AA contrast on #0f1322).
    brand_rules = re.findall(r"\.brand\{[^}]*\}", html)
    assert len(brand_rules) == 1 and "color:var(--chalk-dim);" in brand_rules[0], \
        brand_rules
    # The link sits directly after the brand div, inside .card.
    assert re.search(re.escape(BRAND_DIV) + r'\s*<div class="legal-links">'
                     + re.escape(PRIVACY_LINK) + r"</div>\s*</div>\s*</body>",
                     html)
    assert html.count(TOKENS_CSS) == 1


@pytest.mark.parametrize("page", [
    f"/s/p/{SID}",
    "/s/tiers/qb/someuser",
])
def test_share_pages_carry_privacy_link_and_fleeced_brand(client, page):
    _assert_r13(client.get(page))


@pytest.mark.parametrize("kind", ["live", "numeric_id", "unknown_token"])
def test_trade_pages_carry_privacy_link_and_fleeced_brand(env, kind):
    key = _live_token(env) if kind == "live" else _miss(env, kind)
    r = env.get(f"/s/trade/{key}")
    _assert_r13(r)
    html = r.get_data(as_text=True)
    if kind == "live":
        assert "Trade Match" in html
    else:
        assert og_image.TRADE_LINK_EXPIRED_TITLE in html


def test_privacy_link_target_exists(client):
    assert client.get("/privacy").status_code == 200


def test_og_footer_brand_is_fleeced_source_level():
    """SOURCE-LEVEL check, not a pixel check: reads og_image.py as text.

    It proves the old brand string is gone from the module and the footer
    assignment is marketing's approved string. It does not prove what the
    PNG shows; the next test spies on the drawn text for that.
    """
    src = Path(og_image.__file__).read_text()
    assert "Fantasy Trade Finder" not in src
    footers = re.findall(r"^\s*footer = (.+)$", src, re.M)
    assert footers == [f'"{OG_FOOTER}"'], footers


def test_og_trade_card_still_renders_with_fleeced_footer(env):
    tok = _live_token(env)
    text = og_image.ImageDraw.ImageDraw.text
    with patch.object(og_image.ImageDraw.ImageDraw, "text", autospec=True,
                      side_effect=text) as spy:
        r = env.get(f"/og/trade/{tok}.png")
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "image/png"
    assert r.data[:8] == b"\x89PNG\r\n\x1a\n"
    drawn = [c.args[2] if len(c.args) > 2 else c.kwargs.get("text")
             for c in spy.call_args_list]
    assert OG_FOOTER in drawn
    assert not any("Fantasy Trade Finder" in str(t) for t in drawn)


# ---------------------------------------------------------------------------
# 6. og trade card B1-B3 (design-lead review; Product: before launch)
# ---------------------------------------------------------------------------

INK_0 = (12, 14, 17)


def _spied_get(c, path, flags=None):
    """GET an og PNG, recording every text, line, rounded_rectangle and
    ellipse call on any canvas, in draw order."""
    calls = []
    cls = og_image.ImageDraw.ImageDraw

    def spy(name):
        real = getattr(cls, name)

        def wrapper(self, *a, **kw):
            calls.append((name, a, kw))
            return real(self, *a, **kw)
        return wrapper

    with patch.object(server, "is_enabled", flags or SHARE_ON), \
         patch.object(cls, "text", spy("text")), \
         patch.object(cls, "line", spy("line")), \
         patch.object(cls, "rounded_rectangle", spy("rounded_rectangle")), \
         patch.object(cls, "ellipse", spy("ellipse")):
        r = c.get(path)
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "image/png"
    return r, calls


def _spied_trade_card(env):
    """Render a live /og/trade/<token>.png through _spied_get."""
    return _spied_get(env, f"/og/trade/{_live_token(env)}.png")


def _texts(calls):
    return [(a[0], a[1], kw) for name, a, kw in calls if name == "text"]


def test_og_trade_card_has_no_fairness_number_or_meter(env):
    """models-lead I6 (replaces B1): the search-rank "% fair" number is gone.
    No drawn text has a percentage or the word "fair", nothing is drawn in the
    old meter band (y 500-540), and _compute_fairness no longer exists."""
    _, calls = _spied_trade_card(env)
    for _, text, _ in _texts(calls):
        assert not re.search(r"\d+\s*%", text), text
        assert "fair" not in text.lower(), text
    for name, a, _ in calls:
        if name == "rounded_rectangle":
            _, y0, _, y1 = a[0]
            assert not (y0 <= 540 and y1 >= 500), a[0]
    assert not hasattr(og_image, "_compute_fairness")
    assert not hasattr(og_image, "_fairness_color")


# Every glyph here is in each font og_image can load (Arial, Helvetica, SF,
# DejaVu): printable ASCII plus the "·" footer separator, the "—" empty-side
# dash and the "…" truncation ellipsis.
SAFE_CHARS = {chr(c) for c in range(0x20, 0x7F)} | {"·", "—", "…"}


def test_og_trade_card_b2_no_missing_glyph_or_centre_disc(env):
    """B2: no drawn text uses U+21C4 "⇄" or any character outside SAFE_CHARS
    (printable ASCII U+0020-U+007E, U+00B7 "·", U+2014 "—", U+2026 "…"),
    and nothing is drawn in the card centre between the two columns: no
    ellipse covers it and its pixels are the plain background."""
    r, calls = _spied_trade_card(env)
    for _, text, _ in _texts(calls):
        assert "⇄" not in text
        assert set(text) <= SAFE_CHARS, (text, set(text) - SAFE_CHARS)
    cx, cy = og_image.CARD_W // 2, (175 + 455) // 2   # between the columns
    for name, a, _ in calls:
        if name == "ellipse":
            x0, y0, x1, y1 = a[0]
            assert not (x0 <= cx <= x1 and y0 <= cy <= y1), a[0]
    card = og_image.Image.open(io.BytesIO(r.data)).convert("RGB")
    canvas = og_image._new_canvas()
    for dx in range(-30, 31, 5):
        for dy in range(-30, 31, 5):
            p = (cx + dx, cy + dy)
            assert card.getpixel(p) == canvas.getpixel(p), p


def _invariant_position_colors() -> dict:
    doc = INVARIANTS_MD.read_text()
    section = doc.split("## Position color tokens", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\| (QB|RB|WR|TE) \| [^|]+\| `#([0-9a-fA-F]{6})` \|$",
                      section, re.M)
    return {pos: tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) for pos, h in rows}


def test_og_trade_card_b3_position_colours_match_invariants(env):
    """B3: POS_COLORS equals docs/cross-client-invariants.md § Position color
    tokens, and the trade card's chip labels are ink-0 on those chips."""
    doc = _invariant_position_colors()
    assert sorted(doc) == ["QB", "RB", "TE", "WR"], doc
    assert og_image.POS_COLORS == doc
    _, calls = _spied_trade_card(env)
    chips = [a[0] for name, a, kw in calls
             if name == "rounded_rectangle" and kw.get("fill") == doc["WR"]]
    labels = [kw["fill"] for _, text, kw in _texts(calls) if text in doc]
    assert len(chips) == 2 and len(labels) == 2, (chips, labels)  # one WR per side
    assert labels == [INK_0, INK_0]


# ---------------------------------------------------------------------------
# 7. og tier card position label is ink-0 (B3 follow-up; flag dark)
# ---------------------------------------------------------------------------

TIER_USER = "888888888800000201"
TIER_USERNAME = "tierboardowner"


def _wcag_contrast(fg, bg) -> float:
    """WCAG 2.2 contrast ratio of two sRGB 0-255 colours (see the test)."""
    def lum(rgb):
        c = [v / 255 for v in rgb]
        c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted((lum(fg), lum(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _spied_tier_card(env, pos):
    """Render a filled /og/tiers/<pos>/<username>.png with the flag on,
    recording every text and rounded_rectangle call, in draw order."""
    calls = []
    cls = og_image.ImageDraw.ImageDraw

    def spy(name):
        real = getattr(cls, name)

        def wrapper(self, *a, **kw):
            calls.append((name, a, kw))
            return real(self, *a, **kw)
        return wrapper

    with patch.object(server, "is_enabled", ALL_SHARE_FLAGS), \
         patch.object(cls, "text", spy("text")), \
         patch.object(cls, "rounded_rectangle", spy("rounded_rectangle")):
        r = env.get(f"/og/tiers/{pos.lower()}/{TIER_USERNAME}.png")
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "image/png"
    return calls


def test_og_tier_card_position_label_is_ink_0(env):
    """For each POS_COLORS position, the tier card's 58px position label is
    drawn on its POS_COLORS chip in ink-0 (12, 14, 17), and that label clears
    the WCAG 2.2 large-text bar (SC 1.4.3, 3:1) on the chip. Contrast is the
    WCAG 2.2 formula: each sRGB channel c = v/255 is linearised as c/12.92 if
    c <= 0.04045 else ((c + 0.055)/1.055)^2.4; relative luminance
    L = 0.2126 R + 0.7152 G + 0.0722 B; ratio = (L_hi + 0.05)/(L_lo + 0.05)."""
    db_module.upsert_user(TIER_USER, username=TIER_USERNAME, display_name="Tier Owner")
    with db_module.engine.begin() as conn:
        for pos in og_image.POS_COLORS:
            conn.execute(insert(db_module.players_table).values(
                player_id=f"tier-{pos}", full_name=f"Tierboard {pos}",
                position=pos, search_rank=10))
    db_module.save_tier_overrides(
        TIER_USER, {f"tier-{pos}": 1700.0 for pos in og_image.POS_COLORS},
        scoring_format="1qb_ppr")

    for pos, chip_fill in og_image.POS_COLORS.items():
        calls = _spied_tier_card(env, pos)
        texts = [a[1] for name, a, _ in calls if name == "text"]
        assert f"Tierboard {pos}" in texts, texts          # the filled card
        chips = [a[0] for name, a, kw in calls
                 if name == "rounded_rectangle" and kw.get("fill") == chip_fill]
        labels = [(a[0], kw["font"].getbbox(pos), kw["fill"]) for name, a, kw in calls
                  if name == "text" and a[1] == pos]
        assert len(chips) == 1 and len(labels) == 1, (pos, chips, labels)
        (x0, y0, x1, y1), ((lx, ly), (l, t, r, b), fill) = chips[0], labels[0]
        cx, cy = lx + (l + r) / 2, ly + (t + b) / 2      # glyph-box centre
        assert x0 <= cx <= x1 and y0 <= cy <= y1, (pos, chips[0], labels[0])
        assert _wcag_contrast(fill, chip_fill) >= 3.0, (pos, chip_fill, fill)
        assert fill == INK_0, (pos, fill)


# ---------------------------------------------------------------------------
# 8. og trade card: recentred layout, "+N more" past 3 players a side
# ---------------------------------------------------------------------------

PANEL_FILL = (255, 255, 255, 18)


def test_og_trade_card_layout_is_recentred(env):
    """With the verdict gone the card is recentred (design-lead): the title
    is drawn at y=85, both give/get panels span y 175-455, and the footer
    rule stays at y=560."""
    _, calls = _spied_trade_card(env)
    panels = [a[0] for name, a, kw in calls
              if name == "rounded_rectangle" and kw.get("fill") == PANEL_FILL]
    assert len(panels) == 2, panels
    assert all((p[1], p[3]) == (175, 455) for p in panels), panels
    titles = [xy for xy, text, _ in _texts(calls) if text == "Trade Match"]
    assert titles == [(60, 85)], titles
    rules = [a[0] for name, a, _ in calls if name == "line"]
    assert rules == [[(60, 560), (og_image.CARD_W - 60, 560)]], rules


MORE_RE = re.compile(r"\+\d+ more")
GIVE = [("np1", "Avery Firstman", "WR"), ("np2", "Blake Secondo", "RB"),
        ("np3", "Casey Thirdly", "QB"), ("np4", "Drew Fourtner", "TE"),
        ("np5", "Emery Fifthson", "WR")]


@pytest.mark.parametrize("n", [3, 4, 5])
def test_og_package_card_caps_a_side_at_two_names_plus_n_more(env, n):
    """A side of 3 draws all 3 names. Over 3, it draws the first 2 names and
    then "+N more" (N = len - 2) in TEXT_MUTED, at the third row's y and in
    the player-name font. Rendered through /og/p (render_package_card)."""
    with db_module.engine.begin() as conn:
        for pid, name, pos in GIVE[:n] + [("np9", "Gale Getter", "RB")]:
            conn.execute(insert(db_module.players_table).values(
                player_id=pid, full_name=name, position=pos, search_rank=50))
    sid = f"pkgMore{n}"
    assert db_module.create_shared_package(sid, USER_A, [p for p, _, _ in GIVE[:n]],
                                           ["np9"])
    _, calls = _spied_get(env, f"/og/p/{sid}.png")
    texts = _texts(calls)
    drawn = [text for _, text, _ in texts]
    names = [name for _, name, _ in GIVE[:n]]
    more = [(xy, text, kw) for xy, text, kw in texts if MORE_RE.fullmatch(text)]
    if n == 3:
        assert all(name in drawn for name in names), drawn
        assert more == []
        return
    assert names[:2] == [t for t in drawn if t in names], drawn   # only the first 2
    assert [text for _, text, _ in more] == [f"+{n - 2} more"]
    (x, y), _, kw = more[0]
    assert kw["fill"] == og_image.TEXT_MUTED
    name_fonts = {id(k["font"]) for _, t, k in texts if t in names}
    assert name_fonts == {id(kw["font"])}                 # the player-name font
    assert (x, y) == (60 + 24, 175 + 70 + 2 * 66 + 6)     # third row, give side


def test_og_package_card_names_the_calculators_generic_picks(env):
    """The live calculator's pool holds 12 generic pick rungs that aren't
    players rows; a shared package holding one drew "Unknown player". They
    draw the calculator's label and the "PK" chip on chalk-dim (#564's look);
    an id the shared parser rejects (a round that doesn't exist, an extra
    part) still says "Unknown player"."""
    with db_module.engine.begin() as conn:
        conn.execute(insert(db_module.players_table).values(
            player_id="np1", full_name="Avery Firstman", position="WR", search_rank=50))
    assert db_module.create_shared_package(
        "pkgPicks", USER_A, ["np1", "generic_pick_1_mid_x"],
        ["generic_pick_1_mid", "generic_pick_2_late", "generic_pick_9_mid"])
    _, calls = _spied_get(env, "/og/p/pkgPicks.png")
    drawn = [text for _, text, _ in _texts(calls)]
    assert "Mid 1st Round Pick" in drawn and "Late 2nd Round Pick" in drawn, drawn
    assert drawn.count("PK") == 2 and drawn.count("Unknown player") == 2, drawn
    fills = [kw.get("fill") for name, args, kw in calls if name == "rounded_rectangle"]
    assert og_image.PICK_CHIP_FILL == (151, 161, 174)        # chalk-dim, #564's chip
    assert fills.count((151, 161, 174)) == 2, fills


# ---------------------------------------------------------------------------
# 9. Share-page descriptions promise no fairness read (addendum 14 Part A)
# ---------------------------------------------------------------------------

TRADE_DESCRIPTION = "A dynasty fantasy trade. See the give/get breakdown."
PACKAGE_DESCRIPTION = "A 2-player dynasty trade package. See the give/get breakdown."


def _assert_description_without_fair(html: str, description: str) -> None:
    """The one description feeds meta description, og:description,
    twitter:description and the visible <p>; "fair" is on none of the page."""
    assert _meta(html, "name", "description") == description
    assert _meta(html, "property", "og:description") == description
    assert _meta(html, "name", "twitter:description") == description
    assert html.count(f"<p>{description}</p>") == 1
    assert "fair" not in html.lower(), re.findall(r".{0,40}fair.{0,40}", html, re.I)


def test_live_trade_page_description_has_no_fairness(env):
    tok = _live_token(env)
    r = env.get(f"/s/trade/{tok}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Trade Match" in html                      # the hit, not the miss
    # The random token sits in the image URLs; mask it so a token that
    # happens to contain "fair" cannot flake the check.
    _assert_description_without_fair(html.replace(tok, "<token>"), TRADE_DESCRIPTION)


def test_package_page_description_has_no_fairness(client):
    r = client.get(f"/s/p/{SID}")                     # 1 give + 1 receive: n = 2
    assert r.status_code == 200
    _assert_description_without_fair(r.get_data(as_text=True), PACKAGE_DESCRIPTION)
