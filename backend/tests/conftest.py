"""Session-wide hermeticity for the DynastyProcess **pick** and **player** curves.

WHY THIS FILE EXISTS AT ALL. This repo had no conftest.py before 2026-08-21;
every test brought its own monkeypatching and that was enough, because the two
live DynastyProcess egresses were only reachable from paths tests already
stubbed. D-144 changed that: pick pricing became unconditional, so
`pick_values.priced_pool_value` — reached from `server._owned_pick_assets`,
`server._inject_owned_picks` and `/api/trade/evaluate` — now calls
`data_loader.load_pick_slot_values()` on any test that prices an owned pick.

Without a pin, that is a REAL HTTP GET to DynastyProcess from `pytest`:

  * On a machine with network (GitHub Actions is one), the suite silently
    prices picks off whatever DP published this morning. Values drift daily,
    so pinned-value assertions become flaky-by-calendar rather than wrong.
  * On a machine without network it fail-softs to `{}` and every pick falls
    back to the ladder — the suite then passes for the wrong reason, proving
    nothing about the code path that actually ships.
  * Either way it is rude: one polite fetch per day is the production budget,
    and a full suite run would spend thousands.

`FTF_DP_PICK_VALUES_FILE` is the seam `data_loader._fetch_pick_values_csv`
already honours (it is *mandatory* under `FTF_TEST_MODE`, which the UI-test
harness sets but pytest does not). Pointing it at the checked-in snapshot
makes every run deterministic against a known curve. `setdefault`, not
`environ[...] = `, so an operator can still run the suite against a different
snapshot by exporting the variable — and per-test `monkeypatch.setenv` still
overrides and restores as usual.

The snapshot is `fixtures/dp_values_picks_2026-08-06.csv`, the same file
`test_pick_pricing_m6b.py` and `test_slot_values.py` already pin explicitly;
those explicit pins are LEFT IN PLACE, because a test that depends on this
data should say so at its own top rather than inherit it silently.

THE PLAYER CURVE TOO (2026-10-22). An earlier version of this file said no
unconditional path reaches the player curve. One does: `import backend.server`
calls `load_consensus_maps()` at module level (server.py, the Elo seed), so
every pytest process that imports the server did a live GET of DP's
`values-players.csv`, and on success went on to scrape KTC for the blend.
`FTF_DP_VALUES_FILE` now points at `fixtures/outlook-hypotheses/
dp-values-players-2026-08-09.csv` (a real DP export, same parse path).

KTC is deliberately NOT pinned here. With the DP seam set and no
`FTF_KTC_VALUES_FILE`, `data_loader._fetch_ktc_html` treats KTC as off by
design ("never a live egress from a test run"). Pinning the KTC snapshot
would turn the blend on, and its id matching calls
`espn_service.get_crosswalk()`, a live GET of DP's `db_playerids.csv` with no
env seam. `test_ktc_blend` pins its own KTC data explicitly.
"""

import os
import pathlib
import sys

import pytest

_FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
_PICK_SNAPSHOT = _FIXTURES / "dp_values_picks_2026-08-06.csv"
_PLAYER_SNAPSHOT = _FIXTURES / "outlook-hypotheses" / "dp-values-players-2026-08-09.csv"

os.environ.setdefault("FTF_DP_PICK_VALUES_FILE", str(_PICK_SNAPSHOT))
os.environ.setdefault("FTF_DP_VALUES_FILE", str(_PLAYER_SNAPSHOT))

# `import backend.server` also starts `_cleanup_loop`, a daemon thread whose 300 s
# sweep evicts sessions with last_active=0, the root cause of suite-wide
# flakes on long runs. The server skips the thread when this is "1"; prod never
# sets it.
os.environ.setdefault("FTF_DISABLE_CLEANUP_LOOP", "1")


@pytest.fixture(autouse=True)
def _u4_ledger_guard_state():
    """Every test starts with the U4 ledger guard's rate-limit state clean (its
    young-trim counts per ledger and its last warning), whatever an earlier
    test left (the ledger thread-safety test trims thousands). The server is
    only touched once a test module has imported it; nothing is imported here.
    A plain reset, not `monkeypatch`: an autouse fixture that requested it
    would move every test's monkeypatch undo after its other fixtures'
    teardowns, and a fixture restoring by hand would then be overwritten."""
    server = sys.modules.get("backend.server")
    if server is not None and hasattr(server, "_ledger_guard_young"):
        server._ledger_guard_young = {"held": 0, "evicted": 0}
        server._ledger_guard_warned_at = float("-inf")
    yield


def _drain_deck_i1_checks():
    server = sys.modules.get("backend.server")
    if server is not None and hasattr(server, "_drain_deck_i1_checks"):
        server._drain_deck_i1_checks(5.0)


@pytest.hookimpl(hookwrapper=True, trylast=True)
def pytest_runtest_call(item):
    """A test's queued `deck_i1_check` writes finish as its call ends, inside
    the call's output capture (#419 QA P3). They're written on a worker; left
    to finish later they ran outside any capture window, often against an
    in-memory DB whose tables the worker's connection can't see, and their
    swallowed failures printed into the CI log. trylast: the innermost
    wrapper, so this runs before pytest's capture of the call ends."""
    yield
    _drain_deck_i1_checks()


@pytest.fixture(autouse=True)
def _deck_i1_checks_drained():
    """The same at teardown, for a write a fixture queued after the call. Only
    once `backend.server` is imported; no `monkeypatch`, for the same
    teardown-order reason as above."""
    yield
    _drain_deck_i1_checks()
