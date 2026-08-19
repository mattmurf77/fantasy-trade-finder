# Feature Scope — current-year picks read as their real draft slot

**Date:** 2026-08-19
**Entry point:** direct operator report, 2026-08-19 14:42 UTC, severity POLISH, screen TradesHome, app v1.15.0 — *"For 2026 picks, we should present them as actual draft pick slot rather than a generic 2026 round pick"*
**Builder:** session agent, branch `feat/pick-slot-labels` (worktree off `origin/main` @ `7462c23`)
**Operator sign-off on waivers:** **needed** — two waivers below (§1c analytics, §3 no structural mobile suite), plus one decision that narrows a standing operator position (§6).

---

## 0. The finding, first

**The current year's slot IS resolvable, and it costs no new upstream call.**

A pick's slot is not new information. `draft_picks`' grain is `(league, season, round, original_roster)`, and a slot is that original roster's position in the draft order — the ORDER composed with a column we already store. Two places already hold the order:

| Source | Where | Cost |
|---|---|---|
| Sleeper `draft_order` (user_id → slot) | rides the **`GET /v1/league/<id>/drafts`** payload that `server._sync_sleeper_owned_picks` already fetches for the #228 exclusion, composed with the `roster_id → user_id` map that same function already holds | **zero** additional calls |
| User-assigned (ESPN) order | `leagues.pick_assignment_settings.order`, already persisted by the `picks.assign` grid | **zero** — no network at all |

Verified against live data 2026-08-19: for the operator's league `1312140920132497408` the composition reproduces Sleeper's own `slot_to_roster_id` **exactly** (12/12 rosters), and the operator's own 2026 1st resolves to **1.08**.

**MFL is not supported.** Its order lives in `round1DraftOrder` inside an authed `TYPE=draftResults` fetch that nothing on the label path makes; buying a new upstream call for a label is the wrong trade. An MFL league keeps the generic label, and says so by simply not changing.

### Sizing, from prod (read-only, `SET TRANSACTION READ ONLY`, SELECT only, 2026-08-19)

| | |
|---|---|
| Deck impressions carrying an asset list | 2,651 (of 8,387 total rows) |
| Cards containing ≥1 pick | 1,459 — **55.0 %** |
| Cards containing ≥1 **current-year (2026)** pick | **469 — 17.7 % of served cards** |
| Pick mentions by season | 2026: 565 · 2027: 607 · 2028: 513 · 2029: 418 |
| Leagues holding 2026 picks | **3 of 12** — and all three are `draft_status = not_drafted` |
| 2026-pick cards by league | operator's `1312140920132497408`: **451** · ESPN `11896`: 18 |

**Read honestly:** current-year picks are *not* rare in real decks — better than one served card in six carries one — but they are heavily concentrated in the operator's own league, because it is one of only three leagues whose 2026 draft has not happened. #228 deletes a season's rows once its draft completes, which is exactly why the other nine leagues have no 2026 picks at all. The change is worth making and its blast radius today is small; both statements are true.

---

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** nothing about a user's behaviour changes shape. This alters the *text* of a label already served on five existing payloads; there is no new surface, no new interaction, no new decision point, and no funnel step to count. Adding an event would measure "the server formatted a string", which answers no question anyone has. No existing event carries a pick label as a property, so none needs re-speccing either.

## 2. Schema & flag scope

- **New/changed columns:** `leagues.draft_slot_order` (TEXT, JSON, nullable) via the additive-column seam in `database._ADDITIVE_COLUMNS`. → `docs/data-dictionary.md` updated. **No backfill and none needed**: NULL is the pre-existing state of every row and reads as "unresolved", which produces today's label exactly.
  - **Why store the ORDER and never the SLOT.** Same rule `pick_assignment_settings` follows (D18): a commissioner reordering the draft must renumber every slot without touching a single owner. A denormalized `draft_picks.slot` would go stale on every reorder and the grain cannot express it. Storing the order keeps renumbering free.
- **New/changed feature flags:** `picks.slot_labels` → `config/features.json` (+ its `_comment_pick_slot_labels`), `backend/feature_flags.py` `FLAG_KEYS`, `docs/config-reference.md`, and the three key-equal test fixtures (`release.json`, `onboarding-v2.json`, `profiles-on.json`).
  - **Default state: ON**, matching its two nearest siblings `picks.owned_sync` and `picks.rank_year_labels` — both display-label flags on the same payloads, both shipped ON. **Stated plainly: under D-056 this ships with no runtime proof beyond the manual checklist in §3.** If the operator prefers OFF-then-flip, the only change needed is the one boolean in `config/features.json`; nothing else in the diff depends on the default.
  - **Graduation criterion:** the operator runs the §3 TestFlight checklist and confirms a 2026 pick on TradesHome reads `2026 1.08` and a 2027 pick still reads `2027 1st`.
  - **Kill value:** `false` ⇒ every owned-pick label is the pre-D-090 string **byte-for-byte** at all five sites, and `load_draft_slot_order` is never called (`_league_slot_order` short-circuits before the read — pinned by `test_flag_off_never_reads_the_order`). The column keeps being written while the flag is off, so flipping back on needs no re-sync.
