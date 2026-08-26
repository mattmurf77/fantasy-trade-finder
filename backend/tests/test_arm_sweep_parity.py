"""Opponent-sweep parity pins for the two non-live generation arms.

Plan: `docs/plans/full-sweep/plan.md` §2 ("Other arms — verify, don't
assume") and §5 tests 8–9. Scope: `docs/plans/full-sweep/scope.md` §3.

`trade.full_sweep` removes the `global_target` early exit from the LIVE
loop in `backend/trade_service.py` (`_generate_trades_v2` and the legacy
`_generate_trades_impl`). The other two arms were *claimed* to have no
opponent-level early exit at all. This file is the verification, turned
into a regression pin: both arms must visit EVERY eligible opponent, so
that the "score everyone, rank globally" contract holds on every arm and
not only on the flagged one.

Read of `origin/main` @ `b6e906a` (2026-08-22) — re-grep, these drift:

  backend/trade_gen_v2.py
    :1110  `for idx, member in enumerate(boarded):`  — the sweep
    :1165  `if not survivors: continue`              — skips ONE member
    :1324  `return cards, report`                    — the only exit
    The module's ONLY `break` statements are :877 (inside `_dedup_batch`,
    the per-candidate Jaccard scan) and :913 (inside `_meso_variants`,
    the `len(out) >= max_n` variant budget). Both live in helpers called
    from inside the loop body; neither can terminate the member sweep.
    Budgets are per-pair only (`_ITER_BUDGET`, the staged pools).

  backend/trade_gen_fit.py
    :331   `for member in eligible:`                 — the sweep
    :393   `candidates.extend(_enumerate_pair(...))` — last statement of
           the loop body; no `break`, no `continue`, no `return` in it
    The module's ONLY `break` statements are :614/:619/:632/:637/:640/:651,
    all inside `_enumerate_pair` (:579), guarding the per-pair
    `fit_max_packages_per_pair` budget via the function-local `capped`
    flag — which is re-initialised on every call, so it cannot leak
    across members.

Method: the expensive per-pair stage of each arm is stubbed so the test
is fast, and the stub records the member it was handed. The stub emits
enough cards per member that the LIVE loop's `global_target` arithmetic
(`max(30, max_per_opponent * 6)` = 30 at the default) is crossed after
six members — so a card-count early exit of the live loop's shape would
be caught here too, not just an unconditional one.

SABOTAGE PROOF (run 2026-08-22; each line applied, observed, then
restored from a byte copy taken before the edit (NOT `git checkout --`, which on an uncommitted branch discards the whole feature) — no engine source is changed by this
file):

  gen_v2 — inserted as the first statement of the sweep body, after
  `backend/trade_gen_v2.py:1110`:
      if idx >= 2: break
    => 3 failed, 1 passed.
       test_gen_v2_visits_every_boarded_member  FAILED (visited
         ['opp0', 'opp1'], 10 expected)
       test_gen_v2_emits_cards_for_every_member FAILED (2 distinct
         targets, 10 expected)
       test_gen_v2_streams_once_per_member      FAILED ([1, 2] vs
         [1 … 10])

  fit — inserted as the first statement of the sweep body, after
  `backend/trade_gen_fit.py:331`:
      if len({c["member"].user_id for c in candidates}) >= 2: break
    => 2 failed, 2 passed.
       test_fit_visits_every_eligible_member  FAILED (visited
         ['opp0', 'opp1'], 10 expected)
       test_fit_emits_cards_for_every_member  FAILED ({'opp0', 'opp1'},
         10 expected)

The two `*_module_has_no_sweep_level_break` tests survived both
sabotages, by design and worth stating: they only catch a `break` on its
own line, so they are a cheap structural backstop, never the primary
pin. The behavioural tests above are what actually holds the contract.
"""

from dataclasses import dataclass
from typing import Optional

import pytest

import backend.trade_gen_fit as tgf
import backend.trade_gen_v2 as gen2
import backend.trade_service as ts


#: Number of opponents in the synthetic league. Deliberately larger than
#: the ~6 partners the live loop reaches today, and larger than the six
#: members `global_target` allows at the default knobs.
N_OPPONENTS = 10

#: Cards the stub emits per member. 10 × 5 = 50 > max(30, 5 × 6) = 30.
CARDS_PER_MEMBER = 5


