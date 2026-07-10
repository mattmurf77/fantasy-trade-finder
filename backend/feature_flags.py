"""
feature_flags.py — single source of truth for feature flags.

Every feature shipped in the 2026-04-19 parallel sprint is gated behind a
flag defined here. Defaults are all False so new code ships dark; a
deployer flips a key in config/features.json (or via the FTF_FLAGS env
var) to turn the feature on in production.

Usage
-----
    from .feature_flags import FLAGS, is_enabled

    if FLAGS.swipe_community_compare:
        ...

    if is_enabled("swipe.community_compare"):
        ...

Both work; the attribute form is handy inside routes, the string form is
handy when the flag key comes from request data.

Flag naming
-----------
Dotted group.feature keys inside JSON / API; snake_case_group_feature
inside the Flags dataclass. The `_key_to_attr` helper converts between
them automatically — never hand-maintain a second mapping.

The `GET /api/feature-flags` endpoint serves the dotted map to the
frontend so `window.FTF_FLAGS["swipe.community_compare"]` just works.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Flag declarations
# ---------------------------------------------------------------------------

# Every key here MUST be listed in `DEFAULT_FLAGS` below with a default.
# The agent prompts reference these literal strings; do not rename lightly.
FLAG_KEYS: tuple[str, ...] = (
    # Swipe UX (Agent A1)
    "swipe.community_compare",
    "swipe.qc_compliments",
    "swipe.gesture_audit",
    # Positional tiers (Agent A2)
    "tiers.community_diff",
    "tiers.stability_indicator",
    "tiers.swipe_secondary_actions",
    # Trade UI (Agent A3)
    "trades.queue_2k",
    "trades.new_partners_alerts",
    # League social (Agent A4)
    "league.unlock_badges_per_member",
    "league.activity_feed",
    "league.unlock_badges_nav_pill",
    # Invite virality (Agent A5)
    "invite.k_factor_dashboard",
    # Mobile polish (Agent A6)
    "mobile.sticky_cta",
    "mobile.thumb_zone_tables",
    "mobile.rankings_card_view",
    # New surfaces (Agent A7)
    "profiles.public_pages",
    "landing.smart_start_cta",
    "landing.try_before_sync",
    # Player profiles (#17)
    "players.profile_pages",
    # Trade math (Agent A8)
    "trade_math.qb_tax",
    "trade_math.star_tax",
    "trade_math.roster_clogger",
    "trade_math.human_explanations",
    # Trade engine v2 — Tier 1 scorer rebuild (docs/plans/trade-engine-tier1-fixes.md)
    "trade_engine.v2",
    # Trade engine Tier 2 (docs/plans/trade-engine-tier2-models.md)
    "trade.marginal_value",   # 2.1 over-replacement valuation (trade_service.py)
    "trade.outlook_blend",    # 2.2 now/future valuation blend (trade_service.py)
    "trade.likes_you",        # 2.3a likes-you queue (server.py)
    "trade.fuzzy_match",      # 2.3b fuzzy mirror matching (database.py)
    "trade.thompson_deck",    # A5 Thompson-sampled deck ordering (server.py)
    "trade.deck_diversity",   # A6 league-wide deck diversification (server.py)
    # Trade engine Tier 3 (docs/plans/trade-engine-tier3-rebuild.md)
    "trade_engine.v3",        # exact per-pair package construction + sweeteners
    "trade.three_team",       # 3-team cycle generation (no client surface yet)
    # FB-47 finder targeting (docs/plans/trade-finder-targeting.md)
    "trade.finder_targeting", # pinned-receive + counterparty positional fit
    # FB-96 — automatic positional-need fit (feedback #96; kin of FB-47)
    "trade.need_fit",         # boost swaps that cross-fill positional needs
    # Backlog #1 — opponent outlook inference (docs/plans/competitor-top20/01-*)
    "trade.outlook_infer",    # price opponents with their inferred/declared α
    # Backlog #2 — asset preference lists (docs/plans/competitor-top20/02-*)
    "trade.preference_lists", # untouchables (give-side filter) + targets (reward)
    # Backlog #8 — seed unset-league outlook from the user's own roster (01's classifier)
    "trade.outlook_seed",
    # Backlog #10 — crown-asset package premium (docs/plans/competitor-top20/10-*)
    "trade.crown_asset",
    # "Send in Sleeper" — undocumented Sleeper write API (FLAGGED-BETA / ToS-adverse)
    "trade.send_in_sleeper",  # docs/plans/sleeper-write-capture-runbook.md
)

DEFAULT_FLAGS: dict[str, bool] = {key: False for key in FLAG_KEYS}


def _key_to_attr(key: str) -> str:
    """Convert a dotted flag key to a Python attribute name.

    >>> _key_to_attr("swipe.community_compare")
    'swipe_community_compare'
    >>> _key_to_attr("trade_math.qb_tax")
    'trade_math_qb_tax'
    """
    return key.replace(".", "_").replace("-", "_")


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_ROOT / "config" / "features.json"

_flags_lock = threading.Lock()
_flags_cache: dict[str, bool] | None = None


def _load_from_json(path: Path) -> dict[str, bool]:
    """Load overrides from a JSON file. Returns empty dict on any failure."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
    except Exception as e:
        print(f"[feature_flags] could not parse {path}: {e}")
        return {}
    if not isinstance(raw, dict):
        return {}
    # Only keep keys we know about — typos shouldn't silently create flags.
    clean: dict[str, bool] = {}
    for k, v in raw.items():
        if k in DEFAULT_FLAGS:
            clean[k] = bool(v)
        else:
            print(f"[feature_flags] ignoring unknown key {k!r} in {path.name}")
    return clean


