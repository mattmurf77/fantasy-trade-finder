# Valuation integrity: draft picks under uncertainty, manipulation resistance, and governance calibration

> Round-3 memo. Round 2 flagged the layer everything else in FTF stands on: if the **values** are
> wrong, biased, or gameable, then mutual-gain detection, the consensus fairness band, and
> league-defensibility all inherit the error. Three questions: (1) how should a *future draft pick*
> — an asset whose slot is unknown — be priced inside a fairness test? (2) how manipulable is a
> preference-elicitation system at n=12, and what damping applies? (3) what does real league
> governance (vetoes, league death) tell us about how wide the fairness band should be?
>
> Researched 2026-08-16. Confidence flags per claim: **[H]** well-sourced/converging,
> **[M]** single good source or reasoned inference, **[L]** thin/anecdotal.
>
> **Method caveat, stated up front:** the session's WebSearch budget was exhausted partway through
> Part 1, so Part 1's back half was built from **direct fetches of primary sources** (arXiv,
> OverTheCap, DraftTek, Football Perspective, KTC, DynastyProcess, the live FantasyCalc values API)
> plus **original arithmetic on a live market snapshot**, rather than from a broad survey. Parts 2
> and 3 were swept before the budget ran out and are broad. Two specific Part-1 gaps
> (dynasty rookie-pick *hype-cycle* time series; published dynasty bust rates by rookie-pick slot)
> are unfilled and listed in §5. Numbers I derived myself are shown with their arithmetic so they
> can be audited and re-run.

---

## Part 1 — Draft-pick valuation under uncertainty

### A1. The NFL analytics consensus: the Jimmy Johnson curve is too steep at the top **[H]**

Three independent chart families, all normalized differently, agree that the incumbent
practitioner chart over-prices the top of the draft relative to what the picks actually produce:

| Pick | Jimmy Johnson | Chase Stuart (career AV) | Fitzgerald–Spielberger (2nd-contract APY) |
|---|---|---|---|
| 1 | 3000 | 34.6 | 3000 |
| 10 | 1300 | 19.9 | — |
| 33 | 580 | — | 1228 |
| 100 | 100 | 5.3 | — |

Read as **ratios**, which is the only scale-free comparison:

- **Pick 1 ÷ pick 10:** JJ = 2.31x; Stuart = 1.74x.
- **Pick 1 ÷ pick 100:** JJ = **30x**; Stuart = **6.5x**.
- **Pick 1 ÷ pick 33:** JJ = 5.17x; Fitzgerald–Spielberger = **2.44x**.

Every performance-grounded chart is dramatically **flatter** than Jimmy Johnson. The JJ chart is a
1990s negotiating heuristic with no published derivation; Stuart's is fit to career Approximate
Value, and Fitzgerald–Spielberger retroactively grades 2011–2015 picks by what the player's
*second* contract paid relative to the top-5 APY at his position — i.e. it prices a pick by the
market's revealed verdict on the player after his rookie deal. **[H]**

**Massey–Thaler ("The Loser's Curse," 2005/2013)** is the origin of the flatness claim: GMs
systematically overvalue top picks, and surplus value (performance minus salary cost) *rises*
into the late first round rather than falling monotonically. **[H]**

### A2. The critical amendment: the curve you want depends on your utility function **[H]**

Brill & Wyner, *"The Loser's Curse and the Critical Role of Specifying a Utility Function"*
(arXiv 2411.10400), is the most important paper for FTF's purposes, and it is not really a paper
about football. Their argument: Massey–Thaler's conclusion "hinges on the assumption that general
managers should use expected surplus value as their utility function." Swap the objective to
*probability of acquiring an elite player* and the apparent irrationality evaporates — "general
managers' draft trade behavior appears rational rather than systematically flawed."

The single most useful number in the whole of Part 1:

> **"The 42nd pick produces 89% fewer expected elite players than the 3rd pick, but just 13% less
> expected surplus value."**

That is one asset pair whose relative price changes by nearly an order of magnitude depending on
whether you score the *mean* or the *tail*. They also find GMs "trade draft picks as if they value
a draft position by the probability it produces a player whose second contract exceeds 19.7% of
the salary cap" — a threshold met by "just 12.3% of quarterbacks (8/65) and zero non-quarterbacks"
in their sample. Their model is explicitly two-part: a **logistic "bust spike" near zero** plus a
**Beta regression** for the non-bust mass, with precision (inverse variance) itself a function of
pick. Variance declines with pick number; "higher draft picks offer significantly greater
potential for elite outcomes." **[H]**

Michael Lopez's "Rethinking the draft curve" reaches the same place from the other direction:
build a second curve on P(career AV > 66) — top ~21st percentile — and the "superstar curve" has
"a much steeper cutoff than the average curve," with a superstar "exceedingly unlikely" by pick
100. His recommendation is a **blended curve averaging both**. **[M]**

**Implication for FTF, stated plainly:** a draft pick is not a number, it is a right-skewed
distribution, and *the same pick has two defensible prices* depending on whether the holder is
buying expectation or buying a lottery ticket. A contender consolidating wants expectation; a
rebuilder wants the tail. This is the cleanest academic justification I found for FTF's whole
per-user-board thesis, applied to picks.

### A3. How the dynasty market actually prices unknown-slot picks **[M]**

Nobody in dynasty conditions pick value on the owning team's projected finish. What exists:

- **KeepTradeCut** discretizes: "KTC includes Early/Mid/Late picks for each round for future years
  in our crowdsourced rankings and values. For simplicity's sake, all future draft picks in Power
  Rankings are assumed to be 'Mid' round picks." A 3-bucket approximation of the slot
  distribution, with the *bucket* left to the two managers to argue about. KTC also excludes picks
  from its Liquidity metric "since there are ~12x more of them in every league." **[H]**
- **DynastyProcess** applies a flat present-value haircut: future-year picks are "80% of the
  current year's value" — a constant 20%/year geometric discount, slot-agnostic and
  finish-agnostic. **[H]**
- **FTF today** does the same thing with a different constant: `pick_values.YEAR_DISCOUNT = 0.85`,
  and `pick_pool_value()` prices *every* owned league pick at the **Mid** tier of its round,
  documented as an operator decision ("we can't yet resolve a pick's slot," 2026-07-18). **[H]**

**No one found does the thing Part 1 asked about** — model a "2027 1st" as a distribution over
slots conditioned on the owning team's projected finish. Confidence that this is genuinely absent
rather than merely unfound: **[M]** (search budget limited the sweep; but KTC, FantasyCalc,
DynastyProcess and DLF are the four price-setting institutions and none of them does it).

### A4. Original analysis: how big is the slot-uncertainty error? **[M]**

I pulled a live snapshot of the FantasyCalc values API (12-team, 1QB, PPR dynasty; fetched
2026-08-16) which prices **both** individual slots and generic unknown-slot picks — the rare case
where the market quotes the point estimate and the underlying distribution side by side.

Slot values, round 1: 6789, 4148, 3684, 3412, 3180, 3013, 2794, 2605, 2440, 2295, 2166, 2051.

Derived, assuming a uniform prior over the 12 slots (the correct prior for a pick whose *owner* is
unknown):

| Statistic | Value |
|---|---|
| Mean of the 12 slots | **3,215** |
| Median of the 12 slots | **2,904** |
| Standard deviation | **1,238** |
| Coefficient of variation (sd ÷ mean) | **0.385** |
| Slot 1.01 ÷ slot 1.12 | **3.31x** |
| Market's quoted generic "1st" | **2,904** |

**Finding 1 — the market prices an unknown 1st at the median slot, not the mean.** The quoted
generic first (2,904) matches the median (2,904) to four significant figures and sits **~10% below
the mean** (3,215). Because the slot-value curve is strongly convex, mean > median; pricing at the
median is either risk-aversion or modal thinking, but either way an unknown-slot first is quoted
below its expectation. **[M]** — one snapshot, one platform, one format; the coincidence is
striking enough to be worth replicating before leaning on it.

**Finding 2 — the irreducible dispersion of an unknown-slot first is ~38% of its value.** CV =
0.385. For calibration: FTF's `range_base` — the maximum per-player value half-width fraction
used by the existing range-overlap fairness gate, at zero comparisons — is **0.35**. The
irreducible slot uncertainty of a future first is *larger than FTF's maximum modeled uncertainty
for any asset*, and FTF currently assigns picks **no outcome uncertainty at all**.

