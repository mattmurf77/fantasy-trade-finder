"""Realistic decks for the evidence-pack golden (backend/eval/evidence_pack.py).

Both sources go through the REAL impression writer
(server._log_deck_signal_impressions), so every features_json key and logged
column has its production shape, and are read back through
backend.eval.data.load_decks:

  harness_decks()  full trade jobs via bakeoff_harness.run_capture under three
                   flag mixes. Real, but tiny (1 to 4 cards per deck).
  writer_deck(n)   n synthetic TradeCards handed straight to the writer with
                   bake-off attribution, fatigue, taste and telemetry stamps
                   on: deck-scale goldens and byte measurements.

Each deck is (LoggedDeck, cards): cards are card_dict(c) plus the
deck_impressions attribution columns the pack carries (ATTRIBUTION_COLUMNS).
Ghost rows are dropped, because ghosts are never packed (C5).

Hermetic: DynastyProcess values come from a temp file (FTF_DP_VALUES_FILE),
which also turns KTC off, so nothing here makes a network call. That includes
importing backend.server, which fetches DP and KTC at import (server.py:358);
the env patch is scoped to the import and the runs, never left behind.
"""

import os
import random
import tempfile
from contextlib import contextmanager
from unittest.mock import patch

from sqlalchemy import create_engine, select


@contextmanager
def hermetic_values():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "dp-values.csv")
        with open(path, "w") as fh:
            fh.write("player,pos,value_1qb,value_2qb\n"
                     "Test Stud,WR,9000,9100\nTest Guy,QB,4000,8000\n")
        with patch.dict(os.environ, {"FTF_DP_VALUES_FILE": path}):
            yield


with hermetic_values():
    import backend.server as server
    from backend.tests.support import bakeoff_harness as H

import backend.bakeoff_runner as bo  # noqa: E402
import backend.database as db_module  # noqa: E402
from backend.database import deck_impressions_table, metadata  # noqa: E402
from backend.eval.data import card_dict, load_decks  # noqa: E402
from backend.ranking_service import Player  # noqa: E402
from backend.trade_service import TradeCard  # noqa: E402

ATTRIBUTION_COLUMNS = (
    "policy_version", "candidate_set_id", "candidate_set_size",
    "model_arm", "arm_rank", "group_key", "group_rank", "lane_slot",
    "fairness_threshold", "centerpiece_id",
)
POLICY_VERSION = "v3+ts.ts2.div.fat.rr.taste.expl.fs.ghost@r1"


def decks_with_attribution(engine):
    """[(LoggedDeck, cards)] for every deck in `engine`, ghosts dropped."""
    with engine.connect() as conn:
        rows = {r.impression_id: r for r in conn.execute(select(deck_impressions_table))}
    out = []
    for deck in load_decks(engine=engine):
        deck.cards = [c for c in deck.cards if not rows[c.impression_id].is_ghost]
        cards = []
        for c in deck.cards:
            d = card_dict(c)
            d.update({k: getattr(rows[c.impression_id], k) for k in ATTRIBUTION_COLUMNS})
            cards.append(d)
        out.append((deck, cards))
    return out


def harness_decks():
    configs = {
        "flags_default": [],
        "telemetry_taste_fatigue": [
            patch.object(bo, "bakeoff_enabled", lambda: False),
            patch.object(server, "_suggestion_telemetry_enabled", lambda: True),
            patch.object(server, "_deck_taste_enabled", lambda: True),
            patch.object(server, "_deck_fatigue_enabled", lambda: True),
        ],
        "bakeoff_interleaved_taste": [
            patch.object(bo, "bakeoff_enabled", lambda: True),
            patch.object(bo, "_cfg", lambda k, d: float(
                {"bakeoff_serve_interleaved": 1.0}.get(k, d))),
            patch.object(server, "_suggestion_telemetry_enabled", lambda: True),
            patch.object(server, "_deck_taste_enabled", lambda: True),
            patch.object(server, "_deck_fatigue_enabled", lambda: True),
        ],
    }
    out = {}
    with hermetic_values():
        for name, extra in configs.items():
            _capture, _job, engine = H.run_capture(extra_patches=extra)
            out[name] = decks_with_attribution(engine)
    return out


