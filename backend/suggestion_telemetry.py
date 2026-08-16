"""
suggestion_telemetry.py — counterfactual logging + ghost holdout + executed-
trade tagging (flag `suggestion.telemetry`, default OFF).

Matchmaking research program item 1 ("logging first — unlocks everything,
retroactively impossible"): docs/research/matchmaking/round-2/
03-sparse-data-learning-and-evaluation.md §1.2 (the OPE logging contract),
§1.3 (ghost suggestions / the free Sleeper organic baseline), and the
round-1/02 signal ladder. Scope block:
docs/plans/matchmaking-engine/telemetry-scope.md.

This module is a LEAF: it imports feature_flags + database (+ trade_service's
live config dict), never server.py. server.py calls into it from exactly two
seams — the trade job's impression-logging block (ghost predicate, policy
version) and the session-init background daemon right after
sleeper_trades_service.sync_league_trades (executed-trade matcher).

Three responsibilities:

1. **Ghost predicate** — `is_ghost_suggestion(league_id, trade_hash)`:
   deterministic per (league, ISO week, card identity), ~1-in-N with
   N = model_config `ghost_holdout_one_in` (default 10, ≤0 disables).
   Deterministic-per-week on purpose: a deck regeneration inside the same
   week re-withholds the same card, so a ghost can never leak via refresh.

2. **Policy version** — `serving_policy_version()`: engine version + active
   ordering-layer flags + POLICY_REV, stamped on every telemetry-era
   impression so logged decks are attributable to a serving policy.

3. **Executed-trade tagging** — `match_league_trades(league_id)`: for every
   captured `sleeper_trades` row not yet linked, find the best-matching
   logged suggestion by the documented asset-set similarity rule and write
   one `suggestion_trade_links` row. `was_recommended` counts only NON-ghost
   (actually rendered) matches; the best ghost match is linked separately —
   ghost_impression_id hits are the incrementality read.

Similarity rule (D-scope-5, also in docs/glossary.md):
  same unordered manager pair, served_at ≤ traded_at ≤ served_at + lookback
  (model_config `suggestion_match_lookback_days`, default 14), asset sets
  compared direction-aligned after tokenization (players by id; owned picks
  → "pick:{season}:r{round}:{original_roster_id}"; generic-ladder picks
  relax to round-only pairing). exact = both sides fully pair off;
  partial = matched / max(|suggested|, |executed|) ≥ `suggestion_match_min_overlap`
  (default 0.5) AND ≥1 asset matched on each side. Best candidate:
  exact > overlap > most recent. Two-team trades only; multi-team executed
  trades link with match_type='none' and stay in the ratio denominator.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

from .database import (
    load_impressions_for_matching,
    load_unlinked_league_trades,
    save_suggestion_trade_links,
)
from .feature_flags import is_enabled
from .pick_values import parse_generic_pick_id

log = logging.getLogger(__name__)

# Bump on any change to suggestion scoring/ordering semantics that the flag
# map can't express (e.g. a reweighting inside trade_service). Part of the
# policy_version string stamped on every telemetry-era impression.
POLICY_REV = 1

SLEEPER_API_BASE = "https://api.sleeper.app/v1"

# Same rationale as trade_block_service / sleeper_trades_service —
# Cloudflare 1010-bans naked urllib UAs.
_HEADERS = {
    "accept": "application/json",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
}


# ---------------------------------------------------------------------------
# Config reads — via trade_service's live model_config dict (the _deck_cfg
# pattern): defaults inline so a missing key can never break the trade path.
# ---------------------------------------------------------------------------

def _cfg(key: str, default: float) -> float:
    try:
        from .trade_service import _cfg as _ts_cfg
        return float(_ts_cfg.get(key, default))
    except Exception:
        return float(default)


def ghost_one_in() -> int:
    """1-in-N ghost withholding rate. ≤0 disables ghosting entirely — the
    deploy-free rollback lever inside the flag."""
    return int(_cfg("ghost_holdout_one_in", 10))


def match_lookback_days() -> int:
    return int(_cfg("suggestion_match_lookback_days", 14))


def match_min_overlap() -> float:
    return float(_cfg("suggestion_match_min_overlap", 0.5))


# ---------------------------------------------------------------------------
# 1. Ghost predicate
# ---------------------------------------------------------------------------

def iso_league_week(now: datetime | None = None) -> str:
    """ISO week key, e.g. '2026-W33' — the ghost seed's rotation period."""
    dt = now or datetime.now(timezone.utc)
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def is_ghost_suggestion(
    league_id: str,
    trade_hash: str,
    *,
    week_key: str | None = None,
    one_in: int | None = None,
) -> bool:
    """Deterministic ghost-holdout predicate (D-scope-2).

    sha256("ghost|{league}|{iso_week}|{trade_hash}") % N == 0. Stable for
    the whole league-week (re-serves can't leak a withheld card), rotates
    weekly (no trade is permanently invisible). hashlib, not hash():
    Python salts str hashes per process.
    """
    n = int(one_in) if one_in is not None else ghost_one_in()
    if n <= 0:
        return False
    key = f"ghost|{league_id}|{week_key or iso_league_week()}|{trade_hash}"
    digest = hashlib.sha256(key.encode()).digest()
    return int.from_bytes(digest[:8], "big") % n == 0


