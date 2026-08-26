"""Counterparty breaker — evaluation layer (`backend/trade_breaker.py`).

Spec: docs/plans/counterparty-breaker/LLD.md §7.1/§7.2 (the test names ARE the
spec) + PRD §5.4 (the tone rules that bind `compose_narration`'s eligibility
gating).

FIXTURE REALISM — the #366 lesson, made a precondition (LLD §7.0).
`_POS_TIER_MIN_POOL = 40` (trade_service.py:2086): below 40 ranked players at
a position, `analyze_roster_strengths` silently falls back to ABSOLUTE cuts and
a green depth-class test proves the fallback mode, not production behavior. So
the pool below carries 50 ranked players per `_POS_TIER_CUTS` position and
every depth/tier predicate test asserts `tier_basis == "positional"` in its
preconditions — a fixture shrink that flips the mode fails loudly instead of
quietly testing the wrong bands.

The LLD homes this fixture in `backend/tests/fixtures/breaker_league.py`; it
lives inline here because this wave owns exactly two files. Lift it out when a
second consumer appears.
"""

import json
import math

import pytest

import backend.feature_flags as ff
import backend.trade_breaker as tb
import backend.trade_narrative as tn
import backend.trade_service as ts
from backend.database import PASS_REASON_LAYER2
from backend.trade_service import League, LeagueMember


# ───────────────────────────────────────────────────────────────────────────
# Fixture — a 12-team Sleeper league over a production-sized ranked pool
# ───────────────────────────────────────────────────────────────────────────

_POOL_N = 50                      # > _POS_TIER_MIN_POOL (40) at every position
_CORE = ("QB", "RB", "WR", "TE")


class _Player:
    def __init__(self, pid, position, age=25, team="TST", search_rank=None):
        self.id = pid
        self.name = f"Player {pid}"
        self.position = position
        self.team = team
        self.age = age
        self.search_rank = search_rank
        self.ktc_value = None
        self.pick_value = None
        self.years_experience = 3


class _Card:
    """The three attributes the breaker reads off a served card, plus the
    optional M3 `fit_diag` stamp it passes through (D-3)."""

    def __init__(self, trade_id, target_user_id, give, receive, fit_diag=None):
        self.trade_id = trade_id
        self.target_user_id = target_user_id
        self.give_player_ids = list(give)
        self.receive_player_ids = list(receive)
        if fit_diag is not None:
            self.fit_diag = fit_diag


def _pid(pos, i):
    return f"{pos}{i:02d}"


#: Ages are set per id so a roster's window is a property of the roster, not
#: of the pool. Everything unlisted is 25 (neither vet nor youth at the
#: shipped vet_age/youth_age thresholds).
_AGES = {}
for _i in range(1, _POOL_N + 1):
    for _p in _CORE:
        if 3 <= _i <= 8 or 45 <= _i <= 47:
            _AGES[_pid(_p, _i)] = 22          # rebuilder block
        elif 10 <= _i <= 15 or 40 <= _i <= 41:
            _AGES[_pid(_p, _i)] = 31          # contender block

_PICK_IDS = ("PICK_2027_1", "PICK_2027_2", "PICK_2028_1")


def _build_pool():
    players, seed = {}, {}
    for pos in _CORE:
        for i in range(1, _POOL_N + 1):
            pid = _pid(pos, i)
            players[pid] = _Player(pid, pos, age=_AGES.get(pid, 25),
                                   search_rank=i)
            seed[pid] = 1750.0 - 8.0 * i
    for j, pid in enumerate(_PICK_IDS):
        # Owned-pick pseudo-players: position == "PICK" — the ONLY pick shape
        # at the trade-job seam (LLD §3.10) and the shape that hits
        # ts._now_lean's PICK branch.
        players[pid] = _Player(pid, "PICK", age=None, team="PICK")
        seed[pid] = 1560.0 - 20.0 * j
    # One K asset with no seed price — the G-026 corruption shape.
    players["K01"] = _Player("K01", "K", age=28, search_rank=None)
    return players, seed


_ROSTERS = {
    "opp_rebuilder": [_pid("QB", 3), _pid("RB", 3), _pid("RB", 4),
                      _pid("RB", 45), _pid("RB", 46), _pid("RB", 47),
                      _pid("WR", 3), _pid("WR", 4), _pid("WR", 7),
                      _pid("WR", 8), _pid("WR", 45), _pid("WR", 46),
                      _pid("WR", 47), _pid("TE", 3)],
    "opp_contender": [_pid("QB", 10), _pid("RB", 10), _pid("RB", 11),
                      _pid("RB", 40), _pid("RB", 41), _pid("WR", 10),
                      _pid("WR", 11), _pid("TE", 10)],
    "opp_unboarded": [_pid("QB", 17), _pid("RB", 17), _pid("RB", 18),
                      _pid("WR", 17), _pid("WR", 18), _pid("TE", 17)],
    "opp_thin_te":   [_pid("QB", 24), _pid("RB", 24), _pid("RB", 25),
                      _pid("WR", 24), _pid("WR", 25), _pid("TE", 24)],
}
_VIEWER_ROSTER = [_pid("QB", 31), _pid("RB", 31), _pid("RB", 32),
                  _pid("WR", 31), _pid("WR", 32), _pid("TE", 31)]
_VIEWER_ID = "viewer"

#: Declared outlooks pinned per partner so predicate tests exercise ONE
#: variable at a time; the legacy/inference path has its own test.
_DECLARED = {"opp_rebuilder": "rebuilder", "opp_contender": "contender",
             "opp_unboarded": "not_sure", "opp_thin_te": "contender"}


def _boards(seed):
    """Rebuilder: an authentic board (every row diverges ≥ the default 25).
    Contender: a CLONE with exactly 3 divergent rows — the F-3 shape that must
    fall back to consensus optics. Unboarded: nothing."""
    authentic = {pid: elo + 60.0 for pid, elo in seed.items()}
    clone = dict(seed)
    for pid in (_pid("WR", 10), _pid("RB", 10), _pid("QB", 10)):
        clone[pid] = seed[pid] + 60.0
    return authentic, clone


def _league(players, seed, *, platform="sleeper", n_members=11,
            rosters=None, boards=True):
    authentic, clone = _boards(seed)
    rosters = rosters or _ROSTERS
    members = [
        LeagueMember(user_id="opp_rebuilder", username="Reb",
                     roster=list(rosters["opp_rebuilder"]),
                     elo_ratings=authentic if boards else {},
                     has_rankings=bool(boards)),
        LeagueMember(user_id="opp_contender", username="Con",
                     roster=list(rosters["opp_contender"]),
                     elo_ratings=clone if boards else {},
                     has_rankings=bool(boards)),
        LeagueMember(user_id="opp_unboarded", username="Unb",
                     roster=list(rosters["opp_unboarded"]),
                     elo_ratings={}, has_rankings=False),
        LeagueMember(user_id="opp_thin_te", username="Thin",
                     roster=list(rosters["opp_thin_te"]),
                     elo_ratings={}, has_rankings=False),
    ]
    # Pad to the envelope's 12-team assumption (members exclude the viewer).
    for k in range(len(members), n_members):
        members.append(LeagueMember(user_id=f"filler{k}", username=f"F{k}",
                                    roster=[], elo_ratings={},
                                    has_rankings=False))
    return League(league_id="L_BRK", name="Breaker", platform=platform,
                  members=members[:n_members])


def _deck():
    """~8 served cards across 3 partners (LLD §7.0)."""
    return [
        # 0 — rebuilder receives a 31-y/o RB (aging incoming ⇒ fit_outlook).
        _Card("t0", "opp_rebuilder", [_pid("RB", 10)], [_pid("WR", 45)]),
        # 1 — rebuilder receives a surplus-position WR (fit_duplicate).
        _Card("t1", "opp_rebuilder", [_pid("WR", 12)], [_pid("WR", 46)]),
        # 2 — rebuilder receives another aging RB (repetition candidate).
        _Card("t2", "opp_rebuilder", [_pid("RB", 11)], [_pid("WR", 47)]),
        # 3 — contender sends its only startable TE-equivalent depth.
        _Card("t3", "opp_contender", [_pid("QB", 45)], [_pid("RB", 40)]),
        # 4 — contender receives picks (future capital into a win-now window).
        _Card("t4", "opp_contender", list(_PICK_IDS[:2]), [_pid("WR", 11)]),
        # 5 — thin-TE partner sends its only TE.
        _Card("t5", "opp_thin_te", [_pid("WR", 33)], [_pid("TE", 24)]),
        # 6 — 1-for-2 into the contender's seat (roster crunch).
        _Card("t6", "opp_contender", [_pid("WR", 33), _pid("WR", 34)],
              [_pid("RB", 40)]),
        # 7 — likes-you-style injected card: no fit_diag ⇒ `them` null.
        _Card("t7", "opp_unboarded", [_pid("RB", 17)], [_pid("WR", 35)]),
    ]


