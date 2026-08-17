# #330 — Reconciliation log, round 1 → 2 (G4, Phase 1)

> Author's dispositions for every objection in
> [`review-round-1.md`](review-round-1.md) (4 BLOCKING, 5 NON-BLOCKING),
> per the coordinator's incorporation guidance. All new factual claims the
> critic introduced were independently re-verified against `origin/main` @
> `0b2dcee` before adoption — verification results noted per row.
> Updated artifacts: [`prd.md`](prd.md) (R-1, R-3, R-5, R-6, R-8 revised;
> R-10 added; test plan and checklist extended), [`scope.md`](scope.md)
> (§3 backend row, orchestrator note, §5 evidence row).

## Blocking

| # | Objection (summary) | Disposition | Where |
|---|---|---|---|
| B-1 | Same-team repeat Offer never re-fires the choke-point effect — `scopedOpponent` is a derived string (`TradesScreen.tsx:613-614`, re-verified) so the dep is unchanged; second handoff lands its pin on the stale deck and leaves `autoRunPendingRef` armed. | **Adopted as specced by the critic** (coordinator concurred; nothing strictly better found). `setHandoff` stamps a store-internal monotonic `seq`; the consume path records it into local `autoRunSeq`; the choke-point effect's dep array gains `autoRunSeq`. "No new `mutate` site" rule stands. New coverage: U-1 (strictly increasing seq), S-2 clause (seq in deps), TestFlight step 6. | prd R-1, R-3 §2, U-1, S-2, T-6 |
| B-2 | In-flight mutation race: an old mutation's `onSuccess` (`setJob`, `:1402`, re-verified) can land after the handoff's dispatch and resurrect a pre-scope deck. | **Adopted — generation-epoch guard.** Epoch ref incremented by every `resetDeckForNewTargets()`; dispatches stamp it; results applied only through a pure helper that drops mismatched epochs (no `setJob`/toast/`scopedEmpty`/`deckFailure` from stale results). Deterministic test: U-4 exercises the helper with mismatched epochs and **fails without the guard**; the full async race is honestly stated as TestFlight-only runtime coverage (step 6). Scope note added: rapid manual double-tap without an intervening reset stays last-write-wins (pre-existing, out of G4 scope). | prd R-10 (new), U-4, S-5, T-6 |
| B-3 | Empty-state trigger keyed on handoff origin makes the manual scoped re-run dishonest — same pin, same scope, zero cards would fall back to the old toast + never-searched card. | **Adopted.** Trigger is now scope-based and origin-independent: any zero-card completion while a pin is set AND an opponent is scoped. The surviving-ref mechanism is dropped; `scopedEmpty` names derive at completion from the pin + `scopedOpponentName`. Both under-specified cases made explicit: job error → `deckFailure` owns it, never `scopedEmpty`; exhausted swiped-out deck → deck summary, never `scopedEmpty`. S-4 simplified accordingly; TestFlight step 7 added. | prd R-6, S-4, T-7 |
| B-4 | Hard lock on written proof only is indefensible while G6 concurrently rewrites the enforcing functions (`trade_service.py:3568-3576`) and lands before G4 ships; `test_finder_targeting.py` has no single-pin assert. | **Adopted — critic's resolution, per coordinator.** New G4-owned file `backend/tests/test_offer_hard_lock_330.py` (BT-1): single-give-pin (v2 + v3) and single-receive-pin asserts, harness mirrored from the existing two-pin tests; no G6-owned file touched. P-1 demoted to narrative companion. Scope.md carries the orchestrator note: one backend **test** file joins an otherwise client-only group; not production backend code; path stays Polish. The file doubles as the tripwire G6's merge must keep green (recorded in prd §Dependencies). | prd R-5, R-9, BT-1; scope §3 + orchestrator note |

## Non-blocking

