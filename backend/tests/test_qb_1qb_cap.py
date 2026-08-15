"""#313 — 1QB consensus QB values cap at "1 1st".

The operator reported QBs reading "2 1sts" on the 1QB DraftRoom board. The
tier LABEL is derived client-side from the served consensus Elo, so the
defect is the VALUE: live DP `value_1qb` 7025 (Josh Allen) seeds Elo 1858.9,
inside the `firsts_2` band [1788, 1864]. The fix compresses 1QB QB values
post-blend / pre-Elo-map (data_loader._compress_qb_1qb_values, wired into
_apply_consensus_blend) so every QB lands at or below the top of `first_1`.

Deliberately NOT changed, and pinned here: tier_config.json bands, the
`tier_for_elo` walk, every client band mirror, sf_tep, non-QB positions,
sub-knee QBs.

Every test names the sabotage that must turn it RED:

  1. top QB at DP 10000 → Elo <= cap, label `first_1`
       sabotage: read the knobs but never apply the compression
  2. shape — strict order preserved AND the move scales with height
       sabotage: implement as a hard clamp min(v, C)  [ties → RED]
  3. sf_tep with identical values → byte-identical (format guard)
       sabotage: drop the `fmt == "1qb_ppr"` guard
  4. RB at DP 10000 in 1QB → uncapped (Elo ≈ 1927, firsts_4plus)
       sabotage: compress position-blind
  5. qb_1qb_cap_elo = 0 (and knee = 0) → whole map byte-identical
       sabotage: fall back to the default cap when the knob is 0
  6. compression runs AFTER the KTC blend
       sabotage: compress before the blend step
"""
import pytest

import backend.data_loader as dl
from backend.data_loader import (
    QB_1QB_CAP_ELO_DEFAULT,
    QB_1QB_CAP_KNEE_ELO_DEFAULT,
    _apply_consensus_blend,
    seed_elo_for_value,
    seed_value_for_elo,
)
from backend.ranking_service import RankingService

FMT = "1qb_ppr"
CAP_ELO = QB_1QB_CAP_ELO_DEFAULT
KNEE_ELO = QB_1QB_CAP_KNEE_ELO_DEFAULT


@pytest.fixture(autouse=True)
def _default_knobs(monkeypatch):
    """Knobs at their specced defaults, blend OFF, KTC unreachable — so every
    test below isolates the compression from the #145 blend."""
    monkeypatch.setattr(dl, "_blend_config", lambda: (0.0, 1.0))
    monkeypatch.setattr(dl, "_qb_cap_config", lambda: (CAP_ELO, KNEE_ELO))


def _maps(values: dict[str, float], positions: dict[str, str]):
    """(elo_map, value_map, pos_map) exactly as _fetch_dynasty_process emits."""
    value_map = {k: float(v) for k, v in values.items()}
    elo_map = {k: round(seed_elo_for_value(v), 1) for k, v in value_map.items()}
    return elo_map, value_map, dict(positions)


def _run(fmt, values, positions):
    elo, val, pos = _maps(values, positions)
    return _apply_consensus_blend(fmt, elo, val, pos)


def _tier(elo, pos="QB", fmt=FMT):
    return RankingService.tier_for_elo(elo, pos, fmt)


# ---------------------------------------------------------------------------
# 1. The reported defect: the top 1QB QB reads "1 1st"
# ---------------------------------------------------------------------------

def test_top_qb_caps_at_one_first():
    """A QB at the DP ceiling seeds at/below the cap and labels `first_1`
    through the REAL ladder (unmodified tier_config.json bands)."""
    out_elo, _ = _run(FMT, {"qb1": 10000.0, "wr1": 10000.0},
                      {"qb1": "QB", "wr1": "WR"})
    assert out_elo["qb1"] <= CAP_ELO, (
        f"top QB seeded {out_elo['qb1']} — above the {CAP_ELO} cap")
    assert _tier(out_elo["qb1"]) == "first_1"


def test_live_2026_08_13_top_qbs_all_read_one_first():
    """The operator's actual complaint, on the values that produced it:
    Allen 7025 / Maye 5890 / Daniels 5000 all read `firsts_2` before the fix
    (Elo 1858.9 / 1825.0 / 1793.8) and `first_1` after."""
    live = {"allen": 7025.0, "maye": 5890.0, "daniels": 5000.0}
    for v in live.values():                       # the pre-fix state
        assert _tier(seed_elo_for_value(v)) == "firsts_2"
    out_elo, _ = _run(FMT, live, {k: "QB" for k in live})
    for k, e in out_elo.items():
        assert _tier(e) == "first_1", f"{k} still labels {_tier(e)} at Elo {e}"


# ---------------------------------------------------------------------------
# 2. SHAPE — the invariant a hard clamp cannot satisfy
# ---------------------------------------------------------------------------

