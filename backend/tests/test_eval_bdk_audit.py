"""backend.eval.bdk_audit, the B-DK-4..7 production audit (models-lead-launch.md
addendum C §C5): each rule with a violating and a clean card, both
valuation_json shapes, protected cards exempt (each recorded flag), a repeat
breach of protected cards only reported as explained, the repeat window by
displayed position, the U6 audit set (a viewed card past the window audited,
an unviewed one not, "viewed" from outcomes, never a row), a viewed card with
no full row reported by its upgrade_miss_cards cause (`other` when absent),
the not-auditable paths never reading as 0, skipped decks, the
no-threshold-literal source check, each exit status, the read-only guard, and
that the module never imports backend.server.

In-memory SQLite DBs built with the v5 tests' helpers; the CLI tests write the
same tables to a temporary file and read it through flip_read's read-only
engine.
"""

import ast
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import MetaData, create_engine, insert, text

import backend.deck_quality as dq
import backend.eval.bdk_audit as ba
import backend.eval.flip_read as fr
from backend.database import deck_impressions_table, deck_outcomes_table
from backend.eval.bdk_audit import (
    FAIL, INCOMPLETE, NOT_AUDITABLE, PASS, ReadOnlyViolation, audit, main, render,
)
from backend.tests.test_eval_pack_reader import SERVED, _card, _deck_cards, _row, pack_table
from backend.tests.test_eval_withdrawals_and_paging import (
    DB, _after, act, make_db, put_pack, withdraw, withdrawals_table,
)

REPO = Path(__file__).resolve().parents[2]
SINCE = "2026-10-23T00:00:00+00:00"
AS_OF = _after(2)
W, CAP = dq.REPEAT_WINDOW, dq.REPEAT_CAP

# Market values from deck_quality's own thresholds: a clean pair is HEAD for
# HEAD; LOW breaks a HEAD piece up but is no filler; FILL is filler.
HEAD = 2000.0
LOW = HEAD * dq.BREAKUP_MIN_RATIO * 0.9
FILL = dq.FILLER_FLOOR / 2


def shape(rule, job, i):
    """(give, receive) {asset id: market} for a card tripping `rule` (None: clean)."""
    g, r = f"{job}-g{i}", f"{job}-r{i}"
    return {"breakup": ({g: HEAD}, {r: LOW}),
            "filler": ({g: HEAD}, {r: HEAD, f"{job}-f{i}": FILL}),
            None: ({g: HEAD}, {r: HEAD})}[rule]


def row(job, i, give=None, receive=None, *, valuation="policy", source_like=None,
        full=True, **features):
    """A served deck_impressions row at card_index i: assets_json from the give /
    receive maps (full=False: none, as a packed card's upgrade miss writes),
    valuation_json in the personal-market snapshot's shape ("policy"), the
    value core's ("value_core") or none (None), `features` merged into
    features_json, and the source_like_impression_id column."""
    if give is None:
        give, receive = shape(None, job, i)
    sides = {"give": give, "receive": receive}
    val = ({"assets": {s: [{"id": a, "market_value": v} for a, v in m.items()]
                       for s, m in sides.items()}} if valuation == "policy"
           else {"assets": [{"id": a, "side": s, "market": v} for s, m in sides.items()
                            for a, v in m.items()]} if valuation == "value_core" else None)
    return {**_row({**_card(job, i), **features}),
            "assets_json": json.dumps({s: list(m) for s, m in sides.items()}) if full else None,
            "valuation_json": json.dumps(val) if full and val else None,
            "source_like_impression_id": source_like}


def with_x(job, i, **kw):
    """A clean card that also gives asset X."""
    return row(job, i, {f"{job}-g{i}": HEAD, "X": HEAD}, {f"{job}-r{i}": HEAD}, **kw)


def deck(db: DB, job, n, special=None, *, skip=(), viewed=(), served_at=SERVED):
    """Rows for 0..n-1 not in `skip`: a clean card unless `special` maps the
    index to a row; a viewed outcome per index in `viewed`."""
    special = special or {}
    rows = [special.get(i) or row(job, i) for i in range(n) if i not in skip]
    for r in rows:
        r["served_at"] = served_at
    with db.eng.begin() as conn:
        conn.execute(insert(db.imp), rows)
    for i in viewed:
        act(db, job, i, "viewed", at=served_at)


