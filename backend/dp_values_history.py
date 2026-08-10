"""Dated DynastyProcess value boards — `values_as_of(date) -> {sleeper_id: value}`.

WHY THIS EXISTS
---------------
Three prior #169 analyses (`calibration-report-2026-08-09.md`,
`hypothesis-pick-capital-2026-08-09.md`, `hypothesis-bench-depth-2026-08-09.md`)
all recorded the same blocker: *"FTF has no dated value snapshots, so a past
season's roster can only be priced with TODAY's board"* — which made the
preseason `RosterValueStrength` source untestable and forced two documented
method substitutions.

**That blocker was wrong.** The DynastyProcess data repo keeps the full git
history of `files/values-players.csv` (weekly-ish commits back to ~2020-09),
and any commit's copy of the file is a plain GET:

    https://raw.githubusercontent.com/dynastyprocess/data/<sha>/files/values-players.csv

Each historical snapshot even carries its own `scrape_date` column, so a board
can be dated from its own contents rather than from the commit timestamp alone.
Same CC-BY source, same trust boundary, and the same attribution obligation as
the live file already documented in `docs/integrations/dynastyprocess.md`.

WHAT THIS MODULE IS (AND IS NOT)
--------------------------------
It is a **research/validation** data source. Nothing under `backend/outlook/`,
no route, and no feature flag imports it — the shipped product still reads the
live board through `data_loader.py`. It exists so offline backtests can price a
2022 roster with a 2022 board instead of a 2026 one.

Offline by default. `values_as_of()` reads a **committed, slimmed snapshot**
from `backend/tests/fixtures/dp-values-history/` and never touches the network;
the live resolve/fetch path is opt-in (`allow_network=True`) and is only used by
`scripts/dp_values_history_capture.py` to mint new fixtures.

THE NAME → SLEEPER-ID JOIN
--------------------------
`values-players.csv` is name-keyed; everything downstream in FTF is Sleeper-id
keyed. The join REUSES the shipped crosswalk rather than inventing one:

  Tier 1  `espn_service` DP crosswalk (`db_playerids.csv`), position-strict
          (#127), with `data_loader.DP_TO_SLEEPER_NAME` applied — byte-for-byte
          the join the live Elo-seed pipeline already performs.
  Tier 2  same crosswalk, generational suffixes (jr/sr/ii/iii/iv/v) stripped
          from BOTH sides. Still position-strict. This is pure name drift:
          DP wrote "Allen Robinson II" in 2022 and "Allen Robinson" later.
  Tier 3  OPTIONAL, caller-supplied `extra_name_pos` — a second
          (normalised name, position) → sleeper_id index, e.g. built from the
          Sleeper players dump for the players actually rostered in the
          backtest. Needed because `db_playerids.csv` is a *current* file that
          has dropped some long-retired players, and because DP sometimes uses
          a short form Sleeper does not ("Ken Walker III" vs "Kenneth Walker").
          Also position-strict.

Every call returns a `JoinReport` alongside the value map. **The unmatched rate
is not a footnote** — a board that resolves 70 % of a roster produces a
starting-lineup value that is mostly noise, so callers are expected to report
it. Measured rates for the 2022–2025 preseason boards are in
`docs/feedback/items/169-outlook-league-summary/dated-values-revalidation-2026-08-09.md`.

Unresolved DP rows are DROPPED, never guessed — the same rule the ESPN import
follows (`report.unmatched`, never a placeholder id).
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .data_loader import DP_SCORING_PARAM, DP_TO_SLEEPER_NAME, normalise_name

# ---------------------------------------------------------------------------
# Upstream
# ---------------------------------------------------------------------------

VALUES_PATH = "files/values-players.csv"
COMMITS_URL = "https://api.github.com/repos/dynastyprocess/data/commits"
RAW_URL_TEMPLATE = (
    "https://raw.githubusercontent.com/dynastyprocess/data/{sha}/" + VALUES_PATH
)
# A bare curl gets a redirect stub from raw.githubusercontent.com; a
# User-Agent is required for the real bytes (verified 2026-08-09).
_HEADERS = {"User-Agent": "FantasyTradeFinder/1.0"}

SNAPSHOT_DIR = os.path.join(
    os.path.dirname(__file__), "tests", "fixtures", "dp-values-history"
)
INDEX_PATH = os.path.join(SNAPSHOT_DIR, "index.json")

# Columns kept in a committed snapshot. The live file also carries
# team/age/draft_year/ecr_*/fp_id; none of them are read by anything here or
# by the shipped values pipeline, and dropping them keeps a snapshot ~8x
# smaller than the raw file.
SLIM_COLUMNS = ("player", "pos", "value_1qb", "value_2qb", "scrape_date")

_SUFFIX_TOKENS = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})


# ---------------------------------------------------------------------------
# NFL season calendar (the dates the backtests ask boards for)
# ---------------------------------------------------------------------------
# Thursday-night kickoff of week 1. Used to turn "preseason 2024" into a real
# calendar date; the caller owns the semantics, this is just the anchor.
SEASON_KICKOFF: dict[int, _dt.date] = {
    2022: _dt.date(2022, 9, 8),
    2023: _dt.date(2023, 9, 7),
    2024: _dt.date(2024, 9, 5),
    2025: _dt.date(2025, 9, 4),
}


def week_boundary(season: int, week: int) -> _dt.date:
    """Date on/after which week `week` of `season` is complete.

    `week=0` is kickoff day itself — i.e. "the last board published before a
    single game was played", which is exactly what a preseason prediction is
    allowed to know. Week W lands one week later per week."""
    if season not in SEASON_KICKOFF:
        raise KeyError("no kickoff date recorded for season %r" % season)
    return SEASON_KICKOFF[season] + _dt.timedelta(days=7 * week)


# ---------------------------------------------------------------------------
# Live resolve + fetch (capture path only — never used by an offline run)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CommitRef:
    sha: str
    committed_at: str      # ISO-8601 Z, from the commit's committer date


def _http_get(url: str, timeout: int, _opener=None) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    opener = _opener or urllib.request.urlopen
    with opener(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def resolve_commit(target_date, *, timeout: int = 30, _opener=None) -> CommitRef:
    """Nearest commit to `files/values-players.csv` at-or-before `target_date`.

    GitHub's commits API returns newest-first and honours `until=`, so the
    first row of a `per_page=1&until=<date>` query IS the answer — no paging,
    no client-side scan."""
    if isinstance(target_date, _dt.date):
        until = target_date.isoformat() + "T23:59:59Z"
    else:
        until = str(target_date)
    url = COMMITS_URL + "?" + urllib.parse.urlencode(
        {"path": VALUES_PATH, "per_page": "1", "until": until})
    from . import api_observability as _api_obs
    with _api_obs.observe_call("dynastyprocess", "values_history",
                               active=_opener is None, phase="commits") as _ob:
        raw = _http_get(url, timeout, _opener)
        rows = json.loads(raw)
        _ob.ok(status=200, response_bytes=len(raw), rows=len(rows))
    if not rows:
        raise LookupError("no values-players.csv commit at or before %s" % until)
    head = rows[0]
    return CommitRef(sha=head["sha"],
                     committed_at=head["commit"]["committer"]["date"])


def fetch_values_csv(sha: str, *, timeout: int = 30, _opener=None) -> str:
    """Raw `values-players.csv` as it stood at `sha`."""
    from . import api_observability as _api_obs
    with _api_obs.observe_call("dynastyprocess", "values_history",
                               active=_opener is None, phase="raw") as _ob:
        raw = _http_get(RAW_URL_TEMPLATE.format(sha=sha), timeout, _opener)
        _ob.ok(status=200, response_bytes=len(raw),
               rows=max(raw.count("\n") - 1, 0))
    return raw


def slim_csv(raw: str) -> str:
    """Reduce a raw board to `SLIM_COLUMNS`, dropping value-less rows.

    A row with no 1QB *and* no SF value carries nothing this module can use;
    keeping it would only inflate the committed fixture."""
    reader = csv.DictReader(io.StringIO(raw))
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(SLIM_COLUMNS),
                            lineterminator="\n")
    writer.writeheader()
    for row in reader:
        if not _num(row.get("value_1qb")) and not _num(row.get("value_2qb")):
            continue
        writer.writerow({c: (row.get(c) or "") for c in SLIM_COLUMNS})
    return out.getvalue()


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Committed snapshots (the offline path everything analytical uses)
# ---------------------------------------------------------------------------

def load_index(index_path: str = INDEX_PATH) -> dict:
    with open(index_path) as f:
        return json.load(f)


def available_keys(index_path: str = INDEX_PATH) -> list[str]:
    return sorted(load_index(index_path).get("snapshots") or {})


def load_snapshot_rows(key: str, *, snapshot_dir: str = SNAPSHOT_DIR,
                       index_path: str = INDEX_PATH) -> tuple[list[dict], dict]:
    """(rows, meta) for a committed snapshot, keyed by its target date."""
    index = load_index(index_path)
    meta = (index.get("snapshots") or {}).get(key)
    if meta is None:
        raise KeyError(
            "no committed DP board for %r — available: %s (mint one with "
            "scripts/dp_values_history_capture.py)"
            % (key, sorted(index.get("snapshots") or {})))
    with open(os.path.join(snapshot_dir, meta["file"]), newline="") as f:
        return list(csv.DictReader(f)), meta


# ---------------------------------------------------------------------------
# Name → Sleeper-id join
# ---------------------------------------------------------------------------

def strip_generational_suffix(normed: str) -> str:
    """'allen robinson ii' -> 'allen robinson'. No-op when that would empty
    the name (a one-token name that happens to be a suffix token)."""
    toks = [t for t in normed.split() if t not in _SUFFIX_TOKENS]
    return " ".join(toks) or normed


@dataclass
class JoinReport:
    """How a board resolved onto Sleeper ids. Callers MUST report this — a
    low match rate invalidates everything computed from the value map."""
    total_rows: int = 0
    matched: int = 0
    by_tier: dict[int, int] = field(default_factory=dict)
    unmatched_names: list[tuple[str, str]] = field(default_factory=list)

    @property
    def unmatched(self) -> int:
        return self.total_rows - self.matched

    @property
    def unmatched_rate(self) -> float:
        return (self.unmatched / self.total_rows) if self.total_rows else 0.0

    def summary(self) -> str:
        return ("rows=%d matched=%d unmatched=%d (%.1f%%) tiers=%s"
                % (self.total_rows, self.matched, self.unmatched,
                   100 * self.unmatched_rate,
                   {k: self.by_tier[k] for k in sorted(self.by_tier)}))


def default_crosswalk():
    """The BUNDLED `db_playerids` snapshot, parsed — deliberately not
    `espn_service.get_crosswalk()`, which would hit the network on first call.

    Verified 2026-08-09: on all four preseason boards the bundled snapshot
    resolves exactly as many rows as the live file, so the offline choice
    costs nothing in coverage and buys repeatability."""
    from . import espn_service
    return espn_service.load_crosswalk(espn_service._SNAPSHOT_PATH)


def build_value_map(rows, *, scoring: str = "1qb", crosswalk=None,
                    extra_name_pos: dict | None = None
                    ) -> tuple[dict[str, float], JoinReport]:
    """{sleeper_id: value} from parsed board rows. See the module docstring
    for the three join tiers; `extra_name_pos` supplies tier 3."""
    col = "value_" + DP_SCORING_PARAM.get(scoring, scoring)
    xwalk = crosswalk if crosswalk is not None else default_crosswalk()

    # tier-2 index: suffix-stripped view of the same crosswalk, position-strict
    stripped_xwalk: dict[tuple[str, str], str] = {}
    for (nm, pos), sid in xwalk.by_name_pos.items():
        stripped_xwalk.setdefault((strip_generational_suffix(nm), pos), sid)
    extra = extra_name_pos or {}
    stripped_extra: dict[tuple[str, str], str] = {}
    for (nm, pos), sid in extra.items():
        stripped_extra.setdefault((strip_generational_suffix(nm), pos), sid)

    values: dict[str, float] = {}
    report = JoinReport()
    for row in rows:
        report.total_rows += 1
        pos = (row.get("pos") or "").strip().upper()
        raw_name = normalise_name(row.get("player") or "")
        mapped = DP_TO_SLEEPER_NAME.get(raw_name, raw_name)
        bare = strip_generational_suffix(mapped)

        sid, tier = None, None
        for candidate, t in (
            (xwalk.by_name_pos.get((mapped, pos)), 1),
            (xwalk.by_name_pos.get((raw_name, pos)), 1),
            (stripped_xwalk.get((bare, pos)), 2),
            (extra.get((mapped, pos)) or extra.get((raw_name, pos)), 3),
            (stripped_extra.get((bare, pos)), 3),
        ):
            if candidate:
                sid, tier = candidate, t
                break
        if sid is None:
            report.unmatched_names.append((row.get("player") or "", pos))
            continue
        report.matched += 1
        report.by_tier[tier] = report.by_tier.get(tier, 0) + 1
        # First writer wins: DP rows are value-ordered, so a duplicate
        # normalised name keeps the more valuable player rather than whichever
        # row happened to come last.
        values.setdefault(sid, _num(row.get(col)))
    return values, report


def values_as_of(key, *, scoring: str = "1qb", crosswalk=None,
                 extra_name_pos: dict | None = None,
                 allow_network: bool = False, timeout: int = 30,
                 snapshot_dir: str = SNAPSHOT_DIR, index_path: str = INDEX_PATH,
                 _opener=None) -> tuple[dict[str, float], JoinReport, dict]:
    """`{sleeper_id: dynasty value}` as the board stood on `key`.

    `key` is an ISO date string (or `datetime.date`). Offline by default: the
    date must have a committed snapshot, and a miss raises rather than
    silently substituting a neighbouring board. `allow_network=True` falls
    back to resolving + fetching the nearest commit at-or-before the date.

    Returns `(values, join_report, snapshot_meta)`."""
    key = key.isoformat() if isinstance(key, _dt.date) else str(key)
    try:
        rows, meta = load_snapshot_rows(key, snapshot_dir=snapshot_dir,
                                        index_path=index_path)
    except (KeyError, FileNotFoundError):
        if not allow_network:
            raise
        ref = resolve_commit(_dt.date.fromisoformat(key), timeout=timeout,
                             _opener=_opener)
        raw = fetch_values_csv(ref.sha, timeout=timeout, _opener=_opener)
        rows = list(csv.DictReader(io.StringIO(slim_csv(raw))))
        meta = {"sha": ref.sha, "committed_at": ref.committed_at,
                "file": None, "rows": len(rows), "live": True}
    values, report = build_value_map(rows, scoring=scoring, crosswalk=crosswalk,
                                     extra_name_pos=extra_name_pos)
    return values, report, meta
