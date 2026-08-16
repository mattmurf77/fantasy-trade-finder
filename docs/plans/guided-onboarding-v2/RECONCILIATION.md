# Reconciliation Log — Guided Onboarding v2 PRD

**Document type:** PRD · **Rounds run:** 7 (4 base + 3 for operator amendments) · **Converged:** yes — base signed off round 4; amendment cycle closed round 7 with the verifier's final three consistency prescriptions applied verbatim (flagged below)
**Process:** dual-agent (Agent A = Product/User lens, Agent B = Engineering/Risk lens), both Opus. Two independent drafts → orchestrator synthesis → two cross-review rounds with fixes → sign-off. Every objection below was verified against code by the raising agent before it was accepted.

---

## Round 1 (independent drafts) — major divergences the synthesis had to resolve

| Topic | A's position | B's position | Resolution in candidate v1 |
|---|---|---|---|
| Scope shape | Amend full 19-step script + 5 new beats | Engine-first Phase 0 + only 3 new beats | B's Phase-0-first gate structure; A's five beats distributed across phases 1–2 |
| Rankings beat (seed #3) | Ship now with honest "swipes are teaching me" copy | Defer entirely to Phase B (`grade_count`) | Two-stage honesty: calibration line now (mechanically true), progress promise Phase-B-gated. **B later withdrew its objection** after verifying the per-user Elo scoping (`server.py:~10165` session-scoped service) |
| Exhausted-deck boundary | N4 pin card first, s7.1 later | B2 (outlook) owns it; s7.1 collision = operator question | Declared allocation rule (later corrected again in round 3 — see below) |
| Metrics | +8pp activation target, 2% season holdout, DiD | Holdout = 2 people at N=156; diagnostics only; DiD needs ≥50 devices/week precondition | B's posture won wholesale; A's structure absorbed as diagnostics; holdout dropped, revisit at ≥5,000 MAU |
| "Accept a trade" (seed #1) | Teach send on MatchesScreen | Same conclusion, independently (mobile has no accept verb — `trades.ts:484-487`) | Convergent — the strongest cross-validation in round 1 |

Both drafts independently discovered the headline fact: **the shipped tour is mostly unreachable** (16 of 20 entries dark under release flags), reframing v2 as reachability-first.

## Round 2 — 8 blocking objections (4 per lens, zero overlap), all fixed

**A raised (all code-verified):**
1. N2's trigger (no outlook) and its spotlight target's render condition (needs resolved outlook) were mutually exclusive → **fixed:** two-form beat (Form A spotlight / Form B bubble+CTA); citation corrected.
2. Nearly every retirement/adoption event named in the beats had no emitter and no taxonomy row → **fixed:** §5.3.1 event inventory with verified EXISTS/NEW states, wired as a Phase-0 exit gate and D1 hard blocker.
3. Beats ignored the feature kill-switch flags owning their taught surfaces → **fixed:** owning-flag preconditions required in the §5.0 trigger contract, fail closed; runbook row.
4. Copy mandated but not written (no-OTA means frozen at build) → **fixed:** target copy for every amended line in §5.2/§5.3; D9 copy-freeze owner.

**B raised (all code-verified):**
1. The boundary rule omitted the live `deck.replenishment` summary card, which owns the slot for exactly N4's population → **fixed:** four claimants named; summary card owns the slot; N4 ships as its extension.
2. N4's "pin" verb had no reachable control at its trigger (targeting board gated behind `finderMode==='player'`) → **fixed:** explicit hand-off CTA scoped as a named small UI delta.
3. `s7.1` fires today pointing at nothing (target gated behind `onboarding.rank_routing:false`, displaced by the summary card) → **fixed:** added to §2.1 as a live incoherence; G-1 reachability redefined as "fires AND target mounts"; s7.1 cut with a revival condition.
4. FR-E4 specified arbitration the coordinator doesn't have (`claim()` is first-come, no preemption; priority table is docs-only) → **fixed:** mechanism named (synchronous claim + reactive modal check, flag-gated; preemption explicitly rejected with regression rationale).

**Withdrawn by B in round 2 after verification:** the objection to N1 in Phase 1 (per-user Elo write makes the calibration copy true) and the objection to five-beats-total (phasing + the add-one-retire-one budget rule).

## Round 3 — 2 blocking objections (one raised by both lenses), both fixed

1. **Both lenses:** the round-2 fix itself introduced a fake event — `deck_regenerated{source:'prefs_changed_strip'}` spliced two unrelated code paths and was mislabelled EXISTS (notably, this originated as B's own round-2 non-blocking suggestion; A caught it, B confirmed and retracted). → **fixed:** N2 adoption + G-3 now use `find_trades_tapped{source:'prefs_changed_strip'}` (registered, live), with a "do not use deck_regenerated" row documenting why.
2. **A:** the ESPN send claim was stale — `espn.send` is `true` (flipped 2026-08-12, D-026), so N3 would have shown ESPN users the Copy-trade line while a live in-app send button existed; the error came from stale code comments. → **fixed:** ESPN gets its own send branch; Copy-trade restricted to Fleaflicker/flag-off; missing ESPN attempt event marked NEW; stale comments listed for cleanup.

Also folded from round-3 non-blockers: copy-class column in §5.2 (with s6.2 trimmed to the auto cap and s5.0/s6.2 relabelled CHANGE); `autoMs` recomputed post-freeze; N4's full owning-flag set (`trade.finder_targeting`, `trades.finder_hub`); FR-E4(b) reactive-subscription form, flag-gated; the §5.0 enforcement split (five CI-enforced stored fields vs trigger-as-convention); the returning-user non-fire declared in §5.4; `quickset_started` definitively NEW.

## Round 4 — sign-off

- **A: SIGN-OFF yes.** Verified both round-3 fixes to the line, including that the N2 adoption join is live in production flags today.
- **B: SIGN-OFF yes.** Verified the same, plus the ESPN fix (new to it), the FR-E4 modal-deferral claim (both root modals are pure deferrers), and the §2.1 flag table line-for-line.

Final-round non-blocking suggestions folded into the FINAL doc: N2's receipt flag-dependencies (`trades.edit_full_sheet` + `trades.finder_hub`) added to its trigger; the G-3 undercount caveat (strip arms only when `deck.length > 0` at sheet close); N3's ESPN build-≥103 precondition and the stale-comment cleanup list; `trade.finder_targeting` named; §5.3.1 header relabelled; citation filenames qualified.

## Unresolved disagreements

**None between the agents.** OQ-1 and OQ-2 were subsequently **resolved by operator decisions O-3 and O-1** (2026-08-15). Remaining operator calls live in the PRD §9 (OQ-3…OQ-8), most notably OQ-4 (confirm the exhausted-deck allocation) and OQ-3 (whether the trade engine should confidence-gate the first deck — out of this PRD's scope but material to `s2.1`'s copy). Building mobile accept/decline (`trade_k_accept=20`, the strongest ranking signal in the product, unreachable from mobile) remains open **feature** work outside this PRD.

## Amendment cycle (rounds 5–7) — operator decisions O-1…O-5

After round-4 sign-off, the operator issued binding directions: seed #1 becomes find → **like** → "Awaiting them" → optional proactive send, with the mutual-match walkthrough separate (O-1); and a varied **ranking-method ladder** by effort — Trios lightest, Tiers/Quick Set heaviest (O-5). O-2/O-3/O-4 confirmed beats as specced (resolving OQ-1/OQ-2). The orchestrator added `N6` (two-unit first-like chain, replacing `s6.1`), the ladder policy, and `N7` (Trios rung on the summary card via direct navigation).

**Round 5 (targeted, both lenses): 7 distinct blockers, all fixed.**
- Both: replacing `s6.1` broke `s8.1`'s real predicate (`s2.2 && s6.1`) → rewired to `n6.1 || s6.1`.
- Both: "s6.2 defers to next boundary" invented semantics; the real like-handler timers would fire under a live N6.1 and `maybeAskApple` consumes-before-show → chain moved behind N6.1's completion; consume-only-on-show required.
- A: N6.1's copy stated a false social fact ("waiting on their side" — one-sided likes notify nobody) → honest re-draft.
- A: the awaiting segment's empty state would contradict the bubble one tap later → gated CTA + router-less variant.
- A: ladder ordering never happened (s3.2's early re-offer outraces N7) → arbitration rule + named state.
- A: `trades.send-sleeper-btn` is on every card against a per-testID last-mount-wins registry → per-instance registration id (also fixed N3).
- B: `trio_swipe` is server-emitted and client-invisible — retirement wired to it never fires → NEW client receipt required.

**Round 6 (both lenses): 3 distinct blockers, all fixed.**
- Both (independently): the round-5 "like-time prefetch" races the swipe POST — the router could never render on the very like that triggers it → gate moved to `swipeMutation.onSuccess`, using the response's `{matched, match_id}`.
- B: the s6.2 chain was hooked to a screen-focus event that never fires for 3 of N6.1's 4 exits → fires from the completion callback.
- A: the ladder rule as written gated off s3.2's re-offer during Phase 1, before N7 exists → phase-scoped; rung-advance defined (retired / display-cap exhausted / not-eligible 3 sessions).

**Round 7 (confined joint verification): everything in scope verified correct except 3 consistency items, whose prescribed fixes were applied verbatim and close the loop** *(prescription-applied, not re-reviewed — the honest cap)*:
1. §5.4's awaiting row still described the removed like-time prefetch and contradicted §5.3's matched branch → row split (matched → suppress-and-consume; empty/failed → router-less variant).
2. The matched-branch suppression lost the tour's ending again (nothing wrote `guideSeen['n6.1']`; N3 doesn't exist in Phase 1) → suppression writes `guideSeen['n6.1']` + `guide_step_suppressed{blocked_by:'matched'}`, no shown event; first-like determination moves to `onSuccess`.
3. D2 still carried the superseded Sleeper-pinned registration id → `trades.send-control.guide`, platform-agnostic, mounted on whichever router branch renders.
Round-7 non-blockers also folded: M1 excludes `via:'timeout'`; the `onComplete(via)` hook named as new engine surface (covers ✕); like-that-dismisses-N6.1 ownership declared; `rankLadder` per-rung eligibility fields; MFL attempt event promoted to NEW in D1/N3; `trade.send_in_sleeper` master kill switch as owning flag for N3/N6.2; NFR-1 clock note; s3.2-rung-likely-spent expectation note.

## Process notes

- Zero overlap between the two lenses' round-2 blockers — the asymmetric-lens structure did real work; neither reviewer echoed the other.
- Two synthesis-introduced defects (the event splice, the ESPN staleness) were caught by cross-review, one of them a self-correction by the lens that originally suggested it. The cross-review rounds paid for themselves.
- Every blocking objection in all rounds was grounded in a file:line citation the raising agent had personally verified; no objection was accepted on assertion.