def run(db: DB, **kw):
    return audit(db.eng, since=kw.pop("since", SINCE), as_of=AS_OF, **kw)


# ---------------------------------------------------------------------------
# The per-card rules (B-DK-4, B-DK-5)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("valuation", ["policy", "value_core"])
@pytest.mark.parametrize("rule, other", [("breakup", "filler"), ("filler", "breakup")])
def test_each_value_rule_counts_a_violating_card_and_passes_a_clean_one(rule, other, valuation):
    give, receive = shape(rule, "d", 1)
    rule_fn = {"breakup": dq._breakup, "filler": dq._filler}
    assert rule_fn[rule](list(give), list(receive), {**give, **receive}.get)
    assert not rule_fn[other](list(give), list(receive), {**give, **receive}.get)
    db = make_db()
    deck(db, "d", 3, {i: row("d", i, *shape(rule if i == 1 else None, "d", i),
                             valuation=valuation) for i in range(3)})
    r = run(db)
    hit, miss = r.rules[rule], r.rules[other]
    assert (hit["violations"], hit["audited"], hit["not_auditable"], hit["status"]) == (
        1, 3, 0, FAIL)
    assert hit["examples"] == [{"deck_job_id": "d", "card_index": 1, "position": 1,
                                "trade_hash": f"{1:016x}"}]
    assert (miss["violations"], miss["audited"], miss["status"]) == (0, 3, PASS)
    assert r.overall == FAIL and hit["bdk"] == {"breakup": "B-DK-4", "filler": "B-DK-5"}[rule]
    assert f"| {hit['bdk']} | {rule}: " in render(r)


@pytest.mark.parametrize("flag", [{"likes_you": True}, {"standing_offer": True},
                                  {"wildcard": True}, {"source_like": "other-card:0"}],
                         ids=["likes_you", "standing_offer", "wildcard", "source_like"])
def test_a_protected_card_is_exempt(flag):
    """Each protection the served row records (features_json, or the
    source_like_impression_id column) exempts a breakup card; the same card
    unprotected in another deck is a violation."""
    db = make_db()
    deck(db, "p", 2, {1: row("p", 1, *shape("breakup", "p", 1), **flag)})
    deck(db, "u", 2, {1: row("u", 1, *shape("breakup", "u", 1))})
    t = run(db).rules["breakup"]
    assert (t["violations"], t["protected"], t["audited"]) == (1, 1, 3)
    assert [e["deck_job_id"] for e in t["examples"]] == ["u"]


# ---------------------------------------------------------------------------
# B-DK-6: not auditable from evidence
# ---------------------------------------------------------------------------

def test_redundant_is_not_auditable_and_never_reads_as_zero():
    """Rosters and lineup slots aren't recorded at serve time: B-DK-6 counts
    the non-protected cards it couldn't check, its violations are None (never
    0), and the read is INCOMPLETE, not a pass, even with nothing else wrong."""
    db = make_db()
    te = {"likes_you": False, "give_positions": ["TE"], "receive_positions": ["TE"]}
    deck(db, "d", 4, {2: row("d", 2, **te), 3: row("d", 3, likes_you=True)})
    r = run(db)
    t = r.rules["redundant"]
    assert (t["violations"], t["audited"], t["not_auditable"], t["protected"]) == (None, 0, 3, 1)
    assert t["status"] == NOT_AUDITABLE and r.overall == INCOMPLETE
    assert all(r.rules[k]["status"] == PASS for k in ("breakup", "filler", "repeat"))
    text_ = render(r)
    assert "| B-DK-6 | redundant: " in text_ and "| n/a | 0 | 1 | 3 | 0 | NOT_AUDITABLE |" in text_
    assert "B-DK-6 redundant is NOT AUDITABLE from evidence: 3 cards couldn't be checked." in text_
    assert "not recorded at serve time" in r.evidence["rosters_lineup"]


