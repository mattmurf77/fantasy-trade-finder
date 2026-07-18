"""
data_loader.py — Fantasy Trade Finder
======================================
Fetches the DynastyProcess consensus values CSV and maps each player's
dynasty trade value onto an initial Elo rating.

Source: https://github.com/dynastyprocess/data
File:   files/values-players.csv

CSV columns used:
  player      — player name (string)
  pos         — position: QB | RB | WR | TE
  value_1qb   — dynasty trade value, 0-10000 scale (1QB scoring)
  value_2qb   — dynasty trade value, 0-10000 scale (Superflex/2QB)

Elo seeding formula (recalibrated 2026-07-12, feedback #117 — see
seed_elo_for_value below):
  DP values are a trade-value scale, so they map AFFINELY onto the trade
  engine's value space and only then back onto Elo through the inverse of
  trade_service.elo_to_value (value = 1000·e^(0.005·(elo−1500))):

      v(dp)  = V_FLOOR + (dp / VALUE_MAX) × (V_CEIL − V_FLOOR)
      elo(dp) = 1500 + ln(v / 1000) / 0.005

  anchored at both ends:
  → value 10000 ≈ Elo 1927  (= value_to_elo(4 × value(Mid 1st)) — the top
                              consensus asset is worth ≈ 4 firsts, matching
                              dynasty-market pricing; pre-#117 the linear map
                              capped at Elo 1800 ≈ 2.1 firsts, so top assets
                              could never reach the multi-first tiers)
  → value     0 ≈ Elo 1200  (waiver/depth floor — unchanged from the old map)

This gives every player a cross-position baseline derived from community
consensus. User swipes personalise the rankings from there.

Since 2026-07-17 (#145/#148) the DP baseline is blended with KeepTradeCut
before Elo seeding — KTC rank-normalized onto the DP value curve, weighted
by model_config `ktc_blend_weight` — and sf_tep TE values get the
`tep_te_uplift` TE-premium multiplier. See the "KeepTradeCut consensus
blend" section below; both knobs at neutral (0 / 1) reproduce the pure-DP
pipeline byte-for-byte.
"""

import csv
import io
import json
import math
import os
import pathlib
import re
import threading
import time
import urllib.request
from typing import Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VALUES_URL = (
    "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values-players.csv"
)

ELO_MIN   = 1200.0     # seed Elo at DP value 0 (the affine map's low anchor)
VALUE_MAX = 10_000.0

# Default elo_value_* curve constants (trade_service._DEFAULT_CFG). Hardcoded
# here — like GENERIC_PICK_SEEDS in server.py — because seeds are baked at
# pool build; the ≈-Elo anchors above assume this default curve.
_SEED_VALUE_K    = 0.005
_SEED_VALUE_REF  = 1500.0
_SEED_VALUE_BASE = 1000.0
_MID_FIRST_ELO   = 1650.0   # GENERIC_PICK_SEEDS[(1, "Mid")] — the base first

# Value-space anchors: DP 0 → the old floor Elo 1200 (≈ 223), DP 10000 → the
# 4-firsts rung (4 × value(Mid 1st) ≈ 8468 → Elo ≈ 1927.3).
SEED_VALUE_FLOOR = _SEED_VALUE_BASE * math.exp(
    _SEED_VALUE_K * (ELO_MIN - _SEED_VALUE_REF))
SEED_VALUE_CEIL = 4.0 * _SEED_VALUE_BASE * math.exp(
    _SEED_VALUE_K * (_MID_FIRST_ELO - _SEED_VALUE_REF))


def seed_elo_for_value(value: float) -> float:
    """Map a DynastyProcess value (0–10000, clamped) to a seed Elo.

    DP values are read as a linear trade-value scale: they map affinely onto
    the trade engine's value space (SEED_VALUE_FLOOR..SEED_VALUE_CEIL) and
    then back onto Elo through the inverse of the exponential Elo↔value
    curve. Monotone; DP 0 → Elo 1200, DP 10000 → Elo ≈ 1927.3 (the 4-firsts
    anchor rung). See the module docstring for the recalibration rationale.
    """
    v = SEED_VALUE_FLOOR + (
        min(float(value), VALUE_MAX) / VALUE_MAX
    ) * (SEED_VALUE_CEIL - SEED_VALUE_FLOOR)
    return _SEED_VALUE_REF + math.log(v / _SEED_VALUE_BASE) / _SEED_VALUE_K

# Positions we care about
VALID_POSITIONS = {"QB", "RB", "WR", "TE"}

