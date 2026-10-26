"""F8 — load the F1 impression spine into replayable structures.

Read-only. One LoggedDeck per deck_job_id, cards in served order
(card_index), each card carrying its frozen features_json plus aggregated
outcome flags from deck_outcomes (append-only labels: any number of rows
per impression is legal — we reduce to booleans here).

Narrow rows (C7 (i) scaffolding): a card may carry only a frozen compact
scorer-input block (backend/eval/contract.py) instead of features_json.
It is read from a `features_compact` column when the live table has one
(the DB's own columns, inspected per read, never the code's table
metadata: an unmigrated DB lacks what the metadata may declare, and a DB
column the metadata lacks is still read); without that column, every
card's features_compact is None. The same holds for `evidence_tier`
(replay and calibration exclude 'partial_run'; every other tier,
ghost/first30/delivered/viewed/archive/full_interim, is a usable row) and for
`delivered_at` (ISO UTC, NULL while undelivered; the paging rule below).

Packed cards (ADR-025 C1, C7 (i)): when the engine has a deck_evidence_packs
table, each pack in the window is unpacked (backend/eval/evidence_pack.py)
and merged into its deck: a deck's cards are its rows ∪ its unpacked cards,
in card_index order, and a non-ghost row wins over a packed card with the
same card_index. Every non-ghost card's impression_id is
contract.card_impression_id(run_id, card_index) (R4.2 U2): a packed card
gets it here, the writer gives it to rows, and the client posts outcomes
with it, so outcomes join a packed card exactly as they join an upgraded
row. Ghost rows (C5) are never packed and never displace a packed card.

Delivery (R4.2 U1): in a deck with a pack, a card is delivered when it is
not a ghost and its card_index is within the pack's run["deliveries"]; the
exposure model counts delivered positions only. The legacy rule (models-lead
R5.2 (d)): a deck without a pack, from before paging, delivered every served
card, so delivered = served at every position, as e(k) always counted it.
Paging defense in depth (models-lead R2.4 addendum §3): a deck is MARKED
when a non-ghost row's features_json or compact block (before the
projection trim) has PAGE_STORE_MARKER == 1, a non-ghost row has a non-NULL
evidence_tier, or its pack's run metadata has PAGE_STORE_MARKER == 1. The
legacy rule applies only to an unmarked deck, or to one served before
PAGING_RELEASED_AT when that is set (None: marker-only, so a marked deck is
never legacy). A marked deck without a pack takes delivered from its rows:
a non-ghost row whose delivered_at is at or before as_of (any non-NULL one
without as_of). A marked deck with a pack takes it from deliveries, as
above. In a marked or packed deck, an outcome on a card the evidence says
was not delivered means the deliveries are under-recorded.

In-flight packs (models-eng): the pack row is written at the deck's first
delivery and its header updated on later ones, so its run metadata may
carry "retired" (bool) and "retired_at" (ISO UTC). A pack without the
"retired" key was written at retirement and is final. One with it: with
as_of, only deliveries entries with delivered_at <= as_of count (the last
delivered index is recomputed from them, so a re-read at the same as_of is
the same after the row is updated), and the pack is final iff it retired
at or before as_of, or its served_at is older than as_of - IN_FLIGHT_WINDOW;
without as_of, iff retired is true. A pack that is not final makes its
deck in_flight. Outcome consistency, every packed deck: an outcome (as
read) on a kept non-ghost card past the last delivered index means the
deliveries are under-recorded (outcomes only come from delivered cards),
and the deck is incomplete_deck.

Serve-time withdrawals (models-lead R2.4 addendum §2): when the engine has a
deck_card_withdrawals table, its rows for the loaded decks are read (with
as_of, only those first withdrawn at or before it). The writer's contract:
a served_before=1 card (delivered by an earlier response) keeps its row or
packed card; the pack's card_count is the build N; every index is a build
index. A served_before=0 card (W0: never delivered) may still be present,
as a packed card (cards_blob holds every built card) or a first30 row with
delivered_at NULL (the first 30 rows are written at first delivery). Ghost
rows are ignored by every withdrawal rule (a ghost's card_index is a
would-have-been rank). A W0 index is removed from the deck for eval: its
card, when present, is dropped, so it is never scored, exposed or ranked,
and the index explains the gap there (LoggedDeck.withdrawn_removed counts
them). A served_before=1 index changes nothing: its card keeps its
position and outcomes, and an absent one is an unexplained gap.
LoggedCard.position is the displayed position, the card's dense rank among
the deck's kept non-ghost cards (card_index minus the W0 indexes below it);
with no withdrawals it is card_index. The reason column ('i1_dropped',
'disposition_cut', ...) is read only to count: LoggedDeck.
withdrawn_removed_by_reason splits the W0 removals by it (models-lead B4).
No rule gates on it.

Upgrade misses (models-lead U4-R2): a pack's run metadata may carry
"upgrade_misses", the writer's count of viewed cards that never got a full
row, as a dict of cause -> int. "other" is the only cause that must be 0;
every other key is a named cause (restart_split, U4-R1). A legacy int n is
read as {"other": n} (conservative: it flags), a missing key as {}.
LoggedDeck.upgrade_misses holds it, sorted ({} without a readable pack).
Reporting only: no rule reads it.

LoggedDeck.exclusion, per deck, in this precedence: replay excludes the
deck whole and never sinks it; calibration excludes its cards.
  calibration_refresh
                   a card's features_json (or compact block), or its pack's
                   run metadata, carries
                   deck_source CALIBRATION_REFRESH_SOURCE: Calibration's
                   targeted refresh built the deck (ADR-025 S4), and it is
                   never shown in Trades, so replay, e(k) and calibration
                   leave it out. It takes precedence over every reason
                   below: a refresh deck keeps full rows at build and is
                   never packed, so from PACK_REQUIRED_SINCE on it would
                   otherwise read as in_flight or incomplete_deck (a lost
                   pack). Refresh decks built before #370's relabel carry
                   deck_source 'replenish', can't be told apart, and stay in.
  pack_integrity   unpack_run refuses the pack (unreadable, unknown version,
                   checksum mismatch, row fields disagreeing with its
                   header, malformed deliveries), or it holds another run's
                   cards; its cards are not merged
  withdrawal_conflict
                   the withdrawal disagrees with the evidence: a
                   served_before=0 index's card has a non-NULL
                   delivered_at or an outcome (the user got it), or a
                   served_before=1 index is past the pack's deliveries as
                   of the read, or (a paged deck) its row was not
                   delivered by then; or a withdrawal's index is outside
                   0..N-1 (N as for incomplete_deck): the writer's
                   contract is broken
  in_flight        the deck's pack is not final yet (in-flight packs, above);
                   or a deferred-evidence deck (tiered rows) served
                   at/after PACK_REQUIRED_SINCE has no pack yet and may
                   still be live (served within IN_FLIGHT_WINDOW
                   of as_of). Not an error; without as_of the reader can't
                   tell a pack-less deck is live, and it is incomplete_deck.
  incomplete_deck  the non-ghost card indexes ∪ the served_before=0 indexes
                   are not exactly 0..N-1, where N is the pack's card_count,
                   or without a pack max(the card indexes ∪ every
                   withdrawal index)+1; or a packed or paged deck has an
                   outcome on a card not delivered as of the read (past
                   the pack's last delivered index, or a row with no
                   delivered_at by then); or a deferred-evidence deck
                   (tiered rows) served at/after PACK_REQUIRED_SINCE has no
                   pack and is past IN_FLIGHT_WINDOW (a lost pack)
  no_delivery_evidence
                   a marked deck without a pack (paging, above) whose live
                   table lacks delivered_at, or none of whose non-ghost rows
                   has one: nothing says which cards were delivered

Lean load: only the columns eval reads are selected, and
project_features=True (the nightly) also trims each parsed features dict
to the keys some registered scorer may read (contract.PROJECTION_KEYS).

Engine resolution: pass an explicit SQLAlchemy engine (tests), or a
db_url (CLI --db), or neither — in which case backend.database.engine is
used, read at call time so test patches of backend.database.engine are
honored (same idiom as the product loaders).
"""

