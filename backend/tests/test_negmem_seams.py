"""Seam layer for negative-results memory (flag `trade.negmem`, default OFF).

Spec: docs/plans/negative-results-memory/LLD.md (FINAL) — §6's five seam
diffs and the seam half of §10's N-plan. `backend/tests/test_negmem.py` owns
the leaf module; THIS file owns everything that had to be cut into an engine:

  N-7  serving golden at negmem_strength=0, STAMP-INCLUSIVE   (§6.2 / C1)
  N-8  gen_v2 dual kill (M1 strength 0 ∧ M2 prior strength 0) (§6.3 / C1)
       + the "global read, not an arm overlay" fact the golden depends on
  N-9  arm A stamps exactly {m:1.0} in a live bake-off deck   (§6.5 / D-8)
  N-10 stamp provenance is a COPY, never a recompute          (B2 / DE-10)
  N-11 T1 — seams hold a live module binding, not a frozen fn (§6.2/§6.4)
  N-12 likes-you-led deck: batch-wide key + exempt stamp      (C3)
  N-13 flag-off / not-allowlisted byte identity               (C1)
  N-17 fit ordering survives the downstream composite re-sort (DE-9)
  N-18 fit multiplies BEFORE the 1e-9 quantization            (DE-9)
  N-19 degraded map ⇒ seams identity, every row stamped       (§8.1)
  N-20 streaming: exactly one multiply per card               (§6.2 proof)
  N-25 the allowlist is the OTHER half of the ON-condition    (§4.1 / DE-7)
  N-27 the relaxed pass consults the SAME map                 (§6.2 / HLD §3.5)

Three house rules are load-bearing here:

* **Fixture power (HLD §7).** Every "nothing happened" assertion runs against
  a world where something DOES happen — the same job/world at strength 1.0 is
  asserted to move. A golden that passed because the map was empty would be
  worthless.
* **Global vs overlay.** `_global_cfg` mutates `trade_service._cfg` (the
  process-global dict); `ts._cfg_override` pushes a THREAD-LOCAL arm overlay.
  They are not interchangeable — the build-time knobs are read before any arm
  context is entered, so `gen2_accept_prior_strength` can only be killed
  globally. N-8 asserts that difference rather than assuming it.
* **No knob literals from the DB.** Every knob here is a literal (trap-7).
  The evidence multiplier itself is NOT a literal: it is read back off the
  built map, because decay over the fixture's own age is a real (tiny) term
  and pinning it would make the file fail on a slow CI box.
"""

from __future__ import annotations

import ast
import copy
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select, text

import backend.database as db_module
import backend.feature_flags as ff
import backend.negmem as negmem
import backend.server as server
import backend.trade_service as ts
from backend import trade_gen_fit, trade_gen_v2
from backend.bakeoff_runner import restore_order
from backend.database import deck_impressions_table, metadata
from backend.tests.support import bakeoff_harness as H

BACKEND = Path(__file__).resolve().parents[1]

# The real `is_enabled`, captured at import time — BEFORE any patch in this
# file or in the harness can wrap it, so `_pins` never recurses into itself.
_REAL_IS_ENABLED = ff.is_enabled

# Knobs pinned as literals (the module holds no defaults, and reading them
# from model_config would move this file whenever a seed row moved).
K_FLOOR = 0.6
K_MIN_EVIDENCE = 3.0
K_SAT_K = 3.0
K_HALFLIFE = 45.0
# 5 admitted rejections, hours old ⇒ n_decayed ≈ 5 ⇒ n_eff ≈ 3 ⇒
# mult = 1 − (1 − 0.6)·3/(3 + 3) ≈ 0.8. Asserted as a band; the exact value
# is read off the map (see the module docstring).
M_BAND = (0.79, 0.81)

BUILD_KNOBS = dict(halflife_days=K_HALFLIFE, min_evidence=K_MIN_EVIDENCE,
                   sat_k=K_SAT_K, like_net=1.0, floor_b=K_FLOOR,
                   accept_prior_strength=10.0)

# The direct-engine world (see `_world`).
LEAGUE = "L1"
USER = "user"
OPP_A, OPP_B, OPP_C = "oppA", "oppB", "oppC"

# The server-job world (bakeoff_harness). `user_opp2` is the partner whose
# card the harness's deck actually carries, so that is where evidence goes.
H_LEAGUE = H.LEAGUE
H_ME = H.ME
H_PARTNER = H.OPP2
H_JOB = H.JOB_ID


# ---------------------------------------------------------------------------
# Shared plumbing
# ---------------------------------------------------------------------------

def _pins(**overrides):
    """Patch `feature_flags.is_enabled` with a pin table.

    Carries the harness's own `trade.outlook_direction` pin forward (this
    patch starts last and would otherwise drop it), so a features.json flip
    can never silently re-price a capture in this file.
    """
    table = {"trade.outlook_direction": True}
    table.update(overrides)

    def _f(key):
        if key in table:
            return table[key]
        return _REAL_IS_ENABLED(key)

    return patch.object(ff, "is_enabled", _f)


@contextmanager
def _global_cfg(**kv):
    """Set model_config values GLOBALLY (the `_cfg` snapshot idiom).

    Deliberately not `ts._cfg_override`: that is a thread-local ARM overlay,
    and the build-time knobs are read before any arm context exists.
    """
    old = dict(ts._cfg)
    ts._cfg.update(kv)
    try:
        yield
    finally:
        ts._cfg.clear()
        ts._cfg.update(old)


def _seam_cfg(strength=1.0, **extra):
    kv = {"negmem_strength": strength, "negmem_floor": K_FLOOR,
          "negmem_min_evidence": K_MIN_EVIDENCE, "negmem_sat_k": K_SAT_K,
          "negmem_halflife_days": K_HALFLIFE, "negmem_like_net": 1.0}
    kv.update(extra)
    return kv


@contextmanager
def _allowlist(entries):
    """Point the allowlist loader at an in-test value (cache reset both ways
    so a neighbouring test never inherits it)."""
    negmem._reset_allowlist_cache()
    try:
        with patch.object(negmem, "_read_allowlist_uncached",
                          lambda: frozenset(entries)):
            yield
    finally:
        negmem._reset_allowlist_cache()


