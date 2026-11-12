"""Keep / untouchable as a hard rule on owner-family cards (model_config
``owner_untouchable_hard``, default 1; 0 = the premium-return rule).

Operator report (TestFlight build 186): untouchables showed in trade cards. The
served engine (bilateral revision 2 on ``trade_gen_owner``) let an untouchable
leave whenever the incoming market value beat the outgoing and a same-position
player came back, for the viewer's Keep marks and league-mates' alike. Pins:

- hard (default): no generated card sends the viewer's Keep player or asks for
  a league-mate's, on every owner path: owner-v1, bilateral 1 and 2, the
  rules-first page search, the gated full solve, and the served deck after the
  offline downstream stages; the page still equals the gated full solve, and
  every deck is exactly today's minus the cards that carry a Keep player;
- the viewer's explicit give pin still overrides their own mark; a pinned GET
  never overrides a league-mate's;
- revalidation: a card built under the old rule fails the hard evaluator (a
  stale stored card cannot be re-served), and a revised offer of the viewer's
  own sent offer that sends their Keep player is not proposed;
- likes: a hand-queued like (D-170) still surfaces (as today's consensus card
  when the hard evaluator rejects it); an engine like that would send the
  viewer's untouchable stays skipped;
- knob 0 reproduces today's decks byte for byte on a Keep-heavy synthetic
  league (digests captured from fa83f57b before the change), and its request
  hash is today's; on, the hash is a new unit;
- marking Keep through the real route revokes the cached deck (the viewer's
  and a league-mate's) and marks the league's stored pages stale.

Synthetic data only; no provider, network or production access.
"""
import copy
import json
from dataclasses import asdict

import pytest

from backend import bakeoff_runner as bo, feature_flags as ff, server
from backend import trade_fast_deck as fast, trade_gen_owner as owner, trade_service as ts
from backend import trade_gen_bilateral as bilateral, trade_gen_bilateral_candidate as candidate
from backend import trade_next_move as nm
from backend.eval import served_deck_replay as replay, synthetic_league
from backend.tests.test_bilateral_generation_freeze import digest, generated_value

KNOB = owner.UNTOUCHABLE_HARD_KEY


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS))
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))


def keeps(ctx):
    """3-6 Keep marks per team, the realistic roster-setup shape: the team's
    best player and a spread of starters below it (picks never marked)."""
    out = {}
    rosters = {"me": ctx["user_roster"], **{m.user_id: m.roster for m in ctx["league"].members}}
    for i, (uid, roster) in enumerate(sorted(rosters.items())):
        ranked = sorted((p for p in roster if not p.startswith("k")),
                        key=lambda p: (-ctx["seed_elo"][p], p))
        out[uid] = {"untouchables": [ranked[j] for j in (0, 3, 6, 9, 12, 15)[:3 + i % 4]]}
    return out


_WORLDS = {}


def keep_world(teams=5, seed=7):
    if (teams, seed) not in _WORLDS:
        ctx = synthetic_league.build(teams=teams, seed=seed)
        ctx["manager_preferences"] = keeps(ctx)
        _WORLDS[teams, seed] = ctx
    return copy.deepcopy(_WORLDS[teams, seed])


def violations(cards, prefs):
    mine = set(prefs["me"]["untouchables"])
    return ([c for c in cards if set(c.give_player_ids) & mine],
            [c for c in cards if set(c.receive_player_ids) & set(prefs[c.target_user_id]["untouchables"])])


def ids(cards):
    return [fast._identity(c) for c in cards]


GENERATORS = [candidate.generate_bilateral_trades, bilateral.generate_bilateral_trades,
              owner.generate_owner_trades]


