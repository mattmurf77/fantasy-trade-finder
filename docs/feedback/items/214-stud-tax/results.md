# #214 Stud-Tax — FTF Engine Results vs. Competitor Medians

**STATUS: DRAFT — the main session reviews this before any tuning proposal is written.**

Captured 2026-08-02. FTF numbers pulled via `POST /api/trade/evaluate` (Mode A —
public, consensus, no league context), run in-process through the Flask test
client against the local dev DB (`data/trade_finder.db`), never production.
Script: `feedback-workspace/214/run_matrix.py` (gitignored scratch); raw
response JSON: `feedback-workspace/214/ftf_results.json`. No backend code was
modified.

## Method note vs. the validation plan

The plan asked for "both formats only if our consensus values are
format-aware." They are: FTF Mode A takes `scoring_format ∈ {1qb_ppr, sf_tep}`
and prices from two independently-blended universal pools (confirmed in
`backend/server.py` — `g_universal_by_format["1qb_ppr"|"sf_tep"]`), so every
trade below is run in **both formats**, matching the competitor capture.

## Player-id resolution

All 15 matrix players resolved directly in `data/trade_finder.db` (`players`
table) — **no substitutions needed** for any named player, matching the
competitor-values.md finding that no site needed a substitution either.

One exception: **T4's "2027 1st (mid)"** is a *dated future* pick on every
competitor site (they discount it for being 2 years out). FTF's public Mode A
calculator only prices **generic, year-agnostic** pool picks
(`generic_pick_1_mid`, etc.) — dated future picks only resolve inside a real
`league_id`'s owned-pick set, which Mode A doesn't have. T4 below uses
`generic_pick_1_mid` (an un-discounted Mid 1st) as the nearest available
equivalent inside FTF's own ladder — this is a **like-for-almost-like
substitution**, not a same-value one: FTF's T4 numbers likely run slightly
*rich* for the pick side relative to the competitor sites' year-discounted
version. Flagged, not corrected (no year-discount lever exists in Mode A to
correct it with).

## Mode B (in-league) — SKIPPED

The plan allowed skipping Mode B for T1 "if straightforward with existing
test fixtures — skip if it needs real league data." It does: Mode B prices by
the caller's **and** the opponent's real `member_rankings` inside a real
`league_id`, which only exist for actual synced leagues with actual ranked
boards. `backend/tests/test_trade_evaluate.py`'s Mode B tests inject
synthetic boards via `monkeypatch` — fine for pinning the route's math, not
for producing a numerically meaningful comparison against the operator's real
trade. Producing a real Mode B reading would mean either hitting production
with the operator's session (excluded by the task) or fabricating a league
board that wouldn't mean anything. Skipped; consensus-only comparison below.

---

## 1. Raw FTF table (both formats — one consensus board per format)

All values in FTF's value-space units (not comparable across sites' own
unit scales — only normalized skew is comparable, see §2).

| Trade | Format | Give (stud) | Receive (package) | Naive give | Naive receive | Adjustments (give) | Adjustments (receive) | Final give | Final receive | Verdict | Favors |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T1 | 1QB | Jefferson | Lamb+Nix | 7489.5 | 8581.1 | Consolidation +898.7 | Package depth −2111.6 | 8388.2 | 6469.5 | fair | give |
| T1 | SF | Jefferson | Lamb+Nix | 7117.1 | 10979.0 | Consolidation +854.0 | Package depth −2756.5 | 7971.1 | 8222.5 | even | even |
| T2 | 1QB | Chase | Collins+Thomas | 8469.7 | 7482.4 | Consolidation +1016.4 | Package depth −4199.2 | 9486.1 | 3283.2 | unfair | give |
| T2 | SF | Chase | Collins+Thomas | 8223.5 | 6185.8 | Consolidation +986.9 | Package depth −3845.3 | 9210.4 | 2340.5 | unfair | give |
| T3 | 1QB | Bijan | Gibbs+Achane | 8198.9 | 13659.6 | Depth −62.4, Consolidation +976.3 | Package depth −2155.4 | 9112.8 | 11504.2 | fair | receive |
| T3 | SF | Bijan | Gibbs+Achane | 7873.5 | 12806.3 | Depth −178.3, Consolidation +923.4 | Package depth −2190.9 | 8618.6 | 10615.4 | fair | receive |
| T4 | 1QB | Jefferson | Lamb + generic Mid 1st | 7489.5 | 8920.9 | Consolidation +898.7 | Package depth −2304.6 | 8388.2 | 6616.3 | fair | give |
| T4 | SF | Jefferson | Lamb + generic Mid 1st | 7117.1 | 8410.4 | Consolidation +854.0 | Package depth −2408.8 | 7971.1 | 6001.6 | fair | give |
| T5 | 1QB | Allen | Daniels+Maye | 6119.6 | 9121.5 | Consolidation +734.4 | Package depth −2658.2 | 6854.0 | 6463.3 | fair | give |
| T5 | SF | Allen | Daniels+Maye | 8469.7 | 13561.6 | Consolidation +1016.4 | Package depth −3266.8 | 9486.1 | 10294.8 | fair | receive |
| T6 | 1QB | Nabers | McMillan+Metcalf | 6807.3 | 7254.7 | Consolidation +816.9 | Package depth −2380.2 | 7624.2 | 4874.5 | unfair | give |
| T6 | SF | Nabers | McMillan+Metcalf | 5786.3 | 6001.4 | Consolidation +669.7 | Package depth −1717.0 | 6456.0 | 4284.4 | unfair | give |