| # | Objection (summary) | Disposition | Where |
|---|---|---|---|
| N-1 | (a) R-6's "under your current settings" is false — the #189 relaxed pass already searched beyond them before zero was returned; (b) relaxed cards appear unlabeled in the deck. | **(a) Adopted** — copy rewritten to make the stronger honest claim ("even after stretching the fairness band"); R-6 names the relaxed pass explicitly with a "do not fix this copy back" note for the builder. Critic's claims re-verified: relaxed config at `trade_service.py:156-168`; zero `relaxed` reads in `TradeCard.tsx`/`TradesScreen.tsx`; only label at `AssetIdeasPanel.tsx:112`. **(b) Declined for G4 scope, per coordinator** — pre-existing gap, already spawned as a separate task chip; G4 does not absorb it. Acknowledged in R-6 "Out of scope" and TestFlight step 8's context note. | prd R-6 |
| N-2 | The 0.50 pinned fairness default side-fact is inert and misleading — mobile always sends `fairness_threshold: effectiveFairness`. | **Adopted.** Re-verified (`TradesScreen.tsx:812`, `:1377`). Side-fact rewritten as an explicit correction: the server default never applies to this flow; no wide net exists. | prd §Base notes |
| N-3 | Consume-site ambiguity (focus-gated effect vs raw subscription); un-consumed handoff lifetime unstated; `finder_hub` OFF leaves an armed ref with no consumer. | **Adopted in full.** R-3 now specifies **consume on focus**; R-1 states an un-consumed handoff persists until consume/`clear()`/league-switch GC, no timeout; R-3 step 1 + R-8's new degradation matrix require the ref NOT be armed when the choke point is gated off (prefill-without-autorun degradation). S-2 gains the gating clause. | prd R-1, R-3, R-8, S-2 |
| N-4 | TestFlight checklist cannot catch B-1/B-2/B-3; step 3's zero-result recipe is weak given the relaxed pass. | **Adopted.** Steps 6 (repeat-Offer same team + Offer mid-search), 7 (manual re-run from empty state), and a rewritten step 3 (fairness ON, junk piece to strongest roster, expect a few tries) added; checklist is now 8 steps. | prd §TestFlight checklist |
| N-5 | Copy nit: "Nothing was hidden…" reads defensive and is only true of pin/scope, not the widened fairness band. | **Adopted** — critic's suggested body taken (Author's call per review): "…— even after stretching the fairness band. Your player and team stayed locked." Target-verb mirror updated to match. Coheres with N-1a. | prd R-6 copy |

## Critic verifications accepted into the contract

- The `force: true` removal is stronger than round 1 stated: the
  **registration half** (`server.py:5446` `is_pinned`; `:5466-5468` unpinned-
  only index registration) was re-verified and added to §Base notes — it is
  the half protecting future *unscoped* searches.
- Round-1 items the critic checked and passed unchanged: R-1 lifecycle
  (as amended by N-3), R-2 incl. Target symmetry, R-4/scope §1 analytics
  reasoning, R-5 line anchors, R-8 kill switch (as amended by N-3),
  scope §2-§5, and the Dependencies section's default-no-bypass posture on
  the G6 question.

## Round-2 status

All 4 blockers and all 5 non-blockers dispositioned (8 adopted, 1 split —
N-1b declined for scope per coordinator guidance, tracked separately).
No new open questions for the operator; the G6 bypass question remains with
the orchestrator unchanged. Ready for critic round 2.

## Post-sign-off orchestrator edit (2026-08-16)

- **Dependencies §"Cross-group question"** rewritten by the orchestrator after
  G6's review round resolved the bypass boundary (targeted-vs-untargeted,
  server-side derived — see G6 `review-round-1.md` B3 + the arbitration in
  G6's reconciliation log). G4's "default: NO bypass" assumption superseded;
  R-6 empty-state spec unchanged. Edit made after G4's round-2 sign-off, which
  covered the pre-arbitration text; the change is documentation-of-dependency
  only — no G4 requirement, test, or file-ownership change.
