"""Derived tables, rebuilt from the base tables (local only, no network).

``trades`` / ``trade_assets`` (one row per player, pick, FAAB amount or
in-trade release, with from and to roster), ``standings_weeks``,
``outcomes``, ``reconstruction_checks``, ``trade_rosters``; pick resolution
(research-plan §5.7) and cleaning flags (§5.8, flag never delete).
"""
from __future__ import annotations

import json
from collections import defaultdict

from . import reconstruct as rc
from . import standings as stnd
from .store import DERIVED_TABLES

DAY_MS = 24 * 3600 * 1000
RECON_TARGET = 0.98
STARTUP_DRAFT_MIN_ROUNDS = 10


def _j(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"))


def _insert(conn, table, row):
    conn.execute(f"INSERT OR REPLACE INTO {table} ({','.join(row)}) VALUES"
                 f" ({','.join('?' * len(row))})", tuple(row.values()))


# -- picks --------------------------------------------------------------------

def _lineage_seasons(conn) -> dict:
    out = defaultdict(dict)
    for r in conn.execute("SELECT li.lineage_id, li.league_id, li.season FROM league_index li"
                          " JOIN pull_checkpoints c ON c.league_id=li.league_id"):
        out[r["lineage_id"]][r["season"]] = r["league_id"]
    return out


def resolve_drafted(conn, league_id, rnd, orig):
    """(pick_no, slot, player_id) once that draft has happened, else None."""
    drafts = conn.execute("SELECT * FROM drafts WHERE league_id=? AND status='complete'"
                          " ORDER BY start_time DESC", (league_id,)).fetchall()
    for d in drafts:
        s2r = json.loads(d["slot_to_roster_json"] or "{}")
        slot = next((int(s) for s, rid in s2r.items() if rid == orig), None)
        if slot is None:
            order = json.loads(d["draft_order_json"] or "{}")
            owner = conn.execute("SELECT owner_key FROM rosters WHERE league_id=? AND roster_id=?",
                                 (league_id, orig)).fetchone()
            if owner is not None and owner["owner_key"] in order:
                slot = order[owner["owner_key"]]
        if slot is None:
            continue
        p = conn.execute("SELECT pick_no, player_id FROM draft_picks WHERE draft_id=? AND"
                         " round=? AND draft_slot=?", (d["draft_id"], rnd, slot)).fetchone()
        if p is not None:
            return p["pick_no"], slot, p["player_id"]
    return None


def standing_at(conn, league_id, prev_league_id, roster_id, leg):
    """The original team's standing at the trade's date."""
    r = conn.execute("SELECT * FROM standings_weeks WHERE league_id=? AND roster_id=? AND week<?"
                     " ORDER BY week DESC LIMIT 1", (league_id, roster_id, leg or 0)).fetchone()
    if r is not None:
        return r, "current_season"
    if prev_league_id:
        r = conn.execute("SELECT * FROM standings_weeks WHERE league_id=? AND roster_id=?"
                         " ORDER BY week DESC LIMIT 1", (prev_league_id, roster_id)).fetchone()
        if r is not None:
            return r, "prior_season"
    return None, "none"


# -- trades -------------------------------------------------------------------

def trade_assets(t: dict) -> list:
    adds, drops = json.loads(t["adds_json"]), json.loads(t["drops_json"])
    out = []
    for pid in sorted(adds):
        out.append({"asset_type": "player", "player_id": pid, "from_roster": drops.get(pid),
                    "to_roster": adds[pid]})
    for pid in sorted(set(drops) - set(adds)):
        out.append({"asset_type": "release", "player_id": pid, "from_roster": drops[pid],
                    "to_roster": None})
    for p in json.loads(t["draft_picks_json"]):
        out.append({"asset_type": "pick", "pick_season": p.get("season"),
                    "pick_round": p.get("round"), "pick_orig_roster": p.get("roster_id"),
                    "from_roster": p.get("previous_owner_id"), "to_roster": p.get("owner_id")})
    for w in json.loads(t["waiver_budget_json"]):
        out.append({"asset_type": "faab", "faab_amount": w.get("amount"),
                    "from_roster": w.get("sender"), "to_roster": w.get("receiver")})
    return out


def _moves(t):
    s = {("p", pid, t["drops"].get(pid), to) for pid, to in t["adds"].items()}
    s |= {("k", p.get("season"), p.get("round"), p.get("roster_id"),
           p.get("previous_owner_id"), p.get("owner_id")) for p in t["picks"]}
    return s


def _mirror(m):
    return {(x[0], x[1], x[3], x[2]) if x[0] == "p" else (x[0], x[1], x[2], x[3], x[5], x[4])
            for x in m}


class _SeasonCache:
    def __init__(self, conn, pulled, size=8):
        self.conn, self.pulled, self.size, self.d = conn, pulled, size, {}

    def get(self, lid, default=None):
        if lid not in self.pulled:
            return default
        if lid not in self.d:
            if len(self.d) >= self.size:
                self.d.pop(next(iter(self.d)))
            self.d[lid] = rc.load_season(self.conn, lid)
        return self.d[lid]

    __getitem__ = get


def derive_all(conn, log=print) -> dict:
    conn.execute("BEGIN")
    try:
        for table in DERIVED_TABLES:
            conn.execute(f"DELETE FROM {table}")
        # Lineage then season order, so a season's predecessor is still in the
        # small cache: the whole store is never held in memory at once.
        pulled = [r[0] for r in conn.execute(
            "SELECT c.league_id FROM pull_checkpoints c LEFT JOIN league_index li"
            " ON li.league_id=c.league_id ORDER BY li.lineage_id, c.season, c.league_id")]
        pulled_set = set(pulled)
        seasons = _SeasonCache(conn, pulled_set)
        recon_share = {}
        for lid in pulled:
            st_rows = stnd.compute(conn, lid)
            for row in st_rows:
                _insert(conn, "standings_weeks", row)
            last = max((r["week"] for r in st_rows), default=None)
            final = [r for r in st_rows if r["week"] == last]
            for row in stnd.outcome_rows(conn, lid, final):
                _insert(conn, "outcomes", row)
            _insert(conn, "standings_checks", stnd.check_reported(conn, lid, final))
            sd = seasons[lid]
            prev = seasons.get(sd.previous_league_id) if sd.previous_league_id else None
            checks = rc.verify_season(sd, prev)
            for row in checks:
                _insert(conn, "reconstruction_checks", row)
            ins = [c for c in checks if c["kind"] == "in_season"]
            recon_share[lid] = (sum(c["matched"] for c in ins) / len(ins)) if ins else None
        lineage_of = {r[0]: r[1] for r in conn.execute(
            "SELECT league_id, lineage_id FROM league_index")}
        lin_seasons = _lineage_seasons(conn)
        n_trades = 0
        for lid in pulled:
            sd = seasons[lid]
            prev = seasons.get(sd.previous_league_id) if sd.previous_league_id else None
            lg = conn.execute("SELECT * FROM leagues WHERE league_id=?", (lid,)).fetchone()
            owners = {r["roster_id"]: r["owner_key"] for r in conn.execute(
                "SELECT roster_id, owner_key FROM rosters WHERE league_id=?", (lid,))}
            drafts = conn.execute("SELECT start_time, last_picked, status, rounds FROM drafts"
                                  " WHERE league_id=?", (lid,)).fetchall()
            trades = [dict(t) for t in conn.execute(
                "SELECT * FROM transactions WHERE league_id=? AND type='trade' AND"
                " status='complete'", (lid,))]
            for t in trades:
                t["adds"], t["drops"] = json.loads(t["adds_json"]), json.loads(t["drops_json"])
                t["picks"] = json.loads(t["draft_picks_json"])
                t["roster_ids"] = json.loads(t["roster_ids_json"])
                t["ts"] = t["status_updated"] or t["created"] or 0
            lineage = lineage_of.get(lid)
            for t in trades:
                flags = []
                mirror = _mirror(_moves(t))
                for u in trades:
                    if (u is not t and t["ts"] < u["ts"] <= t["ts"] + DAY_MS
                            and set(u["roster_ids"]) == set(t["roster_ids"])
                            and _moves(u) == mirror):
                        flags.append("reversed_within_day")
                        break
                if any(owners.get(int(r)) is None for r in t["roster_ids"]):
                    flags.append("orphan_side")
                for d in drafts:
                    start = d["start_time"] or 0
                    end = d["last_picked"] or start
                    if start and start <= t["ts"] and (d["status"] != "complete" or t["ts"] <= end):
                        flags.append("during_startup_draft"
                                     if (d["rounds"] or 0) >= STARTUP_DRAFT_MIN_ROUNDS
                                     else "during_draft")
                        break
                if len(trades) < 3:
                    flags.append("low_trade_league")
                if lg["unusual_scoring"]:
                    flags.append("unusual_scoring")
                share = recon_share.get(lid)
                if share is not None and share < RECON_TARGET:
                    flags.append("recon_below_target")
                st = rc.state_for_trade(sd, prev, {
                    "transaction_id": t["transaction_id"], "leg": t["leg"],
                    "status_updated": t["status_updated"], "created": t["created"],
                    "roster_ids": t["roster_ids"]})
                for rid, players in st["rosters"].items():
                    _insert(conn, "trade_rosters", {
                        "league_id": lid, "transaction_id": t["transaction_id"],
                        "roster_id": rid, "method": st["method"],
                        "base_league_id": st["base_league"], "base_week": st["base_week"],
                        "players_json": _j(sorted(players)), "alt_method": st["alt_method"],
                        "alt_agrees": st["alt_agrees"]})
                assets = trade_assets(t)
                for i, a in enumerate(assets):
                    row = {"league_id": lid, "transaction_id": t["transaction_id"],
                           "asset_idx": i, **a}
                    if a["asset_type"] == "pick":
                        res = None
                        target = lin_seasons.get(lineage, {}).get(
                            int(a["pick_season"]) if str(a["pick_season"]).isdigit() else None)
                        if target:
                            res = resolve_drafted(conn, target, a["pick_round"],
                                                  a["pick_orig_roster"])
                        if res:
                            row.update(pick_resolution="drafted", pick_no=res[0],
                                       pick_slot=res[1], pick_player_id=res[2])
                        stand, basis = standing_at(conn, lid, sd.previous_league_id
                                                   if prev is not None else None,
                                                   a["pick_orig_roster"], t["leg"])
                        if not res:
                            row["pick_resolution"] = "standing" if stand is not None else "unresolved"
                        row["standing_basis"] = basis
                        if stand is not None:
                            row.update(orig_rank_at_trade=stand["rank"], orig_wins=stand["wins"],
                                       orig_losses=stand["losses"], orig_ties=stand["ties"],
                                       orig_points_for=stand["points_for"])
                    _insert(conn, "trade_assets", row)
                _insert(conn, "trades", {
                    "league_id": lid, "transaction_id": t["transaction_id"],
                    "season": sd.season, "lineage_id": lineage, "leg": t["leg"],
                    "created": t["created"], "status_updated": t["status_updated"],
                    "n_rosters": len(t["roster_ids"]), "roster_ids_json": t["roster_ids_json"],
                    "creator_key": t["creator_key"],
                    "n_players": sum(1 for a in assets if a["asset_type"] == "player"),
                    "n_picks": sum(1 for a in assets if a["asset_type"] == "pick"),
                    "faab_total": sum(a.get("faab_amount") or 0 for a in assets
                                      if a["asset_type"] == "faab"),
                    "timing": "in_season" if st["method"] == "in_season" else "offseason",
                    "recon_method": st["method"], "recon_agree": st["alt_agrees"],
                    "flags_json": _j(sorted(set(flags)))})
                n_trades += 1
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return {"league_seasons": len(pulled), "trades": n_trades}
