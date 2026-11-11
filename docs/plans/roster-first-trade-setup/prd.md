# PRD — Roster-first setup for Find a Trade

**Date:** 2026-11-10 · **Status:** design approved by the operator 2026-11-10 (all six recommendations accepted); built behind `trades.roster_setup`, turned on 2026-11-10 by the operator before the TestFlight checklist ran · **Flag:** `trades.roster_setup` (new, default off)
**Companion files:** [scope.md](scope.md) · [analytics.md](analytics.md) · [reuse-map.md](reuse-map.md) · mockup [`mockups/roster-first-trade-setup/index.html`](../../../mockups/roster-first-trade-setup/index.html)

---

## Table of Contents
- [0. Open questions for the operator (answer before build)](#0-open-questions-for-the-operator-answer-before-build)
- [1. Why](#1-why)
- [2. The flow in one paragraph](#2-the-flow-in-one-paragraph)
- [3. Entry, return and re-prompt](#3-entry-return-and-re-prompt)
- [4. Step 1 — the roster toggle view](#4-step-1--the-roster-toggle-view)
- [5. Step 2 — rank my roster (inline Quick Rank)](#5-step-2--rank-my-roster-inline-quick-rank)
- [6. Step 3 — done, and the deck regenerates](#6-step-3--done-and-the-deck-regenerates)
- [7. Skip behaviour](#7-skip-behaviour)
- [8. Reused unchanged / changed / new](#8-reused-unchanged--changed--new)
- [9. Recommended cuts from v1](#9-recommended-cuts-from-v1)
- [10. Acceptance criteria](#10-acceptance-criteria)
- [11. Risks](#11-risks)

---

## 0. Open questions for the operator (answer before build)

**Decided 2026-11-10:** the operator accepted every recommendation below, and the web waiver in [scope.md](scope.md). Q1 and Q2 are recorded as D-212 and D-213 in `living-memory/DECISIONS.md`. The table is kept as the reasoning.

| # | Question | Recommendation | Why it matters |
|---|---|---|---|
| **Q1** | Should "want to move" be a **new per-player list**, or map onto an existing preference? | **A new list type, `trade_block`, in the existing `asset_preferences` table.** No new table or column. | Nothing today stores "I would move *this player*". `trade_away_positions` is per position, so mapping one RB to it makes every RB shoppable. `targets` is read only on the receive side, so it can't express this. Details in §4.3. |
| **Q2** | Should "want to keep" **reuse `untouchable`**, or become a softer new list? | **Reuse `untouchable`.** Add a guard when more than ~40% of the roster is marked Keep. | The engine already reads untouchables on every path. The meaning varies by arm: legacy and likes-you paths hard-exclude them (`server.py:9056`, `:9244`). Owner-v1 lets one go only for a market upgrade that includes a player at the same position (`trade_gen_owner.py:537-541`). A softer list would need new engine work and would give users two words for nearly the same thing. |
| **Q3** | Should league-mates be **nudged** to do the same? | **Not in v1. Measure first.** Every member who opens Find a Trade will see the step, and that alone raises counterparty board coverage as members join. A separate session should spec an invite or nudge to non-users. | The acceptance eval found that ~80% of suggested cards are against a counterparty with no board, and those are liked 17–23% of the time vs 46–65% with a board. That is the larger accuracy gap. The step only helps with it when the counterparty uses the app. |
| **Q4** | Is reordering enough, given that Quick Rank only **permutes** values? | **v1 ships ordering only and records the gap. Q4-b, an optional "top asset tier" question, is the v2 candidate.** | `apply_reorder` gives the reordered players the sorted multiset of their *own* current Elos (`ranking_service.py:2096-2142`). Ranking your roster can therefore change *which* of your players you value above market, but never raises the roster's *total*. The eval's "giving too much value" passes say users price their own players above market overall. Reordering can't capture that. Quick Set's tier placement can (`apply_tiers_subset`, `ranking_service.py:1927`), but it costs more interactions. |
| **Q5** | Should picks be **rankable** in the step? | **No in v1. Picks get Move/Keep only.** | Owned picks enter each trade job as pseudo-players. The viewer's board is set to the consensus price for every pick (`server.py:20638`, comment: "user board: consensus for picks"). A personal pick order would have nowhere to land without engine work. You named pick valuation as the app's strongest advantage, so this is worth its own item. |
| **Q6** | Should completion state live **on the device or on the server**? | **On the device (AsyncStorage), like Team Review's completion store.** The server data already says whether a user has preferences. | No server row records "has seen the setup". The `teamReviewCompletion` precedent (`mobile/src/state/CLAUDE.md`, `teamReviewCompletion.ts`) is device-keyed for the same reason. The cost: a reinstall or second device sees the step again, but pre-filled with saved tags, so it is one tap to dismiss. |

---

## 1. Why

The app's pitch is that it reads *your* team, not the market. But the inputs that make it personal are buried. Outlook, Chasing/Shopping positions, untouchables, targets and not-interested all live in the Trade DNA sheet (`mobile/src/components/TradeDnaSheet.tsx`) or behind a long-press on a card (`MatchesScreen.tsx:1966-1970`). Users meet them as filters, after they have already seen a market-value deck.

The 2026-11-10 acceptance eval (`docs/plans/realtime-trade-engine/acceptance-eval.md`, in the `trade-engine-rearch` worktree, uncommitted, not on main) found three things this step targets:

1. **Endowment, viewer side.** In 10 of 10 reasoned passes where the viewer gained at market, the reason given was "giving too much value". The figure was 28 of 29 where the viewer paid at market. Users price their own players above market. *(One account produced almost all of these, so treat it as a lead, not a finding.)*
2. **Unknown boards.** Like rate is 0.17–0.23 against counterparties with no board and 0.46–0.65 against counterparties with one. 80% of cards are the unknown kind.
3. **Sparse preference data.** Preference and pass-reason data comes from 2–3 people. Few users ever open the sheet.

The step asks every new Find a Trade user, once per league, the two questions the engine most needs answered: which of your assets are you willing to move, and how do you order the players you own? It asks right after the user's first pass on a Find a Trade card, when the user has just seen a suggestion that misread their team (operator call, 2026-11-10).

## 2. The flow in one paragraph

On the first pass of a Find a Trade card in a league, the user sees their whole roster grouped QB / RB / WR / TE / Picks. Every asset carries a three-state control: **Move · — · Keep**, defaulting to "—". Tapping writes immediately through the existing asset-prefs route. **Continue** opens an inline rank step: one position at a time, the user taps their own players in the order they value them, using Quick Rank's chip grammar. Each position saves through the existing subset-safe reorder route. The done state summarises what changed and hands back to the deck, which regenerates once with `force` through the existing onboarding regen bus. **Skip** is always one tap away and leaves the deck exactly as it would have been.

## 3. Entry, return and re-prompt

### 3.1 First pass per league (the only automatic entry)

**Trigger (operator change, 2026-11-10):** the user's **first declined (passed) Find a Trade suggestion** in the league. It is not the Trades tab opening or the first deck request. The pass is recorded exactly as it is today. If a pass-reason sheet opens, the push waits until it closes, so reason capture is never interrupted. The setup then pushes on top of the deck, which keeps its position underneath. Why: a pass is the moment the user has seen a suggestion that misread their team, so the ask lands with context and never sits in front of the first deck.

Show the step on that pass when **all** of these hold:

- `trades.roster_setup` is on.
- The league is not `league_demo`.
- The device's `rosterSetup` store has no record for this `leagueId` (§3.4).
- The user has a roster in this league. `findMyRoster` (owner or co-owner, `TradeDnaSheet.tsx:353-356`) returns at least one asset.

Saved preferences do **not** suppress the step. A user with three untouchables still sees it, pre-filled with those three as Keep. The step is a superset of what they have, so there is nothing to lose, and suppressing it would exclude exactly the users with partial data.

It renders as a **pushed screen in the Trades stack**, pushed from the deck surface where the pass happened. It is not a modal, so the deck stays mounted underneath and Skip returns the user to the next card with no reload. It is a tab-stack screen, so it does **not** mount its own `FeedbackFAB` (#188 rule).

### 3.2 Returning to it later (manual entry)

There are two entry points and no new tab:

1. **Trade DNA sheet**: a new row, "Your roster: N to move, N to keep · Edit". It goes in the `full` variant next to the existing untouchables summary (`TradeDnaSheet.tsx` "Off the table" block) and opens the same screen.
2. **TradesHome entry card**: the `TeamReviewEntryCard` pattern, collapsing, shown only after a skip (§7).

A manual entry opens on Step 1 with the saved states. The rank step is offered but never forced.

### 3.3 Roster changes re-prompt (light, not the full step)

The store records the asset IDs the user saw (players and pick IDs). On each TradesHome focus, the client compares the current roster with that snapshot:

- **New assets only** (a trade received, a draft pick made, a waiver add): show a TradesHome card, "3 new on your roster: set them", which opens Step 1 **filtered to the new assets**. Their rank step is offered only for positions that gained a player.
- **Assets only removed**: no prompt. The `asset_preferences` rows for departed assets go inert, because the engine only meets IDs on someone's roster. Leave them; they are harmless and come back to life if the asset returns.
- **A rookie draft completes**: the `draft_context` status flips to `drafted` (`server.py:21817-21826` already reads it). Draft picks become players, so this counts as "new assets".

This uses the same snooze grammar as `QuickSetPromptCard`: Not now → one re-offer in a later session → retired.

### 3.4 Device state (new)

`mobile/src/state/rosterSetup.ts`, modelled on `teamReviewCompletion.ts`, writes key `ftf_roster_setup_v1` with this shape:

```
{ [leagueId]: { status: 'done' | 'skipped', seenAssetIds: string[], at: ISO, rankedPositions: Position[] } }
```

It updates memory synchronously, persists by read-merge-write, and hydrates idempotently. The reason for this design is the one recorded for Team Review: the writer and reader sit in one stack.

## 4. Step 1 — the roster toggle view

### 4.1 Layout

- **Header:** "Your roster" (heading), the league name, and a one-line lede: "Tell us who's available. We'll build trades around it."
- **Counter strip**, pinned under the header: `4 MOVE · 6 KEEP · 21 OPEN`, in mono. It is a live summary, not interactive.
- **Sections in fixed order: QB, RB, WR, TE, Picks.** Players sort by the user's own board value, descending, and fall back to consensus when unranked. Picks sort by season, then round, then priced value (`load_draft_picks` order). Each section header shows the position color bar and a count.
- **Asset row:** name; team · age (or `2027 · 1st · via Bob` for picks, from `_owned_pick_label`); the tier chip color from `tierForElo`; and the three-state control on the right.
- **Footer**, pinned: primary **Continue** (ice), and secondary text button **Skip for now**. It reports its height through `setPinnedBottomBarHeight('roster_setup', h)`, exactly as Quick Set does.

### 4.2 The three states

The control is a three-segment toggle. The selected segment uses fill plus a glyph, never color alone. This follows the #360 R-15 rule in `TradeDnaSheet.tsx`: Move gets an arrow-out glyph, Keep a lock glyph, open a dash. The fills stay neutral (`ink3` with a `chalk.base` label). The only accents allowed are ice for actions and flare for highlights, so a red/green "sell/keep" coding is out.

| State | Label | Stored as | Route call |
|---|---|---|---|
| Move | `Move` | `asset_preferences.list_type = 'trade_block'` **(new value, Q1)** | `POST /api/league/asset-prefs {player_id, list:'trade_block'}` |
| Keep | `Keep` | `asset_preferences.list_type = 'untouchable'` (existing) | `POST /api/league/asset-prefs {player_id, list:'untouchable'}` |
| No opinion | `—` | no row | `POST /api/league/asset-prefs {player_id, list:'none'}` (existing delete) |

- **Single membership is already enforced.** `set_asset_preference` deletes any prior tag before inserting (`database.py:12804-12838`). Move ↔ Keep ↔ none therefore needs no client-side reconciliation. A stale `target` or `not_interested` tag on one of your own players (possible after a trade brought him to you) is replaced, which is correct.
- **Picks use the same route.** `asset_preferences.player_id` is an unvalidated `String`, and owned pick IDs (`draft_picks.pick_id`, prefixed `{league_id}_`) are stable across syncs (`server.py:20612-20620`). The engine's untouchable check already treats picks specially (`trade_gen_owner.py:537-540` exempts `PICK` from the same-position replacement rule). **Caveat:** only the top `picks_pool_cap` picks per owner enter the engine (`server.py:20547-20548`). A tag on a 2029 3rd beyond the cap is stored but inert. The row shows it greyed with "not in trade search" so the toggle never promises what it can't do.
- **Write timing: autosave on tap.** This copies the Trade DNA sheet's #236 machinery: in-flight requests are coalesced and the last write wins. Each call invalidates the league's cached deck (`server.py:28339-28341`), which is harmless because nothing regenerates until Step 3.
- **Keep guard.** When Keep exceeds 40% of non-pick assets, an inline note under the counter reads: "Keeping 14 of 27. Fewer trades will fit." It is information only and never blocks.
- **Position-level preferences are left alone.** The step does not write `trade_away_positions` or `acquire_positions`. Those stay in the DNA sheet. Deriving them from per-player tags would double-count, because the engine adds both (`trade_gen_owner.py:545-550`).

### 4.3 What the engine does with `trade_block` (new reads, Q1)

Today each list is read in these places, verified on `origin/main` `d6fc338f`:

| Input | Owner-v1 `trade_gen_owner.py` | Bilateral `trade_gen_bilateral.py` | Legacy / likes-you `server.py` |
|---|---|---|---|
| `untouchables` | hard reject unless returned at a market gain with a same-position player (537-541) | inherits owner `_owner` | hard filter (9056, 9244) |
| `targets` | +priority on **incoming** (549), +0.1 interest if `direction > 0` (586-587) | +0.3 declared if `direction > 0` (156-158); focal-in `declared` path (183) | — |
| `not_interested` | −priority incoming (550), −0.1 interest (587) | −0.3 declared (158) | hard filter (9060, 9246) |
| `acquire_positions` / `trade_away_positions` | ±priority both sides (545-548), ±0.1 interest (584-585) | ±0.15 declared (154-155); focal `declared` (184-185) | per-position bonus knobs (`database.py:3417-3418`) |
| **`trade_block` (proposed)** | **+priority on outgoing; +0.1 interest when `direction < 0`** | **+0.3 declared when `direction < 0`; `focal_out in trade_block` joins the `declared` path** | none in v1 (see §9) |

The proposal mirrors `targets` exactly on the give side. Both owner arms already carry the preference dict per team (`trade_gen_owner.py:397` copies the list keys into the evidence). The change is therefore one new key in four expressions plus the evidence tuple. All engine reads sit behind `trades.roster_setup`, the same way the job loader gates `avoid_positions` (`server.py:21860`). Persistence is never gated (the #360 rule: a kill switch must not destroy data).

Counterparties: `_owner_generation_context` loads every member's asset prefs (`server.py:21811-21812`, behind `trade.preference_lists`, which is on). A league-mate's `trade_block` therefore also raises the chance that their listed players appear on the receive side of *your* cards. This is the first per-player signal the counterparty side has had.

## 5. Step 2 — rank my roster (inline Quick Rank)

### 5.1 What it reuses

This is Quick Rank's chip grammar (`QuickRankScreen.tsx`). Every player renders as a chip, tapping stamps the next rank number, tapping again unclicks and renumbers, and unclicked players are appended in their current order on save. It writes through the same route, `POST /api/rankings/reorder {position, ordered_ids}` (`server.py:18096`).

**One deliberate difference: it walks positions, not tiers.** Quick Rank walks the tiers that hold 2+ players and posts only that tier's players, so a reorder never crosses a tier boundary. Roster-scoped, that would split a 7-RB room across 4–5 tiny tiers, which defeats "rank my roster". The step posts **the user's roster players at one position** instead. This is still safe:

- `apply_reorder` permutes the Elo multiset of exactly the posted IDs (`ranking_service.py:2096-2142`, subset-safe, pinned by `backend/tests/test_tier_occupancy.py::test_subset_reorder_within_tier_*`). Nobody outside the roster moves.
- Roster players *can* trade places across tiers. That is the user's stated intent ("my RB4 is better than my RB2"). Each pinned player becomes a placement (`_pin` → `placement_bands`), so `_ranking_confidence` marks him `explicit` (`server.py:11702-11749`). The owner engine then reads his value as **personal**, not `consensus_fallback` (`trade_gen_owner.py:282-293`, `_PERSONAL_SOURCES` at :42).

### 5.2 Steps and interaction count

- Positions are walked in the order QB, RB, WR, TE. A position with fewer than 2 roster players is skipped automatically, because there is nothing to order.
- Each position shows its chips. A **Save & next** button posts that position. **Done ranking** exits early from any position, with the earlier positions already saved.
- Taps on a typical 28-player dynasty roster (3 QB / 8 RB / 10 WR / 4 TE, plus picks, which are excluded under Q5): ordering N players needs at most N−1 taps, because the last is implied. That is 2 + 7 + 9 + 3 = **21 taps + 4 saves = 25 interactions**, about 60–90 seconds. The minimum is **1 tap** (Done ranking), and every partial order still saves.
- **Rookie scope does not apply.** No scope is sent. The route takes none (`mobile/src/api/rankings.ts:197-204`), and the ids are the scope.
- Sending `via:'quickrank'` would fire `quickrank_completed` and mix this step into the Quick Rank funnel (`server.py:18142-18155`). Send **no `via`**. The step's own analytics come from client events (analytics.md).

### 5.3 What the rank step does not do (Q4)

Because a reorder is a pure permutation, the roster's total value does not move. Ranking tells the engine which of the user's players they value above or below market *relative to each other*. That feeds the bilateral engine's per-player `direction` feature (`trade_gen_bilateral.py:83-95`). It does not tell the engine "I value all my players above market". That needs an absolute placement. Quick Set does this through `apply_tiers_subset` (`ranking_service.py:1927`), with the merged-band rule built for rookie scope and generalisable to any `scope_pids`. The v2 candidate is one question per position: "Where does your best RB sit?", answered with a tier chip. It would write a tier for that one player and anchor the rest of the order. Tracked as Q4.

## 6. Step 3 — done, and the deck regenerates

- **Summary card:** "4 to move · 6 to keep · 21 ranked" and a single line on what happens next: "Building trades from your roster." Primary button: **See trades**.
- **Regeneration reuses the onboarding bus.** On exit, call `setPendingQuicksetRegen` with the generalised source `'roster_setup'`. The bus already carries non-Quick-Set sources (`consumeGuidedRegenSource`, `TradesScreen.tsx:6232-6237`). TradesHome's focus effect then snapshots the old deck, forces a fresh job, and diffs what's new. No new regen path is needed.
- **Server side:** each asset-pref write and each reorder already invalidated the league's cached jobs (`server.py:28339-28341`, `:18124`). The forced job reads the new tags and the new placements.
- **Store write:** `{status:'done', seenAssetIds, rankedPositions}`.
- A user who changed nothing (all "—", no ranks) gets "Nothing changed. Your trades use consensus values." and the regen is skipped.

## 7. Skip behaviour

- **Skip on Step 1:** writes nothing new (any taps already made are kept, since they autosaved). Store `{status:'skipped'}`. Return to the deck at the next card. It stayed mounted underneath, so the skip costs no time. A collapsing **"Set up your roster"** entry card then appears on TradesHome (TeamReviewEntryCard pattern) with the snooze ladder from §3.3.
- **Skip on Step 2:** positions saved so far stay saved, and Step 3 runs normally. Skipping the rank step is not skipping the setup.
- **Back gesture** = Skip at the current step.
- The step never blocks the deck. If the asset-prefs or roster fetch fails, the screen shows the existing error grammar with "Skip to trades".

## 8. Reused unchanged / changed / new

| Piece | Status | Where |
|---|---|---|
| `asset_preferences` table | **reused, no schema change**; one new allowed value of `list_type` | `database.py:1809-1817` |
| `GET/POST /api/league/asset-prefs` | **changed**: accept `list:'trade_block'`; GET returns a `trade_block` key | `server.py:28278-28347`, `database.py:12739-12838` (`ASSET_PREF_LISTS`, both loaders' key maps) |
| `POST /api/rankings/reorder` | reused unchanged (no `via`) | `server.py:18096` |
| `GET /api/league/picks`, `getLeagueRosters`, `findMyRoster` | reused unchanged | `server.py:19920`, `mobile/src/api/sleeper` |
| Quick Rank chip grammar | **extracted** into a shared component (`RankChipGrid`) used by both `QuickRankScreen` and the new step. Pure extraction; Quick Rank's behaviour is unchanged | `QuickRankScreen.tsx` |
| Onboarding regen bus | reused; one new source string `'roster_setup'` | `mobile/src/state/onboardingBus.ts` |
| Owner / bilateral constructors | **changed**: read `trade_block` on the give side, flag-gated | §4.3 |
| Trade DNA sheet | **changed**: one "Your roster" row in the `full` variant | `TradeDnaSheet.tsx` |
| `RosterSetupScreen`, `rosterSetup.ts` store, `RosterSetupEntryCard` | **new** | `mobile/src/screens/`, `mobile/src/state/`, `mobile/src/components/` |
| Feature flag `trades.roster_setup` | **new**, default off | `config/features.json`, `backend/feature_flags.py` |
| New route? | **none in v1.** A batch `POST /api/league/asset-prefs/batch` is the v2 lever if per-tap writes prove slow | — |

## 9. Recommended cuts from v1

1. **Pick ranking** (Q5): Move/Keep on picks only.
2. **Absolute tier placement** (Q4): ordering only.
3. **`trade_block` in the legacy v2/v3 and likes-you paths**: owner arms only. Legacy has no soft give-side lever that matches. A hard "only offer these" filter would be wrong, because Move means "available", not "only these".
4. **League-mate nudge** (Q3): separate spec.
5. **Importing the platform trade block.** Sleeper has its own trade block. Importing it to pre-fill Move is attractive, but it is an integration item with its own provider risk.
6. **Web client**: mobile only. The web Trades page has no Trade DNA sheet parity today.
7. **Server-side completion state** (Q6).

## 10. Acceptance criteria

Flag **off**:
- AC-0. Every existing path is byte-identical. No screen, entry card or DNA row renders, and the engine ignores any `trade_block` rows. The asset-prefs route still accepts and returns `trade_block` (persistence is never gated).

Flag **on**:
- AC-1. The first pass on a Find a Trade card in a non-demo league with a roster pushes the setup screen, after the pass is recorded and after any pass-reason sheet closes. Opening the Trades tab or loading the first deck never pushes it. The deck underneath keeps its position.
- AC-2. Every rostered player and every owned pick appears exactly once, grouped QB/RB/WR/TE/Picks, with saved tags pre-filled (`untouchable` → Keep, `trade_block` → Move, anything else → —).
- AC-3. Each tap issues exactly one `POST /api/league/asset-prefs` (coalesced while in flight). The final stored state equals the last tap. Reopening the screen shows the stored state.
- AC-4. Picks beyond `picks_pool_cap` render greyed with "not in trade search". Their toggle still saves.
- AC-5. The rank step posts one `/api/rankings/reorder` per saved position, containing only that position's roster player IDs, with no `via`. A player not on the roster never changes Elo (pytest: board diff before and after equals the roster subset).
- AC-6. After a position is saved, every posted player resolves to source `explicit` in the next owner job's `user_sources`.
- AC-7. With a `trade_block` player and the flag on, the owner and bilateral constructors raise that player's give-side interest and count him as `declared` intent. With the flag off, card output is byte-identical (pytest, both arms).
- AC-8. Exiting through Done forces exactly one deck regeneration. Exiting with no changes forces none.
- AC-9. Skip at any point returns to the deck at the next card with no reload, stores `skipped`, and shows the entry card on TradesHome.
- AC-10. A roster that gains assets after completion shows the "N new on your roster" card. Opening it lists only the new assets. A roster that only lost assets shows nothing.
- AC-11. The analytics events in analytics.md fire with exactly the specced props. They are registered in `analytics_taxonomy.py` and classified in `analytics_queries.NON_INTENT_EVENTS` **in the same commit as the emitters**.
- AC-12. There is no `FeedbackFAB` mount in the new screen (tab stack), and the pinned footer reports its height.

## 11. Risks

- **Keep starvation.** Owner-v1 already allows an untouchable out for a same-position upgrade, but legacy paths hard-exclude untouchables. A user who keeps everything gets an empty deck on legacy arms. The 40% guard is the mitigation, and the summary line names the cause.
- **Write storm.** A 30-asset roster can produce 30 POSTs, each invalidating the job cache. The per-league invalidation is cheap, but the batch route is the lever if it shows in latency.
- **Selection bias in the next eval.** Users who complete the step are likely the engaged ones. The analytics spec stamps `roster_setup` completion so the eval can stratify by it rather than read the lift naively.
- **Mockup vs reality.** The mockup's toggle and rank frames are reconstructions. The only embedded captures are `trades/populated.png` and `quick-rank/step--clicked.png` from the 2026-08-11 freeze, and both screens have changed since (mockup page says which files).
