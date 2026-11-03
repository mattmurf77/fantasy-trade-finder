"""C8 whole-deck archive selection: backend.eval.contract.is_archive_deck.

The one definition the evidence writer and eval share: 2% of served decks,
chosen from the deck id alone.
"""

import hashlib
import inspect
import random
import uuid

from backend.eval.contract import ARCHIVE_DAYS, ARCHIVE_RATE_BP, is_archive_deck


def _spec(deck_job_id: str) -> bool:
    """The selection formula as specified, restated independently."""
    h = hashlib.sha256(("c8-archive-v1|" + deck_job_id).encode()).hexdigest()
    return int(h[:8], 16) % 10000 < 200


def _ids(n: int, seed: int = 8) -> list[str]:
    rng = random.Random(seed)
    return [uuid.UUID(int=rng.getrandbits(128), version=4).hex for _ in range(n)]


def test_constants():
    assert ARCHIVE_RATE_BP == 200
    assert ARCHIVE_DAYS == 90


def test_deterministic_and_matches_the_spec():
    ids = _ids(2000, seed=3)
    first = [is_archive_deck(i) for i in ids]
    assert first == [is_archive_deck(i) for i in ids]
    assert first == [_spec(i) for i in ids]
    assert any(first) and not all(first)


def test_rate_is_two_percent():
    ids = _ids(100_000)
    rate = sum(map(is_archive_deck, ids)) / len(ids)
    assert abs(rate - 0.02) <= 0.002, rate


def test_takes_only_the_deck_id():
    params = list(inspect.signature(is_archive_deck).parameters.values())
    assert [p.name for p in params] == ["deck_job_id"]
    assert params[0].default is inspect.Parameter.empty
