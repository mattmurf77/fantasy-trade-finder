"""Offline calibration check for the trade-engine v2 ``elo_to_value`` curve.

Tier 1, Change 1 (docs/plans/trade-engine-tier1-fixes.md): the new
Elo→value transform must agree with the existing ``dynasty_value``
(search_rank → KTC-style exponential) curve, so the fairness gate behaves
identically on 1-for-1 trades. Concretely: Spearman rank correlation of
``elo_to_value(seed_elo[p])`` vs ``dynasty_value(p)`` across the live
player pool must be ≥ 0.98.

What this script does (read-only — never writes to the DB):
  1. Rebuilds the player pool + consensus seed Elo the same way the server
     does (DynastyProcess values fetched live, matched by normalised name
     against the synced ``players`` table; elo = 1200 + value/10000 * 600).
  2. For every player with BOTH a seed Elo and a search_rank, computes
     ``dynasty_value(player)`` and ``elo_to_value(seed_elo)``.
  3. Reports Spearman correlation (implemented locally — no scipy), anchor
     rows at several pool depths, and a grid search over ``elo_value_k``.

Note on the grid search: ``elo_to_value`` is strictly monotone in Elo for
any k > 0, so Spearman is mathematically invariant to k — the grid mostly
confirms that. Ties in Spearman are therefore broken by a *level-fit*
metric (median |log10(elo_to_value / dynasty_value)|), which is what k
actually controls (how well the two curves line up in absolute value).

Usage:
    python3 -m backend.scripts.calibrate_elo_value
"""
from __future__ import annotations

import math

from backend.data_loader import _fetch_dynasty_process, normalise_name
from backend.database import load_players
from backend.ranking_service import Player
from backend.trade_service import dynasty_value, reload_config

# ---------------------------------------------------------------------------
# elo_to_value — import from trade_service when available (trade-engine v2
# lands it there); otherwise fall back to a local copy of the same formula.
# ---------------------------------------------------------------------------

DEFAULT_K = 0.0050
DEFAULT_REF = 1500.0
DEFAULT_BASE = 1000.0

try:  # pragma: no cover — depends on whether v2 has landed yet
    from backend.trade_service import elo_to_value as _svc_elo_to_value
except ImportError:
    _svc_elo_to_value = None


def elo_to_value_local(
    elo: float,
    k: float = DEFAULT_K,
    ref: float = DEFAULT_REF,
    base: float = DEFAULT_BASE,
) -> float:
    """value = base * exp(k * (elo - ref)); elo 1500 → 1000 by default."""
    return base * math.exp(k * (elo - ref))


# ---------------------------------------------------------------------------
# Spearman rank correlation (no scipy): rank both lists with average ranks
# for ties, then Pearson on the ranks.
# ---------------------------------------------------------------------------

def _average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # 1-based average rank for the tie run
        for t in range(i, j + 1):
            ranks[order[t]] = avg_rank
        i = j + 1
    return ranks


