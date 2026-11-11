"""Revision 4 selector through the server: dark hash, page identity, serving.

Mirrors test_outlook_evidence_routes.py for owner-v2-bilateral-4
(docs/plans/offer-learnings/plan.md §3 WS1).
"""
import json

from backend import database as db, server, trade_service as ts, bakeoff_runner as bo
from backend.tests.test_owner_generator_routes import harness, owner_harness, rows, context_for  # noqa: F401

KEY = 'owner_bilateral_revision_4_enabled'


def _revision():
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=1.)


def test_dark_value_keeps_request_hash_and_page_identity(owner_harness):
    _revision()
    ts._cfg[KEY] = 0.
    context = context_for(owner_harness)
    original = server._owner_selected_assignment(context, 'fair_packages', serve=True)['request_hash']
    for dark in (None, 0., 2., .5):
        if dark is None:
            context['config'].pop(KEY, None)
        else:
            context['config'][KEY] = dark
        assert server._owner_selected_assignment(context, 'fair_packages', serve=True)['request_hash'] == original
    signature = server._trade_safety_signature()
    ts._cfg[KEY] = 1.
    assert server._trade_safety_signature() != signature
    assert 'owner_model_version:owner-v2-bilateral-4' in server._trade_safety_signature()
    context['config'][KEY] = 1.
    assert bo.owner_version(context['config']) == 'owner-v2-bilateral-4'
    assert server._owner_selected_assignment(context, 'fair_packages', serve=True)['request_hash'] != original


def test_revision_4_context_carries_no_v3_input_evidence(owner_harness):
    _revision()
    ts._cfg.update({KEY: 1., 'owner_outlook_evidence_enabled': 1.})
    context = context_for(owner_harness)
    assert 'input_evidence' not in context
    cards, report = bo.owner_generator(context['config'])(**context)
    assert cards and report.as_dict()['generator_version'] == 'owner-v2-bilateral-4'


def test_cards_never_relabelled_across_revision_2_and_4(owner_harness):
    _revision()
    for enabled in (0., 1.):
        ts._cfg[KEY] = enabled
        context = context_for(owner_harness)
        cards, _ = bo.owner_generator(context['config'])(**context)
        assert cards and server._owner_cards_valid(cards, context)
        snapshots = [c.owner_evaluation.snapshot_json for c in cards]
        context['config'][KEY] = 1. - enabled
        assert server._owner_cards_valid(cards, context) == []
        assert [c.owner_evaluation.snapshot_json for c in cards] == snapshots


def test_revision_4_route_serves_new_identity_without_private_fields(owner_harness):
    from backend.tests.test_owner_generator_routes import post
    _revision()
    ts._cfg.update({KEY: 1., 'bakeoff_owner_only': 1.})
    client, engine, *_ = owner_harness
    response = post(client)
    assert response.status_code == 200 and response.json['ideas']
    assert {card['generator_version'] for card in response.json['ideas']} == {'owner-v2-bilateral-4'}
    served = json.dumps(response.json)
    for private in ('revision_4', 'pick_premium', 'best_asset_rule', 'counterparty_preference'):
        assert private not in served
    impressions = rows(engine, db.deck_impressions_table)
    assert {json.loads(r['valuation_json'])['generator_version'] for r in impressions} == {'owner-v2-bilateral-4'}
