"""Ready durable inventory retains full quality under the strict HTTP contract."""
import pytest

from backend import server
from backend.tests.test_owner_generator_routes import harness, owner_harness, ME, LEAGUE, TOKEN
from backend.tests.test_owner_only_routes import exclusive, large_exclusive
from backend.tests.test_prepared_trade_runtime import prepared, replace_with_empty


@pytest.mark.parametrize('empty', [False, True])
def test_strict_api_adopts_ready_inventory_without_regeneration_and_keeps_all_pages(prepared, monkeypatch, empty):
    fixture, original, *_ = prepared
    client, *_ = fixture
    if empty:
        replace_with_empty(prepared)
    monkeypatch.setattr(server, '_run_trade_job', lambda *a, **k: pytest.fail('ready inventory regenerated'))
    monkeypatch.setattr(server, '_start_trade_job_thread', lambda *, target, args, kwargs: target(*args, **kwargs))
    headers = {'X-Session-Token': TOKEN, 'X-FTF-Current-Only': '1'}
    response = client.post('/api/trades/generate', headers=headers,
        json={'league_id': LEAGUE, 'fairness_threshold': .5, 'page': 1})
    assert response.status_code == 200, response.json
    assert response.json['status'] == 'complete' and response.json['current_validated'] is True
    job = server._trade_jobs[response.json['job_id']]
    assert job['prepared_inventory_id']
    if empty:
        assert response.json['cards'] == []
        return
    expected = [row['runtime']['trade_id'] for row in original['prepared_bundle']['cards']]
    seen = list(response.json['cards'])
    cursor = response.json['cursor']
    while cursor < len(expected):
        page = client.get('/api/trades/status?job_id=' + job['job_id'] + '&deck=' + job['job_id']
                          + '&cursor=' + str(cursor), headers=headers)
        assert page.status_code == 200 and page.json['current_validated'] is True, page.json
        assert page.json['cursor'] > cursor
        seen.extend(page.json['cards'])
        cursor = page.json['cursor']
    assert len(expected) >= 64
    assert [card['trade_id'] for card in seen] == expected
    assert len({card['impression_id'] for card in seen}) == len(expected)