def _kwargs(players, seed, league, **over):
    base = dict(
        league=league, players=players, seed_elo=seed,
        scoring_format="1qb_ppr", league_id="L_BRK",
        viewer_user_id=_VIEWER_ID, viewer_roster=list(_VIEWER_ROSTER),
        viewer_elo={}, viewer_outlook="not_sure",
        declared_outlooks=dict(_DECLARED), pick_shares={},
    )
    base.update(over)
    return base


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """Hermetic flags + knobs. `trade.position_tiers` ON is what puts the
    depth predicates on positional bands (the §7.0 precondition)."""
    flags = dict(ff.DEFAULT_FLAGS)
    flags["trade.position_tiers"] = True
    flags["trade.crown_asset"] = True
    monkeypatch.setattr(ff, "_flags_cache", flags, raising=False)
    saved = dict(ts._cfg)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    # Wall clock is not an input (NFR-4), but the production 250 ms budget
    # makes it one: past the 0.6× checkpoint pass 2 stamps as "budget", so a
    # loaded runner flakes any payload assertion (CI 2026-08-23,
    # test_stud_tax_pinned_market). Budget rungs are tested via _snap_with /
    # fake clocks only — the real clock never gets to pick the rung here.
    ts._cfg["breaker_ms_budget"] = 10 ** 9
    yield
    ts._cfg.clear()
    ts._cfg.update(saved)


@pytest.fixture
def world():
    players, seed = _build_pool()
    league = _league(players, seed)
    return players, seed, league


def _stamp(players, seed, league, cards=None, **over):
    cards = _deck() if cards is None else cards
    job = tb.stamp_breaker(cards, **_kwargs(players, seed, league, **over))
    return cards, job


def _ctx_and_pctx(players, seed, league, uid, *, prefs=None,
                  prefs_available=True, scoring_format="1qb_ppr"):
    """Build one `_EvalCtx` + `PartnerContext` for direct predicate tests."""
    cfg = tb._knob_snapshot()
    ctx = tb._EvalCtx(cfg=cfg, players=players, seed_elo=seed,
                      scoring_format=scoring_format, league=league)
    member = {m.user_id: m for m in league.members}[uid]
    pctx = tb._build_context(
        user_id=uid, username=member.username, roster=member.roster,
        board_raw=member.elo_ratings, has_rankings=member.has_rankings,
        declared=_DECLARED.get(uid), pick_share=0.0, prefs=prefs or {},
        prefs_available=prefs_available, ctx=ctx)
    return ctx, pctx


def _view(card):
    """The partner-seat view (LLD §3.1 — give/receive swapped)."""
    return tb._CardView(give_ids=list(card.receive_player_ids),
                        recv_ids=list(card.give_player_ids))


def _strip_ms(payload):
    """`ms` is wall-clock diagnostics, never an input (NFR-4) — the only key
    a deterministic re-run may legitimately move."""
    if not isinstance(payload, dict):
        return payload
    out = {k: v for k, v in payload.items() if k != "ms"}
    return out


# ───────────────────────────────────────────────────────────────────────────
# Determinism, vocabulary, vector shape
# ───────────────────────────────────────────────────────────────────────────

def test_breaker_deterministic(world):
    players, seed, league = world
    a, _ = _stamp(players, seed, league)
    b, _ = _stamp(players, seed, league)
    for ca, cb in zip(a, b):
        assert _strip_ms(ca.breaker) == _strip_ms(cb.breaker)
        assert _strip_ms(ca.breaker_shadow) == _strip_ms(cb.breaker_shadow)
        assert isinstance(ca.breaker["ms"], float)
        assert round(ca.breaker["ms"], 1) == ca.breaker["ms"]


def test_severity_rounding_3dp(world):
    players, seed, league = world
    cards, _ = _stamp(players, seed, league)
    for card in cards:
        for entry in card.breaker["objections"]:
            sev = entry["severity"]
            if sev is None:
                continue
            assert isinstance(sev, float)
            assert round(sev, 3) == sev
            assert 0.0 <= sev <= 1.0


def test_breaker_vocabulary_closure(world):
    players, seed, league = world
    coded = {c for codes in PASS_REASON_LAYER2.values() for c in codes}
    coded.discard("other_text")
    allowed = coded | {"roster_crunch"}

    assert set(tb.ALL_CLASSES) <= allowed
    assert "other_text" not in tb.ALL_CLASSES
    assert "shape_aversion" not in tb.ALL_CLASSES          # producer=negmem
    assert set(tb.TIEBREAK_PRIORITY) == set(tb.ALL_CLASSES)

    cards, _ = _stamp(players, seed, league)
    blob = json.dumps([c.breaker for c in cards])
    assert "other_text" not in blob
    assert "shape_aversion" not in blob
    for card in cards:
        for entry in card.breaker["objections"]:
            code = entry["code"]
            assert code in allowed
            # Evidence keys are the whitelist's mechanical form (LLD §2.4):
            # an unlisted key is how a private-state leak sneaks past.
            assert set(entry["evidence"]) <= tb.EVIDENCE_KEYS[code]
        top = card.breaker["top"]
        if top:
            assert set(top["evidence"]) <= tb.EVIDENCE_KEYS[top["code"]]


def test_objections_vector_complete(world):
    players, seed, league = world
    cards, _ = _stamp(players, seed, league)
    for card in cards:
        objs = card.breaker["objections"]
        assert [o["code"] for o in objs] == list(tb.ALL_CLASSES)
        for o in objs:
            assert ("severity" in o) and ("evidence" in o)
            if o["severity"] is None:
                assert o["skipped"] in ("format_gap", "budget",
                                        "budget_exhausted", "not_applicable",
                                        "partner_snapshot", "predicate_error")


def test_provenance_markers(world):
    players, seed, league = world
    cards, _ = _stamp(players, seed, league)
    for card in cards:
        bk = card.breaker
        assert bk["ver"] == tb.BREAKER_VERSION
        assert bk["outlook_src"] in ("declared", "legacy", "composite")
        assert bk["board_auth"] in ("board", "board_suspect", "consensus")
        assert bk["value_mode"] == "market"
        assert bk["identity_src"] == "owner_id"
        assert bk["format_gap"] is None or isinstance(bk["format_gap"], list)
        assert set(bk["outlook_pair"]) == {"declared", "inferred", "score"}
    by_id = {c.trade_id: c for c in cards}
    assert by_id["t0"].breaker["board_auth"] == "board"          # authentic
    assert by_id["t3"].breaker["board_auth"] == "board_suspect"  # clone
    assert by_id["t7"].breaker["board_auth"] == "consensus"      # unboarded


# ───────────────────────────────────────────────────────────────────────────
# Per-class predicates
# ───────────────────────────────────────────────────────────────────────────

def test_fit_outlook_predicate(world):
    players, seed, league = world
    ctx, pctx = _ctx_and_pctx(players, seed, league, "opp_rebuilder")
    # A rebuilder RECEIVING a 31-y/o RB — aging production into a young roster.
    card = _Card("x", "opp_rebuilder", [_pid("RB", 10)], [_pid("WR", 45)])
    out = tb._obj_fit_outlook(_view(card), pctx, ctx)
    lean = ts._now_lean("RB", 31)
    expect = min(1.0, max(0.0, lean - 0.05) / 0.35)
    assert out["severity"] == round(expect, 3)
    assert out["severity"] > 0.0
    assert out["evidence"]["outlook"] == "rebuilder"
    assert out["evidence"]["asset"] == _pid("RB", 10)
    assert out["evidence"]["age"] == 31 and out["evidence"]["pos"] == "RB"

    # A contender receiving PICKS — picks stay IN the mean at −0.25.
    _c2, pc2 = _ctx_and_pctx(players, seed, league, "opp_contender")
    pick_card = _Card("y", "opp_contender", list(_PICK_IDS[:2]),
                      [_pid("WR", 11)])
    out2 = tb._obj_fit_outlook(_view(pick_card), pc2, ctx)
    assert out2["evidence"]["lean"] == -0.25
    assert out2["severity"] == round(min(1.0, (0.25 - 0.05) / 0.35), 3)
    assert out2["evidence"]["asset"] is None          # all-pick incoming
    assert out2["evidence"]["age"] is None and out2["evidence"]["pos"] is None

    # not_sure ⇒ no window claim without a window.
    _c3, pc3 = _ctx_and_pctx(players, seed, league, "opp_unboarded")
    out3 = tb._obj_fit_outlook(_view(card), pc3, ctx)
    assert out3["severity"] == 0.0

    # Legacy haircut: same inputs, `legacy` source ⇒ knob multiplies severity.
    pctx.outlook_src = "legacy"
    hair = tb._obj_fit_outlook(_view(card), pctx, ctx)
    assert hair["severity"] == round(expect * 0.70, 3)
    ctx.cfg["breaker_outlook_haircut_legacy"] = 1.0
    assert tb._obj_fit_outlook(_view(card), pctx, ctx)["severity"] == \
        round(expect, 3)


