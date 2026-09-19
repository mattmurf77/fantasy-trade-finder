# Owner-only high-output performance evidence

## Organic worker: executed synthetic stress run

Recorded 2026-09-06, approximately 21:47 EDT (2026-09-07 01:47 UTC).
This is one local Python 3.12.14 run, not production performance, concurrency,
device acceptance or an estimate of normal user supply. The worker is the
actual asynchronous organic implementation, invoked synchronously by its test
harness so that completion and all impression writes can be measured.

The deliberately dense fixture has 12 teams with 24 unique assets each. The
viewer values its own assets at 85% of market and other assets at 115%; each
opponent values the viewer's assets at 115% and its own at 85%. All outlooks are
`not_sure`. The route harness requests fairness **0.50**, unlike the separate
generator-only 0.75 stress fixture that produced 6,622 cards. The different
counts must not be described as a performance regression or inconsistent run.
Search limits remain pool16 / per-opponent4096 / total60000.

| Measurement | Actual result |
|---|---:|
| Generated / served / persisted impressions | 8,327 / 8,327 / 8,327 |
| Complete worker elapsed | 16.395670 seconds |
| Owner generation, within that worker | 5.641159 seconds |
| F1 assembly and SQLite insert, within that worker | 4.591900 seconds |
| Serialized public job JSON | 10,513,277 bytes |
| Private impression `features_json` total | 176,797,819 bytes |
| Private impression `valuation_json` total | 38,521,130 bytes |
| Impression `assets_json` total | 622,211 bytes |
| Total of those three stored JSON columns | 215,941,160 bytes |
| Process high-water RSS immediately after worker | 667,697,152 bytes (636.8 MiB) |

Generation and F1 timings are nested portions of the complete worker, not
independent runs to add to it. F1 timing includes both Python row/JSON assembly
and the actual insert; it does not isolate database time. Public serialization
and SQL size aggregation occurred afterward and are outside the worker timer.
The RSS reading precedes those two measurement steps. Synthetic strings are
ASCII, so the SQL `length()` totals here equal their encoded byte totals.

The scratch database was **in-memory SQLite in the measured Python process**.
Its approximately 216 MB of stored JSON, SQLite structures, Python objects,
imports and transient allocations contribute to the process high-water mark.
This is not production application RSS; subtracting JSON bytes does not give
a reliable production-memory estimate either. The production database is not
this in-process test database.