# ---------------------------------------------------------------------------
# 2. Policy version
# ---------------------------------------------------------------------------

# Ordering-layer flags that change WHICH card is served where. Order fixed so
# the composed string is stable across processes.
_POLICY_FLAG_TAGS: tuple[tuple[str, str], ...] = (
    ("trade.thompson_deck",  "ts"),
    ("deck.thompson_v2",     "ts2"),
    ("trade.deck_diversity", "div"),
    ("deck.fatigue",         "fat"),
    ("deck.session_rerank",  "rr"),
    ("deck.taste_vectors",   "taste"),
    ("deck.value_model",     "vm"),
    ("deck.exploration",     "expl"),
    ("deck.first_session",   "fs"),
    ("suggestion.telemetry", "ghost"),
)


def serving_policy_version() -> str:
    """Compact serving-policy id, e.g. 'v3+ts.div.fat@r1' (D-scope-7)."""
    engine = ("v3" if is_enabled("trade_engine.v3")
              else "v2" if is_enabled("trade_engine.v2") else "v1")
    tags = [tag for key, tag in _POLICY_FLAG_TAGS if is_enabled(key)]
    return f"{engine}+{'.'.join(tags) or 'plain'}@r{POLICY_REV}"


# ---------------------------------------------------------------------------
# 3. Asset tokenization (shared by candidate-set logging and the matcher)
# ---------------------------------------------------------------------------

_GENERIC_ROUND_TOKEN = "gpick:r{rnd}"


def suggestion_asset_token(asset_id: str, league_id: str) -> str:
    """Normalize one suggested asset id to a comparison token.

    Players pass through as their Sleeper player_id. Owned-pick pseudo-assets
    ("{league_id}_{season}_{round}_{original_roster_id}", database.py
    pick_id format) become "pick:{season}:r{round}:{orig_roster}". Generic-
    ladder picks ("generic_pick_{round}_{tier}") become round-only tokens
    ("gpick:r{round}") that the pairing step relaxes against real picks.
    """
    pid = str(asset_id)
    g = parse_generic_pick_id(pid)
    if g is not None:
        return _GENERIC_ROUND_TOKEN.format(rnd=g[0])
    m = re.match(rf"^{re.escape(str(league_id))}_(\d{{4}})_(\d+)_(.+)$", pid)
    if m:
        return f"pick:{m.group(1)}:r{int(m.group(2))}:{m.group(3)}"
    return pid


def executed_pick_token(pick: dict) -> str | None:
    """Sleeper transaction draft_picks entry → comparison token.
    Entry shape: {season, round, roster_id (original owner), owner_id
    (receiving roster), previous_owner_id (sending roster)}."""
    try:
        season = str(pick.get("season"))
        rnd = int(pick.get("round"))
        orig = str(pick.get("roster_id"))
    except (TypeError, ValueError):
        return None
    if not season or not orig:
        return None
    return f"pick:{season}:r{rnd}:{orig}"


_PICK_TOKEN_RE = re.compile(r"^pick:\d{4}:r(\d+):")
_GPICK_TOKEN_RE = re.compile(r"^gpick:r(\d+)$")


