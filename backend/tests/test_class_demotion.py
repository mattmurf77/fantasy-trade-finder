"""P0-4 (B6) — flag aggregation + bounded class demotion (LLD §4.6, D11, T-23).

House convention: sabotage-proven. Every test names the production change that
must turn it red. Review reads the sabotage list, not the green run.

T-23 is explicitly TWO-SIDED, and the PRD says so for a reason: a one-sided
test that only proves "noise never demotes" passes trivially against a pass
that demotes nothing ever, and a one-sided test that only proves "bad classes
get demoted" passes against a pass that demotes on 3 flags out of 40. Both
directions, in the same fixture, or the bar is decorative:

  * 3 flags / 40 exposures ⇒ demotion EXACTLY 1.0 (noise floor);
  * a high-n, high-rate class ⇒ demotion < 1.0 but ≥ class_demotion_floor.

The other four properties under test:
  * the applied multiplier is FROZEN into features_json and EQUALS what was
    actually multiplied into the ordering key (HLD §2.3 corollary);
  * empty / corrupt `deck_class_stats` ⇒ serving byte-identical (all 1.0);
  * flag off ⇒ no lookup, no multiplier, no frozen key;
  * the chunked scan handles a fixture larger than one chunk.
"""

import json
import uuid
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select

import backend.database as db_module
import backend.relevance.config as rel_config
import backend.server as server
from backend.database import (
    deck_class_stats_table,
    deck_impressions_table,
    deck_outcomes_table,
    metadata,
)
from backend.relevance.passes import flag_agg
from backend.trade_service import TradeCard


LEAGUE = "league_demo"
ME     = "user_me"
OPP    = "user_opp"

NOW = datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc)

SEED_MAP = {"STAR": 3000.0, "STAR2": 2900.0, "f1": 1200.0, "f2": 1100.0}


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

@pytest.fixture
def eng(tmp_path, monkeypatch):
    """Isolated file-backed product engine with the real schema."""
    e = create_engine(f"sqlite:///{tmp_path / 'demotion.db'}",
                      connect_args={"check_same_thread": False, "timeout": 30})
    metadata.create_all(e)
    monkeypatch.setattr(db_module, "engine", e)
    rel_config._reset_cache()
    server._class_demotion_reset_cache()
    yield e
    rel_config._reset_cache()
    server._class_demotion_reset_cache()


def _seed_exposures(eng, *, archetype, shape, band, views, flags,
                    served_at=None, start=0):
    """`views` viewed impressions in one class, `flags` of them also flagged.

    Writes the class through the SAME shape serving reads: archetype and
    shape_bucket are columns, `receive_value_band` lives ONLY inside
    features_json (no SQL column — the reason the group-by is a Python parse).
    """
    served_at = served_at or (NOW - timedelta(days=1)).isoformat()
    imps, outs = [], []
    for i in range(views):
        iid = f"{archetype}-{shape}-{band}-{start + i:06d}-{uuid.uuid4().hex[:8]}"
        imps.append({
            "impression_id": iid, "user_id": ME, "league_id": LEAGUE,
            "deck_job_id": "job-x", "card_index": i,
            "features_json": json.dumps({"receive_value_band": band}),
            "propensity": 1.0, "archetype": archetype, "shape_bucket": shape,
            "served_at": served_at,
        })
        outs.append({"impression_id": iid, "action": "viewed",
                     "acted_at": served_at})
        if i < flags:
            outs.append({"impression_id": iid, "action": "not_interested",
                         "acted_at": served_at})
    with eng.begin() as conn:
        conn.execute(insert(deck_impressions_table), imps)
        conn.execute(insert(deck_outcomes_table), outs)


class _Ctx:
    def __init__(self, now=NOW):
        self.now = now
        self.run_date = now.strftime("%Y-%m-%d")
        self.counters = {}
        self.state = {}
        self.attempt = 1
        self.deadline_at = None