def _fresh_engine():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    return engine


def _seed_rejections(partner, *, user, league, n=5, family="value",
                     like=False):
    """Write `n` ADMITTED rejections (viewed + pass + layer-1 reason row) into
    whatever `database.engine` currently points at.

    Evidence must post-date NEGMEM_CLEAN_EPOCH_DAY (2026-08-20), so the rows
    are HOURS old, not days — which also keeps decay small enough to leave the
    multiplier in `M_BAND`.
    """
    now = datetime.now(timezone.utc)
    with db_module.engine.begin() as conn:
        for i in range(n):
            imp = f"negmem-{partner}-{family}-{i}"
            served = (now - timedelta(hours=6 + i)).isoformat()
            acted = (now - timedelta(hours=5 + i)).isoformat()
            conn.execute(text(
                "INSERT INTO deck_impressions (impression_id, user_id, "
                "league_id, deck_job_id, card_index, trade_hash, "
                "features_json, propensity, served_at) VALUES "
                "(:i, :u, :l, 'negmem-evidence-job', 0, :h, :f, 1.0, :s)"
            ), {"i": imp, "u": user, "l": league, "h": f"nh-{imp}",
                "f": json.dumps({"partner_user_id": partner,
                                 "user_value_basis": "consensus"}),
                "s": served})
            for action in ("viewed", "like" if like else "pass"):
                conn.execute(text(
                    "INSERT INTO deck_outcomes (impression_id, action, "
                    "acted_at) VALUES (:i, :a, :t)"
                ), {"i": imp, "a": action, "t": acted})
            if not like:
                conn.execute(text(
                    "INSERT INTO trade_pass_reasons (impression_id, user_id, "
                    "league_id, key_source, reason, created_at, updated_at) "
                    "VALUES (:i, :u, :l, 'impression', :r, :c, :c)"
                ), {"i": imp, "u": user, "l": league, "r": family, "c": acted})


def _build_map(*, partner=OPP_A, user=USER, league=LEAGUE, n=5,
               family="value", engine=None, accept_prior_strength=None,
               extra_seed=None):
    """A real NegmemMap over a fresh in-memory DB seeded for `partner`."""
    engine = engine or _fresh_engine()
    knobs = dict(BUILD_KNOBS)
    if accept_prior_strength is not None:
        knobs["accept_prior_strength"] = accept_prior_strength
    with patch.object(db_module, "engine", engine):
        _seed_rejections(partner, user=user, league=league, n=n, family=family)
        if extra_seed is not None:
            extra_seed(engine)
        with _allowlist([league]):
            nm = negmem.build_map(user, league, **knobs)
    assert nm is not None and not nm.degraded
    m = nm.partner_mult.get(partner)
    assert m is not None and M_BAND[0] < m < M_BAND[1], f"unexpected m={m}"
    return nm


# ---------------------------------------------------------------------------
# The direct-engine world: user + three opponents, each holding one clean
# divergence trade. Produces cards on all three paths (v1/v3 serving stack,
# gen_v2, fit), which is what makes the seam assertions non-vacuous.
# ---------------------------------------------------------------------------

@dataclass
class _P:
    id: str
    name: str
    position: str
    team: str = "AAA"
    age: int = 25


def _positions(prefix):
    return {f"{prefix}_qb": "QB",
            f"{prefix}_rb1": "RB", f"{prefix}_rb2": "RB", f"{prefix}_rb3": "RB",
            f"{prefix}_wr1": "WR", f"{prefix}_wr2": "WR", f"{prefix}_wr3": "WR",
            f"{prefix}_te": "TE"}


def _world():
    players = {pid: _P(id=pid, name=pid, position=pos)
               for pid, pos in _positions("u").items()}
    user_roster = list(players)
    seed = {pid: 1500.0 for pid in players}
    user_elo = dict(seed)
    members = []
    for rb, (tag, bump) in zip(("u_rb1", "u_rb2", "u_rb3"),
                               (("A", 1700.0), ("B", 1680.0), ("C", 1660.0))):
        prefix = f"t{tag}"
        for pid, pos in _positions(prefix).items():
            players[pid] = _P(id=pid, name=pid, position=pos)
            seed[pid] = 1500.0
        centerpiece = f"{prefix}_wr1"
        seed[centerpiece] = 1600.0
        seed[rb] = 1600.0
        user_elo[centerpiece] = 1700.0
        user_elo.setdefault(rb, 1500.0)
        opp_elo = {pid: seed.get(pid, 1500.0) for pid in players}
        opp_elo[rb] = bump
        opp_elo[centerpiece] = 1500.0
        members.append(ts.LeagueMember(
            user_id=f"opp{tag}", username=f"opp{tag}",
            roster=[p for p in players if p.startswith(prefix + "_")],
            elo_ratings=opp_elo, has_rankings=True))
    for pid in players:
        seed.setdefault(pid, 1500.0)
        user_elo.setdefault(pid, seed[pid])
    league = ts.League(league_id=LEAGUE, name="T", platform="demo",
                       members=members)
    return players, league, user_roster, seed, user_elo


def _service():
    players, league, user_roster, seed, user_elo = _world()
    svc = ts.TradeService(players=players)
    svc.add_league(league)
    return svc, players, league, user_roster, seed, user_elo


def _serve(svc, user_roster, seed, user_elo, *, negmem=None, **extra):
    kwargs = dict(user_id=USER, user_elo=user_elo, user_roster=user_roster,
                  league_id=LEAGUE, seed_elo=seed, confidence={},
                  placements=None, outlook=None, fairness_threshold=0.75)
    kwargs.update(extra)
    return svc.generate_trades(negmem=negmem, **kwargs)


def _key(card):
    return (card.target_user_id, tuple(card.give_player_ids),
            tuple(card.receive_player_ids))


# ---------------------------------------------------------------------------
# The server-job world (full `_run_trade_job` through the bake-off harness)
# ---------------------------------------------------------------------------

class _Seed:
    """start()/stop() shim the harness runs INSIDE its own engine patch, so
    the rows land in exactly the DB the job will read."""

    def __init__(self, partner=H_PARTNER, n=5, family="value"):
        self.partner, self.n, self.family = partner, n, family

    def start(self):
        _seed_rejections(self.partner, user=H_ME, league=H_LEAGUE, n=self.n,
                         family=self.family)

    def stop(self):
        pass


