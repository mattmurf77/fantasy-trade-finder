"""Win Now proposal §9: true horizon, normalized scoring, availability and provenance."""
from copy import deepcopy
import pytest

from backend.season_forecasts import (ForecastValidationError, fetch_projection_snapshot,
    import_projection_snapshot, normalize_scoring_for_slots, score_stat_vector, snapshot_freshness)

CAPTURE = "2026-09-04T18:00:00Z"


def source_row(week=1):
    return {"player_id": "a", "season": "2026", "week": week,
            "category": "proj", "season_type": "regular", "stats": {"rec": 5, "rec_yd": 60, "pts_ppr": 99},
            "player": {"fantasy_positions": ["WR"], "injury_status": None, "team": "BUF"},
            "team": "BUF", "opponent": "NE", "game_id": "game", "date": "2026-09-13",
            "updated_at": 1788500000000, "company": "rotowire"}


def test_live_adapter_uses_week_vectors_not_aggregate_points_or_dynasty():
    result = fetch_projection_snapshot(2026, [1], lambda _: [source_row()], CAPTURE)
    assert result["supported"]
    assert score_stat_vector(result["forecasts"][0], {"rec": 1, "rec_yd": .1}) == 11
    assert "pts_ppr" not in result["forecasts"][0]["stats"]
    assert result["provider"] == "sleeper_weekly_experimental"
    assert result["quality"]["historical_as_of"] is False
    assert result["captured_at"] != result["published_at"]


def test_missing_future_week_fails_instead_of_reusing_season_or_first_week():
    result = fetch_projection_snapshot(2026, [1, 17], lambda url: [source_row()] if "/1?" in url else [], CAPTURE)
    assert not result["supported"]
    assert "missing_forecast_week:17" in result["reasons"]


def test_wrong_week_payload_fails_closed():
    result = fetch_projection_snapshot(2026, [17], lambda _: [source_row()], CAPTURE)
    assert not result["supported"]
    assert "projection_horizon_mismatch:17" in result["reasons"]


def test_adp_only_placeholder_is_missing_not_zero():
    row = source_row()
    row.update(stats={"adp_dd_ppr": 1000}, game_id=None, opponent=None)
    result = fetch_projection_snapshot(2026, [1], lambda _: [row], CAPTURE)
    assert not result["supported"]
    assert result["forecasts"] == []


def test_independently_verified_bye_is_exact_zero():
    row = source_row()
    row.update(stats={"adp_dd_ppr": 1000}, game_id=None, opponent=None)
    result = fetch_projection_snapshot(2026, [1], lambda _: [row], CAPTURE, bye_weeks={"BUF": 1})
    assert result["supported"]
    assert result["forecasts"][0]["bye"]
    assert result["forecasts"][0]["availability"] == 0
    assert score_stat_vector(result["forecasts"][0], {"rec": 1}) == 0


def test_current_ir_is_not_invented_full_season_return_forecast():
    row = source_row(17)
    row["player"]["injury_status"] = "IR"
    result = fetch_projection_snapshot(2026, [17], lambda _: [row], CAPTURE)
    assert result["forecasts"][0]["availability"] is None
    assert result["quality"]["availability_unknown_count"] == 1


def test_exact_custom_linear_scoring_and_unsupported_threshold():
    row = {"stats": {"pass_yd": 300, "pass_td": 2, "pass_int": 1, "rush_yd": 25}}
    assert score_stat_vector(row, {"pass_yd": .05, "pass_td": 6, "pass_int": -3, "rush_yd": .2}) == 29
    with pytest.raises(ForecastValidationError, match="unsupported_scoring"):
        score_stat_vector(row, {"bonus_pass_yd_300": 3})
    with pytest.raises(ForecastValidationError, match="invalid_scoring"):
        score_stat_vector(row, {"pass_td": float("nan")})


def test_provider_neutral_import_deterministic_identity_and_capture_freshness():
    row = {"player_id": "a", "season": 2026, "week": 1, "positions": ["WR"],
           "stats": {"rec": 5}, "availability": .7, "bye": False}
    kwargs = dict(provider="paid_provider", captured_at=CAPTURE, published_at="2026-09-04T12:00:00Z")
    a = import_projection_snapshot(2026, [1], [row], **kwargs)
    b = import_projection_snapshot(2026, [1], [deepcopy(row)], **kwargs)
    assert a["snapshot_id"] == b["snapshot_id"]
    assert a["provider"] == "paid_provider"
    assert snapshot_freshness(a, "2026-09-04T19:00:00Z")["fresh"]
    assert not snapshot_freshness(a, "2026-09-06T19:00:00Z")["fresh"]
    assert not snapshot_freshness(a, "2026-09-03T19:00:00Z")["fresh"]
    with pytest.raises(ForecastValidationError, match="duplicate_player_week"):
        import_projection_snapshot(2026, [1], [row, row], **kwargs)
    with pytest.raises(ForecastValidationError, match="publication_after_capture"):
        import_projection_snapshot(2026, [1], [row], provider="x", captured_at=CAPTURE,
                                   published_at="2026-09-05T00:00:00Z")


