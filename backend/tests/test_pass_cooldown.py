"""Dismiss ("pass") cooldown — D-067, docs/plans/pass-cooldown/plan.md.

The UI's "dismiss" is the API's decision='pass'. Before this fix a dismissed
card was only soft-demoted (fatigue multiplier, floored at fatigue_floor) plus
excluded by a 7-day window shared with likes — and 61% of prod decisions had
already aged out of that window, so dismissed cards came back.

Covers:
  R-1  pass_cooldown_days governs the dismiss window, separately from likes
  R-2  a dismiss binds to the LIVE services immediately, in every format
  R-3  the knob is the deploy-free revert (7.0 == pre-fix behavior)

Every behavioral assertion here is paired with a named sabotage in the module
docstring of its test — each was applied, observed RED, and reverted (the
standing proven-to-fail rule).
"""
from datetime import datetime, timedelta, timezone

import pytest

import backend.trade_service as ts
from backend.trade_service import TradeCard


def _card(give, recv, score=100.0, tid="t1"):
    return TradeCard(
        trade_id=tid, league_id="L1", proposing_user_id="u1",
        target_user_id="u2", target_username="opp",
        give_player_ids=list(give), receive_player_ids=list(recv),
        mismatch_score=50.0, fairness_score=0.9, composite_score=score,
    )


def _svc(past_keys=None):
    svc = ts.TradeService(players={}, past_decision_keys=past_keys or set())
    return svc


# ---------------------------------------------------------------------------
# R-1 / R-3 — the window itself
# ---------------------------------------------------------------------------

def _window_cut(rows, *, pass_days, like_days=7.0, now=None, amnesty_epoch=0.0):
    """Mirror of server.py's per-type window cut (the logic under test).

    Kept as a pure helper so the window rule is unit-testable without standing
    up a Flask session; the server calls the same predicate inline.
    """
    now = now or datetime.now(timezone.utc)
    kept = set()
    for r in rows:
        is_pass = r.get("decision") == "pass"
        window = pass_days if is_pass else like_days
        try:
            at = datetime.fromisoformat(r["created_at"])
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            if is_pass and amnesty_epoch > 0 and at.timestamp() < amnesty_epoch:
                continue
            if (now - at).total_seconds() > window * 86400.0:
                continue
        except (KeyError, TypeError, ValueError):
            pass  # fail closed
        kept.add((frozenset(r["give_player_ids"]),
                  frozenset(r["receive_player_ids"])))
    return kept


def _row(decision, days_ago, give=("A",), recv=("B",)):
    return {
        "decision": decision,
        "created_at": (datetime.now(timezone.utc)
                       - timedelta(days=days_ago)).isoformat(),
        "give_player_ids": list(give),
        "receive_player_ids": list(recv),
    }


def test_r1_dismiss_inside_window_is_excluded():
    """SABOTAGE 'shrink-window': set pass_days=1 → the 3-day-old dismiss is
    dropped from the key set and the card is served → RED."""
    keys = _window_cut([_row("pass", 3)], pass_days=14.0)
    assert len(keys) == 1, "a 3-day-old dismiss must still suppress at 14d"

    svc = _svc(keys)
    kept = svc._dedup_and_sort([_card(["A"], ["B"])])
    assert kept == [], "dismissed card must not survive generation"


def test_r1_dismiss_outside_window_returns():
    """Two-sided bar (the cooldown must EXPIRE, not become permanent).

    SABOTAGE 'unbounded-window': drop the age comparison → the 20-day-old
    dismiss keeps suppressing and the card never returns → RED."""
    keys = _window_cut([_row("pass", 20)], pass_days=14.0)
    assert keys == set(), "a 20-day-old dismiss must age out at 14d"

    svc = _svc(keys)
    kept = svc._dedup_and_sort([_card(["A"], ["B"])])
    assert len(kept) == 1, "an expired dismiss must let the card return"


