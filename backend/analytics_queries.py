"""analytics_queries.py — the P2 report layer (analytics platform, LLD §2.3/§4.4/§4.7).

Every report is parameterized dual-dialect SQL on the READ-ONLY engine
(`database.ro_engine`) plus Python post-processing (percentiles, week folds,
JSON shaping). The dashboard renders this JSON and computes nothing.

Design invariants (verified by the P2 design→adversarial-verify workflow):
  • Dual-dialect: NO json1/JSON_EXTRACT, NO PERCENTILE_CONT/date_trunc/strftime.
    Day bucket = substr(occurred_at,1,10); weeks folded in Python (week_key);
    JSON in props/experiments parsed in Python.
  • Window bounds compare the DATE PREFIX (substr(...,1,10)) against YYYY-MM-DD
    binds — never a 'Z'-suffixed instant against the stored '+00:00' text.
  • Read-only: every query carries a window (≤90d) + a LIMIT (row_cap).
  • Identity: user-scoped metrics exclude 'device:%' pseudo-ids; pre-auth rows
    resolve via attribution_join (nearest link ≤ occurred_at, else earliest
    after) using COALESCE(sleeper_user_id, account_id) — sleeper_user_id FIRST,
    because server rows carry the sleeper id, so coalescing account_id first
    would split one user across two ids and double-count.
  • Honest degradation: a metric whose feeding events have ZERO rows in-window
    renders a "dark" cell ("—"), never a fabricated 0. Cohort <20 → "n_too_small"
    (counts kept, rate suppressed). is_dark() separates a real 0 from "—".

Reality today (analytics.ingest=false): user_events holds only SERVER-fired
rows (event_id NULL, real user_id, but session_id/platform/device_id/screen/
client_ts all NULL). So all ALLOWED_CLIENT_EVENTS are dark, and session/
platform/screen-scoped slices render "—" until the client SDK ships. The live
surface is the signup-onward funnel, WAT, engagement/streaks, and adoption of
server-fired ranking/trade/calc/feedback events.
"""

from __future__ import annotations

import csv
import io
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import bindparam, text

from . import database as db
from .analytics_taxonomy import ALLOWED_CLIENT_EVENTS, SERVER_FIRED_EVENTS

# ---------------------------------------------------------------------------
# Canonical event sets (exact taxonomy strings)
# ---------------------------------------------------------------------------

# North star — Weekly Active Traders. The send leg went LIVE 2026-08-11 (P0-7,
# docs/business/analytics/2026-08-11-p0-7-addendum.md): historical rows carry
# none of these names, so past WAT is unchanged and only the forward series
# gains the leg.
WAT_LIVE = frozenset({"trade_proposed", "match_swiped", "calc_trade_evaluated",
                      "sleeper_send_attempted", "sleeper_send_succeeded",
                      "sleeper_send_failed"})
WAT_DARK = frozenset()
WAT_EVENTS = WAT_LIVE | WAT_DARK

