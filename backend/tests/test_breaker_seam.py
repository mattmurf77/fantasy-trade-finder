"""Counterparty breaker — the SERVER SEAM (stamp site, republish contract,
serialization gate, bulk readers, inertness).

Spec: docs/plans/counterparty-breaker/LLD.md §1.2 (the post-F9 seam block),
§1.3 (the snapshot-republish matrix), §1.4 (`_BK_SENTINEL` + the features
copy — the row-level half lives in test_bakeoff_serving.py), §1.5
(narration-gated `trade_card_to_dict`), §2.2 (the two read-only bulk
readers), §7.4 (the seam/serving/serialization rows).

What this file pins, in the LLD's own words:

  • Flag OFF ⇒ byte-identical. Impression rows and card payloads equal the
    committed pre-bake-off golden, and `backend.trade_breaker` is never
    imported (NFR-3).
  • The dark window (trade.breaker on, trade.breaker_narrative off) serves NO
    breaker key and adds ZERO publishes — snapshots byte-identical to
    flag-off.
  • The seam owns a republish iff `narrated_count > 0`, so the sentence
    reaches the stored snapshot on EVERY flag combination — including
    `deck.signal_v2` OFF, where the seam republish is the only carrier.
  • `card.breaker_shadow` NEVER serializes; the serialized `breaker` object is
    exactly {code, severity, sentence}.
  • Both T-1 skips (demo league, superseded job) hold.
  • Rung 5: an exception anywhere in the block stamps BOTH markers on EVERY
    card, with no knob read and no breaker-module reference.
  • Zero ordering effect on both bake-off draft paths and organic, and no
    module outside server.py + trade_breaker.py reads the stamps (D-11).

Harness: `backend/tests/support/bakeoff_harness.py` drives one complete
`_run_trade_job` against an in-memory DB with a pinned flag configuration —
the same real seam the golden capture ran through.
"""

import ast
import copy
import inspect
import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

import backend.bakeoff_runner as bo
import backend.database as db_module
import backend.feature_flags as ff
import backend.server as server
import backend.trade_breaker as tb
from backend.database import metadata
from backend.tests.support import bakeoff_harness as H


REPO = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).parent / "fixtures" / "bakeoff" / "flag_off_golden.json"

#: Mirrors test_bakeoff_serving.NEW_COLUMNS — the columns the bake-off change
#: ADDS to deck_impressions, stripped before comparing against the golden.
NEW_COLUMNS = ("model_arm", "arm_rank", "fairness_threshold",
               "group_key", "group_rank", "lane_slot", "trade_intent")

SENTENCE = "They may not want to move off a young back."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _restore_flags(monkeypatch):
    """Flag-cache restore (harness pattern 3). Every test sets its own map on
    top of the live config so the harness keeps behaving as it did when the
    golden was captured."""
    yield
    ff.reload()


def _flags(monkeypatch, **over):
    flags = dict(ff.flags_dict())
    flags.update(over)
    monkeypatch.setattr(ff, "_flags_cache", flags, raising=False)


def _strip_new_columns(rows):
    return [{k: v for k, v in row.items() if k not in NEW_COLUMNS}
            for row in rows]


def _scored(code="fit_outlook", severity=0.82):
    return {"ver": tb.BREAKER_VERSION, "degraded": None, "them": None,
            "narrated": None, "tmpl_ver": None,
            "top": {"code": code, "severity": severity, "evidence": {}},
            "objections": [{"code": code, "severity": severity,
                            "evidence": {}}]}


class _Stub:
    """Deterministic stand-ins for the two breaker entry points. The seam is
    what is under test here; the predicates have their own file."""

    def __init__(self, narrate=0, raise_on_stamp=False):
        self.narrate = narrate
        self.raise_on_stamp = raise_on_stamp
        self.stamp_calls = 0
        self.narr_calls = 0

    def stamp(self, cards, **kw):
        self.stamp_calls += 1
        if self.raise_on_stamp:
            raise RuntimeError("sabotaged stamp")
        for c in cards:
            c.breaker = _scored()
            c.breaker_shadow = {"ver": tb.BREAKER_VERSION, "degraded": None,
                                "objections": []}
        return tb.BreakerJob(cfg={}, report=tb.BreakerReport())

    def compose(self, cards, *, players, job):
        self.narr_calls += 1
        n = 0
        for c in list(cards)[:self.narrate]:
            bk = getattr(c, "breaker", None)
            if isinstance(bk, dict) and bk.get("top"):
                bk["narrated"] = SENTENCE
                bk["tmpl_ver"] = "brt-1"
                n += 1
        return n


