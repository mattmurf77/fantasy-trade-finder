"""F8 — load the F1 impression spine into replayable structures.

Read-only. One LoggedDeck per deck_job_id, cards in served order
(card_index), each card carrying its frozen features_json plus aggregated
outcome flags from deck_outcomes (append-only labels: any number of rows
per impression is legal — we reduce to booleans here).

Engine resolution: pass an explicit SQLAlchemy engine (tests), or a
db_url (CLI --db), or neither — in which case backend.database.engine is
used, read at call time so test patches of backend.database.engine are
honored (same idiom as the product loaders).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy import create_engine, select

from backend.database import deck_impressions_table, deck_outcomes_table


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
    """The dict handed to a Scorer: frozen features merged with logged
    fields. Baseline scorers legitimately read `final_score` /
    `card_index`; honest CANDIDATE scorers must not touch `card_index`,
    `final_score`, or `propensity` — those encode the logged policy.
    Logged fields win key collisions (they are ground truth)."""
    d = dict(card.features or {})
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


def load_decks(
    engine=None,
    db_url: str | None = None,
    since: str | None = None,      # ISO — served_at >= since
    until: str | None = None,      # ISO — served_at <  until
    user_id: str | None = None,
    league_id: str | None = None,
) -> list[LoggedDeck]:
    """Load deck_impressions (+reduced outcomes) as LoggedDecks, time-ordered
    by served_at then deck_job_id. ISO-8601 UTC strings compare lexically,
    matching the storage format everywhere in this schema."""
    eng = resolve_engine(engine, db_url)

    imp = deck_impressions_table
    q = select(imp).order_by(imp.c.served_at, imp.c.deck_job_id, imp.c.card_index)
    if since:
        q = q.where(imp.c.served_at >= since)
    if until:
        q = q.where(imp.c.served_at < until)
    if user_id:
        q = q.where(imp.c.user_id == user_id)
    if league_id:
        q = q.where(imp.c.league_id == league_id)

    with eng.connect() as conn:
        rows = conn.execute(q).fetchall()
        imp_ids = [r.impression_id for r in rows]
        outcomes: dict[str, list] = {}
        if imp_ids:
            # Chunk the IN() to stay under SQLite's parameter cap.
            out = deck_outcomes_table
            for i in range(0, len(imp_ids), 500):
                chunk = imp_ids[i:i + 500]
                for orow in conn.execute(
                    select(out.c.impression_id, out.c.action, out.c.dwell_ms)
                    .where(out.c.impression_id.in_(chunk))
                ).fetchall():
                    outcomes.setdefault(orow.impression_id, []).append(orow)

    decks: dict[str, LoggedDeck] = {}
    order: list[str] = []
    for r in rows:
        try:
            features = json.loads(r.features_json) if r.features_json else None
            if not isinstance(features, dict):
                features = None
        except (json.JSONDecodeError, TypeError):
            features = None
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
        )
        for orow in outcomes.get(r.impression_id, ()):
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

    result = [decks[j] for j in order]
    for deck in result:
        deck.cards.sort(key=lambda c: c.card_index)
    return result


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