# Pure lifecycle/impression noise — excluded from DAU/WAU/MAU, churn, retention.
# api_call/api_request are API-observability plumbing (obs.api_events,
# backend/api_observability.py; rows carry user_id='system:api') — they must
# never read as user intent.
NON_INTENT_EVENTS = frozenset({
    "app_opened", "app_backgrounded", "app_open", "screen_viewed",
    "push_sent", "client_error", "api_call", "api_request",
    # P0 remediation 2026-08-11 — impression / navigation / outcome class.
    # INTENT is a deny-list (see INTENT_EVENTS below), so taxonomy growth is
    # intent-by-default: without these four lines, a tab tap and a League
    # mount would make DAU/WAU ≈ app-open count from ship day and every
    # retention and churn series would break at that seam, permanently and
    # silently. Seam date is recorded in
    # docs/business/analytics/2026-08-11-p0-7-addendum.md.
    "tab_selected", "league_view", "experiment_exposed",
    "quickset_abandoned",
    # Feedback #297 / #299 / #302, 2026-08-11 — added in the SAME commit
    # that added them to ALLOWED_CLIENT_EVENTS, for the reason stated
    # directly above. Per-event reasoning (tracking plan:
    # docs/feedback/items/297-lineup-impact-single-pin/analytics.md):
    #
    #   lineup_impact_unavailable — a passive impression. The user did
    #     nothing; it is the opposite of intent. The evaluation that
    #     produced it already counts the user via the server-fired
    #     calc_trade_evaluated (INTENT, and a WAT_LIVE feeder), so
    #     admitting this row adds no user DAU has not already seen.
    #
    #   league_team_closed — a TERMINATOR, and dismissal-class like
    #     quickset_abandoned. Every close is preceded by a
    #     league_team_opened, which IS intent and already counts the user.
    #     The only user-days this could add are ones where the OPENER was
    #     lost to SDK queue overflow — i.e. an artifact, never signal.
    #     league_team_opened itself stays INTENT, untouched.
    "lineup_impact_unavailable",
    "league_team_closed",
    # Team Review (#357/#358/#359), added in the SAME commit that registered
    # them, for the reason at the top of this block.
    #   team_review_beat_viewed — an IMPRESSION, the league_view /
    #     tab_selected class. The user already emitted team_review_opened to
    #     get here; admitting beat views would let ONE flow mint six user-days.
    #   team_review_exited — a TERMINATOR, the league_team_closed class. Every
    #     exit is preceded by an open, which is already intent.
    # team_review_opened and team_review_action_taken are deliberately ABSENT:
    # both are intent, the peers of find_trades_tapped and league_candidate_pinned.
    "team_review_beat_viewed",
    "team_review_exited",
    # Feedback #300, 2026-08-12 — added in the SAME commit that added it to
    # ALLOWED_CLIENT_EVENTS, for the reason stated at the top of this block.
    # Tracking plan:
    # docs/feedback/items/300-league-rankings-trade-candidates/analytics.md.
    #
    #   league_pos_candidates_viewed — an EXPOSURE. The user tapped a
    #     position pill on a screen they had already reached; the event
    #     witnesses that a surface rendered, not that anything was wanted.
    #     Same class as league_view and tab_selected directly above. It is
    #     also the ONLY event on this screen that a user can emit without
    #     ever drilling in, so admitting it to INTENT would promote every
    #     idle filter tap to a user-day and step-change DAU from ship day —
    #     precisely the artifact this deny-list exists to prevent.
    #
    # league_candidate_pinned is deliberately ABSENT from this set: it IS
    # intent (an asset chosen, the finder entered), the peer of
    # find_trades_tapped and league_team_opened. It adds no DAU seam either
    # way — the row action lives inside the drill-in, which is reachable
    # only through openTeam, so every pin is preceded in the same session
    # by a league_team_opened that already counts the user.
    "league_pos_candidates_viewed",
    # P1 remediation commit T1, 2026-08-11 — added in the SAME commit that
    # added them to ALLOWED_CLIENT_EVENTS, for the reason stated above.
    # Operator decision AN-4 (DECISIONS-p1.md D-P1-13). Per-event reasoning:
    #
    #   share_package_created — a SYSTEM OUTCOME, not the user action that
    #     provoked it. The tap is already counted by calc_trade_shared /
    #     trade_card_shared (both INTENT), so admitting this row adds no
    #     user-day DAU has not already seen — it only double-counts. It is
    #     also fired dismissal-INDEPENDENTLY (the mint resolves whether or
    #     not the user goes through with the share), so under the eager-mint
    #     variant it can fire with no completed user gesture at all.
    #
    #   invite_cta_shown — an IMPRESSION, fired on League Home and Matches
    #     mounts. The user did nothing. Leaving it INTENT would make DAU/WAU
    #     approximate app-open count from the day its emitter ships and
    #     break every retention and churn series at that seam, silently and
    #     permanently. Its tapped counterpart carries the intent.
    #
    # Deliberately NOT here, i.e. deliberately INTENT: calc_trade_shared
    # (a user tapped share and completed it) and invite_cta_tapped (a real
    # decision, and the growth action this whole round exists to measure).
    "share_package_created",
    "invite_cta_shown",
    # ── #295/#296/#305 mock-draft family, 2026-08-13 — added in the SAME
    # commit that registered the family in ALLOWED_CLIENT_EVENTS, for the
    # reason stated at the top of this block (INTENT is derived by
    # subtraction; a NON_INTENT name registered without its deny-list row
    # silently step-changes DAU/retention from ship day). Per-event:
    #
    #   mock_completed — an OUTCOME, not an action. The final tap is
    #     already counted by its own mock_pick_made (INTENT); this row only
    #     witnesses the status flip and would double-count the user-day.
    #
    #   mock_create_refused — the IMPRESSION of a refusal. The user's tap
    #     is already counted by the create attempt's surrounding intent
    #     events; the refusal itself is something done TO the user.
    #
    # Deliberately NOT here, i.e. deliberately INTENT: mock_started,
    # mock_pick_made, mock_abandoned — all three are real user decisions.
    "mock_completed",
    "mock_create_refused",
    # Bell inbox instrumentation, 2026-08-13 — added in the SAME commit that
    # added them to ALLOWED_CLIENT_EVENTS, for the reason stated above.
    # Tracking plan: docs/plans/notif-inbox-growth/analytics.md.
    #
    #   notif_inbox_opened — NAVIGATION class, the peer of tab_selected and
    #     league_view directly above. Opening the bell is a glance at a
    #     surface, not a decision about anything on it. It is also the
    #     DENOMINATOR for the other two, and a denominator that inflates
    #     DAU is worse than no denominator at all: the bell sits in the
    #     global TopBar on every tab, so admitting it would promote an idle
    #     bell tap to a user-day from ship day.
    #
    #   notif_empty_state_shown — an IMPRESSION, fired when the sheet opens
    #     onto nothing. Identical class to invite_cta_shown above. Every
    #     firing is preceded in the same tap by a notif_inbox_opened, so it
    #     can add no user-day that event has not already declined to add.
    #
    # Deliberately NOT here, i.e. deliberately INTENT: notif_row_tapped. A
    # user chose one row out of a list — the single number this batch was
    # built to produce.
    "notif_inbox_opened",
    "notif_empty_state_shown",
    # ── Dropped-emitter backlog registration, 2026-08-13 — added in the
    # SAME commit that registered 27 long-dropped live emitters in
    # ALLOWED_CLIENT_EVENTS (tracking plan:
    # docs/business/analytics/2026-08-13-dropped-emitter-backlog.md).
    # Per-event:
    #
    #   prompt_shown / push_primer_shown / notif_denied_settings_shown —
    #     IMPRESSIONS. The user did nothing; a surface rendered. Same
    #     class as invite_cta_shown above.
    #
    #   apple_banner_dismissed / push_primer_dismissed — dismissal-class,
    #     like quickset_abandoned and league_team_closed: something shown
    #     TO the user was waved away. The accepted twins stay INTENT.
    #
    #   deck_summary_viewed — an end-of-deck IMPRESSION; every firing is
    #     preceded in-session by the swipes that produced the tally.
    #
    #   trio_session_started — fires on RankScreen MOUNT, once per visit:
    #     navigation class, the peer of league_view and notif_inbox_opened.
    #     The retention read that consumes it queries the name directly and
    #     is unaffected by intent classification.
    #
    #   rating_prompt_requested — a SYSTEM OUTCOME: the client asked
    #     StoreKit for a review dialog the OS may never show. Nothing the
    #     user chose.
    #
    # Deliberately NOT here, i.e. deliberately INTENT: every other name in
    # the 2026-08-13 batch — undo taps, menu opens, mode changes, help
    # opens, pin/keep/swap/remove card actions, push_primer_accepted,
    # notif_denied_settings_tapped, trio_entry_tapped — all real user
    # decisions, the peers of find_trades_tapped and league_team_opened.
    "prompt_shown",
    "push_primer_shown",
    "notif_denied_settings_shown",
    "apple_banner_dismissed",
    "push_primer_dismissed",
    "deck_summary_viewed",
    "trio_session_started",
    #   guide_step_suppressed — a SYSTEM refusal (guided-onboarding-v2
    #   FR-E5): the engine declined to show a beat. No user intent at all.
    #   awaiting_segment_viewed — a segment-focus IMPRESSION, same class as
    #   deck_summary_viewed; the intent event is the send attempt.
    "guide_step_suppressed",
    "awaiting_segment_viewed",
    "rating_prompt_requested",
    # ── Premium rankings import v1, 2026-08-15 ([D-058]) — added in the
    # SAME commit that registered them in ALLOWED_CLIENT_EVENTS, for the
    # reason stated at the top of this block. Scope:
    # docs/plans/connected-rankings/build-v1-premium-import/scope.md §1.
    #
    #   rankings_preset_detected — a PIPELINE OUTCOME mid-flow: a header
    #     signature matched and a confirmation step cleared. The user's
    #     decision is the apply that follows (`rankings_import_applied`,
    #     server-fired and INTENT), and a detection that the user abandons
    #     is precisely a non-conversion — admitting it to INTENT would
    #     credit a user-day to a flow nobody finished.
    #
    #   rankings_preset_fallback — the same, on the miss branch: a file
    #     shape we could not recognize. Nothing was chosen.
    #
    # Neither can add a user-day that the file-intake gesture ahead of it
    # (and the apply behind it) does not already account for.
    "rankings_preset_detected",
    "rankings_preset_fallback",
    # #362 standing offers, 2026-08-19 — added in the SAME commit that added
    # them to ALLOWED_CLIENT_EVENTS / SERVER_FIRED_EVENTS, for the reason
    # stated above: INTENT_EVENTS is derived by SUBTRACTION, so omitting an
    # impression-class name silently inflates DAU/WAU from ship day.
    # `standing_offer_posted` and `standing_offer_revoked` are deliberately
    # ABSENT — both are deliberate user actions and belong in INTENT.
    "standing_offer_prompted", "standing_offer_skipped",
    "standing_offer_card_shown",
    # ── Receipts, 2026-08-21 (docs/plans/receipts/, PRD DR-9) — added in the
    # SAME commit that registered it in analytics_taxonomy, for the reason
    # stated at the top of this block.
    #
    #   receipts_grade_run — SERVER-fired, one row per grading run, carrying
    #     user_id="system:receipts". It fires on a daily cron tick whether or
    #     not a human opened the app, so admitting it to INTENT would mint a
    #     user-day out of a background job and step-change DAU/WAU at the
    #     seam. The `api_call` / `api_request` class exactly.
    #
    # `receipts_opened` is deliberately ABSENT from this deny-list and stays
    # INTENT: opening your own track record is a deliberate feature
    # engagement, the peer of `find_trades_tapped`. Its NON_INTENT sibling
    # `receipts_window_changed` (navigation, the `tab_selected` class) lands
    # here with the screen that emits it.
    "receipts_grade_run",
    # `receipts_window_changed` — navigation, the `tab_selected` class, added
    # in the SAME commit as its emitter. Every emission is preceded on the
    # same screen by `receipts_opened`, which IS intent and already counts the
    # user, so no user-day exists for this to add. `receipts_opened` itself
    # stays deliberately ABSENT from this deny-list.
    "receipts_window_changed",
    # ── #384 merged calculator + finder, 2026-08-22 — added in the SAME
    # commit that registered the batch in ALLOWED_CLIENT_EVENTS, for the
    # reason stated at the top of this block. Addendum:
    # docs/business/analytics/2026-08-22-384-calc-finder-addendum.md.
    # Per-event, one line each:
    #
    #   calc_tour_started — the tour AUTO-starts on landing on the
    #     calculator, so this is a MOUNT counter for a primary surface (the
    #     `trio_session_started` class); admitting it would promote every
    #     calculator visit to a user-day and step-change DAU from ship day.
    #   calc_tour_ended — a TERMINATOR, the `league_team_closed` /
    #     `team_review_exited` class; every end is preceded by its own start.
    #   calc_tour_beat_missing — a SCRIPT DEFECT diagnostic: a beat the
    #     builder could not resolve. Nothing the user did or was shown.
    #   trade_pass_overlay_opened — an EXPOSURE of the capture surface, not
    #     the decision it collects (`trade_pass_layer1`/`_layer2` carry that
    #     and stay INTENT); an overlay opened and dismissed without a choice
    #     is a NON-conversion, and crediting it a user-day would be the
    #     `rankings_preset_detected` mistake.
    #   trade_pass_overlay_dismissed — a DISMISSAL, the
    #     `apple_banner_dismissed` class: something shown TO the user waved
    #     away. Every one is preceded on the same card by trade_card_viewed.
    #   prompt_deferred — a SYSTEM REFUSAL, the exact peer of
    #     `guide_step_suppressed`: the arbiter declined to show a prompt. The
    #     user chose nothing and, on the `blocked_by:'tour'` lane, was shown
    #     nothing. Its granted twin `prompt_shown` is already here.
    #
    # Deliberately NOT here, i.e. deliberately INTENT: calc_mode_switched,
    # calc_asset_added, calc_cleared, calc_find_a_trade_tapped,
    # calc_trade_queued, deck_back_to_calculator, deck_unpin_retry,
    # deck_search_all_tapped — all eight are real user decisions (a
    # configuration change, the core add-an-asset gesture, a deliberate clear,
    # the hand-off tap, the ✓ queue tap, and three deck actions reachable only
    # from a deck the user asked for). Every one of them fires behind an INTENT
    # event that already counts the user that day, so none opens a DAU seam.
    # (`calc_include_players_toggled` was on this list until 2026-08-22; W6-B
    # / D-153 removed the toggle, so the name is gone from the taxonomy too.)
    #
    # `calc_trade_queued` (#384 W6-A / D-152) is the one worth spelling out,
    # because it fires on a REFUSAL too. The tap is the user's decision to
    # offer the trade; the server's `queued: false` is the answer to that
    # decision, not an unbidden impression — the `sleeper_send_attempted`
    # class, not `prompt_deferred`. ("Unreachable without a filled canvas"
    # stopped being true with #402 rev-3: the ShopAsset window's ✓ queue
    # tap reaches it canvas-free — but that path opens with `shop_opened`,
    # which is INTENT, so the user-day is still already counted on every
    # route to this event. QA-B F4, comment-only.)
    "calc_tour_started",
    "calc_tour_ended",
    "calc_tour_beat_missing",
    "trade_pass_overlay_opened",
    "trade_pass_overlay_dismissed",
    "prompt_deferred",
    # ── Paywall funnel (IAP enablement, 2026-08-28) — added in the SAME
    # commit that registered the five in ALLOWED_CLIENT_EVENTS, for the
    # reason stated at the top of this block. Scope:
    # docs/plans/monetization/iap-enablement/scope.md §1.
    #
    # ALL FIVE are NON_INTENT, which is deliberate and worth the paragraph
    # because two of them look like conversions:
    #
    #   paywall_viewed — the IMPRESSION of a surface the user did not ask
    #     for. The paywall is pushed at them (a 402 gate, an onboarding
    #     beat), which is the `invite_cta_shown` / `prompt_shown` class
    #     exactly. Admitting it would let one interstitial mint a user-day.
    #   paywall_purchase_initiated / _completed / _failed — the purchase
    #     itself is a real decision, but it is NOT OURS TO COUNT: the
    #     authoritative row is the server-fired `entitlement_granted` the
    #     RevenueCat webhook writes (INTENT, and it cannot be spoofed by a
    #     client). These three are the UI echo used to reconcile against it
    #     — admitting them would double-count every purchaser's user-day
    #     and, worse, let a client mint one for a purchase that never
    #     cleared the store. `_failed` is a defect signal, not a decision.
    #   paywall_restore — an outcome the STORE produced, the
    #     `share_package_created` class: the tap that provoked it happens
    #     inside a session that already counted the user (Settings, or the
    #     paywall itself), and a restore that finds nothing is the opposite
    #     of a conversion.
    #
    # Nothing on this surface is deliberately INTENT — the whole paywall
    # funnel is measured against the server's grant row, on purpose.
    "paywall_viewed",
    "paywall_purchase_initiated",
    "paywall_purchase_completed",
    "paywall_purchase_failed",
    "paywall_restore",
})
# INTENT is a deny-list in SQL so taxonomy growth is intent-by-default.
INTENT_EVENTS = (SERVER_FIRED_EVENTS | ALLOWED_CLIENT_EVENTS) - NON_INTENT_EVENTS

# Funnel v2 stages (program plan). Each stage → its entry event(s); we tag the
# subset that is LIVE server-side today so the waterfall degrades honestly.
FUNNEL_STAGES = [
    (0, "install",          ["app_opened"]),                                   # dark
    (1, "signin_started",   ["signin_attempted"]),                             # dark
    (2, "signed_in",        ["signin_succeeded", "signup"]),                   # signup live
    (3, "league_selected",  ["league_selected"]),                             # dark
    (4, "board_started",    ["trio_swipe", "tier_save", "anchor_answered",
                             "quickset_completed", "quickrank_completed"]),   # live
    (5, "activated",        ["ranking_complete_first_time"]),                 # live
    (6, "first_suggestions",["trades_generated"]),                            # live
    (7, "first_opinion",    ["trade_proposed", "match_swiped"]),              # live
    (8, "matched",          ["trade_ratified", "sleeper_send_succeeded"]),    # ratified live
]

# Feature verticals for R6, mapped to event_type(s). Mostly live server events.
FEATURE_VERTICALS = {
    "rank_trios":     ["trio_swipe"],
    "rank_tiers":     ["tier_save"],
    "rank_quickset":  ["quickset_completed"],
    "rank_quickrank": ["quickrank_completed"],
    "rank_anchors":   ["anchor_answered"],
    "rank_manual":    ["ranking_reorder"],
    "calculator":     ["calc_trade_evaluated"],
    "trades_deck":    ["trades_generated", "trade_proposed", "match_swiped"],
    "matches":        ["match_viewed", "trade_ratified", "match_dismissed"],
    "leagues":        ["league_synced"],
    "feedback":       ["feedback_submitted"],
    "send_in_sleeper":["sleeper_send_succeeded"],   # live 2026-08-11 (P0-7)
}

