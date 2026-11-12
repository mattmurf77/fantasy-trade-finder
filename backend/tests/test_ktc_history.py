"""backend/ktc_history.py — KeepTradeCut value history for the trade-universe
research store. Synthetic pages with the real pages' structure (a
`ktc-players` list on the rankings page; `pd-oneqb` / `pd-superflex` blocks
with daily `overallValue` series on a player page). A fake transport, clock
and sleep stand in for the site; no network."""

import datetime as dt
import gzip
import json
import os
import sqlite3

import pytest

from backend import ktc_history as kh
from backend import universe_values as uv

pytestmark = pytest.mark.usefixtures("no_real_network")

XWALK = """name,merge_name,position,team,sleeper_id,fantasypros_id,ktc_id,mfl_id
Alpha Back,alpha back,RB,AAA,1001,9001,501,13001
Bravo Receiver,bravo receiver,WR,BBB,1002,9002,NA,13002
Charlie Passer,charlie passer,QB,CCC,1003,9003,NA,NA
"""

ENTRIES = [
    {"playerName": "Alpha Back", "playerID": 501, "slug": "alpha-back-501", "position": "RB", "mflid": "13001"},
    {"playerName": "Bravo Receiver", "playerID": 602, "slug": "bravo-receiver-602", "position": "WR", "mflid": "13002"},
    {"playerName": "Charlie Passer", "playerID": 603, "slug": "charlie-passer-603", "position": "QB", "mflid": "0"},
    {"playerName": "Delta Nobody", "playerID": 777, "slug": "delta-nobody-777", "position": "TE", "mflid": "0"},
    {"playerName": "2027 Early 1st", "playerID": 1702, "slug": "2027-early-1st-1702", "position": "RDP", "mflid": 0},
    {"playerName": "Kicker Guy", "playerID": 900, "slug": "kicker-guy-900", "position": "K", "mflid": 0},
]


def rankings_html(entries=ENTRIES):
    return ('<html><head></head><body><script type="application/json" id="ktc-players">'
            + json.dumps(entries) + "</script></body></html>")


def series(points):
    return [{"d": d, "v": v} for d, v in points]


def player_html(pid, base, *, oneqb=True, extra_day=None):
    pts = [("231230", base), ("240102", base + 10), ("240103", base + 20)]
    if extra_day:
        pts.append(extra_day)
    block = lambda shift: {                                       # noqa: E731
        "adjacentOverallPlayers": [{"playerID": pid, "playerName": "Self %d" % pid,
                                    "position": "WR", "mflid": 0}],
        "overallValue": series([(d, v + shift) for d, v in pts]),
        "vftValueHistory": series([(d, v + shift - 5) for d, v in pts]),
        "blendValueHistory": series([(d, v + shift - 2) for d, v in pts]),
        "tep": {"adjacentOverallPlayers": []},
    }
    parts = ['<script type="application/json" id="pd-superflex">%s</script>' % json.dumps(block(1000))]
    if oneqb:
        parts.append('<script type="application/json" id="pd-oneqb">%s</script>' % json.dumps(block(0)))
    parts.append('<script type="application/json" id="pd-players">[]</script>')
    return "<html><body>" + "".join(parts) + "</body></html>"


class Clock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


class FakeSite:
    """url -> list of (status, body, headers) answered in order (last repeats)."""

    def __init__(self, pages, clock):
        self.pages = {k: list(v) for k, v in pages.items()}
        self.calls = []
        self.clock = clock

    def __call__(self, url, headers):
        self.calls.append((url, self.clock.t))
        assert "gzip" in headers["Accept-Encoding"] and "Mozilla" in headers["User-Agent"]
        answers = self.pages.get(url, [(404, "", {})])
        status, body, hdrs = answers.pop(0) if len(answers) > 1 else answers[0]
        raw = body.encode() if isinstance(body, str) else body
        return kh.Response(status, hdrs, raw)


def site_pages(entries=ENTRIES):
    pages = {kh.KTC_RANKINGS_URL: [(200, rankings_html(entries), {})]}
    for i, e in enumerate(entries):
        pages[kh.PLAYER_URL.format(slug=e["slug"])] = [
            (200, player_html(e["playerID"], 1000 * (i + 1)), {})]
    return pages


def fetcher(site, clock, **kw):
    return kh.PoliteFetcher(site, sleep=clock.sleep, clock=clock.clock, log=lambda *a: None, **kw)


# --- parsing ----------------------------------------------------------------

