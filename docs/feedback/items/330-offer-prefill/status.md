# FB-330 — group canonical folder

- **Status:** built 2026-08-16 · **Phase:** 2 (build) — awaiting merge + operator TestFlight checklist
- **Group:** G4 — Offer prefill + auto-run
- **Batch plan:** [`../304-positional-need-filter/batch-plan.md`](../304-positional-need-filter/batch-plan.md)
- **Plan base:** `origin/main` @ `d3fe3ac` (v1.13.4); PRD cites re-verified @ `0b2dcee`
- **Build base:** specs commit `56856f7` = `origin/main` @ `96f6945` + Phase-1 specs; branch `feat/fb330-offer`. Every PRD cite was re-verified against this tree (line positions moved; all anchors held — see §Build notes).

## Reported

> Clicking the offer button should open up find a trade with the team I am offering to and the player I am offering. Current experience brings you to the find a trade page, but does not prefill team or player. Additionally in this flow, the user should not have to hit find a trade. [Operator: player = hard lock; empty result = honest empty state + link back to league summary.]

## Build (2026-08-16)

Requirements R-1..R-10 implemented as specced; no PRD deviations beyond the
two noted in §Deviations. Files:

| File | Change |
|---|---|
| `mobile/src/state/useFinderTargets.ts` | R-1: `handoff` field + `setHandoff` (store-stamped monotonic `seq`, module-level counter surviving `clear()`); `clear()` nulls the handoff; league-switch GC covered via the existing subscription |
| `mobile/src/screens/LeagueSummaryScreen.tsx` | R-2: `handleRowAction` sets the handoff for both verbs (name fallback chain verbatim from `focusedTeamName`); dep array gains `selected` |
| `mobile/src/screens/TradesScreen.tsx` | R-3/R-4/R-6/R-8/R-10: focus-gated one-shot consume (`useIsFocused` + handoff-subscribed effect); choke-point effect deps gain `autoRunSeq`, armed ref widens the fresh-mount gate, cleared inside the dispatch branch; `find_trades_tapped {source:'league_offer', mode}` inside the autoRun branch only; generation epoch (ref) incremented in `resetDeckForNewTargets`, stamped via `onMutate`, compared through `applyJobResult` in onSuccess/onError/poll tick; `scopedEmpty` state + completion effect + deck-slot card + toast suppression |
| `mobile/src/utils/applyJobResult.ts` | NEW — R-10 pure helper (zero runtime imports, plain-node testable) |
| `mobile/tests/check-offer-prefill-330.js` | NEW — structural S-1..S-5 (45 assertions) |
| `mobile/tests/check-offer-prefill-330-unit.js` | NEW — U-1..U-4 (transpile-and-run idiom) |
| `mobile/tests/check-analytics-297-302.js` | #298's 2-emitter count updated to 3 (the auto-run emit is a PRD-required third `find_trades_tapped` site; new assertion pins it as the `source:'league_offer'` arm reading the same `deckMode`) |
| `backend/tests/test_offer_hard_lock_330.py` | NEW — BT-1 tripwire (the ONLY backend file; zero production backend changes) |
| `mobile/package.json` | `test:offer-prefill-330` + `test:offer-prefill-330-unit` scripts |
| `living-memory/LLD.md` | Finder preselection contract now carries opponent + auto-run intent (scope §4 row) |

### Build notes — cite drift from `0b2dcee` to this tree

All PRD anchors re-verified; content identical, line positions moved. Key
re-anchors (this tree): `sheetOpponent` `TradesScreen.tsx:595-597`;
`scopedOpponent` `:613-617`; payload `opponent_user_id` `:1395` region;
choke point (pre-change) `:2176-2190` region; zero-result toast `:1408-1426`
region; deck failure card `:5761` region; `_any_pinned` `server.py:10160`
(was 9909); cache lookup skip `:10211-10214` (was 9962); `is_pinned`
registration `:5624,:5644` (was 5446/5466-5468); `_trade_job_key` `:2728`;
mode normalization `:10143-10145` (was 9887-9894); relaxed config
`trade_service.py:156-168` (unchanged); relaxed pass `:2529-2537` +
`_relaxed_targeted_pass` `:2645`.