def test_fit_new_weakness_predicate(world):
    players, seed, league = world
    ctx, thin = _ctx_and_pctx(players, seed, league, "opp_thin_te")
    assert tb._tier_basis(thin.profile, "TE") == "positional"   # §7.0 pin

    card = _Card("x", "opp_thin_te", [_pid("WR", 33)], [_pid("TE", 24)])
    out = tb._obj_fit_new_weakness(_view(card), thin, ctx)
    assert out["severity"] == 1.0
    ev = out["evidence"]
    assert ev["pos"] == "TE" and ev["before"] == 1 and ev["after"] == 0
    assert ev["need"] == 1 and ev["asset"] == _pid("TE", 24)
    assert ev["tier_basis"] == "positional"

    # Slack-1: the contender has 4 RBs and needs 2.
    _c2, con = _ctx_and_pctx(players, seed, league, "opp_contender")
    assert tb._tier_basis(con.profile, "RB") == "positional"
    rb_card = _Card("y", "opp_contender", [_pid("QB", 45)], [_pid("RB", 40)])
    out2 = tb._obj_fit_new_weakness(_view(rb_card), con, ctx)
    assert out2["severity"] == 0.30
    assert out2["evidence"]["before"] == 4 and out2["evidence"]["after"] == 3

    # Receiving can't open a hole — the partner's RECEIVE side never fires it.
    recv_only = tb._CardView(give_ids=[], recv_ids=[_pid("RB", 40)])
    assert tb._obj_fit_new_weakness(recv_only, con, ctx)["skipped"] == \
        "not_applicable"


def test_fit_duplicate_predicate(world):
    players, seed, league = world
    ctx, reb = _ctx_and_pctx(players, seed, league, "opp_rebuilder")
    assert tb._tier_basis(reb.profile, "WR") == "positional"    # §7.0 pin
    assert "WR" in reb.profile["position_surplus"]

    card = _Card("x", "opp_rebuilder", [_pid("WR", 12)], [_pid("WR", 46)])
    out = tb._obj_fit_duplicate(_view(card), reb, ctx)
    bench_n = reb.profile["tier_depth"]["WR"]["bench"]
    assert out["severity"] == round(
        min(1.0, 0.40 + 0.40 * 1.0 + 0.20 * min(bench_n, 4) / 4.0), 3)
    ev = out["evidence"]
    assert ev["pos"] == "WR" and ev["bench_n"] == bench_n
    assert ev["value_share"] == 1.0 and ev["asset"] == _pid("WR", 12)
    assert ev["tier_basis"] == "positional"

    # Non-surplus incoming position ⇒ 0.0 with the mandatory keys present.
    qb_card = _Card("y", "opp_rebuilder", [_pid("QB", 12)], [_pid("WR", 46)])
    out2 = tb._obj_fit_duplicate(_view(qb_card), reb, ctx)
    assert out2["severity"] == 0.0
    assert set(out2["evidence"]) == tb.EVIDENCE_KEYS["fit_duplicate"]


def test_value_giving_one_code_path(world):
    players, seed, league = world
    ctx, reb = _ctx_and_pctx(players, seed, league, "opp_rebuilder")
    _c2, con = _ctx_and_pctx(players, seed, league, "opp_contender")
    _c3, unb = _ctx_and_pctx(players, seed, league, "opp_unboarded")

    assert reb.board_auth == "board"
    assert con.board_auth == "board_suspect"      # clone ⇒ consensus optics
    assert unb.board_auth == "consensus"

    card = _Card("x", "opp_rebuilder", [_pid("RB", 10)], [_pid("WR", 45)])
    b = tb._obj_value_giving(_view(card), reb, ctx)
    c = tb._obj_value_giving(_view(card), con, ctx)
    u = tb._obj_value_giving(_view(card), unb, ctx)
    assert b["evidence"]["basis"] == "board"
    assert c["evidence"]["basis"] == "consensus"
    assert u["evidence"]["basis"] == "consensus"
    # ONE code path (D-3): the clone-board and unboarded partners are the same
    # computation on the same accessor, so their margins are identical.
    assert c["evidence"]["margin"] == u["evidence"]["margin"]
    assert ctx.val_for(con) == ctx.cval and ctx.val_for(unb) == ctx.cval
    assert ctx.val_for(reb) != ctx.cval
    for out in (b, c, u):
        assert out["evidence"]["n_give"] == 1 and out["evidence"]["n_recv"] == 1

    # Severity is the negative their-seat margin over breaker_value_scale.
    lop = _Card("y", "opp_unboarded", [_pid("WR", 45)], [_pid("WR", 1)])
    out = tb._obj_value_giving(_view(lop), unb, ctx)
    assert out["severity"] == round(
        min(1.0, max(0.0, -out["evidence"]["margin"]) / 400.0), 3)
    assert out["severity"] > 0.0

    # The basis-dependent floor split (D-7) is read by the SAME helper.
    assert tb._class_floor("value_giving", c, ctx.cfg) == 0.75
    assert tb._class_floor("value_giving", b, ctx.cfg) == 0.30


def test_other_player_keep_predicate(world):
    players, seed, league = world
    prefs = {"untouchable": [_pid("WR", 10)],
             "target": [_pid("RB", 40)],
             "not_interested": [_pid("QB", 10)]}
    ctx, con = _ctx_and_pctx(players, seed, league, "opp_contender",
                             prefs=prefs)
    # They'd SEND their untouchable (the viewer receives it).
    card = _Card("x", "opp_contender", [], [_pid("WR", 10)])
    card.give_player_ids = [_pid("WR", 33)]
    card.receive_player_ids = [_pid("WR", 10)]
    out = tb._obj_other_player_keep(_view(card), con, ctx)
    assert out["severity"] in (0.9, 1.0)
    assert out["evidence"] == {"asset": _pid("WR", 10), "list": "untouchable"}

    # targets / not_interested never fire it.
    t_card = _Card("y", "opp_contender", [_pid("WR", 33)], [_pid("RB", 40)])
    assert tb._obj_other_player_keep(_view(t_card), con, ctx)["severity"] == 0.0
    n_card = _Card("z", "opp_contender", [_pid("WR", 33)], [_pid("QB", 10)])
    assert tb._obj_other_player_keep(_view(n_card), con, ctx)["severity"] == 0.0


def test_roster_crunch_predicate(world):
    players, seed, league = world
    ctx, con = _ctx_and_pctx(players, seed, league, "opp_contender")
    # 1-for-2 from THEIR seat: they send 1, receive 2 ⇒ extra = 1.
    card = _Card("x", "opp_contender", [_pid("WR", 33), _pid("WR", 34)],
                 [_pid("RB", 40)])
    out = tb._obj_roster_crunch(_view(card), con, ctx)
    assert out["evidence"]["extra"] == 1
    assert out["evidence"]["pileup"] == []          # contender bench WR = 0
    assert out["severity"] == round(425.0 / 850.0, 3) == 0.5

    # extra ≤ 0 ⇒ 0.0.
    even = _Card("y", "opp_contender", [_pid("WR", 33)], [_pid("RB", 40)])
    assert tb._obj_roster_crunch(_view(even), con, ctx)["severity"] == 0.0

    # Picks occupy no Sleeper roster slot.
    picks = _Card("z", "opp_contender", list(_PICK_IDS[:2]), [_pid("RB", 40)])
    assert tb._obj_roster_crunch(_view(picks), con, ctx)["evidence"]["extra"] \
        == -1

    # Pile-up bonus caps at +0.30 (two positions, bench ≥ 3 each).
    _c2, reb = _ctx_and_pctx(players, seed, league, "opp_rebuilder")
    assert reb.profile["tier_depth"]["WR"]["bench"] >= 3
    assert reb.profile["tier_depth"]["RB"]["bench"] >= 3
    pile = _Card("p", "opp_rebuilder", [_pid("WR", 33), _pid("RB", 33)],
                 [_pid("QB", 12)])
    out2 = tb._obj_roster_crunch(_view(pile), reb, ctx)
    assert out2["evidence"]["pileup"] == ["RB", "WR"]
    assert out2["severity"] == round(
        min(1.0, 425.0 / 850.0 + 0.30), 3)