from __future__ import annotations

import json
from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import (
    Integer, LargeBinary, String, Text, column, create_engine, func, inspect, select, table,
)

from backend.database import deck_impressions_table, deck_outcomes_table
from backend.eval import evidence_pack
from backend.eval.contract import PROJECTION_KEYS, card_impression_id

# The deck_impressions columns eval reads (never select(imp): valuation_json,
# assets_json and the rest are large and unused here).
EVAL_COLUMNS = (
    "impression_id", "user_id", "league_id", "deck_job_id", "card_index",
    "trade_hash", "features_json", "propensity", "base_score", "final_score",
    "archetype", "shape_bucket", "served_at", "is_ghost",
)
# Read only when the live table has them (inspected per read, not taken from
# the code's table metadata; module docstring).
OPTIONAL_COLUMNS = ("features_compact", "evidence_tier", "delivered_at")
# evidence_tier written on a partial run's delivered rows (head-eng ruling 21):
# replay excludes the deck, calibration the card.
PARTIAL_RUN_TIER = "partial_run"

# The pack table (ADR-025 C1; trades-eng builds it, the row contract is in
# docs/plans/trade-time-to-suggestion/eng-evidence-contract.md §6). Read only
# when the engine has it: a missing table means no packs.
PACK_TABLE = "deck_evidence_packs"
_PACKS = table(
    PACK_TABLE,
    column("run_id", String), column("user_id", String), column("league_id", String),
    column("served_at", String), column("pack_version", Integer),
    column("header_json", Text), column("cards_blob", LargeBinary),
    column("checksum", String), column("card_count", Integer),
)
# The deck_source a card of Calibration's targeted refresh deck carries in its
# features_json (ADR-025 S4: #370's server._pregenerate_grading_targets builds
# it through _replenish_deck_for(..., source="grading_refresh")).
CALIBRATION_REFRESH_SOURCE = "grading_refresh"
# Serve-time withdrawals (models-lead R2.4 addendum §2; trades-eng writes one
# row per card withdrawn at serve time on the page-store path: I-1's
# 'i1_dropped', the disposition cut's 'disposition_cut'). Read only when the
# engine has it, and only these columns: `reason` is only counted (B4), and
# eval never gates on it.
WITHDRAWALS_TABLE = "deck_card_withdrawals"
_WITHDRAWALS = table(
    WITHDRAWALS_TABLE,
    column("deck_job_id", String), column("card_index", Integer),
    column("served_before", Integer), column("first_withdrawn_at", String),
    column("reason", String),
)
# LoggedDeck.exclusion values (also replay's exclusion reasons).
CALIBRATION_REFRESH = "calibration_refresh"
PACK_INTEGRITY = "pack_integrity"
WITHDRAWAL_CONFLICT = "withdrawal_conflict"
INCOMPLETE_DECK = "incomplete_deck"
IN_FLIGHT = "in_flight"
NO_DELIVERY_EVIDENCE = "no_delivery_evidence"
# The paging marker (module doc): a card's features_json / compact block, or a
# pack's run metadata, with this key == 1 is from the page-store path.
PAGE_STORE_MARKER = "page_store"
# Decks served before this ISO UTC time keep the legacy rule even when marked.
# None: marker-only, so a marked deck is never legacy. That is the strictest
# setting and stays so through the flip (models-eng, 2026-10-26): marked decks
# exist only after trade.first_page_store is on, so a release time would only
# add a way for a mis-dated deck to be read as legacy.
PAGING_RELEASED_AT: str | None = None
# Lost-pack detection: a deferred-evidence deck (a non-ghost row with a
# non-NULL evidence_tier other than 'partial_run') served at or after this ISO
# UTC time must have a pack row (#416 packs every one). A partial run is never
# packed and stays partial_run in replay. Decks without tiered rows (flag-off, live
# evidence: the value core, prepared adoption, Calibration's refresh) are never
# packed and never required to be. Tiered decks exist only once
# trade.packed_evidence and trade.first_page_store are on together, so any
# instant before that flip is safe (models-eng, 2026-10-26: set ahead of it, so
# the flip has no eval-side constant to set).
PACK_REQUIRED_SINCE: str | None = "2026-10-27T00:00:00+00:00"
# A deck's pack is written when it retires (superseded, or the 24 h display
# cap, PRD #339 §5.1); 1 h more for the write.
IN_FLIGHT_WINDOW = timedelta(hours=25)
# The one upgrade-miss cause that must be 0 (U4-R2; module doc); every other
# key of run["upgrade_misses"] is a named cause.
UPGRADE_MISS_OTHER = "other"
# The LoggedCard fields a packed card takes from its unpacked dict; every other
# unpacked key goes into its features_compact.
_PACKED_LOGGED = (
    "deck_job_id", "user_id", "league_id", "card_index", "trade_hash", "propensity",
    "base_score", "final_score", "archetype", "shape_bucket", "served_at",
)


