"""Prod-replay deck/gap measurement — runs IDENTICALLY on origin/main and on
fix/package-benchmark-sweetener against a FROZEN prod fixture (no DB access).

    python3 <abs path to this file> <fixture.json> <out.json>   # from a repo root

Run it from the BRANCH tree and from a `git archive origin/main` scratch tree to
get the two sides.  The prod EXTRACTOR that builds <fixture.json> is deliberately
NOT committed (it holds a prod connection helper) — same posture as the arm-B
audit's probe scripts; the extraction recipe is in TEST_LEDGER 2026-08-21b.
Set DATABASE_URL to one shared throwaway SQLite file for BOTH runs, so neither
tree can read a different local experiments/model_config table.

Recipe follows docs/reviews/2026-08-19-armb-audit-claims-3-4.md §7:
pool+seed from player_value_history; each member's board rebuilt by the REAL
RankingService.replay_from_db over their real swipe_decisions, with
users.tier_overrides restored as _elo_overrides; confidence = comparison_counts(),
placements = placement_bands(); prod model_config loaded into both modules' _cfg;
owned picks injected exactly as server._inject_owned_picks does (tier_ladder
pricing => stored pool_value); cards from the REAL TradeService.generate_trades
under live config/features.json.
"""
import json, os, sys

ROOT = os.getcwd()
sys.path.insert(0, ROOT)

import backend.feature_flags as ff              # noqa: E402
import backend.trade_service as ts              # noqa: E402
import backend.ranking_service as rs            # noqa: E402
from backend.ranking_service import Player, RankingService   # noqa: E402
from backend.trade_service import League, LeagueMember, TradeService  # noqa: E402

GAP_LINE = 1539.0
FIX = json.load(open(sys.argv[1]))
OUT = sys.argv[2]
FMT = FIX["scoring_format"]
LEAGUE_ID = FIX["league"]["sleeper_league_id"]


# ---------------------------------------------------------------- pool + seed
master = {r["player_id"]: r for r in FIX["players"]}
seed_elo, players = {}, {}
for row in FIX["seed_rows"]:
    pid = row["player_id"]
    m = master.get(pid)
    if not m:
        continue
    players[pid] = Player(
        id=pid, name=m.get("full_name") or pid, position=m.get("position") or "WR",
        team=m.get("team") or "FA", age=int(m.get("age") or 25),
        years_experience=int(m.get("years_exp") or 0),
        depth_chart_position=m.get("depth_chart_position"),
        depth_chart_order=(int(m["depth_chart_order"])
                           if m.get("depth_chart_order") is not None else None),
        injury_status=m.get("injury_status"), injury_body_part=m.get("injury_body_part"),
        birth_date=m.get("birth_date"), height=m.get("height"), weight=m.get("weight"),
        college=m.get("college"),
        search_rank=(int(m["search_rank"]) if m.get("search_rank") is not None else None),
        adp=(float(m["adp"]) if m.get("adp") is not None else None))
    seed_elo[pid] = float(row["consensus_elo"])

# ------------------------------------------------------------ owned-pick prep
# server._owned_pick_assets under the default tier_ladder pricing mode: the
# priced value IS the stored pool_value, cap = picks_pool_cap (prod config).
_OWNED_PICK_SEARCH_RANK = {1: 40, 2: 90, 3: 140}
CAP = int(FIX["model_config"].get("picks_pool_cap", 6))


def build_pick_assets():
    by_owner = {}
    for p in FIX["draft_picks"]:
        if p.get("owner_user_id") and (p.get("pool_value") or 0) > 0:
            by_owner.setdefault(p["owner_user_id"], []).append(p)
    out = {}
    for owner, picks in by_owner.items():
        picks.sort(key=lambda p: float(p["pool_value"]), reverse=True)
        assets = []
        for p in picks[:CAP]:
            pool_v = float(p["pool_value"])
            inv = (ts.value_to_elo(pool_v) - 1200.0) / 6.0
            assets.append(Player(
                id=p["pick_id"], name=f"{p['season']} Round {p['round']}",
                position="PICK", team="PICK", age=0, years_experience=0,
                pick_value=round(inv, 3),
                search_rank=_OWNED_PICK_SEARCH_RANK.get(int(p.get("round") or 4), 200)))
        if assets:
            out[owner] = assets
    return out


PICK_ASSETS = build_pick_assets()
PICK_ELOS = {pa.id: 1200.0 + 6.0 * float(pa.pick_value or 0.0)
             for a in PICK_ASSETS.values() for pa in a}