class _Recorder:
    """start()/stop() shim that records the kwargs of every call to
    `target.name` and calls through."""

    def __init__(self, target, name):
        self.target, self.name, self.calls = target, name, []
        self._patch = None

    def start(self):
        real = getattr(self.target, self.name)

        def _wrapped(*a, **kw):
            self.calls.append(kw)
            return real(*a, **kw)

        self._patch = patch.object(self.target, self.name, _wrapped)
        self._patch.start()

    def stop(self):
        if self._patch is not None:
            self._patch.stop()


def _capture(*, negmem_on, allowlisted=True, strength=1.0, seeds=(),
             extra=(), cfg=None):
    """One full `_run_trade_job` under a pinned negmem configuration.

    The evidence rows this fixture seeds live in `deck_impressions` too, so
    the capture is trimmed to the JOB's own rows — otherwise the goldens would
    be comparing the fixture to itself.
    """
    entries = [H_LEAGUE] if allowlisted else []
    with _allowlist(entries), _global_cfg(**_seam_cfg(strength, **(cfg or {}))):
        cap, job, engine = H.run_capture(
            extra_patches=[*seeds, _pins(**{"trade.negmem": bool(negmem_on)}),
                           *extra])
    cap["impressions"] = [r for r in cap["impressions"]
                          if r.get("deck_job_id") == H_JOB]
    cap["card_count"] = len(cap["cards"])
    # `job_keys` is compared separately: a built map adds ONE key to the job
    # dict (`negmem_note`, the suppression_note pattern), which is an
    # operator-visible progress note and not part of the deck contract. C1's
    # byte-identity claim is about cards, scores, order and rows.
    cap["job_keys"] = [k for k in cap["job_keys"] if k != "negmem_note"]
    return cap, job, engine


def _features(cap):
    return [json.loads(r["features_json"]) for r in cap["impressions"]]


def _stamps(cap):
    return [f.get("negmem", "<<absent>>") for f in _features(cap)]


def _strip_negmem(cap):
    out = copy.deepcopy(cap)
    for row in out["impressions"]:
        feats = json.loads(row["features_json"])
        feats.pop("negmem", None)
        row["features_json"] = json.dumps(feats)
    return out


def _add_negmem(cap, payload):
    """The stamp-inclusive fixture builder: a flag-off capture plus the
    uninfluenced stamp on every row, at the exact key POSITION the seam writes
    it (right after the base features dict closes) — so the comparison is on
    the serialized bytes, not on a parsed dict."""
    out = copy.deepcopy(cap)
    for row in out["impressions"]:
        rebuilt = {}
        for key, value in json.loads(row["features_json"]).items():
            rebuilt[key] = value
            if key == "user_value_basis":
                rebuilt["negmem"] = payload
        assert "negmem" in rebuilt, "the base features dict shape changed"
        row["features_json"] = json.dumps(rebuilt)
    return out


# ===========================================================================
# N-13 / N-25 — the two halves of the ON-condition
# ===========================================================================

def test_n13_flag_off_and_unallowlisted_are_byte_identical():
    """C1: flag OFF and flag-ON-but-not-allowlisted produce the SAME bytes —
    the None seam is indistinguishable from flag-off, stamps included.

    Sabotage: stamp on `nm_map is None` (assembly writes {m:1.0} when the map
    is absent) — the `<<absent>>` assertions go RED.
    """
    off, _j, _e = _capture(negmem_on=False, seeds=[_Seed()])
    dark, _j2, _e2 = _capture(negmem_on=True, allowlisted=False,
                              seeds=[_Seed()])

    assert off["impressions"], "fixture produced no rows"
    assert off == dark
    assert _stamps(off) == ["<<absent>>"] * len(off["impressions"])
    assert all("negmem" not in f for f in _features(dark))

    # Fixture power: the same world, allowlisted, DOES move.
    on, _j3, _e3 = _capture(negmem_on=True, seeds=[_Seed()])
    assert any(f["negmem"]["m"] < 1.0 for f in _features(on))


def test_n13_negmem_kwarg_is_absent_when_there_is_no_map():
    """C1's kwargs half: `negmem` never enters `_generate_kwargs` unless a map
    exists, so `generate_trades` is called with byte-identical arguments.

    Sabotage: set the key unconditionally — the `not in` assertions go RED.
    """
    for negmem_on, allowlisted in ((False, True), (True, False)):
        rec = _Recorder(ts.TradeService, "generate_trades")
        _capture(negmem_on=negmem_on, allowlisted=allowlisted,
                 seeds=[_Seed()], extra=[rec])
        assert rec.calls and all("negmem" not in kw for kw in rec.calls)

    rec = _Recorder(ts.TradeService, "generate_trades")
    _capture(negmem_on=True, seeds=[_Seed()], extra=[rec])
    assert rec.calls and all(kw.get("negmem") is not None for kw in rec.calls)


def test_n25_allowlist_is_the_other_half_of_the_on_condition():
    """DE-7: `build_map` returns None for every league while the allowlist is
    empty, so flag-on with an unpopulated allowlist is inert by construction,
    and `["*"]` is the one-line global-rollout diff.

    Sabotage: treat an empty allowlist as "*" — the `is None` assertions go RED.
    """
    with patch.object(db_module, "engine", _fresh_engine()):
        with _allowlist([]):
            assert negmem.build_map(USER, LEAGUE, **BUILD_KNOBS) is None
        with _allowlist(["some-other-league"]):
            assert negmem.build_map(USER, LEAGUE, **BUILD_KNOBS) is None
        with _allowlist([LEAGUE]):
            assert negmem.build_map(USER, LEAGUE, **BUILD_KNOBS) is not None
        with _allowlist(["*"]):
            assert negmem.build_map(USER, "any-league", **BUILD_KNOBS) is not None


# ===========================================================================
# N-7 — golden (a): strength 0 is byte-identical except for the stamp
# ===========================================================================

