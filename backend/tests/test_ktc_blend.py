"""KeepTradeCut consensus blend (#145) + sf_tep TE premium uplift (#148).

The DP baseline consensus is blended with KeepTradeCut before Elo seeding
(data_loader._apply_consensus_blend): KTC values are rank-normalized onto
the DP value curve per format and weighted-averaged (weight
model_config.ktc_blend_weight), and sf_tep TE values get a TE-premium
multiplier (model_config.tep_te_uplift) that DP's value_2qb column lacks.

Fixtures (no network):
  * ktc_rankings_snapshot_2026-07-17.html — a trimmed KTC dynasty-rankings
    page (the embedded `var playersArray = [...]`, top ~24/pos + 2 RDP
    rows) exercising parse_ktc_players and the real _ktc_consensus path.
  * ktc_blend_pipeline_2026-07-17.json — the real 2026-07-17 DP pool (633
    players/format) plus the 441 matched KTC consensus rows, so the blend
    math is pinned end-to-end on live data.

These tests pin:
  1. parse_ktc_players extracts playersArray and drops rookie-draft-pick
     (RDP) rows — universe unchanged.
  2. BLEND-OFF BYTE IDENTITY: ktc_blend_weight=0 + tep_te_uplift=1 returns
     the DP maps untouched (kill switch = the pre-#145 pipeline exactly).
     Mandatory guardrail.
  3. Fail-soft: _ktc_consensus swallows a fetch failure (→ {}), and the
     blend then leaves the maps DP-only.
  4. Universe unchanged: blending never adds/removes pool keys.
  5. Occupancy stays DP-shaped — rank-normalization keeps the #117 affine
     calibration (top asset ≈ 4 firsts; "worth a 1st or more" not inflated).
  6. #148: for the top-8 sf_tep TEs, the blended sf_tep seed value ≥ the
     player's 1qb seed value (a slight upgrade, not a downgrade).
  7. Copy-level (#124 value_rank remap): a 1QB→SF-TEP copy no longer
     demotes the top TEs below their 1QB tier.
"""
import json
from pathlib import Path

import pytest

import backend.data_loader as dl
from backend.data_loader import (
    seed_elo_for_value,
    parse_ktc_players,
    _apply_consensus_blend,
)
from backend.ranking_service import Player, RankingService, ORDERED_TIERS

_FIX = Path(__file__).parent / "fixtures"
_KTC_HTML = (_FIX / "ktc_rankings_snapshot_2026-07-17.html").read_text()
_PIPE = json.loads((_FIX / "ktc_blend_pipeline_2026-07-17.json").read_text())
_DP = _PIPE["dp"]
_DP_POS = _PIPE["dp_pos"]
_KTC = _PIPE["ktc"]

_FIRST_OR_BETTER = ("firsts_4plus", "firsts_3", "firsts_2", "first_1")


def _dp_maps(fmt):
    """(elo_map, value_map, pos_map) as _fetch_dynasty_process emits for the
    real 2026-07-17 pool (from the pipeline fixture)."""
    value_map = {k: float(v) for k, v in _DP[fmt].items()}
    elo_map = {k: round(seed_elo_for_value(v), 1) for k, v in value_map.items()}
    return elo_map, value_map, dict(_DP_POS)


@pytest.fixture(autouse=True)
def _reset_ktc_cache(monkeypatch):
    monkeypatch.setattr(dl, "_ktc_cache", None)
    monkeypatch.setattr(dl, "_ktc_fetched_at", 0.0)


def _use_fixture_ktc(monkeypatch):
    """Inject the 441-row matched KTC consensus (blend-math tests)."""
    monkeypatch.setattr(dl, "_ktc_consensus", lambda: _KTC)


# ---------------------------------------------------------------------------
# 1. Parser
# ---------------------------------------------------------------------------

def test_parse_ktc_players_extracts_and_drops_rdp():
    players = parse_ktc_players(_KTC_HTML)
    assert len(players) > 0
    positions = {p["position"] for p in players}
    assert positions <= {"QB", "RB", "WR", "TE"}
    assert "RDP" not in positions  # rookie draft picks excluded


def test_parse_ktc_players_raises_without_array():
    with pytest.raises(Exception):
        parse_ktc_players("<html><body>no array here</body></html>")


