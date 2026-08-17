# #330 — Critic review, round 1 (G4, Phase 1)

> Critic pass over `prd.md` (R-1…R-9) and `scope.md` (working tree), both
> verified against `origin/main` @ `0b2dcee`. Every
> objection below was re-derived from source, not from the Author's cites.
> Verdict summary: **4 BLOCKING, 5 NON-BLOCKING**; the design's spine
> (store-based handoff, choke-point dispatch, honest empty state, no backend
> change) is sound and most of the Author's verification work checks out —
> including two claims I verified deeper than the PRD states them.

## Coordinator-flagged deviations — verdicts

1. **Re-anchor to `0b2dcee` — accepted**, per instruction and on the merits:
   the plan's cites do match the tip.
2. **`force: true` removal — CONFIRMED CORRECT, and stronger than the PRD
   says.** The PRD cites only the lookup half (`server.py:9909`
   `_any_pinned` includes `opponent_user_id`; `:9960` skips the lookup).
   I verified the **registration half too**: `_kickoff_trade_job` sets
   `is_pinned` (`server.py:5446`) and only registers unpinned jobs in the
   per-key index (`:5466-5468` `if not is_pinned`). So there is no stale
   path in either direction: Offer twice → two fresh jobs; Offer then
   manual re-run → still `_any_pinned` (pin + scope persist per R-7) →
   fresh job; later unscoped run → the index never held the scoped job.
   Recommend the PRD note add the `:5446/:5466-5468` half — it is the half
   that protects *future unscoped* searches. No objection.
3. **`selected` dep-array framing (latent today / live with R-2) — agree.**
   The current body (`LeagueSummaryScreen.tsx:1155-1176`) never reads
   `selected`; the omission is inert until R-2's code reads it. R-2 + S-1
   handle it correctly.
4. **Hard lock on proof-only — NOT defensible as specced.** See B-4.

## BLOCKING

### B-1 — Same-team repeat handoff never auto-runs (R-3 §2, S-2, checklist)

`scopedOpponent` is a **string**: `sheetOpponent?.userId`
(`TradesScreen.tsx:613-614`). R-3's dispatch rests on "the effect already
fires on the `scopedOpponent` change step 1 caused" — true only when the
team actually changes. The high-frequency real path is the *same* team:
user offers player A to Team X, gets a deck (or the empty state), returns
to rankings, offers player B **to the same team**. Step 1's
`setSheetOpponent` stores a new object but the derived dep string is
identical, so the choke-point effect (`:2176-2190`, deps
`[finderMode, scopedOpponent]`) does not re-fire: no
`resetDeckForNewTargets`, no generation — the new pin lands on the old
deck silently, which is #330's original symptom reborn. Worse,
`autoRunPendingRef` stays armed and detonates on the next unrelated scope
change.

**Required:** a per-handoff monotonic `seq` (store-incremented) threaded
into the choke-point effect's deps (or an equivalent nonce), consumed with
the ref; U-tests + an S-2 clause pinning it; and a TestFlight step "repeat
Offer for a second player on the same team → new scoped deck runs".
R-3's "no new `mutate` call site" rule can stand — the nonce only widens
when the *existing* site fires.

### B-2 — In-flight mutation race can resurrect a pre-scope deck (R-3, missing case)

Nothing in R-3 handles "Offer while a finder run is already in flight."
The consume path resets (`job` → null) and dispatches a new mutation, but
the **old** mutation's `onSuccess` (`setJob(snapshot)`,
`TradesScreen.tsx:~1402`) still fires when its network call returns —
potentially *after* the new dispatch, overwriting `job` with the
pre-scope snapshot; React Query does not order two in-flight mutations.
The exposure pre-exists via the in-place team-pick, but auto-run makes it
a first-class flow: the Offer tap is precisely a moment when a prior
search may be streaming. **Required:** a generation epoch (incremented by
every `resetDeckForNewTargets`) captured per-mutation and checked in
`onSuccess`/`onError` (drop stale results) — or an explicit, written
argument in the PRD for why last-write-wins is acceptable, plus a
TestFlight step "tap Offer while a search is running." Today no test in
the plan exercises this case at all.

### B-3 — R-6's handoff-origin trigger leaves the manual scoped re-run dishonest (operator decision 2)

