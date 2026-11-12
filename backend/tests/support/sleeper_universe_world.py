"""A fully synthetic Sleeper for the universe-crawler tests. No network.

Payload shapes follow docs/integrations/sleeper.md §3.2 and the captured
fixtures (league, rosters, users, transactions, matchups with
``players_points`` / ``starters_points``, drafts, picks, traded_picks,
brackets, ``/state/nfl``). Every id, name and timestamp is invented.

The simulator plays each league-season event by event in time order and
records the truth the tests compare against: each trade's rosters just
before it, each week's roster, its own standings. Names are deliberately
long and distinctive so a leak is unmistakable.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

DAY = 86_400_000
HOUR = 3_600_000
BASE = "https://api.sleeper.app/v1"


def U(i):
    return str(9100000000000000000 + i)


def L(n):
    return str(8100000000000000000 + n)


def ms(y, m, d):
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp() * 1000)


SEASON_START = {2023: ms(2023, 9, 5), 2024: ms(2024, 9, 3), 2025: ms(2025, 9, 2),
                2026: ms(2026, 9, 8)}


class WorldKilled(Exception):
    """Raised by the fake transport to simulate a kill mid-run."""


class World:
    def __init__(self):
        self.routes: dict = {}
        self.calls: list = []
        self.kill_after: int | None = None
        self.status_script: list = []          # statuses returned before any route
        self.faults: dict = {}                  # path -> (status, body bytes), served first
        self.user_leagues: dict = {}            # (uid, season) -> [league obj]
        self.users: dict = {}
        self.next_pid = 5000
        self.next_tid = 7100000000000000000
        self.next_did = 6100000000000000000
        self.truth_pre_trade: dict = {}         # txid -> {rid: set}
        self.truth_trades: dict = {}            # league_id -> [txid] (complete)
        self.truth_week_rosters: dict = {}      # (league, week) -> {rid: set}
        self.truth_standings: dict = {}         # league -> {rid: dict}
        self.specs: dict = {}
        self.nfl_state = {"season": "2026", "week": 4, "season_type": "regular",
                          "leg": 4, "display_week": 4}
        self.routes["state/nfl"] = self.nfl_state

    # -- transport ---------------------------------------------------------
    def transport(self, url, headers, timeout):
        path = url[len(BASE) + 1:]
        self.calls.append(path)
        if self.kill_after is not None and len(self.calls) > self.kill_after:
            raise WorldKilled(path)
        if self.status_script:
            st = self.status_script.pop(0)
            if st != 200:
                return st, {}, b""
        if path in self.faults:
            st, body = self.faults[path]
            return st, {}, body
        if path not in self.routes:
            # Like Sleeper: an unknown league or user is null; a list endpoint
            # with nothing in it (an empty leg, a user with no leagues that
            # season, a week after the season) is an empty list.
            parts = path.split("/")
            is_list = (parts[0] == "user" and len(parts) > 2) or \
                      (parts[0] in ("league", "draft") and len(parts) > 2)
            return 200, {}, b"[]" if is_list else b"null"
        return 200, {}, json.dumps(self.routes[path]).encode()

    # -- helpers -----------------------------------------------------------
    def pid(self):
        self.next_pid += 1
        return str(self.next_pid)

    def tid(self):
        self.next_tid += 1
        return str(self.next_tid)

    def user(self, i):
        uid = U(i)
        if uid not in self.users:
            self.users[uid] = {
                "user_id": uid, "username": f"secretusername{i:03d}",
                "display_name": f"Secret Display Person {i:03d}",
                "avatar": hashlib.md5(f"avatar{i}".encode()).hexdigest(),
                "metadata": {"team_name": f"Secret Team Name Number {i:03d}",
                             "mention_pn": "on"},
                "is_bot": False}
            self.routes[f"user/secretusername{i:03d}"] = {
                "user_id": uid, "username": f"secretusername{i:03d}",
                "display_name": f"Secret Display Person {i:03d}",
                "avatar": self.users[uid]["avatar"]}
        return uid

    def all_names(self) -> set:
        out = set()
        for u in self.users.values():
            out.update([u["username"], u["display_name"], u["avatar"],
                        u["metadata"]["team_name"]])
        for spec in self.specs.values():
            out.update([spec["name"], f"Secret Draft Name {spec['league_id']}",
                        f"Nickname For Star {spec['league_id']}"])
        return out

    def all_user_ids(self) -> set:
        return set(self.users)

    def listing_add(self, uid, season, obj):
        lst = self.user_leagues.setdefault((uid, season), [])
        if all(o["league_id"] != obj["league_id"] for o in lst):
            lst.append(obj)
        self.routes[f"user/{uid}/leagues/nfl/{season}"] = lst

    # -- leagues that are only listed (skipped by the filter) ---------------
    def listed_only(self, n, season, owner_idx, *, type_=2, best_ball=0, teams=10,
                    status="in_season", prev=None):
        obj = {"league_id": L(n), "season": str(season), "status": status,
               "total_rosters": teams, "name": f"Secret Skipped League {n}",
               "previous_league_id": prev, "sport": "nfl", "season_type": "regular",
               "avatar": None, "metadata": {"latest_league_winner_roster_id": "1"},
               "settings": {"type": type_, "best_ball": best_ball, "num_teams": teams},
               "roster_positions": ["QB", "RB", "WR", "TE", "FLEX", "BN"],
               "scoring_settings": {"rec": 1.0}}
        self.routes[f"league/{L(n)}"] = obj
        for i in owner_idx:
            self.listing_add(self.user(i), season, obj)
        return obj

    # -- a simulated lineage ----------------------------------------------
    def lineage(self, specs: list[dict]):
        """specs oldest first. Each spec: n (league no), season, teams,
        owners {rid: user idx or None}, co_owners {rid: [idx]}, status,
        played, reg_weeks, median, divisions, rounds, script [...], flags."""
        carry, pick_owner, prev_id = None, {}, specs[0].get("prev")
        for spec in specs:
            spec = dict(spec)
            spec["league_id"] = L(spec["n"])
            spec["prev"] = prev_id
            spec.setdefault("name", f"Super Secret League Name {spec['n']}")
            self.specs[spec["league_id"]] = spec
            carry = self._season(spec, carry, pick_owner)
            prev_id = spec["league_id"]

    def _season(self, spec, carry, pick_owner):
        lid, season, n = spec["league_id"], spec["season"], spec["teams"]
        t0 = SEASON_START[season]
        reg = spec.get("reg_weeks", 3)
        pws = 0 if spec.get("no_playoffs") else reg + 1
        played = spec.get("played", reg + 2)
        rounds = spec.get("rounds", 10 if carry is None else 2)
        owners = spec["owners"]
        co = spec.get("co_owners", {})
        uid_of = {rid: (self.user(i) if i is not None else None) for rid, i in owners.items()}
        for rid, idxs in co.items():
            for i in idxs:
                self.user(i)
        divisions = spec.get("divisions", 0)
        div_of = {rid: (1 if rid <= n // 2 else 2) if divisions else None for rid in owners}
        league_obj = {
            "league_id": lid, "season": str(season), "status": spec.get("status", "complete"),
            "total_rosters": n, "name": spec["name"], "previous_league_id": spec["prev"],
            "sport": "nfl", "season_type": "regular",
            "avatar": hashlib.md5(spec["name"].encode()).hexdigest(),
            "draft_id": None,
            "bracket_id": None if spec.get("no_playoffs") else 1,
            "loser_bracket_id": None if spec.get("no_playoffs") else 2,
            "company_id": None, "shard": 7, "last_message_id": "123456789012345678",
            "metadata": {"latest_league_winner_roster_id": "1", "auto_continue": "on",
                         "custom_text": "Secret commissioner note text"},
            "settings": {"type": 2, "best_ball": 0, "num_teams": n, "playoff_teams": 4,
                         "playoff_week_start": pws, "waiver_type": 2, "waiver_budget": 100,
                         "league_average_match": int(spec.get("median", 0)),
                         "taxi_slots": 2, "reserve_slots": 2, "trade_deadline": 11,
                         "divisions": divisions},
            "roster_positions": ["QB", "RB", "WR", "TE", "SUPER_FLEX", "BN", "BN", "TAXI"],
            "scoring_settings": spec.get("scoring", {"rec": 1.0, "bonus_rec_te": 0.5,
                                                     "pass_td": 4.0}),
        }
        self.routes[f"league/{lid}"] = league_obj
        for rid in owners:
            for uid in [uid_of[rid], *[U(i) for i in co.get(rid, [])]]:
                if uid:
                    self.listing_add(uid, season, league_obj)
        rosters = {rid: set() for rid in owners} if carry is None else {
            rid: set(v) for rid, v in carry.items()}
        events = []   # (time, kind, payload)

        # Draft (startup for a first season, else rookie) ------------------
        did = str(self.next_did + spec["n"] * 10 + season % 100)
        d_start, d_end = t0 - 30 * DAY, t0 - 30 * DAY + HOUR
        slot_to_roster = {str(s): n + 1 - s for s in range(1, n + 1)}
        def make_picks():
            out, pick_no = [], 0
            for r in range(1, rounds + 1):
                order = range(1, n + 1) if (carry is not None or r % 2) else range(n, 0, -1)
                for slot in order:
                    pick_no += 1
                    orig = slot_to_roster[str(slot)]
                    holder = pick_owner.get((season, r, orig), orig)
                    p = self.pid()
                    out.append({"draft_id": did, "pick_no": pick_no, "round": r,
                                "draft_slot": slot, "roster_id": holder, "player_id": p,
                                "is_keeper": None, "picked_by": uid_of.get(holder) or "",
                                "metadata": {"first_name": "Rookiefirst",
                                             "last_name": f"Last{p}", "position": "WR",
                                             "team": "KC", "news_updated": "1700000000000"}})
            return out

        picks = None
        draft_obj = {"draft_id": did, "league_id": lid, "season": str(season),
                     "season_type": "regular", "status": "complete",
                     "type": "snake" if carry is None else "linear",
                     "start_time": d_start, "last_picked": d_end, "created": d_start - DAY,
                     "settings": {"rounds": rounds, "teams": n, "pick_timer": 3600},
                     "slot_to_roster_id": slot_to_roster,
                     "draft_order": {uid_of[rid]: s for s, rid in
                                     ((int(k), v) for k, v in slot_to_roster.items())
                                     if uid_of.get(rid)},
                     "creators": [uid_of[1]] if uid_of.get(1) else [],
                     "metadata": {"name": f"Secret Draft Name {lid}",
                                  "description": "Secret draft description text"}}
        self.routes[f"league/{lid}/drafts"] = [draft_obj]
        self.routes[f"draft/{did}"] = draft_obj

        # Scripted + generic transactions -----------------------------------
        txns_by_leg: dict = {}

        def txn(leg, ts, type_, adds=None, drops=None, rids=None, status="complete",
                picks_=None, faab=None, notes=None, bid=None, creator_rid=None):
            t = {"type": type_, "status": status, "transaction_id": self.tid(), "leg": leg,
                 "roster_ids": rids or sorted({*(adds or {}).values(), *(drops or {}).values()}),
                 "creator": uid_of.get(creator_rid or (rids or [1])[0]) or U(1),
                 "consenter_ids": rids or None, "adds": adds or None, "drops": drops or None,
                 "draft_picks": picks_ or [], "waiver_budget": faab or [],
                 "settings": ({"seq": 1, "waiver_bid": bid} if bid is not None else None),
                 "metadata": ({"notes": notes} if notes else None),
                 "created": ts - 1000, "status_updated": ts, "player_map": None}
            txns_by_leg.setdefault(leg, []).append(t)
            events.append((ts, "txn", t))
            return t

        def roster_pid(rid, k=0):
            """The k-th smallest player on roster rid at simulation time."""
            return sorted(rosters[rid], key=int)[k]

        script = spec.get("script", [])
        # The script is a list of (time, callable(sim_api)) evaluated in order
        # during the replay below, so it can read the rosters at that moment.
        sched = list(script)
        for w in range(1, played + 1):
            tw = t0 + (w - 1) * 7 * DAY + DAY
            sched.append((tw + 1 * HOUR, ("waiver", w)))
            sched.append((tw + 2 * HOUR, ("failed_waiver", w)))
            sched.append((tw + 3 * HOUR, ("free_agent", w)))
            sched.append((tw + 6 * DAY, ("snapshot", w)))
        if spec.get("status", "complete") == "complete":
            sched.append((t0 + played * 7 * DAY + DAY, ("post_season", played + 1)))
        # Partial / future weeks for a season in progress.
        sched.sort(key=lambda e: e[0])
        events_sorted = []
        api = {"txn": txn, "rosters": rosters, "roster_pid": roster_pid, "pid": self.pid,
               "pick_owner": pick_owner, "season": season, "t0": t0, "lid": lid,
               "truth": self}
        draft_done = False
        week_points = {}
        for ts, item in sched:
            if not draft_done and ts > d_end:
                picks = make_picks()
                self._apply_picks(rosters, picks)
                draft_done = True
            if callable(item):
                t = item(api, ts)
                if t is not None and t["type"] == "trade" and t["status"] == "complete":
                    self.truth_pre_trade[t["transaction_id"]] = {
                        int(r): set(rosters.get(int(r), set())) for r in t["roster_ids"]}
                    self.truth_trades.setdefault(lid, []).append(t["transaction_id"])
                    for pk in t["draft_picks"]:
                        pick_owner[(int(pk["season"]), pk["round"], pk["roster_id"])] = pk["owner_id"]
                if t is not None and t["status"] == "complete":
                    self._apply(rosters, t)
                continue
            kind, w = item
            rid_a = ((w - 1) % n) + 1
            if kind == "waiver" and rosters[rid_a]:
                p = self.pid()
                t = txn(w, ts, "waiver", {p: rid_a}, {roster_pid(rid_a): rid_a}, [rid_a],
                        notes="Your waiver claim was processed successfully!", bid=w)
                self._apply(rosters, t)
            elif kind == "failed_waiver":
                txn(w, ts, "waiver", {self.pid(): (w % n) + 1}, None, [(w % n) + 1],
                    status="failed", notes="This player was claimed by another owner.", bid=1)
            elif kind == "free_agent":
                rid = ((w + 1) % n) + 1
                t = txn(w, ts, "free_agent", {self.pid(): rid}, None, [rid])
                self._apply(rosters, t)
            elif kind == "post_season":
                t = txn(w, ts, "free_agent", {self.pid(): 2}, None, [2])
                self._apply(rosters, t)
            elif kind == "snapshot":
                self.truth_week_rosters[(lid, w)] = {r: set(v) for r, v in rosters.items()}
                week_points[w] = self._week_rows(spec, w, rosters, n, pws, partial=False)
        if not draft_done:
            picks = make_picks()
            self._apply_picks(rosters, picks)
        self.routes[f"draft/{did}/picks"] = picks
        self.draft_picks_truth = getattr(self, "draft_picks_truth", {})
        self.draft_picks_truth[lid] = picks
        # The week in progress (partial points) and unplayed weeks.
        last_week = pws + 1
        for w in range(played + 1, last_week + 1):
            if spec.get("status", "complete") == "complete":
                break
            rows = self._week_rows(spec, w, rosters, n, pws, partial=(w == played + 1),
                                   future=(w > played + 1))
            week_points[w] = rows
        for w, rows in week_points.items():
            self.routes[f"league/{lid}/matchups/{w}"] = rows
        for leg, ts in txns_by_leg.items():
            self.routes[f"league/{lid}/transactions/{leg}"] = ts

        # Standings (the simulator's own implementation) + reported record ---
        table = {rid: {"w": 0, "l": 0, "t": 0, "pf": 0.0, "pa": 0.0} for rid in owners}
        for w in range(1, min(played, reg) + 1):
            rows = week_points[w]
            pts = {r["roster_id"]: r["points"] for r in rows}
            bym = {}
            for r in rows:
                if r["matchup_id"] is not None:
                    bym.setdefault(r["matchup_id"], []).append(r["roster_id"])
            for pair in bym.values():
                if len(pair) == 2:
                    a, b = pair
                    table[a]["pa"] += pts[b]
                    table[b]["pa"] += pts[a]
                    if pts[a] > pts[b]:
                        table[a]["w"] += 1; table[b]["l"] += 1
                    elif pts[b] > pts[a]:
                        table[b]["w"] += 1; table[a]["l"] += 1
                    else:
                        table[a]["t"] += 1; table[b]["t"] += 1
            if spec.get("median"):
                vals = sorted(pts.values())
                mid = (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2 if len(vals) % 2 == 0 \
                    else vals[len(vals) // 2]
                for r, p in pts.items():
                    table[r]["w" if p > mid else "l" if p < mid else "t"] += 1
            for r, p in pts.items():
                table[r]["pf"] += p
        self.truth_standings[lid] = table
        mis = spec.get("misreport")
        roster_rows = []
        for rid in owners:
            tr = table[rid]
            pf, pa = round(tr["pf"], 2), round(tr["pa"], 2)
            settings = {"wins": tr["w"] + (mis[1] if mis and mis[0] == rid else 0),
                        "losses": tr["l"], "ties": tr["t"],
                        "fpts": int(pf), "fpts_decimal": int(round((pf - int(pf)) * 100)),
                        "fpts_against": int(pa),
                        "fpts_against_decimal": int(round((pa - int(pa)) * 100)),
                        "ppts": int(pf) + 10, "ppts_decimal": 0,
                        "waiver_budget_used": 3, "total_moves": 4}
            if div_of.get(rid):
                settings["division"] = div_of[rid]
            roster_rows.append({
                "roster_id": rid, "league_id": lid, "owner_id": uid_of[rid],
                "co_owners": [U(i) for i in co.get(rid, [])] or None,
                "players": sorted(rosters[rid], key=int) + [None], "starters": [],
                "reserve": [], "taxi": [], "keepers": None, "settings": settings,
                "metadata": {"team_name": f"Roster Secret Team {lid}-{rid}",
                             "record": "WLWLW",
                             f"p_nick_{sorted(rosters[rid], key=int)[0] if rosters[rid] else 0}":
                             f"Nickname For Star {lid}"},
                "player_map": None})
        self.routes[f"league/{lid}/rosters"] = roster_rows
        members = [dict(self.users[u], is_owner=(u == uid_of.get(1)))
                   for u in sorted({x for x in uid_of.values() if x}
                                   | {U(i) for v in co.values() for i in v})]
        self.routes[f"league/{lid}/users"] = members
        self.routes[f"league/{lid}/traded_picks"] = [
            {"season": str(s), "round": r, "roster_id": o, "owner_id": h,
             "previous_owner_id": o} for (s, r, o), h in sorted(pick_owner.items())
            if h != o and s >= season]
        if spec.get("no_playoffs"):
            # Sleeper answers null for a bracket that does not exist (live, 2026-11-12).
            self.routes[f"league/{lid}/winners_bracket"] = None
            self.routes[f"league/{lid}/losers_bracket"] = None
        elif spec.get("status", "complete") == "complete":
            win = [{"r": 1, "m": 1, "t1": 1, "t2": 4, "w": 1, "l": 4},
                   {"r": 1, "m": 2, "t1": 2, "t2": 3, "w": 2, "l": 3},
                   {"r": 2, "m": 3, "t1": 1, "t2": 2, "w": 2, "l": 1, "p": 1,
                    "t1_from": {"w": 1}, "t2_from": {"w": 2}},
                   {"r": 2, "m": 4, "t1": 4, "t2": 3, "w": 3, "l": 4, "p": 3,
                    "t1_from": {"l": 1}, "t2_from": {"l": 2}}]
            lose = [{"r": 1, "m": 5, "t1": 5, "t2": 8, "w": 5, "l": 8},
                    {"r": 1, "m": 6, "t1": 6, "t2": 7, "w": 6, "l": 7},
                    {"r": 2, "m": 7, "t1": 5, "t2": 6, "w": 6, "l": 5, "p": 1}]
            self.routes[f"league/{lid}/winners_bracket"] = win
            self.routes[f"league/{lid}/losers_bracket"] = lose
        else:
            self.routes[f"league/{lid}/winners_bracket"] = []
            self.routes[f"league/{lid}/losers_bracket"] = []
        return {rid: set(v) for rid, v in rosters.items()}

    @staticmethod
    def _apply(rosters, t):
        for p, r in (t.get("drops") or {}).items():
            rosters.setdefault(int(r), set()).discard(p)
        for p, r in (t.get("adds") or {}).items():
            rosters.setdefault(int(r), set()).add(p)

    @staticmethod
    def _apply_picks(rosters, picks):
        for p in picks:
            rosters.setdefault(p["roster_id"], set()).add(p["player_id"])

    def _week_rows(self, spec, w, rosters, n, pws, partial=False, future=False):
        rows = []
        for rid in sorted(rosters):
            players = sorted(rosters[rid], key=int)
            pp = {p: (0.0 if future else round((int(p) % 7) + w * 0.5, 2)) for p in players}
            if partial:
                pp = {p: (v if i == 0 else 0.0) for i, (p, v) in enumerate(pp.items())}
            starters = players[:3]
            sp = [pp[p] for p in starters]
            pts = 0.0 if future else round(sum(sp) + rid / 100.0, 2)
            rows.append({"roster_id": rid, "matchup_id": None, "points": pts,
                         "custom_points": None, "players": players, "starters": starters,
                         "starters_points": sp, "players_points": pp})
        # Pairings: odd weeks (1,2),(3,4)...; even weeks (1,3),(2,4) per block of 4.
        mid = 0
        ids = sorted(rosters)
        pairs = []
        if w % 2:
            pairs = [(ids[i], ids[i + 1]) for i in range(0, len(ids) - 1, 2)]
        else:
            i = 0
            while i < len(ids):
                blk = ids[i:i + 4]
                pairs += [(blk[0], blk[2]), (blk[1], blk[3])] if len(blk) == 4 else \
                    [(blk[j], blk[j + 1]) for j in range(0, len(blk) - 1, 2)]
                i += 4
        if spec.get("bye_week") == w:
            pairs = pairs[:-1]                      # the last pair has no game
        if not (future and spec.get("unpaired_future")) and not (future and w >= pws):
            for a, b in pairs:
                mid += 1
                for r in rows:
                    if r["roster_id"] in (a, b):
                        r["matchup_id"] = mid
        if spec.get("bye_week") == w:
            # one unpaired roster with a lone matchup id
            rows[-1]["matchup_id"] = 99
        if spec.get("tie_week") == w:
            rows[1]["points"] = rows[0]["points"]
        return rows


# ---------------------------------------------------------------------------
# The standard world used by most tests
# ---------------------------------------------------------------------------

def _trade(api, leg, ts, moves, picks=(), faab=()):
    """moves: [(from_rid, to_rid, k)] -- the k-th smallest player of from_rid."""
    adds, drops = {}, {}
    for fr, to, k in moves:
        p = api["roster_pid"](fr, k)
        adds[p], drops[p] = to, fr
    rids = sorted({x for m in moves for x in m[:2]})
    return api["txn"](leg, ts, "trade", adds, drops, rids,
                      picks_=[{"season": str(s), "round": r, "roster_id": o,
                               "previous_owner_id": fr, "owner_id": to}
                              for s, r, o, fr, to in picks],
                      faab=[{"sender": a, "receiver": b, "amount": x} for a, b, x in faab])


def week_ts(season, week, hours):
    return SEASON_START[season] + (week - 1) * 7 * DAY + DAY + hours * HOUR


def standard_world() -> World:
    w = World()
    owners8 = {r: r for r in range(1, 9)}
    a24, a25, a26 = SEASON_START[2024], SEASON_START[2025], SEASON_START[2026]
    mirror = {}

    def a26_t1(api, ts):
        t = _trade(api, 2, ts, [(1, 2, 0), (2, 1, 0)], picks=[(2027, 1, 1, 1, 2)])
        mirror["t1"] = t
        return t

    def a26_t2(api, ts):
        t1 = mirror["t1"]
        adds = {p: t1["drops"][p] for p in t1["adds"]}
        drops = {p: t1["adds"][p] for p in t1["adds"]}
        return api["txn"](2, ts, "trade", adds, drops, [1, 2],
                          picks_=[{"season": "2027", "round": 1, "roster_id": 1,
                                   "previous_owner_id": 2, "owner_id": 1}])

    def commish(api, ts):
        return api["txn"](2, ts, "commissioner", {api["pid"](): 4}, None, [4], creator_rid=1)

    def mystery(api, ts):
        return api["txn"](3, ts, "mystery_move", {api["pid"](): 6},
                          {api["roster_pid"](6, 1): 6}, [6])

    w.lineage([
        {"n": 101, "season": 2024, "teams": 8, "owners": owners8, "co_owners": {2: [9]},
         "status": "complete", "reg_weeks": 3, "played": 5, "rounds": 10,
         "script": [
             (week_ts(2024, 2, 5), lambda api, ts: _trade(
                 api, 2, ts, [(1, 3, 0), (3, 1, 0)], picks=[(2025, 1, 3, 3, 1)])),
             (week_ts(2024, 2, 6), lambda api, ts: _trade(
                 api, 2, ts, [(5, 6, 0), (6, 7, 0), (7, 5, 0)], faab=[(7, 5, 7)])),
             (week_ts(2024, 3, 5), lambda api, ts: api["txn"](
                 3, ts, "trade", {api["roster_pid"](4): 5}, {api["roster_pid"](4): 4},
                 [4, 5], status="pending")),
         ]},
        {"n": 102, "season": 2025, "teams": 8, "owners": {**owners8, 8: None},
         "co_owners": {2: [9]}, "status": "complete", "reg_weeks": 3, "played": 5,
         "script": [
             (a25 - 40 * DAY, lambda api, ts: _trade(
                 api, 1, ts, [(2, 4, 0), (4, 2, 0)],
                 picks=[(2026, 2, 2, 2, 4), (2027, 1, 2, 2, 4)])),
             (a25 - 30 * DAY + HOUR // 2, lambda api, ts: _trade(
                 api, 1, ts, [(5, 6, 1), (6, 5, 1)])),
             (week_ts(2025, 2, 5), lambda api, ts: _trade(api, 2, ts, [(8, 1, 0), (1, 8, 0)])),
         ]},
        {"n": 103, "season": 2026, "teams": 8, "owners": owners8, "co_owners": {2: [9]},
         "status": "in_season", "reg_weeks": 6, "played": 3,
         "script": [
             (a26 - 40 * DAY, lambda api, ts: _trade(
                 api, 1, ts, [(3, 7, 0), (7, 3, 0)], picks=[(2026, 1, 7, 7, 3)])),
             (week_ts(2026, 2, 5), a26_t1),
             (week_ts(2026, 2, 6), a26_t2),
             (week_ts(2026, 2, 7), commish),
             (week_ts(2026, 3, 5), mystery),
             (week_ts(2026, 3, 6), lambda api, ts: _trade(api, 3, ts, [(4, 5, 0), (5, 4, 0)])),
         ]},
    ])
    w.routes[f"league/{L(200)}"] = {"league_id": L(200), "season": "2023", "status": "complete",
                                    "total_rosters": 10, "name": "Secret Old League",
                                    "previous_league_id": None,
                                    "settings": {"type": 2, "best_ball": 0}}
    w.lineage([
        {"n": 201, "season": 2026, "prev": L(200), "teams": 10,
         "owners": {1: 3, **{r: 8 + r for r in range(2, 11)}}, "status": "in_season",
         "reg_weeks": 6, "played": 3, "median": 1, "divisions": 2, "tie_week": 1,
         "bye_week": 2, "unpaired_future": True,
         "script": [(week_ts(2026, 2, 5), lambda api, ts: _trade(
             api, 2, ts, [(1, 2, 0), (2, 1, 0)]))]},
    ])
    w.lineage([
        {"n": 301, "season": 2025, "teams": 8,
         "owners": {1: 10, **{r: 18 + r for r in range(2, 9)}}, "status": "complete",
         "reg_weeks": 3, "played": 5, "misreport": (3, 1),
         "script": [(week_ts(2025, 2, 5), lambda api, ts: _trade(
             api, 2, ts, [(1, 2, 0), (2, 1, 0)])),
                    (week_ts(2025, 3, 5), lambda api, ts: _trade(
             api, 3, ts, [(3, 4, 0), (4, 3, 0)]))]},
    ])
    w.lineage([
        {"n": 401, "season": 2026, "teams": 8,
         "owners": {1: 20, **{r: 28 + r for r in range(2, 9)}}, "status": "in_season",
         "reg_weeks": 6, "played": 3, "script": []},
    ])
    w.listed_only(501, 2026, [1], type_=0)
    w.listed_only(502, 2026, [1], best_ball=1)
    w.listed_only(503, 2026, [1], teams=6)
    w.listed_only(504, 2026, [1], status="pre_draft")
    w.listed_only(505, 2025, [1], type_=1)
    return w


SEEDS = ["secretusername001"]


def add_no_playoff_league(w: World) -> str:
    """A complete 2024 dynasty league with playoffs switched off: settings
    playoff_week_start 0, bracket_id null, both brackets answer null. Listed
    for the seed user, so discovery finds it at hop 0. Returns its id."""
    w.lineage([
        {"n": 601, "season": 2024, "teams": 8,
         "owners": {1: 1, **{r: 38 + r for r in range(2, 9)}}, "status": "complete",
         "reg_weeks": 5, "played": 5, "no_playoffs": True,
         "script": [(week_ts(2024, 3, 5), lambda api, ts: _trade(
             api, 3, ts, [(1, 2, 0), (2, 1, 0)]))]},
    ])
    return L(601)


# ---------------------------------------------------------------------------
# Running the crawler against a world
# ---------------------------------------------------------------------------

TEST_KEY = "test-hmac-key-0123456789abcdefghijklmnop"
OTHER_KEY = "another-hmac-key-9876543210zyxwvutsrqpo"


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def run_cli(world, data_dir, *args, key=TEST_KEY, seeds=SEEDS, log=None, lock_path=None):
    """Runs the CLI against the world. The key comes from env; the key file
    and the lock live in a temp folder beside the data folder, never the
    operator's real ones."""
    from pathlib import Path
    from backend.sleeper_universe.cli import main
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    if seeds is not None:
        (data_dir / "seeds.txt").write_text("\n".join(seeds) + "\n")
    clock = FakeClock()
    lines = []
    side = data_dir.parent / f".{data_dir.name}-test-side"
    side.mkdir(exist_ok=True)
    code = main([args[0], "--data-dir", str(data_dir),
                 "--key-file", str(side / "hmac.key"), *args[1:]], transport=world.transport,
                sleep=clock.sleep, clock=clock, env={"SLEEPER_UNIVERSE_HMAC_KEY": key},
                log=log or lines.append, lock_path=lock_path or side / "crawler.lock")
    return code, lines


def connect(data_dir):
    import sqlite3
    from pathlib import Path
    c = sqlite3.connect(str(Path(data_dir) / "universe.sqlite"))
    c.row_factory = sqlite3.Row
    return c
