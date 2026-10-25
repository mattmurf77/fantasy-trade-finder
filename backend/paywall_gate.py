"""
paywall_gate.py — the global server paywall gate (C2: trade making and sending).

Spec: Product scope #393 §2 "API surface" item 1 and recommendation §(c), as
overridden by head-eng (2026-10-24):

  * Enforce = entitlements.is_enforcing() (monetize.entitlements ∧
    monetize.paywall ∧ model_config paywall_enforce_enabled == 1). #393's
    `monetize.pro` leg is superseded.
  * Web requests are gated only when, in addition, model_config
    `paywall_web_enforce_enabled` == 1. Mobile = the native app's X-Device
    header (MOBILE_DEVICES); everything else is web.
  * The preview allowance doesn't exist yet: the deck path treats the preview
    as PREVIEW_PAGES = 0 pages.
  * A blocked request gets exactly 402 {"error": "pro_required", "gate": <reason>}.
  * Pro counts only on a verified session (head-eng security ruling,
    2026-10-24); a pro user_id on an unverified session gets `verify_required`.

One before_request hook in server.py reads ROUTES, a per-route table keyed by
(method, Flask rule string), never by prefix: /api/trades/* mixes free and
gated rules. test_paywall_gate_allowlist.py fails CI on any rule missing from
it. Everything stateful is a plain function so it tests without Flask.
"""

from __future__ import annotations

import json

from sqlalchemy import or_, select

from . import database as db
from . import entitlements

GATED, FREE, NEVER_GATE = "gated", "free", "never_gate"

# The paywall_preview_pages knob lands with the preview allowance.
PREVIEW_PAGES = 0

WEB_ENFORCE_KNOB = "paywall_web_enforce_enabled"

# X-Device values the native app sends (mobile/src/api/client.ts
# _resolveDeviceLabel; the same set server.py's feedback route reads as iOS,
# plus android). The web app and the extension send no X-Device; an Expo web
# build sends 'web'. All of those are web here.
MOBILE_DEVICES = frozenset({"iphone", "ipad", "macos", "android"})

# Reasons, the `gate` value of the 402 body.
PREVIEW_USED = "preview_used"      # never held pro; a deck route (the preview is spent)
NEVER_TRIALED = "never_trialed"    # never held pro; any other gated route
TRIAL_EXPIRED = "trial_expired"    # held pro only through an intro trial
LAPSED = "lapsed"                  # held pro any other way (paid, comp, promo)
VERIFY_REQUIRED = "verify_required"  # the user_id holds pro; the session is unverified

# The deck: Find a trade, its job poll and its swipes. Today's Trade
# (trades.presentation_v2) is client-only and rides these same routes.
DECK_ROUTES = frozenset({
    ("GET", "/api/trades"),
    ("POST", "/api/trades/generate"),
    ("POST", "/api/trades/pass-reason"),
    ("GET", "/api/trades/status"),
    ("POST", "/api/trades/swipe"),
})

