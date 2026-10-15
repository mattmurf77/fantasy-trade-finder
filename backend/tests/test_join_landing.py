"""Referral loop D-1 — device-aware install CTA on the join and share landings.

Spec: docs/plans/referral-loop/prd.md @ 9adbf4ce (§5, J2, FR-7, FR-8, §8.2,
§10, §11) and engagement-eng's D-1 design (§0 rulings, §7 evidence plan).

What is pinned here (D-056 evidence; the 302's own contract stays in
test_invite_links.py T4–T7, which must pass unmodified):

  * the join route's two modes behind `growth.join_landing` (302 vs landing),
    the device × IOS_INSTALL_URL CTA matrix (AC-7c), landing contents
    (AC-7b, AC-7d, AC-7e) and the FR-7 headline ladder;
  * the /go/<cta> click-through: closed set, 404s, closed onward query;
  * FR-8 open recording: human / preview / empty-UA / HEAD × the four
    invite_status values and their event owners, plus C6 (the inviter's
    users row never moves);
  * record_event's two new keyword arguments keep today's defaults;
  * the /s/* CTA: /?share=<kind> href, the phone matrix, private + Vary;
  * flag and event registration.

Every test runs against a throwaway SQLite file, never data/trade_finder.db,
and never reaches Sleeper (`_fetch_sleeper_league_meta` is stubbed).
"""
import json
import logging
import pathlib
import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, insert, select, text, update

import backend.analytics_queries as aq
import backend.analytics_taxonomy as at
import backend.database as db_module
import backend.feature_flags as feature_flags
import backend.server as server
from backend.database import (
    metadata, referrals_table, user_events_table, users_table,
)

REPO = pathlib.Path(__file__).resolve().parents[2]

LEAGUE = "990000000000000001"
LEAGUE_NAME = "Lakeview Dynasty"
REFERRER = "u_referrer_1"
REFERRER_NAME = "Matt R"
T_VALID = "AbCdEf123456"
T_EXPIRED = "ExPiReD12345"
T_MISMATCH = "MiSmAtCh1234"
T_UNKNOWN = "UnKnOwN12345"
IOS_URL = "https://testflight.apple.com/join/AbCdEfGh"
PRIOR_ACTIVE = "2026-01-01T00:00:00+00:00"

UA = {
    "iphone": ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
               "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 "
               "Mobile/15E148 Safari/604.1"),
    "ipod": ("Mozilla/5.0 (iPod touch; CPU iPhone OS 15_7 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6 "
             "Mobile/15E148 Safari/604.1"),
    "ipad_legacy": ("Mozilla/5.0 (iPad; CPU OS 12_2 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.1 "
                    "Mobile/15E148 Safari/604.1"),
    # iPadOS Safari's default: a Macintosh UA. Reads as desktop by design.
    "ipados_desktop": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                       "Version/17.5 Safari/605.1.15"),
    "android": ("Mozilla/5.0 (Linux; Android 14; Pixel 8) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Mobile Safari/537.36"),
    "other_mobile": ("Mozilla/5.0 (Mobile; Nokia_8110_4G; rv:48.0) "
                     "Gecko/48.0 Firefox/48.0 KAIOS/2.5"),
    "opera_mini": ("Opera/9.80 (J2ME/MIDP; Opera Mini/9.80 (S60; SymbOS; "
                   "Opera Mobi/23.348; U; en) Presto/2.5.25 Version/10.54"),
    "desktop_chrome": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/126.0.0.0 Safari/537.36"),
}

PREVIEW_UA = {
    "imessage": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_1) "
                 "AppleWebKit/601.2.4 (KHTML, like Gecko) Version/9.0.1 "
                 "Safari/601.2.4 facebookexternalhit/1.1 Facebot "
                 "Twitterbot/1.0"),
    "slack": "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
    "slack_img": "Slack-ImgProxy (+https://api.slack.com/robots)",
    "discord": ("Mozilla/5.0 (compatible; Discordbot/2.0; "
                "+https://discordapp.com)"),
    "whatsapp": "WhatsApp/2.23.20.0 A",
    "telegram": "TelegramBot (like TwitterBot)",
    "linkedin": ("LinkedInBot/1.0 (compatible; Mozilla/5.0; Apache-HttpClient "
                 "+http://www.linkedin.com)"),
    "x": "Twitterbot/1.0",
    "googlebot": ("Mozilla/5.0 (compatible; Googlebot/2.1; "
                  "+http://www.google.com/bot.html)"),
    "crawler": "SomeCrawler/3.1",
    "spider": "Baiduspider/2.0",
}

# Lines from marketing-lead's proposed gp.join.* table (verbatim).
IOS_CTA = "Get the iOS beta"
IOS_HELP = "Installs through Apple&#x27;s TestFlight app."
WEB_CTA = "Open the web app"
WEB_HELP = "Sign-in uses the Fleeced extension for Chrome or Edge."
IOS_SECONDARY = "On an iPhone or iPad?"
A2_NOTE = ("The iPhone beta isn&#x27;t open to the public yet. Already have "
           "it? Open the invite in the app.")
