"""Calibration (in-app blind grading) — value-core Gate 2.

docs/plans/blind-grading/. Graders score cards from today's engine and the value
core without knowing which made each card. This module owns arm sourcing, merge,
shuffle, THE neutral formatter (neutral_trade), validation and scoring. Routes in
backend/server.py only gate, gather ServerInputs and map GradingError to JSON.

Imports backend.database at module level; backend.eval.value_core_bench,
backend.value_core.* and backend.trade_service lazily inside functions.
NEVER imports backend.server or backend.tools.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import random
import secrets
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Mapping, Sequence

from . import database as db

log = logging.getLogger(__name__)

VERSION = "blind-grading-1"
ARMS: tuple[str, ...] = ("current", "value_core")
TAGS: tuple[str, ...] = ("overpay", "they_wont_accept", "junk_filler", "too_small",
                         "wrong_for_my_window", "wrong_for_their_window", "same_guy_again")
PER_ARM = 20            # cards taken from each arm
MIN_PER_ARM = 10        # fewer usable cards in an arm ⇒ refuse the session
MAX_DECK_AGE_DAYS = 14  # the current arm's deck must be at most this old (7 -> 14 on 2026-10-02:
                        # 7 days left only 4 users eligible in prod, 14 days 8; moved players drop anyway)
TARGET_MEAN = 4.0       # value-core PRD §6; reported, never enforced


class GradingError(Exception):
    """A refusal the route returns as (jsonify({"error": code, **detail}), status)."""

    def __init__(self, code: str, status: int, **detail: object) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.detail: dict = dict(detail)


@dataclass(frozen=True)
class ServerInputs:
    """League facts only server.py can supply (it owns the Sleeper client and caches)."""
    lineup_slots: tuple[str, ...] | None      # server._league_lineup_slots; None ⇒ league_record default
    max_players: int | None                   # server._sleeper_roster_limit; None ⇒ size rule skipped
    standings: Mapping[str, object]           # {league user id: value_core.types.Standing}; {} ⇒ none
    completed_weeks: int
    untouchable_ids: frozenset[str] = frozenset()
    not_interested_ids: frozenset[str] = frozenset()


def start_session(*, user_id: str, league_user_id: str, league_id: str,
                  now: datetime | None = None, seed: int | None = None) -> dict:
    """FAST, request-thread half (lead change 2026-10-02, §3.3). Resume the caller's
    open-or-building session for the league, or: check the league is synced, select the
    current-engine arm from deck_impressions (raises needs_fresh_deck), and insert a
    grading_sessions row with status "building" holding those selected trades in
    source_json. No value core, no network. Returns {"session": SessionView,
    "resumed": bool, "needs_build": bool} (§3.2). Raises GradingError:
    league_not_synced 409 · needs_fresh_deck 409."""
    now = now or datetime.now(timezone.utc)
    existing = db.load_open_grading_session(user_id, league_id)       # building | open
    if existing is not None:
        # needs_build is True for a still-"building" row so the route can re-kick a build
        # orphaned by a restart; finish_grading_session_build guards on status, so a
        # second concurrent build writes nothing.
        return {"session": session_view(existing), "resumed": True,
                "needs_build": existing["status"] == "building"}
    job_id, served_at, rows = db.load_grading_legacy_deck(user_id, league_id)
    inputs, seat, catalog = _league_inputs(league_id, league_user_id, now)
    current, cur_meta = select_current_cards(job_id, served_at, rows, viewer_id=seat,
                                             catalog=catalog, now=now)
    seed = secrets.randbits(63) if seed is None else seed
    source = {"version": VERSION, "seat": seat,
              "scoring_format": inputs["league_row"].get("default_scoring") or "1qb_ppr",
              "current": {**cur_meta,
                          "cards": [{"partner_id": c.partner_id, "give": list(c.give),
                                     "receive": list(c.receive), "provenance": dict(c.provenance)}
                                    for c in current]}}
    session_row = {"session_id": new_id(), "user_id": user_id, "league_id": league_id,
                   "status": "building", "seed": str(seed), "created_at": now.isoformat(),
                   "completed_at": None, "counts_json": "{}",
                   "source_json": json.dumps(source, sort_keys=True), "error_json": None}
    db.insert_grading_session(session_row, [])
    return {"session": session_view(session_row), "resumed": False, "needs_build": True}


def pregenerate(*, now: datetime | None = None) -> dict:
    """One-shot Calibration pre-generation (operator 2026-10-02: "generate a calibration
    deck for all users who have downloaded the app"). FAST half only: start_session for
    every candidate with a fresh enough current-engine deck (seat = user_id); the caller
    builds the returned sessions in the background. Never raises per candidate.
    Returns {"candidates", "to_build": [{session_id, user_id, league_id, platform}],
    "resumed_open", "skipped": {code: n}}."""
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=MAX_DECK_AGE_DAYS)).isoformat()
    candidates = db.list_grading_candidates(since)
    to_build, resumed_open, skipped = [], 0, Counter()
    for c in candidates:
        try:
            out = start_session(user_id=c["user_id"], league_user_id=c["user_id"],
                                league_id=c["league_id"], now=now)
        except GradingError as err:
            skipped[err.code] += 1
            continue
        except Exception:
            log.exception("blind-grading: pregenerate start failed user=%s league=%s",
                          c["user_id"], c["league_id"])
            skipped["error"] += 1
            continue
        if out["needs_build"]:
            to_build.append({"session_id": out["session"]["session_id"], **c})
        else:
            resumed_open += 1
    return {"candidates": len(candidates), "to_build": to_build,
            "resumed_open": resumed_open, "skipped": dict(skipped)}


def build_session(*, session_id: str, server: ServerInputs, engine: Callable | None = None,
                  now: datetime | None = None) -> None:
    """SLOW, background-thread half. Runs the value core, merges duplicates, shuffles,
    writes grading_cards and flips the session to "open". On GradingError (value_core_too_few)
    or any exception (value_core_failed) it flips the session to "failed" with
    error_json = {"code": ..., **detail} and never raises. Idempotent: a session that
    is not "building" is left alone."""
    try:
        row = db.load_grading_session(session_id)
        if row is None or row["status"] != "building":
            return
        now = now or datetime.now(timezone.utc)
        source = json.loads(row["source_json"])
        seat = source["seat"]
        inputs, _, catalog = _league_inputs(row["league_id"], seat, now)
        cur_meta = source["current"]
        current = [ArmCard("current", c["partner_id"], tuple(c["give"]), tuple(c["receive"]),
                           c["provenance"]) for c in cur_meta["cards"]]
        vc, vc_meta = run_value_core(inputs, seat=seat, server=server, engine=engine)
        order = shuffle_cards(merge_cards([*current, *vc]), int(row["seed"]))
        cards = [{"card_id": new_id(), "session_id": session_id, "user_id": row["user_id"],
                  "position": pos,
                  "arms_json": json.dumps(m["arms"], sort_keys=True),
                  "trade_json": json.dumps(neutral_trade(m["partner_id"], m["give"], m["receive"],
                                                         catalog), sort_keys=True),
                  "grade": None, "skipped": 0, "tags_json": "[]", "graded_at": None}
                 for pos, m in enumerate(order, 1)]
        counts = {"total": len(order), "current": len(current), "value_core": len(vc),
                  "shared": sum(1 for m in order if len(m["arms"]) > 1),
                  "current_candidates": cur_meta["candidates"],
                  "current_dropped_stale": cur_meta["dropped_stale"],
                  "current_dropped_unknown": cur_meta["dropped_unknown"],
                  "value_core_pool": vc_meta["pool"]}
        final_source = {"version": source["version"], "seat": seat,
                        "scoring_format": source["scoring_format"],
                        "current": {"deck_job_id": cur_meta["deck_job_id"],
                                    "served_at": cur_meta["served_at"]},
                        "value_core": vc_meta}
        if db.finish_grading_session_build(session_id, cards,
                                           counts_json=json.dumps(counts, sort_keys=True),
                                           source_json=json.dumps(final_source, sort_keys=True)):
            log.info("blind-grading: session %s cards=%d shared=%d vc_ms=%d", session_id,
                     len(cards), counts["shared"], vc_meta["elapsed_ms"])
    except GradingError as err:
        _mark_failed(session_id, {"code": err.code, **err.detail})
    except Exception:
        log.exception("blind-grading: build failed session=%s", session_id)
        _mark_failed(session_id, {"code": "value_core_failed"})


def current_session(*, user_id: str, league_id: str) -> dict:
    """{"session": SessionView | None} — the open session for (user_id, league_id)."""
    # The newest session, shown while it is building / open / failed (so the client can
    # render a failure) and never once a later session completed.
    row = db.load_open_grading_session(user_id, league_id,
                                       statuses=("building", "open", "completed", "failed"))
    if row is None or row["status"] == "completed":
        return {"session": None}
    return {"session": session_view(row)}


def next_card(*, user_id: str, session_id: str) -> dict:
    """GradingNext (§3.2). Raises GradingError not_found 404 (unknown or foreign session)."""
    row = db.load_grading_session(session_id, user_id)
    if row is None:
        raise GradingError("not_found", 404)
    progress = db.grading_progress(session_id)
    card = db.load_next_grading_card(session_id) if row["status"] == "open" else None
    if card is None:
        return {"done": True, "session_id": session_id, "progress": progress}
    return {"done": False, "session_id": session_id, "progress": progress,
            "card": {"card_id": card["card_id"], "position": card["position"],
                     "trade": json.loads(card["trade_json"])}}


def answer_card(*, user_id: str, card_id: str, body: object,
                now: datetime | None = None) -> dict:
    """Validate the raw JSON body, then record it. Returns GradingAnswerResult (§3.2).
    Raises GradingError invalid_body 400 · not_found 404 · session_completed 409."""
    grade, skipped, tags = validate_answer(body)
    now = now or datetime.now(timezone.utc)
    res = db.answer_grading_card(card_id, user_id, grade=grade, skipped=skipped,
                                 tags_json=json.dumps(tags), now=now.isoformat())
    if res is None:
        raise GradingError("not_found", 404)
    if res["rejected"]:
        raise GradingError("session_completed", 409)
    return {"card_id": card_id, "session_id": res["session_id"],
            "session_status": res["status"],
            "progress": {"answered": res["answered"], "total": res["total"]}}


def results(*, user_id: str, session_id: str) -> dict:
    """GradingResults (§3.2). Raises GradingError not_found 404 · session_incomplete 409."""
    row = db.load_grading_session(session_id, user_id)
    if row is None:
        raise GradingError("not_found", 404)
    if row["status"] != "completed":
        raise GradingError("session_incomplete", 409, progress=db.grading_progress(session_id))
    cards = db.load_grading_cards(session_id)
    arms, shared = arm_summaries(cards)
    return {"session_id": session_id, "league_id": row["league_id"],
            "completed_at": row["completed_at"], "total": len(cards), "shared": shared,
            "target_mean": TARGET_MEAN, "arms": arms}


def report(*, since: str | None = None, include_open: bool = False) -> dict:
    """GradingReport (§3.2). Raises GradingError invalid_since 400."""
    if since is not None:
        try:
            date.fromisoformat(since)
        except (TypeError, ValueError):
            raise GradingError("invalid_since", 400) from None
    sessions, cards = db.load_grading_report_rows(since, include_open)
    cards_by_session: dict[str, list] = {}
    for c in cards:
        cards_by_session.setdefault(c["session_id"], []).append(c)
    session_rows = []
    grader_cards: dict[str, list] = {}
    grader_sessions: Counter = Counter()
    for s in sessions:
        s_cards = cards_by_session.get(s["session_id"], [])
        arms, _ = arm_summaries(s_cards)
        session_rows.append({"session_id": s["session_id"], "user_id": s["user_id"],
                             "league_id": s["league_id"], "status": s["status"],
                             "created_at": s["created_at"], "completed_at": s["completed_at"],
                             "counts": json.loads(s["counts_json"]),
                             "source": json.loads(s["source_json"]),
                             "arms": arms, "delta_mean": _delta_mean(arms)})
        grader_cards.setdefault(s["user_id"], []).extend(s_cards)
        grader_sessions[s["user_id"]] += 1
    overall_arms, overall_shared = arm_summaries(cards)
    overall = {"sessions": len(sessions), "graders": len(grader_sessions), "cards": len(cards),
               "shared": overall_shared, "arms": overall_arms,
               "delta_mean": _delta_mean(overall_arms)}
    by_grader = []
    for uid in sorted(grader_cards):
        arms, _ = arm_summaries(grader_cards[uid])
        by_grader.append({"user_id": uid, "sessions": grader_sessions[uid], "arms": arms,
                          "delta_mean": _delta_mean(arms)})
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "version": VERSION,
            "target_mean": TARGET_MEAN, "filters": {"since": since, "include_open": include_open},
            "overall": overall, "by_grader": by_grader, "sessions": session_rows}


# ---------------------------------------------------------------------------
# Private helpers (lld.md §6). Everything below is implementation detail; the
# routes call only the public block above.
# ---------------------------------------------------------------------------

_ORDINALS = {1: "1st", 2: "2nd", 3: "3rd"}


def new_id() -> str:
    """Random 18-digit decimal string: str(secrets.randbelow(9 * 10**17) + 10**17).
    Decimal on purpose: the client's api_request_failed route normaliser folds digit runs
    to ':id' (client.ts:365), so a failed grading call never puts a random id into analytics."""
    return str(secrets.randbelow(9 * 10**17) + 10**17)


@dataclass(frozen=True)
class Catalog:
    assets: Mapping[str, Mapping[str, object]]  # id -> {"name","position","nfl_team","age","value"}
    partner_names: Mapping[str, str]            # league user id -> display name
    holdings: Mapping[str, frozenset[str]]      # league user id -> held asset ids


@dataclass(frozen=True)
class ArmCard:
    arm: str                          # "current" | "value_core"
    partner_id: str                   # league identity (league_members.user_id)
    give: tuple[str, ...]
    receive: tuple[str, ...]
    provenance: Mapping[str, object]  # hidden; becomes arms_json[arm]

    @property
    def key(self) -> tuple[str, frozenset[str], frozenset[str]]:
        return (self.partner_id, frozenset(self.give), frozenset(self.receive))


def _roster_ids(raw) -> list[str]:
    if isinstance(raw, str):
        raw = json.loads(raw) if raw.strip() else []
    return [str(pid) for pid in (raw or [])]


def pick_label(row: Mapping) -> str:
    """"2027 1st", plus " (from Kim)" when the pick was acquired via trade — a slot-free
    mirror of server._owned_pick_label."""
    rnd = int(row.get("round") or 0)
    base = f"{row.get('season')} {_ORDINALS.get(rnd, f'{rnd}th')}"
    if row.get("is_traded") and row.get("original_username"):
        return f"{base} (from {row['original_username']})"
    return base


def build_catalog(inputs: Mapping) -> Catalog:
    """One consensus catalog for display (hld G6) from read_league_inputs' output.
    Players: elo_to_value(player_value_history.consensus_elo), rounded; None without a
    history row. Picks: every platform pick, uncapped, valued at round(pool_value)."""
    from backend.trade_service import elo_to_value

    players, consensus = inputs["players"], inputs["consensus_elo"]
    assets: dict[str, dict] = {}
    partner_names: dict[str, str] = {}
    holdings: dict[str, set[str]] = {}
    for m in inputs["members"]:
        uid = str(m["user_id"])
        partner_names[uid] = m.get("display_name") or m.get("username") or uid
        held = holdings.setdefault(uid, set())
        for pid in _roster_ids(m.get("roster_data")):
            held.add(pid)
            p = players.get(pid)
            if p is None or pid in assets:
                continue
            age = p.get("age")
            assets[pid] = {"name": p.get("full_name") or pid,
                           "position": p.get("position"),
                           "nfl_team": p.get("team") or None,
                           "age": int(age) if age is not None else None,
                           "value": (round(elo_to_value(float(consensus[pid])))
                                     if pid in consensus else None)}
    for pk in inputs["picks"]:
        aid = str(pk["pick_id"])
        pool = pk.get("pool_value")
        assets[aid] = {"name": pick_label(pk), "position": "PICK", "nfl_team": None,
                       "age": None, "value": round(float(pool)) if pool else None}
        owner = str(pk.get("owner_user_id") or "")
        if owner in holdings:
            holdings[owner].add(aid)
    return Catalog(assets, partner_names, {u: frozenset(h) for u, h in holdings.items()})


def _league_inputs(league_id: str, league_user_id: str, now: datetime
                   ) -> tuple[dict, str, Catalog]:
    """read_league_inputs on the app engine (DB only, no network) + the seat check.
    ValueError (no leagues / league_members rows) or a seat that is not a member ⇒
    GradingError("league_not_synced", 409)."""
    from backend.eval import value_core_bench as bench

    try:
        with db.engine.connect() as conn:
            inputs = bench.read_league_inputs(conn, league_id, now.date())
    except ValueError:
        raise GradingError("league_not_synced", 409) from None
    seat = str(league_user_id)
    if seat not in {str(m["user_id"]) for m in inputs["members"]}:
        raise GradingError("league_not_synced", 409)
    return inputs, seat, build_catalog(inputs)


def _needs_fresh_deck(reason: str, usable: int) -> GradingError:
    return GradingError("needs_fresh_deck", 409, reason=reason, usable=usable,
                        min_cards=MIN_PER_ARM, max_age_days=MAX_DECK_AGE_DAYS)


def _as_json(x) -> dict:
    return json.loads(x) if isinstance(x, str) else (x or {})


def select_current_cards(job_id: str | None, served_at: str | None, rows: Sequence[Mapping], *,
                         viewer_id: str, catalog: Catalog, now: datetime
                         ) -> tuple[list[ArmCard], dict]:
    """The current-engine arm from the caller's newest qualifying deck (lld §6.3)."""
    if job_id is None:
        raise _needs_fresh_deck("missing", 0)
    ts = datetime.fromisoformat(str(served_at))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if now - ts > timedelta(days=MAX_DECK_AGE_DAYS):
        raise _needs_fresh_deck("stale", 0)
    parsed = [(r, _as_json(r.get("features_json")), _as_json(r.get("assets_json"))) for r in rows]
    candidates = [p for p in parsed if p[1].get("standing_offer") is not True][:PER_ARM]
    cards: list[ArmCard] = []
    seen: set = set()
    dropped_stale = dropped_unknown = 0
    viewer_held = catalog.holdings.get(viewer_id, frozenset())
    for r, features, assets in candidates:
        give = tuple(str(i) for i in (assets.get("give") or []))
        receive = tuple(str(i) for i in (assets.get("receive") or []))
        partner = str(features.get("partner_user_id") or "")
        if any(i not in catalog.assets for i in (*give, *receive)):
            dropped_unknown += 1
            continue
        if (not give or not receive or partner not in catalog.partner_names
                or partner == viewer_id or not set(give) <= viewer_held
                or not set(receive) <= catalog.holdings.get(partner, frozenset())):
            dropped_stale += 1
            continue
        card = ArmCard("current", partner, give, receive,
                       {"impression_id": r["impression_id"], "card_index": r["card_index"],
                        "model_arm": r["model_arm"]})
        if card.key in seen:
            continue
        seen.add(card.key)
        cards.append(card)
    if len(cards) < MIN_PER_ARM:
        raise _needs_fresh_deck("too_few", len(cards))
    meta = {"deck_job_id": job_id, "served_at": served_at, "candidates": len(candidates),
            "dropped_stale": dropped_stale, "dropped_unknown": dropped_unknown}
    return cards, meta


def run_value_core(inputs: Mapping, *, seat: str, server: ServerInputs,
                   engine: Callable | None = None) -> tuple[list[ArmCard], dict]:
    """The value-core arm: the bench's league_record/snapshot_for_seat with the serving
    path's league facts from ServerInputs, run through pipeline.run with the default
    CoreConfig/RankConfig (D8). Any exception ⇒ value_core_failed 503; fewer than
    MIN_PER_ARM usable cards ⇒ value_core_too_few 409."""
    from backend.eval import value_core_bench as bench
    from backend.value_core import pipeline
    from backend.value_core.types import ENGINE_VERSION, CoreConfig, RankConfig, Request

    core_cfg, rank_cfg = CoreConfig(), RankConfig()
    try:
        record = bench.league_record(**inputs, meta=None, state=None)
        if server.lineup_slots:
            record["lineup_slots"] = list(server.lineup_slots)
        record["max_players"] = server.max_players
        record["standings"] = {str(uid): {"wins": s.wins, "losses": s.losses, "ties": s.ties,
                                          "points_for": s.points_for}
                               for uid, s in server.standings.items()}
        record["completed_weeks"] = int(server.completed_weeks)
        snapshot, board = bench.snapshot_for_seat(record, seat,
                                                  standings_weight=bench.DEFAULT_STANDINGS_WEIGHT)
        request = Request(
            viewer_team_id=seat, board=board,
            untouchable_ids=frozenset(i for i in server.untouchable_ids if i in snapshot.assets),
            not_interested_ids=frozenset(i for i in server.not_interested_ids
                                         if i in snapshot.assets))
        result = (engine or pipeline.run)(snapshot, request, core_cfg, rank_cfg)
        cards: list[ArmCard] = []
        dropped_unknown = 0
        for e in result.entries[:PER_ARM]:
            t = e.scored.trade
            if any(i not in snapshot.assets for i in (*t.give, *t.receive)):
                dropped_unknown += 1
                continue
            cards.append(ArmCard("value_core", str(t.partner_team_id), tuple(t.give),
                                 tuple(t.receive),
                                 {"deck_position": e.position, "reasons": list(e.reasons)}))
    except Exception:
        log.exception("blind-grading: value core failed league=%s", inputs["league_row"]
                      .get("sleeper_league_id"))
        raise GradingError("value_core_failed", 503) from None
    if len(cards) < MIN_PER_ARM:
        raise GradingError("value_core_too_few", 409, usable=len(cards), min_cards=MIN_PER_ARM)
    meta = {"engine_version": ENGINE_VERSION,
            "core": dataclasses.asdict(core_cfg), "rank": dataclasses.asdict(rank_cfg),
            "standings_weight": bench.DEFAULT_STANDINGS_WEIGHT,
            "completed_weeks": record["completed_weeks"],
            "lineup_slots": list(record["lineup_slots"]), "max_players": record["max_players"],
            "pool": len(result.entries), "elapsed_ms": result.elapsed_ms,
            "budget_exhausted": result.core.budget_exhausted,
            "dropped_unknown": dropped_unknown}
    return cards, meta


def neutral_trade(partner_id: str, give: Sequence[str], receive: Sequence[str],
                  catalog: Catalog) -> dict:
    """THE ONLY producer of trade_json. Receives no arm, no provenance, no engine object.
    Every field is computable from (partner_id, give, receive, catalog) alone; each side is
    sorted by (-value, name, id)."""
    def asset(i: str) -> dict:
        a = catalog.assets[i]
        return {"id": i, **{k: a[k] for k in ("name", "position", "nfl_team", "age", "value")}}

    def side(ids: Sequence[str]) -> list[dict]:
        ordered = sorted(ids, key=lambda i: (-(catalog.assets[i]["value"] or 0),
                                             catalog.assets[i]["name"], i))
        return [asset(i) for i in ordered]

    return {"partner_name": catalog.partner_names[partner_id],
            "give": side(give), "receive": side(receive)}


def merge_cards(cards: Sequence[ArmCard]) -> list[dict]:
    """Merge by (partner, frozenset(give), frozenset(receive)) — hld G3. A trade both arms
    produced becomes ONE card credited to both; the first occurrence's sides are kept."""
    merged: dict = {}
    for c in cards:
        m = merged.setdefault(c.key, {"partner_id": c.partner_id, "give": c.give,
                                      "receive": c.receive, "arms": {}})
        m["arms"].setdefault(c.arm, dict(c.provenance))
    return list(merged.values())


def shuffle_cards(order: Sequence[dict], seed: int) -> list[dict]:
    """random.Random(seed).shuffle on a copy — the only randomness besides `secrets`."""
    out = list(order)
    random.Random(seed).shuffle(out)
    return out


def _mark_failed(session_id: str, error: dict) -> None:
    """build_session's failure path. Swallows its own DB error: build_session never raises."""
    try:
        db.fail_grading_session(session_id, json.dumps(error, sort_keys=True))
    except Exception:
        log.exception("blind-grading: could not mark session %s failed", session_id)


def validate_answer(body: object) -> tuple[int | None, bool, list[str]]:
    """(grade, skipped, tags). GradingError("invalid_body", 400, message=...) when:
      body is not a dict; both or neither of "grade" / "skip" present (skip counts only when it
      is exactly True); grade not an int, a bool, or outside 1..5; "tags" present and not a list
      of str, or any tag not in TAGS; skip with a non-empty tags list.
    Tags are de-duplicated and returned in TAGS order. Unknown body keys are ignored."""
    def bad(message: str) -> GradingError:
        return GradingError("invalid_body", 400, message=message)

    if not isinstance(body, dict):
        raise bad("body must be a JSON object")
    skipped = body.get("skip") is True
    has_grade = "grade" in body
    if has_grade == skipped:
        raise bad("send exactly one of grade (1-5) or skip: true")
    grade = None
    if has_grade:
        grade = body["grade"]
        if isinstance(grade, bool) or not isinstance(grade, int) or not 1 <= grade <= 5:
            raise bad("grade must be an integer from 1 to 5")
    raw_tags = body.get("tags")
    tags: list[str] = []
    if raw_tags is not None:
        if not isinstance(raw_tags, list) or not all(isinstance(t, str) for t in raw_tags):
            raise bad("tags must be a list of strings")
        unknown = [t for t in raw_tags if t not in TAGS]
        if unknown:
            raise bad(f"unknown tag {unknown[0]!r}")
        tags = [t for t in TAGS if t in raw_tags]
    if skipped and tags:
        raise bad("tags must be empty with skip")
    return grade, skipped, tags


def session_view(row: Mapping) -> dict:
    """SessionView (§3.2): never seed, counts_json, source_json or any arm."""
    error = row.get("error_json")
    return {"session_id": row["session_id"], "league_id": row["league_id"],
            "status": row["status"], "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "progress": db.grading_progress(row["session_id"]),
            "error": json.loads(error) if error else None}


def summarize(graded: Sequence[tuple[int, Sequence[str]]]) -> dict:
    """{"n", "mean", "share_ge_4", "tag_counts"} — the arithmetic of blind_grade._score:
    mean and share rounded to 4 dp, None when n == 0, tag_counts a key-sorted dict."""
    n = len(graded)
    tags = Counter(t for _, row_tags in graded for t in row_tags)
    return {"n": n,
            "mean": round(sum(g for g, _ in graded) / n, 4) if n else None,
            "share_ge_4": round(sum(1 for g, _ in graded if g >= 4) / n, 4) if n else None,
            "tag_counts": dict(sorted(tags.items()))}


def arm_summaries(cards: Sequence[Mapping]) -> tuple[dict, int]:
    """({arm: {"cards", "skipped", **summarize(graded)}} for arm in ARMS, shared_count).
    A card credits every arm key in its arms_json; graded = (grade, tags) for cards with a
    grade. The only reader of arms_json besides report()."""
    buckets = {arm: {"cards": 0, "skipped": 0, "graded": []} for arm in ARMS}
    shared = 0
    for c in cards:
        arms = _as_json(c["arms_json"])
        if len(arms) > 1:
            shared += 1
        tags = json.loads(c["tags_json"]) if isinstance(c["tags_json"], str) else list(c["tags_json"] or [])
        for arm in arms:
            b = buckets.get(arm)
            if b is None:
                continue
            b["cards"] += 1
            if c["skipped"]:
                b["skipped"] += 1
            elif c["grade"] is not None:
                b["graded"].append((int(c["grade"]), tags))
    return ({arm: {"cards": b["cards"], "skipped": b["skipped"], **summarize(b["graded"])}
             for arm, b in buckets.items()}, shared)


def _delta_mean(arms: Mapping[str, Mapping]) -> float | None:
    vc, cur = arms["value_core"]["mean"], arms["current"]["mean"]
    return round(vc - cur, 4) if vc is not None and cur is not None else None