Every single row applies exactly the same two adjustments in the same
direction: a **Consolidation premium** on the stud (give) side and a
**Package depth** discount on the package (receive) side — never the reverse,
never both on the same side, never a stud-side discount or a package-side
bonus. That structural rigidity matters — see §5.

## 2. Normalized skew per trade — final (adjusted) vs. naive (pre-adjustment)

`skew = (receive_total − give_total) / give_total`. Positive = the package
outvalues the stud (no stud tax visible); negative = the stud outvalues the
package even after being consolidated into two players (the stud-tax
signature).

| Trade | Format | FTF naive skew | FTF final skew | Δ from FTF's own adjustments |
|---|---|---|---|---|
| T1 | 1QB | +14.6% | **−22.9%** | −37.5pp |
| T1 | SF | +54.3% | **+3.2%** | −51.1pp |
| T2 | 1QB | −11.7% | **−65.4%** | −53.7pp |
| T2 | SF | −24.8% | **−74.6%** | −49.8pp |
| T3 | 1QB | +66.6% | **+26.2%** | −40.4pp |
| T3 | SF | +62.7% | **+23.2%** | −39.5pp |
| T4 | 1QB | +19.1% | **−21.1%** | −40.2pp |
| T4 | SF | +18.2% | **−24.7%** | −42.9pp |
| T5 | 1QB | +49.1% | **−5.7%** | −54.8pp |
| T5 | SF | +60.1% | **+8.5%** | −51.6pp |
| T6 | 1QB | +6.6% | **−36.1%** | −42.7pp |
| T6 | SF | +3.7% | **−33.6%** | −37.3pp |

FTF's own adjustments move every trade in every format **in the same
direction** — toward the stud side — by 37 to 55 percentage points, with no
exceptions in this matrix. Before any adjustment, FTF's raw/naive skew is
mostly package-favoring (all positive except T2, which every competitor site
also shows package-favoring-the-stud on). After adjustment, half the matrix
flips sign entirely (T1 1QB, T4 both, T5 1QB, T6 both).

## 3. FTF skew vs. competitor median skew

Competitor medians and source counts pulled from
`research/competitor-values.md`'s cross-site summary table (§"Cross-site
summary table — normalized skew per trade"). `n` = number of sources
contributing to that cell's median (see that doc for per-source values; T5
1QB has zero competitor sources — it was an SF-only probe by design, so it's
excluded here). `delta_pp` = competitor median − FTF final skew, in
percentage points; positive means FTF's engine requires a bigger package
premium than the market already prices in (the stud-tax signal).

| Trade | Format | FTF final skew | Competitor median skew | n sources | Delta (pp) |
|---|---|---|---|---|---|
| T1 | SF  | +3.2% | +56.6% | 6 | **+53.4** |
| T1 | 1QB | −22.9% | +60.6%* | 3 | **+83.5** |
| T2 | SF  | −74.6% | −26.4% | 3 | **+48.2** |
| T2 | 1QB | −65.4% | −21.3% | 2 | **+44.1** |
| T3 | SF  | +23.2% | +51.6% | 4 | **+28.5** |
| T3 | 1QB | +26.2% | +69.1% | 2 | **+42.9** |
| T4 | SF  | −24.7% | +29.9% | 2 | **+54.7** |
| T4 | 1QB | −21.1% | +31.4% | 1 | **+52.5** |
| T5 | SF  | +8.5% | +55.3% | 2 | **+46.7** |
| T5 | 1QB | −5.7% | — (no sources) | 0 | n/a |
| T6 | SF  | −33.6% | −8.4% | 3 | **+25.2** |
| T6 | 1QB | −36.1% | +8.3% | 1 | **+44.4** |