def test_board_auth_heuristic(world):
    players, seed, league = world
    cfg = tb._knob_snapshot()
    assert tb._board_auth(None, seed, cfg) == "consensus"
    assert tb._board_auth({}, seed, cfg) == "consensus"
    # Exactly at breaker_board_min_divergent (10) ⇒ authentic.
    keys = list(seed)[:20]
    board = dict(seed)
    for pid in keys[:10]:
        board[pid] = seed[pid] + 30.0
    assert tb._board_auth(board, seed, cfg) == "board"
    board2 = dict(seed)
    for pid in keys[:9]:
        board2[pid] = seed[pid] + 30.0
    assert tb._board_auth(board2, seed, cfg) == "board_suspect"
    # Divergence BELOW breaker_board_div_min does not count.
    board3 = {pid: seed[pid] + 24.0 for pid in seed}
    assert tb._board_auth(board3, seed, cfg) == "board_suspect"


# ───────────────────────────────────────────────────────────────────────────
# Coherence with the shipped narrative writer (M-8 precondition)
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("incoming", [
    [_pid("RB", 10)],                                  # one player
    [_pid("RB", 10), _pid("WR", 45)],                  # mixed ages
    [_pid("RB", 10)] + list(_PICK_IDS[:1]),            # pick-carrying
    list(_PICK_IDS),                                   # all picks
])
def test_lean_quantity_parity(world, incoming):
    """The breaker's `lean` IS trade_narrative._give_side_now_lean over the
    same asset list — picks included at the `_now_lean` PICK constant −0.25.
    Two writers cannot disagree about the same scalar."""
    players, seed, league = world
    ctx, reb = _ctx_and_pctx(players, seed, league, "opp_rebuilder")
    view = tb._CardView(give_ids=[], recv_ids=list(incoming))
    out = tb._obj_fit_outlook(view, reb, ctx)
    mirror = _Card("m", "opp_rebuilder", list(incoming), [])
    assert out["evidence"]["lean"] == round(
        tn._give_side_now_lean(mirror, players), 3)


def test_opponent_frame_breaker_disjoint(world):
    """Characterization: `_opponent_frame` asserts window FIT from exactly the
    quantity the breaker computes window PUSH from, with mirrored thresholds —
    the two can never both fire for one (card, outlook)."""
    players, seed, league = world
    ctx, reb = _ctx_and_pctx(players, seed, league, "opp_rebuilder")
    _c2, con = _ctx_and_pctx(players, seed, league, "opp_contender")
    packages = [[_pid("RB", 10)], [_pid("WR", 45)], list(_PICK_IDS[:1]),
                [_pid("RB", 10), _pid("WR", 45)]]
    for pctx in (reb, con):
        for pkg in packages:
            card = _Card("c", pctx.user_id, list(pkg), [])
            frame = tn._opponent_frame(
                card, {"opponent_outlook": {"value": pctx.outlook}}, players)
            view = tb._CardView(give_ids=[], recv_ids=list(pkg))
            fired = tb._obj_fit_outlook(view, pctx, ctx)["severity"] > 0.0
            assert not (frame is not None and fired)


# ───────────────────────────────────────────────────────────────────────────
# Degenerate inputs (LLD §3.10) — one case per cell
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code,give,recv,expect", [
    # partner's give side = all picks
    ("fit_outlook",       list(_PICK_IDS), [_pid("RB", 10)], "scored"),
    ("fit_new_weakness",  list(_PICK_IDS), [_pid("RB", 10)], "not_applicable"),
    ("value_giving",      list(_PICK_IDS), [_pid("RB", 10)], "scored"),
    ("other_player_keep", list(_PICK_IDS), [_pid("RB", 10)], "scored"),
    ("roster_crunch",     list(_PICK_IDS), [_pid("RB", 10)], "scored"),
    # partner's receive side = all picks
    ("fit_outlook",       [_pid("RB", 10)], list(_PICK_IDS), "scored"),
    ("fit_duplicate",     [_pid("RB", 10)], list(_PICK_IDS), "not_applicable"),
    ("roster_crunch",     [_pid("RB", 10)], list(_PICK_IDS), "scored"),
    # empty sides (defensive)
    ("fit_outlook",       [], [], "not_applicable"),
    ("fit_duplicate",     [], [], "not_applicable"),
    ("fit_new_weakness",  [], [], "not_applicable"),
    ("value_giving",      [], [], "scored"),
    ("other_player_keep", [], [], "scored"),
    ("roster_crunch",     [], [], "scored"),
])
def test_degenerate_inputs_per_class(world, code, give, recv, expect):
    players, seed, league = world
    ctx, con = _ctx_and_pctx(players, seed, league, "opp_contender")
    view = tb._CardView(give_ids=list(give), recv_ids=list(recv))
    out = tb._PREDICATES[code](view, con, ctx)     # never raises
    assert out["code"] == code
    if expect == "scored":
        assert out["severity"] is not None
        assert set(out["evidence"]) == tb.EVIDENCE_KEYS[code]
    else:
        assert out["severity"] is None and out["skipped"] == expect


def test_degenerate_empty_partner_roster(world):
    players, seed, league = world
    ctx, _p = _ctx_and_pctx(players, seed, league, "opp_contender")
    empty = tb._build_context(
        user_id="filler4", username="F4", roster=[], board_raw=None,
        has_rankings=False, declared=None, pick_share=0.0, prefs={},
        prefs_available=True, ctx=ctx)
    view = tb._CardView(give_ids=[_pid("RB", 10)], recv_ids=[_pid("WR", 10)])
    for code in ("fit_new_weakness", "fit_duplicate", "roster_crunch"):
        assert tb._PREDICATES[code](view, empty, ctx)["skipped"] == \
            "not_applicable"
    # Outlook + value + prefs math is roster-free and still scores.
    for code in ("fit_outlook", "value_giving", "other_player_keep"):
        assert tb._PREDICATES[code](view, empty, ctx)["severity"] is not None


def test_format_envelope(world):
    players, seed, league = world
    # 14-team league ⇒ the depth classes gap; fit_outlook/value_giving score.
    big = _league(players, seed, n_members=13)
    cards, _ = _stamp(players, seed, big)
    bk = cards[0].breaker
    assert set(bk["format_gap"]) == set(tb.ENVELOPE_CLASSES)
    by_code = {o["code"]: o for o in bk["objections"]}
    for code in tb.ENVELOPE_CLASSES:
        assert by_code[code]["skipped"] == "format_gap"
        assert by_code[code]["severity"] is None
    assert by_code["fit_outlook"]["severity"] is not None
    assert by_code["value_giving"]["severity"] is not None

    # Non-Sleeper platform gaps the same classes.
    espn = _league(players, seed, platform="espn")
    cards2, _ = _stamp(players, seed, espn)
    assert set(cards2[0].breaker["format_gap"]) == set(tb.ENVELOPE_CLASSES)

    # Superflex is IN envelope (SF QB cuts) — nothing gaps.
    cards3, _ = _stamp(players, seed, league, scoring_format="sf_tep")
    assert cards3[0].breaker["format_gap"] is None

    # An unpriceable IDP/K asset on the partner's roster gaps the depth
    # classes (G-026), and a zero-priced PLAYER in the package additionally
    # gaps value_giving.
    rosters = {k: list(v) for k, v in _ROSTERS.items()}
    rosters["opp_contender"] = rosters["opp_contender"] + ["K01"]
    idp = _league(players, seed, rosters=rosters)
    k_card = _Card("k", "opp_contender", ["K01"], [_pid("WR", 33)])
    cards4, _ = _stamp(players, seed, idp, cards=[k_card])
    gap = cards4[0].breaker["format_gap"]
    assert set(tb.ENVELOPE_CLASSES) <= set(gap)
    assert "value_giving" in gap