@pytest.mark.parametrize("generate", GENERATORS, ids=["revision2", "revision1", "owner_v1"])
def test_no_generated_card_sends_a_keep_player_either_side(generate):
    ctx = keep_world()
    cards, _ = generate(**copy.deepcopy(ctx))
    assert cards
    give, receive = violations(cards, ctx["manager_preferences"])
    assert give == [] and receive == []
    # Non-vacuous: the same world under the premium-return rule breaks both sides.
    ts._cfg[KNOB] = 0.
    old, _ = generate(**copy.deepcopy(ctx))
    give, receive = violations(old, ctx["manager_preferences"])
    assert give and receive
    # Absence is the only effect: the hard inventory is exactly today's minus
    # the cards that send a Keep player (Keep players keep their pool slots).
    broken = {fast._identity(c) for c in give + receive}
    assert set(ids(cards)) == set(ids(old)) - broken


def test_rules_first_page_equals_gated_full_solve_and_serves_no_keep_player():
    ctx = keep_world(12, 7)
    request = replay.Request(copy.deepcopy(ctx), replay.DEFAULT_SLOTS)
    built, _, info = fast.serve(candidate.generate_bilateral_trades, copy.deepcopy(ctx), request.rules())
    gated, _ = fast.gated_full(candidate.generate_bilateral_trades, copy.deepcopy(ctx), request.rules())
    full, _ = candidate.generate_bilateral_trades(**copy.deepcopy(ctx))
    assert info["path"] == "page"
    assert ids(built) == ids(gated)
    assert [c.owner_evaluation.as_dict() for c in built] == [c.owner_evaluation.as_dict() for c in gated]
    served, _ = request.served(built)
    assert served and ids(served) == ids(request.served(gated)[0])
    assert set(ids(served)) == set(ids(request.served(full)[0]))
    assert violations(built, ctx["manager_preferences"]) == ([], [])
    assert violations(served, ctx["manager_preferences"]) == ([], [])
    # The served deck is today's served deck minus its Keep cards, as a set.
    ts._cfg[KNOB] = 0.
    today, _ = request.served(fast.serve(candidate.generate_bilateral_trades, copy.deepcopy(ctx),
                                         request.rules())[0])
    give, receive = violations(today, ctx["manager_preferences"])
    assert give and receive
    assert set(ids(served)) == set(ids(today)) - set(ids(give + receive))


def test_today_the_served_deck_carried_keep_players():
    """Non-vacuity for the served deck: under the premium-return rule the
    rules-first deck, after the offline downstream stages, holds Keep players."""
    ts._cfg[KNOB] = 0.
    ctx = keep_world(12, 7)
    request = replay.Request(copy.deepcopy(ctx), replay.DEFAULT_SLOTS)
    built, _, _ = fast.serve(candidate.generate_bilateral_trades, copy.deepcopy(ctx), request.rules())
    served, _ = request.served(built)
    give, receive = violations(served, ctx["manager_preferences"])
    assert give and receive


def test_explicit_give_pin_overrides_the_viewers_own_keep():
    ctx = keep_world()
    pin = ctx["manager_preferences"]["me"]["untouchables"][1]
    cards, _ = candidate.generate_bilateral_trades(**ctx, pinned_give_players=[pin])
    assert cards and all(pin in c.give_player_ids for c in cards)
    assert ctx["manager_preferences"]["me"]["untouchables"][1] == pin   # never rewritten


def _premium_card(ctx, *, side):
    """A card the premium-return rule builds that sends a Keep player."""
    ts._cfg[KNOB] = 0.
    cards, _ = candidate.generate_bilateral_trades(**copy.deepcopy(ctx))
    give, receive = violations(cards, ctx["manager_preferences"])
    ts._cfg[KNOB] = 1.
    return (give if side == "give" else receive)[0]


def test_pinned_get_never_overrides_a_league_mates_keep():
    ctx = keep_world()
    card = _premium_card(ctx, side="receive")
    keep = next(p for p in card.receive_player_ids
                if p in ctx["manager_preferences"][card.target_user_id]["untouchables"])
    request = dict(ctx, pinned_receive_players=[keep], opponent_user_id=card.target_user_id)
    cards, report = candidate.generate_bilateral_trades(**copy.deepcopy(request))
    assert cards == [] and report.as_dict()["rejections"]["untouchable"]
    ts._cfg[KNOB] = 0.
    assert candidate.generate_bilateral_trades(**copy.deepcopy(request))[0]   # today: offered


