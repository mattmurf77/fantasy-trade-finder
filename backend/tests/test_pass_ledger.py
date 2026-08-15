"""B1 — the nightly pass ledger (LLD §3.3/§4.1, §5 E1/E2, T-1/T-2/T-3).

Sabotage-proven, house convention: every test names the sabotage that must
make it fail. Review checks the sabotage list, not the green run.

The headline test is T-1, the merge gate. `_legacy_daily_tick` below is a
VERBATIM copy of the pre-refactor inline `cron_daily_tick`
(`git show 2080540:backend/server.py`, lines 17276-17470), with three
mechanical edits and nothing else:

  1. `now` is a parameter instead of `datetime.now(timezone.utc)`;
  2. module-level names are qualified `server.<name>` so a monkeypatch on the
     server module is visible to BOTH implementations;
  3. `jsonify({...})` becomes a plain `{...}` (no app context needed).

Both implementations run against the same recorder patches on the same
fixtures — an ordinary day and, mandatorily, **an Aug-25 day** — and must
produce an identical call sequence and an identical payload minus `passes`.
"""

import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, insert, select, update

import backend.database as db_module
import backend.eval.nightly as eval_nightly
import backend.relevance.config as cfg
import backend.relevance.registry as reg
import backend.server as server
from backend.database import cron_pass_runs_table, metadata, model_config_table


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

@pytest.fixture
def eng(tmp_path, monkeypatch):
    """Isolated file-backed product engine with the real schema."""
    e = create_engine(f"sqlite:///{tmp_path / 'ledger.db'}",
                      connect_args={"check_same_thread": False, "timeout": 30})
    metadata.create_all(e)
    monkeypatch.setattr(db_module, "engine", e)
    cfg._reset_cache()
    yield e
    cfg._reset_cache()


def _kill(eng, name, value=1):
    """Set the operational valve `cron.pass_disabled.<name>`."""
    with eng.begin() as conn:
        conn.execute(insert(model_config_table).values(
            key=f"cron.pass_disabled.{name}", value=value, description="test"))


def _rows(eng):
    with eng.connect() as conn:
        return {r.pass_name: r for r in
                conn.execute(select(cron_pass_runs_table)).fetchall()}


NOW_ORDINARY = datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc)
NOW_AUG25    = datetime(2026, 8, 25, 9, 0, tzinfo=timezone.utc)


def _users(now):
    """Five signed-up users covering every branch of the push scan."""
    iso = lambda d: (now - timedelta(days=d)).isoformat()
    return [
        # finish_ranking: signed up >3d ago, nothing unlocked
        {"sleeper_user_id": "u_finish", "signup_at": iso(10),
         "last_active_at": iso(1), "unlocked_formats": []},
        # winback_dormant: 40d idle
        {"sleeper_user_id": "u_dormant", "signup_at": iso(100),
         "last_active_at": iso(40), "unlocked_formats": ["1qb_ppr"]},
        # winback_matches: 10d idle WITH unread
        {"sleeper_user_id": "u_wb_yes", "signup_at": iso(100),
         "last_active_at": iso(10), "unlocked_formats": ["1qb_ppr"]},
        # 10d idle, no unread ⇒ nothing
        {"sleeper_user_id": "u_wb_no", "signup_at": iso(100),
         "last_active_at": iso(10), "unlocked_formats": ["1qb_ppr"]},
        # active ⇒ nothing
        {"sleeper_user_id": "u_active", "signup_at": iso(100),
         "last_active_at": iso(1), "unlocked_formats": ["1qb_ppr"]},
    ]


_UNREAD = {"u_dormant": 2, "u_wb_yes": 3, "u_wb_no": 0}


