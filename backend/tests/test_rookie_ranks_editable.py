"""Editable consolidated rookie ranks + the seasonal Draft tab flag.

Two operator-directed changes from live TestFlight testing of build 82.

**1. `RookieRanksScreen` became editable (drag to reorder).** It shipped
read-only on the argument that "a seventh drag board would just be Overall
ranks under scope"; the Draft Room's "Rank the rookies" row lands there, so
the label promised something the screen did not do. The whole safety story is
one sentence: **the reorder lane only.** Writes go through
`POST /api/rankings/reorder` -> `RankingService.apply_reorder`, and NOTHING on
that screen may reach `save_tiers_position` / `apply_tiers` / the merged-band
`apply_tiers_subset` path — the one construction in this codebase that can
destroy a user's board. Pinned here the way `test_draft_extensions_w1.py` pins
W1's anchor lane:

  (a) behaviour — `apply_reorder` really is subset-safe (only the posted pids
      get overrides, their Elo multiset is invariant, nobody else moves), and
      a scoped subset reorder lands byte-identically to the equivalent
      unscoped full-board reorder of that subsequence;
  (b) source — the screen names no tiers-save symbol and does name
      `reorderRankings`.

**2. The Draft tab became a simple flag, `draft.tab`.** Operator, verbatim:
"On the Draft tab - it should literally just be set to seasonal. So a flag we
turn on and off to display the tab. Right now it should be on for all." The
per-league qualification predicate, its AsyncStorage snapshot and the
multi-league chooser are deleted; `DraftRoom` stays reachable through the root
stack and the canonical deep link either way.
"""
import json
import re
from pathlib import Path

import pytest

import backend.feature_flags as feature_flags
from backend.ranking_service import Player, RankingService

REPO = Path(__file__).resolve().parents[2]

SCREEN = REPO / "mobile/src/screens/RookieRanksScreen.tsx"
TABNAV = REPO / "mobile/src/navigation/TabNav.tsx"
APP_TSX = REPO / "mobile/App.tsx"

# Every symbol that leads to the merged-band board rewrite. If this screen
# ever names one of these, the change has left its lane.
FORBIDDEN_CLIENT = (
    "/api/tiers/save",
    "tiers/save",
    "saveTiers",
    "resetTiers",
    "save_tiers_position",
    "apply_tiers",
)

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _code_only(src: str) -> str:
    """Strip // and /* */ comments.

    Mirrors `test_draft_extensions_w1._code_only`: these files EXPLAIN the
    prohibition in prose, and a rule that fires on its own explanation would
    only teach builders to delete the explanation.
    """
    src = _BLOCK_COMMENT.sub("", src)
    return "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("//")
    )


# ---------------------------------------------------------------------------
# (a) apply_reorder is subset-safe — the claim the scoped board rests on
# ---------------------------------------------------------------------------

# Distinct seeds throughout: `apply_reorder` breaks exact ties with a
# descending epsilon, and a tie-free fixture keeps the assertions about the
# permutation itself rather than about the tie-breaker.
_POOL = [
    ("vet_qb",  "QB", 1900.0),
    ("rk_qb",   "QB", 1750.0),
    ("vet_rb",  "RB", 1800.0),
    ("rk_rb",   "RB", 1600.0),
    ("vet_wr",  "WR", 1700.0),
    ("rk_wr",   "WR", 1550.0),
    ("rk_te",   "TE", 1500.0),
]
ROOKIES = ("rk_qb", "rk_rb", "rk_wr", "rk_te")


def _service() -> RankingService:
    players = [
        Player(id=pid, name=pid.upper(), position=pos, team="AAA", age=23)
        for pid, pos, _ in _POOL
    ]
    return RankingService(
        players=players,
        seed_ratings={pid: elo for pid, _, elo in _POOL},
    )


def _elos(service: RankingService) -> dict[str, float]:
    return {rp.player.id: rp.elo for rp in service.get_rankings(position=None).rankings}


def test_a_scoped_reorder_moves_nobody_outside_the_posted_subset():
    """The rookie board posts a SUBSET of the full board. Every player the
    user did not touch must come out with the Elo they went in with."""
    svc = _service()
    before = _elos(svc)

    # Drag the rookie TE to the top of the rookie board.
    svc.apply_reorder(position=None, ordered_ids=["rk_te", "rk_qb", "rk_rb", "rk_wr"])
    after = _elos(svc)

    for pid in ("vet_qb", "vet_rb", "vet_wr"):
        assert after[pid] == pytest.approx(before[pid]), f"{pid} moved on a rookie-only reorder"
    # Overrides are written for exactly the posted pids — never for a vet.
    assert set(svc._elo_overrides) == set(ROOKIES)


