"""Breadth-first discovery: seed users -> their leagues -> owners -> leagues.

Hops: a seed user's leagues are hop 0. Expanding a hop-h league (reading its
rosters for owners and co-owners, then each new owner's leagues) yields hop
h+1 leagues. Leagues at hop >= ``max_hops`` are kept but not expanded, so the
default ``max_hops=2`` reaches leagues at hop 0, 1 and 2.

The frontier persists in SQLite (``league_index.expanded``, and per user the
seasons already listed in ``discovery_users``, by keyed hash only), so a
restart continues where it stopped. Raw user ids live in memory for the
current user expansion only.

Lineage: ``previous_league_id`` is followed back while the season is inside
the run's range. A lineage id, once assigned, never changes: a league joins
the lineage of an indexed predecessor or successor, else starts its own with
its league id. Adding earlier seasons later therefore keeps the ids of the
lineages already in the store (seasons are listed newest first, and kept
leagues whose predecessor is missing are walked back first). If two separately
started fragments meet, the older-assigned id is kept and the merge counted.

Cap: ``cap`` counts distinct kept lineages. A new lineage met once the cap is
full is recorded as skipped with reason ``cap_reached`` and revived by a later
run with a higher cap.
"""
from __future__ import annotations

from urllib.parse import quote

from .identity import harvest

KEPT_STATUSES = frozenset({"in_season", "post_season", "complete"})
SKIP_REASONS = ("not_dynasty", "best_ball", "team_count", "not_started",
                "cap_reached", "not_found")


def classify(obj: dict) -> str | None:
    """The dynasty filter. None = keep; else the skip reason."""
    s = obj.get("settings") or {}
    if s.get("type") != 2:
        return "not_dynasty"
    if s.get("best_ball") == 1:
        return "best_ball"
    n = obj.get("total_rosters") or s.get("num_teams")
    if not isinstance(n, int) or not 8 <= n <= 16:
        return "team_count"
    if obj.get("status") not in KEPT_STATUSES:
        return "not_started"
    return None


def _prev(obj) -> str | None:
    p = obj.get("previous_league_id")
    return None if p in (None, "", "0", 0) else str(p)


def _season(obj) -> int | None:
    try:
        return int(obj.get("season"))
    except (TypeError, ValueError):
        return None