ROUTES = {
    # ── gated: the deck (DECK_ROUTES) ──────────────────────────────────────
    ("GET", "/api/trades"): GATED,
    ("POST", "/api/trades/generate"): GATED,
    ("POST", "/api/trades/pass-reason"): GATED,
    ("GET", "/api/trades/status"): GATED,
    ("POST", "/api/trades/swipe"): GATED,
    # ── gated: send ────────────────────────────────────────────────────────
    ("POST", "/api/trades/propose"): GATED,
    ("POST", "/api/trades/propose-espn"): GATED,
    ("POST", "/api/trades/propose-mfl"): GATED,
    ("POST", "/api/trades/queue"): GATED,
    ("POST", "/api/trades/respond-mfl"): GATED,
    # ── gated: other trade making (shop a player, the calculator's Find a
    #    trade, standing offers, Matches accept, overhauls, Win Now) ────────
    ("POST", "/api/trades/asset-ideas"): GATED,
    ("POST", "/api/trades/fair-packages"): GATED,
    ("POST", "/api/trades/matches/<int:match_id>/disposition"): GATED,
    ("POST", "/api/trades/standing-offer"): GATED,
    ("GET", "/api/overhauls"): GATED,
    ("POST", "/api/overhauls"): GATED,
    ("GET", "/api/overhauls/<overhaul_id>"): GATED,
    ("POST", "/api/overhauls/<overhaul_id>/assemble"): GATED,
    ("POST", "/api/overhauls/<overhaul_id>/attempts/<attempt_id>/status"): GATED,
    ("POST", "/api/overhauls/<overhaul_id>/decisions"): GATED,
    ("POST", "/api/overhauls/<overhaul_id>/generate"): GATED,
    ("GET", "/api/overhauls/<overhaul_id>/offers"): GATED,
    ("POST", "/api/overhauls/<overhaul_id>/refresh"): GATED,
    ("POST", "/api/overhauls/<overhaul_id>/roadmaps/<roadmap_id>/prepare-send"): GATED,
    ("PUT", "/api/overhauls/<overhaul_id>/roadmaps/<roadmap_id>/priorities"): GATED,
    ("PUT", "/api/overhauls/<overhaul_id>/roadmaps/<roadmap_id>/select"): GATED,
    ("POST", "/api/overhauls/<overhaul_id>/send"): GATED,
    ("PUT", "/api/overhauls/<overhaul_id>/settings"): GATED,
    ("POST", "/api/win-now/evaluate"): GATED,
    ("GET", "/api/win-now/jobs/<job_id>"): GATED,
    ("POST", "/api/win-now/scenarios/<scenario_id>/decision"): GATED,
    ("POST", "/api/win-now/search"): GATED,
    # ── never_gate: secret-guarded operator and provider traffic. /api/admin/*,
    #    /api/cron/*, /api/billing/*, plus the X-Cron-Secret routes outside
    #    those prefixes ─────────────────────────────────────────────────────
    ("GET", "/api/admin/analytics/<report>"): NEVER_GATE,
    ("GET", "/api/admin/analytics/health"): NEVER_GATE,
    ("GET", "/api/admin/config"): NEVER_GATE,
    ("PUT", "/api/admin/config/<key>"): NEVER_GATE,
    ("GET", "/api/admin/engine-metrics"): NEVER_GATE,
    ("GET", "/api/admin/entitlements"): NEVER_GATE,
    ("DELETE", "/api/admin/entitlements/<int:entitlement_id>"): NEVER_GATE,
    ("POST", "/api/admin/entitlements/bulk-grant"): NEVER_GATE,
    ("POST", "/api/admin/entitlements/grant"): NEVER_GATE,
    ("GET", "/api/admin/experiments"): NEVER_GATE,
    ("POST", "/api/admin/experiments"): NEVER_GATE,
    ("GET", "/api/admin/experiments/<key>"): NEVER_GATE,
    ("POST", "/api/admin/experiments/<key>/decide"): NEVER_GATE,
    ("GET", "/api/admin/experiments/<key>/readout"): NEVER_GATE,
    ("POST", "/api/admin/experiments/<key>/revise"): NEVER_GATE,
    ("POST", "/api/admin/experiments/<key>/transition"): NEVER_GATE,
    ("POST", "/api/admin/experiments/preview"): NEVER_GATE,
    ("POST", "/api/admin/experiments/reseed-layers"): NEVER_GATE,
    ("POST", "/api/admin/grading/add-fit-arms"): NEVER_GATE,
    ("POST", "/api/admin/grading/pregenerate"): NEVER_GATE,
    ("GET", "/api/admin/grading/report"): NEVER_GATE,
    ("DELETE", "/api/admin/prepared-trades"): NEVER_GATE,
    ("GET", "/api/admin/prepared-trades"): NEVER_GATE,
    ("POST", "/api/admin/prepared-trades"): NEVER_GATE,
    ("GET", "/api/admin/receipts/metrics"): NEVER_GATE,
    ("GET", "/api/admin/segments"): NEVER_GATE,
    ("POST", "/api/admin/segments"): NEVER_GATE,
    ("DELETE", "/api/admin/segments/<int:seg_id>"): NEVER_GATE,
    ("GET", "/api/admin/suggestion-telemetry/ratio"): NEVER_GATE,
    ("POST", "/api/billing/revenuecat/webhook"): NEVER_GATE,
    ("POST", "/api/billing/stripe/webhook"): NEVER_GATE,
    ("POST", "/api/cron/daily-tick"): NEVER_GATE,
    ("POST", "/api/cron/hourly-tick"): NEVER_GATE,
    ("POST", "/api/cron/players-refresh"): NEVER_GATE,
    ("POST", "/api/cron/realtime-tick"): NEVER_GATE,
    ("POST", "/api/cron/receipts-grade"): NEVER_GATE,
    ("POST", "/api/cron/roster-snapshot"): NEVER_GATE,
    ("POST", "/api/cron/usage-trends-refresh"): NEVER_GATE,
    ("POST", "/api/cron/value-snapshot"): NEVER_GATE,
    ("GET", "/api/debug/log"): NEVER_GATE,
    ("POST", "/api/feature-flags/reload"): NEVER_GATE,
    ("GET", "/api/feedback/admin"): NEVER_GATE,
    ("PUT", "/api/feedback/admin/<int:feedback_id>/status"): NEVER_GATE,
    ("GET", "/api/trades/flags/admin"): NEVER_GATE,
    # ── free: everything else. Sign-in and session, onboarding and league
    #    connect, Settings, account delete and export, entitlements and
    #    paywall config, legal and feedback, events, the extension, every
    #    rank write, the calculator's evaluate, viewing Matches, invites,
    #    profiles, static and web pages ───────────────────────────────────
    ("GET", "/"): FREE,
    ("GET", "/.well-known/apple-app-site-association"): FREE,
    ("GET", "/<path:filename>"): FREE,
    ("DELETE", "/api/account"): FREE,
    ("GET", "/api/account"): FREE,
    ("GET", "/api/account/export"): FREE,
    ("POST", "/api/account/link-sleeper"): FREE,
    ("POST", "/api/account/reset-rankings"): FREE,
    ("POST", "/api/anchor/save"): FREE,
    ("GET", "/api/anchor/scale"): FREE,
    ("POST", "/api/anchor/scale"): FREE,
    ("POST", "/api/auth/apple"): FREE,
    ("POST", "/api/auth/google"): FREE,
    ("GET", "/api/draft/board"): FREE,
    ("POST", "/api/entry/platform"): FREE,
    ("POST", "/api/espn/import"): FREE,
    ("GET", "/api/espn/leagues"): FREE,
    ("DELETE", "/api/espn/link"): FREE,
    ("GET", "/api/espn/link"): FREE,
    ("POST", "/api/espn/link"): FREE,
    ("GET", "/api/espn/my-leagues"): FREE,
    ("POST", "/api/events"): FREE,
    ("POST", "/api/extension/auth"): FREE,
    ("GET", "/api/extension/rankings"): FREE,
    ("GET", "/api/feature-flags"): FREE,
    ("POST", "/api/feedback"): FREE,
    ("GET", "/api/feedback/mine"): FREE,
    ("POST", "/api/fleaflicker/discover"): FREE,
    ("POST", "/api/fleaflicker/import"): FREE,
    ("GET", "/api/fleaflicker/leagues"): FREE,
    ("POST", "/api/fleaflicker/link"): FREE,
    ("POST", "/api/grading/cards/<card_id>"): FREE,
    ("POST", "/api/grading/sessions"): FREE,
    ("GET", "/api/grading/sessions/<session_id>/next"): FREE,
    ("GET", "/api/grading/sessions/<session_id>/results"): FREE,
    ("GET", "/api/grading/sessions/current"): FREE,
    ("GET", "/api/invite/impact"): FREE,
    ("GET", "/api/leaderboard"): FREE,
    ("GET", "/api/league/<league_id>/receipts"): FREE,
    ("GET", "/api/league/activity"): FREE,
    ("GET", "/api/league/asset-prefs"): FREE,
    ("POST", "/api/league/asset-prefs"): FREE,
    ("GET", "/api/league/contrarian"): FREE,
    ("GET", "/api/league/coverage"): FREE,
    ("GET", "/api/league/format-stats"): FREE,
    ("GET", "/api/league/free-agents"): FREE,
    ("GET", "/api/league/invite-meta"): FREE,
    ("GET", "/api/league/member-unlock-states"): FREE,
    ("GET", "/api/league/members"): FREE,
    ("GET", "/api/league/outlook"): FREE,
    ("POST", "/api/league/parse-url"): FREE,
    ("GET", "/api/league/pick-assignments"): FREE,
    ("PUT", "/api/league/pick-assignments/<pick_id>"): FREE,
    ("POST", "/api/league/pick-assignments/order"): FREE,
    ("GET", "/api/league/picks"): FREE,
    ("GET", "/api/league/power-rankings"): FREE,
    ("GET", "/api/league/preferences"): FREE,
    ("POST", "/api/league/preferences"): FREE,
    ("GET", "/api/league/rank-chip"): FREE,
    ("POST", "/api/league/recorded-picks"): FREE,
    ("POST", "/api/league/recorded-picks/void"): FREE,
    ("POST", "/api/league/scoring"): FREE,
    ("GET", "/api/league/season-projections"): FREE,
    ("GET", "/api/league/summary"): FREE,
    ("GET", "/api/league/team-review"): FREE,
    ("GET", "/api/leagues"): FREE,
    ("GET", "/api/market/movers"): FREE,
    ("GET", "/api/me/entitlements"): FREE,
    ("GET", "/api/me/streak"): FREE,
    ("POST", "/api/mfl/auth-import"): FREE,
    ("DELETE", "/api/mfl/auth-link"): FREE,
    ("GET", "/api/mfl/auth-link"): FREE,
    ("POST", "/api/mfl/auth-link"): FREE,
    ("POST", "/api/mfl/import"): FREE,
    ("GET", "/api/mfl/leagues"): FREE,
    ("POST", "/api/mfl/link"): FREE,
    ("GET", "/api/mfl/pending-trades"): FREE,
    ("GET", "/api/mock-draft"): FREE,
    ("POST", "/api/mock-draft"): FREE,
    ("POST", "/api/mock-draft/abandon"): FREE,
    ("POST", "/api/mock-draft/pick"): FREE,
    ("GET", "/api/notifications"): FREE,
    ("POST", "/api/notifications/dismiss-all"): FREE,
    ("GET", "/api/notifications/prefs"): FREE,
    ("PUT", "/api/notifications/prefs"): FREE,
    ("POST", "/api/notifications/read"): FREE,
    ("POST", "/api/notifications/read-all"): FREE,
    ("POST", "/api/notifications/register-device"): FREE,
    ("GET", "/api/paywall/config"): FREE,
    ("GET", "/api/players"): FREE,
    ("GET", "/api/players/<player_id>"): FREE,
    ("GET", "/api/players/<player_id>/profile"): FREE,
    ("GET", "/api/portfolio"): FREE,
    ("GET", "/api/profile/<path:username>"): FREE,
    ("GET", "/api/profile/visibility"): FREE,
    ("PUT", "/api/profile/visibility"): FREE,
    ("GET", "/api/progress"): FREE,
    ("POST", "/api/rank3"): FREE,
    ("POST", "/api/ranking-method"): FREE,
    ("GET", "/api/rankings"): FREE,
    ("POST", "/api/rankings/import-apply"): FREE,
    ("POST", "/api/rankings/import-match"): FREE,
    ("GET", "/api/rankings/progress"): FREE,
    ("POST", "/api/rankings/reorder"): FREE,
    ("POST", "/api/rankings/submit"): FREE,
    ("POST", "/api/reset"): FREE,
    ("GET", "/api/rookies"): FREE,
    ("POST", "/api/scoring/switch"): FREE,
    ("GET", "/api/session/demo"): FREE,
    ("POST", "/api/session/demo"): FREE,
    ("POST", "/api/session/init"): FREE,
    ("GET", "/api/session/ping"): FREE,
    ("POST", "/api/session/signout"): FREE,
    ("GET", "/api/settings/pick-pricing"): FREE,
    ("PUT", "/api/settings/pick-pricing"): FREE,
    ("GET", "/api/settings/stud-tax"): FREE,
    ("PUT", "/api/settings/stud-tax"): FREE,
    ("POST", "/api/share/package"): FREE,
    ("GET", "/api/skips"): FREE,
    ("GET", "/api/sleeper/league_users/<league_id>"): FREE,
    ("GET", "/api/sleeper/leagues/<user_id>"): FREE,
    ("DELETE", "/api/sleeper/link"): FREE,
    ("GET", "/api/sleeper/link"): FREE,
    ("POST", "/api/sleeper/link"): FREE,
    ("GET", "/api/sleeper/players"): FREE,
    ("GET", "/api/sleeper/players/warm"): FREE,
    ("GET", "/api/sleeper/rosters/<league_id>"): FREE,
    ("GET", "/api/sleeper/user/<path:username>"): FREE,
    ("POST", "/api/test-users"): FREE,
    ("DELETE", "/api/test-users/<user_id>"): FREE,
    ("GET", "/api/tier-config"): FREE,
    ("GET", "/api/tiers/community-diff"): FREE,
    ("POST", "/api/tiers/copy-from-format"): FREE,
    ("POST", "/api/tiers/dismiss"): FREE,
    ("POST", "/api/tiers/save"): FREE,
    ("GET", "/api/tiers/stability"): FREE,
    ("GET", "/api/tiers/status"): FREE,
    ("POST", "/api/trade/evaluate"): FREE,
    ("GET", "/api/trade/values"): FREE,
    ("GET", "/api/trades/awaiting"): FREE,
    ("POST", "/api/trades/awaiting/dismiss"): FREE,
    ("POST", "/api/trades/flag"): FREE,
    ("GET", "/api/trades/liked"): FREE,
    ("GET", "/api/trades/matches"): FREE,
    ("POST", "/api/trades/matches/<int:match_id>/dismiss"): FREE,
    ("GET", "/api/trades/matches/all"): FREE,
    ("POST", "/api/trades/standing-offer/revoke"): FREE,
    ("GET", "/api/trades/standing-offers"): FREE,
    ("POST", "/api/trades/suppressions/undo"): FREE,
    ("POST", "/api/trades/validate"): FREE,
    ("GET", "/api/trends/consensus-gap"): FREE,
    ("GET", "/api/trends/contrarian"): FREE,
    ("GET", "/api/trends/risers-fallers"): FREE,
    ("GET", "/api/trio"): FREE,
    ("POST", "/api/trio/skip"): FREE,
    ("GET", "/api/usage-trends"): FREE,
    ("GET", "/app/league/join/<league_id>"): FREE,
    ("GET", "/og/p/<short_id>.png"): FREE,
    ("GET", "/og/tiers/<pos>/<username>.png"): FREE,
    ("GET", "/og/trade/<match_id>.png"): FREE,
    ("GET", "/privacy"): FREE,
    ("GET", "/s/p/<short_id>"): FREE,
    ("GET", "/s/tiers/<pos>/<username>"): FREE,
    ("GET", "/s/trade/<match_id>"): FREE,
    ("GET", "/terms"): FREE,
    ("GET", "/u/<path:username>"): FREE,
}


