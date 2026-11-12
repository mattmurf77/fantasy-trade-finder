"""Fit block without league position ranks (flag trade.fit_position_ranks).

Operator feedback on TestFlight 1.22.0 (186), 2026-11-11: the position-rank
"value change" content above the card is disorienting and adds little beside
the starting-lineup change below the value bar; remove it. Server-side, so
installed builds 184-186 stop showing it without an app update.

Covers:
- registration: default False in code, false in config/features.json and the
  three flag fixtures, documented in docs/config-reference.md;
- flag off, over a corpus (every give/receive shape of the small league in
  test_fit_block_v3 x viewer plans/needs x roster reads x counterparty depth,
  and the revision-2 cards of the owner league and of the 12-team synthetic
  league through trade_card_to_dict): no `positions` row, no `ranks` row, no
  rank-fact lead (holds/shifts/flat/none) on any card;
- tags and reason leads unchanged: the flag-off block is exactly the flag-on
  block with its rank-fact teams removed and `ranks`/`positions` emptied;
- omission: a team with no reason lead is left out (its tag with it), and a
  card where neither team has one gets no block;
- the client-safe shape: every team passes build 184-186's normalizer
  (mobile/src/api/trades.ts normalizeTradeCard, mirrored below) with its tag
  intact, and carries nothing the card would render as a rank;
- the job context: flag off skips the position-value walk
  (`_power_value_inputs`, `compute_power_rankings`) and keeps the same roster
  reads; flag on builds the v22 context;
- flag on is byte-identical to the payload before this flag: the corpus is
  compared with fixtures/fit_block_v22_golden.json, generated from origin/main
  fa83f57b (DECK_PIPELINE_VERSION 22) by `_golden_corpus` below.
"""
import copy
import hashlib
import json
from functools import lru_cache
from pathlib import Path

import pytest

from backend import feature_flags, power_rankings, server, trade_narrative as tn, trade_service as ts
from backend import trade_gen_bilateral_candidate as rev2
from backend.eval import synthetic_league
from backend.tests.test_fit_block_v3 import (P, ROSTERS, VALUE, card, context, noise_league, owner_league,
                                             proof, team)

REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "backend/tests/fixtures/fit_block_v22_golden.json"
RANK_FACT = ("holds", "shifts", "flat", "none")
REASON = ("plan_rebuild", "plan_win_now", "need")


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(ts, "_cfg", dict(ts._DEFAULT_CFG))
    monkeypatch.setattr(feature_flags, "_flags_cache", dict(feature_flags.DEFAULT_FLAGS))


def flags(on_ranks, cache=None):
    cache = feature_flags._flags_cache if cache is None else cache
    cache["trade.fit_first_copy"] = True
    cache["trade.fit_position_ranks"] = on_ranks


# ── the corpus (shared with the golden generator: keep it flag-agnostic) ───

GIVES = (["vqb"], ["vwr"], ["vrb"], ["vte"], ["vpk"], ["vwr", "vpk"], ["vrb", "vte"])
RECEIVES = (["oqb"], ["owr"], ["orb"], ["ote"], ["opk"], ["orb", "opk"], ["owr", "ote"])
BIG = {"QB": 1500, "RB": 2500, "WR": 3000, "TE": 900}


def viewers():
    return (team(), team("rebuilder", benefits=["outlook"]),
            team("rebuilder", "inferred", ["future_pick_capital"]),
            team("contender", benefits=["outlook"]), team("contender", "inferred", ["outlook"]),
            team("contender", delta=BIG), team("championship", "declared", ["market_terms"]))


READS = ({}, {"opp": "rebuilder"}, {"opp": "contender"})


def counterparties():
    return (team(), team("contender", "declared", delta=BIG))


#: The noise-bar league of test_fit_block_v3 (a WR for a pick): 10 holds both
#: ranks (holds.*), 147.4 moves them under the bar (flat.*), 147.5 over it.
NOISE_SENT = (10, 147.4, 147.5)


def small_cases():
    """(name, proof, card, players, league, reads) for every shape of the
    small league and of the noise-bar league; `league` is None (the small
    league) or the WR value sent in the noise-bar league."""
    for gi, give in enumerate(GIVES):
        for ri, receive in enumerate(RECEIVES):
            for vi, viewer in enumerate(viewers()):
                for di, reads in enumerate(READS):
                    for ci, cp in enumerate(counterparties()):
                        yield (f"{gi}.{ri}.{vi}.{di}.{ci}", proof(give, receive, viewer=viewer, counterparty=cp),
                               card(give, receive), P, None, reads)
    for sent in NOISE_SENT:
        players = noise_league(sent)[0]
        for vi, viewer in enumerate(viewers()):
            for di, reads in enumerate(READS):
                prf = {"generator": "owner_v2_bilateral", "generator_version": "owner-v2-bilateral-2",
                       "eligible": True, "assets": [{"id": "mw2", "market": sent}, {"id": "pk", "market": 500}],
                       "viewer": viewer, "counterparty": team()}
                yield f"noise{sent}.{vi}.{di}", prf, card(["mw2"], ["pk"]), players, sent, reads