def _run(monkeypatch, *, breaker=False, narrative=False, signal_v2=True,
         stub=None, extra=()):
    """One full `_run_trade_job` with the breaker flags set as asked.

    Returns (capture, job, engine, live_calls) — `live_calls` counts every
    `_job_live` call, which is exactly one per publish ATTEMPT (streaming and
    every mutation-layer republish alike), so "adds zero publishes" is a
    number this harness can compare."""
    _flags(monkeypatch, **{"trade.breaker": breaker,
                           "trade.breaker_narrative": narrative})
    counter = {"n": 0}
    _real_live = server._job_live

    def _counting_live(j):
        counter["n"] += 1
        return _real_live(j)

    patches = [patch.object(server, "_job_live", _counting_live),
               patch.object(server, "_deck_signal_v2_enabled",
                            lambda: signal_v2)]
    if stub is not None:
        patches += [patch.object(tb, "stamp_breaker", stub.stamp),
                    patch.object(tb, "compose_narration", stub.compose)]
    patches += list(extra)
    capture, job, engine = H.run_capture(extra_patches=patches)
    return capture, job, engine, counter["n"]


def _payloads(job):
    """Published snapshot cards with the per-run volatile keys (`trade_id`,
    `expires_at`, `impression_id`) removed — the harness's own canonical
    form, so two runs are comparable."""
    return H._canonical_cards(job.get("cards") or [])


# ---------------------------------------------------------------------------
# Flag OFF — byte identity (LLD §7.4, NFR-3)
# ---------------------------------------------------------------------------

def test_flag_off_features_json_byte_identical(monkeypatch):
    """Flag off at both sites ⇒ deck_impressions rows are byte-identical to
    the committed pre-bake-off golden. A captured golden, not an assertion
    about ourselves: the breaker cannot have moved a single byte of a
    flag-off row."""
    golden = json.loads(GOLDEN.read_text())
    with patch.object(bo, "bakeoff_enabled", lambda: False):
        capture, _job, _eng, _n = _run(monkeypatch, breaker=False)
    assert _strip_new_columns(capture["impressions"]) == golden["impressions"]
    for row in capture["impressions"]:
        assert "breaker" not in row["features_json"]


def test_flag_off_payload_byte_identical(monkeypatch):
    """Flag off ⇒ every `trade_card_to_dict` payload in the published
    snapshot equals the golden's, key for key."""
    golden = json.loads(GOLDEN.read_text())
    with patch.object(bo, "bakeoff_enabled", lambda: False):
        capture, _job, _eng, _n = _run(monkeypatch, breaker=False)
    assert capture["cards"] == golden["cards"]
    assert all("breaker" not in c for c in capture["cards"])


def test_flag_off_never_imports_breaker(monkeypatch):
    """NFR-3 — the seam's import is lazy and lives INSIDE the flag guard, so a
    flag-off job never loads the module at all."""
    saved = sys.modules.pop("backend.trade_breaker", None)
    try:
        _capture, _job, _eng, _n = _run(monkeypatch, breaker=False)
        assert "backend.trade_breaker" not in sys.modules
    finally:
        if saved is not None:
            sys.modules["backend.trade_breaker"] = saved


# ---------------------------------------------------------------------------
# Serialization gate (LLD §1.5)
# ---------------------------------------------------------------------------

def _card_with(breaker=None, shadow=None):
    from backend.trade_service import TradeCard
    c = TradeCard(trade_id="t1", league_id="L", proposing_user_id="me",
                  target_user_id="opp", target_username="opp",
                  give_player_ids=[], receive_player_ids=[],
                  fairness_score=0.9, mismatch_score=1.0, composite_score=1.0)
    if breaker is not None:
        c.breaker = breaker
    if shadow is not None:
        c.breaker_shadow = shadow
    return c


