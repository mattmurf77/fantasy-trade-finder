"""
rankings_import.py — paste-a-table rankings import (v1, flag ``ranks.import``).

Turns a user's pasted rankings (one player per line, in any of the tolerant
shapes below) into per-row match results against the universal player pool,
for POST /api/rankings/import-match. Pure functions — no Flask, no DB — so
the parser and matcher are unit-testable in isolation.

Accepted line shapes (per the approved mock, rank-method-consolidation-v2):
    "1. Josh Allen"          rank-dot-name
    "Josh Allen"             bare name
    "1\tJosh Allen\tQB\tBUF" TSV row (name in any column)
    "1,Josh Allen,QB,BUF"    CSV-ish row
    "12 Josh Allen QB BUF"   space-separated row (trailing POS/TEAM codes)
Header lines ("Rank,Player,Pos,Team") and numbers-only lines are ignored.

Match tiers (import-match response ``status`` per row):
    matched    exactly one pool player matches (exact-normalized, or a
               single high-confidence fuzzy hit: prefix / initial form)
    ambiguous  2+ candidates — client shows ≤3 chips + Skip
    unmatched  nothing in the pool resembles the name

Normalization strips case, punctuation, and generational suffixes
(Jr/Sr/II–V), so "Kenneth Walker" auto-matches "Kenneth Walker III" —
auto-accepted but surfaced in the review screen for audit (mock B3).

Structured rows (premium rankings import v1, [D-058]; addendum §3.2):
``match_rank_list`` also accepts ``rows`` — ``[{"name", "team"?, "pos"?}]``
in rank order — instead of raw pasted lines, for clients that parsed a CSV
and know which column is which. ``team``/``pos`` are HINTS ONLY: they narrow
a list of 2+ same-name candidates and can never reject a name-only match or
introduce one, so a stale team code degrades to today's behaviour instead of
losing the player. Only the name/team/pos columns are ever read — a premium
CSV's Value/Trend/PPG columns have no path into this module (the import
pipeline is order-only).
"""

from __future__ import annotations

import re
from typing import Optional

from .data_loader import normalise_name

# Generational suffixes stripped for matching ("Marvin Harrison Jr" ≡
# "Marvin Harrison"). Applied AFTER normalise_name (which already lowercases
# and removes punctuation).
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

# Tokens that mark a header row / non-name cell when they make up the WHOLE
# candidate name. Lowercase, punctuation-free (post-normalise_name).
_HEADER_WORDS = {
    "rank", "rk", "no", "num", "overall", "ovr", "row",
    "player", "players", "name", "names",
    "pos", "position", "team", "tm", "club",
    "age", "value", "values", "tier", "adp", "bye", "pts", "points",
}

# Positional codes that never belong to a name run.
_POS_CODES = {"qb", "rb", "wr", "te", "k", "def", "dst", "flex", "sflex"}


def normalize_player_name(name: str) -> str:
    """normalise_name + generational-suffix strip. The matcher's key space."""
    norm = normalise_name(name)
    tokens = norm.split()
    while len(tokens) > 1 and tokens[-1] in _SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _is_name_token(token: str) -> bool:
    """A token that can be part of a player-name run: contains a letter."""
    return bool(re.search(r"[A-Za-z]", token))


def _strip_code_tokens(tokens: list[str]) -> list[str]:
    """Drop trailing POS/TEAM codes from a space-separated name run.

    Heuristic for rows like "Josh Allen QB BUF": trailing tokens that are
    ALL-CAPS and ≤3 chars (team codes) or positional codes get dropped —
    but never below one remaining token, so a bare "QB" cell is left for
    the header/code check rather than emptied here.
    """
    out = list(tokens)
    while len(out) > 1:
        tail = out[-1]
        bare = re.sub(r"[^A-Za-z0-9]", "", tail)
        if bare.lower() in _POS_CODES:
            out.pop()
        elif bare.isupper() and bare.isalpha() and len(bare) <= 3:
            out.pop()
        else:
            break
    return out


def _run_from_cell(cell: str) -> Optional[str]:
    """First maximal alphabetic token run within one cell, code-stripped."""
    tokens = cell.split()
    run: list[str] = []
    for tok in tokens:
        if _is_name_token(tok):
            run.append(tok)
        elif run:
            break  # run ended (e.g. a trailing numeric value column)
    if not run:
        return None
    run = _strip_code_tokens(run)
    name = " ".join(run)
    norm = normalise_name(name)
    if not norm:
        return None
    # Whole run is header words and/or codes → not a name.
    if all(t in _HEADER_WORDS or t in _POS_CODES for t in norm.split()):
        return None
    return name


def extract_name(line: str) -> Optional[str]:
    """Extract the player name from one pasted line, or None to skip it.

    Splits on tab/comma/semicolon into cells and takes the first cell that
    yields an alphabetic token run which isn't purely header words or
    POS/TEAM codes. Lines with no such run (blank, numbers-only, header
    rows) return None.
    """
    if not line or not line.strip():
        return None
    cells = re.split(r"[\t,;]", line)
    for cell in cells:
        name = _run_from_cell(cell)
        if name:
            return name
    return None