def case_context(league, reads, ranks=True):
    """The job's context for a case: the full one (flag on) or, with ranks
    off, the reads-only one the job builds with the flag off."""
    if not ranks:
        return off_context(reads)
    if league is None:
        return context(reads=reads)
    players, values, rosters = noise_league(league)
    return context(rosters, values, players, reads=reads)


def synthetic_owner_league(seed, viewer_outlook):
    kwargs = synthetic_league.build(seed=seed, viewer_outlook=viewer_outlook)
    owner_context = {"user_id": "me", "players": kwargs["players"], "league": kwargs["league"],
                     "user_roster": kwargs["user_roster"], "scoring_format": "1qb_ppr",
                     "config": dict(ts._cfg), "inferred_outlooks": {}, "manager_preferences": {}}
    return kwargs, owner_context, kwargs["seed_elo"]


LEAGUES = {"owner": owner_league,
           "synthetic7_contender": lambda: synthetic_owner_league(7, "contender"),
           "synthetic11_rebuilder": lambda: synthetic_owner_league(11, "rebuilder")}


@lru_cache(maxsize=None)
def league_cards(name):
    """The league's revision-2 cards under default flags and config (cached:
    the 12-team solve is the slow part)."""
    saved_cfg, saved_flags = ts._cfg, feature_flags._flags_cache
    ts._cfg, feature_flags._flags_cache = dict(ts._DEFAULT_CFG), dict(feature_flags.DEFAULT_FLAGS)
    try:
        kwargs, owner_context, seed = LEAGUES[name]()
        cards, _ = rev2.generate_bilateral_trades(**kwargs)
        return cards, kwargs["players"], owner_context, seed
    finally:
        ts._cfg, feature_flags._flags_cache = saved_cfg, saved_flags


def league_payloads(name, monkeypatch):
    """trade_card_to_dict for every card of the league, with the job's context
    built exactly as the worker builds it under the current flags."""
    cards, players, owner_context, seed = league_cards(name)
    monkeypatch.setattr(server, "_get_universal_pool", lambda fmt: (list(players.values()), dict(seed)))
    ctx = server._fit_league_context(owner_context, None)
    out = []
    for c in cards:
        c = copy.copy(c)
        c.fit_context = ctx
        out.append(server.trade_card_to_dict(c, players))
    return out


def _sha(value):
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()


def _golden_corpus(monkeypatch, leagues=False):
    """Flag-on output for the corpus, as digests plus counts (the full corpus
    is ~6 MB). Run against origin/main fa83f57b to produce
    fixtures/fit_block_v22_golden.json; the test runs it on HEAD. The
    committed golden is the small league only: the league payloads also
    depend on the generator, which other work changes, so they were compared
    with fa83f57b once, at this change (leagues=True), not pinned."""
    small = [tn.fit_block(prf, crd, players, case_context(league, reads))
             for _, prf, crd, players, league, reads in small_cases()]
    out = {"small": {"cases": len(small), "blocks": sum(b is not None for b in small),
                     "sha256": _sha(small)}}
    if not leagues:
        return out
    out["leagues"] = {}
    for name in LEAGUES:
        payloads = league_payloads(name, monkeypatch)
        blocks = [p.get("fit_block") for p in payloads]
        out["leagues"][name] = {
            "cards": len(payloads), "blocks": sum(b is not None for b in blocks),
            "fit_blocks_sha256": _sha(blocks),
            # Per run: expires_at (the wall clock) and trade_id (a uuid).
            "payloads_sha256": _sha([{k: v for k, v in p.items() if k not in ("expires_at", "trade_id")}
                                     for p in payloads])}
    return out


# ── client mirror: build 184-186 normalizeTradeCard (mobile/src/api/trades.ts:193-226) ──

def client_teams(block):
    """The teams the installed app keeps (trades.ts:194-199 filter, :200-224 map)."""
    if not isinstance(block, dict) or block.get("v") != "fit-2" or not isinstance(block.get("teams"), list):
        return []
    kept = []
    for t in block["teams"]:
        lead = t.get("lead") or {}
        if t.get("side") not in ("them", "you") or not isinstance(lead.get("code"), str) \
                or not (isinstance(lead.get("text"), str) and len(lead["text"]) > 0):
            continue
        tag = t.get("tag") or {}
        row = {"side": t["side"], "lead": lead}
        if isinstance(tag.get("text"), str) and tag["text"] and tag.get("source") in ("declared", "roster"):
            row["tag"] = tag
        valid = lambda rows: [r for r in rows if r.get("pos") in ("QB", "RB", "WR", "TE")
                              and isinstance(r.get("before"), int) and r["before"] >= 1
                              and isinstance(r.get("after"), int) and r["after"] >= 1] \
            if isinstance(rows, list) else []
        row["ranks"] = valid(t.get("ranks"))
        row["positions"] = valid(t.get("positions"))[:4]
        kept.append(row)
    return kept


