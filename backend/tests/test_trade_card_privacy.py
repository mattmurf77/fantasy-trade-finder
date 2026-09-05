"""Owner contracts: redact known counterparty personal values at the public edge.

Scope: docs/plans/owner-contracts/policy-scope.md, privacy amendment.
Pins real GET /api/trades output, each known numeric field, retained viewer
values/qualitative fit/MESO assets, internal-card immutability, and ordinary
cards' unchanged optional-field behavior. No database or network access.
"""

from copy import deepcopy
from unittest.mock import MagicMock

import pytest

import backend.server as server
from backend.trade_service import TradeCard


@pytest.fixture
def card():
    return TradeCard(
        trade_id="privacy-card", league_id="privacy-league",
        proposing_user_id="viewer", target_user_id="partner",
        target_username="Partner", give_player_ids=["give"],
        receive_player_ids=["receive"], mismatch_score=50.0,
        fairness_score=0.95, composite_score=0.75,
        rationale={
            "user": {"own_board_gain": 321.0, "board": "personal"},
            "counterparty": {
                "own_board_gain": 987.0, "board": "personal",
                "timeline": {"value": "rebuilder", "source": "declared"},
                "why_yes": {
                    "values_return_above_cost": True,
                    "gives_from_surplus": ["WR"], "fills_needs": ["RB"],
                    "timeline_fit": "rebuild_gets_youth_or_picks",
                },
            },
        },
        meso_variants=[{
            "shape": "youth_heavy", "give_player_ids": ["alternative"],
            "recipient_value_delta_pct": 4.7,
        }],
    )


def _assert_public(card, payload):
    expected_rationale = deepcopy(card.rationale)
    expected_rationale["counterparty"].pop("own_board_gain")
    assert payload["rationale"] == expected_rationale
    assert payload["meso_variants"] == [{
        "shape": "youth_heavy", "give_player_ids": ["alternative"],
    }]


def test_serializer_redacts_counterparty_gain_not_viewer_or_fit(card):
    payload = server.trade_card_to_dict(card, {})
    assert "own_board_gain" not in payload["rationale"]["counterparty"]
    assert payload["rationale"]["user"] == card.rationale["user"]
    assert payload["rationale"]["counterparty"]["why_yes"] == (
        card.rationale["counterparty"]["why_yes"])
    assert payload["rationale"]["counterparty"]["timeline"] == (
        card.rationale["counterparty"]["timeline"])


def test_serializer_redacts_meso_recipient_value_not_assets_or_shape(card):
    payload = server.trade_card_to_dict(card, {})
    assert payload["meso_variants"] == [{
        "shape": "youth_heavy", "give_player_ids": ["alternative"],
    }]


def test_serialization_preserves_internal_personal_evidence(card):
    original = deepcopy(card)
    payload = server.trade_card_to_dict(card, {})
    _assert_public(card, payload)
    assert card == original
    assert card.rationale["counterparty"]["own_board_gain"] == 987.0
    assert card.meso_variants[0]["recipient_value_delta_pct"] == 4.7


def test_no_rationale_or_variants_keeps_the_same_payload(card):
    card.rationale = None
    card.meso_variants = None
    absent = server.trade_card_to_dict(card, {})
    assert "rationale" not in absent
    assert "meso_variants" not in absent
    card.rationale = {}
    card.meso_variants = []
    assert server.trade_card_to_dict(card, {}) == absent


def test_get_trades_returns_redacted_copy_not_private_card(card, monkeypatch):
    service = MagicMock()
    service.get_pending_trades.return_value = [card]
    session = {
        "user_id": "viewer", "verified": True, "active_format": "1qb_ppr",
        "league": MagicMock(), "players": [], "trade_svc": service,
    }
    monkeypatch.setattr(server, "_get_session", lambda _token: session)
    monkeypatch.setitem(server.app.config, "TESTING", True)
    with server.app.test_client() as client:
        response = client.get("/api/trades?league_id=privacy-league",
                              headers={"X-Session-Token": "privacy-token"})
    assert response.status_code == 200
    _assert_public(card, response.get_json()[0])
    service.get_pending_trades.assert_called_once_with(
        user_id="viewer", league_id="privacy-league")
    assert card.rationale["counterparty"]["own_board_gain"] == 987.0
    assert card.meso_variants[0]["recipient_value_delta_pct"] == 4.7
