"""Strict linked-provider snapshots for calibration only.

Imports deliberately flatten rosters for discovery. These readers retain every
asset and inactive slot, and refuse rules the common safety gate cannot express.
No provider writes, account sessions, credential persistence or normal serving.
"""
from dataclasses import dataclass, replace
import re

from .blind_grading import GradingError
from . import espn_service as espn, mfl_service as mfl
from .trade_roster import ELIGIBILITY, POSITIONS

ESPN_SLOTS = {0: 'QB', 2: 'RB', 3: 'WRRB_FLEX', 4: 'WR', 5: 'REC_FLEX',
              6: 'TE', 7: 'SUPER_FLEX', 23: 'FLEX', 20: 'BN', 21: 'IR'}
BINDING_KEYS = ('platform', 'user_id', 'default_scoring', 'espn_my_team_id', 'espn_season', 'espn_auth',
                'platform_my_team', 'platform_season', 'platform_host', 'platform_auth',
                'draft_status', 'draft_status_confidence')


def _fail(code):
    raise GradingError(code, 409) from None


def _int(value, *, positive=False):
    if isinstance(value, bool) or not re.fullmatch(r'\d+', str(value)):
        _fail('provider_settings_unsupported')
    result = int(value)
    if result > 100 or (positive and result == 0):
        _fail('provider_settings_unsupported')
    return result


def binding_identity(user_id, league_id):
    """Semantic stored binding plus credential revision, never credential values."""
    from . import database as db
    with db.engine.connect() as conn:
        row = conn.execute(db.select(db.leagues_table).where(
            db.leagues_table.c.sleeper_league_id == league_id)).mappings().first()
    if not row or row['platform'] not in ('espn', 'mfl'):
        return None
    cred = (db.get_espn_credential(user_id) if row['platform'] == 'espn'
            else db.get_mfl_credential(user_id)) or {}
    return {'binding': {k: row.get(k) for k in BINDING_KEYS},
            'credential_revision': {k: cred.get(k) for k in ('created_at', 'updated_at', 'verified_at')}}


def _map(pid, name, position, xwalk, platform):
    if position not in POSITIONS:
        _fail('provider_roster_position_unsupported')
    direct = xwalk.by_espn_id if platform == 'espn' else xwalk.by_mfl_sleeper
    result = direct.get(str(pid)) or xwalk.by_name_pos.get((espn.normalise_name(name), position))
    if not result:
        _fail('provider_roster_asset_unmapped')
    return str(result)


def _check_rosters(rosters):
    if len(rosters) < 2 or any(not r['players'] for r in rosters):
        _fail('league_rosters_unavailable')
    owners = [r['owner_id'] for r in rosters]
    players = [p for r in rosters for p in r['players']]
    if len(set(owners)) != len(owners) or len(set(players)) != len(players):
        _fail('provider_roster_identity_ambiguous')


