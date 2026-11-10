"""Open-loop load test of trade construction: page-first vs the full solve.

Operator tooling only: synthetic leagues, no server, database or network.

    python -m backend.eval.first_page_load --rate 8 --duration 30
    python -m backend.eval.first_page_load --burst 1000 --processes 8
    python -m backend.eval.first_page_load --mode full --rate 0.2 --duration 30

Searches arrive on a schedule (Poisson at ``--rate`` per second, or ``--burst``
all at once) whether or not earlier ones have finished, so a backlog shows up
as latency instead of being hidden by a slowed-down client. Latency is measured
from the scheduled arrival. Workers are ``--processes`` processes of
``--threads`` threads each; production today is one process of four threads on
one CPU, and threads share that CPU under the interpreter lock.

What this measures is construction only. A real request also loads boards and
rosters, runs final checks and commits evidence before a card is shown.
"""

import argparse
import json
import multiprocessing as mp
import os
import random
import resource
import sys
import threading
import time


def _percentile(ordered, share):
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))] if ordered else None


def _worker(tasks, results, threads, mode, k, seeds, teams):
    from backend import trade_first_page, trade_gen_bilateral_candidate as candidate
    from backend.eval import synthetic_league
    leagues = {seed: synthetic_league.build(seed=seed, teams=teams) for seed in seeds}

    def search(seed):
        if mode == "page":
            trade_first_page.first_page(k=k, **leagues[seed])
        else:
            candidate.generate_bilateral_trades(**leagues[seed])

    def loop():
        while True:
            item = tasks.get()
            if item is None:
                return
            seed, arrived = item
            started = time.monotonic()
            search(seed)
            results.put((arrived, started, time.monotonic()))

    search(seeds[0])  # imports and first-use caches are not part of the test
    pool = [threading.Thread(target=loop) for _ in range(threads)]
    for thread in pool:
        thread.start()
    results.put("ready")
    for thread in pool:
        thread.join()
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    results.put(("rss_mb", peak / (1e6 if sys.platform == "darwin" else 1e3)))


def run(*, rate=None, duration=30.0, burst=None, processes=1, threads=4, mode="page",
        k=30, leagues=20, teams=12, seed=1):
    context = mp.get_context("spawn")
    tasks, results = context.Queue(), context.Queue()
    seeds = list(range(100, 100 + leagues))
    workers = [context.Process(target=_worker, args=(tasks, results, threads, mode, k, seeds, teams))
               for _ in range(processes)]
    for worker in workers:
        worker.start()
    for _ in workers:
        assert results.get() == "ready"

    rng = random.Random(seed)
    begin = time.monotonic()
    if burst:
        arrivals = [0.0] * burst
    else:
        arrivals, at = [], rng.expovariate(rate)
        while at < duration:
            arrivals.append(at)
            at += rng.expovariate(rate)
    for at in arrivals:
        delay = begin + at - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        tasks.put((rng.choice(seeds), begin + at))
    for _ in range(processes * threads):
        tasks.put(None)

    latency, service, rss, last = [], [], [], begin
    while len(rss) < processes:
        item = results.get()
        if item[0] == "rss_mb":
            rss.append(item[1])
            continue
        arrived, started, finished = item
        latency.append((finished - arrived) * 1000)
        service.append((finished - started) * 1000)
        last = max(last, finished)
    for worker in workers:
        worker.join()
    latency.sort()
    service.sort()
    elapsed = last - begin
    return {
        "mode": mode, "processes": processes, "threads": threads, "cpus": os.cpu_count(),
        "leagues": leagues, "teams": teams, "k": k,
        "arrivals": len(arrivals), "offered_per_s": None if burst else rate,
        "burst": burst, "arrival_window_s": 0.0 if burst else duration,
        "drained_s": round(elapsed, 2),
        "throughput_per_s": round(len(latency) / elapsed, 2) if elapsed else None,
        "latency_ms": {name: round(_percentile(latency, share), 1) for name, share in
                       (("p50", .5), ("p95", .95), ("p99", .99), ("max", 1.0))} if latency else {},
        "service_ms": {name: round(_percentile(service, share), 1) for name, share in
                       (("p50", .5), ("p95", .95))} if service else {},
        "share_within_200ms": round(sum(v <= 200 for v in latency) / len(latency), 3) if latency else None,
        "peak_rss_mb_per_process": round(max(rss)) if rss else None,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    load = parser.add_mutually_exclusive_group(required=True)
    load.add_argument("--rate", type=float, help="Poisson arrivals per second")
    load.add_argument("--burst", type=int, help="this many arrivals at once")
    parser.add_argument("--duration", type=float, default=30.0, help="arrival window, seconds")
    parser.add_argument("--processes", type=int, default=1)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--mode", choices=("page", "full"), default="page")
    parser.add_argument("--k", type=int, default=30)
    parser.add_argument("--leagues", type=int, default=20)
    parser.add_argument("--teams", type=int, default=12)
    args = parser.parse_args(argv)
    print(json.dumps(run(**vars(args)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
