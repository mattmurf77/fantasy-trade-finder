"""The app's value bar puts its ±2nd tick at the Mid 2nd / Mid 1st value
ratio (mobile/src/components/TradeValueBar.tsx SECOND_IN_FIRSTS). That ratio
comes from backend GENERIC_PICK_SEEDS through elo_to_value, the same source
the share card's bar computes it from (#564). It had drifted to 0.57 while
the seeds gave 0.287, so a fill reading "≈ a Late 1st" ended on the "2nd"
tick. This pins the app constant to the seeds: a seed or curve change that
moves the ratio fails here until the app follows."""
import re
from pathlib import Path

from backend import trade_service as ts
from backend.pick_values import GENERIC_PICK_SEEDS

BAR = Path(__file__).resolve().parents[2] / "mobile/src/components/TradeValueBar.tsx"


def test_the_apps_second_tick_is_the_seeds_mid_2nd_over_mid_1st():
    found = re.search(r"^const SECOND_IN_FIRSTS = ([0-9.]+);$", BAR.read_text(), re.M)
    assert found, "SECOND_IN_FIRSTS moved: update this test"
    e2v = ts.elo_to_value
    ratio = e2v(GENERIC_PICK_SEEDS[(2, "Mid")]) / e2v(GENERIC_PICK_SEEDS[(1, "Mid")])
    assert abs(float(found.group(1)) - ratio) < 0.005, (float(found.group(1)), round(ratio, 4))


def test_the_web_landing_miniature_puts_its_ticks_at_the_same_landmark():
    """web/css/styles.css mirrors the bar on the landing page: its −2nd and
    +2nd ticks and labels sit at 50 ∓ SECOND_IN_FIRSTS × 50 percent."""
    css = (BAR.parents[3] / "web/css/styles.css").read_text()
    second = float(re.search(r"^const SECOND_IN_FIRSTS = ([0-9.]+);$", BAR.read_text(), re.M).group(1))
    for selector, want in ((r"\.lp-market-minus", 50 - second * 50), (r"\.lp-market-plus", 50 + second * 50),
                           (r"\.lp-market-scale span:nth-child\(2\)", 50 - second * 50),
                           (r"\.lp-market-scale span:nth-child\(4\)", 50 + second * 50)):
        got = float(re.search(selector + r" \{ left: ([0-9.]+)%; \}", css).group(1))
        assert abs(got - want) < 0.1, (selector, got, want)


def test_the_league_example_gap_is_a_mid_2nd_at_todays_values():
    """mobile/src/screens/LeagueScreen.tsx EXAMPLE_GAP, the "Works right now"
    card every user with no matches sees, is the clients' only static gap. Its
    pick, value and firsts must be what the server would send for a Mid 2nd
    gap (_pick_gap_equivalent), or the fill and the copy disagree again (#567
    QA P2-1: it said "a Mid 2nd (≈ 0.6 firsts)" and filled past the tick)."""
    league = (BAR.parents[1] / "screens/LeagueScreen.tsx").read_text()
    block = re.search(r"^const EXAMPLE_GAP = \{(.*?)^\};$", league, re.M | re.S)
    assert block, "EXAMPLE_GAP moved: update this test"
    # The top level only (two-space indent): pick_equivalent's nested `value`
    # is checked on its own below (#567 delta QA P2: `^\s*` let it shadow
    # the top-level value users see).
    nums = {k: float(v) for k, v in re.findall(r"^  (value|firsts): ([0-9.]+),$", block.group(1), re.M)}
    assert set(nums) == {"value", "firsts"}, nums
    pick_value = float(re.search(r"pick_equivalent: \{.*?value: ([0-9.]+),", block.group(1), re.S).group(1))
    e2v = ts.elo_to_value
    mid_2nd, mid_1st = e2v(GENERIC_PICK_SEEDS[(2, "Mid")]), e2v(GENERIC_PICK_SEEDS[(1, "Mid")])
    assert "label: 'Mid 2nd Round Pick'" in block.group(1)
    assert abs(pick_value - mid_2nd) < 0.5, (pick_value, round(mid_2nd, 1))
    assert abs(nums["value"] - mid_2nd) < 1, (nums["value"], round(mid_2nd, 1))
    assert abs(nums["firsts"] - round(nums["value"] / mid_1st, 2)) < 0.005, (nums["firsts"], nums["value"] / mid_1st)