def classify(method: str, rule: str) -> str:
    """The table's class for one request. HEAD is GET (Flask serves it from
    the GET view). Anything unlisted (OPTIONS, an unmatched path) is free:
    the completeness test keeps real rules listed, and a gap fails open
    rather than locking users out."""
    if method == "HEAD":
        method = "GET"
    return ROUTES.get((method, rule), FREE)


def is_mobile_request(headers) -> bool:
    return (headers.get("X-Device") or "").strip().lower() in MOBILE_DEVICES


def _web_knob_on() -> bool:
    """model_config `paywall_web_enforce_enabled` == 1, read live through
    database.get_config() like entitlements._enforce_knob_on. A missing row
    or a failed read is 0 (G-064: the fallback matches the seed)."""
    try:
        return float(db.get_config().get(WEB_ENFORCE_KNOB, 0.0)) == 1.0
    except Exception:
        return False


def applies(rule: str, method: str) -> bool:
    """The hook's two early-outs, in order: the table says gated (a pure
    lookup, so a free route never reads anything), then the server is
    enforcing. Neither reads the session or an entitlement."""
    return classify(method, rule) == GATED and entitlements.is_enforcing()


def verdict(rule: str, method: str, user_id: str | None, is_mobile: bool,
            verified: bool) -> tuple[int, dict] | None:
    """The decision for a request that applies(). No user → None: the
    route's own auth answers (401), never a 402.

    Pro counts only on a verified session (or the server-made demo session):
    entitlements resolve by user_id, and an unverified username-only session
    carries the same user_id as the subscriber it names. Such a session gets
    `verify_required` when the user_id holds pro, the normal reason when not."""
    if not user_id:
        return None
    if not is_mobile and not _web_knob_on():
        return None
    has_pro = entitlements.get_entitlements(user_id)["pro"]
    if has_pro and verified:
        return None
    if has_pro:
        reason = VERIFY_REQUIRED
    else:
        deck = (("GET" if method == "HEAD" else method), rule) in DECK_ROUTES
        reason = gate_reason(user_id, deck=deck)
    return 402, {"error": "pro_required", "gate": reason}