def _pair_tokens(suggested: list[str], executed: list[str]) -> int:
    """Count how many suggested tokens pair off against executed tokens.

    Exact tokens pair first (multiset intersection); leftover generic-pick
    tokens then pair against leftover executed picks of the same round
    (round-only relaxation — a suggested 'Mid 1st' matches any executed
    round-1 pick that nothing else claimed).
    """
    remaining = list(executed)
    matched = 0
    generics: list[str] = []
    for tok in suggested:
        if _GPICK_TOKEN_RE.match(tok):
            generics.append(tok)
            continue
        if tok in remaining:
            remaining.remove(tok)
            matched += 1
    for tok in generics:
        rnd = _GPICK_TOKEN_RE.match(tok).group(1)
        hit = next((r for r in remaining
                    if (m := _PICK_TOKEN_RE.match(r)) and m.group(1) == rnd),
                   None)
        if hit is not None:
            remaining.remove(hit)
            matched += 1
    return matched


def score_match(
    sugg_give: list[str],
    sugg_recv: list[str],
    exec_out: list[str],
    exec_in: list[str],
    *,
    min_overlap: float | None = None,
) -> tuple[str, float]:
    """Direction-aligned similarity (D-scope-5).

    `sugg_give`/`exec_out` are assets leaving the suggestion's user;
    `sugg_recv`/`exec_in` are assets arriving. Returns (match_type, overlap)
    with match_type ∈ 'exact' | 'partial' | 'none'.
    """
    thresh = match_min_overlap() if min_overlap is None else float(min_overlap)
    m_give = _pair_tokens(sugg_give, exec_out)
    m_recv = _pair_tokens(sugg_recv, exec_in)
    n_sugg = len(sugg_give) + len(sugg_recv)
    n_exec = len(exec_out) + len(exec_in)
    if not n_sugg or not n_exec:
        return "none", 0.0
    overlap = (m_give + m_recv) / max(n_sugg, n_exec)
    if m_give + m_recv == n_sugg == n_exec:
        return "exact", 1.0
    if overlap >= thresh and m_give >= 1 and m_recv >= 1:
        return "partial", round(overlap, 4)
    return "none", round(overlap, 4)


# ---------------------------------------------------------------------------
# Executed-trade side derivation
# ---------------------------------------------------------------------------

