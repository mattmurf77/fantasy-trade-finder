"""`trade.full_sweep` — score every leaguemate, then rank globally.

docs/plans/full-sweep/plan.md §3 and §5. Both opponent loops in
`backend/trade_service.py` stop as soon as the deck holds
`global_target = max(30, max_per_opponent * 6)` cards, checked AFTER each
opponent's whole batch lands. Visit order is fixed (boarded members first,
then roster order), so in a 12-team league it is the SAME five leaguemates
that are never scored, on every refresh. The flag skips that early exit in
both loops; `_dedup_and_sort` already sorts the whole collected set by
`composite_score`, so a complete sweep IS the global rank — no new ranking
code.

What is pinned here
-------------------
1. Flag OFF, both loops: the visit count equals what today's `global_target`
   arithmetic implies (recomputed from the same formula, not a magic number)
   and is strictly fewer than the eligible members — the break still fires.
2. Flag ON, both loops: every eligible member is visited.
3. Global ranking: the member visited LAST holds the best card, and with the
   flag on it comes back first.
4. Streaming: `on_opponent_done` fires once per eligible member, with `idx`
   strictly increasing, `total` constant, and a snapshot that never shrinks.
5. Both loops — 1 and 2 are parametrised over `trade_engine.v2` off (the
   legacy `_generate_trades_impl` loop) and on (the served
   `_generate_trades_v2` loop).
6. The `exploration_base_per_opp` knob: `_split_exploration_pool` keeps that
   many cards per opponent, the default 5.0 reproduces the pre-knob hardcoded
   `server._EXPLORATION_BASE_PER_OPP` split exactly, and both live read sites
   go through the knob CLAMPED at 1 (a knob of 0 would serve an empty deck).
7. The flag-on wall-clock rail `full_sweep_budget_s` (plan §3.5): it stops the
   sweep between opponents once the budget is spent, `<= 0` disables it, and
   with the flag OFF it never runs at all — the v3 pair path carries no
   deadline of its own, so this is the only ceiling under the 60 s
   `_JOB_HARD_TIMEOUT`.

The per-pair generators are stubbed, so these tests assert loop CONTROL FLOW
(who gets visited, in what order, what the callback sees) and nothing about
package construction — which is the whole of what this change touches.

Sabotage proof (plan §5 item 7)
------------------------------
Every test below was RUN against the engine edit named beside it, observed to
fail, and observed to pass again once reverted. Each sabotage is one line.

HOW TO REVERT A SABOTAGE. Take a byte copy of the file BEFORE editing it
(`cp backend/trade_service.py /tmp/ts.bak`, restore with `cp /tmp/ts.bak
backend/trade_service.py`), or commit first and revert that one file. Do NOT
reach for `git checkout -- <file>`: while this work is uncommitted that
discards the whole feature, not the sabotage.

Flag-OFF tests — neuter the card-count exit entirely, so the sweep completes
when it should not (`trade_service.py`, the named loop):

* `test_flag_off_stops_at_the_global_target[legacy]` — legacy loop:
  `if not FLAGS.trade_full_sweep and _over_target:` → `if False:`
  ⇒ visits 12, expected 6. FAILED as required.
* `test_flag_off_stops_at_the_global_target[v2]` — the same edit at the
  `_generate_trades_v2` exit. FAILED as required (and took
  `test_flag_on_ranks_the_whole_league_globally` with it, via its flag-off
  precondition).

Flag-ON tests — drop the guard, restoring the unconditional break
(`if not FLAGS.trade_full_sweep and _over_target:` → `if _over_target:`):

* `test_flag_on_visits_every_member[legacy]` — legacy site. FAILED (6 of 12).
* `test_flag_on_visits_every_member[v2]` — live site. FAILED, and with it
  `test_flag_on_ranks_the_whole_league_globally` (the boosted last member is
  never reached) and `test_streaming_fires_once_per_eligible_member` (the
  callback fires 6 times, not 12).

Wall-clock rail (B1) — `trade_service.py`, both loops:

* `test_full_sweep_budget_stops_the_sweep[legacy]` / `[v2]` — delete the
  `if FLAGS.trade_full_sweep and _c("full_sweep_budget_s") > 0 …` branch from
  that loop. Each deletion was run separately; each FAILED (12 visits, 2
  expected).
* `test_full_sweep_budget_of_zero_disables_the_rail[legacy]` / `[v2]` — drop
  the disable: `and _c("full_sweep_budget_s") > 0` → `and True`. FAILED.
* `test_the_budget_rail_never_runs_with_the_flag_off` — drop the flag from
  the rail: `if FLAGS.trade_full_sweep and _c("full_sweep_budget_s") > 0` →
  `if _c("full_sweep_budget_s") > 0`. FAILED — this is the one that proves
  the rail cannot move the flag-off path.
* `test_the_budget_knob_is_seeded_in_the_database_defaults` — same shape as
  the seeding test below.

Knob tests:

* `test_exploration_base_per_opp_is_honoured` — `server._split_exploration_pool`:
  `if n < base_per_opp:` → `if n < 5:`  ⇒ keeps 5, expected 3. FAILED.
* `test_every_server_read_of_the_constant_goes_through_the_clamped_knob` —
  three separate reverts at the two live read sites, each run on its own and
  each FAILED: (a) drop the `max(1, …)` clamp at the over-generation site,
  (b) drop it at the split site, (c) revert the split site to the bare
  `_EXPLORATION_BASE_PER_OPP`. This test is the ONLY thing that catches those
  reverts — `test_exploration_base_per_opp_of_zero_behaves_as_one` computes
  the clamp itself and does not touch the call sites, which is why the
  structural pin exists rather than a behavioural one.
* `test_exploration_base_per_opp_default_reproduces_the_constant` —
  `trade_service._DEFAULT_CFG`: `"exploration_base_per_opp": 5.0` → `3.0`
  (FAILED), and deleting the row entirely (FAILED, KeyError).
* `test_the_knob_is_seeded_in_the_database_defaults` —
  `database._MODEL_CONFIG_DEFAULTS`: the seeded `5.0` → `3.0`. FAILED.
"""

