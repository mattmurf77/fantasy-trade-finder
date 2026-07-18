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
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import bindparam, text

from . import database as db
from .analytics_taxonomy import ALLOWED_CLIENT_EVENTS, SERVER_FIRED_EVENTS

# ---------------------------------------------------------------------------
# Canonical event sets (exact taxonomy strings)
# ---------------------------------------------------------------------------

# North star — Weekly Active Traders. The send leg is dark-and-absent (not yet
# in the taxonomy); WAT computes on its 3 live feeders with a "dark" caveat.
WAT_LIVE = frozenset({"trade_proposed", "match_swiped", "calc_trade_evaluated"})
WAT_DARK = frozenset({"sleeper_send_attempted", "sleeper_send_succeeded",
                      "sleeper_send_failed"})
WAT_EVENTS = WAT_LIVE | WAT_DARK

# Pure lifecycle/impression noise — excluded from DAU/WAU/MAU, churn, retention.
NON_INTENT_EVENTS = frozenset({
    "app_opened", "app_backgrounded", "app_open", "screen_viewed",
    "push_sent", "client_error",
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
    "send_in_sleeper":["sleeper_send_succeeded"],   # dark
}

VALID_REPORTS = ("waterfall", "time", "bottlenecks", "churn", "releases",
                 "adoption", "engagement", "pfo", "onepager")
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
    caveats.append(_dark_caveat("metric:wat.sleeper_send",
                                "send-leg WAT events not in taxonomy yet; WAT = trade_proposed/match_swiped/calc_trade_evaluated only"))
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
# Dispatcher
# ---------------------------------------------------------------------------

_BUILDERS = {
    "waterfall": report_waterfall,
    "time": report_time,
    "bottlenecks": report_bottlenecks,
    "churn": report_churn,
    "releases": report_releases,
    "adoption": report_adoption,
    "engagement": report_engagement,
    "pfo": report_pfo,
    "onepager": report_onepager,
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
               fmt="json", segment=None):
    """Compute a report on the read-only engine. Returns (envelope_dict, None)
    for json, or (csv_str, 'text/csv') for csv. Raises BadParam on bad input."""
    if report not in VALID_REPORTS:
        raise BadParam("unknown_report")
    start_day, end_day = _parse_window(start, end)
    row_cap = ROW_CAP_CSV if fmt == "csv" else ROW_CAP_JSON
    builder = _BUILDERS[report]
    with db.ro_engine.connect() as conn:
        rows, caveats, summary = builder(
            conn, start_day, end_day, include_demo, row_cap, segment=segment)
    params_echo = {"segment": segment, "include_demo": include_demo, "format": fmt}
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
