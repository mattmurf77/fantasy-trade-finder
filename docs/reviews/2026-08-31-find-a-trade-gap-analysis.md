# Find a Trade — pre-merge vs merged experience: gap analysis

**Date:** 2026-08-31 · **Requested by:** operator, after the ✓ queue-validation regression (#409 family) surfaced the worry that the #384 calc/finder merge dropped other behaviors.
**Before state:** the guided Find a Trade page + separate calculator at `80dee425~1` (the commit before PR #172 shipped 2026-08-22 as v1.16.0).
**After state:** the merged experience at `main` `e92f95c1` (v1.16.13, 2026-08-31): `calc.merged_layout` + `calc.inline_home` + `calc.canvas_results` all live, guided landing hosts the canvas, found ideas browse inside it.
**Companion docs:** [2026-08-27 calc-vs-guided-finder audit](2026-08-27-calc-vs-guided-finder-audit.md) (77-row parity audit this analysis extends), [#384 e2e review](../feedback/items/384-calc-finder-merge/review-2026-08-22-e2e.md), [#409 status](../feedback/items/409-like-not-league-member/status.md).

---

## Verdict in one paragraph

The merge's core loop (build/search/evaluate/send) survived, and most of the losses that reached users have already been caught and fixed piecemeal by the feedback waves (#406/#407/#409/#410/#411/#412, the partner-summary restore, the outlook-entry restore). But three things remain genuinely broken or lost: **(1)** the like → "other owner sees it tagged" loop — the ✓'s validation gate refused user likes (being removed 2026-08-31 by operator ruling), and even with it removed, **the merged landing may not render the "They're interested" tag at all** (P0 verification below); **(2)** a cluster of card-level affordances the canvas never re-homed (undo on Clear, per-asset swap suggestions, untouchable-from-the-asset, pin/targeting affordances); **(3)** the entire guidance layer (tour, coach marks, analyst beats) is off with no replacement, and the deck-era analytics spine (`trade_card_viewed`, the session-definition event) does not fire on the merged landing.

---

## A. The like loop — the regression that triggered this analysis

| | Pre-merge | Merged (before 2026-08-31) | Now |
|---|---|---|---|
| How a user liked a trade | Swipe right / ✓ on a served deck card. **Always recorded** — no validation beyond the swipe itself. | ✓ on the canvas/browse/shop calls `POST /api/trades/queue`, which ran the injector's mirror gates **up front** and refused with `queued:false` (membership → rosters → untouchable/not-interested → D-096 fairness floor). Recording nothing on refusal. On top of that, G-063 made membership fail **100% of the time** 2026-08-22 → 2026-08-30. | Operator ruling 2026-08-31: gate removed — every well-formed ✓ records; hand-queued (`calcq_`) likes bypass the preference/fairness gates at injection so they genuinely surface. Rosters-valid, cap, and dedup kept. |
| What the other owner saw | The likes-you injector flagged or synthesized a card, **pinned it to the top of their deck** with the flare **"They're interested"** pill (`TradeCard.tsx`). Note: the shipped tag wording has always been "They're interested" — there was never a literal "liked by other owner" string. | Same injector, same pill — **but only on surfaces that render `TradeCard`** (Team/Player-mode decks, flag-off path). | Same, plus bypass for hand-queued likes. **See P0 below.** |

### ⚠ P0 — verify the tag is visible on the merged landing at all

With `calc.canvas_results` live, **the card deck does not render on the merged guided landing** — model-path results present inside the canvas as a browse session, which renders via `InLeagueCalculator`, not `TradeCard`. The "They're interested" pill and the likes-you top-pinning live in `TradeCard`. If injected likes-you cards ride into the browse set without the pill (or don't ride in at all), then a liked trade surfaces to the counterparty **untagged or not at all** on the surface most users now see — which defeats the operator's ruling even with the queue gate removed. **Action: trace `_inject_likes_you_cards_impl` output through the browse-session presentation; if the tag is dropped, add the liked-by-owner treatment to the browse tile.** This is the sharpest open item in this document.

---

## B. Regressions already caught and fixed (for the record)

| Gap | Broken | Fixed | Where |
|---|---|---|---|
| ✓ queue 100% refusal (`not_league_member`, caller-excluded members list) | 2026-08-22 | v1.16.13 (#409, G-063) | `backend/server.py` caller synthesis |
| Fairness/preference gates vetoing user likes | 2026-08-22 | 2026-08-31 (operator ruling, this session) | queue route + injector bypass |
| Partner team-shape summary (#306 QB/RB/WR/TE + picks line) dropped from Team sheet | #384 W1 | 2026-08-27 restore | `PartnerSummaryLine`, both layouts |
| Outlook & filters entry vanished (#376/#379/#394 — "most critical bug") | #384 rebuild | 2026-08-24 fallback row | `calc.outlook-row` / fallback |
| Auto-defaulted partner silently scoping every search (#407) | merge | v1.16.12 (`opponentChosenRef` gate) | payload gate |
| No way to search all teams explicitly (#406) | merge | v1.16.12 ("Any league mate") | Team sheet `partnerAny` |
| Clear mid-browse corrupting the idea's edit map (#410, D-169) | v1.16.11 | v1.16.13 decline ✕ fork | action-row middle cell |
| Name truncation on compact tiles (#411) | merge | v1.16.13 re-flow (83/100 fit) | tile layout |
| "More offers" placement reversion (#412) | v1.16.11 | v1.16.13 (under give-side Add) | `calc.give.more-offers` |
| Fair-sweep zero-result landing on the wrong idle card (audit Q5) | merge | fixed — "No fair package for this canvas" state | `trades.canvas-results` empties |

The pattern worth naming: **every one of these was rediscovered by a user after ship** because `calc.merged_layout` + the tour were lit for all users without the TestFlight pass (#384 status header). The audit's 24 guided-only feature clusters are the standing at-risk list.

## C. Open gaps — prior behavior with no merged equivalent

Ordered by recommended priority. "Audit row" = the 2026-08-27 audit's rating.

| # | Prior feature | Prior behavior | Merged behavior today | Audit row | Priority |
|---|---|---|---|---|---|
| C1 | **Likes-you tag on the merged landing** | Injected card pinned top-of-deck with "They're interested" pill | Deck doesn't render on merged landing; browse tiles may drop the tag entirely | — (post-audit) | **P0 — verify & fix** (§A) |
| C2 | **Undo** | Pass held 5s with "Passed — Undo" toast; calculator Clear had 5s "Trade cleared — Undo" | Merged Clear is one-tap, destructive, unrecoverable (undo survives only on the pushed Real-values page) | 10 · partial | **P1** — audit D7 snapshot-undo pattern |
| C3 | **Per-asset swap suggestions** | Long-press → "Swap suggestions — replacements priced to keep this trade balanced" (`SwapSuggestSheet`), plus manual swap | Eveners answer "what closes the gap", not "what replaces this asset at this price"; long-press menu gone on canvas rows | 15/16 · partial | **P1** |
| C4 | **Deck-era analytics on the merged landing** | `trade_card_viewed` (the session-definition event), dwell, engagement bits per fronted card | Browse pager deliberately emits nothing; `trade_card_viewed` never fires on the surface most users see | 8.1 | **P1** — session metrics undercount |
| C5 | **Untouchable from the asset** | Long-press player → "Mark untouchable" in place | Only via DNA sheet → Off the table → Manage | 18 · partial | P2 |
| C6 | **Pin/targeting affordances** | Pin summary row ("Pinned: X · Edit · ✕"), pre-pin deck snapshot restore (#288), `trade_pin_cleared`, package toggle | Canvas anchors one search, writes no pins; anchor receipt has Change/Clear but no snapshot restore | 36 · partial | P2 |
| C7 | **Guidance layer** | Live v1 analyst beats (s2.x–s8.1), coach marks, Quick Set prompts, swipe coaching | Tour triple-locked off (`guide_v2` false, `guided_avatar` false since 2026-08-29, D-158 structural suppression); nothing guides the merged page | E2E P0-2..4 | P2 — Wave B (already queued in NEXT) |
| C8 | **Swipe gestures** | Pan right/left with rotation, velocity gate, VoiceOver custom actions | Browse session is pager + ✓/✕ buttons only | — | P3 — design call, not obviously a loss |
| C9 | **"Keep · more offers" on BOTH sides** | Both card sides could pin-and-regenerate | Give-side only (#412 ruling: shop is a give-side verb); receive-side survives only in deck modes | — | P3 — ruled, revisit only on feedback |
| C10 | **End-of-deck tally** | "Deck done — x passed · y liked · z proposed" + See liked / Done | Browse exhausted state has no tally; "See liked" exit gone from merged landing | — | P3 |
| C11 | **Bad trade? flag** | Per-card engine-quality flag ("this trains the engine", −2 rerank) | Not present in the browse session chrome | — | P3 |
| C12 | **Lane pills / fairness toggle on-page** | Team-fit moves / Value moves pills + fairness toggle with help sheet on the landing | Live inside the DNA sheet only (verify lanes survived the sheet re-spec) | — | P3 — verify |

## D. Changed by design (operator-ruled — not gaps, listed so nobody re-litigates them by accident)

- **One page instead of two** — D-158 (`calc.inline_home`): the guided landing hosts the canvas; the pushed page is Real-values-only. Demo mode deleted (#384 W0).
- **Find a Trade forks on the canvas** — D-153: empty ⇒ model deck; give-side ⇒ fairness-only `fair-packages` sweep. Receive side is a preference, not a filter.
- **Clear is a labeled button** — D-157 (after a tester wiped his canvas reading bare ✕ as "close"); the ✕ returns only as the browse-session decline cell (D-169).
- **Format chips trimmed on the hosted landing** — T-3 ruling 2026-08-28; alive on the pushed page + league settings.
- **Trades tab is the front door** — `nav.trades_landing`, 2026-08-29.
- **Decline reasons as overlay** on calculator-origin decks (host prop, not flag).
- **Standing offers (#362)** are post-merge additions, not prior behavior — but note the open G-063 sibling: `GET /api/trades/standing-offers` `stale` is permanently false.

## E. Recommended sequence

1. **P0 (C1):** trace and, if needed, restore liked-by-owner tagging in the browse-session presentation — this completes the 2026-08-31 ruling end-to-end.
2. **P1 batch (C2, C3, C4):** undo on Clear, swap suggestions on canvas rows, and `trade_card_viewed`-equivalent emission for browse tiles.
3. **P2 batch (C5, C6):** asset-level untouchable + pin affordances, folded into the next calculator wave.
4. **C7 (tour)** stays with Wave B, already queued in NEXT.md — no new work item needed.
5. Adjudicate the P3 rows only if user feedback raises them; each is one small item.

*Full evidence: the two 2026-08-31 research inventories (session transcript), the 77-row audit, and file:line cites throughout the companions listed at top.*
