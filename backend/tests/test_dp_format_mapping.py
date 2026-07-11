"""DynastyProcess per-format column mapping (bugs #113 / #106).

The owner reported 1QB consensus values "reflecting superflex valuations"
(#113) and Drake Maye ranking QB2 in 1QB vs QB9 in SF (#106). Investigation
(2026-07-11) verified the loader mapping is correct end-to-end — both
numbers faithfully mirror the DynastyProcess source (value_1qb tracks
FantasyPros' 1QB ECR, Spearman 1.0). These tests pin that correctness so a
future regression (crossed columns, single-sourced pool, defaulted format)
fails loudly instead of surfacing as a vague "values look off" report.

Three layers:
  1. The internal-key → DP-column mapping literal.
  2. _fetch_dynasty_process reads each format's OWN value column
     (synthetic CSV, network mocked).
  3. The checked-in pool snapshot has each format's cross-position
     signature: QBs are scarce in the 1QB top-20 and dominant in the SF
     top-20 — the exact fingerprint that distinguishes the two value sets.
"""
import io
import json
from pathlib import Path

import backend.data_loader as data_loader
from backend.data_loader import DP_SCORING_PARAM, _fetch_dynasty_process

_FIXTURE = (
    Path(__file__).parent / "fixtures" / "dp_values_snapshot_2026-07-10.json"
)
_POOL = json.loads(_FIXTURE.read_text())["values"]


# ── 1. Mapping literal ──────────────────────────────────────────────────────

def test_internal_format_keys_map_to_dp_columns():
    assert DP_SCORING_PARAM == {"1qb_ppr": "1qb", "sf_tep": "2qb"}


# ── 2. Loader reads the right column per format ────────────────────────────

_SYNTHETIC_CSV = (
    "player,pos,team,age,value_1qb,value_2qb\n"
    "Drake Maye,QB,NE,23.9,5438,6380\n"
    "Josh Allen,QB,BUF,30.1,6862,10208\n"
    "Bijan Robinson,RB,ATL,24.5,9580,8089\n"
)


class _FakeResponse(io.BytesIO):
    """Minimal stand-in for urlopen's context-manager response."""


def _mock_fetch(monkeypatch):
    monkeypatch.setattr(
        data_loader.urllib.request, "urlopen",
        lambda req, timeout=10: _FakeResponse(_SYNTHETIC_CSV.encode("utf-8")),
    )


def test_each_format_reads_its_own_value_column(monkeypatch):
    _mock_fetch(monkeypatch)
    _, v1 = _fetch_dynasty_process(scoring="1qb_ppr")
    _, v2 = _fetch_dynasty_process(scoring="sf_tep")

    # 1qb_ppr → value_1qb column, sf_tep → value_2qb column
    assert v1["drake maye"] == 5438
    assert v2["drake maye"] == 6380
    assert v1["josh allen"] == 6862
    assert v2["josh allen"] == 10208
    # A known-divergent player must differ across formats — a single-sourced
    # or crossed pool collapses this.
    assert v1["drake maye"] != v2["drake maye"]


def test_raw_dp_suffixes_accepted_too(monkeypatch):
    _mock_fetch(monkeypatch)
    _, via_internal = _fetch_dynasty_process(scoring="sf_tep")
    _, via_raw = _fetch_dynasty_process(scoring="2qb")
    assert via_internal == via_raw


# ── 3. Snapshot fingerprint: QB share of the cross-position top-20 ─────────
# In real 1QB dynasty values QBs are heavily discounted (typically one QB in
# the overall top-20); in Superflex they dominate it. If the pools were ever
# crossed or single-sourced, these two assertions cannot both hold.

def _qb_count_in_top20(fmt: str) -> int:
    tagged = [
        (value, pos)
        for pos, values in _POOL[fmt].items()
        for value in values
    ]
    tagged.sort(key=lambda t: t[0], reverse=True)
    return sum(1 for _, pos in tagged[:20] if pos == "QB")


def test_1qb_top20_has_few_qbs():
    assert _qb_count_in_top20("1qb_ppr") <= 3


def test_sf_top20_is_qb_heavy():
    assert _qb_count_in_top20("sf_tep") >= 6


def test_top_qb_worth_far_more_in_sf():
    top_qb_1qb = max(_POOL["1qb_ppr"]["QB"])
    top_qb_sf = max(_POOL["sf_tep"]["QB"])
    assert top_qb_sf > top_qb_1qb * 1.3
