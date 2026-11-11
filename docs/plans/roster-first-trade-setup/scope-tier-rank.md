# Feature Scope — Roster setup, Step 2 rebuilt as one-page tier placement

**Date:** 2026-11-11
**Entry point:** direct ask. Operator on TestFlight 2026-11-11, looking at "Step 2 of 2 · Rank your RBs": "I thought we would be ranking the entire team (on one page) using the draft pick tier ranker." Asked whether to rebuild the step as one page with tier placement, the operator said yes.
**Builder:** not yet assigned. This session scoped only; no application code was written.
**Operator sign-off on waivers:** **pending.** One waiver (web client, §3) carries over from [scope.md](scope.md), where the operator signed it 2026-11-10. The operator still has to answer the decisions in §7.

Revises: [prd.md](prd.md) §5 (Step 2) and Q4. Step 1 (Move · — · Keep) and Step 3 (done + one regen) are unchanged. Citations are against `origin/main` `adead776`.

---

## Table of Contents
- [0. The change in one paragraph](#0-the-change-in-one-paragraph)
- [1. Findings (answers to the ten scoping questions)](#1-findings-answers-to-the-ten-scoping-questions)
- [2. Recommended design](#2-recommended-design)
- [3. Build plan](#3-build-plan)
- [4. Template §1 — Analytics scope](#4-template-1--analytics-scope)
- [5. Template §2 — Schema & flag scope](#5-template-2--schema--flag-scope)
- [6. Template §3–§5 — Evidence, docs, ship gate](#6-template-35--evidence-docs-ship-gate)
- [7. Operator decisions](#7-operator-decisions)
- [8. Not determined from the code](#8-not-determined-from-the-code)

---

## 0. The change in one paragraph

Step 2 stops being "tap your RBs in order, then your WRs…" and becomes **one page**. Every rostered QB/RB/WR/TE appears once, under the eight pick-value headings (`4+ 1sts` … `FA`), starting in the tier the user's own board already gives him. The user taps one or more players, then taps a tier in a pinned "Move to" bar. **Done** saves only the players whose tier changed, one scoped tier save per position that changed, through the existing `POST /api/tiers/save` with a new `scope:'roster'` value. That save uses the existing merged-band writer (`apply_tiers_subset`). A tier save is an **absolute** placement, so unlike today's reorder it can move the roster's value against market. That was the gap PRD Q4 left open.

## 1. Findings (answers to the ten scoping questions)

### 1.1 Do tier bands differ by position? Can one page use one set of eight headings?

- **The bands are identical across all four positions and both scoring formats.** In `backend/tier_config.json`, every (format, position) cell carries the same eight `[min, max]` bands. For example `first_1` is 1580–1785 and `second` is 1370–1575. The file's `_calibration` note says this is by design: "pick value is position-uniform… the bands are identical across positions AND scoring formats — the per-(format, position) shape is kept so consumers do not change." An RB in "1 1st" and a WR in "1 1st" therefore have the same Elo range. **One shared set of eight headings is correct.**
- `RankingService.tier_bands_for` still takes a position (`backend/ranking_service.py:1814-1830`), and `tier_for_elo` walks the tiers top-down and returns the first tier whose `lo <= elo` (`:1832-1858`). Mobile mirrors this in `tierForElo` (`mobile/src/utils/tierBands.ts:119-132`). One difference: mobile returns `waivers` (FA) below 1220, while the backend returns `None` below 1150 (`ranking_service.py:1858`). That only matters for the old 1100 "unranked" pins, and §2.4 handles it.
- **The save must still be one call per position.** The route 400s anything other than QB/RB/WR/TE (`backend/server.py:17662-17663`). Both writers resolve the pool and the bands per position (`ranking_service.py:1894-1895`, `:1972-1974`). `TiersScreen`'s cross-position "All" view already does this: it splits the merged board by each player's position and posts one save per position (`mobile/src/screens/TiersScreen.tsx:342-381`). Its comment records the one limitation: the order of different positions *within one tier* is not stored. It is re-derived from the Elos on reload. Expect **up to four calls on Done**, and only for positions where something moved.

**Can the existing writer do it as-is? No.** There are two writers, and neither is reachable for this use today:

| Writer | What it does with a subset | Verdict for a roster page |
|---|---|---|
| `apply_tiers` (unscoped, `ranking_service.py:1869-1924`) | Only the assigned and cleared pids are mutated (D-160, `:1890-1892`), so other players' overrides are safe. **But it spreads the submitted list over the whole band.** With one player it pins him at the band **ceiling** (`:1918-1919`). With two, it puts one at the ceiling and one at the floor (`:1920-1922`). | **Wrong.** Moving one RB into "1 1st" would price him at 1785, about two firsts, above every incumbent the user never saw. This is the "naive scoped-list spread" the subset writer's docstring rejects (`:1945-1947`). |
| `apply_tiers_subset` (the merged-band rule, `ranking_service.py:1927-2050`) | It merges the scoped pids into the band's current full membership, ordered by current value (`:2005-2029`), and clamps a scoped pid that is new to the tier to the band edge (`:2017`). It spreads over the **full** merged list (`:2039-2041`) and persists **scoped pids only** (`:2044-2045`). Clears are scoped too (`:1987-1989`). | **Right.** A player moved up lands at the bottom of the new tier, and one moved down lands at its top. Nobody else is respread. This matches the design system's existing tier-step rule: "up → bottom of higher tier, down → top of lower tier" (`docs/design/components.md` §Tier bins & boards, "Tier step buttons"). |

The route only reaches `apply_tiers_subset` when `scope == "rookie"`. The scope set is then the season's rookies (`server.py:17674`, `:17678-17696`, `_rookie_scope_ids` `:15402-15409`). **The build needs one small route change:** a `scope:'roster'` branch whose scope set is the posted pids themselves (§2.3).

**Subset safety of the existing save:** see the table. Both writers leave players who were not posted byte-unchanged (no write). The unscoped one still prices the posted players wrongly. Pinned today by `backend/tests/test_rookie_scope.py::test_m2_04_scoped_save_never_respreads_the_band`, `::test_m2_07_the_equivalence_bar` and `::test_m2_07b_scoped_spread_is_over_the_full_list_not_the_subset`.

### 1.2 What a placement overwrites, pre-fill, and "unchanged"

- **Every write goes through `_pin`** (`ranking_service.py:486-497`), which replaces the player's override and stamps it. A player the user already placed in Tiers, Quick Set, Anchors or a reorder **has his override replaced** when he is moved here. That is the intent: the newest explicit statement wins. A player who is **not moved is not posted and not touched**, including his position inside his tier.
- **Trio votes:** pinned players are left out of comparison replay when `pin_exclude_comparisons` is on (`ranking_service.py:1214`). Votes after a pin move him only inside his placed tier (tier-bounded voting, `_pin_bounds` `:549-594`). A placement made here gets the same protection as any Tiers save.
- **Pre-fill = the tier of the user's current board Elo**, from the board queries the screen already runs (`RosterSetupScreen.tsx:217-234`; the row tier is already computed as `tierForElo(found.elo, section, fmt)` at `:271`). A player the user has never ranked carries his seed Elo, which is the consensus value, so "personal tier if any, else consensus tier" comes for free. A roster player who is not on the board has no pool entry; the screen falls back to the consensus `tier` from the values query (`:271`). A save would drop him anyway (`ranking_service.py:2000-2001` filters to the pool), so he renders read-only.
- **"Unchanged" = the final tier equals the pre-fill tier.** The client keeps the pre-fill map and posts only the difference. A player moved and then moved back is unchanged. **Done with no moves posts nothing**, and with Step 1 also unchanged it skips the regen. That is the existing `anyChange` path (`RosterSetupScreen.tsx:440-460`), with "moved players > 0" replacing "ranked positions > 0".

### 1.3 Interaction for ~26–30 players on one phone screen

Assume a 28-player roster with 25 position players (3 QB / 8 RB / 10 WR / 4 TE, the PRD §5.2 figure), and a typical user who re-tiers about 6 of them.

| | (a) `TiersScreen` drag recipe on the roster | (b) Tap player(s), then tap a tier **(recommended)** | (c) Per-player tier stepper |
|---|---|---|---|
| Typical (6 moves) | 6 long-press drags (220 ms activation, `TiersScreen.tsx:98`) over a list of 8 headers + 25 rows of 60pt + 4pt gap ≈ 1,900pt, about 2.5 screens. Most drags cross the fold and need autoscroll. | 12 taps (6 × select + tier), or fewer when players share a destination (select 3, tap tier = 4 taps), + Done | 6–9 taps (1 per tier step) + Done |
| Whole roster moved | 25 drags | ≤ 25 + 8 taps when batched by destination | up to 7 per player |
| Current step, for reference | 21 taps + 4 saves = 25 interactions (prd §5.2) | | |
| Reuse | `DraggableFlatList` row model, a11y actions, sticky header. `TiersScreen` is 1,878 lines. `OverhaulPrioritiesScreen` reused it "in spirit", not as a component. | `TierTargetChips` (already the multi-select "Move to" bar on Tiers), the Quick Set chip construction (3-per-row, ≥48pt), `TIER_A11Y_ACTIONS` pattern (`TiersScreen.tsx:100-106`) | Nothing. The spec **removed** per-tile tier step buttons in 1.5.4 (#98, `components.md` "Tier step buttons") |
| Risk | Highest: cross-screen drag with autoscroll, plus a drop target between mixed-position rows. A no-drag path is still needed for VoiceOver. | Low: no gesture code, all taps | Contradicts the design spec. Rows stay in position order, so the user never sees the team laid out by tier, which is the thing the operator asked for |

**Recommendation: (b).** It is the only option that shows the whole team by tier on one page and has no gesture risk. Every part already exists. Constraints that apply:
- `docs/design/components.md` §Tier bins & boards: tier headers use the tier's encode color as a tick label (data encoding, `docs/cross-client-invariants.md`). The selected state is the ice border. Chips are ≥48pt tall in the Quick Set construction. The 44pt touch floor applies to the tier chips (`TierTargetChips` grows to 36 + 4pt hitSlop under `ux.touch_polish`).
- The Quick Set chip hides the position token because those walks cover one position (`SHOW_POSITION = false`, `QuickSetTiersScreen.tsx:62`, `RankChipGrid.tsx:32`). **This page mixes positions, so the chip must show it.** Use a `PositionChip` or the 3px position rail, not a new color.
- `mobile/CLAUDE.md`: no emoji glyphs. Accents are ice (actions) and flare (highlights only). Text goes through `chalkline/Text`. A pinned footer reports its height through `setPinnedBottomBarHeight('roster_setup', …)` and does not mount a second FAB (already done, `RosterSetupScreen.tsx:614-620`).

### 1.4 Within-tier order

- **The engine reads it, weakly.** Owner-v1 prices each player continuously (`elo_to_value(raw)`, `backend/trade_gen_owner.py:289`). It classifies upgrade/downgrade by tier first, then by a 5% board-value margin inside a tier (`:418-433`). Bilateral uses a tier coordinate that includes the position inside the band (`within`, `backend/trade_gen_bilateral.py:117-121`) plus a percentile term (`:90-91`). The order inside a tier therefore matters, but much less than the tier itself. The bands are 45–205 Elo wide (`trade_service.py` `_value_uncertainty` note).
- With the merged-band rule, a moved player's place inside his new tier is fixed by direction (bottom when moved up, top when moved down), and the order of incumbents is untouched. The per-position tap pass would add precision at roughly 3× the interactions.
- **Recommendation: drop the per-position tap order from the setup.** It stays one tap away for anyone who wants it, because Quick Rank (the per-tier ordering walk) already exists on the Rank tab. No follow-on pass in v1.

### 1.5 Picks

- **They cannot be placed today.** Owned picks are injected into each trade job as pseudo-players. The viewer's board is then overwritten with consensus for every pick (`server.py:20773`, comment "user board: consensus for picks"), and so is every member's board (`:20774-20776`). The viewer's source for a pick is then `consensus` (user Elo equals seed, `server.py:22060-22063`), which owner-v1 maps to `consensus_fallback` (`trade_gen_owner.py:287-296`). Pick ids (`{league_id}_…`) are not in the `RankingService` pool, so a tier save would silently drop them (`ranking_service.py:2000-2001`).
- **What placeable picks would need:** (1) somewhere to store a per-user pick value keyed by `pick_id`, since tier overrides are filtered to the player pool; (2) an overlay after `server.py:20773` that applies the viewer's pick values and marks them `explicit`; (3) publishing them into `member_rankings` so counterparties' engines read them, which means the same overwrite at `:20774-20776` has to stop clobbering them; (4) a rule for generic pick rungs versus owned picks; (5) tests across owner-v1, bilateral and legacy. That is engine work, as PRD Q5 said.
- **Recommendation for v1:** show the owned picks **read-only** in a "Picks · priced at market" strip at the foot of the page, with their consensus tier chip, so the page is still "the entire team". Placeable picks become their own item (the operator has called pick valuation the app's strongest advantage, prd Q5).

### 1.6 What the engine does differently after an absolute placement (the point of the change)

Today's step calls `apply_reorder`, which hands the posted players **the sorted multiset of their own Elos** (`ranking_service.py:2096-2139`, `target_elos` at `:2126`). The roster's set of values at each position is unchanged; only who holds which value changes. A tier placement **moves a player's Elo into a different band**. Concretely:

1. **Provenance (same for both):** any pinned player is in `placement_bands()` (`ranking_service.py:631-667`), so `_ranking_confidence` marks him `explicit` (`server.py:11761-11807`, stamped by `_confidence_payload` `:11810-11829`), and the owner context gives him source `explicit` (`server.py:22060-22066`). Owner-v1 then prices him from the user's board, not `consensus_fallback` (`trade_gen_owner.py:42`, `:282-296`). This was already true for reordered players. The difference is the **value** read.
2. **Owner-v1 viewer utility:** `personal_gain = (incoming − outgoing) / max(…)`, priced on the viewer's own values (`trade_gen_owner.py:369-371`). After a user lifts a player a tier, an at-market trade that gives him away has a lower or negative `personal_gain`. If utility drops to zero or below, the card is rejected as `viewer_no_benefit` (`:533-537`). **That is the endowment correction the eval asked for:** the engine stops offering a player the user values above market for a market-priced return. A permutation can lower one player's value only by raising another's, so it cannot do this across the roster.
3. **Owner-v1 target selection:** `_asset_interest` scores a give candidate by `direction × (personal − market) / market` (`trade_gen_owner.py:570-600`). A player placed above market scores lower as a give and is shopped less. A player placed **below** market scores higher and is shopped more. This is the "sell" signal, and it now comes from an explicit tier rather than from a reshuffle.
4. **Owner-v1 direction:** `_direction` reads the viewer's personal tier (`tier_elos`, `trade_gen_owner.py:418-433`). A re-tiered player changes which cards count as upgrade, downgrade or lateral, which the intent filter acts on (`:500-506`).
5. **Bilateral:** each player's `direction` feature is `.7 × (personal tier coordinate − market tier coordinate)/3 + .3 × (personal − market percentile)` (`trade_gen_bilateral.py:83-91`). After a permutation, those signs offset across the roster. After an absolute placement, a whole-roster lift reads as "above market" everywhere. The focal sell term `-(sell direction)` (`:182-184`) stops qualifying above-market players for the `personal_board` path (`:196-198`), and below-market players start qualifying.
6. **Legacy v2/v3:** the shrunk user Elo is clamped into the placed tier's band (`trade_service._shrink_user_elo`, `backend/trade_service.py:1889-1950`, clamp at `:1940-1950`, knob `placement_tier_clamp`). A placement moves the band, so it moves the price. A permutation only moves a player into another roster player's band.
7. **Counterparties:** the save republishes the board to `member_rankings` with explicit provenance (`server.py:17723-17738`). League-mates' owner/bilateral contexts read it as this user's board (`server.py:22003-22014`). Their decks see the user's higher asking prices too.
8. **What does not change:** the market floor and overpay gates still price packages on consensus (`trade_gen_owner.py:514-527`). A placement can filter and re-rank the trades the engine finds, but it can never make it propose a trade that fails the market floor.

### 1.7 Analytics

| Event | Still fits? | Change |
|---|---|---|
| `roster_setup_shown` | Yes | none |
| `roster_setup_toggles_done` | Yes (Step 1 unchanged) | none |
| `roster_setup_rank_saved {position, players_ranked, players_total}` | **No.** It is per position and per tap order | Not emitted by the tier page. It stays registered, and the fallback step (old flag path) keeps emitting it |
| `roster_setup_completed {ranked_positions, changed, duration_ms}` | Yes | `ranked_positions` now means "positions with at least one saved tier move" (still 0–4). No prop change |
| `roster_setup_skipped {stage}` | Yes | **Widen the `stage` enum** with `tiers`, so a skip on the new page is distinguishable from one on the old rank step |
| `roster_setup_prompt_tapped` | Yes | none |
| **new** `roster_setup_tiers_saved` | — | Once, when Done's saves all succeed with ≥1 moved player. Props: `league_id, entry, moved_count, moved_up_count, moved_down_count, players_total, positions_saved, duration_ms`. INTENT. |
| server `tier_save` (`server.py:17795-17803`) | Yes, fires once per position call | **Widen the `via` whitelist** (`server.py:17778-17781`) with `roster_setup`, so these saves do not land as plain `tiers` |
| server `ranking_reorder` | No longer fires from this step | none |

A new event type plus two enum widenings needs a **tracking-plan addendum** under `docs/business/analytics/`. The precedent is `2026-11-10-roster-setup-events.md`. `CLIENT_EVENT_PROPS` is default-deny (`backend/analytics_taxonomy.py:1770-1781`). Registration and the `NON_INTENT_EVENTS` classification (`backend/analytics_queries.py:107-118`, where the new event is **not** listed because it is intent) land in the same commit as the emitter.

### 1.8 Flag

**Recommend a new flag, `trades.roster_tier_rank`, code default off.** It is read only on mobile, inside the already-gated screen.

- **On:** Step 2 is the tier page. **Off:** Step 2 is today's per-position rank step, byte-identical, which is the fallback and the deploy-free kill switch.
- **The server must not gate the new scope.** If the server read `scope:'roster'` only behind a flag, a mismatch would fall through to unscoped `apply_tiers` and pin a lone moved player at the band ceiling (§1.1). The roster branch is read **unconditionally**: no old client ever sends it, and persistence is never gated (the #360 rule).
- **Deploy-skew guarantee:** a backend that predates this change does not know the flag key, so it serves the flag as off and no client sends the new scope to it. Ship the backend first anyway (Render auto-deploys on merge, ahead of any TestFlight build).
- **Graduation:** the §6 TestFlight checklist passes, then 2 weeks on, then a follow-up deletes the old rank step and the flag.

The other answer is to reuse `trades.roster_setup` and replace the step outright. That is less code, but the only rollback is turning off the whole setup, Step 1 included.

### 1.9 API / schema

- **No new route, no new table or column.**
- **One contract change** on `POST /api/tiers/save`: `scope` gains `'roster'`, and `via` gains `'roster_setup'`. `docs/api-reference.md` is updated.
- No `model_config` keys. One new flag (§1.8).

### 1.10 Build size

See §3. In short: **backend is small** (one route branch, about 25 lines, plus one test file of about 8 tests). **Mobile is medium** (one new board component of about 350–450 lines, about 120 lines changed in the screen, about 80 lines of pure helpers, plus the check-suite additions). Two builder agents can work in parallel against the contract in §2.3.

## 2. Recommended design

### 2.1 Layout (Step 2, flag on)

- **Header:** "Step 2 of 2 · optional", heading **"Place your players"**, lede: "Tap players, then a tier. Everyone starts where your board has them."
- **Body:** one scroll view with eight tier sections in ladder order, `4+ 1sts` → `FA`. Each header is a tick label in the tier color with a count; empty tiers still render, so they can be targets. Under each header is a 3-per-row grid of player chips in the Quick Set construction, with the **position token shown**. Inside a tier, chips sort by board Elo (descending, across positions). That is the same derivation the Tiers "All" view uses.
- **Selection:** tapping a chip toggles selection (ice border). While anything is selected, the pinned footer shows `TierTargetChips` ("Move to …"). Tapping a tier moves every selected chip there and clears the selection. The page applies the merged-band placement locally: chips moved up go to the bottom of the new tier, and chips moved down go to its top. The page then matches what the server will save.
- **Moved marker:** a moved chip carries a small "was 2nd" micro-label in the old tier's encode color, so the user can see and undo a move by moving it back. Decision 5 (§7) asks whether to also show the market tier.
- **Picks:** not shown on this page (operator, 2026-11-11, decision 3). They keep Move / Keep on Step 1 only.
- **Off-board roster players:** greyed and not selectable, labelled "not on your board".
- **Footer (no selection):** primary **Save tiers** (or **Done** when nothing has moved) and secondary **Skip**. It reports its height (`setPinnedBottomBarHeight`).
- **VoiceOver:** each selectable chip exposes `accessibilityActions` "Move to <tier>", the same pattern as `TIER_A11Y_ACTIONS` (`TiersScreen.tsx:100-106`).

### 2.2 Save

- **On Save:** group the moved players by position. For each position, `saveTiers(pos, {[tier]: ids…}, [], {scope:'roster', via:'roster_setup'})`, called **sequentially**. Each call already invalidates the trade jobs and republishes the board (`server.py:17710-17740`). On success, invalidate `['rankings', fmt, *]`, `['tiers-status']` and `['progress']`, the same as the current rank save (`RosterSetupScreen.tsx:577-579`). Then fire `roster_setup_tiers_saved` and go to Step 3.
- **Within a tier's posted list,** order the ids by their on-page order (moved up = bottom, so submit order matches page order).
- **Partial failure:** positions already saved stay saved. The page keeps the unsaved moves and shows the existing error line with **Retry**. Retry posts only the positions that failed.
- **Back / Skip with unsaved moves:** confirm "Discard your tier changes?" (Discard / Keep editing). With no moves, today's semantics apply: Step 1 counts as done (`RosterSetupScreen.tsx:493-504`), and `roster_setup_skipped` fires with `stage:'tiers'`.

### 2.3 Server contract

In `save_tiers_route` (`server.py:17632`):

```
roster_scope = body.get("scope") == "roster"          # read UNGATED (§1.8)
scope_pids   = {str(p) for ids in tiers.values() for p in ids} | set(cleared_pids)
→ take_tier_override_snapshot(user)                    # as the rookie branch does, :17683-17686
→ service.apply_tiers_subset(position, tiers, scope_pids, fmt, cleared_pids)
→ do NOT call save_tiers_position (read get_tiers_saved, as rookie does, :17762-17765)
→ via whitelist gains "roster_setup" (:17778-17781); _note_ranking_method stays skipped,
  because "roster_setup" is not in ("tiers","quickset") (:17791)
```

**The ids are the scope.** This mirrors how `/api/rankings/reorder` treats its ids, so no roster lookup is needed in the route. The posted ids are the caller's own board entries either way. The rookie branch is unchanged.

### 2.4 Edge cases

- **Sub-1150 pins** (the old 1100 "unranked" markers, `ranking_service.py:1860-1867`) show as FA on mobile. Left in FA, they are not posted. Moved up, the clamp puts them at the floor of the target tier.
- **Player in a band gap** (for example 1576–1579): mobile and backend both bucket by floor, so pre-fill and save agree.
- **Roster-changed entry** (`filterAssetIds`): the page shows only the new assets, plus their tier context (headers only).

## 3. Build plan

### W1 — backend (one builder)

| File | Change |
|---|---|
| `backend/server.py` `save_tiers_route` | `scope:'roster'` branch (§2.3), read ungated; `via` whitelist gains `roster_setup` |
| `backend/feature_flags.py` | `trades.roster_tier_rank` in `FLAG_KEYS` + `DEFAULT_FLAGS` (False) |
| `config/features.json` + `backend/tests/fixtures/flags/release.json` (+ the other fixture mirrors that carry `trades.roster_setup`) | the new key + `_comment_` |
| `backend/analytics_taxonomy.py`, `backend/analytics_queries.py` | `roster_setup_tiers_saved` + props; `stage` enum comment gains `tiers`. **Same commit as the mobile emitter**, so this lands with W2 or W2 rebases onto it |
| `backend/tests/test_roster_tier_save.py` (new) | §6 tests |
| `backend/tests/test_analytics_taxonomy_roster_setup.py` | the new event's props |

### W2 — mobile (one builder)

| File | Change |
|---|---|
| `mobile/src/components/RosterTierBoard.tsx` (new) | The tier-grouped chip board + selection + TierTargetChips footer + a11y actions. Prop-driven, no fetching |
| `mobile/src/screens/RosterSetupScreen.tsx` | Step 2 forks on `useFlag('trades.roster_tier_rank')`. Pre-fill map, moves state, save sequence, discard confirm, `tiers_saved` event, `stage:'tiers'` skip, done-summary copy ("N re-tiered") |
| `mobile/src/utils/rosterSetup.ts` | Pure, zero-runtime-import helpers: `tierPrefill`, `applyTierMove` (edge placement), `tierSavePayloads` (moved-only, per-position split, page order), `tierMoveCounts` |
| `mobile/src/api/rankings.ts` | `saveTiers` opts: `scope` accepts `'roster'`, `via` accepts `'roster_setup'` |
| `mobile/tests/check-roster-setup.js` | New assertions (§6) |
| `mobile/scripts/testid-lint-allow.txt` | Template ids for chips / tier targets |

Size: about 25 lines of backend product code plus about 250 lines of tests; about 650 lines of mobile including helpers, plus about 100 lines of check-suite additions. W1 and W2 can run in parallel against §2.3; W1 merges and deploys first.

## 4. Template §1 — Analytics scope

- [x] **(a) New events specced:**

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `roster_setup_tiers_saved` | `league_id, entry, moved_count, moved_up_count, moved_down_count, players_total, positions_saved, duration_ms` | Every per-position save from one Save tap has succeeded, and ≥1 player moved | mobile |
  | `roster_setup_skipped` (existing) | `stage` enum widened: `toggles \| rank \| tiers` | Skip or back on the tier page | mobile |
  | `tier_save` (existing, server) | `via` enum widened with `roster_setup` | Each per-position save | server |

  → follow-through: tracking-plan addendum `docs/business/analytics/2026-11-xx-roster-setup-tiers.md` **first**; `analytics_taxonomy.py` + `analytics_queries.py` in the emitter's commit; [analytics.md](analytics.md) gets a revision note. Nothing new is stored beyond `user_events`, so `docs/data-dictionary.md` is n/a.
- [ ] (b) Existing events cover it: **no**. `roster_setup_rank_saved` is per position and per tap order (§1.7).
- [ ] (c) Waived: **no**.

**Question it answers:** do users who re-tier (especially upward) see fewer "giving too much value" passes in the 7 days after? Join `roster_setup_tiers_saved.moved_up_count` against `value_giving` pass reasons, read stratified (analytics.md §4).

## 5. Template §2 — Schema & flag scope

- **New/changed tables or columns:** none.
- **New/changed feature flags:** `trades.roster_tier_rank`, **code default false**. Proposed config state: on, after W1 has deployed. It gates only the mobile Step 2 fork; the server's `scope:'roster'` is ungated (§1.8). It depends on `trades.roster_setup`. → `config/features.json` + `backend/feature_flags.py` `FLAG_KEYS`/`DEFAULT_FLAGS` + fixture mirrors + `docs/config-reference.md`. **Graduation:** checklist passes + 2 weeks, then delete the old step and the flag.
- **New env vars / `model_config` keys:** none. **Deploy-free rollback:** flip `trades.roster_tier_rank` false (`POST /api/feature-flags/reload` or `FTF_FLAGS`). The old per-position step returns, and placements already saved stay (they are ordinary tier overrides).

## 6. Template §3–§5 — Evidence, docs, ship gate

### §3 Evidence scope

- [ ] **Structural guard:** `mobile/tests/check-roster-setup.js` (existing `npm run test:roster-setup`). New assertions:
  1. Every `saveTiers` call in the screen passes `scope: 'roster'` and `via: 'roster_setup'`. The screen never calls `saveTiers` without them (sabotage: drop `scope` and the check fails).
  2. The tier page renders only behind `useFlag('trades.roster_tier_rank')`. The old rank step (and `RankChipGrid`, §5e) still renders on the off path.
  3. Pure helpers, executed under node: `tierSavePayloads` posts **only moved players**; move-then-move-back posts nothing; players are split by position; the submitted order equals page order; `applyTierMove` puts moved-up chips at the bottom and moved-down chips at the top; picks and off-board players are never in a payload.
  4. No `FeedbackFAB` import (unchanged, #188); the footer reports its height.
  5. `roster_setup_tiers_saved` exists in `backend/analytics_taxonomy.py` and is **not** in `NON_INTENT_EVENTS`.
- [ ] **Unit tests (backend pytest):** `backend/tests/test_roster_tier_save.py`, each with a named sabotage:
  1. A roster-scope save changes Elo **only** for posted ids (whole-board diff). *Sabotage:* route roster scope to `apply_tiers`, and test 2 fails.
  2. A **single** player moved up into `first_1` lands at the band floor (1580), not the ceiling. *Sabotage:* same as 1.
  3. Incumbents of the target band keep byte-identical overrides (no respread). *Sabotage:* remove the `if pid in scope_pids` persist guard.
  4. `scope:'roster'` is honoured with `ranks.rookie_subset` **and** `trades.roster_tier_rank` both off. *Sabotage:* gate the branch on a flag.
  5. A roster save does not add the position to `tiers_saved`.
  6. The `tier_save` event carries `via:'roster_setup'`.
  7. Posted ids resolve to `explicit` in the next owner context's `user_sources` (`server.py:22060`).
  8. **The point of the change:** a fixture card where the viewer gives player X for an at-market return is `eligible` before; after X is moved up two tiers through the route, the same card evaluates to `viewer_no_benefit`. *Sabotage:* post the same move through `/api/rankings/reorder` instead, and the card stays eligible.
- [ ] **Code-walk proof** (in [build-evidence.md](build-evidence.md) at build time): Save tap → `tierSavePayloads` → `saveTiers` per position → `save_tiers_route` roster branch → `apply_tiers_subset` → `save_tier_overrides` + `member_rankings` publish → `finalizeDone` → `setPendingGuidedRegen('roster_setup')` → TradesHome forced regen → owner context `explicit` source. Each hop cited by file:line. Plus the flag-off path, cited to show the old step is byte-identical.
- [ ] **Manual TestFlight checklist** (runtime proof matters: a new interaction on a first-run surface):
  1. Before starting, open Rank → Tiers and screenshot one position's board (for step 4).
  2. Pass a Find a Trade card → Step 1 is unchanged → Continue. **One page** shows every QB/RB/WR/TE under eight headings. Spot-check three players (different positions): each sits under the tier the Tiers screen shows for him.
  3. Tap **Done** without moving anything (and without Step 1 changes). The done screen says nothing changed; the deck does not regenerate.
  4. Move one RB up one tier. On the page he sits at the bottom of the new tier. Save. On Rank → Tiers → RB he is in the new tier, at or near its bottom. **Every other RB is in the same tier and order as the screenshot.**
  5. Move one WR down a tier. On Tiers he is at the top of the lower tier.
  6. Select three players from different positions, tap one tier. All three move. Save. All three show that tier on Tiers.
  7. Move a player, then move him back, then Save. Nothing changes for him on Tiers.
  8. Note a card that gives away player X for a fair-looking return. Move X up two tiers and save. After the one regen, X no longer appears on the give side of an at-market card.
  9. Airplane mode, move two players at different positions, Save. An error shows and the moves stay on the page. Reconnect and Retry: both save, with no duplicate.
  10. Move a player, then swipe back. The "Discard your tier changes?" confirm appears. Discard leaves Tiers unchanged.
  11. VoiceOver on a chip: "Move to 1 1st" moves it.
  12. A 30+ player roster scrolls to the last tier and the picks strip; the pinned footer never covers a chip; the feedback button sits above the footer.
  13. Flag `trades.roster_tier_rank` off: Step 2 is the old per-position rank step again.
- [ ] **WAIVED — web client:** carried over from [scope.md](scope.md) §3 (signed 2026-11-10). The setup is mobile-only.
- `testID`s to add (must pass `mobile/scripts/testid-lint.sh`): `roster-setup.tiers.board`, `roster-setup.tiers.chip.<player_id>`, `roster-setup.tiers.header.<tier>`, `roster-setup.tiers.move.<tier>`, `roster-setup.tiers.save`, `roster-setup.tiers.retry`, `roster-setup.tiers.picks`. Template ids are added to `testid-lint-allow.txt`.

**Maestro delta / Simulator-gate tier: n/a per D-056.** These sections are no longer in this checkout's template; recorded here because the brief asked for them.

### §4 Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | at build | `POST /api/tiers/save`: `scope:'roster'` (scope = posted pids, merged-band rule, ungated, no completeness mark) and `via:'roster_setup'` |
| `living-memory/LLD.md` | at build | The scoped tier-save convention now has two scopes (`rookie` = server-derived set, `roster` = the posted ids), and both skip `tiers_saved` |
| `docs/architecture.md` | n/a because | No module wiring or data-flow change: an existing route reaches an existing writer through a new branch |
| `living-memory/HLD.md` | n/a because | No new module, client or major flow |
| `docs/cross-client-invariants.md` | at build | The tier-save `scope` and `via` enums are shared by backend and mobile `saveTiers` |
| `docs/glossary.md` | n/a because | No new domain term. "Tier", "placement" and "roster setup" already exist |
| ADR or `DECISIONS.md` entry | at build | **D-232** (next free ID; max is D-231): Step 2 = absolute tier placement through the merged-band writer, scope = posted ids, edge placement, per-position order dropped, picks read-only |
| `docs/config-reference.md` | at build | `trades.roster_tier_rank` row |
| `docs/plans/README.md` + [prd.md](prd.md) §5 / Q4 | at build | Status row, and a note that §5 is superseded by this file |
| `mobile/src/screens/CLAUDE.md`, `mobile/src/components/CLAUDE.md` | at build | `RosterSetupScreen` row; new `RosterTierBoard` row |

### §5 Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (with `check-roster-setup.js`) + `maestro-testid-lint`, on the pushed sha.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming `test_roster_tier_save.py` (with its sabotages), the structural suite, and the code-walk.
- **TestFlight verification:** the §3 checklist, run by the operator and logged in TEST_LEDGER.
- **Express lane declared by the operator?** No. It should not be: this changes an API contract (`/api/tiers/save` enums), adds a feature flag and an analytics event, so it is over the bright line regardless.

## 7. Operator decisions

**Decided 2026-11-11 (operator, in session):** "Tap him then tap the tier. Yes drop per position tap order. No need to show picks (other than the keep, move screen). Yes to on/off switch. Show market. At the edge."

| # | Decision |
|---|---|
| 1 | Tap players, then tap a tier. |
| 2 | The per-position tap-order pass is dropped from the new step. |
| 3 | **Picks are not shown on the tier page** (this differs from the recommendation below, which was a read-only strip). Picks stay on the Move / Keep step only. |
| 4 | New switch `trades.roster_tier_rank`; the old step stays behind it as the fallback. |
| 5 | Show the market tier on a chip when it differs from the tier the player sits in. |
| 6 | A moved player lands at the edge of the new tier. |

The operator was asked which screen "the draft pick tier ranker" meant (the Tiers board or the Pick Anchor wizard) and answered the six decisions without naming one; "tap him then tap the tier" matches the tier ladder this scope assumes. The table below is kept as the reasoning.


| # | Question | Recommendation | Why | If the other answer is picked |
|---|---|---|---|---|
| 1 | How does a player move: drag, or tap players then tap a tier? | **Tap, then tier.** | Same one-page tier view; 2 taps per move (fewer when batched); no drag across 2–3 screens; every part exists (`TierTargetChips`, Quick Set chips) | Drag: reuse the `TiersScreen` recipe. Roughly +300 lines and a no-drag path anyway for VoiceOver. Highest-risk option on a ~30-row list |
| 2 | Drop the "tap your players in order, one position at a time" pass? | **Drop it.** Tiers only. | Tier placement carries most of the signal; the order inside a tier is a weak engine input (§1.4); the old pass cost ~25 interactions; Quick Rank still exists on the Rank tab | Keep it as an optional pass after the tier page: the old step stays wired after Save (`rank` stage), and the done/analytics logic handles both |
| 3 | Picks on the page? | **Show them read-only, priced at market. Make picks placeable a separate project.** | The engine overwrites every board's pick values with consensus (`server.py:20773-20776`), so a placement would be stored and then ignored; placeable picks need storage plus engine changes (§1.5) | Leave picks off the page: smaller, but not "the entire team". Placeable now: adds a backend engine work item roughly the size of this whole change, with its own tests |
| 4 | New on/off switch so the old per-position step stays as a fallback? | **Yes, a new switch** (`trades.roster_tier_rank`). | Rollback without a deploy and without turning off Step 1; graduation then deletes the old step | Reuse `trades.roster_setup`: less code, but the only rollback is hiding the whole setup |
| 5 | Show each player's market tier next to him when it differs from his tier on the page? | **Yes, a small "mkt: 2nd" label.** | It makes "you value him above market" visible, which is the endowment the step exists to capture; the data is already loaded (values query `tier`) | No label: a cleaner chip, but the user is placing blind relative to market |
| 6 | Where in his new tier does a moved player land? | **At the edge** (bottom when moved up, top when moved down). | It is what the existing scoped writer does (no new math), matches the Tiers screen's step rule, and never respreads anyone else | Land at the tier's "label value" (e.g. a mid 1st for "1 1st", Elo 1650): a bigger value change per move, but it needs new placement code (or the per-player anchor lane, which ties every player in a tier at one value and has no FA rung). Note: with the edge rule, moving a player from the very top of "2nd" up to "1 1st" changes his value only slightly |
| — | Keep Move · — · Keep as its own first step? | **Yes** (unchanged). | Two controls per chip on one phone page would crowd it; the operator's comment was about the rank step | Merge both into one page: a redesign of Step 1 too, outside this scope |

## 8. Not determined from the code

- **Which screen the operator meant by "the draft pick tier ranker".** The Tiers board and the Pick Anchor wizard both use the same pick-value labels (`TIER_LABEL`; anchor rows are derived from it, `mobile/src/utils/anchorRows.ts`). This scope assumes the tier ladder. If the operator meant one player at a time ("worth how many firsts?"), that is the anchor lane: `POST /api/anchor/save`, one pin per player at a fixed rung (`server.py:1386-1396`, `:1598-1616`). It needs no API change, but it is per player, not one page.
- **How many players a typical user re-tiers.** No production data was read. The interaction counts in §1.3 assume about 6.
- **How dragging actually feels on a 30-row mixed list.** That is runtime-only, and it is why option (a) is ranked on risk rather than measured.
- **Whether the old rank step has any production completions.** No production read was made. That figure would show how much the fallback flag protects.
- **Whether the pick-value calibration will keep the bands identical across positions.** The `tier_config.json` note says they are identical by design. If they ever diverge, one heading set still works (headings are labels), but pre-fill and the edge placement become per-position, which they already are in the code path above.

## 9. Build notes (2026-11-11)

Built on `feat/roster-setup-tier-rank`; evidence in `living-memory/TEST_LEDGER.md` (2026-11-11), decision D-233.

**Differences from the text above**
- No picks on the page (operator decision 3). The `roster-setup.tiers.picks` id does not exist; a check asserts it is absent.
- `apply_tiers_subset` gained `empty_band_edge` (roster scope only): a lone mover into a band empty at his position lands at the edge he moved toward. Without it he took the band ceiling, which broke decision 6.
- Direction, the "back to his slot" rule and the "was <tier>" marker are judged against the save baseline (the tier the server holds), not the first layout. After a partial save the two differ.
- A back gesture during an in-flight save is held with no prompt; Save and Retry are ref-guarded.
- Added on the page: an "N selected · Clear" row; a `roster-setup.tiers.skip` id; an optional `testIDPrefix` on `TierTargetChips`.
- `_note_ranking_method` is skipped for the roster scope whatever `via` says.
- `mobile/tests/check-quickset-via.js` accepts the widened `via` whitelist and guard.

**Known limits**
- Two or more players moved up into one occupied tier in a single save are spread through its lower part; they do not all sit at the very bottom.
- Test 8 (the lifted player's card becomes `viewer_no_benefit`) covers owner-v1 only.
- Text contrast of the 11pt tier-colored micro-labels was not measured.
- Nothing was run on a device.

**Manual TestFlight checklist (replaces §6's list)**
1. Before starting, open Rank → Tiers and screenshot one position's board.
2. Pass a Find a Trade card. Step 1 is unchanged; tap Continue. One page, "Place your players", shows every QB/RB/WR/TE under eight headings, empty tiers included. No picks appear anywhere on it. Spot-check three players at different positions against Tiers.
3. Tap **Done** with nothing moved and no Step 1 changes. The done screen says nothing changed and the deck does not regenerate.
4. Move one RB up a tier. On the page he sits at the bottom of the new tier with "was <old tier>". Save. On Rank → Tiers → RB he is in the new tier at or near its bottom, and every other RB matches the screenshot.
5. Move one WR down a tier. He lands at the top of the lower tier on the page, and the same on Tiers after saving.
6. Select three players at different positions, tap one tier. All three move. Save. All three show that tier on Tiers. The done summary reads "3 re-tiered".
7. Move a player and then move him back to his starting tier. He returns to his original slot, the button reads Done, and Tiers is unchanged.
8. Note a card that gives away player X for a fair-looking return. Move X up two tiers and save. After the one regeneration, X no longer appears on the give side of an at-market card.
9. In airplane mode, move two players at different positions and Save. An error shows, the moves stay, and the button reads Retry. Reconnect and Retry: both save with no duplicate.
10. Move a player, then swipe back. "Discard your tier changes?" appears. Keep editing stays on the page; Discard leaves Tiers unchanged. Skip with unsaved moves asks the same question.
11. Tap Save and swipe back at once: the page stays until the save finishes, with no prompt.
12. VoiceOver on a chip: the "Move to 1 1st" action moves it.
13. Find a player whose market tier differs from his page tier: he shows "mkt: <tier>". Move him into his market tier: the label disappears.
14. A 30+ player roster scrolls to the FA section. The footer never covers a chip, including while the two-row "Move to" bar is showing. The feedback button sits above the footer.
15. With `trades.roster_tier_rank` off, Step 2 is the old per-position rank step again.