def test_a_scoped_reorder_permutes_the_subsets_own_elo_multiset():
    """Order changes, magnitudes do not: the reordered players receive the
    sorted multiset of their OWN current Elos. This is what keeps tier
    occupancy invariant under a reorder (the FB #60/#69 "44 elite QBs" fix)."""
    svc = _service()
    before = _elos(svc)
    rookie_elos_before = sorted((before[p] for p in ROOKIES), reverse=True)

    svc.apply_reorder(position=None, ordered_ids=["rk_te", "rk_wr", "rk_rb", "rk_qb"])
    after = _elos(svc)

    assert sorted((after[p] for p in ROOKIES), reverse=True) == pytest.approx(
        rookie_elos_before
    )
    # ...and dealt out in exactly the posted order.
    assert after["rk_te"] > after["rk_wr"] > after["rk_rb"] > after["rk_qb"]


def test_a_scoped_reorder_equals_the_unscoped_reorder_of_that_subsequence():
    """THE load-bearing claim. Reordering the rookies among themselves on the
    scoped board must land byte-identically to running the SAME reorder on the
    full board with only the rookie slots permuted — otherwise the scoped
    surface would be a second, divergent write path."""
    new_rookie_order = ["rk_te", "rk_qb", "rk_wr", "rk_rb"]

    scoped = _service()
    scoped.apply_reorder(position=None, ordered_ids=new_rookie_order)

    # The equivalent unscoped edit: the full board in Elo order, with the
    # rookie-occupied slots refilled in the new rookie order.
    unscoped = _service()
    full_order = [pid for pid, _ in sorted(
        _elos(unscoped).items(), key=lambda kv: kv[1], reverse=True)]
    it = iter(new_rookie_order)
    full_order = [next(it) if pid in ROOKIES else pid for pid in full_order]
    unscoped.apply_reorder(position=None, ordered_ids=full_order)

    a, b = _elos(scoped), _elos(unscoped)
    assert a.keys() == b.keys()
    for pid in a:
        assert a[pid] == pytest.approx(b[pid]), f"{pid} diverged between the two lanes"


def test_a_position_filtered_scoped_reorder_leaves_that_positions_vets_alone():
    """Under a position filter the board posts `position: 'QB'` plus the
    rookie QBs only. The pool is every QB, so the vet QB is IN the pool and
    must still not move — subset-safety, not pool-safety."""
    # Only one rookie QB in the base fixture, and <2 valid ids is a no-op, so
    # add a second rookie QB for a meaningful permutation.
    svc = _service()
    svc._players["rk_qb2"] = Player(
        id="rk_qb2", name="RK QB2", position="QB", team="BBB", age=22)
    svc._seed["rk_qb2"] = 1650.0
    svc._version += 1
    before = _elos(svc)

    svc.apply_reorder(position="QB", ordered_ids=["rk_qb2", "rk_qb"])
    after = _elos(svc)

    assert after["vet_qb"] == pytest.approx(before["vet_qb"])
    assert after["rk_qb2"] > after["rk_qb"]
    assert set(svc._elo_overrides) == {"rk_qb", "rk_qb2"}


# ---------------------------------------------------------------------------
# (b) THE REORDER LANE ONLY — source
# ---------------------------------------------------------------------------

def test_the_rookie_board_never_references_the_tiers_lane():
    code = _code_only(SCREEN.read_text())
    for needle in FORBIDDEN_CLIENT:
        assert needle not in code, (
            f"RookieRanksScreen references {needle!r} in CODE — this surface is "
            f"the reorder lane only"
        )


def test_the_rookie_board_writes_on_the_shipped_reorder_lane():
    code = _code_only(SCREEN.read_text())
    assert "reorderRankings(" in code
    assert "from '../api/rankings'" in code


def test_the_rookie_board_tags_its_writes_as_rookie_scoped():
    """`via:'rookie_*'` is the forensic tag the board-restore procedure keys
    off. Request-only on this route (it branches on 'quickrank' alone), but a
    scoped edit must stay identifiable."""
    code = _code_only(SCREEN.read_text())
    assert "'rookie_ranks'" in code
    api = _code_only((REPO / "mobile/src/api/rankings.ts").read_text())
    assert "'quickrank' | 'rookie_ranks'" in api