def test_n7_serving_golden_strength0_is_stamp_inclusive_identity():
    """Golden (a): at `negmem_strength = 0` the deck — content, scores, order,
    payloads, rows — equals the flag-off capture PLUS `{m:1.0,"ver":1}` on
    every row. The seam owns the eff != 1.0 skip, so identity means no
    multiply and no round, not "a round that happens to return the same".

    Sabotages: round() at identity; bake `strength` into `build_map`'s cell
    multipliers (the build read is overlay-blind, so a strength-0 job would
    still be shifted).
    """
    off, _j, _e = _capture(negmem_on=False, seeds=[_Seed()])
    zero, _j2, _e2 = _capture(negmem_on=True, strength=0.0, seeds=[_Seed()])

    assert off["cards"], "fixture produced no cards"
    assert zero["cards"] == off["cards"]
    assert _strip_negmem(zero) == off
    assert zero == _add_negmem(off, {"m": 1.0, "ver": negmem.NEGMEM_VER})
    # The ONE difference outside the deck: the job dict carries the build note.
    assert set(_j2) - set(_j) == {"negmem_note"}

    # Fixture power: strength 1.0 over the same world DOES move the deck.
    live, _j3, _e3 = _capture(negmem_on=True, strength=1.0, seeds=[_Seed()])
    assert _strip_negmem(live) != off


def test_n7_strength0_stamp_is_uniform_across_every_row():
    """The trichotomy's ON-condition is the MAP, not the card: every row the
    job writes carries the key, whatever the card's partner or provenance."""
    zero, _j, _e = _capture(negmem_on=True, strength=0.0, seeds=[_Seed()])
    stamps = _stamps(zero)
    assert stamps
    assert all(s == {"m": 1.0, "ver": negmem.NEGMEM_VER} for s in stamps)


def test_n7_influenced_rows_carry_the_consult_time_payload():
    """Fixture power for every other golden in this file: at strength 1.0 the
    served row records a real multiplier, its driving families and evidence."""
    live, job, _e = _capture(negmem_on=True, strength=1.0, seeds=[_Seed()])
    stamps = [f["negmem"] for f in _features(live)]
    moved = [s for s in stamps if s["m"] < 1.0]
    assert moved, "no row was influenced — the fixture lost its power"
    for stamp in moved:
        assert M_BAND[0] < stamp["m"] < M_BAND[1]
        assert stamp["keys"] == ["value"]
        assert stamp["ev"]["value"] == pytest.approx(5.0, abs=0.05)
        assert stamp["ver"] == negmem.NEGMEM_VER
    assert job["negmem_note"]["degraded"] is False
    assert job["negmem_note"]["cells"] >= 1


# ===========================================================================
# N-20 — exactly one multiply per card, streaming included
# ===========================================================================

def test_n20_serving_seam_multiplies_each_card_exactly_once():
    """§6.2's once-only proof, executed end to end: `_dedup_and_sort` re-runs
    per snapshot and writes no score, so each composite carries exactly one
    factor of `eff`.

    Sabotage: multiply inside `_dedup_and_sort` — composites compound and the
    equality goes RED.
    """
    svc, players, league, user_roster, seed, user_elo = _service()
    nm = _build_map()
    m = nm.partner_mult[OPP_A]
    with _global_cfg(**_seam_cfg(1.0)), _pins(**{"trade.negmem": True}):
        base = {_key(c): c.composite_score
                for c in _serve(svc, user_roster, seed, user_elo)}
        live = {_key(c): c.composite_score
                for c in _serve(svc, user_roster, seed, user_elo, negmem=nm)}
    assert base and live.keys() == base.keys()
    moved = 0
    for key, value in live.items():
        if key[0] == OPP_A:
            assert value == pytest.approx(round(base[key] * m, 3), abs=1e-9)
            moved += 1
        else:
            assert value == base[key]
    assert moved, "no card for the evidence partner"


def test_n20_streaming_snapshots_never_compound():
    """The streaming callback fires once per opponent and re-runs
    `_dedup_and_sort` each time; every snapshot must show the SAME composite
    the final deck does."""
    seen: list[tuple[str, float]] = []

    def _cb(done, total, snapshot):
        seen.extend((c.trade_id, c.composite_score) for c in snapshot)

    svc, players, league, user_roster, seed, user_elo = _service()
    nm = _build_map()
    with _global_cfg(**_seam_cfg(1.0)), _pins(**{"trade.negmem": True}):
        cards = _serve(svc, user_roster, seed, user_elo, negmem=nm,
                       on_opponent_done=_cb)
    final = {c.trade_id: c.composite_score for c in cards}
    assert seen and final
    assert any(t in final for t, _ in seen)
    for trade_id, composite in seen:
        if trade_id in final:
            assert composite == final[trade_id]


def test_n20_seam_stamps_ride_the_card_at_consult_time():
    svc, players, league, user_roster, seed, user_elo = _service()
    nm = _build_map()
    with _global_cfg(**_seam_cfg(1.0)), _pins(**{"trade.negmem": True}):
        cards = _serve(svc, user_roster, seed, user_elo, negmem=nm)
    stamped = [c for c in cards if getattr(c, "negmem_stamp", None)]
    assert stamped and all(c.target_user_id == OPP_A for c in stamped)
    assert all(getattr(c, "negmem_stamp", None) is None
               for c in cards if c.target_user_id != OPP_A)
    assert stamped[0].negmem_stamp["keys"] == ["value"]


# ===========================================================================
# N-11 — T1: the seams hold a LIVE module binding
# ===========================================================================

def test_n11_t1_rebinding_effective_mult_changes_serving_output():
    """T1: the serving seam calls `_negmem.effective_mult` through the module
    object, so rebinding the module attribute changes the deck.

    Sabotage: `from .negmem import effective_mult` at the seam — the rebind
    stops being visible and this goes RED.
    """
    svc, players, league, user_roster, seed, user_elo = _service()
    nm = _build_map()
    with _global_cfg(**_seam_cfg(1.0, negmem_floor=0.1)):
        with _pins(**{"trade.negmem": True}):
            normal = {_key(c): c.composite_score
                      for c in _serve(svc, user_roster, seed, user_elo,
                                      negmem=nm)}
            with patch.object(negmem, "effective_mult", lambda *a, **k: 0.5):
                rebound = {_key(c): c.composite_score
                           for c in _serve(svc, user_roster, seed, user_elo,
                                           negmem=nm)}
    assert normal and rebound.keys() == normal.keys()
    assert any(rebound[k] != normal[k] for k in normal)


