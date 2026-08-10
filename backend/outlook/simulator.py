"""Phase 3 — Monte-Carlo season simulator (pure, deterministically seeded).

`simulate()` takes settled facts (LeagueState), a per-team scoring model
(dict[roster_id → TeamStrength]) and a PlayoffFormat, and returns aggregate
odds. It performs NO I/O and reads NO clock.

Determinism (repo rule — deterministic & resumable)
---------------------------------------------------
The RNG is a single explicitly-seeded `random.Random` instance. The seed is
`stable_hash(league_id) ^ config_seed`. We deliberately do NOT use Python's
builtin `hash()` (it is per-process salted by PYTHONHASHSEED, which would break
resumability across processes/restarts) — `stable_hash` is a SHA-256-derived
stable integer. We never touch the global `random` module state, `time`, or
`datetime.now`. Same (league_id, config_seed, inputs) → byte-identical result.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .league_state import LeagueState
from .playoff_format import PlayoffFormat
from .strength import TeamStrength

DEFAULT_SIMS = 10000


def stable_hash(text: str) -> int:
    """Process-stable 64-bit hash (unlike builtin hash())."""
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


@dataclass
class SimResult:
    n_sims: int
    seed: int
    # roster_id -> aggregate counters
    made_playoffs: dict[int, int] = field(default_factory=dict)
    byes: dict[int, int] = field(default_factory=dict)
    titles: dict[int, int] = field(default_factory=dict)
    sum_wins: dict[int, float] = field(default_factory=dict)
    sum_seed: dict[int, float] = field(default_factory=dict)
    # Remaining weeks the platform published no pairings for, which were
    # re-paired at random (pre-draft leagues only — see league_state.py).
    random_paired_weeks: list[int] = field(default_factory=list)

    def playoff_pct(self, rid: int) -> float:
        return self.made_playoffs.get(rid, 0) / self.n_sims

    def bye_pct(self, rid: int) -> float:
        return self.byes.get(rid, 0) / self.n_sims

    def title_pct(self, rid: int) -> float:
        return self.titles.get(rid, 0) / self.n_sims

    def projected_wins(self, rid: int) -> float:
        return self.sum_wins.get(rid, 0.0) / self.n_sims

    def projected_seed(self, rid: int) -> float:
        return self.sum_seed.get(rid, 0.0) / self.n_sims


def simulate(
    state: LeagueState,
    strengths: dict[int, TeamStrength],
    fmt: PlayoffFormat,
    *,
    n_sims: int = DEFAULT_SIMS,
    config_seed: int = 0,
    weekly_mu_multiplier: dict[int, dict[int, float]] | None = None,
) -> SimResult:
    """Run N seeded season simulations. Pure — no I/O, no clock.

    `weekly_mu_multiplier` (week -> roster_id -> multiplier) is an OPTIONAL
    seam for evaluated-but-unshipped strength variants (e.g. the #169
    bye-week multiplier in `bye_multiplier.py`) — left `None` by every live
    caller, which reproduces the exact draw sequence as if the parameter
    didn't exist. When a roster/week isn't in the map its multiplier is 1.0
    (no change). Regular season only — the playoff bracket always draws at
    the team's flat mu, since byes never overlap the postseason."""
    seed = stable_hash(state.league_id) ^ int(config_seed)
    rng = random.Random(seed)

    roster_ids = [t.roster_id for t in state.teams]
    base_wins = {t.roster_id: t.win_credit for t in state.teams}
    base_pf = {t.roster_id: t.points_for for t in state.teams}
    division = {t.roster_id: t.division for t in state.teams}
    remaining = state.remaining_weeks()
    # Precompute remaining pairings. A scheduled league publishes its full
    # remaining pairing graph, so this is the REAL schedule; the random
    # round-robin fallback fires only for weeks with no pairings at all
    # (pre-draft leagues — see league_state.py).
    remaining_pairs = _remaining_pairings(state, remaining, roster_ids, rng)
    # Sleeper's median match: each week also books a decision against the
    # league median score, so the base standings arrive on a 2-per-week scale
    # and the simulation must increment on that same scale (BUG-1 / G-024).
    median_match = bool(state.median_match)

    res = SimResult(n_sims=n_sims, seed=seed,
                    random_paired_weeks=state.unscheduled_weeks())
    for rid in roster_ids:
        res.made_playoffs[rid] = 0
        res.byes[rid] = 0
        res.titles[rid] = 0
        res.sum_wins[rid] = 0.0
        res.sum_seed[rid] = 0.0

    gauss = rng.gauss
    mu = {rid: strengths[rid].mu for rid in roster_ids}
    sig = {rid: strengths[rid].sigma for rid in roster_ids}
    wmm = weekly_mu_multiplier or None

    for _ in range(n_sims):
        wins = dict(base_wins)
        pf = dict(base_pf)
        # Regular-season remainder
        for week, pairs in zip(remaining, remaining_pairs):
            week_mult = wmm.get(week) if wmm else None
            week_scores = {} if median_match else None
            for a, b in pairs:
                ma = mu[a] * week_mult[a] if week_mult and a in week_mult else mu[a]
                mb = mu[b] * week_mult[b] if week_mult and b in week_mult else mu[b]
                sa = gauss(ma, sig[a])
                sb = gauss(mb, sig[b])
                pf[a] += sa
                pf[b] += sb
                if sa > sb:
                    wins[a] += 1
                elif sb > sa:
                    wins[b] += 1
                else:
                    wins[a] += 0.5
                    wins[b] += 0.5
                if week_scores is not None:
                    week_scores[a] = sa
                    week_scores[b] = sb
            if week_scores:
                # Second decision of the week: every team versus the league
                # median of THIS simulated week's drawn scores. Draws no extra
                # randomness, so a non-median league's draw sequence — and
                # therefore its odds — are byte-identical to before.
                med = _median(week_scores.values())
                for rid, s in week_scores.items():
                    if s > med:
                        wins[rid] += 1
                    elif s == med:
                        wins[rid] += 0.5
        # Seed
        standings = [(rid, wins[rid], pf[rid], division[rid]) for rid in roster_ids]
        seed_order = fmt.seed(standings)
        for rank, rid in enumerate(seed_order, start=1):
            res.sum_seed[rid] += rank
            res.sum_wins[rid] += wins[rid]
        field_ids = seed_order[:fmt.playoff_slots]
        for rid in field_ids:
            res.made_playoffs[rid] += 1
        for rid in field_ids[:fmt.num_byes]:
            res.byes[rid] += 1
        # Bracket — fresh score draw per playoff game
        champ = fmt.champion(seed_order, lambda rid: gauss(mu[rid], sig[rid]))
        if champ in res.titles:
            res.titles[champ] += 1
    return res