def _patch_recorders(monkeypatch, now, *, honest_winbacks: bool,
                     replenish=None, prod=True):
    """Replace every side-effecting call the tick makes with a recorder.

    Returns the shared call log. Both the legacy and the registry tick see the
    exact same patches, which is what makes T-1 a real equivalence test rather
    than two runs of the same code.
    """
    calls: list = []

    def rec(label, ret=None):
        def _f(*a, **kw):
            calls.append((label, a, kw))
            return ret() if callable(ret) else ret
        return _f

    monkeypatch.setattr(server, "load_all_signed_up_users",
                        rec("load_all_signed_up_users", lambda: _users(now)))
    monkeypatch.setattr(server, "_send_typed_push", rec("_send_typed_push"))

    def _unread(uid, *a, **kw):
        calls.append(("load_unread_match_count", (uid,), {}))
        return _UNREAD.get(uid, 0)
    monkeypatch.setattr(server, "load_unread_match_count", _unread)

    monkeypatch.setattr(server, "count_notification_sends_since",
                        rec("count_notification_sends_since", 0))
    monkeypatch.setattr(server, "is_enabled",
                        lambda key, *a, **kw: honest_winbacks
                        if key == "notif.honest_winbacks" else False)

    monkeypatch.setattr(server, "_deck_replenishment_enabled",
                        rec("_deck_replenishment_enabled", replenish is not None))
    monkeypatch.setattr(server, "_run_weekly_replenishment",
                        rec("_run_weekly_replenishment", replenish))

    monkeypatch.setattr(eval_nightly, "run_all",
                        rec("eval.run_all", {"ran": 2, "errors": 0,
                                             "summary": "2 scorers"}))

    monkeypatch.setattr(server, "_deck_value_model_enabled",
                        rec("_deck_value_model_enabled", False))

    monkeypatch.setattr(server, "_IS_PROD_ENV", prod)
    monkeypatch.setattr(server, "_players_cache_age_seconds",
                        rec("_players_cache_age_seconds", 10 ** 9))
    monkeypatch.setattr(server, "_refresh_players_cache_async",
                        rec("_refresh_players_cache_async", True))
    monkeypatch.setattr(server, "_check_rookie_class_load",
                        rec("_check_rookie_class_load"))
    monkeypatch.setattr(server, "_kickoff_roster_snapshot_sweep",
                        rec("_kickoff_roster_snapshot_sweep",
                            {"disabled": False, "leagues_queued": 4}))
    return calls


# ---------------------------------------------------------------------------
# The pre-refactor inline tick, verbatim (see module docstring)
# ---------------------------------------------------------------------------

