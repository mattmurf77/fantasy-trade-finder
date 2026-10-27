"""The B-DK-4..7 production audit (models-lead-launch.md addendum C §C5; the
bars in models-lead-wave2.md B-DK-4..7, D-207): served violations of
deck.quality_filters' four rules (backend/deck_quality.py), against a bar of
0. Read-only. models-eng runs it on the post-flip window, then weekly with
the readout.

    python3 -m backend.eval.bdk_audit --db URL --since ISO [--until ISO]
        [--as-of ISO] [--allow-postgres-readonly] [--json]

  B-DK-4  breakup     deck_quality._breakup, per card
  B-DK-5  filler      deck_quality._filler, per card
  B-DK-6  redundant   deck_quality._redundant_side: not auditable (below)
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
displayed position (LoggedCard.position), plus every viewed card, "viewed"
being a `viewed` outcome joined by impression_id (LoggedCard.viewed), never a
row's existence (U4-R3). assets_json, valuation_json, features_json and
source_like_impression_id are read for those impression_ids, chunked.

A card with no full row (no deck_impressions row with assets_json: a packed
card, or the upgrade miss's row built from the pack) can't be audited. A
viewed one is reported by cause (U4-R3), read from its pack's run metadata
upgrade_miss_cards ({"<card_index>": cause}); no pack or no entry is `other`.
It counts as not auditable for every rule, as does an unviewed one.

The rule inputs, and what the evidence records at serve time:
  give / receive   assets_json: served-time.
  market values    valuation_json's per-asset market: the personal-market
                   snapshot (assets.give / assets.receive rows, market_value)
                   or the value core's evidence (assets rows, market), read
                   by data.valuation_markets (blind_grade's parser too).
                   Served-time but approximate: the filter priced assets with
                   elo_to_value(seed Elo), None when unseeded; the snapshot's
                   market_value is that age-adjusted (age_pref_value), and an
                   unseeded asset reads a default. NULL while
                   trade.valuation_telemetry and the market policy are off;
                   then breakup and filler are not auditable for the card.
  protection       features_json likes_you, standing_offer (the
                   standing_offer_reason) and wildcard, and the
                   source_like_impression_id column: served-time. Not recorded:
                   UNRECORDED_PROTECTION (injected and retest are never set,
                   owner_published is set after the filter, fatigue_retest is
                   set but not frozen), so a fatigue retest card reads
                   unprotected: a violation on one is a false positive (check
                   its trade_hash against deck_suppressions.retest_trade_hash).
  positions        features_json give_positions / receive_positions:
                   served-time.
  rosters, lineup  not recorded at serve time (the rosters are current-state
                   tables; a Sleeper league's lineup template is live league
                   meta, in no table). B-DK-6 is NOT AUDITABLE from evidence:
                   its count is the non-protected cards it couldn't check.
  the filter flag  not recorded per deck (features_json carries nothing; the
                   counts in significance_diag exist only with significance
                   capture on). The window is read whole, on the assumption
                   the flag was on (config/features.json true; live since
                   FILTERS_LIVE_AT, D-207); a --since before that adds a note.

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
deck whose cards are a prefix of what was displayed (any loader exclusion,
e.g. in_flight or a lost pack's incomplete_deck, or a partial_run deck) never
qualifies, else it stays a violation. Both are counted in `explained`, split as
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
     (B-DK-6 never can) or a deck was skipped: not a pass;
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
import math
import sys
import traceback
from collections import Counter
from dataclasses import asdict, dataclass
from types import SimpleNamespace

from sqlalchemy import inspect, select

from backend.database import deck_impressions_table
from backend.deck_quality import (
    BREAKUP_MIN_RATIO, FILLER_FLOOR, FILLER_FRAC, PROTECTED_ATTRS, REDUNDANT_MIN_RATIO, REPEAT_CAP,
    REPEAT_WINDOW, _breakup, _filler, _repeat_cap, is_protected,
)
from backend.eval.data import (
    CALIBRATION_REFRESH, PACK_INTEGRITY, PACK_TABLE, PARTIAL_RUN_TIER, UPGRADE_MISS_OTHER,
    WITHDRAWAL_CONFLICT, _json_dict, load_decks, valuation_markets,
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
    "market": "valuation_json per-asset market (served-time, approximate: age-adjusted "
              "consensus, not the filter's elo_to_value(seed)); absent: breakup and filler "
              "not auditable for the card",
    "protection": "features_json likes_you / standing_offer / wildcard and the "
                  "source_like_impression_id column (served-time); not recorded: "
                  + ", ".join(UNRECORDED_PROTECTION) + " (a fatigue retest card reads "
                  "unprotected: a violation on one is a false positive)",
    "positions": "features_json give_positions / receive_positions (served-time)",
    "rosters_lineup": "not recorded at serve time: redundant (B-DK-6) is not auditable",
    "filter_flag": "not recorded per deck: the window is read whole, assuming "
                   f"deck.quality_filters on (config/features.json; live since "
                   f"{FILTERS_LIVE_AT})",
}


@dataclass
class BdkAudit:
    since: str
    until: str | None
    as_of: str
    decks: int                 # Trades decks audited
    skipped_decks: dict        # PACK_INTEGRITY / WITHDRAWAL_CONFLICT -> decks
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
    trades = [d for d in decks if d.exclusion not in (CALIBRATION_REFRESH, *_UNTRUSTED)]
    sets = {d.deck_job_id: _audit_set(d) for d in trades}
    cards = {job: window + past for job, (window, past) in sets.items()}
    with engine.connect() as conn:
        rows = _full_rows(conn, [c.impression_id for cs in cards.values() for c in cs])
        misses = _miss_cards(conn, sorted(
            job for job, cs in cards.items()
            if any(c.viewed and c.impression_id not in rows for c in cs)))
        repeat = _repeat(trades, sets, rows, lambda ids: _full_rows(conn, ids))

    card_rules = {name: _tally() for name in ("breakup", "filler", "redundant")}
    no_row = {"viewed_by_cause": Counter(), "unviewed": 0, "examples": []}
    for d in trades:
        for c in cards[d.deck_job_id]:
            row = rows.get(c.impression_id)
            if row is None:                       # no full row: nothing to check it with
                for t in card_rules.values():
                    t["not_auditable"] += 1
                if c.viewed:
                    cause = misses.get(d.deck_job_id, {}).get(str(c.card_index),
                                                              UPGRADE_MISS_OTHER)
                    no_row["viewed_by_cause"][cause] += 1
                    _example(no_row["examples"], {**_where(c), "cause": cause})
                else:
                    no_row["unviewed"] += 1
                continue
            give, receive, markets, protected, _ = row
            if protected:
                for t in card_rules.values():
                    t["protected"] += 1
                continue
            card_rules["redundant"]["not_auditable"] += 1   # no served-time rosters / lineup
            if give is None or not all(_is_market(markets.get(a)) for a in (*give, *receive)):
                card_rules["breakup"]["not_auditable"] += 1
                card_rules["filler"]["not_auditable"] += 1
                continue
            for name, rule in (("breakup", _breakup), ("filler", _filler)):
                t = card_rules[name]
                t["audited"] += 1
                if rule(give, receive, markets.get):
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
        audit_cards=sum(len(cs) for cs in cards.values()),
        viewed_past_window=sum(len(p) for _w, p in sets.values()),
        no_full_row=no_row, rules=rules, evidence=EVIDENCE, notes=notes, overall=overall)


def _audit_set(deck) -> tuple[list, list]:
    """(the first REPEAT_WINDOW non-ghost cards by displayed position, the
    viewed cards past them)."""
    shown = sorted((c for c in deck.cards if not c.is_ghost), key=lambda c: c.position)
    return shown[:REPEAT_WINDOW], [c for c in shown[REPEAT_WINDOW:] if c.viewed]


def _is_market(value) -> bool:
    """A usable served market: a finite number (a missing, null or string
    market makes its card not auditable for the value rules, never a pass)."""
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _ids(side) -> list[str] | None:
    """An assets_json side as str ids; None when it isn't a list (the card
    is then not auditable, never a crash)."""
    return [str(a) for a in side] if isinstance(side, list) else None


def _full_rows(conn, ids: list[str]) -> dict[str, tuple]:
    """impression_id -> (give, receive, markets, protected, card) for each
    id with a full row (assets_json), read chunked. give and receive are None
    when either side is missing, empty or not a list; markets is {} when none is recorded;
    `card` carries the ids and the protection attributes, for
    deck_quality._repeat_cap."""
    imp = deck_impressions_table
    out: dict[str, tuple] = {}
    for chunk in _chunks(ids):
        for r in conn.execute(select(imp.c.impression_id, imp.c.assets_json,
                                     imp.c.valuation_json, imp.c.features_json,
                                     imp.c.source_like_impression_id)
                              .where(imp.c.impression_id.in_(chunk))):
            assets = _json_dict(r.assets_json)
            if assets is None:
                continue
            features = _json_dict(r.features_json) or {}
            give, receive = _ids(assets.get("give")), _ids(assets.get("receive"))
            if not give or not receive:           # missing, not a list, or empty: unusable
                give = receive = None
            card = SimpleNamespace(source_like_impression_id=r.source_like_impression_id,
                                   give_player_ids=give or [], receive_player_ids=receive or [],
                                   **{a: features.get(k) for a, k in _RECORDED_FEATURES.items()})
            out[r.impression_id] = (give, receive,
                                    valuation_markets(_json_dict(r.valuation_json)),
                                    is_protected(card), card)
    return out


def _miss_cards(conn, run_ids: list[str]) -> dict[str, dict]:
    """run_id -> its pack's run["upgrade_miss_cards"] ({} when absent or
    unreadable), for the runs with a pack row."""
    if not run_ids or not inspect(conn).has_table(PACK_TABLE):
        return {}
    out: dict[str, dict] = {}
    for chunk in _chunks(run_ids):
        for run_id, header in conn.execute(select(_PACK_ROWS.c.run_id, _PACK_ROWS.c.header_json)
                                           .where(_PACK_ROWS.c.run_id.in_(chunk))):
            run = (_json_dict(header) or {}).get("run")
            cards = run.get("upgrade_miss_cards") if isinstance(run, dict) else None
            out[run_id] = cards if isinstance(cards, dict) else {}
    return out


def _short_deck(deck, rows, fetch) -> bool:
    """Whether the deck's whole displayed order is a fixed point of
    deck_quality._repeat_cap (module doc): False when any displayed card has
    no well-formed full row, and for a deck whose cards are only a prefix of
    what was displayed: one with a loader exclusion (in_flight, or a lost
    pack's incomplete_deck: the first REPEAT_WINDOW and viewed rows) or a partial_run
    deck (its delivered rows), where an over-cap card at the prefix's end
    would read as deferred (#469 QA P1-1). Rows the window didn't need are
    fetched and added to `rows`."""
    if deck.exclusion is not None or any(c.evidence_tier == PARTIAL_RUN_TIER
                                         for c in deck.cards):
        return False
    shown = sorted((c for c in deck.cards if not c.is_ghost), key=lambda c: c.position)
    missing = [c.impression_id for c in shown if c.impression_id not in rows]
    if missing:
        rows.update(fetch(missing))
    served = [rows.get(c.impression_id) for c in shown]
    if any(row is None or row[0] is None for row in served):
        return False
    cards = [row[4] for row in served]
    return [id(c) for c in _repeat_cap(cards)[0]] == [id(c) for c in cards]


def _repeat(trades, sets, rows, fetch) -> dict:
    """B-DK-7 per deck over its window (module doc). `fetch(ids)` reads more
    full rows, for the short-deck check."""
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
            give, receive, _, protected, _ = row
            assets = (*give, *receive)
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
                short = _short_deck(d, rows, fetch) if short is None else short
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
    nf = r.no_full_row
    lines.append(f"Viewed, no full row (U4-R3), by cause: {_pairs(nf['viewed_by_cause'])}; "
                 f"unviewed audit-set cards with no full row: {nf['unviewed']}")
    if nf["examples"]:
        lines.append("  " + ", ".join(f"{e['deck_job_id']}#{e['card_index']} ({e['cause']})"
                                      for e in nf["examples"]))
    if r.skipped_decks:
        lines.append(f"Skipped decks (displayed positions untrustworthy; G1 / G8 signals): "
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