def test_breaker_payload_absent_during_dark_window():
    """LLD §1.5 — trade.breaker ON, trade.breaker_narrative OFF: the card is
    fully stamped but `narrated` is null, so the payload carries NO breaker
    key at all. Dark-class codes must never ship as inspectable structured
    data."""
    stamped = _card_with(breaker=_scored(), shadow={"ver": "brk-1"})
    unstamped = _card_with()
    dark = server.trade_card_to_dict(stamped, {})
    plain = server.trade_card_to_dict(unstamped, {})
    dark.pop("expires_at", None)               # per-call wall clock
    plain.pop("expires_at", None)
    assert "breaker" not in dark
    assert dark == plain                       # byte-identical to flag-off
    # …and a marker-only card (no `top` at all) is equally silent.
    marker = _card_with(breaker={"ver": "brk-1", "degraded": "exception_outer",
                                 "objections": None})
    assert "breaker" not in server.trade_card_to_dict(marker, {})


def test_breaker_shadow_never_serialized():
    """LLD §1.5 / §7.4 — the shadow run is a never-serialized diagnostic, and
    the narrated payload is exactly {code, severity, sentence}: the full
    objection vector stays in features_json."""
    bk = _scored()
    bk["narrated"] = SENTENCE
    bk["tmpl_ver"] = "brt-1"
    card = _card_with(breaker=bk,
                      shadow={"ver": "brk-1", "degraded": None,
                              "objections": [{"code": "value_giving"}]})
    out = server.trade_card_to_dict(card, {})
    assert out["breaker"] == {"code": "fit_outlook", "severity": 0.82,
                              "sentence": SENTENCE}
    assert "breaker_shadow" not in out
    assert "breaker_shadow" not in json.dumps(out)
    assert "objections" not in json.dumps(out["breaker"])


# ---------------------------------------------------------------------------
# The republish matrix (LLD §1.3, M-1) — T-13
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("signal_v2", [True, False])
@pytest.mark.parametrize(
    "breaker,narrative,narrate,expect_sentence",
    [
        (False, False, 0, False),   # flag off
        (True,  False, 0, False),   # dark window — stamped, never narrated
        (True,  True,  0, False),   # narration on, nothing cleared the bar
        (True,  True,  2, True),    # the live row
    ])
def test_narrated_payload_reaches_snapshot_all_flag_combos(
        monkeypatch, signal_v2, breaker, narrative, narrate, expect_sentence):
    """LLD §1.3 — the stored `j["cards"]` snapshot carries `breaker.sentence`
    for narrated cards iff narrated ∧ live, on EVERY combination of
    `deck.signal_v2` × the two breaker flags.

    The signal_v2-OFF rows are the reason the seam owns a republish at all:
    with `deck.signal_v2` off there is no unconditional post-mutation publish,
    so a sentence stamped post-F9 would exist in features_json and reach no
    client.

    The dark rows carry the other half of the contract: ZERO extra publishes
    and a snapshot byte-identical to flag-off (NFR-1)."""
    base_cap, base_job, _eng, base_publishes = _run(
        monkeypatch, breaker=False, signal_v2=signal_v2)
    baseline = copy.deepcopy(_payloads(base_job))
    assert baseline, "harness must serve a deck for this test to mean anything"

    stub = _Stub(narrate=narrate)
    cap, job, _eng2, publishes = _run(
        monkeypatch, breaker=breaker, narrative=narrative,
        signal_v2=signal_v2, stub=stub if breaker else None)
    cards = _payloads(job)

    if not expect_sentence:
        # No key anywhere, snapshot identical to flag-off, and — the NFR-1
        # half — not one extra publish attempt.
        assert all("breaker" not in c for c in cards)
        assert cards == baseline
        assert publishes == base_publishes
    else:
        narrated = [c for c in cards if "breaker" in c]
        assert narrated, "the seam republish is the only carrier when v2 is off"
        for c in narrated:
            assert c["breaker"]["sentence"] == SENTENCE
            assert set(c["breaker"]) == {"code", "severity", "sentence"}
        # The republish is additive decoration: same cards, same order.
        assert ([(c["target_user_id"], c["give"], c["receive"])
                 for c in cards]
                == [(c["target_user_id"], c["give"], c["receive"])
                    for c in baseline])
        assert publishes > base_publishes      # exactly the seam's republish

    if breaker:
        assert stub.stamp_calls == 1
        assert stub.narr_calls == (1 if narrative else 0)