- **New env vars / `model_config` keys:** none. The deploy-free lever is the flag itself (`POST /api/feature-flags/reload`).

## 3. Evidence scope

- [x] **Unit tests:** `backend/tests/test_pick_slot_labels.py` — **28 tests**, all new. Each of the two named sabotages has a trap that fails on it:
  - **S1 "a slot invented where none exists."** Sleeper's pre-draft payload returns `slot_to_roster_id = {"1":1 … "12":12}` — an identity map that reads as a real order and is not one (the D5 rule in `draft_board_service`). `test_identity_slot_to_roster_is_never_read` hands the resolver that perfect identity map alongside a NULL `draft_order` and demands `None`. The fixture's real order is deliberately **not** the identity (roster 1 drafts 8th), so anything that fell back to the roster id would label `1.01` and fail every `1.08` assertion.
  - **S2 "a slot on a season that has no order."** `test_future_season_never_resolves_a_slot` pins `None` for 2027/2028/2029 (and 2025), and `test_future_year_keeps_its_round_ordinal` pins the literal strings `"2027 1st"` / `"2029 3rd"`.
  - Plus: `test_no_price_moves_with_or_without_an_order` (the bright line), `test_route_is_byte_identical_with_the_flag_off` (the kill-switch contract, literal label map), `test_snake_with_reversal_round_refuses_rather_than_guesses`, `test_order_lookup_is_cached_per_league`, `test_a_failing_lookup_degrades_to_generic_labels`, `test_label_never_contains_the_package_separator`.
- [x] **Code-walk proof:** below, §7. The label reaches five payloads; the trace cites each by file:line and states what the client does with it.
- [x] **Manual TestFlight checklist:** §8.
- [x] **WAIVED — no `mobile/tests/check-*.js` structural suite, because:** the mobile diff is **empty**. Every surface renders the server's `label`/`name` string verbatim (`InLeagueCalculator.tsx:219` `name: p.label`; `LeagueSummaryScreen.tsx:2148` `{p.label}`; `MatchesScreen.tsx:1408/1414/1440/1446`; `TradesScreen.tsx` deck cards read `give_players[].name`). There is no client-side derivation of an owned-pick label anywhere to pin. The client-side `{round}.{slot}` formatters that do exist (`PickAssignmentScreen`, `DraftRows`, `MockDraftScreen`, `RecordPicksScreen`) are the **draft-board** family and are untouched — this change deliberately makes the server's owned-pick label agree with them rather than adding a sixth copy.
- **`testID`s added/renamed:** none — no new interactive element, no component change.

