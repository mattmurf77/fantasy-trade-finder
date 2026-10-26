"""blind_grade.served_card_set reads served decks as eval does (models-lead B5).

Trades decks only (a Calibration refresh deck is skipped), never-delivered
withdrawn cards removed, not-yet-paged first30 rows kept, the top N by
displayed position, a chosen card without a full row skipped and counted,
and a league with no gradeable deck, or whose deck yields no card, named.
An in-memory SQLite stands in for prod; it answers SHOW transaction_read_only
like a read-only Postgres session (or, for the guard test, a writable one).
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import MetaData, create_engine, event, insert

from backend import database as db
from backend.eval import blind_grade
from backend.eval import data as eval_data
from backend.eval import evidence_pack as ep
from backend.tests.test_eval_pack_reader import _card, _row, insert_pack, pack_table
from backend.tests.test_eval_withdrawals_and_paging import withdrawals_table
from backend.tools import prod_analytics

SHOW = "SHOW transaction_read_only"
NOW = datetime.now(timezone.utc)


def _ago(hours: float) -> str:
    """ISO UTC, `hours` before now: inside served_card_set's lookback."""
    return (NOW - timedelta(hours=hours)).isoformat()


class Prod:
    """The tables served_card_set and load_decks read, in one SQLite engine.
    `sql` records every statement served_card_set runs, in order."""

    def __init__(self, read_only: str = "on"):
        self.eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        db.metadata.create_all(self.eng, tables=[db.deck_impressions_table, db.deck_outcomes_table,
                                                 db.leagues_table, db.players_table])
        md = MetaData()
        self.packs, self.wd = pack_table(md), withdrawals_table(md)
        md.create_all(self.eng)
        with self.eng.begin() as conn:
            conn.execute(insert(db.leagues_table).values(
                sleeper_league_id="lg", user_id="u1", name="Served League"))
            conn.execute(insert(db.players_table), [
                {"player_id": "T-g0", "full_name": "Top Giver", "position": "WR"},
                {"player_id": "T-r0", "full_name": "Top Getter", "position": "RB"}])
        self.sql: list[str] = []
        self.recording = False

        @event.listens_for(self.eng, "before_cursor_execute", retval=True)
        def _read_only_session(conn, cursor, statement, parameters, context, executemany):
            if self.recording:
                self.sql.append(statement)
            if statement.strip() == SHOW:
                return f"SELECT '{read_only}'", ()
            return statement, parameters

    def connect_readonly(self, url, timeout):
        self.recording = True
        return self.eng


@pytest.fixture
def prod(monkeypatch):
    def make(read_only="on"):
        fake = Prod(read_only)
        monkeypatch.setattr(prod_analytics, "_load_prod_url", lambda: "postgresql://prod")
        monkeypatch.setattr(prod_analytics, "_connect_readonly", fake.connect_readonly)
        monkeypatch.setattr(db, "engine", None)   # the loader never falls back to the app DB
        return fake
    return make


def put_deck(prod: Prod, job: str, n: int, *, served_at: str, rows=None, tier="first30",
             delivered=(), no_assets=(), w0=(), w1=(), source=None):
    """A deck of n built cards: full rows (assets and valuation) for `rows`
    (default every index not in w0), `tier` and delivered_at on the indexes
    in `delivered`, no assets_json on `no_assets`, deck_source `source`, and
    withdrawals: w0 served_before=0, w1 served_before=1."""
    rows = [i for i in range(n) if i not in w0] if rows is None else rows
    out = []
    for i in rows:
        card = _card(job, i, served_at=served_at)
        if source is not None:
            card["deck_source"] = source
        out.append({**_row(card), "evidence_tier": tier,
                    "delivered_at": served_at if i in delivered else None,
                    "assets_json": None if i in no_assets else json.dumps(
                        {"give": [f"{job}-g{i}"], "receive": [f"{job}-r{i}"]}),
                    "valuation_json": json.dumps({"assets": [
                        {"id": f"{job}-g{i}", "market": 1000.0 + i},
                        {"id": f"{job}-r{i}", "market": 1100.0 + i}]})})
    with prod.eng.begin() as conn:
        conn.execute(insert(db.deck_impressions_table), out)
        for served_before, indexes in ((0, w0), (1, w1)):
            for i in indexes:
                conn.execute(insert(prod.wd).values(
                    deck_job_id=job, card_index=i, user_id="u1", league_id="lg",
                    reason="disposition_cut", first_withdrawn_at=served_at,
                    served_before=served_before))


