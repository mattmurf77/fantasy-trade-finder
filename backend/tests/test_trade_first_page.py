"""Page-first exact top-K retrieval (backend/trade_first_page.py).

Covers: exact first-page identity against the full bilateral-1 generator
(order, card fields, proof bytes) across requests, outlooks, floors and k;
revision-2 proof identity and the documented top-M-prefix re-rank; bound
admissibility over exhaustively evaluated universes for both generators; the
market-price envelope the pre-pricing bound relies on; work avoided on a
production-sized synthetic league; unsupported requests, aborts, verification
cap and tiny/empty leagues. Performance machinery, each pinned to the
incumbent: the inlined screen is bit-identical to ``_Member.pre``; the
content-keyed lineup memo equals ``owner._Search._lineup`` under a change to
every input it reads, hands out detached dicts, evicts at its cap and is safe
across threads; the tier-coordinate memo equals the incumbent across formats
and in-place band edits; every deferred proof is the full generator's
(bytes, fields) and the dict used for ordering is its decode, exhaustively;
``PageSearch.take`` equals the one-shot call and reports prefix instability;
the verified prefix held at the stop is the full generator's top k + 31. Hermetic: synthetic worlds, pinned config/flags.
"""

import json
import random
import sys
import threading
from functools import lru_cache

import pytest

from backend import (feature_flags, ranking_service, trade_first_page as fp, trade_gen_bilateral as bilateral,
                     trade_gen_bilateral_candidate as candidate, trade_gen_owner as owner,
                     trade_service as ts)
from backend.eval import synthetic_league
from backend.ranking_service import Player
from backend.trade_roster import Asset


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    monkeypatch.setattr(feature_flags, "_flags_cache", dict(feature_flags.DEFAULT_FLAGS))


@pytest.fixture
def crown(monkeypatch):
    monkeypatch.setitem(feature_flags._flags_cache, "trade.crown_asset", True)


def small(**overrides):
    kwargs = dict(seed=3, teams=5, ranked_opponents=2, players_per_team=8, picks_per_team=2)
    extra = {key: overrides.pop(key) for key in list(overrides)
             if key not in ("seed", "teams", "ranked_opponents", "players_per_team",
                            "picks_per_team", "fairness_threshold", "viewer_outlook")}
    kwargs.update(overrides)
    return {**synthetic_league.build(**kwargs), **extra}


def identity(card):
    return card.target_user_id, tuple(card.give_player_ids), tuple(card.receive_player_ids)


def signature(card):
    return card.target_user_id, frozenset(card.give_player_ids), frozenset(card.receive_player_ids)


_FIELDS = ("league_id", "proposing_user_id", "target_user_id", "target_username", "give_player_ids",
           "receive_player_ids", "give_value", "receive_value", "fairness_score", "owner_group",
           "owner_groups", "basis", "lane", "reasons", "match_context", "decision", "narrative")


def assert_same_card(page_card, full_card):
    for name in _FIELDS:
        assert getattr(page_card, name) == getattr(full_card, name), name
    assert page_card.trade_id.startswith("bilateral_") and len(page_card.trade_id) == len(full_card.trade_id)
    assert page_card.owner_evaluation.snapshot_json == full_card.owner_evaluation.snapshot_json
    assert page_card.owner_evaluation.matches(page_card)