## 4. Docs scope (MANDATORY)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `GET /api/league/picks` — the `label` slot form, the four sibling payloads it applies to, and the explicit "no VALUE changes" statement. No route added, renamed or removed; no request contract changed. |
| `living-memory/LLD.md` | **updated** | New convention: the order is stored on the league, the slot is derived at read time and never persisted. |
| `docs/architecture.md` | **n/a** | No module wiring or data flow changed. `backend/pick_slots.py` is a leaf, dependency-free helper (no Flask, no `database`, no HTTP) called from one existing function; nothing new fetches, and no request path gained an upstream call. |
| `living-memory/HLD.md` | **n/a** | Same reason — a display helper is not an architecture shift. |
| `docs/cross-client-invariants.md` | **n/a** | No shared constant, enum, colour or tier band moved. The label is already documented there as the shared display string, and its *contract* (server owns it, clients render it) is unchanged — only the string's content varies, exactly as `is_traded` already varies it. |
| `docs/glossary.md` | **updated** | New term **Pick slot label**, cross-referenced against **Order confidence** and **Contested slot**. |
| `DECISIONS.md` entry | **updated** | **D-090** (reserved). Records the design and, explicitly, the narrowing of the 2026-07-18 position — see §6. |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` — see `living-memory/TEST_LEDGER.md`. `tsc --noEmit` and `testid-lint` not applicable to the diff (zero mobile files touched) but run anyway and reported.
- **Evidence recorded:** TEST_LEDGER entry naming the 28 new tests, the two sabotages they trap, and the prod sizing.
- **TestFlight verification:** §8 checklist, operator-run, outcome to be logged in TEST_LEDGER.
- **Express lane declared by the operator?** No — full gates.

---

## 6. The standing decision this narrows (operator attention)

`pick_values.pick_pool_value`'s docstring records an **operator decision dated 2026-07-18**: a league pick is priced at the generic ladder's Mid rung of its round *"(operator decision 2026-07-18 — we can't yet resolve a pick's slot)"*.

**That decision is not overturned, and this change does not touch pricing. But its stated premise is now false for the current year, and the docstring should say so.**

- What was true: on 2026-07-18 nothing in the codebase resolved a pick's slot.
- What is true now: the current season's slot is resolvable for Sleeper and for user-assigned ESPN boards, at zero upstream cost. It is still **not** resolvable for any future season (there is no order to read) or for MFL.
- What has *not* changed: the **decision itself** — pricing every pick of a round at the Mid rung. This change deliberately leaves it exactly as it stands, because pricing by slot is a cross-client-invariant move on a bright line and cannot ride a polish item.

Recorded as **D-090**, and the pricing half is logged as **Q-023**.

### What pricing by slot would actually do — measured, not built

DynastyProcess's published 2026 slot curve (`backend/tests/fixtures/dp_values_picks_2026-08-06.csv`, `1qb_ppr`), against the shipped ladder's `pick_pool_value(1, 0) = 2117.0`:

| slot | value | vs ladder | slot | value | vs ladder |
|---|---|---|---|---|---|
| 1.01 | 4867 | **+130 %** | 1.07 | 1680 | −21 % |
| 1.02 | 4025 | +90 % | 1.08 | 1436 | −32 % |
| 1.03 | 3343 | +58 % | 1.09 | 1235 | −42 % |
| 1.04 | 2793 | +32 % | 1.10 | 1070 | −49 % |
| 1.05 | 2343 | +11 % | 1.11 | 934 | −56 % |
| 1.06 | 1979 | −7 % | 1.12 | 821 | **−61 %** |

A 1.01 is worth **5.9×** a 1.12 on the market curve; our ladder prices them identically. On the operator's own league that is not a rounding difference:

- **48 of 48** current-year picks would change price.
- **38 of 48** would change **tier badge** — a 1.12 would badge `second`, not `first_1`, and a 1.01 would badge `firsts_2`.

Repricing 38 badges and every current-year pick's engine value is a pricing decision on a cross-client invariant. **It is the operator's call, separately, on evidence — not a side effect of a label fix.** Q-023.

---

## 7. Code-walk proof

**The resolver.** `backend/pick_slots.py` is dependency-free (no Flask, no `database`, no HTTP) and has two builders and two readers.

- `order_from_sleeper_drafts(drafts, roster_id_to_user, season, teams)` (`pick_slots.py:106`) inverts `roster_id_to_user` to `user_to_roster` (`:127`), finds the draft whose `season` matches (`:135`), and **returns `None` the moment `draft_order` is falsy** (`:137-139`) — that is the D5 refusal, and `slot_to_roster_id` is never referenced anywhere in the module. Composition is `draft_order[user] → user_to_roster[user] → slots[roster] = slot` (`:145-151`).
- `order_from_assignment_settings(settings, season, user_to_roster)` (`:162`) maps `order` index + 1 to a slot (`:182-186`).
- `slot_for(order, season, round_, original_roster_id)` (`:199`) refuses on schema mismatch (`:213`), on a season that is not the stamped one (`:215-216` — #273), on an unknown roster (`:223-224`), on a slot wider than the league (`:227-228`), and on a snake with `reversal_round` set (`:230-232`). Snake's even-round reversal is `teams + 1 - base` (`:236`) — **the same arithmetic as `PickAssignmentScreen.draftPosition`** (`mobile/src/screens/PickAssignmentScreen.tsx:162-171`), so the picks screen and a trade card can never disagree about the same pick.
- `slot_suffix(round_, slot)` (`:240`) is `f"{round}.{slot:02d}"`, matching `PickAssignmentScreen.slotLabel:174`, `DraftRows.slotLabel:62` and `data_loader.pick_slot_label:635`.

**Where the order is written.** `server._sync_sleeper_owned_picks` already fetched `_fetch_sleeper_drafts(league_id)` for the #228 completion check; that call is now bound to `_drafts` and reused. The resolve-and-persist block sits immediately after the #228 loop, writes `None` when the season is excluded (so a completed draft cannot leave a stale order behind), and is wrapped so a failure logs and continues. **Zero new upstream calls.**

**Where it is read.** `_league_slot_order(league_id)` returns `None` immediately for the demo league, an empty id, or a disabled flag — **before** any DB read — then reads `load_draft_slot_order`, falls back to `_assigned_slot_order` (the ESPN path), and caches for 300 s under a lock. Every failure path returns `None`, which is the generic label.

**The label.** `server._owned_pick_label(p, slot_order=None)` is the **one** formatter for an owned pick. It asks `pick_slots.slot_for` for a slot and uses `slot_suffix` when it gets one, `_PICK_ORDINALS` when it does not. The second parameter defaults to `None`, so any caller that does not pass it is byte-identical to the pre-D-090 function. The `(from …)` suffix is untouched and rides on top of either form.

**The five payloads it reaches**, each resolving the order once per league and passing it down:

| # | Call site | Route / consumer | Wire field | Client |
|---|---|---|---|---|
| 1 | `_roster_eveners` | `POST /api/trade/evaluate` | `eveners[].name` | `EvenerRows.tsx`; `TradesScreen.tsx:3804` splits a package name on `' + '` — a slot label introduces no second separator (`test_label_never_contains_the_package_separator`) |
| 2 | `get_league_picks` | `GET /api/league/picks` | `my_picks[].label`, `all_picks[].label` | picks screen + `InLeagueCalculator.tsx:219` (`name: p.label`) — the only consumer of `getLeaguePicks` |
| 3 | `_pick_labels_by_id` | `/api/trades/matches`, `/matches/all`, `/awaiting`, the disposition route | `my_give_names[]`, `my_receive_names[]` | `MatchesScreen.tsx:1408/1414/1440/1446`, `tradeText.ts:69` (clipboard) |
| 4 | `_owned_pick_assets` → `_inject_owned_picks` | the trade job's deck + `/api/trades/asset-ideas` | `give_players[].name`, `receive_players[].name` | **TradesHome deck cards — the reported surface** |
| 5 | `_power_picks_by_owner` | `GET /api/league/power-rankings` | `teams[].picks.items[].label` | `LeagueSummaryScreen.tsx:2148`, `web/league-rankings.html:872` |

Site 3 is cross-league by construction (a Matches list spans leagues), so `league_id` and `original_roster_id` were added to its `IN` query and orders are resolved per **distinct** league.

**Not touched, and why.** The 12 generic ladder rungs (`generic_pick_label`, `year_pick_label`, `_apply_pick_rung_year_labels`, `build_universal_pool`) are universal-pool pseudo-assets with no league and no original roster — there is no slot to resolve, and `"Early 1st Round Pick"` already *is* a within-round position statement. `TradeValueBar.shortPick()` re-cuts `gap.pick_equivalent.label`, which is a generic rung, not an owned pick.

**Chalkline:** no component, style, colour, radius, font or icon changed. Zero files under `mobile/`, `web/` or `extension/`.

---

## 8. Manual TestFlight checklist (operator)

Run on a league whose current-season rookie draft has **not** happened and whose Sleeper draft order **is** set — `1312140920132497408` qualifies today (it is 1 of only 3 such leagues in prod, and 451 of the 469 current-year-pick deck cards are its).

1. **TradesHome — the reported surface.** Open the Acquire/Trades tab and swipe until a card carries a 2026 pick. **Expect** `2026 1.08`-style text (round, dot, two digits), not `2026 1st`. A pick acquired by trade reads `2026 1.08 (from mattmurf77)`.
2. **Future years unchanged, same card.** A 2027/2028/2029 pick on any card still reads `2027 1st` / `2029 4th`. **A future year showing a dotted slot is a failure** — that would be an invented order (#273).
3. **Picks screen / in-league calculator.** Open the calculator's pick picker. Every 2026 row shows a slot; every later year shows a round ordinal. Cross-check one 2026 row against the league's real Sleeper draft order — the slot must match Sleeper, not the team's roster number.
4. **Value is unchanged.** Note a 2026 1st's value chip before and after this build: it must be **identical**, and every 2026 1st in the league must still show the **same** value as every other regardless of slot. A 1.01 showing more than a 1.12 means pricing leaked in and is a stop-ship.
5. **Tier badge is unchanged.** A 2026 1st still badges `first_1`. A 1.12 badging `second` is the same stop-ship as (4).
6. **Matches / awaiting.** Open a match or awaiting row containing a 2026 pick; the give/receive name lists show the slot form and the trade-text copy button produces the same string.
7. **League power rankings.** The draft-capital drill-in lists 2026 picks by slot and later years by round.
8. **A league that should NOT change.** Open a league whose 2026 draft is already complete (most of them) or an MFL league. It carries no 2026 picks at all, or generic labels — **nothing should look different anywhere.**
9. **Kill switch.** Set `picks.slot_labels` to `false`, `POST /api/feature-flags/reload`, pull-to-refresh. Every label in steps 1–7 returns to the round-ordinal form. No restart, no re-sync.