The parent separately reported a read-only live Render metadata check showing
the existing **Standard plan, one instance**, and the official plan mapping of
**1 CPU / 2 GB RAM**. This benchmark did not query Render or independently
measure that deployment. Its 637 MiB high-water result does not demonstrate a
512 MB production outage, nor does the larger provisioned plan prove safety
under concurrent requests.
Parent verification used Render's service metadata API (read-only, existing
service; no plan change) and the official [compute-plan table](https://render.com/docs/compute-plans).

The parent's **15-second review threshold applies to synchronous selected
routes**, not as a hard failure threshold for an asynchronous organic job.
Accordingly, this result is a material latency/payload/storage stress warning,
not by itself a failed organic release gate. Separate selected-route timings
are required; this run cannot establish them. No production latency, parallel
job capacity, database throughput, client parsing memory or long-deck rendering
claim is made. No returned offers or required private evidence were capped or
discarded to obtain these results.

## Source identity

The benchmark used the frozen, uncommitted owner-only runtime in
`/private/tmp/fleeced-owner-only-4f0wl1`, based on
`0e3d6b703c1351f51a7b38d3a561d340eda5e44b`. It was **not** a benchmark of that
unchanged baseline. Source SHA-256 fingerprints captured after the run:

| File | SHA-256 |
|---|---|
| `backend/server.py` | `233d57a646ae0a1b93cef7fa299c822b59d1189229a3fb3ed5de4b4edc5dc79b` |
| `backend/bakeoff_runner.py` | `03976572dff5425b6d08e9bcac17cfd8fc18268f05fb51fef6507c4f82d0940b` |
| `backend/trade_gen_owner.py` | `53e8c098288fce47f77b6581c49cd700a4bdf71caab58d1219aa5ec8bd770786` |
| `backend/trade_service.py` | `8c5d228b57ca46dff72f6d51983d32efad476c9ee96fa91beada5a4add93940e` |
| `backend/database.py` | `55783c4612a6f49be5869bea72dc0d6a9c25bd54a697704639c03f88d38eae90` |
| `backend/tests/test_owner_generator_routes.py` | `2db0ecf910109a0297ee1d49d46895ccf8f14342589fa853d127e986ca4bfa89` |
| `backend/tests/test_fair_packages.py` | `8df2ed25462e7fe347fa6d3141d14e11be417c21beafd0b2c0b8f96fc02f8615` |

Trim-before-deepcopy request snapshots and the once-per-run diagnostics
materialization were already present. The later parent inventory-test
correction did not change this runtime. Functional gates and the independent
snapshot parity comparison are recorded in [verification](verification.md).

## Exact reproduction command and harness procedure

Run from the source worktree above with its isolated dependency environment.
The command imports the existing synthetic fixtures, creates their scratch
SQLite schema, then replaces the small league with the dense synthetic one.
It runs the real constructor, final validation, serialization and F1 writer.
The inherited worker helper disables unrelated exploration, fatigue, taste,
first-session shaping, diversity, incoming-interest and ghost layers; this is
not a benchmark of those features or provider calls. Flags, session objects
and fixture monkeypatches are restored on exit. No production connection,
credential file, user action, seeding target or external API is involved.

```sh
DATABASE_URL=sqlite:///:memory: \
PYTHONDONTWRITEBYTECODE=1 \
FTF_DP_VALUES_FILE=backend/tests/fixtures/outlook-hypotheses/dp-values-players-2026-08-09.csv \
FTF_DP_PICK_VALUES_FILE=backend/tests/fixtures/dp_values_picks_2026-08-06.csv \
/private/tmp/ftf-context-venv/bin/python - <<'PY'
import json, resource, sys, time
import pytest
from sqlalchemy import select, func
from backend import server, trade_service as ts, database as db, trade_gen_owner
from backend.ranking_service import Player, RankingService
from backend.tests.test_owner_generator_routes import harness, owner_harness, worker, ME

with pytest.MonkeyPatch.context() as mp:
    base = harness.__wrapped__()
    env = next(base)
    enhanced = owner_harness.__wrapped__(env, mp)
    env = next(enhanced)
    try:
        _, engine, sess, service, league = env
        values = [300, 500, 800, 1000, 1500, 2200]
        positions = ['QB', 'RB', 'WR', 'WR', 'TE', 'RB']
        spec, rosters = {}, {}
        for team in range(12):
            uid = ME if team == 0 else f'team{team}'
            rosters[uid] = []
            for index in range(24):
                pid = f'{uid}_asset{index}'
                rosters[uid].append(pid)
                spec[pid] = (positions[index % 6], [23, 25, 28, 31][index % 4], values[index % 6])
        players = [Player(pid, pid, pos, 'TST', age) for pid, (pos, age, _) in spec.items()]
        seed = {pid: ts.value_to_elo(value) for pid, (_, _, value) in spec.items()}
        ranking = RankingService(players=players)
        ranking._seed = seed
        ranking._elo_overrides.update({p: ts.value_to_elo(value * (.85 if p in rosters[ME] else 1.15)) for p, (_, _, value) in spec.items()})
        mp.setattr(ranking, 'placement_bands', lambda: {p: (1000, 2000) for p in spec})
        league.members = [ts.LeagueMember(uid, uid, ids, {}) for uid, ids in rosters.items()]
        sess.update(players=players, user_roster=rosters[ME], service=ranking, services={'1qb_ppr': ranking})
        service._players = {p.id: p for p in players}
        boards = {uid: {'elo_ratings': {p: ts.value_to_elo(spec[p][2] * (1.15 if p in rosters[ME] else .85)) for p in rosters[ME] + ids}, 'confidence_sources': dict.fromkeys(rosters[ME] + ids, 'explicit'), 'username': uid} for uid, ids in rosters.items() if uid != ME}
        mp.setattr(server, 'load_member_rankings', lambda *a, **k: boards)
        mp.setattr(server, 'load_league_preferences_bulk', lambda *a: {uid: {'team_outlook': 'not_sure'} for uid in rosters})
        mp.setattr(server, 'load_league_preference', lambda **k: {'team_outlook': 'not_sure'})
        mp.setattr(server, '_infer_user_outlook', lambda *a, **k: ('not_sure', None))
        ts._cfg.update(bakeoff_include_owner=1., bakeoff_serve_owner=1., bakeoff_owner_only=1.)
        timings = {}
        original_generate = trade_gen_owner.generate_owner_trades
        def generated(**kwargs):
            start = time.perf_counter()
            result = original_generate(**kwargs)
            timings['generation_seconds'] = time.perf_counter() - start
            timings['generated_cards'] = len(result[0])
            return result
        mp.setattr(trade_gen_owner, 'generate_owner_trades', generated)
        original_impressions = server._log_deck_signal_impressions
        def impressions(**kwargs):
            start = time.perf_counter()
            result = original_impressions(**kwargs)
            timings['impression_assembly_and_insert_seconds'] = time.perf_counter() - start
            return result
        mp.setattr(server, '_log_deck_signal_impressions', impressions)
        start = time.perf_counter()
        job = worker(env, mp)
        timings['worker_seconds'] = time.perf_counter() - start
        timings['served_cards'] = len(job['cards'])
        timings['peak_rss_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
        timings['public_job_json_bytes'] = len(json.dumps(server._trade_job_public_view(job)).encode())
        table = db.deck_impressions_table
        with engine.connect() as conn:
            timings['impression_rows'] = conn.execute(select(func.count()).select_from(table)).scalar_one()
            timings['private_json_bytes'] = {key: conn.execute(select(func.sum(func.length(table.c[key])))).scalar_one() for key in ('features_json', 'valuation_json', 'assets_json')}
        timings['synthetic_teams'] = 12
        timings['assets_per_team'] = 24
        print(json.dumps(timings, sort_keys=True))
    finally:
        enhanced.close()
        base.close()
PY
```

Exit status was 0. Counts, byte totals and measured durations above are from
that execution, not a prediction. Reproduction under another machine or load
need not reproduce wall-clock duration or RSS exactly.
