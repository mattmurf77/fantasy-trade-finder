"""The B-DK-4..7 production audit (models-lead-launch.md addendum C §C5; the
bars in models-lead-wave2.md B-DK-4..7, D-207): served violations of
deck.quality_filters' four rules (backend/deck_quality.py), against a bar of
0. Read-only. models-eng runs it on the post-flip window, then weekly with
the readout.

    python3 -m backend.eval.bdk_audit --db URL --since ISO [--until ISO]
        [--as-of ISO] [--allow-postgres-readonly] [--no-evidence-log PATH] [--json]

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
                   rules as recorded; NaN tokens are read as NaN (a v5
                   record). A value that is neither null nor a number makes
                   the record record_failed. An asset absent from it (or
                   from `position`) is one the filter never saw: its card is
                   not auditable for B-DK-4..6.
  market_coerced   optional (#515): the str ids whose value the filter saw
                   as NaN or inf, recorded null. Breakup and filler read
                   such a value order-dependently, so a card holding one is
                   not auditable for them. B-DK-6 still checks it: a NaN
                   reads exactly as None there, and on a served card a
                   coerced +-inf (a holding the filter counted toward the
                   cap, or an incoming piece whose bar it made inf) can only
                   lower the audit's count below the filter's, so its
                   verdict can't flip. That holds for served cards only, the
                   ones audited (release-lead's #515 QA: mismatches on
                   dropped cards only).
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
  repeat_head      optional (trades-eng's v6): the trade_hashes of the cards
                   the repeat cap kept, written only when it kept fewer than
                   REPEAT_WINDOW (it ran short), else null. B-DK-7 below.
  give / receive   assets_json: served-time, str ids.
The deck's record state is counted in `filter_inputs`: recorded (the shape
above), record_failed (filter_ran true but no usable inputs: the writer's
recording failed or the record is malformed or another version),
pack_without_record (a pack written before #492), no_pack (live evidence:
pinned, opponent, intent, presentation-exempt and demo decks, and any deck
without a pack). Only a recorded deck's cards are audited for B-DK-4..6; on
the rest they are not auditable, never a pass. The valuation_json markets
are not read: approximate values can't certify a zero bar (D2 (c)).
B-DK-7 needs only the cards' ids, so it audits every Trades deck the filter
ran on (filter_not_run decks are skipped for every rule); a deck
without a record takes protection from its row: features_json likes_you,
standing_offer (the standing_offer_reason) and wildcard, and the
source_like_impression_id column, where UNRECORDED_PROTECTION (injected and
retest are never set, owner_published is set after the filter,
fatigue_retest is set but not frozen) reads unprotected: a violation on a
fatigue retest card is a false positive (check its trade_hash against
deck_suppressions.retest_trade_hash). A deck without a record is read on the
assumption the flag was on (live since FILTERS_LIVE_AT, D-207); a --since
before that adds a note.

What a PASS certifies (models-lead F3): zero violations among the
non-protected audit-set cards, and no non-protected card left unchecked. A
protected card is exempt with or without a record (the filter never checks
it), so the B-DK-4..6 exemptions are split by deck (protected_by_deck:
recorded / no_record) and printed, so a PASS resting on exemptions shows.
A serve-time cut (a never-delivered withdrawal: a disposition cut, or I-1's
drop at mode 2) can pull a deferred card into a deck's window. Every deck
with one inside its displayed first REPEAT_WINDOW lands in exactly one of
four buckets (models-lead G-b4), each counted in `after_cut`:
  audited_packed  a pack row: D3 re-capped it, and a breach there can be
                  explained by the response boundary (below);
  audited_rows    no pack, tiered rows (an S1b partial run, a lost or
                  in-flight pack): D3 didn't run, so a breach is a violation;
  live_evidence   no pack, untiered rows (intent, pinned, opponent decks):
                  not checked by B-DK-7, its window cards not auditable
                  (live_cut); F4's trigger, after_cut_not_checked, is this
                  bucket: n > 0 goes to head-eng;
  no_evidence     #535's decks (no rows, no pack), from the read's captured
                  log lines (--no-evidence-log; G3-a): eval can't see them,
                  so their cuts are unknown; None when no lines were given.

A card whose partner is a redaction token (contract.REDACTED_PARTNER_PREFIX,
the account-deletion scrub's) has unknown protection, and for B-DK-6 unknown
partner holdings: the scrub drops its trade_hash from
filter_inputs.protected and its partner's qb_te entry, and may clear its
row's likes_you (head-eng, 2026-10-29; models-lead G-a4, H1). So it is not
auditable for B-DK-4..6. For B-DK-7 its assets are known (assets_json isn't
scrubbed) and count toward the cap for every other card (H-a1); only its own
over-cap verdict is unknown. An asset whose only unprotected-or-unknown
over-cap copies are redacted cards is neither a violation nor explained (in
particular never "protected"): those cards are not auditable (redacted) and
their deck incomplete. Redacted audit-set cards are counted as
redacted_cards and printed with their share. Only the token marks a card,
never a hash (the partner-hash rule).

Why a card is unchecked (models-lead H-a2): every rule's not_auditable is
split by cause (not_auditable_by_cause: redacted, no_full_row,
no_filter_record, asset_not_recorded, market_coerced, live_cut), and
B-DK-7's incomplete_decks too (incomplete_decks_by_cause). An INCOMPLETE
read also prints "INCOMPLETE from redaction only: yes/no": yes when every
unchecked card of every rule that isn't PASS is redacted and no deck was
skipped (incomplete_from_redaction_only). Status and exit code don't change.

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
have stopped after a publication batch, unmarked). Those stay violations.
A recorded deck whose record carries repeat_head (below) needs no rows past
the window: its breach is explained as short_deck when every unprotected
over-cap appearance is a card the cap deferred (its trade_hash not in
repeat_head); a list naming one of them is a violation. On a packed deck a
breach is also explained by the response boundary (models-lead G-b1) when
every unprotected-or-unknown over-cap card has both proofs, from the pack's
deliveries and the deck's rows only: a recorded cut before it in build order
whose displayed slot is inside the window, and re-running the cap inside its
own response (with the earlier responses' displayed cards fixed and counted
first) leaving that response's order unchanged (_boundary). D3 never moves a
card out of its response, so that is a stretch D3 couldn't fix and the user
saw: a known residual, never folded silently into a PASS. A missing row, a
missing cut or no pack is a violation. All three are counted in `explained`,
split as explained_protected / explained_short_deck / explained_boundary,
with examples (`why`; boundary_examples, up to five, apart); boundary_decks
and packed_decks give G-b3's rate (above 1% of audited packed decks, (c) is
required before the launch-week freeze). A B-DK-7 PASS with a boundary n
above 0 says so in the report's first line (G-b2). A window card with no
full row is not auditable and its deck incomplete (a breach found there
still counts). The filter ran on
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
from bisect import bisect_left
from collections import Counter
from dataclasses import asdict, dataclass
from types import SimpleNamespace

from sqlalchemy import Integer, String, column, inspect, select, table

from backend.database import deck_impressions_table
from backend.eval.contract import REDACTED_PARTNER_PREFIX
from backend.deck_quality import (
    BREAKUP_MIN_RATIO, FILLER_FLOOR, FILLER_FRAC, PROTECTED_ATTRS, REDUNDANT_MIN_RATIO, REPEAT_CAP,
    REPEAT_WINDOW, _breakup, _filler, _redundant_side, _repeat_cap, is_protected, position_caps,
)
from backend.eval.data import (
    CALIBRATION_REFRESH, IN_FLIGHT, PACK_INTEGRITY, PACK_TABLE, PARTIAL_RUN_TIER,
    PARTNER_REDACTED, UPGRADE_MISS_OTHER, WITHDRAWAL_CONFLICT, WITHDRAWALS_TABLE, _json_dict,
    load_decks,
)
from backend.eval.flip_read import (
    _PACK_ROWS, FAIL, LIST_CAP, PASS, ReadOnlyViolation, _chunks, _iso, _Parser, _redact,
    _settled_as_of, parse_no_evidence_log, read_only_engine,
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
# A deck's never-delivered withdrawals (deck_card_withdrawals): F4 / G-b4's
# buckets and G-b1's proof.
_CUT_ROWS = table(WITHDRAWALS_TABLE, column("deck_job_id", String), column("card_index", Integer),
                  column("served_before", Integer), column("first_withdrawn_at", String))
# The protection attributes a served row records: card attribute -> features_json key.
_RECORDED_FEATURES = {"likes_you": "likes_you", "standing_offer_reason": "standing_offer",
                      "wildcard": "wildcard"}
UNRECORDED_PROTECTION = tuple(a for a in PROTECTED_ATTRS if a not in _RECORDED_FEATURES
                              and a != "source_like_impression_id")
# Why a card isn't checked (models-lead H-a2), per rule and for B-DK-7's decks.
REDACTED, NO_FULL_ROW, NO_FILTER_RECORD, ASSET_NOT_RECORDED, MARKET_COERCED, LIVE_CUT = (
    "redacted", "no_full_row", "no_filter_record", "asset_not_recorded", "market_coerced",
    "live_cut")
# G-b4: every deck with a never-delivered withdrawal in its displayed first
# REPEAT_WINDOW lands in exactly one of these (module doc).
CUT_BUCKETS = ("audited_packed", "audited_rows", "live_evidence", "no_evidence")
BOUNDARY_EXAMPLES = 5                    # G-b2
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
    redacted_cards: int = 0    # audit-set cards of a redacted partner (module doc)
    incomplete_from_redaction_only: bool = False   # H-a2 (module doc)


def audit(engine, *, since: str, as_of: str, until: str | None = None,
          no_evidence: dict | None = None) -> BdkAudit:
    """The B-DK-4..7 counts (module doc) for the Trades decks served in
    [since, until), at or before as_of. `no_evidence`: #535's decks as
    flip_read.parse_no_evidence_log reads the read's captured lines (None:
    none were given)."""
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

        def head_of(deck) -> set | None:
            """A recorded deck's repeat_head as a set (module doc), else None."""
            fi = records[deck.deck_job_id][1]
            head = fi.get("repeat_head") if fi is not None else None
            return set(head) if isinstance(head, list) else None

        w0 = _w0_by_deck(conn, [d.deck_job_id for d in trades], as_of)
        buckets = {d.deck_job_id: _cut_bucket(d, headers) for d in trades
                   if min(w0.get(d.deck_job_id, [REPEAT_WINDOW])) < REPEAT_WINDOW}
        repeat = _repeat(trades, sets, rows, lambda ids: _full_rows(conn, ids), headers,
                         protected_of, head_of, w0,
                         {job for job, b in buckets.items() if b == "live_evidence"})
    after_cut = {b: sum(1 for v in buckets.values() if v == b) for b in CUT_BUCKETS}
    after_cut["no_evidence"] = None if no_evidence is None else len(no_evidence)
    repeat["after_cut"] = after_cut
    repeat["after_cut_not_checked"] = after_cut["live_evidence"]     # F4's trigger (G-b4)
    repeat["packed_decks"] = sum(1 for d in trades if d.deck_job_id in headers)

    card_rules = {name: _tally() for name in ("breakup", "filler", "redundant")}
    no_row = {"viewed_by_cause": Counter(), "unviewed": 0, "examples": []}
    redacted = 0
    for d in trades:
        fi = records[d.deck_job_id][1]
        for c in cards[d.deck_job_id]:
            row = rows.get(c.impression_id)
            if row is None:                       # no full row: nothing to check it with
                for t in card_rules.values():
                    _unchecked(t, NO_FULL_ROW)
                if c.viewed:
                    cause = _miss_cards(headers.get(d.deck_job_id)).get(str(c.card_index),
                                                                         UPGRADE_MISS_OTHER)
                    no_row["viewed_by_cause"][cause] += 1
                    _example(no_row["examples"], {**_where(c), "cause": cause})
                else:
                    no_row["unviewed"] += 1
                continue
            give, receive, partner, _ = row
            if _scrubbed(row):                    # protection and holdings unknown
                redacted += 1
                for t in card_rules.values():
                    _unchecked(t, REDACTED)
                continue
            if protected_of(d, c, row):
                for t in card_rules.values():
                    t["protected"] += 1
                    t["protected_by_deck"]["recorded" if fi is not None else "no_record"] += 1
                continue
            if fi is None or give is None or not all(a in fi["market"] and a in fi["position"]
                                                     for a in (*give, *receive)):
                cause = (NO_FILTER_RECORD if fi is None else NO_FULL_ROW if give is None
                         else ASSET_NOT_RECORDED)
                for t in card_rules.values():   # no record, or an asset it never saw
                    _unchecked(t, cause)
                continue
            market, position, held = fi["market"].get, fi["position"].get, fi["qb_te"]
            caps = position_caps(fi["lineup_slots"])   # None: the filter skipped B-DK-6
            # #515: a value the filter saw as NaN/inf is recorded null; breakup and
            # filler read it order-dependently, so they can't be checked. B-DK-6 can
            # (module doc: a served card's verdict can't flip there).
            coerced = not set(fi.get("market_coerced", ())).isdisjoint((*give, *receive))
            if coerced:
                for name in ("breakup", "filler"):
                    _unchecked(card_rules[name], MARKET_COERCED)
            for name, violated in (
                    *(() if coerced else (("breakup", _breakup(give, receive, market)),
                                          ("filler", _filler(give, receive, market)))),
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
        t["not_auditable_by_cause"] = dict(sorted(t["not_auditable_by_cause"].items()))
    repeat["incomplete_decks_by_cause"] = dict(sorted(repeat["incomplete_decks_by_cause"].items()))
    no_row["viewed_by_cause"] = dict(sorted(no_row["viewed_by_cause"].items()))
    statuses = [t["status"] for t in rules.values()]
    overall = (FAIL if FAIL in statuses
               else PASS if not skipped and all(s == PASS for s in statuses) else INCOMPLETE)
    redaction_only = (overall == INCOMPLETE and not skipped and all(
        t["not_auditable"] == t["not_auditable_by_cause"].get(REDACTED, 0)
        for t in rules.values() if t["status"] != PASS))
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
        no_full_row=no_row, rules=rules, evidence=EVIDENCE, notes=notes, overall=overall,
        redacted_cards=redacted, incomplete_from_redaction_only=redaction_only)


