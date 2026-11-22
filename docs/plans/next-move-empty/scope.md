# Feature Scope — Home's next move when there is no move

**Date:** 2026-11-21
**Entry point:** direct ask (operator, 2026-11-21, through the main session). Told that no row "is expected when the forecast has no clear move for that team", the operator said: "It should have content for the expected move too".
**Builder:** builder subagent on `feat/next-move-empty` (D-279). Builds on [Home's next move](../home-next-move/scope.md) (D-278, build 199).
**Operator sign-off on waivers:** NEEDED. The waivers, plainly:
1. No analytics event for the no-move row (§1 (c)): nothing records that it was shown, and it cannot be tapped.
2. Two copy lines from the brief were reworded because, as written, they were false whenever they would show (§7 note): `keep` and the sell `below_threshold` line.
3. A buy whose seller has no live owner (or whose team is gone from the live rosters) also gets "No move to suggest right now". The brief named only "the seller no longer holds him"; the app's existing buy check also needs a live owner, so a failed check of either part is treated the same.

---

## What the user sees

New app flag **`league.next_move_empty`** (code default false, shipped true). With it and `league.next_move` on, Home's next-move row (directly under the playoff card) also shows when there is no move: the same card, the label "Next move", one line, no "Find trades ›", not tappable.

| The server's `next_move` block | Row |
|---|---|
| `ready`, the live-roster check passes | the move, exactly as build 199 (D-278) |
| `ready`, the live rosters loaded and the check fails (sell: the player is no longer on your roster; buy: he is no longer on that team, or that team has no live owner) | "No move to suggest right now" |
| `ready`, the live rosters still loading or failed to load | nothing (as build 199) |
| `none` / `keep` | "Hold: your top sale is a player you marked Keep" |
| `none` / `below_threshold`, direction `draft_pick` | "Hold: your top sale does not move your projected pick enough" |
| `none` / `below_threshold`, direction `playoffs` | "Hold: no single buy moves your playoff chance enough" |
| `none` / `settled`, `playoff_proof.playoff_clinched` | "Playoffs clinched: no move to suggest" |
| `none` / `settled`, `playoff_proof.playoff_eliminated` | "Eliminated from the playoffs: no buy to suggest" |
| `none` / `pick_owned_elsewhere` | "No sale to suggest: another team owns your first-round pick" |
| `none` / `no_moves`, `no_targets`, `collapsed`, `no_direction`, `not_offered` | "No move to suggest right now" |
| `none` / `direction_off`, `unavailable`, `read_failed`, any other reason; `settled` without a proof (or both true); `below_threshold` without a direction; an unknown version or state; no block | nothing (the playoff card above already carries the state) |

With `league.next_move_empty` off, Home is exactly build 199. With `league.next_move` off, nothing shows whatever the new flag says (the server sends no block).

## The rule: the server decides, the app shows

The line is a lookup of what the block says (`reason`, `direction`, and for `settled` its `playoff_proof`); the app re-derives no forecast rule. The one server change: a `settled` none block now carries `playoff_proof` (`{playoff_clinched, playoff_eliminated}`, the served block baseline's, D-262) instead of null, so the app can say clinched or eliminated without deciding it. Additive: build 199 ignores every none block (`honouredBlock` honours only `ready`), so `version` stays 1. Nothing else the server computes changes: the same reasons in the same order, the same `ready` blocks.

### What `keep` and `passes_threshold` mean (read from the code)

- **`keep`** (`backend/league_projections/maxpf_moves.py:599-608`): the row's player is in the viewer's untouchables, the players the user marked Keep. Max PF moves rows are ranked by the largest max PF drop (`:390-391`), not by the pick. So a `keep` answer means the biggest max PF drop is a Keep player; rows below it may still be usable sales.
- **Sell `passes_threshold`** (`maxpf_moves.py:299-306`, settings in `config/league_projections.json`): the max PF drop is at least `min_drop_points` (5) AND (the pick if you miss improves by at least `min_pick_change` (0.1) OR the top-3 chance rises by at least `min_top3_change` (2 points)). The list's own copy for a row that fails it is "does not move your projected pick by a visible amount" (`C-NO-MOVES`, `C-NONE-ALONE`).
- **Sell block state** (`maxpf_moves.py:629`): `ready` only when some row passes. The composer reaches `below_threshold` only on a `ready` block (`next_move.py` `_sell`), so whenever the sell `below_threshold` line would show, some lower row DOES pass.
- **Buy `passes_threshold`** (`backend/league_projections/playoff_targets.py:267`): the playoff chance rises by at least `min_playoff_gain` (2 points). Rows are ranked by that rise, largest first (`:269-270`), and the read's seller filter keeps the order. So if the first served row fails, every row fails, and the block state is `no_targets` (`:349`), not `ready`: a buy `below_threshold` is effectively unreachable (defensive), and the line is true if it ever shows.

### §7 note: the two reworded lines

| Reason | Brief's line | Why it is false | Line built |
|---|---|---|---|
| `keep` | "Hold: no sale improves your projected pick" | The first row is a Keep player; rows below it can pass the threshold and show "Find trades" on Improve Draft Pick | "Hold: your top sale is a player you marked Keep" |
| sell `below_threshold` | "Hold: no sale moves your projected pick enough" | Reached only on a `ready` block, which means some lower row does pass | "Hold: your top sale does not move your projected pick enough" |

Every other line is true as written (the two `settled` lines are defensive: a clinched team's Max PF list is `no_miss` (`maxpf_moves.py` `compose`) and its targets list is `clinched` (`playoff_targets.py:327`), so `team_direction` offers neither direction and the answer is `no_direction`; an eliminated team gets the draft pick, a sell, if anything): `settled` sell is clinched only (`_sell`), `settled` buy is clinched or eliminated (`_buy`), and the proof says which; `pick_owned_elsewhere` is the configured round, which is 1 (`config/league_projections.json` `draft_round`); the catch-all is true for the rest. Note `pick_owned_elsewhere` is rare in practice: the card does not offer the draft pick when another team owns it, so this reason needs a block whose `owns_own_pick` is not `true` but not `false` either.

## 1. Analytics scope

- [x] **(c) WAIVED (operator sign-off NEEDED): no event for the no-move row.** It cannot be tapped, so there is no tap to log, and there is no impression event (as D-278's row, whose impression waiver was signed off). Whether a team saw "no move" cannot be counted. `direction_card_shown` still fires for the card. A `next_move_shown {state, reason}` event is a small follow-up if the operator wants it.

## 2. Schema & flag scope

- New/changed tables or columns: none. Nothing saved; the weekly job is unchanged.
- New feature flag: **`league.next_move_empty`**. Code default False (`backend/feature_flags.py` `FLAG_KEYS`); shipped **true** in `config/features.json` (with `_comment_league_next_move_empty`); mirrored in the three flag fixtures (`release`, `onboarding-v2`, `profiles-on`) and the mobile compiled defaults (`state/useFeatureFlags.ts`), as `league.next_move` was. App-only: no backend code reads it. Requires `league.next_move`. Not in `FTF_FLAGS`.
- Rollback: `league.next_move_empty` false + `POST /api/feature-flags/reload`; no build needed. Graduation: after one TestFlight cycle with the §9 checklist passed.
- New env vars / `model_config` keys: none. No setting in `config/league_projections.json` changed. No existing flag value changed.

## 3. The block (contract change)

The `next_move` block on `GET /api/leagues/<id>/projection-runs/latest` (D-278 §3) is unchanged except: when `state` is `none` and `reason` is `settled`, `playoff_proof` is `{playoff_clinched, playoff_eliminated}` (the served block baseline's). Every other `none` block keeps `playoff_proof` null; every field after `direction` other than `playoff_proof` stays null. Served with or without the new flag; `version` stays 1.

## 4. Where it renders

- `mobile/src/components/home/HomeNextMove.tsx`: when `nextMoveView` gives nothing, `utils/homeNextMove.nextMoveEmptyView` may give a no-move view; the component renders it as a `View` (not a `Pressable`) with the card's styles, `testID="home.next-move"`, `accessible`, `accessibilityLabel` "Next move. {line}.", the label, and the line (`testID="home.next-move.none"`). No `RowAction`, no `onPress`, no role. Same cached read and rosters as the move row; no new request. `HomeHub` is unchanged.
- "Rosters loaded" is the shared `['league-rosters', leagueId]` query having data. A sell also needs the viewer's own live roster found in it (otherwise hidden, as if loading).

## 5. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-home-next-move.js` (`npm run test:home-next-move`) gains J to M: every reason → its line or hidden (including unknown reasons, prototype keys, `settled` without a proof, unknown version or state); either flag off ⇒ nothing; a ready move failing the live check once loaded ⇒ "No move to suggest right now" (player sold, player left the seller, no live owner, team gone); loading or failed rosters ⇒ hidden; the a11y label; the component renders one non-tappable row (no `Pressable`, `RowAction` or `onPress`) with the move row's styles; with the new flag off every render equals the build 199 component loaded from git at `469c84ab` (and the same query); the no-move copy table equals §7 both ways; the flag mirrors; `HomeHub` untouched. The build 199 H section now runs with the new flag off.
- [x] **Unit tests:** `backend/tests/test_next_move.py` (`settled` carries the proof, both sides; every other none answer keeps it null); `backend/tests/test_next_move_read.py` (the new flag's registration, shipping, fixtures, flags endpoint, not env-forced, client default, no backend reader).
- [x] **Code-walk proof:** the server change is `backend/league_projections/next_move.py` `_none(..., playoff_proof)` and the two `settled` returns in `_sell` / `_buy`; the app's lookup is `mobile/src/utils/homeNextMove.ts` `noneLineId` / `nextMoveEmptyView`; the render branch is `HomeNextMove.tsx` (`if (!view)`), reached only when the build 199 path returns nothing.
- [x] **Manual TestFlight checklist:** §9.
- `testID`s added: `home.next-move.none` (the line). `home.next-move` stays on the container. `mobile/scripts/testid-lint.sh` checks flows only (no list to update).

## 6. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | the `next_move` block: `playoff_proof` on `settled` |
| `docs/config-reference.md` | updated | the flag table and the "Home's next move" paragraph |
| `living-memory/LLD.md` | n/a | no convention shift |
| `docs/architecture.md` | updated | the "Home's next move" paragraph |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | no shared constant; the web app does not read the block |
| `docs/glossary.md` | n/a | no new term |
| `DECISIONS.md` | updated | D-279 |
| `CLAUDE.md` index files | updated | `mobile/src/components/CLAUDE.md`, `mobile/src/utils/CLAUDE.md`, `mobile/tests/README.md` |

## 6a. Ship gate declaration

- CI green: `backend-tests`, `mobile-typecheck`, testid-lint, on the pushed sha.
- Evidence recorded in `living-memory/TEST_LEDGER.md` (2026-11-21 entry).
- TestFlight verification: the §9 checklist, by the operator.
- Express lane: no.

## 7. Every new string

All user-facing; source `mobile/src/utils/homeNextMoveCopy.ts` `NEXT_MOVE_NONE_COPY`. The label is build 199's `NM-LABEL` ("Next move"). `{line}` is the row's line.

| Id | String |
|---|---|
| `NM-NONE.keep` | Hold: your top sale is a player you marked Keep |
| `NM-NONE.sell-threshold` | Hold: your top sale does not move your projected pick enough |
| `NM-NONE.buy-threshold` | Hold: no single buy moves your playoff chance enough |
| `NM-NONE.clinched` | Playoffs clinched: no move to suggest |
| `NM-NONE.eliminated` | Eliminated from the playoffs: no buy to suggest |
| `NM-NONE.pick-elsewhere` | No sale to suggest: another team owns your first-round pick |
| `NM-NONE.none` | No move to suggest right now |
| `NM-A11Y.none` | Next move. {line}. |

## 8. What is not built

| Item | Why |
|---|---|
| A tap or link on the no-move row | The ask is content, not an action; the card's "View ›" already opens both Improve pages |
| An event for the no-move row | Waived (§1), sign-off needed |
| A line for `direction_off`, `unavailable`, `read_failed`, unknown reasons | The playoff card above already says why there is no forecast |
| A version bump | Build 199 ignores none blocks, so the added proof cannot change it |
| Any change to which reason the server gives, or to `ready` blocks | The brief |
| The row on League rankings | The ask is Home |

## 9. Manual TestFlight checklist

Needs the app build with this change and the server deployed. A Sleeper league with a current forecast. Both flags on (shipped).

1. A team with a suggested move: the row is exactly as build 199 ("Next move", the line, "Find trades ›"); a tap opens Find a Trade.
2. Mark the suggested sell player Keep on Improve Draft Pick (Rebuilding outlook, own pick): the row now reads "Hold: your top sale is a player you marked Keep", with no "Find trades ›"; tapping it does nothing.
3. A Contending team at over 45% whose card leads with the draft pick (the playoffs not offered): "No move to suggest right now".
4. A clinched team: "No move to suggest right now" (the card offers neither direction, so the server says `no_direction`). The two `settled` lines are defensive and not expected on a device: a clinched team's Max PF list is `no_miss` and its targets list is `clinched`, so neither direction is offered, and an eliminated team is offered the draft pick (a sell), not a buy.
5. Trade away the suggested sell player on Sleeper, pull to refresh Home: the row reads "No move to suggest right now" (not the next player).
6. Turn on airplane mode, kill and reopen the app on Home: while rosters cannot load, no row (no line, no gap change from build 199).
7. VoiceOver on the no-move row: it reads "Next move. <line>." once, and is not announced as a button.
8. An ESPN or MFL league: no row.

Flag off (`league.next_move_empty` false + reload, then pull to refresh):

9. Steps 2 to 5 show no row at all, as build 199; step 1 is unchanged.