def decide(rule: str, method: str, user_id: str | None, is_mobile: bool,
           verified: bool) -> tuple[int, dict] | None:
    """None = let the request through; (402, body) = block it."""
    if not applies(rule, method):
        return None
    return verdict(rule, method, user_id, is_mobile, verified)


def gate_reason(user_id: str, *, deck: bool) -> str:
    held = _held_pro(user_id)
    if held is None:
        # PREVIEW_PAGES == 0, so a deck request always finds the preview spent.
        return PREVIEW_USED if deck else NEVER_TRIALED
    return TRIAL_EXPIRED if held == "trial" else LAPSED


def _held_pro(user_id: str) -> str | None:
    """How a user without pro now once held it, from their entitlement rows
    (any status) and the billing ledger: None (never), 'trial' (only through
    an intro trial) or 'paid'.

    Only App Store rows can be told apart: RevenueCat stamps each event
    `period_type` (TRIAL, INTRO, NORMAL, PROMOTIONAL, PREPAID) and the
    projector stores the whole event as subscription_events.payload. A row
    is a trial only when every ledger event for it says TRIAL. Manual and
    promo grants, founder, season pass and Stripe rows, and App Store rows
    whose ledger is missing or carries no period_type all read as 'paid'
    (→ lapsed): when the history can't prove a trial, `lapsed` is the
    honest default rather than inviting a second free trial."""
    rows = [r for r in entitlements.list_for_user(user_id)
            if r["entitlement"] == "pro"]
    if not rows:
        return None
    if any(r["source"] not in ("apple_iap", "trial") for r in rows):
        return "paid"
    store_rows = [r for r in rows if r["source"] == "apple_iap"]
    if store_rows and _period_types(store_rows) != {"TRIAL"}:
        return "paid"
    return "trial"


def _period_types(rows: list[dict]) -> set[str]:
    """Every RevenueCat period_type in the ledger for these App Store rows:
    events under the row's user and product, plus the event that last
    wrote each row (granted_by, sandbox prefix stripped). Product-scoped,
    so a tip (ftf_tip_*, no entitlement) never reads as a paid period."""
    t = db.subscription_events_table
    user_ids = {r["user_id"] for r in rows}
    products = {r["product_id"] for r in rows if r["product_id"]}
    event_ids = {(r["granted_by"] or "").removeprefix(entitlements.SANDBOX_GRANT_PREFIX)
                 for r in rows} - {""}
    with db.engine.begin() as conn:
        payloads = conn.execute(
            select(t.c.payload)
            .where(t.c.source == "revenuecat")
            .where(t.c.product_id.in_(products))
            .where(or_(t.c.user_id.in_(user_ids), t.c.event_id.in_(event_ids)))
        ).scalars().all()
    out: set[str] = set()
    for raw in payloads:
        try:
            period = (json.loads(raw) or {}).get("period_type")
        except (TypeError, ValueError, AttributeError):
            continue
        if period:
            out.add(str(period).upper())
    return out
