"""Build O8 — unguessable share links for trades.

/s/trade/<x> and /og/trade/<x>.png used to take the sequential
trade_matches.id with no auth, so anyone could walk the ids and read every
mutual match's give/get and fairness verdict. They now resolve ONLY through
a 128-bit token in trade_share_tokens, minted by POST /api/share/trade for a
party to the match. Every miss gets one generic "expired" page and PNG,
status 200, identical bytes. Spec: docs/plans/share-link-tokens/scope.md.

Synthetic in-memory SQLite only — never the live DB.
"""
import base64
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, delete, func, insert, select, text, update
from sqlalchemy.exc import OperationalError

import backend.database as db_module
import backend.server as server
from backend import accounts
from backend.database import metadata

pytest.importorskip("PIL")
from backend import og_image  # noqa: E402

USER_A = "888888888800000101"
USER_B = "888888888800000102"
OUTSIDER = "888888888800000103"
TOKENS = {USER_A: "sess-o8-a", USER_B: "sess-o8-b", OUTSIDER: "sess-o8-out"}

# Recognisable names: if any of these reaches a miss response, trade content
# leaked.
PLAYERS = {"o8p1": "Zebulon Quartermain", "o8p2": "Xavier Oddlybold"}

TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{22}")


def _flags(*enabled):
    on = set(enabled)
    return lambda k: k in on


SHARE_ON = _flags("growth.share_landing")


def _mint(c, user, match_id):
    return c.post("/api/share/trade",
                  headers={"X-Session-Token": TOKENS[user],
                           "Content-Type": "application/json"},
                  data=json.dumps({"match_id": match_id}))


def _add_match(user_a=USER_A, user_b=USER_B) -> int:
    with db_module.engine.begin() as conn:
        res = conn.execute(insert(db_module.trade_matches_table).values(
            league_id="o8-league", user_a_id=user_a, user_b_id=user_b,
            user_a_give=json.dumps(["o8p1"]), user_a_receive=json.dumps(["o8p2"]),
            matched_at="2026-10-20T00:00:00+00:00", status="pending",
        ))
        return res.inserted_primary_key[0]


@pytest.fixture()
def env():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    db_patch = patch.object(db_module, "engine", engine)
    db_patch.start()
    with engine.begin() as conn:
        for pid, name in PLAYERS.items():
            conn.execute(insert(db_module.players_table).values(
                player_id=pid, full_name=name, position="WR", search_rank=50))
    with server._sessions_lock:
        for uid, tok in TOKENS.items():
            server._sessions[tok] = {"verified": True, "user_id": uid,
                                     "active_format": "1qb_ppr",
                                     "last_active": time.time()}
    try:
        yield c
    finally:
        with server._sessions_lock:
            for tok in TOKENS.values():
                server._sessions.pop(tok, None)
        db_patch.stop()


def _miss_page(c):
    """The reference miss: a 22-char token nobody minted."""
    return c.get("/s/trade/" + "A" * 22)


def _same_response(a, b):
    assert a.status_code == b.status_code == 200
    assert a.data == b.data
    assert sorted(a.headers.items()) == sorted(b.headers.items())


# ---------------------------------------------------------------------------
# Mint
# ---------------------------------------------------------------------------

def test_participant_mints_a_token_and_both_routes_render_the_trade(env):
    mid = _add_match()
    with patch.object(server, "is_enabled", SHARE_ON):
        r = _mint(env, USER_A, mid)
    assert r.status_code == 200, r.get_data(as_text=True)
    out = r.get_json()
    tok = out["token"]
    assert out == {"ok": True, "token": tok, "url": f"/s/trade/{tok}",
                   "og_image": f"/og/trade/{tok}.png"}
    # The match id and sharer never go back to the client.
    assert str(mid) not in json.dumps(out).replace(tok, "")

    page = env.get(f"/s/trade/{tok}")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert f'content="/og/trade/{tok}.png"' in html
    assert "Trade Match" in html
    assert "robots" not in html          # only the miss page is noindex
    assert USER_A not in html and USER_B not in html

    png = env.get(f"/og/trade/{tok}.png")
    assert png.status_code == 200
    assert png.headers["Content-Type"] == "image/png"
    assert png.data[:8] == b"\x89PNG\r\n\x1a\n"
    assert png.data != og_image.render_expired_trade_card()