**Finding 3 — conditioning on the owner's finish helps enormously for contenders and barely at all
for rebuilders.** Splitting the same 12 slots:

| Owner profile | Slots | Mean | sd | CV |
|---|---|---|---|---|
| Bottom-3 team (rebuilder) | 1–4 | 4,508 | 1,343 | **0.298** |
| Playoff team (contender) | 7–12 | 2,392 | 254 | **0.106** |
| Unknown owner | 1–12 | 3,215 | 1,238 | 0.385 |

Conditioning cuts a contender's-first CV by **3.6x** (0.385 → 0.106). It cuts a rebuilder's first
by only 1.3x, because the 1.01 lottery ticket (6,789 — 2.1x the mean) dominates the variance and
*cannot* be conditioned away. **[M]**

**Finding 4 — the mispricing from ignoring the owner is larger than any other valuation error in
FTF's pick handling.** Pricing every league first at the generic/mid value (2,904) means:

- a **contender's** first (true mean 2,392) is **overpriced by 21%**;
- a **bottom-3 team's** first (true mean 4,508) is **underpriced by 36%**.

That is a 57-point spread of error across the league, on an asset class that appears in a large
share of dynasty trades. By comparison the constant-vs-true year discount error (below) is single
digits to ~15%. **[M]**

**Finding 5 — the year discount is not constant.** Same snapshot: generic 2027 1st ÷ generic 2026
1st = 2,726 ÷ 2,904 = **0.94** (−6%); generic 2028 1st ÷ generic 2027 1st = 1,920 ÷ 2,726 =
**0.70** (−30%). Both FTF (0.85/yr) and DynastyProcess (0.80/yr) impose a constant geometric rate,
which is wrong in both directions at different horizons. **[M]** — caveat: in August the
"current-year" label is ambiguous (the 2026 rookie draft has typically already run), so the level
is less trustworthy than the *non-constancy*, which is robust to relabeling.

**Finding 6 — FTF's within-round Early/Mid/Late spread is already well calibrated.** FTF's
`GENERIC_PICK_SEEDS` for round 1 are Elo 1720/1650/1580, which through
`elo_to_value = 1000·e^{0.005(elo−1500)}` gives **3,004 / 2,117 / 1,492** — an Early÷Late ratio of
**2.01x**. The market's 2027 Early÷Late ratio is 4,287 ÷ 2,173 = **1.97x**. Near-exact agreement.
The tier *ladder* is fine; the problem is that nothing ever assigns a league pick to a tier. **[H]**

### A5. Precedent for uncertainty-aware fairness bands **[M]**

Direct precedent in *trade fairness* is thin — I found no dynasty tool and no sports-analytics
paper that widens an acceptance band as a function of asset variance. What exists is the
scaffolding:

- **Brill & Wyner's two-part model** (bust spike + Beta with pick-dependent precision) is a
  ready-made variance model for picks; they explicitly note precision "inversely relates to
  variance." **[H]**
- **Lopez's blended curve** is the practitioner version of "price the distribution, not the
  mean." **[M]**
- **Robust statistics** supplies the aggregation half: the mean has breakdown point 1/(n+1), a
  trimmed mean ≈ h%, the median 50%. Any aggregate over possibly-corrupt inputs should use median
  or trimmed aggregation. **[H]**
- **FTF itself already has the mechanism** — and this is the memo's happiest finding.
  `trade_service._fairness()` implements a **range-overlap gate**: each side's package gets an
  interval `[v·(1−unc), v·(1+unc)]` where `unc` is the value-weighted mean of member
  uncertainties, and the trade passes if **the intervals overlap** *or* the point ratio clears
  `fairness_threshold`. Per-player uncertainty is `range_base / sqrt(1 + n)`. This is exactly
  "wider bands for higher-variance assets," already shipped. **[H]**

  **The gap is what feeds `unc`.** `n` is the user's *comparison count* for that player, so the
  quantity modeled is **epistemic uncertainty about the user's taste** — which correctly shrinks
  toward zero as they vote more. Outcome uncertainty of the asset is a different quantity, is
  **irreducible**, and does not shrink with voting. A future 1st that a user has compared 20 times
  currently gets `0.35/√21 = 0.076` — a 7.6% band — when its true dispersion is 38%. **[H]**

---

## Part 2 — Manipulation resistance of crowdsourced and voted value systems

### B1. KTC's defenses, and why they are thinner than the market assumes **[M]**

KTC's published quality control is one sentence: "We occasionally run 'test' KTCs that ask a
question with one obvious right answer. Keep the stud to prove you're paying attention," described
as "one of several things we do behind the scenes." No vote weighting, no reputation model, no
Sybil defense, no rate limiting is disclosed. The value engine is "an adapted ELO algorithm"
withheld as "secret sauce." **[H]** on what is *published*; **[L]** on what actually runs.

Two structural properties do most of the real defensive work, and neither is a countermeasure per
se:

1. **Volume.** Users must periodically vote to keep viewing rankings — the data collection *is*
   the paywall — so the honest-vote stream is enormous and continuous. This is the prediction-market
   thickness argument (§B3) applied to a voting system.
2. **The forced-choice trio format.** A Keep/Trade/Cut answer yields three *ordinal* pairwise
   comparisons, never a cardinal number. An attacker cannot inject a magnitude, only a direction,
   and each vote's marginal Elo displacement is bounded by K.

Against these: attention checks are the **weakest** documented QA method in the crowdsourcing
literature. Comparative MTurk work finds that **restricting to high-reputation workers (>95%
approval) outperforms attention checks** as a quality filter, and that experienced workers learn
to recognize and pass check items specifically before reverting to careless answers on the real
items — marginal effectiveness declining over time as the population adapts. Best practice is to
**rotate check items** and use reputation screening as the first-line filter, with honeypots
supplementary. KTC does the opposite: honeypots only, no disclosed reputation layer. **[M]**

Community criticism (carried forward from round-2/04, **[M]**, secondary sourcing since Reddit
blocks the crawler): KTC values run hot on hype players, first-round rookie picks are systematically
overvalued relative to bust rates, and determined users believe they can nudge thin corners of the
board. Note that the *first two* complaints are not manipulation at all — they are the crowd
sincerely being wrong, which is a different problem with a different fix.

### B2. What the fraud-detection literature says works **[H]**

**Review fraud.** Luca & Zervas, *"Fake It Till You Make It"* (Management Science 2016): roughly
**16% of Yelp restaurant reviews** are filtered as suspicious, rising over time; Yelp separately
states ~25% of all submissions are "not recommended." Fraud concentrates where reputation is
weakest and competition hardest — independents more than chains, businesses with few reviews or
recent negative reviews, and fraud is **bidirectional** (negative fakes on rivals, not just
positive self-promotion). Filtering concentrates on low-activity accounts: only **~4.5% of
reviewers with 5+ reviews** get filtered. Fake reviews are more **extreme** than honest ones.

**The most transferable result in this whole section:** He, Hollenbeck, Overgoor, Proserpio &
Tosyali (PNAS 2022) had *ground truth* on which Amazon products bought fake reviews, and found
that **network structure beats text and metadata**, because buying from a review marketplace
forces reliance on a shared reviewer pool — and network position is expensive to fake, while prose
and behavioral metadata are cheap to vary. The companion Marketing Science paper documents the
market: Facebook groups averaging ~16,000 members and ~568 fake-review requests/day/group; 10,000+
groups reported by Amazon since 2020; one firm spending $250k on fakes and generating $5M+ in
sales. **[H]**

**Wikipedia** is the canonical **graduated-confidence pipeline**, and the architecture matters more
than any single number: AbuseFilter blocks known-bad patterns *before save* → ClueBot NG
auto-reverts high-confidence vandalism within seconds → pending-changes protection holds edits
from new accounts for review on contentious pages → human patrol triages the ambiguous middle.
ClueBot NG's own bot-approval discussion accepted a **0.25% false-positive rate** as the price of
catching **"over 50%" of vandalism**, later tuned toward ~0.1% FP; secondary sources put the catch
rate nearer 40%, so treat it as **40–50%+ [M]**. Most false positives land on **newcomers with
fewer than 10 edits** making poor-but-not-malicious edits. Cheap automatic layers absorb the
obvious majority; expensive human review is reserved for the tail. **[H]** on architecture.

