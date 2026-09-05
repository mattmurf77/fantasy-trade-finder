"""Run the explicitly authorized revised-input Win Now diagnostic, never certification.

Public Sleeper projections are captured now and cached with their true capture
times. Historical scores are outcome labels or completed-week standings only.
No production flags, database, or fitted parameters change. All approximations
are recorded with each cohort. Run with --help for bounded input/output paths.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import median
import sys
import time
import urllib.request

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from backend.season_calibration import evaluate_calibration
from backend.season_forecasts import SUPPORTED_SCORING_KEYS, content_hash, fetch_projection_snapshot
from backend.season_history import model_support
from backend.season_simulator import simulate_season, projected_lineup_points, BENCH_SLOTS, SLOT_POSITIONS


def build_league(season, completed):
    """Freeze the completed-week roster and reconstruct only the settled prefix."""
    settings = season['settings']
    teams = {row['roster_id']: dict(roster_id=row['roster_id'], player_ids=row['players'],
              starters=[p for p in row['starters'] if p not in ('0', '')],
              wins=0, losses=0, ties=0, points_for=0.0)
             for row in season['matchups'][str(completed)]}
    schedule = {}
    regular = settings['playoff_week_start'] - 1
    for week in range(1, regular + 1):
        rows = season['matchups'][str(week)]
        grouped = defaultdict(list)
        for row in rows:
            grouped[row['matchup_id']].append(row['roster_id'])
        if any(len(pair) != 2 for pair in grouped.values()):
            raise ValueError('unpaired_historical_schedule')
        schedule[week] = list(grouped.values())
        if week > completed:
            continue
        scores = {r['roster_id']: r['custom_points'] if r.get('custom_points') is not None else r['points'] for r in rows}
        for rid, score in scores.items():
            teams[rid]['points_for'] += score
        for a, b in schedule[week]:
            for rid, other in ((a, b), (b, a)):
                field = 'wins' if scores[rid] > scores[other] else 'losses' if scores[rid] < scores[other] else 'ties'
                teams[rid][field] += 1
        if settings.get('league_average_match'):
            middle = median(scores.values())
            for rid, score in scores.items():
                teams[rid]['wins' if score > middle else 'losses' if score < middle else 'ties'] += 1
    return dict(league_id=season['league_id'], season=season['season'], teams=list(teams.values()),
        status='in_season', completed_weeks=completed, regular_season_weeks=regular,
        playoff_slots=settings['playoff_teams'], num_byes=2 if settings['playoff_teams'] == 6 else 0,
        playoff_start_week=regular + 1, playoff_seed_type=settings.get('playoff_seed_type', 0),
        playoff_round_weeks=1, median_match=bool(settings.get('league_average_match')),
        roster_slots=season['roster_positions'], scoring_settings=season['scoring_settings'], schedule=schedule)


def diagnostic_feed(payload):
    """Ignore CURRENT injury/team metadata; certify byes only from historical teams."""
    result = []
    for original in payload:
        row = deepcopy(original)
        row['player'].pop('injury_status', None)
        # The production adapter falls back to nested current team. Remove it
        # so that an unprojected player's current team cannot certify a past bye.
        row['player'].pop('team', None)
        result.append(row)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outcomes', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--completed-weeks', type=int, nargs='+', default=[3, 6, 9, 12])
    parser.add_argument('--sims', type=int, default=10000)
    args = parser.parse_args(argv)
    if not 256 <= args.sims <= 10000 or any(w < 1 or w > 13 for w in args.completed_weeks):
        parser.error('sims must be 256..10000 and completed weeks 1..13')
    original = json.loads(args.outcomes.read_text())
    outcomes = deepcopy(original)
    if len(outcomes['seasons']) > 16:
        parser.error('at most sixteen historical seasons per run')
    args.cache.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    schedule_path = REPO / 'backend/tests/fixtures/nflverse_games_2022_2026.csv'
    games = list(csv.DictReader(schedule_path.open()))
    from backend.outlook.bye_weeks import derive_byes
    byes = derive_byes(schedule_path.read_text())
    checkpoints, records, exclusions, sources, diagnostics = [], [], [], [], []
    cached = {}
    last_request = 0.0

    def fetch(url):
        nonlocal last_request
        if url in cached:
            return diagnostic_feed(cached[url]['rows'])
        path = args.cache / (hashlib.sha256(url.encode()).hexdigest() + '.json')
        if path.exists():
            envelope = json.loads(path.read_text())
            if envelope['url'] != url:
                raise ValueError('cache_url_mismatch')
        else:
            time.sleep(max(0.0, .2 - (time.monotonic() - last_request)))
            last_request = time.monotonic()
            with urllib.request.urlopen(url, timeout=25) as response:
                raw = response.read()
            rows = json.loads(raw)
            # Retain only model-related athlete fields, no news or current
            # injury metadata. The hash identifies the original source bytes.
            slim = []
            for r in rows:
                keep = {k: r.get(k) for k in ('category', 'season', 'season_type', 'week', 'player_id',
                        'team', 'date', 'game_id', 'opponent', 'stats', 'updated_at', 'last_modified', 'company')}
                player = r.get('player') or {}
                keep['player'] = {k: player.get(k) for k in ('position', 'fantasy_positions')}
                slim.append(keep)
            envelope = dict(url=url, captured_at=datetime.now(timezone.utc).isoformat(),
                            response_sha256=hashlib.sha256(raw).hexdigest(), rows=slim)
            path.write_text(json.dumps(envelope, separators=(',', ':')))
            print('Captured ' + url.split('?')[0], flush=True)
        cached[url] = envelope
        sources.append({k: envelope[k] for k in ('url', 'captured_at', 'response_sha256')})
        return diagnostic_feed(envelope['rows'])

    for season in outcomes['seasons']:
        sid = dict(league_id=season['league_id'], season=season['season'])
        active = [s for s in season['roster_positions'] if s not in BENCH_SLOTS]
        if any(s not in SLOT_POSITIONS for s in active):
            exclusions.append({**sid, 'reason': 'unsupported_kicker_or_idp_starting_slots'})
            continue
        removed = {k: v for k, v in season['scoring_settings'].items() if k not in SUPPORTED_SCORING_KEYS and v}
        season['scoring_settings'] = {k: v for k, v in season['scoring_settings'].items() if k in SUPPORTED_SCORING_KEYS}
        season['model_support'] = model_support(season)
        assumptions = ['Revised historical weekly forecasts fetched now, including later information; not a historical calibration backtest.',
            'Full remaining-season horizon combines later weekly revisions.',
            'Completed-week roster held fixed thereafter; reserve/taxi eligibility unavailable and all listed players treated as eligible.',
            'Current injury labels ignored; each usable stat forecast treated as available. Missing rows remain missing.',
            'Historical feed player positions used; exact historical eligibility not authenticated.',
            'Projected legal lineups selected using source-covered candidates; actual future manager lineup choices and transactions not modeled.',
            'Unsupported scoring coefficients omitted only for this offensive-lineup diagnostic: ' + json.dumps(removed, sort_keys=True)]
        for completed in sorted(set(args.completed_weeks)):
            league = build_league(season, completed)
            final_week = league['regular_season_weeks'] + (2 if league['playoff_slots'] == 4 else 3)
            weeks = list(range(completed + 1, final_week + 1))
            # Finish retrieval, then preserve the actual batch capture time
            # from the cache manifest. Replays never pretend cached inputs
            # were fetched again, nor backdate them to historical game dates.
            snapshot = fetch_projection_snapshot(season['season'], weeks, fetch, datetime.now(timezone.utc),
                                                  bye_weeks=byes[str(season['season'])])
            captures = [env['captured_at'] for url, env in cached.items()
                        if any(f"/{season['season']}/{week}?" in url for week in weeks)]
            captured_at = max(captures, default=datetime.now(timezone.utc).isoformat())
            snapshot = fetch_projection_snapshot(season['season'], weeks, fetch, captured_at,
                                                  bye_weeks=byes[str(season['season'])])
            original_screen = projected_lineup_points(league, snapshot)
            original_starters = {str(t['roster_id']): t['starters'] for t in league['teams']}
            # Past starters are not future obligations. This explicit diagnostic
            # retry retains all roster IDs and full legal-lineup coverage checks.
            local_assumptions = list(assumptions)
            if not original_screen['supported'] and all(r.startswith('missing_starter_forecast:') for r in original_screen['reasons']):
                for t in league['teams']:
                    t['starters'] = []
                local_assumptions.append('Past-starter coverage requirement relaxed; unprojected players excluded, with missing IDs reported. This can bias estimates.')
            result = simulate_season(league, snapshot, n_sims=args.sims, seed=42)
            detail = {**sid, 'as_of_week': completed, 'original_coverage': original_screen,
                      'original_starters': original_starters, 'simulation': result}
            if result['meta']['supported']:
                detail['missing_original_starters_by_week'] = {
                    str(t['roster_id']): {w: sorted(set(ids) & set(original_starters[str(t['roster_id'])]))
                        for w, ids in t['coverage']['excluded_bench_ids'].items()}
                    for t in result['teams']}
            diagnostics.append(detail)
            if not result['meta']['supported']:
                exclusions.append({**sid, 'as_of_week': completed, 'reason': result['meta']['reasons']})
                print('Excluded ' + str(sid) + ' after week ' + str(completed) + ': ' + str(result['meta']['reasons']), flush=True)
                continue
            dates = [g['gameday'] for g in games if g['season'] == str(season['season']) and g['game_type'] == 'REG' and int(g['week']) == completed + 1]
            cutoff = min(dates) + 'T00:00:00Z'
            checkpoints.append({**sid, 'as_of_week': completed, 'cutoff': cutoff,
                                'evidence_ref': str(schedule_path) + ' (conservative first-game date boundary)'})
            model = result['meta']['model_version'] + '__revised_offense_diagnostic_v1'
            record = {**sid, 'as_of_week': completed, 'model_family': 'win_now_player_week', 'model_version': model,
                'cutoff': cutoff, 'forecast_captured_at': snapshot['captured_at'],
                'league_state_captured_at': original['captured_at'], 'prediction_created_at': datetime.now(timezone.utc).isoformat(),
                'forecast_season': season['season'], 'forecast_as_of_week': completed, 'forecast_weeks': weeks,
                'league_state_season': season['season'], 'league_state_as_of_week': completed,
                'assumptions': local_assumptions,
                'provenance': {'kind': 'revised_historical_diagnostic', 'forecast_evidence_ref': str(args.cache),
                    'forecast_sha256': content_hash(snapshot), 'league_state_evidence_ref': str(args.outcomes),
                    'league_state_sha256': content_hash(league), 'prediction_evidence_ref': str(args.output_dir / 'replay-details.json'),
                    'prediction_sha256': content_hash(result)}, 'teams': result['teams']}
            records.append(record)
            print('Simulated ' + str(sid) + ' after week ' + str(completed), flush=True)
    predictions = dict(schema_version=1, records=records)
    references = dict(schema_version=1, checkpoints=checkpoints)
    report = evaluate_calibration(outcomes, predictions, references, mode='exploratory_revised_inputs')
    report['replay_exclusions'] = exclusions
    report['simulation_draws'] = args.sims
    report['source_manifest'] = sources
    for name, value in [('adjusted-outcomes', outcomes), ('predictions', predictions), ('checkpoints', references),
                        ('replay-details', diagnostics), ('report', report)]:
        (args.output_dir / (name + '.json')).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'status': report['status'], 'eligible_cohorts': len(records),
                      'exclusions': exclusions, 'report': str(args.output_dir / 'report.json')}, indent=2))


if __name__ == '__main__':
    main()