def _audit_set(deck) -> tuple[list, list]:
    """(the first REPEAT_WINDOW non-ghost cards by displayed position, the
    viewed cards past them)."""
    shown = sorted((c for c in deck.cards if not c.is_ghost), key=lambda c: c.position)
    return shown[:REPEAT_WINDOW], [c for c in shown[REPEAT_WINDOW:] if c.viewed]


def _ids(side) -> list[str] | None:
    """An assets_json side as str ids; None when it isn't a list (the card
    is then not auditable, never a crash)."""
    return [str(a) for a in side] if isinstance(side, list) else None


def _scrubbed(row) -> bool:
    """Whether a full row's partner is a redaction token (module doc)."""
    return row[2].startswith(REDACTED_PARTNER_PREFIX)


def _checkable(row) -> bool:
    """Whether B-DK-7 can check a card from its full row: well-formed, its
    partner not redacted (module doc)."""
    return row is not None and row[0] is not None and not _scrubbed(row)


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


def _w0_by_deck(conn, run_ids: list[str], as_of: str) -> dict[str, list[int]]:
    """run_id -> the sorted card_indexes of its never-delivered withdrawals
    (served_before 0) first withdrawn by as_of: the serve-time cuts. The
    smallest is its displayed slot, so a deck has a cut inside its first
    REPEAT_WINDOW when its smallest index is below it (F4); the i-th smallest
    w sits at slot w - i (G-b1)."""
    if not run_ids or not inspect(conn).has_table(WITHDRAWALS_TABLE):
        return {}
    w, out = _CUT_ROWS, {}
    for chunk in _chunks(run_ids):
        for run_id, index in conn.execute(
                select(w.c.deck_job_id, w.c.card_index)
                .where(w.c.deck_job_id.in_(chunk), w.c.served_before == 0,
                       w.c.first_withdrawn_at <= as_of)):
            out.setdefault(run_id, []).append(index)
    return {run_id: sorted(set(idx)) for run_id, idx in out.items()}


