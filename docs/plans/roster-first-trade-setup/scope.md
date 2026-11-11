# Feature Scope — Roster-first setup for Find a Trade

**Date:** 2026-11-10
**Entry point:** direct ask (operator idea, relayed from the parent session); evidence: the 2026-11-10 acceptance eval (`docs/plans/realtime-trade-engine/acceptance-eval.md`, `trade-engine-rearch` worktree, uncommitted)
**Builder:** not yet assigned. This session scoped and designed only.
**Operator sign-off on waivers:** **given 2026-11-10.** The operator accepted the §3 web waiver and the recommended answers to the open questions in [prd.md §0](prd.md#0-open-questions-for-the-operator-answer-before-build).

Design: [prd.md](prd.md) · Analytics: [analytics.md](analytics.md) · Reuse evidence: [reuse-map.md](reuse-map.md) · Mockup: [`mockups/roster-first-trade-setup/`](../../../mockups/roster-first-trade-setup/index.html)

---

## 1. Analytics scope

- [x] **(a) New events specced.** Six client events, `roster_setup_*`. The full spec, including NON_INTENT classification and why existing events are not enough, is in [analytics.md](analytics.md).

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `roster_setup_shown` | `league_id, entry, roster_size, pick_count, prefilled_count` | Setup screen first renders for an entry (`entry` ∈ first_pass, roster_changed, manual_dna, entry_card) | mobile |
  | `roster_setup_toggles_done` | `league_id, entry, move_count, keep_count, open_count, pick_move_count, pick_keep_count, changed_count, duration_ms` | User leaves Step 1 by Continue | mobile |
  | `roster_setup_rank_saved` | `league_id, position, players_ranked, players_total` | One position's reorder POST succeeds | mobile |
  | `roster_setup_completed` | `league_id, entry, ranked_positions, changed, duration_ms` | Done state renders | mobile |
  | `roster_setup_skipped` | `league_id, entry, stage` | Skip, or back, at any step | mobile |
  | `roster_setup_prompt_tapped` | `league_id, surface, new_asset_count` | Entry card / re-prompt card / DNA row tapped | mobile |

  Existing events that also fire, unchanged: server `asset_pref_added` / `asset_pref_removed` (`server.py:28328-28334`, now with `list_type='trade_block'`) and server `ranking_reorder` (`server.py:18124-18136`).
  → follow-through: `backend/analytics_taxonomy.py` (`ALLOWED_CLIENT_EVENTS`, `CLIENT_EVENT_PROPS`) and `backend/analytics_queries.py` `NON_INTENT_EVENTS`, **in the same commit as the emitters**. Add a tracking-plan addendum under `docs/business/analytics/`. Nothing is stored beyond `user_events`, so `docs/data-dictionary.md` changes only for the enum (§2).
- [ ] (b) Existing events cover it. **No.** See analytics.md §1.
- [ ] (c) Waived. **No.**

## 2. Schema & flag scope

- **New/changed tables or columns:** none. **One new enum value:** `asset_preferences.list_type` gains `'trade_block'`. The column is a free `String` (`database.py:1814`), so no migration is needed. Validation lives in `ASSET_PREF_LISTS` (`database.py:12739`) and the route (`server.py:28315-28316`).
  → `docs/data-dictionary.md` (asset_preferences.list_type enum), `docs/cross-client-invariants.md` (the list-type strings are shared by backend and mobile `AssetPrefs`).
- **New/changed feature flags:** `trades.roster_setup`, **default false**. It gates (1) the mobile screen, entry card and DNA row, and (2) the engine reading `trade_block` in the owner and bilateral constructors. **Persistence is not gated**: the asset-prefs route accepts and returns `trade_block` in both states, following the #360 `avoid_positions` precedent, so a kill switch never destroys data.
  → `config/features.json` + `backend/feature_flags.py` `FLAG_KEYS` + `docs/config-reference.md`.
  **Graduation criterion:** on for internal testers for 2 weeks. Then, among users shown the step: completion rate ≥ 40%, and deck like rate in the 7 days after completion is not below the matched no-setup cohort (analytics.md §4). Before reading any lift, check the production `FTF_FLAGS` override list (G-076).
- **New env vars / `model_config` keys:** none. The give-side weights for `trade_block` (+0.1 owner interest, +0.3 bilateral declared) mirror the existing hard-coded `targets` weights rather than adding knobs. **Deploy-free rollback:** flip `trades.roster_setup` off through `POST /api/feature-flags/reload` or `FTF_FLAGS`. The engine then ignores `trade_block` rows and the client hides every surface.

## 3. Evidence scope

- [ ] **Structural guard:** `mobile/tests/check-roster-setup.js` (+ `npm run test:roster-setup`). It pins:
  1. `RosterSetupScreen` mounts no `FeedbackFAB` (tab stack, #188).
  2. Every asset-prefs write passes only `'trade_block' | 'untouchable' | 'none'`.
  3. The reorder call passes no `via`.
  4. The screen renders only behind `useFlag('trades.roster_setup')`.
  5. `QuickRankScreen` and the new screen import the same extracted chip-grid component (the extraction stays shared).
  6. All six event names exist in `backend/analytics_taxonomy.py`.
- [ ] **Unit tests (backend pytest):**
  - `test_asset_prefs.py`: `trade_block` round-trips, single membership with `untouchable`, and the bulk loader returns the `trade_block` key.
  - `test_owner_trade_block.py`: with the flag on, a `trade_block` player raises give-side interest and lands on the `declared` path in both owner-v1 and bilateral. **With the flag off, output is byte-identical** (sabotage: remove the gate, so the test fails).
  - `test_roster_reorder_subset.py`: a roster-subset reorder at one position moves only the posted IDs, and those IDs read `explicit` in the next owner context.
- [ ] **Code-walk proof** (in `build-evidence.md` at build time):
  - entry condition → pushed screen → autosave writes → reorder → bus marker → TradesHome forced regen, each hop cited by file:line;
  - the flag-off path cited to show byte-identity.
- [ ] **Manual TestFlight checklist** (runtime proof matters: this is a first-run interruption):
  1. Fresh league → Trades. Opening the tab and loading the deck do not show the setup. Pass the first card (with and without a pass reason): the setup appears after the pass is recorded, and Skip returns you to the next card.
  2. Mark 2 Move, 2 Keep, 1 pick Keep. Kill the app, reopen the screen from the DNA row. The states persist.
  3. Rank RBs only, then Done ranking. RB order on the Tiers board matches; WR order is untouched.
  4. See trades. Exactly one regeneration, and at least one card gives away a Move player.
  5. Keep 15+ players. The guard note appears.
  6. Skip on a second league. The entry card shows, Not now snoozes it, and it is re-offered once in a later session.
  7. Make a trade on the platform that brings in a player. The "1 new on your roster" card appears and lists only him.
  8. Flag off: no screen, no card, no DNA row.
- [ ] **WAIVED — web client:** v1 is mobile only. The web Trades page has no Trade DNA parity, so there is nowhere to host the step. **Signed off by the operator 2026-11-10.**
- `testID`s to add (must pass `mobile/scripts/testid-lint.sh`):
  - `roster-setup.screen`, `roster-setup.counter`
  - `roster-setup.row.<asset_id>.move|open|keep`
  - `roster-setup.continue`, `roster-setup.skip`
  - `roster-setup.rank.<pos>.chip.<player_id>`, `roster-setup.rank.save`, `roster-setup.rank.done`
  - `roster-setup.done.cta`
  - `trades.roster-setup-card`, `trades.roster-setup-card.dismiss`
  - `dna.roster-setup`

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | at build | `GET/POST /api/league/asset-prefs`: new `list` value `trade_block` and new response key `trade_block`. No new route. |
| `living-memory/LLD.md` | at build | The asset-prefs list vocabulary convention (now four types; single membership spans all four). |
| `docs/architecture.md` | n/a because | No module wiring or data flow change. New reads of an existing preference dict inside existing constructors. |
| `living-memory/HLD.md` | n/a because | No new module, client or major flow. One mobile screen inside the existing Trades stack. |
| `docs/cross-client-invariants.md` | at build | The `list_type` enum shared by backend, mobile `AssetPrefs` (`mobile/src/api/league.ts:89-94`) and analytics. |
| `docs/glossary.md` | at build | **Trade block** (a per-player, per-league "willing to move" tag; give-side twin of *target*). **Roster setup**. |
| ADR or `DECISIONS.md` entry | updated | D-212 (Move = new `trade_block` list type) and D-213 (Keep = `untouchable`, with the 40% guard). |
| `docs/data-dictionary.md` | at build | `asset_preferences.list_type` enum. |
| `docs/config-reference.md` | at build | `trades.roster_setup` row. |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (+ `check-roster-setup.js`) + `maestro-testid-lint` on the pushed sha.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming the three pytest files, the structural suite and the code-walk.
- **TestFlight verification:** the §3 checklist, run by the operator and logged in TEST_LEDGER.
- **Express lane declared by the operator?** No. And it should not be: this touches an API contract (a new enum value on asset-prefs), a feature-flag surface and analytics events, so it is over the bright line regardless.
