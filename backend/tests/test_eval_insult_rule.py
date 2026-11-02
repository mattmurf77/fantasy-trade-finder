"""The D-055 first-deck insult rule (backend/eval/insult_rule.py).

Pins the 2026-08-15 report's statement: insult = net negative by |Δ| ≥ 500 AND
(I1 a haircut ≥ 20% on the give package, OR I2 a return asset ≤ 350 while the
give side holds one ≥ 2,500). Every threshold is inclusive; each edge is
tested on both sides with the other conditions held clear of their limits.
"""
import pytest

from backend.eval.insult_rule import (JUNK_MAX, LOWBALL_HAIRCUT, MATERIALITY, STAR_MIN,
                                      insult_verdict)


def test_thresholds_are_the_ratified_ones():
    assert (MATERIALITY, LOWBALL_HAIRCUT, JUNK_MAX, STAR_MIN) == (500, 0.20, 350, 2500)


def test_totals_delta_and_haircut():
    v = insult_verdict([3000, 1000], [2500, 700])
    assert (v["give_total"], v["receive_total"], v["delta"]) == (4000, 3200, -800)
    assert v["haircut"] == pytest.approx(0.20)


@pytest.mark.parametrize("give,receive,i1", [
    ([2500], [2000], True),     # Δ −500 exactly, haircut 20% exactly
    ([2000], [1501], False),    # haircut 25%, but Δ −499: under the floor
    ([5000], [4000], True),     # haircut 20% exactly, Δ −1000
    ([5000], [4001], False),    # haircut 19.98%, Δ −999
    ([1000], [400], True),      # small package, haircut 60%, Δ −600
])
def test_i1_lowball_edges(give, receive, i1):
    v = insult_verdict(give, receive)
    assert v["i2"] is False                      # no junk return: I1 alone decides
    assert v["i1"] is i1 and v["insult"] is i1


@pytest.mark.parametrize("give,receive,i2", [
    ([2500, 600], [2250, 350], True),     # star 2,500, junk 350, Δ −500 exactly
    ([2499, 600], [2249, 350], False),    # best give asset 2,499: no star
    ([2500, 600], [2249, 351], False),    # worst return asset 351: no junk
    ([2500, 600], [2251, 350], False),    # star and junk, but Δ −499: under the floor
])
def test_i2_junk_filler_edges(give, receive, i2):
    v = insult_verdict(give, receive)
    assert v["haircut"] < LOWBALL_HAIRCUT        # haircut ~16%: I2 alone decides
    assert v["i1"] is False
    assert v["i2"] is i2 and v["insult"] is i2


def test_net_positive_and_even_cards_are_never_insults():
    for give, receive in (([3000], [100, 3100]),     # star for junk and more: Δ +200
                          ([2600], [350, 2250]),     # Δ 0
                          ([400], [2600])):
        v = insult_verdict(give, receive)
        assert v["delta"] >= 0 and v["haircut"] == 0.0
        assert not (v["i1"] or v["i2"] or v["insult"])


def test_both_tags_together_and_empty_sides():
    v = insult_verdict([6000], [300, 1000])          # Δ −4700, haircut 78%, junk and star
    assert v["i1"] and v["i2"] and v["insult"]
    empty = insult_verdict([], [])
    assert empty["delta"] == 0 and empty["haircut"] == 0.0 and not empty["insult"]
    nothing_given = insult_verdict([], [900])
    assert nothing_given["haircut"] == 0.0 and not nothing_given["insult"]
