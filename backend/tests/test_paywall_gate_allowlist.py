"""Completeness of the paywall gate's classification table
(backend/paywall_gate.py ROUTES; scope #393 §3).

  * every (method, rule) in app.url_map has exactly one table entry, and the
    table names no rule that no longer exists
  * the gated set is pinned: the #393 §2.1 / recommendation §(c) C2 list,
    nothing more, nothing less
  * a pinned list of always-reachable rules stays non-gated, and the
    secret-guarded prefixes are never_gate
"""

import backend.paywall_gate as pg
import backend.server as server

IGNORED_METHODS = {"HEAD", "OPTIONS"}   # Flask answers these from the GET view / automatically


def _url_map_keys():
    return {(m, r.rule) for r in server.app.url_map.iter_rules()
            for m in r.methods if m not in IGNORED_METHODS}


def test_every_rule_is_classified():
    missing = sorted(_url_map_keys() - set(pg.ROUTES), key=lambda k: (k[1], k[0]))
    assert not missing, f"unclassified rules (add each to paywall_gate.ROUTES): {missing}"


def test_no_stale_entries():
    stale = sorted(set(pg.ROUTES) - _url_map_keys(), key=lambda k: (k[1], k[0]))
    assert not stale, f"ROUTES names rules that no longer exist: {stale}"


def test_classes_are_the_three():
    assert set(pg.ROUTES.values()) == {pg.GATED, pg.FREE, pg.NEVER_GATE}


PINNED_GATED = {
    ("GET", "/api/trades"), ("POST", "/api/trades/generate"),
    ("POST", "/api/trades/pass-reason"), ("GET", "/api/trades/status"),
    ("POST", "/api/trades/swipe"),
    ("POST", "/api/trades/propose"), ("POST", "/api/trades/propose-espn"),
    ("POST", "/api/trades/propose-mfl"), ("POST", "/api/trades/queue"),
    ("POST", "/api/trades/respond-mfl"),
    ("POST", "/api/trades/asset-ideas"), ("POST", "/api/trades/fair-packages"),
    ("POST", "/api/trades/matches/<int:match_id>/disposition"),
    ("POST", "/api/trades/standing-offer"),
}
GATED_PREFIXES = ("/api/overhauls", "/api/win-now/")


def test_gated_set_is_pinned():
    expected = PINNED_GATED | {k for k in _url_map_keys()
                               if k[1].startswith(GATED_PREFIXES)}
    gated = {k for k, v in pg.ROUTES.items() if v == pg.GATED}
    assert gated == expected


def test_deck_routes_are_gated():
    assert pg.DECK_ROUTES <= {k for k, v in pg.ROUTES.items() if v == pg.GATED}


PINNED_NOT_GATED = [
    ("DELETE", "/api/account"),
    ("GET", "/api/account/export"),
    ("GET", "/api/me/entitlements"),
    ("GET", "/api/paywall/config"),
    ("GET", "/api/feature-flags"),
    ("POST", "/api/events"),
    ("GET", "/api/sleeper/link"),
    ("POST", "/api/sleeper/link"),
    ("DELETE", "/api/sleeper/link"),
    ("POST", "/api/trade/evaluate"),
    ("GET", "/api/trades/matches"),
    ("GET", "/api/trades/matches/all"),
]
NOT_GATED_PREFIXES = ("/api/session/", "/api/auth/", "/api/extension/",
                      "/api/billing/", "/api/admin/", "/api/cron/")
NEVER_GATE_PREFIXES = ("/api/billing/", "/api/admin/", "/api/cron/")


def test_pinned_rules_stay_non_gated():
    keys = _url_map_keys()
    for key in PINNED_NOT_GATED:
        assert key in keys, f"pinned rule vanished: {key}"
        assert pg.ROUTES[key] != pg.GATED, key


def test_pinned_prefixes_stay_non_gated():
    for key in _url_map_keys():
        if key[1].startswith(NOT_GATED_PREFIXES):
            assert pg.ROUTES[key] != pg.GATED, key
        if key[1].startswith(NEVER_GATE_PREFIXES):
            assert pg.ROUTES[key] == pg.NEVER_GATE, key