VALID_REPORTS = ("overview", "waterfall", "time", "bottlenecks", "churn",
                 "releases", "adoption", "engagement", "pfo", "onepager",
                 "journeys", "retention", "segments", "rankquality",
                 "apihealth")
WINDOW_MAX_DAYS = 90
N_MIN = 20
ROW_CAP_JSON = 5000
ROW_CAP_CSV = 50000


class BadParam(ValueError):
    """400 bad_param — surfaced by the route as JSON, never a 500."""


# ---------------------------------------------------------------------------
# Shared fragments (LLD §4.7)
# ---------------------------------------------------------------------------

_ATTR = """
CASE WHEN {a}.user_id NOT LIKE 'device:%' THEN {a}.user_id
ELSE COALESCE(
  (SELECT COALESCE(il.sleeper_user_id, il.account_id) FROM identity_links il
    WHERE il.device_id = {a}.device_id AND il.linked_at <= {a}.occurred_at
    ORDER BY il.linked_at DESC LIMIT 1),
  (SELECT COALESCE(il.sleeper_user_id, il.account_id) FROM identity_links il
    WHERE il.device_id = {a}.device_id
    ORDER BY il.linked_at ASC LIMIT 1)) END"""


def attribution_join(alias="ue", as_col="resolved_user_id"):
    """SELECT-list expression resolving pre-auth device: rows to the signed-in
    identity (sleeper id first — see module docstring). Passthrough for
    non-device rows; NULL for a device that never linked (caller drops NULLs
    for user-scoped metrics). Correlated subqueries ride
    ix_identity_links_device_linked."""
    return f"({_ATTR.format(a=alias).strip()}) AS {as_col}"


def device_exclusion(alias="ue", id_col=None, include_demo=False,
                     tester_device_ids=None, start_day=None, end_day=None):
    """WHERE-predicate fragment. Strips 'device:%' pseudo-ids ALWAYS; strips
    demo_/test_ ids + in-window demo_entered sessions + tester-allowlist devices
    UNLESS include_demo. NULL-safe (the demo NOT EXISTS tolerates NULL session)
    and windowed (the demo subquery carries the same window, never a full
    scan). Returns (sql, params); compose with ' AND '."""
    idc = id_col or f"{alias}.user_id"
    parts = [f"{idc} NOT LIKE 'device:%'"]
    params: dict = {}
    if not include_demo:
        parts.append(f"{idc} NOT LIKE 'demo\\_%' ESCAPE '\\'")
        parts.append(f"{idc} NOT LIKE 'test\\_user\\_fp\\_%' ESCAPE '\\'")
        # Synthetic QA stage-users (backend/test_users.py) — never cohort data.
        parts.append(f"{idc} NOT LIKE 'qa\\_%' ESCAPE '\\'")
        # NULL-safe windowed demo-session exclusion (server rows have NULL
        # session_id → NOT EXISTS is true for them, correctly kept).
        parts.append(
            f"NOT EXISTS (SELECT 1 FROM user_events de "
            f"WHERE de.session_id = {alias}.session_id "
            f"AND de.event_type = 'demo_entered' "
            f"AND substr(de.occurred_at,1,10) >= :dx_start "
            f"AND substr(de.occurred_at,1,10) <= :dx_end)")
        params["dx_start"] = start_day
        params["dx_end"] = end_day
        ids = list(tester_device_ids or [])
        if ids:
            keys = [f"tdev_{i}" for i in range(len(ids))]
            params.update(dict(zip(keys, ids)))
            joined = ", ".join(f":{k}" for k in keys)
            parts.append(f"COALESCE({alias}.device_id,'') NOT IN ({joined})")
    return " AND ".join(parts), params


def week_key(day_str: str) -> str:
    """'YYYY-MM-DD' → that ISO week's Monday (UTC), 'YYYY-MM-DD'."""
    y, m, d = (int(x) for x in day_str.split("-"))
    iso_y, iso_w, _ = date(y, m, d).isocalendar()
    return date.fromisocalendar(iso_y, iso_w, 1).isoformat()


