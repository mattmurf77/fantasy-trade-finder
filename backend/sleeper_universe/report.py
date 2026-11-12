"""Pilot report (research-plan §8.2), aggregates only, and the leak scan.

Leak scan method. Every file under the data folder is read, except exactly two
operator inputs at its top level, ``seeds.txt`` and ``hmac.key`` (the key is
refused there anyway). gzip data is recognised by its magic bytes whatever the
file name (so ``.tmp`` files are read too); the SQLite file is read as raw
bytes (which covers column names, the schema and free pages; the store also
runs with ``secure_delete`` so deleted rows are zeroed) and cell by cell
(text, integer and real cells; JSON cells parsed). It fails on:

a. a dropped field NAME (``identity.NAME_KEYS``: username, display_name,
   team_name, name, avatar, metadata, ``p_nick_*``, ...) as a JSON key in any
   file or as a column of any table;
b. a raw Sleeper user id. Every digit run is examined: a run of 12-20 digits
   whole, and every 15-20 digit window inside any run of 15 or more (so an id
   glued to neighbouring digits in a SQLite record is still found). Each
   candidate is HMAC'd and looked up in ``user_keys`` (every key the crawler
   ever produced), so raw ids are found without storing them; during a run
   the raw ids seen are also held in memory and matched directly, which also
   covers users the crawler never hashed;
c. during a run only: a NAME VALUE seen in a name field (held in memory,
   never written). All decoded text of every file (raw files, the SQLite
   bytes and cells, any text file) is split into words (``\\w+``); a name hits
   when its word sequence appears anywhere, so a name inside a longer string
   is found when it sits on word boundaries, and a name whose first word has
   6+ characters is found glued inside a longer word. Names that are a single word of
   1-2 characters, or a single all-digit word, or in the store's own
   vocabulary, are not value-checked (they would hit everywhere).

d. any number cell of 1e15 or more (no stored number is that large; an id
   stored as a number is caught even after a REAL lost its low digits).

Not detectable by value, by design: an id in another encoding (hex, base64);
an id of a user the crawler never saw; a name glued to other text inside a
word, when the name's first word is under 6 characters.

What ``report`` cannot check, stated in its output: name values (never
stored) and raw ids of users the crawler never hashed (only a run's memory
has them). Output never contains an id or a name: only file names and counts.
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

DIGITS_RE = re.compile(r"[0-9]{12,}")
WORD_RE = re.compile(r"\w+")
REPORT_CANNOT_CHECK = ("name values (never stored; only a run's own scan checks them)",
                       "raw ids of users the crawler never hashed (only a run's memory has them)")
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


def id_candidates(text: str) -> set:
    """Digit runs of 12-20 whole, plus every 15-20 digit window inside a run
    of 15 or more digits."""
    out = set()
    for m in DIGITS_RE.finditer(text):
        run = m.group()
        n = len(run)
        if n <= 20:
            out.add(run)
        if n >= 15:
            for width in range(15, min(20, n) + 1):
                for i in range(n - width + 1):
                    out.add(run[i:i + width])
    return out


GLUE_MIN = 6
_HEXKEY_RE = re.compile(r"^[0-9a-f]{32}$")


class _NameIndex:
    """Word sequences of the names worth checking, by first word; plus, for
    first words of 6+ characters, containment inside a longer word (a name
    glued to other text, 'junksecretuser1'), cached per distinct word."""

    def __init__(self, names):
        self.by_first = defaultdict(set)
        for n in names or ():
            if not isinstance(n, str) or n in VOCAB:
                continue
            words = tuple(WORD_RE.findall(n))
            if not words or (len(words) == 1 and (len(words[0]) < 3 or words[0].isdigit())):
                continue
            self.by_first[words[0]].add(words)
        self.long_first = [w for w in self.by_first if len(w) >= GLUE_MIN]
        self.cache: dict = {}

    def __len__(self):
        return sum(len(v) for v in self.by_first.values())

    def _glued(self, word):
        if word not in self.cache:
            if word.isdigit() or _HEXKEY_RE.match(word) or len(word) <= GLUE_MIN:
                self.cache[word] = ()
            else:
                self.cache[word] = tuple(f for f in self.long_first if f in word and f != word)
        return self.cache[word]

    def hits(self, text: str) -> int:
        if not self.by_first:
            return 0
        words = WORD_RE.findall(text)
        found = set()
        for i, w in enumerate(words):
            for first in (w, *self._glued(w)):
                for seq in self.by_first.get(first, ()):
                    if tuple(words[i + 1:i + len(seq)]) == seq[1:]:
                        found.add(seq)
        return len(found)


def _decode(blob: bytes) -> bytes:
    if blob[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(blob)
        except (OSError, EOFError):
            return blob
    return blob


def leak_scan(data_dir: Path, ring, *, names=None, raw_ids=None, report_mode=False) -> dict:
    data_dir = Path(data_dir)
    db = data_dir / DB_NAME
    known = set()
    if db.exists():
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        known = {r[0] for r in c.execute("SELECT user_key FROM user_keys")}
        c.close()
    idx = _NameIndex(names)
    raw_ids = {str(i) for i in (raw_ids or ())}
    excluded = {data_dir / SEED_FILE, data_dir / KEY_FILE}
    res = {"ok": True, "files_scanned": 0, "bytes_scanned": 0, "field_hits": {},
           "id_hits": {}, "raw_id_hits": {}, "name_hits": {},
           "excluded": sorted(str(p.relative_to(data_dir)) for p in excluded),
           "name_values_checked": len(idx), "numeric_hits": {},
           "raw_ids_checked": len(raw_ids),
           "not_checked": list(REPORT_CANNOT_CHECK) if report_mode else []}
    checked: dict = {}

    def bump(kind, label, n):
        if n:
            res[kind][label] = res[kind].get(label, 0) + n

    def ids_in(label, text):
        hit_key = hit_raw = 0
        for cand in id_candidates(text):
            if cand not in checked:
                checked[cand] = ring.user_key(cand) in known
            hit_key += checked[cand]
            hit_raw += cand in raw_ids
        bump("id_hits", label, hit_key)
        bump("raw_id_hits", label, hit_raw)

    for path in sorted(p for p in data_dir.rglob("*") if p.is_file()):
        if path in excluded:
            continue
        rel = str(path.relative_to(data_dir))
        res["files_scanned"] += 1
        keys: set = set()
        if path.name == DB_NAME:
            with open(path, "rb") as f:
                tail = b""
                while True:
                    chunk = f.read(32 << 20)
                    if not chunk:
                        break
                    res["bytes_scanned"] += len(chunk)
                    text = (tail + chunk).decode("utf-8", "replace")
                    ids_in(rel, text)
                    bump("name_hits", rel, idx.hits(text))
                    tail = chunk[-256:]
            c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'"
                                  " AND name NOT LIKE 'sqlite_%'"):
                keys.update(r[1] for r in c.execute(f"PRAGMA table_info('{t}')"))
                label = f"{rel}:{t}"
                for row in c.execute(f"SELECT * FROM '{t}'"):
                    for v in row:
                        if isinstance(v, bool) or v is None:
                            continue
                        if isinstance(v, (int, float)):
                            # Nothing the store keeps as a number reaches 1e15
                            # (timestamps are ~1.7e12; ids are TEXT). A number
                            # that large is an id stored as a number, whose
                            # low digits a REAL may already have lost.
                            if abs(v) >= 1e15:
                                bump("numeric_hits", label, 1)
                            if isinstance(v, int) or v.is_integer():
                                ids_in(label, str(int(v)))
                        else:
                            text = v if isinstance(v, str) else bytes(v).decode("utf-8", "replace")
                            ids_in(label, text)
                            bump("name_hits", label, idx.hits(text))
                            if text[:1] in "[{":
                                try:
                                    _walk(json.loads(text), keys, [])
                                except ValueError:
                                    pass
            c.close()
        else:
            blob = _decode(path.read_bytes())
            res["bytes_scanned"] += len(blob)
            text = blob.decode("utf-8", "replace")
            ids_in(rel, text)
            bump("name_hits", rel, idx.hits(text))
            try:
                _walk(json.loads(text), keys, [])
            except ValueError:
                pass
        hits = _field_hit(keys)
        if hits:
            res["field_hits"][rel] = hits
    res["ok"] = not (res["field_hits"] or res["id_hits"] or res["raw_id_hits"]
                     or res["name_hits"] or res["numeric_hits"])
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
    inv, prev_lid, top = 0, None, 0
    for r in q("SELECT league_id, leg FROM transactions WHERE status='complete' AND leg IS NOT NULL"
               " ORDER BY league_id, COALESCE(status_updated, created), transaction_id"):
        if r["league_id"] != prev_lid:
            prev_lid, top = r["league_id"], 0
        if r["leg"] < top:
            inv += 1
        top = max(top, r["leg"])
    rep["leg_time_inversions"] = inv
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
    sc = q("SELECT status, matched, record_matched, points_matched, kinds_json FROM standings_checks")
    kinds = Counter()
    for r in sc:
        for k, n in json.loads(r["kinds_json"]).items():
            kinds[k] += n
    rep["standings_vs_reported"] = {
        "league_seasons": len(sc), "agree": sum(r["matched"] for r in sc),
        "records_agree": sum(r["record_matched"] for r in sc),
        "points_agree": sum(r["points_matched"] for r in sc),
        "share_records_agree": round(sum(r["record_matched"] for r in sc) / len(sc), 4) if sc else None,
        "share_points_agree": round(sum(r["points_matched"] for r in sc) / len(sc), 4) if sc else None,
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