SHARE_IOS_NOTE = "The iPhone beta isn&#x27;t open to the public yet."
ANDROID_NOTE = "Fleeced runs on iPhone and desktop web for now."


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    """A throwaway DB, no Sleeper egress, the URL unset, flags OFF."""
    engine = create_engine(f"sqlite:///{tmp_path / 'join.db'}",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(server, "_fetch_sleeper_league_meta",
                        lambda lid: {"name": LEAGUE_NAME})
    monkeypatch.delenv("IOS_INSTALL_URL", raising=False)
    monkeypatch.setattr(server, "is_enabled", _flags())
    server.app.config["TESTING"] = True
    return engine


def _flags(*enabled):
    on = set(enabled)
    return lambda k: k in on


def _set_flags(monkeypatch, *enabled):
    monkeypatch.setattr(server, "is_enabled", _flags(*enabled))


LANDING = ("growth.join_landing",)
LEDGER = ("growth.referral_ledger",)
BOTH = LANDING + LEDGER


def _client():
    return server.app.test_client()


def _get(path, ua=UA["desktop_chrome"], method="GET"):
    """ua=None sends an EMPTY User-Agent (the Flask test client would
    otherwise send its own "Werkzeug/x" UA)."""
    return _client().open(path, method=method,
                          headers={"User-Agent": "" if ua is None else ua})


def _iso(dt):
    return dt.isoformat()


def _seed(engine):
    """The referrer's users row and one referrals row per invite_status."""
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(insert(users_table).values(
            sleeper_user_id=REFERRER, username="mattref",
            display_name=REFERRER_NAME, last_active_at=PRIOR_ACTIVE,
            events_count=5))
        for tok, league, age in ((T_VALID, LEAGUE, 1),
                                 (T_EXPIRED, LEAGUE, 31),
                                 (T_MISMATCH, "424242", 1)):
            conn.execute(insert(referrals_table).values(
                referrer_user_id=REFERRER, league_id=league,
                invite_token=tok, status="pending",
                created_at=_iso(now - timedelta(days=age))))


def _referral(engine, tok):
    with engine.connect() as conn:
        row = conn.execute(select(referrals_table).where(
            referrals_table.c.invite_token == tok)).fetchone()
    return dict(row._mapping) if row else None


def _events(engine, name=None):
    q = select(user_events_table)
    if name:
        q = q.where(user_events_table.c.event_type == name)
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(q).fetchall()]


def _user(engine, uid=REFERRER):
    with engine.connect() as conn:
        row = conn.execute(select(users_table).where(
            users_table.c.sleeper_user_id == uid)).fetchone()
    return dict(row._mapping)


def _visible_text(html):
    """The page minus tags — what a reader sees, plus nothing in attributes."""
    body = html.split("<body>", 1)[1]
    return re.sub(r"<[^>]+>", " ", body)


# ═══════════════════════════════════════════════════════════════════════════
# Classifiers and config
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("key,expected", [
    ("iphone", "ios"), ("ipod", "ios"), ("ipad_legacy", "ios"),
    ("ipados_desktop", "desktop"), ("android", "android"),
    ("other_mobile", "other"), ("opera_mini", "other"),
    ("desktop_chrome", "desktop"),
])
def test_device_class(key, expected):
    assert server.device_class(UA[key]) == expected


def test_device_class_of_nothing_is_desktop():
    assert server.device_class(None) == "desktop"
    assert server.device_class("") == "desktop"


@pytest.mark.parametrize("key", sorted(PREVIEW_UA))
def test_preview_fetchers_are_recognised(key):
    assert server.is_preview_fetcher(PREVIEW_UA[key])


@pytest.mark.parametrize("key", sorted(UA))
def test_human_browsers_are_not_preview_fetchers(key):
    assert not server.is_preview_fetcher(UA[key])


def test_empty_user_agent_counts_as_preview():
    assert server.is_preview_fetcher(None)
    assert server.is_preview_fetcher("")
    assert server.is_preview_fetcher("   ")


def test_preview_token_constant_covers_the_named_fetchers():
    """The design names these; dropping one from the constant is a red."""
    tokens = {t.lower() for t in server.PREVIEW_UA_TOKENS}
    for need in ("facebookexternalhit", "twitterbot", "slackbot",
                 "slack-imgproxy", "discordbot", "whatsapp", "telegrambot",
                 "linkedinbot", "bot", "crawler", "spider"):
        assert need in tokens, need


def test_ios_install_url_https_only(monkeypatch, caplog):
    monkeypatch.setattr(server, "_ios_install_url_warned", False)
    assert server.ios_install_url() is None                 # unset
    monkeypatch.setenv("IOS_INSTALL_URL", f"  {IOS_URL}  ")
    assert server.ios_install_url() == IOS_URL               # stripped
    with caplog.at_level(logging.WARNING, logger="trade_finder"):
        for bad in ("http://testflight.apple.com/join/x",
                    "javascript:alert(1)", "testflight.apple.com/join/x",
                    "//evil.example/x"):
            monkeypatch.setenv("IOS_INSTALL_URL", bad)
            assert server.ios_install_url() is None, bad
    warnings = [r for r in caplog.records if "IOS_INSTALL_URL" in r.getMessage()]
    assert len(warnings) == 1, "a bad value must warn exactly once"


@pytest.mark.parametrize("raw,ok", [
    ("AbCdEf12", True), ("a" * 64, True), ("Ab_-0123456", True),
    ("AbCdEf1", False), ("a" * 65, False), ("AbCdEf12!", False),
    ("AbCdEf12\n", False), ("AbCd Ef12", False), ("", False), (None, False),
])
def test_invite_id_pattern(raw, ok):
    assert (server._invite_id_from(raw) is not None) is ok


def test_invite_id_re_is_defined_once():
    """Contract C1: one definition, in server.py's join-path code."""
    needle = "INVITE_ID_RE" + " = re.compile"   # split so this file can't match
    hits = [p for p in (REPO / "backend").rglob("*.py")
            if needle in p.read_text()]
    assert [p.name for p in hits] == ["server.py"]
    assert server.INVITE_ID_RE.pattern == r"^[A-Za-z0-9_-]{8,64}$"


# ═══════════════════════════════════════════════════════════════════════════
# Join route, flag OFF — the 302 (T4–T7 live in test_invite_links.py)
# ═══════════════════════════════════════════════════════════════════════════