def test_seam_republish_is_skipped_when_the_job_is_not_live(monkeypatch):
    """§1.2 contract point: the seam republish is `_job_live`-guarded like
    every other publish site, so a job that dies mid-block publishes
    nothing."""
    stub = _Stub(narrate=2)
    _cap, job, _eng, _n = _run(
        monkeypatch, breaker=True, narrative=True, stub=stub,
        extra=[patch.object(server, "_job_live", lambda j: False)])
    assert stub.stamp_calls == 1               # the stamp still ran…
    assert _payloads(job) == []                # …and nothing was published


# ---------------------------------------------------------------------------
# The two T-1 skips (LLD §1.2 contract point 4)
# ---------------------------------------------------------------------------

def test_seam_skips_the_demo_league(monkeypatch):
    """Consistent with every neighboring mutation layer and the demo-guarded
    impressions calls — and it avoids narrating synthetic demo partners."""
    monkeypatch.setattr(H, "LEAGUE", "league_demo")
    stub = _Stub(narrate=2)
    _cap, job, _eng, _n = _run(monkeypatch, breaker=True, narrative=True,
                               stub=stub)
    assert stub.stamp_calls == 0
    assert all("breaker" not in c for c in _payloads(job))


def test_seam_skips_a_superseded_job(monkeypatch):
    """Pure wasted-compute avoidance (§5.5 E-13) — a superseded deck is never
    served, so it is never evaluated."""
    stub = _Stub(narrate=2)
    _cap, job, _eng, _n = _run(
        monkeypatch, breaker=True, narrative=True, stub=stub,
        extra=[patch.object(server, "_job_superseded", lambda jid: True)])
    assert stub.stamp_calls == 0
    assert all("breaker" not in c for c in _payloads(job))


# ---------------------------------------------------------------------------
# Rung 5 — the outer handler (LLD §1.2 contract point 3)
# ---------------------------------------------------------------------------

def test_rung5_marks_every_card_with_both_markers(monkeypatch):
    """An exception anywhere in the block — the import line included — stamps
    a minimal marker on EVERY card, primary AND shadow, and the job still
    completes. Read back off the impression rows, which is where the readouts
    see it."""
    stub = _Stub(raise_on_stamp=True)
    capture, job, _eng, _n = _run(monkeypatch, breaker=True, narrative=True,
                                  stub=stub)
    assert capture["status"] == "complete"
    feats = [json.loads(r["features_json"]) for r in capture["impressions"]]
    assert feats
    for f in feats:
        assert f["breaker"] == {"ver": tb.BREAKER_VERSION,
                                "degraded": "exception_outer",
                                "objections": None}
        assert f["breaker_shadow"] == f["breaker"]
    # No sentence can survive a failed stamp.
    assert all("breaker" not in c for c in _payloads(job))


def test_rung5_marker_version_pinned():
    """LLD §7.1 — the seam's hardcoded literal must equal
    `trade_breaker.BREAKER_VERSION`. The literal exists precisely BECAUSE the
    import may be what failed, so it cannot be read from the module."""
    src = inspect.getsource(server._run_trade_job)
    m = re.search(r'"degraded":\s*"exception_outer"', src)
    assert m, "the rung-5 handler is missing from the seam"
    block = src[max(0, m.start() - 200):m.end()]
    vers = re.findall(r'"ver":\s*"([^"]+)"', block)
    assert vers and vers[-1] == tb.BREAKER_VERSION


def test_rung5_handler_reads_no_knob_and_names_no_module():
    """§1.2 contract point 3 made mechanical: the handler is constructible
    with NO breaker state. In `_run_trade_job` the local `trade_service` is
    the per-format TradeService INSTANCE, which has no `_c` — a knob read
    there would be an AttributeError inside an exception handler."""
    src = inspect.getsource(server._run_trade_job)
    start = src.index("except Exception as bk_err:")
    end = src.index("# suggestion.telemetry — split", start)
    handler = "\n".join(l.split("#", 1)[0]
                        for l in src[start:end].splitlines())
    assert "trade_breaker" not in handler
    assert "_c(" not in handler and "stamp_breaker" not in handler
    assert '"exception_outer"' in handler


# ---------------------------------------------------------------------------
# Zero ordering effect + inertness (LLD §7.4, D-11)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path,group_size", [("organic", None),
                                             ("draft", 0),
                                             ("draft", 10)])