def assert_clean(block):
    """No rank content, every team kept whole by the installed client."""
    if block is None:
        return
    assert block["v"] == "fit-2" and 1 <= len(block["teams"]) <= 2
    assert [t["side"] for t in block["teams"]] in (["them", "you"], ["them"], ["you"])
    for t in block["teams"]:
        assert set(t) <= {"side", "tag", "lead", "ranks", "positions"}
        assert t["ranks"] == [] and t["positions"] == []
        assert t["lead"]["code"].split(".")[0] in REASON, t["lead"]
        assert t["lead"]["text"] and "rank" not in t["lead"]["text"].lower()
    # The client keeps every team, its tag included (no dropped tag), and
    # has no rank row or table to draw (TradeCard.tsx:327 fitTable false,
    # :749/:769 no FitRankRows and no fitRanksText, :69 lead shown).
    assert client_teams(block) == [{**t, "ranks": [], "positions": []} for t in block["teams"]]


def strip_ranks(block):
    """The flag-on block with rank content removed, as the flag-off block must be."""
    if block is None:
        return None
    teams = [{**t, "ranks": [], "positions": []} for t in block["teams"]
             if t["lead"]["code"].split(".")[0] not in RANK_FACT]
    return {"v": block["v"], "teams": teams} if teams else None


def off_context(reads):
    """The context the job builds with the flag off: roster reads only."""
    return tn.FitLeagueContext(viewer_id="me", teams=[], medians={}, rosters={}, reads=reads,
                               position_ranks=False)


# ── registration ───────────────────────────────────────────────────────────

def test_flag_registered_default_off_everywhere():
    assert "trade.fit_position_ranks" in feature_flags.FLAG_KEYS
    assert feature_flags.DEFAULT_FLAGS["trade.fit_position_ranks"] is False
    assert json.loads((REPO / "config/features.json").read_text())["trade.fit_position_ranks"] is False
    for name in ("release", "profiles-on", "onboarding-v2"):
        fixture = json.loads((REPO / f"backend/tests/fixtures/flags/{name}.json").read_text())
        assert fixture["trade.fit_position_ranks"] is False, name
    assert "`trade.fit_position_ranks`" in (REPO / "docs/config-reference.md").read_text()


# ── flag off: the composer ─────────────────────────────────────────────────

def test_flag_off_small_league_has_no_rank_content_and_keeps_tags_and_reasons():
    shown, codes = 0, set()
    for name, prf, crd, players, league, reads in small_cases():
        on = tn.fit_block(prf, crd, players, case_context(league, reads))
        off = tn.fit_block(prf, crd, players, case_context(league, reads, ranks=False))
        if league is None:
            # The full-teams context with the flag off says the same: the
            # flag, not the missing walk, is what removes the ranks.
            assert off == tn.fit_block(prf, crd, players, tn.FitLeagueContext(
                viewer_id="me", teams=_teams(), medians=_medians(),
                rosters=_ids(), reads=reads, position_ranks=False)), name
        assert_clean(off)
        assert off == strip_ranks(on), name
        shown += off is not None
        codes |= {t["lead"]["code"] for t in (on or {"teams": []})["teams"]}
    assert shown > 100
    # The corpus reaches every lead code there is, so every rank-fact family
    # is seen removed and every reason family seen kept.
    assert codes == set(tn.FIT_TEMPLATES), set(tn.FIT_TEMPLATES) - codes


def _teams():
    seed = {p: ts.value_to_elo(v) for p, v in VALUE.items()}
    return power_rankings.compute_power_rankings(
        [{"user_id": u, "player_ids": r} for u, r in _ids().items()], seed, P)


def _medians():
    return server._position_medians(_teams())


def _ids():
    return {u: [p for p in r if P[p].position != "PICK"] for u, r in ROSTERS.items()}


