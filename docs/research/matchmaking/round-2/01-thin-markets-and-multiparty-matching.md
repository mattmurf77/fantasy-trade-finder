# Thin Markets and Multi-Party Matching

> Research memo — Round 2, Topic 01 (flagged by Round 1 as the top follow-up gap). How matching systems work when the pool is small and the trade is barter: kidney exchange, swap marketplaces, stable-matching variants for one-sided pools, and the batch-vs-greedy timing literature. Everything is read against the FTF setting: a dynasty league is a **closed 10–12 participant two-sided barter market**, a 2-team trade is a pairwise exchange, a 3-team trade is a 3-cycle, and "when do we surface suggestions" is exactly the match-run cadence question transplant networks have fought over for 15 years.
>
> **Date:** 2026-08-15
> **Confidence legend:** `[high]` = peer-reviewed result, replicated or field-deployed; `[medium]` = single peer-reviewed source or strong empirical study; `[low]` = trade press, blog, or my own inference/extrapolation to the FTF setting (flagged as such).

---

## Table of contents

1. [Executive summary](#executive-summary)
2. [Kidney exchange: the canonical thin-market barter system](#kidney-exchange)
3. [Barter and swap marketplaces](#barter-and-swap-marketplaces)
4. [Stable matching in small one-sided pools](#stable-matching-in-small-one-sided-pools)
5. [NRMP couples and rural hospitals: how stability degrades](#nrmp-couples-and-rural-hospitals)
6. [Batch vs streaming: the match-run timing literature](#batch-vs-streaming)
7. [Simulating small matching markets](#simulating-small-matching-markets)
8. [Best practices](#best-practices)
9. [Antipatterns](#antipatterns)
10. [What matters most (ranked)](#what-matters-most-ranked)
11. [What doesn't matter (even though it seems like it should)](#what-doesnt-matter)
12. [Transfer notes for FTF](#transfer-notes-for-ftf)
13. [Not researched / follow-up topics](#not-researched--follow-up-topics)
14. [Sources](#sources)

---

## Executive summary

Five findings dominate:

1. **2-way + 3-way exchanges capture essentially all the efficiency available in a barter pool; 4-way+ adds almost nothing.** Roth–Sönmez–Ünver proved this analytically and by simulation for kidney exchange (AER 2007), and every fielded exchange program on earth caps cycles at 2–3. `[high]` For FTF: build 2-team and 3-team trade discovery; do not build 4-team.

2. **The binding constraint on cycle size is not compute — it's coordination failure.** Kidney cycles must execute simultaneously because any participant can renege after receiving and before giving; every extra party multiplies the chance the whole thing collapses. Field data: **up to 44% of proposed exchange arcs fail** post-match (crossmatch/dropout), and in Canadian data **62% of 6-transplant cycles/chains failed** outright. Chains (started by an altruistic donor who wants nothing back) escape simultaneity and can be long. `[high]` FTF has no altruistic donors — every trade is a cycle — so the 2–3 cap binds even harder.

3. **The batching-vs-greedy question is settled for thin, sparse markets: match greedily; batching does not thicken your way to more matches.** Akbarpour–Li–Oveis Gharan (JPE 2020): waiting helps *only if* you can see who is about to leave; otherwise greedy is near-optimal. Ashlagi et al. on real registry data (AJT 2018): among periodic policies, the **highest** match-run frequency performs best; longer batching intervals did not increase transplants. The 2022 "Superiority of Instantaneous Decisions in Thin Dynamic Matching Markets" result extends this: with guaranteed sojourn times, instantaneous matching is almost optimal *specifically in thin markets*. `[high]` For FTF: recompute suggestions on every roster/board change; don't hoard liquidity for a weekly "match day" on efficiency grounds (there may still be UX-cadence reasons to batch *presentation* — see [What doesn't matter](#what-doesnt-matter)).

4. **Stability is the wrong North Star in a 12-person one-sided pool.** The league is a stable-roommates-shaped market (one pool, anyone can match with anyone), and stable roommates instances simply fail to have stable solutions at material rates: with random preferences the existence probability is ≈96% at n=4, ≈89% at n=10, **≈87.6% at n=12**, decaying like n^(-1/4). Minimizing blocking pairs when no stable matching exists is NP-hard. `[high]` Fielded thin-market systems (kidney exchange) dropped stability entirely in favor of **maximum-weight packing with priorities** — that is the right objective family for FTF too.

5. **Plan for proposal failure as a first-class design input, not an edge case.** The kidney literature's most transferable operational ideas: pre-screen edges before proposing (ask "would you even consider X?" before building a match on it), optimize for *expected* completed matches under known failure probabilities rather than nominal matches, and keep recourse plans (backup 2-cycles inside 3-cycles). `[high]` This maps 1:1 onto FTF accept/reject signals and fallback trade suggestions.

---

## Kidney exchange

### Why it's the right analogue

Kidney exchange is a barter market with: indivisible goods you can't buy for money, binary-ish compatibility, a thin pool, participants who each bring one asset and one need, and a central algorithmic clearinghouse that *proposes* trades which participants can still refuse. That is structurally closer to a dynasty league than any dating app is — dating apps match streams of strangers; kidney exchange packs cycles among a small registered pool.

### The mechanics

- **Pairwise (2-way) exchange:** donor A → patient B, donor B → patient A. The original mechanism design (Roth–Sönmez–Ünver, QJE 2004; JET 2005) began with pairwise-only exchange under 0/1 preferences, using priority mechanisms adapted from the top-trading-cycles tradition. `[high]`
- **3-way cycles:** shown to matter enormously. In the AER 2007 paper ("Efficient Kidney Exchange: Coincidence of Wants in Markets with Compatibility-Based Preferences"), moving from 2-way-only to 2+3-way adds a large block of transplants; adding 4-way adds a sliver; beyond that, nothing. The theory result: in a type-compatibility model, the largest exchange ever needed for full efficiency equals the number of "types" — and in practice the marginal value is concentrated at 3. `[high]`
- **Chains:** an altruistic (non-directed) donor donates first and wants nothing back, so the chain can execute **non-simultaneously** — each pair receives a kidney before its donor gives one. Rees et al. (NEJM 2009) reported a 10-transplant chain executed over 8 months with bridge donors waiting up to 5 months; key quote of the design logic: if a bridge donor reneges, the next pair "has not yet donated" and can simply be rematched — the failure is a lost *option*, not a lost *kidney*. None of the bridge donors in that first chain reneged. Long chains are now where most US exchange transplants come from. `[high]`

### Why cycles are capped at 2–3 in practice

Three compounding reasons, all documented:

1. **Simultaneity.** A cycle must execute all-at-once because a pair whose patient has already received a kidney has no incentive (and can't be legally compelled) to still give one; a renege mid-cycle leaves some pair having given a kidney and gotten nothing — an irreversible harm. Simultaneity means 2k operating rooms and surgical teams for a k-way cycle; logistics cap k at 2–3. (Roth–Sönmez–Ünver AER 2007; Anderson et al. PNAS 2015 frame long-chain optimization around exactly this asymmetry between cycles and chains.) `[high]`
2. **Failure compounding.** Every edge in a proposed exchange can fail after the match run (positive crossmatch, medical status change, withdrawal, "changed my mind"). Documented rates: **arc failure up to 44%** in European KEP recourse studies; Canadian program 2009–2018: **62% of the 6-transplant cycles/chains failed, only 10% of those could be repaired**, ~30% of planned transplants never proceeded. A k-cycle needs all k edges to survive; failure probability compounds geometrically in k. `[high]`
3. **Computation is NP-hard but *not* the binding constraint at fielded scale.** Clearing with cycle cap ≥3 is NP-hard (Abraham–Blum–Sandholm, EC 2007), but their column-generation IP cleared 10,000-pair pools in 2007, and Anderson–Ashlagi–Gamarnik–Roth (PNAS 2015) solved unbounded-chain formulations with TSP-style subtour techniques. Modern surveys (Mak-Hau 2017; KidneyExchange.jl 2023 branch-and-price) treat national-scale clearing as routine. At n=12, brute force over all 2- and 3-subsets is trivial (66 pairs, 220 triples × orientations). `[high]`

### The IP formulation (the transferable part)

The standard model: build a directed compatibility graph (vertex = pair, arc = "donor of u can give to patient of v"), enumerate all feasible cycles of length ≤ L (and chains from altruistic donors), give each cycle a weight (number of transplants, or a priority-weighted score), then solve **maximum-weight cycle packing**: choose vertex-disjoint cycles maximizing total weight. Two classic formulations — edge formulation (constraints force conservation + cap length) and **cycle formulation** (one binary variable per feasible cycle, one constraint per vertex: each vertex in ≤1 chosen cycle) — with the cycle formulation dominating in practice because at L≤3 the number of cycles is manageable and the LP relaxation is tighter (Abraham–Blum–Sandholm 2007; Mak-Hau survey 2017). `[high]`

Weights are policy: UK's NHSBT run explicitly prioritizes (in order) effective 2-way exchanges, then long-waiting/highly-sensitized patients, then 3-ways, and *prefers 2-cycles embedded with back-arcs* so a failed 3-way can fall back to a 2-way. `[medium]` (Manlove & O'Malley describe the UK algorithm; the priority-ordering detail is from program documentation.)

### Failure-aware matching (most FTF-relevant subliterature)

- **Maximum-expectation matching under recourse** (Klimentova, Pedroso, Viana): model each vertex/edge with a failure probability; when a planned exchange fails, remaining vertices get reassigned; optimize the *expected* number of completed transplants over this process rather than the nominal matched count. `[medium]`
- **Two-stage robust / feasibility-seeking approaches** (2022, using the Canadian failure data above): pick a first-stage matching that admits good second-stage repairs under adversarial failures. `[medium]`
- **Pre-screening** (Improving Policy-Constrained Kidney Exchange via Pre-Screening, NeurIPS 2020): query a small number of edges ("would this donor/patient actually be accepted?") *before* the match run; even a few pre-screens dramatically reduce post-match unraveling. `[medium]`

---

## Barter and swap marketplaces

### Swaptree (direct multi-way barter)

Swaptree (books/CDs/DVDs/games, mid-2000s) is the consumer product closest to FTF's mechanic: users list "have" and "want" lists, and the engine finds **2-, 3-, and 4-way circular trades** — A sends a book to B, B sends a CD to C, C sends a DVD to A. It marketed itself as the first site to engineer three- and four-way trades among users who want different things, explicitly to beat the double-coincidence-of-wants problem: the probability that *some cycle* through your have/want lists exists is vastly higher than the probability of a direct bilateral coincidence. `[medium]` (trade press + company materials; the company is long dead, and no engineering postmortem with cycle-completion failure rates was ever published — see [Not researched](#not-researched--follow-up-topics).)

Academic treatment of the same mechanic: "An improved algorithm for multi-way trading for exchange and barter" (Electronic Commerce Research and Applications, 2011) formalizes multi-way trade discovery as cycle-finding that maximizes trade volume. `[medium]` Recent theory ("Barter Exchange with Bounded Trading Cycles," 2024–25) confirms the general problem with bounded cycle length is hard but approximable — same shape as kidney clearing. `[medium]`

### BookMooch / PaperBackSwap (points: dissolving the cycle problem with currency)

BookMooch (2006–2023) took the opposite route: **don't find cycles at all — mint a currency.** Give a book = earn 1 point; request a book = spend 1 point (international variants cost more). Every trade becomes bilateral against the point pool, the double-coincidence problem vanishes, and no multi-party coordination is ever needed. `[high]` (well documented; Wikipedia + contemporaneous reviews.)

The lesson is a genuine fork in the road for any barter platform: **cycles** preserve "every trade is a real exchange of goods both sides chose" at the cost of coordination fragility; **points** buy liquidity at the cost of needing a credible unit of account and inflation management. Dynasty leagues actually have a native quasi-currency — **draft picks** — which function as the fungible filler asset that turns hard 3-cycles into easy 2-party trades. `[low — my inference, but consistent with the operator's own trade philosophy notes (junk-filler floors, pick-anchored tiers)]`

### Documented failure rates of proposed multi-party swaps

Outside kidney exchange, essentially none published. Swap sites never released completion statistics. The kidney numbers (44% arc failure; 62% of large cycles failing; ~30% of planned transplants never happening) are the only hard field data on "we proposed a multi-party barter cycle and it fell apart," and they say: **failure rates on proposed multi-party exchanges are enormous even when a central authority has verified compatibility and participants are highly motivated.** `[high for kidney; low for generalization]`

---

## Stable matching in small one-sided pools

### The league is a roommates market, not a marriage market

Gale–Shapley marriage (two sides, bipartite) **always** has a stable matching. A dynasty league is one pool where any team can trade with any team — that's **stable roommates**, and Gale & Shapley themselves noted stable roommates may have *no* stable matching. Irving's O(n²) algorithm (1985) finds one or proves none exists. `[high]`

### How often stability fails at league size

Mertens (J. Stat. Mech. 2015, "Stable Roommates Problem with Random Preferences") computed exact/simulated existence probabilities pₙ under uniform random full preference lists:

| n | P(stable matching exists) |
|---|---|
| 4 | 26/27 ≈ 0.963 |
| 6 | ≈ 0.933 |
| 8 | ≈ 0.910 |
| 10 | ≈ 0.891 |
| **12** | **≈ 0.8755** |
| large n | decays ≈ a·n^(-1/4) → 0 |

So even at exactly FTF's league size, **one league in eight has no stable pairing structure at all** under random preferences; and the 2026 preprint "The Random Stable Roommates Problem Typically Has No Solution" settles that asymptotically the answer is "usually none." `[high]`

Three further degradations that all apply to FTF:

- **Ties and incomplete lists:** real preferences have ties ("either of these two trades is fine") and truncation ("I won't trade with him at all"). Stable roommates with ties + incomplete lists: deciding existence of a weakly stable matching is **NP-complete** (Ronn 1990; Irving–Manlove for the SRTI variants). `[high]`
- **Almost-stable fallback is also hard:** finding a matching minimizing the number of blocking pairs when no stable matching exists is NP-hard and hard to approximate (Abraham–Biró–Manlove, "'Almost Stable' Matchings in the Roommates Problem," 2005). `[high]`
- **Many-to-many (each team in several concurrent negotiations):** the generalization is the **stable fixtures** problem (Irving–Scott 2007) — each agent has capacity for multiple partnerships; a polynomial algorithm exists for existence-or-refute, but existence is again not guaranteed. `[medium]`

### What thin-market practitioners use instead of stability

Kidney exchange **abandoned blocking-pair stability as the solution concept** — with 0/1-ish compatibility preferences, the relevant concepts became efficiency + priority mechanisms + incentive compatibility (Roth–Sönmez–Ünver 2005), i.e., **optimize a weighted objective over feasible packings, encode fairness as weights/priorities**. Stability survives only in the weaker sense of "individually rational + no obvious regret." This is the load-bearing design precedent: when your pool is 12 and preferences have ties, holes, and noise, chase *participation constraints* (both sides strictly gain by their own valuation) and *priority-weighted total surplus*, not blocking-pair-freeness. `[high]`

---

## NRMP couples and rural hospitals

Two classic results about what thinness does to centralized matching:

- **Rural hospitals theorem** (Roth 1986): across *all* stable matchings of a given market, every hospital that fails to fill its quota gets **exactly the same set of doctors** in every one. You cannot fix an unattractive, thin participant's outcome by picking a different stable matching — no amount of clever matching within the same preferences helps the market's "rural hospitals." `[high]` The FTF reading: a roster nobody wants to trade with cannot be algorithmically rescued by cleverer matching; it can only be helped by *changing the preferences/prices* (e.g., surfacing that their asking prices are off-market, or widening what they'd accept). `[low — transfer inference]`
- **Couples** (Roth 1984; Kojima–Pathak–Roth QJE 2013; Ashlagi–Braverman–Hassidim follow-on): once participants submit preferences over *joint* outcomes (a couple wants two positions together — the analogue of "I'll only do this trade if I also land that other trade"), stable matchings may not exist at all. They exist with probability → 1 only when couples are a vanishing fraction of a growing market; with a constant fraction of couples, non-existence persists even asymptotically — and in a 12-team league every package deal is a "couple." The fielded fix (Roth–Peranson) is heuristic: find near-stable outcomes and accept that the guarantee is gone. `[high]`

Combined lesson: complementarities (package deals, conditional trades) and thinness each independently break stability guarantees; FTF has both, permanently. Design for *good enough, individually rational, priority-weighted* outcomes.

---

## Batch vs streaming

The single most FTF-actionable literature. Three layers:

### Theory: when does waiting beat greedy?

**Akbarpour–Li–Oveis Gharan, "Thickness and Information in Dynamic Matching Markets" (JPE 2020).** Model: agents arrive/depart stochastically; compatibility is a sparse random graph (each pair acceptable with prob d/n); an agent "perishes" if she leaves unmatched; planner chooses *when* to match. Results, quoted from the paper:

- If the planner **can identify agents about to depart** (critical agents), waiting to thicken the market is highly valuable: loss(Greedy) ≥ 1/(2d+1) while loss(Patient) ≤ ½·e^(−d/2) — an **exponential** separation. Getting the *timing* right matters more than optimizing *whom* to match: local algorithms that only pick the right moment are within the same exponential class as the global optimum (loss(OPT) ≥ e^(−d)/(d+1)).
- If the planner **cannot identify departing agents, greedy is close to optimal.** Waiting without urgency information just accumulates risk.
- With discounting (waiting is costly), even moderate waiting (Patient(α)) preserves most of the gain — but the case for waiting collapses as impatience rises. `[high]`

**On Matching and Thickness in Heterogeneous Dynamic Markets (Ashlagi, Nikzad, et al.):** with hard- and easy-to-match types, *market composition* drives the right technology: when hard-to-match agents are relatively rare, prioritizing them meaningfully cuts their waits and bilateral matching is nearly as good as chains; when they dominate, chains win big and prioritization stops helping. `[medium]`

**Matching in Dynamic Imbalanced Markets (Ashlagi et al., 2019):** in imbalanced markets the thickness-vs-speed trade-off **vanishes in large markets**; greedy gives shorter waits *and* weakly more matches; monthly batching is strictly suboptimal — validated on National Kidney Registry data. `[high]`

**Superiority of Instantaneous Decisions in Thin Dynamic Matching Markets (2022):** even in *thin* markets, if agents have a guaranteed minimum sojourn (they don't vanish instantly), instantaneous matching is nearly optimal — sojourn time substitutes for thickness. `[medium]`

**Ünver, "Dynamic Kidney Exchange" (ReStud 2010):** the dynamically efficient multi-way mechanism is essentially greedy — conduct exchanges as soon as they become feasible — except for deliberately holding back certain overdemanded-type pairs to complete better future exchanges. I.e., the *optimal* policy is "greedy plus a small, targeted reserve," not "batch everything." `[high]`

### Field evidence: match-run cadence

**Ashlagi–Burq–Jaillet–Manshadi, "Effect of match-run frequencies…" (AJT 2018)** — simulations on clinical data from the Alliance for Paired Donation (multi-hospital) and Methodist San Antonio (single-center): among periodic policies (2, 4, 7, 14, 30, 60, 90, 120-day intervals), **high frequency performs best**; longer batching intervals do **not** increase total transplants and **do** increase waiting times. Batching only looks attractive if the batch attracts *new arrivals* the greedy regime wouldn't have seen (i.e., cadence as a demand-generation device, not a combinatorial one). `[high]`

Real-world cadences, for reference: Alliance for Paired Donation & NKR ≈ daily; UNOS ≈ weekly; South Korea ≈ monthly; UK NHSBT, Netherlands, Australia ≈ quarterly; Canada ≈ 3×/year. The trend among US registries has been *toward* higher frequency, consistent with the research. `[high]`

### Why batching fails to thicken (the intuition worth internalizing)

Batching holds back easy-to-match pairs, but easy-to-match pairs would match either way — waiting mostly makes them wait. The hard-to-match pairs that batching is supposed to help stay hard because *their* compatibility scarcity is structural (sensitization / roster shape), not temporal. Thickness helps only when compatibility is uniformly sparse **and** you can time matches around departures. `[high — this is the through-line of all five papers above]`

---

## Simulating small matching markets

How the field tunes policy before deploying — all directly reusable for FTF:

- **Trace-driven / clinical-data simulation** (the AJT 2018 method): take real historical arrivals (pairs + attributes), replay them under counterfactual policies (different cadences, cycle caps, priority weights), measure matches + waiting time. The credibility comes from real arrival distributions, not synthetic ones. `[high]`
- **Generator-based simulation**: Saidman et al.'s widely used generator draws synthetic patient-donor pairs from blood-type and PRA (sensitization) distributions; every kidney-IP paper benchmarks on it. FTF equivalent: a league generator drawing rosters, positional needs, and valuation dispersions from real Sleeper league data. `[high]`
- **Agent-level accept/reject behavior**: the recourse and pre-screening literatures model each proposed edge as accepted with probability p (heterogeneous by agent), then evaluate policies on *expected completed* matches. UNOS/registry sims incorporate per-center acceptance heterogeneity ("center selectivity") — the analogue of per-manager accept thresholds. `[medium]`
- **Mechanism-design ABM**: Ünver (2010) and the dynamic-matching theory papers validate closed-form policies against small-market simulations (Akbarpour et al. include an explicit "Small Market Simulations" appendix — their theory is asymptotic, and they check it holds at modest n). `[medium]`
- **Method transfer for FTF** `[low — my synthesis]`: simulate a 12-team league as 12 agents with (a) private valuations over assets (drawn around consensus values with team-specific noise), (b) roster-need utilities, (c) accept thresholds ("only accept if my perceived gain ≥ ε"), (d) responsiveness/latency distributions. Replay policies: suggestion cadence, 2-way vs 3-way mix, how many suggestions to surface at once, cooldowns after rejection. Score on: completed trades per season, time-to-first-trade, rejection rate (burnout proxy), Gini of trade participation (does the algorithm always feed the same two active managers?).

---

## Best practices

1. **Cap multi-party exchanges at 3 parties; treat 3-cycles as premium, riskier inventory.** Every fielded system converged here from both theory (RSU 2007: efficiency gains concentrated at 3-way) and operations (failure compounding). `[high]`
2. **Formulate discovery as maximum-weight disjoint-cycle packing over a directed "gain graph."** Arc u→v exists iff a specific asset bundle from u strictly improves v by v's own board. At n=12 enumerate all cycles ≤3 exactly; weight = joint surplus × completion probability × priority terms. This is the kidney cycle formulation, trivially small at league scale. `[high]`
3. **Optimize expected *completed* trades, not proposed trades.** Multiply cycle weight by per-edge acceptance probabilities (learned per manager); prefer a 2-way at 60% completion over a 3-way at 25%. The recourse literature is unanimous that ignoring failure probabilities badly overstates nominal-optimal solutions. `[high]`
4. **Embed fallbacks: prefer 3-cycles containing a 2-cycle "back-arc."** UK NHSBT explicitly scores embedded 2-cycles so a collapsed 3-way degrades to a completed 2-way instead of nothing. Direct analogue: when proposing a 3-team trade, know (and maybe show) the best 2-team salvage if one team declines. `[high]`
5. **Pre-screen edges before proposing cycles built on them.** Cheap advance signals ("Would you ever move Player X?" / persistent want/won't-trade lists) prune the failure-prone arcs before they poison a multi-party proposal. Proven to substantially reduce post-match failure. `[medium]`
6. **Match greedily; re-run on every state change; reserve batching for presentation, not computation.** The theory and field evidence agree: without knowledge of who's about to churn, waiting to thicken doesn't create matches in sparse pools. If you *do* have urgency signals (trade deadline approaching, a manager about to go inactive), that's precisely when prioritizing/waiting-for those agents pays — Akbarpour et al.'s "critical agent" channel. `[high]`
7. **Use priorities/weights, not stability, to encode fairness in a 12-agent pool.** Kidney exchange encodes "hard-to-match gets priority" as objective weights. FTF equivalents: boost long-idle teams, boost first-trade-of-season, boost rebuilding↔contending complementarity — as weights in the packing objective. `[high]`
8. **Give hard-to-match participants their boost *early*, and consider holding flexible assets for them.** Heterogeneous-market results: prioritizing hard-to-match agents helps most when they're a minority; Ünver's optimal dynamic mechanism holds back overdemanded types briefly to complete better exchanges. FTF: when a rare complement appears for a hard-to-help roster, prefer routing it there over an equal-surplus easy pairing. `[medium]`
9. **Tune policy in simulation before shipping** — trace-driven replay on real league histories + a synthetic league generator with heterogeneous accept thresholds; measure completed trades, rejection burden, and participation spread, not suggestion counts. `[medium]`
10. **Remember the currency escape hatch.** Points systems (BookMooch) dissolve the double-coincidence problem entirely; in dynasty, draft picks are the native near-currency. Systematically adding pick sweeteners to close near-miss 2-ways is often better than escalating to a fragile 3-way. `[low — inference, strong precedent]`

## Antipatterns

1. **Building 4+-party trades because the engine can find them.** Fielded systems universally refuse; completion probability collapses and the efficiency gain over 3-way is a rounding error. `[high]`
2. **Batching suggestions to "let the market thicken."** Refuted in theory (greedy near-optimal absent departure info) and field data (highest match-run frequency won on real registries). Waiting mainly delays the easy matches and does nothing for the hard ones. `[high]`
3. **Chasing blocking-pair stability as the solution concept.** At n=12 with ties/incomplete/noisy preferences: stable outcomes fail to exist ~12%+ of the time, deciding existence under ties is NP-complete, and near-stability is NP-hard. Nobody fields it; don't. `[high]`
4. **Treating a proposed match as a done match** — reporting nominal matches, not completed ones; not modeling per-participant acceptance; no salvage plan when one leg declines. The kidney field data (44% arc failure, 62% large-structure failure) is the cautionary tale. `[high]`
5. **Trying to algorithmically rescue the unwanted roster by re-matching harder.** Rural hospitals theorem: within fixed preferences, every stable matching strands the same participants. The fix lives in preference/price space (asking-price feedback, widened accept sets), not matching space. `[medium — theorem is high; transfer is inference]`
6. **Ignoring complementarities ("couples") in proposal design.** Conditional/package intents ("only rebuild if I land a QB back") break clean matching guarantees; pretending trades are independent produces proposals users experience as tone-deaf. Handle packages explicitly (bundle arcs), don't assume away. `[medium]`
7. **Assuming greedy needs no urgency layer.** Pure greedy with zero deadline-awareness leaves the one exponential-size gain on the table: if you *can* see who's about to depart (deadline, churn risk), you must prioritize them. `[high]`

## What matters most (ranked)

1. **Completion probability modeling** — per-manager acceptance estimates multiplying every proposal's score. It gates everything: which cycles to show, 2-way vs 3-way, and user trust. (Kidney failure data + recourse/pre-screening literature.)
2. **Greedy cadence with event-driven re-runs** — suggestions always fresh against current rosters/boards; no artificial batching of computation.
3. **2-way first, 3-way as boosted fallback** — run 3-cycle search when the 2-way graph around a team is dry (that's exactly the double-coincidence failure 3-cycles exist to fix), and price in the extra failure risk.
4. **Priority weights for cold/hard-to-match teams** — the fairness instrument that actually works in thin barter markets; also the retention instrument (idle managers are the "highly sensitized patients" of a league).
5. **Urgency signals** (trade deadline, activity decay) — the one condition under which timing policy should deviate from greedy, per the strongest theorem in the literature.
6. **Fallback/salvage structure inside multi-party proposals** — embedded 2-cycles; re-match immediately on decline (recourse).
7. **Simulation harness for policy tuning** — cheap at n=12; converts every knob above from vibes to measured trade-completion deltas.

## What doesn't matter

1. **Optimal-solver sophistication.** The kidney literature's IP machinery (column generation, branch-and-price, TSP encodings) exists for pools of thousands. At n=12, exhaustive enumeration of all ≤3-cycles is microseconds. Spend the effort on edge quality (valuations, acceptance models), not solver tech — echoing Akbarpour et al.: the gains from *when/whether* dominate the gains from *globally optimal whom*. `[high]`
2. **Market thickness engineering within one league.** You cannot thicken a closed 12-team pool by waiting; the pool is the pool. Thickness levers that *do* exist live outside the matcher (getting more of the league onboarded onto boards — that's edge *visibility*, not pool size). `[high]`
3. **Stability guarantees.** Feels like the intellectually right target for a small market; is actually unattainable (non-existence, NP-hardness) and unnecessary (individual rationality + no-regret framing carries the UX weight). `[high]`
4. **4-way+ trade support.** Seems like a differentiating power feature; the entire field's revealed preference says the completion rate makes it a trust-destroyer. `[high]`
5. **Batch cadence as an *efficiency* lever.** It does nothing for match counts — but note the carve-out: batching may still earn its keep as a *presentation/engagement* rhythm (weekly digest creates a ritual; UK quarterly runs create event-ness). The literature only kills batching as a combinatorial strategy; as marketing it's untested. `[medium]`
6. **Very long chains.** The most celebrated kidney innovation (NEAD chains) is the one piece that does **not** transfer: chains require an altruistic first mover who wants nothing back, and dynasty leagues have no altruists — every FTF structure is a closed cycle. Don't cargo-cult chains. `[high]`

## Transfer notes for FTF

The dictionary, then the design implications:

| Kidney / market-design concept | FTF equivalent |
|---|---|
| Patient-donor pair | Team (has assets, has needs) |
| Compatibility arc u→v | Bundle from u that strictly improves v on v's own board |
| 2-way exchange | 2-team trade |
| 3-cycle (simultaneous) | 3-team trade (all-or-nothing accept) |
| Altruistic-donor chain | **No equivalent** (no altruists in a league) |
| Positive crossmatch after match run | Manager rejects the proposed trade |
| Highly sensitized patient | Hard-to-help roster / picky or idle manager |
| Match-run cadence | Suggestion recompute + surfacing cadence |
| Priority weights (waiting time, sensitization) | Boosts for idle teams, deadline urgency, first-trade |
| Pre-screening edges | Want/won't-trade lists; "would you consider X?" micro-prompts |
| Recourse / embedded 2-cycles | Salvage 2-team trade inside every 3-team proposal |
| Points currency (BookMooch) | Draft-pick sweeteners closing near-miss 2-ways |

Concrete recommendations:

1. **Engine shape:** directed gain graph over 12 teams; arcs from dual-board logic (bundle clears sender's "accept" floor and receiver's "want" test — this is already FTF's fairness-gate philosophy); enumerate all 2- and 3-cycles exactly; score = joint surplus × Π(edge acceptance prob) × priority weights; return top-k disjoint or overlapping suggestions per team.
2. **Cadence:** recompute on every roster/board/ranking change (greedy). Add an urgency multiplier as the trade deadline approaches — that's the theoretically sanctioned deviation. If a digest rhythm is wanted for engagement, batch the *notification*, never the *computation*.
3. **3-team trades:** ship them, but (a) only surface when they beat the best available 2-way for at least one involved team by a real margin, (b) always carry the embedded 2-way salvage, (c) present accept/decline as all-or-nothing with visible state ("2 of 3 accepted"), and (d) expect materially lower completion — instrument it from day one; kidney's 62%-failure-at-size-6 is the warning boundary.
4. **Acceptance model before ML sophistication:** even a crude per-manager acceptance prior (base rate from past responses, updated per rejection) multiplied into cycle scores will outperform a better valuation model with no completion term. Round 1's reciprocity finding (harmonic-mean fusion punishing asymmetry) composes cleanly: acceptance probability is the dating-app P(B→A) reborn.
5. **Cold-team priority is the retention weapon:** the "highly sensitized" analogue says the app should visibly work hardest for the team with the fewest options — boost their weight, route rare complements to them, and tell them why ("this is the only roster in the league that fits your timeline").
6. **Rural-hospitals honesty:** when a roster genuinely has no positive-sum trades, say so and pivot to price feedback ("your ask on X is ~1.5 firsts above league consensus") instead of degrading suggestion quality — the theorem says no matcher can conjure a partner that preferences exclude.
7. **Simulation before tuning:** build the 12-agent league sim (heterogeneous boards, accept thresholds ε, response latencies; replay real Sleeper league histories where available) and tune: surplus-split rule, 3-way surfacing threshold, priority weights, cooldown after rejection. Score on completed trades, rejection burden per manager, and participation Gini.

## Not researched / follow-up topics

- **Swaptree/consumer-swap completion rates:** no engineering postmortem or published completion/failure statistics for consumer multi-way swap platforms could be found; the 3–4-way failure-rate claims for consumer barter remain unquantified. (Kidney data is the only hard evidence.)
- **Combinatorial exchange mechanisms with money/points:** the full combinatorial-auction/exchange literature (bundle bids, core-selecting payments) was out of scope; relevant if FTF ever introduces FAAB or a league-point sweetener currency.
- **Strategic misreporting in small barter pools:** kidney IC results assume hospitals/pairs may withhold pairs; whether managers would game boards/want-lists to steer the FTF matcher (and how much it matters at n=12) is untouched.
- **Repeated-game effects:** leagues trade with the same 11 partners for years; reputation, tit-for-tat, and collusion dynamics (Stability in Repeated Matching Markets, arXiv 2020) deserve their own pass.
- **Presentation-layer batching as engagement design:** the efficiency literature kills computational batching but says nothing about whether a weekly "trade digest" ritual beats continuous push for *human attention*; that's a Round-1-style product question, testable in-app.
- **Multi-league cross-listing:** FTF users often run several leagues; whether surfacing the *same* player's tradability across a user's leagues changes thin-market dynamics (effectively thickening across markets, as multi-hospital kidney networks did — including the free-riding problems Ashlagi–Roth documented) is a rich follow-up.
- **Exact UK NHSBT scoring weights** and the Biró/Manlove European KEP survey details were only skimmed; worth a deep read if FTF adopts priority-weighted packing wholesale.

## Sources

Kidney exchange — foundations and cycle caps:
1. Roth, Sönmez, Ünver, "Kidney Exchange," QJE 2004 (NBER WP): https://www.nber.org/system/files/working_papers/w10002/w10002.pdf
2. Roth, Sönmez, Ünver, "Pairwise Kidney Exchange," J. Economic Theory 2005: https://www.sciencedirect.com/science/article/abs/pii/S0022053105001055
3. Roth, Sönmez, Ünver, "Efficient Kidney Exchange: Coincidence of Wants in Markets with Compatibility-Based Preferences," AER 2007: https://www.aeaweb.org/articles?id=10.1257%2Faer.97.3.828
4. Roth, Sönmez, Ünver, "A Kidney Exchange Clearinghouse in New England," AEA P&P 2005: http://www.tayfunsonmez.net/wp-content/uploads/2013/10/Kidney-AEA.pdf
5. Sönmez, "Kidney Exchange: Two Basic Models" (lecture notes): https://www.tayfunsonmez.net/wp-content/uploads/2013/10/Kidneyexchange.pdf

Chains, IP formulations, computation:
6. Abraham, Blum, Sandholm, "Clearing Algorithms for Barter Exchange Markets: Enabling Nationwide Kidney Exchanges," ACM EC 2007: https://scite.ai/reports/10.1145/1250910.1250954
7. Anderson, Ashlagi, Gamarnik, Roth, "Finding long chains in kidney exchange using the traveling salesman problem," PNAS 2015: https://www.pnas.org/doi/10.1073/pnas.1421853112
8. Rees et al., "A Nonsimultaneous, Extended, Altruistic-Donor Chain," NEJM 2009: https://www.nejm.org/doi/full/10.1056/NEJMoa0803645 (PDF: http://www.cs.cmu.edu/~sandholm/nonsimultaneous%20donor%20chain.NEJM09.pdf)
9. Mak-Hau, "On the kidney exchange problem: cardinality constrained cycle and chain problems on directed graphs: a survey of integer programming approaches," J. Combinatorial Optimization: https://link.springer.com/article/10.1007/s10878-015-9932-4
10. KidneyExchange.jl branch-and-price, Mathematical Programming Computation 2023: https://link.springer.com/article/10.1007/s12532-023-00251-7
11. Manlove & O'Malley, "Paired and Altruistic Kidney Donation in the UK: Algorithms and Experimentation," SEA 2012: https://link.springer.com/chapter/10.1007/978-3-642-30850-5_24

Failure rates and failure-aware matching:
12. Pedroso et al., "Maximum-expectation matching under recourse," arXiv: https://arxiv.org/abs/1605.08616
13. "A Feasibility-Seeking Approach to Two-stage Robust Optimization in Kidney Exchange" (Canadian failure data), arXiv: https://arxiv.org/pdf/2211.09242
14. "Improving Policy-Constrained Kidney Exchange via Pre-Screening," arXiv: https://arxiv.org/pdf/2010.12069
15. "Kidney Exchange with Inhomogeneous Edge Existence Uncertainty," arXiv: https://arxiv.org/pdf/2007.03191
16. Canadian program foundations, "Foundations and principles of the Canadian living donor paired exchange program," PMC: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4346240/

Match-run cadence and dynamic matching theory:
17. Ashlagi, Burq, Jaillet, Manshadi, "Effect of match-run frequencies on the number of transplants and waiting times in kidney exchange," AJT 2018: https://web.stanford.edu/~iashlagi/papers/frequency-ajt-final.pdf (PubMed: https://pubmed.ncbi.nlm.nih.gov/29087017/)
18. Akbarpour, Li, Oveis Gharan, "Thickness and Information in Dynamic Matching Markets," JPE 2020 (working paper PDF read in full): https://econ.la.psu.edu/wp-content/uploads/sites/5/2023/05/DynamicMarketMaking.pdf (SSRN: https://ssrn.com/abstract=2394319)
19. Ashlagi et al., "Matching in Dynamic Imbalanced Markets," arXiv: https://arxiv.org/abs/1809.06824
20. Ashlagi, Nikzad et al., "On Matching and Thickness in Heterogeneous Dynamic Markets," arXiv: https://arxiv.org/abs/1606.03626
21. "Superiority of Instantaneous Decisions in Thin Dynamic Matching Markets," arXiv 2022: https://arxiv.org/abs/2206.10287
22. Ünver, "Dynamic Kidney Exchange," Review of Economic Studies 2010: https://academic.oup.com/restud/article-abstract/77/1/372/1547330
23. UK Living Kidney Sharing Scheme (quarterly runs, 2-/3-way): https://kidneycareuk.org/kidney-disease-information/treatments/kidney-transplantation/patient-info-receiving-a-kidney/what-is-pairedpooled-kidney-donation/ and https://www.organdonation.scot/living-donation/uk-living-kidney-sharing-scheme

Stable matching in small/one-sided/complementarity-laden markets:
24. Mertens, "Stable Roommates Problem with Random Preferences," arXiv (read in full; exact pₙ values): https://arxiv.org/pdf/1401.5269
25. Mertens, "Small random instances of the stable roommates problem," J. Stat. Mech. 2015 / arXiv: https://arxiv.org/abs/1502.06635
26. "The Random Stable Roommates Problem Typically Has No Solution," arXiv 2026: https://www.arxiv.org/pdf/2601.07612
27. Pittel, "The 'Stable Roommates' Problem with Random Preferences," Annals of Probability 1993: https://projecteuclid.org/journals/annals-of-probability/volume-21/issue-3/The-Stable-Roommates-Problem-with-Random-Preferences/10.1214/aop/1176989126.full
28. Abraham, Biró, Manlove, "'Almost Stable' Matchings in the Roommates Problem," WAOA 2005: https://link.springer.com/chapter/10.1007/11671411_1
29. Kojima, Pathak, Roth, "Matching with Couples: Stability and Incentives in Large Markets," QJE 2013: https://economics.mit.edu/sites/default/files/publications/couplesQJE.pdf
30. Rural hospitals theorem (overview + Roth 1986 references): https://en.wikipedia.org/wiki/Rural_hospitals_theorem
31. Nguyen & Vohra, "Near-Feasible Stable Matchings with Couples": https://pages.nyu.edu/debraj/Courses/NewRes19/Papers/NguyenVohra.pdf

Barter/swap marketplaces:
32. Swaptree review (multi-way trade mechanics): https://www.mymoneyblog.com/swaptree-review-barter-your-books-cds-dvds-and-video-games.html
33. "The Internet is Facilitating Barter Like Never Before" (Swaptree 3-/4-way trades): https://sniggle.net/TPL/index5.php?entry=17May06
34. "An improved algorithm for multi-way trading for exchange and barter," ECRA 2011: https://www.sciencedirect.com/science/article/abs/pii/S1567422310000645
35. "Barter Exchange with Bounded Trading Cycles," arXiv 2024: https://arxiv.org/pdf/2410.06683
36. BookMooch (points mechanics): https://en.wikipedia.org/wiki/BookMooch
37. "Stability in barter exchange markets," JAAMAS 2019: https://link.springer.com/article/10.1007/s10458-019-09414-0

Simulation methods:
38. Santos et al., "Kidney exchange simulation and optimization," J. Operational Research Society 2017: https://link.springer.com/article/10.1057/s41274-016-0174-3
39. "Dynamic Simulations of Kidney Exchanges": https://link.springer.com/chapter/10.1007/978-3-642-20009-0_85
40. "Enhancing kidney transplantation through multi-agent kidney exchange programs" (2025 review incl. simulation practice), arXiv: https://arxiv.org/pdf/2502.07819
41. "Stability in Repeated Matching Markets," arXiv (follow-up topic): https://arxiv.org/pdf/2007.03794
