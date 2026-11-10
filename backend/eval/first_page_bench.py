"""Operator benchmark: page-first retrieval versus the full bilateral solve.

    python -m backend.eval.first_page_bench [--seeds 7,11,23] [--teams 12] [--k 30] [--first 5]
                                            [--generator candidate|bilateral] [--no-full]

Per seed of ``synthetic_league.build`` prints one JSON object: full-solve
seconds (unless ``--no-full``); first-page best-of-5 totals
``cold_total_ms`` / ``warm_total_ms`` with their stage breakdowns
``*_stages_ms`` (setup, pools, screen, verify, rank) - COLD clears the
process-wide lineup and tier-coordinate memos before each run, WARM means the
process has served this league and viewer before; progressive delivery from
one ``PageSearch``: best-of-5 time to the first ``--first`` cards
(``*_first_<n>_ms``) and then to all k (``*_then_<k>_ms``), cold and warm;
the universe/bounded/priced/verified counts, ``complete``, memo entries, and
overlap@k plus exact-order match against the full generator's first k. Synthetic data only; no server, database, provider or
network access.
"""

import argparse
import json
from time import perf_counter

from .. import trade_first_page, trade_gen_bilateral, trade_gen_bilateral_candidate
from . import synthetic_league

_GENERATORS = {"candidate": trade_gen_bilateral_candidate, "bilateral": trade_gen_bilateral}
_REPEATS = 5


def _identity(card):
    return card.target_user_id, tuple(card.give_player_ids), tuple(card.receive_player_ids)


def _best(run, cold):
    """Best of ``_REPEATS`` by total; ``run()`` returns (cards, report dict)."""
    best = page = None
    if not cold:
        run()
    for _ in range(_REPEATS):
        if cold:
            trade_first_page._LINEUP_MEMO.clear()
            trade_first_page._COORDINATE_MEMO.clear()
        cards, report = run()
        if best is None or report["elapsed_ms"]["total"] < best["elapsed_ms"]["total"]:
            best, page = report, cards
    return best, page


def bench(seed, teams, k, generator, first=5, full=True):
    def build():
        return synthetic_league.build(seed=seed, teams=teams)

    out = {"seed": seed, "teams": teams, "k": k, "generator_version": generator.VERSION}
    expected = None
    if full:
        started = perf_counter()
        cards, _ = generator.generate_bilateral_trades(**build())
        out.update(full_seconds=round(perf_counter() - started, 3), full_emitted=len(cards))
        expected = [_identity(c) for c in cards[:k]]

    def one_shot():
        cards, report = trade_first_page.first_page(k=k, generator=generator, **build())
        return cards, report.as_dict()

    def progressive():
        search = trade_first_page.PageSearch(generator=generator, **build())
        _, head = search.take(first)
        cards, report = search.take(k)
        report = report.as_dict()
        report["first_ms"] = head.as_dict()["elapsed_ms"]["total"]
        return cards, report

    for mode in ("cold", "warm"):
        best, page = _best(one_shot, cold=mode == "cold")
        out[f"{mode}_total_ms"] = best["elapsed_ms"]["total"]
        out[f"{mode}_stages_ms"] = best["elapsed_ms"]
        staged, _ = _best(progressive, cold=mode == "cold")
        out[f"{mode}_first_{first}_ms"], out[f"{mode}_then_{k}_ms"] = staged["first_ms"], staged["elapsed_ms"]["total"]
        out[f"{mode}_prefix_stable"] = staged["prefix_stable"]
    out.update({key: best[key] for key in ("universe", "bounded", "priced", "floor_pass", "support_bounded",
                                          "verified", "eligible_verified", "complete", "incumbent_budgets_bind",
                                          "price_envelope")})
    out["lineup_memo_entries"] = len(trade_first_page._LINEUP_MEMO)
    out["coordinate_memo_entries"] = trade_first_page._COORDINATE_MEMO._size
    if expected is not None:
        served = [_identity(c) for c in page]
        out.update(overlap_at_k=len(set(served) & set(expected)), exact_order_match=served == expected)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", default="7,11,23")
    parser.add_argument("--teams", type=int, default=12)
    parser.add_argument("--k", type=int, default=30)
    parser.add_argument("--first", type=int, default=5)
    parser.add_argument("--generator", choices=sorted(_GENERATORS), default="candidate")
    parser.add_argument("--no-full", action="store_true", help="skip the multi-second full solve")
    args = parser.parse_args(argv)
    for seed in (int(s) for s in args.seeds.split(",") if s.strip()):
        print(json.dumps(bench(seed, args.teams, args.k, _GENERATORS[args.generator],
                               first=args.first, full=not args.no_full), sort_keys=True))


if __name__ == "__main__":
    main()