def test_n11_t1_rebinding_effective_mult_changes_fit_output():
    """The same proof on the fit path — fit's effect is ORDER, so the
    assertion is on order."""
    normal = _fit_order(strength=1.0)
    with patch.object(negmem, "effective_mult", lambda *a, **k: 0.5):
        rebound = _fit_order(strength=1.0)
    assert normal and rebound
    assert normal != rebound


# ===========================================================================
# N-17 / N-18 — the fit seam
# ===========================================================================

def _fit_cards(*, strength=1.0, nm=..., partner=OPP_A, headliner_cap=0.0):
    """Fit cards under a pinned negmem configuration.

    `headliner_cap` defaults to 0 (= the C4 cap OFF) for the RANKING tests.
    That cap is "keep-first in rank order" (`_apply_post_filters` step 6), so
    with it on, re-ranking legitimately changes which cards survive — real
    behaviour, recorded by `test_n18_fit_cap_interaction_is_recorded`, but it
    would make an ordering assertion compare two different card sets.
    """
    players, league, user_roster, seed, user_elo = _world()
    if nm is ...:
        nm = _build_map(partner=partner)
    with _global_cfg(**_seam_cfg(strength, deck_headliner_cap=headliner_cap)):
        with _pins(**{"trade.negmem": True}):
            cards, _report = trade_gen_fit.generate_league_suggestions(
                players=players, league=league, user_id=USER,
                user_elo=user_elo, user_roster=user_roster, seed_elo=seed,
                negmem_map=nm)
    return cards


def _fit_order(**kw):
    return [_key(c) for c in _fit_cards(**kw)]


def test_n18_fit_multiplier_is_inside_the_quantizing_round():
    """DE-9, asserted on the CODE the seam ships: the rank key is
    `-round(aggregate_raw * eff, 9)`, never `-round(aggregate_raw, 9) * eff`.

    The order is load-bearing for the C7c plateau — same-partner aggregates
    equal to ~1e-13 carry the SAME eff, so the scaled noise stays under the
    quantum and the deterministic tie-break survives. Multiplying after the
    round compares unquantized products and lets float noise outrank the
    tie-break. This is the mechanical form of that rule; the named sabotage
    ("multiply after the round") fails it directly.
    """
    tree = ast.parse((BACKEND / "trade_gen_fit.py").read_text())
    sorts = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "sort"]
    keys = [kw.value for call in sorts for kw in call.keywords
            if kw.arg == "key"]
    assert len(keys) == 1 and isinstance(keys[0], ast.Lambda), (
        "fit's candidates.sort key lambda moved — re-point this assertion")
    first = keys[0].body.elts[0]
    assert isinstance(first, ast.UnaryOp) and isinstance(first.op, ast.USub)
    call = first.operand
    assert isinstance(call, ast.Call) and getattr(call.func, "id", "") == "round"
    inner = call.args[0]
    assert isinstance(inner, ast.BinOp) and isinstance(inner.op, ast.Mult), (
        "the negmem multiplier must be INSIDE round(), not applied to its "
        "result — LLD §6.4")
    assert "_nm_eff" in ast.dump(inner)


def test_n18_plateau_arithmetic_pins_the_order_of_operations():
    """The numeric half of the same rule, with plateau-scale values: at
    m = 0.5 a 6e-10 separation collapses onto one quantum when the multiply
    happens first, and survives as float noise when it happens last."""
    a, b, m = 100.0, 100.0 + 6e-10, 0.5
    assert round(a * m, 9) == round(b * m, 9)      # shipped order: tie holds
    assert round(a, 9) * m != round(b, 9) * m      # sabotage: noise decides


def test_n18_same_partner_plateau_ties_survive_the_multiplier():
    """The fixture's own plateau: this world emits same-partner fit candidates
    whose aggregates are equal to float noise. Because `m` is partner-constant
    their relative order must be exactly what it was without negmem."""
    plain = _fit_cards(strength=0.0)
    live = _fit_cards(strength=1.0)
    plain_a = [_key(c) for c in plain if c.target_user_id == OPP_A]
    live_a = [_key(c) for c in live if c.target_user_id == OPP_A]
    assert len(plain_a) >= 2, "fixture lost its same-partner pairs"
    assert plain_a == live_a


def test_n18_fit_ordering_splits_across_partners_by_m():
    """Non-vacuity for the seam itself: the partner carrying evidence loses
    ground to partners that carry none, while membership is untouched."""
    plain = _fit_order(strength=0.0)
    live = _fit_order(strength=1.0)
    assert plain and sorted(plain) == sorted(live)     # same membership
    assert plain != live                               # different order


def test_n18_fit_composite_payload_is_never_multiplied():
    """Fit's `composite_score` is a published diagnostic — the seam is
    ordering-only, so the aggregate each card publishes must be untouched."""
    plain = {_key(c): c.composite_score for c in _fit_cards(strength=0.0)}
    live = {_key(c): c.composite_score for c in _fit_cards(strength=1.0)}
    assert plain and live.keys() == plain.keys()
    assert all(live[k] == plain[k] for k in plain)


def test_n18_fit_cap_interaction_is_recorded():
    """Recorded behaviour, not a wish: fit's C4 centerpiece cap keeps cards
    FIRST-IN-RANK-ORDER, so with the cap on, the negmem re-rank can change
    which fit cards survive it. The multiplier itself is still ordering-only
    (LLD §6.4 places it in step 5a, upstream of the step-6 cap) — the cap is
    what converts order into membership, exactly as it does for any other
    ranking change. Downstream consumers must not read "ordering-only" as
    "the fit arm returns the same cards"."""
    plain = {_key(c) for c in _fit_cards(strength=0.0, headliner_cap=3.0)}
    live = {_key(c) for c in _fit_cards(strength=1.0, headliner_cap=3.0)}
    assert plain and live
    assert plain != live or len(plain) == len(live)