def test_real_ktc_consensus_parses_fixture_html(monkeypatch):
    """The real _ktc_consensus path (parse + name/id match) against the
    trimmed HTML fixture, with the crosswalk unavailable (name fallback)."""
    monkeypatch.setattr(dl, "_fetch_ktc_html", lambda timeout=15: _KTC_HTML)
    monkeypatch.setattr(dl, "_crosswalk_id_maps", lambda: ({}, {}))
    out = dl._ktc_consensus()
    assert out, "expected matched KTC rows"
    bijan = out.get("bijan robinson")
    assert bijan and bijan["pos"] == "RB"
    assert bijan["values"]["1qb_ppr"] > 0 and bijan["values"]["sf_tep"] > 0
    # sf_tep pulls the TEP variant: Brock Bowers' TE-premium SF value > his
    # plain 1QB value in the fixture.
    bowers = out.get("brock bowers")
    assert bowers["values"]["sf_tep"] > bowers["values"]["1qb_ppr"]


# ---------------------------------------------------------------------------
# 2. Blend-off byte identity (kill switch) — MANDATORY
# ---------------------------------------------------------------------------

def test_blend_off_is_byte_identical(monkeypatch):
    monkeypatch.setattr(dl, "_blend_config", lambda: (0.0, 1.0))
    for fmt in ("1qb_ppr", "sf_tep"):
        elo, val, pos = _dp_maps(fmt)
        elo_before, val_before = dict(elo), dict(val)
        out_elo, out_val = _apply_consensus_blend(fmt, elo, val, pos)
        assert out_elo == elo_before, f"{fmt}: elo map changed with blend off"
        assert out_val == val_before, f"{fmt}: value map changed with blend off"


def test_blend_off_never_touches_ktc(monkeypatch):
    """Weight 0 must not even reach KTC (no live egress from the kill switch)."""
    monkeypatch.setattr(dl, "_blend_config", lambda: (0.0, 1.0))

    def _boom():
        raise AssertionError("KTC fetched while blend disabled")

    monkeypatch.setattr(dl, "_ktc_consensus", _boom)
    elo, val, pos = _dp_maps("1qb_ppr")
    _apply_consensus_blend("1qb_ppr", elo, val, pos)


# ---------------------------------------------------------------------------
# 3. Fail-soft
# ---------------------------------------------------------------------------

def test_ktc_consensus_swallows_fetch_failure(monkeypatch):
    def _fail(timeout=15):
        raise OSError("KTC unreachable")

    monkeypatch.setattr(dl, "_fetch_ktc_html", _fail)
    assert dl._ktc_consensus() == {}


def test_blend_with_empty_ktc_is_dp_only(monkeypatch):
    monkeypatch.setattr(dl, "_blend_config", lambda: (0.5, 1.0))
    monkeypatch.setattr(dl, "_ktc_consensus", lambda: {})
    elo, val, pos = _dp_maps("1qb_ppr")
    val_before = dict(val)
    _, out_val = _apply_consensus_blend("1qb_ppr", elo, val, pos)
    assert out_val == val_before


# ---------------------------------------------------------------------------
# 4. Universe unchanged
# ---------------------------------------------------------------------------

def test_blend_preserves_pool_keys(monkeypatch):
    _use_fixture_ktc(monkeypatch)
    monkeypatch.setattr(dl, "_blend_config", lambda: (0.5, 1.18))
    for fmt in ("1qb_ppr", "sf_tep"):
        elo, val, pos = _dp_maps(fmt)
        keys_before = set(val)
        out_elo, out_val = _apply_consensus_blend(fmt, elo, val, pos)
        assert set(out_val) == keys_before, f"{fmt}: pool keys changed"
        assert set(out_elo) >= keys_before


# ---------------------------------------------------------------------------
# 5. Occupancy stays DP-shaped (no #117 recalibration break, no tier inflation)
# ---------------------------------------------------------------------------

def _occupancy(fmt, pos, value_map, pos_map):
    counts = {t: 0 for t in ORDERED_TIERS}
    counts[None] = 0
    for k, v in value_map.items():
        if pos_map[k] == pos:
            counts[RankingService.tier_for_elo(seed_elo_for_value(v), pos, fmt)] += 1
    return counts


@pytest.mark.parametrize("fmt", ("1qb_ppr", "sf_tep"))
def test_blended_occupancy_is_dynasty_sane(monkeypatch, fmt):
    _use_fixture_ktc(monkeypatch)
    monkeypatch.setattr(dl, "_blend_config", lambda: (0.5, 1.18))
    elo, val, pos = _dp_maps(fmt)
    _, out_val = _apply_consensus_blend(fmt, elo, val, pos)
    # Top asset still lands on a firsts tier (affine anchor holds).
    top = max(out_val.values())
    assert RankingService.tier_for_elo(seed_elo_for_value(top), "RB", fmt) in (
        "firsts_4plus", "firsts_3")
    # "Worth a 1st or more" per position stays bounded (FB-69 was inflation).
    for p in ("QB", "RB", "WR", "TE"):
        occ = _occupancy(fmt, p, out_val, pos)
        n = sum(occ[t] for t in _FIRST_OR_BETTER)
        assert n <= 40, f"{fmt}/{p}: {n} at first-round value — inflated"
        assert occ["second"] >= 3, f"{fmt}/{p}: empty 2nd tier"