@dataclass
class LoggedCard:
    impression_id: str
    deck_job_id: str
    user_id: str
    league_id: str
    card_index: int
    trade_hash: str | None
    propensity: float | None
    base_score: float | None
    final_score: float | None
    archetype: str | None
    shape_bucket: str | None
    served_at: str
    features: dict | None          # None ⇔ features_json missing/unparseable
    features_compact: dict | None = None   # frozen compact block (narrow rows, packed cards)
    evidence_tier: str | None = None       # e.g. 'partial_run' (column pending)
    is_ghost: bool = False                 # a withheld ghost row (C5): never packed
    delivered: bool = True                 # sent to a client (R4.2 U1; module doc)
    delivered_at: str | None = None        # the row's first delivery (paging; module doc)
    # The displayed position (module doc); None at construction means card_index.
    position: int | None = None
    # Aggregated outcome flags (deck_outcomes reduce)
    viewed: bool = False
    liked: bool = False
    passed: bool = False
    proposed: bool = False
    not_interested: bool = False
    undone: bool = False
    dwell_ms: int | None = None    # max dwell across outcome rows

    def __post_init__(self):
        if self.position is None:
            self.position = self.card_index


@dataclass
class LoggedDeck:
    deck_job_id: str
    user_id: str
    league_id: str
    served_at: str
    cards: list[LoggedCard] = field(default_factory=list)
    # None, or CALIBRATION_REFRESH / PACK_INTEGRITY / WITHDRAWAL_CONFLICT /
    # IN_FLIGHT / INCOMPLETE_DECK / NO_DELIVERY_EVIDENCE (module doc).
    exclusion: str | None = None
    # served_before=0 withdrawals removed from the deck (module doc): not an
    # exclusion, but counted (replay's EvalRun.withdrawn_removed_cards).
    withdrawn_removed: int = 0
    # The same removals by deck_card_withdrawals.reason, sorted (B4).
    withdrawn_removed_by_reason: dict[str, int] = field(default_factory=dict)
    # The pack's upgrade misses, cause -> count, sorted (U4-R2; module doc);
    # {} without a readable pack.
    upgrade_misses: dict[str, int] = field(default_factory=dict)


