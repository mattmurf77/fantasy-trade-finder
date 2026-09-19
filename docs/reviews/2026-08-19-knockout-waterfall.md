# Knockout waterfall — every candidate trade, and the rule that killed it (2026-08-19)

> **Status:** point-in-time measurement snapshot, not reference. Per [`docs/reviews/CLAUDE.md`](CLAUDE.md),
> read for context; the code is truth. **No engine line was changed by this work** —
> `git diff origin/main -- backend/ config/ mobile/ web/` is empty, checked at the end.
>
> **Question this answers:** where does the engine exclude trades, and where might it be excluding
> *meaningful* ones? The second half of that question is answered by one column —
> **unique kills**: candidates that exactly one rule rejected, and that every other rule
> would have let through.

---

## Table of Contents
- [What was measured](#what-was-measured)
- [The universe — defining the first bar honestly](#the-universe--defining-the-first-bar-honestly)
- [Headline: the rules that exclude trades nothing else would](#headline-the-rules-that-exclude-trades-nothing-else-would)
- [Reading the waterfall](#reading-the-waterfall)
- [The waterfalls](#the-waterfalls)
- [Arm B vs arm C — comparison](#arm-b-vs-arm-c--comparison)
- [After the last gate: selection, not gating](#after-the-last-gate-selection-not-gating)
- [Proof the counters are real](#proof-the-counters-are-real)
- [Resolution limits and confounds](#resolution-limits-and-confounds)
- [Data files](#data-files)
- [Appendix — full tables](#appendix--full-tables)

---

## What was measured

Three generation paths, all replayed against production data read `SET TRANSACTION READ ONLY`:

| Arm / path | Code | Pairs replayed |
|---|---|---|
| **Arm B — divergence** | `_generate_trades_impl` → `_generate_trades_v2` → `trade_optimizer.generate_pair_trades_v3` | 30 ordered pairs (6 boarded members, both directions) |
| **Arm B — consensus** | `_generate_trades_impl` → `_generate_trades_v2` → `_generate_consensus_for_pair` | 36 pairs (6 boarded users × 6 unboarded league members) |
| **Arm C — `gen_v2`** | `bakeoff_runner.gen_v2_cards` → `trade_gen_v2.generate_league_suggestions` | 30 ordered pairs |

The consensus path is included because it is **84.5% of served traffic**
([the arm-B audit](2026-08-19-armb-audit-consolidated.md)); a report that only walked the
divergence path would describe a sixth of the product. In this league it fires for the six
members who have no board — and, in production, also as the zero-divergence fallback for a
boarded partner (`trade_service.py:4355`). That fallback is switched off in the replay so
each generator's candidates are attributed to the generator that produced them.

**Only one production league can support this exercise.** `member_rankings` grouped by league
gives boarded-member counts of **6, 2, 1, 1, 1, 1, 1** — league `1312140920132497408` is the
only one with more than two boarded members, so it is the only place a divergence pair (let
alone thirty) exists. Every ordered pair in it was run.

Jobs are **untargeted**: no pinned give/receive, no acquire/trade-away positions, no opponent
scope. That matters, because `bypass_need_gate` is derived server-side from exactly those
inputs (`server.py:5207-5211`), so R5 is live here — as it is on the ≈73–80% of production
generations that are untargeted.

Owned draft picks are injected exactly as `server._owned_pick_assets` /
`_inject_owned_picks` do it (top `picks_pool_cap` = 6 per team by `pool_value`, bridged to Elo
`1200 + 6·pick_value`), and their labels resolve through the D-090 slot order, so a current-year
pick reads `2026 1.08` rather than `2026 1st`. 68 picks entered the pools across the 12 rosters.

## The universe — defining the first bar honestly

A waterfall is worthless if its first bar is arbitrary, so here is the definition and its defence.

**The first bar is every candidate the engine enumerates as a trade idea, before any evaluative
rule runs.** For each arm that is:

- **Arm B divergence.** Each side is pruned to the top `v3_pool_size` = **12** assets by
  valuation divergence (`_div = _vo·scale − _uv`, `trade_optimizer.py:392-418`) — literally a
  ranking-difference ranking. Every give-subset of 1–3 × every receive-subset of 1–3 inside
  those pools is then enumerated, and the structural shape rule
  `|give| − |receive| ≤ 1` (`trade_optimizer.py:523`) is applied. That is
  **83,524 candidates per ordered pair, 2,505,720 across the thirty.**
- **Arm B consensus.** The receive pool is the partner's roster filtered to the positions the
  user needs; the give pool is the user's whole roster minus untouchables. Every 1×1 and every
  2×1 over those pools is enumerated (`trade_service.py:5136-5152`). **361,674 candidates.**
- **Arm C.** For each of the top `gen2_centerpiece_top_k` = 5 divergence-positive opponent
  assets, the receive side is the centerpiece plus 0–2 of the top `gen2_recv_extra_pool` = 4
  extras, against every 1–3 subset of the top `gen2_give_pool` = 10 give assets.
  **205,625 candidates.**

**Why this is the honest bar, and what it hides.** For the two divergence arms the universe is
*already* a ranking-diff selection — that is exactly what makes it the right first bar for a
question phrased as "all trade ideas that match on ranking diff", and it is also the single
biggest exclusion in the whole system, sitting **before** anything a waterfall can see. Rosters in
this league run from 18 to 34 tradeable assets (median 33, picks included), so for most pairs the 12-deep prune is a real cut and for the
thinnest roster it barely binds at all; the report cannot price what the prune removed, because
the engine never scores those combinations. Read the waterfall as "of the trades the engine
considers, here is what kills them", not "of all trades that exist".

Two smaller pre-gate exclusions are named for the same reason:

- the **shape rule** (`|give| − |receive| ≤ 1`), which removes 5,280 combinations per divergence
  pair — 158,400 across the thirty — before any rule fires;
- the consensus path's **receive-pool need filter**, which restricts the partner's roster to the
  user's needed positions before enumeration. It is a positional-need gate acting at pool
  construction, so it never appears in a kill count, and it is upstream of R5 doing the same
  thing again at candidate level.

Picks are assets throughout. The **pick-horizon filter (D-091)** is not a knockout rule — it
governs which picks exist as rows at all (`database.py:9352-9414`) — so it is upstream of this
entire exercise and is inherited, not measured.

## Headline: the rules that exclude trades nothing else would

This is the number the exercise was run for. A rule with a large first-kill count is not
necessarily excluding anything: if three later rules would have rejected the same candidate, the
rule is redundant and removing it changes nothing. The rules below are the opposite — for these
counts, this rule is the **only** thing between the user and the trade.

| Rule | Arm / path | Unique kills | Share of that universe |
|---|---|---:|---:|
| #141 junk-filler gate | B_divergence | **44,529** | 1.777% |
| #141 junk-filler gate | B_consensus | **8,348** | 2.308% |
| Dual-surplus floor (60, marginal on) | B_divergence | **5,429** | 0.217% |
| #141 junk-filler gate | C_gen_v2 | **4,938** | 2.401% |
| G6 R1 `overpay_ok` | B_consensus | **2,599** | 0.719% |
| G6 R5 `need_gate_ok` | B_consensus | **1,919** | 0.531% |
| Consensus one-way gate `rv − gv < ε` (ε = 0) | B_consensus | **1,156** | 0.320% |
| #108 raw-board 1-for-1 veto | B_consensus | **913** | 0.252% |
| G6 R5 `need_gate_ok` | B_divergence | **827** | 0.033% |
| G6 R1 `overpay_ok` | B_divergence | **697** | 0.028% |
| Consensus fairness + range-overlap escape | B_consensus | **662** | 0.183% |
| Roster feasibility, both sides | B_divergence | **557** | 0.022% |
| G6 R2 `pos_net_ok` | B_divergence | **412** | 0.016% |
| G6 R2 `pos_net_ok` | B_consensus | **271** | 0.075% |
| Consensus fairness band (0.15) | C_gen_v2 | **269** | 0.131% |
| #227 pick-for-pick churn ban | B_consensus | **255** | 0.071% |
| Dual-board ε-gain — user side (100) | C_gen_v2 | **253** | 0.123% |
| Roster feasibility, both sides | C_gen_v2 | **134** | 0.065% |
| G6 #341 net-position cap | C_gen_v2 | **92** | 0.045% |
| Dual-board ε-gain — partner side (100) | C_gen_v2 | **31** | 0.015% |
| G6 R3 `pick_gap_ok` | B_divergence | **20** | 0.001% |
| #108 raw-board 1-for-1 veto | B_divergence | **13** | 0.001% |
| Consensus fairness + range-overlap escape | B_divergence | **4** | 0.000% |
| G6 #339 pick-gap band | C_gen_v2 | **2** | 0.001% |

Across 3,073,019 candidates in three pipelines, **74,330 are killed by exactly one rule** — 2.4%.
Everything else the engine rejects, it rejects several times over. Six things stand out.

**1. `#141`, the junk-filler gate, is the largest unique excluder in every arm — by more than
all other rules put together.** In each of the three pipelines it uniquely kills more than every
other rule in that pipeline *combined*: **44,529 vs 7,959** (arm B divergence), **8,348 vs 7,775**
(arm B consensus), **4,938 vs 781** (arm C).
`filler_ok` (`trade_service.py:1602-1636`) requires every non-headliner piece to
clear both `filler_min_frac` = 0.25 of its side's headliner **and** the absolute
`asset_floor_abs` = 450, judged on `max(user board, partner board)`. Single-asset sides pass
untouched, so this is entirely a tax on multi-asset packages — and multi-asset packages are
where consolidation, the shape managers actually want, lives. It is worth saying plainly: the
rule was added because suggestions were padding both sides with junk, and the audit's own
measurement showed **deleting it makes one-sidedness worse (86.9% → 100%)**. The finding here is
not "delete it" — it is that the size of what it alone removes has never been priced, and it is
by far the largest number in this report.

**2. The dual-surplus floor is nearly pure unique exclusion on the divergence path.** It
first-kills only 5,579 candidates — 0.22% of the universe — but **5,429 of those (97.3%) are
candidates no other rule objects to**. Both sides must gain at least
`min_side_surplus_marginal` = 60 on their **own** board. This is the mutual-gain guarantee, so it
*should* be the last thing standing — but it also means the 60-point floor is doing real,
unshared work, and it is a round number that has never been calibrated against anything. It is
the single highest-leverage knob in the report: it is small, isolated, and every candidate it
removes is otherwise clean.

**3. `G6 R5`, the positional-need gate, is a genuine unique excluder in both arm-B paths — and
arm C does not have it at all.** 827 on the divergence path, **1,919 on the consensus path** —
where it is the third-largest unique excluder. This corroborates the arm-B audit's finding from a
completely different direction: R5 takes no opponent argument (`trade_service.py:1824-1826`), so
it kills trades that fill both sides' holes. `trade_gen_v2` deliberately declined to port it
(`trade_gen_v2.py:573-579`: "gen-v2 optimizes need in the objective, and a hard need filter would
double-penalize"). Two live pipelines disagree about whether this rule should exist, and this
report puts a number on the disagreement.

**4. The consensus one-way gate is a smaller unique excluder than its first-kill count suggests.**
`rv − gv < ε` is by far the biggest first-killer on the consensus path — 259,179 of 361,674, i.e.
**71.7% of the universe** — but only **1,156** of those kills are unique. The other ~258,000 would
have died to fairness, #141 or R1 anyway. That does not make the gate defensible (it is still the
line that makes the user win on 84.5% of served cards); it means removing it alone would surface
far fewer new trades than its bar height implies. The arm-B audit reached the same conclusion by
ablation; this is the mechanism behind that result.

And two negative findings that matter as much, because they tell you where *not* to look:

**5. The Elo-gap guard first-kills half the divergence universe and uniquely kills nothing.**
`trade_elo_gap_max` = 250 rejects any package whose best give and best receive sit more than 250
shrunk-Elo apart. At **1,250,720 first-kills (49.91%)** it is the single largest first-killer in
the report — and its unique-kill count is **zero**. Every candidate it removes is removed by
something else too. As a knockout rule it is free; its only cost is the CPU the later rules would
have spent. Anyone tuning gates should start by knowing this one cannot be the reason a trade is
missing.

**6. Four rules are wholly redundant where they sit.** `consolidation_raw_loss_frac` (consensus)
would reject 236,441 candidates on its own and first-kills **zero** — the ε-gate above it always
gets there first. `G6 R3`'s pick-gap band on the consensus path: 26,706 would-fail, **zero**
first-kills. `#227` pick-for-pick churn: zero unique kills on the divergence path and it **never
fires at all** in arm C (0 of 205,625). These are not bugs; they are rules whose stated job is
already done by something upstream, and they can be reasoned about as free.

### What a uniquely-killed trade actually looks like

Five real rows from the sheet, one per rule, chosen as the largest package that rule alone
rejected. "Gains" are each side's own-board surplus.

| Rule | Trade | Numbers |
|---|---|---|
| **G6 R5** need gate | MangoPatti gives *Josh Allen + A.J. Brown + Parker Washington*, gets *Rome Odunze + Trevor Lawrence + 2026 1.05 (from Bcork)* | consensus 8,881 → 7,275; gains **+74 / +3,249** |
| **Dual-surplus floor** | johnstanfield gives *Tetairoa McMillan + Brock Bowers + Luther Burden*, gets *CeeDee Lamb + A.J. Brown + Chris Olave* | consensus 16,208 → 15,957; gains **+20 / +4,773** |
| **#141** junk filler | mattmurf77 gives *Jahmyr Gibbs + Ashton Jeanty + Brenton Strange*, gets *Tyler Warren + Malik Nabers + Derrick Henry* | consensus 16,510 → 12,104; gains **+8,850 / +15,955** |
| **#108** raw-board veto | mattmurf77 gives *Ashton Jeanty*, gets *Amon-Ra St. Brown* | consensus 7,940 → 8,289 — **consensus says the user gains 349**, the user's own board says no |
| **Arm C ε-gain (user)** | johnstanfield gives *Caleb Williams + Tetairoa McMillan + Brock Bowers*, gets *CeeDee Lamb + James Cook* | gains **−684 / +3,681** |

Read them together and a pattern falls out: the uniquely-killed trades are overwhelmingly
**large multi-asset packages where one side's surplus is thin or slightly negative**. That is the
consolidation shape — many pieces for fewer, better ones. Two of the five rules above (the
surplus floor and arm C's ε-gain) are doing exactly what they were built to do, and the
#141 example is a genuinely junk-padded package. The R5 row is the one that should trouble
anyone: MangoPatti gains only +74 but the partner gains +3,249, and R5's stated reason for
killing it has nothing to do with either number.

## Reading the waterfall

Three columns, three different questions:

- **First-kill** — the waterfall proper. The rule that *actually* rejected the candidate, in real
  execution order, verified from code rather than assumed. Each rule only ever sees what the
  rules above it let through, so these are the numbers that sum to the universe.
- **Would also fail** — order-free. How many candidates in the *whole* universe that rule rejects
  when asked independently. A rule late in the ladder can have a huge number here and a tiny
  first-kill count; that is the signature of redundancy, not harmlessness.
- **Unique kills** — candidates where that rule is the only failing rule. This is the exclusion
  question.

The two are produced from the same pass: every gate was wrapped so it reports its true verdict
and then returns a forced pass, letting each candidate walk the entire ladder.

## The waterfalls

#### Arm B — divergence path (v3 optimizer)

| # | Rule | Where | First-kill | % of universe | Would also fail | **Unique kills** | Left |
|---|---|---|---:|---:|---:|---:|---:|
| 0 | *Candidates admitted on ranking diff alone* | — | — | — | — | — | **2,505,720** |
| 1 | `trade_elo_gap_max` Elo-gap guard (250) | `trade_optimizer.py:527` | 1,250,720 | 49.915% | 1,250,720 | 0 | 1,255,000 |
| 2 | #108 raw-board 1-for-1 veto | `trade_optimizer.py:535` → `trade_service.py:1575` | 981 | 0.039% | 2,635 | **13** | 1,254,019 |
| 3 | #227 pick-for-pick churn ban | `trade_optimizer.py:542` | 3,373 | 0.135% | 3,489 | 0 | 1,250,646 |
| 4 | #141 junk-filler gate | `trade_optimizer.py:547` | 1,200,451 | 47.908% | 2,434,743 | **44,529** | 50,195 |
| 5 | G6 R1 `overpay_ok` | `trade_optimizer.py:553` → `trade_service.py:4210` | 35,014 | 1.397% | 2,078,626 | **697** | 15,181 |
| 6 | G6 R2 `pos_net_ok` | `trade_service.py:4213` | 2,454 | 0.098% | 1,066,206 | **412** | 12,727 |
| 7 | G6 R3 `pick_gap_ok` | `trade_service.py:4216` | 548 | 0.022% | 166,455 | **20** | 12,179 |
| 8 | G6 R5 `need_gate_ok` | `trade_service.py:4219` | 3,058 | 0.122% | 451,963 | **827** | 9,121 |
| 9 | Roster feasibility, both sides | `trade_optimizer.py:556` | 1,711 | 0.068% | 209,570 | **557** | 7,410 |
| 10 | Dual-surplus floor (60, marginal on) | `trade_optimizer.py:560` | 5,579 | 0.223% | 2,181,490 | **5,429** | 1,831 |
| 11 | Consensus fairness + range-overlap escape | `trade_optimizer.py:563` | 4 | 0.000% | 1,640,957 | **4** | 1,827 |
| — | **Survive every rule** | | | | | | **1,827** |

Total unique kills: **52,488** (2.09% of the universe).

#### Arm B — consensus path

| # | Rule | Where | First-kill | % of universe | Would also fail | **Unique kills** | Left |
|---|---|---|---:|---:|---:|---:|---:|
| 0 | *Candidates admitted on ranking diff alone* | — | — | — | — | — | **361,674** |
| 1 | Consensus one-way gate `rv − gv < ε` (ε = 0) | `trade_service.py:5100` | 259,179 | 71.661% | 259,179 | **1,156** | 102,495 |
| 2 | `consolidation_raw_loss_frac` (0.15) | `trade_service.py:5108-5112` | 0 | 0.000% | 236,441 | 0 | 102,495 |
| 3 | #108 raw-board 1-for-1 veto | `trade_service.py:5115` | 1,805 | 0.499% | 11,888 | **913** | 100,690 |
| 4 | #227 pick-for-pick churn ban | `trade_service.py:5118` | 452 | 0.125% | 6,309 | **255** | 100,238 |
| 5 | #141 junk-filler gate | `trade_service.py:5123` | 77,128 | 21.325% | 258,408 | **8,348** | 23,110 |
| 6 | G6 R1 `overpay_ok` | `trade_service.py:5127` → `:4210` | 14,888 | 4.116% | 263,980 | **2,599** | 8,222 |
| 7 | G6 R2 `pos_net_ok` | `trade_service.py:4213` | 559 | 0.155% | 57,269 | **271** | 7,663 |
| 8 | G6 R3 `pick_gap_ok` | `trade_service.py:4216` | 0 | 0.000% | 26,706 | 0 | 7,663 |
| 9 | G6 R5 `need_gate_ok` | `trade_service.py:4219` | 2,342 | 0.648% | 92,690 | **1,919** | 5,321 |
| 10 | Consensus fairness + range-overlap escape | `trade_service.py:5131` | 662 | 0.183% | 251,377 | **662** | 4,659 |
| — | **Survive every rule** | | | | | | **4,659** |

Total unique kills: **16,123** (4.46% of the universe).

#### Arm C — `trade_gen_v2`

| # | Rule | Where | First-kill | % of universe | Would also fail | **Unique kills** | Left |
|---|---|---|---:|---:|---:|---:|---:|
| 0 | *Candidates admitted on ranking diff alone* | — | — | — | — | — | **205,625** |
| 1 | #141 junk-filler gate | `trade_gen_v2.py:598` | 192,827 | 93.776% | 192,827 | **4,938** | 12,798 |
| 2 | #227 pick-for-pick churn ban | `trade_gen_v2.py:601` | 0 | 0.000% | 0 | 0 | 12,798 |
| 3 | G6 #341 net-position cap | `trade_gen_v2.py:609` | 3,881 | 1.887% | 82,507 | **92** | 8,917 |
| 4 | G6 #339 pick-gap band | `trade_gen_v2.py:612` | 241 | 0.117% | 4,283 | **2** | 8,676 |
| 5 | Roster feasibility, both sides | `trade_gen_v2.py:619-626` | 1,294 | 0.629% | 30,353 | **134** | 7,382 |
| 6 | Dual-board ε-gain — user side (100) | `trade_gen_v2.py:632` | 2,467 | 1.200% | 68,009 | **253** | 4,915 |
| 7 | Dual-board ε-gain — partner side (100) | `trade_gen_v2.py:636` | 4,459 | 2.169% | 112,938 | **31** | 456 |
| 8 | Consensus fairness band (0.15) | `trade_gen_v2.py:645` | 269 | 0.131% | 183,467 | **269** | 187 |
| — | **Survive every rule** | | | | | | **118** |

Total unique kills: **5,719** (2.78% of the universe).

## Arm B vs arm C — comparison

Their rule sets genuinely differ, so the taxonomies are reported separately above. The
comparison worth drawing is which rules exist at all:

| Rule | Arm B divergence | Arm B consensus | Arm C |
|---|---|---|---|
| #141 junk filler | yes | yes | yes |
| #227 pick-for-pick churn | yes | yes | yes |
| G6 R2 net-position cap | yes | yes | yes (`g6_pos_net_ok`) |
| G6 R3 pick-gap band | yes | yes | yes (`g6_pick_gap_ok`) |
| Roster feasibility | yes | **no** | yes |
| G6 R1 overpay ceiling | yes | yes | **no** |
| G6 R5 positional need | yes | yes | **no — deliberately** |
| #108 raw-board 1-for-1 veto | yes | yes | **no** |
| Elo-gap guard | yes | **no** | **no** |
| Mutual-gain floor | `min_side_surplus` on own boards | **no** — replaced by the one-way `rv − gv ≥ ε` | `gen2_epsilon` on own boards, both sides |
| Fairness | consensus ratio + range-overlap escape, floor 0.50 | consensus ratio, floor 0.50 | ±`gen2_band` = 0.15 on consolidation-discounted consensus |
| Consolidation discount | `package_value_v2` | `package_value_v2` + `consolidation_raw_loss_frac` | `consolidated_value` (γ 1.5, floor 0.15) |

The structural difference is the mutual-gain test. Arm B's consensus path has **no partner
surplus test of any kind** — it has a one-way test that the *user* must not lose, which is why
that path's biggest first-killer is the epsilon gate and why the audit found the user pays on
0 of 7,094 consensus cards. Arm C gates both sides on their own boards. Arm B's divergence path
does too. Consensus is the odd one out, and it is the majority of the product.

The other structural difference: **arm C has no `feasibility`-free path and no overpay ceiling**,
so its only defence against a lopsided package is the ±15% consensus band — which, per the
tables, is almost entirely redundant with the ε-gates ahead of it.

## After the last gate: selection, not gating

Everything below acts on candidates that already cleared **every** rule. These are budgets and
diversity caps, not knockout rules — but they remove far more surviving trades than most of the
gates do, and any conversation about "we are excluding meaningful trades" that stops at the gates
is missing the larger cut.

**divergence**

| Stage | Cards left | Dropped |
|---|---:|---:|
| gates only | 1,827 |  |
| + v3 diversity | 161 | 1,666 |
| + max_per_opponent=5 | 79 | 82 |
| + past-decision & R4 | 72 | 7 |
| + C4 headliner cap | 65 | 7 |
| + C4b give-headliner cap | 63 | 2 |

**consensus**

| Stage | Cards left | Dropped |
|---|---:|---:|
| gates only | 4,659 |  |
| + v3 diversity | 4,659 | 0 |
| + max_per_opponent=5 | 180 | 4,479 |
| + past-decision & R4 | 158 | 22 |
| + C4 headliner cap | 128 | 30 |
| + C4b give-headliner cap | 124 | 4 |

The `v3_diversity_max_overlap` = 0.4 greedy pass is the striking one: it removes the large
majority of everything that survived the entire divergence gate ladder. It exists for a good
reason (exact enumeration surfaces every sibling of a strong core, so a plain top-K returns K
near-duplicates), but it is, by a wide margin, the biggest single reducer of *defensible* trades
in the divergence pipeline — larger than every gate except #141.

## Proof the counters are real

`trade_optimizer.py` and `trade_gen_v2.py` bind gate functions **by value** at import
(`trade_optimizer.py:53-71`, `trade_gen_v2.py:118-137`). An instrumentation that patched only
the `trade_service` definition would measure a perfect no-op. Every wrapper here is installed in
the namespace that actually calls it, and three independent checks confirm the counters moved:

1. **Call-count assertions.** Every wrapper's invocation count is asserted equal to the candidate
   count before any number is reported (`run.py:60-61`, `:73`, `:89`). A silent no-op fails the run.
2. **Set identity against an uninstrumented pass (arm B divergence).** A second pass runs the same
   thirty pairs at real config with the wrappers reporting real verdicts. The set of candidates
   this harness says survives every rule is **identical, in both directions**, to the set the real
   engine scores. That is the strongest available check: if any recomputed inline gate
   (`min_side_surplus`, the Elo-gap guard) were wrong, the two sets would differ.
3. **Agreement with the engine's own counters (arm C).** `trade_gen_v2` already ships
   `GenerationReport.kill_counts()` — the pattern this exercise was told to mirror rather than
   reinvent. The harness's first-kill counts match it exactly, stage for stage, including
   `S2_considered`.

| Engine counter | Engine value | Harness first-kill | Match |
|---|---:|---:|---|
| `S3a_composition` | 192,827 | 192,827 | yes |
| `S3a_net_cap` | 3,881 | 3,881 | yes |
| `S3a_pick_band` | 241 | 241 | yes |
| `S3b_feasibility` | 1,294 | 1,294 | yes |
| `S3c_dual_board_ir` | 6,926 | 6,926 | yes |
| `S3d_fairness_band` | 269 | 269 | yes |
| `S2_considered` | 205,625 | 205,625 | yes |

One measurement bug was found and fixed mid-flight, and is worth recording because it is the same
class of trap: `user_gain_epsilon` is read by **both** consensus one-way tests — the inline
`rv − gv < ε` at `trade_service.py:5100` **and** `user_gain_ok_1for1` itself
(`trade_service.py:1599`). Neutralising the knob to measure the first silently neutralised #108
as well, and #108's kill count read a clean, plausible zero. It is now restored around that one
call. A zero is not evidence a gate does not fire.

## Resolution limits and confounds

- **One league, six boards, 30 ordered divergence pairs and 36 consensus pairs.** These are
  **replay counts, not production counts**. They describe this league's rosters and boards; the
  *ratios* are informative, the absolute numbers are not extrapolable.
- **Replay, not history.** Boards were rebuilt through the real `RankingService.replay_from_db`
  from current swipe data against the 2026-08-19 consensus snapshot, and picks come from the
  current `draft_picks` grid. So the **D-091 phantom-pick confound does not apply here**: 12.8%
  of *historically served* cards contained picks that did not exist in the league, but nothing in
  this report is drawn from served impressions.
- **Sweeteners are excluded.** v3's 3.4 sweetener pass rescues near-misses by adding a cheap
  asset. It is a rescue mechanism, not a knockout rule, and the instrumented pass suppresses it
  (a candidate cannot be recorded as killed and then un-killed by a different package).
- **Arm C does not receive `placements`.** `bakeoff_runner.gen_v2_cards` passes `confidence` but
  no placement bands, so arm C prices the user board without the D-085 tier clamp that arm B
  applies. That is a property of the bake-off harness, not of the generator, and it is reproduced
  faithfully rather than corrected.
- **`admit_metric` for the divergence arm is recomputed in-harness**, replicating
  `trade_optimizer`'s `_div` prune key. It is a reporting column only; no verdict depends on it.
- **`consensus_both_ways` and `consensus_fairness_floor` are both 0.0** (live default), so the
  consensus path's 1×2 shapes are unreachable and the fairness floor is the caller's 0.50.
  Production holds 6,635 `1x1` and 459 `2x1` cards and exactly zero `1x2`; this replay reproduces
  that — no `1x2` candidate is ever enumerated on the consensus path.

## Data files

All under [`2026-08-19-knockout-waterfall/`](2026-08-19-knockout-waterfall/) — see its
[README](2026-08-19-knockout-waterfall/README.md) for the full column dictionary.

| File | Rows | Size |
|---|---:|---:|
| [`waterfall.html`](2026-08-19-knockout-waterfall/waterfall.html) — self-contained view | — | — |
| [`knockout-all-candidates.csv.gz`](2026-08-19-knockout-waterfall/knockout-all-candidates.csv.gz) — **every** candidate, all arms, all shapes, no sampling | **3,073,019** | 44.0 MB |
| [`knockout-notable.csv.gz`](2026-08-19-knockout-waterfall/knockout-notable.csv.gz) — unique-kill rows + survivors, with readable names | 81,003 | 1.4 MB |
| [`knockout-survivors.csv`](2026-08-19-knockout-waterfall/knockout-survivors.csv) — survivors only, uncompressed | 6,673 | 1.14 MB |
| [`assets.csv`](2026-08-19-knockout-waterfall/assets.csv) — id → name/position, picks with D-090 slot labels | 693 | — |
| [`summary.json`](2026-08-19-knockout-waterfall/summary.json) — every counter, machine-readable | — | — |

The full sheet is **complete — nothing was sampled**. It carries asset ids rather than names to
keep it committable; join `assets.csv` for names. The notable sheet is a *defined filter* of it
(every candidate with exactly one failing rule, plus every survivor), not a sample, and carries
names inline.

## Appendix — full tables

### Shapes

**B_divergence**

| Shape | Candidates | Survive | Dominant first-killer |
|---|---:|---:|---|
| `3x3` | 1,452,000 | 595 | R0_141_filler (740,464) |
| `2x3` | 435,600 | 178 | gap_max (220,143) |
| `3x2` | 435,600 | 545 | gap_max (235,973) |
| `2x2` | 130,680 | 255 | gap_max (71,001) |
| `1x2` | 23,760 | 43 | gap_max (13,000) |
| `2x1` | 23,760 | 176 | gap_max (14,534) |
| `1x1` | 4,320 | 35 | gap_max (2,366) |

**B_consensus**

| Shape | Candidates | Survive | Dominant first-killer |
|---|---:|---:|---|
| `2x1` | 339,015 | 2,036 | consensus_eps (248,738) |
| `1x1` | 22,659 | 2,623 | consensus_eps (10,441) |

**C_gen_v2**

| Shape | Candidates | Survive | Dominant first-killer |
|---|---:|---:|---|
| `3x3` | 73,800 | 6 | S3a_141_filler (72,825) |
| `3x2` | 52,560 | 20 | S3a_141_filler (50,912) |
| `2x3` | 27,675 | 30 | S3a_141_filler (26,487) |
| `2x2` | 19,710 | 24 | S3a_141_filler (17,982) |
| `3x1` | 14,640 | 16 | S3a_141_filler (13,142) |
| `1x3` | 6,150 | 9 | S3a_141_filler (4,740) |
| `2x1` | 5,490 | 32 | S3a_141_filler (4,099) |
| `1x2` | 4,380 | 34 | S3a_141_filler (2,640) |
| `1x1` | 1,220 | 16 | S3c_dual_eps_opp (602) |

### Per-user (first-killer mix)

**B_divergence**

| User | Candidates | Survive | gap_max | R0_108_1for1 | R0_227_pickswap | R0_141_filler | G6_R1_overpay | G6_R2_posnet | G6_R3_pickgap | G6_R5_need | feasibility | min_side_surplus | fairness |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Bcork | 417,620 | 99 | 223,036 | 102 | 1,271 | 187,391 | 3,216 | 66 | 116 | 10 | 803 | 1,510 | 0 |
| MangoPatti | 417,620 | 353 | 189,012 | 185 | 193 | 214,149 | 9,761 | 1,199 | 123 | 2,126 | 0 | 518 | 1 |
| gdubs10 | 417,620 | 124 | 217,489 | 239 | 484 | 193,006 | 4,703 | 277 | 69 | 509 | 161 | 559 | 0 |
| johnstanfield | 417,620 | 848 | 187,102 | 158 | 450 | 215,594 | 10,019 | 694 | 210 | 0 | 680 | 1,862 | 3 |
| jonbonjourvi | 417,620 | 383 | 229,983 | 109 | 972 | 179,287 | 5,487 | 112 | 26 | 305 | 45 | 911 | 0 |
| mattmurf77 | 417,620 | 20 | 204,098 | 188 | 3 | 211,024 | 1,828 | 106 | 4 | 108 | 22 | 219 | 0 |

**B_consensus**

| User | Candidates | Survive | consensus_eps | consolidation_loss | R0_108_1for1 | R0_227_pickswap | R0_141_filler | G6_R1_overpay | G6_R2_posnet | G6_R3_pickgap | G6_R5_need | fairness |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Bcork | 14,742 | 379 | 10,395 | 0 | 1 | 0 | 3,449 | 461 | 12 | 0 | 0 | 45 |
| MangoPatti | 95,931 | 1,116 | 70,715 | 0 | 15 | 129 | 17,860 | 4,773 | 186 | 0 | 1,003 | 134 |
| gdubs10 | 101,745 | 1,320 | 75,707 | 0 | 466 | 144 | 17,664 | 5,277 | 299 | 0 | 761 | 107 |
| johnstanfield | 18,270 | 334 | 13,088 | 0 | 408 | 0 | 4,112 | 313 | 5 | 0 | 0 | 10 |
| jonbonjourvi | 29,241 | 571 | 24,581 | 0 | 238 | 107 | 2,447 | 1,155 | 17 | 0 | 98 | 27 |
| mattmurf77 | 101,745 | 939 | 64,693 | 0 | 677 | 72 | 31,596 | 2,909 | 40 | 0 | 480 | 339 |

**C_gen_v2**

| User | Candidates | Survive | S3a_141_filler | S3a_227_pickswap | S3a_net_cap | S3a_pick_band | S3b_feasibility | S3c_dual_eps_user | S3c_dual_eps_opp | S3d_fairness_band |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Bcork | 38,500 | 20 | 36,245 | 0 | 626 | 35 | 265 | 340 | 913 | 56 |
| MangoPatti | 30,275 | 32 | 28,321 | 0 | 729 | 31 | 60 | 485 | 536 | 81 |
| gdubs10 | 23,625 | 31 | 21,902 | 0 | 695 | 51 | 31 | 319 | 558 | 38 |
| johnstanfield | 38,675 | 23 | 35,838 | 0 | 866 | 50 | 529 | 620 | 680 | 69 |
| jonbonjourvi | 31,150 | 60 | 28,047 | 0 | 769 | 74 | 361 | 457 | 1,364 | 18 |
| mattmurf77 | 43,400 | 21 | 42,474 | 0 | 196 | 0 | 48 | 246 | 408 | 7 |