import pytest

import backend.feature_flags as ff
import backend.server as server
import backend.trade_optimizer as topt
import backend.trade_service as ts
from backend.trade_service import League, LeagueMember, TradeCard, TradeService

# ── fixture — 12 opponents, all boarded, minimal but real players ──────────
# 12-team league = the league in the field report: 11 opponents plus the
# viewer. `max_per_opponent` 5 and 5 cards per member reproduce the shipped
# arithmetic exactly (global_target 30 ⇒ the break fires after 6 members).

_N_OPPONENTS = 12
_PER_MEMBER = 5
_MAX_PER_OPP = 5
_POSITIONS = ("QB", "RB", "RB", "WR", "WR", "TE")


class _Player:
    def __init__(self, pid, position="WR"):
        self.id = pid
        self.name = f"Player {pid}"
        self.position = position
        self.team = "TST"
        self.age = 24
        self.ktc_value = None
        self.pick_value = None
        self.years_experience = 3
        self.search_rank = 50


def _expected_visits_today(n_members, per_member, max_per_opp):
    """The number of opponents today's code visits, recomputed from the
    SHIPPED formula rather than pinned as a literal — if the arithmetic in
    `trade_service` changes, this moves with it and the test still means
    'flag off is what it was'."""
    global_target = max(30, max_per_opp * 6)
    banked = 0
    for visited in range(1, n_members + 1):
        banked += per_member
        if banked >= global_target:
            return visited
    return n_members


def _fixture():
    """One league: `user` plus `_N_OPPONENTS` boarded opponents. Every id is
    a real entry in `players`, because the loop stamps narrative / lane-shift
    on each card and those read the player table."""
    players, seed = {}, {}
    user_roster = []
    for i, pos in enumerate(_POSITIONS):
        pid = f"u{i}"
        players[pid] = _Player(pid, pos)
        seed[pid] = 1500.0
        user_roster.append(pid)

    members = []
    for n in range(_N_OPPONENTS):
        roster = []
        for i, pos in enumerate(_POSITIONS):
            pid = f"o{n:02d}_{i}"
            players[pid] = _Player(pid, pos)
            seed[pid] = 1500.0
            roster.append(pid)
        members.append(LeagueMember(
            user_id=f"opp{n:02d}", username=f"opp{n:02d}", roster=roster,
            elo_ratings={pid: 1500.0 for pid in roster}, has_rankings=True))

    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=members))
    user_elo = dict(seed)
    return svc, user_elo, user_roster, seed, members


def _set_flags(**kw):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update(kw)
    ff._flags_cache = cache


def _reset_cfg(**cfg):
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg.update(cfg)


@pytest.fixture(autouse=True)
def _isolate():
    """config/features.json state and live knob edits must never leak in or
    out of these tests."""
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


