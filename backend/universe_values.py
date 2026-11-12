"""Dated market values for the Sleeper trade-universe research store.

RESEARCH TOOL, NOT APP CODE. Nothing in the Flask app, no route and no flag
imports this module. It builds and reads a local SQLite file under
`data/sleeper-universe/` (git-ignored) that says what the market thought each
player and draft pick was worth on a given day, so a 2024 trade can be priced
with a 2024 board (research plan `docs/plans/sleeper-trade-universe/`, §5.6,
§5.7, decision 5). Design note: `docs/plans/sleeper-trade-universe/values-history.md`.

Tables (one file, two sources share them; `source` is "dp" or "ktc"):

  value_boards  one row per (source, format, board_date): when the board was
                published, which commit it came from (DP), its header (DP).
  values        one row per (board, asset): Sleeper player id or pick key,
                value, position and age where the source has them.
  unmapped      source rows that did not map to a Sleeper id, keyed by the
                SOURCE's id only (DP `fp_id`, KTC `playerID`), never a guess.

Pick keys (shared by both sources and by the crawler's pick identity):

  pick:<season>:<round>:<slot two digits>   "2026 Pick 1.01"  -> pick:2026:1:01
  pick:<season>:<round>:early|mid|late      "2027 Early 1st"  -> pick:2027:1:early
  pick:<season>:<round>                     "2028 2nd"        -> pick:2028:2

The crawler knows a traded pick by (season, round, original roster) and, once
that draft has happened, its slot. `pick_value_on` takes the slot when known,
or an early/mid/late bucket the caller derives from the original team's
standing at the trade's date (plan §5.7), and falls back slot -> bucket ->
round, reporting which it used.

DynastyProcess input: a LOCAL CLONE of github.com/dynastyprocess/data. The
history of `files/values-players.csv` gives one board per commit date (the
last commit of each UTC day). Picks come from `files/values.csv` (its
`pos == "PICK"` rows) at the same commit, else `files/values-picks.csv`.
Headers are checked against the columns this module knows; an unknown layout
fails the whole build and lists every offending commit. Nothing is written
until the whole history has parsed.

Standard library only. No network here: reading a blobless clone may make
git fetch file revisions lazily, which is git's doing, run by the operator.
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import json
import os
import re
import sqlite3
import subprocess
from dataclasses import dataclass, field

from .data_loader import DP_TO_SLEEPER_NAME, normalise_name
from .dp_values_history import strip_generational_suffix

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DP_REPO_URL = "https://github.com/dynastyprocess/data.git"
PLAYERS_PATH = "files/values-players.csv"
COMBINED_PATH = "files/values.csv"
PICKS_PATH = "files/values-picks.csv"
PLAYERIDS_PATH = "files/db_playerids.csv"

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DIR = os.path.join(_REPO_ROOT, "data", "sleeper-universe")
DEFAULT_DB = os.path.join(DEFAULT_DIR, "values.sqlite")
DEFAULT_START = _dt.date(2024, 1, 1)

FORMATS = ("1qb", "sf")
_FORMAT_ALIASES = {"1qb": "1qb", "sf": "sf", "2qb": "sf", "superflex": "sf"}
DP_VALUE_COLUMN = {"1qb": "value_1qb", "sf": "value_2qb"}

# The values-players.csv layout as of 2026 (docs/integrations/dynastyprocess.md).
# A header is accepted when it holds every REQUIRED column and nothing outside
# KNOWN; anything else is an unknown layout and fails the build.
DP_REQUIRED_COLUMNS = frozenset({"player", "pos", "value_1qb", "value_2qb"})
DP_PICK_REQUIRED_COLUMNS = frozenset({"player", "value_1qb", "value_2qb"})
DP_KNOWN_COLUMNS = DP_REQUIRED_COLUMNS | frozenset({
    "team", "age", "draft_year", "ecr_1qb", "ecr_2qb", "ecr_pos",
    "scrape_date", "fp_id"})

_ORDINAL = {1: "st", 2: "nd", 3: "rd"}
_PICK_SLOT_RE = re.compile(r"^(\d{4}) Pick (\d{1,2})\.(\d{1,2})$")
_PICK_BUCKET_RE = re.compile(r"^(\d{4}) (Early|Mid|Late) (\d{1,2})(st|nd|rd|th)$", re.I)
_PICK_ROUND_RE = re.compile(r"^(\d{4}) (\d{1,2})(st|nd|rd|th)$", re.I)
_PICK_KEY_RE = re.compile(r"^pick:(\d{4}):(\d{1,2})(?::(\d{2}|early|mid|late))?$")
BUCKETS = ("early", "mid", "late")


class LayoutError(RuntimeError):
    """The source history holds a layout or label this module does not know."""


# ---------------------------------------------------------------------------
# Pick keys
# ---------------------------------------------------------------------------

def _ordinal_ok(rnd: int, suffix: str) -> bool:
    return _ORDINAL.get(rnd if rnd < 20 else rnd % 10, "th") == suffix.lower()


def pick_key(season: int, rnd: int, *, slot: int | None = None,
             bucket: str | None = None) -> str:
    if slot is not None:
        return "pick:%d:%d:%02d" % (int(season), int(rnd), int(slot))
    if bucket is not None:
        b = bucket.lower()
        if b not in BUCKETS:
            raise ValueError("bucket must be early, mid or late, not %r" % bucket)
        return "pick:%d:%d:%s" % (int(season), int(rnd), b)
    return "pick:%d:%d" % (int(season), int(rnd))


def parse_pick_label(label: str) -> str:
    """A source pick label -> pick key. Raises ValueError on anything else.

    Accepts the DynastyProcess and KeepTradeCut spellings: "2026 Pick 1.01",
    "2027 Early 1st", "2028 2nd", and an existing key ("pick:2027:1:early")."""
    s = " ".join((label or "").split())
    m = _PICK_KEY_RE.match(s)
    if m:
        return s
    m = _PICK_SLOT_RE.match(s)
    if m:
        return pick_key(int(m.group(1)), int(m.group(2)), slot=int(m.group(3)))
    m = _PICK_BUCKET_RE.match(s)
    if m and _ordinal_ok(int(m.group(3)), m.group(4)):
        return pick_key(int(m.group(1)), int(m.group(3)), bucket=m.group(2))
    m = _PICK_ROUND_RE.match(s)
    if m and _ordinal_ok(int(m.group(2)), m.group(3)):
        return pick_key(int(m.group(1)), int(m.group(2)))
    raise ValueError("unknown pick label %r" % label)


def slot_bucket(slot: int, teams: int = 12) -> str:
    """Early/mid/late third of a round: 12 teams -> 1-4 / 5-8 / 9-12."""
    if not 1 <= int(slot) <= int(teams):
        raise ValueError("slot %r outside 1..%r" % (slot, teams))
    third = teams / 3.0
    if slot <= third:
        return "early"
    if slot <= 2 * third:
        return "mid"
    return "late"


# ---------------------------------------------------------------------------
# Crosswalk (DynastyProcess db_playerids.csv)
# ---------------------------------------------------------------------------

@dataclass
class DPCrosswalk:
    by_fp: dict[str, tuple[str, str]]          # fantasypros_id -> (sleeper_id, pos)
    by_ktc: dict[str, tuple[str, str]]         # ktc_id -> (sleeper_id, pos)
    by_mfl: dict[str, tuple[str, str]]         # mfl_id -> (sleeper_id, pos)
    by_name_pos: dict[tuple[str, str], str]    # the app's name tier (espn_service)
    stripped: dict[tuple[str, str], str]       # same, generational suffix stripped
    columns: list[str]


def crosswalk_from_text(text: str) -> DPCrosswalk:
    """Parse db_playerids.csv. The name tier is built by the app's own parser
    (`espn_service._parse_crosswalk_rows`) so it is byte-for-byte the join the
    live pipeline and `dp_values_history` use."""
    from .espn_service import _parse_crosswalk_rows
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    rows = list(reader)
    xw = _parse_crosswalk_rows(rows)
    by: dict[str, dict[str, tuple[str, str]]] = {"fp": {}, "ktc": {}, "mfl": {}}
    for row in rows:
        sid = (row.get("sleeper_id") or "").strip()
        pos = (row.get("position") or "").strip().upper()
        if sid in ("", "NA"):
            continue
        for key, col in (("fp", "fantasypros_id"), ("ktc", "ktc_id"), ("mfl", "mfl_id")):
            v = (row.get(col) or "").strip()
            if v not in ("", "NA"):
                by[key].setdefault(_clean_id(v), (sid, pos))
    stripped: dict[tuple[str, str], str] = {}
    for (nm, pos), sid in xw.by_name_pos.items():
        stripped.setdefault((strip_generational_suffix(nm), pos), sid)
    return DPCrosswalk(by_fp=by["fp"], by_ktc=by["ktc"], by_mfl=by["mfl"],
                       by_name_pos=xw.by_name_pos, stripped=stripped,
                       columns=list(reader.fieldnames or []))


def _clean_id(v) -> str:
    """'12345.0' and 12345 both -> '12345' (R writes some id columns as floats)."""
    s = str(v).strip()
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    return s


def resolve_by_name(name: str, pos: str, xw: DPCrosswalk) -> tuple[str | None, str | None]:
    """The dp_values_history tier 1 + tier 2 name join, position-strict."""
    raw = normalise_name(name or "")
    mapped = DP_TO_SLEEPER_NAME.get(raw, raw)
    sid = xw.by_name_pos.get((mapped, pos)) or xw.by_name_pos.get((raw, pos))
    if sid:
        return sid, "name"
    sid = xw.stripped.get((strip_generational_suffix(mapped), pos))
    if sid:
        return sid, "name_suffix"
    return None, None


def resolve_by_id(index: dict, ext_id, pos: str) -> str | None:
    hit = index.get(_clean_id(ext_id)) if ext_id not in (None, "", "NA") else None
    if hit and hit[1] == pos:
        return hit[0]
    return None


def resolve_dp_row(row: dict, xw: DPCrosswalk) -> tuple[str | None, str | None]:
    """(sleeper_id, tier): fp_id first (ids beat names, #127), then names."""
    pos = (row.get("pos") or "").strip().upper()
    sid = resolve_by_id(xw.by_fp, (row.get("fp_id") or "").strip(), pos)
    if sid:
        return sid, "fp_id"
    return resolve_by_name(row.get("player") or "", pos, xw)


# ---------------------------------------------------------------------------
# Boards and the SQLite store
# ---------------------------------------------------------------------------

@dataclass
class Board:
    source: str
    format: str
    board_date: str                    # ISO date
    published_at: str                  # ISO 'YYYY-MM-DDTHH:MM:SSZ'
    commit_sha: str | None = None
    scrape_date: str | None = None
    header: str | None = None
    picks_file: str | None = None
    player_rows: int = 0
    collisions: int = 0
    # asset_key -> (value, asset_type, position, age, source_id, match_tier)
    values: dict = field(default_factory=dict)
    # source_key -> (position, value)
    unmapped: dict = field(default_factory=dict)

    def add(self, key, value, asset_type, pos=None, age=None, source_id=None, tier=None):
        if key in self.values:
            self.collisions += 1        # first row wins (DP rows are value-ordered)
            return
        self.values[key] = (value, asset_type, pos, age, source_id, tier)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS value_boards (
    board_id     INTEGER PRIMARY KEY,
    source       TEXT NOT NULL,
    format       TEXT NOT NULL,
    board_date   TEXT NOT NULL,
    published_at TEXT NOT NULL,
    commit_sha   TEXT,
    scrape_date  TEXT,
    header       TEXT,
    picks_file   TEXT,
    player_rows  INTEGER NOT NULL DEFAULT 0,
    mapped_rows  INTEGER NOT NULL DEFAULT 0,
    pick_rows    INTEGER NOT NULL DEFAULT 0,
    collisions   INTEGER NOT NULL DEFAULT 0,
    UNIQUE (source, format, board_date)
);
CREATE TABLE IF NOT EXISTS "values" (
    board_id   INTEGER NOT NULL REFERENCES value_boards(board_id),
    asset_key  TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    value      REAL NOT NULL,
    position   TEXT,
    age        REAL,
    source_id  TEXT,
    match_tier TEXT,
    PRIMARY KEY (board_id, asset_key)
);
CREATE TABLE IF NOT EXISTS unmapped (
    board_id   INTEGER NOT NULL REFERENCES value_boards(board_id),
    source_key TEXT NOT NULL,
    position   TEXT,
    value      REAL,
    PRIMARY KEY (board_id, source_key)
);
CREATE TABLE IF NOT EXISTS build_log (
    built_at TEXT NOT NULL,
    source   TEXT NOT NULL,
    detail   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_boards_lookup ON value_boards (source, format, board_date);
CREATE INDEX IF NOT EXISTS ix_values_asset ON "values" (asset_key, board_id);
"""


def connect(db_path: str = DEFAULT_DB) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    return conn


def write_boards(conn: sqlite3.Connection, boards: list[Board], *,
                 source: str, replace: str, detail: dict) -> None:
    """Write boards in one transaction. replace='source' drops every board of
    `source` first (a full rebuild); replace='dates' drops only the (format,
    date) pairs being written."""
    with conn:
        if replace == "source":
            doomed = [r[0] for r in conn.execute(
                "SELECT board_id FROM value_boards WHERE source=?", (source,))]
        else:
            doomed = []
            for b in boards:
                doomed += [r[0] for r in conn.execute(
                    "SELECT board_id FROM value_boards WHERE source=? AND format=? "
                    "AND board_date=?", (b.source, b.format, b.board_date))]
        for bid in doomed:
            conn.execute('DELETE FROM "values" WHERE board_id=?', (bid,))
            conn.execute("DELETE FROM unmapped WHERE board_id=?", (bid,))
            conn.execute("DELETE FROM value_boards WHERE board_id=?", (bid,))
        for b in boards:
            n_pick = sum(1 for v in b.values.values() if v[1] == "pick")
            cur = conn.execute(
                "INSERT INTO value_boards (source, format, board_date, published_at,"
                " commit_sha, scrape_date, header, picks_file, player_rows,"
                " mapped_rows, pick_rows, collisions) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (b.source, b.format, b.board_date, b.published_at, b.commit_sha,
                 b.scrape_date, b.header, b.picks_file, b.player_rows,
                 len(b.values) - n_pick, n_pick, b.collisions))
            bid = cur.lastrowid
            conn.executemany(
                'INSERT INTO "values" (board_id, asset_key, value, asset_type, position,'
                ' age, source_id, match_tier) VALUES (?,?,?,?,?,?,?,?)',
                [(bid, k) + v for k, v in b.values.items()])
            conn.executemany(
                "INSERT INTO unmapped (board_id, source_key, position, value) VALUES (?,?,?,?)",
                [(bid, k) + v for k, v in b.unmapped.items()])
        conn.execute("INSERT INTO build_log VALUES (?,?,?)",
                     (_utc_now(), source, json.dumps(detail, sort_keys=True)))


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_z(ts: _dt.datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=_dt.timezone.utc)
    return ts.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(v) -> float | None:
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return x if x == x else None        # NaN -> None


# ---------------------------------------------------------------------------
# DynastyProcess history from a local clone
# ---------------------------------------------------------------------------

class GitReader:
    """Reads file revisions from a local clone through one `git cat-file --batch`."""

    def __init__(self, repo: str):
        self.repo = repo
        self._proc = None

    def _git(self, *args) -> str:
        return subprocess.run(["git", "-C", self.repo, *args], check=True,
                              capture_output=True, text=True).stdout

    def head(self) -> str:
        return self._git("rev-parse", "HEAD").strip()

    def commits(self, path: str) -> list[tuple[str, _dt.datetime]]:
        """[(sha, committed_at UTC)] oldest first, commits touching `path`."""
        out = []
        for line in self._git("log", "--format=%H %cI", "--", path).splitlines():
            sha, iso = line.split(" ", 1)
            ts = _dt.datetime.fromisoformat(iso.strip()).astimezone(_dt.timezone.utc)
            out.append((sha, ts))
        out.reverse()
        return out

    def read(self, rev: str, path: str) -> str | None:
        if self._proc is None:
            self._proc = subprocess.Popen(
                ["git", "-C", self.repo, "cat-file", "--batch"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self._proc.stdin.write(("%s:%s\n" % (rev, path)).encode())
        self._proc.stdin.flush()
        head = self._proc.stdout.readline().decode().rstrip("\n")
        if head.endswith(" missing") or head.endswith(" ambiguous"):
            return None
        size = int(head.split()[2])
        data = self._proc.stdout.read(size)
        self._proc.stdout.read(1)          # trailing newline
        return data.decode("utf-8")

    def close(self):
        if self._proc is not None:
            self._proc.stdin.close()
            self._proc.wait()
            self._proc = None


def select_board_commits(commits, start: _dt.date, end: _dt.date | None = None):
    """Last commit of each UTC day; days from `start` to `end`, plus the last
    day before `start` so an early-January lookup has a board."""
    by_day: dict[_dt.date, tuple[str, _dt.datetime]] = {}
    for sha, ts in commits:                       # oldest first: later wins
        by_day[ts.date()] = (sha, ts)
    days = sorted(d for d in by_day if end is None or d <= end)
    before = [d for d in days if d < start]
    keep = ([before[-1]] if before else []) + [d for d in days if d >= start]
    return [(d,) + by_day[d] for d in keep]


def _check_header(fieldnames, required, known) -> str | None:
    cols = list(fieldnames or [])
    missing = sorted(required - set(cols))
    unknown = sorted(set(cols) - known)
    if missing or unknown:
        return "missing=%s unknown=%s" % (missing, unknown)
    return None


def _read_csv(text: str):
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    return reader.fieldnames, list(reader)


def build_dp_boards(reader: GitReader, xw: DPCrosswalk, *, start: _dt.date,
                    end: _dt.date | None = None) -> tuple[list[Board], dict]:
    """Parse the whole selected history into Boards. Raises LayoutError listing
    every unknown header or pick label; returns (boards, summary) otherwise."""
    problems: list[str] = []
    boards: list[Board] = []
    selected = select_board_commits(reader.commits(PLAYERS_PATH), start, end)
    for day, sha, ts in selected:
        text = reader.read(sha, PLAYERS_PATH)
        fields, rows = _read_csv(text or "")
        bad = _check_header(fields, DP_REQUIRED_COLUMNS, DP_KNOWN_COLUMNS)
        if bad:
            problems.append("%s %s %s: header %s %s" % (day, sha, PLAYERS_PATH, fields, bad))
            continue
        picks_file, pick_rows = None, []
        for path, only_pick_pos in ((COMBINED_PATH, True), (PICKS_PATH, False)):
            ptext = reader.read(sha, path)
            if ptext is None:
                continue
            pfields, prow = _read_csv(ptext)
            pbad = _check_header(pfields, DP_PICK_REQUIRED_COLUMNS, DP_KNOWN_COLUMNS)
            if pbad:
                problems.append("%s %s %s: header %s %s" % (day, sha, path, pfields, pbad))
                break
            picks_file = path.split("/")[-1]
            pick_rows = [r for r in prow
                         if not only_pick_pos or (r.get("pos") or "").strip().upper() == "PICK"]
            break
        scrape = max((r.get("scrape_date") or "" for r in rows), default="") or None
        for fmt in FORMATS:
            b = Board(source="dp", format=fmt, board_date=day.isoformat(),
                      published_at=_iso_z(ts), commit_sha=sha, scrape_date=scrape,
                      header=",".join(fields), picks_file=picks_file)
            col = DP_VALUE_COLUMN[fmt]
            for r in rows:
                if (r.get("pos") or "").strip().upper() == "PICK":
                    continue
                v = _num(r.get(col))
                if not v or v <= 0:
                    continue
                b.player_rows += 1
                pos = (r.get("pos") or "").strip().upper()
                fp = (r.get("fp_id") or "").strip()
                fp = _clean_id(fp) if fp not in ("", "NA") else ""
                sid, tier = resolve_dp_row(r, xw)
                if sid is None:
                    b.unmapped.setdefault(fp or "name:%s|%s" % (r.get("player"), pos), (pos, v))
                    continue
                b.add(sid, v, "player", pos, _num(r.get("age")), fp or None, tier)
            for r in pick_rows:
                v = _num(r.get(col))
                try:
                    key = parse_pick_label(r.get("player") or "")
                except ValueError:
                    problems.append("%s %s %s: pick label %r" % (day, sha, picks_file, r.get("player")))
                    continue
                if v and v > 0:
                    b.add(key, v, "pick")
            boards.append(b)
    if problems:
        raise LayoutError("DynastyProcess history has %d unknown layout(s)/label(s); "
                          "nothing written:\n  %s" % (len(problems), "\n  ".join(problems)))
    summary = {"commits_selected": len(selected),
               "first": selected[0][0].isoformat() if selected else None,
               "last": selected[-1][0].isoformat() if selected else None,
               "headers": sorted({b.header for b in boards})}
    return boards, summary


def build_dp(repo: str, db_path: str = DEFAULT_DB, *, start: _dt.date = DEFAULT_START,
             end: _dt.date | None = None, crosswalk_text: str | None = None,
             crosswalk_rev: str = "HEAD") -> dict:
    """Full rebuild of source 'dp' in `db_path` from a local clone."""
    reader = GitReader(repo)
    try:
        head = reader.head()
        if crosswalk_text is None:
            crosswalk_text = reader.read(crosswalk_rev, PLAYERIDS_PATH)
            if crosswalk_text is None:
                raise LayoutError("no %s at %s in %s" % (PLAYERIDS_PATH, crosswalk_rev, repo))
        xw = crosswalk_from_text(crosswalk_text)
        boards, summary = build_dp_boards(reader, xw, start=start, end=end)
    finally:
        reader.close()
    summary.update({"repo_head": head, "crosswalk_rev": crosswalk_rev,
                    "crosswalk_fp_ids": len(xw.by_fp), "boards": len(boards),
                    "start": start.isoformat(), "end": end.isoformat() if end else None})
    conn = connect(db_path)
    try:
        write_boards(conn, boards, source="dp", replace="source", detail=summary)
    finally:
        conn.close()
    return summary


def inspect_dp(repo: str, *, start: _dt.date = DEFAULT_START) -> list[dict]:
    """Distinct headers per file over the selected history (no writes)."""
    reader = GitReader(repo)
    try:
        out: dict[tuple[str, str], dict] = {}
        for day, sha, _ts in select_board_commits(reader.commits(PLAYERS_PATH), start):
            for path in (PLAYERS_PATH, COMBINED_PATH, PICKS_PATH):
                text = reader.read(sha, path)
                header = "(absent)" if text is None else ",".join(_read_csv(text)[0] or [])
                e = out.setdefault((path, header), {"file": path, "header": header,
                                                    "boards": 0, "first": day.isoformat(),
                                                    "first_commit": sha})
                e["boards"] += 1
                e["last"], e["last_commit"] = day.isoformat(), sha
        return sorted(out.values(), key=lambda e: (e["file"], e["first"]))
    finally:
        reader.close()


# ---------------------------------------------------------------------------
# Generic dated-values file loader (any source)
# ---------------------------------------------------------------------------
# date,format,asset_type,asset_id,value[,id_type,name,position,age]
#   asset_type player: id_type sleeper (default) | ktc | mfl; name+position
#                      are the fallback join.
#   asset_type pick:   asset_id is a pick label or key ("2027 Early 1st").

LOADER_REQUIRED = frozenset({"date", "format", "asset_type", "asset_id", "value"})
LOADER_KNOWN = LOADER_REQUIRED | frozenset({"id_type", "name", "position", "age"})


def load_dated_csv(path: str, db_path: str = DEFAULT_DB, *, source: str,
                   xw: DPCrosswalk | None = None) -> dict:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        bad = _check_header(reader.fieldnames, LOADER_REQUIRED, LOADER_KNOWN)
        if bad:
            raise LayoutError("%s: header %s %s" % (path, reader.fieldnames, bad))
        rows = list(reader)
    boards: dict[tuple[str, str], Board] = {}
    problems = []
    for i, r in enumerate(rows, start=2):
        fmt = _FORMAT_ALIASES.get((r["format"] or "").strip().lower())
        try:
            day = _dt.date.fromisoformat(r["date"].strip())
        except ValueError:
            day = None
        v = _num(r["value"])
        atype = (r["asset_type"] or "").strip().lower()
        if fmt is None or day is None or v is None or atype not in ("player", "pick"):
            problems.append("line %d: %r" % (i, r))
            continue
        b = boards.setdefault((fmt, day.isoformat()), Board(
            source=source, format=fmt, board_date=day.isoformat(),
            published_at=day.isoformat() + "T23:59:59Z"))
        aid = (r["asset_id"] or "").strip()
        if atype == "pick":
            try:
                b.add(parse_pick_label(aid), v, "pick")
            except ValueError:
                problems.append("line %d: pick label %r" % (i, aid))
            continue
        b.player_rows += 1
        pos = (r.get("position") or "").strip().upper()
        id_type = (r.get("id_type") or "sleeper").strip().lower()
        sid, tier = None, None
        if id_type == "sleeper":
            sid, tier = aid, "sleeper_id"
        elif id_type in ("ktc", "mfl") and xw is not None:
            hit = (xw.by_ktc if id_type == "ktc" else xw.by_mfl).get(_clean_id(aid))
            if hit and (not pos or hit[1] == pos):
                sid, tier = hit[0], id_type + "_id"
        elif id_type not in ("ktc", "mfl"):
            problems.append("line %d: id_type %r" % (i, id_type))
            continue
        if sid is None and xw is not None and r.get("name") and pos:
            sid, tier = resolve_by_name(r["name"], pos, xw)
        if sid is None:
            b.unmapped.setdefault("%s:%s" % (id_type, aid), (pos or None, v))
            continue
        b.add(sid, v, "player", pos or None, _num(r.get("age")), aid, tier)
    if problems:
        raise LayoutError("%s: %d bad row(s); nothing written:\n  %s"
                          % (path, len(problems), "\n  ".join(problems[:50])))
    out = sorted(boards.values(), key=lambda b: (b.format, b.board_date))
    conn = connect(db_path)
    try:
        write_boards(conn, out, source=source, replace="dates",
                     detail={"file": os.path.basename(path), "boards": len(out)})
    finally:
        conn.close()
    return {"boards": len(out), "rows": len(rows)}


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Lookup:
    source: str
    format: str
    asset_key: str
    value: float | None          # None: no board at or before `when` carries it
    board_date: str | None       # the board the value came from
    age_days: int | None         # when.date() - board_date
    latest_board_date: str | None  # newest board of the source at or before `when`
    resolution: str | None = None  # picks: slot | bucket | round

    @property
    def found(self) -> bool:
        return self.value is not None


def _when(when) -> tuple[_dt.date, str, str]:
    """(day, column, bound). A date matches boards dated that day or earlier;
    a datetime matches boards PUBLISHED at or before that instant."""
    if isinstance(when, str):
        when = (_dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
                if "T" in when else _dt.date.fromisoformat(when))
    if isinstance(when, _dt.datetime):
        return when.date() if when.tzinfo is None else \
            when.astimezone(_dt.timezone.utc).date(), "published_at", _iso_z(when)
    return when, "board_date", when.isoformat()


def normalise_format(fmt: str) -> str:
    f = _FORMAT_ALIASES.get((fmt or "").strip().lower())
    if f is None:
        raise ValueError("format must be one of %s, not %r" % (sorted(_FORMAT_ALIASES), fmt))
    return f


class ValueStore:
    def __init__(self, db_path: str = DEFAULT_DB):
        if not os.path.exists(db_path):
            raise FileNotFoundError(db_path)
        self.conn = sqlite3.connect(db_path)

    def close(self):
        self.conn.close()

    def value_on(self, when, asset_key: str, fmt: str, *, source: str = "dp") -> Lookup:
        """Latest board at or before `when` that carries `asset_key`, with the
        board's age in days. `latest_board_date` is the newest board of the
        source at or before `when`; if it is newer than `board_date`, the asset
        had dropped off the newer boards."""
        fmt = normalise_format(fmt)
        day, col, bound = _when(when)
        latest = self.conn.execute(
            "SELECT MAX(board_date) FROM value_boards WHERE source=? AND format=? "
            "AND %s<=?" % col, (source, fmt, bound)).fetchone()[0]
        row = self.conn.execute(
            'SELECT b.board_date, v.value FROM "values" v JOIN value_boards b '
            "ON b.board_id=v.board_id WHERE v.asset_key=? AND b.source=? AND "
            "b.format=? AND b.%s<=? ORDER BY b.board_date DESC LIMIT 1" % col,
            (asset_key, source, fmt, bound)).fetchone()
        if row is None:
            return Lookup(source, fmt, asset_key, None, None, None, latest)
        age = (day - _dt.date.fromisoformat(row[0])).days
        return Lookup(source, fmt, asset_key, row[1], row[0], age, latest)

    def pick_value_on(self, when, season: int, rnd: int, fmt: str, *,
                      slot: int | None = None, bucket: str | None = None,
                      teams: int = 12, source: str = "dp") -> Lookup:
        """A traded pick's value: slot (12-team boards only), else early/mid/
        late (given, or derived from the slot), else the round."""
        tries = []
        if slot is not None:
            if teams == 12:
                tries.append(("slot", pick_key(season, rnd, slot=slot)))
            bucket = bucket or slot_bucket(slot, teams)
        if bucket is not None:
            tries.append(("bucket", pick_key(season, rnd, bucket=bucket)))
        tries.append(("round", pick_key(season, rnd)))
        last = None
        for res, key in tries:
            last = self.value_on(when, key, fmt, source=source)
            if last.found:
                return Lookup(**{**last.__dict__, "resolution": res})
        return last


def value_on(when, asset_key: str, fmt: str, *, source: str = "dp",
             db_path: str = DEFAULT_DB) -> Lookup:
    store = ValueStore(db_path)
    try:
        return store.value_on(when, asset_key, fmt, source=source)
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Coverage report
# ---------------------------------------------------------------------------

def read_lookups(path: str) -> list[tuple[str, str]]:
    """CSV with header `asset_key,date` (date ISO, or an ISO datetime)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not {"asset_key", "date"} <= set(reader.fieldnames or []):
            raise LayoutError("%s: need columns asset_key,date; got %s" % (path, reader.fieldnames))
        return [(r["asset_key"].strip(), r["date"].strip()) for r in reader]


def coverage_report(db_path: str = DEFAULT_DB, *, lookups=None,
                    max_age: int = 14) -> dict:
    conn = sqlite3.connect(db_path)
    rep: dict = {"sources": {}, "max_age_days": max_age}
    try:
        pairs = conn.execute("SELECT DISTINCT source, format FROM value_boards "
                             "ORDER BY source, format").fetchall()
        for source, fmt in pairs:
            dates = [r[0] for r in conn.execute(
                "SELECT board_date FROM value_boards WHERE source=? AND format=? "
                "ORDER BY board_date", (source, fmt))]
            per_month: dict[str, int] = {}
            for d in dates:
                per_month[d[:7]] = per_month.get(d[:7], 0) + 1
            gap = (0, None, None)
            for a, b in zip(dates, dates[1:]):
                g = (_dt.date.fromisoformat(b) - _dt.date.fromisoformat(a)).days
                if g > gap[0]:
                    gap = (g, a, b)
            mapped, unmapped, worst = 0, 0, None
            for bdate, m, u in conn.execute(
                    "SELECT b.board_date, b.mapped_rows, "
                    "(SELECT COUNT(*) FROM unmapped x WHERE x.board_id=b.board_id) "
                    "FROM value_boards b WHERE source=? AND format=?", (source, fmt)):
                mapped += m
                unmapped += u
                if m + u:
                    share = m / (m + u)
                    if worst is None or share < worst[0]:
                        worst = (round(share, 4), bdate)
            top_unmapped = [r[0] for r in conn.execute(
                "SELECT x.source_key FROM unmapped x JOIN value_boards b ON "
                "b.board_id=x.board_id WHERE b.source=? AND b.format=? GROUP BY "
                "x.source_key ORDER BY MAX(x.value) DESC LIMIT 25", (source, fmt))]
            rep["sources"]["%s/%s" % (source, fmt)] = {
                "boards": len(dates), "first": dates[0] if dates else None,
                "last": dates[-1] if dates else None, "boards_per_month": per_month,
                "longest_gap_days": gap[0], "longest_gap": [gap[1], gap[2]],
                "player_rows_mapped": mapped, "player_rows_unmapped": unmapped,
                "mapped_share": round(mapped / (mapped + unmapped), 4) if mapped + unmapped else None,
                "worst_board_mapped_share": worst,
                "distinct_unmapped": conn.execute(
                    "SELECT COUNT(DISTINCT x.source_key) FROM unmapped x JOIN value_boards b "
                    "ON b.board_id=x.board_id WHERE b.source=? AND b.format=?",
                    (source, fmt)).fetchone()[0],
                "top_unmapped_source_keys": top_unmapped,
            }
        if lookups is not None:
            sources = sorted({s for s, _ in pairs})
            fmts = sorted({f for _, f in pairs})
            conn.close()
            conn = None
            store = ValueStore(db_path)
            try:
                rep["lookups"] = _lookup_coverage(store, lookups, sources, fmts, max_age)
            finally:
                store.close()
    finally:
        if conn is not None:
            conn.close()
    return rep


def _lookup_coverage(store, lookups, sources, fmts, max_age) -> dict:
    out = {"n": len(lookups)}
    for fmt in fmts:
        hit_counts = {s: 0 for s in sources}
        combos: dict[str, int] = {}
        for key, when in lookups:
            have = []
            for s in sources:
                lk = store.value_on(when, key, fmt, source=s)
                if lk.found and lk.age_days <= max_age:
                    hit_counts[s] += 1
                    have.append(s)
            label = "+".join(have) or "none"
            combos[label] = combos.get(label, 0) + 1
        n = len(lookups) or 1
        out[fmt] = {"within_max_age": {s: c for s, c in hit_counts.items()},
                    "share_within_max_age": {s: round(c / n, 4) for s, c in hit_counts.items()},
                    "by_sources_present": combos}
    return out


def format_report(rep: dict) -> str:
    lines = []
    for name, s in rep["sources"].items():
        lines.append("== %s: %d boards, %s .. %s" % (name, s["boards"], s["first"], s["last"]))
        lines.append("   longest gap %d days (%s -> %s)" % (
            s["longest_gap_days"], s["longest_gap"][0], s["longest_gap"][1]))
        lines.append("   player rows mapped to Sleeper ids: %s of %d (worst board %s)" % (
            s["mapped_share"], s["player_rows_mapped"] + s["player_rows_unmapped"],
            s["worst_board_mapped_share"]))
        lines.append("   distinct unmapped source ids: %d; highest valued: %s" % (
            s["distinct_unmapped"], ", ".join(s["top_unmapped_source_keys"][:10])))
        lines.append("   boards per month: " + " ".join(
            "%s:%d" % kv for kv in sorted(s["boards_per_month"].items())))
    if "lookups" in rep:
        lk = rep["lookups"]
        lines.append("== lookups: %d (value on a board within %d days)" % (lk["n"], rep["max_age_days"]))
        for fmt, d in lk.items():
            if fmt == "n":
                continue
            lines.append("   %s: %s; by sources present: %s" % (
                fmt, d["share_within_max_age"], d["by_sources_present"]))
    return "\n".join(lines)
