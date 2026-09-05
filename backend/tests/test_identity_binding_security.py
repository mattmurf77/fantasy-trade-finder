"""Security review #1: provider proof cannot claim an unproven Sleeper identity.

Synthetic provider accounts and mocked Sleeper proofs exercise the binding
boundary before board reads or mutations; no upstream network is used.
"""
from unittest.mock import patch
import pytest
from sqlalchemy import select
from backend import server, accounts, database as db
from backend.tests.test_account_first import (
    client, _mock_jwks, _post_apple, _sleeper_lookup, _seed_board, _swipe_uids, SLEEPER_UID,
)


def test_unrelated_provider_does_not_verify_username_session(client):
    c, engine, _ = client
    _seed_board(engine, SLEEPER_UID, swipes=1)
    token = 'synthetic-unverified-session'
    sess = {'user_id': SLEEPER_UID, 'verified': False}
    server._sessions[token] = sess
    response = _post_apple(c, headers={'X-Session-Token': token})
    assert response.status_code == 200
    body = response.get_json()
    assert body['account_only'] is True
    assert body['user_id'].startswith('acct_')
    assert sess['verified'] is False
    assert accounts.get_account_for_user(SLEEPER_UID) is None
    assert _swipe_uids(engine) == [SLEEPER_UID]


@pytest.mark.parametrize('failure', ['missing', 'mismatch', 'expired', 'rejected', 'outage'])
def test_new_source_requires_proof_before_board_access(client, failure):
    c, engine, _ = client
    account = _post_apple(c).get_json()
    _seed_board(engine, SLEEPER_UID, swipes=1)
    body = {'username': 'realmanager', 'strategy': 'keep_account'}
    if failure != 'missing':
        body['sleeper_token'] = 'synthetic-proof'
    with patch.object(server, '_sleeper_get', _sleeper_lookup), \
         patch.object(server._sleeper_write, 'is_expired', return_value=failure == 'expired'), \
         patch.object(server._sleeper_write, 'token_sleeper_user_id', return_value='other' if failure == 'mismatch' else SLEEPER_UID), \
         patch.object(server._sleeper_write, 'verify_token_live') as oracle, \
         patch.object(accounts, 'board_data_summary', side_effect=AssertionError('private board read before proof')):
        if failure == 'rejected':
            oracle.side_effect = server._sleeper_write.SleeperAuthError('synthetic rejection')
        elif failure == 'outage':
            oracle.side_effect = server._sleeper_write.SleeperWriteError('transport', detail='synthetic outage')
        response = c.post('/api/account/link-sleeper', json=body,
                          headers={'X-Session-Token': account['session_token']})
    assert response.status_code == (503 if failure == 'outage' else 403)
    assert accounts.get_account(account['account_id'])['sleeper_user_id'] is None
    assert _swipe_uids(engine) == [SLEEPER_UID]