@dataclass
class LinkedSnapshot:
    platform: str
    resolved: dict
    rosters: list
    slots: list
    capacity: int
    positions: dict
    provenance: dict
    future_picks: list | None = None

    def validate_owned_picks(self, picks):
        """A concurrent cache refresh may not substitute a different observation."""
        if self.platform != 'mfl':
            return
        from . import server as s
        binding = self.provenance['binding']['binding']
        year = int(binding['platform_season'] or s._MFL_DEFAULT_YEAR)
        exclude = not s._current_season_picks_visible(
            binding.get('draft_status'), binding.get('draft_status_confidence'))
        owner = lambda fid: (binding['user_id'] if str(fid) == str(binding['platform_my_team'])
                             else s._mfl_member_id(self.provenance['league_id'], str(fid)))
        expected = {}
        for pick in self.future_picks:
            yr, rnd = int(pick['year']), int(pick['round'])
            if exclude and yr == year:
                continue
            pid = s.make_pick_id(self.provenance['league_id'], yr, rnd, str(pick['original_owner']))
            expected[pid] = (owner(pick['franchise_id']), owner(pick['original_owner']), yr, rnd)
        actual = {p['pick_id']: (str(p['owner_user_id']), str(p['original_user_id']),
                                int(p['season']), int(p['round'])) for p in picks}
        if actual != expected or len(actual) != len(picks):
            _fail('provider_pick_ownership_changed')

    def normalized_metadata(self, players, metadata):
        """Native eligibility controls both priced and unpriced roster assets."""
        result = dict(metadata)
        for pid, pos in self.positions.items():
            if pid in players and players[pid].position != pos:
                _fail('provider_player_position_conflict')
            row = metadata.get(pid)
            if (not isinstance(row, dict) or not row
                    or row.get('player_id') not in (None, pid)):
                _fail('provider_player_availability_unavailable')
            result[pid] = {**row, 'position': pos, 'fantasy_positions': [pos]}
        return result

    def roster_context(self, **kwargs):
        """Use common asset math, then attach the fully validated observations."""
        from .trade_roster_adapter import build_context
        if not kwargs.get("availability_fresh"):
            _fail("provider_player_availability_unavailable")
        context = build_context(platform=self.platform, raw_rosters=self.rosters,
                                slots=self.slots, capacity=self.capacity, **kwargs)
        for pid, position in self.positions.items():
            if pid in context.assets:
                context.assets[pid] = replace(context.assets[pid], positions=frozenset({position}))
        context.rules = replace(context.rules, source='observed')
        context.teams = {uid: replace(team, availability_known=True)
                         for uid, team in context.teams.items()}
        return context


def parse_espn(raw, *, league_id, user_id, team_id, xwalk):
    if str(raw.get('id')) != league_id:
        _fail('provider_league_mismatch')
    settings = raw.get('settings') or {}
    roster_settings = settings.get('rosterSettings') or {}
    counts = roster_settings.get('lineupSlotCounts')
    if not isinstance(counts, dict) or not counts:
        _fail('lineup_unavailable')
    slots = []
    for key, count in counts.items():
        count = _int(count)
        if count and (not str(key).isdigit() or int(key) not in ESPN_SLOTS):
            _fail('provider_lineup_unsupported')
        if count:
            slots.extend([ESPN_SLOTS[int(key)]] * count)
    starters = [s for s in slots if s not in ('BN', 'IR')]
    capacity = len([s for s in slots if s != 'IR'])
    if not starters or len(starters) > 16 or capacity > 100:
        _fail('provider_lineup_unsupported')
    # A finite position cap needs its own legality check, absent in common
    # roster evaluation. Never silently treat it as an unrestricted bench.
    limits = roster_settings.get('positionLimits') or {}
    if not isinstance(limits, dict):
        _fail('provider_settings_unsupported')
    for key, limit in limits.items():
        if str(key) in ('1', '2', '3', '4') and str(limit) != '-1' and _int(limit) < capacity:
            _fail('provider_position_limits_unsupported')
    parsed = espn.parse_league(raw)
    teams = {t.team_id: t for t in parsed['teams']}
    if _int(settings.get('size'), positive=True) != len(teams) or len(teams) != len(parsed['teams']):
        _fail('league_rosters_unavailable')
    if team_id not in teams:
        _fail('league_seat_changed')
    from .server import _espn_member_id
    rosters, positions, mapping, members = [], {}, {}, []
    for team in raw.get('teams') or []:
        tid = team.get('id')
        known = teams.get(tid)
        entries = (team.get('roster') or {}).get('entries')
        if not known or not isinstance(entries, list):
            _fail('league_rosters_unavailable')
        uid = user_id if tid == team_id else _espn_member_id(league_id, known)
        roster = dict(owner_id=uid, players=[], reserve=[], taxi=[])
        for entry in entries:
            p = (entry.get('playerPoolEntry') or {}).get('player') or {}
            pid, position = p.get('id'), espn.ESPN_POSITION_BY_ID.get(p.get('defaultPositionId'))
            if pid in (None, ''):
                _fail('provider_roster_asset_unmapped')
            sid = _map(pid, p.get('fullName') or '', position, xwalk, 'espn')
            slot = entry.get('lineupSlotId')
            if slot not in ESPN_SLOTS or ESPN_SLOTS[slot] not in slots:
                _fail('provider_roster_slot_unknown')
            eligible = p.get('eligibleSlots')
            if not isinstance(eligible, list) or any(
                    (native in eligible) != (position in ELIGIBILITY[ESPN_SLOTS[native]])
                    for native in ESPN_SLOTS if ESPN_SLOTS[native] in starters):
                _fail('provider_player_eligibility_unsupported')
            roster['players'].append(sid)
            if slot == 21:
                roster['reserve'].append(sid)
            positions[sid], mapping[str(pid)] = position, sid
        rosters.append(roster)
        members.append(dict(user_id=uid, username=known.name, player_ids=roster['players']))
    _check_rosters(rosters)
    mine = next(m for m in members if m['user_id'] == user_id)
    return LinkedSnapshot('espn', dict(platform='espn', league_user_id=user_id,
        user_player_ids=mine['player_ids'], opponent_rosters=[m for m in members if m is not mine]),
        rosters, starters, capacity, positions,
        {'platform': 'espn', 'rules': roster_settings, 'native_player_map': mapping,
         'pick_policy': 'existing_asserted_assignments_only_if_enabled'})