@lru_cache(maxsize=None)
def full_solve(generator, seed):
    """The full generator on ``synthetic_league.build(seed)`` under default flags/config."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
        patch.setattr(feature_flags, "_flags_cache", dict(feature_flags.DEFAULT_FLAGS))
        return generator.generate_bilateral_trades(**synthetic_league.build(seed=seed))[0]


def run(k, generator, kwargs_fn):
    result = fp.first_page(k=k, generator=generator, **kwargs_fn())
    assert result is not None
    page, report = result
    return page, report.as_dict()


_VARIANTS = {
    "default": {},
    "seed_9_more_ranked": {"seed": 9, "ranked_opponents": 4},
    "opponent_scope": {"opponent_user_id": "u02"},
    "intent_upgrade": {"trade_intent": "upgrade"},
    "intent_downgrade": {"seed": 5, "trade_intent": "tier_down"},
    "avoid_rb_swap_wr": {"avoid_positions": ["RB"], "swap_positions": ["WR", "TE"]},
    "viewer_jets": {"seed": 4, "viewer_outlook": "jets"},
    "viewer_rebuilder": {"seed": 6, "viewer_outlook": "rebuilder"},
    "unranked_opponents": {"seed": 8, "ranked_opponents": 0},
    "loose_floor": {"seed": 10, "fairness_threshold": .65},
    "tight_floor": {"seed": 11, "fairness_threshold": .9},
    "bigger": {"seed": 12, "teams": 6, "players_per_team": 10},
}


@pytest.mark.parametrize("name", sorted(_VARIANTS))
@pytest.mark.parametrize("flags", ["defaults", "crown"])
def test_bilateral_1_first_page_is_exactly_the_full_generators_first_k(name, flags, monkeypatch):
    if flags == "crown":
        monkeypatch.setitem(feature_flags._flags_cache, "trade.crown_asset", True)
    def kwargs():
        return small(**_VARIANTS[name])
    full, _ = bilateral.generate_bilateral_trades(**kwargs())
    for k in (1, 5, 30, len(full) + 7):
        page, report = run(k, bilateral, kwargs)
        assert not report["incumbent_budgets_bind"] and report["complete"]
        assert report["generator_version"] == bilateral.VERSION and report["returned"] == len(page)
        assert [identity(c) for c in page] == [identity(c) for c in full[:k]]
        for page_card, full_card in zip(page, full):
            assert_same_card(page_card, full_card)
        assert [c.composite_score for c in page] == [float(len(page) - i) for i in range(len(page))]
        assert all(c.mismatch_score == c.composite_score for c in page)


@pytest.mark.parametrize("seed", [11, 23])
def test_bilateral_1_production_sized_first_page_is_exact(seed):
    # The stop proof's main guard: on small worlds best-first order verifies
    # the true top cards before a premature stop could drop one.
    def kwargs():
        return synthetic_league.build(seed=seed)
    full = full_solve(bilateral, seed)
    page, report = run(30, bilateral, kwargs)
    assert report["complete"] and not report["incumbent_budgets_bind"]
    assert [identity(c) for c in page] == [identity(c) for c in full[:30]]
    for page_card, full_card in zip(page, full):
        assert_same_card(page_card, full_card)


def test_exclusions_of_top_cards_are_respected_exactly():
    full, _ = bilateral.generate_bilateral_trades(**small())
    excluded = {(frozenset(c.give_player_ids), frozenset(c.receive_player_ids)) for c in full[:4]}
    def kwargs():
        return small(exclusion_keys=excluded)
    expected, _ = bilateral.generate_bilateral_trades(**kwargs())
    page, report = run(30, bilateral, kwargs)
    assert report["complete"]
    assert [identity(c) for c in page] == [identity(c) for c in expected[:30]]
    assert not {signature(c)[1:] for c in page} & excluded


def test_stop_is_proven_before_the_universe_is_exhausted():
    page, report = run(5, bilateral, lambda: small(seed=12, teams=6, players_per_team=10))
    assert report["complete"] and len(page) == 5
    assert report["verified"] < report["universe"] / 5


def _revision_2_reference(full, k):
    """Top-(k + 31) prefix by bilateral-1 quality, then revision 2's rank."""
    prefix = sorted(full, key=fp._quality)[:k + fp._LOOKAHEAD]
    return candidate._rank(prefix)[:k]


@pytest.mark.parametrize("name", ["default", "seed_9_more_ranked", "viewer_jets", "viewer_rebuilder",
                                  "unranked_opponents", "loose_floor", "bigger"])
def test_revision_2_proofs_match_and_page_is_the_reranked_top_m_prefix(name):
    def kwargs():
        return small(**_VARIANTS[name])
    full, _ = candidate.generate_bilateral_trades(**kwargs())
    by_signature = {signature(c): c for c in full}
    for k in (5, 30):
        page, report = run(k, candidate, kwargs)
        assert report["complete"] and report["generator_version"] == candidate.VERSION
        for card in page:
            reference = by_signature[signature(card)]
            assert identity(card) == identity(reference)
            assert_same_card(card, reference)
        # The one documented difference: term_precedence only sees the verified
        # top-M prefix, so the page equals that prefix re-ranked, not
        # necessarily the full generator's first k.
        assert [identity(c) for c in page] == [identity(c) for c in _revision_2_reference(full, k)]
        overlap = len({identity(c) for c in page} & {identity(c) for c in full[:k]})
        assert overlap >= .8 * min(k, len(full))