def test_parse_rankings_keeps_picks_and_drops_other_positions():
    got = kh.parse_rankings(rankings_html())
    assert [e["slug"] for e in got] == [e["slug"] for e in ENTRIES[:5]]
    assert got[4] == {"id": "1702", "name": "2027 Early 1st", "slug": "2027-early-1st-1702",
                      "position": "RDP", "mflid": ""}
    with pytest.raises(ValueError):
        kh.parse_rankings("<html>nothing here</html>")


def test_parse_player_page_series_last_point_of_a_day_wins():
    html = player_html(501, 1000, extra_day=("240103", 5555))
    p = kh.parse_player_page(html, "501")
    assert p["series"]["1qb"]["crowd"] == [["2023-12-30", 1000], ["2024-01-02", 1010], ["2024-01-03", 5555]]
    assert p["series"]["sf"]["crowd"][-1] == ["2024-01-03", 6555]
    assert p["series"]["sf"]["vft"][0] == ["2023-12-30", 1995]
    assert p["duplicates"] == {"1qb/crowd": 1, "1qb/vft": 1, "1qb/blend": 1,
                               "sf/crowd": 1, "sf/vft": 1, "sf/blend": 1}
    assert p["self"]["name"] == "Self 501"


def test_parse_player_page_without_a_format_block_raises():
    with pytest.raises(ValueError):
        kh.parse_player_page(player_html(501, 1000, oneqb=False), "501")


def test_gzip_bodies_are_decoded():
    body = gzip.compress(b"hello")
    assert kh.Response(200, {"Content-Encoding": "gzip"}, body).text() == "hello"


def test_pick_label_from_slug():
    assert kh.pick_label_from_slug("2025-mid-1st-1450") == "2025 Mid 1st"
    assert kh.pick_label_from_slug("josh-allen-365") is None


# --- politeness -------------------------------------------------------------

def test_requests_are_paced_and_the_interval_has_a_one_second_floor():
    c = Clock()
    site = FakeSite({"u": [(200, "x", {})]}, c)
    f = fetcher(site, c, interval=0.2)
    for _ in range(3):
        f.get("u")
    times = [t for _, t in site.calls]
    assert times == [0.0, 1.0, 2.0]


def test_429_backs_off_honours_retry_after_then_succeeds():
    c = Clock()
    site = FakeSite({"u": [(429, "", {"Retry-After": "90"}), (503, "", {}), (200, "ok", {})]}, c)
    f = fetcher(site, c, interval=3, backoff=(30, 60))
    assert f.get("u").text() == "ok"
    assert len(site.calls) == 3
    assert 90 in c.sleeps and 60 in c.sleeps


def test_hard_stop_after_three_consecutive_blocks():
    c = Clock()
    site = FakeSite({"u": [(403, "", {})]}, c)
    f = fetcher(site, c, max_retries=10, backoff=(1,))
    with pytest.raises(kh.HardStop):
        f.get("u")
    assert len(site.calls) == 3


def test_404_is_not_retried():
    c = Clock()
    site = FakeSite({}, c)
    assert fetcher(site, c).get("nope").status == 404
    assert len(site.calls) == 1


# --- the pull ---------------------------------------------------------------

def test_pull_checkpoints_each_page_and_a_restart_skips_done_pages(tmp_path):
    c = Clock()
    pages = site_pages()
    pages[kh.PLAYER_URL.format(slug="charlie-passer-603")] = [(500, "", {})]
    site = FakeSite(pages, c)
    s1 = kh.run_pull(str(tmp_path), fetcher=fetcher(site, c, max_retries=0), log=lambda *a: None)
    assert (s1["fetched"], s1["failed"]) == (5, 1)
    assert sorted(os.listdir(tmp_path / "pages")) == sorted(
        e["slug"] + ".json.gz" for e in ENTRIES[:5] if e["playerID"] != 603)
    assert not (tmp_path / "html").exists()            # raw HTML not kept by default

    c2 = Clock()
    site2 = FakeSite(site_pages(), c2)
    s2 = kh.run_pull(str(tmp_path), fetcher=fetcher(site2, c2), log=lambda *a: None)
    assert [u for u, _ in site2.calls] == [kh.PLAYER_URL.format(slug="charlie-passer-603")]
    assert (s2["already_done"], s2["fetched"], s2["failed"]) == (4, 1, 0)