def test_breaker_zero_ordering_effect(monkeypatch, path, group_size):
    """The fit `test_fit_diag_inert` contract, at the seam and with the REAL
    module: served deck byte-identical with `trade.breaker` on vs off, on both
    bake-off draft paths and organic. Attribute writes only — the stamp feeds
    nothing the serving path reads."""
    if path == "organic":
        extra = [patch.object(bo, "bakeoff_enabled", lambda: False)]
    else:
        knobs = {"bakeoff_group_size": float(group_size),
                 "bakeoff_deck_limit": 0.0}
        extra = [patch.object(bo, "_cfg",
                              lambda k, d: float(knobs.get(k, d)))]

    off_cap, _j1, _e1, _n1 = _run(monkeypatch, breaker=False, extra=extra)
    on_cap, _j2, _e2, _n2 = _run(monkeypatch, breaker=True, extra=extra)
    # Real module, narrative dark ⇒ the payload cannot change at all.
    assert on_cap["cards"] == off_cap["cards"]
    assert on_cap["card_count"] == off_cap["card_count"]


@pytest.mark.parametrize("bakeoff", [True, False])
def test_every_impression_logged_card_is_stamped(monkeypatch, bakeoff):
    """T-10 at the seam, with the REAL module: the block sits POST-mutation
    stack, so EVERY card the impression logger receives — likes-you
    injections included — leaves the seam carrying the attribute. Absence is
    impossible by construction (M4).

    Parametrized over the two `them`-passthrough branches (D-3): on a bake-off
    deck the M3 fit stamp exists and `them` is copied off `card.fit_diag`
    verbatim; on an ORGANIC deck the M3 stamp never runs and `them` is null on
    every card — the same state a likes-you card is in, because it enters
    after M3. Never recomputed either way."""
    seen = {}
    _real_log = server._log_deck_signal_impressions

    def _spy(*a, **kw):
        seen["cards"] = list(kw.get("cards") or ())
        return _real_log(*a, **kw)

    extra = [patch.object(server, "_log_deck_signal_impressions", _spy)]
    if not bakeoff:
        extra.append(patch.object(bo, "bakeoff_enabled", lambda: False))
    _cap, _job, _eng, _n = _run(monkeypatch, breaker=True, extra=extra)
    cards = seen.get("cards")
    assert cards, "no deck reached the impression logger"
    fit_diags = [getattr(c, "fit_diag", None) for c in cards]
    if bakeoff:
        assert any(fd is not None for fd in fit_diags)
    else:
        assert all(fd is None for fd in fit_diags)   # no M3 stamp at all
    for c, fd in zip(cards, fit_diags):
        bk = getattr(c, "breaker", None)
        assert isinstance(bk, dict) and bk.get("ver") == tb.BREAKER_VERSION
        if bk.get("degraded") is None:
            assert bk.get("them") == (fd or {}).get("them")


def test_breaker_inert_seam_creep_guard():
    """D-11 — nothing outside `server.py` (seam + features + serialization)
    and `trade_breaker.py` may import the module or read the stamps. A
    generator that learns to read `card.breaker` turns an evaluation layer
    into a ranking input, silently."""
    def _offenses(path: Path) -> list:
        """AST, not grep: a docstring that NAMES the module (trade_narrative
        documents who calls its template) is not seam creep — an import or an
        attribute read is."""
        tree = ast.parse(path.read_text())
        bad = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                bad += [a.name for a in node.names if "trade_breaker" in a.name]
            elif isinstance(node, ast.ImportFrom):
                if "trade_breaker" in (node.module or ""):
                    bad.append(node.module)
                bad += [a.name for a in node.names if a.name == "trade_breaker"]
            elif isinstance(node, ast.Attribute):
                if node.attr in ("breaker", "breaker_shadow"):
                    bad.append(f"attr {node.attr}")
            elif isinstance(node, ast.Call):
                fn = getattr(node.func, "id", None)
                if fn in ("getattr", "setattr", "hasattr") and node.args[1:]:
                    a1 = node.args[1]
                    if (isinstance(a1, ast.Constant)
                            and a1.value in ("breaker", "breaker_shadow")):
                        bad.append(f"{fn}(…, {a1.value!r})")
        return bad

    backend = REPO / "backend"
    skip = {"server.py", "trade_breaker.py"}
    files = [p for p in backend.glob("*.py") if p.name not in skip]
    for sub in ("outlook", "eval", "tools"):
        files += list((backend / sub).glob("*.py"))
    assert len(files) > 30
    for path in files:
        assert _offenses(path) == [], path.name

    # Belt: the engine modules by import, not by filename.
    import backend.trade_gen_v2 as tgv2
    import backend.trade_optimizer as topt
    import backend.trade_service as ts
    for mod in (ts, tgv2, topt):
        stripped = "\n".join(l.split("#", 1)[0]
                             for l in inspect.getsource(mod).splitlines())
        assert "trade_breaker" not in stripped


