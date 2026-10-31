"""The model-side 24 h read after the one-step 200 ms flip
(trade.packed_evidence and trade.first_page_store on together;
models-lead-launch.md §Gate-11-03 §3, addenda A3 and B3 (f3)). Read-only:
models-eng runs it and posts the output, release-lead collects it, and
models-lead rules on it.

    python3 -m backend.eval.flip_read --db URL --since ISO [--until ISO]
        [--as-of ISO] [--allow-postgres-readonly] [--weekly] [--json]
        [--i1-mode {0,1,2}]

The window is decks served in [since, until) and at or before as_of
(as_of defaults to now minus STAMP_SETTLE, until to none), read through
data.load_decks(as_of=...) plus a few direct read-only queries.

The CLI settles as_of itself: delivered_at is stamped off the request
thread, so near now an outcome can commit before its card's stamp and a
live deck reads as incomplete_deck (a transient G2 FAIL). as_of defaults to
the wall clock minus STAMP_SETTLE (5 min), and an --as-of later than that is
clamped to it, with a note on stderr giving both values. flip_read() takes
as_of as given; only the CLI reads the clock.

The G-table (a barred G prints PASS or FAIL):

  G1   pack integrity: pack_integrity decks among the decks with a pack row,
       retired or not, plus packs whose WHOLE run["display_moves"] (moves past
       as_of too) breaks the writer's contract (data.display_moves_problem;
       models-lead F1: the loader checks only delivered moves, so a malformed
       later move fails here at once). Bar 0.
  G2   no unexplained gaps: incomplete_deck decks among the FINAL packed
       decks and EVERY pack-less deck (A3). A packed deck is final when its
       pack retired by as_of or was served more than 25 h
       (data.IN_FLIGHT_WINDOW) before it. A pack-less deck (live evidence:
       the value core, prepared adoption; rows at build, delivered_at
       stamps) has no in-flight state, so its incomplete_deck (a gap, or an
       outcome on a row never stamped delivered) is final at once. A
       deferred-evidence (tiered) deck with no pack yet is the loader's
       in_flight inside 25 h, not incomplete_deck (past it, a lost pack, and
       barred like any other). calibration_refresh decks are not
       Trades decks and are not counted. Bar 0. Each incomplete deck must
       coincide with a restart or the kill (A3, B3), so their ids (at most
       20) are listed for that cross-check. The sufficiency count is the
       final packed decks alone: fewer than 10 is INSUFFICIENT, extend the
       window to 48 h.
  G3   outcomes join (U2): outcomes acted in the window (and by as_of) whose
       impression_id joins no loaded card, row or packed. An outcome whose
       deck was not loaded (served before the window) is checked against
       the evidence directly: a non-ghost deck_impressions row with that id,
       or a pack row of its run whose card_count covers its index; it is
       counted apart, as joined outside the window. An outcome joining a
       ghost row, loaded (LoggedCard.is_ghost) or of a deck not loaded (a
       deck_impressions row with is_ghost = 1), is counted apart too, as on
       a ghost row: ghosts are never shown, so it means a ghost reached a
       client. Bar 0 on each: orphans and outcomes on a ghost row. The kill
       recommendation (B3 (f4)) prints when G1 fails or G3 has orphans (lost
       data); an outcome on a ghost row is a serve bug and goes back to
       models-lead.
  G7   upgrade misses (U4-R2), every cause summed over the loaded packs but
       pack_integrity decks (G1's; row gone skips them too).
       Bar: other == 0. Reported, never barred (addendum C4): row gone, the
       misses whose pack recorded a stored count above the card while its
       page row was gone, with how many are named (C4 (d1)'s sub-count) and
       the (d1) split; the U4-R4 sum over the window, indicative only; and
       the packs whose per-card miss map (run["upgrade_miss_cards"]) does not
       tally to their upgrade_misses, the writer's invariant (a pack without
       the map, from before #439, isn't checked).
  G8   withdrawal_conflict decks. Bar 0.
  G9   no_delivery_evidence decks with any outcome (a missed delivered_at
       stamp, B3). Bar 0. The no_delivery_evidence total is reported too.
  G10  withdrawals by reason, first withdrawn in the window, read straight
       from deck_card_withdrawals. disposition_cut > 0 is expected and only
       reported. i1_dropped is barred at 0 unless --i1-mode is 2: trade_i1_mode
       1 (the launch value, the default) and 0 never withdraw for I-1, so any
       i1_dropped there is a bug (B3); at mode 2 it is reported.
Then the v5 exclusion counts over every loaded deck (each LoggedDeck.exclusion
value, the deck count, the partial_run decks replay leaves out) and
withdrawn_removed_by_reason over every loaded deck, and the overall line:
FAIL if a barred G fails, else INSUFFICIENT if G2 has fewer than 10 final
packed decks, else PASS.

--weekly adds the two rolling 7-day ceilings over [as_of - 7 d, as_of], for
the weekly BL-001 monitor through head-bizops:
  U4-R4  restart_split + evicted_split (U4_R4_CAUSES, addendum C2; a cause
         added later joins only by name) over viewed cards, at most
         U4_R4_CEILING, per cause and with row gone. Viewed cards are the
         distinct loaded non-ghost cards with a `viewed` outcome.
  B4     disposition_cut removals over delivered-range positions, at most
         B4_CEILING. Delivered-range positions are the delivered non-ghost
         cards plus the disposition_cut never-delivered (W0) removals, over
         the decks the loader includes (no exclusion: an excluded deck's
         deliveries are not read) that have delivery evidence: a pack, or a
         row with delivered_at by as_of.
Each prints its ratio, numerator and denominator, and OK or OVER.

--json prints the same as one JSON object. flip_read() returns a FlipRead
and weekly_read() a dict, so tests read the numbers without parsing text.

Exit status:
  0  PASS (and no weekly ceiling OVER);
  1  FAIL, or a weekly ceiling OVER (either wins over INSUFFICIENT);
  2  a refused database or a ReadOnlyViolation (nothing is printed to
     stdout), or a usage error, a malformed ISO 8601 --since, --until or
     --as-of included;
  3  INSUFFICIENT: fewer than 10 final packed decks, nothing failed; not a
     pass, extend the window to 48 h;
  4  an unexpected error (a crash, not a verdict): its traceback goes to
     stderr, nothing to stdout.

Read-only, enforced, not promised:
  - a SQLite path or sqlite:/// URL opens with mode=ro;
  - any other URL is refused unless --allow-postgres-readonly, and then only
    Postgres: every new connection is opened with
    default_transaction_read_only=on, runs SET SESSION CHARACTERISTICS AS
    TRANSACTION READ ONLY, and must answer SHOW transaction_read_only = on
    before anything reads (else ReadOnlyViolation);
  - on both, a statement that is not a read raises ReadOnlyViolation;
  - backend.server is never imported (a test pins it).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from urllib.parse import unquote, unquote_plus

from sqlalchemy import Integer, String, Text, column, create_engine, event, func, inspect, select, table

from backend.database import deck_impressions_table, deck_outcomes_table
from backend.eval import data, evidence_pack
from backend.eval.data import (
    CALIBRATION_REFRESH, IN_FLIGHT, IN_FLIGHT_WINDOW, INCOMPLETE_DECK, NO_DELIVERY_EVIDENCE,
    PACK_INTEGRITY, PACK_TABLE, PARTIAL_RUN_TIER, UPGRADE_MISS_OTHER, WITHDRAWAL_CONFLICT,
    WITHDRAWALS_TABLE, load_decks,
)

# A3: fewer final packed decks than this and G2 reads INSUFFICIENT (extend to 48 h).
MIN_FINAL_DECKS = 10
# U4-R4: the upgrade-miss causes the weekly ceiling sums (addendum C2) and the
# ceiling over viewed cards.
U4_R4_CAUSES = ("restart_split", "evicted_split")
U4_R4_CEILING = 0.01
# B4: disposition_cut removals over delivered-range positions.
B4_CEILING = 0.05
DISPOSITION_CUT = "disposition_cut"
# G10: I-1's withdrawal reason, barred unless trade_i1_mode is 2 (module doc).
I1_DROPPED = "i1_dropped"
WEEK = timedelta(days=7)
# The CLI's as_of is at most the wall clock minus this: delivered_at is
# stamped off the request thread, so an outcome can commit before its stamp.
STAMP_SETTLE = timedelta(minutes=5)
LIST_CAP = 20                   # ids listed per G
LOADER_EXCLUSIONS = (CALIBRATION_REFRESH, PACK_INTEGRITY, WITHDRAWAL_CONFLICT, IN_FLIGHT,
                     INCOMPLETE_DECK, NO_DELIVERY_EVIDENCE)
PASS, FAIL, INSUFFICIENT, REPORT = "PASS", "FAIL", "INSUFFICIENT", "REPORT"

# Only the columns the direct queries read.
_PACK_ROWS = table(PACK_TABLE, column("run_id", String), column("served_at", String),
                   column("header_json", Text), column("card_count", Integer))
_WITHDRAWAL_ROWS = table(WITHDRAWALS_TABLE, column("reason", String),
                         column("first_withdrawn_at", String), column("deck_job_id", String),
                         column("card_index", Integer), column("served_before", Integer))


class ReadOnlyViolation(RuntimeError):
    """The connection is not read-only, or a statement would write."""


# ---------------------------------------------------------------------------
# Read-only engine
# ---------------------------------------------------------------------------

_READ_PREFIXES = ("select", "with", "pragma", "show", "explain", "begin", "commit",
                  "rollback", "savepoint", "release")


def read_only_engine(db: str, *, allow_postgres_readonly: bool = False):
    """An engine that can only read `db` (a SQLite path or URL, or with
    allow_postgres_readonly a Postgres URL). Raises ValueError for anything
    else; the message never repeats the URL (it may hold a password)."""
    url = db if "://" in db else f"sqlite:///{db}"
    if url.startswith("sqlite:///"):
        eng = create_engine(f"sqlite:///file:{url[len('sqlite:///'):]}?mode=ro&uri=true",
                            connect_args={"uri": True})
    elif not allow_postgres_readonly:
        raise ValueError("refusing a non-SQLite database without --allow-postgres-readonly")
    elif url.startswith(("postgresql://", "postgresql+psycopg2://", "postgres://")):
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        eng = create_engine(url, connect_args={
            "options": "-c default_transaction_read_only=on -c statement_timeout=120s"})
        event.listen(eng, "connect", _read_only_session)
    else:
        raise ValueError("only a SQLite or a Postgres database can be read")
    event.listen(eng, "before_cursor_execute", _reads_only)
    return eng


def _read_only_session(dbapi_conn, _record) -> None:
    """Postgres, every new connection: make the session read-only and prove
    it (SHOW transaction_read_only = on) before anything reads on it."""
    cur = dbapi_conn.cursor()
    try:
        cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        dbapi_conn.commit()            # a SET rolled back would be undone
        cur.execute("SHOW transaction_read_only")
        state = cur.fetchone()[0]
        dbapi_conn.rollback()
    finally:
        cur.close()
    if state != "on":
        raise ReadOnlyViolation("read-only session required: transaction_read_only is not on")


def _reads_only(conn, cursor, statement, parameters, context, executemany) -> None:
    head = statement.lstrip().lstrip("(").split(None, 1)
    if not head or head[0].lower() not in _READ_PREFIXES:
        raise ReadOnlyViolation(f"blocked a non-read statement: {statement.strip()[:80]!r}")


# ---------------------------------------------------------------------------
# The 24 h read
# ---------------------------------------------------------------------------

@dataclass
class FlipRead:
    since: str
    until: str | None
    as_of: str
    decks: int
    exclusions: dict           # every LoggedDeck.exclusion value ("none": included) -> decks
    partial_run_decks: int     # unexcluded decks replay leaves out as partial_run
    withdrawn_removed_by_reason: dict   # over every loaded deck
    g1: dict
    g2: dict
    g3: dict
    g7: dict
    g8: dict
    g9: dict
    g10: dict
    overall: str
    weekly: dict | None = None


def flip_read(engine, *, since: str, as_of: str, until: str | None = None,
              i1_mode: int = 1) -> FlipRead:
    """The G-table (module doc) for decks served in [since, until), at or
    before as_of, and outcomes and withdrawals in the same window, with
    trade_i1_mode `i1_mode` in effect over it (G10)."""
    decks = load_decks(engine=engine, since=since, until=until, as_of=as_of)
    in_flight_from = (datetime.fromisoformat(as_of) - IN_FLIGHT_WINDOW).isoformat()
    with engine.connect() as conn:
        packs = _pack_rows(conn, since, until, as_of)
        g3 = _g3(conn, decks, _outcome_ids(conn, since, until, as_of))
        withdrawals = _withdrawals_by_reason(conn, since, until, as_of)
        w0 = _w0_indexes(conn, list(packs))

    pack_integrity = [d for d in decks if d.exclusion == PACK_INTEGRITY]
    malformed = _malformed_moves(packs, skip={d.deck_job_id for d in pack_integrity}, w0=w0)
    g1 = {"pack_decks": len(packs), "pack_integrity": len(pack_integrity),
          "display_moves_malformed": len(malformed),
          "ids": ([d.deck_job_id for d in pack_integrity] + malformed)[:LIST_CAP],
          "status": FAIL if pack_integrity or malformed else PASS}

    trades = [d for d in decks if d.exclusion != CALIBRATION_REFRESH]
    final_packed = [d for d in trades if d.deck_job_id in packs
                    and _final(d, packs[d.deck_job_id], as_of, in_flight_from)]
    packless = [d for d in trades if d.deck_job_id not in packs]
    read = {d.deck_job_id for d in final_packed + packless}
    incomplete = [d for d in trades if d.deck_job_id in read and d.exclusion == INCOMPLETE_DECK]
    g2 = {"final_packed_decks": len(final_packed), "packless_decks": len(packless),
          "incomplete": len(incomplete),
          "ids": [[d.deck_job_id, d.served_at] for d in incomplete][:LIST_CAP],
          "insufficient": len(final_packed) < MIN_FINAL_DECKS,
          "status": FAIL if incomplete else PASS}

    misses = _sum_counts(d.upgrade_misses for d in decks if d.exclusion != PACK_INTEGRITY)
    gone = _row_gone(packs, skip={d.deck_job_id for d in pack_integrity})
    off_map = _miss_map_mismatches(packs, skip={d.deck_job_id for d in pack_integrity})
    g7 = {"upgrade_misses": misses, "row_gone": gone["total"], "row_gone_named": gone["named"],
          "row_gone_split": gone["split"],
          "miss_map_mismatch": len(off_map), "miss_map_mismatch_ids": off_map[:LIST_CAP],
          # Addendum C4: the U4-R4 sum over this window is indicative only; the
          # 7-day ceiling is read weekly. Never part of G7's status.
          "indicative": _ceiling(_named_misses(misses), _viewed(decks), U4_R4_CEILING),
          "status": FAIL if misses.get(UPGRADE_MISS_OTHER, 0) > 0 else PASS}

    conflicts = [d.deck_job_id for d in decks if d.exclusion == WITHDRAWAL_CONFLICT]
    g8 = {"withdrawal_conflict": len(conflicts), "ids": conflicts[:LIST_CAP],
          "status": FAIL if conflicts else PASS}

    nde = [d for d in decks if d.exclusion == NO_DELIVERY_EVIDENCE]
    acted = [d.deck_job_id for d in nde if any(_acted(c) for c in d.cards)]
    g9 = {"no_delivery_evidence": len(nde), "with_outcomes": len(acted),
          "ids": acted[:LIST_CAP], "status": FAIL if acted else PASS}

    if i1_mode == 2:
        g10 = {"by_reason": withdrawals, "i1_mode": i1_mode, "status": REPORT,
               "note": "disposition_cut > 0 expected; i1_dropped reported at trade_i1_mode 2"}
    else:
        g10 = {"by_reason": withdrawals, "i1_mode": i1_mode,
               "status": FAIL if withdrawals.get(I1_DROPPED, 0) else PASS,
               "note": f"disposition_cut > 0 expected; any i1_dropped at trade_i1_mode "
                       f"{i1_mode} is a bug (barred at 0)"}

    exclusions = Counter(d.exclusion or "none" for d in decks)
    barred = (g1, g2, g3, g7, g8, g9, g10)
    overall = (FAIL if any(g["status"] == FAIL for g in barred)
               else INSUFFICIENT if g2["insufficient"] else PASS)
    return FlipRead(
        since=since, until=until, as_of=as_of, decks=len(decks),
        exclusions={k: exclusions.get(k, 0) for k in (*LOADER_EXCLUSIONS, "none")},
        partial_run_decks=sum(1 for d in decks if d.exclusion is None and any(
            c.evidence_tier == PARTIAL_RUN_TIER for c in d.cards)),
        withdrawn_removed_by_reason=_sum_counts(d.withdrawn_removed_by_reason for d in decks),
        g1=g1, g2=g2, g3=g3, g7=g7, g8=g8, g9=g9, g10=g10, overall=overall)


def _named_misses(misses: dict) -> int:
    """The U4-R4 numerator: the U4_R4_CAUSES counts, summed."""
    return sum(misses.get(cause, 0) for cause in U4_R4_CAUSES)


def _viewed(decks) -> int:
    """The U4-R4 denominator: viewed non-ghost cards (a viewed outcome joined by
    impression_id, never a row's existence)."""
    return sum(1 for d in decks for c in d.cards if not c.is_ghost and c.viewed)


def _miss_map_mismatches(packs, skip=()) -> list[str]:
    """The run_ids whose per-card miss map doesn't tally to their counts:
    Counter(run["upgrade_miss_cards"].values()) against run["upgrade_misses"]
    read as the loader reads it (data._upgrade_misses), zero causes dropped.
    The writer keeps the counts as the map's tally (#439), so any entry here
    is a writer defect. Reported under G7, never barred. A pack without the
    map (written before #439) isn't checked; one in `skip` (failing
    integrity) or unreadable is G1's."""
    off = []
    for job, (_served_at, header_json) in sorted(packs.items()):
        if job in skip:
            continue
        try:
            run = json.loads(header_json)["run"]
        except (ValueError, KeyError, TypeError):
            continue
        if not isinstance(run, dict) or not isinstance(run.get("upgrade_miss_cards"), dict):
            continue
        try:
            counts = data._upgrade_misses(run)
        except (TypeError, ValueError):
            off.append(job)
            continue
        tally = Counter(run["upgrade_miss_cards"].values())
        if {c: n for c, n in counts.items() if n} != dict(tally):
            off.append(job)
    return off


def _row_gone(packs, skip=()) -> dict:
    """U4 option A's guard, reported under G7 and never barred: the misses on
    the stored path whose pack recorded a stored count above the card while its
    page row was gone (run["upgrade_miss_row_gone"], card_index -> the pack's
    stored count), and how many of those carry a named cause in
    run["upgrade_miss_cards"] (absent means other). With A on, the named ones
    are named only because the row was gone; with A off, the entries are the
    `other` misses A would name. A page-store bug can't hide behind A.
    Addendum C4 (d1) splits it by run["upgrade_miss_row_gone_why"]
    (card_index -> "replaced", the key's row now holds a newer deck, explained,
    or "no_row": aged, over budget, or a bug); an entry with no why is
    "unsplit", as is any other why. (d1)'s sub-count is `named`. Absent keys
    count 0; a pack in `skip` (failing integrity) or unreadable is G1's."""
    total = named = 0
    split = {"replaced": 0, "no_row": 0, "unsplit": 0}
    for job, (_served_at, header_json) in packs.items():
        if job in skip:
            continue
        try:
            run = json.loads(header_json)["run"]
        except (ValueError, KeyError, TypeError):
            continue
        if not isinstance(run, dict):
            continue
        gone, causes = run.get("upgrade_miss_row_gone"), run.get("upgrade_miss_cards")
        why = run.get("upgrade_miss_row_gone_why")
        if not isinstance(gone, dict):
            continue
        causes = causes if isinstance(causes, dict) else {}
        why = why if isinstance(why, dict) else {}
        for index in gone:
            total += 1
            named += causes.get(index, UPGRADE_MISS_OTHER) != UPGRADE_MISS_OTHER
            reason = why.get(index)
            split[reason if reason in ("replaced", "no_row") else "unsplit"] += 1
    return {"total": total, "named": named, "split": split}


def _final(deck, pack, as_of: str, in_flight_from: str) -> bool:
    """Whether a packed deck is final for G2 (module doc). A readable pack's
    run metadata decides it through the loader's own rule
    (data._pack_state); an unreadable one (pack_integrity) only by age."""
    served_at, header_json = pack
    if deck.exclusion == PACK_INTEGRITY:
        return served_at < in_flight_from
    run = json.loads(header_json)["run"]
    return data._pack_state(run, -1, served_at, as_of, in_flight_from)[0]


def _g3(conn, decks, outcome_ids: list[str]) -> dict:
    loaded = {c.impression_id for d in decks for c in d.cards if not c.is_ghost}
    ghosts = {c.impression_id for d in decks for c in d.cards if c.is_ghost}
    jobs = {d.deck_job_id for d in decks}
    joined = 0
    on_ghost: list[str] = []           # never shown, so a ghost reached a client
    orphans: list[str] = []
    elsewhere: list[str] = []          # their deck was not loaded: check the evidence
    for iid in outcome_ids:
        if iid in loaded:
            joined += 1
        elif iid in ghosts:
            on_ghost.append(iid)
        elif _run_of(iid)[0] in jobs:  # its deck is in the window, the card is not
            orphans.append(iid)
        else:
            elsewhere.append(iid)
    found, ghost_rows = _joins_elsewhere(conn, set(elsewhere))
    on_ghost += [iid for iid in elsewhere if iid in ghost_rows]
    orphans += [iid for iid in elsewhere if iid not in found and iid not in ghost_rows]
    return {"outcomes": len(outcome_ids), "joined": joined,
            "joined_outside_window": sum(1 for iid in elsewhere if iid in found),
            "on_ghost": len(on_ghost), "ghost_ids": sorted(set(on_ghost))[:LIST_CAP],
            "orphans": len(orphans), "ids": sorted(set(orphans))[:LIST_CAP],
            "status": FAIL if orphans or on_ghost else PASS}


def _run_of(impression_id: str) -> tuple[str | None, int | None]:
    """(run_id, card_index) of a contract id (contract.card_impression_id),
    else (None, None)."""
    run, sep, index = impression_id.rpartition(":")
    return (run, int(index)) if sep and index.isdigit() else (None, None)


def _joins_elsewhere(conn, ids: set[str]) -> tuple[set[str], set[str]]:
    """Of ids whose deck was not loaded: those that join a card of a deck
    outside the window (a non-ghost deck_impressions row, or a pack of their
    run covering their index), and those on a ghost row there (is_ghost = 1)."""
    imp = deck_impressions_table
    found: set[str] = set()
    ghosts: set[str] = set()
    for chunk in _chunks(sorted(ids)):
        for iid, ghost in conn.execute(select(imp.c.impression_id, func.coalesce(
                imp.c.is_ghost, 0)).where(imp.c.impression_id.in_(chunk))):
            (ghosts if ghost else found).add(iid)
    parsed = {iid: _run_of(iid) for iid in ids - found - ghosts}
    parsed = {iid: ri for iid, ri in parsed.items() if ri[0] is not None}
    if parsed and inspect(conn).has_table(PACK_TABLE):
        counts: dict[str, int] = {}
        for chunk in _chunks(sorted({run for run, _i in parsed.values()})):
            counts.update(conn.execute(select(_PACK_ROWS.c.run_id, _PACK_ROWS.c.card_count)
                                       .where(_PACK_ROWS.c.run_id.in_(chunk))).all())
        found.update(iid for iid, (run, index) in parsed.items()
                     if run in counts and index < counts[run])
    return found, ghosts


def _pack_rows(conn, since, until, as_of) -> dict[str, tuple[str, str]]:
    """run_id -> (served_at, header_json) for the pack rows in the window
    (load_decks' filters)."""
    if not inspect(conn).has_table(PACK_TABLE):
        return {}
    p = _PACK_ROWS
    q = select(p.c.run_id, p.c.served_at, p.c.header_json).where(p.c.served_at <= as_of)
    if since:
        q = q.where(p.c.served_at >= since)
    if until:
        q = q.where(p.c.served_at < until)
    return {r.run_id: (r.served_at, r.header_json) for r in conn.execute(q)}


def _malformed_moves(packs: dict, skip=(), w0=None) -> list[str]:
    """G1 (F1): the run_ids, sorted, whose pack header's whole
    run["display_moves"] breaks the writer's contract, past as_of included
    (data.display_moves_problem; `w0`: run_id -> its served_before=0
    indexes, from _w0_indexes). A pack in `skip` (already pack_integrity)
    or with an unreadable header or deliveries is the loader's."""
    out = []
    for run_id, (_served_at, header) in packs.items():
        head = data._json_dict(header) or {}
        run, card_count = head.get("run"), head.get("card_count")
        if run_id in skip or not isinstance(run, dict) or type(card_count) is not int:
            continue
        try:
            evidence_pack.check_deliveries(run, card_count)
        except evidence_pack.PackIntegrityError:
            continue
        if data.display_moves_problem(run, card_count, (w0 or {}).get(run_id, frozenset())):
            out.append(run_id)
    return sorted(out)


def _w0_indexes(conn, run_ids: list[str]) -> dict[str, set[int]]:
    """run_id -> the card_indexes of its served_before=0 withdrawals, every
    one recorded (G1 checks the whole header, past as_of too)."""
    if not run_ids or not inspect(conn).has_table(WITHDRAWALS_TABLE):
        return {}
    w, out = _WITHDRAWAL_ROWS, {}
    for chunk in _chunks(sorted(run_ids)):
        for run_id, index in conn.execute(select(w.c.deck_job_id, w.c.card_index).where(
                w.c.deck_job_id.in_(chunk), w.c.served_before == 0)):
            out.setdefault(run_id, set()).add(index)
    return out


def _outcome_ids(conn, since, until, as_of) -> list[str]:
    """The impression_id of every outcome acted in the window, by as_of."""
    out = deck_outcomes_table
    q = select(out.c.impression_id).where(out.c.acted_at >= since, out.c.acted_at <= as_of)
    if until:
        q = q.where(out.c.acted_at < until)
    return list(conn.execute(q).scalars())


def _withdrawals_by_reason(conn, since, until, as_of) -> dict[str, int]:
    """G10: deck_card_withdrawals rows first withdrawn in the window, by reason."""
    if not inspect(conn).has_table(WITHDRAWALS_TABLE):
        return {}
    w = _WITHDRAWAL_ROWS
    q = (select(w.c.reason, func.count()).where(w.c.first_withdrawn_at >= since,
                                                 w.c.first_withdrawn_at <= as_of)
         .group_by(w.c.reason))
    if until:
        q = q.where(w.c.first_withdrawn_at < until)
    return dict(sorted(conn.execute(q).all()))


def _acted(card) -> bool:
    """Any outcome (the writer's whole action vocabulary reduces to these)."""
    return (card.viewed or card.liked or card.passed or card.proposed
            or card.not_interested or card.undone)


def _sum_counts(dicts) -> dict[str, int]:
    total: Counter = Counter()
    for d in dicts:
        total.update(d)
    return dict(sorted(total.items()))


def _chunks(items: list, size: int = 500):
    for i in range(0, len(items), size):
        yield items[i:i + size]


# ---------------------------------------------------------------------------
# The weekly ceilings (U4-R4, B4)
# ---------------------------------------------------------------------------

def weekly_read(engine, *, as_of: str) -> dict:
    """U4-R4 and B4 over decks served in [as_of - 7 d, as_of] (module doc)."""
    since = (datetime.fromisoformat(as_of) - WEEK).isoformat()
    decks = load_decks(engine=engine, since=since, as_of=as_of)
    with engine.connect() as conn:
        packs = _pack_rows(conn, since, None, as_of)
    packed = set(packs)

    misses = _sum_counts(d.upgrade_misses for d in decks if d.exclusion != PACK_INTEGRITY)
    causes = {cause: n for cause, n in misses.items() if cause in U4_R4_CAUSES}
    viewed = _viewed(decks)
    gone = _row_gone(packs, skip={d.deck_job_id for d in decks if d.exclusion == PACK_INTEGRITY})

    evidenced = [d for d in decks if d.exclusion is None and (
        d.deck_job_id in packed or any(not c.is_ghost and data._delivered_by(c.delivered_at, as_of)
                                       for c in d.cards))]
    cuts = sum(d.withdrawn_removed_by_reason.get(DISPOSITION_CUT, 0) for d in evidenced)
    delivered = sum(1 for d in evidenced for c in d.cards if not c.is_ghost and c.delivered)
    return {
        "since": since, "as_of": as_of,
        "u4_r4": {**_ceiling(sum(causes.values()), viewed, U4_R4_CEILING), "causes": causes,
                  "row_gone": gone["total"], "row_gone_named": gone["named"],
                  "row_gone_split": gone["split"]},
        "b4": {**_ceiling(cuts, delivered + cuts, B4_CEILING), "evidenced_decks": len(evidenced)},
    }


def _ceiling(numerator: int, denominator: int, ceiling: float) -> dict:
    over = (Fraction(numerator, denominator) > Fraction(str(ceiling)) if denominator
            else numerator > 0)
    return {"numerator": numerator, "denominator": denominator,
            "ratio": numerator / denominator if denominator else None,
            "ceiling": ceiling, "status": "OVER" if over else "OK"}


# ---------------------------------------------------------------------------
# Output and CLI
# ---------------------------------------------------------------------------

def _pairs(counts: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in counts.items()) or "none"


def render(r: FlipRead) -> str:
    g1, g2, g3, g7, g8, g9, g10 = r.g1, r.g2, r.g3, r.g7, r.g8, r.g9, r.g10
    lines = [
        f"Flip read (model side, models-lead §Gate-11-03 §3, A3, B3): decks served "
        f"from {r.since}{f' until {r.until}' if r.until else ''}, as of {r.as_of}; "
        f"{r.decks} decks loaded.",
        "",
        "| G | what | result | bar | status |",
        "|---|---|---|---|---|",
        f"| G1 | pack_integrity decks (+ malformed display moves) / decks with a pack row "
        f"| {g1['pack_integrity']} (+ {g1['display_moves_malformed']}) / "
        f"{g1['pack_decks']} | 0 | {g1['status']} |",
        f"| G2 | incomplete_deck / Trades decks read (final packed + every pack-less) "
        f"| {g2['incomplete']} / {g2['final_packed_decks'] + g2['packless_decks']} "
        f"({g2['final_packed_decks']} final packed + {g2['packless_decks']} pack-less) "
        f"| 0; INSUFFICIENT below {MIN_FINAL_DECKS} final packed | {g2['status']} |",
        f"| G3 | outcomes joining no card / on a ghost row | {g3['orphans']} / "
        f"{g3['on_ghost']} of {g3['outcomes']} (joined {g3['joined']}, outside the window "
        f"{g3['joined_outside_window']}) | 0 / 0 | {g3['status']} |",
        f"| G7 | upgrade misses by cause | {_pairs(g7['upgrade_misses'])} | other 0 "
        f"| {g7['status']} |",
        f"| G8 | withdrawal_conflict decks | {g8['withdrawal_conflict']} | 0 | {g8['status']} |",
        f"| G9 | no_delivery_evidence decks with an outcome | {g9['with_outcomes']} of "
        f"{g9['no_delivery_evidence']} | 0 | {g9['status']} |",
        f"| G10 | withdrawals by reason (window), trade_i1_mode {g10['i1_mode']} | "
        f"{_pairs(g10['by_reason'])} | "
        f"{'reported' if g10['i1_mode'] == 2 else 'i1_dropped 0'} | {g10['status']} |",
        "",
    ]
    if g1["ids"]:
        lines.append(f"G1 pack_integrity or malformed-display-moves decks: {', '.join(g1['ids'])}")
    if g2["ids"]:
        lines.append("G2 incomplete decks (each must coincide with a restart or the kill): "
                     + ", ".join(f"{job} (served {at})" for job, at in g2["ids"]))
    if g2["insufficient"]:
        lines.append(f"G2 INSUFFICIENT (<{MIN_FINAL_DECKS} final packed decks): extend to "
                     f"48 h ({g2['final_packed_decks']} final packed)")
    if g3["ids"]:
        lines.append(f"G3 outcomes joining no card: {', '.join(g3['ids'])}")
    if g3["ghost_ids"]:
        lines.append("G3 outcomes on a ghost row (ghosts are never shown: a ghost reached "
                     f"a client): {', '.join(g3['ghost_ids'])}")
    if g8["ids"]:
        lines.append(f"G8 withdrawal_conflict decks: {', '.join(g8['ids'])}")
    if g9["ids"]:
        lines.append(f"G9 no_delivery_evidence decks with an outcome: {', '.join(g9['ids'])}")
    lines.append(f"G7 (not barred) row gone: {g7['row_gone']} misses whose pack recorded a "
                 f"stored count above the card while its page row was gone; "
                 f"{g7['row_gone_named']} of them with a named cause (U4 option A's guard); "
                 f"{_pairs(g7['row_gone_split'])}.")
    lines.append(f"G7 (not barred) packs whose per-card miss map doesn't tally to their "
                 f"upgrade_misses (a writer defect, #439's invariant): "
                 f"{g7['miss_map_mismatch']}"
                 + (f" ({', '.join(g7['miss_map_mismatch_ids'])})" if g7["miss_map_mismatch_ids"]
                    else "") + ".")
    lines.append(_ceiling_line("G7 (not barred) indicative U4-R4 over this window, named misses "
                               "/ viewed cards", g7["indicative"])
                 + "; indicative only, the 7-day ceiling is read with --weekly.")
    lines.append(f"G10 note: {g10['note']}.")
    lines.append(f"v5 exclusions (decks): {_pairs(r.exclusions)}; partial_run decks "
                 f"(replay): {r.partial_run_decks}; withdrawn_removed_by_reason "
                 f"(every loaded deck): {_pairs(r.withdrawn_removed_by_reason)}")
    lines.append(f"OVERALL: {r.overall}")
    # B3 (f4): the kill is for lost data, unreadable packs (G1) or outcomes that
    # join no card (G3 orphans). An outcome on a ghost row is a serve bug (a
    # ghost reached a client), not lost data: it goes back to models-lead.
    if g1["status"] == FAIL or g3["orphans"]:
        lines.append("G1 failed or G3 has orphans: models-lead recommends the kill "
                     "(first_page_store_enabled 0) at once; the operator decides via "
                     "release-lead (B3 (f4)).")
    elif r.overall == FAIL:
        if g3["on_ghost"]:
            lines.append("G3: an outcome on a ghost row (a ghost reached a client): "
                         "a serve bug, not lost data.")
        lines.append("Back to models-lead, who rules within the turn (B3 (f4)).")
    if r.weekly:
        w = r.weekly
        lines += ["", f"Weekly ceilings, decks served {w['since']} to {w['as_of']} "
                      "(BL-001 monitor, via head-bizops):",
                  _ceiling_line("U4-R4 named upgrade misses / viewed cards", w["u4_r4"])
                  + f" [{_pairs(w['u4_r4']['causes'])}]; row gone "
                  f"{w['u4_r4']['row_gone']} ({w['u4_r4']['row_gone_named']} named; "
                  f"{_pairs(w['u4_r4']['row_gone_split'])}), not barred",
                  _ceiling_line("B4 disposition_cut removals / delivered-range positions",
                                w["b4"])]
    return "\n".join(lines)


def _ceiling_line(label: str, c: dict) -> str:
    ratio = "n/a" if c["ratio"] is None else f"{c['ratio'] * 100:.2f}%"
    return (f"{label}: {ratio} ({c['numerator']} / {c['denominator']}), ceiling "
            f"{c['ceiling'] * 100:g}%: {c['status']}")


def _iso(value: str) -> str:
    """argparse type: an ISO time as UTC isoformat (naive means UTC), so it
    compares lexically with the stored timestamps. A malformed one is a
    usage error (exit 2)."""
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an ISO 8601 time: {value!r}") from None
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        dt - _WINDOW_REACH            # the read reaches back this far: must not overflow
    except (ValueError, OverflowError):
        raise argparse.ArgumentTypeError(
            f"out of range for the read (it reaches back {_WINDOW_REACH.days} days): "
            f"{value!r}") from None
    return dt.isoformat()


# How far a read reaches back from as_of: the weekly window (7 d) and the
# in-flight window (25 h) both reach back from as_of, so 9 days covers either
# with a margin. A time out of range for that is a usage error, not a crash.
_WINDOW_REACH = timedelta(days=9)


def _secret_fragments(db: str) -> list[str]:
    """The pieces of a database URL a driver or URL parser may echo in an
    error: everything after the scheme, and each piece of it split on
    ':', '@', '/', '?', '&', '=', '#' and ',' (so an unencoded '@', '?', '/'
    or ',' in a password, a libpq host list, or a query-string password can't
    shift what counts as the host), each also percent-decoded, both plain and
    with '+' as a space. Longest first, so a username inside a
    password can't leave the password's tail behind. Pieces shorter than 3
    characters are left (they would redact noise), and harmless words in the
    URL (a username like postgres) are redacted too: a safe-side cost. A SQLite
    URL carries no credentials, so nothing."""
    if "://" not in db or db.split("://", 1)[0].lower().startswith("sqlite"):
        return []
    rest = db.split("://", 1)[1]
    pieces = {rest, *re.split(r"[:@/?&=#,]", rest)}
    pieces |= {unquote(p) for p in pieces} | {unquote_plus(p) for p in pieces}
    return sorted((p for p in pieces if len(p) >= 3), key=len, reverse=True)


def _redact(text: str, db: str) -> str:
    for piece in _secret_fragments(db):
        text = text.replace(piece, "***")
    return text


def _now() -> datetime:
    """The wall clock, UTC: the CLI's only clock read (tests pin it)."""
    return datetime.now(timezone.utc)


def _settled_as_of(as_of: str | None, prog: str) -> str:
    """The CLI's as_of (module doc): the wall clock minus STAMP_SETTLE by
    default, and a later --as-of clamped to that, with a note on stderr
    giving both values. bdk_audit's CLI shares it."""
    settled = (_now() - STAMP_SETTLE).replace(microsecond=0).isoformat()
    as_of = as_of or settled
    if datetime.fromisoformat(as_of) > datetime.fromisoformat(settled):
        print(f"{prog}: note: --as-of {as_of} is later than now minus STAMP_SETTLE "
              f"({STAMP_SETTLE.total_seconds() / 60:g} min); clamped to {settled}",
              file=sys.stderr)
        as_of = settled
    return as_of


class _Parser(argparse.ArgumentParser):
    """argparse whose usage errors are redacted: a database URL passed by
    mistake (a stray positional, a mistyped flag) is never printed in full."""

    redact_argv: list[str] = []

    def error(self, message):
        for token in self.redact_argv:
            if "://" in token:
                message = _redact(message, token)
        super().error(message)


def main(argv=None) -> int:
    ap = _Parser(
        prog="python3 -m backend.eval.flip_read",
        description="The model-side 24 h read after the 200 ms flip (G1-G3, G7-G10), "
                    "read-only.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--db", required=True,
                    help="SQLite path or sqlite:/// URL (opened mode=ro), or a Postgres URL "
                         "with --allow-postgres-readonly")
    ap.add_argument("--since", required=True, type=_iso,
                    help="ISO start of the window: decks served, outcomes acted and "
                         "withdrawals first withdrawn at or after it")
    ap.add_argument("--until", type=_iso,
                    help="ISO end of the window, exclusive (default: none)")
    ap.add_argument("--as-of", type=_iso,
                    help="ISO clock of the read (default: now minus STAMP_SETTLE, 5 min; a "
                         "later value is clamped to that, with a note on stderr)")
    ap.add_argument("--allow-postgres-readonly", action="store_true",
                    help="allow a Postgres URL; the session is set read-only and must "
                         "report transaction_read_only = on before anything reads")
    ap.add_argument("--weekly", action="store_true",
                    help="also print the rolling 7-day ceilings over [as_of - 7 d, as_of]: "
                         "U4-R4, restart_split + evicted_split / viewed cards <= 1%%; B4, "
                         "disposition_cut removals / delivered-range positions <= 5%%, "
                         "where delivered-range positions are the delivered non-ghost cards "
                         "plus the disposition_cut never-delivered removals, over the "
                         "loader-included decks with delivery evidence (a pack, or rows "
                         "with delivered_at)")
    ap.add_argument("--json", action="store_true", help="print one JSON object")
    ap.add_argument("--i1-mode", type=int, choices=(0, 1, 2), default=1,
                    help="the trade_i1_mode the window ran under (default 1, the launch "
                         "value): at 0 or 1 any i1_dropped withdrawal fails G10; at 2 it is "
                         "only reported")
    ap.redact_argv = list(sys.argv[1:] if argv is None else argv)
    args = ap.parse_args(argv)
    try:
        return _run(args)
    except Exception:             # a crash is never a verdict: 4, apart from FAIL's 1
        # Redacted: a driver's connect error can echo the URL's credentials.
        print(_redact(traceback.format_exc(), args.db), file=sys.stderr, end="")
        return 4


def _run(args) -> int:
    """main() past parsing: the read, its output and its exit status."""
    try:
        eng = read_only_engine(args.db, allow_postgres_readonly=args.allow_postgres_readonly)
    except ValueError as e:              # a URL parser's message can echo the URL
        print(f"flip_read: {_redact(str(e), args.db)}", file=sys.stderr)
        return 2
    as_of = _settled_as_of(args.as_of, "flip_read")
    try:
        result = flip_read(eng, since=args.since, as_of=as_of, until=args.until,
                           i1_mode=args.i1_mode)
        if args.weekly:
            result.weekly = weekly_read(eng, as_of=as_of)
    except ReadOnlyViolation as e:
        print(f"flip_read: {_redact(str(e), args.db)}", file=sys.stderr)
        return 2
    finally:
        eng.dispose()
    print(json.dumps(asdict(result), indent=2, sort_keys=True) if args.json else render(result))
    over = result.weekly is not None and "OVER" in (
        result.weekly["u4_r4"]["status"], result.weekly["b4"]["status"])
    if result.overall == FAIL or over:
        return 1
    return 3 if result.overall == INSUFFICIENT else 0


if __name__ == "__main__":
    sys.exit(main())
