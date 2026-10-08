# Build specs — Calibration: in-app blind grading (parallel work packages)

**Date:** 2026-10-02 · **Status:** build contract · Companion: [scope.md](scope.md) · [prd.md](prd.md) · [hld.md](hld.md) · [lld.md](lld.md)

This is the contract for **four parallel build agents**. Every file belongs to exactly one package. Nobody edits a file they do not own. If a package needs a change in someone else's file, it stops and reports to the lead.

Algorithms and exact edit points live in [lld.md](lld.md). This document fixes four things: ownership, the two shared contracts (verbatim), the tests, and the gates.

## Contents

1. [Ground rules](#1-ground-rules)
2. [Work packages](#2-work-packages)
3. [Shared contracts (verbatim)](#3-shared-contracts-verbatim)
4. [Sequencing](#4-sequencing)
5. [Package specs](#5-package-specs)
6. [Integration checklist (lead)](#6-integration-checklist-lead)
7. [Docs matrix](#7-docs-matrix)
8. [Lead-only items](#8-lead-only-items)

---

## 1. Ground rules

- **Branching.** Every package branches from `feat/blind-grading` **after** the contract commit (§4), in its own worktree. `feat/blind-grading` sits on `feat/value-core-engine`, which supplies `backend/value_core/` and `backend/eval/value_core_bench.py`.
- **Guidelines.** Follow `docs/coding-guidelines.md`: simplicity first, surgical edits. No drive-by refactors in `server.py`, `database.py`, `TabNav.tsx` or any other existing module.
- **Search.** Tracked files only: `git grep -n`.
- **Imports.**
  - No new dependency.
  - `backend/blind_grading.py` never imports `backend.server` or `backend.tools`.
  - `backend/value_core/` stays free of `backend.server`; this feature does not touch it.
- **Determinism.** The only randomness is `secrets` (seed and ids) and `random.Random(seed)`. Tests inject `seed=` and monkeypatch `blind_grading.secrets` / `new_id` where order matters.
- **Tests.**
  - Run on Python 3.12 (CI), with `python3 -m pytest <file> -q`.
  - No network. Stub every Sleeper-touching helper.
  - In-memory SQLite, following harness pattern 1 or 2 in `backend/tests/CLAUDE.md`.
- **Naming.**
  - UI copy says **Calibration**.
  - Code and storage say `grading`, except the mobile screen, stack and route, which are `CalibrationScreen` / `CalibrationStackNav` / `CalibrationHome` / `Calibration`.
- **Out of bounds.** `living-memory/*` except P4's `HLD.md`/`LLD.md`, every `CLAUDE.md`, and `docs/plans/README.md` are lead-only (§8).

## 2. Work packages

C = create, E = edit.

| Package | Owned files | Purpose |
|---|---|---|
| **P1 — Backend service + schema** | C `backend/blind_grading.py` · E `backend/database.py` · E `backend/eval/value_core_bench.py` · E `backend/accounts.py` · C `backend/tests/test_blind_grading_service.py` · C `backend/tests/test_blind_grading_db.py` · E `backend/tests/test_value_core_bench.py` | Two tables and nine helpers. Extract the bench DB reader and fix its pick predicate. Arm sourcing, merge, shuffle, the neutral formatter, validation and scoring. Account deletion and export coverage. |
| **P2 — Routes + flags + route tests** | E `backend/server.py` · E `backend/feature_flags.py` · E `config/features.json` · E `backend/tests/fixtures/flags/release.json` · E `…/profiles-on.json` · E `…/onboarding-v2.json` · E `…/release-300.json` · E `…/release-espn-send-off.json` · E `backend/tests/test_rookie_ranks_editable.py` · C `backend/tests/test_blind_grading_routes.py` · C `backend/tests/test_blind_grading_e2e.py` · C `docs/plans/blind-grading/code-walk-backend.md` | The audience predicate, the per-caller flag resolution, the gate, six routes, `grading.blind`, and `draft.tab` → false |
| **P3 — Mobile** | C `mobile/src/api/grading.ts` · C `mobile/src/components/GradingCard.tsx` · C `mobile/src/components/GradingResults.tsx` · C `mobile/src/screens/CalibrationScreen.tsx` · E `mobile/src/navigation/TabNav.tsx` · E `mobile/src/api/client.ts` · C `mobile/tests/check-blind-grading.js` · E `mobile/package.json` · E `mobile/tests/README.md` · E `mobile/src/screens/README.md` · E `mobile/src/navigation/README.md` · C `docs/plans/blind-grading/code-walk-mobile.md` | The Calibration tab in the Draft slot, the screen, the neutral card, results, the wire module and the structural guard |
| **P4 — Reference docs** | E `docs/api-reference.md` · E `docs/data-dictionary.md` · E `docs/config-reference.md` · E `docs/architecture.md` · E `docs/glossary.md` · E `docs/runbook.md` · E `docs/cross-client-invariants.md` · E `living-memory/HLD.md` · E `living-memory/LLD.md` | Every trigger-table doc update, written from this spec |

**Shared contracts:** §3.1, the service skeleton (P1 writes it; P2 codes against it), and §3.2, the route JSON plus `api/grading.ts` (P2 serves it; P3 consumes it).

## 3. Shared contracts (verbatim)

### 3.1 Service contract: `backend/blind_grading.py` skeleton

P1 commits this file **exactly** as below as the contract commit (§4). It then fills the bodies, and adds the private helpers from [lld.md §6](lld.md#6-service-backendblind_gradingpy) (`Catalog`, `ArmCard`, `build_catalog`, `select_current_cards`, `run_value_core`, `neutral_trade`, `new_id`, `validate_answer`, `session_view`, `summarize`, `arm_summaries`) **below** the public block.

The names, signatures, constants, `GradingError` and `ServerInputs` below must not change without the lead's sign-off.

```python
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
```

### 3.2 Route contract (JSON)

#### Conventions and the gate

**Common to every `/api/grading/*` route:**
- Authentication: the `X-Session-Token` header.
- The mobile client also sends `X-Device-Id` (best effort).

**The gate, `_grading_gate`, runs first.** Either condition fails ⇒ `404 {"error":"not_found"}`:
- **a session exists**, and the caller resolves `grading.blind` true: global, OR a running-experiment overlay for `device:<X-Device-Id>` or the session's account unit;
- **`_calibration_allowed(sess)`** passes: the session `user_id` or league user id is in the tester allowlist.

**After the gate:**
- 403 `{"error":"verification_required"}` for unverified sessions;
- 401 for a token that expired mid-request.

**Ids:** 18-digit decimal strings. **Times:** ISO-8601 UTC strings.

**Shared shapes:**

```jsonc
// SessionView
{"session_id": "418273645512093847", "league_id": "1312140920132497408",
 "status": "open",                      // "building" | "open" | "completed" | "failed"
 "created_at": "2026-10-02T15:04:05.123456+00:00", "completed_at": null,
 "progress": {"answered": 0, "total": 37},   // total 0 while building / failed
 "error": null}                         // failed only: {"code":"value_core_too_few","usable":4,"min_cards":10} | {"code":"value_core_failed"}

// NeutralTrade — the ONLY card payload; produced by blind_grading.neutral_trade
{"partner_name": "Jared",
 "give":    [{"id": "4046", "name": "Patrick Mahomes", "position": "QB",
              "nfl_team": "KC", "age": 31, "value": 6123}],
 "receive": [{"id": "9509", "name": "Bijan Robinson", "position": "RB",
              "nfl_team": "ATL", "age": 24, "value": 7710},
             {"id": "1312140920132497408_2027_1_4", "name": "2027 1st (from Kim)",
              "position": "PICK", "nfl_team": null, "age": null, "value": 2117}]}
// Asset keys are EXACTLY {id, name, position, nfl_team, age, value}. value: int | null.
// Each side is sorted by (-value, name, id).

// ArmSummary
{"cards": 20, "n": 18, "skipped": 2, "mean": 3.1111, "share_ge_4": 0.3889,
 "tag_counts": {"overpay": 4, "wrong_for_my_window": 2}}   // mean/share null when n == 0
```

#### 1. `POST /api/grading/sessions`

**Request:** `{"league_id": "1312140920132497408"}`

**Success (lead change 2026-10-02, §3.3):**
- `202` `{"session": SessionView, "resumed": false}` — a new session, `status: "building"`; the server builds it on a background thread. The client polls route 2 until the status is no longer `building`.
- `200` `{"session": SessionView, "resumed": true}` — a `building` or `open` session for this user and league already existed. A `failed` session is never resumed; POST starts a fresh one.

**Errors:**

| Status | Body |
|---|---|
| 400 | `{"error":"invalid_body","message":"league_id is required"}` |
| 400 | `{"error":"league_not_active"}` |
| 409 | `{"error":"session_not_initialized", …}` (existing) |
| 409 | `{"error":"league_not_synced"}` |
| 409 | `{"error":"needs_fresh_deck","reason":"missing"\|"stale"\|"too_few","usable":7,"min_cards":10,"max_age_days":7}` |
| *(moved)* | `value_core_too_few` / `value_core_failed` are no longer HTTP errors on this route: they surface as `status: "failed"` with `error` on the SessionView (§3.3). |

#### 2. `GET /api/grading/sessions/current?league_id=<id>`

**Success:** `200` `{"session": SessionView}` or `{"session": null}`. Returns the newest `building`, `open` or `failed` session for the league (so the client can show a failure), never a `completed` one.

**Errors:** `400` `{"error":"invalid_body","message":"league_id is required"}`.

#### 3. `GET /api/grading/sessions/<session_id>/next`

**Success:**
- `200` `{"done": false, "session_id": "…", "progress": {"answered": 11, "total": 37}, "card": {"card_id": "907112334455667788", "position": 12, "trade": NeutralTrade}}`
- `200` `{"done": true, "session_id": "…", "progress": {"answered": 37, "total": 37}}`

**Errors:** `404` `{"error":"not_found"}` (unknown or foreign session).

#### 4. `POST /api/grading/cards/<card_id>`

**Request:** `{"grade": 4, "tags": ["overpay"]}` | `{"grade": 2}` | `{"skip": true}`.
- `tags` is optional, comes from the fixed 7, and is de-duplicated.
- `tags` must be empty or absent with `skip`.

**Success:** `200` `{"card_id": "…", "session_id": "…", "session_status": "open", "progress": {"answered": 12, "total": 37}}`. `session_status` is `"completed"` after the last answer.

**Errors:**

| Status | Body |
|---|---|
| 400 | `{"error":"invalid_body","message":"…"}` |
| 404 | `{"error":"not_found"}` |
| 409 | `{"error":"session_completed"}` |

#### 5. `GET /api/grading/sessions/<session_id>/results`

**Success:** `200`:

```json
{"session_id": "…", "league_id": "…", "completed_at": "…", "total": 37, "shared": 3,
 "target_mean": 4.0,
 "arms": {"current": ArmSummary, "value_core": ArmSummary}}
```

**Errors:** `404` `{"error":"not_found"}`; `409` `{"error":"session_incomplete","progress":{"answered":12,"total":37}}`.

#### 6. `GET /api/admin/grading/report?since=YYYY-MM-DD&include_open=1`

- **Auth:** `X-Cron-Secret`. **Not** gated by the flag or the audience.
- **`since`:** optional; filters on `created_at`.
- **`include_open=1`:** adds open sessions; by default only completed sessions are counted.

**Success:** `200`:

```json
{"generated_at": "…", "version": "blind-grading-1", "target_mean": 4.0,
 "filters": {"since": null, "include_open": false},
 "overall": {"sessions": 3, "graders": 2, "cards": 111, "shared": 7,
             "arms": {"current": ArmSummary, "value_core": ArmSummary}, "delta_mean": 0.41},
 "by_grader": [{"user_id": "…", "sessions": 2,
                "arms": {"current": ArmSummary, "value_core": ArmSummary}, "delta_mean": 0.2}],
 "sessions": [{"session_id": "…", "user_id": "…", "league_id": "…", "status": "completed",
               "created_at": "…", "completed_at": "…",
               "counts": {"total": 37, "current": 20, "value_core": 20, "shared": 3,
                          "current_candidates": 20, "current_dropped_stale": 0,
                          "current_dropped_unknown": 0, "value_core_pool": 214},
               "source": {"version": "blind-grading-1", "seat": "…", "scoring_format": "1qb_ppr",
                          "current": {"deck_job_id": "…", "served_at": "…"},
                          "value_core": {"engine_version": "value-core-1", "core": {}, "rank": {},
                                         "standings_weight": 0.3, "completed_weeks": 4,
                                         "lineup_slots": [], "max_players": 30, "pool": 214,
                                         "elapsed_ms": 1840, "budget_exhausted": false}},
               "arms": {"current": ArmSummary, "value_core": ArmSummary}, "delta_mean": 0.6}]}
```

`delta_mean` = `value_core.mean − current.mean`, rounded to 4 dp; `null` if either is `null`.

**Errors:** `400` `{"error":"invalid_since"}`; `401` / `503` from the cron-auth abort.

#### `mobile/src/api/grading.ts` (P3 writes it verbatim)

```ts
import { api, getDeviceId } from './client';

// Calibration — in-app blind grading, value-core Gate 2.
// Contract: docs/plans/blind-grading/specs.md §3.2. Every /api/grading/* call
// 404s unless grading.blind resolves true for this caller AND the caller is on
// the tester allowlist. X-Device-Id rides every call so the server can resolve a
// device-unit flag overlay exactly as /api/feature-flags does (api/flags.ts).

export type GradingTag =
  | 'overpay' | 'they_wont_accept' | 'junk_filler' | 'too_small'
  | 'wrong_for_my_window' | 'wrong_for_their_window' | 'same_guy_again';

export const GRADING_TAGS: readonly GradingTag[] = [
  'overpay', 'they_wont_accept', 'junk_filler', 'too_small',
  'wrong_for_my_window', 'wrong_for_their_window', 'same_guy_again',
];

export const GRADING_TAG_LABELS: Record<GradingTag, string> = {
  overpay: 'Overpay',
  they_wont_accept: "They won't accept",
  junk_filler: 'Junk filler',
  too_small: 'Too small',
  wrong_for_my_window: 'Wrong for my window',
  wrong_for_their_window: 'Wrong for their window',
  same_guy_again: 'Same guy again',
};

export interface GradingProgress { answered: number; total: number; }

export interface GradingSession {
  session_id: string;
  league_id: string;
  status: 'building' | 'open' | 'completed' | 'failed';
  created_at: string;
  completed_at: string | null;
  progress: GradingProgress;
  error: { code: 'value_core_too_few' | 'value_core_failed'; [k: string]: unknown } | null;
}

export interface GradingAsset {
  id: string;
  name: string;
  position: string;            // 'QB' | 'RB' | 'WR' | 'TE' | 'PICK'
  nfl_team: string | null;
  age: number | null;
  value: number | null;
}

export interface GradingTrade {
  partner_name: string;
  give: GradingAsset[];
  receive: GradingAsset[];
}

export interface GradingCard {
  card_id: string;
  position: number;            // 1-based
  trade: GradingTrade;
}

export type GradingNext =
  | { done: false; session_id: string; progress: GradingProgress; card: GradingCard }
  | { done: true; session_id: string; progress: GradingProgress };

export type GradingAnswer =
  | { grade: 1 | 2 | 3 | 4 | 5; tags: GradingTag[] }
  | { skip: true };

export interface GradingAnswerResult {
  card_id: string;
  session_id: string;
  session_status: 'open' | 'completed';
  progress: GradingProgress;
}

export interface GradingArmSummary {
  cards: number;
  n: number;
  skipped: number;
  mean: number | null;
  share_ge_4: number | null;
  tag_counts: Partial<Record<GradingTag, number>>;
}

export interface GradingResults {
  session_id: string;
  league_id: string;
  completed_at: string;
  total: number;
  shared: number;
  target_mean: number;
  arms: { current: GradingArmSummary; value_core: GradingArmSummary };
}

async function deviceHeaders(): Promise<{ headers: Record<string, string> } | undefined> {
  try {
    return { headers: { 'X-Device-Id': await getDeviceId() } };
  } catch {
    return undefined;   // best effort, exactly as api/flags.ts
  }
}

export async function getCurrentGradingSession(
  leagueId: string,
): Promise<{ session: GradingSession | null }> {
  return api.get<{ session: GradingSession | null }>(
    `/api/grading/sessions/current?league_id=${encodeURIComponent(leagueId)}`,
    await deviceHeaders(),
  );
}

export async function startGradingSession(
  leagueId: string,
): Promise<{ session: GradingSession; resumed: boolean }> {
  return api.post<{ session: GradingSession; resumed: boolean }>(
    '/api/grading/sessions', { league_id: leagueId }, await deviceHeaders(),
  );
}

export async function getNextGradingCard(sessionId: string): Promise<GradingNext> {
  return api.get<GradingNext>(
    `/api/grading/sessions/${encodeURIComponent(sessionId)}/next`, await deviceHeaders(),
  );
}

export async function answerGradingCard(
  cardId: string, answer: GradingAnswer,
): Promise<GradingAnswerResult> {
  return api.post<GradingAnswerResult>(
    `/api/grading/cards/${encodeURIComponent(cardId)}`, answer, await deviceHeaders(),
  );
}

export async function getGradingResults(sessionId: string): Promise<GradingResults> {
  return api.get<GradingResults>(
    `/api/grading/sessions/${encodeURIComponent(sessionId)}/results`, await deviceHeaders(),
  );
}
```

### 3.3 Change control

A change to §3.1 or §3.2 after the contract commit needs the lead's sign-off. Record it here as a dated line.

- **2026-10-02 — background session build (lead, before the contract commit).** Production runs ONE synchronous gunicorn worker (`render.yaml:16`, `--workers 1`, no threads), so a 2–12 s inline build would stall every user's request. `create_session` is split into `start_session` (fast: resume, league check, current-arm selection, `building` row) and `build_session` (slow: value core, merge, shuffle, cards; never raises; sets `open` or `failed`). `grading_sessions` gains `error_json` (Text, nullable); `status` ∈ {building, open, completed, failed}; `counts_json`/`total` are filled by `build_session`. **Routes:** POST returns 202 + `building` for a new session and starts `threading.Thread(target=_build_grading_session, daemon=True)`, which computes `ServerInputs` (standings, lineup slots, roster limit, prefs — the network work moves off the request thread too) and calls `build_session`. Route tests patch the thread start to run inline. **Mobile:** after POST, while `status === "building"`, poll `GET /current` every 1500 ms (cap 60 s, then a "taking longer than usual — try again" state); `failed` renders a plain message per `error.code` with a "Start over" button that POSTs again. **Where any other text in specs.md, lld.md or hld.md says `create_session`, 201, or 409/503 for value-core failures, this entry wins.** Test names: P1 `test_create_session_*` become `test_start_session_*` / `test_build_session_*` with the same assertions split across the halves, plus `test_build_session_failure_marks_failed_never_raises` and `test_failed_session_is_not_resumed`; P2 `test_create_passes_server_inputs_and_returns_201` becomes `test_create_returns_202_and_builds_in_background` (thread start patched inline; asserts `ServerInputs` reach `build_session`).
- **2026-10-05 — open to every app user; 14-day freshness; pre-generation; orphan re-kick; purpose copy (operator).** (1) **Audience.** `grading.blind` is **true** in `config/features.json`, mirrored in `release.json`, `profiles-on.json` and `onboarding-v2.json`; the code default in `feature_flags.py` stays false. `server._calibration_allowed` returns `True` (its docstring says how to restore the tester-allowlist check). No `calibration_rollout` overlay is needed — the overlay path in `_grading_flag_for_caller` stays but is redundant while the global flag is on. Kill = flag false + deploy (or `FTF_FLAGS` + `POST /api/feature-flags/reload`): routes 404, the tab disappears at the next launch. (2) **Freshness.** `blind_grading.MAX_DECK_AGE_DAYS` 7 → 14 (prod: 7 days left four users eligible, 14 leaves eight; moved players are dropped regardless); `needs_fresh_deck.max_age_days` is now 14. (3) **New route** `POST /api/admin/grading/pregenerate`, `X-Cron-Secret` only, not flag- or audience-gated: `blind_grading.pregenerate()` runs `start_session` for every candidate from `database.list_grading_candidates(since)` — a user with a qualifying current-engine deck within `MAX_DECK_AGE_DAYS`, in a league they are a member of; seat = `user_id`, co-owner seats left to on-demand creation — then builds every returned session **sequentially** on one daemon thread named `grading-pregenerate` via `_build_grading_session`. → 202 `{candidates, building, already_open, skipped: {code: n}}`. Re-running is safe: open sessions are resumed, building ones re-kicked. (4) **Orphaned builds.** `POST /api/grading/sessions` always calls `start_session` (the `current_session` short-circuit is removed): a resumed `building` row returns `needs_build=True`, so a build orphaned by a restart or deploy is re-kicked, and a duplicate build writes nothing. `_build_grading_session` falls back to empty `ServerInputs` if gathering league facts fails, so a session can never stay `building`. (5) **Screen copy.** The Calibration intro gains a purpose line (`calibration.purpose`): Calibration captures honest reactions to improve the trade model; grades are compared across both engines and used to tune which trade ideas Fleeced suggests. **Where §3.2, §5.2, §5.3 or any earlier text says testers only, allowlist, 7 days or `max_age_days: 7`, this entry wins.** Tests: `test_open_to_every_app_user`, `test_calibration_allowed_is_the_single_audience_predicate` (now open; making it refuse closes every route), `test_flag_registered_default_off_and_shipped_on_mirrored`, `test_admin_pregenerate_builds_every_candidate_in_one_background_thread`, `test_pregenerate_starts_a_session_per_fresh_candidate`, `test_create_rekicks_an_orphaned_building_session`, `test_create_resumes_open_session_without_building`, `test_build_thread_survives_server_inputs_failure`.

## 4. Sequencing

1. **Contract commit (P1, about 15 minutes).**
   1. Create `backend/blind_grading.py` exactly as in §3.1.
   2. Run `python3 -c "import backend.blind_grading"`.
   3. Commit `blind-grading: service contract skeleton` on `feat/blind-grading`.
2. **Fan-out.** P1 (bodies), P2, P3 and P4 start in parallel from that commit.
3. **Merge order onto `feat/blind-grading`:** P1 → P2 → P3 → P4. File conflicts are impossible by construction; the order only keeps each intermediate state importable and testable. After each merge, the lead runs that package's verification block.
4. **Integration** (§6) after all four have merged.

| Package | Runtime dependency on another package | Isolation strategy |
|---|---|---|
| P1 | none. `backend/value_core/` and `value_core_bench` already exist. | Tests inject `engine=` stubs for `pipeline.run`. |
| P2 | `backend.blind_grading` (the skeleton is present after step 1) | Route tests monkeypatch the six public service functions on the module. `test_blind_grading_e2e.py` is **integration-only** and is excluded from P2's isolated run. |
| P3 | none (JSON only) | Typecheck and the guard. No backend needed. |
| P4 | none (docs) | — |

## 5. Package specs

**Test conventions.** Each test file defines its own tiny builders. Nothing is shared across packages, and there is no conftest beyond the existing one.

- **DB tests** use harness pattern 1: `create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})`, `metadata.create_all`, `patch.object(db, "engine", eng)`.
- **Route tests** use pattern 2: `server.app.test_client()` plus a `server._sessions[TOKEN]` entry, popped in `finally`.

**Common seed** for P1, and copied into P2's e2e:
- **League.** `leagues` row `L1` (`platform="sleeper"`, `default_scoring="1qb_ppr"`).
- **Members.** `league_members` rows for `u1` (the viewer, "Me"), `u2` ("Jared") and `u3` ("Kim"). Each `roster_data` holds 8 players.
- **Players.** `players` rows with `team` and `age` set.
- **Values.** `player_value_history` rows dated `2026-10-01` for every player.
- **Picks.** `draft_picks` rows: one `source=None`, owned by `u2`, `is_traded=1`, `original_username="Kim"`, `season=2027`, `round=1`, `pool_value=2117`; and one `source='platform'`, owned by `u1`.
- **Deck.** `deck_impressions` rows written by `seed_deck(job, served_at, rows)`, with `user_id="u1"`, `propensity=1.0` and the required columns.
- **Clock.** `NOW = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)`.

**Stub engine.**

```python
def stub_engine(trades):          # trades: [(partner, give_ids, receive_ids)]
    from backend.value_core.types import (CoreDiagnostics, DeckEntry, FairTrade,
                                          PipelineResult, ScoredTrade, Scores)
    calls = []
    def run(snapshot, request, core_cfg, rank_cfg, **kw):
        calls.append((snapshot, request, core_cfg, rank_cfg))
        entries = [DeckEntry(i, ScoredTrade(FairTrade(p, tuple(g), tuple(r), 1.0, 1.0, 1.0,
                                                      0.0, None, False, (0, 0)),
                                            Scores(.5, .5, .5, .5), {}), .5, ("Fair on value",))
                   for i, (p, g, r) in enumerate(trades)]
        return PipelineResult(entries, CoreDiagnostics(), 5)
    run.calls = calls
    return run
```

### 5.1 P1 — Backend service + schema

**Owns:** see §2. Implements [lld.md §3–§6 and §9](lld.md#3-schema) exactly.

**Acceptance criteria:**
- **Schema:** both tables exist after `metadata.create_all` on SQLite, with the columns, `uq_grading_card_position` and the two indexes from lld §3.
- **Bench refactor:**
  - `read_league_inputs(conn, league_id, today)` returns exactly the seven keys. It performs no network call and imports nothing from `backend.tools`.
  - `_freeze_league` is a three-step wrapper.
  - The pick predicate is `(source IS NULL OR source = 'platform')`.
- **Isolation:**
  - `create_session` writes only `grading_sessions` and `grading_cards`.
  - `backend/blind_grading.py` has no import of `backend.server` or `backend.tools`, statically or at runtime.
- **Blinding (G1):** `neutral_trade` output depends only on `(partner_id, give, receive, catalog)`. The same trade from either arm serialises byte-identically.
- **Account coverage:** `_ADDITIONAL_PRIVATE_TABLES` contains both names, and `test_account_deletion_coverage.py` passes with them.

**Tests:**

| File::test | Asserts |
|---|---|
| `test_blind_grading_service.py::test_neutral_trade_has_exact_keys_and_sorted_sides` | Top keys == `{"partner_name","give","receive"}`. Every asset's keys == `{"id","name","position","nfl_team","age","value"}`. Each side is ordered by (−value, name, id). |
| `::test_neutral_trade_identical_for_both_arms` | `neutral_trade(p,("a","b"),("c",),cat)` == `neutral_trade(p,("b","a"),("c",),cat)`, and their `json.dumps(sort_keys=True)` strings are equal |
| `::test_pick_label_and_null_fields` | The NULL-source traded pick renders `name == "2027 1st (from Kim)"`, `position == "PICK"`, `nfl_team is None`, `age is None`, `value == 2117` |
| `::test_catalog_values_come_from_history_and_pool` | A player's value == `round(elo_to_value(elo))`. A player with no history row has value None. A pick's value == `round(pool_value)`. |
| `::test_select_current_refuses_missing_stale_and_too_few` | Three cases. `GradingError.code == "needs_fresh_deck"`, status 409, `detail["reason"]` in {missing, stale, too_few}, `detail["min_cards"] == 10`, `detail["max_age_days"] == 7`. |
| `::test_select_current_takes_first_20_then_drops_stale` | 22 rows. Cards come only from `card_index` 0–19. Two are stale (a give id not held; the partner removed) ⇒ 18 cards. `meta["dropped_stale"] == 2`. |
| `::test_select_current_drops_standing_offers_and_duplicates` | `features_json.standing_offer` rows are excluded. A duplicate key keeps the first. |
| `::test_run_value_core_feeds_bench_snapshot_with_default_config` | The stub captures `core_cfg == CoreConfig()`, `rank_cfg == RankConfig()`, `request.viewer_team_id == "u1"`, untouchables cut to snapshot assets, `snapshot.rules.lineup_slots == server.lineup_slots`, `snapshot.rules.max_players == server.max_players`, and a non-None `pf_index` on a team window when `completed_weeks=8` and standings are given |
| `::test_run_value_core_too_few_and_failed` | 3 entries ⇒ `value_core_too_few` 409 with `usable == 3`. The stub raises ⇒ `value_core_failed` 503. |
| `::test_merge_shared_trade_one_card_both_arms` | One current card and one value-core card with the same key ⇒ a single merged card whose `arms` keys == `{"current","value_core"}` |
| `::test_shuffle_is_deterministic_for_a_seed` | The same seed gives the same order. Two different seeds give different orders on a 30-card fixture. |
| `::test_create_session_end_to_end` | The seeded DB plus the stub engine (one shared trade) produce the following. **Rows:** a session row; cards with `position` = 1..N, where N == 39 (20 current + 20 value-core − 1 shared). **Ids:** every `card_id` matches `^\d{18}$` and all are unique. **`trade_json`:** passes the key check. **`arms_json`:** keys ⊆ `ARMS`. **`counts_json`:** `shared == 1`. **`source_json`:** has `current.deck_job_id` and `value_core.core.band == 0.2`. |
| `::test_create_session_resumes_open_session` | A second call returns `resumed is True` with the same `session_id`, and the card count is unchanged |
| `::test_create_session_writes_no_engine_tables` | Row counts of `deck_impressions`, `trade_impressions`, `trade_decisions`, `swipe_decisions` and `deck_candidate_sets` are unchanged. `len(trade_service._trade_cards)` is unchanged. |
| `::test_module_never_imports_server_or_tools` | A subprocess runs `import sys, backend.blind_grading`, then checks `backend.server` and `backend.tools.prod_analytics` are not in `sys.modules`. A static `git grep`-style scan of the file source for `server` / `tools` imports is empty. |
| `::test_summarize_matches_blind_grade_score` | For the same `[(4,["overpay"]),(2,[]),(5,["overpay","too_small"])]`, `summarize(...)` == `backend.eval.blind_grade._score(...)` |
| `::test_arm_summaries_shared_card_counts_for_both_arms` | A shared card graded 5 counts in both arms' `n`. `shared == 1`. Skipped cards count in `skipped`, never in `n`. |
| `::test_validate_answer` (parametrised) | Valid: `{"grade":4}`, `{"grade":1,"tags":["overpay","overpay"]}` (tags de-duplicated), `{"skip":True}`. Invalid ⇒ `invalid_body` 400: `None`, `[]`, `{}`, `{"grade":0}`, `{"grade":6}`, `{"grade":"4"}`, `{"grade":True}`, `{"grade":3,"skip":True}`, `{"skip":"yes"}`, `{"grade":3,"tags":["bogus"]}`, `{"skip":True,"tags":["overpay"]}`. |
| `::test_answer_card_regrade_then_complete_then_reject` | A re-grade overwrites. The last answer gives `session_status == "completed"`. A further answer raises `session_completed` 409. |
| `::test_results_and_report` | `results` on an open session ⇒ `session_incomplete` 409. On a completed one, the shape matches §3.2. `report` covers overall, `by_grader` and `sessions`, gives `delta_mean` = vc − current, and `since="bad"` ⇒ `invalid_since` 400. |
| `test_blind_grading_db.py::test_tables_created_with_expected_columns` | Column names and nullability per lld §3 |
| `::test_load_grading_legacy_deck_picks_newest_qualifying_job` | Older job A has qualifying rows. Newer job B has only `model_arm IS NULL` rows. A row each of ghost, `value_core`, `source_like_impression_id`, `trade_intent` and NULL `assets_json` sits in A. Returns A, and only A's qualifying rows, ordered by `card_index`. |
| `::test_insert_load_round_trip_and_next_card_never_returns_arms` | `load_next_grading_card` keys == `{card_id, position, trade_json}` |
| `::test_answer_grading_card_foreign_user_returns_none` | Returns None for another user's card, and the card is unchanged |
| `::test_report_rows_since_and_include_open` | Filters work |
| `::test_account_deletion_removes_grading_rows` | `accounts.delete_user_data(UID)` removes UID's rows from both tables and keeps OTHER's |
| `test_value_core_bench.py::test_freeze_reads_through_read_only_connection` (**edit**) | Add a pick `{"pick_id":"pk3","league_id":"1234","season":2027,"round":3,"owner_user_id":"u1","pick_value":10.0,"pool_value":600.0,"source":None}` and assert `"pk3" in league["assets"]`. Every existing assert is kept. Update the `summary` `assets` count from 3 to 4. |
| `test_value_core_bench.py::test_read_league_inputs_returns_league_record_kwargs` (**new**) | On a plain in-memory SQLite connection (not the read-only wrapper), the keys == the seven names. `league_record(**inputs, meta=None, state=None)` succeeds. `inputs["players"]["p1"]["team"]` is present. |

**Verify (isolated):**

```bash
python3 -c "import backend.blind_grading, backend.eval.value_core_bench"
python3 -m pytest backend/tests/test_blind_grading_service.py backend/tests/test_blind_grading_db.py \
  backend/tests/test_value_core_bench.py backend/tests/test_account_deletion_coverage.py -q
git grep -nE "backend\.server|from \.server|from \. import server|backend\.tools|from \.tools" -- backend/blind_grading.py   # must print nothing
```

### 5.2 P2 — Routes + flags + route tests

**Owns:** see §2. Implements [lld.md §7–§8.1](lld.md#7-routes-backendserverpy) exactly.

**Acceptance criteria:**
- **The two decision points.** `_calibration_allowed` and `_grading_flag_for_caller` are the **only** two functions that decide the audience. `_grading_gate` is the outermost decorator on all five user routes.
- **Audience opening is a one-line change.** Replacing `_calibration_allowed`'s body with `return True` is the whole code change, and the test proves it.
- **The admin route** uses `_require_cron_auth()` and no gate.
- **No imports into the engine path.** `server.py` imports `backend.blind_grading` at the section, which is cheap: it imports only `database`. No route calls `trade_service`, `log_*_impressions`, `record_event` or `_trade_cards`.
- **Flags.**
  - `grading.blind` is false in `FLAG_KEYS`/`DEFAULT_FLAGS`, `config/features.json`, `release.json`, `profiles-on.json` and `onboarding-v2.json`, and absent from `all-on.json`, `release-300.json` and `release-espn-send-off.json`.
  - `draft.tab` is false in `config/features.json` and the five fixtures that carry it.
  - `profiles/draft.json` / `draft-pre.json` are untouched.
- **`test_rookie_ranks_editable.py`:** passes, with only the `…_ships_on` test renamed and flipped.

**Tests:**

| File::test | Asserts |
|---|---|
| `test_blind_grading_routes.py::test_flag_registered_default_off_and_mirrored` | As the flags criterion above |
| `::test_draft_tab_off_wherever_it_is_set` | `config/features.json` plus the five fixtures read `false`. `profiles/draft.json` reads `true`. |
| `::test_routes_404_without_flag_for_caller` | Allowlisted session. `experiments.resolve_for_unit` is monkeypatched to `({}, {})`; global off. Each of the five user routes returns 404 `{"error":"not_found"}`. |
| `::test_routes_404_when_not_allowlisted` | `server.is_enabled` is monkeypatched true for `grading.blind`, with an empty allowlist. All five routes return 404. |
| `::test_account_overlay_resolves_flag_for_caller` | `resolve_for_unit(unit)` returns `({"calibration_rollout":"treatment"}, {"calibration_rollout":{"flags":{"grading.blind":True}}})` only for the session's account unit. `GET current` returns 200, with the service stubbed. |
| `::test_device_overlay_needs_x_device_id` | The overlay is resolved only for `device:abc`. A request with `X-Device-Id: abc` returns 200; without the header, 404. |
| `::test_gate_404_precedes_verification_403` | Unverified session (`verified` falsy, not demo). Gate false ⇒ 404 on GET and POST. Gate true ⇒ 403 `verification_required`. |
| `::test_no_session_404` | No token ⇒ 404 |
| `::test_calibration_allowed_is_the_single_audience_predicate` | With an empty allowlist and the flag resolving true, monkeypatching `server._calibration_allowed` to `lambda s: True` makes `GET current` return 200. |
| `::test_create_validates_body_and_active_league` | 400 `invalid_body` without `league_id`. 400 `league_not_active` when it differs from `sess["league"].league_id`. |
| `::test_create_resume_short_circuits_network` | `current_session` returns a session. `_value_core_standings` / `_league_lineup_slots` / `_sleeper_roster_limit` are monkeypatched to `pytest.fail`. Expect 200 `resumed: true`. |
| `::test_create_passes_server_inputs_and_returns_201` | The stubbed `create_session` captures `ServerInputs`. Standings come from the monkeypatched `_value_core_standings`, plus slots, `max_players`, and untouchables / not-interested from a monkeypatched `load_asset_preferences` with `trade.preference_lists` on. The route returns 201. |
| `::test_grading_errors_map_to_json` | `GradingError("needs_fresh_deck",409,reason="stale",usable=0,min_cards=10,max_age_days=7)` ⇒ status 409 with body equal to `{"error":"needs_fresh_deck","reason":"stale","usable":0,"min_cards":10,"max_age_days":7}`. Same for `not_found`, `session_completed`, `session_incomplete` and `value_core_failed`. |
| `::test_answer_passes_raw_body` | The stubbed `answer_card` receives the exact JSON dict, and `None` for a non-JSON body |
| `::test_admin_report_cron_secret_and_ungated` | `server._CRON_SECRET` is set (monkeypatch). No header ⇒ 401. Correct header with the flag off and no allowlist ⇒ 200. `since=bad` ⇒ 400 `invalid_since`, with the service stubbed to raise. |
| `test_rookie_ranks_editable.py::test_draft_tab_flag_is_mirrored_and_ships_off` (**renamed edit**) | `features["draft.tab"] == release["draft.tab"]` and `features["draft.tab"] is False`. The docstring cites the operator's 2026-10-02 decision. |
| `test_blind_grading_e2e.py` (**integration-only**) | **Setup:** the common seed, with `deck_impressions` for job J served `NOW - 1 day`, carrying 20 qualifying cards. `backend.value_core.pipeline.run` is monkeypatched to `stub_engine` with 20 trades, one equal to a current card. Also monkeypatched: `server._value_core_standings` → `({}, 0)`; `_league_lineup_slots` / `_sleeper_roster_limit` → None; `server._load_tester_allowlist` → `{"u1"}`; `experiments.resolve_for_unit` → the account overlay for `u1`. The injected session is `{"user_id": "u1", "league_user_id": "u1", "verified": True, "league": SimpleNamespace(league_id="L1", platform="sleeper"), "players": [], "trade_svc": object(), "last_active": 0.0}`. The `league`, `players` and `trade_svc` keys are what `_require_initialized_session` checks (`server.py:2570-2585`). |
| `::test_no_response_reveals_an_arm_until_results` | **Flow:** create, then loop `next` / answer (alternating grade 4 + `["overpay"]`, grade 2, skip) until `done`. **Every response body before `results`** is collected and deep-walked. **Forbidden keys:** `{"arm","arms","arms_json","model_arm","reasons","engine","seed","source","source_json","counts","counts_json","impression_id","deck_job_id","trade_id","trade_concept_id","basis","lane","scores","priority","policy_variant","valuation_json"}`. **Forbidden string values:** `{"current","value_core","value-core-1","legacy","bakeoff","gen_v2","baseline"}`, and any value starting with `"vc_"`. Every `card.trade` matches the NeutralTrade key sets exactly, and the served `position`s are 1..N. **After completion:** `results` returns 200; `arms.current.cards + arms.value_core.cards == total + shared`; `shared == 1`. |
| `::test_shared_trade_served_once` | The shared trade's (partner, give set, receive set) occurs exactly once among the served cards |
| `::test_grading_leaves_deck_and_swipes_untouched` | Counts of `deck_impressions` / `trade_impressions` / `trade_decisions` / `swipe_decisions` and `len(trade_service._trade_cards)` are unchanged across the whole flow |
| `::test_order_is_not_blocked_by_arm` | `blind_grading.secrets.randbits` is monkeypatched to return a fixed value. The arm sequence by position (read from the DB) is not all-current-then-all-value-core. |
| `::test_stopping_the_overlay_kills_routes_not_the_report` | `resolve_for_unit` is flipped to `({}, {})` mid-flow. The next `next` returns 404. The admin report, with the cron secret, still returns 200 and includes the session when `include_open=1`. |

**Verify (isolated; e2e excluded):**

```bash
python3 -m pytest backend/tests/test_blind_grading_routes.py backend/tests/test_rookie_ranks_editable.py \
  backend/tests/test_seed_ui_test_db.py::test_release_flags_mirror_features_json \
  backend/tests/test_entitlements.py::test_features_json_keys_known \
  backend/tests/test_outlook_route_cache.py -q
python3 -c "import json;[json.load(open(p)) for p in ['config/features.json']+__import__('glob').glob('backend/tests/fixtures/flags/*.json')]"
```

**Also writes `code-walk-backend.md`,** covering the three claims in [scope.md §3](scope.md#3-evidence-scope), with file:line citations to the merged code.

### 5.3 P3 — Mobile

**Owns:** see §2. Implements [lld.md §10](lld.md#10-mobile) exactly, and writes `api/grading.ts` verbatim from §3.2.

**Acceptance criteria:**
- **Tab presence and placement.**
  - `TabNav` renders Calibration in the third slot only when `useFeatureFlags.getState().flags['grading.blind']` was true **at mount**.
  - It precedes Draft: `showCalibrationTab ? Calibration : showDraftTab ? Draft : null`.
  - The Draft `<Tab.Screen>` element is unchanged, byte for byte, apart from indentation.
  - `showDraftTab`'s `useState` initializer is untouched, so `test_rookie_ranks_editable.py:265-275` keeps passing.
- **Tab wiring.**
  - `tabBarButtonTestID: 'tab.calibration'`, `tabBarLabel: 'Calibration'`, icon `check`.
  - `trackTab('calibration', navigation)` on press; on a focused re-tap, `popNestedToTop`.
- **Tab-stack conventions.** `CalibrationStackNav` has one screen, `CalibrationHome`, with `chalklineHeader('Calibration')`. `CalibrationScreen` mounts **no** `FeedbackFAB`.
- **Card rendering.**
  - `GradingCard` renders only `GradingTrade` fields, built from Chalkline primitives (`Card`, `Text`, `TickLabel`, `Badge`/`PositionBadge`) and theme tokens.
  - No hex literals, no emoji, no gradients, no radius above 8, no flare.
- **Arm labels.** `GradingResults` is the only component with arm labels. It renders only in the results phase.
- **Screen phases and copy** per lld §10.3 and §10.6.
  - "Open Acquire" switches to the `Trades` tab.
  - The session state survives a tab switch.
  - A league switch resets the session.
- **Timeout.** `SLOW_POST_PATHS` includes `/api/grading/sessions`.
- **testIDs.** All are static literals, per scope §3.
- **Checks.** `npx tsc --noEmit` and `testid-lint.sh` are clean, and every `check-*.js` passes, including the new one.

**Tests (structural; [lld.md §10.8](lld.md#108-structural-guard--mobiletestscheck-blind-gradingjs)):** `mobile/tests/check-blind-grading.js`, assertions 0–9. Each one is sabotage-proven before hand-off. For assertions 1, 3, 4 and 6, temporarily plant the violation, confirm FAIL, and revert:
- `card.reasons` in `GradingCard`;
- a `<FeedbackFAB` in `CalibrationScreen`;
- `value_core` in `CalibrationScreen`;
- `useFlag('grading.blind')` in `TabNav`.

Record the four sabotages in `code-walk-mobile.md`.

**Verify (isolated):**

```bash
cd mobile
npx tsc --noEmit
bash scripts/testid-lint.sh
node tests/check-blind-grading.js
npm run test:blind-grading
for f in tests/check-*.js; do node "$f" > /dev/null || echo "FAIL $f"; done   # must print nothing
```

**Also writes `code-walk-mobile.md`,** covering the four claims in [scope.md §3](scope.md#3-evidence-scope) plus the sabotage log.

### 5.4 P4 — Reference docs

**Owns:** see §2. Writes from this folder only. Code citations are marked `(verify after P1/P2/P3 merge)`, and the lead resolves them at integration.

| Doc | Edit |
|---|---|
| `docs/api-reference.md` | **New H2,** "Calibration — blind grading (`/api/grading/*`; flag `grading.blind` resolved per caller, tester allowlist)", after "Test users" (`:1079`), plus its TOC line near `:106`. It covers the gate (both predicates; 404 posture; `X-Device-Id`), the five routes with request/response/errors from §3.2, the NeutralTrade shape and the blinding rule. **A row in "Admin"** (`:946`) for `GET /api/admin/grading/report` (cron secret, ungated). |
| `docs/data-dictionary.md` | **New `## Blind grading tables`** after Receipts (`:1810`): `grading_sessions` and `grading_cards`, column by column (lld §3), with the hidden-column rule, account deletion and export, and the `counts_json` / `source_json` / `arms_json` shapes. **A `tab_selected` note:** `tab`/`from_tab` gain `calibration`; `draft` is absent while `draft.tab` is false. |
| `docs/config-reference.md` | **New `grading.blind` row** next to `trade.value_core` (`:351`): false, never global, reaches testers through `calibration_rollout`, server per-caller resolution plus the allowlist, kill = stop the experiment. **Edit the `draft.tab` row:** now **false** (2026-10-02; the Calibration tab takes the slot; code kept). It must still contain "`draft.tab`" and "seasonal" (`test_rookie_ranks_editable.py:260-263`). |
| `docs/architecture.md` | **New section** "Calibration (blind grading)" after "Value-core trade engine" (`:258`), with the three layers and the data flow (hld §1–§2). **A Components › Backend row** (`:472`) for `backend/blind_grading.py`. |
| `docs/glossary.md` | **New entries:** Calibration (tab), blind grading (in-app), grading session, grading card, arm (current / value core), shared card. **Amend "Blind grade"** (`:544`) to point to Calibration. **Note** that it is distinct from Receipts grading. |
| `docs/runbook.md` | **Under "Value-core bench"** (`:421`), a subsection "Gate 2 — Calibration": allowlist edit; create, launch and stop `calibration_rollout` (curl, as in `../ram-mascot/experiment.md §4`, with the lld §8.2 fields); verify via `/api/feature-flags`; the report curl; local dev (`POST /api/cron/value-snapshot` first); the `draft.tab` rollback. |
| `docs/cross-client-invariants.md` | **New section** "Calibration tags and scale": the 7 keys, the 1–5 scale, and that `backend/blind_grading.TAGS` == `mobile/src/api/grading.ts GRADING_TAGS`. **A tab-inventory note:** the third slot is Calibration or Draft, never both. |
| `living-memory/HLD.md` | **A Major Components row** (`:80`), and "Flow C″ — Calibration (blind grading)" after Flow C′ (`:150`) |
| `living-memory/LLD.md` | **New section** "Blind grading: one neutral formatter, hidden arms, per-caller flag resolution (2026-10-02)". The conventions: `neutral_trade` is the only payload producer; `arms_json` is read only by results/report; the audience is decided only in `_calibration_allowed` + `_grading_flag_for_caller`; tab presence is mount-once. The file's TOC is updated. |

**Verify:**

```bash
python3 - <<'EOF'
import re, pathlib
for p in ["docs/api-reference.md","docs/data-dictionary.md","docs/config-reference.md","docs/architecture.md",
          "docs/glossary.md","docs/runbook.md","docs/cross-client-invariants.md",
          "living-memory/HLD.md","living-memory/LLD.md"]:
    t = pathlib.Path(p).read_text()
    for link in re.findall(r"\]\(([^)#]+\.md)", t):
        q = (pathlib.Path(p).parent / link).resolve()
        assert q.exists(), f"{p}: broken link {link}"
cfg = pathlib.Path("docs/config-reference.md").read_text()
assert "`draft.tab`" in cfg and "seasonal" in cfg and "grading.blind" in cfg
EOF
```

Then run the `living-memory-format-check` skill on `HLD.md` / `LLD.md` (TOC matches the H2s).

## 6. Integration checklist (lead)

Run on `feat/blind-grading` after all four packages have merged, from the worktree root, on Python 3.12.

1. **Contract intact.** `git diff <contract-commit> -- backend/blind_grading.py` shows only bodies and private helpers added below the public block. The signatures, constants, `GradingError` and `ServerInputs` are unchanged, or match the §3.3 log.
2. **Leaf rules.**
   - `python3 -c "import backend.blind_grading, backend.server"` succeeds.
   - `git grep -nE "backend\.server|from \.server|backend\.tools|from \.tools" -- backend/blind_grading.py backend/value_core` prints nothing.
3. **Full suite.** `python3 -m pytest backend/tests -q` is green, including:
   - `test_blind_grading_e2e.py`;
   - `test_account_deletion_coverage.py` (now parametrised over both grading tables);
   - `test_rookie_ranks_editable.py`;
   - `test_seed_ui_test_db.py::test_release_flags_mirror_features_json`;
   - `test_entitlements.py::test_features_json_keys_known`;
   - `test_value_core_bench.py`;
   - `test_bakeoff_serving.py::test_flag_off_is_byte_identical_to_the_captured_golden`, to prove the trade path is untouched.
4. **Blinding.** `python3 -m pytest backend/tests/test_blind_grading_e2e.py::test_no_response_reveals_an_arm_until_results -q` passes. Spot-read one captured `next` body.
5. **Gate behavior, local server.**
   - Start `python3 run.py` with an empty allowlist. Every `/api/grading/*` call with a valid session returns 404.
   - Set `FTF_TESTER_ALLOWLIST=<your session user_id>` while `grading.blind` is false and there is no experiment. Still 404.
   - With `FTF_FLAGS='{"grading.blind": true}'`, `GET /api/grading/sessions/current?league_id=…` returns 200.
   - Removing the allowlist entry returns it to 404.
6. **Mobile.** In `mobile/`: `npx tsc --noEmit`, `bash scripts/testid-lint.sh`, and every `tests/check-*.js`.
7. **Code-walks.** Read `code-walk-backend.md` and `code-walk-mobile.md`. Spot-check three citations against the code. Resolve P4's `(verify after merge)` markers.
8. **CI.** Push the branch, not `main`. Confirm `backend-tests`, `mobile-typecheck` and `maestro-testid-lint` are green.
9. **Bench bug (D6).** Count the `PICK` assets in the existing frozen bench file. If there are none, tell the operator, and re-freeze before trusting Gate 1.
10. **Operator hand-off, before any production write.**
    - Surface the scope §1 waiver and the prd §11 decisions D1–D9.
    - Ask the operator to add the graders' account ids to `config/tester_allowlist.json`.
    - Ask the operator to approve creating `calibration_rollout`, a production write per lld §8.2, on a free layer (check `GET /api/admin/experiments`).
    - Build TestFlight. The operator runs the scope §3 checklist; log the result in TEST_LEDGER.

## 7. Docs matrix

| Doc | Trigger (root `CLAUDE.md` / `docs/CLAUDE.md`) | Package |
|---|---|---|
| `docs/api-reference.md` | Six new routes | P4 |
| `docs/data-dictionary.md` | Two new tables; a new `tab_selected` value | P4 |
| `docs/config-reference.md` | New flag `grading.blind`; `draft.tab` default changed | P4 |
| `docs/architecture.md` + `living-memory/HLD.md` | New backend module and data flow; new mobile tab | P4 |
| `living-memory/LLD.md` | New conventions: the neutral formatter, hidden arms, the per-caller flag, the one audience predicate | P4 |
| `docs/glossary.md` | New terms | P4 |
| `docs/runbook.md` | New operator procedure (overlay, report, rollback) | P4 |
| `docs/cross-client-invariants.md` | Tag enum and scale shared by backend and mobile; the tab slot rule | P4 |
| `docs/adr/` | — n/a: no irreversible architecture. The decisions go in DECISIONS. | — |
| `docs/plans/blind-grading/code-walk-backend.md` / `code-walk-mobile.md` | Scope §3 evidence | P2 / P3 |
| `living-memory/DECISIONS.md`, `CHANGELOG.md`, `TEST_LEDGER.md`, `NEXT.md`/`HANDOFF.md` | Session write-back | **lead** |
| `docs/plans/README.md` row for `blind-grading/` | `docs/plans/CLAUDE.md` ("add the README row") | **lead** |
| `mobile/src/navigation/CLAUDE.md`, `mobile/src/screens/CLAUDE.md`, `mobile/CLAUDE.md`, `backend/CLAUDE.md` | Map rows: the tab bar is now Rank · Acquire · [Calibration\|Draft] · Matches · League. The `eval/` note "no server wiring" now has one exception, `backend/blind_grading.py` → `value_core_bench`. | **lead** (operating-contract files) |

## 8. Lead-only items

- **`docs/plans/README.md`:** add the status row for `blind-grading/`. This spec author was restricted to this folder.
- **`DECISIONS.md`:** one entry. Grep for the max D-id first; D-197 records it (D-195 went to decline reasons on main; value core is D-196). It records:
  - the operator's 2026-10-02 decisions: Calibration tab in the Draft slot; `draft.tab` off with the code kept; testers only via overlay plus allowlist;
  - the scope §1 waiver;
  - the outcomes of D1–D9.
- **CLAUDE.md map rows** (§7 last row).
- **`TEST_LEDGER.md`:** §6 results and the TestFlight outcome. **`CHANGELOG.md`:** on merge. **NEXT / HANDOFF:** as work moves.
- **Production writes** (operator approval each time): the allowlist edit; `calibration_rollout` create, launch and, later, stop; `POST /api/feature-flags/reload` after the `draft.tab` deploy.
- **Follow-up, not in this build:** D7 (CSV tag vocabulary) and D6 (re-freeze the bench).
