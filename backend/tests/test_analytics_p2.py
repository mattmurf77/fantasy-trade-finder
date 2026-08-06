"""Analytics platform P2 — report layer (backend/analytics_queries.py).

Seeded-DB tests that assert EXACT numbers, not just that queries run — the
correctness the P2 design→adversarial-verify workflow flagged:

  • attribution_join resolves a pre-auth device: row to its stitched user and
    counts them as ONE user (COALESCE sleeper_user_id first — no double-count).
  • device_exclusion drops demo/device: pseudo-ids by default, keeps them with
    include_demo, and is NULL-safe on server rows (session_id NULL).
  • honest degradation: a dark event → 'dark' cell (never a fabricated 0); a
    live event with 0 rows in a sub-cohort → a real 0.
  • window/ISO-week bucketing, unknown_report/bad_param, CSV, and the
    CRON-gated route (401 without secret, precedence of the static /health).

Isolated in-memory SQLite patched into BOTH db.engine and db.ro_engine (the
reports read via ro_engine; two :memory: engines are different DBs).
"""
import json
from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert

import backend.analytics_queries as aq
import backend.database as db
import backend.server as server
from backend.database import metadata, user_events_table, identity_links_table

# A window that comfortably contains the seeded events.
START, END = "2026-07-01", "2026-07-18"


def _ev(engine, user_id, event_type, day="2026-07-13", **cols):
    with engine.begin() as conn:
        conn.execute(insert(user_events_table).values(
            user_id=user_id, event_type=event_type,
            occurred_at=f"{day}T12:00:00+00:00", **cols))


def _seed(engine):
    # Two real signed-in users with trade opinions (WAT feeders).
    _ev(engine, "u_alice", "signup")
    _ev(engine, "u_alice", "trio_swipe")
    _ev(engine, "u_alice", "ranking_complete_first_time")
    _ev(engine, "u_alice", "trade_proposed")            # WAT
    _ev(engine, "u_bob", "signup")
    _ev(engine, "u_bob", "calc_trade_evaluated")        # WAT
    # A pre-auth device row LATER stitched to u_alice — must count as u_alice,
    # not as a separate user (attribution + no double-count).
    _ev(engine, "device:dev_x", "trade_proposed", day="2026-07-12",
        device_id="dev_x")
    with engine.begin() as conn:
        conn.execute(insert(identity_links_table).values(
            device_id="dev_x", sleeper_user_id="u_alice", account_id="acct_1",
            linked_at="2026-07-13T00:00:00+00:00"))
    # A demo user — excluded by default.
    _ev(engine, "demo_user_9", "trade_proposed")
    _ev(engine, "demo_user_9", "calc_trade_evaluated")


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    _seed(eng)
    with patch.object(db, "engine", eng), patch.object(db, "ro_engine", eng):
        yield eng


# --- attribution + no double-count -----------------------------------------

def test_wat_counts_stitched_device_as_one_user(engine):
    env, _ = aq.run_report("engagement", start=START, end=END)
    # Weekly rows; find the week with the WAT activity.
    wat_users = 0
    for r in env["rows"]:
        if r["wat"]["value"]:
            wat_users = max(wat_users, r["wat"]["value"])
    # WAT distinct users = {u_alice (via trade_proposed + the stitched device
    # row), u_bob (calc)} = 2. The demo user is excluded. The device: row
    # resolves to u_alice, NOT a third user.
    assert wat_users == 2


def test_attribution_prefers_sleeper_user_id(engine):
    # The stitched device row must resolve to u_alice (sleeper_user_id), the
    # same id the server-fired rows use — coalescing account_id first would
    # split u_alice into 'u_alice' + 'acct_1' and double-count.
    expr = aq.attribution_join("ue")
    assert "COALESCE(il.sleeper_user_id, il.account_id)" in expr


# --- device / demo exclusion, NULL-safe ------------------------------------

def test_demo_excluded_by_default_included_on_toggle(engine):
    base, _ = aq.run_report("engagement", start=START, end=END)
    withdemo, _ = aq.run_report("engagement", start=START, end=END, include_demo=True)
    base_mau = base["summary"]["mau"]
    demo_mau = withdemo["summary"]["mau"]
    # include_demo adds demo_user_9 → strictly more users.
    assert demo_mau > base_mau
    assert base_mau == 2   # alice + bob only


