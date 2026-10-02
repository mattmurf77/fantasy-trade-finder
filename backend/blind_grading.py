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

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Mapping

from . import database as db

log = logging.getLogger(__name__)

VERSION = "blind-grading-1"
ARMS: tuple[str, ...] = ("current", "value_core")
TAGS: tuple[str, ...] = ("overpay", "they_wont_accept", "junk_filler", "too_small",
                         "wrong_for_my_window", "wrong_for_their_window", "same_guy_again")
PER_ARM = 20            # cards taken from each arm
MIN_PER_ARM = 10        # fewer usable cards in an arm ⇒ refuse the session
MAX_DECK_AGE_DAYS = 7   # the current arm's deck must be at most this old
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
    raise NotImplementedError


def build_session(*, session_id: str, server: ServerInputs, engine: Callable | None = None,
                  now: datetime | None = None) -> None:
    """SLOW, background-thread half. Runs the value core, merges duplicates, shuffles,
    writes grading_cards and flips the session to "open". On GradingError (value_core_too_few)
    or any exception (value_core_failed) it flips the session to "failed" with
    error_json = {"code": ..., **detail} and never raises. Idempotent: a session that
    is not "building" is left alone."""
    raise NotImplementedError


def current_session(*, user_id: str, league_id: str) -> dict:
    """{"session": SessionView | None} — the open session for (user_id, league_id)."""
    raise NotImplementedError


def next_card(*, user_id: str, session_id: str) -> dict:
    """GradingNext (§3.2). Raises GradingError not_found 404 (unknown or foreign session)."""
    raise NotImplementedError


def answer_card(*, user_id: str, card_id: str, body: object,
                now: datetime | None = None) -> dict:
    """Validate the raw JSON body, then record it. Returns GradingAnswerResult (§3.2).
    Raises GradingError invalid_body 400 · not_found 404 · session_completed 409."""
    raise NotImplementedError


def results(*, user_id: str, session_id: str) -> dict:
    """GradingResults (§3.2). Raises GradingError not_found 404 · session_incomplete 409."""
    raise NotImplementedError


def report(*, since: str | None = None, include_open: bool = False) -> dict:
    """GradingReport (§3.2). Raises GradingError invalid_since 400."""
    raise NotImplementedError