def test_token_is_22_char_urlsafe_128_bits_and_unique(env):
    matches = [_add_match() for _ in range(200)]
    toks = [db_module.create_trade_share_token(m, USER_A) for m in matches]
    assert len(set(toks)) == len(toks)
    for t in toks:
        assert TOKEN_RE.fullmatch(t), t
        assert len(base64.urlsafe_b64decode(t + "==")) == 16   # 128 bits


def test_remint_is_idempotent_per_sharer_and_each_party_gets_their_own(env):
    mid = _add_match()
    with patch.object(server, "is_enabled", SHARE_ON):
        a1 = _mint(env, USER_A, mid).get_json()["token"]
        a2 = _mint(env, USER_A, mid).get_json()["token"]
        b1 = _mint(env, USER_B, mid).get_json()["token"]
    assert a1 == a2
    assert b1 != a1
    with db_module.engine.connect() as conn:
        rows = conn.execute(select(db_module.trade_share_tokens_table)).mappings().all()
    assert {(r["token"], r["created_by"], r["match_id"]) for r in rows} == {
        (a1, USER_A, mid), (b1, USER_B, mid)}
    assert all(r["created_at"] and r["revoked_at"] is None for r in rows)
    for t in (a1, b1):
        assert db_module.resolve_trade_share_token(t)["id"] == mid


def test_non_participant_missing_and_malformed_all_get_one_identical_404(env):
    mid = _add_match()
    with patch.object(server, "is_enabled", SHARE_ON):
        outsider = _mint(env, OUTSIDER, mid)
        missing = _mint(env, USER_A, mid + 1000)
        malformed = [_mint(env, USER_A, bad) for bad in (
            "abc", -1, 0, True, 1.5, None, 2**31, "1e3", " 1", "١", [mid], {"id": mid})]
    for r in [outsider, missing] + malformed:
        assert r.status_code == 404
        assert r.data == outsider.data
        assert r.get_json() == {"error": "not_found"}
    with db_module.engine.connect() as conn:
        assert conn.execute(select(db_module.trade_share_tokens_table)).first() is None


def test_digit_string_match_id_is_accepted(env):
    """The mobile client keeps the swipe response's match_id as a string."""
    mid = _add_match()
    with patch.object(server, "is_enabled", SHARE_ON):
        r = _mint(env, USER_B, str(mid))
    assert r.status_code == 200
    assert TOKEN_RE.fullmatch(r.get_json()["token"])


def test_demo_session_refused(env):
    mid = _add_match()
    with server._sessions_lock:
        server._sessions[TOKENS[USER_A]]["is_demo"] = True
    with patch.object(server, "is_enabled", SHARE_ON):
        r = _mint(env, USER_A, mid)
    assert r.status_code == 400
    assert r.get_json()["error"] == "demo_session"


def test_mint_404s_while_share_landing_is_dark(env):
    mid = _add_match()
    with patch.object(server, "is_enabled", _flags()):
        r = _mint(env, USER_A, mid)
    assert r.status_code == 404
    assert r.get_json() == {"error": "not_found"}


def test_mint_requires_a_verified_session(env):
    mid = _add_match()
    with patch.object(server, "is_enabled", SHARE_ON):
        anon = env.post("/api/share/trade", data=json.dumps({"match_id": mid}),
                        content_type="application/json")
        with server._sessions_lock:
            server._sessions[TOKENS[USER_A]]["verified"] = False
        unverified = _mint(env, USER_A, mid)
    assert anon.status_code == 401
    assert unverified.status_code == 403


def test_hourly_mint_limit_is_30(env):
    assert server._TRADE_SHARE_HOURLY_LIMIT == 30
    mids = [_add_match() for _ in range(31)]
    with patch.object(server, "is_enabled", SHARE_ON):
        for m in mids[:30]:
            assert _mint(env, USER_A, m).status_code == 200
        r = _mint(env, USER_A, mids[30])
        assert r.status_code == 429
        assert r.get_json()["error"] == "rate_limited"
        # Another user's budget is their own.
        assert _mint(env, USER_B, mids[30]).status_code == 200
        # Mints older than an hour fall out of the window.
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        with db_module.engine.begin() as conn:
            conn.execute(update(db_module.trade_share_tokens_table)
                         .where(db_module.trade_share_tokens_table.c.created_by == USER_A)
                         .values(created_at=old))
        assert _mint(env, USER_A, mids[30]).status_code == 200