@pytest.mark.parametrize("mixed", [False, True], ids=["none_valued", "one_valued"])
def test_a_card_without_per_asset_markets_is_not_auditable_for_the_value_rules(mixed):
    """valuation_json is NULL while trade.valuation_telemetry and the market
    policy are off. A breakup card without it is unchecked, never a pass: with
    nothing checked the rule is NOT_AUDITABLE (violations None); with some
    checked it is INCOMPLETE."""
    db = make_db()
    deck(db, "d", 3, {0: row("d", 0, valuation="policy" if mixed else None),
                      1: row("d", 1, *shape("breakup", "d", 1), valuation=None),
                      2: row("d", 2, valuation=None)})
    r = run(db)
    for name in ("breakup", "filler"):
        t = r.rules[name]
        assert t["not_auditable"] == 2 + (not mixed) and t["audited"] == int(mixed)
        if mixed:
            assert (t["violations"], t["status"]) == (0, INCOMPLETE)
        else:
            assert (t["violations"], t["status"]) == (None, NOT_AUDITABLE)
    assert r.overall == INCOMPLETE


# ---------------------------------------------------------------------------
# B-DK-7: the repeat cap over the first REPEAT_WINDOW displayed cards
# ---------------------------------------------------------------------------

def test_repeat_counts_an_asset_over_the_cap_in_the_window():
    """X in CAP + 1 window cards is a breach; in CAP window cards plus one
    past the window it is not."""
    db = make_db()
    deck(db, "rep", W, {i: with_x("rep", i) for i in range(CAP + 1)})
    deck(db, "ok", W + 1, {**{i: with_x("ok", i) for i in range(CAP)}, W: with_x("ok", W)})
    t = run(db).rules["repeat"]
    assert (t["violations"], t["explained"], t["audited"], t["status"]) == (1, 0, 2 * W, FAIL)
    assert t["examples"] == [{"deck_job_id": "rep", "asset": "X",
                              "card_indexes": list(range(CAP + 1)),
                              "over_cap_protected": [False], "ghost_slots": 0,
                              "withdrawn_removed": 0}]


def test_a_repeat_breach_of_protected_cards_only_is_explained():
    """_repeat_cap lets protected cards hold their positions: an over-cap
    appearance on a protected card is explained, not a violation. Protected
    cards still count toward the cap, so a later unprotected one breaches."""
    db = make_db()
    deck(db, "ok", W, {**{i: with_x("ok", i) for i in range(CAP)},
                       CAP: with_x("ok", CAP, likes_you=True)})
    deck(db, "bad", W, {**{i: with_x("bad", i, wildcard=True) for i in range(CAP)},
                        CAP: with_x("bad", CAP)})
    r = run(db)
    t = r.rules["repeat"]
    assert (t["violations"], t["explained"]) == (1, 1)
    assert [(e["deck_job_id"], e["over_cap_protected"]) for e in t["explained_examples"]] == [
        ("ok", [True])]
    assert [(e["deck_job_id"], e["over_cap_protected"]) for e in t["examples"]] == [
        ("bad", [False])]
    assert "(explained by protected cards: 1)" in render(r)


def test_the_repeat_window_is_by_displayed_position():
    """A never-delivered withdrawal at index 2 moves card W up to displayed
    position W - 1, inside the window: X there is a fourth appearance."""
    db = make_db()
    deck(db, "w", W + 1, {**{i: with_x("w", i) for i in (10, 11, 12)}, W: with_x("w", W)},
         skip={2})
    withdraw(db, "w", 2, 0, reason="disposition_cut")
    t = run(db).rules["repeat"]
    assert t["violations"] == 1 and t["audited"] == W
    assert t["examples"][0]["card_indexes"] == [10, 11, 12, W]
    assert t["examples"][0]["withdrawn_removed"] == 1


# ---------------------------------------------------------------------------
# The U6 audit set and the viewed cards with no full row (U4-R3)
# ---------------------------------------------------------------------------

