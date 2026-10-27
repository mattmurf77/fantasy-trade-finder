"""MOD-M1 task 1: scripts/deck_eval.py measures the live first deck.

Acceptance (a): for one league and seat, deck_eval's path
(backend/eval/first_deck.py) serves the same first page, card for card, as the
plain live flow driven here without any deck_eval code: the league connected
by another member's first open, then the brand-new user's POST
/api/session/init, its pregen job on a worker thread, and the client's
first-page POST /api/trades/generate. Same flags, overrides and RNG seed.
Acceptance (b): the report defaults into the gitignored feedback-workspace.
Also: overrides change what deck_eval produces (none silently ignored), and
the scratch-database guards.

Synthetic superflex TEP league (so the stored, daemon-detected format is
exercised), Sleeper mocked, sockets refused: no network.
"""
import json
import random
import socket
import subprocess
import threading
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

import backend.database as db
import backend.feature_flags as ff
import backend.ranking_service as rs
import backend.server as server
import backend.sleeper_trades_service as trades_service
import backend.suggestion_telemetry as sugg_tel
import backend.trade_block_service as tb_service
import backend.trade_service as ts
from backend import deck_quality, trade_bilateral_presentment
from backend.eval import first_deck as fd
from backend.ranking_service import Player
from scripts import deck_eval

LEAGUE = "1100000000000000001"
TEAMS = ["u1", "u2", "u3"]          # roster ids 1..3: u1 connects the league
SEAT = "u2"                         # the brand-new user under test (not the connector)
SEED = 0
VOLATILE = ("trade_id", "impression_id", "expires_at")

# The live engine: owner_v2_bilateral, exclusive serve, with the revision (so
# owner presentment runs) and the D-207 quality filters.
LIVE = {"flags": {"trade.bakeoff": True, "deck.quality_filters": True, "deck.signal_v2": True,
                  "picks.owned_sync": True, "trade.picks_in_pool": True},
        "model_config": {"bakeoff_include_owner": 1, "bakeoff_serve_owner": 1,
                         "bakeoff_owner_only": 1, "owner_bilateral_enabled": 1,
                         "owner_bilateral_revision_enabled": 1}}


def _league():
    positions = ["QB", "RB", "WR", "TE", "RB", "WR", "WR", "RB"]
    rng = random.Random(7)
    players, seed, rosters = [], {}, {}
    for t, uid in enumerate(TEAMS):
        rosters[uid] = []
        for i, pos in enumerate(positions):
            pid = f"{uid}_{i}"
            players.append(Player(id=pid, name=f"{pos} {uid}-{i}", position=pos, team="AAA",
                                  age=22 + (i * 3 + t) % 12))
            seed[pid] = round(1250 + rng.random() * 600, 1)
            rosters[uid].append(pid)
    meta = {"league_id": LEAGUE, "name": "Eval League", "season": "2026", "total_rosters": 3,
            "roster_positions": ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX", "BN", "BN"],
            "scoring_settings": {"rec": 1.0, "bonus_rec_te": 0.5},
            "settings": {"draft_rounds": 1}}
    sleeper = {f"league/{LEAGUE}": meta,
               f"league/{LEAGUE}/rosters": [{"roster_id": n + 1, "owner_id": uid,
                                             "players": rosters[uid]} for n, uid in enumerate(TEAMS)],
               f"league/{LEAGUE}/users": [{"user_id": uid, "username": uid,
                                           "display_name": uid.upper()} for uid in TEAMS],
               f"league/{LEAGUE}/traded_picks": [], f"league/{LEAGUE}/drafts": []}
    return players, seed, sleeper


_LEAGUE_CACHES = ("_DRAFT_CONTEXT_CACHE", "_LEAGUE_MEMBERS_CACHE", "_FA_LEAGUE_META_CACHE",
                  "_trade_block_cache", "_slot_order_cache", "_SUGGESTED_ORDER_CACHE",
                  "_rookie_ids_memo", "_consensus_rank_cache", "_OUTLOOK_IMPACT_CACHE",
                  "_rank_chip_cache", "_deck_withdrawn_cache", "_experiment_digest_memo")