def test_a_team_without_a_reason_is_left_out_with_its_tag():
    # Them: rebuild read (a tag) but no rebuild-shaped gain; you: a declared
    # rebuild plan. Flag on, them reads "Up at WR, ..."; flag off, them is gone.
    prf, crd = proof(["vrb"], ["opk"], viewer=team("rebuilder", benefits=["outlook"])), card(["vrb"], ["opk"])
    on = tn.fit_block(prf, crd, P, context(reads={"opp": "rebuilder"}))
    assert [t["side"] for t in on["teams"]] == ["them", "you"]
    assert on["teams"][0]["lead"]["code"].split(".")[0] in RANK_FACT and "tag" in on["teams"][0]
    off = tn.fit_block(prf, crd, P, off_context({"opp": "rebuilder"}))
    assert off == {"v": "fit-2", "teams": [{
        "side": "you", "lead": {"code": "plan_rebuild.you", "text": "Rebuilding: adds the 2028 2nd"},
        "ranks": [], "positions": [],
        "tag": {"code": "rebuilder", "source": "declared", "text": "Rebuilding"}}]}


def test_no_reason_on_either_side_means_no_block():
    # Flag on this card shows rank facts for both teams; off it has nothing.
    prf, crd = proof(["vwr"], ["orb"]), card(["vwr"], ["orb"])
    assert tn.fit_block(prf, crd, P, context()) is not None
    assert tn.fit_block(prf, crd, P, off_context({})) is None


def test_both_teams_with_reasons_keep_both_rows_and_tags():
    prf = proof(["vwr", "vpk"], ["owr"], viewer=team("contender", benefits=["outlook"]))
    off = tn.fit_block(prf, card(["vwr", "vpk"], ["owr"]), P, off_context({"opp": "rebuilder"}))
    assert [(t["side"], t["lead"]["code"], t["tag"]["text"]) for t in off["teams"]] == [
        ("them", "plan_rebuild.them", "Looks rebuilding"), ("you", "plan_win_now.you", "Contending")]
    assert_clean(off)


# ── flag off: the job and the served payload ───────────────────────────────

@pytest.mark.parametrize("name", list(LEAGUES))
def test_flag_off_served_cards_carry_no_rank_content(name, monkeypatch):
    flags(True)
    on = league_payloads(name, monkeypatch)
    flags(False)
    off = league_payloads(name, monkeypatch)
    assert len(on) == len(off) > 0
    for a, b in zip(on, off):
        assert_clean(b.get("fit_block"))
        assert b.get("fit_block") == strip_ranks(a.get("fit_block"))
        # Nothing else on the card moves.
        rest = lambda p: {k: v for k, v in p.items() if k != "fit_block"}
        assert json.dumps(rest(a)) == json.dumps(rest(b))


def test_flag_off_context_skips_the_walk_and_keeps_the_reads(monkeypatch):
    cards, players, owner_context, seed = league_cards("owner")
    monkeypatch.setattr(server, "_get_universal_pool", lambda fmt: (list(players.values()), dict(seed)))
    flags(True)
    on = server._fit_league_context(owner_context, None)
    walks, inputs = [], []
    real_walk, real_inputs = power_rankings.compute_power_rankings, server._power_value_inputs
    monkeypatch.setattr(power_rankings, "compute_power_rankings",
                        lambda *a, **k: walks.append(1) or real_walk(*a, **k))
    monkeypatch.setattr(server, "_power_value_inputs", lambda *a, **k: inputs.append(1) or real_inputs(*a, **k))
    flags(False)
    off = server._fit_league_context(owner_context, None)
    assert not walks and not inputs
    assert off.reads == on.reads and off.position_ranks is False and on.position_ranks is True
    assert off.values == {} and off.valued == 0 and off.owner == {}
    flags(True)
    again = server._fit_league_context(owner_context, None)
    assert walks == [1] and inputs == [1] and again.values == on.values


# ── flag on: byte-identical to v22 ─────────────────────────────────────────

def test_flag_on_is_byte_identical_to_the_v22_golden(monkeypatch):
    flags(True)
    golden = json.loads(GOLDEN.read_text())
    assert _golden_corpus(monkeypatch) == golden
    assert golden["small"]["cases"] == 2121 and golden["small"]["blocks"] > 1000


# ── the real worker (owner route harness, revision 2) ──────────────────────

from backend.tests.test_owner_generator_routes import harness, owner_harness  # noqa: E402,F401
from backend.tests.test_trade_fast_deck import revised, run, spy  # noqa: E402,F401


def test_flag_off_job_builds_the_reads_once_and_never_walks_the_league(revised, monkeypatch):
    flags(False)
    contexts = spy(monkeypatch, server, "_fit_league_context")
    league_walks = spy(monkeypatch, power_rankings, "compute_power_rankings")
    value_reads = spy(monkeypatch, server, "_power_value_inputs")
    composed = spy(monkeypatch, tn, "fit_block")
    job = run(monkeypatch)
    assert job["cards"]
    assert len(contexts) == 1 and contexts[0] is not None
    assert not league_walks and not value_reads
    assert len(composed) == len(job["cards"])
    for c in job["cards"]:
        assert_clean(c.get("fit_block"))