### B3. Do thin markets get moved, and do they self-correct? **[H, with an important exception]**

The classic literature is reassuring and the modern evidence is not:

- **Hanson, Oprea & Porter (JEBO 2006)** — lab market with paid manipulators: prices stayed
  accurate, because informed traders **adjusted the threshold at which they'd trade** to
  compensate for the known bias in manipulator order flow. Manipulation was priced in. **[H]**
- **Camerer (JPE 1998)** — real money at racetracks: placed $500 and $1,000 bets, then cancelled
  them. Odds visibly moved, but the **net post-cancellation effect was ~zero and not statistically
  significant**, and replicated at a *smaller* (theoretically more manipulable) track. **[H]**
- **Rhode & Strumpf** — injected trades totalling **~2% of total volume** into the Iowa Electronic
  Market: prices moved initially and **reverted quickly**. Their century-plus historical survey
  finds election betting markets forecast well *despite* documented, repeated manipulation
  attempts by campaigns. **[H]**
- **The exception — Intrade 2012.** Rothschild & Sethi: a single anonymous trader placed **$4–7M**
  on Romney over the final two weeks, roughly **one third of all Romney-side volume**, and the
  price *did* stay distorted — an apparent "firewall" near 30%, with the Intrade–Betfair spread
  persistently widened for ~2 weeks. Arbitrage did not close it, plausibly because Intrade had
  capital and shorting constraints. The manipulator lost heavily. **[H]**
- **The modern qualifier.** A 2025 field experiment (arXiv 2503.03312) ran randomized price shocks
  across **817 markets** and found effects **still detectable up to 60 days later**, fading slowly.
  The three factors that most increase resistance: **trader count, trading volume, and the
  availability of an external probability estimate** (polls, another market). **[M]** —
  preprint, abstract-level reading.

**The synthesis that transfers:** self-correction is not a property of markets, it is a property of
*thick* markets *with an external anchor*. Remove either and manipulation persists. A 12-manager
league has neither. **[H]**

### B4. Rating-system manipulation and its countermeasures **[H]**

FIDE's operational answer is a **statistical outlier test with an explicit, very conservative
threshold**: Kenneth Regan's Intrinsic Performance Rating models P(player picks the engine's top
move) per position, backs out an implied skill level, and compares it to official Elo as a
**z-score**. FIDE's suspicion threshold is **z = 4.5** — about a **1-in-300,000** chance of arising
naturally. FIDE's 2024 Anti-Cheating Regulations define "manipulation" to explicitly include
**sandbagging and rating fraud**, minimum 3-month suspension. **[H]**

Chess.com's disclosed scale (Q1 2025): **~314,000 accounts closed in three months** (~3,500/day),
**~85% fully automated** across "100+ gameplay factors," and of ~28,000 appeals reviewed only
**0.2% granted**. Sandbagging detection is automated (warn-then-close) but no sandbagging-specific
closure count is published. **[H]** on the figures, **[L]** on any widely-circulated
sandbagging-specific numbers, which did not trace to a primary source.

The online-games analog is instructive for FTF because it *isn't* punitive: for smurfing, the
industry answer is not banning but **fast MMR re-calibration** — TrueSkill 2 exists partly to
shrink the cold-start window in which a miscalibrated rating is exploitable. **Fix the estimate
faster, rather than police the actor.** **[M]**

### B5. Robustness of pairwise-comparison ranking specifically **[H]**

This is FTF's exact mathematical family, and the news is blunt: **the standard Bradley–Terry /
Thurstone MLE has no robustness whatsoever.** Every comparison is weighted equally, so a small
fraction of adversarial or careless annotators distorts the fitted latent strengths with no
correction. Deliberate attacks on BT-based rankings are now formalized as constrained
combinatorial optimization (e.g. "Adaptive Subset Selection Attack") — manipulating a BT ranking
with a bounded number of adversarial comparisons is an *actively studied attack surface*, not a
hypothetical. **[H]**

The literature's fixes, in rough order of cost:

1. **Per-annotator reliability weighting** — Dawid–Skene (1979) fits a per-worker confusion matrix
   jointly with the unknown labels via EM, so unreliable, biased and random-answering raters are
   automatically down-weighted with no hand-flagging. Gold-standard items can be folded in as
   anchors that pin down the confusion-matrix estimation, which is strictly better than using
   honeypots alone. **[H]**
2. **Shrinkage / regularization** toward a prior (group lasso, empirical Bayes) — bounds how far a
   thinly-sampled item can drift. **[H]**
3. **Median or trimmed aggregation** instead of the mean, per the breakdown-point argument. **[H]**
4. **Kemeny consensus** satisfies the extended Condorcet property and resists certain manipulation
   patterns structurally — but is **NP-hard**, which is why production systems fall back to
   Borda/BT approximations and buy tractability with robustness. **[H]**

On collusion scale: no source gave a clean "N colluders move the aggregate by X%" law — a genuine
gap. The closest general statement in the recommender-shilling literature is that "even modest
attacks are sufficient to manipulate the behavior of the most commonly used recommendation
algorithms," directionally consistent with the mean's 1/(n+1) breakdown point. The best-documented
real case of a *small* coordinated bloc moving a platform-wide aggregate remains the 2008 Digg /
Ron Paul episode — low hundreds of accounts, in a system that weighted votes equally regardless of
account history. **[M]** Modern platforms answer with **pre-emptive damping**: reported Reddit
architecture applies a continuously-updated contributor-quality score that **down-weights or zeroes
low-trust accounts' votes at cast time**, before they ever count — not post-hoc removal. **[L]**,
non-primary sourcing.

### B6. Strategic misreporting: when does lying pay? **[H]**

**Kidney exchange** is the sharpest cautionary tale, because the misreporting is *rational and
observed*. Ashlagi & Roth (*Theoretical Economics* 2014) show transplant centers can reveal only
their hard-to-match pairs to a national clearinghouse while quietly doing easy 2-way exchanges
in-house — individually rational, collectively destructive, and explicitly described as behavior
"already observed," not hypothetical. Agarwal, Ashlagi, Azevedo, Featherstone & Karaduman (AER
2019) quantify the damage: fixing the fragmentation would **increase transplants by 30–63%**. And
there is a hard limit on how good a fix can be: **no mechanism can be simultaneously strategy-proof,
individually rational, and guarantee more than half the maximum transplants** even restricted to
2-way cycles. **[H]**

**School choice** supplies the design principle. The Boston (immediate-acceptance) mechanism is not
strategy-proof; Gale–Shapley deferred acceptance is. Pathak & Sönmez (AER 2008) formalize the harm:
with sincere and sophisticated players mixed, the Nash outcomes equal the stable matchings of an
economy where **sincere players lose priority to sophisticated ones** — naive truth-telling is a
*fixed tax*, not a gamble. Boston abandoned the mechanism in July 2005; the superintendent's stated
rationale was that a strategy-proof algorithm "levels the playing field." **[H]**

**But strategy-proofness does not buy truth-telling.** Rees-Jones & Skowronek (PNAS 2018) surveyed
graduating medical students immediately after the *strategy-proof* residency match and found
roughly **17%** self-assessed their reporting as non-truthful (a related figure of 23% appears in
overlapping summaries; treat the exact number as **[M]**, the double-digit magnitude as **[H]**).
Lab studies of strategy-proof mechanisms find truth-telling rates of only **~43–50% for DA** and
**~56–72% for TTC**. People misreport out of confusion and distrust even when it strictly cannot
help them. **[M]**

**The n=12 problem.** Every "manipulation vanishes at scale" result requires scale it does not
have. Immorlica & Mahdian and Kojima & Pathak (AER 2009) both need a **growing population with
bounded-length preference lists**, so that competition for any specific match becomes rare;
Roth & Peranson's empirical <1%-can-benefit finding is on the NRMP, i.e. **tens of thousands** of
participants. Meanwhile **Roth's 1982 impossibility bites at three agents per side** — it is not an
asymptotic result at all. A 12-team dynasty league is in the worst region of this map: large enough
for the impossibility theorems, far too small for the vanishing-incentive asymptotics, and with
*no* bounded-preference-list dilution because every manager effectively holds an opinion on every
asset. **[M]** — this synthesis is my inference across the papers, not any single paper's claim.