def test_keep_html_is_a_debug_opt_in(tmp_path):
    c = Clock()
    kh.run_pull(str(tmp_path), fetcher=fetcher(FakeSite(site_pages(), c), c),
                keep_html=True, limit=1, log=lambda *a: None)
    assert os.listdir(tmp_path / "html") == ["alpha-back-501.html"]


def test_extra_slugs_are_queued_and_bare_unknown_ids_reported(tmp_path):
    c = Clock()
    pages = site_pages()
    pages[kh.PLAYER_URL.format(slug="2025-mid-1st-1450")] = [(200, player_html(1450, 300), {})]
    extra = tmp_path / "extra.txt"
    extra.write_text("# extras\n2025-mid-1st-1450\n501\n4242\nBad Slug!\n")
    site = FakeSite(pages, c)
    s = kh.run_pull(str(tmp_path / "out"), fetcher=fetcher(site, c),
                    extra=kh.read_extra(str(extra)), log=lambda *a: None)
    assert s["unresolved_extra"] == ["4242", "Bad Slug!"]
    assert os.path.exists(tmp_path / "out" / "pages" / "2025-mid-1st-1450.json.gz")


# --- ingest -----------------------------------------------------------------

@pytest.fixture
def pulled(tmp_path):
    c = Clock()
    pages = site_pages()
    pages[kh.PLAYER_URL.format(slug="2025-mid-1st-1450")] = [(200, player_html(1450, 300), {})]
    out = str(tmp_path / "ktc")
    kh.run_pull(out, fetcher=fetcher(FakeSite(pages, c), c), extra=["2025-mid-1st-1450"],
                log=lambda *a: None)
    return out, str(tmp_path / "v.sqlite")


def test_ingest_maps_ids_picks_and_keeps_dates_from_since(pulled):
    out, db = pulled
    xw = uv.crosswalk_from_text(XWALK)
    s = kh.ingest(out, db, xw=xw, since=dt.date(2024, 1, 1))
    assert s["tiers"] == {"ktc_id": 1, "mfl_id": 1, "name": 1, "pick_label": 2}
    assert s["unmapped_ids"] == ["777"]
    with sqlite3.connect(db) as c:
        dates = [r[0] for r in c.execute("SELECT DISTINCT board_date FROM value_boards "
                                         "WHERE source='ktc' ORDER BY 1")]
        unm = {r[0] for r in c.execute("SELECT source_key FROM unmapped")}
    assert dates == ["2024-01-02", "2024-01-03"]
    assert unm == {"777"}
    lk = uv.value_on("2024-01-05", "1001", "1qb", source="ktc", db_path=db)
    assert (lk.value, lk.board_date, lk.age_days) == (1020, "2024-01-03", 2)
    assert uv.value_on("2024-01-02", "pick:2027:1:early", "sf", source="ktc", db_path=db).value == 6010
    assert uv.value_on("2024-01-02", "pick:2025:1:mid", "1qb", source="ktc", db_path=db).value == 310
    assert not uv.value_on("2023-12-31", "1001", "1qb", source="ktc", db_path=db).found


def test_vft_series_is_a_separate_source(pulled):
    out, db = pulled
    xw = uv.crosswalk_from_text(XWALK)
    kh.ingest(out, db, xw=xw, series="crowd")
    kh.ingest(out, db, xw=xw, series="vft")
    assert uv.value_on("2024-01-03", "1001", "1qb", source="ktc", db_path=db).value == 1020
    assert uv.value_on("2024-01-03", "1001", "1qb", source="ktc_vft", db_path=db).value == 1015


def test_coverage_says_which_lookups_only_dp_can_price(pulled, tmp_path):
    out, db = pulled
    kh.ingest(out, db, xw=uv.crosswalk_from_text(XWALK))
    dp = tmp_path / "dp.csv"
    dp.write_text("date,format,asset_type,asset_id,value\n"
                  "2024-01-01,1qb,player,1001,900\n2024-01-01,1qb,player,5000,800\n")
    uv.load_dated_csv(str(dp), db, source="dp")
    lookups = [("1001", "2024-01-04"), ("5000", "2024-01-04"), ("1003", "2024-01-04"),
               ("1001", "2024-03-01")]
    rep = uv.coverage_report(db, lookups=lookups, max_age=14)
    assert rep["lookups"]["1qb"]["by_sources_present"] == {"dp+ktc": 1, "dp": 1, "ktc": 1, "none": 1}
    assert rep["sources"]["ktc/1qb"]["distinct_unmapped"] == 1