def parse_rank_lines(lines: list[str]) -> list[tuple[str, str]]:
    """[(original_line, extracted_name)] for lines that parse to a name."""
    out = []
    for line in lines:
        name = extract_name(line)
        if name:
            out.append((line, name))
    return out


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _player_payload(p) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "team": getattr(p, "team", None),
        "position": getattr(p, "position", None),
    }


def _norm_code(value) -> Optional[str]:
    """Team/position hint → bare uppercase code ("bUf." → "BUF"), or None."""
    if not isinstance(value, str):
        return None
    code = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    return code or None


def _hint_narrow(candidates: list, team_hint: Optional[str],
                 pos_hint: Optional[str]) -> tuple[Optional[object], list]:
    """Disambiguate 2+ same-name candidates with team/position hints.

    Returns ``(winner|None, candidates_to_show)``. Hints only ever NARROW:
    if nothing satisfies them the original list comes back untouched, so a
    stale team code (post-trade CSV) or a missing column can never turn a
    name match into a miss. Tried strictest-first — both hints, then
    position alone, then team alone — because position is the stable half
    of a premium export and team is the half that goes stale.
    """
    tests = []
    if team_hint and pos_hint:
        tests.append(lambda p: (_norm_code(getattr(p, "position", None)) == pos_hint
                                and _norm_code(getattr(p, "team", None)) == team_hint))
    if pos_hint:
        tests.append(lambda p: _norm_code(getattr(p, "position", None)) == pos_hint)
    if team_hint:
        tests.append(lambda p: _norm_code(getattr(p, "team", None)) == team_hint)

    narrowed = candidates
    for test in tests:
        subset = [p for p in candidates if test(p)]
        if len(subset) == 1:
            return subset[0], subset
        if len(subset) > 1 and narrowed is candidates:
            narrowed = subset
    return None, narrowed


def _entries_from_rows(rows: list) -> list[tuple]:
    """[(input, name, team_hint, pos_hint)] from structured client rows.

    Rows without a usable ``name`` are dropped, mirroring how the paste path
    drops header/blank lines. Nothing but name/team/pos is read.
    """
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw = row.get("name")
        name = raw.strip() if isinstance(raw, str) else ""
        if not name or not normalise_name(name):
            continue
        out.append((name, name, _norm_code(row.get("team")),
                    _norm_code(row.get("pos"))))
    return out


def match_rank_list(lines: list[str], players: list, seed: Optional[dict] = None,
                    max_candidates: int = 3,
                    rows: Optional[list[dict]] = None) -> list[dict]:
    """Match pasted lines (or structured rows) against the universal pool.

    Returns one row per parsed line (headers/numbers-only lines are dropped):
        {input, name, status: matched|ambiguous|unmatched,
         player: {...}|None, candidates: [{...}] (≤max_candidates)}

    ``seed`` (pid → consensus Elo) orders candidate lists best-first so the
    chips the user sees lead with the likeliest player.

    ``rows`` (``[{"name", "team"?, "pos"?}]``, rank-ordered) replaces
    ``lines`` when given: the name is taken from the column rather than
    extracted, and team/pos disambiguate multi-candidate names only (see
    ``_hint_narrow``). ``rows=None`` is the paste path, unchanged.
    """
    ordered = sorted(
        players,
        key=lambda p: -(seed or {}).get(p.id, 0.0),
    )
    norm_index: dict[str, list] = {}
    normed: list[tuple] = []  # (player, norm, tokens)
    for p in ordered:
        norm = normalize_player_name(p.name)
        norm_index.setdefault(norm, []).append(p)
        normed.append((p, norm, norm.split()))

    if rows is None:
        entries = [(line, name, None, None)
                   for line, name in parse_rank_lines(lines)]
    else:
        entries = _entries_from_rows(rows)

    out = []
    for line, name, team_hint, pos_hint in entries:
        query = normalize_player_name(name)
        row = {"input": line.strip(), "name": name, "status": "unmatched",
               "player": None, "candidates": []}
        exact = norm_index.get(query, [])
        if len(exact) == 1:
            row["status"] = "matched"
            row["player"] = _player_payload(exact[0])
            out.append(row)
            continue
        if len(exact) > 1:
            candidates = exact
        else:
            # Fuzzy tier: prefix match either way, or "K. Walker" initial form.
            q_tokens = query.split()
            fuzzy = []
            for p, norm, p_tokens in normed:
                if norm.startswith(query + " ") or query.startswith(norm + " "):
                    fuzzy.append(p)
                    continue
                if (len(q_tokens) >= 2 and len(q_tokens[0]) == 1
                        and p_tokens
                        and p_tokens[0].startswith(q_tokens[0])
                        and p_tokens[1:] == q_tokens[1:]):
                    fuzzy.append(p)
            if len(fuzzy) == 1:
                row["status"] = "matched"
                row["player"] = _player_payload(fuzzy[0])
                out.append(row)
                continue
            candidates = fuzzy

        if candidates:
            winner, shown = _hint_narrow(candidates, team_hint, pos_hint)
            if winner is not None:
                row["status"] = "matched"
                row["player"] = _player_payload(winner)
            else:
                row["status"] = "ambiguous"
                row["candidates"] = [_player_payload(p)
                                     for p in shown[:max_candidates]]
        out.append(row)
    return out