# ---------------------------------------------------------------------------
# 6. #148 — sf_tep top TEs upgraded, not downgraded, vs their 1qb analogs
# ---------------------------------------------------------------------------

def test_sf_tep_top_tes_beat_their_1qb_seed(monkeypatch):
    _use_fixture_ktc(monkeypatch)
    monkeypatch.setattr(dl, "_blend_config", lambda: (0.5, 1.18))
    e1, v1, p1 = _dp_maps("1qb_ppr")
    es, vs, ps = _dp_maps("sf_tep")
    _, v1b = _apply_consensus_blend("1qb_ppr", e1, v1, p1)
    _, vsb = _apply_consensus_blend("sf_tep", es, vs, ps)

    te_1qb = sorted((v for k, v in v1b.items() if p1[k] == "TE"), reverse=True)
    te_sf = sorted((v for k, v in vsb.items() if ps[k] == "TE"), reverse=True)
    for i in range(8):
        assert te_sf[i] >= te_1qb[i], (
            f"TE #{i+1}: sf_tep seed {te_sf[i]:.0f} < 1qb {te_1qb[i]:.0f} "
            f"— TEs must be worth MORE in sf_tep, not less (#148)")


def test_uplift_off_leaves_sf_tep_te1_below_1qb(monkeypatch):
    """Root-cause pin: with the uplift disabled, the premium-less DP
    value_2qb (plus KTC blend alone) leaves the sf TE1 at/under 1qb TE1 —
    the exact demotion #148 reported. Justifies the multiplier."""
    _use_fixture_ktc(monkeypatch)
    monkeypatch.setattr(dl, "_blend_config", lambda: (0.5, 1.0))  # uplift off
    e1, v1, p1 = _dp_maps("1qb_ppr")
    es, vs, ps = _dp_maps("sf_tep")
    _, v1b = _apply_consensus_blend("1qb_ppr", e1, v1, p1)
    _, vsb = _apply_consensus_blend("sf_tep", es, vs, ps)
    te1_1qb = max(v for k, v in v1b.items() if p1[k] == "TE")
    te1_sf = max(v for k, v in vsb.items() if ps[k] == "TE")
    assert te1_sf < te1_1qb, "expected sf TE1 below 1qb TE1 without the uplift"


# ---------------------------------------------------------------------------
# 7. Copy-level: 1QB → SF-TEP copy no longer demotes top TEs (#124 remap)
# ---------------------------------------------------------------------------

def test_copy_1qb_to_sf_tep_does_not_demote_top_te(monkeypatch):
    """A user copies their 1QB board to SF-TEP. The value_rank remap
    (RankingService.apply_value_map) re-seeds each copied player from the
    TARGET format's consensus seeds at the user's rank order. With the #148
    uplift baked into the sf_tep seeds, the top TE lands at least as high as
    it did in 1QB — the copy stops demoting TEs."""
    _use_fixture_ktc(monkeypatch)
    monkeypatch.setattr(dl, "_blend_config", lambda: (0.5, 1.18))
    e1, v1, p1 = _dp_maps("1qb_ppr")
    es, vs, ps = _dp_maps("sf_tep")
    _, v1b = _apply_consensus_blend("1qb_ppr", e1, v1, p1)
    _, vsb = _apply_consensus_blend("sf_tep", es, vs, ps)

    te_ids = sorted((k for k in v1b if p1[k] == "TE"),
                    key=lambda k: -v1b[k])[:6]
    players = [Player(id=k, name=k, position="TE", team="AAA", age=25)
               for k in te_ids]
    sf_seeds = {k: round(seed_elo_for_value(vsb[k]), 1) for k in te_ids}
    to_svc = RankingService(players=players, seed_ratings=sf_seeds)
    to_svc._scoring_format = "sf_tep"

    to_svc.apply_value_map("TE", te_ids)   # copy 1QB order into SF-TEP
    ov = to_svc._elo_overrides

    top = te_ids[0]
    tier_1qb = RankingService.tier_for_elo(
        seed_elo_for_value(v1b[top]), "TE", "1qb_ppr")
    tier_sf = RankingService.tier_for_elo(ov[top], "TE", "sf_tep")
    order = list(ORDERED_TIERS)
    assert order.index(tier_sf) <= order.index(tier_1qb), (
        f"top TE demoted on copy: 1qb {tier_1qb} -> sf_tep {tier_sf}")