def resolve_engine(engine=None, db_url: str | None = None):
    """Explicit engine > db_url > backend.database.engine (read late so
    test patches apply)."""
    if engine is not None:
        return engine
    if db_url:
        connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
        return create_engine(db_url, future=True, connect_args=connect_args)
    import backend.database as db_module
    return db_module.engine


def card_dict(card: LoggedCard) -> dict:
    """The dict handed to a Scorer: frozen features (features_json when
    present, else the compact block) merged with logged fields. Baseline
    scorers legitimately read `final_score` / `card_index`; honest
    CANDIDATE scorers must not touch `card_index`, `final_score`, or
    `propensity` — those encode the logged policy (backend/eval/contract.py
    declares what each scorer may read). Logged fields win key collisions
    (they are ground truth)."""
    frozen = card.features if card.features is not None else card.features_compact
    d = dict(frozen or {})
    d.update({
        "impression_id": card.impression_id,
        "deck_job_id":   card.deck_job_id,
        "user_id":       card.user_id,
        "league_id":     card.league_id,
        "card_index":    card.card_index,
        "trade_hash":    card.trade_hash,
        "propensity":    card.propensity,
        "base_score":    card.base_score,
        "final_score":   card.final_score,
        "archetype":     card.archetype,
        "shape_bucket":  card.shape_bucket,
        "served_at":     card.served_at,
    })
    return d