def test_revision_2_production_sized_overlap():
    def kwargs():
        return synthetic_league.build(seed=7)
    full = full_solve(candidate, 7)
    page, report = run(30, candidate, kwargs)
    assert report["complete"] and not report["incumbent_budgets_bind"]
    assert [identity(c) for c in page] == [identity(c) for c in _revision_2_reference(full, 30)]
    assert len({identity(c) for c in page} & {identity(c) for c in full[:30]}) >= 27


_AUDIT_BUILDS = [
    {"seed": 1}, {"seed": 2, "viewer_outlook": "jets"}, {"seed": 3, "viewer_outlook": "rebuilder"},
    {"seed": 4, "fairness_threshold": .65, "ranked_opponents": 4},
    {"seed": 5, "teams": 4, "players_per_team": 12, "fairness_threshold": .9}]


@pytest.mark.parametrize("generator", [bilateral, candidate])
@pytest.mark.parametrize("build", _AUDIT_BUILDS)
def test_bounds_are_admissible_over_the_exhaustive_universe(generator, build, crown):
    kwargs = small(**build)
    search = (getattr(generator, "_GenerationSearch", None) or generator._Search)(**kwargs)
    eligible = 0
    with search.ts._cfg_override(search.config), search.ts.stud_tax_override("market"):
        for (screened, pre, priced, support), give, receive, member in fp.screened_universe(search):
            assert screened, (give, receive)
            assert support <= priced + 1e-9 and priced <= pre + 1e-9
            proof = search.evaluate(fp._card(search, member, give, receive))
            if proof.eligible:
                eligible += 1
                weaker = proof.as_dict()["bilateral"]["weaker_support"]
                assert weaker <= support + 1e-9
                assert support - weaker <= 1e-9  # the support level is the exact score
    assert eligible > 20


def test_every_eligible_candidate_clears_the_screened_floor():
    kwargs = small(seed=2)
    full, _ = bilateral.generate_bilateral_trades(**kwargs)
    search = bilateral._Search(**small(seed=2))
    with search.ts._cfg_override(search.config), search.ts.stud_tax_override("market"):
        screened = {(m.user_id, frozenset(g), frozenset(r)) for _, g, r, m in fp.screened_universe(search)}
    assert {signature(c) for c in full} <= screened


_PRICING_CONFIGS = {"default": {},
                    "inverted_floors": {"package_floor_market": .2, "package_floor_cross": .9,
                                        "package_adj_gamma_market": 2.0, "crown_elite_value": 2500.0},
                    "own_benchmark": {"package_bench_trade_wide": 0.0, "package_discount_cap": .9,
                                      "crown_rate_market": .3, "skew_phaseout": 0.0}}


@pytest.mark.parametrize("config", sorted(_PRICING_CONFIGS))
@pytest.mark.parametrize("flag", [False, True])
def test_market_price_envelope_contains_every_package_price(flag, config, monkeypatch):
    # Both envelopes: the loose price_range (companion window) and the tight
    # side_price (pre bound). Pick ids include first-round picks (exempt).
    monkeypatch.setitem(feature_flags._flags_cache, "trade.crown_asset", flag)
    rng = random.Random(17)
    search = bilateral._Search(**small(config=_PRICING_CONFIGS[config]))
    ids = ["L_2027_1_3", "L_2027_2_3", "a", "L_2028_1_5", "b", "c"]
    with search.ts._cfg_override(search.config), search.ts.stud_tax_override("market"):
        bounds = fp._Bounds(search)
        assert bounds.envelope
        for _ in range(4000):
            values = [rng.choice([rng.uniform(1, 400), rng.uniform(400, 3000), rng.uniform(3000, 9900)])
                      for _ in range(rng.randint(2, 4))]
            rng.shuffle(ids)
            split = rng.randint(1, len(values) - 1)
            give, receive = ids[:split], ids[split:len(values)]
            value = dict(zip(give + receive, values))
            ratio, gv, rv = ts.price_consensus_package(give, receive, value_of=value.__getitem__)
            sides = []
            for price, side, other in ((gv, give, receive), (rv, receive, give)):
                lo, hi = bounds.price_range(sum(value[p] for p in side), len(side))
                assert lo <= price <= hi
                lo, hi = bounds.side_price([value[p] for p in side], max(value[p] for p in other))
                assert lo <= price <= hi, (config, side, other, value)
                sides += [lo, hi]
            # can_clear never rejects a package whose priced ratio clears the floor.
            for floor in (.5, .75, .9, ratio, ratio + 1e-6):
                bounds.floor = floor
                assert bounds.can_clear(*sides) or ratio < floor, (config, value, floor)


