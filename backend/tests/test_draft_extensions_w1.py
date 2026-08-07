"""draft-extensions W1 — draft-room per-player actions + instrumentation.

Plan `docs/plans/draft-extensions/plan.md` §4, LLD §2.1/§2.2/§4.1.

W1's whole safety story is one sentence: **the anchor lane only.** The Draft
Room's new row actions may reach `POST /api/anchor/save` and nothing else.
`save_tiers_position` / the merged-band `apply_tiers*` path is the one
construction in this codebase that can destroy a user's board, so "we didn't
call it" is pinned three ways here rather than asserted in a comment:

  (a) AST — `save_anchor_route`'s own body names no tiers-save symbol;
  (b) runtime — a live anchor save with `save_tiers_position` booby-trapped
      to raise still returns 200, and never touches `tiers_saved`/`all_done`;
  (c) source — the W1 CLIENT surfaces (the Draft Room screen and the new
      anchor sheet) contain no tiers-save reference at all.

Also covered: the request-only `via` field (whitelist + fallback + a
byte-identical response), the four new client events being registered in
BOTH taxonomy registries and in NEITHER server registry, and the
`draft.rank_inline` flag landing OFF in all three mirrors.
"""
import ast
import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import backend.analytics_taxonomy as taxonomy
import backend.feature_flags as feature_flags
import backend.server as server
from backend.ranking_service import Player, RankingService

REPO = Path(__file__).resolve().parents[2]
SERVER_PATH = REPO / "backend" / "server.py"

ME = "user_w1_test"

# Every symbol that leads to the merged-band board rewrite. If a W1 surface
# ever names one of these, the wave has left its lane.
FORBIDDEN_BACKEND = ("save_tiers_position", "apply_tiers", "apply_tiers_subset")


# ---------------------------------------------------------------------------
# harness — mirrors backend/tests/test_pick_anchor.py's session fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def harness():
    pool = [
        Player(id="rb1", name="Runner Back", position="RB", team="AAA", age=24),
    ]
    service = RankingService(players=pool)
    token = "test-token-w1"
    sess = {
        "user_id":       ME,
        "league":        None,       # no league → member_rankings publish skipped
        "players":       pool,
        "services":      {"1qb_ppr": service},
        "service":       service,
        "trade_svc":     MagicMock(),
        "active_format": "1qb_ppr",
        "last_active":   0.0,
    }
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    with patch.object(server, "save_tier_overrides", MagicMock()):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield client, token
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _post(client, token, body):
    return client.post(
        "/api/anchor/save",
        headers={"X-Session-Token": token, "Content-Type": "application/json"},
        data=json.dumps(body),
    )


# ---------------------------------------------------------------------------
# (a) the optional `via` / `surface` field — request-only
# ---------------------------------------------------------------------------

def test_via_is_whitelisted_and_reaches_the_event_props(harness):
    client, token = harness
    with patch.object(server, "record_event") as rec:
        r = _post(client, token,
                  {"player_id": "rb1", "anchor": "1_first", "via": "draft_room"})
    assert r.status_code == 200
    assert rec.call_count == 1
    assert rec.call_args.kwargs["props"]["via"] == "draft_room"


def test_surface_is_accepted_as_an_alias_for_via(harness):
    client, token = harness
    with patch.object(server, "record_event") as rec:
        r = _post(client, token,
                  {"player_id": "rb1", "anchor": "1_first",
                   "surface": "draft_room"})
    assert r.status_code == 200
    assert rec.call_args.kwargs["props"]["via"] == "draft_room"


@pytest.mark.parametrize("body_extra", [
    {},                              # omitted entirely — the wizard's body
    {"via": "tiers"},                # a real value, but not on THIS whitelist
    {"via": "rookie_quickset"},      # a tiers-save member — must not leak in
    {"via": ""},
    {"via": "  "},
])
def test_unrecognised_via_falls_back_and_never_400s(harness, body_extra):
    client, token = harness
    with patch.object(server, "record_event") as rec:
        r = _post(client, token,
                  {"player_id": "rb1", "anchor": "1_first", **body_extra})
    assert r.status_code == 200
    assert rec.call_args.kwargs["props"]["via"] == "anchors"


