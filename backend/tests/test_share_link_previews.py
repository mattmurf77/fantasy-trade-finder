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
"""
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.server as server
from backend.database import metadata

SID = "pkgPreview1"
ROBOTS_TXT = Path(__file__).resolve().parents[2] / "web" / "robots.txt"


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

@pytest.mark.parametrize("page, image_path", [
    (f"/s/p/{SID}", f"/og/p/{SID}.png"),
    ("/s/trade/m123", "/og/trade/m123.png"),
])
@pytest.mark.parametrize("is_prod, origin", [
    (False, "http://localhost"),
    (True, "https://localhost"),
])
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
    "/s/trade/m123",
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
    "/og/trade/m123.png",
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