@pytest.fixture
def world(monkeypatch, tmp_path):
    """Pools, Sleeper and the network patched; every flow gets its own scratch DB."""
    players, seed, sleeper = _league()
    unexpected = []

    def fake_get(url, timeout=15):
        tail = url.split("/v1/")[-1]
        if tail not in sleeper:
            unexpected.append(url)
            raise RuntimeError(f"unexpected Sleeper GET {url}")
        return json.loads(json.dumps(sleeper[tail]))

    def refuse(*_a, **_k):
        raise RuntimeError("network refused in test")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(server, "_sleeper_get", fake_get)
    monkeypatch.setattr(tb_service, "_fetch_rosters",
                        lambda lid, **k: json.loads(json.dumps(sleeper[f"league/{LEAGUE}/rosters"])))
    monkeypatch.setattr(tb_service, "fetch_league_players", lambda lid, **k: [])
    monkeypatch.setattr(trades_service, "fetch_week_transactions", lambda lid, wk, **k: [])
    monkeypatch.setattr(sugg_tel, "fetch_league_roster_map", lambda lid, **k: {})
    pools = {f: {"players": list(players), "seed": dict(seed)} for f in db.SCORING_FORMATS}
    monkeypatch.setattr(server, "_load_sleeper_cache", lambda: {})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setattr(server, "g_universal_by_format", pools)
    monkeypatch.setattr(server, "g_universal_players", list(players))
    monkeypatch.setattr(server, "_start_deck_evidence_thread", lambda *, target, args: target(*args))
    monkeypatch.setattr(server, "_send_typed_push", MagicMock())
    for name in ("_trade_jobs", "_trade_jobs_by_key", "_trade_input_epochs", *_LEAGUE_CACHES):
        monkeypatch.setattr(server, name, type(getattr(server, name))())
    base_flags, base_ts, base_rs = ff.flags_dict(), dict(ts._cfg), dict(rs._cfg)
    calls = {"quality": 0, "presentment": 0}
    real_filter, real_present = deck_quality.filter_deck, trade_bilateral_presentment.present

    def count(name, real):
        def wrapper(*a, **k):
            calls[name] += 1
            return real(*a, **k)
        return wrapper

    monkeypatch.setattr(deck_quality, "filter_deck", count("quality", real_filter))
    monkeypatch.setattr(trade_bilateral_presentment, "present", count("presentment", real_present))

    engines = []

    def scratch(name, overrides=LIVE):
        """A fresh scratch DB (init_db + overrides) and empty league caches."""
        work = tmp_path / name
        work.mkdir()
        engine = create_engine(f"sqlite:///{work / 'scratch.sqlite3'}",
                               connect_args={"check_same_thread": False})
        engines.append(engine)
        for attr in ("engine", "ingest_engine", "ro_engine"):
            monkeypatch.setattr(db, attr, engine)
        db.init_db()
        monkeypatch.setattr(ff, "_flags_cache", dict(base_flags))
        _restore(ts._cfg, base_ts)
        for cache in _LEAGUE_CACHES:
            getattr(server, cache).clear()
        fd.apply_overrides(overrides)
        calls.update(quality=0, presentment=0)
        return work

    yield scratch, calls, unexpected
    _restore(ts._cfg, base_ts)
    _restore(rs._cfg, base_rs)
    for engine in engines:
        engine.dispose()


def _restore(cfg, base):
    """reload_config updates the module config dicts in place."""
    cfg.clear()
    cfg.update(base)


def _deck_eval(scratch, name, overrides=LIVE, max_teams=2):
    work = scratch(name, overrides)
    with fd.FirstDeckEval(work, seed=SEED) as evaluation:
        return evaluation.run_league(LEAGUE, max_teams=max_teams)