def test_flag_off_302_ignores_t_while_the_ledger_is_off():
    r = _get(f"/app/league/join/123?ref=matt&t={T_VALID}")
    assert r.status_code == 302
    assert r.headers["Location"] == "/?league=123&ref=matt"


def test_flag_off_302_forwards_a_well_formed_t_with_the_ledger_on(monkeypatch):
    _set_flags(monkeypatch, *LEDGER)
    r = _get(f"/app/league/join/123?ref=matt&t={T_VALID}&utm_source=x")
    assert r.headers["Location"] == f"/?league=123&ref=matt&t={T_VALID}"
    r = _get(f"/app/league/join/123?t={T_VALID}")
    assert r.headers["Location"] == f"/?league=123&t={T_VALID}"


@pytest.mark.parametrize("bad", ["short", "AbCdEf12%0A", "AbCd%26x%3D1234",
                                 "a" * 65])
def test_flag_off_302_drops_a_malformed_t(monkeypatch, bad):
    _set_flags(monkeypatch, *LEDGER)
    r = _get(f"/app/league/join/123?ref=matt&t={bad}")
    assert r.headers["Location"] == "/?league=123&ref=matt"


# ═══════════════════════════════════════════════════════════════════════════
# Join route, flag ON — the landing
# ═══════════════════════════════════════════════════════════════════════════

# (UA key, URL set?) → which of the CTA pieces render. AC-7c.
CTA_MATRIX = [
    ("iphone",         True,  {"ios_btn", "ios_help", "retap"}),
    ("iphone",         False, {"a2"}),
    ("ipod",           True,  {"ios_btn", "ios_help", "retap"}),
    ("ipad_legacy",    False, {"a2"}),
    ("android",        True,  {"android"}),
    ("android",        False, {"android"}),
    ("other_mobile",   True,  {"android"}),
    ("other_mobile",   False, {"android"}),
    ("desktop_chrome", True,  {"web_btn", "web_help", "ios_secondary"}),
    ("desktop_chrome", False, {"web_btn", "web_help"}),
    ("ipados_desktop", True,  {"web_btn", "web_help", "ios_secondary"}),
    ("ipados_desktop", False, {"web_btn", "web_help"}),
]

PIECES = {
    "ios_btn": IOS_CTA,
    "ios_help": IOS_HELP,
    "retap": "Installed? Go back to the chat and tap the invite again",
    "a2": A2_NOTE,
    "android": ANDROID_NOTE,
    "web_btn": WEB_CTA,
    "web_help": WEB_HELP,
    "ios_secondary": IOS_SECONDARY,
}


@pytest.mark.parametrize("ua_key,url_set,expected", CTA_MATRIX)
def test_landing_cta_matrix(monkeypatch, ua_key, url_set, expected):
    _set_flags(monkeypatch, *LANDING)
    if url_set:
        monkeypatch.setenv("IOS_INSTALL_URL", IOS_URL)
    r = _get(f"/app/league/join/{LEAGUE}", ua=UA[ua_key])
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for piece, needle in PIECES.items():
        assert (needle in html) is (piece in expected), (ua_key, url_set, piece)
    # One primary action per device state, never more.
    assert html.count('class="primary"') == (1 if expected & {"ios_btn", "web_btn"} else 0)
    # The /go/ios path renders only when the URL is set (unset: it 404s).
    assert ("/go/ios" in html) is bool(url_set and expected & {"ios_btn", "ios_secondary"})
    assert ("/go/web" in html) is ("web_btn" in expected)
    # Never a dtf:// link, never a TestFlight-request link, never the URL itself.
    assert "dtf://" not in html
    assert "contact.html" not in html and "Request TestFlight" not in html
    assert IOS_URL not in html


def test_landing_headers_and_og(monkeypatch):
    """AC-7b: 200 HTML, no-store, noindex, absolute https og:image/og:url
    (https even though the test client speaks http — no ProxyFix)."""
    _set_flags(monkeypatch, *LANDING)
    r = _client().get(f"/app/league/join/{LEAGUE}",
                      base_url="http://fleeced.example",
                      headers={"User-Agent": UA["desktop_chrome"]})
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("text/html")
    assert r.headers["Cache-Control"] == "no-store"
    html = r.get_data(as_text=True)
    assert '<meta name="robots" content="noindex">' in html
    assert ('<meta property="og:image" '
            'content="https://fleeced.example/img/og-invite.png">') in html
    assert ('<meta property="og:url" '
            f'content="https://fleeced.example/app/league/join/{LEAGUE}">') in html
    assert "http://fleeced.example" not in html
    assert (f'<meta property="og:title" content="{LEAGUE_NAME}: trades that '
            'work for both sides">') in html
    assert f"<title>{LEAGUE_NAME} on Fleeced: Dynasty Trade Finder</title>" in html


def test_landing_og_title_long_league_name(monkeypatch):
    _set_flags(monkeypatch, *LANDING)
    name = "The Extremely Long Dynasty League Name For Testing Cuts Here OK"
    monkeypatch.setattr(server, "_fetch_sleeper_league_meta",
                        lambda lid: {"name": name})
    html = _get(f"/app/league/join/{LEAGUE}").get_data(as_text=True)
    assert f'<meta property="og:title" content="{name[:59]}…">' in html