def test_transport_failure_safe_explicit_reason():
    def fail(_):
        raise OSError("secret host path never returned")
    result = fetch_projection_snapshot(2026, [1], fail, CAPTURE)
    assert not result["supported"]
    assert "projection_fetch_failed:1" in result["reasons"]
    assert "secret" not in str(result)


def test_exact_kickoff_only_when_supplied_date_only_is_not_invented_time():
    row = {"player_id": "a", "season": 2026, "week": 1, "positions": ["WR"],
           "stats": {"rec": 5}, "availability": 1, "bye": False,
           "kickoff_at": "2026-09-13T13:00:00-04:00"}
    result = import_projection_snapshot(2026, [1], [row], provider="paid", captured_at=CAPTURE)
    assert result["earliest_kickoff_at"] == "2026-09-13T17:00:00Z"
    source = fetch_projection_snapshot(2026, [1], lambda _: [source_row()], CAPTURE)
    assert source["earliest_kickoff_at"] is None
    assert source["forecasts"][0]["game_date"] == "2026-09-13"


def test_week_start_date_includes_unrostered_first_game():
    rostered, thursday = source_row(), source_row()
    thursday.update(player_id="unrostered", date="2026-09-10")
    result = fetch_projection_snapshot(2026, [1], lambda _: [rostered, thursday], CAPTURE, player_ids=["a"])
    assert len(result["forecasts"]) == 1
    assert result["earliest_game_date"] == "2026-09-10"
    assert result["earliest_game_dates"] == {"1": "2026-09-10"}


def reimport(snapshot, **updates):
    arguments = {key: snapshot.get(key) for key in ("provider", "captured_at", "published_at",
                 "supported_scoring_keys", "provenance", "earliest_game_date", "earliest_game_dates",
                 "earliest_kickoff_at")}
    return import_projection_snapshot(snapshot["season"], snapshot["weeks"], snapshot["forecasts"],
                                      **{**arguments, **updates})


def test_filtered_sleeper_snapshot_reimport_preserves_full_feed_cutoff_and_hash():
    import json
    rostered, thursday = source_row(), source_row()
    thursday.update(player_id="unrostered", date="2026-09-10")
    original = fetch_projection_snapshot(2026, [1], lambda _: [rostered, thursday], CAPTURE, player_ids=["a"])
    loaded = reimport(json.loads(json.dumps(original)))
    assert loaded == original
    assert loaded["earliest_game_date"] == "2026-09-10"
    assert loaded["forecasts"][0]["game_date"] == "2026-09-13"
    assert loaded["earliest_kickoff_at"] is None


def test_supplied_exact_global_kickoff_normalizes_and_changes_snapshot_identity():
    original = fetch_projection_snapshot(2026, [1], lambda _: [source_row()], CAPTURE)
    imported = reimport(original, earliest_kickoff_at="2026-09-10T20:20:00-04:00")
    assert imported["earliest_kickoff_at"] == "2026-09-11T00:20:00Z"
    assert imported["snapshot_id"] != original["snapshot_id"]
    assert reimport(imported) == imported
    earlier = reimport(imported, earliest_game_date="2026-09-10")
    assert earlier["snapshot_id"] != imported["snapshot_id"]
    assert earlier["earliest_game_date"] == "2026-09-10"


@pytest.mark.parametrize("change,reason", [
    ({"earliest_game_date": "2026-09-31"}, "invalid_game_date"),
    ({"earliest_game_date": "2026-09-04T12:00:00Z"}, "invalid_game_date"),
    ({"earliest_game_dates": {"1": "2026-9-04"}}, "invalid_game_date"),
    ({"earliest_game_dates": {"2": "2026-09-04"}}, "cutoff_horizon_mismatch"),
    ({"earliest_game_dates": ["2026-09-04"]}, "invalid_cutoff_weeks"),
    ({"earliest_kickoff_at": "2026-09-04"}, "timestamp_timezone_required"),
    ({"earliest_kickoff_at": "2026-09-04T18:00:00"}, "timestamp_timezone_required"),
])
def test_invalid_cutoff_metadata_cannot_become_a_serving_timestamp(change, reason):
    original = fetch_projection_snapshot(2026, [1], lambda _: [source_row()], CAPTURE)
    with pytest.raises(ForecastValidationError, match=reason):
        reimport(original, **change)


def test_later_global_cutoff_cannot_override_earlier_row_evidence():
    original = fetch_projection_snapshot(2026, [1], lambda _: [source_row()], CAPTURE)
    imported = reimport(original, earliest_game_date="2026-09-20", earliest_game_dates={"1": "2026-09-20"})
    assert imported["earliest_game_date"] == "2026-09-13"
    assert imported["earliest_game_dates"] == {"1": "2026-09-13"}


