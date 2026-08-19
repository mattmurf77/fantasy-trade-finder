# C1 — both-ways does not collapse the deck. It doubles it.

**Date:** 2026-08-19
**Ticket:** [PRD.md](PRD.md) §5 Track C1 — *"a one-page note in this folder (`measurement.md`) with the four counts."*
**Status:** measurement only. No engine, flag, config or client file was changed by C1.
**Full analysis:** `docs/reviews/2026-08-19-consensus-gate-matrix.md`, on branch `audit/consensus-gate-matrix` @ `9026da7` — every method, proof and cross-check below is sourced there. This page is its distillation for the §7 product call.

---

## The counts

66 pair-runs per cell (6 real production boards × 11 league partners, one prod league, draft picks injected), consensus path forced, run against the real `RankingService.replay_from_db` and `TradeService._generate_trades_impl` with live `config/features.json` and prod `model_config`. **These are replay counts, not production counts — read the ratios within the table, not the absolute numbers.**

| Cell | Surviving | % of shipping baseline | User pays | Fairness p10 · p25 · p50 · p75 · p90 |
|---|---:|---:|---|---|
| 0.50 one-way *(ships today)* | 1,366 | 100% | 0 (0.0%) | .773 · .876 · .944 · .979 · .993 |
| 0.75 one-way | 1,290 | 94.4% | 0 (0.0%) | .826 · .891 · .951 · .981 · .994 |
| 0.85 one-way *(not asked for; included for the column)* | 1,141 | 83.5% | 0 (0.0%) | .881 · .916 · .962 · .983 · .995 |
| **0.75 both-ways — *this is the challenger*** | **2,739** | **200.5%** | **1,677 (61.2%)** | .814 · .887 · .951 · .983 · .995 |
| **0.85 both-ways — *the fallback*** | **2,376** | **173.9%** | **1,383 (58.2%)** | .885 · .923 · .962 · .987 · .996 |

The PRD's four cells are rows 1, 2, 4 and 5. **Risk row 1 of §8 — "challenger under-produces" — is dead.** 0.75 both-ways is 2.12× the same-threshold one-way cell and 2.01× what ships today; 0.85 both-ways is still 1.74× today. Fairness quality does not degrade: at the same threshold the both-ways distribution is indistinguishable from one-way. Both-ways is not adding worse cards, it is adding cards of the same fairness on the other side of the ledger.

The 0.75 floor is doing real work, and the PRD was right to set it: the source memo's 0.50 both-ways cell is 3,090 cards at **65.3%** user-pays — the "2:1 user-pays flood" §4 predicted.

**Independent served-impression cross-check** (production impressions, not replay; one-way cells only, because a served deck contains zero user-pays cards by construction): 0.50 → 7,105 cards · 0.75 → 6,353 (**89.4%**) · 0.85 → 3,767 (**53.0%**); zero user-pays in all three; fairness p10 .736 · p25 .789 · p50 .857 · p75 .928 · p90 .975. Note the exact arithmetic: **7,105 − 6,353 = 752**, which is precisely the independently-measured count of served cards where the partner overpays by more than a third. Raising the floor to 0.75 removes exactly that population and nothing else.

---

## Three findings the four-cell frame did not anticipate

**1. The direction of the volume risk was inverted.** §8 hypothesised under-production. The measured effect is a doubling. Deck volume does not decide this question; nothing in the size column argues against either both-ways cell.

**2. Fairness stops being only a quality gate and becomes a damage cap.** On user-pays cards, the share of their give side the user forfeits is:

| Cell | median | p75 | p90 | max |
|---|---:|---:|---:|---:|
| 0.75 both-ways | 5.3% | 13.0% | 19.5% | **25.0%** |
| 0.85 both-ways | 4.1% | 7.6% | 11.8% | **15.0%** |

The maxima are exactly `1 − threshold`, and structurally must be: with the one-sided sign gone, fairness ≥ `t` forces the forfeit `(gv − rv)/gv = 1 − fairness ≤ 1 − t`. **A 0.75 both-ways deck can never ask the viewer to give up more than a quarter more than they get, and the typical card asks for 5%.** This materially changes the risk profile of the §7 call: the downside is bounded by construction, not by tuning.

**3. There is a fifth cell nobody specified, and it is a real option.** Most of the expansion is *not* the `rv − gv` package test at `trade_service.py:4987`. It is `user_gain_ok_1for1` at `:1509` — the raw-board 1-for-1 ordering veto — which kills **22,748 of the 42,118** 1-for-1s that reach it. Separating them:

| Floor | one-way (ships) | drop `:4987` package test only | drop the one-sided family |
|---|---|---|---|
| 0.75 | 1,290 · 0.0% pays | **1,516 (+17.5%) · 30.6% pays** | 2,739 (+112%) · 61.2% pays |
| 0.85 | 1,141 · 0.0% pays | **1,375 (+20.5%) · 32.0% pays** | 2,376 (+108%) · 58.2% pays |

