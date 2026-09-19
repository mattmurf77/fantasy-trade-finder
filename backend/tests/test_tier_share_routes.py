"""Tier-board share routes are closed by default — flag `growth.tier_board_share`.

Operator decision D-P1-12 (docs/plans/audit-p1-remediation/DECISIONS-p1.md):
sharing of rankings / tier boards is not a product surface and must not be
live in any form.

Both routes shipped with NO guard: they take no session, need no in-app
link, and echo the username back in the page title — so any user's board
was fetchable by guessing `/s/tiers/qb/<username>`. These tests pin the
404 so a future edit cannot silently re-open the surface.
"""
import json

import pytest

import backend.feature_flags as feature_flags
import backend.server as server


def _flags(*enabled):
    on = set(enabled)
    return lambda k: k in on


@pytest.fixture()
def client():
    server.app.config["TESTING"] = True
    return server.app.test_client()


# ---------------------------------------------------------------------------
# The guard itself
# ---------------------------------------------------------------------------

def test_both_tier_share_surfaces_404_while_dark(client, monkeypatch):
    """The whole point of the flag: dark ⇒ neither surface answers."""
    monkeypatch.setattr(server, "is_enabled", _flags())
    assert client.get("/s/tiers/qb/someuser").status_code == 404
    assert client.get("/og/tiers/qb/someuser.png").status_code == 404


def test_tier_share_404s_are_not_route_misses(client, monkeypatch):
    """404 must come from the flag guard, not from an unregistered rule.

    A typo'd path would also 404, so assert the routes exist and that the
    body is the guard's JSON — otherwise this file would keep passing after
    someone deleted the routes *and* after someone deleted the guard but
    renamed the path.
    """
    monkeypatch.setattr(server, "is_enabled", _flags())
    for path in ("/s/tiers/qb/someuser", "/og/tiers/qb/someuser.png"):
        r = client.get(path)
        assert r.status_code == 404, path
        assert json.loads(r.data) == {"error": "not_found"}, path

    rules = {r.rule for r in server.app.url_map.iter_rules()}
    assert "/s/tiers/<pos>/<username>" in rules
    assert "/og/tiers/<pos>/<username>.png" in rules


def test_unrelated_flag_does_not_open_tier_shares(client, monkeypatch):
    """`growth.share_landing` is ON in production — it must not carry these."""
    monkeypatch.setattr(server, "is_enabled", _flags("growth.share_landing"))
    assert client.get("/s/tiers/qb/someuser").status_code == 404
    assert client.get("/og/tiers/qb/someuser.png").status_code == 404


def test_guard_runs_before_any_board_lookup(client, monkeypatch):
    """No user, board or renderer work happens while the flag is dark.

    Guards placed after the work still leak timing and still burn a DB read
    on an unauthenticated request, so pin the ordering.
    """
    monkeypatch.setattr(server, "is_enabled", _flags())

    class _Boom:
        def __getattr__(self, name):
            raise AssertionError(f"_og_image.{name} called while flag is dark")

    monkeypatch.setattr(server, "_og_image", _Boom())
    assert client.get("/og/tiers/qb/someuser.png").status_code == 404


# ---------------------------------------------------------------------------
# Registration — a flag the loader ignores is not a flag
# ---------------------------------------------------------------------------

def test_flag_is_registered_and_defaults_off():
    assert "growth.tier_board_share" in feature_flags.FLAG_KEYS
    assert feature_flags.DEFAULT_FLAGS["growth.tier_board_share"] is False


def test_shipped_config_has_the_flag_off():
    """config/features.json is what production actually runs with."""
    features = json.loads((feature_flags._CONFIG_PATH).read_text())
    assert features["growth.tier_board_share"] is False