def test_envelope_is_disabled_outside_its_proven_config(monkeypatch):
    search = bilateral._Search(**small())
    with search.ts._cfg_override({**search.config, "package_discount_cap": 1.5}), \
            search.ts.stud_tax_override("market"):
        assert not fp._Bounds(search).envelope
    page, report = run(5, bilateral, lambda: small(config={"crown_rate_market": -.1}))
    full, _ = bilateral.generate_bilateral_trades(**small(config={"crown_rate_market": -.1}))
    assert not report["price_envelope"] and report["complete"]
    assert [identity(c) for c in page] == [identity(c) for c in full[:5]]


@pytest.mark.parametrize("generator", [bilateral, candidate])
def test_production_sized_league_verifies_a_small_fraction(generator):
    page, report = run(30, generator, lambda: synthetic_league.build(seed=7))
    assert len(page) == 30 and report["complete"] and not report["incumbent_budgets_bind"]
    assert report["universe"] == 11 * 4096
    assert report["verified"] <= 400
    assert report["priced"] <= report["bounded"] < report["universe"]
    assert set(report["elapsed_ms"]) == {"setup", "pools", "screen", "verify", "rank", "total"}
    assert report["bound"] == "support_upper_bound_v1" and report["page_first_version"] == fp.PAGE_FIRST_VERSION
    assert report["score_kind"] == "interpretable_support_not_probability"


@pytest.mark.parametrize("pin", [{"pinned_give_players": ["p00_00"]}, {"pinned_receive_players": ["p01_00"]},
                                 {"exact_give": True}, {"require_all_give": True}])