@pytest.mark.parametrize("side", ["give", "receive"])
def test_a_card_built_under_the_old_rule_fails_revalidation(side):
    ctx = keep_world()
    card = _premium_card(ctx, side=side)
    for evaluate in (candidate.evaluate_bilateral_trades, bilateral.evaluate_bilateral_trades,
                     owner.evaluate_owner_trades):
        proof = evaluate([copy.copy(card)], **copy.deepcopy(ctx))[0]
        assert not proof.eligible and proof.reason == "untouchable"


def test_a_revised_offer_never_sends_the_viewers_keep_player():
    from backend.tests.test_trade_next_move import context, offer
    ff._flags_cache[nm.FLAG] = True
    ts._cfg.update(age_pref_mult_u23=1.0, age_pref_mult_30plus=1.0)
    ctx = context(own=("give", "mid"), market={"give": 1000., "target": 1400., "mid": 300.},
                  viewer={"give": 800., "target": 1680., "mid": 250.},
                  partner={"give": 1350., "target": 1120., "mid": 380.},
                  manager_preferences={"viewer": {"untouchables": ["give"]}})
    assert nm.propose_revision(offer(), ctx, step_min=.05) is None
    premium = {**ctx, "config": {**ctx["config"], KNOB: 0.}}
    move = nm.propose_revision(offer(), premium, step_min=.05)
    assert move is not None and "give" in move.card.give_player_ids     # today: proposed


# ── Likes: D-170 stands ────────────────────────────────────────────────────

def _inject(monkeypatch, ctx, like, untouchable_ids):
    monkeypatch.setattr(server, "load_recent_league_likes", lambda **kw: [like])
    monkeypatch.setattr(server, "_standing_offers_enabled", lambda: False)
    service = ts.TradeService(dict(ctx["players"]))
    proofs = []

    def prove(card):   # _prove_liked_card's decision: the job's own owner evaluator
        probe = ts.TradeCard("", card.league_id, "me", card.target_user_id, card.target_username,
                             list(card.give_player_ids), list(card.receive_player_ids), 0, 0, 0)
        proof = candidate.evaluate_bilateral_trades([probe], **copy.deepcopy(ctx))[0]
        proofs.append(proof)
        return proof if proof.eligible else None

    cards = server._inject_likes_you_cards_impl(
        [], service, "me", "L", ctx["league"], ctx["user_roster"], dict(ctx["seed_elo"]),
        untouchable_ids=untouchable_ids, prove=prove)
    return cards, proofs


def _like(card, trade_id):
    # The league-mate's like, from their side: they give what the viewer receives.
    return {"user_id": card.target_user_id, "trade_id": trade_id, "impression_id": None,
            "give_player_ids": list(card.receive_player_ids),
            "receive_player_ids": list(card.give_player_ids)}


def test_a_hand_queued_like_still_surfaces_with_the_viewers_keep_player(monkeypatch):
    ctx = keep_world()
    card = _premium_card(ctx, side="give")
    keep = set(ctx["manager_preferences"]["me"]["untouchables"])
    cards, proofs = _inject(monkeypatch, ctx, _like(card, "calcq_abc"), keep)
    assert len(cards) == 1 and cards[0].likes_you
    assert set(cards[0].give_player_ids) & keep
    # The hard evaluator does not prove it, so it is today's consensus card.
    assert [p.reason for p in proofs] == ["untouchable"]
    assert getattr(cards[0], "owner_evaluation", None) is None


def test_an_engine_like_sending_the_viewers_keep_player_is_skipped(monkeypatch):
    ctx = keep_world()
    card = _premium_card(ctx, side="give")
    keep = set(ctx["manager_preferences"]["me"]["untouchables"])
    cards, proofs = _inject(monkeypatch, ctx, _like(card, "deck123"), keep)
    assert cards == [] and proofs == []


