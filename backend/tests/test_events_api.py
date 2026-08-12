"""POST /api/events — first-party client-event ingestion, P1 contract
(docs/plans/analytics-platform/lld.md §2.1 / §4.1). Rewritten from the v0
contract (404/400/429, {accepted,dropped}) to the final always-200 pipeline.

Covers:
  (a) flag off (`analytics.ingest`) → 200 disposition "disabled", no rows
  (b) flag on → batch lands rows with the full envelope; {accepted, deduped,
      rejected, dropped, disposition}
  (c) identity — session token wins; else user_id='device:<id>'; neither →
      all-rejected(no_identity), still 200
  (d) dedup on event_id (within a batch and across retries) → `deduped`
  (e) unknown event_type → accepted-and-dropped (counted in accepted + dropped,
      no row), rest of batch unaffected
  (f) oversize batch (>50) → disposition batch_rejected:too_many, no rows
  (g) per-device rate limit → 200, accepted-and-dropped (never 429)
  (h) accounting invariant (T-3): accepted + deduped + len(rejected) == N
      across a batch mixing every disposition
  (i) empty batch → legal no-op
  (j) PII scrub of an allowed prop value (FR-47)

Isolated in-memory SQLite. The pipeline lives in backend/analytics_ingest.py
and writes via db.ingest_engine, so the harness patches BOTH db.engine and
db.ingest_engine to the same engine (two sqlite:///:memory: engines are
different databases), and patches analytics_ingest.is_enabled (the pipeline
imports the name directly).
"""
import json
import time
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.analytics_ingest as ingest
import backend.database as db_module
import backend.server as server
from backend.database import metadata, user_events_table

USER = "user_events_test"
TOKEN = "events-test-token"
DEVICE = "dev_abc123"


def _envelope(i=0, event_type="screen_viewed", **over):
    env = {
        "event_id": f"evt-{i:04d}xx",           # ≥8 chars, matches _EVENT_ID_RE
        "event_type": event_type,
        "client_ts": "2026-07-17T12:00:00Z",
        "screen": "Trades",
        "props": {"tab": "trades"},             # allowed prop for screen_viewed
        "session_id": "sess-uuid-0001",
        "seq": i + 1,
    }
    env.update(over)
    return env