### B7. FTF's actual threat model — and why it is much better than KTC's **[H]**

I read the code rather than reasoning from the product description, and the conclusion changes the
answer materially. **FTF is not a crowdsourced value oracle.** Two facts:

1. **The consensus layer is externally sourced.** `data_loader.VALUES_URL` /`PICK_VALUES_URL` pull
   DynastyProcess's `values-players.csv` / `values.csv` (FantasyPros ECR-derived) and
   `seed_elo_for_value()` maps them affinely onto seed Elo. **User votes do not feed the consensus
   seeds.**
2. **Elo boards are per-user.** `ranking_service` decomposes each 3-player interaction into three
   pairwise decisions against *that user's* board. There is no shared pool of votes for a
   coordinated bloc to brigade.

This kills the entire Part-2 attack class that applies to KTC. There is **no Sybil surface on the
shared value layer**, because the shared value layer is not voted on. **[H]**

So what remains? The one attack worth naming: **a manager shades their own board to game the
suggestion engine.** Assessment: **this attack is self-defeating by construction, and that is a
design property worth protecting deliberately.**

The engine optimizes trades *against the user's reported board* — mutual gain is checked on both
parties' own boards, and `user_gain_ok_1for1` explicitly enforces "never send a player you rank
above the player you receive" on the user's **raw** board. A manager who votes down a player they
secretly covet has told the engine they don't want him; the engine will duly stop suggesting
acquisitions of that player and may suggest trading him away. **Misreporting your type to a
mechanism that optimizes for your reported type is a tax on yourself** — the same structural reason
DA is strategy-proof for the proposing side. **[M]** (reasoned from the code plus the school-choice
literature; not empirically tested.)

The residual risks are real but small and are **not** manipulation:

- **Sincere error and inattention.** Per §B6, even in strategy-proof mechanisms 17%+ misreport out
  of confusion. FTF's exposure here is *carelessness*, not adversarial gaming — a user
  speed-tapping through matchups produces a noisy board the engine takes at face value.
  Countermeasure: reliability weighting and shrinkage, not policing.
- **Board staleness after news.** A board that was sincere in June is a misreport in September.
- **The one genuine adversarial residue:** if FTF ever adds a *shared* crowd-value layer (its own
  KTC), it inherits the entire KTC threat model at 1/1000th of KTC's volume — the thin-market case
  from §B3, where manipulation demonstrably does *not* self-correct. **This is the decision to be
  careful about.** **[H]**

Damping that already exists and should be kept: **confidence shrinkage** `w = n/(n+4)` toward the
consensus seed (a thinly-sampled player cannot diverge far, which caps the value of a cheap
shading attack), the **range-overlap** gate, the **junk-filler** floors (`filler_min_frac` 0.25 +
`asset_floor_abs` 450), and the **consolidation raw-loss** cap (0.15). Together these bound how far
a distorted board can push an actual suggestion. **[H]**

---

## Part 3 — Governance calibration

### C1. Platform veto settings: the industry converged on short windows and away from votes **[H]**

| Platform | Model | Specifics |
|---|---|---|
| **Sleeper** | Commissioner-only cancellation; **no native league-vote veto**. Review-period length is a commissioner setting. Third-party guides report the emerging norm as **commissioner-only, ~48h**. | **[M]** on the default |
| **ESPN** | League vote, **48-hour review**; in a standard 10-team league **4 votes against cancels** (~40%). | **[H]** |
| **Yahoo** | League vote, **~1/3 of managers** must vote against (rounds up). Prize leagues instead: 2-day protest window, Yahoo staff review within 24h. | **[H]** |
| **Fantrax** | Configurable. Common in-season: **24h window, two-thirds majority to overturn**; some leagues 48h. Off-season: **1 week**. Alternative thresholds ~51%. | **[H]** |
| **MFL** | Configurable: no approval / commissioner approval / league poll. | **[M]**, numeric default unconfirmed |

Two patterns transfer. **(1) The window is short** — 24–48 hours in-season everywhere. **(2) The
direction of travel is away from peer votes**, on the explicit theory that vote-vetoes get
weaponized by managers protecting their own playoff odds rather than policing fairness. **[H]**

### C2. What actually triggers a veto **[M]**

The stated norm is near-unanimous across practitioner sources: **veto only for provable collusion,
never for lopsidedness.** "Team owners should be free to run their teams however they see fit —
including poorly."

The revealed norm is different, and the difference is the useful part. Old Man Dynasty's account
of a five-aging-stars-for-young-assets deal vetoed "within hours — the fastest veto the author had
witnessed" is instructive precisely because **the proposer agreed with the veto afterward**, and
reframed it: the league blocked the trade not because either party was cheated but because it
would have made one team dominant enough that the league stopped being fun. That is a **third
category** beyond collusion and unfairness — **competitive-balance outrage** — and it is
consolidation-shaped, not value-gap-shaped. **[M]**

**No survey or dataset quantifies what value gap triggers outrage.** This is a real hole in the
practitioner literature. The data to answer it exists (Dynasty Daddy cites 1M+ trades across 200k+
leagues; FantasyCalc runs millions of real trades) but nobody has published the analysis. **[H]**
that the gap exists.

### C3. League mortality: the evidence is anecdotal and the gap is an opportunity **[L]**

Every dynasty outlet treats **orphan teams as a recurring structural problem** — FantasyPros,
Footballguys, Dynasty Nerds and FantasyPoints all run orphan-strategy content, dispersal drafts are
the standard remedy, and **fantasyorphans.com exists as a standalone matchmaking business** for
orphan teams, which is itself market evidence of frequency. Commissioner countermeasures in the
wild: **requiring 2 years of dues upfront** at startup, and requiring managers who trade away
future rookie picks to prepay a future season. **[H]** that the problem is real and common.

**No published fold rate, orphan rate, or turnover statistic was found for any platform.** The one
quantitative-flavored claim located is FFPC's (a paid, managed platform) that its leagues "never
fold — literally, it has never happened," offered as a contrast to free home leagues. **[L]**

**No study links trade volume to league survival.** Not one. The datasets exist; the analysis
doesn't. **[H]** that the gap exists.

This is worth saying directly: **FTF's own Sleeper-synced corpus could produce the first real
dataset on dynasty league mortality and its correlates.** That is a research asset and a marketing
asset, and it is the only path to *empirically* calibrating the fairness band rather than guessing
it — see the transfer notes.

---

## 1. Best practices

1. **Price an uncertain asset as a distribution, and let the utility function pick the summary
   statistic.** Brill & Wyner's 89%-vs-13% result is the proof that mean and tail can disagree by
   an order of magnitude on the same asset. Contenders buy expectation; rebuilders buy the tail.
   (A2, A4) **[H]**
2. **Condition slot distributions on the owner's projected finish where you can.** It cuts a
   contender's-first dispersion 3.6x and corrects a 21%/36% two-sided mispricing. (A4) **[M]**
3. **Widen the acceptance band in proportion to asset variance, not just sampling noise.** The
   range-overlap construction — pass if intervals overlap *or* the point ratio clears the
   threshold — is the right shape; it just needs the right `unc`. (A5) **[H]**
4. **Make truth-telling the dominant strategy by optimizing against the reported type.** DA's
   lesson: when the mechanism serves you *your* reported preferences, lying is a tax on yourself.
   This is the strongest manipulation defense available and it is architectural, not detective.
   (B6, B7) **[H]**
5. **Anchor the shared value layer externally, not on your own users' votes.** FTF's use of
   DynastyProcess for consensus seeds removes the entire Sybil/brigading attack class. The
   prediction-market literature says the same thing from the other side: resistance rises with
   **an available external probability estimate**. (B3, B7) **[H]**
6. **Weight raters by reliability rather than filtering them.** Dawid–Skene-style per-rater
   weighting dominates attention checks, which experienced participants learn to pass. Use gold
   items as *anchors inside* the reliability model, not as a standalone gate. (B1, B5) **[H]**
7. **Shrink thinly-sampled estimates toward a prior.** `w = n/(n+n0)` caps how far a lightly-voted
   asset can drift, which simultaneously fixes noise and bounds cheap manipulation. FTF already
   does this. (B5, B7) **[H]**
8. **Build a graduated-confidence pipeline, not a single gate.** Wikipedia's block-before-save →
   auto-revert → hold-for-review → human-patrol ladder puts cheap layers on the obvious majority
   and reserves expensive review for the ambiguous tail. (B2) **[H]**
