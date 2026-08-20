# Consensus gate matrix — the two both-ways cells

**Date:** 2026-08-19
**Branch:** `audit/consensus-gate-matrix` (from `origin/main` @ `50e0451`)
**Kind:** measurement only. No engine, flag, config or client file was changed.

---

## The question

The consensus path gates twice, in this order
([`backend/trade_service.py:4987`](../../backend/trade_service.py) then `:5017`):

```
if rv - gv < _c("user_gain_epsilon"):        # eps = 0.0 -> user must never pay
    return
...
fairness = min(gv, rv) / max(gv, rv)
if fairness < fairness_threshold:
    return
```

The first test is one-sided: it kills **every** card on which the user would
give more consensus value than they receive. Because it fires at generation,
the served-card population contains zero user-pays cards by construction, and
no query against served data can say what a both-ways deck would look like.
The one-way column was measured directly from prod; the two both-ways cells
below required a replay.

**"Both-ways"** here = drop the one-sided test and let fairness alone gate.
`user_gain_epsilon` is read by the *two* one-sided consensus tests — the
package test at `:4987` and `user_gain_ok_1for1` at `:1509` (the raw-board
1-for-1 ordering test, called at `:5002`) — so setting it to `-1e9` drops the
one-sided family. Both readings are reported: **A** drops the family (fairness
alone gates, the literal "let fairness alone gate"), **B** drops only the
`:4987` package test and leaves the raw-board ordering test at eps = 0.

---

## The matrix

66 pair-runs per cell (6 real boards × 11 league partners), one prod league,
draft picks injected. Counts are **replay counts, not prod counts** — read the
ratios, not the absolute numbers (see Resolution limit).

| Cell | Surviving | % of shipping baseline | User pays | Fairness p10 · p25 · p50 · p75 · p90 |
|---|---|---|---|---|
| 0.50 one-way *(ships today)* | 1,366 | 100% | 0 (0.0%) | .773 · .876 · .944 · .979 · .993 |
| 0.75 one-way | 1,290 | 94.4% | 0 (0.0%) | .826 · .891 · .951 · .981 · .994 |
| 0.85 one-way | 1,141 | 83.5% | 0 (0.0%) | .881 · .916 · .962 · .983 · .995 |
| 0.50 both-ways | 3,090 | 226.2% | 2,018 (65.3%) | .717 · .836 · .940 · .981 · .995 |
| **0.75 both-ways** | **2,739** | **200.5%** | **1,677 (61.2%)** | .814 · .887 · .951 · .983 · .995 |
| **0.85 both-ways** | **2,376** | **173.9%** | **1,383 (58.2%)** | .885 · .923 · .962 · .987 · .996 |

**0.75 both-ways does not collapse the deck. It doubles it** (2.12× the
same-threshold one-way cell; 2.01× what ships today). 0.85 both-ways is still
1.74× today. Neither both-ways cell is anywhere near a collapse; the collapse
risk in this design lives entirely in the one-way column, where 0.85 costs
16.5% of the deck here (and 47% on served data — see the caveat).

Fairness quality does not degrade. At the same threshold the both-ways
distribution is indistinguishable from one-way (0.75: p50 .951 both ways;
0.85: p50 .962 both ways). Both-ways does not add worse cards — it adds cards
of the same fairness on the other side of the ledger.

### How much does the user actually pay?

Share of the give side the user forfeits, on user-pays cards only:

| Cell | median | p75 | p90 | max |
|---|---|---|---|---|
| 0.75 both-ways | 5.3% | 13.0% | 19.5% | **25.0%** |
| 0.85 both-ways | 4.1% | 7.6% | 11.8% | **15.0%** |

The maxima are exactly `1 − threshold`. That is structural, not a coincidence:
with the one-sided test gone, the fairness floor *is* the cap on how badly the
user can be asked to pay. A 0.75 both-ways deck can never propose a card that
asks the user to give up more than a quarter more than they get, and the
typical one asks for 5%.

### Which one-sided test does the work

| thr | C: one-way (prod) | B: drop `:4987` only | A: drop the one-sided family |
|---|---|---|---|
| 0.75 | 1,290 · 0.0% pays | 1,516 (+17.5%) · 30.6% pays | 2,739 (+112%) · 61.2% pays |
| 0.85 | 1,141 · 0.0% pays | 1,375 (+20.5%) · 32.0% pays | 2,376 (+108%) · 58.2% pays |