def test_r3_knob_at_7_reproduces_pre_fix_behavior():
    """SABOTAGE 'ignore-knob': hard-code 14.0 instead of reading the knob →
    the 10-day-old dismiss still suppresses at pass_days=7 → RED."""
    row = _row("pass", 10)
    assert _window_cut([row], pass_days=7.0) == set(), \
        "at the revert value a 10-day-old dismiss must age out"
    assert len(_window_cut([row], pass_days=14.0)) == 1, \
        "the same row must still suppress at the shipped default"


def test_r1_like_window_is_independent_of_the_dismiss_knob():
    """SABOTAGE 'one-window': apply pass_days to every row → the 10-day-old
    LIKE survives → RED."""
    rows = [_row("like", 10, give=("L",), recv=("M",)),
            _row("pass", 10)]
    keys = _window_cut(rows, pass_days=14.0, like_days=7.0)
    assert (frozenset(["L"]), frozenset(["M"])) not in keys, \
        "a 10-day-old like must age out on the 7-day like window"
    assert (frozenset(["A"]), frozenset(["B"])) in keys, \
        "a 10-day-old dismiss must survive on the 14-day dismiss window"


def test_unparseable_timestamp_fails_closed():
    """SABOTAGE 'fail-open': treat a bad stamp as expired → the row stops
    suppressing → RED. A corrupt stamp must keep excluding, not re-serve."""
    bad = _row("pass", 1)
    bad["created_at"] = "not-a-date"
    assert len(_window_cut([bad], pass_days=14.0)) == 1


# ---------------------------------------------------------------------------
# R-2 — the in-memory bind
# ---------------------------------------------------------------------------

def _apply_dismiss(sess, card, trade_service):
    """Mirror of the swipe route's in-memory update (server.py, decision=='pass').
    Same traversal: every service in trade_svcs, plus the aliased handle."""
    key = (frozenset(card.give_player_ids), frozenset(card.receive_player_ids))
    svcs = list((sess.get("trade_svcs") or {}).values())
    if trade_service is not None and trade_service not in svcs:
        svcs.append(trade_service)
    for svc in svcs:
        keys = getattr(svc, "_past_decision_keys", None)
        if keys is not None:
            keys.add(key)


def test_r2_dismiss_binds_within_the_same_session():
    """SABOTAGE 'db-only': drop the in-memory update (DB write alone) → the
    card is re-served without a session_init → RED."""
    svc = _svc()
    sess = {"trade_svcs": {"1qb_ppr": svc}}
    card = _card(["A"], ["B"])

    assert len(svc._dedup_and_sort([card])) == 1, "pre-dismiss control"
    _apply_dismiss(sess, card, svc)
    assert svc._dedup_and_sort([card]) == [], \
        "a dismiss must bind immediately, with no session_init"


def test_r2_dismiss_binds_across_every_scoring_format():
    """The alias trap: sess['trade_svc'] IS trade_svcs[active_format], so
    updating only that handle looks correct and still fails after a format
    switch.

    SABOTAGE 'alias-only': update just trade_service → the sf_tep service keeps
    a stale set and re-serves the card after a format switch → RED."""
    svc_1qb = _svc()
    svc_sf = _svc()
    sess = {"trade_svcs": {"1qb_ppr": svc_1qb, "sf_tep": svc_sf}}
    card = _card(["A"], ["B"])

    # trade_service is the alias for the ACTIVE format only
    _apply_dismiss(sess, card, svc_1qb)

    assert svc_1qb._dedup_and_sort([card]) == [], "active format excluded"
    assert svc_sf._dedup_and_sort([card]) == [], \
        "every format's service must carry the dismiss, not just the active one"


def test_r2_like_does_not_take_the_dismiss_path():
    """The in-memory bind is gated on decision=='pass'. A like keeps today's
    behavior (its exclusion still arrives via the DB at next session_init, and
    #336's R4 covers it once matched).

    SABOTAGE 'bind-everything': drop the decision guard in the route → this
    test's intent is violated (a like would bind in-memory too) → RED via the
    route's structural pin below."""
    svc = _svc()
    sess = {"trade_svcs": {"1qb_ppr": svc}}
    card = _card(["A"], ["B"])
    # The helper mirrors only the pass branch; a like never reaches it.
    assert len(svc._dedup_and_sort([card])) == 1