def _live_first_page(user_id, connector):
    """The plain live flow: no deck_eval code but the shared RNG seed input.
    Each init's daemon finishes before its response, as in the session-init
    tests; the user's pregen job runs on its own worker thread; the
    connector's job is not under test."""
    client, kicked, real_thread = server.app.test_client(), [], threading.Thread

    class InlineDaemon(real_thread):
        def start(self):
            if self.name == "session-init-bg-writes":
                return self.run()
            return super().start()

    with patch.object(server.threading, "Thread", InlineDaemon), \
            patch.object(server, "_start_trade_job_thread", lambda **kw: kicked.append(kw)), \
            fd.stable_rng_seed(SEED):
        for uid in (connector, user_id):
            server._sessions[f"live-{uid}"] = {"user_id": uid, "verified": True}
            response = client.post("/api/session/init", headers={"X-Session-Token": f"live-{uid}"},
                                   json={"user_id": uid, "league_id": LEAGUE,
                                         "trade_fairness_threshold": 0.5})
            assert response.status_code == 200, response.get_json()
        _connector_job, job = kicked
        worker = real_thread(target=job["target"], args=job["args"], kwargs=job["kwargs"])
        worker.start()
        worker.join(120)
        response = client.post("/api/trades/generate", headers={"X-Session-Token": f"live-{user_id}"},
                               json={"league_id": LEAGUE, "fairness_threshold": 0.5,
                                     "page": 1, "search_id": "live"})
    for uid in (connector, user_id):
        server._sessions.pop(f"live-{uid}", None)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def _stable(cards):
    return [json.loads(json.dumps({k: v for k, v in c.items() if k not in VOLATILE},
                                  sort_keys=True, default=str)) for c in cards]


# ---------------------------------------------------------------------------
# Acceptance (a)
# ---------------------------------------------------------------------------

def test_deck_eval_reproduces_the_live_first_deck_card_for_card(world):
    scratch, calls, unexpected = world
    scratch("live")
    live = _live_first_page(SEAT, connector=TEAMS[0])
    assert calls["quality"] == 1 and calls["presentment"] == 1   # the D-207 filters, presentment

    league = _deck_eval(scratch, "eval")
    assert calls["quality"] == 2 and calls["presentment"] == 2   # one job per evaluated team
    assert league["error"] is None
    assert league["format"] == {"qb": "SF", "tep": True, "te_bonus": 0.5, "teams": 3,
                                "scoring_format": "sf_tep"}
    seat = league["seats"][1]
    assert seat["user_id"] == SEAT and seat["status"] == "complete" and not seat["regenerated"]

    # The first-30 publication: the deck is longer than the client's first page.
    assert len(live["cards"]) == 30 and live["total_ready"] > 30
    assert {c["model_arm"] for c in live["cards"]} == {"owner_v2_bilateral"}
    assert _stable(seat["first_page"]) == _stable(live["cards"])
    assert seat["first_page_size"] == 30 and seat["deck_size"] == live["total_ready"]
    assert not unexpected

    # The scored first-5 records carry what the gate and the audit sheet need.
    first = seat["cards"][0]
    assert [a["id"] for a in first["give"]] == [p["id"] for p in live["cards"][0]["give"]]
    assert all(a["value"] > 0 and a["position"] for a in first["give"] + first["receive"])
    assert first["delta"] == first["receive_total"] - first["give_total"]
    assert {"i1", "i2", "insult", "haircut", "league_format"} <= set(first)
    assert not any(c["unpriced"] for c in seat["cards"])


# ---------------------------------------------------------------------------
# Overrides are never silently ignored
# ---------------------------------------------------------------------------

def test_overrides_change_what_deck_eval_produces(world):
    scratch, calls, _ = world
    base = _deck_eval(scratch, "base", max_teams=1)["seats"][0]
    assert calls["quality"] == 1 and base["first_page_size"] == 30

    no_quality = {**LIVE, "flags": {**LIVE["flags"], "deck.quality_filters": False}}
    off = _deck_eval(scratch, "no-quality", no_quality, max_teams=1)["seats"][0]
    assert calls["quality"] == 0
    assert off["deck_size"] > base["deck_size"]                  # nothing filtered out
    assert _stable(off["first_page"]) != _stable(base["first_page"])

    page_of_3 = {**LIVE, "model_config": {**LIVE["model_config"], "trade_page_size": 3}}
    short = _deck_eval(scratch, "page-3", page_of_3, max_teams=1)["seats"][0]
    assert short["first_page_size"] == 3
    assert _stable(short["first_page"]) == _stable(base["first_page"][:3])