\* Low-confidence cell per competitor-values.md (DD×KTC 1QB adjustment may not
have applied in the UI); included anyway since it's within the 3-source
median and doesn't change any trade's pass/fail outcome.

**Every single delta is positive** — FTF's engine requires a larger side-B
premium than the market consensus, in every trade, in every format captured.
There is no trade where FTF is *more* lenient on the package side than the
market; the direction is 100% one-sided.

## 4. Heuristic — applied mechanically

Plan's rule: *"If FTF's required package premium exceeds the competitor
median by >10 percentage points on 3+ of the 6 matrix trades, the stud tax is
too heavy."*

Per-trade delta = mean of the available per-format deltas from §3 (T5 uses
its single SF cell; every other trade averages 2 format cells):

| Trade | Format deltas (pp) | Trade-level delta (pp) | Exceeds +10pp? |
|---|---|---|---|
| T1 | +53.4, +83.5 | **+68.4** | YES |
| T2 | +48.2, +44.1 | **+46.1** | YES |
| T3 | +28.5, +42.9 | **+35.7** | YES |
| T4 | +54.7, +52.5 | **+53.6** | YES |
| T5 | +46.7 | **+46.7** | YES |
| T6 | +25.2, +44.4 | **+34.8** | YES |

**Count exceeding +10pp: 6 / 6 trades** (threshold for "too heavy" is 3+).

**Mechanical verdict (DRAFT): the stud tax is too heavy — decisively, not
marginally.** Every trade clears the 10pp bar by at least 2.5x (the smallest
margin, T6, is +34.8pp on a +10pp bar); the largest (T1) clears it by nearly
7x. This isn't a borderline call that a source or two could flip.

---

## 5. Notable observations

**FTF's crown/consolidation premium is a near-flat 12% bonus, unconditionally
applied — unlike every competitor's own adjustment mechanic.** The
"Consolidation premium" row is `crown_rate=0.12` (see
`backend/trade_service.py` `_DEFAULT_CFG`) scaled by the stud's share of its
side (always 100% here — single-player side) and by the stud's value vs.
`crown_elite_value=6000` (every matrix stud clears this, so the scaling
saturates at the full 12%). Result: every trade in this matrix gets almost
exactly +12% tacked onto the stud's naive value (11.6%–12.0% across all 12
rows), **regardless of how lopsided the trade already is naively**. Compare:

- **KTC** explicitly *phases its adjustment out* as the raw gap widens — on
  T3 (already 73% naive-lopsided), KTC shows **zero** visible adjustment at
  all, because its adjustment is reverse-engineered off the even-up gap, not
  compounded on top of an already-large one (competitor-values.md §1, note
  under the T1 table).
- **FantasyCalc**'s "Waiver Adjustment" is a flat *absolute* amount (+753 in
  every trade, any players) — also non-compounding with trade lopsidedness,
  but flat in raw units rather than a % that scales with the stud's own
  value.
- **DynastyDealer** ties its STUD BONUS to *any* side holding a qualifying
  elite piece, independent of piece count — in their T3, the two-piece
  RB package (Gibbs+Achane) earns its own stud bonus ("STUD BONUS (2)") for
  containing two individually-elite pieces, which partially offsets that
  side's package discount.

