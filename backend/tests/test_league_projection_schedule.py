from datetime import datetime
import pytest
from backend.league_projections import batch

@pytest.fixture
def weekly(monkeypatch):
    monkeypatch.setattr(batch,'settings',lambda:{'schedule':{'weekday':1,'hour':9,'minute':30,'timezone':'America/New_York'}})

@pytest.mark.parametrize('now,expected',[
    ('2026-03-03T14:30:00+00:00','2026-03-10T13:30:00+00:00'),
    ('2026-10-27T13:30:00+00:00','2026-11-03T14:30:00+00:00'),
    ('2026-11-03T14:29:59+00:00','2026-11-03T14:30:00+00:00'),
    ('2026-11-03T14:30:01+00:00','2026-11-10T14:30:00+00:00'),
    ('2026-11-06T19:00:00+00:00','2026-11-10T14:30:00+00:00'),
])
def test_weekly_wall_time_and_exact_boundary(weekly,now,expected):
    assert batch.next_weekly_slot(datetime.fromisoformat(now))==expected
