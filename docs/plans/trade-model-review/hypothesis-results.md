# Gripe-to-hypothesis matrix — results (Phase 3), 2026-08-27

> **Purpose:** the community's documented complaints about incumbent dynasty tools (KTC et al.),
> tested against OUR model. Gripe evidence: §11 of
> `docs/business/product/2026-08-27-monetization-timing-research.md` (authored on the
> app-launch-scorecard worktree; unmerged at time of writing). Model facts:
> [current-state.md](current-state.md). Numbers: [data-readout-2026-08-27.md](data-readout-2026-08-27.md)
> — power labels apply throughout. Verdict scale: **SUPPORTED / PARTIAL / NOT SUPPORTED /
> UNTESTABLE-YET**, each tagged measured / code-verified / assumed.

## Contents

- [Scorecard](#scorecard)
- [H1 — pick overvaluation](#h1--pick-overvaluation)
- [H2 — consolidation trap](#h2--consolidation-trap)
- [H3 — youth hype / veteran undervaluation](#h3--youth-hype--veteran-undervaluation)
- [H4 — knee-jerk volatility](#h4--knee-jerk-volatility)
- [H5 — format blindness](#h5--format-blindness)
- [H6 — liquidity/context blindness](#h6--liquiditycontext-blindness)
- [H7 — personalization demand (the core product hypothesis)](#h7--personalization-demand-the-core-product-hypothesis)
- [H8 — insult offers / "KTC-fair" weaponization](#h8--insult-offers--ktc-fair-weaponization)

## Scorecard

| # | Community gripe about incumbents | Does OUR model have the problem? | Verdict |
|---|---|---|---|
| H1 | Picks/rookies overvalued; far-year firsts priced like current | **Yes, on the give side** — flat-firsts pricing (D-079/D-161) makes the engine spend far firsts as currency; users refuse at 9.3% like | **SUPPORTED** (measured) |
| H2 | Consolidation trap (three WR3s = one Jefferson) | Guardrails (filler floors, consolidation discount, R1) appear to hold; 3:1 unlock too new to read | **NOT SUPPORTED so far** (measured, underpowered) |
| H3 | Youth hype / veteran undervaluation | The engine applies no age curve at all; the *users* are strongly youth-biased | **NOT SUPPORTED for the model; inverted — it's the users** (code-verified + measured) |
| H4 | Knee-jerk volatility | Our values move ≤ daily; big jumps are our own recalibrations. Risk is staleness, not overreaction | **NOT SUPPORTED; inverse risk noted** (measured + code-verified) |
| H5 | Format blindness (SF QB premium, TEP) | Partially blind: one two-bucket bit, SF/TEP conflated, PPR magnitude invisible; sf_tep leagues like at half the rate | **PARTIAL — real gaps found** (code-verified + measured) |
| H6 | Liquidity/context blindness | Need-fit is live but doesn't separate like-rates; windows label, never price; partner liquidity unseen | **PARTIAL** (measured + code-verified) |
| H7 | "Flat values don't work" → our divergence cards should outperform | **They don't yet** — consensus-basis cards outperform or tie divergence for every user | **NOT SUPPORTED — core pitch needs work** (measured) |
| H8 | Insult offers | Consensus guardrail stable at 1.48% (pass); divergence cards have an unmeasured partner-perception exposure (8.18% by the raw rule) | **PARTIAL — new rule needed** (measured) |

## H1 — pick overvaluation

**Gripe:** "KTC waaaay overvalues picks"; far-year firsts priced like current-year.
**Our mechanism:** we are *deliberately* flat on future firsts — D-079 (`pick_year_decay_r1` = 1.0)
and D-161 (`market_r1_yoy_floor` = 1.0) both operator-ruled, twice, against all four market sources
(DP −20%/yr, FantasyCalc 0.80, KTC 0.83). Flat pricing makes different-year firsts interchangeable
currency to a delta-maximizing search, so the engine freely builds "your player for a far first" /
"your far first for a player" packages.

**Measured:** cards asking the user to **give** a far-year 1st (2027+) like at **9.3%** [4.6–18.0]
vs 38.8% [32.9–45.0] for player-only — CI-separated even at these n. Receiving a far first is fine
(36.2%). Current-year firsts are fine both ways (36–39%). This reproduces the D-084-era read
(1st-on-give 15.6% vs 1st-on-receive 47.1%) on 3× the data.

**Reading:** the users' revealed preference agrees with the *gripe direction* — they will not part
with future firsts at our flat price, i.e. behaviorally they price their own future firsts *above*
even our above-market flat line (endowment/lottery value), while happily accepting them. The
asymmetry means this is not fixable by moving the price alone (any single price keeps one side
wrong); it is a **presentment/exposure problem**: stop spending the user's far firsts as filler
currency. gen_v2 is the worst offender (46.4% of its logged cards ask for a far first vs the
incumbent's 10.3%). D-079/D-161 are operator rulings — nothing here recommends overturning them; it
recommends a give-side exposure treatment (see champion doc §flips).

## H2 — consolidation trap

**Gripe:** incumbents grade three WR3s ≈ one Jefferson (FantasyCalc's vendor-sourced 46% accuracy on
several-for-one).
**Our mechanism (code-verified):** non-additive `package_value_v2` (market mode: depth discount,
floor 0.70, discount cap 0.35), #141 filler floors (`filler_min_frac` live 0.15, `asset_floor_abs`
450), the consensus-path raw-loss kill (0.15), R1 overpay, and G6 kill-rate history (91% of #141
kills carry a sub-450 body — D-159).

**Measured:** consolidation cards the user *gives more* on perform at parity with 1:1 (2→1: 33.9% vs
1:1 36.9%); the junk-stuffed shape simply doesn't reach users at volume. The 08-24 3:1 unlock has
served 256 3:1/4:1 cards but only 5 have decisions (0 likes) — **no read yet**; the shape-unlock
watch item stands (operator intent: R2 `pos_net_starter_relief` is the real positional protection,
per the shape-rule-intent memory).

## H3 — youth hype / veteran undervaluation

**Gripe:** community says incumbents undervalue veterans / overvalue rookies.
**Code-verified:** our engine has **no age input to any value** in the live config — every
valuation-touching age path (`trade.outlook_blend`, `outlook_direction`, gen_v2 youth tag) is dark;
age reaches labels, taste attributes, and outlook inference only. Whatever vet-vs-youth bias exists
in our prices is inherited from DP/KTC consensus, not added.

**Measured (the inversion):** the *users* are youth-biased, monotonically: like-rate for receiving
u23 47.8% → 30+ 15.0%; for giving, u23 18.8% → 30+ 40.5%. So a candidate engine that "fixes
veteran undervaluation" by boosting vet cards would fight the users' own revealed preference. The
taste layer already learns this per user (age-band attributes, live). If anything, the H3 gripe
predicts our users would *reject* vet-heavy returns — which they do.

## H4 — knee-jerk volatility

**Gripe:** incumbent values overreact to news.
**Code-verified:** we cannot overreact to news: there is no news input. Consensus refreshes at most
~daily (20 h TTL + daily tick); KTC/DP caches 24 h; failed fetches silently serve yesterday's pool.
**Measured:** median day-over-day |Δ| of top-200 values = 1.14%; the only >3.5% days are our own
recalibration deploys (07-27 spine restart 14.3%, 08-22 QB-compression session 8.2%).

**Reading:** the gripe does not reproduce; our exposure is the mirror image — **staleness** (≤24 h
lag, silent stale-pool on fetch failure, in-season this will lag Sunday-night news by up to a day)
and **self-inflicted jumps** (deploy-driven recalibrations that dwarf market movement and are
invisible to users as such). §11 named freshness the durable moat; today's cadence does not deliver
it. Candidate work, not a flip: intraday refresh in-season + a visible "values updated" stamp.

## H5 — format blindness

**Gripe:** incumbents ignore SF QB premium and TEP.
**Code-verified:** we are half-sighted, precisely: one bit (`1qb_ppr` vs `sf_tep`) drives per-format
DP values, TE ×1.18, SF starter-need 2, per-format tier bands, and format-aware slot prices — but
(a) SF and TEP are **conflated** (a 1QB TEP league gets full superflex QB pricing), (b) PPR
magnitude is invisible, (c) the fallback pick ladder ignores format, (d) no other scoring setting
exists as an input.

**Measured:** `sf_tep`-labeled leagues like at **16.4%** vs 35.5% elsewhere (league/user
confounded, but large); QB-centerpiece cards like at **8.9%** overall — and the 1QB QB compression
knobs were hand-tuned live three times on 08-21, i.e. QB pricing is actively unsettled. The gripe
partially lands: our format handling is better than the incumbents' (they have none) but the
conflation + QB card failure is the weakest spot the data can currently see.

## H6 — liquidity/context blindness

**Gripe:** incumbents ignore window, roster construction, whether the counterparty trades.
**Code-verified:** need-fit, lanes, and outlook inference are live but **value-inert** (labels and
composite multipliers, never prices); the starter template is fixed (real `roster_positions`, FLEX,
byes, depth charts unseen); partner liquidity totally unseen (negmem M2 dark, `sleeper_trades`
unconsumed by generation).
**Measured:** like-rate is flat across need-fit bands (30.7% vs 31.4%) and window alignment (30.0%
vs 32.4%) — the fit machinery is not measurably buying acceptance at deck level. Either the signal
is weak, or its effect is upstream (gating what's generated) where a like-rate cut can't see it.
PARTIAL: the gripe describes us less than the incumbents, but nothing here proves our context
features earn their keep either.

## H7 — personalization demand (the core product hypothesis)

**Gripe → pitch:** "flat values don't work"; explicit demand for league/team-specific values. Our
divergence-basis cards (built from two real boards disagreeing) should outperform consensus-basis
cards.

**Measured — they do not, yet:**
- All-time: divergence 26.2% vs consensus 34.6%.
- Every user with both cuts likes consensus cards ≥ divergence cards (9.1 vs 21.1 / 31.5 vs 34.1 /
  48.5 vs 61.3).
- Interleave window (fairest read): parity — 40.2% vs 43.0%, both anecdote-grade.

**Confounds, stated honestly:** divergence cards are structurally different (more multi-asset, more
picks, boarded partners only), board coverage varies (642 ranked players for the heaviest user),
and n is small. The 2026-08-22 second-read review identified the structural mechanism:
consensus-path cards must favor the viewer by construction (the #108 identity line), so their
like-rate advantage partly measures "the viewer wins" rather than "consensus values are better" —
and it ruled that basis comparisons should be graded on match rate and partner-side likes
([Q-030](../../../living-memory/OPEN_QUESTIONS.md) second-read addendum). At n=15 matches that
grading is not yet possible. The plan's own bar was "if this is not clearly positive, the core pitch needs work
before scale" — **it is not clearly positive.** Two things follow: (1) the pitch's §11 reframe
("your board vs the room's anchor" — consensus as the negotiation anchor, not garbage) is the
defensible form; (2) before any scale push, divergence card quality needs work the H1/H8 findings
already point at (divergence cards carry the 8.18% consensus-haircut exposure and most of the
give-far-first cards). A powered basis read needs ~385 decided per basis ≈ 3–4 more weeks at
current traffic, or an explicit interleaving experiment per F8.

## H8 — insult offers / "KTC-fair" weaponization

**Gripe:** incumbents' "fair" framing gets weaponized for lowballs; first impressions die on insult
offers.
**Measured:** the 2026-08-15 rule, re-applied to *served* first-5 cards: **consensus-basis 1.48%
(25/1,693) — numerically identical to the 08-15 offline run, PASS** against the <3% gate.
Divergence-basis cards flag at **8.18%** under the same arithmetic — but the rule's premise
(consensus = what the viewer believes) does not hold there, so this is exposure quantification, not
a gate failure. Per-arm (logged first-5, raw rule): current 5.37%, gen_v2 6.15%, challenger 7.98%
— the challenger's landability overlay loosens exactly the gates that hold this line.

**What's missing (candidate work):** a divergence-specific insult rule judging the card from the
*counterparty's* consensus anchor (the §11 mechanism: the partner prices your offer at the room's
values). Until every candidate's decks are gated on both rules, H8 is only half-guarded. Phase 4
carries this as a gate condition on any future arm promotion.