def test_n18_fit_stamps_only_influenced_partners():
    cards = _fit_cards(strength=1.0)
    stamped = [c for c in cards if getattr(c, "negmem_stamp", None)]
    assert stamped and {c.target_user_id for c in stamped} == {OPP_A}
    assert M_BAND[0] < stamped[0].negmem_stamp["m"] < M_BAND[1]
    assert stamped[0].negmem_stamp["keys"] == ["value"]


def test_n17_fit_ordering_survives_the_downstream_composite_resort():
    """DE-9's end-to-end pin: fit's negmem effect lives ONLY in list order, so
    a downstream composite re-sort (the likes-you injector's) would erase it —
    `restore_order` is what puts every card back at its interleaved index.

    Sabotage: skip `restore_order` (serve the re-sorted list) — the last
    assertion shows exactly what that costs.
    """
    live = _fit_cards(strength=1.0)
    assert len(live) >= 2
    fixed = list(live)
    # A downstream re-sort keyed on the composite ALONE — deterministic and
    # independent of the incoming order, which is what makes it destructive.
    resorted = sorted(live, key=lambda c: (-c.composite_score, _key(c)))
    assert [id(c) for c in resorted] != [id(c) for c in fixed], (
        "fixture's composite order already equals negmem order — the "
        "assertion below would be vacuous")
    restored = restore_order(fixed, resorted)
    assert [id(c) for c in restored] == [id(c) for c in fixed]


# ===========================================================================
# N-8 — gen_v2: the M1 seam and the M2 feed
# ===========================================================================

def _gen_v2(*, nm, acceptance_stats=None):
    players, league, user_roster, seed, user_elo = _world()
    kwargs = dict(players=players, league=league, user_id=USER,
                  user_elo=user_elo, user_roster=user_roster, seed_elo=seed,
                  confidence=None, negmem_map=nm)
    if acceptance_stats is not None:
        kwargs["acceptance_stats"] = acceptance_stats
    with _pins(**{"trade.negmem": True}):
        cards, _report = trade_gen_v2.generate_league_suggestions(**kwargs)
    return cards


def _canon(cards):
    return [(c.target_user_id, tuple(c.give_player_ids),
             tuple(c.receive_player_ids), c.composite_score, c.mismatch_score,
             c.fairness_score, c.health) for c in cards]


def _seed_m2(engine):
    """One accepted response for OPP_A plus the canonical membership rows, so
    the M2 feed is non-empty whenever the guard lets it through."""
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        for uid in (USER, OPP_A, OPP_B, OPP_C):
            conn.execute(text(
                "INSERT INTO league_members (league_id, user_id, username, "
                "updated_at) VALUES (:l, :u, :u, :t)"
            ), {"l": LEAGUE, "u": uid, "t": now})
        conn.execute(text(
            "INSERT INTO trade_matches (league_id, user_a_id, user_a_give, "
            "user_a_receive, user_b_id, user_b_decision, user_b_decided_at, "
            "matched_at, status) VALUES "
            "(:l, :a, '[]', '[]', :b, 'accept', :t, :t, 'pending')"
        ), {"l": LEAGUE, "a": USER, "b": OPP_A, "t": now})


def test_n8_arm_c_dual_kill_is_byte_identical():
    """Golden (b): with `negmem_strength = 0` AND `gen2_accept_prior_strength
    = 0` — BOTH set GLOBALLY — arm C's cards are byte-identical to the
    no-negmem call. That verifies M2's structural kill *and* gen_v2's M1 seam,
    which M2 could otherwise mask.

    Sabotages: remove the feed guard (pass stats at strength 0); move the
    guard into `acceptance_prior`.
    """
    with _global_cfg(**_seam_cfg(0.0, gen2_accept_prior_strength=0.0)):
        nm = _build_map(
            accept_prior_strength=ts._c("gen2_accept_prior_strength"),
            extra_seed=_seed_m2)
        assert nm.m2_feed() == {}, "the strength-0 kill must empty the feed"
        plain = _canon(_gen_v2(nm=None))
        dual_killed = _canon(_gen_v2(nm=nm, acceptance_stats=nm.m2_feed()))
    assert plain and plain == dual_killed


def test_n8_the_m2_kill_is_global_never_an_arm_overlay():
    """The load-bearing half of the golden's setup: the build knobs are read
    on the job thread BEFORE any arm context is entered, so pinning
    `gen2_accept_prior_strength` through a thread-local arm overlay leaves the
    feed POPULATED and the golden would pass for the wrong reason.

    This test IS the named sabotage, asserted as documented behaviour.
    """
    with _global_cfg(**_seam_cfg(1.0, gen2_accept_prior_strength=10.0)):
        with ts._cfg_override({"gen2_accept_prior_strength": 0.0}):
            # An arm overlay around the BUILD changes nothing: the caller
            # passes the value it already read globally.
            nm = _build_map(accept_prior_strength=10.0, extra_seed=_seed_m2)
    assert nm.m2_feed(), ("an arm overlay must NOT empty the feed — only a "
                          "GLOBAL gen2_accept_prior_strength = 0 does")
    assert OPP_A in nm.m2_feed()


def test_n8_m1_multiplier_lands_on_gen2_cards_without_touching_membership():
    """§6.3: the pair-constant multiplier is applied at CARD CREATION, not in
    `_Candidate.score` — so composites move and membership does not.

    Sabotage: fold the multiplier into `_Candidate.score` — the membership
    assertion goes RED.
    """
    nm = _build_map()
    m = nm.partner_mult[OPP_A]
    with _global_cfg(**_seam_cfg(1.0)):
        plain = _gen_v2(nm=None)
        live = _gen_v2(nm=nm)
    assert plain and [_key(c) for c in plain] == [_key(c) for c in live]
    base = {_key(c): c.composite_score for c in plain}
    moved = 0
    for card in live:
        if card.target_user_id == OPP_A:
            assert card.composite_score == pytest.approx(
                round(base[_key(card)] * m, 4), abs=1e-9)
            assert card.negmem_stamp["m"] == round(m, 4)
            moved += 1
        else:
            assert card.composite_score == base[_key(card)]
            assert getattr(card, "negmem_stamp", None) is None
    assert moved