def percentile(vals, q):
    """Type-7 linear-interp percentile (numpy default), pure Python."""
    xs = sorted(v for v in vals if v is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


# ---------------------------------------------------------------------------
# Insufficiency / envelope helpers
# ---------------------------------------------------------------------------

def _tester_device_ids() -> list[str]:
    """Operator/tester device allowlist excluded from cohort metrics. Empty
    today (no client rows exist until the SDK ships); when needed, source it
    from an env var or a dedicated string-config table — model_config is
    float-only so it can't hold a JSON array. Returns [] safely for now."""
    import os
    raw = os.environ.get("ANALYTICS_TESTER_DEVICE_IDS", "")
    return [x.strip() for x in raw.split(",") if x.strip()] if raw else []


def is_dark(conn, feeders, start_day, end_day) -> bool:
    """True when NONE of `feeders` have a row in-window — the signal that
    separates a real 0 from a '—' (never fabricate zeros)."""
    if not feeders:
        return True
    q = text(
        "SELECT 1 FROM user_events WHERE event_type IN :ev "
        "AND substr(occurred_at,1,10) >= :s AND substr(occurred_at,1,10) <= :e "
        "LIMIT 1"
    ).bindparams(bindparam("ev", expanding=True))
    hit = conn.execute(q, {"ev": list(feeders), "s": start_day, "e": end_day}).first()
    return hit is None


def rate_cell(numerator, denominator, dark, n_min=N_MIN):
    """The single insufficiency decision point. dark → '—'; small n → suppress
    the rate but keep counts; else the number."""
    if dark:
        return {"value": None, "n": None, "caveat": "dark"}
    if denominator is None or denominator < n_min:
        return {"value": None, "n": denominator, "caveat": "n_too_small"}
    return {"value": (numerator / denominator) if denominator else 0.0,
            "n": denominator, "caveat": None}


def _envelope(report, start_day, end_day, rows, caveats, params_echo):
    return {
        "report": report,
        "window": {"start": start_day, "end": end_day, "tz": "UTC",
                   "week_definition": "ISO Monday 00:00 UTC, keyed by the Monday's date"},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "params": params_echo,
        "caveats": caveats,
        "rows": rows,
    }


def _dark_caveat(scope, detail):
    return {"code": "dark", "scope": scope, "detail": detail}


# ---------------------------------------------------------------------------
# Base scans (window-bounded, LIMITed, attribution-resolved)
# ---------------------------------------------------------------------------

def _resolved_intent_days(conn, start_day, end_day, event_filter, params_extra,
                          include_demo, row_cap):
    """Rows of (day, resolved_user_id) for a WHERE `event_filter` (a SQL
    predicate string over ue.*), attribution-resolved and device-excluded.
    Used by DAU/WAU/MAU/WAT and any distinct-user-by-week metric."""
    excl, ex_params = device_exclusion(
        alias="t", id_col="t.resolved_user_id", include_demo=include_demo,
        tester_device_ids=_tester_device_ids(), start_day=start_day, end_day=end_day)
    sql = f"""
        SELECT day, resolved_user_id, session_id, device_id FROM (
          SELECT substr(ue.occurred_at,1,10) AS day,
                 {attribution_join('ue')},
                 ue.session_id AS session_id, ue.device_id AS device_id
            FROM user_events ue
           WHERE substr(ue.occurred_at,1,10) >= :start_day
             AND substr(ue.occurred_at,1,10) <= :end_day
             AND ({event_filter})
        ) t
        WHERE t.resolved_user_id IS NOT NULL AND {excl}
        GROUP BY day, resolved_user_id, session_id, device_id
        LIMIT :row_cap"""
    stmt = text(sql)
    p = {"start_day": start_day, "end_day": end_day, "row_cap": row_cap}
    p.update(params_extra)
    p.update(ex_params)
    # expanding binds present in event_filter must be declared by the caller via
    # params_extra keys; we bind them here. (frozenset is NOT a subclass of set,
    # so check it explicitly — this bit once.)
    for k, v in list(params_extra.items()):
        if isinstance(v, (list, tuple, set, frozenset)):
            stmt = stmt.bindparams(bindparam(k, expanding=True))
            p[k] = sorted(v)
    return conn.execute(stmt, p).mappings().all()


# ---------------------------------------------------------------------------
# Overview — the dashboard home (Fullstory-style KPI cards + daily series).
# Every KPI ships as {label, value, delta_pct, series[], unit, caveat} so the
# renderer can draw a big number, a sparkline, and a WoW delta with no client
# computation. Coverage tells the operator exactly what is measured vs waiting.
# ---------------------------------------------------------------------------

def _daily_distinct(conn, start_day, end_day, event_filter, params, include_demo, row_cap):
    """[(day, n_distinct_users)] for the window, zero-filled across every day."""
    rows = _resolved_intent_days(conn, start_day, end_day, event_filter, params,
                                 include_demo, row_cap)
    by_day = defaultdict(set)
    for r in rows:
        by_day[r["day"]].add(r["resolved_user_id"])
    out = []
    d0, d1 = date.fromisoformat(start_day), date.fromisoformat(end_day)
    cur = d0
    while cur <= d1:
        k = cur.isoformat()
        out.append({"day": k, "value": len(by_day.get(k, set()))})
        cur += timedelta(days=1)
    return out


def _delta_pct(series):
    """Trailing-7d vs prior-7d % change on a daily series (None when no base)."""
    vals = [p["value"] for p in series]
    if len(vals) < 14:
        return None
    cur, prev = sum(vals[-7:]), sum(vals[-14:-7])
    if prev == 0:
        return None
    return (cur - prev) / prev


def _event_count(conn, start_day, end_day, events):
    q = text(
        "SELECT COUNT(*) FROM user_events WHERE event_type IN :ev "
        "AND substr(occurred_at,1,10) >= :s AND substr(occurred_at,1,10) <= :e "
        "AND user_id NOT LIKE 'device:%'"
    ).bindparams(bindparam("ev", expanding=True))
    return conn.execute(q, {"ev": list(events), "s": start_day, "e": end_day}).scalar() or 0


def report_overview(conn, start_day, end_day, include_demo, row_cap, **_):
    caveats = []
    kpis = []

    # --- Active users (intent) + WAT north star, as daily series -----------
    active = _daily_distinct(conn, start_day, end_day,
                             "ue.event_type NOT IN :non_intent",
                             {"non_intent": NON_INTENT_EVENTS}, include_demo, row_cap)
    wat = _daily_distinct(conn, start_day, end_day, "ue.event_type IN :wat",
                          {"wat": WAT_LIVE}, include_demo, row_cap)
    total_active = len({u for r in _resolved_intent_days(
        conn, start_day, end_day, "ue.event_type NOT IN :non_intent",
        {"non_intent": NON_INTENT_EVENTS}, include_demo, row_cap)
        for u in [r["resolved_user_id"]]})
    wat_users = len({r["resolved_user_id"] for r in _resolved_intent_days(
        conn, start_day, end_day, "ue.event_type IN :wat", {"wat": WAT_LIVE},
        include_demo, row_cap)})

    kpis.append({"key": "active_users", "label": "Active users",
                 "sublabel": "distinct, intent events", "value": total_active,
                 "unit": "count", "series": active, "delta_pct": _delta_pct(active),
                 "caveat": None})
    kpis.append({"key": "wat", "label": "Weekly Active Traders",
                 "sublabel": "north star — a trade opinion", "value": wat_users,
                 "unit": "count", "series": wat, "delta_pct": _delta_pct(wat),
                 "caveat": None})

    # --- Trade-loop volume (the product's reason for existing) -------------
    decks = _event_count(conn, start_day, end_day, ["trades_generated"])
    opinions = _event_count(conn, start_day, end_day, ["trade_proposed", "match_swiped"])
    matches = _event_count(conn, start_day, end_day, ["trade_ratified"])
    kpis.append({"key": "decks", "label": "Trade decks generated", "sublabel": "server-fired",
                 "value": decks, "unit": "count", "series": None,
                 "delta_pct": None, "caveat": None if decks else "no_data"})
    kpis.append({"key": "opinions", "label": "Trade opinions", "sublabel": "likes + passes",
                 "value": opinions, "unit": "count", "series": None,
                 "delta_pct": None, "caveat": None if opinions else "no_data"})
    kpis.append({"key": "matches", "label": "Mutual matches", "sublabel": "both sides accepted",
                 "value": matches, "unit": "count", "series": None,
                 "delta_pct": None, "caveat": None if matches else "no_data"})

    # --- Activation (live: signup → first board unlock) --------------------
    su = {r["resolved_user_id"] for r in _resolved_intent_days(
        conn, start_day, end_day, "ue.event_type IN :ev", {"ev": {"signup"}},
        include_demo, row_cap)}
    ac = {r["resolved_user_id"] for r in _resolved_intent_days(
        conn, start_day, end_day, "ue.event_type IN :ev",
        {"ev": {"ranking_complete_first_time"}}, include_demo, row_cap)}
    act_cell = rate_cell(len(su & ac), len(su),
                         dark=is_dark(conn, ["signup"], start_day, end_day))
    kpis.append({"key": "activation", "label": "Activation", "sublabel": "signup → board unlocked",
                 "value": act_cell["value"], "unit": "rate", "series": None,
                 "delta_pct": None, "n": act_cell["n"], "caveat": act_cell["caveat"]})

    # --- Frustration signals (Fullstory-style; ours are product-specific) ---
    # insult rate + client errors are client-fired → dark until the SDK ships.
    frustration = []
    for label, evs, denom_evs in (
        ("Flagged trades (insult)", ["trade_flagged"], ["trade_card_viewed"]),
        ("API failures", ["api_request_failed"], None),
        ("Client errors", ["client_error"], None),
        ("Sign-in failures", ["signin_failed"], ["signin_attempted"]),
    ):
        dark = is_dark(conn, evs, start_day, end_day)
        n = 0 if dark else _event_count(conn, start_day, end_day, evs)
        denom = _event_count(conn, start_day, end_day, denom_evs) if denom_evs and not dark else None
        frustration.append({"label": label, "count": None if dark else n,
                            "rate": (n / denom) if denom else None,
                            "caveat": "dark" if dark else None})

    # --- Top failing routes (props parsed in Python — no json1) ------------
    # A raw failure count is not actionable; the route × status pair is. Prod
    # 2026-08-05 showed /api/league/format-stats → 409 fourteen times (the
    # session_not_initialized race) hiding behind an undifferentiated "81".
    failing = []
    try:
        prop_rows = conn.execute(text(
            "SELECT props FROM user_events WHERE event_type = 'api_request_failed' "
            "AND substr(occurred_at,1,10) >= :s AND substr(occurred_at,1,10) <= :e "
            "LIMIT :cap"), {"s": start_day, "e": end_day, "cap": row_cap}).scalars().all()
        agg = defaultdict(int)
        for raw in prop_rows:
            try:
                p = json.loads(raw) if raw else {}
            except Exception:
                continue
            agg[(p.get("route") or "?", p.get("status"))] += 1
        failing = [{"route": r, "status": s, "count": n}
                   for (r, s), n in sorted(agg.items(), key=lambda kv: -kv[1])[:8]]
    except Exception:
        failing = []

    # --- Coverage: what's measured vs waiting (honest, not depressing) -----
    live_types = conn.execute(text(
        "SELECT DISTINCT event_type FROM user_events "
        "WHERE substr(occurred_at,1,10) >= :s AND substr(occurred_at,1,10) <= :e "
        "LIMIT 200"), {"s": start_day, "e": end_day}).scalars().all()
    live_set = set(live_types)
    client_dark = sorted(ALLOWED_CLIENT_EVENTS - live_set)
    coverage = {
        "events_flowing": sorted(live_set),
        "client_events_dark": client_dark[:12],
        "client_events_dark_total": len(client_dark),
        "status": ("client_capture_off" if client_dark else "full"),
        "explain": ("Server-fired events are flowing. Client events (install, "
                    "sign-in funnel, think-time, errors) start flowing when "
                    "analytics.ingest is enabled and an app build carries the SDK."),
    }
    caveats.append(_dark_caveat("coverage:client_events",
                                f"{len(client_dark)} client event types have no rows in window — "
                                "metrics that need them render — rather than a fabricated 0"))
    return ({"kpis": kpis, "frustration": frustration,
             "failing_routes": failing, "coverage": coverage}, caveats, None)


# ---------------------------------------------------------------------------
# R7 — Engagement & Streaks (the live-heavy flagship for today's data)
# ---------------------------------------------------------------------------

def report_engagement(conn, start_day, end_day, include_demo, row_cap, **_):
    caveats = []
    # DAU/WAU/MAU + WAT off INTENT / WAT feeders. Distinct users per grain.
    intent_rows = _resolved_intent_days(
        conn, start_day, end_day, "ue.event_type NOT IN :non_intent",
        {"non_intent": NON_INTENT_EVENTS}, include_demo, row_cap)
    wat_rows = _resolved_intent_days(
        conn, start_day, end_day, "ue.event_type IN :wat",
        {"wat": WAT_LIVE}, include_demo, row_cap)

    # Fold to weekly distinct-user sets.
    by_week_intent = defaultdict(set)
    by_day_intent = defaultdict(set)
    for r in intent_rows:
        by_week_intent[week_key(r["day"])].add(r["resolved_user_id"])
        by_day_intent[r["day"]].add(r["resolved_user_id"])
    by_week_wat = defaultdict(set)
    for r in wat_rows:
        by_week_wat[week_key(r["day"])].add(r["resolved_user_id"])

    mau = len({u for s in by_day_intent.values() for u in s})
    dau_median = percentile([len(s) for s in by_day_intent.values()], 0.5)

    # Streak distribution from users.current_streak (live hot column). The
    # users PK is sleeper_user_id; demo users are demo_user_*.
    streak_rows = conn.execute(text(
        "SELECT current_streak AS s, COUNT(*) AS n FROM users "
        "WHERE current_streak IS NOT NULL AND current_streak > 0 "
        "AND sleeper_user_id NOT LIKE 'demo\\_%' ESCAPE '\\' "
        "GROUP BY current_streak ORDER BY current_streak LIMIT :cap"
    ), {"cap": row_cap}).mappings().all()
    streak_dist = {int(r["s"]): int(r["n"]) for r in streak_rows}

    # Push funnel: push_sent live, push_opened dark.
    push_dark = is_dark(conn, ["push_opened"], start_day, end_day)
    push_sent = conn.execute(text(
        "SELECT COUNT(*) FROM user_events WHERE event_type='push_sent' "
        "AND substr(occurred_at,1,10) >= :s AND substr(occurred_at,1,10) <= :e"
    ), {"s": start_day, "e": end_day}).scalar() or 0

    weeks = sorted(set(by_week_intent) | set(by_week_wat))
    wat_dark = is_dark(conn, WAT_LIVE, start_day, end_day)
    rows = []
    for wk in weeks:
        wau = len(by_week_intent.get(wk, set()))
        wat_n = len(by_week_wat.get(wk, set()))
        rows.append({
            "week": wk,
            "wau": wau,
            "wat": ({"value": None, "n": None, "caveat": "dark"} if wat_dark
                    else {"value": wat_n, "n": wau, "caveat": None}),
        })
    # The unconditional "send leg not in taxonomy yet" caveat was deleted with
    # P0-7 (2026-08-11): the three sleeper_send_* names are in WAT_LIVE, so a
    # window with no send rows already renders per-week caveat "dark" through
    # wat_dark above. A second is_dark() call would re-query for a caveat the
    # rows already carry.
    if push_dark:
        caveats.append(_dark_caveat("metric:push.opened",
                                    "push_opened is a dark client event; open-rate renders — until the SDK ships"))
    summary = {
        "mau": mau,
        "dau_median": dau_median,
        "streak_distribution": streak_dist,
        "push_sent": push_sent,
        "push_open_rate": {"value": None, "n": push_sent, "caveat": "dark"} if push_dark
                          else {"value": None, "n": push_sent, "caveat": None},
    }
    return rows, caveats, summary


# ---------------------------------------------------------------------------
# R6 — Feature Adoption Matrix (live server events)
# ---------------------------------------------------------------------------

def report_adoption(conn, start_day, end_day, include_demo, row_cap, **_):
    caveats = []
    # WAT users for overlap.
    wat_rows = _resolved_intent_days(conn, start_day, end_day,
                                     "ue.event_type IN :wat", {"wat": WAT_LIVE},
                                     include_demo, row_cap)
    wat_users = {r["resolved_user_id"] for r in wat_rows}

    rows = []
    for vert, evs in FEATURE_VERTICALS.items():
        dark = is_dark(conn, evs, start_day, end_day)
        if dark:
            rows.append({"vertical": vert, "events": list(evs),
                         "weekly_users": None, "events_per_user": None,
                         "wat_overlap": None, "caveat": "dark"})
            continue
        vr = _resolved_intent_days(conn, start_day, end_day,
                                   "ue.event_type IN :vev", {"vev": set(evs)},
                                   include_demo, row_cap)
        users = {r["resolved_user_id"] for r in vr}
        # events/user via a bounded count (distinct rows collapsed above; recount raw).
        ecount = conn.execute(text(
            "SELECT COUNT(*) FROM user_events ue WHERE ue.event_type IN :vev "
            "AND substr(ue.occurred_at,1,10) >= :s AND substr(ue.occurred_at,1,10) <= :e "
            "AND ue.user_id NOT LIKE 'device:%'"
        ).bindparams(bindparam("vev", expanding=True)),
            {"vev": list(evs), "s": start_day, "e": end_day}).scalar() or 0
        n = len(users)
        overlap = len(users & wat_users)
        rows.append({
            "vertical": vert, "events": list(evs),
            "weekly_users": n,
            "events_per_user": round(ecount / n, 2) if n else None,
            "wat_overlap": rate_cell(overlap, n, dark=False),
            "caveat": None,
        })
    caveats.append(_dark_caveat("verticals:dark",
                                "verticals fed only by client/dark events render — until the SDK ships"))
    return rows, caveats, None


# ---------------------------------------------------------------------------
# R1 — Onboarding Waterfall (signup-onward live; stages 0/1/3 dark)
# ---------------------------------------------------------------------------

def report_waterfall(conn, start_day, end_day, include_demo, row_cap, segment=None, **_):
    caveats = []
    # Per user: earliest occurrence of each stage's events, attribution-resolved.
    # We compute stage-reached counts over the whole window's users (device-excluded).
    stage_users: dict[int, set] = {s[0]: set() for s in FUNNEL_STAGES}
    stage_dark: dict[int, bool] = {}
    for stage_no, name, events in FUNNEL_STAGES:
        dark = is_dark(conn, events, start_day, end_day)
        stage_dark[stage_no] = dark
        if dark:
            continue
        rows_s = _resolved_intent_days(conn, start_day, end_day,
                                       "ue.event_type IN :sev", {"sev": set(events)},
                                       include_demo, row_cap)
        stage_users[stage_no] = {r["resolved_user_id"] for r in rows_s}

    # Waterfall: users reaching each stage, step + cumulative conversion vs the
    # first LIVE stage as the base. Drop-off = base_or_prev - this.
    live_stage_nos = [s for s, dk in stage_dark.items() if not dk]
    base_n = len(stage_users[live_stage_nos[0]]) if live_stage_nos else 0
    rows = []
    prev_n = None
    for stage_no, name, events in FUNNEL_STAGES:
        if stage_dark[stage_no]:
            rows.append({"stage": stage_no, "name": name, "events": events,
                         "reached": None, "step_conv": {"value": None, "n": None, "caveat": "dark"},
                         "cumulative": None, "dropoff": None})
            continue
        n = len(stage_users[stage_no])
        step = rate_cell(n, prev_n, dark=False) if prev_n is not None else \
               {"value": 1.0, "n": n, "caveat": None}
        cum = rate_cell(n, base_n, dark=False) if base_n else \
              {"value": None, "n": n, "caveat": "n_too_small"}
        rows.append({"stage": stage_no, "name": name, "events": events,
                     "reached": n, "step_conv": step, "cumulative": cum,
                     "dropoff": (prev_n - n) if prev_n is not None else 0})
        prev_n = n
    caveats.append(_dark_caveat("stage:0-install,1-signin_started,3-league_selected",
                                "client-event stages dark until analytics.ingest + TestFlight SDK"))
    if segment:
        caveats.append(_dark_caveat(f"segment:{segment}",
                                    "server-fired rows carry NULL platform/device/experiments; segmentation lights up with the client SDK"))
    return rows, caveats, {"base_stage": live_stage_nos[0] if live_stage_nos else None,
                           "base_n": base_n}


# ---------------------------------------------------------------------------
# R8 — PFO Report (TTFV + guardrails; partially dark)
# ---------------------------------------------------------------------------

_PFO_GRADES = {  # (works_min, friction_min) for rate-style rows
    "signin_conversion": (0.95, 0.85),
}


def report_pfo(conn, start_day, end_day, include_demo, row_cap, **_):
    caveats = []
    # TTFV endpoints: signin_succeeded (DARK) → trades_generated (LIVE). The
    # start endpoint is dark, so TTFV is unavailable until the SDK ships — but
    # we report the live half (trades_generated reach + empty-deck rate) and
    # the activation guardrail (ranking_complete_first_time, live).
    ttfv_dark = is_dark(conn, ["signin_succeeded"], start_day, end_day)

    # Empty-deck rate from trades_generated props.count (parsed in Python).
    tg_rows = conn.execute(text(
        "SELECT props FROM user_events WHERE event_type='trades_generated' "
        "AND substr(occurred_at,1,10) >= :s AND substr(occurred_at,1,10) <= :e "
        "LIMIT :cap"
    ), {"s": start_day, "e": end_day, "cap": row_cap}).mappings().all()
    empty = total = 0
    for r in tg_rows:
        try:
            c = (json.loads(r["props"]) if r["props"] else {}).get("count")
        except Exception:
            c = None
        if c is None:
            continue
        total += 1
        if c == 0:
            empty += 1
    tg_dark = is_dark(conn, ["trades_generated"], start_day, end_day)

    # Insult rate = trade_flagged / trade_card_viewed — both DARK.
    insult_dark = is_dark(conn, ["trade_flagged", "trade_card_viewed"], start_day, end_day)

    # Activation guardrail (stage 2→5). signup live, ranking_complete_first_time live.
    signups = _resolved_intent_days(conn, start_day, end_day,
                                    "ue.event_type IN :ev", {"ev": {"signup"}},
                                    include_demo, row_cap)
    activated = _resolved_intent_days(conn, start_day, end_day,
                                      "ue.event_type IN :ev", {"ev": {"ranking_complete_first_time"}},
                                      include_demo, row_cap)
    su = {r["resolved_user_id"] for r in signups}
    ac = {r["resolved_user_id"] for r in activated}
    activation = rate_cell(len(su & ac), len(su), dark=is_dark(conn, ["signup"], start_day, end_day))

    stages = [
        {"stage": "sign_in", "measure": "signin_attempted→succeeded conversion",
         "cell": {"value": None, "n": None, "caveat": "dark"}, "grade": None},
        {"stage": "league_pick", "measure": "succeeded→league_selected p50 gap",
         "cell": {"value": None, "n": None, "caveat": "dark"}, "grade": None},
        {"stage": "board_build", "measure": "league→ranking_complete p50 (min)",
         "cell": {"value": None, "n": None, "caveat": "dark"}, "grade": None},
        {"stage": "first_suggestions", "measure": "empty-deck rate",
         "cell": rate_cell(empty, total, dark=tg_dark), "grade": None},
        {"stage": "opinion_formed", "measure": "insult rate (flagged/viewed)",
         "cell": {"value": None, "n": None, "caveat": "dark"} if insult_dark else None,
         "grade": None},
        {"stage": "real_world_action", "measure": "like→sleeper_send conversion",
         "cell": {"value": None, "n": None, "caveat": "dark"}, "grade": None},
    ]
    guardrails = {
        "activation_rate": activation,
        "ttfv_p50_min": {"value": None, "n": None, "caveat": "dark"},
        "empty_deck_rate": rate_cell(empty, total, dark=tg_dark),
        "insult_rate": {"value": None, "n": None, "caveat": "dark"},
        "crash_free_core_loop": {"value": None, "n": None, "caveat": "dark"},
    }
    caveats.append(_dark_caveat("metric:ttfv",
                                "TTFV start endpoint signin_succeeded is a dark client event; TTFV renders — until the SDK ships (trades_generated end endpoint IS live)"))
    return {"stages": stages, "guardrails": guardrails}, caveats, None


# ---------------------------------------------------------------------------
# R4 — Churn & Problem-Feature (hot-column + intent)
# ---------------------------------------------------------------------------

CHURN_DAYS = 14


def report_churn(conn, start_day, end_day, include_demo, row_cap, **_):
    caveats = []
    # Churn = no INTENT event in CHURN_DAYS. Use users.last_active_at hot column
    # as the cheap proxy; churned = last_active_at older than CHURN_DAYS before
    # end_day. last screen/error-adjacency are dark (client events).
    cutoff = (date.fromisoformat(end_day) - timedelta(days=CHURN_DAYS)).isoformat()
    churn_rows = conn.execute(text(
        "SELECT sleeper_user_id AS uid, last_active_at, last_rank_at "
        "FROM users WHERE last_active_at IS NOT NULL "
        "AND substr(last_active_at,1,10) < :cutoff "
        "AND sleeper_user_id NOT LIKE 'device:%' "
        "AND sleeper_user_id NOT LIKE 'demo\\_%' ESCAPE '\\' "
        "ORDER BY last_active_at DESC LIMIT :cap"
    ), {"cutoff": cutoff, "cap": row_cap}).mappings().all()
    active_total = conn.execute(text(
        "SELECT COUNT(*) FROM users WHERE last_active_at IS NOT NULL "
        "AND sleeper_user_id NOT LIKE 'demo\\_%' ESCAPE '\\'"
    )).scalar() or 0
    rows = [{"user_id": r["uid"], "last_active_at": r["last_active_at"],
             "last_rank_at": r["last_rank_at"],
             "last_screen": None, "error_adjacent": None} for r in churn_rows]
    caveats.append(_dark_caveat("metric:last_screen,error_adjacency",
                                "last screen + error-adjacency need client screen_viewed/client_error (dark)"))
    summary = {"churned": len(churn_rows), "active_total": active_total,
               "churn_threshold_days": CHURN_DAYS,
               "churn_rate": rate_cell(len(churn_rows), active_total, dark=False)}
    return rows, caveats, summary


# ---------------------------------------------------------------------------
# R5 — Release Health (per app_version; guardrails; client-error dark)
# ---------------------------------------------------------------------------

def report_releases(conn, start_day, end_day, include_demo, row_cap, **_):
    caveats = []
    # Per app_version: distinct users + intent volume. app_version rides on the
    # request header snapshot, present on any row that carried it. Server rows
    # DO carry device/os/app headers when the client sent them (authed calls),
    # so app_version adoption is partially live.
    rows_raw = conn.execute(text(
        "SELECT app_version AS av, substr(occurred_at,1,10) AS day, "
        "user_id AS uid FROM user_events "
        "WHERE app_version IS NOT NULL AND event_type NOT IN :non_intent "
        "AND substr(occurred_at,1,10) >= :s AND substr(occurred_at,1,10) <= :e "
        "AND user_id NOT LIKE 'device:%' AND user_id NOT LIKE 'demo\\_%' ESCAPE '\\' "
        "LIMIT :cap"
    ).bindparams(bindparam("non_intent", expanding=True)),
        {"non_intent": sorted(NON_INTENT_EVENTS), "s": start_day, "e": end_day,
         "cap": row_cap}).mappings().all()
    by_ver = defaultdict(set)
    for r in rows_raw:
        by_ver[r["av"]].add(r["uid"])
    crash_dark = is_dark(conn, ["client_error"], start_day, end_day)
    rows = [{"app_version": av, "active_users": len(us),
             "crash_free_pct": {"value": None, "n": None, "caveat": "dark"}}
            for av, us in sorted(by_ver.items(), reverse=True)]
    caveats.append(_dark_caveat("metric:crash_free,guardrail_deltas",
                                "crash-free % + guardrail regression need client_error + the client funnel (dark); per-version active users ARE live where app_version headers were sent"))
    return rows, caveats, {"crash_reporting": "JS-errors-only (Sentry not armed); dark until SDK"}


# ---------------------------------------------------------------------------
# R2 — Time / Think-Time (needs client_ts + session_id → dark today)
# ---------------------------------------------------------------------------

def report_time(conn, start_day, end_day, include_demo, row_cap, **_):
    caveats = []
    # Think-time needs intra-session client_ts deltas + decision_ms/dwell_ms/
    # duration_ms props. Server rows have NULL session_id/client_ts. The only
    # live think-time is duration_ms on quickset/quickrank (server-fired with
    # a client-passed duration prop).
    rows = []
    for ev in ("quickset_completed", "quickrank_completed"):
        dark = is_dark(conn, [ev], start_day, end_day)
        vals = []
        if not dark:
            prop_rows = conn.execute(text(
                "SELECT props FROM user_events WHERE event_type=:ev "
                "AND substr(occurred_at,1,10) >= :s AND substr(occurred_at,1,10) <= :e "
                "LIMIT :cap"), {"ev": ev, "s": start_day, "e": end_day, "cap": row_cap}
            ).mappings().all()
            for r in prop_rows:
                try:
                    v = (json.loads(r["props"]) if r["props"] else {}).get("duration_ms")
                    if isinstance(v, (int, float)):
                        vals.append(v)
                except Exception:
                    pass
        rows.append({"action": ev, "metric": "duration_ms",
                     "p50": percentile(vals, 0.5) if vals else None,
                     "p90": percentile(vals, 0.9) if vals else None,
                     "n": len(vals),
                     "caveat": "dark" if not vals else None})
    caveats.append(_dark_caveat("metric:think_time",
                                "intra-session gaps + decision_ms/dwell_ms need client_ts/session_id on client rows (dark); only quickset/quickrank duration_ms is live"))
    return rows, caveats, None


# ---------------------------------------------------------------------------
# R3 — Bottleneck & Rage (drop-off live via waterfall; friction dark)
# ---------------------------------------------------------------------------

def report_bottlenecks(conn, start_day, end_day, include_demo, row_cap, **_):
    # Propagate the waterfall's honest-degradation caveats — the dark stages
    # (0/1/3) are SKIPPED from the ranking below (reached is None), so without
    # this a consumer can't tell "near-zero drop-off" from "not instrumented"
    # and could trust a top bottleneck that's really an artifact of an
    # unmeasured stage.
    wf_rows, wf_caveats, _ = report_waterfall(conn, start_day, end_day, include_demo, row_cap)
    caveats = list(wf_caveats)
    ranked = []
    for r in wf_rows:
        if r["reached"] is None or r["dropoff"] is None:
            continue
        ranked.append({"stage": r["stage"], "name": r["name"],
                       "dropoff": r["dropoff"], "reached": r["reached"],
                       "severity": r["dropoff"]})  # drop-off × cohort proxy
    ranked.sort(key=lambda x: x["severity"], reverse=True)
    caveats.append(_dark_caveat("metric:friction_signatures",
                                "signin_failed/retry taps/client_error clusters/screen-exit-to-churn need client events (dark); live drop-off from the server-side funnel is ranked below"))
    return ranked, caveats, None


# ---------------------------------------------------------------------------
# R10 — Weekly One-Pager (composition)
# ---------------------------------------------------------------------------

def report_onepager(conn, start_day, end_day, include_demo, row_cap, **_):
    caveats = []
    eng_rows, eng_cav, eng_sum = report_engagement(conn, start_day, end_day, include_demo, row_cap)
    bott, bott_cav, _ = report_bottlenecks(conn, start_day, end_day, include_demo, row_cap)
    # North star: latest week's WAT + WoW delta.
    wat_by_week = [(r["week"], r["wat"]["value"]) for r in eng_rows
                   if r["wat"]["value"] is not None]
    north_star = None
    if wat_by_week:
        wk, val = wat_by_week[-1]
        prev = wat_by_week[-2][1] if len(wat_by_week) > 1 else None
        north_star = {"metric": "WAT", "week": wk, "value": val,
                      "wow_delta": (val - prev) if prev is not None else None}
    top_bottleneck = bott[0] if bott else None
    # Carry EVERY constituent caveat governing a surfaced number — the
    # one-pager presents top_bottleneck + MAU + WAT, so the engagement dark
    # caveats and the bottlenecks caveats (which now include the waterfall's
    # stage-dark disclosure) must reach the executive envelope. Dedup by
    # (code, scope) to keep it tidy.
    seen = set()
    for c in list(eng_cav) + list(bott_cav):
        k = (c.get("code"), c.get("scope"))
        if k not in seen:
            seen.add(k)
            caveats.append(c)
    return {
        "north_star": north_star,
        "mau": eng_sum["mau"],
        "top_bottleneck": top_bottleneck,
        "top_experiment": {"status": "no experiments running (P3)"},
        "anomalies": [],
    }, caveats, None


# ---------------------------------------------------------------------------
# Journeys — path analysis (Fullstory "Journeys"): what users do immediately
# before and after an anchor event, ranked by frequency.
#
# Sessions are RECONSTRUCTED in Python from a 30-minute inactivity gap rather
# than read off session_id, because server-fired rows carry NULL session_id
# (only client rows have one). This works on today's data and stays correct
# when client sessions arrive.
# ---------------------------------------------------------------------------

SESSION_GAP_S = 30 * 60


def _iso_to_epoch(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _sessionized_paths(conn, start_day, end_day, include_demo, row_cap):
    """[[event_type, …], …] — one ordered list per reconstructed session."""
    excl, ex_params = device_exclusion(
        alias="ue", include_demo=include_demo,
        tester_device_ids=_tester_device_ids(), start_day=start_day, end_day=end_day)
    sql = f"""
        SELECT ue.user_id AS uid, ue.event_type AS et, ue.occurred_at AS at
          FROM user_events ue
         WHERE substr(ue.occurred_at,1,10) >= :start_day
           AND substr(ue.occurred_at,1,10) <= :end_day
           AND ue.event_type NOT IN :non_intent
           AND {excl}
         ORDER BY ue.user_id, ue.occurred_at
         LIMIT :row_cap"""
    stmt = text(sql).bindparams(bindparam("non_intent", expanding=True))
    p = {"start_day": start_day, "end_day": end_day, "row_cap": row_cap,
         "non_intent": sorted(NON_INTENT_EVENTS)}
    p.update(ex_params)
    rows = conn.execute(stmt, p).mappings().all()
    sessions, cur, last_uid, last_ts = [], [], None, None
    for r in rows:
        ts = _iso_to_epoch(r["at"])
        new_session = (r["uid"] != last_uid or last_ts is None or ts is None
                       or (ts - last_ts) > SESSION_GAP_S)
        if new_session and cur:
            sessions.append(cur)
            cur = []
        cur.append(r["et"])
        last_uid, last_ts = r["uid"], ts
    if cur:
        sessions.append(cur)
    return sessions


def report_journeys(conn, start_day, end_day, include_demo, row_cap,
                    anchor=None, **_):
    """Top paths INTO and OUT OF an anchor event. `anchor` defaults to the
    most frequent event in the window so the view is never empty-by-default."""
    caveats = []
    sessions = _sessionized_paths(conn, start_day, end_day, include_demo, row_cap)
    freq = defaultdict(int)
    for s in sessions:
        for e in s:
            freq[e] += 1
    if not freq:
        caveats.append(_dark_caveat("report:journeys",
                                    "no intent events in window — nothing to path"))
        return {"anchor": None, "candidates": [], "before": [], "after": [],
                "sequences": [], "sessions": 0}, caveats, None
    if anchor not in freq:
        anchor = max(freq, key=freq.get)

    before, after, seqs = defaultdict(int), defaultdict(int), defaultdict(int)
    anchor_hits = 0
    for s in sessions:
        for i, e in enumerate(s):
            if e != anchor:
                continue
            anchor_hits += 1
            before[s[i - 1] if i > 0 else "(session start)"] += 1
            after[s[i + 1] if i + 1 < len(s) else "(session end)"] += 1
        # whole-session shape (deduped consecutive repeats keeps it readable)
        shape = [s[0]]
        for e in s[1:]:
            if e != shape[-1]:
                shape.append(e)
        if anchor in shape:
            seqs[" → ".join(shape[:6])] += 1

    def top(d, total):
        out = [{"step": k, "count": v,
                "share": (v / total) if total else None}
               for k, v in sorted(d.items(), key=lambda kv: -kv[1])[:8]]
        return out

    return ({"anchor": anchor,
             "anchor_hits": anchor_hits,
             "sessions": len(sessions),
             "candidates": [k for k, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:14]],
             "before": top(before, anchor_hits),
             "after": top(after, anchor_hits),
             "sequences": [{"path": k, "count": v} for k, v in
                           sorted(seqs.items(), key=lambda kv: -kv[1])[:8]]},
            caveats, None)


# ---------------------------------------------------------------------------
# Retention — the classic cohort triangle (Fullstory "Retention").
# Weekly signup cohorts × weeks-since-signup, % with ≥1 intent event.
# ---------------------------------------------------------------------------

RETENTION_WEEKS = 8


def report_retention(conn, start_day, end_day, include_demo, row_cap, **_):
    caveats = []
    # Cohort = the ISO week of a user's FIRST signup event in-window.
    signup_rows = _resolved_intent_days(conn, start_day, end_day,
                                        "ue.event_type IN :ev", {"ev": {"signup"}},
                                        include_demo, row_cap)
    first_day = {}
    for r in signup_rows:
        u = r["resolved_user_id"]
        if u not in first_day or r["day"] < first_day[u]:
            first_day[u] = r["day"]
    if not first_day:
        caveats.append(_dark_caveat("report:retention",
                                    "no signup events in window — no cohorts to track"))
        return [], caveats, {"cohorts": 0, "weeks": RETENTION_WEEKS}

    # Activity = any intent event, by week.
    act_rows = _resolved_intent_days(conn, start_day, end_day,
                                     "ue.event_type NOT IN :non_intent",
                                     {"non_intent": NON_INTENT_EVENTS},
                                     include_demo, row_cap)
    active_weeks = defaultdict(set)
    for r in act_rows:
        active_weeks[r["resolved_user_id"]].add(week_key(r["day"]))

    cohorts = defaultdict(set)
    for u, d in first_day.items():
        cohorts[week_key(d)].add(u)

    rows = []
    for cw in sorted(cohorts):
        users = cohorts[cw]
        cw_date = date.fromisoformat(cw)
        cells = []
        for n in range(RETENTION_WEEKS + 1):
            target = (cw_date + timedelta(weeks=n)).isoformat()
            # Only compute weeks that fall inside the window.
            if target > end_day:
                cells.append(None)
                continue
            retained = sum(1 for u in users if target in active_weeks.get(u, set()))
            cells.append({"week_n": n, "retained": retained,
                          "rate": (retained / len(users)) if users else None,
                          "small": len(users) < N_MIN})
        rows.append({"cohort": cw, "size": len(users), "cells": cells})
    caveats.append(_dark_caveat("metric:retention.small_cohorts",
                                f"cohorts under {N_MIN} users show counts; rates are "
                                "directional only at beta scale"))
    return rows, caveats, {"cohorts": len(rows), "weeks": RETENTION_WEEKS}


# ---------------------------------------------------------------------------
# Segments — saved cohort definitions (Fullstory "Segments").
# A segment is a named filter over users; evaluating it returns the matching
# user set + a breakdown, and its id can be passed as `segment=saved:<id>`
# to scope other reports.
# ---------------------------------------------------------------------------

# Filter grammar (kept deliberately small and safe — every operand maps to a
# code-controlled SQL fragment; NO user string ever reaches SQL unparameterized):
#   {"did": "<event_type>"}            user emitted this event in-window
#   {"did_not": "<event_type>"}        user did NOT emit it in-window
#   {"platform": "ios|web|extension"}  any event carried this platform  [client-dark today]
#   {"min_events": 5}                  at least N intent events
# Product-table ops — these work TODAY regardless of client instrumentation,
# because they read member_rankings / leagues / trade_decisions rather than
# the event log (which is why they're the useful ones right now):
#   {"has_ranks": true}                user has a saved board (member_rankings)
#   {"min_players_ranked": 100}        board depth
#   {"scoring_format": "1qb_ppr"}      ranked in this format
#   {"min_leagues": 2}                 multi-league users
#   {"traded": true}                   has any trade decision (like/pass)
#   {"liked_trades_min": 1}            liked at least N suggested trades
SEGMENT_OPS = ("did", "did_not", "platform", "min_events",
               "has_ranks", "min_players_ranked", "scoring_format",
               "min_leagues", "traded", "liked_trades_min")


def evaluate_segment(conn, definition, start_day, end_day, include_demo, row_cap):
    """Return the set of user_ids matching a segment definition."""
    # Universe = event-active users UNION real user rows. The union matters:
    # product-table ops (has_ranks, traded, …) must be able to match users who
    # have a board or a trade history but no captured events yet — which is
    # every user until client instrumentation is on.
    base = {r["resolved_user_id"] for r in _resolved_intent_days(
        conn, start_day, end_day, "ue.event_type NOT IN :non_intent",
        {"non_intent": NON_INTENT_EVENTS}, include_demo, row_cap)}
    try:
        known = set(conn.execute(text(
            "SELECT sleeper_user_id FROM users")).scalars().all())
        if not include_demo:
            known = {u for u in known if u and not u.startswith("demo_")
                     and not u.startswith("test_user_fp_")}
        base |= known
    except Exception:
        pass
    users = set(base)
    counts = defaultdict(int)
    for r in _resolved_intent_days(conn, start_day, end_day,
                                   "ue.event_type NOT IN :non_intent",
                                   {"non_intent": NON_INTENT_EVENTS},
                                   include_demo, row_cap):
        counts[r["resolved_user_id"]] += 1

    for key, val in (definition or {}).items():
        if key not in SEGMENT_OPS:
            raise BadParam(f"unknown segment op: {key}")
        if key in ("did", "did_not"):
            if val not in (SERVER_FIRED_EVENTS | ALLOWED_CLIENT_EVENTS):
                raise BadParam(f"unknown event_type in segment: {val}")
            hit = {r["resolved_user_id"] for r in _resolved_intent_days(
                conn, start_day, end_day, "ue.event_type IN :ev", {"ev": {val}},
                include_demo, row_cap)}
            users = (users & hit) if key == "did" else (users - hit)
        elif key == "platform":
            if val not in ("ios", "web", "extension"):
                raise BadParam(f"unknown platform: {val}")
            hit = {r["resolved_user_id"] for r in _resolved_intent_days(
                conn, start_day, end_day, "ue.platform = :plat", {"plat": val},
                include_demo, row_cap)}
            users &= hit
        elif key == "min_events":
            try:
                n = int(val)
            except Exception:
                raise BadParam("min_events must be an integer")
            users = {u for u in users if counts.get(u, 0) >= n}
        else:
            users &= _product_op(conn, key, val)
    return users, base


def _product_op(conn, key, val):
    """Product-table segment ops (work without client instrumentation). Every
    branch uses a fixed SQL string + bound params — `val` never reaches SQL as
    text except as a bind."""
    if key == "has_ranks":
        rows = conn.execute(text(
            "SELECT DISTINCT user_id FROM member_rankings")).scalars().all()
        got = set(rows)
        return got if val else (set() if val is None else got)
    if key == "min_players_ranked":
        try:
            n = int(val)
        except Exception:
            raise BadParam("min_players_ranked must be an integer")
        rows = conn.execute(text(
            "SELECT user_id FROM member_rankings GROUP BY user_id "
            "HAVING COUNT(*) >= :n"), {"n": n}).scalars().all()
        return set(rows)
    if key == "scoring_format":
        if val not in ("1qb_ppr", "sf_tep"):
            raise BadParam(f"unknown scoring_format: {val}")
        rows = conn.execute(text(
            "SELECT DISTINCT user_id FROM member_rankings "
            "WHERE scoring_format = :f"), {"f": val}).scalars().all()
        return set(rows)
    if key == "min_leagues":
        try:
            n = int(val)
        except Exception:
            raise BadParam("min_leagues must be an integer")
        rows = conn.execute(text(
            "SELECT user_id FROM league_members GROUP BY user_id "
            "HAVING COUNT(DISTINCT league_id) >= :n"), {"n": n}).scalars().all()
        return set(rows)
    if key == "traded":
        rows = conn.execute(text(
            "SELECT DISTINCT user_id FROM trade_decisions")).scalars().all()
        return set(rows)
    if key == "liked_trades_min":
        try:
            n = int(val)
        except Exception:
            raise BadParam("liked_trades_min must be an integer")
        rows = conn.execute(text(
            "SELECT user_id FROM trade_decisions WHERE decision = 'like' "
            "GROUP BY user_id HAVING COUNT(*) >= :n"), {"n": n}).scalars().all()
        return set(rows)
    raise BadParam(f"unknown segment op: {key}")


def report_segments(conn, start_day, end_day, include_demo, row_cap, **_):
    """List saved segments with their live size in the current window."""
    caveats = []
    try:
        saved = conn.execute(text(
            "SELECT id, name, definition_json, created_at FROM analytics_segments "
            "ORDER BY created_at DESC LIMIT :cap"), {"cap": row_cap}).mappings().all()
    except Exception:
        saved = []
    rows = []
    for s in saved:
        try:
            definition = json.loads(s["definition_json"] or "{}")
            users, base = evaluate_segment(conn, definition, start_day, end_day,
                                           include_demo, row_cap)
            rows.append({"id": s["id"], "name": s["name"], "definition": definition,
                         "users": len(users),
                         "share": (len(users) / len(base)) if base else None,
                         "created_at": s["created_at"], "error": None})
        except BadParam as e:
            rows.append({"id": s["id"], "name": s["name"],
                         "definition": None, "users": None, "share": None,
                         "created_at": s["created_at"], "error": str(e)})
    if not rows:
        caveats.append(_dark_caveat("report:segments",
                                    "no saved segments yet — POST /api/admin/segments "
                                    "with {name, definition} to create one"))
    return rows, caveats, {"saved": len(rows), "ops": list(SEGMENT_OPS)}


# ---------------------------------------------------------------------------
# Rank quality — "what is letting users rank actually worth?"
#
# Compares each user's own player Elos (member_rankings) against the consensus
# Elo for the same player+format (player_value_history, latest snapshot). Three
# questions, one query set:
#   1. HOW MUCH do users diverge from consensus? (mean |Δ|, correlation, spread)
#      → the size of the personalization signal the trade engine is acting on.
#   2. WHICH ranking surface did they use? (method mix from ranking events)
#   3. Is the divergence HONEST or SELF-SERVING? — own_roster_bias compares a
#      user's Δ on players they OWN vs players they don't. A user who marks up
#      their own roster and marks down everyone else's is manufacturing
#      favorable trades; that's the gaming signature, and it is separable from
#      "has genuinely different opinions" (which is symmetric across ownership).
#
# Everything here reads product tables, NOT user_events — so it works today,
# independent of client instrumentation.
# ---------------------------------------------------------------------------

def _spearman(pairs):
    """Rank correlation without scipy. pairs = [(a, b), …]."""
    n = len(pairs)
    if n < 3:
        return None

    def ranks(vals):
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        r = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    ra, rb = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = math.sqrt(sum((x - ma) ** 2 for x in ra))
    dbv = math.sqrt(sum((x - mb) ** 2 for x in rb))
    return (num / (da * dbv)) if da and dbv else None


def _consensus_map(conn):
    """{(player_id, scoring_format): consensus_elo} from the latest snapshot."""
    rows = conn.execute(text(
        "SELECT player_id, scoring_format, consensus_elo FROM player_value_history "
        "WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM player_value_history) "
        "AND consensus_elo IS NOT NULL")).fetchall()
    return {(r[0], r[1] or "1qb_ppr"): r[2] for r in rows}


def _owned_players(conn):
    """{(league_id, user_id): {player_id, …}} from league_members.roster_data."""
    owned = {}
    rows = conn.execute(text(
        "SELECT league_id, user_id, roster_data FROM league_members "
        "WHERE roster_data IS NOT NULL")).fetchall()
    for lid, uid, raw in rows:
        try:
            data = json.loads(raw)
        except Exception:
            continue
        ids = data if isinstance(data, list) else (data.get("players") or [])
        owned[(lid, uid)] = {str(p) for p in ids if p}
    return owned


def report_rankquality(conn, start_day, end_day, include_demo, row_cap, **_):
    caveats = []
    consensus = _consensus_map(conn)
    if not consensus:
        caveats.append(_dark_caveat("report:rankquality",
                                    "no consensus snapshot in player_value_history — "
                                    "run the value-snapshot cron before comparing"))
        return [], caveats, None
    owned = _owned_players(conn)

    rank_rows = conn.execute(text(
        "SELECT user_id, league_id, player_id, elo, scoring_format "
        "FROM member_rankings LIMIT :cap"), {"cap": row_cap}).mappings().all()
    by_user = defaultdict(list)
    for r in rank_rows:
        by_user[r["user_id"]].append(r)

    # Ranking-surface mix (which feature produced the board) from live events.
    method_rows = conn.execute(text(
        "SELECT user_id, event_type, COUNT(*) n FROM user_events "
        "WHERE event_type IN ('trio_swipe','tier_save','anchor_answered',"
        "'quickset_completed','quickrank_completed','ranking_reorder') "
        "GROUP BY user_id, event_type")).fetchall()
    methods = defaultdict(dict)
    for uid, et, n in method_rows:
        methods[uid][et] = n

    rows = []
    for uid, urows in by_user.items():
        if not include_demo and (uid.startswith("demo_") or uid.startswith("device:")):
            continue
        pairs, deltas, own_d, other_d = [], [], [], []
        for r in urows:
            key = (str(r["player_id"]), r["scoring_format"] or "1qb_ppr")
            cons = consensus.get(key)
            if cons is None or r["elo"] is None:
                continue
            d = r["elo"] - cons
            pairs.append((r["elo"], cons))
            deltas.append(d)
            roster = owned.get((r["league_id"], uid))
            if roster is not None:
                (own_d if str(r["player_id"]) in roster else other_d).append(d)
        if not deltas:
            continue
        n = len(deltas)
        mean_abs = sum(abs(d) for d in deltas) / n
        # The gaming signature: own-roster markup MINUS others' markup. A user
        # with genuinely different opinions diverges symmetrically (≈0); a user
        # manufacturing favorable trades marks their own players UP and
        # everyone else's DOWN, so the gap is large and positive.
        bias = None
        if len(own_d) >= 5 and len(other_d) >= 5:
            bias = (sum(own_d) / len(own_d)) - (sum(other_d) / len(other_d))
        rows.append({
            "user_id": uid,
            "players_ranked": n,
            "mean_abs_delta": round(mean_abs, 1),
            "spearman_vs_consensus": (round(_spearman(pairs), 3)
                                      if _spearman(pairs) is not None else None),
            "own_roster_bias": (round(bias, 1) if bias is not None else None),
            "own_n": len(own_d), "other_n": len(other_d),
            "methods": methods.get(uid) or {},
            "integrity_flag": _integrity_flag(mean_abs, _spearman(pairs), bias, n),
        })
    rows.sort(key=lambda r: -(r["own_roster_bias"] or 0))
    caveats.append(_dark_caveat("metric:own_roster_bias",
                                "needs ≥5 owned and ≥5 non-owned ranked players per "
                                "user; renders — otherwise. Elo units, not %"))
    summary = {
        "users_scored": len(rows),
        "consensus_players": len(consensus),
        "median_abs_delta": percentile([r["mean_abs_delta"] for r in rows], 0.5),
        "note": ("mean_abs_delta = average |user Elo − consensus Elo| across the "
                 "user's ranked players; own_roster_bias = own-player markup minus "
                 "other-player markup (Elo). High bias + low correlation = review."),
    }
    return rows, caveats, summary


def _integrity_flag(mean_abs, spearman, bias, n):
    """Cheap triage label for consensus-eligibility review. Deliberately
    conservative: 'divergent' is NOT an accusation — only the combination of a
    large own-roster markup with weak consensus correlation is suspicious."""
    if n < 25:
        return "insufficient"
    if bias is not None and bias >= 100 and (spearman is None or spearman < 0.5):
        return "review"          # marks own roster up AND ordering unlike market
    if bias is not None and bias >= 150:
        return "review"          # extreme self-markup regardless of correlation
    if spearman is not None and spearman < 0.2:
        return "divergent"       # very different ordering, but not self-serving
    return "ok"


# ---------------------------------------------------------------------------
# R-API — API observability (flag obs.api_events, backend/api_observability.py)
# ---------------------------------------------------------------------------

def report_apihealth(conn, start_day, end_day, include_demo, row_cap,
                     service=None, **_):
    """API observability over api_call (outbound) / api_request (inbound) rows.

    rows    = per (day, direction, service, endpoint) aggregates: recorded
              event count, error count, est_calls (Σ sample_n on sampled
              successes + 1 per error row — the honest rescale), failure
              rate, p50/p95 latency.
    summary = per-service totals + recent_failures (newest 100) + slowest
              (top 20 recorded calls by ms).

    `service` filters to ONE outbound service (e.g. 'espn' — "all failed
    ESPN calls today" is ?start=<today>&end=<today>&service=espn); inbound
    rows are excluded while the filter is active. Aggregation happens in
    Python (rows are bounded by retention + sampling + row_cap) so no
    cross-dialect JSON extraction is needed.
    """
    q = text(
        "SELECT occurred_at, event_type, props FROM user_events "
        "WHERE event_type IN ('api_call', 'api_request') "
        "AND user_id = 'system:api' "
        "AND substr(occurred_at,1,10) >= :s AND substr(occurred_at,1,10) <= :e "
        "ORDER BY occurred_at DESC LIMIT :cap")
    db_rows = conn.execute(
        q, {"s": start_day, "e": end_day, "cap": row_cap}).fetchall()

    caveats = []
    if not db_rows:
        caveats.append(_dark_caveat(
            "report:apihealth",
            "no api_call/api_request rows in window — flag obs.api_events "
            "off, capture not yet deployed, or rows aged out (retention)"))
        return [], caveats, {"services": {}, "recent_failures": [],
                             "slowest": []}
    if len(db_rows) >= row_cap:
        caveats.append({"code": "row_cap", "scope": "report:apihealth",
                        "detail": f"window truncated to the newest {row_cap} "
                                  "rows — narrow the date range"})
    caveats.append({
        "code": "sampled", "scope": "report:apihealth",
        "detail": "successes are 1-in-N sampled (model_config "
                  "obs_success_sample_n); est_calls rescales via each row's "
                  "sample_n — errors are always recorded in full"})

    buckets: dict = {}     # (day, direction, service, endpoint) → agg
    svc_tot: dict = {}     # service → totals
    failures: list = []
    slowest: list = []
    for occurred_at, etype, props_json in db_rows:
        try:
            p = json.loads(props_json) if props_json else {}
        except Exception:
            p = {}
        direction = "outbound" if etype == "api_call" else "inbound"
        svc = p.get("service", "unknown") if direction == "outbound" else "ftf_api"
        if service:
            if direction == "inbound" or svc != service:
                continue
        endpoint = (p.get("endpoint") if direction == "outbound"
                    else p.get("route")) or "unknown"
        ok = bool(p.get("ok", True))
        ms = p.get("ms") if isinstance(p.get("ms"), (int, float)) else None
        weight = int(p.get("sample_n") or 1) if ok else 1
        day = occurred_at[:10]

        b = buckets.setdefault((day, direction, svc, endpoint),
                               {"recorded": 0, "errors": 0, "est_calls": 0,
                                "ms": []})
        b["recorded"] += 1
        b["est_calls"] += weight
        if ms is not None:
            b["ms"].append(ms)
        t = svc_tot.setdefault(svc, {"direction": direction, "recorded": 0,
                                     "errors": 0, "est_calls": 0, "ms": []})
        t["recorded"] += 1
        t["est_calls"] += weight
        if ms is not None:
            t["ms"].append(ms)
        if not ok:
            b["errors"] += 1
            t["errors"] += 1
            if len(failures) < 100:
                failures.append({
                    "occurred_at": occurred_at, "direction": direction,
                    "service": svc, "endpoint": endpoint,
                    "status": p.get("status"),
                    "error_class": p.get("error_class"),
                    "error_kind": p.get("error_kind"),
                    "error_code": p.get("error_code"),
                    "ms": ms, "league_id": p.get("league_id"),
                })
        if ms is not None:
            slowest.append({"occurred_at": occurred_at, "service": svc,
                            "endpoint": endpoint, "ms": ms,
                            "status": p.get("status"), "ok": ok})

    rows = []
    for (day, direction, svc, endpoint), b in sorted(buckets.items()):
        rows.append({
            "day": day, "direction": direction, "service": svc,
            "endpoint": endpoint, "recorded": b["recorded"],
            "errors": b["errors"], "est_calls": b["est_calls"],
            "failure_rate": (b["errors"] / b["est_calls"])
                            if b["est_calls"] else None,
            "p50_ms": percentile(b["ms"], 0.5),
            "p95_ms": percentile(b["ms"], 0.95),
        })
    summary = {
        "services": {
            svc: {
                "direction": t["direction"], "recorded": t["recorded"],
                "errors": t["errors"], "est_calls": t["est_calls"],
                "failure_rate": (t["errors"] / t["est_calls"])
                                if t["est_calls"] else None,
                "p50_ms": percentile(t["ms"], 0.5),
                "p95_ms": percentile(t["ms"], 0.95),
            } for svc, t in sorted(svc_tot.items())
        },
        "recent_failures": failures,
        "slowest": sorted(slowest, key=lambda r: r["ms"], reverse=True)[:20],
    }
    return rows, caveats, summary


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_BUILDERS = {
    "overview": report_overview,
    "journeys": report_journeys,
    "retention": report_retention,
    "segments": report_segments,
    "rankquality": report_rankquality,
    "waterfall": report_waterfall,
    "time": report_time,
    "bottlenecks": report_bottlenecks,
    "churn": report_churn,
    "releases": report_releases,
    "adoption": report_adoption,
    "engagement": report_engagement,
    "pfo": report_pfo,
    "onepager": report_onepager,
    "apihealth": report_apihealth,
}


def _parse_window(start, end):
    today = datetime.now(timezone.utc).date()
    try:
        end_day = date.fromisoformat(end) if end else today
        start_day = date.fromisoformat(start) if start else (end_day - timedelta(days=27))
    except ValueError:
        raise BadParam("start/end must be ISO dates (YYYY-MM-DD)")
    if start_day > end_day:
        raise BadParam("start must be <= end")
    if (end_day - start_day).days > WINDOW_MAX_DAYS:
        raise BadParam(f"window exceeds {WINDOW_MAX_DAYS} days")
    return start_day.isoformat(), end_day.isoformat()


def run_report(report, *, start=None, end=None, include_demo=False,
               fmt="json", segment=None, anchor=None, service=None):
    """Compute a report on the read-only engine. Returns (envelope_dict, None)
    for json, or (csv_str, 'text/csv') for csv. Raises BadParam on bad input.
    `service` is consumed by apihealth only (outbound-service filter)."""
    if report not in VALID_REPORTS:
        raise BadParam("unknown_report")
    start_day, end_day = _parse_window(start, end)
    row_cap = ROW_CAP_CSV if fmt == "csv" else ROW_CAP_JSON
    builder = _BUILDERS[report]
    with db.ro_engine.connect() as conn:
        rows, caveats, summary = builder(
            conn, start_day, end_day, include_demo, row_cap,
            segment=segment, anchor=anchor, service=service)
    params_echo = {"segment": segment, "include_demo": include_demo,
                   "format": fmt, "anchor": anchor, "service": service}
    env = _envelope(report, start_day, end_day, rows, caveats, params_echo)
    if summary is not None:
        env["summary"] = summary
    if fmt == "csv":
        return _to_csv(env), "text/csv"
    return env, None


def _to_csv(env):
    """Flatten the report rows to CSV; caveats as leading '#' comments."""
    out = io.StringIO()
    for c in env.get("caveats", []):
        out.write(f"# {c.get('code')}: {c.get('scope')} — {c.get('detail')}\n")
    rows = env.get("rows")
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        # Flatten dict-valued cells to value + _caveat columns.
        def flat(r):
            o = {}
            for k, v in r.items():
                if isinstance(v, dict) and "value" in v:
                    o[k] = v.get("value")
                    o[f"{k}_caveat"] = v.get("caveat")
                elif isinstance(v, (list, dict)):
                    o[k] = json.dumps(v)
                else:
                    o[k] = v
            return o
        flat_rows = [flat(r) for r in rows]
        fields = list(flat_rows[0].keys())
        w = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in flat_rows:
            w.writerow(r)
    else:
        out.write(json.dumps(rows))
    return out.getvalue()