def test_via_does_not_change_the_response_body(harness):
    """D10 — the byte-identical-RESPONSE bar. `via` is request-only."""
    client, token = harness
    plain = _post(client, token, {"player_id": "rb1", "anchor": "2_firsts"})
    withv = _post(client, token,
                  {"player_id": "rb1", "anchor": "2_firsts",
                   "via": "draft_room"})
    assert plain.status_code == withv.status_code == 200
    assert plain.get_data() == withv.get_data()


def test_the_anchor_via_whitelist_is_not_the_tiers_save_one():
    """The tiers-save `via` whitelist belongs to the lane W1 FORBIDS.

    Sharing one list would let a draft-room save be waved through the
    merged-band path (or a rookie-tiers save be counted as a draft-room
    anchor). They are separate constants on purpose.
    """
    assert server._ANCHOR_VIA == ("anchors", "draft_room")
    # The tiers-save whitelist's own members must not appear in ours.
    for member in ("rookie_tiers", "rookie_quickset"):
        assert member not in server._ANCHOR_VIA


# ---------------------------------------------------------------------------
# (b) THE ANCHOR LANE ONLY — AST, runtime and source
# ---------------------------------------------------------------------------

def _route_function(name: str) -> ast.FunctionDef:
    tree = ast.parse(SERVER_PATH.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in server.py")


def test_ast_anchor_route_never_names_a_tiers_save_symbol():
    """(a) — structural. Copies the test_m3_07 AST-containment pattern."""
    fn = _route_function("save_anchor_route")
    named = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Name):
            named.add(node.id)
        elif isinstance(node, ast.Attribute):
            named.add(node.attr)
    for symbol in FORBIDDEN_BACKEND:
        assert symbol not in named, (
            f"save_anchor_route names {symbol!r} — W1 is the anchor lane only"
        )


def test_runtime_anchor_save_never_calls_save_tiers_position(harness):
    """(b) — behavioural. A booby-trapped tiers-save must never fire."""
    client, token = harness

    def _boom(*a, **k):  # pragma: no cover - the point is that it never runs
        raise AssertionError("save_tiers_position reached from the anchor lane")

    with patch.object(server, "save_tiers_position", _boom):
        r = _post(client, token,
                  {"player_id": "rb1", "anchor": "2_firsts",
                   "via": "draft_room"})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_runtime_anchor_save_leaves_tiers_saved_and_all_done_alone(harness):
    """D1 — `tiers_saved` / `all_done` are untouched by an anchor save."""
    client, token = harness
    with patch.object(server, "get_tiers_saved") as saved:
        r = _post(client, token,
                  {"player_id": "rb1", "anchor": "1_third",
                   "via": "draft_room"})
    assert r.status_code == 200
    saved.assert_not_called()


W1_CLIENT_FILES = (
    "mobile/src/screens/DraftRoomScreen.tsx",
    "mobile/src/components/AnchorSheet.tsx",
    "mobile/src/utils/anchorRows.ts",
)

# Substrings that would mean a W1 client surface can REACH the tiers lane.
FORBIDDEN_CLIENT = ("/api/tiers/save", "saveTiers", "resetTiers",
                    "tiers/save", "save_tiers_position", "apply_tiers")

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _code_only(src: str) -> str:
    """Strip // and /* */ comments.

    Mirrors the docstring-exclusion in test_m3_08: these files EXPLAIN the
    prohibition in prose, and a rule that fires on its own explanation would
    only teach builders to delete the explanation.
    """
    src = _BLOCK_COMMENT.sub("", src)
    return "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("//")
    )


def test_w1_client_surfaces_never_reference_the_tiers_lane():
    """(c) — the mobile half of the same rule."""
    for rel in W1_CLIENT_FILES:
        code = _code_only((REPO / rel).read_text())
        for needle in FORBIDDEN_CLIENT:
            assert needle not in code, f"{rel} references {needle!r} in CODE"


def test_the_anchor_sheet_uses_the_shipped_anchor_lane():
    """The sheet is net-new (HLD RB-11); the LANE it writes on is not."""
    sheet = (REPO / "mobile/src/components/AnchorSheet.tsx").read_text()
    assert "saveAnchor(" in sheet
    # One rung table, imported — never a second copy of the cross-client enum.
    assert "from '../utils/anchorRows'" in sheet
    wizard = (REPO / "mobile/src/screens/PickAnchorScreen.tsx").read_text()
    assert "utils/anchorRows" in wizard
    assert "'4_firsts', label" not in wizard, "the rung table was copied, not shared"
    # The surface attribution is supplied by the HOST, so a second host
    # cannot accidentally inherit the draft room's label.
    room = (REPO / "mobile/src/screens/DraftRoomScreen.tsx").read_text()
    assert 'via="draft_room"' in room