def test_no_breaker_tables():
    """The `breaker_` table prefix is reserved-UNUSED in v1 — no schema
    change, no migration."""
    assert not [t for t in metadata.tables if t.startswith("breaker_")]


def test_bk_sentinel_is_a_fresh_object():
    """LLD §1.4 — a fresh sentinel, never None, so "attribute absent" stays
    distinguishable from any stamped value."""
    assert server._BK_SENTINEL is not None
    assert type(server._BK_SENTINEL) is object


# ---------------------------------------------------------------------------
# The two bulk readers (LLD §2.2) — read-only, one IN(...) select each
# ---------------------------------------------------------------------------

@pytest.fixture
def bulk_db():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    with patch.object(db_module, "engine", engine):
        yield engine


def test_bulk_readers_match_the_singular_loaders(bulk_db):
    """One `IN (...)` select each, per-user shape identical to the singular
    loaders — the whole point is replacing ~2 × 11 per-partner queries on the
    trade-job thread."""
    L, OTHER = "L1", "L2"
    db_module.set_asset_preference("u1", L, "p1", "untouchable")
    db_module.set_asset_preference("u1", L, "p2", "target")
    db_module.set_asset_preference("u2", L, "p3", "not_interested")
    db_module.set_asset_preference("u3", OTHER, "p9", "untouchable")
    db_module.upsert_league_preference("u1", L, "rebuilder",
                                       acquire_positions=["WR"])
    db_module.upsert_league_preference("u3", OTHER, "contender")

    prefs = db_module.load_asset_preferences_bulk(["u1", "u2", "u3"], L)
    assert set(prefs) == {"u1", "u2"}                  # absent users missing
    assert prefs["u1"] == db_module.load_asset_preferences("u1", L)
    assert prefs["u2"] == db_module.load_asset_preferences("u2", L)
    assert prefs["u1"]["untouchables"] == ["p1"]
    assert prefs["u1"]["targets"] == ["p2"]

    lp = db_module.load_league_preferences_bulk(["u1", "u2", "u3"], L)
    assert set(lp) == {"u1"}
    assert lp["u1"] == db_module.load_league_preference("u1", L)
    assert lp["u1"]["team_outlook"] == "rebuilder"

    # League-scoped: another league's rows never leak in.
    assert db_module.load_asset_preferences_bulk(["u3"], L) == {}
    assert db_module.load_league_preferences_bulk(["u3"], L) == {}


def test_bulk_readers_short_circuit_on_an_empty_id_set(bulk_db):
    """An empty served deck (F3 can empty one) must not issue a query."""
    def _boom():
        raise AssertionError("bulk reader queried on an empty id set")

    with patch.object(db_module, "engine", property(lambda self: _boom())):
        assert db_module.load_asset_preferences_bulk([], "L1") == {}
        assert db_module.load_league_preferences_bulk([None], "L1") == {}


def test_breaker_consumes_the_bulk_readers(bulk_db):
    """The module-level lookup in `trade_breaker._bulk_prefs` /
    `_bulk_league_prefs` resolves to the readers this wave landed (they are
    fetched by `getattr` so the module degrades gracefully while a build is
    in flight — this pins that the graceful path is no longer the live one)."""
    db_module.set_asset_preference("u1", "L1", "p1", "untouchable")
    prefs, ok = tb._bulk_prefs(["u1"], "L1")
    assert ok is True
    assert tb._untouchables(prefs["u1"]) == {"p1"}
    db_module.upsert_league_preference("u1", "L1", "contender")
    assert tb._bulk_league_prefs(["u1"], "L1")["u1"]["team_outlook"] == \
        "contender"