def _mfl_slots(league):
    """Only min/max systems exactly equal to fixed slots plus one flex class."""
    settings = league.get('starters') or {}
    total = _int(settings.get('count'), positive=True)
    if total > 16:
        _fail('provider_lineup_unsupported')
    bounds = {}
    for row in mfl._as_list(settings.get('position')):
        pos, limit = row.get('name'), mfl._txt(row.get('limit'))
        if not re.fullmatch(r'\d+(?:-\d+)?', limit):
            _fail('provider_lineup_unsupported')
        values = list(map(int, limit.split('-')))
        lo, hi = values[0], values[-1]
        if pos in bounds or hi < lo or hi > 100 or (pos not in POSITIONS and hi):
            _fail('provider_lineup_unsupported')
        if pos in POSITIONS:
            bounds[pos] = (lo, hi)
    slots = [p for p, (lo, _) in bounds.items() for _ in range(lo)]
    extra = total - len(slots)
    if extra < 0:
        _fail('provider_lineup_unsupported')
    flexible = frozenset(p for p, (lo, hi) in bounds.items() if hi > lo)
    if extra:
        if not flexible or any(bounds[p][1] - bounds[p][0] < extra for p in flexible):
            _fail('provider_lineup_unsupported')
        flex = next((s for s, positions in ELIGIBILITY.items() if positions == flexible), None)
        if not flex:
            _fail('provider_lineup_unsupported')
        slots += [flex] * extra
    return slots


