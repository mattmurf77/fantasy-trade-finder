# Manual TestFlight checklist — Team Review defect batch (#364 / #367 / #368)

**Owner:** operator · **Build:** next EAS build off `main` after this merges
**Why this exists:** under [D-056](../../../../living-memory/DECISIONS.md) this is the only runtime
evidence mobile gets. Three of the five changes are copy and ordering — things a test can pin the
*shape* of but cannot judge. **Nobody has seen the corrected divergence beat on a device.**

**Preconditions:** your FFv3 IDP league (it is the one with unpriced slots), `trades.team_review`
and `outlook.odds` both on, board with ≥16 ranking interactions so the divergence beat renders.

| # | Step | Expected |
|---|---|---|
| 1 | TradesHome → open Team Review from the entry card | Flow opens on `standing` |
| 2 | **#364** — read the caption under the playoff band | Names IDP explicitly: *"…we do not rank IDP or kickers, so N of your M starting slots (DL, LB, DB) carry no value here."* Slot names match your actual lineup. **Not** the old generic "Based on your offensive starters" |
| 3 | Confirm the band itself | A band word (Likely / Toss-up / Unlikely). **No bare percentage anywhere** — if you see a number like "62%", stop and flag it |
| 4 | Next → `window`. Read the three share rows | Says **"Value age 26 and under"**, not 23. Vet row says 27 and over |
| 5 | **New inputs card** — "Every input behind that call" | Four rows: veteran share × weight, young share × −weight, pick capital × −weight, and a **Total score**. Each contribution signed. Fine print names the two cuts and states the model reads age + pick capital only |
| 6 | Sanity-check the arithmetic | The three signed contributions sum to the Total score (±0.01 rounding). If they don't, the client and server disagree — flag it |
| 7 | **#367** — go to the `divergence` beat | **Sell card comes first.** Its players are **on your roster**. Buy card second, its players are **not** on your roster. The old "Skip these — you'd be buying at a price you don't believe" line is **gone** |
| 8 | **#367, the real test** — pick one name in the Sell list | It should be someone **you are lower on than the league** — a guy you'd happily move because the market likes him more than you do. If the sell list is full of your favourite players, the inversion is back |
| 9 | **#368** — go to `partners`, read "Pointed the other way" | Each row shows a **non-zero** firsts count where that team actually holds firsts — not "0 firsts" for everyone. As a contender, the team holding the most pick capital is **first in the list** |
| 10 | **Completion** — finish the flow with "Find my trades", then return to TradesHome | Team Review entry is **minimized to a row** reading **"Team review · done"**, not the full card |
| 11 | Tap that row | Review reopens and runs normally (minimizing is not removal) |
| 12 | Force-quit the app, reopen, go to TradesHome | Still minimized — the completion survived the restart |
| 13 | **Cross-surface** — open Trends → "Easiest sells & easiest buys" | Sells label reads *"(league consensus ranks them higher than you)"* and the list matches that. This surface changed too |

## Rollback

Both levers are deploy-free (`POST /api/feature-flags/reload`), no client release:

- `trades.team_review` → `false` — route 404s, entry card vanishes, every other path byte-identical.
- `outlook.odds` → `false` — the band and its #364 caption disappear; the rest of the review stands.

**Neither flag reverts #367.** The sell-direction fix is in `compute_consensus_gap`, which is
shared with Trends and ungated — reverting it is a code change, not a flag flip. That is the one
item on this list to look at hardest.