Most of the expansion is **not** the `:4987` package test. It is
`user_gain_ok_1for1` — the raw-board 1-for-1 ordering test, which vetoes
22,748 of the 42,118 1-for-1s that reach it. Dropping only the package test
buys ~18–20% of deck; dropping both roughly doubles it. These are separable
product decisions and the operator should pick deliberately:

* **B (package test only)** — a modest, conservative change. The deck grows
  ~18%, roughly a third of cards ask the user to pay, and a 1-for-1 still can
  never ask the user to send a player they personally rank above the one they
  receive.
* **A (the family)** — the real "market-even" product. Deck doubles, ~61% of
  cards ask the user to pay, and the user's own board no longer vetoes a
  market-even 1-for-1.

### Where the growth lands

Shapes, 0.75, one-way → both-ways: 1-for-1 838 → 2,301; 2-for-1 452 → 438.
The expansion is **entirely 1-for-1**. User-give-side 2-for-1 consolidations
were already surviving one-way (`package_value_v2`'s crown premium lifts `rv`
on a consolidation) and are still bounded by `consolidation_raw_loss_frac`
(0.15, left live in every cell).

Per-user, 0.75 one-way → both-ways: mattmurf77 246→504, Bcork 131→306,
gdubs10 301→666, jonbonjourvi 190→341, johnstanfield 117→370, MangoPatti
305→552. The expansion is broad, not one board's artifact. The largest
multiple (3.2×) is johnstanfield — the thinnest board in the set (21 swipes).
That follows: a sparse raw board is noisy, and the raw-board ordering test was
vetoing on that noise.

---

## Proof the gate manipulation actually took effect

`trade_optimizer.py:62-63` and `trade_gen_v2.py:118-121` bind these names by
value at import time, so a naive patch of the `trade_service` definition runs
the original and reports a no-op. Five independent checks, all asserted in the
harness rather than eyeballed:

1. **The knob is not a rebind.** `_c` is a *function* that reads
   `trade_service._cfg` at call time; the by-value import copies the function
   object, not the value. The harness mutates `ts._cfg` in place and asserts
   `ts._c(...) == topt._c(...) == tg2._c(...) == eps` before every cell. All
   three see the change.
2. **Kill counter moves to zero.** Instrumented `user_gain_ok_1for1`:
   3,093 vetoes out of 186,581 calls under one-way → **0 out of 226,538**
   under both-ways. A no-op patch would have left 3,093.
3. **User-pays goes 0 → non-zero.** Every one-way cell emits exactly **0**
   cards with `receive_value < give_value`; every both-ways cell emits
   thousands. This is the outcome the gate exists to prevent, measured on the
   emitted cards rather than on the gate.
4. **Card counts move in the right direction and magnitude**
   (1,290 → 2,739 at 0.75), and the call count into the downstream gate rises
   (186,581 → 226,538) because candidates no longer return early at `:4987`.
5. **The right code path ran.** Every cell asserts all cards carry
   `basis == "consensus"`, zero carry `relaxed`, and the `max_cards` cap never
   bound in any of the 66 runs. Partners are constructed with
   `has_rankings=False`, which routes to `_generate_consensus_for_pair` at
   `trade_service.py:4267`.

---

## Method

* Worktree from a freshly fetched `origin/main` @ `50e0451`. Prod is
  **read-only**: `psycopg2`, `set_session(readonly=True)` +
  `SET TRANSACTION READ ONLY`, SELECT only, DSN read from the gitignored
  `secrets.local.env` and scrubbed out of every error path.
* Six real boards rebuilt through the real `RankingService.replay_from_db`
  from prod `swipe_decisions` (1,718 / 799 / 927 / 120 / 42 / 21 swipes),
  with real pins and placement bands; consensus seed from
  `player_value_history` @ 2026-08-19; live `config/features.json`; prod
  `model_config` (144 keys) loaded into both modules' `_cfg`.
* Cards generated through the real `TradeService._generate_trades_impl` with
  `bypass_need_gate=False` — the prod default for an untargeted deck, so the
  G6 R5 need gate is live in every cell.
* Draft picks injected by porting `server._owned_pick_assets` /
  `_inject_owned_picks` (68 pick pseudo-assets, cap 6/team from
  `model_config.picks_pool_cap`, elo = `value_to_elo(pool_value)`). This is
  faithful for this league: it holds 144 platform pick rows and **zero**
  user-asserted rows, so `source='any'` and the contested/orphaned row filter
  are both no-ops.
