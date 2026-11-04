"""#370's series break in trades_generated (analytics-lead 2026-10-26): every
report that reads the event says so when its window includes the break day."""
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

import backend.analytics_queries as aq
import backend.database as db
from backend.database import metadata

BREAK_DAY = "2026-10-26"


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db, "engine", eng), patch.object(db, "ro_engine", eng):
        yield eng


def _breaks(env):
    return [c for c in env["caveats"] if c.get("code") == "series_break"]


def test_the_370_break_is_declared_once():
    assert [b for b in aq.SERIES_BREAKS if b[1] == "trades_generated"] == [
        (BREAK_DAY, "trades_generated", "#370: Calibration refresh decks stop emitting trades_generated")]


@pytest.mark.parametrize("start, end, flagged", [
    ("2026-10-20", "2026-11-01", True),     # spans it
    ("2026-10-26", "2026-11-01", True),     # starts on the break day (mixed)
    ("2026-10-19", "2026-10-26", True),     # ends on it
    ("2026-10-01", "2026-10-25", False),    # all before
    ("2026-10-27", "2026-11-03", False),    # all after
])
def test_the_caveat_follows_the_window(start, end, flagged):
    got = aq._series_break_caveats(start, end, ["trades_generated"])
    assert bool(got) is flagged
    if flagged:
        assert got == [{"code": "series_break", "scope": "event:trades_generated",
                        "detail": "#370: Calibration refresh decks stop emitting trades_generated",
                        "day": BREAK_DAY}]


def test_reports_that_do_not_read_the_event_never_carry_it():
    assert aq._series_break_caveats("2026-10-01", "2026-11-30", ["trio_swipe"]) == []


@pytest.mark.parametrize("report", ["overview", "waterfall", "pfo"])
def test_every_trades_generated_reader_carries_it(engine, report):
    spanning, _ = aq.run_report(report, start="2026-10-20", end="2026-11-01")
    assert len(_breaks(spanning)) == 1
    before, _ = aq.run_report(report, start="2026-10-01", end="2026-10-20")
    assert _breaks(before) == []