def _json_dict(raw) -> dict | None:
    """A JSON object column → dict; None when missing, unparseable, or not
    an object."""
    try:
        value = json.loads(raw) if raw else None
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def load_decks(
    engine=None,
    db_url: str | None = None,
    since: str | None = None,      # ISO — served_at >= since
    until: str | None = None,      # ISO — served_at <  until
    user_id: str | None = None,
    league_id: str | None = None,
    project_features: bool = False,
    as_of: str | None = None,      # ISO UTC — the read's clock
) -> list[LoggedDeck]:
    """Load deck_impressions (+reduced outcomes) as LoggedDecks, time-ordered
    by served_at then deck_job_id. ISO-8601 UTC strings compare lexically,
    matching the storage format everywhere in this schema. Packs in the same
    window (deck_evidence_packs.served_at, user_id, league_id) are merged
    into their decks (module docstring); a card is ordered by card_index,
    a non-ghost card before a ghost row at the same index.

    `as_of` is the read's explicit clock (the loader reads no wall clock):
    only decks served at or before it, outcomes acted at or before it
    (deck_outcomes.acted_at), withdrawals first withdrawn at or before it
    (deck_card_withdrawals.first_withdrawn_at), and an in-flight-capable
    pack's deliveries made at or before it, are read, so a re-read at the
    same as_of is the same however many outcomes, withdrawals or deliveries
    arrive later (models-lead R5.2 (b)); and the in_flight rules measure
    from it. Choosing as_of so labels are
    complete (a settle lag) is the caller's job: replay.settled_read.

    project_features=True keeps only contract.PROJECTION_KEYS inside each
    parsed features dict (and each packed card's features_compact): every
    registered scorer, and value_model's training path, scores the
    projected decks identically."""
    eng = resolve_engine(engine, db_url)

    imp = deck_impressions_table
    with eng.connect() as conn:
        # An optional column is selected iff the live table has it; one the
        # code's metadata lacks is still read, by name.
        live = {c["name"] for c in inspect(conn).get_columns(imp.name)}
        cols = [imp.c[name] for name in EVAL_COLUMNS]
        cols += [imp.c[name] if name in imp.c else column(name, Text)
                 for name in OPTIONAL_COLUMNS if name in live]
        q = select(*cols).order_by(imp.c.served_at, imp.c.deck_job_id, imp.c.card_index)
        if since:
            q = q.where(imp.c.served_at >= since)
        if until:
            q = q.where(imp.c.served_at < until)
        if as_of:
            q = q.where(imp.c.served_at <= as_of)
        if user_id:
            q = q.where(imp.c.user_id == user_id)
        if league_id:
            q = q.where(imp.c.league_id == league_id)
        rows = conn.execute(q).fetchall()
        packs = []
        if inspect(conn).has_table(PACK_TABLE):
            pq = select(_PACKS)
            if since:
                pq = pq.where(_PACKS.c.served_at >= since)
            if until:
                pq = pq.where(_PACKS.c.served_at < until)
            if as_of:
                pq = pq.where(_PACKS.c.served_at <= as_of)
            if user_id:
                pq = pq.where(_PACKS.c.user_id == user_id)
            if league_id:
                pq = pq.where(_PACKS.c.league_id == league_id)
            packs = conn.execute(pq).fetchall()
        unpacked = {p.run_id: _unpack(p) for p in packs}   # None: pack_integrity
        imp_ids = list(dict.fromkeys(
            [r.impression_id for r in rows]
            + [card_impression_id(run_id, u["card_index"])
               for run_id, got in unpacked.items() if got for u in got[2]]))
        outcomes: dict[str, list] = {}
        if imp_ids:
            # Chunk the IN() to stay under SQLite's parameter cap.
            out = deck_outcomes_table
            for i in range(0, len(imp_ids), 500):
                chunk = imp_ids[i:i + 500]
                oq = (select(out.c.impression_id, out.c.action, out.c.dwell_ms)
                      .where(out.c.impression_id.in_(chunk)))
                if as_of:
                    oq = oq.where(out.c.acted_at <= as_of)
                for orow in conn.execute(oq).fetchall():
                    outcomes.setdefault(orow.impression_id, []).append(orow)
        # deck_job_id -> {card_index: served_before}, for the loaded decks only,
        # and the same keys -> reason.
        withdrawals: dict[str, dict[int, int]] = {}
        reasons: dict[str, dict[int, str]] = {}
        if inspect(conn).has_table(WITHDRAWALS_TABLE):
            jobs = list(dict.fromkeys([r.deck_job_id for r in rows] + [p.run_id for p in packs]))
            for i in range(0, len(jobs), 500):   # chunked like the outcomes IN()
                wq = select(_WITHDRAWALS).where(_WITHDRAWALS.c.deck_job_id.in_(jobs[i:i + 500]))
                if as_of:
                    wq = wq.where(_WITHDRAWALS.c.first_withdrawn_at <= as_of)
                for wrow in conn.execute(wq).fetchall():
                    withdrawals.setdefault(wrow.deck_job_id, {})[int(wrow.card_index)] = (
                        wrow.served_before)
                    reasons.setdefault(wrow.deck_job_id, {})[int(wrow.card_index)] = wrow.reason

    decks: dict[str, LoggedDeck] = {}
    order: list[str] = []
    refresh: set[str] = set()   # deck_job_ids of Calibration refresh decks
    marked: set[str] = set()    # deck_job_ids carrying a paging marker (module doc)
    deferred: set[str] = set()  # deck_job_ids with deferred-evidence (tiered) rows
    for r in rows:
        features = _json_dict(r.features_json)
        # getattr: None when the live table lacks the column (not selected).
        features_compact = _json_dict(getattr(r, "features_compact", None))
        evidence_tier = getattr(r, "evidence_tier", None)
        # Before the projection trim: deck_source is not a PROJECTION_KEYS key.
        if any(d is not None and d.get("deck_source") == CALIBRATION_REFRESH_SOURCE
               for d in (features, features_compact)):
            refresh.add(r.deck_job_id)
        # Before the trim too: neither is PAGE_STORE_MARKER.
        if r.is_ghost != 1 and (evidence_tier is not None or any(
                d is not None and d.get(PAGE_STORE_MARKER) == 1
                for d in (features, features_compact))):
            marked.add(r.deck_job_id)
        # A partial run (every row 'partial_run', ruling 21) is never packed by
        # design: replay and calibration exclude it as partial_run, and its
        # delivered cards keep counting in e(k), as before v5.
        if r.is_ghost != 1 and evidence_tier not in (None, PARTIAL_RUN_TIER):
            deferred.add(r.deck_job_id)
        if project_features and features is not None:
            features = {k: v for k, v in features.items() if k in PROJECTION_KEYS}
        card = LoggedCard(
            impression_id=r.impression_id,
            deck_job_id=r.deck_job_id,
            user_id=r.user_id,
            league_id=r.league_id,
            card_index=int(r.card_index),
            trade_hash=r.trade_hash,
            propensity=(float(r.propensity) if r.propensity is not None else None),
            base_score=(float(r.base_score) if r.base_score is not None else None),
            final_score=(float(r.final_score) if r.final_score is not None else None),
            archetype=r.archetype,
            shape_bucket=r.shape_bucket,
            served_at=r.served_at,
            features=features,
            features_compact=features_compact,
            evidence_tier=evidence_tier,
            is_ghost=(r.is_ghost == 1),
            delivered_at=getattr(r, "delivered_at", None),
        )
        _reduce_outcomes(card, outcomes.get(r.impression_id, ()))
        deck = decks.get(r.deck_job_id)
        if deck is None:
            deck = LoggedDeck(
                deck_job_id=r.deck_job_id,
                user_id=r.user_id,
                league_id=r.league_id,
                served_at=r.served_at,
            )
            decks[r.deck_job_id] = deck
            order.append(r.deck_job_id)
        deck.cards.append(card)

    in_flight_from = (None if as_of is None else
                      (datetime.fromisoformat(as_of) - IN_FLIGHT_WINDOW).isoformat())
    # run_id -> (card_count, final, last delivered card_index as of the read)
    packed: dict[str, tuple[int, bool, int]] = {}
    pack_only = False
    for p in packs:
        deck = decks.get(p.run_id)
        if deck is None:   # no row in the window: a deck missing its full rows
            deck = LoggedDeck(deck_job_id=p.run_id, user_id=p.user_id,
                              league_id=p.league_id, served_at=p.served_at)
            decks[p.run_id] = deck
            order.append(p.run_id)
            pack_only = True
        got = unpacked[p.run_id]
        if got is None:
            deck.exclusion = PACK_INTEGRITY
            continue
        run, last_delivered, cards = got
        deck.upgrade_misses = _upgrade_misses(run)
        if run.get(PAGE_STORE_MARKER) == 1:
            marked.add(p.run_id)
        # deck_source is not a pack key (CONTRACT_KEYS): refresh decks are kept
        # at "live" evidence, full rows (#370). If S8 ever packs one, the writer
        # must carry deck_source in the run metadata, where this reads it.
        if run.get("deck_source") == CALIBRATION_REFRESH_SOURCE:
            refresh.add(p.run_id)
        packed[p.run_id] = (p.card_count,
                            *_pack_state(run, last_delivered, p.served_at, as_of, in_flight_from))
        full = {c.card_index for c in deck.cards if not c.is_ghost}
        for u in cards:
            if u["card_index"] not in full:
                card = _packed_card(p, u, project_features)
                _reduce_outcomes(card, outcomes.get(card.impression_id, ()))
                deck.cards.append(card)

    result = [decks[j] for j in order]
    if pack_only:
        result.sort(key=lambda d: (d.served_at, d.deck_job_id))
    for deck in result:
        deck.cards.sort(key=lambda c: (c.card_index, c.is_ghost))
        if deck.deck_job_id in refresh:   # not a Trades deck: ahead of every other reason
            deck.exclusion = CALIBRATION_REFRESH
            continue
        if deck.exclusion is not None:
            continue
        idx = [c.card_index for c in deck.cards if not c.is_ghost]   # sorted
        withdrawn = withdrawals.get(deck.deck_job_id, {})
        w0 = sorted(i for i, served_before in withdrawn.items() if served_before == 0)
        pack = packed.get(deck.deck_job_id)
        # Without a pack, every withdrawal index bounds N (a trailing W1 with no
        # card is a gap, not out of range); only a negative index is outside.
        n = pack[0] if pack else max(idx + list(withdrawn), default=-1) + 1
        removed = set(w0)
        paged = deck.deck_job_id in marked and not (
            PAGING_RELEASED_AT is not None and deck.served_at < PAGING_RELEASED_AT)
        by_index = {c.card_index: c for c in deck.cards if not c.is_ghost}

        def shown(i: int) -> bool | None:
            """Whether the evidence says index i was delivered as of the read:
            the pack's deliveries, else a paged deck's row delivered_at; None
            when there is no such evidence (no card, or a legacy deck)."""
            if pack:
                return i <= pack[2]
            card = by_index.get(i)
            return None if card is None or not paged else _delivered_by(card.delivered_at, as_of)

        if (any(i in by_index and (by_index[i].delivered_at is not None
                                   or by_index[i].impression_id in outcomes)
                for i in w0)                       # never delivered, yet delivered or acted on
                or any(shown(i) is False for i, served_before in withdrawn.items()
                       if served_before != 0)      # delivered before, yet no delivery
                or any(not 0 <= i < n for i in withdrawn)):
            deck.exclusion = WITHDRAWAL_CONFLICT
            continue
        # A present W0 card (packed, or an undelivered first30 row) is dropped.
        deck.cards = [c for c in deck.cards if c.is_ghost or c.card_index not in removed]
        idx = [c.card_index for c in deck.cards if not c.is_ghost]
        deck.withdrawn_removed = len(w0)
        reason_of = reasons.get(deck.deck_job_id, {})
        deck.withdrawn_removed_by_reason = dict(sorted(Counter(reason_of[i] for i in w0).items()))
        for c in deck.cards:
            if not c.is_ghost:
                c.position = c.card_index - bisect_left(w0, c.card_index)
        if pack:
            _n, final, last_delivered = pack
            if not final:
                deck.exclusion = IN_FLIGHT
                continue
            for c in deck.cards:
                c.delivered = not c.is_ghost and c.card_index <= last_delivered
        elif (PACK_REQUIRED_SINCE is not None and deck.served_at >= PACK_REQUIRED_SINCE
              and deck.deck_job_id in deferred):   # only a deferred-evidence deck is packed
            maybe_live = in_flight_from is not None and deck.served_at >= in_flight_from
            deck.exclusion = IN_FLIGHT if maybe_live else INCOMPLETE_DECK
            continue
        elif paged:   # never the legacy rule: delivered only where a row says so, by as_of
            for c in deck.cards:
                c.delivered = not c.is_ghost and _delivered_by(c.delivered_at, as_of)
        no_evidence = paged and not pack and not any(c.delivered for c in deck.cards)
        under_recorded = (pack or paged) and not no_evidence and any(
            not c.is_ghost and not c.delivered and c.impression_id in outcomes
            for c in deck.cards)          # an outcome on a card not delivered as of the read
        if sorted(idx + w0) != list(range(n)) or under_recorded:
            deck.exclusion = INCOMPLETE_DECK
        elif no_evidence:
            deck.exclusion = NO_DELIVERY_EVIDENCE
    return result


