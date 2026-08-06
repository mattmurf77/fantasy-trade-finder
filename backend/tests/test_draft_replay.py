"""rookie-draft M1 — draft replay & fixture harness (plan §M1, lld §4.1, §7 M1).

Proves the harness itself, not the board: M3/M4/M5 have no code yet, so what
is under test here is that the cassettes replay hermetically, that
``truncate_picks`` manufactures every draft state deterministically, that TTL
tests can be driven by a fake clock, and that the fixture seam actually
intercepts what the plan claims it intercepts.

  T-M1-01  every corpus replays with zero live egress
  T-M1-02  truncate_picks(k), k in {0,1,24,48} -> upcoming/live/live/complete
  T-M1-03  the fake clock drives TTL expiry deterministically; no time.sleep
  T-M1-04  [RV-3] the bulk players fetch is intercepted by the fixture seam
           -- xfail until M0 routes it through _sleeper_get

Run: ``python3 -m pytest backend/tests/test_draft_replay.py``
"""

from __future__ import annotations

import ast
import json
import pathlib
import urllib.error

import pytest

import backend.server as server
from backend import mfl_service, test_support
from backend.tests.support.draft_replay import (
    FIXTURES_ROOT,
    SLEEPER_STATUS_TO_STATE,
    DraftReplay,
    FakeClock,
    mfl_corpus,
    mfl_manifest,
    mfl_opener,
    mfl_unit_counts,
)

SLEEPER_CORPORA = ["lakeview-complete", "ffv3-predraft", "startup-shaped", "empty-drafts"]
MFL_CORPORA = ["mfl-made0", "mfl-partial", "mfl-complete", "mfl-multi-unit"]
BASE = "https://api.sleeper.app/v1"


def _cassette_urls(corpus_root: pathlib.Path) -> list[str]:
    """Every URL the corpus can answer, reconstructed from the file tree.

    This is the inverse of ``server._sleeper_fixture_path``, so it doubles as a
    check that the recorded layout is the layout the seam looks for.
    """
    urls = []
    for path in sorted(corpus_root.glob("**/*.json")):
        rel = path.relative_to(corpus_root)
        if rel.name == "manifest.json":
            continue
        urls.append(f"{BASE}/{rel.as_posix()[: -len('.json')]}")
    return urls


@pytest.fixture
def counters_reset():
    before = dict(test_support.counters)
    for key in test_support.counters:
        test_support.counters[key] = 0
    yield test_support.counters
    test_support.counters.update(before)


# ── T-M1-01 — hermetic replay ────────────────────────────────────────────

@pytest.mark.parametrize("corpus", SLEEPER_CORPORA)
def test_m1_01_corpus_replays_with_zero_live_egress(
        corpus, tmp_path, monkeypatch, counters_reset):
    replay = DraftReplay(corpus, tmp_path)
    replay.install(monkeypatch, server, test_mode=True)

    urls = _cassette_urls(replay.tmp_dir)
    assert urls, f"{corpus} recorded no cassettes"

    for url in urls:
        doc = server._sleeper_get(url)
        assert isinstance(doc, (dict, list))

    assert counters_reset["sleeper_live_egress_attempts"] == 0
    assert counters_reset["vcr_misses"] == 0


def test_m1_01_a_fixture_miss_never_falls_through_to_live(
        tmp_path, monkeypatch, counters_reset):
    """The seam's failure mode must be a loud 599, not a quiet live call.

    Without this the zero-egress claim above is only as strong as the URL list
    the test happens to ask for.
    """
    replay = DraftReplay("lakeview-complete", tmp_path)
    replay.install(monkeypatch, server, test_mode=True)

    with pytest.raises(urllib.error.HTTPError) as exc:
        server._sleeper_get(f"{BASE}/league/does-not-exist/drafts")

    assert exc.value.code == 599
    assert counters_reset["vcr_misses"] == 1
    assert counters_reset["sleeper_live_egress_attempts"] == 0


def test_m1_01_b_committed_corpora_are_never_mutated(tmp_path):
    """Every mutation lands on the temp copy — the cassettes stay pristine."""
    src = FIXTURES_ROOT / "lakeview-complete"
    before = {p.relative_to(src): p.read_bytes() for p in sorted(src.glob("**/*.json"))}

    replay = DraftReplay("lakeview-complete", tmp_path)
    replay.truncate_picks(7)
    replay.set_status("paused")

    after = {p.relative_to(src): p.read_bytes() for p in sorted(src.glob("**/*.json"))}
    assert after == before
    assert replay.tmp_dir != src


# ── corpus integrity — the traps the fixtures exist to pin ───────────────

