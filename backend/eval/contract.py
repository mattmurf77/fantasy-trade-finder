"""C7 (iii): the declared scorer-input contract for narrow evidence rows.

Narrow evidence rows (models-lead-launch §DEC-2, C1 and C7) keep a frozen
compact scorer-input block for unseen cards instead of the wide
features_json. Replay over those rows is only valid if every registered
scorer reads nothing the narrow row lacks. The contract:

    keys a scorer reads from card_dict(card)
        ⊆ COMPACT_KEYS ∪ INJECTED_KEYS ∪ IDENTITY_KEYS ∪ PERMITTED_LOGGED[name]

- COMPACT_KEYS: exactly the card keys `value_model.extract_features`
  reads (value_model.py:133-177). Guarded: a key extract_features reads
  that is not listed here fails backend/tests/test_eval_scorer_contract.py.
- INJECTED_KEYS: what `ValueModel._inject` (value_model.py:408-420) adds
  or reads. INJECTED_COMPUTED_KEYS are computed at eval time from other
  tables and are never stored. INJECTED_CARD_INPUTS are read raw from the
  card to compute them, so they must be frozen with the compact block:
  a row without them replays value_model to a different score.
- IDENTITY_KEYS: the deck_impressions columns card_dict always merges in
  that do not encode the logged policy. Every narrow row keeps them, so
  any scorer may read them (extract_features falls back to shape_bucket
  and archetype when shape and lane are absent).
- LOGGED_POLICY_KEYS: the columns that encode the logged policy. A scorer
  reads one only if PERMITTED_LOGGED grants it (the honesty rule in
  scorers.py).

THE RULE, from 2026-10-20 on: adding a feature to any scorer means adding
it to COMPACT_KEYS (and to the writer that freezes the compact block)
first. Unseen cards written before that date cannot be backtested on the
new feature, except on the C8 whole-deck archive.
"""

from __future__ import annotations

COMPACT_KEYS = frozenset({
    "give_value", "receive_value", "surplus_margin", "fairness_score",
    "ranked_player_count",
    "shape", "lane", "basis",
    "give_positions", "receive_positions",
    "involves_pick", "likes_you", "relaxed", "user_value_basis",
})

# value_model.K_PREF_LONG / K_PREF_SHORT / K_PARTNER_RATE / K_POSITION.
INJECTED_COMPUTED_KEYS = frozenset({
    "_pref_long", "_pref_short", "_partner_rate", "_position",
})
# _inject reads these from the card: partner_user_id for the partner-rate
# lookup (and taste_service.attrs_from_features' partner attr), taste_attrs
# for the prefMatch scores.
INJECTED_CARD_INPUTS = frozenset({"partner_user_id", "taste_attrs"})
INJECTED_KEYS = INJECTED_COMPUTED_KEYS | INJECTED_CARD_INPUTS

# What a narrow row's frozen block must hold for every registered scorer
# to replay exactly: the extract_features inputs plus _inject's card inputs.
FROZEN_INPUT_KEYS = COMPACT_KEYS | INJECTED_CARD_INPUTS

# The logged columns card_dict merges into every card (backend/eval/data.py).
LOGGED_POLICY_KEYS = frozenset({
    "card_index", "propensity", "base_score", "final_score",
})
IDENTITY_KEYS = frozenset({
    "impression_id", "deck_job_id", "user_id", "league_id", "trade_hash",
    "archetype", "shape_bucket", "served_at",
})

# Per registered scorer (backend/eval/scorers.py): the logged policy
# columns it may read. Every registered scorer needs an entry.
PERMITTED_LOGGED = {
    "logged": frozenset({"card_index"}),
    "production": frozenset({"final_score", "base_score"}),
    "base_score": frozenset({"base_score"}),
    "random": frozenset(),
    "value_model": frozenset(),   # compact + injected only
}


def allowed_keys(scorer_name: str) -> frozenset:
    """Every card key `scorer_name` may read under the contract. KeyError
    for a scorer without a PERMITTED_LOGGED entry."""
    return (COMPACT_KEYS | INJECTED_KEYS | IDENTITY_KEYS
            | PERMITTED_LOGGED[scorer_name])