def served(**kw) -> dict:
    return blind_grade.served_card_set(secrets=Path("unused.env"), league_ids=["lg"],
                                       user_id="u1", **kw)


def shown(card_set) -> list[str]:
    """Each card's give id: '<deck>-g<card_index>'."""
    return [card["give"][0]["id"] for card in card_set["cards"]]


def test_a_newer_refresh_deck_is_skipped_for_the_older_trades_deck(prod):
    fake = prod()
    put_deck(fake, "T", 4, served_at=_ago(3), delivered=range(4))
    put_deck(fake, "R", 4, served_at=_ago(1), tier=None,
             source=eval_data.CALIBRATION_REFRESH_SOURCE)
    card_set = served()
    assert shown(card_set) == ["T-g0", "T-g1", "T-g2", "T-g3"]
    assert card_set["skipped_no_row"] == 0
    assert (card_set["variant"], card_set["source"]) == ("incumbent", "served")
    first = card_set["cards"][0]
    assert first["league"] == "Served League" and first["seat"] == "u1"
    assert first["partner"] == "opp0"
    assert first["give"] == [{"id": "T-g0", "name": "Top Giver", "position": "WR",
                              "market": 1000.0}]
    assert first["receive"][0]["name"] == "Top Getter"
    # The guard ran first, and the loader read through the engine it vetted.
    assert fake.sql[0] == SHOW
    assert any("deck_impressions" in s and "served_at >=" in s for s in fake.sql[1:])


def test_top_n_is_by_displayed_position_after_never_delivered_withdrawals(prod):
    fake = prod()
    # Index 2 was dropped before it was written (I-1, C-b); index 4 is a cut
    # whose undelivered first30 row is present. Both are W0.
    put_deck(fake, "T", 8, served_at=_ago(2), rows=[0, 1, 3, 4, 5, 6, 7],
             delivered=[0, 1, 3, 5, 6, 7], w0=[2, 4])
    card_set = served(top=5)
    assert shown(card_set) == ["T-g0", "T-g1", "T-g3", "T-g5", "T-g6"]
    assert card_set["skipped_no_row"] == 0


def test_a_withdrawn_card_delivered_before_keeps_its_place(prod):
    fake = prod()
    put_deck(fake, "T", 5, served_at=_ago(2), delivered=range(5), w1=[1])
    assert shown(served(top=3)) == ["T-g0", "T-g1", "T-g2"]


def test_not_yet_paged_first30_rows_are_kept(prod):
    fake = prod()
    put_deck(fake, "T", 6, served_at=_ago(2), delivered=[0, 1])   # page 1 only so far
    assert shown(served()) == [f"T-g{i}" for i in range(6)]


def test_a_chosen_card_without_a_full_row_is_skipped_and_counted(prod, tmp_path, capsys):
    fake = prod()
    # Rows for the first page; the in-flight pack holds the whole build, so
    # cards 3-5 are packed only. Row 1 has no assets_json.
    put_deck(fake, "T", 3, served_at=_ago(2), delivered=range(3), no_assets=[1])
    run = ep.pack_run({"values_snapshot_id": "vsn1:t", "built_at": _ago(2),
                       "deliveries": [[2, _ago(2)]], "retired": False, "page_store": 1},
                      [_card("T", i, served_at=_ago(2)) for i in range(6)], card_count=6)
    with fake.eng.begin() as conn:
        insert_pack(conn, fake.packs, run_id="T", user_id="u1", league_id="lg",
                    served_at=_ago(2), packed=run)
    out = tmp_path / "served.json"
    assert blind_grade.main(["served", "--secrets", str(tmp_path / "s.env"), "--user", "u1",
                             "--league", "lg", "--output", str(out), "--top", "5"]) == 0
    card_set = json.loads(out.read_text())
    assert shown(card_set) == ["T-g0", "T-g2"]           # never filled from card 5
    assert card_set["skipped_no_row"] == 3                # 1 (no assets), 3 and 4 (packed)
    assert json.loads(capsys.readouterr().out) == {"cards": 2, "leagues": 1,
                                                   "skipped_no_row": 3, "leagues_without_deck": [],
                                                   "leagues_with_no_cards": []}