def last_served_at(engine=None, db_url: str | None = None, since: str | None = None,
                   until: str | None = None, user_id: str | None = None,
                   league_id: str | None = None) -> str | None:
    """The latest deck_impressions.served_at in the window (load_decks'
    since / until / scope filters), or None when nothing was served in it:
    the anchor a settle lag is added to (replay.settled_read)."""
    imp = deck_impressions_table
    q = select(func.max(imp.c.served_at))
    if since:
        q = q.where(imp.c.served_at >= since)
    if until:
        q = q.where(imp.c.served_at < until)
    if user_id:
        q = q.where(imp.c.user_id == user_id)
    if league_id:
        q = q.where(imp.c.league_id == league_id)
    with resolve_engine(engine, db_url).connect() as conn:
        return conn.execute(q).scalar()


def _delivered_by(delivered_at: str | None, as_of: str | None) -> bool:
    """A row's delivered_at says it was delivered as of the read (inclusive)."""
    return delivered_at is not None and (as_of is None or delivered_at <= as_of)


def _unpack(p) -> tuple[dict, int, list[dict]] | None:
    """(run metadata, last delivered card_index, unpacked cards) for one pack
    row, or None when it fails integrity."""
    try:
        run, cards = evidence_pack.unpack_run(evidence_pack.PackedRun(
            pack_version=p.pack_version, header_json=p.header_json,
            cards_blob=p.cards_blob, checksum=p.checksum, card_count=p.card_count))
        last_delivered = evidence_pack.check_deliveries(run, p.card_count)
        if any(u.get("deck_job_id") != p.run_id for u in cards):
            raise evidence_pack.PackIntegrityError("the pack holds another run's cards")
    except evidence_pack.PackIntegrityError:
        return None
    return run, last_delivered, cards