# ── per-pair stubs ────────────────────────────────────────────────────────
# Stubbing the generators is what makes this a LOOP test: it removes package
# construction, gates and timing from the picture, so a changed visit count
# can only come from the loop's early exit.
#
# Three seams, because the two loops route differently:
#   legacy  → TradeService._generate_for_pair
#   v2/v3   → trade_optimizer.generate_pair_trades_v3, which the live loop
#             imports lazily INSIDE the loop body (`from .trade_optimizer
#             import generate_pair_trades_v3` — a module-level import would
#             cycle), so the binding it resolves is the attribute on
#             `backend.trade_optimizer` and that is where the patch belongs.
#   consensus fallback → TradeService._generate_consensus_for_pair, patched
#             too so a member that somehow takes the unboarded branch is
#             still counted rather than silently yielding nothing.


class _Recorder:
    """Records the visit order and hands out `_PER_MEMBER` cards per call."""

    def __init__(self, boost_last_member_id=None):
        self.visits = []
        self._boost = boost_last_member_id

    def cards_for(self, opponent, user_roster):
        out = []
        for i in range(_PER_MEMBER):
            # 0.5 .. 0.9, and every member ties — so ONLY the boosted card
            # can lead the deck, and only if its member was visited.
            score = 0.9 - 0.1 * i
            if self._boost == opponent.user_id and i == 0:
                score = 9.9
            out.append(TradeCard(
                trade_id=f"{opponent.user_id}-{i}",
                league_id="L1",
                proposing_user_id="user",
                target_user_id=opponent.user_id,
                target_username=opponent.username,
                give_player_ids=[user_roster[i % len(user_roster)]],
                receive_player_ids=[opponent.roster[i % len(opponent.roster)]],
                mismatch_score=100.0,
                fairness_score=0.9,
                composite_score=score,
            ))
        return out


def _install_stubs(monkeypatch, rec, user_roster):
    def _legacy(self, *, opponent, **kw):
        rec.visits.append(opponent.user_id)
        return rec.cards_for(opponent, user_roster)

    def _v3(*, opponent, **kw):
        rec.visits.append(opponent.user_id)
        return rec.cards_for(opponent, user_roster)

    def _consensus(self, *, opponent, **kw):
        rec.visits.append(opponent.user_id)
        return rec.cards_for(opponent, user_roster)

    monkeypatch.setattr(TradeService, "_generate_for_pair", _legacy)
    monkeypatch.setattr(TradeService, "_generate_consensus_for_pair",
                        _consensus)
    monkeypatch.setattr(topt, "generate_pair_trades_v3", _v3)


def _run(monkeypatch, *, engine_v2, full_sweep, boost=None,
         on_opponent_done=None):
    """One generation call under the requested loop + flag combination."""
    flags = {"trade.full_sweep": full_sweep}
    if engine_v2:
        # v3 on so the boarded branch routes through generate_pair_trades_v3,
        # the seam the plan names.
        flags["trade_engine.v2"] = True
        flags["trade_engine.v3"] = True
    _set_flags(**flags)
    _reset_cfg()
    svc, user_elo, user_roster, seed, members = _fixture()
    rec = _Recorder(boost_last_member_id=boost)
    _install_stubs(monkeypatch, rec, user_roster)
    cards = svc.generate_trades(
        user_id="user", user_elo=user_elo, user_roster=user_roster,
        league_id="L1", seed_elo=seed, fairness_threshold=0.6,
        max_per_opponent=_MAX_PER_OPP, is_dynasty=True,
        on_opponent_done=on_opponent_done)
    return rec, cards, members


# ── 1 + 5 — flag OFF is today, on both loops ──────────────────────────────

@pytest.mark.parametrize("engine_v2, loop", [(False, "legacy"), (True, "v2")],
                         ids=["legacy", "v2"])
def test_flag_off_stops_at_the_global_target(monkeypatch, engine_v2, loop):
    """OFF ⇒ the break still fires at exactly the count today's arithmetic
    implies, and most of the league is never scored."""
    expected = _expected_visits_today(_N_OPPONENTS, _PER_MEMBER, _MAX_PER_OPP)
    assert expected < _N_OPPONENTS, (
        "fixture no longer reproduces the field condition — the break must "
        "trip before the sweep completes for this test to mean anything")

    rec, _cards, _members = _run(monkeypatch, engine_v2=engine_v2,
                                 full_sweep=False)
    assert len(rec.visits) == expected, (
        f"{loop} loop, flag OFF: visited {len(rec.visits)} opponents, "
        f"today's global_target arithmetic implies {expected}")