def fetch_league_roster_map(
    league_id: str, *, _opener=None, timeout: int = 15
) -> dict[str, str]:
    """{roster_id(str): owner user_id(str)} from Sleeper's public rosters
    endpoint. `_opener` injects a fake urlopen in tests (house pattern)."""
    url = f"{SLEEPER_API_BASE}/league/{league_id}/rosters"
    request = urllib.request.Request(url)
    for k, v in _HEADERS.items():
        request.add_header(k, v)
    opener = _opener or urllib.request.urlopen
    with opener(request, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    out: dict[str, str] = {}
    for r in payload if isinstance(payload, list) else []:
        rid, owner = r.get("roster_id"), r.get("owner_id")
        if rid is not None and owner:
            out[str(rid)] = str(owner)
    return out


def executed_trade_sides(
    trade_row: dict, roster_map: dict[str, str]
) -> dict[str, list[str]] | None:
    """Per-user outgoing asset tokens for a captured 2-team sleeper_trades
    row: {user_id: [tokens the user SENT]}. None when the trade isn't a
    resolvable 2-team trade (multi-team, unknown roster owner, no assets).
    """
    try:
        roster_ids = json.loads(trade_row.get("roster_ids") or "[]")
        adds = json.loads(trade_row.get("adds") or "{}")
        picks = json.loads(trade_row.get("draft_picks") or "[]")
    except (TypeError, ValueError):
        return None
    if len(roster_ids) != 2:
        return None
    users = {str(rid): roster_map.get(str(rid)) for rid in roster_ids}
    if not all(users.values()):
        return None
    rid_a, rid_b = (str(r) for r in roster_ids)
    sent: dict[str, list[str]] = {users[rid_a]: [], users[rid_b]: []}
    # adds: {player_id: receiving roster_id} — the OTHER roster sent it.
    for pid, recv_rid in (adds or {}).items():
        recv_rid = str(recv_rid)
        if recv_rid not in (rid_a, rid_b):
            return None
        sender = rid_b if recv_rid == rid_a else rid_a
        sent[users[sender]].append(str(pid))
    # picks move previous_owner_id → owner_id.
    for pk in picks or []:
        tok = executed_pick_token(pk)
        prev = str(pk.get("previous_owner_id"))
        if tok is None or prev not in (rid_a, rid_b):
            continue
        sent[users[prev]].append(tok)
    if not any(sent.values()):
        return None
    return sent


# ---------------------------------------------------------------------------
# The matcher
# ---------------------------------------------------------------------------

def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def match_league_trades(
    league_id: str,
    *,
    roster_map: dict[str, str] | None = None,
    _opener=None,
) -> int:
    """Link every not-yet-linked captured trade in this league to its best-
    matching logged suggestion. Idempotent (skips linked transaction_ids);
    returns the number of link rows written. Best-effort by contract —
    callers wrap in try/except like every other background sync step.
    """
    trades = load_unlinked_league_trades(league_id)
    if not trades:
        return 0
    if roster_map is None:
        try:
            roster_map = fetch_league_roster_map(league_id, _opener=_opener)
        except Exception as e:
            log.warning("suggestion telemetry: roster fetch failed for %s: %s",
                        league_id, e)
            return 0  # leave unlinked; next sync retries

    lookback = timedelta(days=match_lookback_days())
    now_iso = datetime.now(timezone.utc).isoformat()
    links: list[dict] = []
    for tr in trades:
        traded_at = _parse_iso(tr.get("traded_at")) or _parse_iso(tr.get("synced_at"))
        link = {
            "transaction_id":      tr["transaction_id"],
            "league_id":           league_id,
            "was_recommended":     0,
            "matched_impression_id": None,
            "match_type":          None,
            "overlap_score":       None,
            "ghost_impression_id": None,
            "ghost_match_type":    None,
            "ghost_overlap_score": None,
            "traded_at":           tr.get("traded_at"),
            "computed_at":         now_iso,
        }
        sides = executed_trade_sides(tr, roster_map)
        if sides is not None and traded_at is not None:
            since = (traded_at - lookback).isoformat()
            until = traded_at.isoformat()
            imps = load_impressions_for_matching(league_id, since, until)
            # Best candidate per pool (D-scope-5): exact beats partial, then
            # highest overlap, then most recent served_at. ISO timestamps
            # sort lexicographically, so max() on the key tuple works.
            best: dict[bool, tuple[tuple, str, float, dict]] = {}
            for imp in imps:
                cand = _score_impression(imp, sides)
                if cand is None:
                    continue
                mtype, overlap = cand
                is_ghost = bool(imp.get("is_ghost"))
                key = (1 if mtype == "exact" else 0, overlap,
                       imp.get("served_at") or "")
                cur = best.get(is_ghost)
                if cur is None or key > cur[0]:
                    best[is_ghost] = (key, mtype, overlap, imp)
            if False in best:
                _, mtype, overlap, imp = best[False]
                link.update({
                    "was_recommended":       1,
                    "matched_impression_id": imp["impression_id"],
                    "match_type":            mtype,
                    "overlap_score":         overlap,
                })
            if True in best:
                _, mtype, overlap, imp = best[True]
                link.update({
                    "ghost_impression_id": imp["impression_id"],
                    "ghost_match_type":    mtype,
                    "ghost_overlap_score": overlap,
                })
        links.append(link)
    return save_suggestion_trade_links(links)


def _score_impression(
    imp: dict, sides: dict[str, list[str]]
) -> tuple[str, float] | None:
    """Score one logged impression against an executed trade's per-user
    outgoing token sets. None unless the manager pair matches and the
    similarity rule yields exact/partial."""
    user = imp.get("user_id")
    partner = imp.get("partner_user_id")
    if not user or not partner:
        return None
    if {str(user), str(partner)} != {str(u) for u in sides}:
        return None
    assets = imp.get("assets") or {}
    give = list(assets.get("give") or [])
    recv = list(assets.get("receive") or [])
    league_id = imp.get("league_id") or ""
    give_t = [suggestion_asset_token(a, league_id) for a in give]
    recv_t = [suggestion_asset_token(a, league_id) for a in recv]
    exec_out = sides.get(str(user)) or []
    exec_in = sides.get(str(partner)) or []
    mtype, overlap = score_match(give_t, recv_t, exec_out, exec_in)
    if mtype == "none":
        return None
    return mtype, overlap