9. **Prefer fast re-estimation over enforcement.** The smurf answer in online games is
   re-calibrate MMR quickly, not ban. Applied to FTF: a stale or careless board should be *fixed*
   (re-prompt, decay, re-ask) rather than policed. (B4) **[M]**
10. **Use median/trimmed aggregation wherever you aggregate across people.** Breakdown point 50%
    vs 1/(n+1). (B5) **[H]**
11. **Keep governance windows short and commissioner-shaped.** 24–48h is the whole industry, and
    the drift away from peer votes is a warning that peer judgment gets weaponized. (C1) **[H]**
12. **Design against the competitive-balance objection, not only the fairness objection.** The best
    documented real veto was a *consolidation* deal that passed value fairness and failed the "is
    the league still fun" test. (C2) **[M]**

## 2. Antipatterns

1. **Point-estimating a future draft pick.** A single number for an asset with CV ≈ 0.385 is the
   valuation-integrity equivalent of reporting a mean with no error bar — and it silently
   overprices contenders' picks by 21% and underprices rebuilders' by 36%. (A3, A4) **[H]**
2. **A constant geometric year discount.** 0.85/yr (FTF) and 0.80/yr (DynastyProcess) are both
   contradicted by the observed −6% then −30% term structure. (A3, A5) **[M]**
3. **Attention checks as the primary quality control.** The one defense KTC publishes is the one
   the crowdsourcing literature ranks lowest, and its effectiveness decays as the population
   adapts. (B1) **[H]**
4. **Un-robustified Bradley–Terry.** Equal-weighted pairwise MLE has no breakdown resistance, and
   bounded-budget attacks on it are a published optimization problem. Never ship BT over
   multi-party inputs without reliability weighting or shrinkage. (B5) **[H]**
5. **Assuming a thin market self-corrects.** It does not. Intrade 2012 held a distorted price for
   two weeks against ~⅓-of-volume pressure; the 2025 817-market field experiment finds shocks
   detectable at 60 days. Self-correction requires thickness *and* an external anchor. (B3) **[H]**
6. **Launching a crowd-voted shared value layer at low volume.** Inheriting KTC's threat model at
   1/1000th of KTC's vote volume is strictly worse than either having no crowd layer or using an
   external one. (B3, B7) **[H]**
7. **Relying on strategy-proofness to produce truthful reports.** 17%+ misreport in the residency
   match *where it cannot help them*; lab truth-telling under DA runs ~43–50%. Design for sincere
   error, not just for adversaries. (B6) **[M]**
8. **Importing large-market incentive results into a 12-team league.** Kojima–Pathak and
   Immorlica–Mahdian need growth with bounded preference lists; Roth–Peranson's <1% is measured at
   NRMP scale. None of it applies at n=12. (B6) **[M]**
9. **Detecting fraud from text/behavioral surface features alone.** Ground-truth Amazon work says
   network structure wins precisely because it is expensive to fake. (B2) **[H]**
10. **Peer-vote vetoes as a fairness mechanism.** The whole industry is walking away from them
    because managers vote their own playoff odds. Any FTF feature resembling a league vote on
    suggestion quality inherits this. (C1) **[H]**
11. **Claiming a league-health or fairness threshold is "calibrated" without data.** No published
    number exists for what value gap triggers outrage; anyone quoting one is guessing. Say so.
    (C2) **[H]**

## 3. What matters most (ranked)

1. **Conditioning pick value on the owning team, and carrying pick variance into the fairness
   band.** This is the single largest measured valuation error in FTF today (a 57-point spread of
   two-sided mispricing) and the fix is small: a slot distribution per pick and an uncertainty
   floor. Everything downstream — mutual gain, fairness, defensibility — is currently computed on
   a wrong number for the most-traded asset class in dynasty. (A3, A4, A5) **[M/H]**
2. **Never voting the shared value layer.** FTF's externally-anchored consensus is a structural
   advantage over every crowdsourced competitor, and it is the kind of advantage that is quietly
   thrown away by a well-meaning "let's build our own KTC" feature. Protect it as an architectural
   invariant with a written decision. (B3, B7) **[H]**
3. **Keeping board-shading self-defeating.** The engine's incentive-compatibility comes from
   optimizing against the user's own reported board (`user_gain_ok_1for1` on the *raw* board).
   Any future change that makes a user's board influence what *others* are offered breaks this and
   converts a non-problem into a real one. (B6, B7) **[H]**
4. **Reliability weighting + shrinkage over policing.** The dominant real threat is careless
   voting, not adversarial voting, and both are treated by the same machinery. Shrinkage already
   ships; per-user reliability does not. (B1, B5, B7) **[H]**
5. **Surviving the competitive-balance objection, not just the value-gap objection.** The engine's
   consolidation gates are load-bearing governance features, not just math. (C2) **[M]**
6. **Owning the missing dataset.** Nobody has published dynasty league mortality, orphan rates, or
   the trade-volume/survival correlation. FTF's synced corpus can. This converts the fairness band
   from a guess into a measurement. (C3) **[M]**
7. **Short, commissioner-shaped governance affordances** if FTF ever touches trade review. (C1)
   **[H]**

## 4. What doesn't matter even though it seems like it should

- **Which pick-value *chart* you adopt.** JJ, Stuart, Fitzgerald–Spielberger and PFF differ wildly
  in shape, and it barely matters for FTF, because fairness is a **ratio between two packages on a
  single scale**. A uniformly-too-steep curve mostly cancels. What does *not* cancel is
  **within-league heterogeneity** — pricing every team's first identically — which is why A4 ranks
  first and chart choice ranks nowhere. **[M]**
- **Sybil resistance, vote rate-limiting, and account-graph detection.** The entire apparatus that
  Yelp, Reddit, and chess.com need is inapplicable to FTF as built: private per-user boards over an
  external consensus have no shared aggregate to attack. Building Sybil defenses now would be
  defending a door that isn't in the wall. **[H]**
- **The absolute calibration of pick values.** Whether a mid 1st is "2,117" or "2,904" is nearly
  irrelevant to whether a trade is fair, as long as it's consistent — but it is *very* relevant to
  advice quality and to what users believe. Keep the two concerns separate; don't chase precision
  in the fairness path. (Extends round-2/04's "cardinal value precision doesn't matter" finding —
  with the correction that *relative* pick pricing across teams does.) **[M]**
- **Detecting the malicious board-shader.** At n=12, with a mechanism that optimizes against the
  reported board, this person harms only themselves. Spending detection effort here is spending it
  on the one attacker whose attack already fails. **[M]**
- **Veto-proofing as a feature.** Reaffirmed from round-2/04 and strengthened by C1: the industry
  is removing peer vetoes, not adding them, and the real veto trigger (competitive balance) is
  addressed by the consolidation gates the engine already has. **[M]**
- **Attention-check ("test matchup") infrastructure.** Tempting because KTC publishes it; ranked
  lowest by the literature; and FTF's shrinkage already does the job it would do. Reputation
  weighting is the better spend. **[M]**

## Transfer notes for FTF

### T1 — Pick-valuation recommendation

**Do these three things, in this order.**

**(a) Replace `pick_pool_value`'s unconditional Mid pricing with an owner-conditioned slot
distribution.** FTF already syncs rosters and standings, so the owning team's projected finish is
available. Concretely: map each owned future pick to a slot *distribution* — a simple three-bin
prior keyed off the owner's projected finish (bottom third → Early, middle → Mid, top third →
Late) is already most of the win, since FTF's Early/Mid/Late Elo ladder is well calibrated (A4,
Finding 6: FTF 2.01x vs market 1.97x early/late ratio). The current code comments
("we can't yet resolve a pick's slot," operator decision 2026-07-18) predate the standings sync
being reliable; this is a decision worth revisiting with the 21%/36% mispricing numbers attached.
Expected-value pricing should use the **mean** of the bin distribution, not the modal bin.

**(b) Give picks an uncertainty *floor* in the fairness gate.** `_value_uncertainty` currently
returns `range_base / sqrt(1 + n)` where `n` is the user's comparison count — **epistemic
uncertainty about taste**, which correctly shrinks to zero. A pick's **outcome** uncertainty is
irreducible and must not shrink. Add a per-asset floor:

```
unc(pid) = max(range_base / sqrt(1 + n), slot_unc(pid))
```

with `slot_unc = 0` for players, and for picks something like **0.35–0.40 for an unconditioned
future 1st**, **~0.30 for a rebuilder's first**, **~0.11 for a contender's first**, scaled up by
years out. These come straight from A4's CV table and happen to land almost exactly on FTF's
existing `range_base = 0.35`, which makes the change cheap to reason about and easy to explain.
The *shape* — wider bands for higher-variance assets — is already implemented and shipping; this
supplies the missing input.

**(c) Replace the constant `YEAR_DISCOUNT = 0.85` with a term structure.** The observed curve is
roughly −6% at one year out and −30% at two. A two- or three-element lookup keyed on `years_out`
is sufficient; a constant rate is wrong at both ends. Lower priority than (a) and (b) — the error
is single-digit-to-15%, not 21–36%.

**Do NOT** chase a better pick-value *chart*. Chart choice largely cancels in a ratio test (§4);
owner-conditioning does not.

**One product-facing consequence worth taking seriously.** If picks carry a visible band rather
than a number, FTF can say something no competitor says: *"a 2027 1st from a contender is worth
about 2,400 ± 250; from a rebuilder, about 4,500 ± 1,300."* That is both more honest and more
persuasive than KTC's single number, and it is a defensible answer to the round-2 finding that
users demand a "calc win" — you cannot demand a calc win against an interval. It also gives the
rebuild/contend counterparty asymmetry (A2's utility-function point) a legible surface: the tail
buyer and the expectation buyer can both be right about the same pick, which is precisely the
mutual-gain story FTF wants to tell.

### T2 — Board-gaming threat assessment and countermeasures

**Assessment: LOW risk today, and the reason is architectural — protect the architecture, not the
votes.**

FTF's consensus seeds come from DynastyProcess (external), and Elo boards are per-user. There is
**no shared voted aggregate** for a coordinated bloc to attack, which removes the entire KTC/Yelp/
Digg threat class. And because the engine optimizes against the user's *own reported* board — with
`user_gain_ok_1for1` enforcing "never send a player you rank above the player you receive" on the
**raw** board — a manager who votes down a player they covet has instructed the engine to stop
offering that player to them. Shading is a tax on the shader, for the same structural reason
deferred acceptance is strategy-proof for the proposing side.

**Concrete countermeasures, ranked by value:**

1. **Write the invariant down as a decision (D-###) before someone proposes an in-house crowd
   value layer.** Something like: *"FTF's consensus value layer is externally anchored. User votes
   affect only the voting user's own board. Any feature that lets one user's votes move another
   user's prices requires an explicit threat-model review."* This is the highest-leverage item in
   this memo and it costs nothing. The reason is §B3: at FTF's volume a home-grown crowd oracle
   would be the *thin* market where manipulation demonstrably does **not** self-correct.
2. **Add per-user reliability weighting to board fitting** (Dawid–Skene-shaped). The real problem
   is careless voting, not malice: 17%+ misreport even where it cannot help them, and lab
   truth-telling under strategy-proof mechanisms runs 43–50%. A user whose pairwise judgments are
   internally inconsistent (high intransitivity rate, implausibly fast responses) should have their
   comparisons down-weighted — which is *also* the correct treatment for the adversarial case, so
   one mechanism covers both. Cheaper and more effective than test matchups.
3. **Treat intransitivity rate as the native quality signal.** The 3-player format is a gift here:
   each interaction yields three pairwise decisions whose mutual consistency is checkable for free,
   and consistency across *sessions* on the same pair is a second free signal. This is FTF's
   equivalent of Regan's z-score — a statistical outlier test on behavior, with no honeypots and no
   extra user burden. Use it to weight, never to accuse; note Wikipedia's finding that false
   positives land overwhelmingly on newcomers.
4. **Keep shrinkage; do not weaken it.** `w = n/(n+4)` toward the consensus seed is the single
   mechanism bounding how far any board — careless or adversarial — can drift on a thinly-sampled
   asset. It is also the reason a cheap shading attack has a low ceiling.
5. **Add staleness decay, not staleness policing.** A June board is a September misreport. Per §B4,
   the right answer to a miscalibrated rating is faster re-estimation, not enforcement: decay
   confidence over time (so `unc` widens and shrinkage re-asserts) and re-prompt on assets whose
   consensus has moved sharply since the user last voted on them.
6. **Do NOT build test/honeypot matchups.** Lowest-ranked defense in the literature, learnable by
   repeat users, and redundant with (2) and (3).

### T3 — How to set the consensus fairness band width

**The honest headline: no published number exists.** No survey or dataset quantifies what value gap
triggers league outrage (C2). Anyone — including this memo — quoting a band width is reasoning from
structure, not measurement. Say so in the docs, and then go get the measurement.

**Structural recommendations for the interim:**

1. **Keep the band as a two-test disjunction, which is what `_fairness()` already is.** Pass if the
   value intervals overlap **or** the point ratio clears `fairness_threshold`. This is the right
   shape because it makes the band *automatically* wider for uncertain packages and tighter for
   certain ones, without a second knob. With T1(b)'s uncertainty floor, a pick-heavy package earns
   a genuinely wider band and a two-known-players swap earns a tight one — which is exactly the
   behavior a neutral observer would endorse. **[M]**
2. **`fairness_threshold = 0.75` is defensible; do not tighten it.** A 0.75 lesser/greater ratio
   is a 25% value gap. Compare the governance evidence: ESPN needs ~40% of a league to cancel a
   trade, Fantrax two-thirds, Yahoo a third — these are *high* bars, and the stated community norm
   is that lopsidedness alone should never trigger a veto. The binding constraint on FTF is
   liquidity (round-2/04's finding that un-sent offers, not un-found matches, limit trade volume),
   and a tighter band directly costs suggestions. The relaxed 0.55 stage is a sensible escape
   valve. **[M]**
3. **The band should be widened by uncertainty, never by desperation.** The current relaxation
   ladder ("fairness_band" → "fairness_band+surplus_floor") widens the band when nothing else
   qualifies. That is a *scarcity* trigger, not an *epistemic* one, and it is the mechanism most
   likely to produce a card the league later calls a fleece. Prefer: widen automatically when the
   package is genuinely uncertain (T1b), and when scarcity forces relaxation, **say so on the
   card** ("wider than your usual fairness band") — which the code already tracks via
   `relaxed_reason`. Surfacing it is the difference between an honest band and a hidden one. **[M]**
4. **Add a competitive-balance test alongside the value test.** C2's best-documented real veto was
   a *consolidation* that was value-fair. FTF's `consolidation_raw_loss_frac = 0.15` and the
   package depth discount are already doing governance work; recognize them as such in the docs and
   tune them against the veto evidence rather than against value math alone. **[M]**
5. **Then measure it.** The calibration path is FTF's own data, and it is the only one available to
   anyone (C3). Log, per suggested and per executed trade: consensus value gap, uncertainty-adjusted
   gap, whether it was accepted, whether it was later reversed/complained about, and league-level
   trade volume and manager activity. Two regressions nobody has published: **(i)** value gap →
   P(accepted) and P(regret), which calibrates the band empirically; **(ii)** trade volume →
   league survival, which is the dynasty-mortality result the whole hobby lacks. Both are
   marketing assets as well as engineering ones.

---

## 5. Not researched / follow-up topics

- **Dynasty rookie-pick hype cycle (the "picks peak before the draft, decay after" claim).** Not
  established with data. The WebSearch budget expired before this could be swept, and FantasyCalc's
  historical-values endpoint was not reverse-engineered. **Highest-value follow-up in Part 1**: it
  is directly testable against the FantasyCalc or KTC value history, and if real it means FTF's
  pick pricing has a *seasonal* bias, not just a slot bias.
- **Published bust rates by dynasty rookie-pick slot.** Brill & Wyner's bust-spike model and elite
  probabilities are NFL-draft-level; the dynasty-specific hit rate by rookie pick (1.01 vs 1.06 vs
  2.05) was not found. Would let T1(b)'s `slot_unc` be fit rather than derived from price
  dispersion.
- **Replication of the A4 snapshot analysis.** All of A4 rests on a single FantasyCalc API pull on
  2026-08-16, in one format, with an ambiguous current-year label. Re-run across formats
  (superflex especially — pick premiums differ), across platforms (KTC's Early/Mid/Late ladder),
  and across dates before treating the median-vs-mean finding as settled.
- **Whether FantasyCalc/KTC's generic-pick price is a median by design or by accident.** The
  four-significant-figure match is either a deliberate modeling choice or a coincidence, and the
  answer changes whether it's evidence about crowd risk preferences.
- **Formal small-market analysis of FTF's mechanism.** §B6's "the asymptotics don't apply at n=12"
  is my inference across papers, not a result. A proper analysis — is FTF's suggestion mechanism
  strategy-proof for the user given the engine's actual objective? — would either confirm T2's
  low-risk verdict rigorously or find the exploit.
- **PNAS network-detection precision/recall figures** (403 on fetch), **chess.com
  sandbagging-specific closure counts** (a circulating "50,000 accounts / +15% YoY" figure did not
  trace to a primary source — do not cite), **Lichess rating-manipulation ban volumes**, and
  **MFL's default numeric review window**. All flagged unverified by the sweeps.
- **The arXiv 2503.03312 field experiment** was read at abstract level only; its effect sizes
  matter for the thin-market argument and deserve a full read before that claim carries more weight.
- **Quantitative dynasty league mortality.** Still unfound (round-2/04 flagged this too, and a
  second sweep confirms it). Now upgraded from "gap" to "opportunity" — see T3(5).
- **Reddit r/DynastyFF primary threads on KTC manipulation.** Reddit blocks the crawler at both
  the HTML and JSON endpoints; all KTC community criticism here remains secondary-sourced **[M]**.
  A manual browse session would firm this up.

## 6. Sources

**Part 1 — draft-pick valuation**

1. Brill & Wyner, "The Loser's Curse and the Critical Role of Specifying a Utility Function" — https://arxiv.org/abs/2411.10400 ; full text https://arxiv.org/html/2411.10400v4 ; earlier versions https://arxiv.org/html/2411.10400v1 , https://arxiv.org/html/2411.10400v2
2. Massey & Thaler, "The Loser's Curse: Decision Making & Market Efficiency in the National Football League Draft" — https://www.researchgate.net/publication/228290300_The_Loser's_Curse_Decision_Making_Market_Efficiency_in_the_National_Football_League_Draft
3. Advanced Football Analytics, "The Value of Each Draft Pick: A Re-Examination of Massey-Thaler Surplus Value under the New CBA" — https://advancedfootballanalytics.com/index.php/home/research/draft/242-the-value-of-each-draft-pick-a-re-examination-of-massey-thaler-surplus-value-under-the-new-cba (fetch returned HTTP 500; cited from search abstract only, **[L]**)
4. Fitzgerald–Spielberger NFL Draft Trade Value Chart (OverTheCap) — https://overthecap.com/draft-trade-value-chart
5. Jimmy Johnson chart values (DraftTek) — https://www.drafttek.com/NFL-Trade-Value-Chart.asp
6. Chase Stuart, AV-based draft value chart (Football Perspective) — https://www.footballperspective.com/draft-value-chart/
7. Michael Lopez, "Rethinking the draft curve" — https://statsbylopez.netlify.app/post/rethinking-draft-curve/
8. KeepTradeCut FAQ (adapted Elo, test KTCs, Early/Mid/Late future picks, Value Adjustment) — https://keeptradecut.com/frequently-asked-questions ; About — https://keeptradecut.com/about
9. DynastyProcess values methodology (exponential ECR decay; future picks at 80% per year) — https://dynastyprocess.com/values/ ; data repo — https://github.com/dynastyprocess/data
10. FantasyCalc live values API (slot and generic pick prices; snapshot 2026-08-16, 12-team 1QB PPR dynasty) — https://api.fantasycalc.com/values/current?isDynasty=true&numQbs=1&numTeams=12&ppr=1 ; site — https://www.fantasycalc.com/

**Part 2 — manipulation resistance**

11. Luca & Zervas, "Fake It Till You Make It: Reputation, Competition, and Yelp Review Fraud" (Management Science 2016) — https://pubsonline.informs.org/doi/abs/10.1287/mnsc.2015.2304 ; SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2293164 ; BU summary https://www.bu.edu/articles/2013/yelp-reviews-can-you-trust-them/
12. He, Hollenbeck, Overgoor, Proserpio & Tosyali, "Detecting Fake Review Buyers Using Network Structure: Direct Evidence from Amazon" (PNAS 2022) — https://www.pnas.org/doi/10.1073/pnas.2211932119 ; SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4147920
13. He, Hollenbeck & Proserpio, "The Market for Fake Reviews" (Marketing Science 2022) — https://pubsonline.informs.org/doi/10.1287/mksc.2022.1353 ; PDF https://www.anderson.ucla.edu/sites/default/files/document/2025-08/The%20Market%20for%20Fake%20Reviews.pdf ; Amazon/Facebook enforcement https://time.com/6198725/amazon-lawsuit-facebook-groups-fake-reviews/
14. Wikipedia ClueBot NG bot-approval trial (false-positive vs catch-rate tradeoff) — https://en.wikipedia.org/wiki/Wikipedia:Bots/Requests_for_approval/ClueBot_NG/Trial_2 ; https://en.wikipedia.org/wiki/Wikipedia:Bots/Requests_for_approval/ClueBot_NG/Pretrial ; overview https://wikimedia.brussels/meet-cluebot-ng-an-anti-vandal-ai-bot-that-tries-to-detect-and-revert-vandalism/
15. MediaWiki, "Manual:Combating vandalism" (layered defenses) — https://www.mediawiki.org/wiki/Manual:Combating_vandalism ; pending changes https://en.wikipedia.org/wiki/Wikipedia:Pending_changes
16. Priedhorsky et al., "Creating, Destroying, and Restoring Value in Wikipedia" (CSCW 2007) — https://www.researchgate.net/publication/234775766_Creating_destroying_and_restoring_value_in_Wikipedia
17. Hanson, Oprea & Porter, "Information Aggregation and Manipulation in an Experimental Market" (JEBO 2006) — http://mason.gmu.edu/~rhanson/biastest.pdf ; summary https://mason.gmu.edu/~rhanson/testbias.html
18. Camerer, "Can Asset Markets Be Manipulated? A Field Experiment with Racetrack Betting" (JPE 1998) — https://authors.library.caltech.edu/80440/
19. Rhode & Strumpf, "Manipulating Political Stock Markets" — https://s3.amazonaws.com/fieldexperiments-papers2/papers/00325.pdf ; "Historical Political Futures Markets" (NBER w14377) — https://www.nber.org/system/files/working_papers/w14377/w14377.pdf
20. Rothschild & Sethi on the 2012 Intrade "Romney whale" — http://rajivsethi.blogspot.com/2013/09/the-romney-whale.html ; https://slate.com/news-and-politics/2013/09/2012-intrade-paper-suggests-a-single-intrade-trader-spent-millions-to-make-it-look-like-mitt-romney-could-win.html
21. "How manipulable are prediction markets?" (817-market field experiment, preprint) — https://arxiv.org/abs/2503.03312
22. Polymarket 2024 "Trump whale" coverage — https://www.nbcnews.com/business/markets/french-trader-bet-28-million-trump-election-win-4-polymarket-accounts-rcna177106 ; https://fortune.com/2024/11/02/french-whale-polymarket-30-million-donald-trump-election-bet-kamala-harris
23. FIDE Anti-Cheating Regulations (sandbagging, rating fraud) — https://handbook.fide.com/files/handbook/ACCRegulations.pdf ; guidelines https://www.fide.com/FIDE/handbook/Anti%20Cheating%20Guidelines.pdf
24. Kenneth Regan, "Cheating Detection and Cognitive Modeling at Chess" (IPR, z=4.5 threshold) — https://cse.buffalo.edu/~regan/Talks/CogSciOct2024np.pdf ; https://en.chessbase.com/post/prof-regan-s-statistical-system ; https://time.com/6227677/magnus-carlsen-hans-niemann-kenneth-regan-chess-scandal/
25. Chess.com, "Our Fair Play System Explained" (Q1 2025 closure and appeal statistics) — https://www.chess.com/cheating
26. Minka et al., "TrueSkill 2" (fast cold-start recalibration) — https://www.microsoft.com/en-us/research/wp-content/uploads/2018/03/trueskill2.pdf ; boosting/smurfing survey https://www.sciencedirect.com/science/article/pii/S1875952120301014
27. "Ranking Abuse via Strategic Pairwise Data Perturbations" (attacks on Bradley–Terry rankings) — https://arxiv.org/html/2604.17805v1 ; BT survey https://arxiv.org/pdf/2601.14727 ; BT diagnostics https://rss.onlinelibrary.wiley.com/doi/full/10.1111/rssa.12959
28. Dawid–Skene reliability weighting and variants — https://www.researchgate.net/publication/301875153_Reliable_Crowdsourcing_under_the_Generalized_Dawid-Skene_Model ; weighted majority voting bounds https://arxiv.org/pdf/1411.4086 ; gold data vs multiple workers (Ipeirotis) https://www.behind-the-enemy-lines.com/2010/09/worker-evaluation-in-crowdsourcing-gold.html
29. Attention checks vs reputation screening on MTurk — https://www.surveypractice.org/article/77641-comparing-amazon-s-mturk-and-a-sona-student-sample-a-test-of-data-quality-using-attention-and-manipulation-checks ; https://pubmed.ncbi.nlm.nih.gov/34357539/ ; adversarial attacks on crowdsourcing QA https://www.researchgate.net/publication/338644755_Adversarial_Attacks_on_Crowdsourcing_Quality_Control
30. Robust pairwise-label aggregation — https://arxiv.org/pdf/1501.06202 ; Kemeny rank aggregation complexity — https://link.springer.com/article/10.1007/s10458-013-9236-y
31. Shilling/collusion attacks on recommenders — https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0196533 ; https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0130968
32. Sybilproof reputation mechanisms — https://www.researchgate.net/publication/228367243_Sybilproof_reputation_mechanisms ; Reddit vote-manipulation policy https://reddit.zendesk.com/hc/en-us/articles/360043066412-What-constitutes-vote-cheating-or-vote-manipulation- ; 2008 Digg/Ron Paul bloc (secondary) https://news.ycombinator.com/item?id=7974181
33. Ashlagi & Roth, "Free riding and participation in large scale, multi-hospital kidney exchange" (Theoretical Economics 2014) — https://onlinelibrary.wiley.com/doi/abs/10.3982/TE1357 ; NBER w16720 https://www.nber.org/system/files/working_papers/w16720/w16720.pdf ; AER P&P 2012 https://web.stanford.edu/~alroth/papers/KidneyExchange%20AEAPP2012.pdf
34. Agarwal, Ashlagi, Azevedo, Featherstone & Karaduman, "Market Failure in Kidney Exchange" (AER 2019 / NBER w24775) — https://www.nber.org/papers/w24775 ; https://economics.mit.edu/sites/default/files/publications/agarwal-et-al-kidney-exchange.pdf ; VoxEU summary https://cepr.org/voxeu/columns/market-failure-kidney-exchange
35. Abdulkadiroğlu, Pathak, Roth & Sönmez, "Changing the Boston School Choice Mechanism" (NBER w11965) — https://www.nber.org/papers/w11965
36. Pathak & Sönmez, "Leveling the Playing Field: Sincere and Sophisticated Players in the Boston Mechanism" (AER 2008) — https://www.aeaweb.org/articles?id=10.1257/aer.98.4.1636
37. Rees-Jones & Skowronek, "An experimental investigation of preference misrepresentation in the residency match" (PNAS 2018) — https://www.pnas.org/doi/10.1073/pnas.1803212115 ; open access https://pmc.ncbi.nlm.nih.gov/articles/PMC6233132/ ; companion JEBO paper https://www.ssrn.com/abstract=2662670
38. "Strategy-proofness in experimental matching markets" (observed truth-telling rates) — https://www.waseda.jp/fpse/winpec/assets/uploads/2019/09/WP_E1913.pdf
39. Kojima & Pathak, "Incentives and Stability in Large Two-Sided Matching Markets" (AER 2009) — https://www.aeaweb.org/articles?id=10.1257/aer.99.3.608 ; PDF https://economics.mit.edu/sites/default/files/publications/kojima.pdf
40. Immorlica & Mahdian, "Incentives in Large Random Two-Sided Markets" — https://immorlica.com/pubs/stableMarriageJournal.pdf ; ACM TEAC https://dl.acm.org/doi/10.1145/2656202
41. Roth & Peranson, "The Redesign of the Matching Market for American Physicians" (AER 1999) — https://web.stanford.edu/~alroth/papers/rothperansonaer.PDF
42. "On the Susceptibility of the Deferred Acceptance Algorithm" — https://arxiv.org/abs/1502.06318
43. Myerson–Satterthwaite overview — https://saylordotorg.github.io/text_introduction-to-economic-analysis/s19-02-myerson-satterthwaite-theorem.html ; "Second-Best Bilateral Trade is 1/2 Efficient" https://arxiv.org/abs/2606.03849 ; Gibbard–Satterthwaite overview https://umbrex.com/resources/economics-concepts/microeconomic-theory/gibbard-satterthwaite-theorem/
44. Farrell & Gibbons, "Cheap Talk Can Matter in Bargaining" (JET 1989) — https://pages.ucsd.edu/~bslantchev/courses/pdf/farrell-jet1989v48n1.pdf ; "Cheap Talk, Round Numbers, and the Economics of Negotiation" (NBER w21285) https://www.nber.org/papers/w21285

**Part 3 — governance**

45. Sleeper support: trading and vetoes — https://support.sleeper.com/en/articles/3188802-how-to-trade ; https://support.sleeper.com/en/articles/4702096-trading-details ; https://support.sleeper.com/en/articles/3200544-can-i-veto-a-trade ; commissioner-setting guidance https://lordskunk.com/guides/best-sleeper-league-settings/
46. ESPN trade review and veto thresholds — https://support.espn.com/hc/en-us/articles/360000973131-Trade-Review ; https://support.espn.com/hc/en-us/articles/115003850351-Veto-or-Protest-a-Trade
47. Yahoo trade protest/veto rules — https://help.yahoo.com/kb/protest-veto-trade-yahoo-fantasy-sln6613.html
48. Fantrax league setup — trade voting system and windows — https://fantraxhq.com/setting-up-your-fantrax-league-part-2/
49. MyFantasyLeague features and operational policies — https://home.myfantasyleague.com/features.html ; https://home.myfantasyleague.com/operational-policy/
50. FantraxHQ, "Whose Veto? What Collusion?" (collusion-only norm) — https://fantraxhq.com/whose-veto-what-collusion/ ; Bleacher Report veto guide https://bleacherreport.com/articles/214600-veto-power-a-guide-to-evaluating-pending-fantasy-football-trades
51. Old Man Dynasty, "The trade veto is the most fun you can have without winning your league" (competitive-balance veto case study) — https://oldmandynasty.substack.com/p/the-trade-veto-is-the-most-fun-you
52. Dynasty orphan-team literature — https://www.fantasypros.com/2020/02/dynasty-orphan-takeover-strategy-fantasy-football/ ; https://www.footballguys.com/article/2024-how-to-fill-orphans-in-your-dynasty-leagues ; https://www.dynastynerds.com/strategy/strategy-for-orphan-teams/ ; https://www.fantasypoints.com/nfl/articles/2026/ffpc-dynasty-orphan-strategy ; dispersal drafts https://commissionimpossible.substack.com/p/dynasty-dispersal-drafts-explained ; orphan marketplace https://www.fantasyorphans.com/

**FTF code read for the transfer notes (repo-internal, not external sources)**

- `backend/pick_values.py` — `GENERIC_PICK_SEEDS`, `YEAR_DISCOUNT = 0.85`, `pick_pool_value()` (Mid-tier pricing of every league pick), `discount_pick_value()`
- `backend/trade_service.py` — `_fairness()` range-overlap gate, `_value_uncertainty()` (`range_base = 0.35`), `_shrink_*` (`shrink_pseudocount = 4.0`), `fairness_threshold = 0.75`, `relaxed_fairness_threshold = 0.55`, `user_gain_ok_1for1`, `filler_ok`, `consolidation_raw_loss_frac`, `elo_to_value`
- `backend/data_loader.py` — `VALUES_URL` / `PICK_VALUES_URL` (DynastyProcess), `seed_elo_for_value()`
- `backend/ranking_service.py` — per-user 3-player → 3-pairwise Elo decomposition