def test_a_viewed_card_past_the_window_is_audited_and_an_unviewed_one_is_not():
    """Both past the window, both breakup cards with full rows: only the one
    with a `viewed` outcome is in the audit set."""
    db = make_db()
    deck(db, "d", W + 3, {W + 1: row("d", W + 1, *shape("breakup", "d", W + 1)),
                          W + 2: row("d", W + 2, *shape("breakup", "d", W + 2))},
         viewed=[0, W + 1])
    r = run(db)
    assert (r.audit_cards, r.viewed_past_window) == (W + 1, 1)
    t = r.rules["breakup"]
    assert (t["violations"], t["audited"]) == (1, W + 1)
    assert [e["card_index"] for e in t["examples"]] == [W + 1]


@pytest.mark.parametrize("mapped", [True, False], ids=["miss_map", "no_miss_map"])
def test_a_viewed_card_with_no_full_row_is_reported_by_cause(mapped):
    """Rows for the window, a pack of every card past it: a viewed packed card
    and a viewed card whose row the upgrade miss built from the pack (no
    assets) are reported by their upgrade_miss_cards cause; a card with no
    entry, or a pack with no map, reads other. They count as not auditable,
    and an unviewed packed card is not in the audit set at all."""
    db = make_db()
    n = W + 10
    deck(db, "pk", W, viewed=[0, W + 3, W + 4, W + 5])
    with db.eng.begin() as conn:
        conn.execute(insert(db.imp), [row("pk", W + 5, full=False)])
    misses = {str(W + 3): "restart_split", str(W + 5): "evicted_split"}
    put_pack(db, "pk", _deck_cards("pk", n)[W:], card_count=n, deliveries=[[n - 1, SERVED]],
             **({"upgrade_miss_cards": misses} if mapped else {}))
    r = run(db)
    nf = r.no_full_row
    expect = ({"evicted_split": 1, "other": 1, "restart_split": 1} if mapped else {"other": 3})
    assert nf["viewed_by_cause"] == expect and nf["unviewed"] == 0
    assert [(e["card_index"], e["cause"]) for e in nf["examples"]] == [
        (W + 3, "restart_split" if mapped else "other"), (W + 4, "other"),
        (W + 5, "evicted_split" if mapped else "other")]
    assert r.audit_cards == W + 3 and r.decks == 1
    for name in ("breakup", "filler"):
        assert r.rules[name]["not_auditable"] == 3 and r.rules[name]["status"] == INCOMPLETE
    assert r.rules["repeat"]["status"] == PASS and r.overall == INCOMPLETE
    assert "Viewed, no full row (U4-R3), by cause: " in render(r)


def test_an_unviewed_window_card_with_no_full_row_leaves_its_deck_incomplete():
    """A window card with no assets (a packed card moved up by a withdrawal)
    can't be checked: not auditable for every rule, and its deck's repeat
    window incomplete."""
    db = make_db()
    deck(db, "d", W, {5: row("d", 5, full=False)})
    r = run(db)
    assert r.no_full_row["unviewed"] == 1 and r.no_full_row["viewed_by_cause"] == {}
    t = r.rules["repeat"]
    assert (t["not_auditable"], t["incomplete_decks"], t["status"]) == (1, 1, INCOMPLETE)
    assert r.rules["breakup"]["not_auditable"] == 1


# ---------------------------------------------------------------------------
# Which decks, and the overall verdict
# ---------------------------------------------------------------------------

def _all_protected(db: DB, job="safe", n=4):
    deck(db, job, n, {i: row(job, i, likes_you=True) for i in range(n)})


def test_every_card_exempt_or_checked_and_no_violation_passes():
    db = make_db()
    _all_protected(db)
    r = run(db)
    assert {k: t["status"] for k, t in r.rules.items()} == dict.fromkeys(r.rules, PASS)
    assert r.overall == PASS and r.notes == []


def test_untrusted_decks_are_skipped_and_counted_and_refresh_decks_left_out():
    """A withdrawal_conflict deck's positions can't be trusted: skipped,
    counted, and the read is not a pass. A Calibration refresh deck isn't a
    Trades deck: not audited, not counted."""
    db = make_db()
    _all_protected(db)
    deck(db, "refresh", 3, {i: row("refresh", i, deck_source="grading_refresh")
                            for i in range(3)})
    deck(db, "conflict", 3, viewed=[1])
    withdraw(db, "conflict", 1, 0)           # never delivered, yet viewed
    r = run(db)
    assert (r.decks, r.skipped_decks) == (1, {"withdrawal_conflict": 1})
    assert r.overall == INCOMPLETE
    assert "Skipped decks (displayed positions untrustworthy; G1 / G8 signals): " \
           "withdrawal_conflict=1" in render(r)