def test_apply_overrides_rejects_what_it_cannot_apply(world):
    scratch, _, _ = world
    scratch("guards")
    for bad in ({"flags": {"trade.no_such_flag": True}},
                {"flags": {"deck.quality_filters": "false"}},
                {"model_config": {"no_such_knob": 1}},
                {"model_config": {"trade_page_size": True}},
                {"model_config": {}, "knobs": {}}):
        with pytest.raises(ValueError):
            fd.apply_overrides(bad)
    applied = fd.apply_overrides({"model_config": {"trade_page_size": 7}})
    assert applied == {"flags": {}, "model_config": {"trade_page_size": 7.0}}
    assert server._trade_page_size() == 7


# ---------------------------------------------------------------------------
# Acceptance (b) and the scratch-database guards
# ---------------------------------------------------------------------------

def test_report_defaults_to_the_gitignored_workspace():
    json_path, report_path = deck_eval.output_paths("20261027T000000Z")
    assert deck_eval.OUT_DIR == deck_eval.PROJECT_ROOT / "feedback-workspace" / "deck-eval"
    for path in (json_path, report_path):
        assert path.parent == deck_eval.OUT_DIR
        ignored = subprocess.run(["git", "check-ignore", "-q", str(path)],
                                 cwd=deck_eval.PROJECT_ROOT)
        assert ignored.returncode == 0, f"{path} is not gitignored"


def test_require_scratch_db_refuses_anything_else(monkeypatch, tmp_path):
    repo = create_engine(f"sqlite:///{db._DB_PATH}")
    scratch_engine = create_engine(f"sqlite:///{tmp_path / 's.sqlite3'}")
    for engine, expected in ((repo, None), (create_engine("sqlite://"), None),
                             (scratch_engine, str(tmp_path / "other.sqlite3"))):
        for attr in ("engine", "ingest_engine", "ro_engine"):
            monkeypatch.setattr(db, attr, engine)
        with pytest.raises(RuntimeError):
            fd.require_scratch_db(expected)
    monkeypatch.setattr(db, "ingest_engine", repo)              # a second engine elsewhere
    with pytest.raises(RuntimeError):
        fd.require_scratch_db()
    monkeypatch.setattr(db, "ingest_engine", scratch_engine)
    assert fd.require_scratch_db(str(tmp_path / "s.sqlite3")).endswith("s.sqlite3")


def test_the_cli_refuses_a_process_that_already_imported_the_backend(tmp_path):
    with pytest.raises(SystemExit):
        deck_eval._isolate(tmp_path / "scratch.sqlite3", None)


def test_summary_rates_and_bars():
    def card(insult):
        return {"insult": insult, "i1": insult, "i2": False}

    def seat(n_cards, insults=0, status="complete"):
        return {"first_page_size": n_cards, "status": status, "init_ms": 1.0, "job_ms": 2.0,
                "page_ms": 3.0, "regenerated": False,
                "cards": [card(i < insults) for i in range(min(n_cards, 5))]}

    fmt = {"qb": "SF", "tep": False, "teams": 12}
    # 20 teams, 1 empty (5.0%: fails the strict < 5% bar); 95 first-5 cards, 2 insults (2.1%).
    seats = [seat(0)] + [seat(30, insults=1 if i < 2 else 0) for i in range(19)]
    s = fd.summarize([{"format": fmt, "seats": seats, "error": None}])
    assert (s["seats"], s["empty_decks"], s["empty_deck_rate_pct"]) == (20, 1, 5.0)
    assert (s["first5_cards"], s["insult_cards"], s["insult_rate_pct"]) == (95, 2, 2.11)
    assert s["pass"] == {"empty_deck": False, "insult": True}
    assert s["cells"] == {"SF / no TEP / 12 teams": {"leagues": 1, "seats": 20, "empty_decks": 1,
                                                     "first5_cards": 95, "insult_cards": 2}}