def _legacy_daily_tick(now):
    cutoff_7d  = (now - timedelta(days=7)).isoformat()
    cutoff_30d = (now - timedelta(days=30)).isoformat()
    cutoff_3d  = (now - timedelta(days=3)).isoformat()

    counters: dict[str, int] = {
        "winback_matches": 0, "winback_dormant": 0,
        "finish_ranking":  0, "season_start":    0,
    }
    is_aug25 = (now.month == 8 and now.day == 25)

    for u in server.load_all_signed_up_users():
        uid = u["sleeper_user_id"]
        last_active = u.get("last_active_at")
        signup_at   = u.get("signup_at")
        unlocked    = u.get("unlocked_formats") or []

        # ── season_start: Aug 25 fan-out, all signed-up users ──
        if is_aug25:
            server._send_typed_push(
                uid, "season_start",
                title = "Football is back",
                body  = "Re-rank your players to find this year's trades.",
                data  = {"season": now.year},
            )
            counters["season_start"] += 1
            continue   # don't double-stack a winback on top of season kickoff

        # ── finish_ranking: signed up >3d ago, no format unlocked ──
        if signup_at and signup_at < cutoff_3d and not unlocked:
            server._send_typed_push(
                uid, "finish_ranking",
                title = "You're 5 minutes from your first trade",
                body  = "Finish ranking your players to unlock matches.",
                data  = {},
            )
            counters["finish_ranking"] += 1
            continue

        # ── winback_dormant: 30d inactive ──
        if last_active and last_active < cutoff_30d:
            if server.is_enabled("notif.honest_winbacks"):
                if server.count_notification_sends_since(
                        uid, "winback_dormant", last_active) >= 3:
                    continue
                unread = server.load_unread_match_count(uid)
                if unread <= 0:
                    continue
                server._send_typed_push(
                    uid, "winback_dormant",
                    title = "Your league misses you",
                    body  = (f"You have {unread} unreviewed trade "
                             f"match{'es' if unread != 1 else ''} waiting."),
                    data  = {"unread_count": unread},
                )
            else:
                server._send_typed_push(
                    uid, "winback_dormant",
                    title = "Your league misses you",
                    body  = "New trade matches are waiting when you're ready.",
                    data  = {},
                )
            counters["winback_dormant"] += 1
            continue

        # ── winback_matches: 7d inactive AND ≥1 unread match ──
        if last_active and last_active < cutoff_7d:
            unread = server.load_unread_match_count(uid)
            if unread > 0:
                server._send_typed_push(
                    uid, "winback_matches",
                    title = (f"{unread} match{'es' if unread != 1 else ''} "
                             "waiting"),
                    body  = "Your leaguemates have been busy. Tap to review.",
                    data  = {"unread_count": unread},
                )
                counters["winback_matches"] += 1

    # ── F10 (flag deck.replenishment) — weekly deck pre-generation ──
    replenish_stats: dict | None = None
    if server._deck_replenishment_enabled():
        try:
            replenish_stats = server._run_weekly_replenishment(now)
        except Exception as e:
            server.log.warning("daily-tick: replenishment pass failed: %s", e)
            replenish_stats = {"error": str(e)}

    # ── F8 — offline eval nightly (operator tooling, unflagged) ──
    eval_summary: str | None = None
    try:
        from backend.eval.nightly import run_all as _eval_run_all
        _eval_stats = _eval_run_all(window_days=30)
        eval_summary = _eval_stats.get("summary")
        if _eval_stats.get("ran"):
            counters["eval_scorers_graded"] = _eval_stats["ran"]
        if _eval_stats.get("errors"):
            server.log.warning("daily-tick eval: %s scorer(s) errored "
                               "(recorded in runs.jsonl)", _eval_stats["errors"])
    except Exception as e:
        server.log.warning("daily-tick: offline-eval pass failed (non-fatal): %s", e)
    if eval_summary:
        server.log.info("daily-tick eval: %s", eval_summary)

    # ── F6 (flag deck.value_model — SHIPS DARK) — nightly refit ──
    if server._deck_value_model_enabled():
        try:
            vm_stats = server._value_model.nightly_refit(now=now)
            server.log.info("daily-tick value-model refit: %s", vm_stats)
            if vm_stats.get("status") == "trained":
                counters["value_model_trained"] = 1
        except Exception as e:
            server.log.warning("daily-tick: value-model refit failed "
                               "(non-fatal): %s", e)

    # ── M0 — player-cache refresh fallback guard ──
    players_refresh_started: bool | None = None
    try:
        _age = server._players_cache_age_seconds()
        if server._IS_PROD_ENV and (_age is None
                                    or _age > server._PLAYERS_CACHE_TTL_SECONDS):
            players_refresh_started = server._refresh_players_cache_async()
    except Exception as e:
        server.log.warning("daily-tick: players-refresh guard failed "
                           "(continuing): %s", e)

    # ── M0 — rookie class-load monitor ──
    try:
        server._check_rookie_class_load(server._CURRENT_SEASON + 1)
    except Exception as e:
        server.log.warning("daily-tick: class-load monitor failed "
                           "(continuing): %s", e)

    # ── ADR-011 Writer B — weekly roster-snapshot sweep kickoff ──
    roster_snapshot_stats: dict | None = None
    try:
        roster_snapshot_stats = server._kickoff_roster_snapshot_sweep(now)
    except Exception as e:
        server.log.warning("daily-tick: roster-snapshot kickoff failed "
                           "(continuing): %s", e)

    server.log.info("daily-tick: %s", counters)
    extra: dict = {}
    if roster_snapshot_stats is not None and not roster_snapshot_stats.get("disabled"):
        extra["roster_snapshot"] = roster_snapshot_stats
    if players_refresh_started is not None:
        extra["players_refresh_started"] = players_refresh_started
    if replenish_stats is not None:
        server.log.info("daily-tick replenish: %s", replenish_stats)
        return {"ok": True, **counters, "replenish": replenish_stats, **extra}
    return {"ok": True, **counters, **extra}