def test_te_premium_and_position_bonuses_derive_from_events_without_bonus_columns():
    te = {"positions": ["TE"], "stats": {"rec": 6, "rec_yd": 70, "rec_td": 1}}
    scoring = {"rec": 1, "bonus_rec_te": .5, "rec_yd": .1, "rec_td": 6}
    assert score_stat_vector(te, scoring) == 22
    wr = {"positions": ["WR"], "stats": te["stats"]}
    assert score_stat_vector(wr, scoring) == 19
    qb = {"positions": ["QB"], "stats": {"rush_td": 2}}
    assert score_stat_vector(qb, {"rush_td": 6, "bonus_rush_td_qb": 2}) == 16
    rb = {"positions": ["RB"], "stats": {"rec": 5, "bonus_rec_rb": 999}}
    assert score_stat_vector(rb, {"rec": 1, "bonus_rec_rb": .25}) == 6.25
    assert score_stat_vector(wr, {"bonus_rec_wr": .25}) == 1.5


def test_multi_position_bonus_requires_and_uses_primary_position():
    row = {"positions": ["TE", "WR"], "stats": {"rec": 6}}
    with pytest.raises(ForecastValidationError, match="primary_position"):
        score_stat_vector(row, {"bonus_rec_te": .5})
    row["primary_position"] = "WR"
    assert score_stat_vector(row, {"bonus_rec_te": .5, "bonus_rec_wr": .25}) == 1.5


def test_scoring_support_is_limited_to_verified_events_not_aggregate_or_threshold_guesses():
    from backend.season_forecasts import SUPPORTED_SCORING_KEYS
    # Explicit source event fields observed across the 2026-09-04 week1–17
    # capture. Point aggregates, ADP and nonlinear thresholds are excluded.
    verified = set("""pass_yd pass_td pass_int pass_2pt pass_att pass_cmp pass_inc pass_sack pass_fd
    pass_cmp_40p pass_int_td rush_yd rush_td rush_2pt rush_att rush_fd rush_40p rec rec_yd rec_td
    rec_2pt rec_tgt rec_fd rec_0_4 rec_5_9 rec_10_19 rec_20_29 rec_30_39 rec_40p fum fum_lost
    def_fum_td pr pr_td pr_yd def_kr_td def_kr_yd bonus_rec_rb bonus_rec_wr bonus_rec_te bonus_rush_td_qb""".split())
    assert SUPPORTED_SCORING_KEYS <= verified
    for key in ("pts_ppr", "adp_dd_ppr", "bonus_rec_yd_100", "bonus_pass_yd_300", "fgm", "idp_tkl"):
        with pytest.raises(ForecastValidationError, match="unsupported_scoring"):
            score_stat_vector({"positions": ["TE"], "stats": {"rec": 6}}, {key: 1})


def test_inactive_sleeper_kicker_defense_defaults_do_not_block_offensive_scoring():
    scoring = {"rec": 1, "rec_yd": .1, "rec_td": 6, "bonus_rec_te": .5,
               "fum_lost": -2, "fgm_0_19": 3, "xpm": 1, "xpmiss": -1,
               "pts_allow_0": 10, "def_td": 6, "def_st_td": 6,
               "def_st_ff": 1, "def_st_fum_rec": 1, "fum_rec": 2,
               "blk_kick": 2, "int": 2, "sack": 1, "safe": 2, "ff": 1}
    original = deepcopy(scoring)
    normalized = normalize_scoring_for_slots(scoring, ["QB", "RB", "WR", "TE", "FLEX", "BN"])
    row = {"positions": ["TE"], "stats": {"rec": 6, "rec_yd": 70, "rec_td": 1, "fum_lost": 1}}
    assert score_stat_vector(row, normalized) == 20
    assert scoring == original


@pytest.mark.parametrize("key", ["st_ff", "st_fum_rec", "st_td", "fum_rec_td",
    "idp_tkl", "bonus_rec_yd_100", "def_new_rule", "fgm_new_rule", "unknown_offense"])
def test_normalization_never_erases_unmodeled_player_events_or_unknown_rules(key):
    row = {"positions": ["WR"], "stats": {"rec": 5}}
    normalized = normalize_scoring_for_slots({"rec": 1, key: 1}, ["WR"])
    assert normalized[key] == 1
    with pytest.raises(ForecastValidationError, match=f"unsupported_scoring:{key}"):
        score_stat_vector(row, normalized)
    assert score_stat_vector(row, normalize_scoring_for_slots({"rec": 1, key: 0}, ["WR"])) == 5


@pytest.mark.parametrize("slot,key", [("K", "fgm"), ("DEF", "def_td"), ("IDP_FLEX", "idp_tkl")])
def test_active_unsupported_positions_keep_scoring_and_lineup_refusal(slot, key):
    from backend.season_simulator import select_projected_lineup
    normalized = normalize_scoring_for_slots({key: 1}, ["WR", slot])
    assert normalized[key] == 1
    with pytest.raises(ForecastValidationError, match="unsupported_roster_slots"):
        select_projected_lineup([], ["WR", slot], {}, normalized)


def test_offensive_return_and_fumble_vectors_are_not_discarded_as_defense():
    scoring = {"def_fum_td": 6, "def_kr_td": 6, "def_kr_yd": .1, "pr_td": 6, "pr_yd": .1}
    normalized = normalize_scoring_for_slots(scoring, ["WR"])
    assert normalized == scoring
    assert score_stat_vector({"positions": ["WR"], "stats": {"def_fum_td": 1, "def_kr_yd": 40}}, normalized) == 10