def test_ffv3_pins_the_identity_slot_to_roster_id_trap():
    """D5's central trap, pinned at the fixture layer.

    The pre-draft draft object carries ``draft_order: null`` while
    ``slot_to_roster_id`` is the IDENTITY map. Reading the identity map as an
    order invents a draft order out of nothing. M3's T-M3-03 asserts the
    behaviour; this asserts the fixture still contains the hazard, so nobody
    "tidies" the trap away and leaves T-M3-03 passing vacuously.
    """
    root = FIXTURES_ROOT / "ffv3-predraft"
    man = json.loads((root / "manifest.json").read_text())
    detail = json.loads((root / "draft" / f"{man['draft_id']}.json").read_text())

    assert detail["draft_order"] is None
    assert detail["start_time"] is None
    assert detail["last_picked"] is None

    s2r = detail["slot_to_roster_id"]
    assert s2r, "the trap requires slot_to_roster_id to be POPULATED"
    assert all(int(slot) == int(roster) for slot, roster in s2r.items()), \
        "ffv3 corpus no longer carries the identity map — the trap is gone"

    assert json.loads((root / "draft" / man["draft_id"] / "picks.json").read_text()) == []

    # And the same draft, read from the league's /drafts list, does NOT carry
    # the map at all. Two Sleeper surfaces, two answers for one draft — so a
    # reader that only ever sees the list would never even meet the trap.
    drafts = json.loads((root / "league" / man["league_id"] / "drafts.json").read_text())
    assert len(drafts) == 1
    assert drafts[0].get("slot_to_roster_id") is None
    assert drafts[0]["draft_order"] is None


def test_lakeview_is_the_honest_order_control():
    root = FIXTURES_ROOT / "lakeview-complete"
    man = json.loads((root / "manifest.json").read_text())
    detail = json.loads((root / "draft" / f"{man['draft_id']}.json").read_text())

    assert detail["status"] == "complete"
    assert detail["draft_order"] and len(detail["draft_order"]) == 12
    s2r = detail["slot_to_roster_id"]
    assert any(int(slot) != int(roster) for slot, roster in s2r.items()), \
        "lakeview must be a NON-identity order or it stops being the control"

    picks = json.loads((root / "draft" / man["draft_id"] / "picks.json").read_text())
    assert len(picks) == 48 == detail["settings"]["rounds"] * detail["settings"]["teams"]

    traded = json.loads((root / "league" / man["league_id"] / "traded_picks.json").read_text())
    assert traded, "the traded-pick overlay case needs traded picks"


def test_empty_and_startup_corpora_pin_their_shapes():
    empty_man = json.loads((FIXTURES_ROOT / "empty-drafts" / "manifest.json").read_text())
    drafts = json.loads(
        (FIXTURES_ROOT / "empty-drafts" / "league" / empty_man["league_id"]
         / "drafts.json").read_text())
    assert drafts == []

    su_man = json.loads((FIXTURES_ROOT / "startup-shaped" / "manifest.json").read_text())
    detail = json.loads(
        (FIXTURES_ROOT / "startup-shaped" / "draft" / f"{su_man['draft_id']}.json").read_text())
    assert detail["settings"]["rounds"] == 28
    assert detail["status"] == "pre_draft"
    # Derived from lakeview, so it keeps a REAL order — startup-labelled is a
    # separate axis from order-not-set, and the fixtures must not conflate them.
    assert detail["draft_order"]


@pytest.mark.parametrize("corpus", SLEEPER_CORPORA + MFL_CORPORA + ["players-bulk"])
def test_every_corpus_declares_its_provenance(corpus):
    man = json.loads((FIXTURES_ROOT / corpus / "manifest.json").read_text())
    assert man["provenance"] in {"recorded-live", "authored"} \
        or man["provenance"].startswith("derived-from-")
    assert man["recorded"]
    assert man["pins"]
    if man["provenance"] != "recorded-live":
        assert man["derivation"], f"{corpus} is not live — it must say how it was made"


# ── T-M1-02 — truncate_picks manufactures every state ────────────────────

@pytest.mark.parametrize("k, expected_state", [
    (0, "upcoming"),
    (1, "live"),
    (24, "live"),
    (48, "complete"),
])
def test_m1_02_truncate_picks_yields_state_and_last_picked(
        k, expected_state, tmp_path, monkeypatch, counters_reset):
    replay = DraftReplay("lakeview-complete", tmp_path)
    replay.install(monkeypatch, server, test_mode=True)
    replay.truncate_picks(k)

    detail = server._sleeper_get(f"{BASE}/draft/{replay.draft_id}")
    picks = server._sleeper_get(f"{BASE}/draft/{replay.draft_id}/picks")

    assert len(picks) == k
    assert replay.state_label == expected_state
    assert SLEEPER_STATUS_TO_STATE[detail["status"]] == expected_state
    assert detail["last_picked"] == replay.pick_timestamp(k)
    assert (detail["last_picked"] is None) == (k == 0)

    # The same draft read from the league list must not disagree with itself.
    listed = server._sleeper_get(f"{BASE}/league/{replay.league_id}/drafts")[0]
    assert listed["status"] == detail["status"]
    assert listed["last_picked"] == detail["last_picked"]

    assert counters_reset["sleeper_live_egress_attempts"] == 0