# ---------------------------------------------------------------------------
# T-1 — equivalence (THE MERGE GATE)
# ---------------------------------------------------------------------------

_FIXTURES = [
    # (label, now, honest_winbacks, replenish_stats)
    ("ordinary_honest_off", NOW_ORDINARY, False, None),
    ("ordinary_honest_on",  NOW_ORDINARY, True,  None),
    ("ordinary_replenish",  NOW_ORDINARY, False, {"decks_generated": 3}),
    # MANDATORY: the fan-out date. Legacy sends season_start and nothing else;
    # the split must reproduce that exactly.
    ("aug25",               NOW_AUG25,    False, None),
    ("aug25_honest_on",     NOW_AUG25,    True,  None),
]


@pytest.mark.parametrize("label,now,honest,repl", _FIXTURES,
                         ids=[f[0] for f in _FIXTURES])
def test_t1_registry_tick_matches_legacy_inline_tick(
        eng, monkeypatch, label, now, honest, repl):
    # SABOTAGE (any of these must turn this red):
    #   • drop a pass from DAILY_TICK_REGISTRY, or reorder two of them;
    #     (NOTE: swapping `season_start` and `pushes` specifically does NOT
    #     fail here, and shouldn't — they are mutually exclusive by date, so
    #     the observable sequence is identical either way. The declared order
    #     is pinned by test_registry_order_matches_the_lld instead.)
    #   • delete the `is_aug25` early-return in `_tick_pass_pushes` (the
    #     Aug-25 fixtures gain 5 winback/finish_ranking sends on top of the
    #     fan-out — the double-send this split exists to prevent);
    #   • delete the `not_aug25` early-return in `_tick_pass_season_start`
    #     (load_all_signed_up_users is then called twice on ordinary days);
    #   • change a push title/body/data payload, a cutoff, or a counter name;
    #   • drop `ctx.state["replenish_stats"]` / `players_refresh_started` /
    #     `roster_snapshot_stats` (the response loses a key).
    legacy_calls = _patch_recorders(monkeypatch, now, honest_winbacks=honest,
                                    replenish=repl)
    legacy_payload = _legacy_daily_tick(now)
    legacy_seq = list(legacy_calls)

    new_calls = _patch_recorders(monkeypatch, now, honest_winbacks=honest,
                                 replenish=repl)
    new_payload = server._daily_tick_payload(now)
    new_seq = list(new_calls)

    assert new_seq == legacy_seq, (
        f"[{label}] call sequence diverged\nlegacy={legacy_seq}\nnew   ={new_seq}")

    assert "passes" in new_payload
    stripped = {k: v for k, v in new_payload.items() if k != "passes"}
    assert stripped == legacy_payload, f"[{label}] response payload diverged"


def test_t1_aug25_sends_only_season_start(eng, monkeypatch):
    # SABOTAGE: remove the is_aug25 guard from `_tick_pass_pushes` ⇒ the
    # fan-out date also fires finish_ranking/winback pushes. This is the
    # PRD's named double-send blocker, asserted directly rather than only
    # via the equivalence diff.
    calls = _patch_recorders(monkeypatch, NOW_AUG25, honest_winbacks=False)
    payload = server._daily_tick_payload(NOW_AUG25)

    kinds = [a[1] for (label, a, kw) in calls if label == "_send_typed_push"]
    assert kinds == ["season_start"] * 5
    assert payload["season_start"] == 5
    assert payload["winback_matches"] == payload["winback_dormant"] == 0
    assert payload["finish_ranking"] == 0
    # load_all_signed_up_users called ONCE, by season_start only.
    assert sum(1 for c in calls if c[0] == "load_all_signed_up_users") == 1
    assert payload["passes"]["season_start"] == reg.STATUS_OK
    assert payload["passes"]["pushes"] == reg.STATUS_OK


def test_t1_ordinary_day_season_start_is_a_noop(eng, monkeypatch):
    # SABOTAGE: drop the date gate from `_tick_pass_season_start` ⇒ every
    # signed-up user gets a "Football is back" push in June.
    calls = _patch_recorders(monkeypatch, NOW_ORDINARY, honest_winbacks=False)
    payload = server._daily_tick_payload(NOW_ORDINARY)
    kinds = [a[1] for (label, a, kw) in calls if label == "_send_typed_push"]
    assert "season_start" not in kinds
    assert payload["season_start"] == 0
    assert sum(1 for c in calls if c[0] == "load_all_signed_up_users") == 1