def test_unsupported_requests_return_none_without_building_a_search(pin, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("search constructed")
    monkeypatch.setattr(candidate, "_GenerationSearch", forbidden)
    monkeypatch.setattr(bilateral, "_Search", forbidden)
    assert fp.first_page(**small(**pin)) is None
    assert fp.first_page(generator=bilateral, **small(**pin)) is None


@pytest.mark.parametrize("after", [0, 5, 60])
def test_check_current_raising_aborts(after):
    class Stale(Exception):
        pass
    calls = []
    def check():
        calls.append(1)
        if len(calls) > after:
            raise Stale
    with pytest.raises(Stale):
        fp.first_page(_check_current=check, **small())


def test_verification_cap_reports_incomplete():
    page, report = run(30, bilateral, lambda: small())
    capped, capped_report = fp.first_page(k=30, generator=bilateral, max_verifications=3, **small())[0:2]
    capped_report = capped_report.as_dict()
    assert report["complete"] and not capped_report["complete"]
    assert capped_report["verified"] == 3 and len(capped) <= 3


def _micro(rosters=(["g"], ["r"])):
    spec = {"g": ("WR", 26, 1000), "r": ("WR", 26, 1000), "add": ("TE", 24, 300)}
    players = {pid: Player(pid, pid, pos, "TST", age) for pid, (pos, age, _) in spec.items()}
    seed = {pid: ts.value_to_elo(value) for pid, (_, _, value) in spec.items()}
    other = ts.LeagueMember("opp", "Other", list(rosters[1]),
                            {"g": ts.value_to_elo(1200), "r": ts.value_to_elo(800)}, True)
    return dict(players=players, league=ts.League("L", "Synthetic", "sleeper", [other]),
                user_id="me", user_roster=list(rosters[0]), seed_elo=seed,
                user_elo={"g": ts.value_to_elo(800), "r": ts.value_to_elo(1200)},
                outlook="not_sure", opponent_outlooks={"opp": "not_sure"}, fairness_threshold=.75)


@pytest.mark.parametrize("generator", [bilateral, candidate])
@pytest.mark.parametrize("rosters", [(["g"], ["r"]), (["g"], ["r", "add"]), (["g"], []), ([], ["r"])])
def test_tiny_and_empty_leagues_return_what_exists(generator, rosters):
    full, _ = generator.generate_bilateral_trades(**_micro(rosters))
    page, report = fp.first_page(k=30, generator=generator, **_micro(rosters))
    report = report.as_dict()
    assert report["complete"] and report["returned"] == len(page) == len(full)
    assert [identity(c) for c in page] == [identity(c) for c in full]
    for page_card, full_card in zip(page, full):
        assert_same_card(page_card, full_card)


# ---------------------------------------------------------------- screen parity

@pytest.mark.parametrize("name", ["default", "viewer_jets", "viewer_rebuilder", "loose_floor", "tight_floor", "bigger"])
@pytest.mark.parametrize("generator", [bilateral, candidate])
def test_screen_is_bit_identical_to_pre(name, generator, crown):
    search = (getattr(generator, "_GenerationSearch", None) or generator._Search)(**small(**_VARIANTS[name]))
    _assert_screen_matches_pre(search, search.members)


def test_screen_is_bit_identical_to_pre_on_a_production_build():
    search = candidate._GenerationSearch(**synthetic_league.build(seed=7))
    _assert_screen_matches_pre(search, search.members[:3])


def _assert_screen_matches_pre(search, members):
    """The screen pushes exactly the focal pairs and windowed canonical
    expansions ``can_clear`` admits, in enumeration order, with ``pre``'s bits."""
    with search.ts._cfg_override(search.config), search.ts.stud_tax_override("market"):
        bounds = fp._Bounds(search)
        assert bounds.envelope
        for index, member in enumerate(members):
            m = fp._Member(search, bounds, member)
            screened = []
            m.screen(index, screened)
            universe = [(g, r) for g0 in m.give_pool for r0 in m.receive_pool
                        for g, r in [((g0,), (r0,)), *m.expansions((g0,), (r0,), canonical=True)]]
            kept = [(g, r) for g, r in universe if m.can_clear(g, r)]
            assert len(kept) < len(universe)
            expected = [(-m.pre(g, r)[0], tie, index, g, r, m.pre(g, r)[1][1])
                        for tie, (g, r) in enumerate(kept)]
            assert [(e[0], e[1], e[3], *fp._screened_package(e), e[7:]) for e in screened] == expected


# ------------------------------------------------------------ deferred proofs

_CACHED_PROOF_FIELDS = {"_market_terms", "model_identity", "selection_coverage", "_effective_floor_scalar"}


@pytest.mark.parametrize("generator", [bilateral, candidate])
@pytest.mark.parametrize("build", _AUDIT_BUILDS)
def test_every_eligible_proof_is_the_generators_and_ordering_reads_its_decode(generator, build, crown):
    # Exhaustive: verify the whole universe, then for EVERY eligible candidate
    # the proof a take would hand out is the full generator's (type, bytes,
    # fields, __dict__ bar cached properties) and the dict used for quality,
    # decoration and ranking equals json.loads of those bytes.
    full, _ = generator.generate_bilateral_trades(**small(**build))
    expected = {signature(c): c.owner_evaluation for c in full}
    resumable = fp.PageSearch(generator=generator, **small(**build))
    page, report = resumable.take(100_000)
    assert report.as_dict()["complete"] and len(page) == len(full) > 20
    held = {}
    for _, card, data in resumable.eligible.values():
        proof = card.owner_evaluation.final()
        held[signature(card)] = proof
        reference = expected[signature(card)]
        assert type(proof) is owner.OwnerDecisionContext
        assert proof.snapshot_json == reference.snapshot_json
        assert data == json.loads(proof.snapshot_json)
        assert proof == reference
        assert ({k: v for k, v in vars(proof).items() if k not in _CACHED_PROOF_FIELDS}
                == {k: v for k, v in vars(reference).items() if k not in _CACHED_PROOF_FIELDS})
    assert set(held) == set(expected)
    for card in page:
        assert card.owner_evaluation is held[signature(card)]


# ------------------------------------------------------------------- lineup memo

def _memo_search(**overrides):
    search = bilateral._Search(**small(seed=4, players_per_team=12, **overrides))
    memo = fp._LineupMemo(cap=10_000)
    memo.install(search)
    return search, memo


def _incumbent_lineup(search, roster, team):
    return owner._Search._lineup(search, roster, team)


def test_lineup_memo_equals_the_incumbent_and_keys_every_input():
    search, memo = _memo_search()
    team = search.teams[search.user_id]
    roster = team["roster"]
    starters = sorted((pid for pid in roster if pid in search._lineup_assets),
                      key=lambda pid: -search._lineup_assets[pid].value)
    top = starters[0]
    baseline = search._lineup(roster, team)
    assert baseline == _incumbent_lineup(search, roster, team) and memo.misses == 1
    assert search._lineup(roster, team) == baseline and memo.hits == 1

    def changed(label):
        result = search._lineup(roster, team)
        assert result == _incumbent_lineup(search, roster, team), label
        assert result != baseline, label + " did not change the lineup: the check would be vacuous"
        return result

    # Team inputs (slots, native bounds, inactive set), changed in place on the
    # same search, then restored.
    original = dict(team)
    slots = list(original["slots"])
    slots.remove("WR")
    team["slots"] = tuple(slots)
    changed("slots")
    team["slots"] = original["slots"] + ("FLEX", "SUPER_FLEX")
    changed("flex slots")
    team["slots"] = original["slots"]
    team["native_bounds"] = (("QB", 1, 1), ("RB", 1, 3), ("WR", 2, 4), ("TE", 0, 2))
    changed("native bounds")
    team["native_bounds"] = original["native_bounds"]
    team["inactive"] = original["inactive"] | {top}
    changed("inactive")
    team["inactive"] = original["inactive"]
    # Asset inputs are fixed for a search's life (built in __init__), so a
    # changed value or position is another search's input: reinstall, keeping
    # the same process memo, whose stored entries must not answer for it.
    asset = search._lineup_assets[top]
    search._lineup_assets[top] = Asset(top, asset.positions, asset.value * .5)
    memo.install(search)
    changed("lineup value")
    other = next(p for p in ("QB", "RB", "WR", "TE") if p not in asset.positions)
    search._lineup_assets[top] = Asset(top, frozenset([other]), asset.value)
    search._positions[top] = other
    memo.install(search)
    changed("eligible position and _position")
    search._lineup_assets[top] = asset
    memo.install(search)
    changed("_position alone")
    search._positions.pop(top)  # re-derived from the player on next use
    memo.install(search)
    roster = original["roster"] - {top}
    changed("roster membership")
    roster = original["roster"]
    hits = memo.hits
    assert search._lineup(roster, team) == baseline and memo.hits == hits + 1


def test_lineup_memo_hands_out_detached_results():
    search, memo = _memo_search()
    team = search.teams[search.user_id]
    first = search._lineup(team["roster"], team)
    expected = dict(first)
    first["QB"] = -1.0
    first.pop("RB")
    again = search._lineup(team["roster"], team)
    assert memo.hits == 1 and again == expected and again is not first
    assert list(again) == list(owner._POSITIONS)


def test_lineup_memo_evicts_least_recently_used_at_its_cap():
    search = bilateral._Search(**small(seed=4, players_per_team=12))
    memo = fp._LineupMemo(cap=3)
    memo.install(search)
    team = search.teams[search.user_id]
    rosters = [team["roster"] - {pid} for pid in sorted(team["roster"] & set(search._lineup_assets))[:5]]
    for roster in rosters[:3]:
        search._lineup(roster, team)
    search._lineup(rosters[0], team)  # refresh: rosters[1] is now the oldest
    search._lineup(rosters[3], team)
    assert len(memo) == 3 and (memo.hits, memo.misses) == (1, 4)
    search._lineup(rosters[0], team)
    assert memo.hits == 2
    search._lineup(rosters[1], team)
    assert memo.misses == 5


def test_lineup_memo_leaves_overridden_lineups_alone():
    class Override(bilateral._Search):
        def _lineup(self, roster, team):
            return super()._lineup(roster, team)
    search = Override(**small())
    fp._LineupMemo(cap=10).install(search)
    assert "_lineup" not in vars(search)


def test_a_finished_search_is_freed_without_the_cycle_collector(monkeypatch):
    # The memo's shadow lives on the search; it must not make a reference cycle
    # that keeps every finished search alive until a full collection.
    import gc
    import weakref
    created, init = [], bilateral._Search.__init__
    def tracking(self, **kwargs):
        init(self, **kwargs)
        created.append(weakref.ref(self))
    monkeypatch.setattr(bilateral._Search, "__init__", tracking)
    enabled = gc.isenabled()
    gc.disable()
    try:
        fp.first_page(k=5, generator=bilateral, **small())
        assert created and created[0]() is None
    finally:
        if enabled:
            gc.enable()


def test_concurrent_searches_share_the_memo_and_match_serial_results(monkeypatch):
    leagues = [dict(seed=seed, teams=6, players_per_team=10, ranked_opponents=3) for seed in (21, 22, 23, 24)]
    def search(build):
        page, report = fp.first_page(k=10, generator=bilateral, **small(**build))
        return [(identity(c), c.owner_evaluation.snapshot_json) for c in page]
    with monkeypatch.context() as patch:
        patch.setattr(fp._LineupMemo, "install", lambda self, search: None)
        unmemoised = [search(build) for build in leagues]
    fp._LINEUP_MEMO.clear()
    serial = [search(build) for build in leagues]
    assert serial == unmemoised
    fp._LINEUP_MEMO.clear()
    results, errors = {}, []
    def worker(offset):
        try:
            for round_ in range(3):
                for i in range(len(leagues)):
                    j = (i + offset + round_) % len(leagues)
                    results.setdefault(j, []).append(search(leagues[j]))
        except BaseException as exc:  # surfaced below
            errors.append(exc)
    threads = [threading.Thread(target=worker, args=(offset,)) for offset in range(4)]
    interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-5)  # interleave threads inside each search, not between searches
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sys.setswitchinterval(interval)
    assert not errors
    assert fp._LINEUP_MEMO.hits > 0
    for j, runs in results.items():
        assert len(runs) == 12 and all(run == serial[j] for run in runs), j