def test_reshare_at_the_limit_returns_the_live_token_and_only_new_mints_count(env):
    """Release-lead P3-1: the live-token lookup runs before the count, so a
    re-share at the limit is a 200 with the same body, not a 429."""
    mids = [_add_match() for _ in range(31)]
    with patch.object(server, "is_enabled", SHARE_ON):
        first = [_mint(env, USER_A, m) for m in mids[:30]]
        assert all(r.status_code == 200 for r in first)
        again = _mint(env, USER_A, mids[0])
        assert again.status_code == 200
        assert again.get_json() == first[0].get_json()       # same token, same shape
        assert _mint(env, USER_A, mids[30]).status_code == 429   # a new match still is
        # A revoked token isn't live: sharing that match again is a NEW mint,
        # so it counts, and at the limit it is refused.
        tst = db_module.trade_share_tokens_table
        with db_module.engine.begin() as conn:
            conn.execute(update(tst).where(tst.c.token == first[1].get_json()["token"])
                         .values(revoked_at="2026-10-31T00:00:00+00:00"))
        assert _mint(env, USER_A, mids[1]).status_code == 429
    with db_module.engine.connect() as conn:          # the re-share wrote nothing
        assert conn.execute(select(func.count()).select_from(tst)).scalar() == 30


def test_count_and_insert_share_the_mint_transaction(env):
    """A count failure fails the whole mint (500, nothing written) instead of
    being skipped: the count runs on the mint's own transaction."""
    mid = _add_match()
    with patch.object(db_module, "_count_recent_trade_share_tokens",
                      side_effect=RuntimeError("count failed")), \
            patch.object(server, "is_enabled", SHARE_ON):
        r = _mint(env, USER_A, mid)
    assert r.status_code == 500 and r.get_json() == {"error": "store_failed"}
    with db_module.engine.connect() as conn:
        assert conn.execute(select(db_module.trade_share_tokens_table)).first() is None


# ---------------------------------------------------------------------------
# Misses: numeric ids, unknown / revoked / malformed / orphaned tokens
# ---------------------------------------------------------------------------

def test_numeric_match_ids_never_return_trade_content(env):
    mid = _add_match()
    with patch.object(server, "is_enabled", SHARE_ON):
        assert _mint(env, USER_A, mid).status_code == 200   # a live share exists
    ref_page = _miss_page(env)
    ref_png = env.get("/og/trade/" + "A" * 22 + ".png")
    for numeric in (str(mid), "1", "0", "999999", "1" * 22):
        page = env.get(f"/s/trade/{numeric}")
        _same_response(page, ref_page)
        html = page.get_data(as_text=True)
        for name in PLAYERS.values():
            assert name not in html
        assert "Trade Match" not in html
        assert "fair" not in html.lower()
        assert f"/og/trade/{numeric}.png" not in html

        png = env.get(f"/og/trade/{numeric}.png")
        _same_response(png, ref_png)
        assert png.data == og_image.render_expired_trade_card()


def test_every_miss_is_the_same_generic_page_and_png(env):
    live_mid = _add_match()
    orphan_mid = _add_match()
    revoked = db_module.create_trade_share_token(live_mid, USER_A)
    orphaned = db_module.create_trade_share_token(orphan_mid, USER_B)
    with db_module.engine.begin() as conn:
        conn.execute(update(db_module.trade_share_tokens_table)
                     .where(db_module.trade_share_tokens_table.c.token == revoked)
                     .values(revoked_at="2026-10-20T00:00:00+00:00"))
        conn.execute(delete(db_module.trade_matches_table)
                     .where(db_module.trade_matches_table.c.id == orphan_mid))
    misses = [
        revoked, orphaned,
        "B" * 22,                 # unknown
        revoked[:21],             # too short
        revoked + "x",            # too long
        "!" * 22,                 # outside the alphabet
        "expired",                # the page's own og:image path
        str(live_mid),            # numeric id of a shared match
    ]
    ref_page = _miss_page(env)
    ref_png = env.get("/og/trade/" + "A" * 22 + ".png")
    html = ref_page.get_data(as_text=True)
    assert og_image.TRADE_LINK_EXPIRED_TITLE in html
    assert og_image.TRADE_LINK_EXPIRED_BODY in html
    assert '<meta name="robots" content="noindex">' in html
    assert 'content="/og/trade/expired.png"' in html
    assert 'href="/"' in html
    assert ref_png.data == og_image.render_expired_trade_card()
    for m in misses:
        _same_response(env.get(f"/s/trade/{m}"), ref_page)
        _same_response(env.get(f"/og/trade/{m}.png"), ref_png)