# ───────────────────────────────────────────────────────────────────────────
# Knob snapshot, binding discipline, stud-tax pin
# ───────────────────────────────────────────────────────────────────────────

def test_knob_snapshot_covers_the_declared_key_set():
    cfg = tb._knob_snapshot()
    assert set(cfg) == set(tb._BREAKER_KNOB_KEYS) | set(tb._SHARED_ENGINE_KNOB_KEYS)
    assert len(tb._BREAKER_KNOB_KEYS) == 25
    assert cfg["waiver_slot_cost"] == ts._c("waiver_slot_cost")


def test_default_knob_ordering():
    """D-8 — the narration bar sits ABOVE the stamp bar in the shipped
    defaults: `breaker_min_severity` dominates every class floor except the
    deliberately-higher consensus-basis `value_giving` floor, which in turn
    dominates `breaker_min_severity` (the testable half of §7.6 item 4)."""
    d = tb._BREAKER_KNOB_DEFAULTS
    min_sev = d["breaker_min_severity"]
    for code in tb.ALL_CLASSES:
        floor = d[f"breaker_floor_{code}"]
        assert max(floor, min_sev) >= floor
        if code != "value_giving":
            assert min_sev >= floor, code
    assert d["breaker_floor_value_giving_consensus"] >= min_sev
    assert d["breaker_floor_value_giving"] <= min_sev
    # Every narration switch ships OFF — graduation is an operator flip.
    for code in tb.ALL_CLASSES:
        assert d[f"breaker_narrate_{code}"] == 0.0


def test_knob_snapshot_frozen_within_job(world):
    """One job, one knob-state: a knob mutated mid-job must not move stamps."""
    players, seed, league = world
    cards = _deck()
    real = tb._obj_roster_crunch

    def _flip(view, pctx, ctx):
        ts._cfg["waiver_slot_cost"] = 5000.0     # hot flip between the passes
        return real(view, pctx, ctx)

    tb._PREDICATES["roster_crunch"] = _flip
    try:
        tb.stamp_breaker(cards, **_kwargs(players, seed, league))
    finally:
        tb._PREDICATES["roster_crunch"] = real
        ts._cfg["waiver_slot_cost"] = ts._DEFAULT_CFG["waiver_slot_cost"]
    by_id = {c.trade_id: c for c in cards}
    crunch = {o["code"]: o for o in by_id["t6"].breaker["objections"]}["roster_crunch"]
    assert crunch["evidence"]["slot_cost"] == 425.0      # the snapshot value


def test_breaker_binding_sabotage(world, monkeypatch):
    """T1 discipline: symbols reached as `ts.<name>` at CALL time, so a knob
    or a module-attribute monkeypatch moves the NEXT call's verdicts. A
    value-binding import would no-op and fail this test."""
    players, seed, league = world
    cards_a, _ = _stamp(players, seed, league)
    base = {o["code"]: o for o in
            {c.trade_id: c for c in cards_a}["t6"].breaker["objections"]}

    ts._cfg["waiver_slot_cost"] = 900.0
    cards_b, _ = _stamp(players, seed, league)
    moved = {o["code"]: o for o in
             {c.trade_id: c for c in cards_b}["t6"].breaker["objections"]}
    assert moved["roster_crunch"]["severity"] != \
        base["roster_crunch"]["severity"]
    ts._cfg["waiver_slot_cost"] = ts._DEFAULT_CFG["waiver_slot_cost"]

    monkeypatch.setattr(ts, "package_value_v2",
                        lambda *a, **k: 1.0, raising=True)
    cards_c, _ = _stamp(players, seed, league)
    sab = {o["code"]: o for o in
           {c.trade_id: c for c in cards_c}["t6"].breaker["objections"]}
    assert sab["value_giving"]["evidence"]["margin"] != \
        base["value_giving"]["evidence"]["margin"]


def test_stud_tax_pinned_market(world):
    """An ambient stud-tax mode at the seam must not move breaker valuations —
    the partner's own mode is private state the breaker cannot know (M-5)."""
    players, seed, league = world
    cards_a, _ = _stamp(players, seed, league)
    with ts.stud_tax_override("heavy"):
        cards_b, _ = _stamp(players, seed, league)
    for a, b in zip(cards_a, cards_b):
        assert _strip_ms(a.breaker) == _strip_ms(b.breaker)
        assert b.breaker["value_mode"] == "market"


# ───────────────────────────────────────────────────────────────────────────
# top selection
# ───────────────────────────────────────────────────────────────────────────

def _fake_pctx():
    return tb.PartnerContext(
        user_id="u", username="u", roster=["p"], counts={}, profile={},
        outlook="rebuilder", outlook_src="declared", outlook_declared="rebuilder",
        outlook_inferred="rebuilder", outlook_score=0.0, board=None,
        board_auth="consensus", prefs={}, format_gap=[])


def test_top_tiebreak_priority():
    cfg = tb._knob_snapshot()
    objs = {"fit_outlook": tb._entry("fit_outlook", 0.900, {}),
            "fit_duplicate": tb._entry("fit_duplicate", 0.900, {}),
            "fit_new_weakness": tb._entry("fit_new_weakness", 0.900, {}),
            "value_giving": tb._entry("value_giving", 0.0,
                                      {"basis": "consensus"}),
            "other_player_keep": tb._entry("other_player_keep", 0.0, {}),
            "roster_crunch": tb._entry("roster_crunch", 0.900, {})}
    card = _Card("t", "u", [], [])
    out = tb._finalize(objs, _fake_pctx(), card, cfg,
                       pass2_skip_reason=None, ms=1.0, shadow=False)
    assert out["top"]["code"] == "fit_new_weakness"      # earliest in priority

    del objs["fit_new_weakness"]
    objs["fit_new_weakness"] = tb._entry("fit_new_weakness", 0.0, {})
    out2 = tb._finalize(objs, _fake_pctx(), card, cfg,
                        pass2_skip_reason=None, ms=1.0, shadow=False)
    assert out2["top"]["code"] == "fit_outlook"

    # Below-floor classes are still LISTED but can never be `top`.
    low = {c: tb._entry(c, 0.05, {"basis": "consensus"}) for c in tb.ALL_CLASSES}
    out3 = tb._finalize(low, _fake_pctx(), card, cfg,
                        pass2_skip_reason=None, ms=1.0, shadow=False)
    assert out3["top"] is None
    assert len(out3["objections"]) == len(tb.ALL_CLASSES)


def test_them_is_passthrough(world):
    players, seed, league = world
    sentinel = object()
    withdiag = _Card("d", "opp_contender", [_pid("RB", 40)], [_pid("WR", 33)],
                     fit_diag={"them": sentinel, "you": 12.0})
    plain = _Card("p", "opp_contender", [_pid("RB", 40)], [_pid("WR", 33)])
    cards, _ = _stamp(players, seed, league, cards=[withdiag, plain])
    assert cards[0].breaker["them"] is sentinel
    assert cards[1].breaker["them"] is None
    # The shadow is a viewer-seat payload — `them` is a partner quantity.
    assert cards[0].breaker_shadow["them"] is None


def test_stamp_size_budget(world):
    """A tripwire against evidence-shape creep: `features_json` rows are read
    back by every readout query (LLD §2.7)."""
    players, seed, league = world
    cards, _ = _stamp(players, seed, league)
    for card in cards:
        for payload in (card.breaker, card.breaker_shadow):
            assert len(json.dumps(payload, default=str)) < 4096


# ───────────────────────────────────────────────────────────────────────────
# Degradation ladder
# ───────────────────────────────────────────────────────────────────────────

def test_empty_deck_noop(world):
    players, seed, league = world
    job = tb.stamp_breaker([], **_kwargs(players, seed, league))
    assert job.report.cards_seen == 0 and job.report.stamped == 0
    assert tb.compose_narration([], players=players, job=job) == 0


def test_self_partner_marker(world):
    players, seed, league = world
    card = _Card("s", _VIEWER_ID, [_pid("RB", 10)], [_pid("WR", 33)])
    cards, job = _stamp(players, seed, league, cards=[card, _deck()[0]])
    assert cards[0].breaker == tb._marker("self_partner")
    assert cards[1].breaker["objections"] is not None      # others unaffected
    assert job.report.degraded_by_rung[4] == 1