def test_the_rookie_board_uses_the_shipped_drag_list():
    """Reuse, not reinvention: the same component and the same activation
    discipline Overall ranks and Tiers landed on."""
    code = _code_only(SCREEN.read_text())
    assert "react-native-draggable-flatlist" in code
    assert "DraggableFlatList" in code
    assert "activationDistance={DRAG_ACTIVATION_DISTANCE}" in code
    # The no-drag power path — a drag-only board is unusable under VoiceOver.
    assert "moveUp" in code and "moveDown" in code


def test_the_rookie_board_keeps_its_shipped_entry_points_and_testids():
    src = SCREEN.read_text()
    for tid in (
        "rookie-ranks.back-to-draft",   # the W1 two-way Draft Room bridge
        "rookie-ranks.list",
        "rookie-ranks.row.${item.id}",
        "rookie-ranks.filter.${f.toLowerCase()}",
    ):
        assert tid in src, f"{tid} disappeared"
    # New, in the shipped naming style.
    assert "rookie-ranks.drag-handle.${item.id}" in src


# ---------------------------------------------------------------------------
# (c) the Draft tab is a simple flag
# ---------------------------------------------------------------------------

def test_draft_tab_flag_is_registered_and_defaults_off():
    assert "draft.tab" in feature_flags.FLAG_KEYS
    assert feature_flags.DEFAULT_FLAGS["draft.tab"] is False


def test_draft_tab_flag_is_mirrored_and_ships_on():
    """The 4-touch rule: the two flag files never disagree, or `is_enabled`
    and the release fixture diverge. Operator: "right now it should be on for
    all"."""
    features = json.loads((REPO / "config/features.json").read_text())
    release = json.loads(
        (REPO / "backend/tests/fixtures/flags/release.json").read_text())
    assert "draft.tab" in features
    assert features["draft.tab"] == release["draft.tab"]
    assert features["draft.tab"] is True


def test_draft_tab_flag_is_documented_as_the_seasonal_switch():
    doc = (REPO / "docs/config-reference.md").read_text()
    assert "`draft.tab`" in doc
    assert "seasonal" in doc


def test_the_tab_is_gated_on_the_flag_and_nothing_else():
    """The whole predicate, in one line, read imperatively at first mount."""
    code = _code_only(TABNAV.read_text())
    assert "const [showDraftTab] = useState(" in code
    assert "useFeatureFlags.getState().flags['draft.tab']" in code
    # First-mount discipline: never the reactive hook for this decision.
    assert "useFlag('draft.tab')" not in code
    # No qualification of any kind survives.
    for gone in ("qualifyingDraftLeagues", "leagueQualifiesForDraftTab",
                 "draft_status", "draft_status_confidence", "DraftLeaguePicker",
                 "draft-chooser"):
        assert gone not in code, f"TabNav still computes the tab via {gone!r}"


def test_the_tab_lands_on_the_active_leagues_draft_room():
    """No chooser and no leagueId override: with the tab always on there is
    nothing to choose between, and the room renders every state honestly."""
    code = _code_only(TABNAV.read_text())
    assert "initialParams={{ inTabs: true }}" in code
    assert "leagueId: single.league_id" not in code


def test_the_retired_snapshot_module_is_gone_everywhere():
    assert not (REPO / "mobile/src/state/draftLeagues.ts").exists()
    app = APP_TSX.read_text()
    for gone in ("hydrateDraftLeagues", "refreshDraftLeagues", "draftLeagues"):
        assert gone not in app, f"App.tsx still wires {gone!r}"
    # The AsyncStorage key goes with it — nothing may still read or write it.
    for path in (REPO / "mobile/src").rglob("*.ts*"):
        assert "ftf_draft_leagues_v2" not in path.read_text(), path


def test_the_draft_room_stays_reachable_without_the_tab():
    """DraftRoom is DUAL-REGISTERED (root stack + the tab's stack) with ONE
    canonical deep-link path on the root-stack copy, so a link resolves
    identically with the tab present or hidden and can never 404."""
    root = (REPO / "mobile/src/navigation/RootNav.tsx").read_text()
    assert 'name="DraftRoom"' in root
    links = (REPO / "mobile/src/utils/deepLinks.ts").read_text()
    assert "DraftRoom: 'app/league/draft-room'" in links