def test_landing_echoes_no_query_username(monkeypatch):
    """AC-7b: nothing from the query string reaches the page as text, title
    or OG. `ref` survives only URL-encoded inside the onward /go/web href
    (so a legacy link keeps its attribution through the landing)."""
    _set_flags(monkeypatch, *LANDING)
    html = _get(f"/app/league/join/{LEAGUE}?ref=sneakyref&username=sneakyuser"
                "&name=sneakyname&display_name=sneakydn").get_data(as_text=True)
    for s in ("sneakyuser", "sneakyname", "sneakydn"):
        assert s not in html, s
    assert html.count("sneakyref") == 1
    assert f'href="/app/league/join/{LEAGUE}/go/web?ref=sneakyref"' in html
    assert "sneakyref" not in _visible_text(html)
    assert "A leaguemate invited you to Lakeview Dynasty" in html


def test_landing_neutralises_hostile_query_and_names(monkeypatch, env):
    _set_flags(monkeypatch, *LANDING)
    _seed(env)
    with env.begin() as conn:
        conn.execute(update(users_table).values(
            display_name='Matt"><img src=x onerror=alert(1)>'))
    monkeypatch.setattr(server, "_fetch_sleeper_league_meta",
                        lambda lid: {"name": "<script>alert(1)</script>"})
    html = _get(f"/app/league/join/{LEAGUE}?t={T_VALID}"
                "&ref=%22%3E%3Cscript%3Ex%3C%2Fscript%3E").get_data(as_text=True)
    assert "<script>" not in html and "<img" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "Matt&quot;&gt;&lt;img src=x onerror=alert(1)&gt;" in html


def test_landing_is_chalkline_not_share_chrome(monkeypatch):
    """AC-7d / AC-7e: Fleeced brand, tokens.css + the web font link, none of
    the /s/* chrome (999px pill, Roboto stack, 16px radius, shadow)."""
    _set_flags(monkeypatch, *LANDING)
    html = _get(f"/app/league/join/{LEAGUE}").get_data(as_text=True)
    assert '<link rel="stylesheet" href="/css/tokens.css">' in html
    index = (REPO / "web" / "index.html").read_text()
    fonts = re.search(r'<link href="https://fonts\.googleapis\.com/css2[^>]+>',
                      index).group(0)
    assert fonts in html
    assert "FLEECED" in html and "Fantasy Trade Finder" not in html
    for chrome in ("999px", "Roboto", "-apple-system", "border-radius:16px",
                   "box-shadow", "#0f1322", "#6eb4ff", "gradient",
                   "backdrop-filter", "--neg", "--flare"):
        assert chrome not in html, chrome
    # Floors: ice focus ring, 44px targets, reduced motion, dark only.
    assert "outline:2px solid var(--ice)" in html
    assert "min-height:44px" in html
    assert "prefers-reduced-motion" in html
    assert "color-scheme:dark" in html
    radii = [int(x) for x in re.findall(r"border-radius:(\d+)px", html)]
    assert all(r <= 8 for r in radii)


@pytest.mark.parametrize("tok,league_meta,headline", [
    (T_VALID, {"name": LEAGUE_NAME},
     f"{REFERRER_NAME} invited you to {LEAGUE_NAME}"),
    (T_VALID, None, f"{REFERRER_NAME} invited you to their league"),
    (None, {"name": LEAGUE_NAME}, f"A leaguemate invited you to {LEAGUE_NAME}"),
    (None, None, "A leaguemate invited you"),
    (T_EXPIRED, {"name": LEAGUE_NAME},
     f"A leaguemate invited you to {LEAGUE_NAME}"),
    (T_MISMATCH, {"name": LEAGUE_NAME},
     f"A leaguemate invited you to {LEAGUE_NAME}"),
    (T_UNKNOWN, None, "A leaguemate invited you"),
])
def test_headline_ladder(monkeypatch, env, tok, league_meta, headline):
    """FR-7: the name comes only from a VALID t; expired, mismatched and
    unknown ids get the neutral headline and no name anywhere (AC-7e)."""
    _set_flags(monkeypatch, *LANDING)
    _seed(env)
    monkeypatch.setattr(server, "_fetch_sleeper_league_meta",
                        lambda lid: league_meta)
    q = f"?t={tok}" if tok else ""
    html = _get(f"/app/league/join/{LEAGUE}{q}").get_data(as_text=True)
    assert f"<h1>{headline}</h1>" in html
    if tok != T_VALID:
        assert REFERRER_NAME not in html