def _median(values) -> float:
    """Median of the week's drawn scores — Sleeper's median-match opponent.
    Even team counts average the two middle scores, matching Sleeper (verified
    to reproduce all 24 median-league rosters' real records)."""
    vals = sorted(values)
    n = len(vals)
    if n % 2:
        return vals[n // 2]
    return (vals[n // 2 - 1] + vals[n // 2]) / 2.0


def _remaining_pairings(state, remaining_weeks, roster_ids, rng):
    """Pairings for each remaining week. Uses the real published schedule where
    present — which, on a scheduled Sleeper league, is EVERY remaining week
    (validated 2026-08-09, 18/18 weeks on an unplayed league). The random
    round-robin fallback fires only for a week the platform publishes no
    pairings for at all, i.e. a `pre_draft` league; `SimResult.
    random_paired_weeks` records exactly which weeks took that path."""
    out = []
    for week in remaining_weeks:
        pairs = state.schedule.get(week)
        if pairs:
            out.append([(int(a), int(b)) for a, b in pairs])
        else:
            out.append(_random_pairing(roster_ids, rng))
    return out


def _random_pairing(roster_ids, rng):
    ids = list(roster_ids)
    rng.shuffle(ids)
    return [(ids[i], ids[i + 1]) for i in range(0, len(ids) - 1, 2)]


# ---------------------------------------------------------------------------
# Protocol wrapper — so the simulator is swappable behind a stable interface
# (e.g. a future closed-form / analytic estimator) just like the other phases.
# ---------------------------------------------------------------------------

class Simulator(Protocol):
    def run(self, state: LeagueState, strengths: dict[int, TeamStrength],
            fmt: PlayoffFormat, *, n_sims: int, config_seed: int) -> SimResult:
        ...


class MonteCarloSimulator:
    name = "monte_carlo"

    def run(self, state, strengths, fmt, *, n_sims=DEFAULT_SIMS, config_seed=0):
        return simulate(state, strengths, fmt,
                        n_sims=n_sims, config_seed=config_seed)


SIMULATORS: dict[str, type] = {"monte_carlo": MonteCarloSimulator}


def get_simulator(key: str = "monte_carlo") -> Simulator:
    factory = SIMULATORS.get((key or "monte_carlo").lower())
    if factory is None:
        raise KeyError(f"no Simulator registered for {key!r}")
    return factory()