# Supported scoring formats — each produces an independent rank set.
# The values on the right are DynastyProcess's column suffix (without the
# "value_" prefix), used by _fetch_dynasty_process(scoring=...).
SCORING_FORMATS = ("1qb_ppr", "sf_tep")
DEFAULT_SCORING = "1qb_ppr"
# Map our internal keys → DP's scoring parameter
DP_SCORING_PARAM = {
    "1qb_ppr": "1qb",
    "sf_tep":  "2qb",
}
# Reverse map: DP column suffix → internal format key (blend + TEP uplift
# are keyed by internal format).
DP_PARAM_TO_FORMAT = {v: k for k, v in DP_SCORING_PARAM.items()}

# ---------------------------------------------------------------------------
# KeepTradeCut consensus blend (#145) + sf_tep TE premium uplift (#148)
# ---------------------------------------------------------------------------
# KTC has no official API. The dynasty-rankings page embeds its full top-500
# player list as a `var playersArray = [...]` literal in the HTML; each entry
# carries BOTH formats (oneQBValues / superflexValues) plus TE-premium
# variants (tep/tepp/teppp), so ONE polite GET per boot (24h in-memory TTL)
# serves both format builds. This is an unsanctioned surface — expect it to
# break without notice (see docs/runbook.md → "KTC consensus blend").
# Fail-soft everywhere: any failure → DP-only seeds, logged, never blocks
# boot. Kill switch: model_config ktc_blend_weight = 0 (DP-only,
# byte-identical to the pre-#145 pipeline when tep_te_uplift is also 1).
#
# Blend design ("values in, same shape out"):
#   1. NORMALIZE — KTC's value curve is much fatter in the mid-range than
#      DP's (naive linear 0-9999→0-10000 averaging inflated the per-position
#      "worth a 1st or more" cohort from ~36 to ~86 on 2026-07-17 data — the
#      FB-69 tier-inflation failure mode). So KTC is normalized RANK-wise
#      onto the DP value curve per format: the KTC-rank-i matched player gets
#      the i-th largest DP pool value. This keeps the value distribution
#      (and hence tier occupancy / the #117 affine calibration) DP-shaped
#      while importing KTC's opinion of the ORDERING.
#   2. BLEND — per matched player: (1-w)·dp + w·ktc_on_dp_curve, with
#      w = model_config ktc_blend_weight. Unmatched pool players keep pure
#      DP; unmatched KTC players are ignored (pool universe unchanged).
#   3. GUARD — if the blended max slips below the DP max (sources disagree
#      on the #1 asset), rescale so the top asset still lands on the
#      4-firsts rung (the #117 anchor). No-op when sources agree.
#   4. TEP UPLIFT (#148) — DP's value_2qb column carries no TE premium
#      (sf_tep TE values sit ~25% BELOW their 1qb analogs), so cross-format
#      copies demoted TEs. tep_te_uplift multiplies TE values in sf_tep
#      only (default 1.18, calibrated 2026-07-17 so the top-8 sf_tep TE
#      seeds clear their 1qb analogs — KTC's own TEP effect is ≈ +11%).
#
# Matching follows the #127 crosswalk rules: id-based where possible
# (KTC playerID / mflid → DP db_playerids ktc_id/mfl_id → DP name), name
# fallback otherwise, and NEVER across positions.

KTC_RANKINGS_URL = "https://keeptradecut.com/dynasty-rankings"
KTC_VALUE_MAX = 9999.0          # KTC's published scale tops out at 9999
_KTC_TTL_SECONDS = 24 * 3600    # one polite fetch per day, like the DP CSV

# KTC serves Cloudflare-guarded HTML — bare urllib signatures risk a 403
# (same lesson as the Sleeper 1010 / ESPN browser-header fixes).
_KTC_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# Where each internal format reads its value inside a playersArray entry.
# sf_tep uses the TEP (+0.5 TE premium) variant — that IS our format;
# 1qb_ppr is plain 1QB (no premium).
_KTC_FORMAT_PATH = {
    "1qb_ppr": ("oneQBValues", None),
    "sf_tep":  ("superflexValues", "tep"),
}

_ktc_lock = threading.Lock()
_ktc_cache: dict[str, dict] | None = None   # {key: {"pos": .., "values": {fmt: v}}}
_ktc_fetched_at: float = 0.0

