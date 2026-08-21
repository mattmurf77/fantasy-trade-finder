"""Session-wide hermeticity for the DynastyProcess **pick** curve.

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

This pins the PICK curve only. The player curve (`FTF_DP_VALUES_FILE`) is not
set here: no unconditional code path reaches it, and pinning it would change
what a large number of unrelated tests see.
"""

import os
import pathlib

_PICK_SNAPSHOT = (pathlib.Path(__file__).resolve().parent
                  / "fixtures" / "dp_values_picks_2026-08-06.csv")

os.environ.setdefault("FTF_DP_PICK_VALUES_FILE", str(_PICK_SNAPSHOT))