# ── Knob 0 is today, byte for byte ──────────────────────────────────────────

# Captured on fa83f57b (before this change) from keep_world(5, 7) with the
# default config: generated_value digests (test_bilateral_generation_freeze),
# and the rules-first serve's identities and terms.
TODAY = {
    "revision2": "1c2c2e06f07746cc5e0b54bc6cd1ece1ab7e04cdd9b74e8ac071b7d00279f32a",
    "revision1": "2d01dfe69f69ed734f8aa210452457a77c6333027968c9cc700b2f2feac438a6",
    "owner_v1": "bf518810a3b03f3679146ca9181575d33306fdcb2ca130dd6b7cdf348c4d19c1",
    "serve": "bd0793807b073f2e37bbcee2e9fcaa43f75cb7ed270a410490caa70e96461b93",
}


def _owner_value(ctx):
    cards, report = owner.generate_owner_trades(**copy.deepcopy(ctx))
    values = []
    for card in cards:
        data = asdict(card)
        for key in ("trade_id", "created_at", "expires_at"):
            data.pop(key, None)
        values.append(data)
    return json.loads(json.dumps([values, report.as_dict()], default=asdict))


def _serve_value(ctx):
    request = replay.Request(copy.deepcopy(ctx), replay.DEFAULT_SLOTS)
    built, _, info = fast.serve(candidate.generate_bilateral_trades, copy.deepcopy(ctx), request.rules())
    assert info["path"] == "page"
    return [[c.target_user_id, c.give_player_ids, c.receive_player_ids, c.give_value,
             c.receive_value, c.fairness_score, c.composite_score] for c in built]


def test_knob_zero_reproduces_todays_decks_byte_for_byte():
    ts._cfg[KNOB] = 0.
    ctx = keep_world()
    assert digest(generated_value(candidate, ctx)) == TODAY["revision2"]
    assert digest(generated_value(bilateral, ctx)) == TODAY["revision1"]
    assert digest(_owner_value(ctx)) == TODAY["owner_v1"]
    assert digest(_serve_value(ctx)) == TODAY["serve"]
    ts._cfg[KNOB] = 1.
    assert digest(generated_value(candidate, ctx)) != TODAY["revision2"]


def test_the_knob_never_enters_report_or_proof_bytes():
    ctx = keep_world()
    for value in (0., 1.):
        ts._cfg[KNOB] = value
        cards, report = candidate.generate_bilateral_trades(**copy.deepcopy(ctx))
        assert KNOB not in report.snapshot_json
        assert all(KNOB not in c.owner_evaluation.snapshot_json for c in cards)


def test_request_hash_is_todays_at_knob_zero_and_a_new_unit_on():
    ctx = keep_world()
    def request_hash(config):
        return server._owner_selected_assignment(dict(ctx, config=config), "organic",
                                                 serve=False)["request_hash"]
    base = {k: v for k, v in ts._DEFAULT_CFG.items() if k != KNOB}
    today = request_hash(dict(base))
    assert request_hash({**base, KNOB: 0.}) == today
    assert request_hash({**base, KNOB: 1.}) != today
    assert owner.untouchable_hard({}) and owner.untouchable_hard({KNOB: float("nan")})
    assert not owner.untouchable_hard({KNOB: 0.})


def test_the_replay_tool_measures_the_keep_rule():
    """`served_deck_replay --untouchable` (the operator's recorded-request run) on
    a synthetic request: the hard rule removes cards and leaves no Keep player."""
    row = replay.untouchable_effect(candidate.generate_bilateral_trades, keep_world(),
                                    replay.DEFAULT_SLOTS)
    assert row["premium_breaks"] > 0 and row["hard_breaks"] == 0
    assert row["removed_served"] == row["premium_served"] - row["hard_served"]
    assert row["viewer_keeps"] == 3 and row["mate_keeps"] > 0
    assert "must be 0): 0" in replay.summarize_untouchable([row])
