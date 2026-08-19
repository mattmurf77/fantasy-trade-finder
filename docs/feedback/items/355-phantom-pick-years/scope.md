# Feature Scope — Draft-pick horizon (stop offering picks for classes a league does not have)

**Date:** 2026-08-19
**Entry point:** feedback #355 (BUG, TradesHome, v1.15.0, 2026-08-19T12:01:22Z) — "2029 picks showing on sleeper league without 2029 picks available"
**Builder:** agent session `fix/pick-horizon`
**Operator sign-off on waivers:** not needed (no waivers)

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** `deck_impressions.assets_json` already records the exact
  asset ids on every served card, which is what made the defect measurable at all (339 polluted
  cards, see `evidence.md`). Re-running the same query after the fix ships answers "did the
  phantom class stop being served?" with no new instrumentation.
- No new events. This is a write-path correctness fix; the card shape, the deck payload and every
  emitter are unchanged, so nothing new is observable to instrument.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. `draft_picks` is unchanged in shape; only WHICH rows the
  Sleeper sync writes changes. `docs/data-dictionary.md` updated anyway, because the `season`
  column's *meaning* is now bounded (it was previously "current_season..+3", it is now "the
  league's real horizon") — a reader of that table needs to know the bound moved.
- **New/changed feature flags:** `picks.league_horizon` (default **ON**).
  Registered in `backend/feature_flags.py` and `config/features.json`; documented in
  `docs/config-reference.md`.
  - **Default-ON rationale:** the flag's OFF state is the defect. Shipping it OFF would ship
    nothing. OFF is retained purely as the deploy-free rollback lever.
  - **Graduation criterion:** the flag is removable once one full sync cycle has run with zero
    out-of-horizon rows in `draft_picks` and the `evidence.md` prod query returns 0 polluted
    impressions for a week.
- **New env vars / `model_config` keys:** none.
  - **Ship-the-knob:** `picks.league_horizon = false` restores the historical
    `[current_season .. current_season + seasons_ahead]` grid byte-for-byte, with no deploy —
    flags hot-reload via `POST /api/feature-flags/reload`, and because the sync is a
    *replace*-sync the previous rows are rebuilt on the next `session_init` either way. Rollback
    is therefore data-complete, not just code-complete.

## 3. Evidence scope

- [x] **Unit tests:** `backend/tests/test_pick_horizon.py` — 16 tests, two layers.
  - Pure helper (`draft_status.pick_horizon`): the pre-draft window, the post-draft roll-forward,
    the always-3-classes invariant, existence-proof widening, the widening cap, garbage-input
    tolerance, and the unknown-horizon degradation.
  - Grid builder (`sync_draft_picks`): the operator's exact case (no 2029 for a pre-draft league),
    the post-draft case (2029 *kept*, because it is real), the kill switch restoring the old
    window, a reported far pick pulling its whole class in, the "never widens past the legacy
    ceiling" safety bound, and the #220 empty-roster guard surviving the change.
- [x] **Structural guard:** n/a — no mobile file is touched. `mobile/tests/check-*.js` pins mobile
  structure; this change is backend-write-path only.
- [x] **Code-walk proof:** `code-walk.md` in this folder — file:line trace from the operator's
  screen back to the line that invented the class, plus the proof that no read path needed
  changing.
- [x] **Manual TestFlight checklist:** `testflight-checklist.md` in this folder. Runtime proof
  genuinely matters here because the user-visible outcome (a card offering a 2029 pick) is
  produced by a *background sync* the tests stub, so only a real device against real Sleeper data
  closes the loop.
- **`testID`s added/renamed:** none (no mobile diff).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed, removed, or contract-changed. `GET /api/league/picks` and the deck payload keep their exact shapes; only which pick rows exist changes. (The sibling session working feedback #356 owns the pick *labelling* edits to this file.) |
| `living-memory/LLD.md` | **updated** | New invariant: a `draft_picks` row's `season` must lie inside the league's derived horizon; the horizon is anchored to the first undrafted class, not to `current_season`. |
| `docs/architecture.md` | n/a | No module wiring or data-flow change. `draft_status` was already imported by `database.py`; one more pure helper on an existing seam is not an architecture shift. |
| `living-memory/HLD.md` | n/a | No new module, client, or major flow. |
| `docs/cross-client-invariants.md` | **updated** | The 3-class horizon is a shared truth about what assets exist — mobile, web and the extension all render pick years, so a client must not assume `current_season + 3`. |
| `docs/glossary.md` | **updated** | New domain term: **pick horizon** (and **draft class** as its unit). |
| ADR or `DECISIONS.md` entry | **updated** | **D-091** — the horizon rule, the unknown-horizon degradation choice, and why the assignment grid was deliberately left alone. Open question **Q-022** logged for the ESPN/assignment exposure. |

## 5. Ship gate declaration

- **CI green:** `backend-tests` — full `pytest backend/tests` run reported in TEST_LEDGER.
  `mobile-typecheck` and `maestro-testid-lint` are unaffected (zero mobile files touched) but
  must still pass on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming the unit tests, the code-walk,
  and the prod quantification.
- **TestFlight verification:** checklist written in §3 — **pending operator run**; outcome to be
  logged in TEST_LEDGER.
- **Express lane declared by the operator?** No. Full gates.
