# Group F plan — #381 + #346: Quick Set drops unselected players to FA

- **Date:** 2026-08-24 · **Planner:** Group F (fast-track bug path)
- **Items:** #381 (bug, v1.15.0, mattmurf77 — detailed Nabers repro) · #346 (polish, v1.13.4, jonbonjourvi — preseeded-values angle)
- **Canonical folder:** this one (`346-quickset-tier-drop/`). `plan.md` here is the **batch** plan — untouched.
- **Verdict up front:** reproduces on current code, by design — the #161 demotion rule (shipped 2026-07-25, commit `a8898a7`, TestFlight v1.10.0 `d44200f`) is the "regression". The operator's #381 preference supersedes it. Fix = stop auto-demoting; unselected players **hold** their current tier.

## 1. Flow trace (current code)

State each tier screen holds — `mobile/src/screens/QuickSetTiersScreen.tsx`:

- `selected` (line 153) starts **empty** on every rung. Already-tiered players are **not** pre-selected; pre-selection happens only for tiers saved earlier *this run* when revisited via Back (`goTo`, line 412: `setSelected(new Set(savedMap[TIERS[idx]] ?? []))`). So "not re-selecting" is the *default* state, not an explicit act — the heart of both reports.
- `savedByTier` (line 160) tracks this-run commits; `claimedBy`/`gridPlayers` (lines 239–252) hide only players claimed by *another* tier this run. Everyone else — including players currently tiered at/above this rung — renders in the grid, sorted elo-desc (lines 231–234), chip labeled with `tierForElo(elo)` (lines 532, 581).

What "save tier" does to previously-valued, unselected players — `onSave`, lines 448–487:

- `ids` = selected, `cleared` = this-run deselects (line 452).
- **The drop:** lines 475–485 — on any explicit save (`ids.length > 0`), every grid-visible unselected player whose `tierForElo(elo)` is the saved tier **or higher** goes into `demoted`.
- `saveTiers(position, {tier: ids}, cleared, demoted, …)` (`mobile/src/api/rankings.ts:321–351`) posts `demoted_pids` (line 347) to `POST /api/tiers/save`.

Where the FA write happens — backend:

- `backend/server.py:8697` `save_tiers_route` parses `demoted_pids` (8724–8727) and passes it to `RankingService.apply_tiers` (8776) / `apply_tiers_subset` (8762, rookie scope).
- `backend/ranking_service.py:1782` `DEMOTED_ELO = 1100.0`; pin loop at 1832–1835 (subset mirror 1918–1920) pins each demoted pid to 1100 — **below even the waivers band floor (1150**, `backend/tier_config.json`).
- The pin persists via `save_tier_overrides` (server.py:8782) into `users.tier_overrides` — durable, per-format.

Why Nabers "disappears": `onSuccess` invalidates `['rankings', activeFormat, position]` (QuickSetTiersScreen.tsx:437) → the pool refetches mid-walk → Nabers' elo is now 1100 → he sorts to the **bottom** of a ~200-player WR grid (line 232) with chip label **FA** (`tierForElo` returns `waivers` for anything < the `fourth` floor, `mobile/src/utils/tierBands.ts:119–133`). He is still in the response (`/api/rankings` is uncapped, server.py:7247) — but off-screen at the bottom, which reads as vanished. #346 is the identical mechanism seen from the preseeded-values angle: consensus-seeded "1 1st" players not re-selected on that rung drop to zero value instead of holding.

## 2. Repro verdict and the "regressing" commit

**Reproduces on current code: yes** — deterministically, by the trace above. Not a malfunction; it is the #161 rule working as specified.

**Regressing commit: `a8898a7` (2026-07-25)** — "feat(#161,…): quickset demote…". Before it, unselected players kept their tier (pinned by its own test `test_no_demoted_pids_is_todays_behavior`). It shipped in **v1.10.0** (`d44200f`), so both reporting builds (1.13.4, 1.15.0) carry it — "new behavior" from a tester who hadn't walked Quick Set since ≤ v1.9. Verified nothing newer touched the path: the only screen commits since 2026-08-01 are guide/analytics (`8827810`, `4733f78`, `e66d51c`); `ranking_service.py`'s August commits (tier-bounded voting `9d24da3`, clamp `7f16217`/D-085, band floor D-084) don't touch the demote writers. The scoped mirror was added by `a3152d4` (rookie M2), same semantics.

**The conflict to surface:** #161 was itself a deliberate tester-driven rule ("passed-over players must not silently keep a stale tier" — the Jameson Williams case; see `../161-quickset-demote/status.md` §Semantics decision). #381 is the operator overruling it: "By default, they should stay in the same tier." Operator preference wins; this plan supersedes the #161 rule and says so in DECISIONS.md + the #161 status doc. Note #346's reporter expected *step-down-one-tier* — the operator's stated second choice; HOLD also cures #346's actual pain ("easy to miss these players"), since nothing silently moves at all.