* Every manipulation is a monkeypatch inside the measuring process. Probe
  scripts stay in the session scratchpad (`scratchpad/matrix/`) and are not
  committed.

Cross-check without picks (players-only): 1,077 / 1,004 / 875 one-way and
2,528 / 2,256 / 1,975 both-ways — same shape, same conclusion (2.25× at 0.75).

---

## Resolution limit — what these numbers can and cannot support

**They can support:** the *direction and rough magnitude* of the both-ways
change (a doubling, not a collapse), the structural fact that fairness caps
the user's loss at exactly `1 − threshold`, the decomposition showing the
raw-board 1-for-1 test is the dominant censor, and the finding that fairness
quality is unchanged.

**They cannot support** any absolute forecast of prod deck size. Specifically:

* **Six boards, one league, 66 pair-runs.** The served-card measurements
  (7,105 baseline) come from many leagues over a window. A replay count is not
  a production count and the two must not be compared as if they were.
* **The one-way column does not reproduce the served one-way column.**
  Replay: 100% / 94.4% / 83.5%. Served: 100% / 89.4% / 53.0%. The 0.85 cell is
  a wide divergence — this league's cards are markedly more fair than the
  served population, so raising the floor costs less here. Any read of the
  both-ways cells as "% of prod deck" inherits that error; the ratios *within*
  this replay are the trustworthy part.
* **Consensus path only.** All 66 pairs are forced onto
  `_generate_consensus_for_pair`. That is the majority path in prod (84.5% of
  served cards) and the one the question is about, but the divergence /v3 path
  is entirely absent, and with it every 2×2 and 3×3 shape. This replay emits
  only 1-for-1 and 2-for-1, because the consensus generator builds nothing
  else.
* **Picks are under-represented.** 36.2% of one-way cards here are
  pick-bearing, against ~55% in prod — a consequence of the shape restriction
  above (picks are most useful as package filler).
* **One pricing deviation.** One of the six users
  (`867830050538598400`) has `pick_pricing_mode = 'market_slots'` in prod; the
  port pins `tier_ladder` (stored `pool_value`) for all six.
* **Today's values.** Boards, rosters and consensus are as of 2026-08-19.

### The D-091 confound: not inherited

[D-091](../../living-memory/DECISIONS.md) recorded that **339 of 2,651 served
cards (12.8%)** in the historical window offered a phantom 2029 pick that did
not exist in the league. **This replay does not inherit it**, for two
independent reasons: the fix has already converged the grid — prod
`draft_picks` for this league now holds seasons 2026–2028 only, 144 rows, no
2029 — and the table was read fresh today. Zero cards in any cell carry a
phantom pick.

The consequence cuts two ways. Because the phantom is absent from *every* cell
equally, it cannot bias the one-way ↔ both-ways comparison, which is the
comparison this memo exists to make. But it does mean the replay's one-way
baseline is not the same population as the 7,105 served cards, which were
generated while phantoms were live — one more reason the absolute counts are
not comparable across the two measurements.

---

## What this feeds

The decision was framed as: *if both-ways at 0.75 collapses the deck it is not
a shippable product, and one-way at 0.75 still is.*

**It does not collapse.** On this evidence 0.75 both-ways is a viable deck by
size — twice today's — and 0.85 both-ways remains 1.74× today, so the fallback
cell is viable too. Deck volume does not decide this.

What decides it is a product question the measurement can only frame: a
0.75 both-ways deck is **61% cards that ask the user to pay** (58% at 0.85).
That is a different product, not a tuned one — today's deck promises "here are
trades that gain you value" and a both-ways deck promises "here are
market-even trades." The measured guardrail is that the payment is small and
hard-bounded: median 5.3% of the give side, and never more than 25% at a 0.75
floor by construction.

If 61% reads as too many, the decomposition offers a middle setting that was
not on the original matrix: drop only the `:4987` package test and keep the
raw-board 1-for-1 ordering veto. At a 0.75 floor that yields a deck ~18%
larger than today's with 31% user-pays cards, at a 0.85 floor ~20% larger with
32% — and in that setting a 1-for-1 still cannot ask the user to send a player
they personally rank above the one they receive.

No decision, gotcha or open-question ID was allocated by this work.