# ── 2 + 5 — flag ON sweeps the whole league, on both loops ────────────────

@pytest.mark.parametrize("engine_v2, loop", [(False, "legacy"), (True, "v2")],
                         ids=["legacy", "v2"])
def test_flag_on_visits_every_member(monkeypatch, engine_v2, loop):
    rec, _cards, members = _run(monkeypatch, engine_v2=engine_v2,
                                full_sweep=True)
    assert len(rec.visits) == _N_OPPONENTS, (
        f"{loop} loop, flag ON: visited {len(rec.visits)} of "
        f"{_N_OPPONENTS} eligible opponents")
    assert set(rec.visits) == {m.user_id for m in members}


# ── 3 — the sweep IS the global rank ──────────────────────────────────────

def test_flag_on_ranks_the_whole_league_globally(monkeypatch):
    """The best card in the league belongs to the member visited LAST — the
    one today's break guarantees is never reached. With the flag on it leads
    the deck; the ordering itself comes from `_dedup_and_sort`, unchanged."""
    last_member = f"opp{_N_OPPONENTS - 1:02d}"

    rec_off, cards_off, _ = _run(monkeypatch, engine_v2=True,
                                 full_sweep=False, boost=last_member)
    assert last_member not in rec_off.visits, (
        "fixture drift: the boosted member must be unreachable with the "
        "flag off, or the ON assertion below proves nothing")
    assert all(c.target_user_id != last_member for c in cards_off)

    rec_on, cards_on, _ = _run(monkeypatch, engine_v2=True,
                               full_sweep=True, boost=last_member)
    assert rec_on.visits[-1] == last_member
    assert cards_on, "flag ON produced no cards"
    assert cards_on[0].target_user_id == last_member
    assert cards_on[0].composite_score == max(c.composite_score
                                              for c in cards_on)


# ── 4 — streaming fires per opponent, and the snapshot only grows ─────────

def test_streaming_fires_once_per_eligible_member(monkeypatch):
    seen = []

    def _cb(idx, total, snapshot):
        seen.append((idx, total, len(snapshot)))

    rec, _cards, _members = _run(monkeypatch, engine_v2=True,
                                 full_sweep=True, on_opponent_done=_cb)

    assert len(seen) == _N_OPPONENTS == len(rec.visits)
    assert [s[0] for s in seen] == list(range(1, _N_OPPONENTS + 1))
    assert {s[1] for s in seen} == {_N_OPPONENTS}
    sizes = [s[2] for s in seen]
    assert all(b >= a for a, b in zip(sizes, sizes[1:])), (
        f"streaming snapshot shrank between opponents: {sizes}")


# ── B1 — the flag-on wall-clock rail ──────────────────────────────────────
# Removing the card-count exit removes the only practical ceiling on a job:
# `trade_optimizer.generate_pair_trades_v3` has no deadline of its own
# (trade_optimizer.py:231), so `full_sweep_budget_s` is what stands between a
# slow league and `_JOB_HARD_TIMEOUT`.


def _clock_from(rec, seconds_per_member):
    """A monotonic clock driven by the sweep's own progress rather than by
    call count — the loop calls `monotonic()` an unspecified number of times
    per opponent, so anything counting calls would be pinning an accident."""
    return lambda: seconds_per_member * len(rec.visits)


@pytest.mark.parametrize("engine_v2, loop", [(False, "legacy"), (True, "v2")],
                         ids=["legacy", "v2"])
def test_full_sweep_budget_stops_the_sweep(monkeypatch, engine_v2, loop):
    """20 s per opponent against a 30 s budget: the check runs BETWEEN
    opponents, so opponent 1 lands at t=20 (under budget, continue) and
    opponent 2 at t=40 (over, stop). Two members visited, not twelve."""
    _set_flags(**({"trade.full_sweep": True}
                  | ({"trade_engine.v2": True, "trade_engine.v3": True}
                     if engine_v2 else {})))
    _reset_cfg(full_sweep_budget_s=30.0)
    svc, user_elo, user_roster, seed, _members = _fixture()
    rec = _Recorder()
    _install_stubs(monkeypatch, rec, user_roster)
    monkeypatch.setattr(ts.time, "monotonic", _clock_from(rec, 20.0))

    svc.generate_trades(
        user_id="user", user_elo=user_elo, user_roster=user_roster,
        league_id="L1", seed_elo=seed, fairness_threshold=0.6,
        max_per_opponent=_MAX_PER_OPP, is_dynasty=True)

    assert len(rec.visits) == 2, (
        f"{loop} loop: budget 30 s at 20 s/opponent should stop after 2, "
        f"visited {len(rec.visits)}")