def _stats(eng, stat_date=None):
    with eng.connect() as conn:
        q = select(deck_class_stats_table)
        if stat_date:
            q = q.where(deck_class_stats_table.c.stat_date == stat_date)
        return {(r.archetype, r.shape_bucket, r.value_band): r
                for r in conn.execute(q)}


def _mk_card(*, lane, give, recv, recv_value, composite, likes_you=False):
    c = TradeCard(
        trade_id           = f"t_{uuid.uuid4().hex[:8]}",
        league_id          = LEAGUE,
        proposing_user_id  = ME,
        target_user_id     = OPP,
        target_username    = "opp",
        give_player_ids    = list(give),
        receive_player_ids = list(recv),
        mismatch_score     = 1.0,
        fairness_score     = 0.9,
        composite_score    = composite,
        likes_you          = likes_you,
    )
    c.lane = lane
    c.receive_value = recv_value
    return c


def _serving_env(*, on: bool):
    """class_demotion flag pinned; every OTHER ordering layer pinned off, so
    an ordering difference can only come from this layer."""
    stack = ExitStack()
    stack.enter_context(patch.object(
        server, "_deck_class_demotion_enabled", lambda: on))
    for helper in ("_thompson_deck_enabled", "_deck_thompson_v2_enabled",
                   "_deck_diversity_enabled", "_deck_fatigue_enabled",
                   "_deck_dedup_enabled"):
        stack.enter_context(patch.object(server, helper, lambda: False))
    return stack


def _order(cards, capture=None):
    return server._order_deck(
        cards, user_id=ME, league_id=LEAGUE, job_id="job-A",
        seed_map=SEED_MAP, capture=capture)


# ---------------------------------------------------------------------------
# Pure math — the two floors (T-23, both directions)
# ---------------------------------------------------------------------------

def test_noise_never_demotes_3_flags_on_40_exposures():
    # SABOTAGE: drop the `views < min_views ⇒ 1.0` branch in `demotion_for`
    # (or make it `<=`-clamp instead of an exact 1.0) ⇒ a 7.5% flag rate on
    # 40 exposures starts demoting an archetype product-wide. This is D11's
    # named rejected design.
    d, shrunk = flag_agg.demotion_for(3, 40, 0.02, floor=0.5, min_views=200)
    assert d == 1.0
    assert shrunk is not None          # still REPORTED, just not applied

def test_high_n_high_rate_class_is_demoted_but_never_below_the_floor():
    # SABOTAGE: remove the `max(floor, ...)` clamp ⇒ a pathological class can
    # be driven toward 0 and effectively gated. Remove the ratio entirely ⇒
    # nothing is ever demoted and the whole pass is decorative.
    d, shrunk = flag_agg.demotion_for(150, 500, 0.05, floor=0.5, min_views=200)
    assert 0.5 <= d < 1.0
    assert shrunk > 0.05               # this class is worse than global


def test_zero_global_flag_rate_never_demotes_anything():
    # SABOTAGE: delete the `rho <= 0` guard ⇒ rho/shrunk is 0/1e-9 = 0 for
    # EVERY class and the clamp pins the entire product at the floor. The
    # single most destructive bug this function can have.
    d, _ = flag_agg.demotion_for(0, 10_000, 0.0, floor=0.5, min_views=200)
    assert d == 1.0


def test_class_at_the_global_rate_rides_1_0():
    # SABOTAGE: shrink toward 0 instead of toward rho ⇒ an average class is
    # demoted for being average.
    d, _ = flag_agg.demotion_for(50, 1000, 0.05, floor=0.5, min_views=200)
    assert d == 1.0


def test_class_key_normalizes_nulls_to_one_sentinel():
    # SABOTAGE: return None for a missing archetype ⇒ the NOT NULL insert
    # explodes, or (worse) the serving lookup builds a different key and
    # every NULL-archetype class silently misses.
    assert flag_agg.class_key(None, "1x1", None) == ("unknown", "1x1", "unknown")
    assert server._deck_class_key(
        _mk_card(lane=None, give=["f1"], recv=["STAR"],
                 recv_value=None, composite=1.0)) == ("unknown", "1x1", "unknown")