def test_landing_survives_a_failed_league_lookup(monkeypatch):
    _set_flags(monkeypatch, *LANDING)

    def _boom(_lid):
        raise RuntimeError("sleeper is down")
    monkeypatch.setattr(server, "_fetch_sleeper_league_meta", _boom)
    r = _get(f"/app/league/join/{LEAGUE}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "<h1>A leaguemate invited you</h1>" in html
    assert "Your league on Fleeced: Dynasty Trade Finder" in html
    assert 'content="Dynasty trades that work for both sides"' in html


def test_landing_onward_links_carry_t_not_ref(monkeypatch):
    _set_flags(monkeypatch, *LANDING)
    monkeypatch.setenv("IOS_INSTALL_URL", IOS_URL)
    html = _get(f"/app/league/join/{LEAGUE}?t={T_VALID}&ref=matt").get_data(as_text=True)
    assert f'href="/app/league/join/{LEAGUE}/go/web?t={T_VALID}"' in html
    assert f'href="/app/league/join/{LEAGUE}/go/ios?t={T_VALID}"' in html
    assert "matt" not in html


def test_landing_encodes_hostile_league_ids(monkeypatch):
    _set_flags(monkeypatch, *LANDING)
    r = _get('/app/league/join/%22%3E%3Cscript%3E')
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "<script>" not in html and '"><' not in html
    assert 'href="/app/league/join/%22%3E%3Cscript%3E/go/web"' in html
    assert 'content="https://localhost/app/league/join/%22%3E%3Cscript%3E"' in html


# ═══════════════════════════════════════════════════════════════════════════
# /go/<cta> — the click-through
# ═══════════════════════════════════════════════════════════════════════════

def test_go_404s_while_the_flag_is_off(monkeypatch):
    monkeypatch.setenv("IOS_INSTALL_URL", IOS_URL)
    for cta in ("ios", "web"):
        r = _get(f"/app/league/join/{LEAGUE}/go/{cta}")
        assert r.status_code == 404, cta
        assert r.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("cta", ["android", "IOS", "Web", "dtf", "javascript",
                                 "web.", "ios%20", "https:"])
def test_go_closed_set(monkeypatch, cta):
    _set_flags(monkeypatch, *LANDING)
    monkeypatch.setenv("IOS_INSTALL_URL", IOS_URL)
    assert _get(f"/app/league/join/{LEAGUE}/go/{cta}").status_code == 404


@pytest.mark.parametrize("value", [None, "", "http://testflight.apple.com/x",
                                   "javascript:alert(1)"])
def test_go_ios_404s_while_the_url_is_unset(monkeypatch, env, value):
    _set_flags(monkeypatch, *LANDING)
    if value is not None:
        monkeypatch.setenv("IOS_INSTALL_URL", value)
    r = _get(f"/app/league/join/{LEAGUE}/go/ios", ua=UA["iphone"])
    assert r.status_code == 404
    assert _events(env, "invite_landing_cta") == []


def test_go_ios_redirects_to_exactly_the_install_url(monkeypatch):
    _set_flags(monkeypatch, *LANDING)
    monkeypatch.setenv("IOS_INSTALL_URL", IOS_URL)
    r = _get(f"/app/league/join/{LEAGUE}/go/ios?t={T_VALID}"
             "&next=https://evil.example&url=//evil.example", ua=UA["iphone"])
    assert r.status_code == 302
    assert r.headers["Location"] == IOS_URL
    assert r.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("query,location", [
    (f"?t={T_VALID}", f"/?league={LEAGUE}&t={T_VALID}"),
    ("?ref=matt", f"/?league={LEAGUE}&ref=matt"),
    (f"?t={T_VALID}&ref=matt", f"/?league={LEAGUE}&t={T_VALID}"),
    ("?t=bad!&ref=matt", f"/?league={LEAGUE}&ref=matt"),
    ("", f"/?league={LEAGUE}"),
    ("?next=https://evil.example&url=https://evil.example"
     "&redirect=//evil.example&utm_source=x", f"/?league={LEAGUE}"),
    ("?ref=a%20b%26c%3D1", f"/?league={LEAGUE}&ref=a+b%26c%3D1"),
])
def test_go_web_closed_onward_query(monkeypatch, query, location):
    _set_flags(monkeypatch, *LANDING)
    r = _get(f"/app/league/join/{LEAGUE}/go/web{query}")
    assert r.status_code == 302
    assert r.headers["Location"] == location
    assert r.headers["Cache-Control"] == "no-store"


def test_go_web_hostile_league_ids(monkeypatch):
    """Unroutable shapes 404; routable ones come back encoded and relative."""
    _set_flags(monkeypatch, *LANDING)
    for hostile in ("https:%2F%2Fevil.com", "%2F%2Fevil.com",
                    "..%2F..%2Fetc%2Fpasswd"):
        assert _get(f"/app/league/join/{hostile}/go/web").status_code == 404
    loc = _get("/app/league/join/..%252F..%252Fetc/go/web").headers["Location"]
    assert loc == "/?league=..%252F..%252Fetc"
    loc = _get("/app/league/join/%3Cscript%3E/go/web?ref=%0d%0aSet-Cookie:x"
               ).headers["Location"]
    assert loc.startswith("/?") and "://" not in loc
    assert "<" not in loc and "\r" not in loc and "\n" not in loc


def test_every_go_location_is_relative_or_exactly_the_install_url(monkeypatch):
    _set_flags(monkeypatch, *LANDING)
    monkeypatch.setenv("IOS_INSTALL_URL", IOS_URL)
    queries = ["", f"?t={T_VALID}", "?ref=matt", "?next=//evil.example",
               "?url=https://evil.example", "?redirect=https:evil.example",
               "?ref=https://evil.example"]
    for cta in ("ios", "web"):
        for q in queries:
            loc = _get(f"/app/league/join/{LEAGUE}/go/{cta}{q}").headers["Location"]
            assert loc == IOS_URL or (loc.startswith("/?") and "/" not in loc[1:]
                                      and ":" not in loc), loc


def test_go_fires_invite_landing_cta(monkeypatch, env):
    _set_flags(monkeypatch, *LANDING)
    monkeypatch.setenv("IOS_INSTALL_URL", IOS_URL)
    _seed(env)
    _get(f"/app/league/join/{LEAGUE}/go/ios?t={T_VALID}", ua=UA["iphone"])
    _get(f"/app/league/join/{LEAGUE}/go/web?ref=matt")
    rows = _events(env, "invite_landing_cta")
    assert len(rows) == 2
    ios, web = rows
    assert ios["user_id"] == REFERRER          # valid t → the inviter owns it
    assert json.loads(ios["props"]) == {
        "invite_id": T_VALID, "league_id": LEAGUE, "cta": "ios_install",
        "device_class": "ios"}
    assert web["user_id"] == "system:invite"   # no t → system owner
    assert json.loads(web["props"]) == {
        "league_id": LEAGUE, "cta": "web_app", "device_class": "desktop"}
    for row in rows:
        assert row["platform"] == "server"
        assert row["league_id"] == LEAGUE
    # C6: the inviter's users row did not move.
    u = _user(env)
    assert u["last_active_at"] == PRIOR_ACTIVE and u["events_count"] == 5


def test_go_records_nothing_for_head_or_previews(monkeypatch, env):
    _set_flags(monkeypatch, *BOTH)
    monkeypatch.setenv("IOS_INSTALL_URL", IOS_URL)
    _seed(env)
    for cta in ("ios", "web"):
        url = f"/app/league/join/{LEAGUE}/go/{cta}?t={T_VALID}"
        assert _get(url, method="HEAD").status_code == 302
        assert _get(url, ua=PREVIEW_UA["imessage"]).status_code == 302
        assert _get(url, ua=None).status_code == 302
    assert _events(env) == []


# ═══════════════════════════════════════════════════════════════════════════
# FR-8 — landing-open recording (both join modes)
# ═══════════════════════════════════════════════════════════════════════════

MODES = [pytest.param(LEDGER, 302, id="302-mode"),
         pytest.param(BOTH, 200, id="landing-mode")]


@pytest.mark.parametrize("flags,status", MODES)
def test_human_get_increments_and_fires(monkeypatch, env, flags, status):
    _set_flags(monkeypatch, *flags)
    _seed(env)
    r = _get(f"/app/league/join/{LEAGUE}?t={T_VALID}", ua=UA["iphone"])
    assert r.status_code == status
    row = _referral(env, T_VALID)
    assert row["open_count"] == 1
    assert row["opened_at"] and row["last_opened_at"] == row["opened_at"]
    assert row["unfurled_at"] is None
    first = row["opened_at"]

    _get(f"/app/league/join/{LEAGUE}?t={T_VALID}", ua=UA["desktop_chrome"])
    row = _referral(env, T_VALID)
    assert row["open_count"] == 2
    assert row["opened_at"] == first                 # first open wins
    assert row["last_opened_at"] >= first

    events = _events(env, "invite_landing_opened")
    assert len(events) == 2
    assert [json.loads(e["props"])["device_class"] for e in events] == [
        "ios", "desktop"]
    e = events[0]
    assert e["user_id"] == REFERRER
    assert e["platform"] == "server"
    assert e["league_id"] == LEAGUE
    assert json.loads(e["props"]) == {
        "invite_id": T_VALID, "league_id": LEAGUE,
        "invite_status": "valid", "device_class": "ios"}


@pytest.mark.parametrize("flags,status", MODES)
@pytest.mark.parametrize("ua", [PREVIEW_UA["imessage"], PREVIEW_UA["slack"],
                                PREVIEW_UA["whatsapp"], None, ""])
def test_preview_sets_only_unfurled_at(monkeypatch, env, flags, status, ua):
    _set_flags(monkeypatch, *flags)
    _seed(env)
    assert _get(f"/app/league/join/{LEAGUE}?t={T_VALID}", ua=ua).status_code == status
    row = _referral(env, T_VALID)
    assert row["unfurled_at"]
    first = row["unfurled_at"]
    assert row["opened_at"] is None and row["last_opened_at"] is None
    assert row["open_count"] == 0
    _get(f"/app/league/join/{LEAGUE}?t={T_VALID}", ua=ua)
    assert _referral(env, T_VALID)["unfurled_at"] == first   # first fetch wins
    assert _events(env) == []


@pytest.mark.parametrize("flags,status", MODES)
def test_head_records_nothing(monkeypatch, env, flags, status):
    """Flask runs the GET view for HEAD; the route must check the method."""
    _set_flags(monkeypatch, *flags)
    _seed(env)
    before = _referral(env, T_VALID)
    for ua in (UA["iphone"], PREVIEW_UA["imessage"], None):
        r = _get(f"/app/league/join/{LEAGUE}?t={T_VALID}", ua=ua, method="HEAD")
        assert r.status_code == status
    assert _referral(env, T_VALID) == before
    assert _events(env) == []


@pytest.mark.parametrize("flags", [(), LANDING])
def test_nothing_records_while_the_ledger_is_off(monkeypatch, env, flags):
    _set_flags(monkeypatch, *flags)
    _seed(env)
    before = _referral(env, T_VALID)
    _get(f"/app/league/join/{LEAGUE}?t={T_VALID}", ua=UA["iphone"])
    _get(f"/app/league/join/{LEAGUE}?t={T_VALID}", ua=PREVIEW_UA["slack"])
    assert _referral(env, T_VALID) == before
    assert _events(env) == []


def test_nothing_records_without_a_well_formed_t(monkeypatch, env):
    _set_flags(monkeypatch, *BOTH)
    _seed(env)
    for q in ("", "?ref=matt", "?t=short", f"?t={T_VALID}%0A", f"?t={T_VALID}!"):
        _get(f"/app/league/join/{LEAGUE}{q}", ua=UA["iphone"])
    assert _referral(env, T_VALID)["open_count"] == 0
    assert _events(env) == []


@pytest.mark.parametrize("flags", [LEDGER, BOTH])
@pytest.mark.parametrize("tok,status,owner,touched", [
    (T_VALID, "valid", REFERRER, True),
    (T_EXPIRED, "expired", "system:invite", True),
    (T_MISMATCH, "league_mismatch", "system:invite", True),
    (T_UNKNOWN, "unknown", "system:invite", False),
])
def test_invite_status_and_owner(monkeypatch, env, flags, tok, status, owner,
                                 touched):
    _set_flags(monkeypatch, *flags)
    _seed(env)
    _get(f"/app/league/join/{LEAGUE}?t={tok}", ua=UA["android"])
    (e,) = _events(env, "invite_landing_opened")
    assert e["user_id"] == owner
    props = json.loads(e["props"])
    assert props == {"invite_id": tok, "league_id": LEAGUE,
                     "invite_status": status, "device_class": "android"}
    row = _referral(env, tok)
    assert (row is not None and row["open_count"] == 1) is touched


def test_event_props_carry_no_identity(monkeypatch, env):
    """C1/C4/C9: never the UA string, IP, username, display name or league
    name; no prop key contains "token"."""
    _set_flags(monkeypatch, *BOTH)
    monkeypatch.setenv("IOS_INSTALL_URL", IOS_URL)
    _seed(env)
    _get(f"/app/league/join/{LEAGUE}?t={T_VALID}&ref=mattref", ua=UA["iphone"])
    _get(f"/app/league/join/{LEAGUE}/go/ios?t={T_VALID}", ua=UA["iphone"])
    _get(f"/app/league/join/{LEAGUE}/go/web?ref=mattref")
    rows = _events(env)
    assert {r["event_type"] for r in rows} == {"invite_landing_opened",
                                              "invite_landing_cta"}
    for r in rows:
        blob = r["props"]
        for leak in ("Mozilla", "iPhone OS", "127.0.0.1", "mattref",
                     REFERRER_NAME, LEAGUE_NAME):
            assert leak not in blob, (r["event_type"], leak)
        assert not any("token" in k for k in json.loads(blob))
        assert r["device_type"] is None and r["session_id"] is None


def test_c6_referrer_users_row_never_moves(monkeypatch, env):
    _set_flags(monkeypatch, *BOTH)
    monkeypatch.setenv("IOS_INSTALL_URL", IOS_URL)
    _seed(env)
    before = _user(env)
    _get(f"/app/league/join/{LEAGUE}?t={T_VALID}", ua=UA["iphone"])
    _get(f"/app/league/join/{LEAGUE}/go/ios?t={T_VALID}", ua=UA["iphone"])
    _get(f"/app/league/join/{LEAGUE}/go/web?t={T_VALID}")
    assert len(_events(env)) == 3
    assert {e["user_id"] for e in _events(env)} == {REFERRER}
    assert _user(env) == before
    assert before["last_active_at"] == PRIOR_ACTIVE and before["events_count"] == 5


# ═══════════════════════════════════════════════════════════════════════════
# record_event — the two new keyword arguments keep today's defaults
# ═══════════════════════════════════════════════════════════════════════════

def test_record_event_defaults_write_the_same_row(env):
    with env.begin() as conn:
        conn.execute(insert(users_table).values(
            sleeper_user_id="u_def", last_active_at=PRIOR_ACTIVE,
            events_count=2))
    db_module.record_event("u_def", "match_viewed", league_id="L1",
                           source="api", props={"k": 1})
    (row,) = _events(env)
    assert {k: v for k, v in row.items() if v is not None} == {
        "id": row["id"], "user_id": "u_def", "event_type": "match_viewed",
        "occurred_at": row["occurred_at"], "league_id": "L1",
        "source": "api", "props": '{"k": 1}'}
    u = _user(env, "u_def")
    assert u["last_active_at"] == row["occurred_at"]
    assert u["last_match_seen_at"] == row["occurred_at"]
    assert u["events_count"] == 3


def test_record_event_default_still_runs_the_streak(env):
    with env.begin() as conn:
        conn.execute(insert(users_table).values(sleeper_user_id="u_rank"))
    out = db_module.record_event("u_rank", "trio_swipe")
    assert out and out["current"] == 1
    assert _user(env, "u_rank")["events_count"] == 1


def test_record_event_touch_user_false_writes_only_the_event(env):
    with env.begin() as conn:
        conn.execute(insert(users_table).values(
            sleeper_user_id="u_quiet", last_active_at=PRIOR_ACTIVE,
            events_count=7))
    before = _user(env, "u_quiet")
    out = db_module.record_event("u_quiet", "trio_swipe", platform="server",
                                 touch_user=False)
    assert out is None                         # no streak step
    (row,) = _events(env)
    assert row["platform"] == "server"
    assert _user(env, "u_quiet") == before


def test_record_event_platform_insert_is_unchanged_by_default(env, monkeypatch):
    """Byte-identical default: the INSERT names no `platform` column unless a
    caller passes one, so every existing call site emits the statement it
    emitted before."""
    seen = []

    @db_module.sa_event.listens_for(env, "before_cursor_execute")
    def _spy(conn, cursor, statement, params, context, executemany):
        if statement.startswith("INSERT INTO user_events"):
            seen.append(statement)

    db_module.record_event("u_x", "app_open")
    db_module.record_event("u_x", "app_open", platform="server")
    assert "platform" not in seen[0]
    assert "platform" in seen[1]


# ═══════════════════════════════════════════════════════════════════════════
# Schema — the four referrals columns
# ═══════════════════════════════════════════════════════════════════════════

def _migration_cols():
    import inspect
    src = inspect.getsource(db_module._migrate_db)
    return [tuple(m) for m in re.findall(
        r'\(\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]+)"\s*\)', src)]


def test_referrals_columns_in_table_and_migration():
    cols = referrals_table.c
    for name in ("opened_at", "last_opened_at", "open_count", "unfurled_at"):
        assert name in cols, name
    assert str(cols.open_count.server_default.arg) == "0"
    mig = _migration_cols()
    for entry in (("referrals", "opened_at", "VARCHAR"),
                  ("referrals", "last_opened_at", "VARCHAR"),
                  ("referrals", "open_count", "INTEGER DEFAULT 0"),
                  ("referrals", "unfurled_at", "VARCHAR")):
        assert entry in mig, entry


def test_migrate_db_adds_the_columns_to_a_legacy_table_idempotently(tmp_path,
                                                                     monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with eng.begin() as conn:     # the pre-D-1 referrals shape, one live row
        conn.execute(text(
            "CREATE TABLE referrals (id INTEGER PRIMARY KEY, "
            "referrer_user_id VARCHAR NOT NULL, referred_user_id VARCHAR, "
            "league_id VARCHAR NOT NULL, invite_token VARCHAR NOT NULL UNIQUE, "
            "status VARCHAR NOT NULL DEFAULT 'pending', qualifying_event VARCHAR, "
            "reward_entitlement_id INTEGER, created_at VARCHAR NOT NULL, "
            "joined_at VARCHAR, activated_at VARCHAR, rewarded_at VARCHAR)"))
        conn.execute(text(
            "INSERT INTO referrals (referrer_user_id, league_id, invite_token, "
            "created_at) VALUES ('u', 'L', 'LeGaCy123456', '2026-10-01')"))
    metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    monkeypatch.setattr(db_module, "DATABASE_URL", "sqlite:///legacy")
    db_module._migrate_db()
    db_module._migrate_db()       # second run: every ALTER is a no-op
    with eng.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(referrals)"))}
        assert {"opened_at", "last_opened_at", "open_count",
                "unfurled_at"} <= cols
        assert conn.execute(text(
            "SELECT open_count FROM referrals")).scalar() == 0
    assert db_module.record_referral_landing_open("LeGaCy123456", "open") == 1


def test_get_referral_by_invite_token(env):
    _seed(env)
    row = db_module.get_referral_by_invite_token(T_VALID)
    assert row["referrer_user_id"] == REFERRER
    assert row["referrer_display_name"] == REFERRER_NAME
    assert db_module.get_referral_by_invite_token(T_UNKNOWN) is None


# ═══════════════════════════════════════════════════════════════════════════
# /s/* — the CTA
# ═══════════════════════════════════════════════════════════════════════════

def _share_paths(env):
    sid = "pkgAbc123"
    assert db_module.create_shared_package(sid, "u_sharer", ["4034"], ["7564"])
    return {"tiers": "/s/tiers/qb/someuser", "trade": "/s/trade/m123",
            "package": f"/s/p/{sid}"}


SHARE_OPEN = ("growth.share_landing", "growth.tier_board_share")


def test_share_headers_and_href_flag_off(monkeypatch, env):
    _set_flags(monkeypatch, *SHARE_OPEN)
    monkeypatch.setenv("IOS_INSTALL_URL", IOS_URL)
    labels = {"tiers": "Build your tiers", "trade": "Find your next trade",
              "package": "Build your own trade"}
    for kind, path in _share_paths(env).items():
        for ua in UA.values():
            r = _get(path, ua=ua)
            assert r.status_code == 200, path
            assert r.headers["Cache-Control"] == "private, max-age=300"
            assert r.headers["Vary"] == "User-Agent"
            html = r.get_data(as_text=True)
            assert (f'<a class="cta" href="/?share={kind}">{labels[kind]}</a>'
                    in html), (kind, ua)
            assert IOS_CTA not in html and ANDROID_NOTE not in html
            assert "dtf://" not in html


@pytest.mark.parametrize("ua_key,url_set,expect", [
    ("desktop_chrome", True, "button"), ("desktop_chrome", False, "button"),
    ("ipados_desktop", True, "button"),
    ("iphone", True, "ios"), ("iphone", False, "ios_note"),
    ("ipad_legacy", True, "ios"),
    ("android", True, "android"), ("android", False, "android"),
    ("other_mobile", True, "android"),
])
def test_share_cta_matrix_flag_on(monkeypatch, env, ua_key, url_set, expect):
    _set_flags(monkeypatch, *(SHARE_OPEN + LANDING))
    if url_set:
        monkeypatch.setenv("IOS_INSTALL_URL", IOS_URL)
    for kind, path in _share_paths(env).items():
        r = _get(path, ua=UA[ua_key])
        assert r.headers["Cache-Control"] == "private, max-age=300"
        assert r.headers["Vary"] == "User-Agent"
        html = r.get_data(as_text=True)
        has_button = f'href="/?share={kind}"' in html
        assert has_button is (expect == "button"), (kind, ua_key)
        assert (f'<a class="cta" href="{IOS_URL}">{IOS_CTA}</a>' in html) is (
            expect == "ios")
        assert (IOS_HELP in html) is (expect == "ios")
        assert (SHARE_IOS_NOTE in html) is (expect == "ios_note")
        assert (ANDROID_NOTE in html) is (expect == "android")
        assert html.count('class="cta"') == (1 if expect in ("button", "ios") else 0)
        assert "dtf://" not in html and "contact.html" not in html


def test_share_trade_page_keeps_its_chrome(monkeypatch):
    """GB-02: only the CTA element changed."""
    html = _get("/s/trade/m1").get_data(as_text=True)
    assert "<title>Trade Match · Fantasy Trade Finder</title>" in html
    assert '<div class="brand">Fantasy Trade Finder</div>' in html
    assert 'content="/og/trade/m1.png"' in html


# ═══════════════════════════════════════════════════════════════════════════
# Registration
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("key", ["growth.join_landing", "growth.referral_ledger"])
def test_flags_registered_and_off(key):
    assert key in feature_flags.FLAG_KEYS
    assert feature_flags.DEFAULT_FLAGS[key] is False
    for path in (REPO / "config" / "features.json",
                 REPO / "backend" / "tests" / "fixtures" / "flags" / "release.json"):
        data = json.loads(path.read_text())
        assert data[key] is False, path
        assert f"_comment_{key.replace('.', '_')}" in data, path


@pytest.mark.parametrize("name", ["invite_landing_opened", "invite_landing_cta"])
def test_events_registered_server_fired_and_non_intent(name):
    assert name in at.SERVER_FIRED_EVENTS
    assert name not in at.ALLOWED_CLIENT_EVENTS
    assert name in aq.NON_INTENT_EVENTS
    assert name not in aq.INTENT_EVENTS