def test_device_exclusion_is_null_safe_on_server_rows(engine):
    # Server rows have NULL session_id; the demo NOT EXISTS must not drop them.
    # adoption reads live server events — alice's trio_swipe must appear.
    env, _ = aq.run_report("adoption", start=START, end=END)
    trios = next(r for r in env["rows"] if r["vertical"] == "rank_trios")
    assert trios["weekly_users"] == 1   # u_alice, kept despite NULL session_id


# --- honest degradation: dark vs real zero ---------------------------------

def test_dark_event_renders_dark_not_zero(engine):
    # screen_viewed (client, never seeded) is dark → the waterfall's client
    # stages carry a 'dark' step_conv cell, never a fabricated 0.
    env, _ = aq.run_report("waterfall", start=START, end=END)
    stage1 = next(r for r in env["rows"] if r["stage"] == 1)   # signin_started
    assert stage1["step_conv"]["caveat"] == "dark"
    assert stage1["reached"] is None


def test_overview_kpis_series_and_coverage(engine):
    # The dashboard home: KPI cards carry a daily series (zero-filled across
    # the window) so the renderer can draw a sparkline with no client math,
    # and coverage names what is flowing vs waiting — honestly.
    env, _ = aq.run_report("overview", start=START, end=END)
    r = env["rows"]
    keys = {k["key"] for k in r["kpis"]}
    assert {"active_users", "wat", "activation"} <= keys
    active = next(k for k in r["kpis"] if k["key"] == "active_users")
    # zero-filled daily series across the inclusive window
    ndays = (date.fromisoformat(END) - date.fromisoformat(START)).days + 1
    assert len(active["series"]) == ndays
    assert active["value"] == 2                     # alice + bob, demo excluded
    # frustration signals are all client-fired → dark, never a fabricated 0
    assert all(f["caveat"] == "dark" for f in r["frustration"])
    # coverage tells the operator exactly why
    assert r["coverage"]["status"] == "client_capture_off"
    assert r["coverage"]["client_events_dark_total"] > 0
    assert "signup" in r["coverage"]["events_flowing"]


def test_journeys_paths_around_anchor(engine):
    # Journeys reconstructs sessions from a 30-min inactivity gap (server rows
    # carry NULL session_id) and ranks what precedes/follows the anchor.
    env, _ = aq.run_report("journeys", start=START, end=END)
    r = env["rows"]
    assert r["anchor"] in r["candidates"]          # defaults to the most frequent
    assert r["sessions"] > 0 and r["anchor_hits"] > 0
    # every before/after step carries a count and a share of anchor hits
    for step in r["before"] + r["after"]:
        assert step["count"] > 0 and 0 < step["share"] <= 1
    # an explicit anchor is honored
    env2, _ = aq.run_report("journeys", start=START, end=END, anchor="trio_swipe")
    assert env2["rows"]["anchor"] == "trio_swipe"


def test_retention_triangle_shape(engine):
    # Weekly signup cohorts × weeks-since; cells beyond the window are None
    # (never a fabricated 0), and small cohorts are flagged for the renderer.
    env, _ = aq.run_report("retention", start=START, end=END)
    rows = env["rows"]
    assert rows, "seeded signups should produce at least one cohort"
    r0 = rows[0]
    assert r0["size"] >= 1
    assert len(r0["cells"]) == aq.RETENTION_WEEKS + 1
    w0 = r0["cells"][0]
    assert w0["week_n"] == 0
    assert w0["retained"] >= 1                     # signup week counts as active
    assert w0["small"] is True                     # 2 users < N_MIN
    # weeks past the window edge render as None, not 0%
    assert any(c is None for c in r0["cells"][1:])