## 3. Chosen contract

> **HOLD (chosen):** During the Quick Set walk, a save assigns the selected players to the rung and touches **no one else**. A visible-but-unselected player keeps his current tier and remains selectable on any later rung (Nabers stays "4+ 1sts", appears near the top of the "3 1sts" grid labeled 4+ 1sts, one tap places him). No auto-demotion exists anywhere in the walk.

Explicit demotion survives, unchanged, via three existing affordances:

1. **The FA rung** — `waivers` is the walk's 8th step; selecting a player there pins him into the FA band (1150–1215) like any other rung. This is *the* explicit "demote to FA" gesture.
2. **Revisit-deselect** — Back to a rung saved this run, deselect, save → `cleared_pids` → override deleted → player returns to his consensus-suggested tier (pre-#161 semantics; the #161 "demote wins over clear" precedence dies with the demote).
3. **TiersScreen** — drag-to-pool / clear paths, untouched.

Alternatives considered:

- **Step down one tier** (operator's second choice, #346 reporter's expectation) — rejected: still silently moves players the user never touched; repeats the surprise at every rung; more code (client would synthesize tier assignments).
- **Pre-select current-tier players in the grid**, making deselection an explicit act that could honestly demote — attractive UX, but it changes the #233 empty-save CTA logic, the F3 `seeded_accepted` telemetry, and the walk's whole selection model. Noted as an **optional follow-up for the operator to opt into**, not part of this fix.

## 4. Fix — where it belongs (both sides, and why)

Backend *and* mobile. The backend half matters for reach: Render auto-deploys immediately, while the mobile fix waits on an EAS build + TestFlight — killing the pin server-side stops the damage for **every installed binary** (v1.10.0–v1.16.x all send `demoted_pids`) the moment the backend ships.

| File | Change |
|---|---|
| `mobile/src/screens/QuickSetTiersScreen.tsx` | Delete the `demoted` computation (lines 475–485) and the `demoted` member of the mutation payload/`mutationFn` (lines 419–429, 486); rewrite the #161 comment blocks (68–79, 461–474) to state HOLD. |
| `mobile/src/api/rankings.ts` | Remove the `demotedPids` param + `demoted_pids` body key from `saveTiers` (lines 321–351); its only non-`[]` caller was the screen. |
| `mobile/src/screens/TiersScreen.tsx` | Mechanical: drop the positional `[]` at the 4 `saveTiers(…, [], scopeOpts)` call sites (lines 339, 380, 1096, 1103). No behavior change. |
| `backend/server.py` | `save_tiers_route` (8697): stop parsing `demoted_pids` (8724–8727), revert the emptiness guard (8736) to `total_assigned == 0 and not cleared_pids`, drop the kwarg at 8762/8776, fix the docstring. Old clients still sending the key: it becomes an ignored unknown body key; they only ever send it alongside `ids > 0` (onSave computes `demoted` only when `ids.length > 0`), so no old request starts 400ing. |
| `backend/ranking_service.py` | Remove the pin loops (1832–1835; subset 1918–1920) and the `demoted_pids` params + docstring sections from `apply_tiers`/`apply_tiers_subset`. **Keep `DEMOTED_ELO`** — it's load-bearing in the D-085 tier-bounded-voting goldens (`backend/tests/test_pin_tier_bounded.py:113, 214, 407`) and mirrors `server.ANCHOR_NO_VALUE_ELO = 1100.0` (server.py:1313); re-comment it as the anchor-"no value"/unranked pin value, no longer a quickset writer. |
| `backend/tests/test_quickset_demote.py` | Rewrite to pin the **new** contract (see §5). Keep the filename for history. |
| `backend/tests/test_override_pin_unpin.py`, `test_rookie_scope.py` | Update the assertions that exercise demote (pin-stamp + scoped-O4 cases) to the ignore/hold contract. |
| `docs/api-reference.md` | `/api/tiers/save`: `demoted_pids` removed (accepted-and-ignored as an unknown key for wire compat). |
| `docs/feedback/items/161-quickset-demote/status.md` | Add a superseded-by-#381 note (don't rewrite history). |
| `living-memory/DECISIONS.md` | New D-id: Quick Set saves hold unselected players (supersedes the #161 demote rule; operator call, #381). Also CHANGELOG + TEST_LEDGER at ship. |

**No data repair.** Existing 1100-pins from past demotions stay — they are byte-indistinguishable from an anchor "no value" answer (both 1100.0), so a backfill can't tell operator intent from #161 damage. Affected players are rescued by re-placing them (any rung, anchors, or Tiers board); the TestFlight checklist has the operator re-place Nabers.

## 5. Evidence plan (D-056 — no Maestro, no simulator)

**Backend unit tests** (`backend/tests/test_quickset_demote.py`, rewritten — each sabotage-provable by re-adding the pin loop):

1. `test_passed_over_player_holds_tier` — seed a player in `firsts_4plus`; save that tier with three *other* ids; assert his elo/tier unchanged. (The Nabers repro as a unit test; red under the old code.)
2. `test_demoted_pids_key_is_ignored` — POST `/api/tiers/save` with a `demoted_pids` list (an old-binary request); assert target override unchanged and response `ok`. (Pins the backend-reach half; red if the parse/pin returns.)
3. `test_clear_restores_consensus_tier` — revisit-deselect sends `cleared_pids` only → override deleted, consensus tier back.
4. `test_fa_rung_save_pins_waivers_band` — selecting a tiered player on the `waivers` rung lands him in 1150–1215 (the explicit-demote affordance survives).
5. Scoped mirror: rookie-scope save passes over a visible rookie → rookie holds (replaces the O4 demote cases in `test_rookie_scope.py`).
6. Guard regression: save with `total_assigned == 0` and no clears still 400s.

**Mobile structural guard** (`mobile/tests/check-quickset-hold.js` + `npm run test:quickset-hold` in `mobile/package.json`): asserts `QuickSetTiersScreen.tsx` contains no `demoted` computation (no `TIERS.indexOf(cur) <= tierRank` filter, no `demoted` key in the mutate payload) and that `api/rankings.ts`'s `saveTiers` body has no `demoted_pids`. Sabotage: re-adding either turns it red. (Note: `check-*.js` suites are `npm run`-only, not CI-gating — the pytest half is the CI-gated evidence.)

**Code-walk proof** (goes in this folder's status at build time): the §1 trace re-cited against the post-fix tree — `onSave` builds `{ids, cleared}` only; `saveTiers` body has three keys; `save_tiers_route` never reads `demoted_pids`; no caller of `_pin(…, DEMOTED_ELO)` remains outside anchors.

**Operator TestFlight checklist** (the Nabers scenario, exactly):

1. Rank tab → Quick set → WR, format as in the league. On **4+ 1sts**: confirm Nabers' chip shows current tier "4+ 1STS". Select 3 other WRs — **not** Nabers. Save.
2. On **3 1sts**: Nabers is still near the **top** of the grid, chip still "4+ 1STS" — not FA, not missing. *(Old behavior: bottom of the list as FA — this step alone catches the regression.)*
3. Tap Nabers + save → Tiers board shows the 3 WRs in 4+ 1sts and Nabers in 3 1sts; nobody new in FA.
4. Explicit demote still works: walk to the **FA** rung, select a currently-tiered depth player, save → Tiers board shows him in FA.
5. Revisit path: Back to a rung saved this run, deselect one player you placed, save → he returns to his consensus-suggested tier (chip label), not FA.
6. #346 angle: on the **1 1st** rung, select only some of the preseeded 1-1st players and save → the unselected ones still read "1 1ST" on the next rung.
7. Cleanup: re-place any player previously FA'd by the old behavior (Nabers included — the fix does not retro-repair old pins).

## 6. Risks

- **`threshold_met` / rank-set unlock:** unaffected — completeness (`save_tiers_position`, `all_done`, `_note_ranking_method`) keys off `tiers`/`via`, never `demoted_pids`. The reverted emptiness guard removes the (never-exercised) demote-only save path that would have marked a position saved while writing nothing.
- **Cross-format derivation (`rankings.cross_format_derive`, server.py:10044):** derivation copies overrides; fewer 1100-pins ever exist to propagate. Pre-existing derived pins stay (same no-backfill stance). No change needed.
- **KTC blend / consensus preseed (`data_loader`):** HOLD literally means "leave the override state alone" — the consensus-seeded elo the chip label reads is untouched by an unselecting save. No interaction.
- **Tier-bounded voting (D-085 / `test_pin_tier_bounded.py`):** keeps consuming `DEMOTED_ELO` as the unranked pin value; only the quickset *writer* of that value is removed. Anchors' "no value" (1100) still creates unranked pins — that path is explicit and stays.
- **Old binaries (v1.10.0–v1.16.x):** keep sending `demoted_pids`; backend ignores it → they get HOLD immediately on backend deploy. The only visible in-app oddity on an old binary: nothing (the demote was invisible at save time anyway — that was the bug).
- **`member_rankings` publish / trends snapshot:** payload shapes unchanged.

## 7. Observation (out of scope, flagged separately)

Mobile's unscoped Quick Set saves send no `via` (only rookie-scoped saves do, `api/rankings.ts:336`), so `save_tiers_route`'s `via` defaults to `"tiers"` and the FR-20 `quickset_completed` server event (server.py `if via == "quickset"`) never fires for mobile walks — despite `QuickSetTiersScreen.tsx:364–370` asserting the server row is the authoritative completion. Analytics-only; not touched by this fix.