# ---------------------------------------------------------------------------
# The pass — T-23 end to end, both directions in ONE fixture
# ---------------------------------------------------------------------------

def test_t23_pass_writes_both_floors_from_one_window(eng):
    # SABOTAGE (any of these must turn this red):
    #   • drop the min_views floor ⇒ the noise class gets demoted;
    #   • drop the [floor, 1.0] clamp ⇒ the bad class falls below 0.5;
    #   • join flags off `bad_trade_flags` instead of the impression-keyed
    #     `not_interested` outcome ⇒ no numerator at all (that table has
    #     neither impression_id nor trade_hash);
    #   • group on give_value_band instead of receive_value_band ⇒ the
    #     classes collapse into one and both floors vanish.
    _seed_exposures(eng, archetype="win_now", shape="1x1", band="1000-1500",
                    views=40, flags=3)                 # noise: under n
    _seed_exposures(eng, archetype="rebuild", shape="2x1", band="2000-2500",
                    views=500, flags=150)              # high n, high rate
    _seed_exposures(eng, archetype="neutral", shape="1x1", band="500-1000",
                    views=1000, flags=20)              # high n, healthy

    result = flag_agg.run_pass(_Ctx())
    rows = _stats(eng, NOW.strftime("%Y-%m-%d"))
    assert len(rows) == 3 == result["classes"]

    noise = rows[("win_now", "1x1", "1000-1500")]
    assert noise.exposures == 40 and noise.flags == 3
    assert noise.demotion == 1.0, "noise must NEVER demote"

    bad = rows[("rebuild", "2x1", "2000-2500")]
    assert bad.exposures == 500 and bad.flags == 150
    assert 0.5 <= bad.demotion < 1.0, "a high-n high-rate class must demote"
    assert bad.demotion >= 0.5, "the floor is what keeps this from being a gate"

    healthy = rows[("neutral", "1x1", "500-1000")]
    assert healthy.demotion == 1.0

    assert result["demoted"] == 1
    assert result["exposures"] == 1540 and result["flags"] == 173


def test_pass_ignores_impressions_outside_the_30d_window(eng):
    # SABOTAGE: drop the `served_at >= since_day` predicate ⇒ the window is
    # "all time" and a class that was fixed months ago stays demoted forever.
    old = (NOW - timedelta(days=60)).isoformat()
    _seed_exposures(eng, archetype="stale", shape="1x1", band="0-500",
                    views=500, flags=250, served_at=old)
    result = flag_agg.run_pass(_Ctx())
    assert result["classes"] == 0
    assert _stats(eng) == {}


def test_pass_counts_only_viewed_impressions_as_exposures(eng):
    # SABOTAGE: drop the `viewed` gate ⇒ served-but-never-fronted cards enter
    # the denominator, the rate is diluted, and a genuinely bad class stops
    # clearing the bar. Cascade rule, same as the Thompson v2 arms.
    served = (NOW - timedelta(days=1)).isoformat()
    _seed_exposures(eng, archetype="a", shape="1x1", band="0-500",
                    views=300, flags=90)
    with eng.begin() as conn:                 # 200 served, never viewed
        imps = [{
            "impression_id": f"unviewed-{i}", "user_id": ME, "league_id": LEAGUE,
            "deck_job_id": "job-y", "card_index": i,
            "features_json": json.dumps({"receive_value_band": "0-500"}),
            "propensity": 1.0, "archetype": "a", "shape_bucket": "1x1",
            "served_at": served,
        } for i in range(200)]
        conn.execute(insert(deck_impressions_table), imps)
        conn.execute(insert(deck_outcomes_table), [
            {"impression_id": "unviewed-0", "action": "not_interested",
             "acted_at": served}])
    result = flag_agg.run_pass(_Ctx())
    row = _stats(eng)[("a", "1x1", "0-500")]
    assert row.exposures == 300, "unviewed impressions are not exposures"
    assert row.flags == 90
    assert result["flags_unviewed"] == 1      # reported, not silently dropped


