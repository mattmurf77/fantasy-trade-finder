# Manual TestFlight checklist — likes-you quality gates (D-096)

D-056 evidence artefact: under the retired-simulator posture this is the **only runtime
proof** this change gets. Run it after the branch merges and the Render deploy is live.
Log the outcome in `living-memory/TEST_LEDGER.md`.

**Why runtime proof matters here:** the unit tests prove the gate arithmetic, but they
cannot prove that the number the *gate* compared is the number the **value bar draws** on
a real device against real league data. Step 3 is the whole point of this checklist.

**Setup.** Sleeper league `1312140920132497408` (the league that produced all 198 measured
impressions) on the operator's account. `trade.likes_you` ON (it is), backend deployed at
the merge SHA. A leaguemate must have at least one live "like" in the last 90 days that is
still actionable — if the deck shows no `LIKES YOU` badge at all, that is **inconclusive**,
not a pass; see step 6.

| # | Step | Expected |
|---|---|---|
| 1 | Trades tab → generate a fresh deck. Swipe to the first card carrying the **LIKES YOU** badge. | A likes-you card appears within the first 3 positions (the boost is unchanged). |
| 2 | On that card, read the **value bar**. | The bar is **level or tilted toward you** — the receive side is never shorter than the give side. **Any likes-you card whose bar shows you giving more value is a FAIL** and the single thing this change exists to prevent. |
| 3 | Tap into the card's detail / expand the value numbers. | The give and receive totals are the same two numbers the bar renders, and `receive − give ≥ 0`. |
| 4 | Repeat steps 1–3 for **every** likes-you card in the deck (there are at most 3). | All of them pass step 2. |
| 5 | Note how many likes-you cards the deck contains, and compare with a deck generated before the merge if you still have one on screen. | Fewer likes-you cards is **expected and correct** — measured 198 → 83 impressions (41.9%). Zero across several regenerations is worth reporting (see step 6) but is not automatically a bug. |
| 6 | If **no** likes-you card appears at all across 3 regenerations: in Sleeper, have a leaguemate account like a trade whose mirror is clearly good for you (they offer you more value than they ask), then regenerate. | The mirrored card appears with the LIKES YOU badge, bar tilted toward you. If it does **not**, the gate is over-firing — report before shipping further. |
| 7 | Swipe **like** on a likes-you card, then check the match/awaiting surface. | The card is swipeable and resolves normally — synthesized cards are still registered by `trade_id`, so a 404 or "trade not found" here is a FAIL. |
| 8 | Regenerate the deck once more. | The card you just swiped does not reappear (`_past_decision_keys` unchanged), and the deck does not shrink below its normal size — gated likes-you cards must not leave holes. |
| 9 | Open a **different** league (non-demo) and generate. | Behaviour is the same; no crash, no empty deck. |
| 10 | Open the demo league. | No likes-you injection at all (unchanged guard) and no error. |

## Rollback rehearsal (do this once, then undo)

| # | Step | Expected |
|---|---|---|
| R1 | `PUT /api/admin/config/likes_you_gate_level` with value `0`, then `POST /api/feature-flags/reload` is **not** needed (model_config is read live). Regenerate a deck. | Pre-D-096 behaviour returns: more likes-you cards, and cards whose bar shows you paying may reappear. This proves the one-value deploy-free revert works on the live service. |
| R2 | Set `likes_you_gate_level` back to `2`. Regenerate. | Gated behaviour returns; step 2's expectation holds again. |

## What a FAIL looks like

- Any likes-you card whose value bar shows the user giving more than receiving (steps 2–4).
- A likes-you card that 404s on swipe (step 7).
- Zero likes-you cards even after step 6's deliberately-good like is planted.
- The deck shrinking, or showing an empty slot, where a likes-you card was gated out (step 8).