The middle setting is a modestly larger deck (~18–20%) in which **a 1-for-1 still can never ask the viewer to send a player they personally rank above the one they receive** — the viewer stays protected on every trade they hold a board for. These are separable product decisions and should be picked deliberately, not bundled.

Relatedly: the expansion is entirely 1-for-1 (838 → 2,301 at 0.75; 2-for-1 452 → 438), and it is broad across all six boards (per-user multiples 1.8×–3.2×), not one board's artifact.

---

## How far these numbers reach

Carry these forward; do not round them off.

- **Replay, not production.** Six boards, 15 pairs, 66 runs, one league. The 7,105 served baseline comes from many leagues over a window. A replay count is not a production count and the two must not be compared as if they were.
- **The replay's own one-way column does not reproduce the served one** — 100 / 94.4 / 83.5% against served 100 / 89.4 / 53.0%. This league's cards are unusually fair, so raising the floor costs less here than it would in prod. Read the within-replay ratios; **do not read the both-ways cells as "% of the production deck."**
- **Consensus path only.** All 66 pairs are forced onto `_generate_consensus_for_pair`. That is the 84.5% the question is about, but the divergence/v3 path is absent, and with it every 2×2 and 3×3 shape. Only 1-for-1 and 2-for-1 exist in this replay.
- **Picks are under-represented** — 36% of cards here are pick-bearing against ~55% in prod, a consequence of the shape restriction above.
- **One pricing deviation.** One of the six users runs `pick_pricing_mode = 'market_slots'` in prod; the replay pinned `tier_ladder` for all six.
- **D-091 is not inherited, and that cuts two ways.** Prod `draft_picks` for this league now holds 2026–2028 only, so **zero** phantom picks appear in any cell — the confound cannot bias the one-way ↔ both-ways comparison, which is the comparison this note exists to make. But it also means the replay baseline is not the same population as the 7,105 served cards, which were generated while phantoms were live.
- **Today's values.** Boards, rosters and consensus as of 2026-08-19.

---

## What this hands to §7

The decision was framed as *"if both-ways at 0.75 collapses the deck it is not a shippable product."* **It does not collapse, so that gate is answered and retired.** What is left is a product-promise question, not a viability one:

| §7 call | What C1 says about it |
|---|---|
| **Stay viewer-first** | Still coherent, and now cheap: 0.75 *one-way* costs 5.6% of the replay deck (10.6% on served data) and removes exactly the cards where the partner overpays by a third or more. B1 (likes-you floor) is required regardless. |
| **Switch to both-willing** | Viable by size — 2.01× today at 0.75, 1.74× at 0.85. The cost is the promise: **61% of the deck asks the viewer to pay something** (58% at 0.85), bounded at a quarter of their give side and typically 5%. That is a different product, not a tuned one — today's deck promises "trades that gain you value"; this one promises "market-even trades." |
| **Blend** | C1 supplies a blend the PRD did not list: drop the `:4987` package test only, keep the raw-board 1-for-1 veto. ~18% more deck, ~31% user-pays, viewer never asked to downgrade a 1-for-1 they hold a board for. |

Per §6, do not light `bakeoff_serve_interleaved` on this note alone — C1 sizes the decks, it does not measure whether anyone likes them (that is C2).

---

## Sources

- `docs/reviews/2026-08-19-consensus-gate-matrix.md` (branch `audit/consensus-gate-matrix` @ `9026da7`) — the full memo: matrix, per-user and per-shape breakdowns, the five-check proof that the gate manipulation took effect, method, and a players-only cross-check that reproduces the same shape (2.25× at 0.75).
- Gate sites: `backend/trade_service.py:4987` (package `rv − gv` test) and `:1509` / `:5002` (`user_gain_ok_1for1`), both reading `user_gain_epsilon`.
- Prod reads for the served cross-check were read-only (`SET TRANSACTION READ ONLY`, SELECT only, DSN from the gitignored `secrets.local.env`).

## What I could not determine

- **Any absolute forecast of production deck size under both-ways.** The both-ways cells exist only in replay, because served data contains zero user-pays cards by construction. The doubling is a within-replay ratio; what it becomes across all leagues is unmeasured.
- **Why the replay and served one-way columns diverge so widely at 0.85** (83.5% vs 53.0%). "This league's cards are unusually fair" is the stated explanation and is consistent with both fairness distributions, but it was not decomposed further — league size, roster depth and pick mix are all plausible contributors and none was isolated.
- **Whether the 7,105 served baseline reconciles with the PRD's 7,094.** The two counts differ by 11 cards and the window definitions were not compared; nothing here turns on the difference, but it is not explained.
- **What either both-ways deck does to divergence/v3 cards.** Zero coverage — no 2×2 or 3×3 shape appears in any cell, and the 15.5% boarded-pair population is untouched by this measurement. P2 (`user_elo_shrink`) is unmeasured here.
- **Like-rate, acceptance rate, or any behavioural outcome.** C1 counts cards. Whether a 61%-user-pays deck is a deck anyone swipes right on is C2, and needs interleaved serving lit.

No decision, gotcha, mistake or open-question ID was allocated by this work.