# Blend defaults — mirrored in database._MODEL_CONFIG_DEFAULTS (the DB rows
# are authoritative at runtime; these are the no-DB fallback).
KTC_BLEND_WEIGHT_DEFAULT = 0.5
TEP_TE_UPLIFT_DEFAULT = 1.18


def _blend_config() -> tuple[float, float]:
    """(ktc_blend_weight, tep_te_uplift) from model_config, defaults on any
    failure. Weight clamped to [0, 1]; uplift floored at 0."""
    w, u = KTC_BLEND_WEIGHT_DEFAULT, TEP_TE_UPLIFT_DEFAULT
    try:
        from .database import get_config
        cfg = get_config()
        w = float(cfg.get("ktc_blend_weight", w))
        u = float(cfg.get("tep_te_uplift", u))
    except Exception:
        pass
    return max(0.0, min(1.0, w)), max(0.0, u)


def parse_ktc_players(html: str) -> list[dict]:
    """Extract the embedded playersArray from KTC rankings-page HTML.

    Returns the raw player dicts filtered to real players (KTC also lists
    rookie draft picks under position "RDP" — excluded; the pool's generic
    picks are seeded separately). Raises on parse failure (callers treat
    any exception as "KTC unavailable")."""
    m = re.search(r"var\s+playersArray\s*=\s*(\[.*?\]);", html, re.S)
    if not m:
        raise ValueError("playersArray not found in KTC page")
    players = json.loads(m.group(1))
    return [p for p in players if p.get("position") in VALID_POSITIONS]