# ------------------------------------------------------- per-member boards
MEMBERS = FIX["members"]
RANK_COUNTS = FIX["member_ranking_counts"]
USERS = {u["sleeper_user_id"]: u for u in FIX["users"]}
PREFS = {p["user_id"]: p for p in FIX["prefs"]}
ASSET_PREFS = {}
for r in FIX["asset_prefs"]:
    ASSET_PREFS.setdefault(r["user_id"], {}).setdefault(r["list_type"], set()).add(r["player_id"])

ROSTERS = {m["user_id"]: [pid for pid in m["roster"] if pid in players] for m in MEMBERS}


def apply_prod_cfg():
    """Prod model_config into BOTH modules' _cfg, on top of code defaults."""
    ts._cfg.clear(); ts._cfg.update(ts._DEFAULT_CFG)
    rs._cfg.clear(); rs._cfg.update(rs._DEFAULT_CFG)
    for k, v in FIX["model_config"].items():
        if k in ts._cfg:
            ts._cfg[k] = float(v)
        if k in rs._cfg:
            rs._cfg[k] = float(v)


def live_flags(**over):
    cfg = json.load(open(os.path.join(ROOT, "config/features.json")))
    base = dict(ff.DEFAULT_FLAGS)
    base.update({k: v for k, v in cfg.items() if isinstance(v, bool)})
    base.update(over)
    ff._flags_cache = base


def build_board(uid):
    """REAL replay: RankingService.replay_from_db over this member's real
    swipes + their persisted tier_overrides. Returns (elo_map, counts, bands)."""
    svc = RankingService(players=list(players.values()), seed_ratings=dict(seed_elo))
    svc._scoring_format = FMT
    svc._user_id = uid
    swipes = FIX["swipes"].get(uid) or []
    svc.replay_from_db(swipes)
    raw = USERS.get(uid, {}).get("tier_overrides")
    if raw:
        try:
            ov = json.loads(raw)
        except Exception:
            ov = {}
        # dual-format shape: {fmt: {pid: elo}} or legacy flat {pid: elo}
        block = ov.get(FMT) if isinstance(ov, dict) and FMT in ov else ov
        if isinstance(block, dict):
            stamps = block.get("__OVERRIDE_AT__") or {}
            for pid, elo in block.items():
                if pid == "__OVERRIDE_AT__" or pid not in players:
                    continue
                try:
                    svc._elo_overrides[pid] = float(elo)
                except (TypeError, ValueError):
                    continue
            if isinstance(stamps, dict):
                svc._elo_override_at.update(
                    {k: v for k, v in stamps.items() if k in svc._elo_overrides})
    rk = svc.get_rankings(position=None)
    return ({rp.player.id: rp.elo for rp in rk.rankings},
            svc.comparison_counts(), svc.placement_bands(), len(swipes))


def build_service(viewer, boards):
    """A TradeService whose league carries every OTHER member, boarded members
    holding their replayed board (has_rankings True)."""
    pl = dict(players)
    for a in PICK_ASSETS.values():
        for pa in a:
            pl[pa.id] = pa
    members = []
    for m in MEMBERS:
        uid = m["user_id"]
        if uid == viewer:
            continue
        boarded = RANK_COUNTS.get(uid, 0) > 0 and uid in boards
        elo = dict(boards[uid][0]) if boarded else dict(seed_elo)
        elo.update(PICK_ELOS)
        roster = list(ROSTERS.get(uid, [])) + [pa.id for pa in PICK_ASSETS.get(uid, [])]
        members.append(LeagueMember(user_id=uid, username=m.get("username") or uid,
                                    roster=roster, elo_ratings=elo,
                                    has_rankings=boarded))
    svc = TradeService(players=pl)
    svc.add_league(League(league_id=LEAGUE_ID, name=FIX["league"].get("name") or "L",
                          platform=FIX["league"].get("platform") or "sleeper",
                          members=members))
    return svc