def test_pass_is_idempotent_within_a_day(eng):
    # SABOTAGE: switch batch_write from `upsert` to `insert` ⇒ a same-day
    # re-run (double-POST, stale-claim recovery, retry) raises on the unique
    # key and leaves the day half-written.
    _seed_exposures(eng, archetype="a", shape="1x1", band="0-500",
                    views=300, flags=90)
    flag_agg.run_pass(_Ctx())
    flag_agg.run_pass(_Ctx())
    assert len(_stats(eng)) == 1


def test_pass_prunes_history_past_30_days(eng):
    # SABOTAGE: drop the prune ⇒ deck_class_stats grows without bound and the
    # operator report's MAX(stat_date) read gets slower every night.
    with eng.begin() as conn:
        conn.execute(insert(deck_class_stats_table).values(
            archetype="old", shape_bucket="1x1", value_band="0-500",
            exposures=1, flags=0, flag_rate_shrunk=0.0, demotion=1.0,
            computed_at="2026-01-01T00:00:00+00:00", stat_date="2026-01-01"))
    _seed_exposures(eng, archetype="a", shape="1x1", band="0-500",
                    views=10, flags=1)
    result = flag_agg.run_pass(_Ctx())
    assert result["pruned"] == 1
    assert all(k[0] != "old" for k in _stats(eng))


