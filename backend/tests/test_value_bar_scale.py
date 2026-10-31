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