def _fetch_ktc_html(timeout: int = 15) -> str:
    """Fetch the KTC rankings page (or the test-seam file).

    Hermetic-run rules mirror the DP seam: when FTF_KTC_VALUES_FILE is set
    it is served instead of the network; under FTF_TEST_MODE (or when the
    DP seam is active) a missing KTC file means KTC is simply OFF — never
    a live egress from a test run."""
    _ktc_file = os.environ.get("FTF_KTC_VALUES_FILE")
    if _ktc_file:
        return pathlib.Path(_ktc_file).read_text()  # missing file = loud, by design
    if os.environ.get("FTF_TEST_MODE") == "1" or os.environ.get("FTF_DP_VALUES_FILE"):
        raise RuntimeError("hermetic run without FTF_KTC_VALUES_FILE — KTC off")
    req = urllib.request.Request(KTC_RANKINGS_URL, headers=_KTC_BROWSER_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _crosswalk_id_maps() -> tuple[dict, dict]:
    """(by_ktc_id, by_mfl_id) from the cached DP db_playerids crosswalk
    (espn_service fetches/caches it with a bundled-snapshot fallback).
    Empty dicts on any failure — matching then falls back to name+pos."""
    try:
        from .espn_service import get_crosswalk
        xw = get_crosswalk()
        return xw.by_ktc_id, xw.by_mfl_id
    except Exception:
        return {}, {}


def _ktc_consensus() -> dict[str, dict]:
    """Fetch+parse+match KTC once per TTL. Returns
        { normalised_sleeper_name: {"pos": str, "values": {fmt: float}} }
    keyed the same way as the DP maps (DP_TO_SLEEPER_NAME applied), or {}
    when KTC is unavailable. Never raises."""
    global _ktc_cache, _ktc_fetched_at
    with _ktc_lock:
        now = time.time()
        if _ktc_cache is not None and (now - _ktc_fetched_at) < _KTC_TTL_SECONDS:
            return _ktc_cache
        try:
            players = parse_ktc_players(_fetch_ktc_html())
        except Exception as e:
            print(f"⚠️  KTC fetch failed ({e}) — DP-only consensus seeds")
            # Cache the failure for the TTL too: a broken/blocked endpoint
            # shouldn't be re-hammered by every pool rebuild in one process.
            _ktc_cache, _ktc_fetched_at = {}, now
            return _ktc_cache
        by_ktc_id, by_mfl_id = _crosswalk_id_maps()
        out: dict[str, dict] = {}
        for p in players:
            pos = p.get("position")
            key = None
            # id-based first (#127: ids beat names)…
            xw = (by_ktc_id.get(str(p.get("playerID") or ""))
                  or by_mfl_id.get(str(p.get("mflid") or "")))
            if xw and xw[1] == pos:
                normed = normalise_name(xw[0])
                key = DP_TO_SLEEPER_NAME.get(normed, normed)
            if key is None:
                normed = normalise_name(p.get("playerName") or "")
                key = DP_TO_SLEEPER_NAME.get(normed, normed)
            if not key or key in DP_EXCLUDED:
                continue
            values = {}
            for fmt, (block, variant) in _KTC_FORMAT_PATH.items():
                node = p.get(block) or {}
                if variant:
                    node = node.get(variant) or {}
                v = node.get("value")
                if isinstance(v, (int, float)) and v > 0:
                    values[fmt] = float(v)
            if values:
                # setdefault: on a key collision keep the higher-ranked entry
                out.setdefault(key, {"pos": pos, "values": values})
        print(f"✅ Loaded {len(out)} KTC consensus values "
              f"(top-{len(players)} page snapshot)")
        _ktc_cache, _ktc_fetched_at = out, now
        return _ktc_cache


def _apply_consensus_blend(
    fmt: str,
    elo_map: dict[str, float],
    value_map: dict[str, float],
    pos_map: dict[str, str],
) -> tuple[dict[str, float], dict[str, float]]:
    """Blend KTC into the DP value/elo maps for one format (see the section
    comment above for the design). Returns (elo_map, value_map) — the inputs
    untouched (byte-identical) when both knobs are neutral."""
    weight, uplift = _blend_config()
    if not value_map:
        return elo_map, value_map

    blended = dict(value_map)
    if weight > 0.0:
        ktc = _ktc_consensus()
        # #127: a KTC row may only blend into a pool player at the SAME
        # position — never cross-position, even on a name hit.
        matched = [
            (k, ktc[k]["values"][fmt])
            for k in value_map
            if k in ktc and ktc[k]["pos"] == pos_map.get(k)
            and fmt in ktc[k]["values"]
        ]
        if matched:
            # Rank-normalize KTC onto the DP value curve, then weighted-avg.
            curve = sorted(value_map.values(), reverse=True)
            matched.sort(key=lambda t: (-t[1], -value_map[t[0]], t[0]))
            ktc_on_dp = {k: curve[i] for i, (k, _) in enumerate(matched)}
            for k, _ in matched:
                blended[k] = (1.0 - weight) * value_map[k] + weight * ktc_on_dp[k]
            # Top-anchor guard: DP-max-equivalent must stay on the 4-firsts
            # rung (seed_elo_for_value clamps at VALUE_MAX).
            dp_max = min(max(value_map.values()), VALUE_MAX)
            blended_max = max(blended.values())
            if 0 < blended_max < dp_max:
                scale = dp_max / blended_max
                blended = {k: v * scale for k, v in blended.items()}
            print(f"✅ Blended KTC consensus into {fmt} "
                  f"(weight {weight:g}, {len(matched)}/{len(value_map)} matched)")

    if fmt == "sf_tep" and uplift != 1.0:
        blended = {
            k: (v * uplift if pos_map.get(k) == "TE" else v)
            for k, v in blended.items()
        }

    if blended == value_map:                     # both knobs neutral / no-op
        return elo_map, value_map
    blended = {k: round(v, 1) for k, v in blended.items()}
    for k, v in blended.items():
        elo_map[k] = round(seed_elo_for_value(v), 1)
    return elo_map, blended

# ---------------------------------------------------------------------------
# Name-mismatch reference table: DynastyProcess → Sleeper
# ---------------------------------------------------------------------------
# DP includes suffixes (Jr., Sr., II, III) that Sleeper strips.  This table
# maps the normalised DP name to the normalised Sleeper name so we can join
# them correctly without a lossy last-name fallback.
#
# Generated 2026-04-12 from a full cross-reference of the DP values CSV
# against the Sleeper player cache.  Validated by the user.

DP_TO_SLEEPER_NAME: dict[str, str] = {
    "aaron jones sr": "aaron jones",
    "anthony richardson sr": "anthony richardson",
    "brian robinson jr": "brian robinson",
    "brian thomas jr": "brian thomas",
    "calvin austin iii": "calvin austin",
    "cedrick wilson jr": "cedrick wilson",
    "chris brazzell ii": "chris brazzell",
    "chris godwin jr": "chris godwin",
    "chris rodriguez jr": "chris rodriguez",
    "darrell henderson jr": "darrell henderson",
    "deebo samuel sr": "deebo samuel",
    "donte thornton jr": "donte thornton",
    "efton chism iii": "efton chism",
    "erick all jr": "erick all",
    "gardner minshew ii": "gardner minshew",
    "harold fannin jr": "harold fannin",
    "henry ruggs iii": "henry ruggs",
    "james cook iii": "james cook",
    "jeff wilson jr": "jeff wilson",
    "jimmy horn jr": "jimmy horn",
    "joe milton iii": "joe milton",
    "john metchie iii": "john metchie",
    "kenneth walker iii": "kenneth walker",
    "kevin coleman jr": "kevin coleman",
    "kyle pitts sr": "kyle pitts",
    "laviska shenault jr": "laviska shenault",
    "lequint allen jr": "lequint allen",
    "lew nichols iii": "lew nichols",
    "luther burden iii": "luther burden",
    "marvin harrison jr": "marvin harrison",
    "marvin mims jr": "marvin mims",
    "mecole hardman jr": "mecole hardman",
    "michael penix jr": "michael penix",
    "michael pittman jr": "michael pittman",
    "mike washington jr": "mike washington",
    "odell beckham jr": "odell beckham",
    "ollie gordon ii": "ollie gordon",
    "omar cooper jr": "omar cooper",
    "oronde gadsden ii": "oronde gadsden",
    "patrick mahomes ii": "patrick mahomes",
    "pierre strong jr": "pierre strong",
    "rayray mccloud iii": "rayray mccloud",
    "robert henry jr": "robert henry",
    "russell gage jr": "russell gage",
    "thomas fidone ii": "thomas fidone",
    "travis etienne jr": "travis etienne",
    "trent sherfield sr": "trent sherfield",
    "tyrone tracy jr": "tyrone tracy",
    "velus jones jr": "velus jones",
    "vinny anthony ii": "vinny anthony",
}

# DP players with no valid Sleeper counterpart — exclude from the pool
DP_EXCLUDED: set[str] = {
    "bam knight",
    "barion brown",
    "dallen bentley",
    "frank gore jr",
    "terion stewart",
    "tyren montgomery",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_consensus_elo(
    scoring: str = "1qb",          # "1qb" or "2qb" (superflex)
    fallback_elo: float = 1500.0,  # rating for players not found in the data
    timeout: int = 10,
) -> dict[str, float]:
    """
    Fetch DynastyProcess values and return a dict of:
        { normalised_player_name: initial_elo_rating }

    Keys are normalised (lowercase, alphanumeric only) so they can be
    matched against your player pool with `normalise_name()`.

    Returns an empty dict (falls back to flat 1500) if the fetch fails.
    """
    elo_map, _, _ = _fetch_dynasty_process(scoring=scoring, timeout=timeout)
    return elo_map


def load_consensus_values(
    scoring: str = "1qb",
    timeout: int = 10,
) -> dict[str, float]:
    """
    Fetch DynastyProcess values and return a dict of:
        { normalised_player_name: raw_dynasty_value (0-10000) }

    Only includes players with value > 0.
    Used to determine which Sleeper players should be in the universal
    ranking pool (any player with a positive dynasty trade value).
    """
    _, value_map, _ = _fetch_dynasty_process(scoring=scoring, timeout=timeout)
    return value_map


def load_consensus_maps(
    scoring: str = "1qb",
    timeout: int = 10,
) -> tuple[dict[str, float], dict[str, float], dict[str, str]]:
    """
    Fetch DynastyProcess values ONCE and return all three name-keyed maps:
        (elo_map, value_map, pos_map)

    pos_map = { normalised_player_name: DP position (QB/RB/WR/TE) } and
    exists so joins against the Sleeper pool can be position-strict
    (feedback #127): two different NFL players can share a normalised name
    (e.g. Kenneth Walker the veteran WR vs Kenneth Walker III the RB), and
    a name-only join pulls both into the pool under one DP value.
    """
    return _fetch_dynasty_process(scoring=scoring, timeout=timeout)


def _fetch_dynasty_process(
    scoring: str = "1qb",
    timeout: int = 10,
) -> tuple[dict[str, float], dict[str, float], dict[str, str]]:
    """
    Internal: fetch DynastyProcess CSV and return:
        (elo_map, value_map, pos_map)
    where:
        elo_map   = { normalised_name: initial_elo }
        value_map = { normalised_name: raw_value }  (only for value > 0)
        pos_map   = { normalised_name: DP position (QB/RB/WR/TE) }

    pos_map lets consumers join by name AND position — a name-only join
    can cross positions when two NFL players share a name (#127).

    Accepts either DP's raw column suffix ("1qb" / "2qb") OR our internal
    format keys ("1qb_ppr" / "sf_tep").
    """
    # Translate our internal format key into DP's column suffix if needed
    if scoring in DP_SCORING_PARAM:
        scoring = DP_SCORING_PARAM[scoring]
    value_col = f"value_{scoring}"

    # UI-test harness seam (docs/plans/mobile-testing/lld.md §4.3): the DP CSV
    # is a live egress the fixture seam can't see. FTF_DP_VALUES_FILE serves a
    # local DP-shaped CSV through the IDENTICAL parse path; under FTF_TEST_MODE
    # it is mandatory — the silent flat-Elo fallback below would otherwise
    # reshape the universal pool mid-test without any counter tripping.
    _dp_file = os.environ.get("FTF_DP_VALUES_FILE")
    if os.environ.get("FTF_TEST_MODE") == "1" and not _dp_file:
        raise RuntimeError(
            "FTF_TEST_MODE=1 requires FTF_DP_VALUES_FILE (hermetic DynastyProcess values)")
    if _dp_file:
        raw = pathlib.Path(_dp_file).read_text()  # missing file = loud failure, by design
    else:
        try:
            req = urllib.request.Request(
                VALUES_URL,
                headers={"User-Agent": "FantasyTradeFinder/1.0"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
        except Exception as e:
            print(f"⚠️  DynastyProcess fetch failed ({e}) — using flat Elo baseline")
            return {}, {}, {}

    elo_map: dict[str, float] = {}
    value_map: dict[str, float] = {}
    pos_map: dict[str, str] = {}

    reader = csv.DictReader(io.StringIO(raw))
    for row in reader:
        pos = (row.get("pos") or "").strip().upper()
        if pos not in VALID_POSITIONS:
            continue

        name_raw = (row.get("player") or "").strip()
        if not name_raw:
            continue

        value_str = (row.get(value_col) or "0").strip()
        try:
            value = float(value_str)
        except ValueError:
            value = 0.0

        elo = seed_elo_for_value(value)
        normed = normalise_name(name_raw)

        # Skip DP players with no valid Sleeper counterpart
        if normed in DP_EXCLUDED:
            continue

        # Translate DP name to Sleeper name via reference table
        lookup_key = DP_TO_SLEEPER_NAME.get(normed, normed)

        elo_map[lookup_key] = round(elo, 1)
        pos_map[lookup_key] = pos
        if value > 0:
            value_map[lookup_key] = value

    print(f"✅ Loaded {len(elo_map)} player values from DynastyProcess "
          f"({len(value_map)} with value > 0)")

    # #145/#148 — blend KTC into the DP baseline + sf_tep TE premium uplift.
    # Fail-soft: any KTC problem leaves the maps DP-only. With
    # ktc_blend_weight=0 and tep_te_uplift=1 the maps are returned untouched.
    fmt_key = DP_PARAM_TO_FORMAT.get(scoring, scoring)
    elo_map, value_map = _apply_consensus_blend(fmt_key, elo_map, value_map, pos_map)
    return elo_map, value_map, pos_map


def seed_elo_for_players(
    players,                        # list[Player]
    elo_map: dict[str, float],
    fallback_elo: float = 1500.0,
    pos_map: dict[str, str] | None = None,
) -> dict[str, float]:
    """
    Match your Player objects against the DynastyProcess elo_map and
    return a dict of { player.id: initial_elo }.

    Matching is by exact normalised name.  The DP_TO_SLEEPER_NAME
    reference table (applied in _fetch_dynasty_process) has already
    translated DP names into Sleeper names, so no fuzzy fallback is needed.

    When `pos_map` is provided (load_consensus_maps), the match is also
    position-strict: a name hit whose DP position differs from the
    player's position is treated as unmatched (#127 — never name-match
    across positions; two NFL players can share a name).

    Unmatched players receive fallback_elo (1500 by default).
    """
    seeded: dict[str, float] = {}
    unmatched: list[str] = []

    for player in players:
        key = normalise_name(player.name)

        if key in elo_map and (
            pos_map is None or pos_map.get(key) == player.position
        ):
            seeded[player.id] = elo_map[key]
        else:
            seeded[player.id] = fallback_elo
            unmatched.append(player.name)

    if unmatched:
        print(f"ℹ️  {len(unmatched)} players unmatched in consensus data "
              f"(using {fallback_elo} Elo): {', '.join(unmatched[:5])}"
              + (" …" if len(unmatched) > 5 else ""))

    return seeded


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalise_name(name: str) -> str:
    """Lowercase, remove punctuation/accents, collapse whitespace."""
    name = name.lower()
    name = re.sub(r"[^a-z0-9 ]", "", name)   # strip punctuation
    name = re.sub(r"\s+", " ", name).strip()
    return name