def test_nothing_to_audit_is_not_a_pass_and_an_early_since_is_noted():
    db = make_db()
    r = run(db, since="2026-10-01T00:00:00+00:00")
    assert {t["status"] for t in r.rules.values()} == {NOT_AUDITABLE}
    assert all(t["violations"] is None for t in r.rules.values())
    assert r.overall == INCOMPLETE
    assert r.notes == [f"--since 2026-10-01T00:00:00+00:00 is before deck.quality_filters "
                       f"went live ({ba.FILTERS_LIVE_AT}): earlier decks were served "
                       "unfiltered."]


# ---------------------------------------------------------------------------
# Source checks
# ---------------------------------------------------------------------------

def test_no_threshold_literal_appears_in_the_module():
    """Every threshold is imported from deck_quality. A numeric literal equal
    to one is allowed only as an exit code (EXIT: 3 is INCOMPLETE, and
    REPEAT_CAP is 3); none may appear in the text either."""
    source = Path(ba.__file__).read_text()
    tree = ast.parse(source)
    thresholds = {dq.BREAKUP_MIN_RATIO, dq.FILLER_FLOOR, dq.FILLER_FRAC,
                  dq.REDUNDANT_MIN_RATIO, dq.REPEAT_WINDOW, dq.REPEAT_CAP}
    exit_map = next(n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                    and any(getattr(t, "id", None) == "EXIT" for t in n.targets))
    allowed = {id(n) for n in ast.walk(exit_map)}
    restated = [(n.lineno, n.value) for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and type(n.value) in (int, float)
                and n.value in thresholds and id(n) not in allowed]
    assert restated == []
    for value in (dq.BREAKUP_MIN_RATIO, dq.FILLER_FLOOR, dq.FILLER_FRAC,
                  dq.REDUNDANT_MIN_RATIO, dq.REPEAT_WINDOW):
        text_forms = {f"{value:g}", repr(value), f"{value:.2f}"}
        for form in text_forms:
            assert not re.search(rf"(?<![\w.]){re.escape(form)}(?![\w])", source), form
    for name in ("_breakup", "_filler", "is_protected", "REPEAT_CAP", "REPEAT_WINDOW",
                 "BREAKUP_MIN_RATIO", "FILLER_FLOOR", "FILLER_FRAC", "REDUNDANT_MIN_RATIO"):
        assert getattr(ba, name) is getattr(dq, name)


def test_the_unrecorded_protections_are_deck_qualitys_less_the_recorded_ones():
    assert ba.UNRECORDED_PROTECTION == ("injected", "fatigue_retest", "retest",
                                        "owner_published")
    assert set(ba.UNRECORDED_PROTECTION) | set(ba._RECORDED_FEATURES) | {
        "source_like_impression_id"} == set(dq.PROTECTED_ATTRS)


def test_importing_bdk_audit_never_imports_the_server():
    code = "import sys, backend.eval.bdk_audit; print('backend.server' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True,
                         text=True, check=True)
    assert out.stdout.strip() == "False"


# ---------------------------------------------------------------------------
# CLI: exit statuses, read-only, redaction, the settle clamp
# ---------------------------------------------------------------------------

def _file_db(path) -> DB:
    md = MetaData()
    imp = deck_impressions_table.to_metadata(md)
    deck_outcomes_table.to_metadata(md)
    packs, wd = pack_table(md), withdrawals_table(md)
    eng = create_engine(f"sqlite:///{path}")
    md.create_all(eng)
    return DB(eng, packs, wd, imp)


def _cli(path, *extra):
    return main(["--db", str(path), "--since", SINCE, "--as-of", AS_OF, *extra])


