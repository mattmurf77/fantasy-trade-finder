"""
Smart Matchup Generator — Fantasy Trade Finder
================================================
Uses Claude to intelligently select the most informative player matchup
for the dynasty ranking swipe interface.

How it works:
  1. Compute live Elo ratings from the user's swipe history
  2. Generate ~10 candidate pairs (nearby Elo, not yet compared)
  3. Ask Claude to pick the most dynasty-informative pair
  4. Return the chosen players + Claude's reasoning

Usage:
  from backend.smart_matchup_generator import SmartMatchupGenerator, Player, SwipeDecision

  generator = SmartMatchupGenerator(api_key="your-key")
  p1, p2, reason = generator.generate_next_matchup(players, swipe_history)
"""

import json
import anthropic
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class Player:
    id: str
    name: str
    position: str      # "QB", "RB", "WR", "TE"
    team: str
    age: int
    years_experience: int = 0


@dataclass
class SwipeDecision:
    """A single head-to-head result: winner preferred over loser."""
    winner_id: str
    loser_id: str


# ---------------------------------------------------------------------------
# Core Generator
# ---------------------------------------------------------------------------

class SmartMatchupGenerator:
    """
    Generates the most informative next head-to-head player matchup
    using Elo ratings + Claude dynasty reasoning.
    """

    MODEL = "claude-sonnet-4-6"
    MAX_CANDIDATES = 10

    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_next_matchup(
        self,
        players: list[Player],
        swipe_history: list[SwipeDecision],
        position_filter: Optional[str] = None,
    ) -> tuple[Player, Player, str]:
        """
        Return the most informative next matchup.

        Args:
            players:         Full pool of players to rank.
            swipe_history:   All swipe decisions recorded so far.
            position_filter: Optionally restrict to one position group
                             ("QB", "RB", "WR", "TE").

        Returns:
            (player_1, player_2, claude_reasoning)
        """
        filtered = [
            p for p in players
            if position_filter is None or p.position == position_filter
        ]

        if len(filtered) < 2:
            raise ValueError(
                f"Need at least 2 players (got {len(filtered)}) "
                f"for position_filter={position_filter!r}"
            )

        stats       = self._build_comparison_stats(filtered, swipe_history)
        elo_ratings = self._compute_elo(filtered, swipe_history)
        candidates  = self._get_candidate_pairs(filtered, stats, elo_ratings)

        # Cold-start fallback: no history yet, just return two players
        if not candidates:
            return filtered[0], filtered[1], "No swipe history yet — starting fresh."

        return self._ask_claude(candidates, elo_ratings, stats, swipe_history, position_filter)

    # ------------------------------------------------------------------
    # Elo Engine
    # ------------------------------------------------------------------

    def _compute_elo(
        self,
        players: list[Player],
        history: list[SwipeDecision],
        k: float = 32,
        initial: float = 1500.0,
    ) -> dict[str, float]:
        """Compute Elo ratings from pairwise swipe history."""
        ratings = {p.id: initial for p in players}
        valid_ids = set(ratings)

        for decision in history:
            w, l = decision.winner_id, decision.loser_id
            if w not in valid_ids or l not in valid_ids:
                continue
            ra, rb = ratings[w], ratings[l]
            ea = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
            ratings[w] += k * (1.0 - ea)
            ratings[l] += k * (0.0 - (1.0 - ea))

        return ratings

    # ------------------------------------------------------------------
    # Comparison Stats
    # ------------------------------------------------------------------

    def _build_comparison_stats(
        self,
        players: list[Player],
        history: list[SwipeDecision],
    ) -> dict[str, dict]:
        """Return wins, losses, and the set of already-compared opponents per player."""
        valid_ids = {p.id for p in players}
        stats: dict[str, dict] = {
            p.id: {"wins": 0, "losses": 0, "compared_against": set()}
            for p in players
        }

        for d in history:
            if d.winner_id in valid_ids and d.loser_id in valid_ids:
                stats[d.winner_id]["wins"]                     += 1
                stats[d.loser_id]["losses"]                    += 1
                stats[d.winner_id]["compared_against"].add(d.loser_id)
                stats[d.loser_id]["compared_against"].add(d.winner_id)

        return stats

    # ------------------------------------------------------------------
    # Candidate Pair Selection
    # ------------------------------------------------------------------

    def _get_candidate_pairs(
        self,
        players: list[Player],
        stats: dict,
        elo_ratings: dict,
    ) -> list[tuple[Player, Player]]:
        """
        Build up to MAX_CANDIDATES uncompared pairs, prioritising
        players adjacent in Elo (most uncertainty to resolve).
        """
        sorted_players = sorted(
            players,
            key=lambda p: elo_ratings.get(p.id, 1500),
            reverse=True,
        )

        candidates: list[tuple[Player, Player]] = []
        seen: set[tuple[str, str]] = set()

        # Pass 1: adjacent ±3 in Elo order (close-call matchups)
        for i, p1 in enumerate(sorted_players):
            window = sorted_players[max(0, i - 3) : i] + sorted_players[i + 1 : i + 4]
            for p2 in window:
                key = tuple(sorted([p1.id, p2.id]))
                if key not in seen and p2.id not in stats[p1.id]["compared_against"]:
                    candidates.append((p1, p2))
                    seen.add(key)
                if len(candidates) >= self.MAX_CANDIDATES:
                    return candidates

        # Pass 2: any remaining uncompared pairs
        if len(candidates) < 3:
            for i, p1 in enumerate(sorted_players):
                for p2 in sorted_players[i + 1 :]:
                    key = tuple(sorted([p1.id, p2.id]))
                    if key not in seen and p2.id not in stats[p1.id]["compared_against"]:
                        candidates.append((p1, p2))
                        seen.add(key)
                    if len(candidates) >= self.MAX_CANDIDATES:
                        return candidates

        return candidates

    # ------------------------------------------------------------------
    # Claude Reasoning
    # ------------------------------------------------------------------

    def _ask_claude(
        self,
        candidates: list[tuple[Player, Player]],
        elo_ratings: dict,
        stats: dict,
        swipe_history: list[SwipeDecision],
        position_filter: Optional[str],
    ) -> tuple[Player, Player, str]:
        """Ask Claude to pick the most dynasty-informative pair."""

        lines = []
        for i, (p1, p2) in enumerate(candidates, start=1):
            e1 = elo_ratings.get(p1.id, 1500)
            e2 = elo_ratings.get(p2.id, 1500)
            s1 = stats[p1.id]
            s2 = stats[p2.id]
            gap = abs(e1 - e2)
            lines.append(
                f"{i}. {p1.name} ({p1.position}, {p1.team}, age {p1.age}, "
                f"{p1.years_experience} yr exp) "
                f"[Elo {e1:.0f} | W{s1['wins']}/L{s1['losses']}]  vs  "
                f"{p2.name} ({p2.position}, {p2.team}, age {p2.age}, "
                f"{p2.years_experience} yr exp) "
                f"[Elo {e2:.0f} | W{s2['wins']}/L{s2['losses']}]  "
                f"(Elo gap: {gap:.0f})"
            )

        prompt = f"""You are a dynasty fantasy football expert helping a user build their personal player rankings through head-to-head comparisons.

The user is ranking players using a swipe interface (like Tinder). Your job is to choose the MOST INFORMATIVE next matchup from the candidates below.

CONTEXT
- Swipes so far: {len(swipe_history)}
- Position group: {position_filter or "All positions"}
- Elo ratings estimate current ranking signal (higher = ranked higher by this user so far)
- Elo gap = how close the two players currently are in the ranking

CANDIDATE MATCHUPS
{chr(10).join(lines)}

PICK THE BEST MATCHUP using this priority:
1. Close Elo gap → outcome is genuinely uncertain, so the swipe carries more information
2. Neither player has many comparisons yet → fresh signal, not redundant
3. Dynasty relevance → matchups at a position inflection point (e.g. aging vet vs ascending youngster) tell us the most about long-term roster strategy
4. Avoid matchups where the outcome is already strongly implied by transitive results

Respond with JSON only — no markdown, no explanation outside the JSON:
{{
  "selected_index": <integer, 1-based>,
  "reasoning": "<1–2 sentences explaining why this matchup is most informative for dynasty rankings>"
}}"""

        message = self.client.messages.create(
            model=self.MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()

        # Strip markdown code fences if present
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.split("```")[0]

        result = json.loads(raw.strip())
        idx = int(result["selected_index"]) - 1  # to 0-based
        idx = max(0, min(idx, len(candidates) - 1))  # clamp

        p1, p2 = candidates[idx]
        return p1, p2, result["reasoning"]

    # ------------------------------------------------------------------
    # Trio Generation (3-player ranking)
    # ------------------------------------------------------------------

    def generate_next_trio(
        self,
        players: list[Player],
        swipe_history: list[SwipeDecision],
        position_filter: Optional[str] = None,
        skipped_player_ids: Optional[set] = None,
    ) -> object:
        """
        Generate the most informative next 3-player ranking group.
        Returns a MatchupTrio-compatible object (duck-typed).

        skipped_player_ids: optional set of player IDs to exclude (Agent 1 —
        "I don't know this player" persistent skip). Filtered out before
        candidate generation so they never appear in future trios.
        """
        from dataclasses import dataclass

        @dataclass
        class Trio:
            player_a: Player
            player_b: Player
            player_c: Player
            reasoning: str

        _skipped: set = skipped_player_ids or set()
        filtered = [
            p for p in players
            if (position_filter is None or p.position == position_filter)
            and p.id not in _skipped
        ]

        if len(filtered) < 3:
            raise ValueError("Need at least 3 players for a trio")

        stats       = self._build_comparison_stats(filtered, swipe_history)
        elo_ratings = self._compute_elo(filtered, swipe_history)

        # Build candidate trios: adjacent players in Elo order
        sorted_p   = sorted(filtered, key=lambda p: elo_ratings.get(p.id, 1500), reverse=True)
        candidates: list[tuple[Player, Player, Player]] = []
        seen: set[tuple] = set()

        for i in range(len(sorted_p) - 2):
            for j in range(i + 1, min(i + 4, len(sorted_p) - 1)):
                for k in range(j + 1, min(j + 4, len(sorted_p))):
                    key = tuple(sorted([sorted_p[i].id, sorted_p[j].id, sorted_p[k].id]))
                    if key not in seen:
                        candidates.append((sorted_p[i], sorted_p[j], sorted_p[k]))
                        seen.add(key)
                    if len(candidates) >= self.MAX_CANDIDATES:
                        break
                if len(candidates) >= self.MAX_CANDIDATES:
                    break
            if len(candidates) >= self.MAX_CANDIDATES:
                break

        if not candidates:
            return Trio(sorted_p[0], sorted_p[1], sorted_p[2], "First trio — no history yet.")

        lines = []
        for i, (p1, p2, p3) in enumerate(candidates, start=1):
            spread = abs(elo_ratings.get(p1.id, 1500) - elo_ratings.get(p3.id, 1500))
            existing = sum([
                p2.id in stats[p1.id]["compared_against"],
                p3.id in stats[p1.id]["compared_against"],
                p3.id in stats[p2.id]["compared_against"],
            ])
            lines.append(
                f"{i}. {p1.name} ({p1.position}, {p1.team}, age {p1.age}) "
                f"[Elo {elo_ratings.get(p1.id,1500):.0f}]  |  "
                f"{p2.name} ({p2.position}, {p2.team}, age {p2.age}) "
                f"[Elo {elo_ratings.get(p2.id,1500):.0f}]  |  "
                f"{p3.name} ({p3.position}, {p3.team}, age {p3.age}) "
                f"[Elo {elo_ratings.get(p3.id,1500):.0f}]  "
                f"(spread {spread:.0f}, {existing}/3 pairs already compared)"
            )

        prompt = f"""You are a dynasty fantasy football expert. A user is ranking players by seeing 3 at a time and ordering them 1st/2nd/3rd.

Pick the MOST INFORMATIVE trio from the candidates below — the group whose full ranking will resolve the most uncertainty in the dynasty rankings.

CONTEXT
- Swipes so far: {len(swipe_history)}
- Position: {position_filter or 'All positions'}

CANDIDATE TRIOS
{chr(10).join(lines)}

Prioritise:
1. Tight Elo spread (all 3 players genuinely close in value)
2. Few existing comparisons between them (fresh signal)
3. Dynasty-relevant tier boundaries (e.g. elite vs solid starters)

Respond with JSON only:
{{
  "selected_index": <1-based integer>,
  "reasoning": "<1-2 sentences why this trio is most informative>"
}}"""

        message = self.client.messages.create(
            model=self.MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.split("```")[0]

        result = __import__("json").loads(raw.strip())
        idx    = max(0, min(int(result["selected_index"]) - 1, len(candidates) - 1))
        p1, p2, p3 = candidates[idx]
        return Trio(player_a=p1, player_b=p2, player_c=p3, reasoning=result["reasoning"])