def _incumbent_coordinates(generator, kwargs):
    """Probes and the incumbent's answers: every (pid, elo) a plain search
    asked for, plus those Elo values under other positions' pids (so a key
    missing position or format would collide)."""
    plain = (getattr(generator, "_GenerationSearch", None) or generator._Search)(**kwargs)
    probes = set(plain._tier_coordinates)
    by_position = {}
    for pid in plain.market:
        by_position.setdefault(plain._position(pid), pid)
    elos = sorted({elo for _, elo in probes})[::7]
    probes |= {(pid, elo) for pid in by_position.values() for elo in elos}
    assert len(probes) > 100
    return {probe: bilateral._Search._coordinate(plain, *probe) for probe in probes}


def _shifted_bands(scoring_format, position, shift):
    bands = {tier: dict(band) for tier, band in ranking_service.TIER_CONFIG[scoring_format][position].items()}
    for band in bands.values():
        band["min"], band["max"] = band["min"] + shift, band["max"] + shift
    return bands


@pytest.mark.parametrize("generator", [bilateral, candidate])
def test_coordinate_memo_equals_the_incumbent_across_formats_and_tier_bands(generator, monkeypatch):
    fp._COORDINATE_MEMO.clear()
    search_class = fp._private_search(getattr(generator, "_GenerationSearch", None) or generator._Search)
    # The shipped formats share bands; make them differ so the format matters.
    monkeypatch.setitem(ranking_service.TIER_CONFIG["sf_tep"], "RB", _shifted_bands("sf_tep", "RB", 53.0))
    for scoring_format in ("1qb_ppr", "sf_tep", "1qb_ppr"):
        kwargs = small(seed=6, scoring_format=scoring_format)
        expected = _incumbent_coordinates(generator, kwargs)
        private = search_class(**kwargs)
        assert {probe: private._coordinate(*probe) for probe in expected} == expected, scoring_format
    # Bands edited in place (as a test or a hot fix would) select a new table.
    kwargs = small(seed=6)
    before = _incumbent_coordinates(generator, kwargs)
    monkeypatch.setitem(ranking_service.TIER_CONFIG["1qb_ppr"], "RB", _shifted_bands("1qb_ppr", "RB", 37.0))
    after = _incumbent_coordinates(generator, kwargs)
    private = search_class(**kwargs)
    assert {probe: private._coordinate(*probe) for probe in after} == after != before