@pytest.mark.parametrize("build, code, overall", [
    (lambda db: _all_protected(db), 0, PASS),
    (lambda db: deck(db, "d", 3), 3, INCOMPLETE),
    (lambda db: deck(db, "d", 3, {1: row("d", 1, *shape("filler", "d", 1))}), 1, FAIL),
], ids=["pass", "incomplete", "fail"])
def test_the_cli_reads_a_sqlite_file_read_only_and_exits_by_the_verdict(
        tmp_path, capsys, build, code, overall):
    path = tmp_path / "audit.db"
    db = _file_db(path)
    build(db)
    db.eng.dispose()
    before = path.read_bytes()
    assert _cli(path) == code
    assert f"OVERALL: {overall}" in capsys.readouterr().out
    assert _cli(path, "--json") == code
    got = json.loads(capsys.readouterr().out)
    assert got["overall"] == overall and set(got["rules"]) == {
        "breakup", "filler", "redundant", "repeat"}
    assert path.read_bytes() == before

    eng = fr.read_only_engine(str(path))
    try:
        with pytest.raises(ReadOnlyViolation):
            with eng.begin() as conn:
                conn.execute(text("DELETE FROM deck_outcomes"))
    finally:
        eng.dispose()


def test_a_read_only_violation_inside_the_read_exits_2(tmp_path, capsys, monkeypatch):
    path = tmp_path / "audit.db"
    _file_db(path).eng.dispose()

    def writes(engine, **_kw):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM deck_outcomes"))

    monkeypatch.setattr(ba, "load_decks", writes)
    assert _cli(path) == 2
    out, err = capsys.readouterr()
    assert out == "" and "bdk_audit: blocked a non-read statement" in err


def test_a_non_sqlite_database_is_refused_without_the_flag(capsys):
    assert main(["--db", "postgresql://reader:hunter2@db.invalid/ftf", "--since", SINCE]) == 2
    err = capsys.readouterr().err
    assert "--allow-postgres-readonly" in err and "hunter2" not in err


def test_a_crash_exits_4_with_the_credentials_redacted(capsys, monkeypatch):
    def refused(url, **_kw):
        raise RuntimeError('could not translate host name "RET123@192.0.2.1" to address')

    monkeypatch.setattr(ba, "read_only_engine", refused)
    assert main(["--db", "postgresql://ftf:SEC@RET123@192.0.2.1:5432/ftf",
                 "--allow-postgres-readonly", "--since", SINCE, "--as-of", AS_OF]) == 4
    out, err = capsys.readouterr()
    assert out == "" and "Traceback (most recent call last)" in err and "***" in err
    for secret in ("SEC", "RET123", "192.0.2.1"):
        assert secret not in err


def test_a_malformed_time_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as usage:
        main(["--db", "unused.db", "--since", "tomorrow"])
    assert usage.value.code == 2
    assert "argument --since: not an ISO 8601 time: 'tomorrow'" in capsys.readouterr().err


def test_the_cli_settles_as_of_behind_the_clock(tmp_path, capsys, monkeypatch):
    clock = datetime.fromisoformat(_after(3))
    settled = (clock - timedelta(minutes=5)).isoformat()
    monkeypatch.setattr(fr, "_now", lambda: clock)
    path = tmp_path / "audit.db"
    _file_db(path).eng.dispose()
    args = ["--db", str(path), "--since", SINCE, "--json"]
    assert main(args) == 3
    out, err = capsys.readouterr()
    assert json.loads(out)["as_of"] == settled and err == ""
    assert main(args + ["--as-of", clock.isoformat()]) == 3
    out, err = capsys.readouterr()
    assert json.loads(out)["as_of"] == settled
    assert err == (f"bdk_audit: note: --as-of {clock.isoformat()} is later than now minus "
                   f"STAMP_SETTLE (5 min); clamped to {settled}\n")


def test_help_documents_the_exit_codes(capsys):
    with pytest.raises(SystemExit) as done:
        main(["--help"])
    assert done.value.code == 0
    out = capsys.readouterr().out
    for line in ("0  PASS", "1  FAIL", "2  a refused database or a ReadOnlyViolation",
                 "3  INCOMPLETE", "4  an unexpected error"):
        assert line in out