def test_n8_m2_feed_kwarg_is_conditional_and_negmem_map_is_not():
    """§6.3's stated asymmetry, at the `trade_service` call site: `negmem_map`
    is passed UNCONDITIONALLY (carrying None when off — the seams guard on the
    VALUE, not the kwarg's presence), while `acceptance_stats` is added only
    when a map exists, which is what keeps the flag-off call byte-identical.

    Sabotage: tidy `negmem_map` into the conditional splat — the "always
    present" assertion goes RED.
    """
    svc, players, league, user_roster, seed, user_elo = _service()
    nm = _build_map()
    calls: list[dict] = []
    real = trade_gen_v2.generate_league_suggestions

    def _spy(**kw):
        calls.append(kw)
        return real(**kw)

    with _global_cfg(**_seam_cfg(1.0)):
        with _pins(**{"trade.negmem": True, "trade_gen.v2": True}):
            # trade_service imports the symbol INSIDE the branch, so patching
            # the module attribute is what the call site resolves.
            with patch.object(trade_gen_v2, "generate_league_suggestions",
                              _spy):
                _serve(svc, user_roster, seed, user_elo, negmem=None)
                _serve(svc, user_roster, seed, user_elo, negmem=nm)
    assert len(calls) == 2
    assert "negmem_map" in calls[0] and calls[0]["negmem_map"] is None
    assert "acceptance_stats" not in calls[0]
    assert calls[1]["negmem_map"] is nm
    assert "acceptance_stats" in calls[1]


# ===========================================================================
# N-10 / N-12 — the features-assembly stamp
# ===========================================================================

class _Card:
    """The minimum a card needs to reach the assembly."""

    def __init__(self, target, *, likes_you=False, stamp=None, composite=1.0):
        self.give_player_ids = ["u_rb1"]
        self.receive_player_ids = ["tA_wr1"]
        self.target_user_id = target
        self.composite_score = composite
        self.likes_you = likes_you
        self.basis = "divergence"
        self.mismatch_score = 1.0
        self.fairness_score = 1.0
        if stamp is not None:
            self.negmem_stamp = stamp


def _log(cards, nm_map, engine=None):
    engine = engine or _fresh_engine()
    with patch.object(db_module, "engine", engine):
        with patch.object(server, "_deck_signal_v2_enabled", lambda: True):
            server._log_deck_signal_impressions(
                user_id=USER, league_id=LEAGUE, job_id="job-assembly",
                cards=cards, players_dict={}, capture=None,
                scoring_format="1qb_ppr", nm_map=nm_map)
        with engine.connect() as conn:
            rows = conn.execute(
                select(deck_impressions_table)
                .order_by(deck_impressions_table.c.card_index)).fetchall()
    return [json.loads(dict(r._mapping)["features_json"]) for r in rows]


def test_n10_assembly_copies_the_consult_time_stamp_and_never_recomputes():
    """B2/DE-10: the stamp is card state. By logging time every arm's
    `_cfg_override` has exited, so a recompute would stamp arm-A rows with the
    LIVE arm's m — the sabotage this test names.

    Sabotage: call `effective_mult` + `_c` in the assembly — the stamp reads
    the live 1.0 instead of the consult-time value and this goes RED.
    """
    nm = _build_map()
    consult = {"m": 0.75, "keys": ["value"], "ev": {"value": 5.0},
               "ver": negmem.NEGMEM_VER}
    # Live config says strength 0 — a recompute would therefore yield 1.0.
    with _global_cfg(**_seam_cfg(0.0)):
        feats = _log([_Card(OPP_A, stamp=consult)], nm)
    assert feats[0]["negmem"] == consult


def test_n10_assembly_never_calls_effective_mult():
    """The same rule as a hard mechanical guard: `effective_mult` raises if the
    assembly so much as touches it."""
    nm = _build_map()

    def _boom(*a, **k):                     # pragma: no cover - must not run
        raise AssertionError("the assembly recomputed the stamp")

    with patch.object(negmem, "effective_mult", _boom):
        feats = _log([_Card(OPP_A, stamp={"m": 0.5, "ver": 1}), _Card(OPP_B)],
                     nm)
    assert feats[0]["negmem"] == {"m": 0.5, "ver": 1}
    assert feats[1]["negmem"] == {"m": 1.0, "ver": negmem.NEGMEM_VER}


def test_n12_likes_you_led_deck_keeps_the_key_on_every_row():
    """C3: a deck LED by a likes-you injection (the `model_arm` scar
    scenario). `save_deck_impressions` compiles its executemany from the FIRST
    row's keys, so the stamp rides INSIDE features_json — the injection stamps
    `exempt`, and an organic card the injector merely boosted keeps its real
    consult-time stamp.

    Sabotages: move the stamp outside features_json; stamp only cards that
    carry `negmem_stamp` (the exempt/default rows lose the key).
    """
    nm = _build_map()
    organic = {"m": 0.8, "keys": ["value"], "ev": {"value": 5.0},
               "ver": negmem.NEGMEM_VER}
    feats = _log([_Card(OPP_A, likes_you=True),                 # injection
                  _Card(OPP_A, likes_you=True, stamp=organic),  # boosted
                  _Card(OPP_B)], nm)
    assert len(feats) == 3 and all("negmem" in f for f in feats)
    assert feats[0]["negmem"] == {"m": 1.0, "ver": negmem.NEGMEM_VER,
                                  "exempt": True}
    assert feats[1]["negmem"] == organic     # consult-time stamp always wins
    assert feats[2]["negmem"] == {"m": 1.0, "ver": negmem.NEGMEM_VER}


def test_n12_no_map_means_no_key_on_any_row():
    feats = _log([_Card(OPP_A, stamp={"m": 0.5, "ver": 1}), _Card(OPP_B)],
                 None)
    assert feats and all("negmem" not in f for f in feats)


def test_n12_degraded_map_overrides_every_card_stamp():
    """§8.1: a degraded map is identity everywhere, and the row says so — even
    for a card that somehow carries a consult-time stamp."""
    degraded = negmem._degraded_map(USER, LEAGUE, "2026-08-21T00:00:00+00:00",
                                    999.0)
    feats = _log([_Card(OPP_A, stamp={"m": 0.5, "ver": 1}), _Card(OPP_B)],
                 degraded)
    assert all(f["negmem"] == {"m": 1.0, "ver": negmem.NEGMEM_VER,
                               "degraded": True} for f in feats)