def test_yesterdays_rows_stay_live_when_the_pass_fails(eng):
    # SABOTAGE: make the pass write a "clearing" row set (DELETE-then-INSERT)
    # ⇒ a mid-pass crash leaves the product with no stats at all instead of
    # yesterday's. Fail-soft is a property of the data layout, not a handler.
    _seed_exposures(eng, archetype="a", shape="1x1", band="0-500",
                    views=300, flags=90)
    flag_agg.run_pass(_Ctx(NOW - timedelta(days=1)))
    before = _stats(eng)
    with patch.object(flag_agg, "aggregate", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            flag_agg.run_pass(_Ctx())
    assert _stats(eng) == before


# ---------------------------------------------------------------------------
# Chunking (PRD R8 pre-build check 2)
# ---------------------------------------------------------------------------

def test_chunked_scan_reads_a_fixture_larger_than_one_chunk(eng):
    # SABOTAGE: drop the keyset cursor (`impression_id > :cursor`) ⇒ every
    # chunk re-reads page 1 and the loop either spins forever or counts the
    # first chunk N times. Drop the pagination entirely and only `chunk_rows`
    # of the window is ever aggregated.
    _seed_exposures(eng, archetype="a", shape="1x1", band="0-500",
                    views=250, flags=25, start=0)
    _seed_exposures(eng, archetype="b", shape="2x1", band="0-500",
                    views=250, flags=125, start=1000)
    agg = flag_agg.aggregate(since_day=(NOW - timedelta(days=30)).strftime("%Y-%m-%d"),
                             engine=eng, chunk_rows=37)
    assert agg["scanned"] == 500
    assert agg["views"] == 500 and agg["flags"] == 150
    assert agg["counts"][("a", "1x1", "0-500")] == [250, 25]
    assert agg["counts"][("b", "2x1", "0-500")] == [250, 125]
    assert agg["truncated"] is False


def test_row_ceiling_stops_the_scan_and_says_so(eng):
    # SABOTAGE: remove the max_rows ceiling ⇒ the pass is unbounded and the
    # 60s budget becomes a hope at 10× volume (the PRD's exact words).
    _seed_exposures(eng, archetype="a", shape="1x1", band="0-500",
                    views=300, flags=30)
    agg = flag_agg.aggregate(since_day=(NOW - timedelta(days=30)).strftime("%Y-%m-%d"),
                             engine=eng, chunk_rows=50, max_rows=100)
    assert agg["truncated"] is True
    assert agg["scanned"] == 100


def test_malformed_features_json_becomes_the_unknown_band(eng):
    # SABOTAGE: let json.loads raise ⇒ one corrupt row kills the whole night's
    # aggregation and yesterday's numbers go stale silently.
    served = (NOW - timedelta(days=1)).isoformat()
    with eng.begin() as conn:
        conn.execute(insert(deck_impressions_table).values(
            impression_id="bad-1", user_id=ME, league_id=LEAGUE,
            deck_job_id="j", card_index=0, features_json="{not json",
            propensity=1.0, archetype="a", shape_bucket="1x1",
            served_at=served))
        conn.execute(insert(deck_outcomes_table).values(
            impression_id="bad-1", action="viewed", acted_at=served))
    agg = flag_agg.aggregate(since_day=(NOW - timedelta(days=30)).strftime("%Y-%m-%d"),
                             engine=eng)
    assert agg["counts"] == {("a", "1x1", "unknown"): [1, 0]}


# ---------------------------------------------------------------------------
# Serving — the frozen stamp, the empty/corrupt table, the flag
# ---------------------------------------------------------------------------

def _seed_class_stats(eng, entries, stat_date="2026-08-14"):
    with eng.begin() as conn:
        for (arch, shape, band), demotion in entries.items():
            conn.execute(insert(deck_class_stats_table).values(
                archetype=arch, shape_bucket=shape, value_band=band,
                exposures=500, flags=100, flag_rate_shrunk=0.2,
                demotion=demotion, computed_at=NOW.isoformat(),
                stat_date=stat_date))
    server._class_demotion_reset_cache()


def test_flag_off_applies_nothing_and_freezes_nothing(eng):
    # SABOTAGE: read the stats before checking the flag ⇒ a dark feature
    # starts reordering decks and stamping features_json.
    _seed_class_stats(eng, {("win_now", "1x1", "1000-1500"): 0.5})
    cards = [_mk_card(lane="win_now", give=["f1"], recv=["STAR"],
                      recv_value=1200.0, composite=1.0),
             _mk_card(lane="rebuild", give=["f2"], recv=["STAR2"],
                      recv_value=1200.0, composite=0.9)]
    capture = {}
    with _serving_env(on=False):
        ordered = _order(cards, capture=capture)
    assert [c.trade_id for c in ordered] == [c.trade_id for c in cards]
    assert "class_demotion" not in capture


def test_demotion_reorders_and_the_frozen_value_equals_what_was_applied(eng):
    # SABOTAGE (either turns this red):
    #   • stamp the map read from the table instead of the map ACTUALLY
    #     applied ⇒ replay reconstructs a serve that never happened;
    #   • drop the freeze entirely ⇒ replay has to reconstruct last night's
    #     deck_class_stats, which D8 forbids as leakage (HLD §2.3 corollary).
    _seed_class_stats(eng, {("win_now", "1x1", "1000-1500"): 0.5})
    demoted = _mk_card(lane="win_now", give=["f1"], recv=["STAR"],
                       recv_value=1200.0, composite=1.0)
    clean   = _mk_card(lane="rebuild", give=["f2"], recv=["STAR2"],
                       recv_value=1200.0, composite=0.9)
    capture = {}
    with _serving_env(on=True):
        ordered = _order([demoted, clean], capture=capture)

    # 1.0 × 0.5 = 0.5 < 0.9 ⇒ the demoted card sorts BELOW the clean one.
    assert [c.trade_id for c in ordered] == [clean.trade_id, demoted.trade_id]
    assert capture["class_demotion"][id(demoted)] == 0.5
    assert capture["class_demotion"][id(clean)] == 1.0
    # The frozen key is the applied multiplier, and final_key proves it was
    # the multiplier that actually moved the card.
    assert capture["final_key"][id(demoted)] == pytest.approx(0.5)
    assert capture["final_key"][id(clean)] == pytest.approx(0.9)

    features = _frozen_features(eng, [demoted, clean], capture)
    assert features[demoted.trade_id]["class_demotion"] == 0.5
    assert features[clean.trade_id]["class_demotion"] == 1.0


def _frozen_features(eng, cards, capture):
    """Run the impression writer and read back features_json per card."""
    with patch.object(server, "load_board_state", lambda *a, **k: (0, None)), \
         patch.object(server, "_deck_taste_enabled", lambda: False), \
         patch.object(server, "_deck_fatigue_enabled", lambda: False):
        imp_by_card = server._log_deck_signal_impressions(
            user_id=ME, league_id=LEAGUE, job_id="job-A", cards=cards,
            players_dict={}, capture=capture, scoring_format="1qb_ppr")
    with eng.connect() as conn:
        blobs = {r.impression_id: json.loads(r.features_json) for r in
                 conn.execute(select(deck_impressions_table.c.impression_id,
                                     deck_impressions_table.c.features_json))}
    return {c.trade_id: blobs[imp_by_card[id(c)]] for c in cards}


def test_missing_class_rides_1_0(eng):
    # SABOTAGE: default a missing class to the floor (or to the global rate)
    # ⇒ every brand-new archetype is punished for having no history.
    _seed_class_stats(eng, {("win_now", "1x1", "1000-1500"): 0.5})
    unknown = _mk_card(lane="brand_new", give=["f1"], recv=["STAR"],
                       recv_value=1200.0, composite=1.0)
    capture = {}
    with _serving_env(on=True):
        _order([unknown], capture=capture)
    assert capture["class_demotion"][id(unknown)] == 1.0


@pytest.mark.parametrize("state", ["empty", "null_demotion", "garbage",
                                   "no_table"])
def test_empty_or_corrupt_stats_serves_byte_identically(eng, state):
    # SABOTAGE: let the stats read raise into _order_deck, or treat an
    # unreadable table as "demote everything" ⇒ a nightly pass failure or a
    # bad migration silently reorders (or wrecks) every deck in the product.
    if state == "null_demotion":
        _seed_class_stats(eng, {("win_now", "1x1", "1000-1500"): None})
    elif state == "garbage":
        # Driver-level insert: SQLite is happy to store text in a REAL column,
        # and a hand-repaired / cross-dialect-migrated row is exactly how this
        # arrives in production. The ORM layer would coerce it away.
        with eng.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO deck_class_stats (archetype, shape_bucket, "
                "value_band, exposures, flags, flag_rate_shrunk, demotion, "
                "computed_at, stat_date) VALUES "
                "('win_now','1x1','1000-1500',500,100,0.2,'not-a-number',"
                "'2026-08-14T09:00:00+00:00','2026-08-14')")
        server._class_demotion_reset_cache()
    elif state == "no_table":
        with eng.begin() as conn:
            conn.exec_driver_sql("DROP TABLE deck_class_stats")
        server._class_demotion_reset_cache()

    cards = [_mk_card(lane="win_now", give=["f1"], recv=["STAR"],
                      recv_value=1200.0, composite=1.0),
             _mk_card(lane="rebuild", give=["f2"], recv=["STAR2"],
                      recv_value=1200.0, composite=0.9)]
    with _serving_env(on=False):
        baseline = [c.trade_id for c in _order(list(cards))]
    server._class_demotion_reset_cache()
    capture = {}
    with _serving_env(on=True):
        ordered = [c.trade_id for c in _order(list(cards), capture=capture)]

    assert ordered == baseline, f"{state}: ordering must be byte-identical"
    assert set(capture["class_demotion"].values()) == {1.0}
    # Nothing was multiplied, so the sort never ran: final_key stays absent
    # exactly as it does with the flag off.
    assert "final_key" not in capture


def test_read_clamp_holds_even_if_a_row_is_hand_edited(eng):
    # SABOTAGE: clamp only at write ⇒ an operator (or a bad migration) writing
    # demotion=0.01 turns the bounded reorder into a de-facto gate, which is
    # the ONE thing D11 forbids.
    _seed_class_stats(eng, {("win_now", "1x1", "1000-1500"): 0.01,
                            ("rebuild", "2x1", "1000-1500"): 4.0})
    lo = _mk_card(lane="win_now", give=["f1"], recv=["STAR"],
                  recv_value=1200.0, composite=1.0)
    hi = _mk_card(lane="rebuild", give=["f1", "f2"], recv=["STAR2"],
                  recv_value=1200.0, composite=1.0)
    capture = {}
    with _serving_env(on=True):
        _order([lo, hi], capture=capture)
    assert capture["class_demotion"][id(lo)] == 0.5    # floor, not 0.01
    assert capture["class_demotion"][id(hi)] == 1.0    # ceiling, never a boost


def test_serving_reads_only_the_latest_stat_date(eng):
    # SABOTAGE: drop the MAX(stat_date) filter ⇒ 30 days of history all match
    # the same class and whichever row the driver returns last wins.
    _seed_class_stats(eng, {("win_now", "1x1", "1000-1500"): 0.5},
                      stat_date="2026-08-10")
    _seed_class_stats(eng, {("win_now", "1x1", "1000-1500"): 1.0},
                      stat_date="2026-08-14")
    card = _mk_card(lane="win_now", give=["f1"], recv=["STAR"],
                    recv_value=1200.0, composite=1.0)
    capture = {}
    with _serving_env(on=True):
        _order([card], capture=capture)
    assert capture["class_demotion"][id(card)] == 1.0


def test_demotion_never_removes_a_card(eng):
    # SABOTAGE: turn the multiplier into a filter ("drop below X") ⇒ P0-4
    # becomes a gate. D11's whole point: this layer reorders admitted cards.
    _seed_class_stats(eng, {("win_now", "1x1", "1000-1500"): 0.5,
                            ("rebuild", "1x1", "1000-1500"): 0.5})
    cards = [_mk_card(lane="win_now", give=["f1"], recv=["STAR"],
                      recv_value=1200.0, composite=1.0),
             _mk_card(lane="rebuild", give=["f2"], recv=["STAR2"],
                      recv_value=1200.0, composite=0.9)]
    with _serving_env(on=True):
        ordered = _order(cards)
    assert {c.trade_id for c in ordered} == {c.trade_id for c in cards}


def test_serving_key_matches_the_key_the_pass_groups_on(eng):
    # SABOTAGE: derive the serving band from give_value (or re-derive the
    # archetype some other way) ⇒ the two keys drift, every lookup misses,
    # and the feature is silently inert forever — green tests, zero effect.
    _seed_exposures(eng, archetype="win_now", shape="1x1", band="1000-1500",
                    views=500, flags=200)
    # A healthy bulk class, so the global rate is well below win_now's — a
    # lone class IS the global rate and can never demote itself.
    _seed_exposures(eng, archetype="calm", shape="2x1", band="0-500",
                    views=4000, flags=80, start=100_000)
    flag_agg.run_pass(_Ctx())
    written = set(_stats(eng))
    card = _mk_card(lane="win_now", give=["f1"], recv=["STAR"],
                    recv_value=1200.0, composite=1.0)
    assert server._deck_class_key(card) in written
    capture = {}
    with _serving_env(on=True):
        _order([card], capture=capture)
    assert capture["class_demotion"][id(card)] < 1.0


# ---------------------------------------------------------------------------
# Numerator purity (PRD R8 pre-build check 1)
# ---------------------------------------------------------------------------

def test_report_lists_demoted_classes_with_their_n(eng, monkeypatch):
    # SABOTAGE: drop `exposures` from the demoted-class rows ⇒ the operator
    # sees "win_now/2x1 demoted to 0.62" with no way to tell a real signal
    # from 3 flags on 40 views, and D11's editorial hand-off is broken.
    import backend.analytics_queries as aq
    monkeypatch.setattr(db_module, "ro_engine", eng)
    _seed_exposures(eng, archetype="win_now", shape="2x1", band="1000-1500",
                    views=500, flags=200)
    _seed_exposures(eng, archetype="calm", shape="1x1", band="0-500",
                    views=4000, flags=80, start=100_000)
    flag_agg.run_pass(_Ctx())

    env, _ = aq.run_report("relevance", start="2026-08-01", end="2026-08-14")
    demoted = env["summary"]["demoted_classes"]
    assert len(demoted) == 1
    assert demoted[0]["archetype"] == "win_now"
    assert demoted[0]["exposures"] == 500
    assert 0.5 <= demoted[0]["demotion"] < 1.0
    assert env["summary"]["class_stats"]["classes"] == 2
    assert any(c["code"] == "editorial" for c in env["caveats"])


def test_report_splits_skipped_passes_by_cause(eng, monkeypatch):
    # SABOTAGE: collapse `skipped` into one bucket ⇒ a chronically
    # deadline-starved pass reads as healthy dark, which is exactly the
    # silent-skip failure the ledger exists to kill (M1).
    import backend.analytics_queries as aq
    from backend.database import cron_pass_runs_table
    monkeypatch.setattr(db_module, "ro_engine", eng)
    with eng.begin() as conn:
        conn.execute(insert(cron_pass_runs_table), [
            {"pass_name": "flag_aggregation", "run_date": "2026-08-13",
             "status": "skipped", "started_at": NOW.isoformat(), "attempt": 1,
             "error_text": "valve"},
            {"pass_name": "refit", "run_date": "2026-08-13",
             "status": "skipped", "started_at": NOW.isoformat(), "attempt": 1,
             "error_text": "deadline"},
            {"pass_name": "pushes", "run_date": "2026-08-13", "status": "ok",
             "started_at": NOW.isoformat(), "attempt": 1, "duration_ms": 12,
             "error_text": None},
        ])
    env, _ = aq.run_report("relevance", start="2026-08-01", end="2026-08-14")
    causes = env["summary"]["ledger"]["skipped_by_cause"]
    assert causes["valve"] == 1 and causes["deadline"] == 1
    assert env["summary"]["ledger"]["status_counts"]["ok"] == 1
    by_pass = {r["pass_name"]: r for r in env["rows"]}
    assert by_pass["refit"]["skip_cause"] == "deadline"
    assert by_pass["pushes"]["skip_cause"] is None


def test_report_is_dark_not_zero_on_an_empty_database(eng, monkeypatch):
    # SABOTAGE: render 0% for an unmeasured join rate ⇒ the operator reads a
    # fabricated zero as a broken loop and rolls back a healthy feature.
    import backend.analytics_queries as aq
    monkeypatch.setattr(db_module, "ro_engine", eng)
    env, _ = aq.run_report("relevance", start="2026-08-01", end="2026-08-14")
    assert env["rows"] == []
    lh = env["summary"]["loop_health"]
    assert lh["disposition_join_rate"]["value"] is None
    assert lh["disposition_join_rate"]["caveat"] == "dark"
    scopes = {c["scope"] for c in env["caveats"]}
    assert {"section:ledger", "section:demoted_classes"} <= scopes


def test_not_interested_has_exactly_one_writer():
    # SABOTAGE: add a second `_save_deck_outcome_safe(..., "not_interested")`
    # call site (or let the swipe route pass a client-supplied action through)
    # ⇒ the numerator is inflated by a signal that isn't a bad-trade flag and
    # innocent classes get demoted. If this test fails, the fix is a DISTINCT
    # action string, not a wider join.
    import pathlib
    src = pathlib.Path(server.__file__).read_text()
    writers = [ln for ln in src.splitlines()
               if '"not_interested"' in ln and "_save_deck_outcome_safe" in ln]
    assert len(writers) == 1, f"expected 1 writer, found: {writers}"