def test_m1_02_a_full_truncation_is_byte_faithful_to_the_live_recording(tmp_path):
    """truncate_picks(total) must reproduce the recorded cassette exactly.

    Without this the synthesised timestamp ladder could silently drift away
    from what Sleeper actually served.
    """
    replay = DraftReplay("lakeview-complete", tmp_path)
    recorded = json.loads(
        (FIXTURES_ROOT / "lakeview-complete" / "draft"
         / f"{replay.draft_id}.json").read_text())

    replay.truncate_picks(replay.total_picks)

    assert replay.detail["last_picked"] == recorded["last_picked"]
    assert replay.detail["status"] == recorded["status"]
    assert replay.picks == json.loads(
        (FIXTURES_ROOT / "lakeview-complete" / "draft" / replay.draft_id
         / "picks.json").read_text())


def test_m1_02_b_pick_timestamps_are_strictly_increasing(tmp_path):
    replay = DraftReplay("lakeview-complete", tmp_path)
    stamps = [replay.pick_timestamp(k) for k in range(1, replay.total_picks + 1)]
    assert all(b > a for a, b in zip(stamps, stamps[1:]))
    assert replay.pick_timestamp(0) is None


def test_m1_02_c_advance_steps_and_is_reversible(tmp_path):
    replay = DraftReplay("lakeview-complete", tmp_path)
    replay.truncate_picks(0)
    assert replay.state_label == "upcoming"

    replay.advance()
    assert replay.picks_made == 1 and replay.state_label == "live"

    replay.advance(23)
    assert replay.picks_made == 24 and len(replay.picks) == 24

    replay.advance(24)
    assert replay.state_label == "complete"

    # Stepping back re-slices from the pristine list, not from the truncation.
    replay.truncate_picks(3)
    assert [p["pick_no"] for p in replay.picks] == [1, 2, 3]

    with pytest.raises(ValueError):
        replay.truncate_picks(replay.total_picks + 1)


def test_m1_02_d_set_status_handles_the_disagreeing_cases(tmp_path):
    """Status and pick count can legitimately diverge — a complete draft with
    zero picks is #207's own conflict case."""
    replay = DraftReplay("lakeview-complete", tmp_path)
    replay.truncate_picks(0)
    replay.set_status("complete")

    assert replay.picks == []
    assert replay.state_label == "complete"
    assert replay.drafts[0]["status"] == "complete"

    replay.set_status("paused")
    assert replay.state_label == "live"

    with pytest.raises(ValueError):
        replay.set_status("nonsense")


def test_m1_02_e_predraft_corpus_has_nothing_to_truncate(tmp_path):
    replay = DraftReplay("ffv3-predraft", tmp_path)
    assert replay.total_picks == 0
    assert replay.state_label == "upcoming"
    replay.truncate_picks(0)
    assert replay.detail["last_picked"] is None


# ── T-M1-03 — the fake clock ─────────────────────────────────────────────

def test_m1_03_fake_clock_drives_ttl_expiry_deterministically():
    """A stand-in for the per-draft TTL cache M3 will build.

    The point is the mechanism: a module-level ``_now_monotonic`` indirection
    that a test can replace, so TTL boundaries are exact and the suite never
    sleeps.
    """
    clock = FakeClock(start=1_000.0)
    fetches = []

    def cached_fetch(cache: dict, key: str, ttl: float):
        entry = cache.get(key)
        if entry is not None and clock() - entry[0] < ttl:
            return entry[1]
        fetches.append(key)
        cache[key] = (clock(), f"payload-{len(fetches)}")
        return cache[key][1]

    cache: dict = {}
    assert cached_fetch(cache, "d1", ttl=20) == "payload-1"

    clock.advance(19.999)
    assert cached_fetch(cache, "d1", ttl=20) == "payload-1"
    assert len(fetches) == 1

    clock.advance(0.001)          # exactly at the boundary -> expired
    assert cached_fetch(cache, "d1", ttl=20) == "payload-2"
    assert len(fetches) == 2

    # Nothing moves unless the test moves it.
    for _ in range(10):
        cached_fetch(cache, "d1", ttl=20)
    assert len(fetches) == 2

    assert clock.now == 1_020.0