@pytest.mark.parametrize("engine_v2, loop", [(False, "legacy"), (True, "v2")],
                         ids=["legacy", "v2"])
def test_full_sweep_budget_of_zero_disables_the_rail(monkeypatch, engine_v2,
                                                     loop):
    """<= 0 is the documented disable. Same absurd clock, whole league swept
    — so the rail is a knob, not a second hardcoded ceiling."""
    _set_flags(**({"trade.full_sweep": True}
                  | ({"trade_engine.v2": True, "trade_engine.v3": True}
                     if engine_v2 else {})))
    _reset_cfg(full_sweep_budget_s=0.0)
    svc, user_elo, user_roster, seed, _members = _fixture()
    rec = _Recorder()
    _install_stubs(monkeypatch, rec, user_roster)
    monkeypatch.setattr(ts.time, "monotonic", _clock_from(rec, 20.0))

    svc.generate_trades(
        user_id="user", user_elo=user_elo, user_roster=user_roster,
        league_id="L1", seed_elo=seed, fairness_threshold=0.6,
        max_per_opponent=_MAX_PER_OPP, is_dynasty=True)

    assert len(rec.visits) == _N_OPPONENTS, (
        f"{loop} loop: budget 0 must disable the rail, visited "
        f"{len(rec.visits)} of {_N_OPPONENTS}")


def test_the_budget_rail_never_runs_with_the_flag_off(monkeypatch):
    """Flag off, an absurd clock, and a 1 s budget: the sweep must still stop
    on the CARD COUNT at today's number, proving the rail is inside the
    `FLAGS.trade_full_sweep` short-circuit and cannot move the flag-off
    path."""
    expected = _expected_visits_today(_N_OPPONENTS, _PER_MEMBER, _MAX_PER_OPP)
    _set_flags(**{"trade_engine.v2": True, "trade_engine.v3": True})
    _reset_cfg(full_sweep_budget_s=1.0)
    svc, user_elo, user_roster, seed, _members = _fixture()
    rec = _Recorder()
    _install_stubs(monkeypatch, rec, user_roster)
    monkeypatch.setattr(ts.time, "monotonic", _clock_from(rec, 1000.0))

    svc.generate_trades(
        user_id="user", user_elo=user_elo, user_roster=user_roster,
        league_id="L1", seed_elo=seed, fairness_threshold=0.6,
        max_per_opponent=_MAX_PER_OPP, is_dynasty=True)

    assert len(rec.visits) == expected


def test_the_budget_knob_is_seeded_in_the_database_defaults():
    import backend.database as db
    rows = {k: v for k, v, _ in db._MODEL_CONFIG_DEFAULTS}
    assert rows["full_sweep_budget_s"] == \
        ts._DEFAULT_CFG["full_sweep_budget_s"] == 30.0


# ── 6 — the exploration_base_per_opp knob ─────────────────────────────────

class _Card:
    def __init__(self, target):
        self.target_user_id = target


def _overgenerated(n_opponents=3, per_opp=8):
    return [_Card(f"opp{n}") for n in range(n_opponents)
            for _ in range(per_opp)]


def test_exploration_base_per_opp_is_honoured(monkeypatch):
    """Set the knob to 3 and the served split keeps 3 per opponent — the
    point of the knob is that the per-opponent keep is settable without a
    deploy (it was `server._EXPLORATION_BASE_PER_OPP`, hardcoded)."""
    _reset_cfg(exploration_base_per_opp=3.0)
    base = int(server._deck_cfg("exploration_base_per_opp",
                                server._EXPLORATION_BASE_PER_OPP))
    assert base == 3

    deck, pool = server._split_exploration_pool(_overgenerated(), base)
    per_opp = {}
    for c in deck:
        per_opp[c.target_user_id] = per_opp.get(c.target_user_id, 0) + 1
    assert set(per_opp.values()) == {3}
    assert len(deck) == 9 and len(pool) == 15