class _FakeBakeoffRun:
    """The four bakeoff_run reads the writer makes, from a seeded draw."""

    def __init__(self, rng, cards):
        self._attr, self._group, self._agree = {}, {}, {}
        arm_ranks, group_ranks = {}, {}
        for c in cards:
            arm = None if c.likes_you else rng.choice(["current", "current", "challenger", "gen_v2"])
            if arm:
                self._attr[id(c)] = (arm, arm_ranks.setdefault(arm, 0))
                arm_ranks[arm] += 1
                key = f"{arm}_{c.basis}"
                self._group[id(c)] = (key, group_ranks.setdefault(key, 0),
                                      rng.choice(["value", "outlook"]))
                group_ranks[key] += 1
            if rng.random() < 0.2:
                self._agree[id(c)] = ["challenger"]

    def attribution_for(self, card):
        return self._attr.get(id(card))

    def fairness_threshold_for(self, card):
        arm = (self._attr.get(id(card)) or (None,))[0]
        return {"current": 0.75, "challenger": 0.8}.get(arm)

    def group_for(self, card):
        return self._group.get(id(card))

    def trade_intent_for(self, card):
        return None

    def also_proposed_by(self, card):
        return self._agree.get(id(card))


def _pool(rng):
    players, seed = {}, {}
    for pos, count in (("QB", 40), ("RB", 70), ("WR", 90), ("TE", 35)):
        for i in range(count):
            pid = f"{pos.lower()}{i}"
            players[pid] = Player(id=pid, name=f"{pos} {i}", position=pos,
                                  team="T", age=rng.randint(21, 33))
            seed[pid] = round(rng.uniform(1300, 1900), 1)
    for year in (2027, 2028):
        for rnd, label in ((1, "1st"), (2, "2nd"), (3, "3rd")):
            pid = f"generic_pick_{rnd}_{year}"
            players[pid] = Player(id=pid, name=f"{year} {label}", position="PICK",
                                  team="PICK", age=0)
            seed[pid] = round(rng.uniform(1400, 1700), 1)
    return players, seed


def writer_deck(n, *, seed=0, taste=True, ranked=(37, "2026-10-19T12:00:00+00:00"),
                job_id="job-evpack", user_id="user_me", league_id="league_evpack"):
    """One served deck of n cards written by the real impression writer."""
    rng = random.Random(seed)
    players, seed_map = _pool(rng)
    ids = sorted(players)
    partners = [f"user_{i:02d}" for i in range(11)]
    cards, capture = [], {"propensity": {}, "final_key": {}}
    for i in range(n):
        give = rng.sample(ids, rng.choice([1, 1, 2, 2, 2, 3]))
        recv = rng.sample(ids, rng.choice([1, 1, 2, 2, 3]))
        if rng.random() < 0.01:
            give.append(f"unknown{i}")   # Sleeper null player: position "?"
        card = TradeCard(
            trade_id=f"t{i}", league_id=league_id, proposing_user_id=user_id,
            target_user_id=rng.choice(partners), target_username="opp",
            give_player_ids=give, receive_player_ids=recv,
            mismatch_score=round(rng.uniform(-40.0, 400.0), 2),
            fairness_score=round(rng.uniform(0.6, 1.0), 3),
            composite_score=rng.random(),
        )
        card.basis = rng.choice(["divergence", "consensus"])
        card.lane = rng.choice(["value", "outlook", "window", None])
        card.likes_you = rng.random() < 0.03
        card.relaxed = rng.random() < 0.1
        card.give_value = round(sum(rng.uniform(300, 5000) for _ in give), 1)
        card.receive_value = round(sum(rng.uniform(300, 5000) for _ in recv), 1)
        card.need_fit = round(rng.random(), 3)
        capture["propensity"][id(card)] = rng.uniform(0.5, 1.6)
        capture["final_key"][id(card)] = card.composite_score * capture["propensity"][id(card)]
        cards.append(card)

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    with patch.object(db_module, "engine", engine), \
            patch.object(server, "_deck_taste_enabled", lambda: taste), \
            patch.object(server, "_deck_fatigue_enabled", lambda: True), \
            patch.object(server, "load_board_state", lambda *a: ranked):
        server._log_deck_signal_impressions(
            user_id=user_id, league_id=league_id, job_id=job_id, cards=cards,
            players_dict=players, capture=capture, scoring_format="1qb_ppr",
            seed_map=seed_map, policy_version=POLICY_VERSION,
            bakeoff_run=_FakeBakeoffRun(rng, cards))
    [(deck, dicts)] = decks_with_attribution(engine)
    return deck, dicts