def _cut_bucket(deck, headers: dict) -> str:
    """G-b4's bucket of a deck with a cut in its window (module doc): a pack
    row, else a tiered (deferred-evidence) row, else live evidence."""
    if deck.deck_job_id in headers:
        return "audited_packed"
    if any(c.evidence_tier is not None for c in deck.cards if not c.is_ghost):
        return "audited_rows"
    return "live_evidence"


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
    market, coerced = fi.get("market"), fi.get("market_coerced", [])
    if (fi.get("filter_ran") is True and isinstance(market, dict)
            and all(v is None or (isinstance(v, (int, float)) and not isinstance(v, bool))
                    for v in market.values())
            and isinstance(coerced, list) and all(isinstance(a, str) for a in coerced)
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
    `protected_of(deck, card, row)` is each card's protection (module doc).
    A redacted partner's card may read unprotected (the scrub may have
    removed its protection, never added one). That can only break the fixed
    point, never make one, so it needs no exclusion here."""
    if deck.exclusion not in (None, PARTNER_REDACTED) and not (
            packed and deck.exclusion == IN_FLIGHT):     # a redacted deck holds every card
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


def _boundary(deck, card, run: dict, cuts: list[int], rows, fetch, protected_of) -> bool:
    """models-lead G-b1: whether an over-cap card's breach is the response
    boundary's, proved from the pack's deliveries and the deck's rows
    (module doc). Both must hold: a recorded cut (`cuts`, sorted) before the
    card in build order whose displayed slot is inside the window; and
    re-running the cap inside the card's own response (its deliveries
    entry), with the earlier responses' displayed cards fixed and counted
    first, leaves that response's displayed order unchanged. A card the
    re-run needs with no well-formed full row, or a card in no delivery,
    fails the proof. Protection is protected_of's; a redacted card may read
    unprotected, which can only break the fixed point, never make one."""
    if not any(w < card.card_index and w - i < REPEAT_WINDOW for i, w in enumerate(cuts)):
        return False
    lasts = [entry[0] for entry in run.get("deliveries") or []]
    response = bisect_left(lasts, card.card_index)
    if response == len(lasts):
        return False
    shown = sorted((c for c in deck.cards if not c.is_ghost), key=lambda c: c.position)
    prior = [c for c in shown if bisect_left(lasts, c.card_index) < response][:REPEAT_WINDOW]
    own = [c for c in shown if bisect_left(lasts, c.card_index) == response]
    missing = [c.impression_id for c in prior + own if c.impression_id not in rows]
    if missing:
        rows.update(fetch(missing))

    def assets(c):
        row = rows.get(c.impression_id)
        return None if row is None or row[0] is None else (*row[0], *row[1])

    seen: Counter = Counter()
    for c in prior:
        if assets(c) is None:
            return False
        seen.update(assets(c))
    head, taken, deferred, tail = len(prior), [], [], []
    for c in own:
        if head >= REPEAT_WINDOW:
            tail.append(c)
            continue
        if assets(c) is None:
            return False
        if (not protected_of(deck, c, rows[c.impression_id])
                and any(seen[a] >= REPEAT_CAP for a in assets(c))):
            deferred.append(c)
            continue
        seen.update(assets(c))
        head += 1
        taken.append(c)
    return [id(c) for c in taken + deferred + tail] == [id(c) for c in own]


def _repeat(trades, sets, rows, fetch, packed: dict, protected_of, head_of, w0: dict,
            not_checked: set) -> dict:
    """B-DK-7 per deck over its window (module doc). `fetch(ids)` reads more
    full rows, for the short-deck and boundary checks; `packed` maps the
    run_ids with a pack to its run metadata; `protected_of(deck, card, row)`
    is a card's protection; `head_of(deck)` the trade_hashes of the cap's
    head when it ran short (repeat_head), else None; `w0` each deck's
    never-delivered withdrawal indexes (_w0_by_deck); `not_checked` the
    live-evidence decks with a cut in their window (G-b4), whose cards
    B-DK-7 doesn't check."""
    t = {"violations": 0, "explained": 0, "explained_protected": 0, "explained_short_deck": 0,
         "explained_boundary": 0, "boundary_decks": 0, "audited": 0, "not_auditable": 0,
         "not_auditable_by_cause": Counter(), "incomplete_decks": 0,
         "incomplete_decks_by_cause": Counter(), "examples": [], "explained_examples": [],
         "boundary_examples": []}
    for d in trades:
        window = sets[d.deck_job_id][0]
        if d.deck_job_id in not_checked:
            _unchecked(t, LIVE_CUT, len(window))
            t["incomplete_decks"] += bool(window)
            t["incomplete_decks_by_cause"][LIVE_CUT] += bool(window)
            continue
        causes: set[str] = set()
        seen: Counter = Counter()
        at: dict[str, list[int]] = {}
        over: dict[str, list] = {}         # asset -> (card, protected or None), per over-cap one
        for c in window:
            row = rows.get(c.impression_id)
            if row is None or row[0] is None:          # its assets are unknown
                _unchecked(t, NO_FULL_ROW)
                causes.add(NO_FULL_ROW)
                continue
            t["audited"] += 1
            # H-a1: a redacted card's assets count for every other card; only
            # its own protection (so its own over-cap verdict) is unknown.
            protected = None if _scrubbed(row) else protected_of(d, c, row)
            assets = (*row[0], *row[1])
            for a in assets:
                if seen[a] >= REPEAT_CAP:
                    over.setdefault(a, []).append((c, protected))
                at.setdefault(a, []).append(c.card_index)
            seen.update(assets)
        head = head_of(d)                  # the cap's short head (repeat_head), else None
        short = None                       # checked once per deck, only on a breach
        unknown: set[str] = set()          # redacted cards whose own verdict is unknown
        boundary = False                   # a breach here explained by the boundary
        for asset, apps in over.items():
            pending = [c for c, p in apps if p is not True]
            why = None if pending else "protected"
            if why is None and head is not None:   # every pending one was deferred
                why = "short_deck" if all(c.trade_hash not in head for c in pending) else None
            elif why is None:
                short = (_short_deck(d, rows, fetch, d.deck_job_id in packed, protected_of)
                         if short is None else short)
                why = "short_deck" if short else None
            if why is None and d.deck_job_id in packed and all(
                    _boundary(d, c, packed[d.deck_job_id], w0.get(d.deck_job_id, []), rows,
                              fetch, protected_of) for c in pending):
                why = "boundary"
            if why:
                t["explained"] += 1
                t[f"explained_{why}"] += 1
                boundary |= why == "boundary"
            elif any(p is False for _c, p in apps):    # a checkable, unprotected one
                t["violations"] += 1
            else:                                      # only redacted ones: unknown
                unknown.update(c.impression_id for c, p in apps if p is None)
                continue
            example = {
                "deck_job_id": d.deck_job_id, "asset": asset, "card_indexes": at[asset],
                "why": why, "over_cap_protected": [p for _c, p in apps],
                "ghost_slots": sum(1 for c in d.cards
                                   if c.is_ghost and c.card_index < REPEAT_WINDOW),
                "withdrawn_removed": d.withdrawn_removed}
            if why == "boundary":
                if len(t["boundary_examples"]) < BOUNDARY_EXAMPLES:
                    t["boundary_examples"].append(example)
            else:
                _example(t["explained_examples" if why else "examples"], example)
        t["boundary_decks"] += boundary
        if unknown:
            t["audited"] -= len(unknown)
            _unchecked(t, REDACTED, len(unknown))
            causes.add(REDACTED)
        t["incomplete_decks"] += bool(causes)
        for cause in causes:
            t["incomplete_decks_by_cause"][cause] += 1
    return t