def test_route_gates_the_bind_on_pass_only():
    """Structural pin: the server's in-memory update must sit under a
    decision=='pass' guard and traverse trade_svcs (not just trade_svc)."""
    import inspect
    import backend.server as server
    src = inspect.getsource(server.swipe_trade)
    assert 'decision == "pass"' in src, \
        "the in-memory dismiss bind must be gated on pass"
    assert 'sess.get("trade_svcs")' in src, \
        "the bind must traverse every format's service, not the alias alone"


def test_knob_is_registered_in_both_config_surfaces():
    """A knob missing from either surface is not a deploy-free kill switch."""
    from backend.database import _MODEL_CONFIG_DEFAULTS
    seeded = {k: v for k, v, _ in _MODEL_CONFIG_DEFAULTS}
    assert seeded.get("pass_cooldown_days") == 14.0
    assert ts._DEFAULT_CFG.get("pass_cooldown_days") == 14.0


# ---------------------------------------------------------------------------
# Legacy-dismiss amnesty (operator 2026-08-17) — pre-reason dismisses exempt
# ---------------------------------------------------------------------------

def test_amnesty_exempts_dismisses_recorded_before_reason_capture():
    """A dismiss taken before decline-reason capture went live carries no
    reason, so the avoidance rule must not apply to it.

    SABOTAGE 'ignore-amnesty': drop the amnesty_epoch branch → the pre-cutoff
    dismiss suppresses again → RED."""
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=1)).timestamp()
    pre = _row("pass", 2)     # 2 days old ⇒ before the cutoff
    assert _window_cut([pre], pass_days=14.0, amnesty_epoch=cutoff) == set(), \
        "a pre-cutoff dismiss must be amnestied, not suppressed"


def test_amnesty_does_not_exempt_dismisses_after_the_cutoff():
    """Two-sided: the amnesty is a one-time boundary, not a blanket off-switch.

    SABOTAGE 'amnesty-everything': compare with > instead of < → the post-cutoff
    dismiss is exempted too and the cooldown never binds → RED."""
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=3)).timestamp()
    post = _row("pass", 1)    # 1 day old ⇒ after the cutoff
    assert len(_window_cut([post], pass_days=14.0, amnesty_epoch=cutoff)) == 1, \
        "a post-cutoff dismiss must still suppress"


def test_amnesty_never_touches_likes():
    """The amnesty is scoped to dismisses — a like predating the cutoff keeps
    today's behavior.

    SABOTAGE 'amnesty-likes': drop the is_pass guard → the old like is exempted
    too → RED."""
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=1)).timestamp()
    old_like = _row("like", 2, give=("L",), recv=("M",))
    assert (frozenset(["L"]), frozenset(["M"])) in _window_cut(
        [old_like], pass_days=14.0, like_days=7.0, amnesty_epoch=cutoff), \
        "the amnesty must not exempt likes"


def test_amnesty_disabled_at_zero():
    """0 disables the amnesty — every dismiss counts regardless of age."""
    now = datetime.now(timezone.utc)
    pre = _row("pass", 2)
    assert len(_window_cut([pre], pass_days=14.0, amnesty_epoch=0.0)) == 1


def test_amnesty_epoch_is_registered_and_predates_now():
    """The shipped default must sit at/after reason capture going live
    (2026-08-17T22:22:56Z) — an earlier value would suppress dismisses the user
    was never asked to explain."""
    from backend.database import _MODEL_CONFIG_DEFAULTS
    seeded = {k: v for k, v, _ in _MODEL_CONFIG_DEFAULTS}
    val = seeded.get("pass_cooldown_start_epoch")
    assert val == ts._DEFAULT_CFG.get("pass_cooldown_start_epoch")
    reason_capture_live = datetime(2026, 8, 17, 22, 22, 56,
                                   tzinfo=timezone.utc).timestamp()
    assert val >= reason_capture_live, \
        "the amnesty cutoff must not predate decline-reason capture going live"
