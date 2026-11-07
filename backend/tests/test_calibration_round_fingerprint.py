"""Semantic freshness uses actual SQLite readers, synthetic known roster facts."""
import pytest
from backend import database as db, server, outlook_calibration_adapter as adapter
from backend.tests.test_outlook_calibration_persistence import engine

@pytest.fixture
def roster(engine,monkeypatch):
    monkeypatch.setattr(server,'_load_sleeper_cache',lambda:{})
    monkeypatch.setattr(server,'_league_slot_order',lambda lid:{})
    monkeypatch.setattr(server,'_load_presentment_exclusions',lambda *a:set())
    monkeypatch.setattr(server,'g_universal_by_format',{})
    monkeypatch.setattr(adapter,'code_revision',lambda:'frozen-code')
    with engine.begin() as conn:
        conn.execute(db.leagues_table.insert().values(sleeper_league_id='L',user_id='a',default_scoring='1qb_ppr'))
        conn.execute(db.league_members_table.insert(),[
            dict(id=1,league_id='L',user_id='a',roster_data='["p1"]',updated_at='2026-11-01'),
            dict(id=2,league_id='L',user_id='b',roster_data='["p2"]',updated_at='2026-11-01')])

def test_routine_identical_roster_sync_does_not_rebuild_wait_free_exercise(roster,engine):
    before=adapter._input_identity('a','L')
    with engine.begin() as conn:
        conn.execute(db.league_members_table.update().values(updated_at='2026-11-06',id=db.league_members_table.c.id+100))
    assert adapter._input_identity('a','L')==before

def test_actual_roster_change_invalidates_unstarted_exercise(roster,engine):
    before=adapter._input_identity('a','L')
    with engine.begin() as conn:
        conn.execute(db.league_members_table.update().where(db.league_members_table.c.user_id=='b')
                     .values(roster_data='["p3"]'))
    assert adapter._input_identity('a','L')!=before

@pytest.mark.parametrize('field,value', [('position','WR'), ('fantasy_positions',['WR']),
    ('player_id','different'), ('active',False), ('injury_status','IR')])
def test_unranked_occupancy_metadata_changes_invalidate_before_exposure(roster, monkeypatch, field, value):
    facts = {'p1': {'position':'RB', 'fantasy_positions':['RB'], 'player_id':'p1',
                    'active':True, 'injury_status':None}}
    monkeypatch.setattr(server, '_load_sleeper_cache', lambda: facts)
    before = adapter._input_identity('a', 'L')
    facts['p1'][field] = value
    assert adapter._input_identity('a', 'L') != before