def test_coordinate_memo_drops_its_tables_past_the_cap():
    memo = fp._CoordinateMemo(cap=3)
    table = memo.table("bands")
    for i in range(4):
        table[i] = i
        memo.added()
    assert memo.table("bands") is not table and memo.table("bands") == {}


# ------------------------------------------------------ resumable search and stop

@pytest.mark.parametrize("generator", [bilateral, candidate])
@pytest.mark.parametrize("takes", [(5, 30), (30, 5), (1, 1, 12)])
@pytest.mark.parametrize("name", ["default", "seed_9_more_ranked", "loose_floor"])
def test_each_take_equals_the_one_shot_call(generator, takes, name):
    def kwargs():
        return small(**_VARIANTS[name])
    resumable = fp.PageSearch(generator=generator, **kwargs())
    for n in takes:
        page, report = resumable.take(n)
        report = report.as_dict()
        expected, expected_report = run(n, generator, kwargs)
        assert [identity(c) for c in page] == [identity(c) for c in expected]
        assert [c.owner_evaluation.snapshot_json for c in page] == [
            c.owner_evaluation.snapshot_json for c in expected]
        assert [c.composite_score for c in page] == [c.composite_score for c in expected]
        assert report["complete"] == expected_report["complete"] and report["returned"] == len(page)
        assert report["verified"] >= expected_report["verified"]
    assert report["takes"] == len(takes)