def test_partner_snapshot_rung1(world):
    players, seed, league = world
    ghost = _Card("g", "nobody", [_pid("RB", 10)], [_pid("WR", 33)])
    cards, job = _stamp(players, seed, league, cards=[ghost, _deck()[0]])
    assert cards[0].breaker == tb._marker("partner_snapshot")
    assert cards[0].breaker_shadow == tb._marker("partner_snapshot")
    assert cards[1].breaker["objections"] is not None
    assert job.report.partner_ctx_failed == 1
    assert job.report.degraded_by_rung[1] == 1


def test_bulk_reader_failure_field_level(world, monkeypatch):
    """A failed prefs bulk read degrades the FIELD, not the rung — prefs
    absence is a legitimate common state (LLD §2.2)."""
    players, seed, league = world
    monkeypatch.setattr(tb, "_bulk_prefs", lambda *a, **k: ({}, False))
    cards, job = _stamp(players, seed, league)
    for card in cards:
        by_code = {o["code"]: o for o in card.breaker["objections"]}
        assert by_code["other_player_keep"]["skipped"] == "not_applicable"
        assert card.breaker["degraded"] is None
    assert job.report.degraded_by_rung[1] == 0
    assert job.report.degraded_by_rung[0] == len(cards)


def test_per_class_exception_contained(world, monkeypatch):
    """E-14 — one flaky predicate must not zero the coverage metric for all
    six classes: that class alone stamps a DURABLE `predicate_error`."""
    players, seed, league = world

    def _boom(view, pctx, ctx):
        raise RuntimeError("sabotage")

    monkeypatch.setitem(tb._PREDICATES, "fit_duplicate", _boom)
    cards, job = _stamp(players, seed, league)
    for card in cards:
        by_code = {o["code"]: o for o in card.breaker["objections"]}
        assert by_code["fit_duplicate"]["skipped"] == "predicate_error"
        assert by_code["fit_duplicate"]["severity"] is None
        for code in tb.ALL_CLASSES:
            if code == "fit_duplicate":
                continue
            assert by_code[code].get("skipped") != "predicate_error"
        assert card.breaker["degraded"] is None          # card stays rung 0
    assert job.report.predicate_errors >= len(cards)


def test_exception_rungs_card_level(world, monkeypatch):
    """A failure OUTSIDE any class predicate is a whole-card rung 4."""
    players, seed, league = world
    real = tb._CardView

    def _bad(**kw):
        if kw.get("recv_ids") == [_pid("RB", 11)]:
            raise RuntimeError("context assembly")
        return real(**kw)

    monkeypatch.setattr(tb, "_CardView", _bad)
    cards, job = _stamp(players, seed, league)
    by_id = {c.trade_id: c for c in cards}
    assert by_id["t2"].breaker == tb._marker("exception_card")
    assert by_id["t0"].breaker["objections"] is not None
    assert job.report.degraded_by_rung[4] == 1


def _snap_with(**over):
    """A frozen-snapshot override — the ONLY sanctioned way to move a knob for
    one job, since the module reads `cfg` and never `ts._c` after §3.0."""
    real = tb._knob_snapshot

    def _snap():
        cfg = real()
        cfg.update(over)
        return cfg
    return _snap


def test_budget_ladder_labeling(world):
    players, seed, league = world

    # breaker_ms_budget = 0 ⇒ documented disable, minimal markers everywhere.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(tb, "_knob_snapshot", _snap_with(breaker_ms_budget=0.0))
        cards, job = _stamp(players, seed, league)
    assert all(c.breaker == tb._marker("budget_exhausted") for c in cards)
    assert job.report.degraded_by_rung[3] == len(cards)

    # Checkpoint trip after pass 1 ⇒ pass 2 dropped WHOLE, deck-uniform.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(tb, "_knob_snapshot",
                   _snap_with(breaker_ms_budget=10000.0,
                              breaker_budget_checkpoint_frac=0.0))
        cards2, job2 = _stamp(players, seed, league)
    assert job2.report.pass2_ran is False
    for card in cards2:
        assert card.breaker["skipped"] == {"classes": list(tb.PASS_2_CLASSES),
                                           "reason": "budget"}
        by_code = {o["code"]: o for o in card.breaker["objections"]}
        for code in tb.PASS_2_CLASSES:
            assert by_code[code]["skipped"] == "budget"
        assert by_code["fit_outlook"]["severity"] is not None   # pass 1 kept
        assert card.breaker["degraded"] is None

    # Mid-pass-2 exhaustion ⇒ buffered pass-2 results DISCARDED for the whole
    # deck (M-9 atomicity); pass-1 scores KEPT, deck-uniform label.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(tb, "_knob_snapshot",
                   _snap_with(breaker_ms_budget=0.001,      # 1 µs
                              breaker_budget_checkpoint_frac=1e9))
        cards3, job3 = _stamp(players, seed, league)
    assert job3.report.pass2_ran is False
    scored = [c for c in cards3 if c.breaker.get("objections")]
    assert scored, "pass-1 scores must survive the atomic discard"
    for card in scored:
        assert card.breaker["degraded"] == "budget_exhausted"
        assert card.breaker["skipped"]["reason"] == "budget_exhausted"
        by_code = {o["code"]: o for o in card.breaker["objections"]}
        for code in tb.PASS_2_CLASSES:
            assert by_code[code]["severity"] is None


def test_budget_boundary_is_strict_gt(world, monkeypatch):
    """E-17 — the budget comparisons are strict `>`: a run sitting EXACTLY at
    the budget (and exactly at the checkpoint) finishes. Pinned so the
    boundary is testable, not because it matters."""
    players, seed, league = world

    class _Clock:
        """t0 = 0.0; every later read is exactly the 250 ms budget."""
        def __init__(self):
            self.n = 0

        def monotonic(self):
            self.n += 1
            return 0.0 if self.n == 1 else 0.25

    monkeypatch.setattr(tb, "time", _Clock())
    monkeypatch.setattr(tb, "_knob_snapshot",
                        _snap_with(breaker_ms_budget=250.0,
                                   breaker_budget_checkpoint_frac=1.0))
    cards, job = _stamp(players, seed, league)
    assert job.report.pass2_ran is True
    assert cards[0].breaker["skipped"] is None
    assert cards[-1].breaker["objections"] is not None


def test_co_owner_prefs_not_read(world, monkeypatch):
    """§2.3 ruling: counterparty state resolves under `member.user_id` alone —
    a co-owner's prefs stored under a DIFFERENT account id are not read. A
    documented limitation, stamped, not silent wrongness."""
    players, seed, league = world
    stored = {"co_owner_account": {"untouchable": [_pid("WR", 10)]}}
    seen = {}

    def _bulk(user_ids, league_id):
        seen["ids"] = list(user_ids)
        return {uid: stored[uid] for uid in user_ids if uid in stored}

    monkeypatch.setattr(tb, "_bulk_prefs",
                        lambda ids, lid: (_bulk(ids, lid), True))
    card = _Card("c", "opp_contender", [_pid("WR", 33)], [_pid("WR", 10)])
    cards, _ = _stamp(players, seed, league, cards=[card])
    assert "co_owner_account" not in seen["ids"]
    by_code = {o["code"]: o for o in cards[0].breaker["objections"]}
    assert by_code["other_player_keep"]["severity"] == 0.0
    assert cards[0].breaker["identity_src"] == "owner_id"


# ───────────────────────────────────────────────────────────────────────────
# Shadow run + outlook resolution
# ───────────────────────────────────────────────────────────────────────────

def test_shadow_run(world, monkeypatch):
    players, seed, league = world
    cards, _ = _stamp(players, seed, league)
    for card in cards:
        shadow = card.breaker_shadow
        assert set(shadow) == set(card.breaker)
        assert shadow["narrated"] is None and shadow["suppressed"] is None
        assert shadow["tmpl_ver"] is None and shadow["them"] is None
    # Viewer seat is UNSWAPPED: the shadow's value_giving n_give/n_recv are
    # the card's own sides, the primary's are mirrored.
    card0 = cards[0]
    prim = {o["code"]: o for o in card0.breaker["objections"]}["value_giving"]
    shad = {o["code"]: o for o in card0.breaker_shadow["objections"]}["value_giving"]
    assert prim["evidence"]["n_give"] == len(card0.receive_player_ids)
    assert shad["evidence"]["n_give"] == len(card0.give_player_ids)

    # Knob off ⇒ no shadow attribute at all.
    real_snap = tb._knob_snapshot

    def _off():
        cfg = real_snap()
        cfg["breaker_shadow_run"] = 0.0
        return cfg

    monkeypatch.setattr(tb, "_knob_snapshot", _off)
    cards2, _ = _stamp(players, seed, league)
    assert all(getattr(c, "breaker_shadow", None) is None for c in cards2)