# ---------------------------------------------------------------------------
# Fixture league
# ---------------------------------------------------------------------------

@dataclass
class _Player:
    id: str
    name: str
    position: str = "RB"
    team: str = "TST"
    age: Optional[int] = 25
    ktc_value: Optional[int] = None
    pick_value: Optional[float] = None


_SKELETON = ("QB", "RB", "RB", "RB", "WR", "WR", "WR", "TE")


def _roster(prefix: str) -> dict[str, str]:
    """A feasible 8-man skeleton, ids prefixed so every roster is disjoint."""
    return {f"{prefix}_{i}_{pos.lower()}": pos
            for i, pos in enumerate(_SKELETON)}


def _fixture_league():
    """One user plus `N_OPPONENTS` boarded opponents, all rosters disjoint.

    Every opponent carries real `elo_ratings` + `has_rankings=True` so it
    survives `trade_gen_v2`'s `boarded` filter; `trade_gen_fit` takes
    every member with a roster regardless.
    """
    pos_map: dict[str, str] = dict(_roster("u"))
    member_rosters: dict[str, list[str]] = {}
    for k in range(N_OPPONENTS):
        r = _roster(f"m{k}")
        pos_map.update(r)
        member_rosters[f"opp{k}"] = list(r)

    players = {pid: _Player(id=pid, name=pid, position=pos)
               for pid, pos in pos_map.items()}
    user_roster = [pid for pid in pos_map if pid.startswith("u_")]
    seed = {pid: 1500.0 + (i % 7) * 10.0
            for i, pid in enumerate(sorted(pos_map))}

    members = [ts.LeagueMember(user_id="user", username="You",
                               roster=list(user_roster),
                               elo_ratings=dict(seed), has_rankings=True)]
    for uid, roster in member_rosters.items():
        # A board that diverges from consensus on the member's own assets,
        # so the member is genuinely "boarded" rather than seeded flat.
        board = {pid: elo + (40.0 if pid in roster else -40.0)
                 for pid, elo in seed.items()}
        members.append(ts.LeagueMember(user_id=uid, username=uid,
                                       roster=list(roster),
                                       elo_ratings=board, has_rankings=True))

    league = ts.League(league_id="Lsweep", name="Sweep League",
                       platform="demo", members=members)
    return players, league, user_roster, seed, member_rosters


@pytest.fixture(autouse=True)
def _pinned_defaults():
    """Both arms read live knobs through `ts._c`; pin them to the defaults
    so another module's leftover `_cfg` mutation cannot move a verdict."""
    saved = dict(ts._cfg)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    yield
    ts._cfg.clear()
    ts._cfg.update(saved)


#: The LIVE loop's early-exit threshold, recomputed from its own formula
#: (`trade_service.py:5343`, and identically at `:4414`):
#: `max(30, max_per_opponent * 6)`, with `max_per_opponent` defaulting to
#: 5 (`trade_service.py:4158`). Neither arm under test may honour it.
LIVE_LOOP_GLOBAL_TARGET = max(30, 5 * 6)


# ---------------------------------------------------------------------------
# Arm `gen_v2` — backend/trade_gen_v2.py
# ---------------------------------------------------------------------------

def _stub_pair_survivors(monkeypatch, players, user_roster, member_rosters):
    """Replace the expensive staged search with a fixed survivor set.

    Records each opponent handed to it, in call order. Every candidate
    gets a distinct centerpiece and disjoint asset set so neither the
    exact/bucket dedup nor the Jaccard rule in `_dedup_batch` collapses
    them — the pin must not be weakened by dedup eating the fixture.
    """
    visited: list[str] = []

    def _fake(*, opponent, **_kw):
        visited.append(opponent.user_id)
        opp_roster = member_rosters[opponent.user_id]
        out = []
        for i in range(CARDS_PER_MEMBER):
            give = user_roster[i]
            recv = opp_roster[i]
            out.append(gen2._Candidate(
                opponent_id=opponent.user_id,
                centerpiece=recv,
                give_ids=[give],
                recv_ids=[recv],
                user_gain=100.0 + i,
                opp_gain=100.0 + i,
                joint_gain=200.0 + 2 * i,
                symmetry=1.0,
                split_ratio=0.5,
                fairness_ratio=1.0,
                band_position=0.0,
                accept_prior=0.5,
                # Descending within the pair, and descending across
                # members, so ordering assertions stay deterministic.
                score=1000.0 - i,
                give_val_opp=1000.0,
            ))
        return out

    monkeypatch.setattr(gen2, "_pair_survivors", _fake)
    return visited