def _upgrade_misses(run: dict) -> dict[str, int]:
    """A pack's run["upgrade_misses"] as cause -> count, sorted (module doc,
    U4-R2): a legacy int n is {"other": n}, a missing key {}."""
    raw = run.get("upgrade_misses")
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {cause: int(n) for cause, n in sorted(raw.items())}
    return {UPGRADE_MISS_OTHER: int(raw)}


def _pack_state(run: dict, last_delivered: int, served_at: str, as_of: str | None,
                in_flight_from: str | None) -> tuple[bool, int]:
    """(final, last delivered card_index) of a pack as of the read (module
    doc, in-flight packs). `last_delivered` is check_deliveries' over the
    whole, already-validated list; `in_flight_from` is as_of minus
    IN_FLIGHT_WINDOW."""
    if "retired" not in run:      # written at retirement: final, every delivery in
        return True, last_delivered
    if as_of is None:
        return run["retired"] is True, last_delivered
    seen = [d[0] for d in run["deliveries"] if d[1] <= as_of]
    retired_at = run.get("retired_at")
    final = ((run["retired"] is True and isinstance(retired_at, str) and retired_at <= as_of)
             or served_at < in_flight_from)
    return final, (seen[-1] if seen else -1)


def _reduce_outcomes(card: LoggedCard, orows) -> None:
    for orow in orows:
        action = orow.action
        if action == "viewed":
            card.viewed = True
        elif action == "like":
            card.liked = True
        elif action == "pass":
            card.passed = True
        elif action == "propose":
            card.proposed = True
        elif action == "not_interested":
            card.not_interested = True
        elif action == "undo":
            card.undone = True
        if orow.dwell_ms is not None:
            card.dwell_ms = max(card.dwell_ms or 0, int(orow.dwell_ms))


