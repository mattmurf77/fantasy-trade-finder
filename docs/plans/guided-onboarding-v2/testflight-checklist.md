# Guided Onboarding v2 — Operator TestFlight Checklist (Phase 0+1)

> Runtime QA per D-056/D-P1-08 (Maestro retired; TestFlight is primary). Prereq: a build containing this branch, `onboarding.guide_v2 → true` for your device (tester allowlist or flag flip). Log outcomes in `living-memory/TEST_LEDGER.md`. Kill switch: `onboarding.guide_v2 → false` (hot reload).

## A. Fresh install (delete app first), guide_v2 ON
1. Sign-in: Analyst intro (11w) → username spotlight. Type your Sleeper name — step advances on the real submit.
2. Deck: wait line shows real roster count → "trades both sides should want" (the softened market claim, NOT "my model thinks both sides say yes") → swipe coaching → **first swipe advances it**.
3. Third swipe: **N1** on the provenance chip — "your swipes are already teaching me yours." Tap chip or tap-through.
4. After a pass (or swipe 3): **two-minute ask** → CTA `Fix {pos} →` now lands on **Rank home** and **N8 asks the import question** ("Do you pay for rankings…"). Verify BOTH arms across two devices/reinstalls if possible:
   - `Upload →` opens the import sheet; complete a CSV/paste import → return to Trades → deck regenerates → reveal fires on your imported numbers ("{n} new trades…"). **No Quick Set celebration toast, no Apple sheet on this return.**
   - `No — start simple` → lands on **Trios**; cast one vote → back to Trades → deck regenerates → reveal fires (positive only; silence on null is correct).
5. **First like:** bubble reads "**Logged — they haven't seen it yet.** Send it to them now?" (never "waiting on their side"). `See it →` lands on Matches **Awaiting them** with your liked trade listed. If your like instantly matched: NO bubble at all (correct). If the awaiting list would be empty: bubble has NO button, says "I'll flag it the moment they like it back."
6. After the like flow settles (next Trades visit): Apple save-moment line + system sheet (once). It must NEVER appear over an open Analyst bubble.
7. **Pass 3 cards in a row** (no like): **N2** — "Not your kind of deal?" → opens the Trade DNA sheet (spotlight on the receipt's Change if visible, plain bubble+button otherwise). Set an outlook → deck re-aims. The beat never returns after a save.
8. **Exhaust the deck:** summary card shows **`Pin targets →` as primary** (Done demoted). Tap → lands in player targeting; pin someone. Card never shows the pin line again.
9. **Matches tab (organic first visit,** before ever tapping See-it**):** one bubble — "Mutual matches land here…". Never appears when you arrived via the like-flow button.
10. **League tab first visit** (league with ≥3 ranked members): bubble on the position pills — "Filter one position…". Tap a pill → buyer/seller divider draws → beat never returns.
11. Sign-off: after the swipe-coaching and first-like beats, "That's the tour." fires once. **This must happen — its absence = the tour lost its ending (file a blocker).**

## B. Regression arms
12. **guide_v2 OFF (flag flip, relaunch):** v1 tour exactly — s6.1 "First target logged…" toast on first like, s2.3 provenance beat after first swipe, NO N-beats, NO import question (two-minute ask goes straight to Quick Set), no pin line on the summary card.
13. **v1-upgrade install** (install main build, complete tour, then update to this build, flag ON): no re-teaching of seen steps; at most ONE new beat this release; sign-off stays completed.
14. **`guideDismissed` install** (Skip the tour, then update, flag ON): **zero bubbles anywhere.** Settings re-enable replays only non-outgrown steps.
15. **Redraft league:** N1 never appears; the two-minute ask still works.
16. Non-Sleeper league (MFL/Fleaflicker) on the awaiting screen: send/copy controls render per platform; no beat claims the wrong platform (send-teaching beats are Phase 2 — none should spotlight the button yet).

## C. Feel checks (subjective, you're the instrument)
- Never two bubbles/sheets at once; nothing covers an open bubble.
- No bubble outstays: the like bubble auto-clears on your next swipe or ~8s.
- Copy: one line, one action, everything readable in its window (esp. the two auto-toasts).
