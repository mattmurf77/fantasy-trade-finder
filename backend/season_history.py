"""Win Now historical-validation scope: bounded public outcome-only collection.

Weekly player lists describe end-of-week rosters, never pre-kickoff evidence.
This module imports no server/database and performs no IO; fetch is injected.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import math
from statistics import median

from .season_forecasts import SUPPORTED_SCORING_KEYS
from .season_simulator import SLOT_POSITIONS, BENCH_SLOTS

SCHEMA_VERSION = 1
SETTINGS = ('num_teams', 'playoff_week_start', 'playoff_teams', 'playoff_seed_type',
            'playoff_round_type', 'league_average_match', 'start_week', 'divisions', 'best_ball', 'playoff_type')
MATCHUP_FIELDS = ('roster_id', 'matchup_id', 'points', 'custom_points', 'players', 'starters')
BRACKET_FIELDS = ('m', 'r', 'p', 't1', 't2', 'w', 'l')


def _int(value, minimum=1, maximum=100):
    return type(value) is int and minimum <= value <= maximum


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def model_support(record):
    slots = record.get('roster_positions')
    scoring = record.get('scoring_settings')
    reasons = []
    if not isinstance(slots, list) or not slots or any(not isinstance(s, str) for s in slots):
        reasons.append('invalid_roster_positions')
    else:
        active = [s for s in slots if s not in BENCH_SLOTS]
        if not active or len(active) > 12 or any(s not in SLOT_POSITIONS for s in active):
            reasons.append('unsupported_roster_slots')
    if not isinstance(scoring, dict) or not scoring:
        reasons.append('invalid_scoring_settings')
    else:
        for key, value in sorted(scoring.items()):
            if not _number(value):
                reasons.append(f'invalid_scoring:{key}')
            elif value and key not in SUPPORTED_SCORING_KEYS:
                reasons.append(f'unsupported_scoring:{key}')
    settings = record.get('settings') or {}
    if settings.get('playoff_teams') not in (4, 6, 8):
        reasons.append('unsupported_playoff_format')
    if not _int(settings.get('num_teams'), 4, 20):
        reasons.append('unsupported_team_count')
    if settings.get('divisions', 0):
        reasons.append('unsupported_division_seeding')
    if settings.get('best_ball', 0):
        reasons.append('best_ball_unsupported')
    if settings.get('playoff_seed_type', 0) not in (0, 1):
        reasons.append('unsupported_playoff_seed_type')
    if settings.get('playoff_round_type', 0) or settings.get('playoff_type', 0):
        reasons.append('unsupported_playoff_rounds')
    start = settings.get('playoff_week_start')
    rounds = 2 if settings.get('playoff_teams') == 4 else 3
    if not _int(start, 2, 18) or start + rounds - 1 > 18:
        reasons.append('playoffs_exceed_nfl_horizon')
    return {'supported': not reasons, 'reasons': reasons,
            'scope': 'league_rules_only_forecast_and_as_of_roster_evidence_not_checked'}


def derive_outcomes(record):
    """Fail closed on incomplete scores/brackets; standings cover regular season only."""
    def fail(reason):
        return {'status': 'excluded', 'reasons': [reason], 'teams': []}

    if record.get('status') != 'complete':
        return fail('season_not_complete')
    settings = record.get('settings')
    if not isinstance(settings, dict):
        return fail('invalid_settings')
    count, start, spots = (settings.get(k) for k in ('num_teams', 'playoff_week_start', 'playoff_teams'))
    if not _int(count, 2, 32) or not _int(start, 2, 18) or not _int(spots, 2, count):
        return fail('invalid_season_structure')
    if settings.get('start_week', 1) != 1 or settings.get('league_average_match', 0) not in (0, 1):
        return fail('unsupported_regular_season_structure')
    matchups = record.get('matchups')
    if not isinstance(matchups, dict):
        return fail('missing_matchups')
    teams = {}
    for week in range(1, start):
        rows = matchups.get(str(week))
        if not isinstance(rows, list) or len(rows) != count:
            return fail(f'missing_or_incomplete_week:{week}')
        scores, games = {}, defaultdict(list)
        for row in rows:
            if not isinstance(row, dict) or not _int(row.get('roster_id'), 1, 1000):
                return fail(f'invalid_roster:{week}')
            rid = row['roster_id']
            if rid in scores or not _int(row.get('matchup_id'), 1, 1000):
                return fail(f'invalid_matchup:{week}')
            points = row.get('custom_points') if row.get('custom_points') is not None else row.get('points')
            if not _number(points):
                return fail(f'invalid_score:{week}')
            scores[rid] = float(points)
            games[row['matchup_id']].append(rid)
        if teams and set(scores) != set(teams):
            return fail(f'roster_set_changed:{week}')
        if any(len(ids) != 2 for ids in games.values()):
            return fail(f'unpaired_matchup:{week}')
        for rid, points in scores.items():
            team = teams.setdefault(rid, dict(roster_id=rid, wins=0, losses=0, ties=0, points_for=0.0))
            team['points_for'] += points
        for ids in games.values():
            a, b = ids
            for rid, other in ((a, b), (b, a)):
                key = 'wins' if scores[rid] > scores[other] else 'losses' if scores[rid] < scores[other] else 'ties'
                teams[rid][key] += 1
        if settings.get('league_average_match', 0):
            mid = median(scores.values())
            for rid, points in scores.items():
                teams[rid]['wins' if points > mid else 'losses' if points < mid else 'ties'] += 1
    bracket = record.get('winners_bracket')
    if not isinstance(bracket, list) or not bracket:
        return fail('missing_winners_bracket')
    field, matches, ranks = set(), set(), {}
    championship = []
    for game in bracket:
        if not isinstance(game, dict):
            return fail('invalid_bracket')
        t1, t2, win, loss = (game.get(k) for k in ('t1', 't2', 'w', 'l'))
        if any(not _int(v, 1, 1000) or v not in teams for v in (t1, t2, win, loss)):
            return fail('unresolved_bracket')
        if t1 == t2 or win == loss or {t1, t2} != {win, loss}:
            return fail('invalid_bracket_result')
        if not _int(game.get('m'), 1, 1000) or game['m'] in matches or not _int(game.get('r'), 1, 18):
            return fail('invalid_bracket_match')
        matches.add(game['m'])
        field.update((t1, t2))
        place = game.get('p')
        if place is not None:
            if not _int(place, 1, spots - 1) or win in ranks or loss in ranks or place in ranks.values() or place + 1 in ranks.values():
                return fail('invalid_bracket_placement')
            ranks.update({win: place, loss: place + 1})
        if place == 1:
            championship.append(win)
    if len(championship) != 1 or len(field) != spots:
        return fail('invalid_playoff_field_or_champion')
    for rid, team in teams.items():
        team.update(playoff=rid in field, champion=rid == championship[0])
        if rid in ranks:
            team['final_rank'] = ranks[rid]
    return {'status': 'valid', 'reasons': [], 'regular_season_weeks': list(range(1, start)),
            'teams': [teams[rid] for rid in sorted(teams)]}


def collect_history(seed_league_ids, seasons, fetch, *, captured_at=None, max_chain=8, max_seasons=16):
    """Fetch receives v1-relative paths; all errors become typed exclusions, no raw payloads.

    Bounded to at most max_chain league reads per seed and 19 outcome reads per
    included season. No user/profile/rosters endpoints are requested.
    """
    seeds = sorted(set(str(s) for s in seed_league_ids))
    wanted = set(seasons)
    if not seeds or len(seeds) > 16 or any(not s.isdecimal() for s in seeds):
        raise ValueError('invalid_seed_leagues')
    if not wanted or len(wanted) > 16 or any(not _int(s, 2000, 2100) for s in wanted):
        raise ValueError('invalid_seasons')
    if not _int(max_chain, 1, 32) or not _int(max_seasons, 1, 32):
        raise ValueError('invalid_capture_bounds')
    captured = datetime.now(timezone.utc) if captured_at is None else datetime.fromisoformat(str(captured_at).replace('Z', '+00:00'))
    if captured.tzinfo is None:
        raise ValueError('capture_timezone_required')
    output = {'schema_version': SCHEMA_VERSION, 'captured_at': captured.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'),
              'source': 'sleeper_public_v1', 'seasons': [], 'exclusions': []}
    seen, cache, lineage_links = set(), {}, {}
    def exclude(lid, lineage, reason):
        output['exclusions'].append(dict(league_id=lid, lineage_id=lineage, reason=reason))
    for seed in seeds:
        lid, chain, previous_season = seed, set(), 2101
        found_years = set()
        for _ in range(max_chain):
            if not lid:
                break
            if lid in chain:
                exclude(lid, seed, 'chain_cycle'); break
            chain.add(lid)
            try:
                if lid not in cache:
                    cache[lid] = fetch(f'league/{lid}')
                league = cache[lid]
                if not isinstance(league, dict) or str(league.get('league_id')) != lid:
                    raise ValueError('league_identity_mismatch')
                year = int(league['season'])
                if year >= previous_season:
                    raise ValueError('non_descending_season_chain')
                previous_season = year
                if league.get('sport') != 'nfl' or league.get('season_type') != 'regular':
                    raise ValueError('unsupported_sport_or_season_type')
                found_years.add(year)
                previous = league.get('previous_league_id')
                if previous in (None, '', '0', 0):
                    previous = None
                elif not isinstance(previous, str) or not previous.isdecimal():
                    raise ValueError('invalid_previous_league_id')
            except (ValueError, TypeError, KeyError):
                exclude(lid, seed, 'invalid_league_metadata'); break
            except Exception:
                exclude(lid, seed, 'league_fetch_failed'); break
            if previous:
                lineage_links[lid] = previous
            if year in wanted and lid not in seen:
                seen.add(lid)
                if len(output['seasons']) >= max_seasons:
                    exclude(lid, seed, 'season_limit'); break
                if league.get('status') != 'complete' or year >= captured.year:
                    exclude(lid, seed, 'season_not_complete')
                else:
                    settings = league.get('settings')
                    if not isinstance(settings, dict):
                        exclude(lid, seed, 'invalid_settings')
                        lid = previous
                        continue
                    record = dict(league_id=lid, lineage_id=seed, season=year, status=league['status'],
                                  settings={k: settings[k] for k in SETTINGS if k in settings},
                                  scoring_settings=league.get('scoring_settings'), roster_positions=league.get('roster_positions'),
                                  roster_evidence='end_of_week_not_kickoff', matchups={}, winners_bracket=[])
                    try:
                        for week in range(1, 19):
                            rows = fetch(f'league/{lid}/matchups/{week}')
                            if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
                                raise ValueError('malformed_matchups')
                            record['matchups'][str(week)] = [{k: r.get(k) for k in MATCHUP_FIELDS} for r in rows]
                        bracket = fetch(f'league/{lid}/winners_bracket')
                        if not isinstance(bracket, list) or any(not isinstance(r, dict) for r in bracket):
                            raise ValueError('malformed_bracket')
                        record['winners_bracket'] = [{k: r[k] for k in BRACKET_FIELDS if k in r} for r in bracket]
                        record['outcomes'] = derive_outcomes(record)
                    except Exception:
                        record['outcomes'] = {'status': 'excluded', 'reasons': ['outcome_fetch_or_shape_failed'], 'teams': []}
                    record['model_support'] = model_support(record)
                    output['seasons'].append(record)
                    for reason in record['outcomes']['reasons']:
                        exclude(lid, seed, reason)
            lid = previous
            if year < min(wanted):
                break
        else:
            if lid:
                exclude(lid, seed, 'chain_limit')
        for missing in sorted(wanted - found_years):
            output['exclusions'].append(dict(league_id=seed, lineage_id=seed,
                                             season=missing, reason='requested_season_not_found'))
    # Connected seed chains are one sampling lineage, even when a seed is also
    # an ancestor of another seed. Canonicalize within the bounded observed graph.
    def canonical(seed):
        connected, pending = set(), [seed]
        neighbors = defaultdict(set)
        for child, ancestor in lineage_links.items():
            neighbors[child].add(ancestor)
            neighbors[ancestor].add(child)
        while pending:
            node = pending.pop()
            if node not in connected:
                connected.add(node)
                pending.extend(neighbors[node] - connected)
        return min(connected & set(seeds))
    for entry in output['seasons'] + output['exclusions']:
        entry['lineage_id'] = canonical(entry['lineage_id'])
    output['seasons'].sort(key=lambda r: (r['lineage_id'], r['season'], r['league_id']))
    return output