def parse_mfl(raw, *, league_id, user_id, franchise_id, xwalk):
    league = (raw.get('league') or {}).get('league') or {}
    if str(league.get('id')) != league_id:
        _fail('provider_league_mismatch')
    if (not ((raw.get('rules') or {}).get('rules') or {}).get('positionRules')
            or not (raw.get('players') or {}).get('players')):
        _fail('provider_rules_or_players_unavailable')
    slots = _mfl_slots(league)
    capacity = _int(league.get('rosterSize'), positive=True)
    if capacity < len(slots):
        _fail('provider_settings_unsupported')
    # Salary/contracts and positional roster caps are not modeled by the
    # current common gate. Preserve an honest unsupported result.
    if any(league.get(k) not in (None, '', '0', 0, 'No') for k in
           ('salaryCapAmount', 'usesSalaries', 'usesContractYear', 'rosterLimits')):
        _fail('provider_settings_unsupported')
    future = (raw.get('futureDraftPicks') or {}).get('futureDraftPicks')
    if not isinstance(future, dict) or 'franchise' not in future:
        _fail('pick_ownership_unavailable')
    for franchise in mfl._as_list(future['franchise']):
        if not isinstance(franchise, dict) or not franchise.get('id'):
            _fail('pick_ownership_unavailable')
        for pick in mfl._as_list(franchise.get('futureDraftPick')):
            if not isinstance(pick, dict):
                _fail('pick_ownership_unavailable')
    parsed = mfl.parse_bundle(raw)
    teams = {f['franchise_id']: f for f in parsed['franchises']}
    declared = mfl._as_list((league.get('franchises') or {}).get('franchise'))
    if (_int((league.get('franchises') or {}).get('count'), positive=True) != len(teams)
            or len(declared) != len(teams) or len(teams) != len(parsed['franchises'])):
        _fail('league_rosters_unavailable')
    if franchise_id not in teams:
        _fail('league_seat_changed')
    from .server import _mfl_member_id
    rosters, positions, mapping, members = [], {}, {}, []
    raw_teams = mfl._as_list((raw.get('rosters') or {}).get('rosters', {}).get('franchise'))
    if {r.get('id') for r in raw_teams} != set(teams):
        _fail('league_rosters_unavailable')
    for team in raw_teams:
        fid = team.get('id')
        known = teams[fid]
        details = {str(pid): (name, pos) for pid, name, pos in known['players']}
        uid = user_id if fid == franchise_id else _mfl_member_id(league_id, fid)
        roster = dict(owner_id=uid, players=[], reserve=[], taxi=[])
        for p in mfl._as_list(team.get('player')):
            pid, status = str(p.get('id') or ''), p.get('status')
            name, pos = details.get(pid, ('', None))
            sid = _map(pid, name, pos, xwalk, 'mfl')
            if status not in ('ROSTER', 'INJURED_RESERVE', 'TAXI_SQUAD'):
                _fail('provider_roster_slot_unknown')
            if status != 'ROSTER':
                field = 'injuredReserve' if status == 'INJURED_RESERVE' else 'taxiSquad'
                _int(league.get(field), positive=True)
                roster['reserve' if status == 'INJURED_RESERVE' else 'taxi'].append(sid)
            roster['players'].append(sid)
            positions[sid], mapping[pid] = pos, sid
        rosters.append(roster)
        members.append(dict(user_id=uid, username=known['name'], player_ids=roster['players']))
    _check_rosters(rosters)
    mine = next(m for m in members if m['user_id'] == user_id)
    picks = parsed['future_picks']
    if any(str(p.get('franchise_id')) not in teams or str(p.get('original_owner')) not in teams
           or not re.fullmatch(r'[2-9]\d{3}', str(p.get('year')))
           or not str(p.get('round')).isdigit() or not 1 <= int(p['round']) <= 100 for p in picks):
        _fail('pick_ownership_unavailable')
    keys = [(str(p['year']), str(p['round']), str(p['original_owner'])) for p in picks]
    if len(keys) != len(set(keys)):
        _fail('pick_ownership_unavailable')
    return LinkedSnapshot('mfl', dict(platform='mfl', league_user_id=user_id,
        user_player_ids=mine['player_ids'], opponent_rosters=[m for m in members if m is not mine]),
        rosters, slots, capacity, positions,
        {'platform': 'mfl', 'rules': {k: league.get(k) for k in
         ('starters', 'rosterSize', 'injuredReserve', 'taxiSquad')},
         'native_player_map': mapping, 'pick_policy': 'provider_owned_future_draft_picks',
         'scoring_rules': raw['rules']['rules'], 'future_owned_picks': picks}, picks)


def pick_ownership(rows):
    return sorted((str(p['pick_id']), str(p['owner_user_id']), str(p['original_user_id']),
                   int(p['season']), int(p['round'])) for p in rows)


