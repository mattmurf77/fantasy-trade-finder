"""F8 — load the F1 impression spine into replayable structures.

Read-only. One LoggedDeck per deck_job_id, cards in served order
(card_index), each card carrying its frozen features_json plus aggregated
outcome flags from deck_outcomes (append-only labels: any number of rows
per impression is legal — we reduce to booleans here).

Narrow rows (C7 (i) scaffolding): a card may carry only a frozen compact
scorer-input block (backend/eval/contract.py) instead of features_json.
It is read from a `features_compact` column when the table has one; until
that column exists, every card's features_compact is None. The same holds
for `evidence_tier` (replay and calibration exclude 'partial_run'; every
other tier, ghost/first30/delivered/archive/full_interim, is a usable row).

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

LoggedDeck.exclusion, per deck: replay excludes the deck whole and never
sinks it; calibration excludes its cards.
  pack_integrity   unpack_run refuses the pack (unreadable, unknown version,
                   checksum mismatch, row fields disagreeing with its
                   header, malformed deliveries), or it holds another run's
                   cards; its cards are not merged
  incomplete_deck  the non-ghost card indexes are not exactly 0..N-1, where
                   N is the pack's card_count, or max+1 without a pack; or a
                   deck served at/after PACK_REQUIRED_SINCE has no pack and
                   is past IN_FLIGHT_WINDOW (a lost pack)
  in_flight        a deck served at/after PACK_REQUIRED_SINCE has no pack yet
                   and may still be live (served within IN_FLIGHT_WINDOW of
                   as_of): the pack is written when the deck retires. Not an
                   error; without as_of the reader can't tell, and such a
                   deck is incomplete_deck.

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
# Read only when the table has them (neither column exists yet).
OPTIONAL_COLUMNS = ("features_compact", "evidence_tier")
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
# LoggedDeck.exclusion values (also replay's exclusion reasons).
PACK_INTEGRITY = "pack_integrity"
INCOMPLETE_DECK = "incomplete_deck"
IN_FLIGHT = "in_flight"
# Lost-pack detection: decks served at or after this ISO UTC time must have a
# pack row. None until trades-eng's packed writer ships; then set it to the
# writer's go-live time.
PACK_REQUIRED_SINCE: str | None = None
# A deck's pack is written when it retires (superseded, or the 24 h display
# cap, PRD #339 §5.1); 1 h more for the write.
IN_FLIGHT_WINDOW = timedelta(hours=25)
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
    # Aggregated outcome flags (deck_outcomes reduce)
    viewed: bool = False
    liked: bool = False
    passed: bool = False
    proposed: bool = False
    not_interested: bool = False
    undone: bool = False
    dwell_ms: int | None = None    # max dwell across outcome rows


@dataclass
class LoggedDeck:
    deck_job_id: str
    user_id: str
    league_id: str
    served_at: str
    cards: list[LoggedCard] = field(default_factory=list)
    # None, or PACK_INTEGRITY / INCOMPLETE_DECK / IN_FLIGHT (module doc).
    exclusion: str | None = None


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
    only decks served at or before it, and outcomes acted at or before it
    (deck_outcomes.acted_at), are read, so a re-read at the same as_of is
    the same however many outcomes arrive later (models-lead R5.2 (b)); and
    the in_flight rule measures from it. Choosing as_of so labels are
    complete (a settle lag) is the caller's job: replay.settled_read.

    project_features=True keeps only contract.PROJECTION_KEYS inside each
    parsed features dict (and each packed card's features_compact): every
    registered scorer, and value_model's training path, scores the
    projected decks identically."""
    eng = resolve_engine(engine, db_url)

    imp = deck_impressions_table
    cols = [imp.c[name] for name in EVAL_COLUMNS]
    cols += [c for c in (imp.c.get(name) for name in OPTIONAL_COLUMNS)
             if c is not None]
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

    with eng.connect() as conn:
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
               for run_id, got in unpacked.items() if got for u in got[1]]))
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

    decks: dict[str, LoggedDeck] = {}
    order: list[str] = []
    for r in rows:
        features = _json_dict(r.features_json)
        if project_features and features is not None:
            features = {k: v for k, v in features.items() if k in PROJECTION_KEYS}
        # The column does not exist yet; getattr keeps this a no-op until it does.
        features_compact = _json_dict(getattr(r, "features_compact", None))
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
            evidence_tier=getattr(r, "evidence_tier", None),
            is_ghost=(r.is_ghost == 1),
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

    packed: dict[str, tuple[int, int]] = {}   # run_id -> (card_count, last delivered)
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
        last_delivered, cards = got
        packed[p.run_id] = (p.card_count, last_delivered)
        full = {c.card_index for c in deck.cards if not c.is_ghost}
        for u in cards:
            if u["card_index"] not in full:
                card = _packed_card(p, u, project_features)
                _reduce_outcomes(card, outcomes.get(card.impression_id, ()))
                deck.cards.append(card)

    in_flight_from = (None if as_of is None else
                      (datetime.fromisoformat(as_of) - IN_FLIGHT_WINDOW).isoformat())
    result = [decks[j] for j in order]
    if pack_only:
        result.sort(key=lambda d: (d.served_at, d.deck_job_id))
    for deck in result:
        deck.cards.sort(key=lambda c: (c.card_index, c.is_ghost))
        if deck.exclusion is not None:
            continue
        idx = [c.card_index for c in deck.cards if not c.is_ghost]
        if deck.deck_job_id in packed:
            n, last_delivered = packed[deck.deck_job_id]
            for c in deck.cards:
                c.delivered = not c.is_ghost and c.card_index <= last_delivered
        elif PACK_REQUIRED_SINCE is not None and deck.served_at >= PACK_REQUIRED_SINCE:
            live = in_flight_from is not None and deck.served_at >= in_flight_from
            deck.exclusion = IN_FLIGHT if live else INCOMPLETE_DECK
            continue
        else:
            n = idx[-1] + 1 if idx else 0
        if idx != list(range(n)):
            deck.exclusion = INCOMPLETE_DECK
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


def _unpack(p) -> tuple[int, list[dict]] | None:
    """(last delivered card_index, unpacked cards) for one pack row, or None
    when it fails integrity."""
    try:
        run, cards = evidence_pack.unpack_run(evidence_pack.PackedRun(
            pack_version=p.pack_version, header_json=p.header_json,
            cards_blob=p.cards_blob, checksum=p.checksum, card_count=p.card_count))
        last_delivered = evidence_pack.check_deliveries(run, p.card_count)
        if any(u.get("deck_job_id") != p.run_id for u in cards):
            raise evidence_pack.PackIntegrityError("the pack holds another run's cards")
    except evidence_pack.PackIntegrityError:
        return None
    return last_delivered, cards


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