def _tally() -> dict:
    return {"violations": 0, "audited": 0, "protected": 0, "not_auditable": 0,
            "not_auditable_by_cause": Counter(), "examples": [],
            "protected_by_deck": {"recorded": 0, "no_record": 0}}   # F3


def _unchecked(t: dict, cause: str, n: int = 1) -> None:
    """Count n cards a rule couldn't check, by cause (H-a2)."""
    t["not_auditable"] += n
    t["not_auditable_by_cause"][cause] += n


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


def _share(n: int, of: int) -> str:
    return f"{n / of:.1%}" if of else "n/a"


def render(r: BdkAudit) -> str:
    rp = r.rules["repeat"]
    lines = []
    if rp["status"] == PASS and rp["explained_boundary"]:       # G-b2: said first
        lines.append(f"B-DK-7 PASS with {rp['explained_boundary']} breaches explained by a "
                     f"response boundary on {rp['boundary_decks']} decks "
                     f"({_share(rp['boundary_decks'], rp['packed_decks'])} of audited packed "
                     "decks): a known residual the user saw, not a clean pass (models-lead G-b2).")
    lines += [
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
                          f"cards, {t['explained_short_deck']} by a short deck, "
                          f"{t['explained_boundary']} by a response boundary)")
        lines.append(f"| {t['bdk']} | {name}: {t['rule']} | {violations} | {t['audited']} | "
                     f"{t.get('protected', '-')} | {t['not_auditable']} | 0 | {t['status']} |")
    lines.append("")
    for name, t in r.rules.items():
        if t["status"] == NOT_AUDITABLE:
            lines.append(f"{t['bdk']} {name} is NOT AUDITABLE from evidence: "
                         f"{t['not_auditable']} cards couldn't be checked.")
    if rp["incomplete_decks"]:
        lines.append(f"B-DK-7 repeat: {rp['incomplete_decks']} decks have an unchecked window "
                     f"card, by cause: {_pairs(rp['incomplete_decks_by_cause'])}.")
    lines.append("Not auditable, by cause (models-lead H-a2): " + "; ".join(
        f"{t['bdk']} {name} {_pairs(t['not_auditable_by_cause'])}" for name, t in r.rules.items()))
    if r.overall == INCOMPLETE:
        lines.append("INCOMPLETE from redaction only: "
                     + ("yes" if r.incomplete_from_redaction_only else "no"))
    ac = rp["after_cut"]
    no_evidence = "not read (no --no-evidence-log)" if ac["no_evidence"] is None else ac[
        "no_evidence"]
    lines.append(
        f"B-DK-7 decks with a serve-time cut in their first {REPEAT_WINDOW} (models-lead G-b4): "
        f"audited, packed {ac['audited_packed']} (D3 re-caps them); audited from rows, no pack "
        f"{ac['audited_rows']} (S1b partial runs, lost or in-flight packs: D3 didn't run, so a "
        f"breach is a violation); not checked, live evidence {ac['live_evidence']} (F4: n > 0 "
        f"goes to head-eng); not checked, no rows and no pack {no_evidence} (#535's lines).")
    lines.append(
        f"B-DK-7 response boundary (models-lead G-b1): {rp['explained_boundary']} breaches on "
        f"{rp['boundary_decks']} decks, {_share(rp['boundary_decks'], rp['packed_decks'])} of "
        f"{rp['packed_decks']} audited packed decks (G-b3: above 1% makes (c) required before "
        "the launch-week freeze).")
    if rp["boundary_examples"]:
        lines.append("  " + "; ".join(
            f"{e['deck_job_id']} asset {e['asset']} at card_index "
            f"{', '.join(map(str, e['card_indexes']))}" for e in rp["boundary_examples"]))
    if r.redacted_cards:
        lines.append(f"Redacted partners (account deletion): {r.redacted_cards} of "
                     f"{r.audit_cards} audit-set cards ({_share(r.redacted_cards, r.audit_cards)})"
                     ". Not auditable for B-DK-4..6 (their protection and the partner's holdings"
                     " were scrubbed); for B-DK-7 their copies count, and only their own "
                     "over-cap verdicts are unknown (models-lead H-a1).")
    pd = r.rules["breakup"]["protected_by_deck"]
    lines.append(f"B-DK-4..6 exempt (protected) cards by deck (F3): recorded {pd['recorded']}, "
                 f"no record {pd['no_record']}.")
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
    ap.add_argument("--no-evidence-log",
                    help="a text file of the read's captured #535 log lines ('deck-evidence "
                         "<deck_job_id>: n delivered cards of a deck with no evidence'), for "
                         "G-b4's no-rows-no-pack bucket (models-lead G3-a)")
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
    no_evidence = None
    if args.no_evidence_log:
        with open(args.no_evidence_log, encoding="utf-8") as fh:
            no_evidence = parse_no_evidence_log(fh.read())
    try:
        result = audit(eng, since=args.since, as_of=as_of, until=args.until,
                       no_evidence=no_evidence)
    except ReadOnlyViolation as e:
        print(f"bdk_audit: {_redact(str(e), args.db)}", file=sys.stderr)
        return 2
    finally:
        eng.dispose()
    print(json.dumps(asdict(result), indent=2, sort_keys=True) if args.json else render(result))
    return EXIT[result.overall]


if __name__ == "__main__":
    sys.exit(main())