def capture_linked(*, user_id, league_id):
    from . import server as s, database as db
    before = binding_identity(user_id, league_id)
    if not before:
        _fail('provider_roster_coverage_unavailable')
    row = before['binding']
    if str(row['user_id']) != user_id:
        _fail('provider_account_binding_unavailable')
    platform = row['platform']
    try:
        if platform == 'espn':
            cred = db.get_espn_credential(user_id) or {}
            s2, swid = None, cred.get('swid')
            if cred:
                try:
                    s2 = s._sleeper_write.decrypt_token(cred['espn_s2_encrypted'])
                except Exception:
                    _fail('espn_credentials_unavailable')
            if row['espn_auth'] == 'cookie' and not (s2 and swid):
                _fail('espn_credentials_unavailable')
            raw = espn.fetch_league(league_id, row['espn_season'] or s._ESPN_DEFAULT_SEASON,
                                    espn_s2=s2, swid=swid)
            if raw.get('seasonId') != (row['espn_season'] or s._ESPN_DEFAULT_SEASON):
                _fail('provider_season_mismatch')
            team_id = row['espn_my_team_id']
            team = next((t for t in espn.parse_league(raw)['teams'] if t.team_id == team_id), None)
            if swid and (not team or espn.swid_identity(swid) not in team.owner_swids):
                _fail('league_seat_changed')
            snapshot = parse_espn(raw, league_id=league_id, user_id=user_id,
                                  team_id=team_id, xwalk=s._shared_crosswalk())
            basis = 'current_provider_owner' if swid else 'existing_public_import_binding'
            native_sf = snapshot.slots.count('QB') > 1 or 'SUPER_FLEX' in snapshot.slots
            if native_sf and db.get_league_scoring(league_id) != 'sf_tep':
                _fail('provider_scoring_format_changed')
            snapshot.provenance.update(valuation_basis='stored_configured_format',
                native_tep_verification='unknown', requested_season=row['espn_season'] or s._ESPN_DEFAULT_SEASON)
        else:
            year = row['platform_season'] or s._MFL_DEFAULT_YEAR
            cred = db.get_mfl_credential(user_id) or {}
            cookie = None
            if cred:
                try:
                    cookie = s._sleeper_write.decrypt_token(cred['cookie_encrypted'])
                except Exception:
                    _fail('mfl_credentials_unavailable')
            if row['platform_auth'] == 'cookie' and not cookie:
                _fail('mfl_credentials_unavailable')
            fid = str(row['platform_my_team'] or '')
            if cookie:
                own = [l for l in mfl.fetch_my_leagues(cookie, year)
                       if str(l['league_id']) == league_id]
                if not any(str(l.get('franchise_id')) == fid for l in own):
                    _fail('league_seat_changed')
            host = row['platform_host'] or mfl.resolve_host(league_id, year)
            raw = mfl.fetch_league_bundle(league_id, year, host, cookie=cookie)
            snapshot = parse_mfl(raw, league_id=league_id, user_id=user_id,
                                 franchise_id=fid, xwalk=s._shared_crosswalk())
            basis = 'current_provider_owner' if cookie else 'existing_public_import_binding'
            if mfl.detect_scoring_format(raw) != db.get_league_scoring(league_id):
                _fail('provider_scoring_format_changed')
            snapshot.provenance.update(valuation_basis='existing_canonical_format_mapping',
                requested_season=year)
    except (espn.EspnAuthError, mfl.MflAuthError):
        _fail(platform + '_auth_required')
    except (espn.EspnError, mfl.MflError):
        raise GradingError(platform + '_unavailable', 503) from None
    if before != binding_identity(user_id, league_id):
        _fail('inputs_changed_during_capture')
    snapshot.provenance.update(binding=before, ownership_basis=basis, league_id=league_id)
    return snapshot