def _packed_card(p, u: dict, project_features: bool) -> LoggedCard:
    """An unpacked card as a LoggedCard: the deterministic impression_id
    (outcomes join on it), the logged fields from the pack, and every other
    packed key (the frozen scorer inputs, the attribution and the per-run
    shared fields) in features_compact."""
    compact = {k: v for k, v in u.items() if k not in _PACKED_LOGGED}
    if project_features:
        compact = {k: v for k, v in compact.items() if k in PROJECTION_KEYS}

    def num(k):
        return float(u[k]) if u.get(k) is not None else None

    return LoggedCard(
        impression_id=card_impression_id(p.run_id, u["card_index"]),
        deck_job_id=p.run_id,
        user_id=u.get("user_id", p.user_id),
        league_id=u.get("league_id", p.league_id),
        card_index=u["card_index"],
        trade_hash=u.get("trade_hash"),
        propensity=num("propensity"),
        base_score=num("base_score"),
        final_score=num("final_score"),
        archetype=u.get("archetype"),
        shape_bucket=u.get("shape_bucket"),
        served_at=u.get("served_at", p.served_at),
        features=None,
        features_compact=compact,
    )


def split_decks(
    decks: list[LoggedDeck], eval_start: str,
) -> tuple[list[LoggedDeck], list[LoggedDeck]]:
    """Time-ordered protocol split: decks served BEFORE eval_start are the
    fit/train set, decks served AT/AFTER it are the eval set. Split is by
    the deck's served_at (all cards in a job share it) — no impression
    after the split can leak into scorer fitting because the harness only
    ever hands the pre-split list to fit(). There is deliberately NO
    shuffled/random-CV API in this package: sequential logs get sequential
    splits only."""
    if not eval_start:
        raise ValueError("eval_start is required for a train/eval split")
    train = [d for d in decks if d.served_at < eval_start]
    evals = [d for d in decks if d.served_at >= eval_start]
    return train, evals