def test_registry_order_matches_the_lld(eng):
    # SABOTAGE: reorder the registry. LLD §4.1 fixes the order (time-sensitive
    # user-facing work first, analysis second, guards last) so that a wall
    # deadline starves the least important passes, not the pushes. Equivalence
    # alone cannot catch a swap between two passes whose date gates are
    # mutually exclusive, so the declared order is asserted directly.
    assert [s.name for s in server.DAILY_TICK_REGISTRY] == [
        "season_start", "pushes", "replenish", "eval", "refit",
        "players_guard", "class_load", "roster_snapshot",
    ]
    by_name = {s.name: s for s in server.DAILY_TICK_REGISTRY}
    # Only the date-gated fan-out is exempt from the deadline skip.
    assert by_name["season_start"].klass == reg.KLASS_MUST_COMPLETE
    assert all(s.klass == reg.KLASS_RESUMABLE
               for n, s in by_name.items() if n != "season_start")


def test_t1_every_pass_gets_a_ledger_row(eng, monkeypatch):
    # SABOTAGE: skip the `_write` on the success path ⇒ rows stay 'running'
    # forever and the ledger stops being a record of what completed.
    _patch_recorders(monkeypatch, NOW_ORDINARY, honest_winbacks=False)
    server._daily_tick_payload(NOW_ORDINARY)
    rows = _rows(eng)
    assert set(rows) == {s.name for s in server.DAILY_TICK_REGISTRY}
    for name, r in rows.items():
        assert r.status == reg.STATUS_OK, name
        assert r.run_date == "2026-06-10"
        assert r.attempt == 1
        assert r.duration_ms is not None


# ---------------------------------------------------------------------------
# Synthetic registry — claim semantics (T-2, T-3, isolation, valves, classes)
# ---------------------------------------------------------------------------

def _spec(name, fn, **kw):
    kw.setdefault("budget_s", 10.0)
    return reg.PassSpec(name=name, fn=fn, **kw)


def _counter_pass(log, name, *, raises=False, sleep=0.0):
    def fn(ctx):
        if sleep:
            import time as _t
            _t.sleep(sleep)
        log.append(name)
        if raises:
            raise RuntimeError(f"{name} exploded")
        return {"items": 1}
    return fn