def gen_kwargs(viewer, boards, svc, **over):
    elo, counts, bands, _ = boards[viewer]
    user_elo = dict(elo); user_elo.update(PICK_ELOS)
    smap = dict(seed_elo); smap.update(PICK_ELOS)
    roster = list(ROSTERS.get(viewer, [])) + [pa.id for pa in PICK_ASSETS.get(viewer, [])]
    pref = PREFS.get(viewer) or {}
    ap = ASSET_PREFS.get(viewer, {})
    opp_outlooks = {u: (PREFS[u].get("team_outlook")) for u in PREFS
                    if u != viewer and PREFS[u].get("team_outlook")}
    grand = sum((p.get("pick_value") or 0.0) for p in FIX["draft_picks"])
    shares = {}
    if grand > 0:
        for p in FIX["draft_picks"]:
            o = p.get("owner_user_id")
            if o:
                shares[o] = shares.get(o, 0.0) + (p.get("pick_value") or 0.0) / grand
    kw = dict(
        user_id=viewer, user_elo=user_elo, user_roster=roster, league_id=LEAGUE_ID,
        seed_elo=smap, confidence=counts, placements=bands,
        outlook=pref.get("team_outlook"),
        fairness_threshold=0.75, max_per_opponent=5,
        acquire_positions=json.loads(pref.get("acquire_positions") or "[]") or None,
        trade_away_positions=json.loads(pref.get("trade_away_positions") or "[]") or None,
        scoring_format=FMT,
        opponent_outlooks=opp_outlooks or None,
        opponent_pick_shares=shares or None,
        untouchable_ids=ap.get("untouchable") or None,
        target_ids=ap.get("target") or None,
        not_interested_ids=ap.get("not_interested") or None,
        bypass_need_gate=False, exclusion_keys=None,
    )
    kw.update(over)
    return kw


def stats(cards):
    rows = []
    for c in cards:
        gap = abs((c.give_value or 0.0) - (c.receive_value or 0.0))
        rows.append({
            "basis": getattr(c, "basis", "divergence"),
            "gap": round(gap, 1),
            "over": gap > GAP_LINE,
            "sweet": bool(getattr(c, "gap_sweetener", None)),
            "sweet_info": getattr(c, "gap_sweetener", None),
            "n_give": len(c.give_player_ids), "n_recv": len(c.receive_player_ids),
            "target": c.target_user_id,
            "key": "|".join(sorted(c.give_player_ids)) + "=>" + "|".join(sorted(c.receive_player_ids)),
        })
    return rows


def main():
    apply_prod_cfg()
    boards = {}
    for m in MEMBERS:
        uid = m["user_id"]
        if RANK_COUNTS.get(uid, 0) > 0 or FIX["swipes"].get(uid):
            boards[uid] = build_board(uid)
    viewers = [u for u in boards if RANK_COUNTS.get(u, 0) > 0]
    viewers.sort()
    lim = int(os.environ.get("FTF_REPLAY_LIMIT") or 0)
    if lim:
        viewers = viewers[:lim]

    results = []
    from backend.bakeoff_profiles import model_a, model_challenger
    import backend.bakeoff_runner as bo

    for path, v3 in (("v3", True), ("v2_only", False)):
        live_flags(**{"trade_engine.v2": True, "trade_engine.v3": v3,
                      "trade.bakeoff": False})
        for viewer in viewers:
            svc = build_service(viewer, boards)
            base = gen_kwargs(viewer, boards, svc)

            mode = (USERS.get(viewer, {}).get("stud_tax_mode")
                    or ts.STUD_TAX_DEFAULT)
            if mode not in ts.STUD_TAX_MODES:
                mode = ts.STUD_TAX_DEFAULT

            def rec(arm, cards, note=None):
                results.append({"path": path, "viewer": viewer,
                                "username": USERS.get(viewer, {}).get("username") or viewer,
                                "outlook": (PREFS.get(viewer) or {}).get("team_outlook"),
                                "arm": arm, "note": note, "cards": stats(cards)})

            apply_prod_cfg()
            with ts.stud_tax_override(mode):
                rec("B_current", svc.generate_trades(**base))
            if "sweetener_gap_threshold" in ts._DEFAULT_CFG:
                apply_prod_cfg()
                ts._cfg["sweetener_gap_threshold"] = 0.0
                with ts.stud_tax_override(mode):
                    rec("B_current_sweet_off", svc.generate_trades(**base))
            apply_prod_cfg()
            with model_a(), ts.stud_tax_override(mode):
                rec("A_baseline", svc.generate_trades(**base))
            apply_prod_cfg()
            with model_challenger(), ts.stud_tax_override(mode):
                rec("D_challenger", svc.generate_trades(**base))
            if not v3:
                apply_prod_cfg()
                try:
                    with ts.stud_tax_override(mode):
                        rec("C_gen_v2", bo.gen_v2_cards(svc, dict(base)))
                except Exception as e:          # noqa: BLE001
                    results.append({"path": path, "viewer": viewer, "arm": "C_gen_v2",
                                    "error": repr(e)[:300], "cards": []})
            print(f"  done {path} {viewer}", file=sys.stderr, flush=True)

    json.dump({"tree": os.path.basename(ROOT), "results": results,
               "viewers": viewers,
               "board_sizes": {u: boards[u][3] for u in boards}}, open(OUT, "w"))
    print(json.dumps({"viewers": len(viewers), "rows": len(results)}))


if __name__ == "__main__":
    main()