def _post(client, events, device_id=DEVICE, token=None, headers=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["X-Session-Token"] = token
    if device_id is not None:
        h["X-Device-Id"] = device_id
    if headers:
        h.update(headers)
    return client.post("/api/events", headers=h,
                       data=json.dumps({"events": events}))


def _rows(engine):
    with engine.begin() as conn:
        return conn.execute(
            select(user_events_table).order_by(user_events_table.c.id)
        ).fetchall()


def _assert_invariant(body, n):
    """The one contract that must always hold on a committed txn."""
    assert body["accepted"] + body["deduped"] + len(body["rejected"]) == n


@pytest.fixture()
def harness():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    sess = {"user_id": USER, "last_active": 0.0}
    server.app.config["TESTING"] = True
    client = server.app.test_client()

    with patch.object(db_module, "engine", engine), \
         patch.object(db_module, "ingest_engine", engine), \
         patch.object(ingest, "is_enabled",
                      lambda k: k == "analytics.ingest"):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        with ingest._rate_lock:
            ingest._events_rate.clear()
        try:
            yield client, engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            with ingest._rate_lock:
                ingest._events_rate.clear()


# ── (a) flag off → disabled, queue retained (no 404) ───────────────────────

def test_flag_off_disabled():
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    with patch.object(ingest, "is_enabled", lambda k: False):
        r = _post(client, [_envelope()])
    assert r.status_code == 200
    assert r.get_json()["disposition"] == "disabled"
    assert r.get_json()["accepted"] == 0


# ── (b) batch insert works ─────────────────────────────────────────────────

def test_batch_insert_with_session(harness):
    client, engine = harness
    events = [_envelope(i, event_type=t) for i, t in
              enumerate(["app_opened", "screen_viewed", "find_trades_tapped"])]
    r = _post(client, events, token=TOKEN,
              headers={"X-Device": "iphone", "X-OS-Version": "18.1",
                       "X-App-Version": "1.8.0"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["accepted"] == 3 and body["deduped"] == 0
    assert body["rejected"] == [] and body["disposition"] == "ok"
    _assert_invariant(body, 3)

    rows = _rows(engine)
    assert len(rows) == 3
    first = rows[0]._mapping
    assert first["user_id"] == USER          # session identity wins
    assert first["event_type"] == "app_opened"
    assert first["device_id"] == DEVICE
    assert first["platform"] == "ios"        # derived from X-Device
    assert first["screen"] == "Trades"
    assert first["session_id"] == "sess-uuid-0001"
    assert first["source"] == "mobile"
    assert first["occurred_at"]              # server-stamped
    # screen_viewed row keeps its allowed prop + the seq rider
    sv = next(r._mapping for r in rows if r._mapping["event_type"] == "screen_viewed")
    props = json.loads(sv["props"])
    assert props["tab"] == "trades" and props["seq"] == 2


def test_api_request_failed_keeps_bg_and_allows_missing_ms(harness):
    # The client omits `ms` when a request spanned a foreground exit (the
    # wall-clock number would be meaningless) and sends bg=true instead.
    # `bg` must survive the prop allowlist or the fix is unobservable.
    client, engine = harness
    r = _post(client, [_envelope(event_type="api_request_failed", props={
        "route": "/api/sleeper/rosters/:id", "method": "GET",
        "status": 0, "timeout": True, "bg": True,   # note: no "ms"
    })], token=TOKEN)
    assert r.get_json()["accepted"] == 1
    props = json.loads(_rows(engine)[0]._mapping["props"])
    assert props["bg"] is True          # survived the allowlist
    assert "ms" not in props            # untrustworthy sample, correctly absent
    assert props["route"] == "/api/sleeper/rosters/:id"


def test_platform_from_body_when_no_device_header(harness):
    # Web + extension send no X-Device header, so they declare `platform` in
    # the body. Regression guard for the 2026-08-05 prod bug: every client
    # event had platform NULL because no SDK sent either signal.
    client, engine = harness
    r = client.post("/api/events",
                    headers={"Content-Type": "application/json",
                             "X-Device-Id": DEVICE, "X-Source": "web"},
                    data=json.dumps({"platform": "web",
                                     "events": [_envelope(event_type="app_opened",
                                                          props={"launch_type": "web"})]}))
    assert r.status_code == 200 and r.get_json()["accepted"] == 1
    row = _rows(engine)[0]._mapping
    assert row["platform"] == "web"          # body value honored
    assert row["source"] == "web"


def test_platform_derived_from_device_header(harness):
    # Mobile sends X-Device (+ X-OS-Version / X-App-Version); the backend
    # derives platform and stores the version snapshot. Guards the fix that
    # made events.ts forward getClientHeaders().
    client, engine = harness
    r = _post(client, [_envelope(event_type="app_opened", props={"launch_type": "cold"})],
              token=TOKEN, headers={"X-Device": "iphone", "X-OS-Version": "18.2",
                                    "X-App-Version": "1.9.0"})
    assert r.get_json()["accepted"] == 1
    row = _rows(engine)[0]._mapping
    assert row["platform"] == "ios"
    assert row["os_version"] == "18.2" and row["app_version"] == "1.9.0"


# ── (c) identity resolution ────────────────────────────────────────────────

def test_no_session_uses_device_identity(harness):
    client, engine = harness
    r = _post(client, [_envelope(event_type="signin_attempted",
                                 props={"method": "apple"})])
    body = r.get_json()
    assert body["accepted"] == 1
    assert _rows(engine)[0]._mapping["user_id"] == f"device:{DEVICE}"


def test_no_session_no_device_all_rejected(harness):
    client, _ = harness
    r = _post(client, [_envelope(), _envelope(1)], device_id=None)
    assert r.status_code == 200
    body = r.get_json()
    assert body["accepted"] == 0
    assert [x["reason"] for x in body["rejected"]] == ["no_identity", "no_identity"]
    _assert_invariant(body, 2)


# ── (d) dedup on event_id ──────────────────────────────────────────────────

def test_dedup_across_retries(harness):
    client, engine = harness
    batch = [_envelope(1), _envelope(2)]
    r1 = _post(client, batch, token=TOKEN)
    assert r1.get_json()["accepted"] == 2
    r2 = _post(client, batch, token=TOKEN)           # idempotent replay
    body = r2.get_json()
    assert body["accepted"] == 0 and body["deduped"] == 2
    _assert_invariant(body, 2)
    assert len(_rows(engine)) == 2


def test_dedup_within_batch(harness):
    client, engine = harness
    r = _post(client, [_envelope(7), _envelope(7)], token=TOKEN)
    body = r.get_json()
    assert body["accepted"] == 1 and body["deduped"] == 1
    _assert_invariant(body, 2)
    assert len(_rows(engine)) == 1


# ── (e) unknown event types → accepted-and-dropped, batch continues ────────

def test_unknown_type_dropped(harness):
    client, engine = harness
    r = _post(client, [
        _envelope(1, event_type="screen_viewed"),
        _envelope(2, event_type="totally_made_up", props={}),
        _envelope(3, event_type="find_trades_tapped", props={}),
        # A name that LOOKS right — the single-`c` misspelling of the P0-7
        # send leg. The guard has to be armed against plausible typos, not
        # only against "totally_made_up".
        _envelope(4, event_type="sleeper_send_suceeded", props={}),
    ], token=TOKEN)
    body = r.get_json()
    # accepted counts the dropped-unknown (accepted-and-dropped); dropped=2
    assert body["accepted"] == 4 and body["dropped"] == 2 and body["deduped"] == 0
    _assert_invariant(body, 4)
    types = [row._mapping["event_type"] for row in _rows(engine)]
    assert types == ["screen_viewed", "find_trades_tapped"]   # unknown never landed


# ── (f) oversize batch → batch_rejected, no rows ───────────────────────────

def test_oversize_batch_rejected(harness):
    client, engine = harness
    r = _post(client, [_envelope(i) for i in range(51)], token=TOKEN)
    assert r.status_code == 200
    assert r.get_json()["disposition"] == "batch_rejected:too_many"
    assert len(_rows(engine)) == 0


# ── (g) rate limit → accepted-and-dropped, never 429 ───────────────────────

def test_rate_limit_accepts_and_drops(harness):
    client, engine = harness
    bucket = int(time.time() // 3600)
    with ingest._rate_lock:
        ingest._events_rate[DEVICE] = (bucket, 10_000)   # cap already blown
    r = _post(client, [_envelope()], token=TOKEN)
    assert r.status_code == 200
    body = r.get_json()
    assert body["accepted"] == 1 and body["dropped"] == 1
    _assert_invariant(body, 1)
    assert len(_rows(engine)) == 0                        # nothing persisted


# ── (h) accounting invariant across a fully mixed batch (T-3) ──────────────

def test_accounting_invariant_mixed_batch(harness):
    client, engine = harness
    # Pre-seed one event_id so it dedups against the DB.
    _post(client, [_envelope(1)], token=TOKEN)
    batch = [
        _envelope(1),                                   # dup-in-db → deduped
        _envelope(2), _envelope(2),                     # dup-in-batch → 1 deduped
        _envelope(3, event_type="nope", props={}),      # unknown → accepted-and-dropped
        {"event_type": "screen_viewed"},                # malformed (no id/seq) → rejected
        _envelope(4),                                   # clean insert
    ]
    r = _post(client, batch, token=TOKEN)
    body = r.get_json()
    _assert_invariant(body, len(batch))
    assert body["deduped"] == 2                          # db-dup + batch-dup
    assert len(body["rejected"]) == 1
    assert body["accepted"] == 3                         # unknown(1) + evt-2(1) + evt-4(1)


# ── (i) empty batch → legal no-op ──────────────────────────────────────────

def test_empty_batch_noop(harness):
    client, _ = harness
    r = _post(client, [], token=TOKEN)
    body = r.get_json()
    assert body == {"accepted": 0, "deduped": 0, "rejected": [],
                    "dropped": 0, "disposition": "ok"}


# ── (j) PII scrub of an allowed prop value (FR-47) ─────────────────────────

def test_pii_scrubbed_in_allowed_prop(harness):
    client, engine = harness
    r = _post(client, [_envelope(
        1, event_type="client_error",
        props={"screen": "SignIn", "error_kind": "auth",
               "message": "failed for a@b.com bearer eyJabc.def.ghi", "fatal": False},
    )], token=TOKEN)
    assert r.get_json()["accepted"] == 1
    props = json.loads(_rows(engine)[0]._mapping["props"])
    assert "a@b.com" not in props["message"]
    assert "[scrubbed]" in props["message"]
    assert props["error_kind"] == "auth"        # non-PII prop preserved


# --- observability addendum (2026-07-19) -----------------------------------

def test_new_observability_events_accepted(harness):
    """api_request_failed + screen_left are in the taxonomy with their props."""
    client, engine = harness
    body = _post(client, [
        _envelope(0, event_type="api_request_failed",
                  props={"route": "/api/trades/generate", "method": "POST",
                         "status": 502, "ms": 1200, "timeout": False}),
        _envelope(1, event_type="screen_left",
                  props={"screen": "Trades", "dwell_ms": 8100, "reason": "nav"}),
    ]).get_json()
    _assert_invariant(body, 2)
    assert body["accepted"] == 2 and body["dropped"] == 0
    by_type = {r._mapping["event_type"]: r._mapping for r in _rows(engine)}
    assert set(by_type) == {"api_request_failed", "screen_left"}
    arf = json.loads(by_type["api_request_failed"]["props"])
    assert arf["route"] == "/api/trades/generate" and arf["status"] == 502
    sl = json.loads(by_type["screen_left"]["props"])
    assert sl["dwell_ms"] == 8100 and sl["reason"] == "nav"


def test_country_stamped_from_header(harness):
    """Coarse geo rides the CDN header (X-Country-Code fallback) — never IP."""
    client, engine = harness
    _post(client, [_envelope(0)], headers={"X-Country-Code": "us"})
    _post(client, [_envelope(1)])
    rows = sorted((r._mapping for r in _rows(engine)),
                  key=lambda m: m["event_id"])
    assert rows[0]["country"] == "US"      # normalized upper, 2 chars
    assert rows[1]["country"] is None      # no header → NULL, never guessed


def test_guide_events_accepted(harness):
    """Guided-avatar tour events (script §6) are in the taxonomy."""
    client, engine = harness
    body = _post(client, [
        _envelope(0, event_type="guide_step_shown",
                  props={"step": "s3.2", "pose": "thinking", "screen": "Trades"}),
        _envelope(1, event_type="guide_step_advanced",
                  props={"step": "s3.2", "via": "cta"}),
        _envelope(2, event_type="guide_tour_completed",
                  props={"steps_seen": 12}),
    ]).get_json()
    _assert_invariant(body, 3)
    assert body["accepted"] == 3 and body["dropped"] == 0


# --- P0 remediation batch (2026-08-11 addendum) ---------------------------

def test_p0_remediation_events_accepted(harness):
    """All 16 P0-batch client events land with their full prop sets.

    dropped == 0 AND an exact set(by_type) are the two assertions a
    default-deny allowlist can otherwise fail silently — this is the test
    that would have caught invite_shared, deck_regenerated and
    celebration_fired.
    """
    client, engine = harness
    specs = [
        ("tab_selected",  {"tab": "league", "from_tab": "trades",
                           "refocus": False, "intercepted": False}),
        ("league_view",   {"surface": "league_rankings", "state": "ready",
                           "platform": "sleeper", "team_count": 12,
                           "basis": "consensus", "subset": "all",
                           "starters_available": True, "outlook_shown": False,
                           "is_tab_root": True}),
        ("league_basis_changed",   {"basis": "personal", "from": "consensus",
                                    "boards_differ": True,
                                    "team_focused": False}),
        ("league_subset_changed",  {"subset": "starters", "from": "all",
                                    "source": "chart", "filter_count": 0,
                                    "picks_stripped": False}),
        ("league_team_opened",     {"via": "row", "rank": 3,
                                    "basis": "consensus", "subset": "all",
                                    "filter_count": 0}),
        ("league_home_action_tapped", {"action": "find_trades"}),
        ("sleeper_send_attempted", {"surface": "deck", "give_n": 2,
                                    "receive_n": 1, "from_deck": True,
                                    "has_target": True}),
        ("sleeper_send_failed",    {"surface": "awaiting",
                                    "error_code": "sleeper_rejected",
                                    "status": 409, "kind": "graphql",
                                    "give_n": 2, "receive_n": 1,
                                    "from_deck": False}),
        ("invite_shared",          {"league_id": "123456789012345678"}),
        ("invite_link_opened",     {"league_id": "123456789012345678",
                                    "has_ref": True, "format": "legacy",
                                    "auth_state": "account_only"}),
        ("invite_league_pinned",   {"league_id": "123456789012345678",
                                    "source": "picker_autopin",
                                    "ms_since_open": 4200}),
        ("invite_pin_failed",      {"league_id": "123456789012345678",
                                    "reason": "not_member"}),
        ("experiment_exposed",     {"experiment": "onboarding_v2_rollout",
                                    "variant": "v2", "unit": "device",
                                    "key": "onboarding.trades_first"}),
        ("quickset_step_advanced", {"position": "QB", "tier_index": 2,
                                    "tier_count": 8, "seeded_accepted": True,
                                    "picked_n": 3, "via": "save", "ms": 5100}),
        ("quickset_abandoned",     {"position": "QB", "tier_index": 3,
                                    "tiers_done": 2, "ms": 41000,
                                    "reason": "nav"}),
        ("deck_regenerated",       {"position": "QB", "new_trades": 7}),
    ]
    body = _post(client, [
        _envelope(i, event_type=t, props=p) for i, (t, p) in enumerate(specs)
    ]).get_json()
    _assert_invariant(body, len(specs))
    assert body["accepted"] == len(specs) and body["dropped"] == 0
    by_type = {r._mapping["event_type"]: r._mapping for r in _rows(engine)}
    assert set(by_type) == {t for t, _ in specs}          # every one LANDED
    # Spot-check that props survived the per-event allowlist intact.
    assert json.loads(by_type["league_view"]["props"])["team_count"] == 12
    assert json.loads(
        by_type["sleeper_send_failed"]["props"])["error_code"] == "sleeper_rejected"
    assert json.loads(
        by_type["experiment_exposed"]["props"])["experiment"] == "onboarding_v2_rollout"
    assert json.loads(by_type["deck_regenerated"]["props"])["new_trades"] == 7


def test_sleeper_send_succeeded_is_not_client_submittable(harness):
    """The success leg is server-authoritative — a client POST is dropped."""
    client, engine = harness
    body = _post(client, [
        _envelope(0, event_type="sleeper_send_succeeded",
                  props={"give_n": 1, "receive_n": 1}),
    ]).get_json()
    assert body["accepted"] == 1 and body["dropped"] == 1
    assert _rows(engine) == []


def test_p0_events_reject_device_platform_prop(harness):
    """No P0 event carries a DEVICE platform prop — the column is derived
    server-side from the batch body / X-Device headers. A bogus one is
    stripped."""
    client, engine = harness
    _post(client, [
        _envelope(0, event_type="league_view",
                  props={"surface": "league_home", "state": "ready",
                         "platform": "espn", "device_platform": "ios"}),
    ])
    props = json.loads(_rows(engine)[0]._mapping["props"])
    assert props["platform"] == "espn"          # LEAGUE platform survives
    assert "device_platform" not in props       # device prop stripped


# --- feedback #297 / #298 / #299 / #302 addendum (2026-08-11) --------------
# Tracking plan: docs/feedback/items/297-lineup-impact-single-pin/analytics.md
#
# These exist because NAME survival and PROP survival are SEPARATE silent
# failures on this endpoint (analytics_ingest.py:379-390):
#   * an unregistered event_type is accepted-and-DROPPED, never 4xx'd, so a
#     client track() call for it looks live and records nothing;
#   * a registered type with an unregistered prop keeps the row but has that
#     prop POPPED, so the row lands hollowed out.
# `trade_card_shared` is the live in-tree example of the second: registered,
# but props limited to {trade_id, channel}, so any `landing` is discarded.
#
# A test asserting "the client calls track with X" passes under BOTH failure
# modes. These assert the ROUND TRIP: every prop is read back out of
# user_events after ingestion, so a stripped prop fails.

def test_feedback_297_302_new_events_land_with_every_prop(harness):
    """Both new names register AND every specced prop survives ingest."""
    client, engine = harness
    body = _post(client, [
        _envelope(0, event_type="lineup_impact_unavailable",
                  screen="TradeCalculator",
                  props={"platform": "mfl"}),
        _envelope(1, event_type="league_team_closed",
                  screen="LeagueRankings",
                  props={"via": "header_back", "dwell_ms": 41200, "rank": 4}),
    ]).get_json()
    _assert_invariant(body, 2)
    # dropped == 0 proves the NAMES registered: an unknown type still counts
    # in `accepted`, so accepted alone proves nothing.
    assert body["accepted"] == 2 and body["dropped"] == 0

    by_type = {r._mapping["event_type"]: r._mapping for r in _rows(engine)}
    assert set(by_type) == {"lineup_impact_unavailable", "league_team_closed"}

    lu = json.loads(by_type["lineup_impact_unavailable"]["props"])
    assert lu["platform"] == "mfl"   # LEAGUE platform, not device
    assert by_type["lineup_impact_unavailable"]["screen"] == "TradeCalculator"

    lc = json.loads(by_type["league_team_closed"]["props"])
    assert lc["via"] == "header_back"        # the whole point of #302
    assert lc["dwell_ms"] == 41200
    assert lc["rank"] == 4


def test_feedback_299_302_reuses_league_team_opened_for_the_enter_half(harness):
    """#299/#302 adds an EXIT event only — the enter half is the shipped
    P0-7 `league_team_opened`, and no parallel 'focused' name exists.

    A duplicate enter name would be two sources of truth for one
    interaction; this pins that neither was minted.
    """
    from backend import analytics_taxonomy as t
    assert "league_team_opened" in t.ALLOWED_CLIENT_EVENTS
    assert "league_team_focused" not in t.ALLOWED_CLIENT_EVENTS
    assert "league_team_unfocused" not in t.ALLOWED_CLIENT_EVENTS

    client, engine = harness
    body = _post(client, [
        _envelope(0, event_type="league_team_opened", screen="LeagueRankings",
                  props={"via": "bar", "rank": 4, "basis": "consensus",
                         "subset": "all", "filter_count": 0}),
        _envelope(1, event_type="league_team_closed", screen="LeagueRankings",
                  props={"via": "refocus", "dwell_ms": 900, "rank": 4}),
    ]).get_json()
    assert body["accepted"] == 2 and body["dropped"] == 0
    assert {r._mapping["event_type"] for r in _rows(engine)} == {
        "league_team_opened", "league_team_closed"}


def test_feedback_298_mode_and_source_survive_on_existing_events(harness):
    """#298 rides `mode` on two events that ALREADY fire on this path, and
    un-strips the `source` the client has been sending since #257."""
    client, engine = harness
    body = _post(client, [
        _envelope(0, event_type="find_trades_tapped",
                  props={"source": "prefs_changed_strip",
                         "mode": "single_pin"}),
        _envelope(1, event_type="trade_card_viewed",
                  props={"trade_id": "t-99", "card_index": 0,
                         "mode": "single_pin"}),
    ]).get_json()
    _assert_invariant(body, 2)
    assert body["accepted"] == 2 and body["dropped"] == 0
    by_type = {r._mapping["event_type"]: r._mapping for r in _rows(engine)}
    ft = json.loads(by_type["find_trades_tapped"]["props"])
    assert ft["mode"] == "single_pin"
    assert ft["source"] == "prefs_changed_strip"   # was being stripped
    tc = json.loads(by_type["trade_card_viewed"]["props"])
    assert tc["mode"] == "single_pin" and tc["trade_id"] == "t-99"


def test_feedback_297_302_events_are_not_intent():
    """Exposure/terminator telemetry must NOT enter the DAU/WAU series.

    `analytics_queries.INTENT_EVENTS` is derived by SUBTRACTION
    (`(SERVER_FIRED | ALLOWED_CLIENT) - NON_INTENT_EVENTS`), so taxonomy
    growth is intent-BY-DEFAULT: registering a name and stopping there
    step-changes DAU/WAU with no error and no log, and the jump is
    indistinguishable from real growth after the fact. INTENT_EVENTS feeds
    ~10 call sites in that module.
    """
    from backend import analytics_queries as q
    new = {"lineup_impact_unavailable", "league_team_closed"}
    assert new <= q.NON_INTENT_EVENTS
    assert not (new & q.INTENT_EVENTS)
    # The enter half deliberately STAYS intent — the interaction is counted
    # once, by its opener.
    assert "league_team_opened" in q.INTENT_EVENTS
    # #298 added NO event name: a property on an event that already fires
    # cannot perturb the series at all.
    assert "find_trades_tapped" in q.INTENT_EVENTS


# --- feedback #300 addendum (2026-08-12) -----------------------------------
# Tracking plan:
# docs/feedback/items/300-league-rankings-trade-candidates/analytics.md
#
# #300 shipped LIT with the simulator gate and the Maestro run waived, so
# these two names are the only evidence that will ever exist that the
# League-rankings median divider works in the wild. Same two silent failure
# modes as the block above: an unregistered NAME is counted-and-dropped, and
# a registered name with an unregistered PROP lands hollowed out.

def test_feedback_300_new_events_land_with_every_prop(harness):
    """Both #300 names register AND every specced prop survives ingest."""
    client, engine = harness
    body = _post(client, [
        _envelope(0, event_type="league_pos_candidates_viewed",
                  screen="LeagueRankings",
                  props={"position": "WR", "divider": "shown"}),
        _envelope(1, event_type="league_candidate_pinned",
                  screen="LeagueRankings",
                  props={"verb": "target", "position": "WR", "rank": 3,
                         "side": "above"}),
    ]).get_json()
    _assert_invariant(body, 2)
    # dropped == 0 proves NAME survival; an unknown type still counts in
    # `accepted`, so `accepted` alone proves nothing.
    assert body["accepted"] == 2 and body["dropped"] == 0

    by_type = {r._mapping["event_type"]: r._mapping for r in _rows(engine)}
    assert set(by_type) == {"league_pos_candidates_viewed",
                            "league_candidate_pinned"}

    # PROP survival — read back out of user_events.props, not asserted on the
    # request. An unregistered prop is popped while the envelope still
    # reports dropped == 0.
    # `seq` and `ts_suspect` are stamped by the server AFTER the strip and
    # never pass through CLIENT_EVENT_PROPS, so they are excluded rather than
    # registered (analytics_taxonomy.py's own note).
    def _client_props(row):
        return {k: v for k, v in json.loads(row["props"]).items()
                if k not in {"seq", "ts_suspect"}}

    assert _client_props(by_type["league_pos_candidates_viewed"]) == {
        "position": "WR", "divider": "shown"}

    pin = _client_props(by_type["league_candidate_pinned"])
    assert pin == {"verb": "target", "position": "WR", "rank": 3,
                   "side": "above"}
    # `side` is what makes the pair readable: with the mirror roster stacked
    # in the drill-in, (verb, side) has four live combinations and
    # verb-against-side is the direct measure of users overriding the line.
    assert pin["side"] == "above" and pin["verb"] == "target"


def test_feedback_300_divider_outcome_values_all_survive(harness):
    """`divider` is three-valued on purpose — a shown-only impression event
    cannot distinguish "nobody found it" from "the payload arrived without
    `medians`", which is an incomplete-rollout signal, not a product one."""
    client, engine = harness
    body = _post(client, [
        _envelope(i, event_type="league_pos_candidates_viewed",
                  screen="LeagueRankings",
                  props={"position": p, "divider": d})
        for i, (p, d) in enumerate(
            [("QB", "shown"), ("RB", "no_median"), ("TE", "no_split")])
    ]).get_json()
    assert body["accepted"] == 3 and body["dropped"] == 0
    seen = {json.loads(r._mapping["props"])["divider"] for r in _rows(engine)}
    assert seen == {"shown", "no_median", "no_split"}


def test_feedback_300_position_prop_is_not_a_device_platform(harness):
    """#300's `position` is a CORE POSITION (QB|RB|WR|TE). Neither event may
    carry a device-platform prop — that is a server-derived COLUMN (the
    NULL-`platform` incident), and it is stripped here."""
    client, engine = harness
    _post(client, [
        _envelope(0, event_type="league_candidate_pinned",
                  screen="LeagueRankings",
                  props={"verb": "offer", "position": "TE", "rank": 9,
                         "side": "below", "platform": "ios"}),
    ])
    props = json.loads(_rows(engine)[0]._mapping["props"])
    assert props["position"] == "TE"
    assert "platform" not in props


def test_feedback_300_exposure_is_not_intent_but_the_action_is():
    """The split that keeps DAU/WAU honest.

    `INTENT_EVENTS` is derived by SUBTRACTION, so taxonomy growth is
    intent-BY-DEFAULT. `league_pos_candidates_viewed` is a passive exposure
    and is the ONLY event on that screen a user can emit without ever
    drilling in — admitting it would promote every idle position-pill tap to
    a user-day and step-change DAU from ship day.

    `league_candidate_pinned` deliberately STAYS intent: an asset chosen and
    the finder entered is a real value moment, the peer of
    `find_trades_tapped`. It seams nothing either way, because the row
    action is reachable only inside a drill-in and every drill-in emits an
    (intent) `league_team_opened` first.
    """
    from backend import analytics_queries as q
    assert "league_pos_candidates_viewed" in q.NON_INTENT_EVENTS
    assert "league_pos_candidates_viewed" not in q.INTENT_EVENTS
    assert "league_candidate_pinned" not in q.NON_INTENT_EVENTS
    assert "league_candidate_pinned" in q.INTENT_EVENTS


def test_feedback_300_mints_no_duplicate_of_a_shipped_league_event():
    """#300 adds an EXPOSURE and an ACTION. It must not re-mint an enter/exit
    name for the drill-in — `league_team_opened` / `league_team_closed`
    already own that interaction, and a second source of truth for one tap is
    the #208/#248/#293 bug class."""
    from backend import analytics_taxonomy as t
    assert "league_team_opened" in t.ALLOWED_CLIENT_EVENTS
    assert "league_team_closed" in t.ALLOWED_CLIENT_EVENTS
    for minted in ("league_candidate_opened", "league_divider_shown",
                   "league_candidate_viewed", "league_band_shown"):
        assert minted not in t.ALLOWED_CLIENT_EVENTS
