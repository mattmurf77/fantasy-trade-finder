"""The B-DK-4..7 production audit (models-lead-launch.md addendum C §C5; the
bars in models-lead-wave2.md B-DK-4..7, D-207): served violations of
deck.quality_filters' four rules (backend/deck_quality.py), against a bar of
0. Read-only. models-eng runs it on the post-flip window, then weekly with
the readout.

    python3 -m backend.eval.bdk_audit --db URL --since ISO [--until ISO]
        [--as-of ISO] [--allow-postgres-readonly] [--json]

  B-DK-4  breakup     deck_quality._breakup, per card
  B-DK-5  filler      deck_quality._filler, per card
  B-DK-6  redundant   deck_quality._redundant_side, per card
  B-DK-7  repeat      per deck: an asset in more than REPEAT_CAP of the first
                      REPEAT_WINDOW displayed cards; a breach on a short deck
                      is checked with deck_quality._repeat_cap itself

Every threshold is deck_quality's own, imported, never restated (a test pins
it).

The audit set (U6): the Trades decks served in [since, until), at or before
as_of, read through data.load_decks(as_of=...). calibration_refresh decks are
not Trades decks. pack_integrity and withdrawal_conflict decks are skipped and
counted by reason: the loader stops before removing their never-delivered
withdrawals, so their displayed positions can't be trusted (as blind_grade's
served set, B5). Per deck: the first REPEAT_WINDOW non-ghost cards by
displayed position (LoggedCard.position, serve-time display moves included:
data.py, D3), plus every viewed card, "viewed"
being a `viewed` outcome joined by impression_id (LoggedCard.viewed), never a
row's existence (U4-R3). assets_json, features_json and
source_like_impression_id are read for those impression_ids, chunked, and
every audited deck's pack header (its run metadata).

A card with no full row (no deck_impressions row with assets_json: a packed
card, or the upgrade miss's row built from the pack) can't be audited. A
viewed one is reported by cause (U4-R3), read from its pack's run metadata
upgrade_miss_cards ({"<card_index>": cause}); no pack or no entry is `other`.
It counts as not auditable for every rule, as does an unviewed one.

The rule inputs (models-lead addendum D2): the filter's own, frozen once per
run in its pack's run["filter_inputs"] (#492), v FILTER_INPUTS_VERSION:
  filter_ran       false: the filter didn't run (flag off, an empty deck, or
                   it raised), so the deck went out unfiltered. It is skipped
                   and counted (skipped_decks filter_not_run), for every rule.
  market           {asset id: the filter's elo_to_value(seed) value}, null
                   for an unseeded asset (the filter's None), passed to the
                   rules as recorded; NaN tokens are read as NaN. An asset
                   absent from it (or from `position`) is one the filter
                   never saw: its card is not auditable for B-DK-4..6.
  position         {asset id: position}, null for None.
  lineup_slots     the league's starting slots as the filter read them;
                   position_caps() of them None (unknown) means the filter
                   skipped B-DK-6, which reads as a pass.
  viewer_team,     the viewer's key and per-team QB/TE holdings: B-DK-6 reads
  qb_te            the viewer's and the card's counterparty's (features_json
                   partner_user_id, as str); an absent team holds nothing.
  protected        the trade_hashes the filter exempted (is_protected at
                   filter time; owner_published is set after the filter).
                   A recorded deck's protection, for all four rules, is its
                   card's trade_hash being in it.
  give / receive   assets_json: served-time, str ids.
The deck's record state is counted in `filter_inputs`: recorded (the shape
above), record_failed (filter_ran true but no usable inputs: the writer's
recording failed or the record is malformed or another version),
pack_without_record (a pack written before #492), no_pack (live evidence:
pinned, opponent, intent, presentation-exempt and demo decks, and any deck
without a pack). Only a recorded deck's cards are audited for B-DK-4..6; on
the rest they are not auditable, never a pass. The valuation_json markets
are not read: approximate values can't certify a zero bar (D2 (c)).
B-DK-7 needs only the cards' ids, so it audits every Trades deck; a deck
without a record takes protection from its row: features_json likes_you,
standing_offer (the standing_offer_reason) and wildcard, and the
source_like_impression_id column, where UNRECORDED_PROTECTION (injected and
retest are never set, owner_published is set after the filter,
fatigue_retest is set but not frozen) reads unprotected: a violation on a
fatigue retest card is a false positive (check its trade_hash against
deck_suppressions.retest_trade_hash). A deck without a record is read on the
assumption the flag was on (live since FILTERS_LIVE_AT, D-207); a --since
before that adds a note.

Per rule: violations, audited cards (the rule ran on them), protected cards
(exempt), not auditable cards, the bar 0, a status, and up to LIST_CAP
examples (deck id, card_index, displayed position, trade_hash). A card can
violate more than one rule; each counts. Repeat counts breaches, one per
(deck, asset): its over-cap appearances are those past the REPEAT_CAP-th in
displayed order, and a breach whose over-cap appearances are all protected
cards is explained (_repeat_cap lets them hold their positions), counted
apart, not a violation. So is a breach on a short deck: _repeat_cap defers
an over-cap card to just after the cards it keeps, so with fewer than
REPEAT_WINDOW cards to keep the deferred ones still land in the window. A
breach is explained that way when re-running deck_quality._repeat_cap on
the deck's whole displayed order leaves it unchanged (the filter could do no
better); that needs a well-formed full row for every displayed card, and a
deck whose cards may be a prefix of what was built never qualifies: a loader
exclusion (but a packed deck's in_flight: its pack holds every card), a
partial_run deck, or a pack-less deck of REPEAT_WINDOW cards or more (it may
have stopped after a publication batch, unmarked). Those stay violations. Both are counted in `explained`, split as
explained_protected / explained_short_deck, with examples (`why`). A window card with no full row is not auditable and
its deck incomplete (a breach found there still counts). The filter ran on
the built order, ghost rows and later withdrawals included, so a served
breach can come from the serve order: each example gives the deck's ghost
rows inside the filter's window and its never-delivered withdrawals removed.

Status: FAIL (a violation); PASS (no violation, every audit-set card checked
or exempt); NOT_AUDITABLE (nothing checked: violations is None, never 0);
else INCOMPLETE (no violation among the checked cards, some unchecked).
OVERALL: FAIL if a rule fails, PASS if every rule passes and no deck was
skipped, else INCOMPLETE.

Exit status (flip_read's scheme):
  0  PASS;
  1  FAIL;
  2  a refused database or a ReadOnlyViolation (nothing on stdout), or a usage
     error, a malformed ISO 8601 --since, --until or --as-of included;
  3  INCOMPLETE: no violation found, but a rule couldn't check every card
     (a deck without a filter record can't be, for B-DK-4..6) or a deck was skipped: not a pass;
  4  an unexpected error (a crash, not a verdict): its redacted traceback on
     stderr, nothing on stdout.

Read-only as flip_read is (its read_only_engine, statement guard, redaction,
ISO parsing and the --as-of settle clamp, all imported): a SQLite path opens
mode=ro; any other URL is refused unless --allow-postgres-readonly, and then
every Postgres session must prove transaction_read_only = on. backend.server
is never imported (a test pins it). audit() returns a BdkAudit; --json
prints it as one object.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from collections import Counter
from dataclasses import asdict, dataclass
from types import SimpleNamespace

from sqlalchemy import inspect, select

from backend.database import deck_impressions_table
from backend.deck_quality import (
    BREAKUP_MIN_RATIO, FILLER_FLOOR, FILLER_FRAC, PROTECTED_ATTRS, REDUNDANT_MIN_RATIO, REPEAT_CAP,
    REPEAT_WINDOW, _breakup, _filler, _redundant_side, _repeat_cap, is_protected, position_caps,
)
from backend.eval.data import (
    CALIBRATION_REFRESH, IN_FLIGHT, PACK_INTEGRITY, PACK_TABLE, PARTIAL_RUN_TIER,
    UPGRADE_MISS_OTHER, WITHDRAWAL_CONFLICT, _json_dict, load_decks,
)
from backend.eval.flip_read import (
    _PACK_ROWS, FAIL, LIST_CAP, PASS, ReadOnlyViolation, _chunks, _iso, _Parser, _redact,
    _settled_as_of, read_only_engine,
)

INCOMPLETE, NOT_AUDITABLE = "INCOMPLETE", "NOT_AUDITABLE"
EXIT = {PASS: 0, FAIL: 1, INCOMPLETE: 3}
# D-207: deck.quality_filters went live in prod (baseline-request.md, CHANGELOG).
FILTERS_LIVE_AT = "2026-10-15T01:18:00+00:00"
# Decks whose displayed positions can't be trusted (module doc): skipped, counted.
_UNTRUSTED = (PACK_INTEGRITY, WITHDRAWAL_CONFLICT)
# run["filter_inputs"] (models-lead D2, #492): the version read, and a deck's
# record states (module doc). FILTER_NOT_RUN decks are skipped, counted.
FILTER_INPUTS_VERSION = 1
RECORDED, RECORD_FAILED, PACK_WITHOUT_RECORD, NO_PACK = (
    "recorded", "record_failed", "pack_without_record", "no_pack")
FILTER_NOT_RUN = "filter_not_run"
# The protection attributes a served row records: card attribute -> features_json key.
_RECORDED_FEATURES = {"likes_you": "likes_you", "standing_offer_reason": "standing_offer",
                      "wildcard": "wildcard"}
UNRECORDED_PROTECTION = tuple(a for a in PROTECTED_ATTRS if a not in _RECORDED_FEATURES
                              and a != "source_like_impression_id")
RULES = {
    "breakup": ("B-DK-4", f"best piece received < {BREAKUP_MIN_RATIO:g} x best piece given"),
    "filler": ("B-DK-5", f"a piece below max({FILLER_FLOOR:g}, {FILLER_FRAC:g} x the "
                         "headliner)"),
    "redundant": ("B-DK-6", f"either side gets a TE/QB while keeping its slot cap of "
                            f"comparables (>= {REDUNDANT_MIN_RATIO:g} x the incoming)"),
    "repeat": ("B-DK-7", f"an asset in more than {REPEAT_CAP} of the first {REPEAT_WINDOW} "
                         "displayed cards"),
}
EVIDENCE = {
    "give_receive": "assets_json (served-time)",
    "filter_inputs": "the pack's run['filter_inputs'] (v1, models-lead D2): the market, "
                     "positions, lineup slots, viewer and counterparty QB/TE holdings and "
                     "protected trade_hashes the filter read; only recorded decks are "
                     "audited for B-DK-4..6 (valuation_json is not read: D2 (c))",
    "protection": "a recorded deck: the filter-time protected trade_hashes; otherwise "
                  "(B-DK-7 only) features_json likes_you / standing_offer / wildcard and "
                  "the source_like_impression_id column, where "
                  + ", ".join(UNRECORDED_PROTECTION) + " read unprotected (a violation on "
                  "a fatigue retest card is a false positive)",
    "filter_flag": "filter_ran per recorded deck (false: skipped, filter_not_run); a deck "
                   "without a record assumes deck.quality_filters on (live since "
                   f"{FILTERS_LIVE_AT})",
}


@dataclass
class BdkAudit:
    since: str
    until: str | None
    as_of: str
    decks: int                 # Trades decks audited
    skipped_decks: dict        # PACK_INTEGRITY / WITHDRAWAL_CONFLICT / FILTER_NOT_RUN -> decks
    filter_inputs: dict        # the audited decks by record state (module doc)
    audit_cards: int           # the U6 set: the window plus viewed cards past it
    viewed_past_window: int
    no_full_row: dict          # viewed by cause (U4-R3), unviewed, examples
    rules: dict                # breakup / filler / redundant / repeat -> counts
    evidence: dict             # rule input -> where the evidence records it
    notes: list
    overall: str


def audit(engine, *, since: str, as_of: str, until: str | None = None) -> BdkAudit:
    """The B-DK-4..7 counts (module doc) for the Trades decks served in
    [since, until), at or before as_of."""
    decks = load_decks(engine=engine, since=since, until=until, as_of=as_of)
    skipped = Counter(d.exclusion for d in decks if d.exclusion in _UNTRUSTED)
    candidates = [d for d in decks if d.exclusion not in (CALIBRATION_REFRESH, *_UNTRUSTED)]
    with engine.connect() as conn:
        headers = _run_headers(conn, [d.deck_job_id for d in candidates])
        records = {d.deck_job_id: _filter_inputs(headers.get(d.deck_job_id))
                   for d in candidates}
        skipped.update(state for state, _ in records.values() if state == FILTER_NOT_RUN)
        trades = [d for d in candidates if records[d.deck_job_id][0] != FILTER_NOT_RUN]
        sets = {d.deck_job_id: _audit_set(d) for d in trades}
        cards = {job: window + past for job, (window, past) in sets.items()}
        rows = _full_rows(conn, [c.impression_id for cs in cards.values() for c in cs])

        def protected_of(deck, card, row) -> bool:
            """A recorded deck's filter-time protection, else the row's (module doc)."""
            fi = records[deck.deck_job_id][1]
            *_ids_and_partner, own = row
            return card.trade_hash in fi["protected"] if fi is not None else own

        repeat = _repeat(trades, sets, rows, lambda ids: _full_rows(conn, ids), set(headers),
                         protected_of)

    card_rules = {name: _tally() for name in ("breakup", "filler", "redundant")}
    no_row = {"viewed_by_cause": Counter(), "unviewed": 0, "examples": []}
    for d in trades:
        fi = records[d.deck_job_id][1]
        for c in cards[d.deck_job_id]:
            row = rows.get(c.impression_id)
            if row is None:                       # no full row: nothing to check it with
                for t in card_rules.values():
                    t["not_auditable"] += 1
                if c.viewed:
                    cause = _miss_cards(headers.get(d.deck_job_id)).get(str(c.card_index),
                                                                         UPGRADE_MISS_OTHER)
                    no_row["viewed_by_cause"][cause] += 1
                    _example(no_row["examples"], {**_where(c), "cause": cause})
                else:
                    no_row["unviewed"] += 1
                continue
            give, receive, partner, _ = row
            if protected_of(d, c, row):
                for t in card_rules.values():
                    t["protected"] += 1
                continue
            if fi is None or give is None or not all(a in fi["market"] and a in fi["position"]
                                                     for a in (*give, *receive)):
                for t in card_rules.values():   # no record, or an asset it never saw
                    t["not_auditable"] += 1
                continue
            market, position, held = fi["market"].get, fi["position"].get, fi["qb_te"]
            caps = position_caps(fi["lineup_slots"])   # None: the filter skipped B-DK-6
            for name, violated in (
                    ("breakup", _breakup(give, receive, market)),
                    ("filler", _filler(give, receive, market)),
                    ("redundant", caps is not None and (
                        _redundant_side(held.get(fi["viewer_team"], ()), give, receive,
                                        market, position, caps)
                        or _redundant_side(held.get(partner, ()), receive, give,
                                           market, position, caps)))):
                t = card_rules[name]
                t["audited"] += 1
                if violated:
                    t["violations"] += 1
                    _example(t["examples"], _where(c))

    rules = {**card_rules, "repeat": repeat}
    for name, t in rules.items():
        t["bdk"], t["rule"] = RULES[name]
        t["status"] = _status(t)
        if t["status"] == NOT_AUDITABLE:
            t["violations"] = None
    no_row["viewed_by_cause"] = dict(sorted(no_row["viewed_by_cause"].items()))
    statuses = [t["status"] for t in rules.values()]
    overall = (FAIL if FAIL in statuses
               else PASS if not skipped and all(s == PASS for s in statuses) else INCOMPLETE)
    notes = []
    if since < FILTERS_LIVE_AT:
        notes.append(f"--since {since} is before deck.quality_filters went live "
                     f"({FILTERS_LIVE_AT}): earlier decks were served unfiltered.")
    return BdkAudit(
        since=since, until=until, as_of=as_of, decks=len(trades),
        skipped_decks=dict(sorted(skipped.items())),
        filter_inputs=dict(sorted(Counter(records[d.deck_job_id][0] for d in trades).items())),
        audit_cards=sum(len(cs) for cs in cards.values()),
        viewed_past_window=sum(len(p) for _w, p in sets.values()),
        no_full_row=no_row, rules=rules, evidence=EVIDENCE, notes=notes, overall=overall)


def _audit_set(deck) -> tuple[list, list]:
    """(the first REPEAT_WINDOW non-ghost cards by displayed position, the
    viewed cards past them)."""
    shown = sorted((c for c in deck.cards if not c.is_ghost), key=lambda c: c.position)
    return shown[:REPEAT_WINDOW], [c for c in shown[REPEAT_WINDOW:] if c.viewed]


def _ids(side) -> list[str] | None:
    """An assets_json side as str ids; None when it isn't a list (the card
    is then not auditable, never a crash)."""
    return [str(a) for a in side] if isinstance(side, list) else None


def _full_rows(conn, ids: list[str]) -> dict[str, tuple]:
    """impression_id -> (give, receive, partner, protected) for each id with
    a full row (assets_json), read chunked. give and receive are None when
    either side is missing, empty or not a list; partner is features_json's
    partner_user_id as str (the filter's str(target_user_id)); protected is
    the row's recorded protection (module doc), for a deck without a record."""
    imp = deck_impressions_table
    out: dict[str, tuple] = {}
    for chunk in _chunks(ids):
        for r in conn.execute(select(imp.c.impression_id, imp.c.assets_json,
                                     imp.c.features_json, imp.c.source_like_impression_id)
                              .where(imp.c.impression_id.in_(chunk))):
            assets = _json_dict(r.assets_json)
            if assets is None:
                continue
            features = _json_dict(r.features_json) or {}
            give, receive = _ids(assets.get("give")), _ids(assets.get("receive"))
            if not give or not receive:           # missing, not a list, or empty: unusable
                give = receive = None
            card = SimpleNamespace(source_like_impression_id=r.source_like_impression_id,
                                   **{a: features.get(k) for a, k in _RECORDED_FEATURES.items()})
            out[r.impression_id] = (give, receive, str(features.get("partner_user_id")),
                                    is_protected(card))
    return out


def _run_headers(conn, run_ids: list[str]) -> dict[str, dict]:
    """run_id -> its pack's run metadata ({} when unreadable), for the runs
    with a pack row (a pack holds every built card). JSON's NaN token reads
    as NaN, as the filter's own value was."""
    if not run_ids or not inspect(conn).has_table(PACK_TABLE):
        return {}
    out: dict[str, dict] = {}
    for chunk in _chunks(run_ids):
        for run_id, header in conn.execute(select(_PACK_ROWS.c.run_id, _PACK_ROWS.c.header_json)
                                           .where(_PACK_ROWS.c.run_id.in_(chunk))):
            run = (_json_dict(header) or {}).get("run")
            out[run_id] = run if isinstance(run, dict) else {}
    return out


def _miss_cards(run: dict | None) -> dict:
    """A pack's run["upgrade_miss_cards"] ({} without a pack, or when absent
    or unreadable)."""
    cards = (run or {}).get("upgrade_miss_cards")
    return cards if isinstance(cards, dict) else {}


def _filter_inputs(run: dict | None) -> tuple[str, dict | None]:
    """(record state, run["filter_inputs"] when RECORDED) for a deck whose
    pack's run metadata is `run` (None: no pack). Module doc."""
    if run is None:
        return NO_PACK, None
    fi = run.get("filter_inputs")
    if fi is None:
        return PACK_WITHOUT_RECORD, None
    if (not isinstance(fi, dict) or type(fi.get("v")) is not int
            or fi["v"] != FILTER_INPUTS_VERSION):
        return RECORD_FAILED, None
    if fi.get("filter_ran") is False:
        return FILTER_NOT_RUN, None
    held, slots = fi.get("qb_te"), fi.get("lineup_slots")
    if (fi.get("filter_ran") is True and isinstance(fi.get("market"), dict)
            and isinstance(fi.get("position"), dict) and isinstance(fi.get("viewer_team"), str)
            and isinstance(fi.get("protected"), list) and isinstance(held, dict)
            and all(isinstance(h, list) for h in held.values())
            and (slots is None or isinstance(slots, list))):
        return RECORDED, fi
    return RECORD_FAILED, None


def _short_deck(deck, rows, fetch, packed: bool, protected_of) -> bool:
    """Whether the deck's whole displayed order is a fixed point of
    deck_quality._repeat_cap (module doc). False when any displayed card has
    no well-formed full row, and for any deck whose cards may be only a prefix
    of what was built, where an over-cap card at the prefix's end would read
    as deferred (#469 QA): a loader exclusion other than a packed deck's
    in_flight (a pack holds every built card; a pack-less in_flight or lost
    pack's incomplete_deck holds the first REPEAT_WINDOW and viewed rows); a
    partial_run deck (its delivered rows); and a pack-less deck of
    REPEAT_WINDOW cards or more, never-delivered withdrawals included, which
    may have stopped after a publication batch with nothing marking it
    (complete ones read FAIL: the safe side).
    Rows the window didn't need are fetched and added to `rows`;
    `protected_of(deck, card, row)` is each card's protection (module doc)."""
    if deck.exclusion is not None and not (packed and deck.exclusion == IN_FLIGHT):
        return False
    if any(c.evidence_tier == PARTIAL_RUN_TIER for c in deck.cards):
        return False
    shown = sorted((c for c in deck.cards if not c.is_ghost), key=lambda c: c.position)
    if not packed and len(shown) + deck.withdrawn_removed >= REPEAT_WINDOW:   # W0s count
        return False
    missing = [c.impression_id for c in shown if c.impression_id not in rows]
    if missing:
        rows.update(fetch(missing))
    served = [rows.get(c.impression_id) for c in shown]
    if any(row is None or row[0] is None for row in served):
        return False
    # _repeat_cap reads is_protected(card): likes_you carries the protection.
    cards = [SimpleNamespace(give_player_ids=row[0], receive_player_ids=row[1],
                             likes_you=protected_of(deck, c, row))
             for c, row in zip(shown, served)]
    return [id(c) for c in _repeat_cap(cards)[0]] == [id(c) for c in cards]


def _repeat(trades, sets, rows, fetch, packed: set, protected_of) -> dict:
    """B-DK-7 per deck over its window (module doc). `fetch(ids)` reads more
    full rows, for the short-deck check; `packed` is the run_ids with a pack;
    `protected_of(deck, card, row)` is a card's protection."""
    t = {"violations": 0, "explained": 0, "explained_protected": 0, "explained_short_deck": 0,
         "audited": 0, "not_auditable": 0, "incomplete_decks": 0, "examples": [],
         "explained_examples": []}
    for d in trades:
        window = sets[d.deck_job_id][0]
        seen: Counter = Counter()
        at: dict[str, list[int]] = {}
        over: dict[str, list[bool]] = {}   # asset -> protected, per over-cap appearance
        for c in window:
            row = rows.get(c.impression_id)
            if row is None or row[0] is None:
                t["not_auditable"] += 1
                continue
            t["audited"] += 1
            protected = protected_of(d, c, row)
            assets = (*row[0], *row[1])
            for a in assets:
                if seen[a] >= REPEAT_CAP:
                    over.setdefault(a, []).append(protected)
                at.setdefault(a, []).append(c.card_index)
            seen.update(assets)
        t["incomplete_decks"] += any((rows.get(c.impression_id) or (None,))[0] is None
                                     for c in window)
        short = None                       # checked once per deck, only on a breach
        for asset, protected in over.items():
            why = "protected" if all(protected) else None
            if why is None:
                short = (_short_deck(d, rows, fetch, d.deck_job_id in packed, protected_of)
                         if short is None else short)
                why = "short_deck" if short else None
            if why:
                t["explained"] += 1
                t[f"explained_{why}"] += 1
            else:
                t["violations"] += 1
            _example(t["explained_examples" if why else "examples"], {
                "deck_job_id": d.deck_job_id, "asset": asset, "card_indexes": at[asset],
                "why": why, "over_cap_protected": protected,
                "ghost_slots": sum(1 for c in d.cards
                                   if c.is_ghost and c.card_index < REPEAT_WINDOW),
                "withdrawn_removed": d.withdrawn_removed})
    return t


def _tally() -> dict:
    return {"violations": 0, "audited": 0, "protected": 0, "not_auditable": 0, "examples": []}


def _where(card) -> dict:
    return {"deck_job_id": card.deck_job_id, "card_index": card.card_index,
            "position": card.position, "trade_hash": card.trade_hash}


def _example(examples: list, item: dict) -> None:
    if len(examples) < LIST_CAP:
        examples.append(item)


def _status(t: dict) -> str:
    if t["violations"]:
        return FAIL
    if not t["not_auditable"] and (t["audited"] or t.get("protected")):
        return PASS
    return INCOMPLETE if t["audited"] else NOT_AUDITABLE


# ---------------------------------------------------------------------------
# Output and CLI
# ---------------------------------------------------------------------------

def _pairs(counts: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in counts.items()) or "none"


def render(r: BdkAudit) -> str:
    rp = r.rules["repeat"]
    lines = [
        f"B-DK-4..7 production audit (deck.quality_filters on served cards; models-lead "
        f"addendum C §C5): Trades decks served from {r.since}"
        f"{f' until {r.until}' if r.until else ''}, as of {r.as_of}; {r.decks} decks, "
        f"{r.audit_cards} audit-set cards (the first {REPEAT_WINDOW} by displayed position "
        f"plus {r.viewed_past_window} viewed past them).",
        "",
        "| B-DK | rule | violations | audited | protected (exempt) | not auditable | bar | "
        "status |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, t in r.rules.items():
        violations = "n/a" if t["violations"] is None else t["violations"]
        if name == "repeat":
            violations = (f"{violations} (explained: {t['explained_protected']} by protected "
                          f"cards, {t['explained_short_deck']} by a short deck)")
        lines.append(f"| {t['bdk']} | {name}: {t['rule']} | {violations} | {t['audited']} | "
                     f"{t.get('protected', '-')} | {t['not_auditable']} | 0 | {t['status']} |")
    lines.append("")
    for name, t in r.rules.items():
        if t["status"] == NOT_AUDITABLE:
            lines.append(f"{t['bdk']} {name} is NOT AUDITABLE from evidence: "
                         f"{t['not_auditable']} cards couldn't be checked.")
    if rp["incomplete_decks"]:
        lines.append(f"B-DK-7 repeat: {rp['incomplete_decks']} decks have a window card with "
                     "no full row.")
    lines.append(f"Filter inputs (models-lead D2), audited decks by record: "
                 f"{_pairs(r.filter_inputs)}; only recorded decks are audited for B-DK-4..6.")
    nf = r.no_full_row
    lines.append(f"Viewed, no full row (U4-R3), by cause: {_pairs(nf['viewed_by_cause'])}; "
                 f"unviewed audit-set cards with no full row: {nf['unviewed']}")
    if nf["examples"]:
        lines.append("  " + ", ".join(f"{e['deck_job_id']}#{e['card_index']} ({e['cause']})"
                                      for e in nf["examples"]))
    if r.skipped_decks:
        lines.append(f"Skipped decks (pack_integrity / withdrawal_conflict: displayed positions "
                     f"untrustworthy, G1 / G8 signals; filter_not_run: served unfiltered): "
                     f"{_pairs(r.skipped_decks)}")
    for name, t in r.rules.items():
        if name != "repeat" and t["examples"]:
            lines.append(f"{t['bdk']} {name} violations: " + ", ".join(
                f"{e['deck_job_id']}#{e['card_index']} (position {e['position']}, "
                f"trade_hash {e['trade_hash']})" for e in t["examples"]))
    for key, label in (("examples", "violations"), ("explained_examples", "explained")):
        if rp[key]:
            lines.append(f"B-DK-7 repeat {label}: " + "; ".join(
                f"{e['deck_job_id']} asset {e['asset']} at card_index "
                f"{', '.join(map(str, e['card_indexes']))} ("
                + (f"{e['why']}, " if e["why"] else "") + "over-cap protected "
                f"{e['over_cap_protected']}, ghost slots {e['ghost_slots']}, withdrawn "
                f"{e['withdrawn_removed']})" for e in rp[key]))
    lines.append("Evidence (rule input: where it is recorded):")
    lines += [f"  {k}: {v}" for k, v in r.evidence.items()]
    lines += [f"Note: {n}" for n in r.notes]
    lines.append(f"OVERALL: {r.overall}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = _Parser(
        prog="python3 -m backend.eval.bdk_audit",
        description="The B-DK-4..7 production audit (deck.quality_filters on served cards), "
                    "read-only.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--db", required=True,
                    help="SQLite path or sqlite:/// URL (opened mode=ro), or a Postgres URL "
                         "with --allow-postgres-readonly")
    ap.add_argument("--since", required=True, type=_iso,
                    help="ISO start of the window: decks served at or after it")
    ap.add_argument("--until", type=_iso,
                    help="ISO end of the window, exclusive (default: none)")
    ap.add_argument("--as-of", type=_iso,
                    help="ISO clock of the read (default: now minus STAMP_SETTLE, 5 min; a "
                         "later value is clamped to that, with a note on stderr)")
    ap.add_argument("--allow-postgres-readonly", action="store_true",
                    help="allow a Postgres URL; the session is set read-only and must "
                         "report transaction_read_only = on before anything reads")
    ap.add_argument("--json", action="store_true", help="print one JSON object")
    ap.redact_argv = list(sys.argv[1:] if argv is None else argv)
    args = ap.parse_args(argv)
    try:
        return _run(args)
    except Exception:             # a crash is never a verdict: 4, apart from FAIL's 1
        print(_redact(traceback.format_exc(), args.db), file=sys.stderr, end="")
        return 4


def _run(args) -> int:
    """main() past parsing: the audit, its output and its exit status."""
    try:
        eng = read_only_engine(args.db, allow_postgres_readonly=args.allow_postgres_readonly)
    except ValueError as e:              # a URL parser's message can echo the URL
        print(f"bdk_audit: {_redact(str(e), args.db)}", file=sys.stderr)
        return 2
    as_of = _settled_as_of(args.as_of, "bdk_audit")
    try:
        result = audit(eng, since=args.since, as_of=as_of, until=args.until)
    except ReadOnlyViolation as e:
        print(f"bdk_audit: {_redact(str(e), args.db)}", file=sys.stderr)
        return 2
    finally:
        eng.dispose()
    print(json.dumps(asdict(result), indent=2, sort_keys=True) if args.json else render(result))
    return EXIT[result.overall]


if __name__ == "__main__":
    sys.exit(main())