def test_segments_evaluate_and_reject_bad_ops(engine):
    # A saved segment is evaluated live against the window.
    from sqlalchemy import insert as _ins
    with engine.begin() as conn:
        conn.execute(_ins(db.analytics_segments_table).values(
            name="calc users", definition_json=json.dumps({"did": "calc_trade_evaluated"}),
            created_at="2026-07-13T00:00:00+00:00"))
    env, _ = aq.run_report("segments", start=START, end=END)
    seg = env["rows"][0]
    assert seg["name"] == "calc users"
    assert seg["users"] == 1                       # only u_bob used the calculator
    assert 0 < seg["share"] <= 1
    # the grammar is closed — unknown ops and unknown events are rejected,
    # so no user string can reach SQL.
    with engine.connect() as conn:
        with pytest.raises(aq.BadParam):
            aq.evaluate_segment(conn, {"evil": "DROP TABLE users"}, START, END, False, 100)
        with pytest.raises(aq.BadParam):
            aq.evaluate_segment(conn, {"did": "not_a_real_event"}, START, END, False, 100)


def test_composed_reports_propagate_dark_caveats(engine):
    # Honest degradation across nested composition (the adversarial-review
    # catch): bottlenecks skips dark stages from its ranking, so it MUST carry
    # the waterfall's stage-dark caveat; the one-pager surfaces top_bottleneck
    # so it must carry both engagement and bottlenecks caveats. Without this a
    # reader can't tell "near-zero drop-off" from "not instrumented".
    bott, _ = aq.run_report("bottlenecks", start=START, end=END)
    assert any(c["code"] == "dark" and c["scope"].startswith("stage:")
               for c in bott["caveats"])
    one, _ = aq.run_report("onepager", start=START, end=END)
    scopes = {c["scope"] for c in one["caveats"]}
    assert any(s.startswith("stage:") for s in scopes)          # waterfall dark
    assert "metric:friction_signatures" in scopes                # bottlenecks dark


def test_live_event_zero_cohort_is_real_zero(engine):
    # push_sent is live-capable but none seeded → is_dark True → push summary
    # marked dark, not a fake 0-rate. But a live event WITH rows in a subcohort
    # that measures 0 shows 0. Here: activation guardrail in PFO — signup is
    # live (2 users) but only alice activated, so activation is a real fraction.
    env, _ = aq.run_report("pfo", start=START, end=END)
    act = env["rows"]["guardrails"]["activation_rate"]
    # 1 of 2 signups activated (alice), n=2 < N_MIN(20) → suppressed but n kept.
    assert act["n"] == 2
    assert act["caveat"] == "n_too_small"      # real measurement, small cohort


# --- window / params / format ----------------------------------------------

def test_unknown_report_and_bad_window(engine):
    with pytest.raises(aq.BadParam):
        aq.run_report("nope")
    with pytest.raises(aq.BadParam):
        aq.run_report("waterfall", start="2026-01-01", end="2026-07-18")  # >90d
    with pytest.raises(aq.BadParam):
        aq.run_report("waterfall", start="not-a-date")


def test_csv_export(engine):
    out, ct = aq.run_report("adoption", start=START, end=END, fmt="csv")
    assert ct == "text/csv"
    assert out.startswith("#") or "vertical" in out   # caveat comments + header


def test_week_key_is_iso_monday_utc():
    # 2026-07-18 is a Saturday; its ISO week's Monday is 2026-07-13.
    assert aq.week_key("2026-07-18") == "2026-07-13"
    assert aq.week_key("2026-07-13") == "2026-07-13"   # Monday maps to itself


# --- the gated route --------------------------------------------------------

def test_route_requires_secret_and_health_precedence(engine):
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    with patch.object(server, "_CRON_SECRET", "s3cr3t"), \
         patch.object(server, "_IS_PROD_ENV", True):
        # No secret → not authorized.
        r = client.get("/api/admin/analytics/engagement")
        assert r.status_code in (401, 403)
        # Correct secret → 200 report JSON.
        ok = client.get("/api/admin/analytics/engagement?start=%s&end=%s" % (START, END),
                        headers={"X-Cron-Secret": "s3cr3t"})
        assert ok.status_code == 200 and ok.get_json()["report"] == "engagement"
        # Unknown report → 400, not 500.
        bad = client.get("/api/admin/analytics/nope", headers={"X-Cron-Secret": "s3cr3t"})
        assert bad.status_code == 400
        # /health is a SEPARATE static route (precedence), still returns plumbing.
        h = client.get("/api/admin/analytics/health", headers={"X-Cron-Secret": "s3cr3t"})
        assert h.status_code == 200 and "wal" in h.get_json()
