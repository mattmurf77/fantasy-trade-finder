"""Frozen replay adapter avoids invented conviction, private IDs and runtime IO."""
from copy import deepcopy
from types import SimpleNamespace

from backend.eval.scorecard_replay import normalize_offer, _pick, _descriptive
from backend.eval.scorecard_dimensions import evaluate_offer


def context():
    players = {p: {"position": "WR", "age": 23} for p in ("high", "mid", "low")}
    return {"version": "1", "captured_at": "2026-09-19T12:00:00+00:00", "market_as_of": "unavailable",
            "input": {"user_id": "A-user", "user_roster": ["mid"], "players": players,
                      "members": [{"id": "B-user", "roster": ["high", "low"], "elo": {}}],
                      "seed_elo": {"high": 1700, "mid": 1600, "low": 1500},
                      "user_elo": {"mid": 1600}, "user_sources": {"mid": "explicit"},
                      "scoring_format": "1qb_ppr", "outlook": "jets"}}


def normalize(raw):
    card = SimpleNamespace(target_user_id="B-user", give_player_ids=["mid"], receive_player_ids=["high"])
    return normalize_offer(card, raw, model_id="model", market_values={"mid": 2, "high": 3, "low": 1},
                           tier_for=lambda *args: "second", tiers=("first", "second"))


def test_sparse_identical_board_does_not_fabricate_personal_gap():
    raw = context()
    before = deepcopy(raw)
    offer = normalize(raw)
    personal = offer["managers"]["A"]["personal_board"]["entries"]
    market = offer["evidence"]["market"]["entries"]
    assert personal["mid"]["order"] == market["mid"]["order"] == 1
    assert personal["mid"]["explicit"] is True
    assert personal["high"]["explicit"] is False
    assert "personal_board" not in offer["managers"]["B"]
    assert raw == before


def test_capture_time_does_not_claim_market_publication():
    offer = normalize(context())
    p = offer["evidence"]["market"]["provenance"]
    assert p["timestamp_semantics"] == "capture_not_market_publication"
    assert p["source_market_as_of"] == "unavailable"
    assert "projections" not in offer["managers"]["A"]
    result = evaluate_offer(offer)
    assert result["behavioral_acceptance"]["status"] == "unknown"


def test_pick_identity_is_not_inferred_from_display_name():
    assert _pick("generic_pick_1_mid", "PICK") == {"pick_round": 1}
    assert _pick("generic_pick_1_mid", "WR") is None
    assert _pick("looks like a first", "PICK") == {}
    pick = _pick("league_2027_1_roster_with_underscores", "PICK")
    assert pick["original_roster_id"] == "roster_with_underscores"
    assert "original_owner_id" not in pick


def test_preserve_declared_preferences_without_mapping_roster_to_owner():
    raw = context()
    raw["input"]["outlook"] = None
    raw["input"]["manager_preferences"] = {"A-user": {"team_outlook": "jets", "next_draft_year": 2027}}
    offer = normalize(raw)
    assert offer["managers"]["A"]["selected_outlook"] == "jets"
    assert offer["managers"]["A"]["next_draft_year"] == 2027


def test_raw_balance_uses_per_offer_relative_reference_not_acceptance():
    raw = context()
    players = {p: SimpleNamespace(**v) for p, v in raw["input"]["players"].items()}
    cards = [SimpleNamespace(give_player_ids=["mid"], receive_player_ids=["high"]),
             SimpleNamespace(give_player_ids=["high"], receive_player_ids=["mid"])]
    report = _descriptive(cards, raw["input"], players, ("first", "second"),
                          lambda *args: "second", {"mid": 2, "high": 3})
    balance = report["unadjusted_market_return"]
    assert balance["known_offers"] == 2
    assert abs(balance["mean_fraction"] - (0.5 - 1/3)/2) < 1e-12
    assert "Not stud-adjusted" in balance["limitation"]


def test_reconstructed_snapshot_identity_changes_with_values_or_config():
    raw = context()
    raw["request_hash"] = "historical-capture"
    card = SimpleNamespace(target_user_id="B-user", give_player_ids=["mid"], receive_player_ids=["high"])
    kwargs = {"model_id": "model", "tier_for": lambda *args: "second", "tiers": ("first", "second")}
    a = normalize_offer(card, raw, market_values={"mid": 2, "high": 3}, configuration_sha256="cfg1", **kwargs)
    b = normalize_offer(card, raw, market_values={"mid": 2, "high": 4}, configuration_sha256="cfg1", **kwargs)
    c = normalize_offer(card, raw, market_values={"mid": 2, "high": 3}, configuration_sha256="cfg2", **kwargs)
    assert len({a["snapshot_id"], b["snapshot_id"], c["snapshot_id"]}) == 3
    assert a["snapshot_id"] != raw["request_hash"]
    assert a["evidence"]["market"]["provenance"]["source_request_hash"] == "historical-capture"