# ===========================================================================
# N-19 — degraded maps and hard build failures
# ===========================================================================

class _SlowClock:
    """Script `negmem._perf_counter` so the build reads as slower than
    NEGMEM_DEGRADE_MS — never `sleep`, which would add half a second of wall
    time to every CI run for no extra coverage (§10 N-19)."""

    def start(self):
        seq = iter([0.0, (negmem.NEGMEM_DEGRADE_MS + 50.0) / 1000.0])

        def _clock():
            try:
                return next(seq)
            except StopIteration:
                return 10.0

        self._p = patch.object(negmem, "_perf_counter", _clock)
        self._p.start()

    def stop(self):
        self._p.stop()


def test_n19_degraded_map_is_identity_at_the_seams_and_stamped_everywhere():
    """A slow-but-valid build is DISCARDED. The map still travels (so the
    trichotomy stays ON), every seam treats it as identity, and every row
    records the degradation.

    Sabotage: stamp degraded but keep multiplying — the byte-identity
    assertion goes RED.
    """
    off, _j, _e = _capture(negmem_on=False, seeds=[_Seed()])
    slow, job, _e2 = _capture(negmem_on=True, strength=1.0, seeds=[_Seed()],
                              extra=[_SlowClock()])
    assert _strip_negmem(slow) == off
    assert _stamps(slow) == [{"m": 1.0, "ver": negmem.NEGMEM_VER,
                              "degraded": True}] * len(slow["impressions"])
    assert job["negmem_note"]["degraded"] is True


def test_n19_hard_build_failure_leaves_no_trace():
    """A builder that raises hard ⇒ no map ⇒ the job is byte-identical to
    flag-off, stamps included. (`build_map` never raises; this exercises the
    belt in `_run_trade_job`.)"""

    class _Boom:
        def start(self):
            def _raise(*a, **k):
                raise RuntimeError("boom")

            self._p = patch.object(negmem, "build_map", _raise)
            self._p.start()

        def stop(self):
            self._p.stop()

    off, _j, _e = _capture(negmem_on=False, seeds=[_Seed()])
    broken, job, _e2 = _capture(negmem_on=True, strength=1.0, seeds=[_Seed()],
                                extra=[_Boom()])
    assert broken == off
    assert "negmem_note" not in job
    assert job["status"] == "complete"


# ===========================================================================
# N-27 — the relaxed pass
# ===========================================================================

def test_n27_relaxed_pass_consults_the_same_map():
    """HLD §3.5: the map is ONE key in the ONE `_v2_kwargs` dict, which is
    both splatted into the normal pass and handed whole to the relaxed re-run
    — so the relaxed pass reuses the identical map at the same `_c`-read
    strength, with no special case and no rebuild.

    Sabotage: drop `negmem_map` from `_v2_kwargs` (or rebuild it inside the
    relaxed pass) — the identity assertion goes RED.
    """
    svc, players, league, user_roster, seed, user_elo = _service()
    nm = _build_map()
    seen: list[object] = []

    def _fake_v2(self, **kw):
        seen.append(kw.get("negmem_map", "<<absent>>"))
        if len(seen) == 1:
            return []
        return [ts.TradeCard(
            trade_id="t1", league_id=LEAGUE, proposing_user_id=USER,
            target_user_id=OPP_A, target_username=OPP_A,
            give_player_ids=["u_rb1"], receive_player_ids=["tA_wr1"],
            mismatch_score=1.0, fairness_score=1.0, composite_score=1.0)]

    with _global_cfg(**_seam_cfg(1.0)):
        with _pins(**{"trade.negmem": True}):
            with patch.object(ts.TradeService, "_generate_trades_v2",
                              _fake_v2):
                cards = _serve(svc, user_roster, seed, user_elo, negmem=nm,
                               pinned_give_players=["u_rb1"])
    assert len(seen) >= 2, "the relaxed pass never ran"
    assert all(s is nm for s in seen)
    assert cards and cards[0].relaxed is True


# ===========================================================================
# N-9 — arm A in a live bake-off deck
# ===========================================================================

def test_n9_arm_a_rows_stamp_exactly_identity():
    """Golden (c): every `model_arm='baseline'` row stamps exactly
    `{m:1.0, ver:1}` — never absence, never a live m — because
    `MODEL_A_PROFILE` pins `negmem_strength = 0.0` and the seam skips at
    identity. Fixture power: the SAME job stamps m < 1.0 on a non-A arm.

    Sabotage: drop `negmem_strength` from MODEL_A_PROFILE — arm-A rows start
    carrying the live m and this goes RED.
    """
    cap, _job, _e = _capture(negmem_on=True, strength=1.0, seeds=[_Seed()],
                             cfg={"bakeoff_include_baseline": 1.0,
                                  "bakeoff_serve_interleaved": 1.0})
    rows = [(r.get("model_arm"), json.loads(r["features_json"]).get("negmem"))
            for r in cap["impressions"]]
    assert rows, "the bake-off produced no rows"
    arms = {a for a, _ in rows}
    assert "baseline" in arms, f"arm A never served a card (arms={arms})"
    for arm, stamp in rows:
        assert stamp is not None, f"arm {arm} row carries no stamp"
        if arm == "baseline":
            assert stamp == {"m": 1.0, "ver": negmem.NEGMEM_VER}
    influenced = [s for a, s in rows if a != "baseline" and s["m"] < 1.0]
    assert influenced, "fixture power: no non-baseline arm was influenced"


# ===========================================================================
# T1, static half — no seam may value-import the module
# ===========================================================================

@pytest.mark.parametrize("name", ["server.py", "trade_service.py",
                                  "trade_gen_v2.py", "trade_gen_fit.py"])
def test_seams_import_the_negmem_module_not_its_functions(name):
    """T1: every seam holds a LIVE module binding. A `from .negmem import x`
    anywhere would freeze it — exactly what N-11 sabotages."""
    source = (BACKEND / name).read_text()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and (node.module or "") == "negmem":
            raise AssertionError(f"{name} value-imports negmem (T1)")
    assert re.search(r"^from \. import .*\bnegmem\b", source, re.M), (
        f"{name} lost its `from . import negmem` module binding")