def test_lookup_failure_degrades_to_the_generic_miss(env):
    tok = db_module.create_trade_share_token(_add_match(), USER_A)
    ref_page = _miss_page(env)
    with patch.object(server, "resolve_trade_share_token",
                      side_effect=RuntimeError("db down")):
        _same_response(env.get(f"/s/trade/{tok}"), ref_page)


# ---------------------------------------------------------------------------
# Logging: the app never logs a token (release-lead P3-2). A DB error's text
# carries its bound parameters, so the two DB log sites log the type only.
# ---------------------------------------------------------------------------

CANARY = "LOGcanaryTOKEN0123456x"   # 22 chars: a well-formed token


def _app_log(caplog):
    return "\n".join(r.getMessage() for r in caplog.records if r.name == "trade_finder")


def test_a_lookup_db_error_logs_no_token(env, caplog):
    caplog.set_level(logging.WARNING, logger="trade_finder")
    tok = db_module.create_trade_share_token(_add_match(), USER_A)
    with db_module.engine.begin() as conn:           # a real DB error
        conn.execute(text("DROP TABLE trade_share_tokens"))
    r = env.get(f"/s/trade/{tok}")
    assert r.status_code == 200 and tok not in r.get_data(as_text=True)
    logged = _app_log(caplog)
    assert "trade share lookup failed: OperationalError" in logged
    assert tok not in logged


def test_a_mint_db_error_logs_no_token(env, caplog):
    caplog.set_level(logging.WARNING, logger="trade_finder")
    mid = _add_match()
    # Make the INSERT itself fail with a real OperationalError (a trigger
    # that writes to a dropped table), and fix the token so it can be found.
    with db_module.engine.begin() as conn:
        conn.execute(text("CREATE TABLE o8_gone (x)"))
        conn.execute(text("CREATE TRIGGER o8_fail BEFORE INSERT ON trade_share_tokens "
                          "BEGIN INSERT INTO o8_gone VALUES (1); END"))
        conn.execute(text("DROP TABLE o8_gone"))
    with patch("secrets.token_urlsafe", return_value=CANARY):
        # The hazard is real: the error's own text carries the new token.
        with pytest.raises(OperationalError) as err:
            db_module.create_trade_share_token(mid, USER_A)
        assert CANARY in str(err.value)
        with patch.object(server, "is_enabled", SHARE_ON):
            r = _mint(env, USER_A, mid)
    assert r.status_code == 500
    assert r.get_json() == {"error": "store_failed"}
    logged = _app_log(caplog)
    assert f"share/trade: could not mint a token for {USER_A}: OperationalError" in logged
    assert CANARY not in logged


def test_expired_card_is_deterministic():
    first = og_image.render_expired_trade_card()
    og_image.render_expired_trade_card.cache_clear()
    assert og_image.render_expired_trade_card() == first


# ---------------------------------------------------------------------------
# Account deletion
# ---------------------------------------------------------------------------

def test_account_deletion_removes_the_users_tokens_only(env):
    mid = _add_match()
    with patch.object(server, "is_enabled", SHARE_ON):
        a_tok = _mint(env, USER_A, mid).get_json()["token"]
        b_tok = _mint(env, USER_B, mid).get_json()["token"]
    counts = accounts.delete_user_data(USER_A)
    assert counts["trade_share_tokens_deleted"] == 1
    assert db_module.resolve_trade_share_token(a_tok) is None
    _same_response(env.get(f"/s/trade/{a_tok}"), _miss_page(env))
    # The counterparty's own share survives (the match is anonymized, not
    # deleted, by account deletion).
    assert db_module.resolve_trade_share_token(b_tok)["id"] == mid
    assert "Trade Match" in env.get(f"/s/trade/{b_tok}").get_data(as_text=True)