def test_takes_extend_for_bilateral_1_and_report_reordering_for_revision_2():
    # bilateral-1: the first n outputs depend only on the first n + 31 sorted
    # cards, so a later take extends an earlier one. Revision 2's term
    # precedence can reorder: seed 11 is a production build where it does.
    resumable = fp.PageSearch(generator=bilateral, **synthetic_league.build(seed=11))
    first, _ = resumable.take(5)
    page, report = resumable.take(30)
    assert [identity(c) for c in page[:5]] == [identity(c) for c in first]
    assert report.as_dict()["prefix_stable"] is True
    resumable = fp.PageSearch(generator=candidate, **synthetic_league.build(seed=11))
    first, report = resumable.take(5)
    assert report.as_dict()["prefix_stable"] is True
    page, report = resumable.take(30)
    assert [identity(c) for c in page[:5]] != [identity(c) for c in first]
    assert report.as_dict()["prefix_stable"] is False
    one_shot, _ = fp.first_page(k=30, generator=candidate, **synthetic_league.build(seed=11))
    assert [identity(c) for c in page] == [identity(c) for c in one_shot]


def test_a_later_take_never_alters_cards_already_handed_out():
    resumable = fp.PageSearch(generator=candidate, **small(seed=9, ranked_opponents=4))
    first, _ = resumable.take(5)
    handed_out = [(c.trade_id, c.composite_score, c.owner_evaluation.snapshot_json) for c in first]
    page, _ = resumable.take(30)
    assert [(c.trade_id, c.composite_score, c.owner_evaluation.snapshot_json) for c in first] == handed_out
    by_signature = {signature(c): c.trade_id for c in page}
    assert all(by_signature[signature(c)] == c.trade_id for c in first)  # same offer, same id
    proof = page[0].owner_evaluation
    assert proof.as_dict() == proof.as_dict() and proof.as_dict() is not proof.as_dict()
    assert "as_dict" not in vars(proof)


def test_page_search_refuses_unsupported_requests():
    with pytest.raises(ValueError):
        fp.PageSearch(**small(pinned_give_players=["p00_00"]))


@pytest.mark.parametrize("generator, seed", [(bilateral, 11), (bilateral, 23), (candidate, 7), (candidate, 23)])
def test_stop_holds_exactly_the_full_generators_top_k_plus_lookahead(generator, seed):
    # The stop proof's direct check: the verified prefix the ranker sees is
    # the full survivor list's top k + 31 by quality, not just a prefix whose
    # ranked head happens to match.
    resumable = fp.PageSearch(generator=generator, **synthetic_league.build(seed=seed))
    _, report = resumable.take(30)
    assert report.as_dict()["complete"]
    held = [identity(card) for card, _ in resumable.prefix(30)]
    expected = [identity(c) for c in sorted(full_solve(generator, seed), key=fp._quality)[:30 + fp._LOOKAHEAD]]
    assert len(held) == 61 and held == expected