### Deviations from the PRD (with reasons)

1. **`mobile/tests/check-analytics-297-302.js` updated** (not in the owned
   file list). Its #298 assertion pins "exactly 2 `find_trades_tapped`
   emitters in TradesScreen"; R-4's auto-run emit is a legitimate third, so
   the intended change turned the suite red. Updated the count to 3 and
   added an assertion pinning the third emitter's exact shape (same
   `deckMode` derivation). A test that fails on the intended change gets
   deleted — updating it with a tightened companion assertion is the
   documented #300-suite lesson.
2. **PRD §R-5 side-fact correction:** the PRD says `pinned_give_mode`
   normalizes to `"any"` "unless 2+ pins and an explicit `all`". In this
   tree the server (`server.py:10143-10145`) normalizes to `"all"` whenever
   `pinned_give` is non-empty AND the client sent `"all"` — the 2+ gate
   lives in the CLIENT (`TradesScreen.tsx` sends `pinned_give_mode: 'all'`
   only when `packageMode && pins.length >= 2`). Conclusion unchanged:
   a #330 handoff always runs single-pin mode `"any"`, and with one pin
   "any" (≥1-of-1) ≡ the pin in every card regardless.

## Verification evidence (D-056)

- **`npm ci`** (fresh, no symlink) → `npx tsc --noEmit` clean.
- **BT-1** `python3 -m pytest backend/tests/test_offer_hard_lock_330.py` →
  **4 passed** against the CURRENT backend (pre-G6-merge baseline proof).
  Red-proof: with the give/receive pin filters neutralized in BOTH engines
  (`trade_service.py` `_consider` + `trade_optimizer.py` subset loops,
  transient uncommitted edit) → **4 failed**; reverted → 4 passed;
  `git status` confirmed production files untouched.
- **U-1..U-4** `node tests/check-offer-prefill-330-unit.js` → 14/14 PASS.
  Proven-to-fail, one named sabotage at a time (apply → RED → revert →
  green):
  - U-1: seq stamping removed (`seq: 0`) → U-1d + U-2c RED.
  - U-2: `handoff` dropped from `clear()`'s reset object → U-2a + U-2b RED.
  - U-3: `setSide` made additive → U-3b + U-3c RED.
  - U-4: `applyJobResult` returns the result unconditionally → U-4b + U-4c
    RED (the guard, not the plumbing, is what the test exercises).
- **S-1..S-5** `node tests/check-offer-prefill-330.js` → 45/45 PASS,
  including: choke-point deps contain `autoRunSeq`; `generateMutation.mutate`
  call-site count unchanged over base (8); ref-arm behind the same
  `finderHubOn && finderMode` gate as the choke point; empty-state trigger
  origin-independent; toast suppressed under exactly the card's condition;
  never-relax over all three zero-card regions; epoch stamped/compared at
  all three application sites.
- **Full mobile check-suite sweep:** all 39 `tests/check-*.js` PASS
  (including the updated `check-analytics-297-302.js`);
  `scripts/testid-lint.sh` OK (`trades.scoped-empty.back` +
  `trades.scoped-empty` added).
- **Backend sanity:** `test_finder_targeting.py` + BT-1 together → 11 passed.
- **Flag preconditions re-verified ON in `config/features.json`:**
  `trades.finder_hub`, `trades.sheet_targeting`, `trade.finder_targeting`,
  `trade.asset_ideas`, `league.player_trade_handoff` (the kill switch).

## P-1 — single-pin hard lock (narrative companion to BT-1)

Operator decision 1: the offered player is in EVERY suggested trade. The
client sends exactly one `pinned_give_players` (Offer) / one
`pinned_receive_players` (Target) element; the engine's documented contract
("give side includes at least one of these player IDs",
`backend/trade_service.py:2444-2445`) degenerates at one pin to "the pin is
in every card". Enforcement, per generator (this tree):