def test_exploration_base_per_opp_of_zero_behaves_as_one():
    """S3 — the read sites clamp at 1. Unclamped, a knob of 0 keeps NOTHING
    per opponent: the whole deck falls into the wildcard pool and the user is
    served an empty deck by a config typo."""
    _reset_cfg(exploration_base_per_opp=0.0)
    base = max(1, int(server._deck_cfg("exploration_base_per_opp",
                                       server._EXPLORATION_BASE_PER_OPP)))
    assert base == 1

    deck, pool = server._split_exploration_pool(_overgenerated(), base)
    assert len(deck) == 3 and len(pool) == 21, (
        "clamped to 1 per opponent, so 3 opponents keep 3 cards total")

    # …and the unclamped read is what the clamp exists to prevent.
    raw = int(server._deck_cfg("exploration_base_per_opp",
                               server._EXPLORATION_BASE_PER_OPP))
    empty_deck, _ = server._split_exploration_pool(_overgenerated(), raw)
    assert empty_deck == []


def test_exploration_base_per_opp_default_reproduces_the_constant():
    """At the shipped default the knob is byte-identical to the constant it
    replaced — nothing moves at ship."""
    _reset_cfg()
    assert ts._DEFAULT_CFG["exploration_base_per_opp"] == 5.0
    base = int(server._deck_cfg("exploration_base_per_opp",
                                server._EXPLORATION_BASE_PER_OPP))
    assert base == server._EXPLORATION_BASE_PER_OPP

    cards = _overgenerated()
    knob_deck, knob_pool = server._split_exploration_pool(list(cards), base)
    const_deck, const_pool = server._split_exploration_pool(
        list(cards), server._EXPLORATION_BASE_PER_OPP)
    assert knob_deck == const_deck and knob_pool == const_pool


def test_every_server_read_of_the_constant_goes_through_the_clamped_knob():
    """The two live reads are deep inside `_run_trade_job` (the
    over-generation width, then the served trim) and are not reachable from a
    unit test, so pin them structurally rather than pretend otherwise. Two
    properties, both regressions A3 asked for:

      * `_EXPLORATION_BASE_PER_OPP` may appear ONLY as the fallback argument
        of `_deck_cfg("exploration_base_per_opp", ...)` — revert either site
        to the bare constant and the knob is unsettable there;
      * every such read is wrapped `max(1, int(...))` — S3: a knob of 0 would
        otherwise empty the served deck into the wildcard pool.
    """
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path(server.__file__).read_text())

    def _is_knob_read(node):
        return (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_deck_cfg"
                and len(node.args) == 2
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "exploration_base_per_opp")

    reads = [n for n in ast.walk(tree) if _is_knob_read(n)]
    assert len(reads) == 2, (
        f"expected exactly the two documented knob reads, found {len(reads)}")

    # Only the fallback slot of a knob read may name the constant.
    allowed = {id(r.args[1]) for r in reads}
    stray = [n.lineno for n in ast.walk(tree)
             if isinstance(n, ast.Name)
             and n.id == "_EXPLORATION_BASE_PER_OPP"
             and isinstance(n.ctx, ast.Load)
             and id(n) not in allowed]
    assert not stray, (
        f"server.py reads the hardcoded _EXPLORATION_BASE_PER_OPP directly at "
        f"line(s) {stray}. Every read must be "
        f'_deck_cfg("exploration_base_per_opp", _EXPLORATION_BASE_PER_OPP) or '
        "the knob is unsettable at that site and the deploy-free claim is "
        "false.")

    # …and each read is clamped: max(1, int(<knob read>)).
    clamped = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "max"
                and len(node.args) == 2
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == 1):
            continue
        inner = node.args[1]
        if (isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "int"
                and len(inner.args) == 1
                and _is_knob_read(inner.args[0])):
            clamped.add(id(inner.args[0]))

    unclamped = sorted(r.lineno for r in reads if id(r) not in clamped)
    assert not unclamped, (
        f"exploration_base_per_opp is read unclamped at line(s) {unclamped}. "
        "Each read must be max(1, int(_deck_cfg(...))) — at 0 the split keeps "
        "nothing per opponent and the user is served an empty deck by a "
        "config typo.")


def test_the_knob_is_seeded_in_the_database_defaults():
    """A knob with no `model_config` row cannot be flipped remotely, which is
    what would make the deploy-free claim theater."""
    import backend.database as db
    rows = {k: v for k, v, _ in db._MODEL_CONFIG_DEFAULTS}
    assert rows["exploration_base_per_opp"] == \
        ts._DEFAULT_CFG["exploration_base_per_opp"]
