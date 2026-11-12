"""Pilot report (research-plan §8.2), aggregates only, and the leak scan.

Leak scan method. Every file under the data folder is read (``.gz`` files
decompressed; the SQLite file read both as raw bytes and cell by cell), except
the operator's own inputs: the seed file and the key file. It fails on:

a. a dropped field NAME (``identity.NAME_KEYS``: username, display_name,
   team_name, name, avatar, metadata, ...) appearing as a JSON key in any file
   or as a column of any table;
b. a raw Sleeper user id: every 15-20 digit run in every file is HMAC'd with
   the run's key and looked up in ``user_keys`` (every key the crawler ever
   produced) -- so raw ids are found without ever storing them; plus, during
   a pull run, a direct search for the raw ids held in memory;
c. during a pull run only: the name VALUES seen in name fields (held in
   memory, never written) compared with every string the store holds (every
   JSON key and value, every SQLite text cell and the strings inside JSON
   cells). Exact match, names of 4+ characters, excluding the store's own
   vocabulary (statuses, positions, codes). The store keeps no free text, so a
   leaked name would be a whole value; a name embedded inside a longer
   string is not looked for.

Output never contains an id or a name: only file names and hit counts.
"""
from __future__ import annotations

import gzip
import json
import re
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .identity import KEY_FILE, NAME_KEYS
from .store import DB_NAME, SEED_FILE

ID_RE = re.compile(rb"(?<![0-9])[0-9]{15,20}(?![0-9])")
EST_REQUESTS_PER_LEAGUE_SEASON = 44

BACKWARD_NOTE = ("backward reconstruction cannot see roster changes before week 1 "
                 "that left no transaction or draft pick (commissioner edits, roster resets)")


def _walk(obj, keys: set, strings: list):
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(str(k))
            strings.append(str(k))
            _walk(v, keys, strings)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, keys, strings)
    elif isinstance(obj, str):
        strings.append(obj)


def _field_hit(keys: set) -> list:
    return sorted(k for k in keys if k in NAME_KEYS or k.startswith("p_nick_")
                  or k.startswith("team_name"))


# Values the store legitimately holds; a user whose name equals one of these
# would otherwise be a false hit.
VOCAB = frozenset({
    "trade", "waiver", "free_agent", "commissioner", "complete", "failed", "pending",
    "in_season", "post_season", "pre_draft", "drafting", "regular", "rookie", "snake",
    "linear", "auction", "outbid", "roster_full", "already_played", "processed", "other",
    "winners", "losers", "player", "release", "pick", "faab", "drafted", "standing",
    "unresolved", "forward", "backward", "none", "current_season", "prior_season",
    "offseason", "offseason_forward", "offseason_backward",
    "QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX", "REC_FLEX", "WRRB_FLEX", "K", "DEF",
    "BN", "TAXI", "IR", "IDP_FLEX", "DL", "LB", "DB", "nfl"})