- **v2 pair generator** (`_generate_for_pair_v2`, `:3503`): `pinned_set`
  `:3541`, `pinned_recv_set` `:3546-3547`; every candidate package passes
  `_consider` (`:3704-3712`), which rejects any give side not intersecting
  `pinned_set` (`:3709-3710`) and any receive side not intersecting
  `pinned_recv_set` (`:3711-3712`). With |set| = 1, "intersects" = "contains
  the pin". The pinned players are also force-added to the candidate pools
  (`:3824-3826` receive, `:3838-3840` give) so the lock can't be starved by
  pool pruning.
- **v3 optimizer** (`trade_optimizer.py`): sets `:247-252`; pool re-adds
  `:395-397` / `:402-404`; subset loops skip any give combination not
  intersecting `pinned_set` (`:498-502`) and any receive combination not
  intersecting `pinned_recv_set` (`:505-506`).
- **Consensus fallback** (`_generate_consensus_for_pair`, `:3927` — the
  unranked-opponent arm inside v2 generation): give POOL restricted to
  pinned players (`:4008-4009`) — a single pin makes every emitted give side
  exactly `[pin]`-bearing; receive pool restricted to pinned players
  (`:3990-3993`) — mirror.
- **Legacy v1 pair path** (`_generate_for_pair`, `:4141`; only reachable
  with `trade_engine.v2` OFF): give-side checks at `:4297`, `:4346`,
  `:4391`, `:4457` all require intersection with `pinned_set` — single pin ⇒
  present. (No receive-pin param exists on this path; Target-verb pins
  require the v2 path, which is the shipped configuration.)
- **Mode is irrelevant at one pin:** the client only sends
  `pinned_give_mode:'all'` at 2+ pins (`TradesScreen.tsx` payload build);
  server normalization `server.py:10143-10145`; and ≥1-of-1 ≡ all-of-1
  anyway.

BT-1 (`backend/tests/test_offer_hard_lock_330.py`) executes this claim for
v2 + v3, both sides, with an organic-run sanity check proving the pin
genuinely REDIRECTS the deck (the unpinned top card trades the OTHER
player).

## P-2 — #189 relaxed-pass constraint survival

A targeted job that yields zero cards re-runs through
`_relaxed_targeted_pass` (`trade_service.py:2529-2537` call site, `:2645`
def). The re-run copies `_v2_kwargs` verbatim (`kwargs = dict(v2_kwargs)`)
and overrides ONLY `fairness_threshold` (widened to
`relaxed_fairness_threshold` = 0.55, never tightening) and, stage 2, the
surplus floors via the thread-local `_cfg_override` — `pinned_give_players`,
`pinned_receive_players`, `pinned_give_mode`, and `opponent_user_id` ride
through unchanged, and the docstring names untouchables + the #108 user-gain
gates as never relaxed. So the R-6 empty state only appears after the server
has already searched beyond the user's settings WITH the pin and scope still
locked — which is exactly what the card's copy claims.

## P-3 — never-relax: every zero-card handler walked (client)

Zero-card handling sites in `TradesScreen.tsx` after this change:

1. **`generateMutation.onSuccess` zero-card block** — either returns early
   (pinned + scoped: the card is the surface) or toasts. Mutates no pin or
   scope state.
2. **Completion effect** (keyed `job_id`/`status`/`cards.length`) — sets or
   clears `scopedEmpty` only; reads pins via `getState()` without writing.
3. **`scopedEmpty` deck-slot card** — renders copy + one `navigation.navigate`
   back to League rankings. No store calls.
4. **Poll-failure path** — `setJob(null)` + `deckFailure`; never touches the
   store or `sheetOpponent`.

No path calls `setSide`, `clear()`, `removeGive/Receive`, or
`setSheetOpponent(null)` — pinned by S-4's three region sweeps. After the
empty state the pin chips and the sheet's "Trade with" tap-again-to-clear
remain the only (visible, manual) ways to change pin or scope; league switch
drops everything including a parked handoff (U-2b).

## Operator TestFlight checklist

The 8-step runtime checklist is in [`prd.md`](prd.md) §Test plan — steps 6
(repeat Offer, same team; Offer mid-search) and 7 (manual re-run honesty)
cover the B-1/B-2/B-3 behaviors that have no deterministic client-side
runtime proof under D-056.