def test_m1_03_a_replay_surface_never_sleeps():
    """No wall-clock waiting in the M1 surface — the fake clock is the point.

    Parsed rather than grepped so prose about sleeping doesn't count as a call.
    """
    for path in (pathlib.Path(__file__),
                 pathlib.Path(__file__).parent / "support" / "draft_replay.py"):
        tree = ast.parse(path.read_text())
        calls = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "sleep"
        ]
        assert not calls, f"{path.name} calls sleep() at line {calls[0].lineno}"


# ── MFL half — committed snapshots + injected _opener ────────────────────

@pytest.mark.parametrize("corpus", MFL_CORPORA)
def test_mfl_corpus_replays_through_the_opener_seam(corpus):
    """``mfl_service`` has no env seam, so the corpus rides ``_opener``.

    Also asserts D8's premise on live data: a franchise on EVERY pick, made or
    not — which is what lets MFL answer "who picks at 2.03" pre-draft.
    """
    man = mfl_manifest(corpus)
    calls: list[str] = []

    raw = mfl_service.fetch_draft_results(
        man["league_id"], man["year"], man["host"],
        _opener=mfl_opener(corpus, calls=calls))

    assert raw == mfl_corpus(corpus)
    assert len(calls) == 1
    assert f"TYPE=draftResults&L={man['league_id']}" in calls[0]
    assert calls[0].startswith(f"https://{man['host']}/{man['year']}/export?")

    units, made, total = mfl_unit_counts(raw)
    assert (units, made, total) == (man["units"], man["made"], man["total"])

    du = raw["draftResults"]["draftUnit"]
    for unit in (du if isinstance(du, list) else [du]):
        picks = unit["draftPick"]
        picks = picks if isinstance(picks, list) else [picks]
        assert all(str(p.get("franchise", "")).strip() for p in picks), \
            "D8 depends on a franchise on every unmade pick"


def test_mfl_corpora_cover_the_four_states():
    states = {}
    for corpus in MFL_CORPORA:
        man = mfl_manifest(corpus)
        units, made, total = mfl_unit_counts(mfl_corpus(corpus))
        if made == 0:
            states["made0"] = corpus
        elif made < total:
            states["partial"] = corpus
        else:
            states["multi_unit" if units > 1 else "complete"] = corpus
        assert man["provenance"] == "recorded-live", \
            f"{corpus} must be a live MFL export, not a hand-edit"
    assert set(states) == {"made0", "partial", "complete", "multi_unit"}


def test_mfl_opener_refuses_an_unrecorded_export():
    """A second export type must fail loudly, never reach the network."""
    with pytest.raises(AssertionError, match="only serves draftResults"):
        mfl_service.fetch_future_draft_picks(
            "10005", 2026, "www48.myfantasyleague.com",
            _opener=mfl_opener("mfl-complete"))


# ── T-M1-04 — [RV-3] the bulk players fetch ──────────────────────────────

def test_m1_04_bulk_players_fetch_is_intercepted_by_the_fixture_seam(
        tmp_path, monkeypatch, counters_reset):
    """The plan's replay mechanism does not currently cover the 5 MB dump.

    Verify-failing-first (lld §7): red against today's tree, green the moment
    M0 routes the fetch through ``_sleeper_get``.
    """
    replay = DraftReplay("players-bulk", tmp_path)
    # test_mode=False: under test mode the function raises before it would
    # fetch, which would hide the seam gap rather than expose it.
    replay.install(monkeypatch, server, test_mode=False)
    monkeypatch.setattr(server, "_sleeper_cache", None)
    monkeypatch.setattr(server, "PLAYERS_CACHE_FILE", tmp_path / "no-such-cache.json")
    monkeypatch.setattr(server, "needs_player_sync", lambda: False)

    seen: list[str] = []
    real_get = server._sleeper_get

    def spy(url, timeout=15):
        seen.append(url)
        return real_get(url, timeout)

    monkeypatch.setattr(server, "_sleeper_get", spy)

    def no_live(*args, **kwargs):
        raise AssertionError(
            "bulk players fetch went straight to the network — the fixture "
            "seam never saw it ([RV-3])")

    monkeypatch.setattr(server.urllib.request, "urlopen", no_live)

    server._ensure_sleeper_cache_populated()

    assert any(url.endswith("/players/nfl") for url in seen)
    assert counters_reset["vcr_misses"] == 0


def test_m1_04_a_players_bulk_cassette_sits_where_the_seam_looks(
        tmp_path, monkeypatch):
    """Independent of [RV-3]: once the fetch is routed, the cassette is there.

    This one passes today, so the xfail above is isolated to the routing gap
    and cannot be satisfied by a missing fixture.
    """
    replay = DraftReplay("players-bulk", tmp_path)
    replay.install(monkeypatch, server, test_mode=True)

    url = f"{BASE}/players/nfl"
    assert server._sleeper_fixture_path(url) == replay.tmp_dir / "players" / "nfl.json"
    assert "13287" in server._sleeper_get(url)
