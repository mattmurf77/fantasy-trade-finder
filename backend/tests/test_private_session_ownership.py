"""Security hardening: username claims cannot read, mutate or erase private data.

Exercises extension entry, both rollout-flag values, absent/broken controller
lookups, strict synthetic demo isolation, and verification retry integrity.
All persistence uses scratch SQLite and every external boundary is mocked.
"""
from unittest.mock import patch

import pytest

import backend.accounts as accounts
import backend.database as db
import backend.server as server
from .test_verified_reads import client, _sess, GATED_READS, BARE_SESSION_200_READS
from .test_verified_sessions import UID, _h, _token


@pytest.mark.parametrize('enforce', [False, True])
@pytest.mark.parametrize('controller', [None, 'sleeper', RuntimeError('database unavailable')])
def test_claimed_identity_private_routes_fail_closed(client, enforce, controller):
    c, token, flags = client
    flags.add('account.data_export')
    if enforce:
        flags.add('auth.enforce_verified_writes')
    db.upsert_user(sleeper_user_id=UID)
    db.save_ranking_swipes(user_id=UID, ordered_ids=['1', '2'], scoring_format='1qb_ppr')
    before = db.load_swipe_decisions(user_id=UID, scoring_format='1qb_ppr')
    lookup = ({'side_effect': controller} if isinstance(controller, Exception)
              else {'return_value': controller})
    with patch.object(accounts, 'get_user_verified_via', **lookup), \
         patch.object(accounts, 'export_user_data') as export, \
         patch.object(accounts, 'delete_user_data') as delete:
        for path in ['/api/skips'] + GATED_READS + ['/api/account/export']:
            result = c.get(path, headers=_h(token))
            assert result.status_code == 403, path
            assert result.json['error'] == 'verification_required', path
        for method, path, body in [
            ('post', '/api/ranking-method', {'method': 'trio'}),
            ('post', '/api/trio/skip', {'player_id': '1'}),
            ('post', '/api/share/package', {'give_player_ids': ['1']}),
            ('delete', '/api/account', {}),
        ]:
            result = getattr(c, method)(path, headers=_h(token), json=body)
            assert result.status_code == 403, path
        export.assert_not_called()
        delete.assert_not_called()
    assert db.load_swipe_decisions(user_id=UID, scoring_format='1qb_ppr') == before


def test_extension_username_entry_does_not_grant_private_access(client):
    c, token, flags = client
    flags.add('account.data_export')
    with patch.object(server, '_sleeper_get', side_effect=[{'user_id': UID}, []]), \
         patch.object(server, '_extension_build_session', return_value=(token, _sess(token))), \
         patch.object(server, '_link_device_identity'):
        result = c.post('/api/extension/auth', json={'username': 'public-name'})
    assert result.status_code == 200
    headers = _h(result.json['session_token'])
    for path in ['/api/rankings', '/api/extension/rankings', '/api/account/export']:
        assert c.get(path, headers=headers).status_code == 403
    assert c.delete('/api/account', headers=headers).status_code == 403


@pytest.mark.parametrize('user_id,is_demo,allowed', [
    ('demo_user_security', True, True),
    (UID, True, False),
    ('demo_user_security', False, False),
])
def test_demo_exemption_requires_both_server_marker_and_synthetic_identity(client, user_id, is_demo, allowed):
    c, token, flags = client
    _sess(token).update(user_id=user_id, is_demo=is_demo)
    for path in BARE_SESSION_200_READS:
        assert c.get(path, headers=_h(token)).status_code == (200 if allowed else 403), path
    result = c.post('/api/ranking-method', headers=_h(token), json={'method': 'trio'})
    assert result.status_code == (200 if allowed else 403)
    flags.add('account.data_export')
    assert c.get('/api/account/export', headers=_h(token)).status_code == 400
    assert c.delete('/api/account', headers=_h(token)).status_code == 400


def test_inconclusive_proof_cannot_overwrite_existing_credential(client):
    c, token, _ = client
    db.upsert_sleeper_credential(UID, UID, 'existing-encrypted-token', None)
    with patch.object(server._sleeper_write, 'verify_token_live',
                      side_effect=server._sleeper_write.SleeperWriteError('network', kind='network')):
        result = c.post('/api/sleeper/link', headers=_h(token), json={'token': _token()})
    assert result.status_code == 503
    assert result.json['error'] == 'verification_unavailable'
    assert not _sess(token).get('verified')
    assert db.get_sleeper_credential(UID)['token_encrypted'] == 'existing-encrypted-token'
