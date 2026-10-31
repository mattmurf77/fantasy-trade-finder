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
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, select, update

from . import database as db
from .eval.contract import REDACTED_PARTNER_PREFIX

log = logging.getLogger("trade_finder")

# Bump when a store or field is added: a row whose db_version is older runs
# its DB phase again.
SCRUB_VERSION = 1
# False until every store in the scope is built (scope §5's staging). Until
# then a finished row is kept, so the later stages scrub its deletion too.
COMPLETE = False

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
_VALUATION_KEYS_REMOVED = ("partner_board", "mutual", "counterparty", "preference_priority",
                           "counterparty_benefits")
_VALUATION_ASSET_KEYS_REMOVED = ("partner_raw_value", "partner_effective_value",
                                 "partner_confidence", "counterparty_personal",
                                 "counterparty_source")
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


def enqueue(conn, user_ids, league_ids, now: datetime | None = None) -> str:
    """Insert the job row in the caller's (the deletion's) transaction and
    return its token."""
    token = new_token()
    conn.execute(db.deletion_scrub_jobs_table.insert().values(
        job_id=uuid.uuid4().hex, token=token,
        partner_ids_json=json.dumps(sorted(user_ids)),
        league_ids_json=json.dumps(sorted(league_ids)),
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


def _redact_impressions(impression_ids, job: dict) -> int:
    """Redact these deck_impressions rows (any that still name a deleted id)."""
    ids, token = set(job["ids"]), job["token"]
    imp = db.deck_impressions_table
    changed = 0
    for start in range(0, len(impression_ids), _BATCH):
        with db.engine.begin() as conn:
            rows = conn.execute(select(imp.c.impression_id, imp.c.features_json,
                                       imp.c.valuation_json).where(
                imp.c.impression_id.in_(impression_ids[start:start + _BATCH]))).all()
            for impression_id, raw_features, raw_valuation in rows:
                features = _loads(raw_features)
                if not isinstance(features, dict):
                    continue
                new = redact_features(features, ids, token)
                if new == features:
                    continue
                values = {"features_json": json.dumps(new)}
                if features.get("partner_user_id") in ids:
                    values.update({c: None for c in _COLUMNS_NULLED})
                    valuation = _loads(raw_valuation)
                    if valuation is not None:
                        values["valuation_json"] = json.dumps(redact_valuation(valuation))
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


def _scan_impressions(job: dict, after: str, budget: list) -> tuple[str | None, int]:
    """The fallback scan (head-eng, 10-31: a league the person left before
    deleting isn't captured): every deck_impressions row up to the cutoff, in
    keyset pages of _SCAN_BATCH by impression_id, while `budget` (a one-item
    list of pages left) lasts. Returns (the cursor to resume from, or None at
    the end; rows changed)."""
    ids = set(job["ids"])
    imp = db.deck_impressions_table
    changed = 0
    while budget[0] > 0:
        budget[0] -= 1
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
            values["candidates_packed"] = evidence_pack.pack_candidates(run, new).candidates_packed
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
        with db.engine.begin() as conn:
            for row in conn.execute(select(*_candidate_columns()).where(
                    cs.c.user_id == viewer, cs.c.league_id == league_id,
                    cs.c.created_at <= job["cutoff"])).all():
                changed += _redact_candidate_set(conn, row, job)
    return changed


def _scan_candidate_sets(job: dict, after: str, budget: list) -> tuple[str | None, int]:
    """The fallback scan of deck_candidate_sets, as _scan_impressions. A
    packed set is compressed, so it's decoded here to be checked (one row
    per deck, a few KB)."""
    ids = set(job["ids"])
    cs = db.deck_candidate_sets_table
    changed = 0
    while budget[0] > 0:
        budget[0] -= 1
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


def redact_bakeoff_config(config, ids, token: str):
    """A bakeoff run's config_json: any id becomes the token, and the owner
    request's frozen input (every member's board, sources, preferences and
    outlooks) loses the person's account fields (legal f's trace, 10-31)."""
    if not isinstance(config, dict):
        return config
    out = _replace_ids(config, set(ids), token)
    if isinstance(out.get("owner_request"), dict):
        out["owner_request"] = _redact_owner_request(out["owner_request"], token)
    return out


def _redact_bakeoff_runs(run_ids, job: dict) -> int:
    ids, token = set(job["ids"]), job["token"]
    t = db.bakeoff_runs_table
    changed = 0
    for start in range(0, len(run_ids), _BATCH):
        with db.engine.begin() as conn:
            for run_id, raw in conn.execute(select(t.c.run_id, t.c.config_json).where(
                    t.c.run_id.in_(run_ids[start:start + _BATCH]))).all():
                config = _loads(raw)
                new = redact_bakeoff_config(config, ids, token)
                if new != config:
                    conn.execute(update(t).where(t.c.run_id == run_id)
                                 .values(config_json=json.dumps(new, default=str)))
                    changed += 1
    return changed


def _scrub_bakeoff_runs(job: dict) -> int:
    """The league pass over bakeoff_runs (ix_bakeoff_runs_league)."""
    ids = set(job["ids"])
    t = db.bakeoff_runs_table
    with db.engine.connect() as conn:
        found = conn.execute(select(t.c.run_id).where(
            t.c.league_id.in_(job["leagues"]), t.c.created_at <= job["cutoff"],
            t.c.user_id.notin_(sorted(ids)), _mentions(t.c.config_json, ids))).scalars().all()
    return _redact_bakeoff_runs(found, job)


def _scan_bakeoff_runs(job: dict, after: str, budget: list) -> tuple[str | None, int]:
    """The fallback scan of bakeoff_runs, as _scan_impressions."""
    ids = set(job["ids"])
    t = db.bakeoff_runs_table
    changed = 0
    while budget[0] > 0:
        budget[0] -= 1
        with db.engine.connect() as conn:
            rows = conn.execute(select(t.c.run_id, _mentions(t.c.config_json, ids).label("hit")).where(
                t.c.run_id > after, t.c.created_at <= job["cutoff"],
                t.c.user_id.notin_(sorted(ids)),
            ).order_by(t.c.run_id).limit(_SCAN_BATCH)).all()
        if not rows:
            return None, changed
        changed += _redact_bakeoff_runs([r.run_id for r in rows if r.hit], job)
        after = rows[-1].run_id
    return after, changed


# The DB phase, in order (scope §0.2; packs and the page store come with
# SCRUB_VERSION 2). First the league pass over the captured leagues, then the
# fallback scans of whole stores, resumable from a cursor on the job row.
_STORES = (
    ("deck_impressions", _scrub_impressions),
    ("deck_candidate_sets", _scrub_candidate_sets),
    ("bakeoff_runs", _scrub_bakeoff_runs),
)
_SCANS = (
    ("deck_impressions", _scan_impressions),
    ("deck_candidate_sets", _scan_candidate_sets),
    ("bakeoff_runs", _scan_bakeoff_runs),
)


def _job(row) -> dict:
    deleted = datetime.fromisoformat(row["deleted_at"])
    return {**dict(row), "ids": json.loads(row["partner_ids_json"]),
            "leagues": json.loads(row["league_ids_json"]),
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


def _claim(now: datetime) -> list[dict]:
    """The due rows this caller now holds, each by a CAS on its lease, so two
    runners (a deploy overlap, the kicked thread and the cleanup loop) never
    work one row at once."""
    t = db.deletion_scrub_jobs_table
    with db.engine.connect() as conn:
        rows = conn.execute(select(t).where(or_(t.c.claimed_until.is_(None),
                                                t.c.claimed_until < _iso(now)))).mappings().all()
    return [_job(row) for row in rows if _db_due(row, now) and _take(row, now)]


def _take(row, now: datetime) -> bool:
    """Take the row's lease if it is still the one read (CAS): of two
    runners that read the same row, one wins."""
    t = db.deletion_scrub_jobs_table
    lease = (t.c.claimed_until.is_(None) if row["claimed_until"] is None
             else t.c.claimed_until == row["claimed_until"])
    with db.engine.begin() as conn:
        return bool(conn.execute(update(t).where(t.c.job_id == row["job_id"], lease).values(
            claimed_until=_iso(now + LEASE), attempts=t.c.attempts + 1)).rowcount)


def _short(job_id: str) -> str:
    return job_id[:8]


def _run_db(job: dict, now: datetime) -> bool:
    """One run of the job's DB phase: the league pass when a pass starts,
    then the fallback scans for up to _SCAN_PAGES_PER_RUN pages. A pass that
    isn't finished keeps its cursor on the row (scan_json) and the next run
    resumes it; True only when the whole pass is done."""
    t = db.deletion_scrub_jobs_table
    state = _loads(job.get("scan_json"))
    if not isinstance(state, dict) or state.get("version") != SCRUB_VERSION:
        state = None
    try:
        if state is None:
            state = {"version": SCRUB_VERSION, "scan": 0, "after": "",
                     "counts": {name: scrub(job) for name, scrub in _STORES}}
        budget = [_SCAN_PAGES_PER_RUN]
        while state["scan"] < len(_SCANS):
            name, scan = _SCANS[state["scan"]]
            after, changed = scan(job, state["after"], budget)
            key = name + "_scan"
            state["counts"][key] = state["counts"].get(key, 0) + changed
            if after is not None:
                break
            state["scan"], state["after"] = state["scan"] + 1, ""
        else:
            after = None
        if after is not None:
            state["after"] = after
    except Exception as err:      # the class only: a message may quote an id
        with db.engine.begin() as conn:
            conn.execute(update(t).where(t.c.job_id == job["job_id"]).values(
                claimed_until=None, last_error=type(err).__name__))
        log.warning("[scrub] job=%s db pass failed: %s", _short(job["job_id"]), type(err).__name__)
        return False
    if state["scan"] < len(_SCANS):
        with db.engine.begin() as conn:
            conn.execute(update(t).where(t.c.job_id == job["job_id"]).values(
                scan_json=json.dumps(state), claimed_until=None, last_error=None))
        return False
    with db.engine.begin() as conn:
        conn.execute(update(t).where(t.c.job_id == job["job_id"]).values(
            db_version=SCRUB_VERSION, db_done_at=_iso(now), scan_json=None,
            claimed_until=None, last_error=None))
    log.info("[scrub] job=%s db_done version=%d counts=%s", _short(job["job_id"]),
             SCRUB_VERSION, json.dumps(state["counts"], sort_keys=True))
    return True


def run_pending(now: datetime | None = None) -> int:
    """Run every due DB pass this caller can claim; returns how many finished.
    The deletion route's kicked thread and the cleanup loop call it."""
    now = now or datetime.now(timezone.utc)
    done = _db_pass(now)
    _finish(now)
    return done


def _db_pass(now: datetime) -> int:
    return sum(_run_db(job, now) for job in _claim(now))


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
            if not _db_due(row, now):
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
    ready = [r for r in rows if r["model_done_at"] is None
             and r["db_version"] == SCRUB_VERSION and r["db_done_at"] is not None]
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