def test_compression_preserves_strict_order_and_scales_with_height():
    """A draft board needs an ORDER, not a shelf of ties. Two independent
    shape pins: (a) the top QBs stay strictly ordered under the cap, and
    (b) a mid-range above-knee QB moves strictly less than the top QB — the
    map is a compression, not a step. A clamp min(v, C) ties (a)."""
    values = {"qb1": 10000.0, "qb2": 7025.0, "qb3": 5890.0, "qb4": 3000.0}
    before = {k: seed_elo_for_value(v) for k, v in values.items()}
    out_elo, _ = _run(FMT, values, {k: "QB" for k in values})

    ordered = ["qb1", "qb2", "qb3", "qb4"]
    for hi, lo in zip(ordered, ordered[1:]):
        assert out_elo[hi] > out_elo[lo], (
            f"{hi} ({out_elo[hi]}) must stay strictly above {lo} "
            f"({out_elo[lo]}) — ties break the board's ordering")
    for k in ordered:
        assert out_elo[k] <= CAP_ELO

    # (b) the drop scales with height: qb4 sits above the knee, so it MOVES,
    # but strictly less than the top QB.
    assert before["qb4"] > KNEE_ELO, "fixture drift: qb4 must sit above the knee"
    drop_top = before["qb1"] - out_elo["qb1"]
    drop_mid = before["qb4"] - out_elo["qb4"]
    assert drop_mid > 0.0, "an above-knee QB must be compressed at all"
    assert drop_mid < drop_top, (
        f"mid QB dropped {drop_mid:.1f} vs top {drop_top:.1f} — the "
        f"compression must scale with height")


def test_sub_knee_qbs_are_byte_identical():
    """Below the knee the map is the identity — the fix re-prices the top of
    the QB market, not the whole position.

    (DP serves integer values, which is what makes this byte-identical: once
    any key changes, _apply_consensus_blend re-rounds the whole map to 1dp,
    a pre-#313 no-op on integers.)"""
    assert seed_value_for_elo(KNEE_ELO) > 1500.0, "fixture drift: knee moved"
    values = {"qb_lo": 1500.0, "qb_lo2": 500.0, "qb_hi": 9000.0}
    elo, val, pos = _maps(values, {k: "QB" for k in values})
    before_elo, before_val = dict(elo), dict(val)
    out_elo, out_val = _apply_consensus_blend(FMT, elo, val, pos)
    for k in ("qb_lo", "qb_lo2"):
        assert out_val[k] == before_val[k], f"{k}: sub-knee value changed"
        assert out_elo[k] == before_elo[k], f"{k}: sub-knee Elo changed"
    assert out_val["qb_hi"] < before_val["qb_hi"]


# ---------------------------------------------------------------------------
# 3. Format guard — sf_tep is untouched
# ---------------------------------------------------------------------------

def test_sf_tep_qbs_are_untouched():
    """Superflex QBs are SUPPOSED to price at multiple firsts. Identical
    input in sf_tep must come back byte-identical."""
    values = {"qb1": 10000.0, "qb2": 7025.0}
    elo, val, pos = _maps(values, {k: "QB" for k in values})
    before_elo, before_val = dict(elo), dict(val)
    out_elo, out_val = _apply_consensus_blend("sf_tep", elo, val, pos)
    assert out_val == before_val, "sf_tep QB values changed"
    assert out_elo == before_elo, "sf_tep QB Elos changed"
    assert _tier(out_elo["qb1"], "QB", "sf_tep") == "firsts_4plus"


# ---------------------------------------------------------------------------
# 4. Position guard — only QBs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pos", ("RB", "WR", "TE"))
def test_non_qb_positions_are_uncapped_in_1qb(pos):
    """The 4-firsts anchor (#117) still belongs to the top skill asset."""
    values = {"skill": 10000.0, "qb1": 10000.0}
    elo, val, pmap = _maps(values, {"skill": pos, "qb1": "QB"})
    before_val = dict(val)
    out_elo, out_val = _apply_consensus_blend(FMT, elo, val, pmap)
    assert out_val["skill"] == before_val["skill"], f"{pos} value compressed"
    assert out_elo["skill"] == pytest.approx(1927.3, abs=0.1)
    assert _tier(out_elo["skill"], pos) == "firsts_4plus"
    assert out_elo["qb1"] < out_elo["skill"]