def spearman(x: list[float], y: list[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        return float("nan")
    rx, ry = _average_ranks(x), _average_ranks(y)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx == 0 or vy == 0:
        return float("nan")
    return cov / math.sqrt(vx * vy)


# ---------------------------------------------------------------------------
# Pool + seed Elo, replicated minimally from server._ensure_universal_pools /
# build_universal_pool (read-only; generic picks excluded — they carry a
# synthetic search_rank and a pick_value-based dynasty value, so they don't
# belong in a players-curve calibration).
# ---------------------------------------------------------------------------

def load_pool_with_seeds(scoring: str = "1qb_ppr") -> list[tuple[Player, float]]:
    """Return [(player, seed_elo)] for every synced player that has a
    DynastyProcess value > 0 (the server's universal-pool membership rule)."""
    elo_map, value_map = _fetch_dynasty_process(scoring=scoring)
    if not elo_map:
        raise SystemExit(
            "DynastyProcess fetch failed — cannot derive consensus seed Elo. "
            "(The server seeds Elo from the live DP values CSV; there is no "
            "offline cache of it.) Re-run with network access."
        )

    db_players = load_players(position=None)
    pool: list[tuple[Player, float]] = []
    for row in db_players:
        pos = (row.get("position") or "").upper()
        if pos not in {"QB", "RB", "WR", "TE"}:
            continue
        name = row.get("full_name") or ""
        normed = normalise_name(name)
        if normed not in value_map:  # no DP value > 0 → not in universal pool
            continue
        player = Player(
            id=str(row["player_id"]),
            name=name,
            position=pos,
            team=row.get("team") or "FA",
            age=row.get("age") or 25,
            search_rank=row.get("search_rank"),
        )
        seed = elo_map.get(normed, 1500.0)
        pool.append((player, seed))
    return pool


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def main() -> None:
    reload_config()  # read model_config so dynasty_value uses live constants

    print("=" * 74)
    print("elo_to_value calibration — trade-engine v2, Tier 1 Change 1")
    print("=" * 74)
    if _svc_elo_to_value is not None:
        svc_val = _svc_elo_to_value(1790.0)
        loc_val = elo_to_value_local(1790.0)
        print(f"trade_service.elo_to_value: AVAILABLE "
              f"(elo 1790 → {svc_val:.1f}; local formula → {loc_val:.1f})")
    else:
        print("trade_service.elo_to_value: not present yet — using local "
              "fallback (same formula, default constants).")

    pool = load_pool_with_seeds("1qb_ppr")
    usable = [
        (p, seed) for p, seed in pool
        if seed is not None and p.search_rank is not None
    ]
    print(f"\nPool: {len(pool)} players with DP value > 0; "
          f"{len(usable)} also have a search_rank (used for calibration).")
    if len(usable) < 50:
        raise SystemExit("Too few usable players to calibrate — aborting.")

    dv = [dynasty_value(p) for p, _ in usable]
    seeds = [seed for _, seed in usable]

    # ── Grid search over elo_value_k ─────────────────────────────────────
    ks = [round(0.003 + 0.0005 * i, 4) for i in range(13)]  # 0.003 … 0.009
    print(f"\nGrid search elo_value_k ∈ [{ks[0]}, {ks[-1]}] step 0.0005 "
          f"(ref={DEFAULT_REF:.0f}, base={DEFAULT_BASE:.0f}):")
    print(f"{'k':>8}  {'spearman':>9}  {'median |log10(ev/dv)|':>22}")
    results: list[tuple[float, float, float]] = []
    for k in ks:
        ev = [elo_to_value_local(s, k=k) for s in seeds]
        rho = spearman(ev, dv)
        logdiffs = sorted(
            abs(math.log10(e / d)) for e, d in zip(ev, dv) if e > 0 and d > 0
        )
        med = logdiffs[len(logdiffs) // 2] if logdiffs else float("nan")
        results.append((k, rho, med))
        marker = "  ← default" if abs(k - DEFAULT_K) < 1e-9 else ""
        print(f"{k:>8.4f}  {rho:>9.5f}  {med:>22.4f}{marker}")

    best_rho = max(r for _, r, _ in results)
    contenders = [r for r in results if abs(r[1] - best_rho) < 1e-9]
    best_k, _, best_med = min(contenders, key=lambda r: r[2])
    default_rho = next(r for k, r, _ in results if abs(k - DEFAULT_K) < 1e-9)
    if len(contenders) == len(results):
        print("\nNote: Spearman is identical at every k — elo_to_value is "
              "strictly monotone in Elo, so rank order never changes. The "
              "k recommendation below is the best *level fit* (anchor "
              "agreement) among the Spearman-maximal ks.")

    print(f"\nSpearman @ default k={DEFAULT_K}:  {default_rho:.5f}")
    print(f"Spearman @ best    k={best_k}:  {best_rho:.5f} "
          f"(median |log10 ratio| {best_med:.4f})")

    # Least-squares level fit: ln(dv) = ln(base) + k*(elo - ref), ref/base
    # fixed at defaults → closed-form k. This is the statistically natural
    # "make the two curves agree in absolute value" answer.
    num = sum((s - DEFAULT_REF) * math.log(d / DEFAULT_BASE)
              for s, d in zip(seeds, dv) if d > 0)
    den = sum((s - DEFAULT_REF) ** 2 for s, d in zip(seeds, dv) if d > 0)
    k_ls = num / den if den else float("nan")
    print(f"Least-squares level-fit k (ref={DEFAULT_REF:.0f}, "
          f"base={DEFAULT_BASE:.0f}): {k_ls:.4f}")
    print(f"Recommended elo_value_k: {best_k} (grid, level-fit tiebreak); "
          f"LS fit suggests {k_ls:.4f}")

    # ── Anchor rows ──────────────────────────────────────────────────────
    by_rank = sorted(usable, key=lambda t: t[0].search_rank)
    anchor_idx = [0, 4, 23, 59, 119, 249]
    print(f"\nAnchors (pool sorted by search_rank; elo_to_value at default "
          f"k={DEFAULT_K} and best k={best_k}):")
    print(f"{'pool#':>5}  {'name':<24} {'srch_rk':>7}  {'dynasty_v':>9}  "
          f"{'ev@default':>10}  {'ev@best':>9}")
    for idx in anchor_idx:
        if idx >= len(by_rank):
            continue
        p, seed = by_rank[idx]
        print(f"{idx + 1:>5}  {p.name:<24.24} {p.search_rank:>7}  "
              f"{dynasty_value(p):>9.1f}  "
              f"{elo_to_value_local(seed, k=DEFAULT_K):>10.1f}  "
              f"{elo_to_value_local(seed, k=best_k):>9.1f}")

    # ── PASS/FAIL ────────────────────────────────────────────────────────
    threshold = 0.98
    verdict = "PASS" if default_rho >= threshold else "FAIL"
    print(f"\n{verdict}: Spearman(elo_to_value(seed), dynasty_value) = "
          f"{default_rho:.5f} (threshold ≥ {threshold})")
    if verdict == "FAIL":
        print("  → seed Elo (DynastyProcess values) and search_rank "
              "(Sleeper's rank proxy) disagree on player ordering more than "
              "the Tier 1 plan assumed. See anchor rows above for where.")


if __name__ == "__main__":
    main()