def test_per_player_testids_are_qualified():
    """D0 — the shipped rows shared one non-unique id, so the flow was
    untestable. The qualifier is a stable domain id, never a list index."""
    src = (REPO / "mobile/src/screens/DraftRoomScreen.tsx").read_text()
    assert "draft-room.undrafted-row.${row.player_id}" in src
    assert 'testID="draft-room.undrafted-row"' not in src
    assert 'testID="draft-room.order-row"' not in src
    assert 'testID="draft-room.pick-row"' not in src


# ---------------------------------------------------------------------------
# (c) analytics taxonomy — default-deny, both registries, neither server one
# ---------------------------------------------------------------------------

W1_CLIENT_EVENTS = (
    "draft_room_row_menu_opened",
    "draft_room_action_taken",
    "draft_room_coverage_nudge_shown",
    "draft_room_rank_rookies_tapped",
)


@pytest.mark.parametrize("event", W1_CLIENT_EVENTS)
def test_w1_events_are_registered_in_both_client_registries(event):
    assert event in taxonomy.ALLOWED_CLIENT_EVENTS
    assert event in taxonomy.CLIENT_EVENT_PROPS
    assert taxonomy.CLIENT_EVENT_PROPS[event], "an empty prop set drops every prop"


@pytest.mark.parametrize("event", W1_CLIENT_EVENTS)
def test_w1_events_are_not_server_authoritative(event):
    """Adding a client event to SERVER_FIRED_EVENTS crashes the app at
    import (the disjointness assert). Keep them out."""
    assert event not in taxonomy.SERVER_FIRED_EVENTS
    assert event not in taxonomy._SERVER_AUTHORITATIVE


def test_w1_event_props_match_the_lld():
    props = taxonomy.CLIENT_EVENT_PROPS
    assert props["draft_room_row_menu_opened"] == frozenset(
        {"surface", "player_id", "valued", "rank"})
    assert props["draft_room_action_taken"] == frozenset(
        {"action", "player_id", "valued"})
    assert props["draft_room_coverage_nudge_shown"] == frozenset(
        {"unvalued_count", "window"})
    assert props["draft_room_rank_rookies_tapped"] == frozenset(
        {"state", "from"})


def test_the_draft_room_now_emits_analytics_at_all():
    """D0's first deliverable: the room shipped with ZERO track() calls."""
    src = (REPO / "mobile/src/screens/DraftRoomScreen.tsx").read_text()
    for event in W1_CLIENT_EVENTS:
        assert f"'{event}'" in src, f"{event} is registered but never fired"


# ---------------------------------------------------------------------------
# (d) the flag lands OFF, in every mirror
# ---------------------------------------------------------------------------

def test_rank_inline_flag_is_registered_and_defaults_off():
    assert "draft.rank_inline" in feature_flags.FLAG_KEYS
    assert feature_flags.DEFAULT_FLAGS["draft.rank_inline"] is False


def test_rank_inline_flag_is_registered_and_mirrored():
    """The flag exists in BOTH files and they agree.

    This asserted `is False` when W1 landed dark. The operator flipped it ON
    (2026-08-06) after reporting they could not rank rookies from the draft
    page, and W1's code was already in build 82 — so a ship-off assertion is
    now wrong. What must stay true is the 4-touch mirror: the two files never
    disagree, or `is_enabled` and the release fixture diverge.
    """
    features = json.loads((REPO / "config/features.json").read_text())
    release = json.loads(
        (REPO / "backend/tests/fixtures/flags/release.json").read_text())
    assert "draft.rank_inline" in features
    assert features["draft.rank_inline"] == release["draft.rank_inline"]


def test_flag_off_leaves_the_undrafted_rows_inert():
    """The client-side kill switch: no handler ⇒ the shipped plain View."""
    src = (REPO / "mobile/src/screens/DraftRoomScreen.tsx").read_text()
    assert "rowActionsOn ? onRowMenu : undefined" in src
    assert "if (!onMenu) {" in src