def test_shadow_degrades_with_primary(world, monkeypatch):
    """Budget exhaustion degrades primary and shadow TOGETHER (interleave pin
    — uncorrelated shadow missingness would bias the §8 calibration cut)."""
    players, seed, league = world
    real_snap = tb._knob_snapshot

    def _snap():
        cfg = real_snap()
        cfg["breaker_ms_budget"] = 0.0000001
        return cfg

    monkeypatch.setattr(tb, "_knob_snapshot", _snap)
    cards, _ = _stamp(players, seed, league)
    for card in cards:
        assert (card.breaker.get("objections") is None) == \
            (card.breaker_shadow.get("objections") is None)


def test_outlook_declared_vs_inferred(world, monkeypatch):
    players, seed, league = world
    cards, _ = _stamp(players, seed, league)
    bk = cards[0].breaker
    assert bk["outlook_src"] == "declared"
    assert bk["outlook_pair"]["declared"] == "rebuilder"
    assert bk["outlook_pair"]["inferred"] in (
        "contender", "rebuilder", "not_sure")
    assert isinstance(bk["outlook_pair"]["score"], float)

    # No declared map at all ⇒ the legacy inferred vector, via the bulk reader.
    seen = {}

    def _lprefs(ids, lid):
        seen["ids"] = list(ids)
        return {"opp_rebuilder": {"team_outlook": "jets"}}

    monkeypatch.setattr(tb, "_bulk_league_prefs", _lprefs)
    cards2, _ = _stamp(players, seed, league, declared_outlooks={})
    by_id = {c.trade_id: c for c in cards2}
    assert "opp_rebuilder" in seen["ids"]
    assert by_id["t0"].breaker["outlook_src"] == "declared"      # from prefs
    assert by_id["t0"].breaker["outlook_pair"]["declared"] == "jets"
    assert by_id["t3"].breaker["outlook_src"] == "legacy"        # inferred
    assert by_id["t3"].breaker["outlook_pair"]["declared"] is None


# ───────────────────────────────────────────────────────────────────────────
# compose_narration (LLD §3.8; PRD §5.4 tone rules bind the gating)
# ───────────────────────────────────────────────────────────────────────────

def _stub_templates(monkeypatch, fn=None, ver="brt-1"):
    monkeypatch.setattr(
        tn, "hesitation_line",
        fn or (lambda objection, players: f"line:{objection['code']}"),
        raising=False)
    monkeypatch.setattr(tn, "HESITATION_TMPL_VERSION", ver, raising=False)


def _narrating_deck(players, seed, league, monkeypatch, *, code="fit_outlook",
                    severity=0.95, n=1, partner="opp_rebuilder",
                    evidence=None, outlook_src="declared"):
    """A deck of `n` cards whose stamped `top` is a graduated, above-floor
    objection of `code` — built by stamping, then pinning `top`."""
    cards = [_Card(f"n{i}", partner, [_pid("RB", 10)], [_pid("WR", 45)])
             for i in range(n)]
    job = tb.stamp_breaker(cards, **_kwargs(players, seed, league))
    for card in cards:
        card.breaker["top"] = {"code": code, "severity": severity,
                               "evidence": dict(evidence or {})}
        card.breaker["format_gap"] = None
        card.breaker["outlook_src"] = outlook_src
    return cards, job


def test_narration_switch_ladder(world, monkeypatch):
    players, seed, league = world
    _stub_templates(monkeypatch)
    cards, job = _narrating_deck(players, seed, league, monkeypatch)

    # All switches 0 ⇒ a flag-on deck renders NOTHING by design.
    assert tb.compose_narration(cards, players=players, job=job) == 0
    assert cards[0].breaker["narrated"] is None
    assert cards[0].breaker["suppressed"] == "class_ineligible"

    job.cfg["breaker_narrate_fit_outlook"] = 1.0
    assert tb.compose_narration(cards, players=players, job=job) == 1
    assert cards[0].breaker["narrated"] == "line:fit_outlook"
    assert cards[0].breaker["suppressed"] is None
    assert job.report.narrated == 1


def test_tmpl_ver_stamped(world, monkeypatch):
    players, seed, league = world
    _stub_templates(monkeypatch)
    cards, job = _narrating_deck(players, seed, league, monkeypatch, n=2)
    job.cfg["breaker_narrate_fit_outlook"] = 1.0
    job.cfg["breaker_max_repeat_frac"] = 1.0
    tb.compose_narration(cards, players=players, job=job)
    assert cards[0].breaker["tmpl_ver"] == "brt-1"
    # A card that never narrated carries a null tmpl_ver.
    dark, job2 = _narrating_deck(players, seed, league, monkeypatch)
    tb.compose_narration(dark, players=players, job=job2)
    assert dark[0].breaker["tmpl_ver"] is None


def test_narration_whitelist_dark_classes(world, monkeypatch):
    players, seed, league = world
    _stub_templates(monkeypatch)
    # other_player_keep: private state — never narrates even with its switch on.
    cards, job = _narrating_deck(players, seed, league, monkeypatch,
                                 code="other_player_keep", severity=1.0,
                                 evidence={"asset": "x", "list": "untouchable"})
    job.cfg["breaker_narrate_other_player_keep"] = 1.0
    assert tb.compose_narration(cards, players=players, job=job) == 0
    assert cards[0].breaker["suppressed"] == "class_ineligible"

    # value_giving: the board basis is narration-ineligible OUTRIGHT (D-7).
    b_cards, b_job = _narrating_deck(players, seed, league, monkeypatch,
                                     code="value_giving", severity=0.99,
                                     evidence={"basis": "board", "margin": -900.0,
                                               "n_give": 1, "n_recv": 1})
    b_job.cfg["breaker_narrate_value_giving"] = 1.0
    assert tb.compose_narration(b_cards, players=players, job=b_job) == 0
    assert b_cards[0].breaker["suppressed"] == "class_ineligible"

    # The consensus basis narrates — behind the deliberately higher floor.
    c_cards, c_job = _narrating_deck(players, seed, league, monkeypatch,
                                     code="value_giving", severity=0.99,
                                     evidence={"basis": "consensus",
                                               "margin": -900.0,
                                               "n_give": 1, "n_recv": 1})
    c_job.cfg["breaker_narrate_value_giving"] = 1.0
    assert tb.compose_narration(c_cards, players=players, job=c_job) == 1


def test_narration_floors_and_min_severity(world, monkeypatch):
    players, seed, league = world
    _stub_templates(monkeypatch)
    cards, job = _narrating_deck(players, seed, league, monkeypatch,
                                 severity=0.50)      # over floor, under min_sev
    job.cfg["breaker_narrate_fit_outlook"] = 1.0
    assert tb.compose_narration(cards, players=players, job=job) == 0
    assert cards[0].breaker["suppressed"] == "below_floor"
    assert job.report.suppressed_by_reason["below_floor"] == 1

    # The consensus value_giving floor (0.75) outranks breaker_min_severity.
    v_cards, v_job = _narrating_deck(
        players, seed, league, monkeypatch, code="value_giving", severity=0.70,
        evidence={"basis": "consensus", "margin": -1.0, "n_give": 1,
                  "n_recv": 1})
    v_job.cfg["breaker_narrate_value_giving"] = 1.0
    assert tb.compose_narration(v_cards, players=players, job=v_job) == 0
    assert v_cards[0].breaker["suppressed"] == "below_floor"


def test_narration_format_gap(world, monkeypatch):
    players, seed, league = world
    _stub_templates(monkeypatch)
    cards, job = _narrating_deck(players, seed, league, monkeypatch,
                                 code="fit_duplicate", severity=0.95,
                                 evidence={"pos": "WR", "bench_n": 3,
                                           "value_share": 1.0, "asset": "x",
                                           "tier_basis": "positional"})
    job.cfg["breaker_narrate_fit_duplicate"] = 1.0
    cards[0].breaker["format_gap"] = ["fit_duplicate"]
    assert tb.compose_narration(cards, players=players, job=job) == 0
    assert cards[0].breaker["suppressed"] == "format_gap"