def test_t2_double_post_runs_each_body_exactly_once(eng):
    # T-2 SABOTAGE: replace the INSERT-claim with a SELECT-then-INSERT (or
    # drop the uq_pass_run constraint) ⇒ both threads run every body.
    log: list = []
    registry = [_spec("a", _counter_pass(log, "a", sleep=0.15)),
                _spec("b", _counter_pass(log, "b", sleep=0.15))]
    now = NOW_ORDINARY
    errs: list = []

    def go():
        try:
            reg.run_ledger(now, registry=registry)
        except Exception as e:                # pragma: no cover
            errs.append(e)

    ts = [threading.Thread(target=go) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    assert not errs
    assert sorted(log) == ["a", "b"], f"a body ran twice: {log}"
    rows = _rows(eng)
    assert {n: r.status for n, r in rows.items()} == {"a": "ok", "b": "ok"}


def test_t3_stale_running_row_is_reclaimed(eng):
    # T-3 SABOTAGE: delete the stale-`running` branch in `_claim` ⇒ one
    # mid-pass OOM wedges the pass for the whole day and this body never runs.
    now = NOW_ORDINARY
    stale_at = (now - timedelta(seconds=30)).isoformat()   # 3× a 10s budget
    with eng.begin() as conn:
        conn.execute(insert(cron_pass_runs_table).values(
            pass_name="a", run_date="2026-06-10", status=reg.STATUS_RUNNING,
            started_at=stale_at, attempt=1))

    log: list = []
    reg.run_ledger(now, registry=[_spec("a", _counter_pass(log, "a"))])

    assert log == ["a"]
    row = _rows(eng)["a"]
    assert row.status == reg.STATUS_OK
    assert row.attempt == 2


def test_fresh_running_row_is_not_stolen(eng):
    # SABOTAGE: make the stale window unconditional (or compare against the
    # wrong side of 2× budget) ⇒ a live worker's pass gets run twice.
    now = NOW_ORDINARY
    fresh_at = (now - timedelta(seconds=5)).isoformat()    # < 2× 10s
    with eng.begin() as conn:
        conn.execute(insert(cron_pass_runs_table).values(
            pass_name="a", run_date="2026-06-10", status=reg.STATUS_RUNNING,
            started_at=fresh_at, attempt=1))
    log: list = []
    out = reg.run_ledger(now, registry=[_spec("a", _counter_pass(log, "a"))])
    assert log == []
    assert out["statuses"]["a"] == reg.STATUS_SKIPPED


def test_already_ok_today_is_skipped(eng):
    # SABOTAGE: drop the `status == ok ⇒ skip` branch ⇒ a Render retry of the
    # tick re-runs every pass, re-sending pushes.
    now = NOW_ORDINARY
    log: list = []
    registry = [_spec("a", _counter_pass(log, "a"))]
    reg.run_ledger(now, registry=registry)
    reg.run_ledger(now, registry=registry)
    assert log == ["a"]


def test_raising_pass_is_isolated_and_recorded_error(eng):
    # SABOTAGE: remove the per-pass try/except ⇒ `c` never runs, exactly the
    # silent-skip failure the ledger exists to kill.
    log: list = []
    registry = [_spec("a", _counter_pass(log, "a")),
                _spec("b", _counter_pass(log, "b", raises=True)),
                _spec("c", _counter_pass(log, "c"))]
    out = reg.run_ledger(NOW_ORDINARY, registry=registry)

    assert log == ["a", "b", "c"]
    assert out["statuses"] == {"a": "ok", "b": "error", "c": "ok"}
    rows = _rows(eng)
    assert rows["b"].status == reg.STATUS_ERROR
    assert "exploded" in rows["b"].error_text


def test_errored_resumable_pass_is_not_retried_same_day(eng):
    # SABOTAGE: let `error` re-claim for resumable passes ⇒ E2's "resumable
    # next day" becomes an unbounded same-tick retry loop.
    log: list = []
    registry = [_spec("a", _counter_pass(log, "a", raises=True))]
    reg.run_ledger(NOW_ORDINARY, registry=registry)
    reg.run_ledger(NOW_ORDINARY, registry=registry)
    assert log == ["a"]


# ---------------------------------------------------------------------------
# Valves — inverted polarity
# ---------------------------------------------------------------------------

def test_valve_disables_only_the_named_pass(eng):
    # SABOTAGE: invert the polarity (absent ⇒ disabled) ⇒ every pass is
    # skipped by default and the nightly pushes silently stop. Or key the
    # valve off the wrong name ⇒ the wrong pass dies.
    _kill(eng, "b")
    log: list = []
    registry = [_spec("a", _counter_pass(log, "a")),
                _spec("b", _counter_pass(log, "b")),
                _spec("c", _counter_pass(log, "c"))]
    out = reg.run_ledger(NOW_ORDINARY, registry=registry)

    assert log == ["a", "c"]
    assert out["statuses"] == {"a": "ok", "b": "skipped", "c": "ok"}
    # M1: the skip must record its CAUSE, so a dark pass and a starved pass
    # can be told apart in the green-rate report.
    assert _rows(eng)["b"].error_text == reg.SKIP_VALVE


def test_absent_valve_runs_the_pass(eng):
    # SABOTAGE: treat a missing model_config row as "disabled".
    log: list = []
    reg.run_ledger(NOW_ORDINARY, registry=[_spec("a", _counter_pass(log, "a"))])
    assert log == ["a"]


def test_valve_goes_through_the_resolver_exempt_path(eng, monkeypatch):
    # SABOTAGE: read the valve through `resolve()` (which RAISES on a valve
    # key) or through the 5s snapshot cache ⇒ an experiment overlay could
    # resurrect a killed pass, and the kill switch would not bite immediately.
    seen: list = []
    real_valve = cfg.valve

    def spy(key, default=0.0):
        seen.append(key)
        return real_valve(key, default)
    monkeypatch.setattr(reg, "valve", spy)
    reg.run_ledger(NOW_ORDINARY, registry=[_spec("zz", lambda ctx: {})])
    assert seen == ["cron.pass_disabled.zz"]
    with pytest.raises(ValueError):
        cfg.resolve("cron.pass_disabled.zz", 0.0)


# ---------------------------------------------------------------------------
# Classes: deadline skip vs must_complete_today
# ---------------------------------------------------------------------------

def test_resumable_passes_are_deadline_skipped_but_must_complete_runs(eng):
    # SABOTAGE: check the deadline for every class ⇒ the Aug-25 fan-out is
    # lost to a slow night and never comes back (its date gate is gone
    # tomorrow). Or check the deadline mid-pass ⇒ preemption, which §2.1
    # forbids.
    log: list = []
    registry = [
        _spec("slow", _counter_pass(log, "slow")),
        _spec("later", _counter_pass(log, "later")),
        _spec("dated", _counter_pass(log, "dated"),
              klass=reg.KLASS_MUST_COMPLETE),
    ]
    # wall_budget_s=0 ⇒ the deadline is already past at the first check.
    out = reg.run_ledger(NOW_ORDINARY, wall_budget_s=0.0, registry=registry)

    assert log == ["dated"]
    assert out["statuses"] == {"slow": "skipped", "later": "skipped",
                               "dated": "ok"}
    assert _rows(eng)["slow"].error_text == reg.SKIP_DEADLINE


def test_deadline_skipped_pass_is_picked_up_by_the_next_tick(eng):
    # SABOTAGE: treat a `skipped` row as terminal ⇒ a pass skipped once is
    # skipped for the rest of the day, forever silently.
    log: list = []
    registry = [_spec("a", _counter_pass(log, "a"))]
    reg.run_ledger(NOW_ORDINARY, wall_budget_s=0.0, registry=registry)
    assert log == []
    reg.run_ledger(NOW_ORDINARY, wall_budget_s=600.0, registry=registry)
    assert log == ["a"]
    assert _rows(eng)["a"].status == reg.STATUS_OK


def test_must_complete_today_retries_twice_then_errors(eng):
    # SABOTAGE: drop the same-day retry loop ⇒ one transient failure loses
    # date-gated work for the year. Or make it unbounded ⇒ the tick spins.
    log: list = []
    registry = [_spec("dated", _counter_pass(log, "dated", raises=True),
                      klass=reg.KLASS_MUST_COMPLETE, max_same_day_retries=2)]
    out = reg.run_ledger(NOW_ORDINARY, registry=registry)

    assert log == ["dated"] * 3          # 1 attempt + 2 retries
    assert out["statuses"]["dated"] == reg.STATUS_ERROR
    row = _rows(eng)["dated"]
    assert row.attempt == 3
    assert "exploded" in row.error_text


def test_must_complete_today_stops_retrying_once_it_succeeds(eng):
    # SABOTAGE: retry unconditionally instead of only on exception ⇒ the
    # Aug-25 fan-out sends three times (the frequency cap is the only thing
    # left standing between that and three real pushes).
    log: list = []
    state = {"n": 0}

    def flaky(ctx):
        state["n"] += 1
        log.append(ctx.attempt)
        if state["n"] == 1:
            raise RuntimeError("transient")
        return {"items": 1}

    out = reg.run_ledger(NOW_ORDINARY, registry=[
        _spec("dated", flaky, klass=reg.KLASS_MUST_COMPLETE)])
    assert log == [1, 2]
    assert out["statuses"]["dated"] == reg.STATUS_OK
    assert _rows(eng)["dated"].attempt == 2


def test_overrunning_pass_is_recorded_timeout_not_killed(eng):
    # SABOTAGE: implement preemption (LLD §2.1 forbids it) ⇒ the body would
    # not finish. Or drop the budget comparison ⇒ a pass that blew its budget
    # reads as green.
    log: list = []
    out = reg.run_ledger(NOW_ORDINARY, registry=[
        _spec("a", _counter_pass(log, "a", sleep=0.05), budget_s=0.001)])
    assert log == ["a"]                              # it completed
    assert out["statuses"]["a"] == reg.STATUS_TIMEOUT
    assert _rows(eng)["a"].status == reg.STATUS_TIMEOUT


# ---------------------------------------------------------------------------
# Push-kind registration assert (HLD §2.1)
# ---------------------------------------------------------------------------

def test_registration_rejects_a_push_kind_with_no_cap(monkeypatch):
    # SABOTAGE: drop `_validate_push_kinds` from `register` ⇒ a future pass
    # can dispatch an uncapped kind, and the ledger's own re-run mechanisms
    # (double-POST claim, stale reclaim, same-day retry) turn into duplicate
    # pushes to real users.
    monkeypatch.setattr(reg, "REGISTRY", [])
    reg.configure_push_kinds(freq_capped=server._NOTIF_FREQ_CAPS,
                             dedup_keyed=server._NOTIF_DEDUP_CAPS)
    with pytest.raises(ValueError, match="no frequency cap"):
        reg.register(_spec("bad", lambda ctx: {},
                           push_kinds=("brand_new_uncapped_kind",)))


def test_registration_accepts_freq_capped_and_dedup_keyed_kinds(monkeypatch):
    # SABOTAGE: validate only against _NOTIF_FREQ_CAPS ⇒ the replenish pass
    # (deck_replenished is dedup-keyed, not freq-capped) fails to register
    # and the whole server import dies.
    monkeypatch.setattr(reg, "REGISTRY", [])
    reg.configure_push_kinds(freq_capped=server._NOTIF_FREQ_CAPS,
                             dedup_keyed=server._NOTIF_DEDUP_CAPS)
    reg.register(_spec("p1", lambda ctx: {}, push_kinds=("season_start",)))
    reg.register(_spec("p2", lambda ctx: {}, push_kinds=("deck_replenished",)))
    # Explicit per-pass whitelist: the documented escape hatch.
    reg.register(_spec("p3", lambda ctx: {}, push_kinds=("odd_kind",),
                       dedup_key_kinds=("odd_kind",)))
    assert [s.name for s in reg.REGISTRY] == ["p1", "p2", "p3"]


def test_real_registry_declares_every_push_kind_the_tick_sends(monkeypatch):
    # SABOTAGE: add a `_send_typed_push` kind to a pass body without adding it
    # to that pass's push_kinds ⇒ the registration assert can't see it. This
    # pins the four kinds the tick actually dispatches today.
    declared = {k for s in server.DAILY_TICK_REGISTRY for k in s.push_kinds}
    assert declared == {"season_start", "finish_ranking", "winback_dormant",
                        "winback_matches", "deck_replenished"}
    for kind in declared:
        assert (kind in server._NOTIF_FREQ_CAPS
                or kind in server._NOTIF_DEDUP_CAPS), kind


# ---------------------------------------------------------------------------
# Retention wiring
# ---------------------------------------------------------------------------

def test_prune_cron_pass_runs_drops_rows_past_retention(eng):
    # SABOTAGE: never call `prune_cron_pass_runs` from `_cleanup_loop` (the
    # LLD's assumed retention endpoint does not exist) ⇒ the ledger grows
    # without bound.
    old = (datetime.now(timezone.utc) - timedelta(days=200)).strftime("%Y-%m-%d")
    new = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with eng.begin() as conn:
        for d in (old, new):
            conn.execute(insert(cron_pass_runs_table).values(
                pass_name="a", run_date=d, status="ok",
                started_at=d + "T00:00:00+00:00", attempt=1))
    assert db_module.prune_cron_pass_runs(90) == 1
    with eng.connect() as conn:
        remaining = [r.run_date for r in
                     conn.execute(select(cron_pass_runs_table)).fetchall()]
    assert remaining == [new]
    import inspect
    src = inspect.getsource(server._cleanup_loop)
    assert "prune_cron_pass_runs()" in src