def test_gen_v2_visits_every_boarded_member(monkeypatch):
    """`generate_league_suggestions` has no opponent-level early exit.

    Pins `backend/trade_gen_v2.py:1110`. If a `global_target`-style break
    were added, the sweep would stop around member 6 (see
    `_global_target_at_defaults`); it must reach all 10.
    """
    players, league, user_roster, seed, rosters = _fixture_league()
    visited = _stub_pair_survivors(monkeypatch, players, user_roster, rosters)

    cards, report = gen2.generate_league_suggestions(
        players=players, league=league, user_id="user",
        user_elo=dict(seed), user_roster=user_roster, seed_elo=dict(seed),
    )

    assert visited == [f"opp{k}" for k in range(N_OPPONENTS)]
    assert report.boarded_opponents == N_OPPONENTS
    assert len(report.viable_by_opponent) == N_OPPONENTS
    # Sensitivity: the deck is well past the live loop's stop threshold,
    # so a count-based exit of that shape would have fired mid-sweep.
    assert len(cards) > LIVE_LOOP_GLOBAL_TARGET


def test_gen_v2_emits_cards_for_every_member(monkeypatch):
    """Every visited member reaches the emitted deck — the sweep is not
    merely entered for each member, it produces cards for each."""
    players, league, user_roster, seed, rosters = _fixture_league()
    _stub_pair_survivors(monkeypatch, players, user_roster, rosters)

    cards, report = gen2.generate_league_suggestions(
        players=players, league=league, user_id="user",
        user_elo=dict(seed), user_roster=user_roster, seed_elo=dict(seed),
    )

    assert {c.target_user_id for c in cards} == {
        f"opp{k}" for k in range(N_OPPONENTS)}
    assert len(cards) == N_OPPONENTS * CARDS_PER_MEMBER
    assert set(report.exposure_by_opponent) == {
        f"opp{k}" for k in range(N_OPPONENTS)}


def test_gen_v2_streams_once_per_member(monkeypatch):
    """`on_opponent_done` fires once per boarded member, with a
    monotonically increasing index, a constant total, and a snapshot that
    never shrinks (plan §5 test 4, applied to this arm)."""
    players, league, user_roster, seed, rosters = _fixture_league()
    _stub_pair_survivors(monkeypatch, players, user_roster, rosters)

    calls: list[tuple[int, int, int]] = []

    def _on_done(done, total, snapshot):
        calls.append((done, total, len(snapshot)))

    gen2.generate_league_suggestions(
        players=players, league=league, user_id="user",
        user_elo=dict(seed), user_roster=user_roster, seed_elo=dict(seed),
        on_opponent_done=_on_done,
    )

    assert [d for d, _t, _n in calls] == list(range(1, N_OPPONENTS + 1))
    assert {t for _d, t, _n in calls} == {N_OPPONENTS}
    sizes = [n for _d, _t, n in calls]
    assert sizes == sorted(sizes)
    assert sizes[-1] == N_OPPONENTS * CARDS_PER_MEMBER


def test_gen_v2_module_has_no_sweep_level_break():
    """Structural companion to the behavioural pins: no bare `break` on
    its own line anywhere in the member sweep's body. Cheap, and it
    catches a reintroduced early exit even if a future fixture stops
    accumulating enough cards to trip the behavioural tests. It does NOT
    catch a one-line `if cond: break` — see the module docstring."""
    src = open(gen2.__file__, encoding="utf-8").read().splitlines()
    start = next(i for i, line in enumerate(src)
                 if line.strip().startswith("for idx, member in enumerate(boarded)"))
    body = []
    for line in src[start + 1:]:
        if line.strip() and not line.startswith("        "):
            break                       # dedent out of the loop body
        body.append(line)
    offenders = [ln for ln in body
                 if ln.strip() == "break" or ln.strip().startswith("break ")]
    assert offenders == [], offenders


# ---------------------------------------------------------------------------
# Arm `fit` — backend/trade_gen_fit.py
# ---------------------------------------------------------------------------