def leak_scan(data_dir: Path, ring, *, names=None, raw_ids=None,
              exclude=(SEED_FILE, KEY_FILE)) -> dict:
    data_dir = Path(data_dir)
    db = data_dir / DB_NAME
    known = set()
    if db.exists():
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        known = {r[0] for r in c.execute("SELECT user_key FROM user_keys")}
        c.close()
    names = {n for n in (names or ()) if len(n) >= 4 and n not in VOCAB}
    raw_ids = {str(i) for i in (raw_ids or ())}
    excluded = {str(x) for x in exclude}
    res = {"ok": True, "files_scanned": 0, "bytes_scanned": 0, "field_hits": {},
           "id_hits": {}, "raw_id_hits": {}, "name_hits": {},
           "excluded": sorted(excluded), "name_values_checked": len(names),
           "raw_ids_checked": len(raw_ids)}

    def bump(kind, label, n):
        if n:
            res[kind][label] = res[kind].get(label, 0) + n

    def check_ids(label, blob: bytes):
        toks = {m.decode() for m in ID_RE.findall(blob)}
        bump("id_hits", label, sum(1 for t in toks if ring.user_key(t) in known))
        bump("raw_id_hits", label, len(toks & raw_ids))

    for path in sorted(p for p in data_dir.rglob("*") if p.is_file()):
        rel = str(path.relative_to(data_dir))
        if path.name in excluded or rel in excluded:
            continue
        res["files_scanned"] += 1
        keys: set = set()
        name_hit: set = set()
        if path.name == DB_NAME:
            # Raw bytes in chunks (the file can be gigabytes), then cell by cell.
            with open(path, "rb") as f:
                tail = b""
                while True:
                    chunk = f.read(64 << 20)
                    if not chunk:
                        break
                    res["bytes_scanned"] += len(chunk)
                    check_ids(rel, tail + chunk)
                    tail = chunk[-24:]
            c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'"
                                  " AND name NOT LIKE 'sqlite_%'"):
                keys.update(r[1] for r in c.execute(f"PRAGMA table_info({t})"))
                for row in c.execute(f"SELECT * FROM {t}"):
                    for v in row:
                        if not isinstance(v, str):
                            continue
                        if v in names:
                            name_hit.add(v)
                        if len(v) > 64:   # may span overflow pages in the raw bytes
                            check_ids(f"{rel}:{t}", v.encode("utf-8"))
                        if v[:1] in "[{":
                            strings: list = []
                            try:
                                _walk(json.loads(v), keys, strings)
                            except ValueError:
                                pass
                            name_hit.update(x for x in strings if x in names)
            c.close()
        else:
            blob = path.read_bytes()
            if path.suffix == ".gz":
                blob = gzip.decompress(blob)
            res["bytes_scanned"] += len(blob)
            check_ids(rel, blob)
            strings = []
            try:
                _walk(json.loads(blob), keys, strings)
            except ValueError:
                strings.append(blob.decode("utf-8", "replace"))
            name_hit.update(x for x in strings if x in names)
        bump("name_hits", rel, len(name_hit))
        hits = _field_hit(keys)
        if hits:
            res["field_hits"][rel] = hits
    res["ok"] = not (res["field_hits"] or res["id_hits"] or res["raw_id_hits"]
                     or res["name_hits"])
    return res


def _dist(xs) -> dict:
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"n": 0}
    xs = sorted(xs)
    return {"n": len(xs), "total": round(sum(xs), 3), "mean": round(statistics.mean(xs), 3),
            "median": statistics.median(xs), "p90": xs[min(len(xs) - 1, int(0.9 * len(xs)))],
            "max": xs[-1], "min": xs[0]}