def test_the_read_only_check_still_fires(prod):
    fake = prod(read_only="off")
    put_deck(fake, "T", 3, served_at=_ago(2), delivered=range(3))
    with pytest.raises(ValueError, match="transaction_read_only is not on"):
        served()
    assert fake.sql == [SHOW]                             # nothing read before it


@pytest.mark.parametrize("user, leagues", [("", ["lg"]), ("u1", ["lg", ""])])
def test_an_empty_scope_is_refused_before_connecting(monkeypatch, user, leagues):
    monkeypatch.setattr(prod_analytics, "_connect_readonly",
                        lambda url, timeout: pytest.fail("connected"))
    with pytest.raises(ValueError):
        blind_grade.served_card_set(secrets=Path("unused.env"), league_ids=leagues,
                                    user_id=user)


def test_refresh_decks_are_detected_through_the_pinned_constant_only():
    source = Path(blind_grade.__file__).read_text()
    assert eval_data.CALIBRATION_REFRESH_SOURCE not in source
    assert "CALIBRATION_REFRESH" in source


def test_a_deck_whose_evidence_contradicts_itself_is_not_graded(prod):
    """A newer withdrawal_conflict deck (a never-delivered withdrawal whose row
    says it was delivered) is skipped: the loader leaves its withdrawn cards
    in, so its top N could hold cards nobody saw. The older clean deck is
    graded instead."""
    fake = prod()
    put_deck(fake, "T", 4, served_at=_ago(3), delivered=range(4))
    put_deck(fake, "C", 4, served_at=_ago(1), rows=range(4), delivered=range(4), w0=[1])
    assert shown(served()) == ["T-g0", "T-g1", "T-g2", "T-g3"]


def test_a_league_without_a_gradeable_deck_is_named_not_silent(prod):
    """#423 QA P3: a league with no Trades deck in SERVED_LOOKBACK yields no
    cards, and the CardSet names it rather than leaving a silent zero."""
    fake = prod()
    put_deck(fake, "T", 3, served_at=_ago(2), delivered=range(3))
    card_set = blind_grade.served_card_set(secrets=Path("unused.env"),
                                           league_ids=["lg", "empty-league"], user_id="u1")
    assert shown(card_set) == ["T-g0", "T-g1", "T-g2"]
    assert card_set["leagues_without_deck"] == ["empty-league"]
    assert card_set["leagues_with_no_cards"] == []


def test_a_league_whose_deck_yields_no_gradeable_card_is_named(prod, tmp_path, capsys):
    """#426 QA P3: the latest deck is found, but every chosen card lacks a
    full row, so the league yields 0 cards; before, only the total
    skipped_no_row showed it. It is named in leagues_with_no_cards, apart
    from a league with no deck at all, and the CLI summary prints both."""
    fake = prod()
    put_deck(fake, "T", 3, served_at=_ago(2), delivered=range(3), no_assets=range(3))
    out = tmp_path / "served.json"
    assert blind_grade.main(["served", "--secrets", str(tmp_path / "s.env"), "--user", "u1",
                             "--league", "lg", "--league", "empty-league",
                             "--output", str(out)]) == 0
    card_set = json.loads(out.read_text())
    assert card_set["cards"] == [] and card_set["skipped_no_row"] == 3
    assert card_set["leagues_with_no_cards"] == ["lg"]
    assert card_set["leagues_without_deck"] == ["empty-league"]
    assert json.loads(capsys.readouterr().out) == {
        "cards": 0, "leagues": 2, "skipped_no_row": 3, "leagues_without_deck": ["empty-league"],
        "leagues_with_no_cards": ["lg"]}


def test_the_prod_engine_opens_every_connection_read_only(monkeypatch):
    """#423 QA P3: pins _connect_readonly's startup option, which every
    pooled connection (the loader's included) opens with; before this only
    the runtime SHOW guard caught its removal."""
    import sqlalchemy
    seen = {}

    def fake_create_engine(url, **kw):
        seen.update(kw)
        return object()

    monkeypatch.setattr(sqlalchemy, "create_engine", fake_create_engine)
    prod_analytics._connect_readonly("postgresql://u:p@h/db", 15000)
    assert "-c default_transaction_read_only=on" in seen["connect_args"]["options"]