def _load_from_env() -> dict[str, bool]:
    """Load overrides from the FTF_FLAGS env var — JSON-encoded dict."""
    raw = os.environ.get("FTF_FLAGS", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception as e:
        print(f"[feature_flags] could not parse FTF_FLAGS env var: {e}")
        return {}
    if not isinstance(parsed, dict):
        return {}
    clean: dict[str, bool] = {}
    for k, v in parsed.items():
        if k in DEFAULT_FLAGS:
            clean[k] = bool(v)
    return clean


def _compute_flags() -> dict[str, bool]:
    """Merge defaults + json file + env var into the effective flag map.

    Precedence (later wins): defaults → config/features.json → FTF_FLAGS env
    """
    merged = dict(DEFAULT_FLAGS)
    merged.update(_load_from_json(_CONFIG_PATH))
    merged.update(_load_from_env())
    return merged


def flags_dict() -> dict[str, bool]:
    """Return the current effective flag map (dotted keys → bool).

    Cached — call `reload()` to force a re-read after editing the JSON file.
    """
    global _flags_cache
    if _flags_cache is None:
        with _flags_lock:
            if _flags_cache is None:
                _flags_cache = _compute_flags()
    return dict(_flags_cache)


def reload() -> dict[str, bool]:
    """Force re-read of config/env. Useful for runtime config swaps."""
    global _flags_cache
    with _flags_lock:
        _flags_cache = _compute_flags()
    return dict(_flags_cache)


def is_enabled(key: str) -> bool:
    """Return True if `key` is enabled. Unknown keys return False."""
    return bool(flags_dict().get(key, False))


# ---------------------------------------------------------------------------
# Dataclass access — `FLAGS.swipe_community_compare` and friends
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _FlagsSnapshot:
    """Immutable snapshot of the flag map. Built lazily via `FLAGS`."""
    # Populated dynamically below via setattr; declared here for type hints.

    def __getattr__(self, name: str) -> bool:
        # Fall back for flags declared only in DEFAULT_FLAGS — useful so
        # agents don't have to also edit this class when adding new flags.
        # Convert attr → dotted key via reverse of _key_to_attr: any
        # single underscore preserved, the first underscore (at a group
        # boundary) becomes a dot.
        for key in DEFAULT_FLAGS:
            if _key_to_attr(key) == name:
                return is_enabled(key)
        raise AttributeError(f"No such feature flag: {name!r}")


class _FlagsProxy:
    """Live proxy — every attribute access hits the current flag map.

    Avoids the 'snapshot stale after reload()' gotcha that would bite
    agents stashing `FLAGS.whatever` at module-import time.
    """
    def __getattr__(self, name: str) -> bool:
        for key in DEFAULT_FLAGS:
            if _key_to_attr(key) == name:
                return is_enabled(key)
        raise AttributeError(f"No such feature flag: {name!r}")

    def __getitem__(self, key: str) -> bool:
        return is_enabled(key)

    def __repr__(self) -> str:
        enabled = [k for k, v in flags_dict().items() if v]
        return f"<FLAGS enabled={enabled!r}>"


FLAGS = _FlagsProxy()