# ---------------------------------------------------------------------------
# 5. Kill switch
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("knobs", [
    (0.0, KNEE_ELO),          # cap off
    (CAP_ELO, 0.0),           # knee off
    (0.0, 0.0),               # both off
    (-1.0, KNEE_ELO),         # negative reads as off, not as a cap
])
def test_kill_switch_is_byte_identical(monkeypatch, knobs):
    """Either knob <= 0 → the pre-#313 pipeline exactly (with the blend also
    neutral, that is the pure-DP pipeline)."""
    monkeypatch.setattr(dl, "_qb_cap_config", lambda: knobs)
    values = {"qb1": 10000.0, "qb2": 7025.0, "wr1": 9000.0}
    elo, val, pos = _maps(values, {"qb1": "QB", "qb2": "QB", "wr1": "WR"})
    before_elo, before_val = dict(elo), dict(val)
    out_elo, out_val = _apply_consensus_blend(FMT, elo, val, pos)
    assert out_val == before_val, f"{knobs}: values changed with the cap off"
    assert out_elo == before_elo, f"{knobs}: Elos changed with the cap off"
    assert _tier(out_elo["qb1"]) == "firsts_4plus"   # the pre-fix behaviour


def test_degenerate_knobs_are_a_no_op(monkeypatch):
    """Knee above cap has no sane compression — no-op rather than an
    inverted (order-destroying) map."""
    monkeypatch.setattr(dl, "_qb_cap_config", lambda: (1580.0, 1785.0))
    values = {"qb1": 10000.0}
    elo, val, pos = _maps(values, {"qb1": "QB"})
    before = dict(val)
    _, out_val = _apply_consensus_blend(FMT, elo, val, pos)
    assert out_val == before


def test_knobs_are_seeded_in_model_config_defaults():
    """The operator tunes these from model_config, so the rows must exist
    with the specced defaults (data_loader's constants are the no-DB
    fallback and must agree)."""
    from backend.database import _MODEL_CONFIG_DEFAULTS
    rows = {k: v for k, v, _ in _MODEL_CONFIG_DEFAULTS}
    assert rows["qb_1qb_cap_elo"] == QB_1QB_CAP_ELO_DEFAULT == 1785.0
    assert rows["qb_1qb_cap_knee_elo"] == QB_1QB_CAP_KNEE_ELO_DEFAULT == 1580.0


# ---------------------------------------------------------------------------
# 6. Ordering: the compression runs AFTER the KTC blend
# ---------------------------------------------------------------------------

def test_cap_applies_after_the_ktc_blend(monkeypatch):
    """KTC's rank-normalization can lift a mid-priced QB onto the top of the
    DP curve. Compressing before the blend would let that lift land the QB
    back above the cap — so the cap must be the LAST step."""
    monkeypatch.setattr(dl, "_blend_config", lambda: (0.5, 1.0))
    monkeypatch.setattr(dl, "_ktc_consensus", lambda: {
        "qb_boosted": {"pos": "QB", "values": {FMT: 9999.0}},
        "wr1":        {"pos": "WR", "values": {FMT: 5000.0}},
    })
    # DP prices the QB mid-market; KTC ranks him #1, so rank-normalization
    # maps him onto the pool's top DP value (10000).
    values = {"qb_boosted": 3000.0, "wr1": 10000.0}
    out_elo, out_val = _run(FMT, values, {"qb_boosted": "QB", "wr1": "WR"})
    assert out_elo["qb_boosted"] <= CAP_ELO, (
        f"KTC-boosted QB seeded {out_elo['qb_boosted']} — the blend pushed "
        f"him back over the cap, so the cap ran too early")
    assert _tier(out_elo["qb_boosted"]) == "first_1"
    # The blend really did lift him (otherwise the test proves nothing).
    assert out_val["qb_boosted"] > values["qb_boosted"] * 0.9
    assert seed_elo_for_value(
        0.5 * 3000.0 + 0.5 * 10000.0) > CAP_ELO, (
        "fixture drift: the un-capped blended value must exceed the cap")


# ---------------------------------------------------------------------------
# End-to-end: the cap survives the whole loader path, not just the blend
# ---------------------------------------------------------------------------

def test_fetch_dynasty_process_serves_capped_1qb_qbs(monkeypatch):
    """The pool builder's real entry point — a refactor that stops routing
    through _apply_consensus_blend must not silently drop the cap."""
    import io

    csv = ("player,pos,team,age,value_1qb,value_2qb\n"
           "Josh Allen,QB,BUF,30.1,7025,10208\n"
           "Bijan Robinson,RB,ATL,24.5,9580,8089\n")
    monkeypatch.setattr(
        dl.urllib.request, "urlopen",
        lambda req, timeout=10: io.BytesIO(csv.encode("utf-8")))
    monkeypatch.setattr(dl, "_ktc_consensus", lambda: {})   # hermetic

    e1, v1, _ = dl._fetch_dynasty_process(scoring="1qb_ppr")
    assert e1["josh allen"] <= CAP_ELO
    assert _tier(e1["josh allen"]) == "first_1"
    assert v1["josh allen"] < 7025.0
    assert v1["bijan robinson"] == 9580.0            # RB untouched

    e2, v2, _ = dl._fetch_dynasty_process(scoring="sf_tep")
    assert v2["josh allen"] == 10208.0               # sf_tep untouched
    assert _tier(e2["josh allen"], "QB", "sf_tep") == "firsts_4plus"