def test_narration_outlook_margin(world, monkeypatch):
    players, seed, league = world
    _stub_templates(monkeypatch)
    cut = ts._c("infer_rebuilder_cut")

    # Legacy source INSIDE the margin ⇒ not narrated; the stamp is untouched.
    cards, job = _narrating_deck(players, seed, league, monkeypatch,
                                 outlook_src="legacy")
    job.cfg["breaker_narrate_fit_outlook"] = 1.0
    cards[0].breaker["outlook_pair"] = {"declared": None,
                                        "inferred": "rebuilder",
                                        "score": cut - 0.01}
    assert tb.compose_narration(cards, players=players, job=job) == 0
    assert cards[0].breaker["suppressed"] == "class_ineligible"
    assert cards[0].breaker["top"]["severity"] == 0.95      # stamp untouched

    # Outside the margin ⇒ narrated.
    cards[0].breaker["outlook_pair"]["score"] = cut - 0.50
    assert tb.compose_narration(cards, players=players, job=job) == 1

    # declared ≠ inferred ⇒ not narrated; the pair still stamps both.
    d_cards, d_job = _narrating_deck(players, seed, league, monkeypatch)
    d_job.cfg["breaker_narrate_fit_outlook"] = 1.0
    d_cards[0].breaker["outlook_pair"] = {"declared": "contender",
                                          "inferred": "rebuilder",
                                          "score": 0.0}
    assert tb.compose_narration(d_cards, players=players, job=d_job) == 0
    assert d_cards[0].breaker["suppressed"] == "class_ineligible"
    assert d_cards[0].breaker["outlook_pair"]["declared"] == "contender"


def test_repetition_suppression(world, monkeypatch):
    """Anti-wallpaper (D-7): within one (partner, code) group larger than
    ceil(frac × that partner's cards), only the max-severity card narrates."""
    players, seed, league = world
    _stub_templates(monkeypatch)
    cards, job = _narrating_deck(players, seed, league, monkeypatch, n=5)
    job.cfg["breaker_narrate_fit_outlook"] = 1.0
    job.cfg["breaker_max_repeat_frac"] = 0.34            # ceil(0.34*5) = 2
    for i, card in enumerate(cards):
        card.breaker["top"]["severity"] = 0.90 + i * 0.01
    assert tb.compose_narration(cards, players=players, job=job) == 1
    assert cards[-1].breaker["narrated"] == "line:fit_outlook"
    assert all(c.breaker["suppressed"] == "repetition" for c in cards[:-1])
    assert job.report.suppressed_by_reason["repetition"] == 4

    # A group at/below the cap narrates every card.
    job.cfg["breaker_max_repeat_frac"] = 1.0
    assert tb.compose_narration(cards, players=players, job=job) == 5


def test_narration_template_error_contained(world, monkeypatch):
    players, seed, league = world

    def _boom(objection, players_):
        raise RuntimeError("template")

    _stub_templates(monkeypatch, fn=_boom)
    cards, job = _narrating_deck(players, seed, league, monkeypatch)
    job.cfg["breaker_narrate_fit_outlook"] = 1.0
    assert tb.compose_narration(cards, players=players, job=job) == 0
    assert cards[0].breaker["suppressed"] == "template_error"
    assert cards[0].breaker["narrated"] is None
    assert cards[0].breaker["top"]["severity"] == 0.95      # stamps untouched


def test_null_evidence_is_honest_silence(world, monkeypatch):
    """D-053 mechanically: a template that cannot render its evidence returns
    None, and the breaker stamps SILENCE — never a half-rendered sentence and
    never a false suppression reason."""
    players, seed, league = world
    _stub_templates(monkeypatch, fn=lambda objection, players_: None)
    cards, job = _narrating_deck(players, seed, league, monkeypatch,
                                 evidence={"outlook": "rebuilder", "lean": 0.4,
                                           "asset": None, "age": None,
                                           "pos": None})
    job.cfg["breaker_narrate_fit_outlook"] = 1.0
    assert tb.compose_narration(cards, players=players, job=job) == 0
    assert cards[0].breaker["narrated"] is None
    assert cards[0].breaker["suppressed"] is None
    assert cards[0].breaker["tmpl_ver"] is None


def test_narration_never_touches_shadow(world, monkeypatch):
    players, seed, league = world
    _stub_templates(monkeypatch)
    cards, job = _narrating_deck(players, seed, league, monkeypatch)
    job.cfg["breaker_narrate_fit_outlook"] = 1.0
    before = json.dumps(cards[0].breaker_shadow, default=str)
    tb.compose_narration(cards, players=players, job=job)
    assert json.dumps(cards[0].breaker_shadow, default=str) == before
    assert cards[0].breaker_shadow["narrated"] is None


def test_narration_skips_marker_only_cards(world, monkeypatch):
    players, seed, league = world
    _stub_templates(monkeypatch)
    ghost = _Card("g", "nobody", [_pid("RB", 10)], [_pid("WR", 33)])
    cards, job = _stamp(players, seed, league, cards=[ghost])
    for code in tb.ALL_CLASSES:
        job.cfg[f"breaker_narrate_{code}"] = 1.0
    assert tb.compose_narration(cards, players=players, job=job) == 0
    assert cards[0].breaker == tb._marker("partner_snapshot")


def test_compose_narration_is_idempotent(world, monkeypatch):
    players, seed, league = world
    _stub_templates(monkeypatch)
    cards, job = _narrating_deck(players, seed, league, monkeypatch)
    job.cfg["breaker_narrate_fit_outlook"] = 1.0
    assert tb.compose_narration(cards, players=players, job=job) == 1
    first = dict(cards[0].breaker)
    assert tb.compose_narration(cards, players=players, job=job) == 1
    assert cards[0].breaker == first


def test_top_is_argmax_over_per_class_floors():
    """`top` is a SELECTION, not a score (D-4): the highest-severity class
    that clears its own floor wins; a higher-severity class BELOW its floor
    never does."""
    cfg = tb._knob_snapshot()
    card = _Card("t", "u", [], [])
    objs = {c: tb._entry(c, 0.0, {"basis": "consensus"}) for c in tb.ALL_CLASSES}
    objs["fit_duplicate"] = tb._entry("fit_duplicate", 0.40, {})
    objs["fit_outlook"] = tb._entry("fit_outlook", 0.90, {})
    out = tb._finalize(objs, _fake_pctx(), card, cfg,
                       pass2_skip_reason=None, ms=0.0, shadow=False)
    assert out["top"]["code"] == "fit_outlook" and out["top"]["severity"] == 0.90

    # roster_crunch at 0.39 sits under its 0.40 floor and loses to a 0.31
    # fit_duplicate that clears its 0.30 floor.
    objs["fit_outlook"] = tb._entry("fit_outlook", 0.0, {})
    objs["fit_duplicate"] = tb._entry("fit_duplicate", 0.31, {})
    objs["roster_crunch"] = tb._entry("roster_crunch", 0.39, {})
    out2 = tb._finalize(objs, _fake_pctx(), card, cfg,
                        pass2_skip_reason=None, ms=0.0, shadow=False)
    assert out2["top"]["code"] == "fit_duplicate"
    # ...and the below-floor class is still in the vector (§6.4 needs it).
    assert {o["code"]: o["severity"]
            for o in out2["objections"]}["roster_crunch"] == 0.39


def test_breaker_is_inert_on_existing_card_fields(world):
    """Evaluation only: the ONLY writes are `breaker` / `breaker_shadow`."""
    players, seed, league = world
    cards = _deck()
    before = [(c.trade_id, c.target_user_id, list(c.give_player_ids),
               list(c.receive_player_ids)) for c in cards]
    job = tb.stamp_breaker(cards, **_kwargs(players, seed, league))
    for code in tb.ALL_CLASSES:
        job.cfg[f"breaker_narrate_{code}"] = 1.0
    tb.compose_narration(cards, players=players, job=job)
    after = [(c.trade_id, c.target_user_id, list(c.give_player_ids),
              list(c.receive_player_ids)) for c in cards]
    assert before == after
    for card in cards:
        assert set(vars(card)) - {"fit_diag"} <= {
            "trade_id", "target_user_id", "give_player_ids",
            "receive_player_ids", "breaker", "breaker_shadow"}
