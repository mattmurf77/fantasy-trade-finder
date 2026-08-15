"""
data_loader.py — Fantasy Trade Finder
======================================
Fetches the DynastyProcess consensus values CSV and maps each player's
dynasty trade value onto an initial Elo rating.

Source: https://github.com/dynastyprocess/data
File:   files/values-players.csv
        files/values.csv — the combined file, read ONLY for its `pos == "PICK"`
        rows (per-slot draft-pick market prices, display-only; see
        load_pick_slot_values near the bottom of this module).

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

Since 2026-08-14 (#313) 1QB QB seeds are additionally compressed so no
quarterback prices above one first-round pick in a 1QB league — monotone
piecewise-linear, order-preserving, knobs `qb_1qb_cap_elo` /
`qb_1qb_cap_knee_elo` (either <= 0 disables). See the "#313 — 1QB QB
consensus compression" section below. All four knobs neutral reproduces
the pure-DP pipeline byte-for-byte.
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

# Rookie-draft M6 — DynastyProcess's *combined* file. Same columns as
# values-players.csv, but it additionally carries `pos == "PICK"` rows: the
# per-slot current-year curve ("2026 Pick 1.01" … "2026 Pick 5.12") and the
# future-year rungs ("2027 Early 1st", "2028 2nd", …). This is a SECOND remote
# file, so it has its own hermetic seam (FTF_DP_PICK_VALUES_FILE) —
# see load_pick_slot_values below.
PICK_VALUES_URL = (
    "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values.csv"
)

ELO_MIN   = 1200.0     # seed Elo at DP value 0 (the affine map's low anchor)
VALUE_MAX = 10_000.0

# Default elo_value_* curve constants (trade_service._DEFAULT_CFG). Hardcoded
# here — like GENERIC_PICK_SEEDS in backend/pick_values.py — because seeds are
# baked at pool build; the ≈-Elo anchors above assume this default curve.
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


def seed_value_for_elo(elo: float) -> float:
    """Inverse of `seed_elo_for_value`: seed Elo → the DP-scale value that
    seeds it.

    Used by the #313 1QB QB compression to express its knee/cap knobs — which
    are authored in *Elo* (tier-band space, where the operator reads them) —
    as the DP-scale numbers the compression actually operates on. Exact
    inverse over the affine map's range; values above VALUE_MAX are not
    representable (seed_elo_for_value clamps there).
    """
    v = _SEED_VALUE_BASE * math.exp(_SEED_VALUE_K * (float(elo) - _SEED_VALUE_REF))
    return (v - SEED_VALUE_FLOOR) / (SEED_VALUE_CEIL - SEED_VALUE_FLOOR) * VALUE_MAX

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


# ---------------------------------------------------------------------------
# #313 — 1QB QB consensus compression (cap at "1 1st")
# ---------------------------------------------------------------------------
# In 1QB leagues the market does not pay two firsts for a quarterback, but the
# DP → seed-Elo affine map (#117) put the top 1QB QBs inside the `firsts_2`
# band (Josh Allen value_1qb 7025 → Elo 1858.9, live 2026-08-13). The tier
# LABEL is derived client-side from the served Elo, so the defect is the
# VALUE: the fix re-prices, it does not relabel. tier_config.json and every
# client band mirror stay untouched.
#
# Shape: monotone piecewise-linear compression of 1QB QB values, applied
# post-blend / pre-Elo-map. Identity at or below the knee; above it, the
# stretch (knee, VALUE_MAX] is squeezed onto (knee, cap]. Because the map is
# strictly increasing, the QB board's ORDER is preserved — a hard clamp would
# tie Allen/Maye/Daniels at the cap, which a draft board cannot use.
QB_1QB_CAP_ELO_DEFAULT = 1785.0        # top of `first_1` (firsts_2 starts 1788)
QB_1QB_CAP_KNEE_ELO_DEFAULT = 1580.0   # `first_1` floor — below this, identity


def _qb_cap_config() -> tuple[float, float]:
    """(qb_1qb_cap_elo, qb_1qb_cap_knee_elo) from model_config, defaults on
    any failure. Either knob <= 0 is the kill switch (see
    `_compress_qb_1qb_values`)."""
    cap, knee = QB_1QB_CAP_ELO_DEFAULT, QB_1QB_CAP_KNEE_ELO_DEFAULT
    try:
        from .database import get_config
        cfg = get_config()
        cap = float(cfg.get("qb_1qb_cap_elo", cap))
        knee = float(cfg.get("qb_1qb_cap_knee_elo", knee))
    except Exception:
        pass
    return cap, knee


def _compress_qb_1qb_values(
    value_map: dict[str, float],
    pos_map: dict[str, str],
) -> dict[str, float]:
    """Compress QB values so no QB seeds above the cap Elo. 1QB only —
    the caller applies the format guard.

    Returns a NEW map; every non-QB and every at-or-below-knee QB carries
    through byte-identical. Kill switch: either knob <= 0 (or a degenerate
    knee/cap ordering) returns the input unchanged.
    """
    cap_elo, knee_elo = _qb_cap_config()
    if cap_elo <= 0.0 or knee_elo <= 0.0:
        return value_map
    knee = seed_value_for_elo(knee_elo)
    cap = seed_value_for_elo(cap_elo)
    if not (0.0 <= knee < cap < VALUE_MAX):
        # Degenerate config (knee above cap, cap at/above the pool ceiling,
        # knee below the seed floor) — nothing sane to compress onto.
        return value_map
    # Slope < 1: (knee, VALUE_MAX] → (knee, cap].
    slope = (cap - knee) / (VALUE_MAX - knee)
    out = dict(value_map)
    for k, raw in value_map.items():
        if pos_map.get(k) != "QB":
            continue
        v = min(float(raw), VALUE_MAX)   # same ceiling seed_elo_for_value uses
        if v > knee:
            out[k] = knee + (v - knee) * slope
    return out


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
    # obs.api_events — KTC is a separate external call surface from DP (same
    # module, different host; unsanctioned HTML scrape — dynastyprocess.md §6).
    from . import api_observability as _api_obs
    with _api_obs.observe_call("ktc", "rankings_html") as _ob:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        _ob.ok(status=getattr(resp, "status", 200), response_bytes=len(raw))
    return raw


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

    # #313: last, so KTC's rank-normalization (and its top-anchor rescale)
    # cannot push a QB back over the cap. 1QB only — sf_tep QBs are supposed
    # to price at multiple firsts.
    if fmt == "1qb_ppr":
        blended = _compress_qb_1qb_values(blended, pos_map)

    if blended == value_map:                     # every knob neutral / no-op
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
    # 2026-08-10: DP's CURRENT board says "Kenneth Walker III"; its 2022-era
    # boards said "Ken Walker III". Both map to the same Sleeper player, so
    # dated historical boards (backend/dp_values_history.py, used by the
    # outlook backtests) join instead of silently dropping DP rank 61.
    # Inert on the live path while DP emits the long form. The RB/WR
    # "Kenneth Walker" collision is handled downstream by the position-strict
    # join (#127's pos_map), not by this name map.
    "ken walker iii": "kenneth walker",
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
            # obs.api_events — public CSV, nothing to redact; the Elo-seed
            # pipeline's only staleness/latency signal (dynastyprocess.md §7).
            from . import api_observability as _api_obs
            with _api_obs.observe_call("dynastyprocess", "values_players",
                                       format=scoring) as _ob:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read().decode("utf-8")
                _ob.ok(status=getattr(resp, "status", 200),
                       response_bytes=len(raw))
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


# ---------------------------------------------------------------------------
# Draft-pick market prices — DISPLAY ONLY (rookie-draft M6)
# ---------------------------------------------------------------------------
# DynastyProcess's combined `files/values.csv` prices individual draft SLOTS
# ("2026 Pick 1.01") as well as the year rungs we already model. The values are
# on the SAME 0-10000 scale as the player rows, so seed_elo_for_value maps them
# into our Elo space unchanged.
#
# Bound (plan KD-9 / hld §2.2): these prices are served on the Draft Room
# board's `order[]` entries and NOWHERE ELSE. `pick_values.GENERIC_PICK_SEEDS`,
# the tier ladder, the tier bands and the trade engine do not read this map —
# DP's current-year slot curve is far steeper than our shipped ladder, so
# adopting it in the engine is a repricing decision, not a data plumb.
#
# ⚠️  LLD-vs-OPERATOR-DECISION CONFLICT (hld KD-9 / lld §4.7 predate the
# 2026-08-06 operator block at the bottom of plan.md). KD-9 records engine
# adoption as *rejected*; operator decision **O2 REVERSES that** — market slot
# values ARE going into the trade engine, behind a #214-style user toggle, in a
# dedicated calibration wave (M6b). What survives unchanged is THIS wave's
# bound: M6 ships the display axis only, and M6b is the only thing allowed to
# widen it. Do not read "display-only" here as "the engine will never see
# this"; read it as "not yet, and not from this code path".
#
# Fail-soft, like every other consensus source here: any failure returns {} and
# the board simply renders without the slot-value axis.

_PICK_VALUES_TTL_SECONDS = 24 * 3600     # one polite fetch per day, like the DP CSV
_pick_values_lock = threading.Lock()
# {internal format key: {DP pick label: seed Elo}} — both formats parsed from
# the single fetch, so a superflex board costs no extra egress.
_pick_values_cache: dict[str, dict[str, float]] | None = None
_pick_values_fetched_at: float = 0.0

def pick_slot_label(season, round_no, slot) -> str:
    """The DP label for one draft slot: ``pick_slot_label(2026, 1, 1)`` →
    ``"2026 Pick 1.01"``. DP zero-pads the slot to two digits."""
    return f"{int(season)} Pick {int(round_no)}.{int(slot):02d}"


def _fetch_pick_values_csv(timeout: int = 10) -> str:
    """Fetch DP's combined values.csv (or the test-seam file).

    Hermetic-run rules mirror the values-players.csv seam, and are STRICTER
    than KTC's: `values.csv` is a second live egress, so under FTF_TEST_MODE
    the override is mandatory rather than "absent means off". `backend/server`
    refuses to start in test mode without it (T-M6-01), so reaching this
    function's network branch from a test run is impossible by construction.
    """
    _pick_file = os.environ.get("FTF_DP_PICK_VALUES_FILE")
    if os.environ.get("FTF_TEST_MODE") == "1" and not _pick_file:
        raise RuntimeError(
            "FTF_TEST_MODE=1 requires FTF_DP_PICK_VALUES_FILE "
            "(hermetic DynastyProcess pick values)")
    if _pick_file:
        return pathlib.Path(_pick_file).read_text()  # missing file = loud, by design
    req = urllib.request.Request(
        PICK_VALUES_URL, headers={"User-Agent": "FantasyTradeFinder/1.0"})
    # obs.api_events — DP's SECOND file (values.csv PICK rows), separate egress.
    from . import api_observability as _api_obs
    with _api_obs.observe_call("dynastyprocess", "values_picks") as _ob:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        _ob.ok(status=getattr(resp, "status", 200), response_bytes=len(raw))
    return raw


def _parse_pick_values(raw: str) -> dict[str, dict[str, float]]:
    """Parse `pos == "PICK"` rows into {format: {label: seed Elo}}.

    Rows with a non-positive or unparseable value in a format are omitted from
    THAT format only — a missing price must never render as a 0-value pick.
    """
    out: dict[str, dict[str, float]] = {fmt: {} for fmt in SCORING_FORMATS}
    reader = csv.DictReader(io.StringIO(raw))
    for row in reader:
        if (row.get("pos") or "").strip().upper() != "PICK":
            continue
        label = (row.get("player") or "").strip()
        if not label:
            continue
        for fmt, dp_suffix in DP_SCORING_PARAM.items():
            try:
                value = float((row.get(f"value_{dp_suffix}") or "0").strip())
            except ValueError:
                continue
            if value > 0:
                out[fmt][label] = round(seed_elo_for_value(value), 1)
    return out


def load_pick_slot_values(scoring: str = DEFAULT_SCORING) -> dict[str, float]:
    """``{"2026 Pick 1.01": 1816.5, "2027 Early 1st": 1718.6, …}`` in seed-Elo
    space, for one scoring format.

    Accepts either an internal format key (``"1qb_ppr"`` / ``"sf_tep"``) or
    DP's own column suffix (``"1qb"`` / ``"2qb"``). 24 h in-memory TTL, shared
    by both formats. **Never raises**: any fetch/parse failure returns ``{}``
    (and caches that emptiness for the TTL, so a broken endpoint is not
    re-hammered by every board render), which the Draft Room renders as "no
    slot-value axis" rather than an error.
    """
    global _pick_values_cache, _pick_values_fetched_at
    fmt = DP_PARAM_TO_FORMAT.get(scoring, scoring)
    with _pick_values_lock:
        now = time.time()
        if (_pick_values_cache is None
                or (now - _pick_values_fetched_at) >= _PICK_VALUES_TTL_SECONDS):
            try:
                _pick_values_cache = _parse_pick_values(_fetch_pick_values_csv())
                print(f"✅ Loaded {len(_pick_values_cache.get(DEFAULT_SCORING, {}))} "
                      f"DynastyProcess pick prices (display-only)")
            except Exception as e:
                print(f"⚠️  DynastyProcess pick values unavailable ({e}) — "
                      f"draft board renders without slot values")
                _pick_values_cache = {}
            _pick_values_fetched_at = now
        return dict(_pick_values_cache.get(fmt, {}))


def reset_pick_values_cache() -> None:
    """Drop the pick-price TTL cache. Tests only — no production caller."""
    global _pick_values_cache, _pick_values_fetched_at
    with _pick_values_lock:
        _pick_values_cache, _pick_values_fetched_at = None, 0.0


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
