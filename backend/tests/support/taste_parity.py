"""R4.1 (iii) parity: the frozen taste matches equal what taste_multipliers used.

The evidence writer freezes, per served card, the two prefMatch values the F5
taste layer ordered it by: features["taste_pref_long"] and
features["taste_pref_short"] (float8, exact), absent when the layer didn't run
(taste_multipliers returned None: flag off, no taste signal, or the layer
skipped). value_model's fits and evals read those values and nothing live
(models-lead-launch §Reviews-4 R4.1).

trades-eng's writer test calls assert_frozen_prefs_match_multipliers with one
served deck's cards, the features it froze for each card, and what
taste_service.taste_multipliers returned for the same cards in the same serve.
It passes only when every card's frozen pair is, bit for bit, the pair
taste_multipliers built that card's multiplier from.

Run it on taste state that can't move between the serve and the check:
prior-only taste rows (never time-decayed) or a pinned taste_service clock.
"""

import struct

from backend import taste_service
from backend.value_model import K_TASTE_PREF_LONG, K_TASTE_PREF_SHORT

FROZEN_KEYS = (K_TASTE_PREF_LONG, K_TASTE_PREF_SHORT)


def serve_time_prefs(cards, *, user_id, players_dict, seed_map) -> dict | None:
    """{id(card): (pref_long, pref_short)} computed exactly as
    taste_multipliers computes them (same vector read, same card attributes,
    same _pref_match), or None when taste_multipliers returns None for lack
    of signal."""
    short, long_ = taste_service.load_taste_vectors(user_id)
    if not short and not long_:
        return None
    out = {}
    for c in cards:
        attrs = taste_service.card_taste_attrs(c, players_dict or {}, seed_map or {})
        out[id(c)] = (taste_service._pref_match(long_, attrs),
                      taste_service._pref_match(short, attrs))
    return out


def _bits(x: float) -> bytes:
    return struct.pack("<d", x)


def assert_frozen_prefs_match_multipliers(cards, frozen: dict, multipliers: dict | None, *,
                                          user_id, players_dict, seed_map) -> None:
    """frozen: {id(card): the features dict the writer froze for that card}.
    multipliers: taste_multipliers' return value for the same cards and serve."""
    if multipliers is None:
        for c in cards:
            present = set(FROZEN_KEYS) & set(frozen[id(c)])
            assert not present, f"the taste layer didn't run, but {sorted(present)} are frozen"
        return
    ref = serve_time_prefs(cards, user_id=user_id, players_dict=players_dict,
                           seed_map=seed_map)
    assert ref is not None, "taste_multipliers ran, but the user has no taste signal now"
    eta_l = taste_service._cfg("taste_eta_long", 0.2)
    eta_s = taste_service._cfg("taste_eta_short", 0.3)
    lo = taste_service._cfg("taste_clamp_lo", 0.7)
    hi = max(lo, taste_service._cfg("taste_clamp_hi", 1.4))
    for c in cards:
        f = frozen[id(c)]
        missing = [k for k in FROZEN_KEYS if k not in f]
        assert not missing, f"card {id(c)}: the taste layer ran, but {missing} are not frozen"
        pl, ps = f[K_TASTE_PREF_LONG], f[K_TASTE_PREF_SHORT]
        assert type(pl) is float and type(ps) is float, (pl, ps)
        assert (_bits(pl), _bits(ps)) == tuple(map(_bits, ref[id(c)])), (
            f"card {id(c)}: frozen ({pl!r}, {ps!r}) != serve-time {ref[id(c)]!r}")
        m = min(hi, max(lo, (1.0 + eta_l * pl) * (1.0 + eta_s * ps)))
        assert _bits(m) == _bits(multipliers[id(c)]), (
            f"card {id(c)}: the frozen pair rebuilds multiplier {m!r}, "
            f"taste_multipliers used {multipliers[id(c)]!r}")
