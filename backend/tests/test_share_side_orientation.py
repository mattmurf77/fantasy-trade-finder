"""A shared trade is drawn from the SHARER's side (marketing addendum 14, C1).

trade_matches stores one orientation: user_a_give / user_a_receive. A share
token can be minted by either party, and the og card always draws
user_a_give as YOU GIVE, so when user_b shared, YOU GIVE listed what user_b
GETS. `resolve_trade_share_token` now orients the row to the token's
creator: for a user_b token the two lists come back swapped, with
`shared_by` = "b". Both callers (`og_trade_card`, `share_trade_page`) draw
from the resolved row unchanged, so the fix lives in one place.

Synthetic in-memory SQLite only (test_trade_share_tokens.py's fixture).
"""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import update

import backend.database as db_module
import backend.server as server
from backend.tests.test_trade_share_tokens import (  # noqa: F401  (env is a fixture)
    PLAYERS, SHARE_ON, USER_A, USER_B, _add_match, _mint, env,
)

pytest.importorskip("PIL")
from backend import og_image  # noqa: E402

A_GIVES = PLAYERS["o8p1"]      # _add_match: user_a gives o8p1 ...
A_GETS = PLAYERS["o8p2"]       # ... and receives o8p2


def _tokens(c, mid):
    with patch.object(server, "is_enabled", SHARE_ON):
        a = _mint(c, USER_A, mid)
        b = _mint(c, USER_B, mid)
    assert a.status_code == b.status_code == 200
    return a.get_json()["token"], b.get_json()["token"]


def _columns(c, tok):
    """(names drawn in the YOU GIVE column, names drawn in the YOU GET
    column) on /og/trade/<tok>.png, from a text-draw spy."""
    calls = []
    cls = og_image.ImageDraw.ImageDraw
    real = cls.text

    def spy(self, xy, text, *a, **kw):
        calls.append((xy, text))
        return real(self, xy, text, *a, **kw)

    with patch.object(cls, "text", spy):
        r = c.get(f"/og/trade/{tok}.png")
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "image/png"
    assert r.data != og_image.render_expired_trade_card()
    heads = {text: xy for xy, text in calls if text in ("YOU GIVE", "YOU GET")}
    assert heads["YOU GIVE"][0] < og_image.CARD_W // 2 < heads["YOU GET"][0], heads
    names = set(PLAYERS.values())
    give = [t for (x, _), t in calls if t in names and x < og_image.CARD_W // 2]
    get = [t for (x, _), t in calls if t in names and x >= og_image.CARD_W // 2]
    return give, get


def test_resolver_orients_the_lists_to_each_sharer(env):
    mid = _add_match()
    a_tok, b_tok = _tokens(env, mid)

    a_row = db_module.resolve_trade_share_token(a_tok)
    b_row = db_module.resolve_trade_share_token(b_tok)
    assert a_row["id"] == b_row["id"] == mid
    assert (json.loads(a_row["user_a_give"]), json.loads(a_row["user_a_receive"])) \
        == (["o8p1"], ["o8p2"])
    assert (json.loads(b_row["user_a_give"]), json.loads(b_row["user_a_receive"])) \
        == (["o8p2"], ["o8p1"])
    assert (a_row["shared_by"], b_row["shared_by"]) == ("a", "b")
    # The sharer's id stays server-side; only the side marker is added.
    assert "created_by" not in a_row and "created_by" not in b_row
    # The stored match is untouched: the swap is on the read only.
    with db_module.engine.connect() as conn:
        stored = conn.execute(db_module.trade_matches_table.select()
                              .where(db_module.trade_matches_table.c.id == mid)
                              ).mappings().one()
    assert json.loads(stored["user_a_give"]) == ["o8p1"]
    assert json.loads(stored["user_a_receive"]) == ["o8p2"]


def test_og_card_draws_the_sharers_give_under_you_give(env):
    mid = _add_match()
    a_tok, b_tok = _tokens(env, mid)
    assert _columns(env, a_tok) == ([A_GIVES], [A_GETS])
    assert _columns(env, b_tok) == ([A_GETS], [A_GIVES])


def test_misses_are_unchanged(env):
    """A revoked user_b token, an unknown token and a numeric id all still
    get the one generic expired page and PNG, byte-identical."""
    mid = _add_match()
    _, b_tok = _tokens(env, mid)
    tst = db_module.trade_share_tokens_table
    with db_module.engine.begin() as conn:
        conn.execute(update(tst).where(tst.c.token == b_tok)
                     .values(revoked_at="2026-10-31T00:00:00+00:00"))
    assert db_module.resolve_trade_share_token(b_tok) is None
    ref_page = env.get("/s/trade/" + "A" * 22)
    ref_png = env.get("/og/trade/" + "A" * 22 + ".png")
    assert ref_png.data == og_image.render_expired_trade_card()
    for key in (b_tok, "B" * 22, str(mid)):
        page = env.get(f"/s/trade/{key}")
        png = env.get(f"/og/trade/{key}.png")
        for r, ref in ((page, ref_page), (png, ref_png)):
            assert r.status_code == ref.status_code == 200
            assert r.data == ref.data
            assert sorted(r.headers.items()) == sorted(ref.headers.items())
