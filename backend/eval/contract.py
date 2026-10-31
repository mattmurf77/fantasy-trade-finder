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
- INJECTED_KEYS: what `ValueModel._inject` adds or reads.
  INJECTED_COMPUTED_KEYS are the model inputs it writes and are never
  stored. INJECTED_CARD_INPUTS are read raw from the card to compute them,
  so they must be frozen with the compact block: a row without them
  replays value_model to a different score. The taste matches are frozen
  per card at serve time (models-lead R4.1), never read from live taste
  rows in a fit or an eval.
- FROZEN_PROVENANCE_KEYS: frozen with the block but read by no scorer
  (taste_attrs, the source of the frozen taste matches).
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

C8 archive selection (`is_archive_deck`) and the card impression id
(`card_impression_id`) live here too, as the one definition the evidence
writer and eval share.
"""

from __future__ import annotations

import hashlib

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
# lookup, and the serve-time taste matches taste_service.taste_multipliers
# used (float8; absent when the taste layer didn't run, read as 0.0).
INJECTED_CARD_INPUTS = frozenset({
    "partner_user_id", "taste_pref_long", "taste_pref_short",
})
INJECTED_KEYS = INJECTED_COMPUTED_KEYS | INJECTED_CARD_INPUTS
# Account deletion (legal R28.20, models-lead E-b1): a deleted user's platform
# id in other users' records becomes one random token per deleted user with
# this prefix (agreed with trades-eng's scrub). Eval counts the tokens
# (replay.redacted_partners, E-b5) and never resolves one: such a partner is
# unknown, and no hash that embeds the partner (trade_hash and the like) is
# used to work out whose it was.
REDACTED_PARTNER_PREFIX = "redacted:"
# Frozen with the block, read by no scorer: the card's taste attributes.
FROZEN_PROVENANCE_KEYS = frozenset({"taste_attrs"})

# What a narrow row's frozen block (and a packed card) must hold: the
# extract_features inputs, _inject's card inputs and the provenance keys.
FROZEN_INPUT_KEYS = COMPACT_KEYS | INJECTED_CARD_INPUTS | FROZEN_PROVENANCE_KEYS

# The logged columns card_dict merges into every card (backend/eval/data.py).
LOGGED_POLICY_KEYS = frozenset({
    "card_index", "position", "propensity", "base_score", "final_score",
})
IDENTITY_KEYS = frozenset({
    "impression_id", "deck_job_id", "user_id", "league_id", "trade_hash",
    "archetype", "shape_bucket", "served_at",
})

# Per registered scorer (backend/eval/scorers.py): the logged policy
# columns it may read. Every registered scorer needs an entry.
PERMITTED_LOGGED = {
    "logged": frozenset({"position"}),
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


# What load_decks(project_features=True) keeps inside each parsed features
# dict: every key some registered scorer may read, plus the frozen block
# (⊇ FROZEN_INPUT_KEYS ∪ IDENTITY_KEYS). value_model training reads the same
# keys (extract_features and _inject), so a refit on projected decks is
# unchanged.
PROJECTION_KEYS = FROZEN_INPUT_KEYS.union(*(allowed_keys(n) for n in PERMITTED_LOGGED))


# C8 whole-deck archive (models-lead-launch §DEC-2 C8): a fixed share of
# served decks, chosen by deck and never by row, keeps full rows for every
# card for ARCHIVE_DAYS, so a scorer needing a feature outside the compact
# block can still be backtested.
ARCHIVE_RATE_BP = 200    # basis points of served decks (2%)
ARCHIVE_DAYS = 90


def card_impression_id(run_id: str, card_index: int) -> str:
    """R4.2 U2, the one definition the evidence writer, the client and eval
    share: every non-ghost card of a served deck, row or packed, has this
    impression_id, and outcomes are posted with it. A ghost row never does
    (its would-have-been rank can equal a served card's index)."""
    return f"{run_id}:{card_index}"


def is_archive_deck(deck_job_id: str) -> bool:
    """C8 selection, the single definition (the evidence writer imports it).
    A pure function of the deck id alone: no user, league, content or
    clock, so the choice is stable across processes and re-runs and can't
    correlate with what the deck contains."""
    digest = hashlib.sha256(("c8-archive-v1|" + deck_job_id).encode()).hexdigest()
    return int(digest[:8], 16) % 10000 < ARCHIVE_RATE_BP