def build_report(conn) -> dict:
    q = lambda sql, *a: conn.execute(sql, a).fetchall()  # noqa: E731
    rep: dict = {}
    pulled = q("SELECT league_id, season, requests, seconds FROM pull_checkpoints")
    tcount = {r[0]: r[1] for r in q("SELECT league_id, COUNT(*) FROM trades GROUP BY league_id")}
    rep["league_seasons_pulled"] = len(pulled)
    rep["trades_total"] = sum(tcount.values())
    rep["trades_per_league_season"] = _dist([tcount.get(r["league_id"], 0) for r in pulled])
    by_season = defaultdict(list)
    for r in pulled:
        by_season[r["season"]].append(tcount.get(r["league_id"], 0))
    rep["trades_per_league_season_by_season"] = {str(s): _dist(v) for s, v in sorted(by_season.items())}
    rep["leagues_kept"] = q("SELECT COUNT(*) FROM league_index WHERE kept=1")[0][0]
    rep["lineages_kept"] = q("SELECT COUNT(DISTINCT lineage_id) FROM league_index WHERE kept=1")[0][0]
    rep["leagues_skipped_by_reason"] = {r[0]: r[1] for r in q(
        "SELECT reason, COUNT(*) FROM skipped_leagues GROUP BY reason ORDER BY reason")}
    rep["pull_failures_by_kind"] = {r[0]: r[1] for r in q(
        "SELECT kind, COUNT(*) FROM pull_failures GROUP BY kind")}
    rep["requests_per_league_season"] = _dist([r["requests"] for r in pulled])
    rep["requests_estimate_per_league_season"] = EST_REQUESTS_PER_LEAGUE_SEASON
    rep["seconds_per_league_season"] = _dist([r["seconds"] for r in pulled])
    runs = q("SELECT command, requests, seconds FROM runs WHERE status='ok'")
    rep["requests_by_command"] = {c: sum(r["requests"] or 0 for r in runs if r["command"] == c)
                                  for c in sorted({r["command"] for r in runs})}
    checks = q("SELECT kind, matched FROM reconstruction_checks")
    rk = defaultdict(lambda: [0, 0])
    for c in checks:
        rk[c["kind"]][0] += c["matched"]
        rk[c["kind"]][1] += 1
    rep["reconstruction_match"] = {k: {"matched": v[0], "checked": v[1],
                                       "rate": round(v[0] / v[1], 4) if v[1] else None}
                                   for k, v in sorted(rk.items())}
    rep["reconstruction_target"] = 0.98
    ls = q("SELECT league_id, SUM(matched)*1.0/COUNT(*) AS s FROM reconstruction_checks"
           " WHERE kind='in_season' GROUP BY league_id")
    rep["league_seasons_below_target"] = sum(1 for r in ls if r["s"] < 0.98)
    rep["trades_by_recon_method"] = {r[0]: r[1] for r in q(
        "SELECT recon_method, COUNT(*) FROM trades GROUP BY recon_method ORDER BY 1")}
    agree = q("SELECT recon_agree, COUNT(*) FROM trades WHERE recon_agree IS NOT NULL"
              " GROUP BY recon_agree")
    n_ag = sum(r[1] for r in agree)
    rep["forward_backward_agreement"] = {
        "compared": n_ag, "agree": sum(r[1] for r in agree if r[0] == 1),
        "rate": round(sum(r[1] for r in agree if r[0] == 1) / n_ag, 4) if n_ag else None}
    rep["backward_method_caveat"] = BACKWARD_NOTE
    legs = defaultdict(Counter)
    for r in q("SELECT leg, status_updated, created FROM trades"):
        ts = r["status_updated"] or r["created"]
        month = (datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m")
                 if ts else "unknown")
        legs[str(r["leg"])][month] += 1
    rep["trade_dates_by_leg"] = {k: dict(sorted(v.items()))
                                 for k, v in sorted(legs.items(), key=lambda kv: int(kv[0])
                                                    if kv[0].isdigit() else 99)}
    picks = {r[0]: r[1] for r in q("SELECT pick_resolution, COUNT(*) FROM trade_assets"
                                   " WHERE asset_type='pick' GROUP BY pick_resolution")}
    n_picks = sum(picks.values())
    rep["traded_picks"] = {"total": n_picks, **picks,
                           "share_resolved_to_slot": round(picks.get("drafted", 0) / n_picks, 4)
                           if n_picks else None}
    depth = Counter(r[0] for r in q(
        "SELECT COUNT(*) FROM league_index WHERE kept=1 GROUP BY lineage_id"))
    rep["lineage_depth_seasons"] = {str(k): v for k, v in sorted(depth.items())}
    flags = Counter()
    for (fj,) in q("SELECT flags_json FROM trades"):
        flags.update(json.loads(fj or "[]"))
    rep["trade_flags"] = dict(sorted(flags.items()))
    rep["trades_with_any_flag"] = q("SELECT COUNT(*) FROM trades WHERE flags_json != '[]'")[0][0]
    nulls = Counter()
    for (sj,) in q("SELECT summary_json FROM runs WHERE summary_json IS NOT NULL"):
        nulls.update((json.loads(sj) or {}).get("null_as_none") or {})
    rep["null_answers_accepted_as_none_by_endpoint"] = dict(sorted(nulls.items()))
    rep["transactions_by_type_status"] = {f"{r[0]}/{r[1]}": r[2] for r in q(
        "SELECT type, status, COUNT(*) FROM transactions GROUP BY type, status ORDER BY 1, 2")}
    rep["transaction_types_seen"] = sorted({r[0] for r in q("SELECT DISTINCT type FROM transactions")
                                            if r[0] is not None})
    causes = defaultdict(lambda: defaultdict(int))
    for r in q("SELECT l.season, c.kind, SUM(1-c.matched), SUM(c.n_no_add_event),"
               " SUM(c.n_no_drop_event), SUM(c.n_wrong_roster), SUM(c.n_other), COUNT(*)"
               " FROM reconstruction_checks c JOIN leagues l ON l.league_id=c.league_id"
               " GROUP BY l.season, c.kind"):
        causes[f"{r[0]}/{r[1]}"].update({"roster_weeks": r[7], "mismatched": r[2],
                                         "players_no_add_event": r[3],
                                         "players_no_drop_event": r[4],
                                         "players_wrong_roster": r[5], "players_other": r[6]})
    rep["reconstruction_mismatch_causes_by_season"] = {k: dict(v) for k, v in sorted(causes.items())}
    rep["draft_pick_timing"] = ("every pick of a completed draft is timed at the draft's end "
                                "(Sleeper pick objects carry no timestamp)")
    sc = q("SELECT status, matched, kinds_json FROM standings_checks")
    kinds = Counter()
    for r in sc:
        for k, n in json.loads(r["kinds_json"]).items():
            kinds[k] += n
    rep["standings_vs_reported"] = {
        "league_seasons": len(sc), "agree": sum(r["matched"] for r in sc),
        "share_agree": round(sum(r["matched"] for r in sc) / len(sc), 4) if sc else None,
        "by_status": {st: {"n": sum(1 for r in sc if r["status"] == st),
                           "agree": sum(r["matched"] for r in sc if r["status"] == st)}
                      for st in sorted({r["status"] for r in sc if r["status"]})},
        "disagreement_kinds_rosters": dict(sorted(kinds.items()))}
    rep["standings_rank_rule"] = "combined win pct, then points for, then roster id"
    rep["unplayed_weeks"] = {
        "roster_weeks": q("SELECT COUNT(*) FROM matchups WHERE played=0")[0][0],
        "without_pairing": q("SELECT COUNT(*) FROM matchups WHERE played=0 AND paired=0")[0][0]}
    rep["played_vs_points_disagree"] = {
        "zero_point_roster_weeks": q(
            "SELECT COUNT(*) FROM roster_weeks WHERE has_points=0")[0][0],
        "scored_but_not_complete": q(
            "SELECT COUNT(*) FROM roster_weeks WHERE played=0 AND has_points=1")[0][0]}
    rep["matchup_phase_counts"] = {r[0]: r[1] for r in q(
        "SELECT phase, COUNT(*) FROM matchups GROUP BY phase ORDER BY 1")}
    last = q("SELECT leak_scan_json FROM runs WHERE leak_scan_json IS NOT NULL AND command IN"
             " ('pull','run') ORDER BY run_id DESC LIMIT 1")
    rep["last_pull_leak_scan_ok"] = (json.loads(last[0][0]).get("ok") if last else None)
    return rep


def format_report(rep: dict, leak: dict) -> str:
    lines = ["Sleeper trade universe -- report (aggregates only)", ""]
    for k, v in rep.items():
        lines.append(f"{k}: {json.dumps(v, sort_keys=False)}")
    lines.append("")
    lines.append(f"leak_scan: {'PASS' if leak['ok'] else 'FAIL'} "
                 f"({leak['files_scanned']} files, {leak['bytes_scanned']} bytes; "
                 f"field hits {len(leak['field_hits'])} files, id hits {sum(leak['id_hits'].values())}, "
                 f"raw-id hits {sum(leak['raw_id_hits'].values())}, "
                 f"name hits {sum(leak['name_hits'].values())}; "
                 f"excluded {', '.join(leak['excluded'])})")
    for kind in ("field_hits", "id_hits", "raw_id_hits", "name_hits"):
        for f, n in leak[kind].items():
            lines.append(f"  {kind}: {f}: {n}")
    return "\n".join(lines)