R-6 gates the empty card on "a handoff-originated search (a ref survives
from R-3 until the job resolves)." The operator's decision is about *the
scoped search*, not which button started it. Under this spec, a user on
the empty state who opens the sheet, tweaks nothing material, and taps
Find a Trade manually — same pin, same scope, zero cards — gets the old
toast + `"Hit \"Find a Trade\" to start"` card (`TradesScreen.tsx:5781`):
the exact dishonest state this requirement exists to remove.
Under-specified alongside it: does the surviving ref clear on job *error*
(it must — `deckFailure` owns that state), and an exhausted swiped-out
scoped deck must stay the deck-summary, never `scopedEmpty`.
**Required:** trigger on **any** zero-card completion while a pin is set
and an opponent is scoped (`pinnedGive/pinnedReceive` non-empty AND
`scopedOpponent`), origin-independent; drop the surviving-ref mechanism;
state the error and exhausted-deck exclusions explicitly. This also
simplifies S-4.

### B-4 — Hard lock cannot ship on a written proof while G6 rewrites the enforcing code (R-5)

P-1 is a point-in-time walk of `0b2dcee`. G6 is **concurrently
rewriting the presentment/generation path in the same functions**
(`backend/trade_service.py` — construction gates #340/#341/#339 sit
exactly where `_consider` enforces the pin, `:3568-3576`), and the batch
plan lands G6 *before* G4 ships. A narrative proof cannot regression-test
code that changes after it is written; the operator's explicit decision 1
would reach production guarded by nothing executable, and the PRD itself
documents that `test_finder_targeting.py` has **no single-give-pin
assert**. The ownership argument is real but only bars *editing G6's
file*: a **new** file (e.g. `backend/tests/test_offer_hard_lock_330.py`)
with single-give-pin (v2 + v3) and single-receive-pin asserts, mirroring
the existing two-pin tests' harness, collides with no one and turns the
operator's decision into a tripwire G6's merge must pass. **Required:**
add it; demote P-1 to the narrative companion. If the orchestrator rules
even a new backend test file out of G4's lane, the fallback is a named
handoff requirement on G6 ("your suite must add the single-pin assert
before ship") recorded in both groups' plans — proof-only with no
executable guard anywhere is not acceptable for this decision.

## NON-BLOCKING

### N-1 — The #189 relaxed pass is invisible to the PRD, and R-6's copy is wrong because of it

Zero-card *targeted* jobs do not go straight to zero: the server
auto-runs the relaxed fallback first — fairness band widened to 0.55,
surplus floors dropped; pins/scope/untouchables never relaxed
(`backend/trade_service.py:156-168`). Two consequences the PRD must own:
(a) the empty card's body "under your current settings" is literally
false — by the time it renders, the server already searched *beyond* the
user's settings and still found nothing (which is a *stronger* honest
claim; say that instead, or drop the clause); (b) relaxed cards can
appear in the auto-run deck with **no label** — `TradeCard.tsx` and
`TradesScreen.tsx` never read `relaxed` (verified: zero grep hits; only
`AssetIdeasPanel.tsx:112` labels "Stretch"). (b) is pre-existing and out
of G4 scope — flagged as a separate task chip — but R-6 should name the
relaxed pass so the builder doesn't "fix" the copy back.

### N-2 — The fairness side-fact in §Base notes is inert and mildly misleading

Mobile always sends `fairness_threshold: effectiveFairness`
(`TradesScreen.tsx:812`, `:1377`), so the server's 0.50 pinned default
(`server.py:9911`) **never applies to this flow** — scoped auto-runs
execute at the user's 0.75 with fairness ON, not a wide net. Delete the
side-fact or mark it server-default-only, so no builder assumes the wide
net exists.

### N-3 — Consume-site semantics: focus gating and the flag matrix (R-1/R-3 contract ambiguity)