**FTF's crown premium, by contrast, is exclusive to the single/outnumbered
side** — `package_value_v2`'s crown bonus only triggers when
`len(values) < n_other` (`backend/trade_service.py`). In T3, Gibbs and Achane
are individually comparable in value to Bijan, but FTF's package (receive)
side gets **no offsetting stud credit whatsoever** for holding two elite
running backs — only the flat depth discount. Under DynastyDealer's own
framework (which explicitly models "stud premium" and "consolidation
discount" as two *independent, simultaneously-applicable* adjustments), FTF's
design can structurally never award that credit to a multi-piece side. This
is a design gap, not just a mis-tuned constant — a re-tune of `crown_rate`
alone wouldn't fix it; it would need the crown/stud-bonus eligibility rule
itself to become count-independent.

**The package-depth discount rate is unusually large on WR-only
consolidations.** `package_adj_gamma=1.5` shrinks each package asset's
contribution based on its value *relative to the single highest-value asset
in the WHOLE trade* (`v_max`, `package_value_v2`) — not relative to its own
package's best piece. Because the stud is (almost) always the trade's
overall `v_max`, a package piece far below the stud's tier gets shrunk hard
even if it's a fine player in its own right. This shows up starkly in **T2**
(Chase vs. Collins+Thomas Jr.): FTF's package-depth discount is −56% to −62%
of the package's naive sum — well outside DynastyDealer's own observed range
of −22% to −38% across their captured trades (competitor-values.md §4,
"worth flagging" note). T2 is also the one trade where the market itself
shows a stud-side premium (every competitor source calls Chase ahead of the
package), so FTF isn't wrong about direction here — but the magnitude runs
far hotter than anything in the competitor sample.

**T1 — the operator's reported trade — in plain language.** The operator
gave Justin Jefferson and received CeeDee Lamb + Bo Nix, and felt shorted.
The market is unanimous that this specific complaint has it backwards: every
competitor source that returned T1 says Lamb+Nix clearly *outvalue* Jefferson
alone — by +25.6% at the low end (Dynasty Daddy's KTC-sourced numbers) up to
+73.7% at the high end (KTC's own native site), with a 6-source median of
+56.6% in Superflex and a 3-source median of +60.6% in 1QB. Nobody in the
competitive landscape flags the *package* as overpaying in this trade.

FTF's engine tells a different story. Superflex: FTF calls it roughly even
(+3.2%, verdict "even") — already 53 points short of what the market
considers fair. 1QB is worse: FTF's adjustments flip the trade entirely,
landing at **−22.9%** — meaning FTF thinks Jefferson alone is worth *more*
than Lamb and Nix combined, the exact opposite of every competitor site's
read, and the opposite of the direction the operator's complaint assumed.
Mechanically: FTF's naive (pre-tax) numbers already lean toward the package
(+14.6% 1QB / +54.3% SF, roughly consistent with the low end of the
competitor range) — it's the crown premium (+12% onto Jefferson) stacked
with the package-depth discount (shaving ~25% off Lamb+Nix's naive sum) that
does the flipping, a combined ~40–50pp swing away from the market's read on
this exact trade. The operator's instinct that "the stud tax is too heavy"
is borne out here, just not in the direction the phrase "for Lamb and Nix"
initially suggested — FTF isn't slightly stingy toward the package, it's
inverting the market's clear verdict.

---

## Summary for the review session

- **FTF final skew** (adjusted, consensus, both formats) ranges from
  **+26.2% to −74.6%** across the matrix — see §1–2 for the full per-trade
  table.
- **Mechanical heuristic outcome: 6 / 6 trades exceed the +10pp threshold**
  (needs only 3+), with per-trade deltas of +34.8pp to +68.4pp — the stud tax
  reads as too heavy by a wide, unambiguous margin under the plan's own rule.
- **Substitutions:** none needed for named players; T4's future pick
  substituted with FTF's year-agnostic generic Mid 1st (Mode A has no
  dated-pick pricing lever) — flagged as likely running slightly rich for
  the pick side, not corrected.
- **Limitations:** Mode B (in-league) skipped entirely — it needs real
  league/session data the task excluded (no production access) and
  synthetic test-fixture boards wouldn't be numerically meaningful here.
- **Root causes identified (not yet fixed):** (1) the crown/consolidation
  premium is a near-flat, non-compounding +12% applied unconditionally to
  every stud-side trade regardless of how lopsided it already is, unlike
  every competitor's own adjustment, which phases out or stays flat-absolute
  rather than flat-percentage; (2) it's structurally exclusive to the
  single/outnumbered side, so a multi-piece side holding genuinely elite
  players (T3) gets zero offsetting credit, unlike DynastyDealer's
  independent stud-bonus-per-side model; (3) `package_adj_gamma`'s discount
  is measured against the trade's overall best asset rather than the
  package's own best asset, producing outsized discounts (−56% to −62% vs.
  DynastyDealer's observed −22% to −38% ceiling) on trades like T2 where the
  package's pieces sit well below the stud's tier.
- This document is **DRAFT** — verdict, root causes, and any recommended
  constants are for the main session to confirm before a `tuning-proposal.md`
  is written (per validation-plan.md's deliverables list).