def _stub_enumerate_pair(monkeypatch):
    """Replace the per-pair cartesian enumeration with a fixed handful of
    scored candidates, produced by the arm's OWN `score` closure so the
    candidate dicts stay faithful to `_score_candidate`'s contract.

    Records the member each call was made for (read back off the closure's
    own stamp, since `_enumerate_pair` is not handed the member).
    """
    visited: list[str] = []

    def _fake(user_pool, opp_pool, kill, score, report, cap, expand_from):
        out = []
        for i in range(CARDS_PER_MEMBER):
            g = user_pool[i % len(user_pool)]
            r = opp_pool[i % len(opp_pool)]
            report.enumerated += 1
            out.append(score([g], [r]))
        visited.append(out[0]["member"].user_id)
        return out

    monkeypatch.setattr(tgf, "_enumerate_pair", _fake)
    return visited


def test_fit_visits_every_eligible_member(monkeypatch):
    """`trade_gen_fit.generate_league_suggestions` has no opponent-level
    early exit — pins `backend/trade_gen_fit.py:331`. The only budget is
    `fit_max_packages_per_pair`, and it is per-pair (the `capped` flag is
    local to `_enumerate_pair`)."""
    players, league, user_roster, seed, _rosters = _fixture_league()
    visited = _stub_enumerate_pair(monkeypatch)

    cards, report = tgf.generate_league_suggestions(
        players=players, league=league, user_id="user",
        user_elo=dict(seed), user_roster=user_roster, seed_elo=dict(seed),
    )

    assert visited == [f"opp{k}" for k in range(N_OPPONENTS)]
    assert report.opponents == N_OPPONENTS
    assert report.boarded_opponents == N_OPPONENTS
    assert cards                                # the sweep produced a deck
    # Sensitivity: the candidate accumulator crosses the live loop's stop
    # threshold well before the last member, so a count-based exit of that
    # shape would have fired mid-sweep. Measured on the PRE-filter
    # accumulator (`report.enumerated`), not on `cards`: fit's §1.9
    # post-score filters (`deck_headliner_cap` in particular) shrink the
    # emitted list for reasons unrelated to the sweep.
    assert report.enumerated > LIVE_LOOP_GLOBAL_TARGET


def test_fit_emits_cards_for_every_member(monkeypatch):
    """Every eligible member reaches the emitted deck.

    `deck_headliner_cap` is switched off for this assertion: it is a
    presentation cap over the RANKED list (`_apply_post_filters` step 6)
    that would drop same-centerpiece cards regardless of which member
    produced them, which is orthogonal to — and would mask — the sweep
    property under test.
    """
    ts._cfg["deck_headliner_cap"] = 0.0
    players, league, user_roster, seed, _rosters = _fixture_league()
    _stub_enumerate_pair(monkeypatch)

    cards, _report = tgf.generate_league_suggestions(
        players=players, league=league, user_id="user",
        user_elo=dict(seed), user_roster=user_roster, seed_elo=dict(seed),
    )

    assert {c.target_user_id for c in cards} == {
        f"opp{k}" for k in range(N_OPPONENTS)}


def test_fit_per_pair_budget_does_not_leak_across_members():
    """The `fit_max_packages_per_pair` budget is per-pair: `_enumerate_pair`
    re-initialises `capped` on every call, so exhausting it for one member
    cannot silence the next. Driven directly, with cap = 1."""
    calls: list[int] = []

    def _kill(_g, _r):
        return None

    def _score(g, r):
        calls.append(1)
        return {"give_ids": list(g), "recv_ids": list(r)}

    report = tgf.FitReport(league_id="L", user_id="user")
    for _member in range(3):
        tgf._enumerate_pair(["u1", "u2"], ["o1", "o2"], _kill, _score,
                            report, 1, 25)
    # One candidate scored per pair — three pairs, three candidates. A
    # leaked `capped` flag would score only on the first pair.
    assert len(calls) == 3
    assert report.capped_pairs == 3


def test_fit_module_has_no_sweep_level_break():
    """Structural companion: the `for member in eligible` body carries no
    `break`."""
    src = open(tgf.__file__, encoding="utf-8").read().splitlines()
    start = next(i for i, line in enumerate(src)
                 if line.strip().startswith("for member in eligible"))
    body = []
    for line in src[start + 1:]:
        if line.strip() and not line.startswith("        "):
            break                       # dedent out of the loop body
        body.append(line)
    offenders = [ln for ln in body
                 if ln.strip() == "break" or ln.strip().startswith("break ")]
    assert offenders == [], offenders