"Focus-scoped effect" vs "subscribes to the store" can be implemented two
ways (isFocused-gated effect vs raw subscription firing while unfocused).
Specify one: **consume on focus** (navigate always focuses Trades
immediately after `setHandoff`, and it makes cold-mount ordering
deterministic); state that an un-consumed handoff simply persists until
league-switch/`clear()` GC — no timeout. Also record the flag interplay:
the choke-point effect is gated `!finderHubOn || !finderMode` return, so
with `trades.finder_hub` OFF (currently ON, `config/features.json:11`)
the handoff would prefill but never auto-run and never clear the armed
ref — acceptable degradation, but it belongs in R-8's kill-switch story
and the ref must be cleared or simply not armed in that branch.

### N-4 — TestFlight checklist cannot catch B-1/B-2/B-3

Steps 1-2 do catch the original #330 symptom (prefill + auto-run + hard
lock observed across several cards) — that half is sound. Add three
steps: repeat-Offer to the same team (B-1); Offer while a search is
running (B-2); manual re-run from the empty state yielding zero again
shows the card, not the toast (B-3). Step 3's "pick a pairing with no
plausible deal" is operationally weak given the relaxed pass exists to
prevent exactly that — suggest offering an untouchable-adjacent junk
piece to the top roster *with fairness ON* and accepting that this step
may take a few tries.

### N-5 — Copy nit (R-6)

"Nothing was hidden — there's no deal that works right now" is
Chalkline-compliant in form (plain, no emoji) but reads defensive, and
per N-1 "nothing was hidden" is only true of pin/scope, not of the
fairness band the server quietly widened. Suggested body: `We couldn't
build a trade that sends {player} to {team} — even after stretching the
fairness band. Your player and team stayed locked.` Author's call.

## Explicitly checked and sound (no objection)

- R-1 lifecycle (set/consume/clear/league-switch) — clear, one-shot
  semantics unambiguous *given* N-3's focus ruling.
- R-2 including the Target-verb symmetry rationale.
- R-4 / scope §1 analytics reasoning — prop-name-level enforcement
  verified at `analytics_taxonomy.py:523`; free-form `source` values
  already ship.
- R-5's line anchors — spot-verified (`trade_service.py:3568-3576`
  matches the quoted enforcement; ≥1-of with one pin is a hard lock).
- R-8 kill switch (modulo N-3's finder_hub note); scope §2-§5 including
  the D-056 posture and the docs table (api-reference n/a is correct —
  payload uses only documented fields).
- Dependencies §: carrying the G6 bypass question to the orchestrator
  with default no-bypass matches the plan and the operator's Q21 shape.

---

# ROUND 2: SIGNED OFF

All nine round-1 objections are dispositioned and — verified against the
round-2 `prd.md`/`scope.md` text, not just the reconciliation log — actually
present: B-1's store-stamped monotonic `seq` is specified in R-1 (stamped
internally, never caller-supplied, never resets) and threaded as `autoRunSeq`
into the choke-point deps in R-3 §2, with U-1's strictly-increasing assert,
S-2's dep clause, and checklist step 6; B-2's generation epoch is R-10 with
the pure `applyJobResult` helper, U-4 explicitly failing without the guard,
S-5, and an honest statement that the full async race is TestFlight-only
(step 6), plus a correct out-of-scope note for epoch-less manual double-taps;
B-3's trigger is now scope-based and origin-independent in R-6 with both
exclusions (error → `deckFailure`, exhausted → deck summary) explicit and the
surviving-ref mechanism dropped; B-4 is resolved exactly as required — new
G4-owned `backend/tests/test_offer_hard_lock_330.py` (BT-1, give + receive
single-pin across v2 and v3), P-1 demoted to narrative, the orchestrator
note and §3 backend row present in scope.md, and the file named as G6's
tripwire in Dependencies. N-1/N-5's copy makes the stronger
relaxed-pass-honest claim with a builder do-not-revert note; N-2's fairness
correction is in §Base notes; N-3's consume-on-focus, no-timeout lifecycle
and the finder_hub-OFF no-armed-ref degradation are in R-1/R-3/R-8 with S-2
coverage; N-4's checklist is 8 steps covering repeat-Offer, mid-search
Offer, and manual re-run honesty. The two re-checked factual claims hold
against `0b2dcee`: `is_pinned` computed at `server.py:5446` with
unpinned-only index registration at `:5466-5468`, and `effectiveFairness`
always sent at `TradesScreen.tsx:812`/`:1377`. No new defects found; no
objections remain. G4 Phase 1 is ready for build.