class Discoverer:
    def __init__(self, store, client, ring, col, *, seasons, max_hops=2,
                 cap=3000, log=print):
        self.store, self.client, self.ring, self.col = store, client, ring, col
        self.seasons = sorted({int(s) for s in seasons}, reverse=True)
        self.min_season = min(self.seasons)
        self.max_hops = max_hops
        self.cap = cap
        self.emit = log
        self.stats = {"users_expanded": 0, "leagues_expanded": 0, "seeds_unresolved": 0,
                      "lineage_merges": 0, "revived": 0}

    def cap_reached(self) -> bool:
        return self.store.kept_lineage_count() >= self.cap

    def _get(self, path):
        obj = self.client.get(path)
        harvest(obj, self.col)
        return obj

    # -- entry -----------------------------------------------------------
    def run(self, seeds: list[str]) -> dict:
        self._reopen_for_new_seasons()
        self._extend_lineages_back()
        self._revive_deferred()
        for i, seed in enumerate(seeds, 1):
            if self.cap_reached():
                break
            uid = self._resolve_seed(seed, i)
            if uid is not None:
                self.expand_user(uid, 0)
        while not self.cap_reached():
            row = self.store.next_league_to_expand(self.max_hops, self.seasons)
            if row is None:
                break
            self.expand_league(row["league_id"], row["hop"])
        self.store.commit()
        self.stats["kept_lineages"] = self.store.kept_lineage_count()
        return self.stats

    def _reopen_for_new_seasons(self):
        row = self.store.conn.execute(
            "SELECT value FROM meta WHERE key='discovery_seasons'").fetchone()
        before = set(int(x) for x in row[0].split(",")) if row and row[0] else set()
        if before and not set(self.seasons) <= before:
            # New seasons: every kept league's owners must be listed again for
            # the new seasons (users only fetch the seasons they lack).
            self.store.conn.execute("UPDATE league_index SET expanded=0 WHERE kept=1")
        merged = ",".join(str(s) for s in sorted(before | set(self.seasons)))
        self.store.conn.execute("INSERT OR REPLACE INTO meta VALUES ('discovery_seasons', ?)",
                                (merged,))

    def _resolve_seed(self, seed: str, line_no: int):
        seed = seed.strip()
        if seed.isdigit():
            return seed
        obj = self._get(f"/user/{quote(seed, safe='')}")
        uid = obj.get("user_id") if isinstance(obj, dict) else None
        if not uid:
            self.stats["seeds_unresolved"] += 1
            self.emit(f"seed line {line_no}: not found")
            return None
        return str(uid)

    # -- expansion ----------------------------------------------------------
    def expand_user(self, uid: str, hop: int) -> None:
        key = self.ring.user_key(uid)
        self.col.user_keys.add(key)
        todo = [s for s in self.seasons if s not in self.store.user_seasons_done(key)]
        if not todo:
            return
        for season in todo:  # newest first: keeps lineage ids stable
            leagues = self._get(f"/user/{uid}/leagues/nfl/{season}") or []
            for obj in leagues if isinstance(leagues, list) else []:
                if isinstance(obj, dict):
                    self.consider(obj, hop)
        self.store.mark_user(key, hop, todo)
        self.store.add_user_keys([key])
        self.stats["users_expanded"] += 1

    def expand_league(self, league_id: str, hop: int) -> None:
        rosters = self._get(f"/league/{league_id}/rosters") or []
        uids: list[str] = []
        for r in rosters if isinstance(rosters, list) else []:
            if not isinstance(r, dict):
                continue
            for u in [r.get("owner_id"), *(r.get("co_owners") or [])]:
                if u and str(u) not in uids:
                    uids.append(str(u))
        for uid in uids:
            if self.cap_reached():
                return  # not marked expanded: a later run with room resumes it
            self.expand_user(uid, hop + 1)
        self.store.mark_expanded(league_id)
        self.stats["leagues_expanded"] += 1

    # -- leagues --------------------------------------------------------------
    def consider(self, obj: dict, hop: int) -> None:
        lid = str(obj.get("league_id") or "")
        season = _season(obj)
        if not lid or season is None or self.store.league_row(lid) is not None:
            return
        if season not in self.seasons:
            return
        reason = classify(obj)
        if reason:
            self.store.add_league(lid, season, hop, self._neighbour_lineage(lid, obj),
                                  _prev(obj), False, reason, obj.get("status"))
            return
        chain = self._walk_back(obj)
        lineage = self._lineage_for(chain)
        if not self.store.lineage_exists(lineage) and self.cap_reached():
            for o in chain:
                self.store.add_league(str(o["league_id"]), _season(o), hop, lineage,
                                      _prev(o), False, "cap_reached", o.get("status"))
            return
        for o in chain:
            r = classify(o)
            self.store.add_league(str(o["league_id"]), _season(o), hop, lineage,
                                  _prev(o), r is None, r, o.get("status"))

    def _walk_back(self, obj: dict) -> list[dict]:
        """[obj, its predecessor, ...] while unindexed and inside the range."""
        chain = [obj]
        cur = obj
        for _ in range(len(self.seasons) + 1):
            prev = _prev(cur)
            if prev is None or self.store.league_row(prev) is not None:
                break
            pobj = self._get(f"/league/{prev}")
            ps = _season(pobj) if isinstance(pobj, dict) else None
            if ps is None or ps < self.min_season or ps not in self.seasons:
                break
            chain.append(pobj)
            cur = pobj
        return chain

    def _neighbour_lineage(self, lid, obj):
        succ = self.store.successor_of(lid)
        if succ is not None and succ["lineage_id"]:
            return succ["lineage_id"]
        prev = _prev(obj)
        row = self.store.league_row(prev) if prev else None
        if row is not None and row["lineage_id"]:
            return row["lineage_id"]
        return lid

    def _lineage_for(self, chain: list[dict]) -> str:
        succ = self.store.successor_of(str(chain[0]["league_id"]))
        prev = _prev(chain[-1])
        pred = self.store.league_row(prev) if prev else None
        a = succ["lineage_id"] if succ is not None and succ["lineage_id"] else None
        b = pred["lineage_id"] if pred is not None and pred["lineage_id"] else None
        if a and b and a != b:
            self.store.relabel_lineage(a, b)
            self.stats["lineage_merges"] += 1
            return b
        return a or b or str(chain[0]["league_id"])

    def _extend_lineages_back(self):
        """Seasons were added: walk kept leagues back into the new range."""
        for row in self.store.unlinked_kept(self.seasons):
            cur_prev = row["previous_league_id"]
            lineage = row["lineage_id"]
            for _ in range(len(self.seasons)):
                if not cur_prev or self.store.league_row(cur_prev) is not None:
                    break
                pobj = self._get(f"/league/{cur_prev}")
                ps = _season(pobj) if isinstance(pobj, dict) else None
                if ps is None or ps not in self.seasons:
                    break
                r = classify(pobj)
                self.store.add_league(str(pobj["league_id"]), ps, row["hop"], lineage,
                                      _prev(pobj), r is None, r, pobj.get("status"))
                cur_prev = _prev(pobj)

    def _revive_deferred(self):
        if self.cap_reached():
            return
        for row in self.store.deferred_leagues():
            if self.cap_reached():
                return
            obj = self._get(f"/league/{row['league_id']}")
            self.store.drop_league(row["league_id"])
            if not isinstance(obj, dict):
                self.store.add_league(row["league_id"], None, row["hop"], None, None,
                                      False, "not_found", None)
                continue
            self.consider(obj, row["hop"])
            self.stats["revived"] += 1
