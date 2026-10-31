"""Deletion scrub: a deleted user's traces in OTHER users' decks (legal R28.20
(ii), R28.22; models-lead addendum G). Scope:
docs/plans/trade-time-to-suggestion/scope-deletion-scrub.md.

accounts._delete_user_data inserts one deletion_scrub_jobs row in the
deletion's own transaction (enqueue): a random token, the deleted user's
resolved ids and the leagues they were in, captured before league_members
loses them. This module then works the row:

  * the DB phase (run_pending): every deck store, in a background thread the
    deletion route kicks, retried by the cleanup loop under a lease. It runs
    again once IN_FLIGHT_GRACE after the deletion, for rows a deck in flight
    at deletion wrote later from its build-time snapshot;
  * the model phase (tick, a daily-tick step placed before value_model_refit,
    models-eng #542): eval.redaction.redact_model_store with the tokens;
  * the row is deleted once both are done (legal (ix)). Past ALERT_AFTER it
    is kept and retried, and the tick logs a count at ERROR. Until every
    store in the scope is built (COMPLETE), rows are kept, so a later
    SCRUB_VERSION re-runs them.

On a redacted card (its partner is a deleted id), in every store alike
(R28.22 b2, uniformity): the partner id becomes the token; every field from
the deleted user's Fleeced account is REMOVED, never set False (G-a1); the
blended scores that solve back to a removed value are nulled (scope §1.3).
Any other row that names a deleted id gets the token in its place. Decks
built after the deletion are never touched: they treat the person as any
non-user leaguemate (legal (vii)). No id is ever logged (legal (ix)).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select, update

from . import database as db
from .eval.contract import REDACTED_PARTNER_PREFIX

log = logging.getLogger("trade_finder")

# Bump when a store or field is added: a row whose db_version is older runs
# its DB phase again. 3: every store in the scope (stage 3, COMPLETE).
SCRUB_VERSION = 3
# True once every store in the scope is built (stage 3). Before that a
# finished row was kept, so the later stages scrubbed its deletion too.
COMPLETE = True

LEASE = timedelta(minutes=10)
IN_FLIGHT_GRACE = timedelta(hours=6)
ALERT_AFTER = timedelta(hours=24)
_BATCH = 200
# The fallback scans: rows per keyset page, and pages per run (one run per
# cleanup tick, so ~100k rows a tick, well inside the lease).
_SCAN_BATCH = 2000
_SCAN_PAGES_PER_RUN = 50

# ── What a redacted card loses (scope §0.2, §1.3) ───────────────────────────
# features_json keys from the partner's account (likes, standing offers and
# their breaker objections), removed whole.
_FEATURE_KEYS_REMOVED = ("likes_you", "standing_offer", "standing_offer_reason",
                         "breaker", "breaker_shadow")
# Blended scalars that solve back to a removed value, nulled.
_FEATURE_KEYS_NULLED = ("surplus_margin",)
_COLUMNS_NULLED = ("base_score", "final_score", "source_like_impression_id")
# The partner's side of the fit challenger's payload; `you` (the viewer's)
# and `boards` stay.
_FIT_KEYS_REMOVED = ("them", "aggregate", "bucket")
# valuation_json, every engine's shape (trade_policy, owner, value_core).
# owner_v2_bilateral (#557 QA P1-1): `bilateral` sums or mins both sides'
# support and net preference with the viewer's side kept (it solves back,
# scope §1.3), and `term_efficiency` classifies each companion by its
# recipient's preference-derived benefits.
_VALUATION_KEYS_REMOVED = ("partner_board", "mutual", "counterparty", "preference_priority",
                           "counterparty_benefits", "bilateral", "term_efficiency")
_VALUATION_ASSET_KEYS_REMOVED = ("partner_raw_value", "partner_effective_value",
                                 "partner_confidence", "counterparty_personal",
                                 "counterparty_source", "counterparty_preference")
_VALUATION_POLICY_KEYS_REMOVED = ("policy_floor", "effective_floor")


def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).isoformat()


def new_token() -> str:
    """One per deletion, random (legal (ii) c1: never derived from the id)."""
    return REDACTED_PARTNER_PREFIX + uuid.uuid4().hex


# ── In the deletion transaction ─────────────────────────────────────────────

def capture_leagues(conn, user_ids) -> list[str]:
    """The leagues whose decks may name the person, read before the deletion
    removes their rows: their memberships, the leagues they imported, the
    roster history naming them, and their own decks' leagues. (A league they
    left that none of these still names isn't found; the 365-day prune bounds
    it, scope §0.1.)"""
    ids = list(user_ids)
    found: set[str] = set()
    for column, where in (
            (db.league_members_table.c.league_id, db.league_members_table.c.user_id),
            (db.leagues_table.c.sleeper_league_id, db.leagues_table.c.user_id),
            (db.league_roster_history_table.c.league_id,
             db.league_roster_history_table.c.owner_user_id),
            (db.deck_impressions_table.c.league_id, db.deck_impressions_table.c.user_id),
            (db.deck_evidence_packs_table.c.league_id, db.deck_evidence_packs_table.c.user_id)):
        found.update(conn.execute(select(column).where(where.in_(ids)).distinct()).scalars())
    return sorted(x for x in found if x)


def capture_names(conn, user_ids) -> dict:
    """The person's names, read before the deletion removes their rows:
    `leagues` = {league_id: [display names and usernames]} (a Calibration card
    names its partner by display name, never by id), and `usernames`, which
    are unique (a notification names its partner by username, so only those
    match there: a display name could be someone else's)."""
    m, u = db.league_members_table, db.users_table
    ids = list(user_ids)
    by_league: dict[str, set] = {}
    usernames: set = set()
    for league_id, display, username in conn.execute(select(
            m.c.league_id, m.c.display_name, m.c.username).where(m.c.user_id.in_(ids))):
        by_league.setdefault(league_id, set()).update(n for n in (display, username) if n)
        if username:
            usernames.add(username)
    usernames.update(n for n in conn.execute(select(u.c.username).where(
        u.c.sleeper_user_id.in_(ids))).scalars() if n)
    return {"leagues": {lg: sorted(ns) for lg, ns in by_league.items() if ns},
            "usernames": sorted(usernames)}


def enqueue(conn, user_ids, league_ids, now: datetime | None = None) -> str:
    """Insert the job row in the caller's (the deletion's) transaction and
    return its token."""
    token = new_token()
    conn.execute(db.deletion_scrub_jobs_table.insert().values(
        job_id=uuid.uuid4().hex, token=token,
        partner_ids_json=json.dumps(sorted(user_ids)),
        league_ids_json=json.dumps(sorted(league_ids)),
        partner_names_json=json.dumps(capture_names(conn, user_ids)),
        deleted_at=_iso(now or datetime.now(timezone.utc)), db_version=0, attempts=0))
    return token


def scrub_side_tables(conn, user_ids, token: str) -> dict[str, int]:
    """The small stores, in the deletion transaction with the same token:
    other users' taste for the person (user_taste `partner:<id>`) and their
    standing offers' team lists. `trade_matches.match_valuation_json` is
    cleared by the caller with the ids it already anonymizes (R28.22 e)."""
    counts = {}
    taste = db.user_taste_table
    attrs = [f"partner:{pid}" for pid in sorted(user_ids)]
    by_user: dict[str, list] = {}
    for row in conn.execute(select(taste).where(taste.c.attr.in_(attrs))).mappings():
        by_user.setdefault(row["user_id"], []).append(dict(row))
    for viewer, rows in by_user.items():
        # Two aliases of the person become one token, so their weights merge
        # (the key is (user_id, attr)).
        conn.execute(delete(taste).where(taste.c.user_id == viewer, taste.c.attr.in_(attrs)))
        conn.execute(taste.insert().values(
            user_id=viewer, attr=f"partner:{token}",
            w_short=sum(r["w_short"] for r in rows), w_long=sum(r["w_long"] for r in rows),
            updated_at=max(r["updated_at"] for r in rows)))
    counts["user_taste_partner_redacted"] = sum(len(rows) for rows in by_user.values())
    offers = db.standing_offers_table
    rows = conn.execute(select(offers.c.id, offers.c.team_user_ids).where(
        offers.c.user_id.notin_(list(user_ids)),
        or_(*[offers.c.team_user_ids.contains(pid, autoescape=True) for pid in user_ids]),
    )).all()
    changed = 0
    for offer_id, raw in rows:
        try:
            teams = json.loads(raw or "[]")
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(teams, list):
            continue
        new = [token if t in user_ids else t for t in teams]
        if new != teams:
            conn.execute(update(offers).where(offers.c.id == offer_id)
                         .values(team_user_ids=json.dumps(new)))
            changed += 1
    counts["standing_offers_team_redacted"] = changed
    return counts


# ── The redaction rules ─────────────────────────────────────────────────────

def _replace_ids(value, ids, token):
    """Every dict key and string value equal to a deleted id becomes the token."""
    if isinstance(value, dict):
        return {(token if k in ids else k): _replace_ids(v, ids, token) for k, v in value.items()}
    if isinstance(value, list):
        return [_replace_ids(v, ids, token) for v in value]
    if isinstance(value, str) and value in ids:
        return token
    return value


def _taste_attr(attr, ids, token):
    if isinstance(attr, str) and attr.startswith("partner:") and attr[len("partner:"):] in ids:
        return f"partner:{token}"
    return attr


def redact_features(features: dict, ids, token: str) -> dict:
    """A deck row's features_json for a card naming a deleted id. The id
    becomes the token everywhere (a dict key, a value, a taste attr). On a
    redacted card (the partner is a deleted id) the partner's own fields go
    too, the same way on every such card (scope §0.2)."""
    ids = set(ids)
    redacted = features.get("partner_user_id") in ids
    # The partner's team entry and its explicit outlook, keyed by their id.
    roster = features.get("roster_evaluation")
    if isinstance(roster, dict):
        roster = dict(roster)
        if isinstance(roster.get("teams"), dict):
            roster["teams"] = {k: v for k, v in roster["teams"].items() if k not in ids}
        if redacted:
            roster.pop("mutual_benefit", None)
        features = {**features, "roster_evaluation": roster}
    out = _replace_ids(features, ids, token)
    if isinstance(out.get("taste_attrs"), list):
        out["taste_attrs"] = [_taste_attr(a, ids, token) for a in out["taste_attrs"]]
    # The owner engine's frozen request rides on every card of its run, with
    # every member's declared and inferred outlook, so the person's account
    # fields go from it on any card that names them, not only their own.
    for key in ("owner_request", "owner_experiment"):
        if isinstance(out.get(key), dict):
            out[key] = _redact_owner_request(out[key], token)
    if not redacted:
        return out
    for key in _FEATURE_KEYS_REMOVED:
        out.pop(key, None)
    for key in _FEATURE_KEYS_NULLED:
        if key in out:
            out[key] = None
    if isinstance(out.get("negmem"), dict):
        out["negmem"] = {k: v for k, v in out["negmem"].items() if k != "exempt"}
    for key in ("fit", "fit_diag"):
        if isinstance(out.get(key), dict):
            fit = {k: v for k, v in out[key].items() if k not in _FIT_KEYS_REMOVED}
            if isinstance(fit.get("lenses"), dict):
                fit["lenses"] = {k: v for k, v in fit["lenses"].items() if k != "them"}
            out[key] = fit
    return out


def _redact_owner_request(snapshot: dict, token: str) -> dict:
    """The owner engine's frozen request (ids already the token): the
    person's board (their member's elo and board time), sources, preferences
    and declared and inferred outlooks go. A per-card snapshot holds only its
    partner's member; a bakeoff run's holds every member's."""
    snapshot = dict(snapshot)
    inputs = snapshot.get("input")
    if isinstance(inputs, dict):
        inputs = dict(inputs)
        if isinstance(inputs.get("members"), list):
            inputs["members"] = [
                {k: v for k, v in m.items() if k not in ("elo", "board_updated_at")}
                if isinstance(m, dict) and m.get("id") == token else m
                for m in inputs["members"]]
        for key in ("opponent_sources", "manager_preferences", "opponent_outlooks",
                    "inferred_outlooks"):
            if isinstance(inputs.get(key), dict):
                inputs[key] = {k: v for k, v in inputs[key].items() if k != token}
        snapshot["input"] = inputs
    return snapshot


def redact_valuation(valuation):
    """A redacted card's valuation_json, any engine's shape: the partner's
    board, preferences and the values that blend them go; the market and
    the viewer's own stay."""
    if not isinstance(valuation, dict):
        return valuation
    out = {k: v for k, v in valuation.items() if k not in _VALUATION_KEYS_REMOVED}
    if isinstance(out.get("policy"), dict):
        out["policy"] = {k: v for k, v in out["policy"].items()
                         if k not in _VALUATION_POLICY_KEYS_REMOVED}
    if isinstance(out.get("assets"), list):
        out["assets"] = [{k: v for k, v in a.items() if k not in _VALUATION_ASSET_KEYS_REMOVED}
                         if isinstance(a, dict) else a for a in out["assets"]]
    if isinstance(out.get("windows"), dict):
        out["windows"] = {k: v for k, v in out["windows"].items() if k != "partner"}
    detail = out.get("detail")
    if isinstance(detail, dict) and isinstance(detail.get("outlook"), dict):
        out["detail"] = {**detail, "outlook": {k: v for k, v in detail["outlook"].items()
                                               if k != "partner"}}
    core = out.get("core")
    if isinstance(core, dict) and isinstance(core.get("throwin"), dict):
        out["core"] = {**core, "throwin": {k: v for k, v in core["throwin"].items()
                                           if k != "recipient_value"}}
    # value_core blends the partner's outlook in: outlook = (viewer + partner)
    # / 2 with the viewer's side kept, priority and effective from it (scope
    # §1.3). value and rank (market and the viewer's own board) stay.
    out.pop("effective", None)
    if isinstance(out.get("scores"), dict):
        out["scores"] = {k: v for k, v in out["scores"].items() if k not in ("outlook", "priority")}
    return out


# ── The DB phase ────────────────────────────────────────────────────────────

def _viewers(conn, league_id: str, ids) -> list[str]:
    """Who may hold decks in the league: its members and its importers, but
    the deleted ids."""
    found = set(conn.execute(select(db.league_members_table.c.user_id).where(
        db.league_members_table.c.league_id == league_id)).scalars())
    found.update(conn.execute(select(db.leagues_table.c.user_id).where(
        db.leagues_table.c.sleeper_league_id == league_id)).scalars())
    return sorted(u for u in found if u and u not in ids)


def _loads(raw):
    try:
        return json.loads(raw) if raw else None
    except (json.JSONDecodeError, TypeError):
        return None


def redact_row(row: dict, ids, token: str) -> dict:
    """A deck_impressions row (as a dict of its columns, features_json and
    valuation_json as JSON text or objects) after the scrub: the same rules
    as the stored rows get. Used by the server for a row it writes from a
    deck's build-time snapshot after the scrub redacted that card."""
    ids = set(ids)
    out = dict(row)
    raw = out.get("features_json")
    features = _loads(raw) if isinstance(raw, str) else raw
    if not isinstance(features, dict):
        return out
    new = redact_features(features, ids, token)
    out["features_json"] = json.dumps(new) if isinstance(raw, str) else new
    raw_valuation = out.get("valuation_json")
    valuation = _loads(raw_valuation) if isinstance(raw_valuation, str) else raw_valuation
    if features.get("partner_user_id") in ids:
        out.update({c: None for c in _COLUMNS_NULLED if c in out})
        if isinstance(valuation, dict):
            valuation = redact_valuation(valuation)
    if isinstance(valuation, dict):
        valuation = _replace_ids(valuation, ids, token)
        out["valuation_json"] = json.dumps(valuation) if isinstance(raw_valuation, str) else valuation
    return out


def _row_failed(job: dict, store: str, err: Exception) -> None:
    """A row whose redaction raised (a poison row, #557 QA P3): counted, so
    the pass isn't done and is retried; the class only is logged."""
    job["failures"] = job.get("failures", 0) + 1
    log.warning("[scrub] job=%s %s row not redacted: %s", _short(job["job_id"]), store,
                type(err).__name__)


def _redact_impressions(impression_ids, job: dict) -> int:
    """Redact these deck_impressions rows (any that still name a deleted id)."""
    ids, token = set(job["ids"]), job["token"]
    imp = db.deck_impressions_table
    changed = 0
    for start in range(0, len(impression_ids), _BATCH):
        _renew(job)
        with db.engine.begin() as conn:
            rows = conn.execute(select(imp.c.impression_id, imp.c.features_json,
                                       imp.c.valuation_json).where(
                imp.c.impression_id.in_(impression_ids[start:start + _BATCH]))).all()
            for impression_id, raw_features, raw_valuation in rows:
                features = _loads(raw_features)
                if not isinstance(features, dict):
                    continue
                try:
                    new = redact_features(features, ids, token)
                except Exception as err:   # a poison row: counted, the pass not done
                    _row_failed(job, "deck_impressions", err)
                    continue
                if new == features:
                    continue
                values = {"features_json": json.dumps(new)}
                valuation = _loads(raw_valuation)
                if features.get("partner_user_id") in ids:
                    values.update({c: None for c in _COLUMNS_NULLED})
                    if valuation is not None:
                        valuation = redact_valuation(valuation)
                if valuation is not None:
                    new_valuation = _replace_ids(valuation, ids, token)
                    if new_valuation != _loads(raw_valuation):
                        values["valuation_json"] = json.dumps(new_valuation)
                conn.execute(update(imp).where(imp.c.impression_id == impression_id)
                             .values(**values))
                changed += 1
    return changed


def _mentions(column, ids):
    return or_(*[column.contains(pid, autoescape=True) for pid in sorted(ids)])


def _scrub_impressions(job: dict) -> int:
    """The league pass: deck_impressions rows naming a deleted id, of decks
    served up to the job's cutoff, per viewer and league
    (ix_deck_impressions_user_league)."""
    ids = set(job["ids"])
    imp = db.deck_impressions_table
    changed = 0
    with db.engine.connect() as conn:
        pairs = [(v, lg) for lg in job["leagues"] for v in _viewers(conn, lg, ids)]
    for viewer, league_id in pairs:
        with db.engine.connect() as conn:
            found = conn.execute(select(imp.c.impression_id).where(
                imp.c.user_id == viewer, imp.c.league_id == league_id,
                imp.c.served_at <= job["cutoff"],
                _mentions(imp.c.features_json, ids))).scalars().all()
        changed += _redact_impressions(found, job)
    return changed


def _scan_impressions(job: dict, after: str, budget: "_Budget") -> tuple[str | None, int]:
    """The fallback scan (head-eng, 10-31: a league the person left before
    deleting isn't captured): every deck_impressions row up to the cutoff, in
    keyset pages of _SCAN_BATCH by impression_id, while `budget` (the run's
    pages left; each renews the job's lease) lasts. Returns (the cursor to resume from, or None at
    the end; rows changed)."""
    ids = set(job["ids"])
    imp = db.deck_impressions_table
    changed = 0
    while budget.take():
        with db.engine.connect() as conn:
            rows = conn.execute(select(
                imp.c.impression_id, _mentions(imp.c.features_json, ids).label("hit")).where(
                imp.c.impression_id > after, imp.c.served_at <= job["cutoff"],
                imp.c.user_id.notin_(sorted(ids)),
            ).order_by(imp.c.impression_id).limit(_SCAN_BATCH)).all()
        if not rows:
            return None, changed
        changed += _redact_impressions([r.impression_id for r in rows if r.hit], job)
        after = rows[-1].impression_id
    return after, changed


def _redact_member(member: dict, ids, token: str) -> dict:
    if member.get("partner") not in ids:
        return member
    out = {**member, "partner": token}
    if "base_score" in out:
        out["base_score"] = None
    return out


def _redact_candidate_set(conn, row, job: dict) -> bool:
    """A member whose partner is a deleted id takes the token and loses its
    base_score, in the packed column through the codec (G-a3) and in legacy
    candidates_json. True when the row changed."""
    from .eval import evidence_pack
    ids, token = set(job["ids"]), job["token"]
    cs = db.deck_candidate_sets_table
    values = {}
    try:
        members = _loads(row.candidates_json)
        if isinstance(members, list):
            new = [_redact_member(m, ids, token) if isinstance(m, dict) else m for m in members]
            if new != members:
                values["candidates_json"] = json.dumps(new)
        if row.candidates_packed is not None:
            run, cards = evidence_pack.unpack_candidates(evidence_pack.PackedCandidates(
                row.cand_pack_version, row.candidates_packed))
            new = [_redact_member(m, ids, token) for m in cards]
            if new != cards:
                values["candidates_packed"] = evidence_pack.pack_candidates(
                    run, new).candidates_packed
    except Exception as err:      # a poison row (an unreadable pack): counted
        _row_failed(job, "deck_candidate_sets", err)
        return False
    if values:
        conn.execute(update(cs).where(cs.c.candidate_set_id == row.candidate_set_id)
                     .values(**values))
    return bool(values)


def _candidate_columns():
    cs = db.deck_candidate_sets_table
    return (cs.c.candidate_set_id, cs.c.candidates_json, cs.c.candidates_packed,
            cs.c.cand_pack_version)


def _scrub_candidate_sets(job: dict) -> int:
    """The league pass: deck_candidate_sets made up to the job's cutoff, per
    viewer and league."""
    ids = set(job["ids"])
    cs = db.deck_candidate_sets_table
    changed = 0
    with db.engine.connect() as conn:
        pairs = [(v, lg) for lg in job["leagues"] for v in _viewers(conn, lg, ids)]
    for viewer, league_id in pairs:
        _renew(job)
        with db.engine.begin() as conn:
            for row in conn.execute(select(*_candidate_columns()).where(
                    cs.c.user_id == viewer, cs.c.league_id == league_id,
                    cs.c.created_at <= job["cutoff"])).all():
                changed += _redact_candidate_set(conn, row, job)
    return changed


def _scan_candidate_sets(job: dict, after: str, budget: "_Budget") -> tuple[str | None, int]:
    """The fallback scan of deck_candidate_sets, as _scan_impressions. A
    packed set is compressed, so it's decoded here to be checked (one row
    per deck, a few KB)."""
    ids = set(job["ids"])
    cs = db.deck_candidate_sets_table
    changed = 0
    while budget.take():
        with db.engine.begin() as conn:
            rows = conn.execute(select(*_candidate_columns()).where(
                cs.c.candidate_set_id > after, cs.c.created_at <= job["cutoff"],
                cs.c.user_id.notin_(sorted(ids)),
            ).order_by(cs.c.candidate_set_id).limit(_SCAN_BATCH)).all()
            if not rows:
                return None, changed
            for row in rows:
                if row.candidates_packed is not None or any(
                        pid in (row.candidates_json or "") for pid in ids):
                    changed += _redact_candidate_set(conn, row, job)
        after = rows[-1].candidate_set_id
    return after, changed


# ── Packs (deck_evidence_packs): through the codec only (G-a3) ─────────────

# A packed card's blended scores (scope §1.3); `likes_you` is removed.
_PACKED_NULLED = ("surplus_margin", "base_score", "final_score")


def redact_packed_card(card: dict, ids, token: str) -> dict:
    """One packed card: a `partner:<id>` taste attr takes the token on any
    card; a redacted card (its partner is a deleted id) takes the token as
    its partner, loses `likes_you` and has its blended scores nulled."""
    out = dict(card)
    if isinstance(out.get("taste_attrs"), list):
        out["taste_attrs"] = [_taste_attr(a, ids, token) for a in out["taste_attrs"]]
    if out.get("partner_user_id") in ids:
        out["partner_user_id"] = token
        out.pop("likes_you", None)
        for key in _PACKED_NULLED:
            if key in out:
                out[key] = None
    return out


def redact_pack_run(run: dict, cards: list[dict], ids) -> dict:
    """The pack's run metadata: the person's QB/TE holdings and the protected
    trade_hashes of their cards leave the quality filter's recorded inputs
    (G-a3's third change)."""
    inputs = run.get("filter_inputs")
    if not isinstance(inputs, dict):
        return run
    inputs = dict(inputs)
    if isinstance(inputs.get("qb_te"), dict):
        inputs["qb_te"] = {k: v for k, v in inputs["qb_te"].items() if k not in ids}
    if isinstance(inputs.get("protected"), list):
        theirs = {c.get("trade_hash") for c in cards if c.get("partner_user_id") in ids}
        inputs["protected"] = [h for h in inputs["protected"] if h not in theirs]
    return {**run, "filter_inputs": inputs}


def redact_pack(row: dict, ids, token: str, now: str):
    """A deck_evidence_packs row's new pack columns, or None when nothing
    names a deleted id: unpack_run, the four changes (the token, the c2
    field, the run's holdings and protected hashes, `redacted_at`), then
    pack_run, which refuses an inexact pack. card_count and every other card
    are unchanged (G-a2)."""
    from .eval import evidence_pack
    ids = set(ids)
    run, cards = evidence_pack.unpack_run(evidence_pack.PackedRun(
        row["pack_version"], row["header_json"], bytes(row["cards_blob"]), row["checksum"],
        row["card_count"]))
    new_cards = [redact_packed_card(c, ids, token) for c in cards]
    new_run = redact_pack_run(run, cards, ids)
    if new_cards == cards and new_run == run:
        return None
    return evidence_pack.pack_run({**new_run, "redacted_at": now}, new_cards,
                                  card_count=row["card_count"])


def _redact_packs(run_ids, job: dict) -> int:
    """Rewrite these packs by compare-and-swap on their checksum: a live
    writer's header update in between makes the scrub re-read and redo (and
    the writer, on its own miss, rebuilds from the scrubbed row:
    server._fresh_pack_state)."""
    ids, token = set(job["ids"]), job["token"]
    t = db.deck_evidence_packs_table
    changed = 0
    for run_id in run_ids:
        _renew(job)
        for _attempt in range(5):
            with db.engine.begin() as conn:
                row = conn.execute(select(t).where(t.c.run_id == run_id)).mappings().first()
                if row is None:
                    break
                try:
                    packed = redact_pack(row, ids, token, _iso(datetime.now(timezone.utc)))
                except Exception as err:   # pack_run refused, or an unreadable pack
                    _row_failed(job, "deck_evidence_packs", err)
                    break
                if packed is None:
                    break
                if conn.execute(update(t).where(
                        t.c.run_id == run_id, t.c.checksum == row["checksum"]).values(
                        pack_version=packed.pack_version, header_json=packed.header_json,
                        cards_blob=packed.cards_blob, checksum=packed.checksum)).rowcount:
                    changed += 1
                    break
        else:
            raise RuntimeError("pack kept changing")
    return changed


def _scrub_packs(job: dict) -> int:
    """The league pass over packs: the partner dictionary, the taste
    vocabulary and the holdings are all in header_json."""
    ids = set(job["ids"])
    t = db.deck_evidence_packs_table
    found = []
    with db.engine.connect() as conn:
        pairs = [(v, lg) for lg in job["leagues"] for v in _viewers(conn, lg, ids)]
        for viewer, league_id in pairs:
            found += conn.execute(select(t.c.run_id).where(
                t.c.user_id == viewer, t.c.league_id == league_id,
                t.c.served_at <= job["cutoff"], _mentions(t.c.header_json, ids))).scalars().all()
    return _redact_packs(found, job)


def _scan_packs(job: dict, after: str, budget: "_Budget") -> tuple[str | None, int]:
    """The fallback scan of packs, as _scan_impressions, matching on
    header_json (never reading cards_blob unless it matches)."""
    ids = set(job["ids"])
    t = db.deck_evidence_packs_table
    changed = 0
    while budget.take():
        with db.engine.connect() as conn:
            rows = conn.execute(select(t.c.run_id, _mentions(t.c.header_json, ids).label("hit")).where(
                t.c.run_id > after, t.c.served_at <= job["cutoff"],
                t.c.user_id.notin_(sorted(ids)),
            ).order_by(t.c.run_id).limit(_SCAN_BATCH)).all()
        if not rows:
            return None, changed
        changed += _redact_packs([r.run_id for r in rows if r.hit], job)
        after = rows[-1].run_id
    return after, changed


def redact_bakeoff_config(config, ids, token: str):
    """A bakeoff run's config_json: any id becomes the token, and the owner
    engine's frozen input (every member's board, sources, preferences and
    outlooks) loses the person's account fields (legal f's trace, 10-31),
    under `owner_request` (organic runs) or at the top level (owner-selected
    runs: fair packages, asset ideas; #557 QA P1-2)."""
    if not isinstance(config, dict):
        return config
    out = _replace_ids(config, set(ids), token)
    if isinstance(out.get("owner_request"), dict):
        out["owner_request"] = _redact_owner_request(out["owner_request"], token)
    if isinstance(out.get("input"), dict):
        out = _redact_owner_request(out, token)
    return out


def _drop_pools(value, token: str):
    """An owner arm's diagnostics keep each member's asset pools, ordered by
    that member's preferences (trade_gen_owner._Search.pools): the person's
    entry goes, wherever a `pools` map sits."""
    if isinstance(value, dict):
        return {k: ({u: p for u, p in v.items() if u != token} if k == "pools" and isinstance(v, dict)
                    else _drop_pools(v, token)) for k, v in value.items()}
    if isinstance(value, list):
        return [_drop_pools(v, token) for v in value]
    return value


def redact_bakeoff_json(value, ids, token: str):
    """A bakeoff run's arms_json, agreement_json or groups_json (#557 QA
    P1-3): any id becomes the token and the person's pools go."""
    return _drop_pools(_replace_ids(value, set(ids), token), token)


_BAKEOFF_JSON_COLUMNS = ("arms_json", "agreement_json", "groups_json")
# Bakeoff rows can run to megabytes (#557 QA P2: one 2,000-row page of 2.2 MB
# rows took 20 s; a 21.7 MB row is possible), so they're read in batches of at
# most this many rows and this many bytes, each batch renewing the lease.
_BAKEOFF_BATCH = 20
_BAKEOFF_BATCH_BYTES = 8 * 1024 * 1024


def _renew(job: dict) -> None:
    """Renew the job's lease between batches (none in a direct call)."""
    if job.get("lease") is not None:
        job["lease"].renew()


def _bakeoff_batches(conn, run_ids) -> list[list]:
    """run_ids grouped into batches by count and by their rows' total size
    (one row bigger than the byte cap is a batch of its own)."""
    t = db.bakeoff_runs_table
    size = sum((func.coalesce(func.length(t.c[c]), 0)
                for c in ("config_json",) + _BAKEOFF_JSON_COLUMNS), 0)
    sizes = dict(conn.execute(select(t.c.run_id, size).where(t.c.run_id.in_(list(run_ids)))).all())
    batches, current, total = [], [], 0
    for run_id in run_ids:
        n = sizes.get(run_id, 0) or 0
        if current and (len(current) >= _BAKEOFF_BATCH or total + n > _BAKEOFF_BATCH_BYTES):
            batches.append(current)
            current, total = [], 0
        current.append(run_id)
        total += n
    if current:
        batches.append(current)
    return batches


def _redact_bakeoff_runs(run_ids, job: dict) -> int:
    ids, token = set(job["ids"]), job["token"]
    t = db.bakeoff_runs_table
    columns = ("config_json",) + _BAKEOFF_JSON_COLUMNS
    changed = 0
    batches = []
    for start in range(0, len(run_ids), 500):
        with db.engine.connect() as conn:
            batches += _bakeoff_batches(conn, run_ids[start:start + 500])
    for batch in batches:
        _renew(job)
        with db.engine.begin() as conn:
            for row in conn.execute(select(t.c.run_id, *(t.c[c] for c in columns)).where(
                    t.c.run_id.in_(batch))).mappings().all():
                values = {}
                try:
                    for column in columns:
                        old = _loads(row[column])
                        if old is None:
                            continue
                        new = (redact_bakeoff_config(old, ids, token) if column == "config_json"
                               else redact_bakeoff_json(old, ids, token))
                        if new != old:
                            values[column] = json.dumps(new, default=str)
                except Exception as err:   # a poison row: counted, the pass not done
                    _row_failed(job, "bakeoff_runs", err)
                    continue
                if values:
                    conn.execute(update(t).where(t.c.run_id == row["run_id"]).values(**values))
                    changed += 1
    return changed


def _bakeoff_mentions(t, ids):
    return or_(*[_mentions(t.c[c], ids) for c in ("config_json",) + _BAKEOFF_JSON_COLUMNS])


# The bakeoff scan's page: the database still reads each row's text to match
# it, so a page of megabyte rows is kept to a size one lease covers.
_BAKEOFF_SCAN_BATCH = 200


def _scan_bakeoff_runs(job: dict, after: str, budget: "_Budget") -> tuple[str | None, int]:
    """The fallback scan of bakeoff_runs, as _scan_impressions."""
    ids = set(job["ids"])
    t = db.bakeoff_runs_table
    changed = 0
    while budget.take():
        with db.engine.connect() as conn:
            rows = conn.execute(select(t.c.run_id, _bakeoff_mentions(t, ids).label("hit")).where(
                t.c.run_id > after, t.c.created_at <= job["cutoff"],
                t.c.user_id.notin_(sorted(ids)),
            ).order_by(t.c.run_id).limit(_BAKEOFF_SCAN_BATCH)).all()
        if not rows:
            return None, changed
        changed += _redact_bakeoff_runs([r.run_id for r in rows if r.hit], job)
        after = rows[-1].run_id
    return after, changed


# ── The page store (trade_page_store) ───────────────────────────────────────

# accounts.DELETED_USER_PLACEHOLDER (accounts imports this module lazily).
_PLACEHOLDER = "deleted_user"
# A served card's fields from the partner's account, removed on a redacted
# card (the c2 list's PG keys), and its blended scores, nulled.
_PAGE_CARD_KEYS_REMOVED = ("likes_you", "standing_offer_reason", "reasons", "rationale",
                           "fit", "breaker",
                           # its second sentence frames the card in the
                           # partner's declared window (trade_narrative)
                           "narrative")
_PAGE_CARD_KEYS_NULLED = ("mismatch_score", "composite_score", "surplus_margin",
                          "base_score", "final_score")


def redact_page_card(card: dict, ids, token: str) -> dict:
    """One stored page card. Its target becomes the token and the placeholder
    name, and the partner's fields go. It never serves again: the serve rules
    drop a token-target card in every I-1 mode, before I-1, and record it as
    a never-delivered withdrawal, reason "partner_deleted" (server.
    _roster_serve_rules; models-lead addendum J4: at prod's mode 1, I-1
    alone would serve it)."""
    if card.get("target_user_id") not in ids:
        return _replace_ids(card, ids, token)
    out = {k: v for k, v in card.items() if k not in _PAGE_CARD_KEYS_REMOVED}
    out.update(target_user_id=token, target_username=_PLACEHOLDER)
    for key in _PAGE_CARD_KEYS_NULLED:
        if key in out:
            out[key] = None
    if isinstance(out.get("match_context"), dict):
        out["match_context"] = {k: v for k, v in out["match_context"].items()
                                if k != "opponent_outlook"}
    return _replace_ids(out, ids, token)


def redact_evidence_blob(blob: dict, ids, token: str) -> dict:
    """A page row's deferred evidence: its rows and ghosts as deck_impressions
    rows are redacted, its candidate set's members, its trade_impressions'
    target (NULL, as deletion does to the table), its run metadata as a pack
    run; then any other mention of an id takes the token."""
    ids = set(ids)
    out = dict(blob)
    rows = [r for r in (out.get("rows") or []) if isinstance(r, dict)]
    for key in ("rows", "ghosts"):
        if isinstance(out.get(key), list):
            out[key] = [redact_row(r, ids, token) if isinstance(r, dict) else r for r in out[key]]
    cs = out.get("candidate_set")
    if isinstance(cs, dict):
        members = _loads(cs.get("candidates_json")) if isinstance(cs.get("candidates_json"), str) else None
        if isinstance(members, list):
            out["candidate_set"] = {**cs, "candidates_json": json.dumps(
                [_redact_member(m, ids, token) if isinstance(m, dict) else m for m in members])}
    ti = out.get("trade_impressions")
    if isinstance(ti, list):
        out["trade_impressions"] = [{**r, "target_user_id": None}
                                    if isinstance(r, dict) and r.get("target_user_id") in ids else r
                                    for r in ti]
    if isinstance(out.get("run_meta"), dict):
        partners = []
        for r in rows:
            f = _loads(r.get("features_json")) if isinstance(r.get("features_json"), str) else r.get("features_json")
            partners.append({"trade_hash": r.get("trade_hash"),
                             "partner_user_id": (f or {}).get("partner_user_id")})
        out["run_meta"] = redact_pack_run(out["run_meta"], partners, ids)
    return _replace_ids(out, ids, token)


def _redact_page_rows(row_ids, job: dict) -> int:
    """Rewrite these page rows, unless a rebuild replaced one meanwhile (its
    deck_job_id moved): that row is re-read and redone."""
    ids, token = set(job["ids"]), job["token"]
    t = db.trade_page_store_table
    changed = 0
    for row_id in row_ids:
        _renew(job)
        for _attempt in range(5):
            with db.engine.begin() as conn:
                row = conn.execute(select(t).where(t.c.id == row_id)).mappings().first()
                if row is None:
                    break
                pages, evidence = row["pages_blob"], row["evidence_blob"]
                try:
                    new_pages = pages
                    if isinstance(pages, dict) and isinstance(pages.get("cards"), list):
                        new_pages = {**pages, "cards": [redact_page_card(c, ids, token)
                                                        if isinstance(c, dict) else c
                                                        for c in pages["cards"]]}
                    new_evidence = (redact_evidence_blob(evidence, ids, token)
                                    if isinstance(evidence, dict) else evidence)
                except Exception as err:   # a poison row: counted, the pass not done
                    _row_failed(job, "trade_page_store", err)
                    break
                if new_pages == pages and new_evidence == evidence:
                    break
                size = len(db.CompressedJSON.encode(new_pages)) + (
                    len(db.CompressedJSON.encode(new_evidence)) if new_evidence is not None else 0)
                if conn.execute(update(t).where(
                        t.c.id == row_id, t.c.deck_job_id == row["deck_job_id"],
                        t.c.built_at == row["built_at"]).values(
                        pages_blob=new_pages, evidence_blob=new_evidence,
                        stored_bytes=size)).rowcount:
                    changed += 1
                    break
        else:
            raise RuntimeError("page row kept changing")
    return changed


def _scrub_page_store(job: dict) -> int:
    """The league pass over the page store (ix_trade_page_store_league)."""
    t = db.trade_page_store_table
    with db.engine.connect() as conn:
        found = conn.execute(select(t.c.id).where(
            t.c.league_id.in_(job["leagues"]), t.c.built_at <= job["cutoff"])).scalars().all()
    return _redact_page_rows(found, job)


def _scan_page_store(job: dict, after: str, budget: "_Budget") -> tuple[str | None, int]:
    """The fallback scan of the page store. Its blobs are compressed, so every
    row is decoded and rewritten if it names an id (one row per user, league
    and scope; pages expire in days)."""
    t = db.trade_page_store_table
    changed = 0
    cursor = int(after or 0)
    while budget.take():
        with db.engine.connect() as conn:
            found = conn.execute(select(t.c.id).where(
                t.c.id > cursor, t.c.built_at <= job["cutoff"],
                t.c.user_id.notin_(sorted(job["ids"])),
            ).order_by(t.c.id).limit(_SCAN_BATCH)).scalars().all()
        if not found:
            return None, changed
        changed += _redact_page_rows(found, job)
        cursor = found[-1]
    return str(cursor), changed


# ── Calibration (grading_sessions / grading_cards) and diagnostics ──────────

def _redact_grading_session(conn, session: dict, job: dict) -> int:
    """One other user's Calibration session. Its hidden source names the
    current arm's partners by id (→ the token). A card is the person's when
    the source's current arm lists it with a deleted partner id, or when it
    names them by one of their names (that league's, or, where the source
    shows they were a partner but no names were captured, any of theirs):
    its partner_name becomes the placeholder. Returns the cards changed."""
    ids, token = set(job["ids"]), job["token"]
    by_league = (job.get("names") or {}).get("leagues") or {}
    names = set(by_league.get(session["league_id"], ()))
    gs, gc = db.grading_sessions_table, db.grading_cards_table
    source = _loads(session["source_json"])
    theirs = set()
    if isinstance(source, dict):
        current = (source.get("current") or {}).get("cards") or []
        theirs = {(frozenset(c.get("give") or ()), frozenset(c.get("receive") or ()))
                  for c in current if isinstance(c, dict) and c.get("partner_id") in ids}
        if theirs and not names:
            # A league the person had left (no names captured there), but the
            # session's own source shows they were a partner in it: their
            # names from every league.
            names = {n for ns in by_league.values() for n in ns}
        new = _replace_ids(source, ids, token)
        if new != source:
            conn.execute(update(gs).where(gs.c.session_id == session["session_id"])
                         .values(source_json=json.dumps(new, sort_keys=True)))
    changed = 0
    for card in conn.execute(select(gc.c.card_id, gc.c.trade_json, gc.c.arms_json).where(
            gc.c.session_id == session["session_id"])).mappings():
        trade, arms = _loads(card["trade_json"]), _loads(card["arms_json"])
        values = {}
        if isinstance(trade, dict):
            key = (frozenset(a.get("id") for a in trade.get("give") or () if isinstance(a, dict)),
                   frozenset(a.get("id") for a in trade.get("receive") or () if isinstance(a, dict)))
            if key in theirs or trade.get("partner_name") in names:
                if trade.get("partner_name") != _PLACEHOLDER:
                    values["trade_json"] = json.dumps({**trade, "partner_name": _PLACEHOLDER},
                                                      sort_keys=True)
        if isinstance(arms, dict):
            new_arms = _replace_ids(arms, ids, token)
            if new_arms != arms:
                values["arms_json"] = json.dumps(new_arms, sort_keys=True)
        if values:
            conn.execute(update(gc).where(gc.c.card_id == card["card_id"]).values(**values))
            changed += 1
    return changed


def _scrub_grading(job: dict) -> int:
    """The league pass over Calibration sessions in the captured leagues."""
    gs = db.grading_sessions_table
    changed = 0
    _renew(job)
    with db.engine.begin() as conn:
        for session in conn.execute(select(gs.c.session_id, gs.c.league_id, gs.c.source_json).where(
                gs.c.league_id.in_(job["leagues"]), gs.c.created_at <= job["cutoff"],
                gs.c.user_id.notin_(sorted(job["ids"])))).mappings().all():
            changed += _redact_grading_session(conn, session, job)
    return changed


def _scan_grading(job: dict, after: str, budget: "_Budget") -> tuple[str | None, int]:
    """The fallback scan of Calibration sessions whose source names an id (a
    league the person had left)."""
    ids = set(job["ids"])
    gs = db.grading_sessions_table
    changed = 0
    while budget.take():
        with db.engine.begin() as conn:
            rows = conn.execute(select(gs.c.session_id, gs.c.league_id, gs.c.source_json,
                                       _mentions(gs.c.source_json, ids).label("hit")).where(
                gs.c.session_id > after, gs.c.created_at <= job["cutoff"],
                gs.c.user_id.notin_(sorted(ids)),
            ).order_by(gs.c.session_id).limit(_SCAN_BATCH)).mappings().all()
            if not rows:
                return None, changed
            for row in rows:
                if row["hit"]:
                    changed += _redact_grading_session(conn, row, job)
        after = rows[-1]["session_id"]
    return after, changed


# Diagnostics expire at 14 days (FTF_DECK_DIAGNOSTIC_RETENTION_DAYS); one
# that has outlived 30 (a purge that fell behind) and names the person goes
# (legal R28.22, c3 #13).
_DIAGNOSTICS_OVERDUE = timedelta(days=30)


def _scan_diagnostics(job: dict, after: str, budget: "_Budget") -> tuple[str | None, int]:
    ids = set(job["ids"])
    t = db.deck_diagnostic_snapshots_table
    overdue = _iso(datetime.now(timezone.utc) - _DIAGNOSTICS_OVERDUE)
    deleted = 0
    while budget.take():
        with db.engine.begin() as conn:
            rows = conn.execute(select(t.c.snapshot_id, _mentions(t.c.payload_json, ids).label("hit")).where(
                t.c.snapshot_id > after, t.c.created_at < overdue,
            ).order_by(t.c.snapshot_id).limit(_SCAN_BATCH)).all()
            if not rows:
                return None, deleted
            hits = [r.snapshot_id for r in rows if r.hit]
            if hits:
                deleted += conn.execute(delete(t).where(t.c.snapshot_id.in_(hits))).rowcount or 0
        after = rows[-1].snapshot_id
    return after, deleted


# ── Other users' notifications and events (head-eng, 10-31; release-lead's
# #557 QA): a match / disposition notification names its partner by username
# in its title, body and metadata; an event's props can carry a partner id.

def redact_notification(row: dict, ids, token: str, usernames) -> dict | None:
    """One other user's notification, or None when it doesn't name the person.
    It's theirs when its metadata names them by username (unique) or holds one
    of their ids: their username becomes the placeholder in the title, body
    and metadata, and every id the token."""
    meta = _loads(row["metadata_json"]) if isinstance(row["metadata_json"], str) else None
    meta = meta if isinstance(meta, dict) else {}
    named = meta.get("partner_username") in usernames
    text_ids = any(pid in (row["metadata_json"] or "") for pid in ids)
    if not named and not text_ids:
        return None
    title, body = row["title"] or "", row["body"] or ""
    for name in (usernames if named else ()):
        title = title.replace(f"@{name}", f"@{_PLACEHOLDER}")
        body = body.replace(f"@{name}", f"@{_PLACEHOLDER}")
    new_meta = _replace_ids(meta, set(ids), token)
    if named:
        new_meta["partner_username"] = _PLACEHOLDER
    return {"title": title if row["title"] is not None else None,
            "body": body if row["body"] is not None else None,
            "metadata_json": json.dumps(new_meta)}


def _scan_notifications(job: dict, after: str, budget: "_Budget") -> tuple[str | None, int]:
    ids, token = set(job["ids"]), job["token"]
    usernames = set((job.get("names") or {}).get("usernames") or ())
    t = db.notifications_table
    terms = sorted(ids) + [f'"partner_username": "{n}"' for n in sorted(usernames)]
    hit = or_(*[t.c.metadata_json.contains(term, autoescape=True) for term in terms])
    changed, cursor = 0, int(after or 0)
    while budget.take():
        with db.engine.begin() as conn:
            rows = conn.execute(select(t.c.id, t.c.title, t.c.body, t.c.metadata_json,
                                       hit.label("hit")).where(
                t.c.id > cursor, t.c.user_id.notin_(sorted(ids)),
            ).order_by(t.c.id).limit(_SCAN_BATCH)).mappings().all()
            if not rows:
                return None, changed
            for row in rows:
                if not row["hit"]:
                    continue
                try:
                    values = redact_notification(row, ids, token, usernames)
                except Exception as err:   # a poison row: counted, the pass not done
                    _row_failed(job, "notifications", err)
                    continue
                if values:
                    conn.execute(update(t).where(t.c.id == row["id"]).values(**values))
                    changed += 1
        cursor = rows[-1]["id"]
    return str(cursor), changed


def _scan_user_events(job: dict, after: str, budget: "_Budget") -> tuple[str | None, int]:
    """Other users' events whose props name a deleted id: the token."""
    ids, token = set(job["ids"]), job["token"]
    t = db.user_events_table
    changed, cursor = 0, int(after or 0)
    while budget.take():
        with db.engine.begin() as conn:
            rows = conn.execute(select(t.c.id, t.c.props, _mentions(t.c.props, ids).label("hit")).where(
                t.c.id > cursor, t.c.user_id.notin_(sorted(ids)),
            ).order_by(t.c.id).limit(_SCAN_BATCH)).mappings().all()
            if not rows:
                return None, changed
            for row in rows:
                if not row["hit"]:
                    continue
                props = _loads(row["props"])
                if not isinstance(props, (dict, list)):
                    continue
                new = _replace_ids(props, ids, token)
                if new != props:
                    conn.execute(update(t).where(t.c.id == row["id"]).values(props=json.dumps(new)))
                    changed += 1
        cursor = rows[-1]["id"]
    return str(cursor), changed


# The DB phase, in order (scope §0.2). First the league pass over the captured leagues, then the
# fallback scans of whole stores, resumable from a cursor on the job row.
_STORES = (
    ("deck_impressions", _scrub_impressions),
    ("deck_candidate_sets", _scrub_candidate_sets),
    # bakeoff_runs has no league pass: a LIKE over its megabyte rows isn't
    # bounded, and the bounded scan below covers every row (#557 QA P2).
    ("deck_evidence_packs", _scrub_packs),
    ("trade_page_store", _scrub_page_store),
    ("grading_cards", _scrub_grading),
)
_SCANS = (
    ("deck_impressions", _scan_impressions),
    ("deck_candidate_sets", _scan_candidate_sets),
    ("bakeoff_runs", _scan_bakeoff_runs),
    ("deck_evidence_packs", _scan_packs),
    ("trade_page_store", _scan_page_store),
    ("grading_cards", _scan_grading),
    ("deck_diagnostic_snapshots", _scan_diagnostics),
    ("notifications", _scan_notifications),
    ("user_events", _scan_user_events),
)


def _job(row) -> dict:
    deleted = datetime.fromisoformat(row["deleted_at"])
    return {**dict(row), "ids": json.loads(row["partner_ids_json"]),
            "leagues": json.loads(row["league_ids_json"]),
            "names": json.loads(row.get("partner_names_json") or "{}"),
            # A deck's rows carry its first delivery as served_at, so a deck
            # built before the deletion and first delivered after it is told
            # apart only by the grace: decks served up to IN_FLIGHT_GRACE
            # after the deletion are scrubbed, later ones never.
            "cutoff": _iso(deleted + IN_FLIGHT_GRACE)}


def _db_due(row, now: datetime) -> bool:
    """A full DB pass is due: never run at this SCRUB_VERSION, or the last one
    ran before IN_FLIGHT_GRACE after the deletion and that time has come."""
    if row["db_version"] < SCRUB_VERSION or row["db_done_at"] is None:
        return True
    grace = datetime.fromisoformat(row["deleted_at"]) + IN_FLIGHT_GRACE
    return now >= grace and datetime.fromisoformat(row["db_done_at"]) < grace


class _LeaseLost(Exception):
    """Another runner holds the job now (this run outlasted its lease)."""


class _Lease:
    """A job's lease while one run works it (#557 QA P2): renewed by CAS on
    every scan page and league store, and every write of the run is
    conditioned on it, so a runner that outlasted it writes nothing."""

    def __init__(self, job_id: str, held: str, now: datetime):
        self.job_id, self.held, self.now, self.t0 = job_id, held, now, time.monotonic()

    def write(self, **values) -> bool:
        t = db.deletion_scrub_jobs_table
        with db.engine.begin() as conn:
            return bool(conn.execute(update(t).where(
                t.c.job_id == self.job_id, t.c.claimed_until == self.held).values(**values)).rowcount)

    def renew(self) -> None:
        held = _iso(self.now + timedelta(seconds=time.monotonic() - self.t0) + LEASE)
        if held != self.held:
            if not self.write(claimed_until=held):
                raise _LeaseLost()
            self.held = held


class _Budget:
    """The scan pages a run has left; taking one renews the job's lease."""

    def __init__(self, pages: int, lease: _Lease):
        self.pages, self.lease = pages, lease

    def take(self) -> bool:
        if self.pages <= 0:
            return False
        self.pages -= 1
        self.lease.renew()
        return True


def _claim_one(now: datetime, skip: set) -> dict | None:
    """One due job this caller now holds, by a CAS on its lease (#557 QA P2:
    claiming every due job at once let leases run out while the others
    waited). Of two runners that read the same row, one wins."""
    t = db.deletion_scrub_jobs_table
    with db.engine.connect() as conn:
        rows = conn.execute(select(t).where(or_(t.c.claimed_until.is_(None),
                                                t.c.claimed_until < _iso(now)))
                            .order_by(t.c.deleted_at)).mappings().all()
    for row in rows:
        if row["job_id"] in skip or not _db_due(row, now):
            continue
        held = _take(row, now)
        if held is not None:
            return {**_job(row), "lease": _Lease(row["job_id"], held, now)}
    return None


def _take(row, now: datetime) -> str | None:
    """Take the row's lease if it is still the one read (CAS); the new
    lease's value, or None when another runner took it first."""
    t = db.deletion_scrub_jobs_table
    lease = (t.c.claimed_until.is_(None) if row["claimed_until"] is None
             else t.c.claimed_until == row["claimed_until"])
    held = _iso(now + LEASE)
    with db.engine.begin() as conn:
        got = conn.execute(update(t).where(t.c.job_id == row["job_id"], lease).values(
            claimed_until=held, attempts=t.c.attempts + 1)).rowcount
    return held if got else None


def _short(job_id: str) -> str:
    return job_id[:8]


# A pass that left rows it couldn't redact (a poison row) is retried from the
# start after this, not every tick; past 24 h the tick's count says so.
_ROW_FAILURE_BACKOFF = timedelta(hours=1)


def _run_db(job: dict, now: datetime) -> bool:
    """One run of the job's DB phase: the league pass when a pass starts,
    then the fallback scans for up to _SCAN_PAGES_PER_RUN pages. A pass that
    isn't finished keeps its cursor on the row (scan_json) and the next run
    resumes it; True only when the whole pass is done. Every write is a CAS
    on the run's lease."""
    lease = job["lease"]
    state = _loads(job.get("scan_json"))
    if not isinstance(state, dict) or state.get("version") != SCRUB_VERSION:
        state = None
    job["failures"] = 0
    try:
        if state is None:
            counts = {}
            for name, scrub in _STORES:
                lease.renew()
                counts[name] = scrub(job)
            state = {"version": SCRUB_VERSION, "scan": 0, "after": "", "counts": counts,
                     "failures": 0}
        budget = _Budget(_SCAN_PAGES_PER_RUN, lease)
        after = None
        while state["scan"] < len(_SCANS):
            name, scan = _SCANS[state["scan"]]
            after, changed = scan(job, state["after"], budget)
            key = name + "_scan"
            state["counts"][key] = state["counts"].get(key, 0) + changed
            if after is not None:
                break
            state["scan"], state["after"] = state["scan"] + 1, ""
        if after is not None:
            state["after"] = after
        state["failures"] = state.get("failures", 0) + job["failures"]
    except _LeaseLost:
        log.warning("[scrub] job=%s lease lost: another runner holds it", _short(job["job_id"]))
        return False
    except Exception as err:      # the class only: a message may quote an id
        lease.write(claimed_until=None, last_error=type(err).__name__)
        log.warning("[scrub] job=%s db pass failed: %s", _short(job["job_id"]), type(err).__name__)
        return False
    if state["scan"] < len(_SCANS):
        lease.write(scan_json=json.dumps(state), claimed_until=None, last_error=None)
        return False
    if state["failures"]:
        # Rows it couldn't redact: the whole pass again later, never done.
        lease.write(scan_json=None, claimed_until=_iso(now + _ROW_FAILURE_BACKOFF),
                    last_error="row_failures")
        log.warning("[scrub] job=%s pass had %d failed row redactions; retried in %s",
                    _short(job["job_id"]), state["failures"], _ROW_FAILURE_BACKOFF)
        return False
    values = dict(db_version=SCRUB_VERSION, db_done_at=_iso(now), scan_json=None,
                  claimed_until=None, last_error=None)
    if 0 < job["db_version"] < SCRUB_VERSION:
        values["model_done_at"] = None    # a new version: the model store again too
    if not lease.write(**values):
        log.warning("[scrub] job=%s lease lost before its done write", _short(job["job_id"]))
        return False
    log.info("[scrub] job=%s db_done version=%d counts=%s", _short(job["job_id"]),
             SCRUB_VERSION, json.dumps(state["counts"], sort_keys=True))
    return True


def run_pending(now: datetime | None = None) -> int:
    """Run every due DB pass this caller can claim, one job at a time;
    returns how many finished. The deletion route's kicked thread and the
    cleanup loop call it."""
    now = now or datetime.now(timezone.utc)
    done = _db_pass(now)
    _finish(now)
    return done


def _db_pass(now: datetime) -> int:
    done, seen = 0, set()
    while (job := _claim_one(now, seen)) is not None:
        seen.add(job["job_id"])
        done += _run_db(job, now)
    return done


def kick() -> None:
    """Start the DB phase now, off the request (the deletion route). The
    test suite sets FTF_DISABLE_DELETION_SCRUB_KICK (a thread would outlive a
    test's engine); prod never does, and the cleanup loop retries either way."""
    if os.environ.get("FTF_DISABLE_DELETION_SCRUB_KICK") == "1":
        return
    def run():
        try:
            run_pending()
        except Exception as err:      # the class only: a DB error's text quotes its ids
            log.error("[scrub] kicked pass failed: %s", type(err).__name__)
    threading.Thread(target=run, name="deletion-scrub", daemon=True).start()


def _finish(now: datetime) -> int:
    """Delete the rows whose scrub is done (legal (ix))."""
    if not COMPLETE:
        return 0
    t = db.deletion_scrub_jobs_table
    finished = 0
    with db.engine.begin() as conn:
        for row in conn.execute(select(t).where(
                t.c.db_version == SCRUB_VERSION, t.c.model_done_at.isnot(None))).mappings():
            # Done means the grace pass ran too (decks in flight at deletion).
            grace = datetime.fromisoformat(row["deleted_at"]) + IN_FLIGHT_GRACE
            if (row["scan_json"] is None and row["db_done_at"] is not None
                    and datetime.fromisoformat(row["db_done_at"]) >= grace):
                finished += conn.execute(delete(t).where(t.c.job_id == row["job_id"])).rowcount or 0
    return finished


# ── The daily-tick step ─────────────────────────────────────────────────────

def tick(now: datetime) -> tuple[str, dict]:
    """The daily-tick step `deletion_scrub`, run BEFORE value_model_refit
    (models-eng #542): any due DB pass, then the model store for every row
    whose DB pass is current (so the refit after it trains on scrubbed
    data), then the finished rows go and the unfinished are counted. Never
    raises: the runner would log the error's text, which may quote an id."""
    try:
        return _tick(now)
    except Exception as err:
        return "error", {"error": type(err).__name__}


def _tick(now: datetime) -> tuple[str, dict]:
    from .eval import redaction
    _db_pass(now)
    t = db.deletion_scrub_jobs_table
    with db.engine.connect() as conn:
        rows = [_job(r) for r in conn.execute(select(t)).mappings()]
    # A pass that ran every store but left poison rows (row_failures) has
    # still scrubbed the rest, and the model store needs only the ids, so a
    # permanent poison row never blocks it (#557 re-QA P3).
    ready = [r for r in rows if r["model_done_at"] is None
             and ((r["db_version"] == SCRUB_VERSION and r["db_done_at"] is not None)
                  or r["last_error"] == "row_failures")]
    detail = {"jobs": len(rows), "model_rows": len(ready)}
    model_error = None
    if ready:
        tokens = {pid: r["token"] for r in ready for pid in r["ids"]}
        try:
            detail["model_changed"] = redaction.redact_model_store(tokens)
        except Exception as err:      # the class only: a message may quote an id
            model_error = type(err).__name__
            with db.engine.begin() as conn:
                conn.execute(update(t).where(t.c.job_id.in_([r["job_id"] for r in ready]))
                             .values(last_error=model_error))
        else:
            with db.engine.begin() as conn:
                conn.execute(update(t).where(t.c.job_id.in_([r["job_id"] for r in ready]))
                             .values(model_done_at=_iso(now)))
    detail["finished"] = _finish(now)
    with db.engine.connect() as conn:
        left = conn.execute(select(t.c.deleted_at)).scalars().all()
    old = [datetime.fromisoformat(d) for d in left
           if datetime.fromisoformat(d) < now - ALERT_AFTER]
    if old:
        oldest = now - min(old)
        log.error("[scrub] unfinished jobs=%d oldest_h=%d", len(old), oldest // timedelta(hours=1))
    detail["unfinished_24h"] = len(old)
    if model_error:
        detail["model_error"] = model_error
        return "error", detail
    return "ok", detail
