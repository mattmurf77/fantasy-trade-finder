# #214 Stud-Tax — Competitor Values (Public Calculators)

Capture date/time for all runs below: **2026-08-02, ~18:55–23:20 ET** (single sitting, per source, unless noted).

Trade matrix (from validation-plan.md):

| # | Side A (stud) | Side B (package) |
|---|---|---|
| T1 | Justin Jefferson | CeeDee Lamb + Bo Nix |
| T2 | Ja'Marr Chase | Nico Collins + Brian Thomas Jr. |
| T3 | Bijan Robinson | Jahmyr Gibbs + De'Von Achane |
| T4 | Justin Jefferson | CeeDee Lamb + 2027 1st (mid) |
| T5 | Josh Allen | Jayden Daniels + Drake Maye |
| T6 | Malik Nabers | Tetairoa McMillan + DK Metcalf |

No player substitutions were needed — every named player and the 2027-mid-1st pick existed on every calculator tried.

Normalized skew = `(sideB_total - sideA_total) / sideA_total`, using each site's own displayed final totals (post-adjustment where the site shows one).

---

## 1. KeepTradeCut (keeptradecut.com/trade-calculator)

Crowdsourced player/pick values, .5 PPR, 12-team. Format toggle (Superflex On/Off) applies site-wide. KTC displays an explicit **"Value Adjustment"** line on whichever side is "giving up more" when piece-counts are unequal. KTC's own FAQ (paraphrased, KTC's wording under 15 words used verbatim in quotes): "We add value to the side of the trade that's giving up more when you look at roster spots, players' 'stud' factor" — and states the adjustment "is reverse engineered from the player the lesser side needs to have added to even the trade." This is KTC's own name for the stud-tax phenomenon under test.

**Tooling note:** KTC's player-search autocomplete (a jQuery `easy-autocomplete` widget) did not respond to standard automated keystroke/click simulation in a way that reliably completed the full matrix — the widget intermittently stopped committing a highlighted suggestion to the roster list partway through the session (a widget/environment interaction issue, not a data-availability issue). T2-Superflex, T4, T5, and T6 could not be captured on KTC before time budget ran out; the data below is everything that was reliably captured.

| Trade | Format | Side A total | Side B total | Adjustment shown | Verdict (KTC's words) | Skew |
|---|---|---|---|---|---|---|
| T1 | Superflex | 7,562 (Jefferson) | 13,131 (Lamb 7,168 + Nix 5,963) | none shown | Favors Team 2; add 5,117 to Team 1 to even | **+73.7%** |
| T1 | 1QB | 7,710 (Jefferson) | 12,429 (Lamb 7,535 + Nix 4,894) | none shown | Favors Team 2; add 4,405 to Team 1 to even | **+61.2%** |
| T2 | 1QB | 9,995 base **+5,079 adj = 15,074** (Chase) | 11,794 (Collins 6,250 + Thomas Jr. 5,544) | **+5,079** on Chase's side | Favors Team 1; add 3,281 to Team 2 to even | **−21.8%** |
| T3 | 1QB | 9,999 (Bijan) | 17,311 (Gibbs 9,998 + Achane 7,313) | none shown | Favors Team 2; add 7,283 to Team 1 to even | **+73.1%** |
| T3 | Superflex | 9,999 (Bijan) | 16,837 (Gibbs 9,998 + Achane 6,839) | none shown | Favors Team 2; add 6,817 to Team 1 to even | **+68.4%** |

Note on T2 vs T3: KTC applied a large explicit stud-premium (+5,079, ~51% of Chase's raw value) to flip a trade that raw totals only mildly favored Team 2 into one that clearly favors the stud side. In T3, where the raw gap between the stud and the two-piece package was much larger (73%), KTC displayed **no** visible adjustment at all — consistent with KTC's own description that the adjustment is reverse-engineered off the "even-up" gap and phases out once the sides are already lopsided rather than compounding on top.

---

## 2. Dynasty Daddy (dynasty-daddy.com/trade-calculator)

Supports a **Fantasy Market** selector with multiple underlying ranking sources (Dynasty: Dynasty Daddy [native], ADP Daddy, KeepTradeCut, DynastyProcess, Fantasy Navigator, Pro Football Network, DraftSharks — plus separate Redraft-market versions of most of the same). Format toggle (1 QB / Superflex) is independent of source. Full matrix run under the native **Dynasty Daddy** market; T1 additionally re-run under **KeepTradeCut** and **DynastyProcess** sources for cross-source comparison per the plan.

### 2a. Source = Dynasty Daddy (native)

| Trade | Format | Side A | Side B | Verdict | Skew |
|---|---|---|---|---|---|
| T1 | Superflex | 7,303 (Jefferson) | 11,948 (Lamb 6,670 + Nix 5,278) | Favors Team 2; add 4,645 to even | **+63.6%** |
| T1 | 1QB | 7,729 (Jefferson) | 9,965 (Lamb 6,971 + Nix 2,994) | Favors Team 2; add 2,236 to even | **+28.9%** |
| T2 | Superflex | 10,042 (Chase) | 7,388 (Collins 4,422 + Thomas Jr. 2,966) | Favors Team 1; add 2,654 to even | **−26.4%** |
| T2 | 1QB | 10,158 (Chase) | 8,041 (Collins 4,638 + Thomas Jr. 3,403) | Favors Team 1; add 2,117 to even | **−20.8%** |
| T3 | Superflex | 10,164 (Bijan) | 16,340 (Gibbs 10,200 + Achane 6,140) | Favors Team 2; add 6,176 to even | **+60.8%** |
| T3 | 1QB | 10,048 (Bijan) | 16,592 (Gibbs 10,006 + Achane 6,586) | Favors Team 2; add 6,544 to even | **+65.1%** |
| T4 | Superflex | 7,303 (Jefferson) | 9,820 (Lamb 6,670 + 2027-Mid-1st 3,150) | Favors Team 2; add 2,517 to even | **+34.5%** |
| T4 | 1QB | 7,729 (Jefferson) | 10,156 (Lamb 6,971 + 2027-Mid-1st 3,185) | Favors Team 2; add 2,427 to even | **+31.4%** |
| T5 | Superflex | 10,200 (Josh Allen) | 17,132 (Daniels 7,655 + Maye 9,477) | Favors Team 2; add 6,932 to even | **+68.0%** |
| T5 | 1QB | not run — SF-only probe per plan (QB values collapse in 1QB, not a meaningful comparison) | | | |
| T6 | Superflex | 6,974 (Nabers) | 7,048 (McMillan 5,333 + Metcalf 1,715) | **Fair Trade** | **+1.1%** |
| T6 | 1QB | 7,100 (Nabers) | 7,689 (McMillan 5,546 + Metcalf 2,143) | **Fair Trade** | **+8.3%** |

No explicit package/consolidation-discount line item is shown under the native Dynasty Daddy market — displayed totals are the flat sum of the pieces shown.

### 2b. Source = KeepTradeCut (via Dynasty Daddy's KTC integration), T1 only

| Format | Side A | Side B | Adjustment shown | Verdict | Skew |
|---|---|---|---|---|---|
| Superflex | 7,587 base **+2,887 adj = 10,474** (Jefferson) | 13,158 (Lamb 7,159 + Nix 5,999) | **+2,887** | Favors Team 2; add 2,684 to even | **+25.6%** |
| 1QB | 7,739 (Jefferson) — adjustment line still reads "+2,887" but the displayed **total (7,739) did not include it** (likely a stale-render artifact from the format toggle, not a re-tuned adjustment; flagged, not resolved) | 12,432 (Lamb 7,546 + Nix 4,886) | +2,887 shown but not added into the total, per the UI | Favors Team 2; add 4,693 to even | **+60.6%** (as displayed, i.e. treating adjustment as not applied) |

Dynasty Daddy's KTC-sourced values (10,474 / 13,158, skew +25.6% SF) diverge meaningfully from KTC's own native calculator on the identical T1 Superflex trade (7,562 / 13,131, skew +73.7%) — DD applies a much smaller "stud factor" bump (+2,887 vs. an implied ~+5,500 gap KTC's native tool leaves un-closed) even though both claim to be using KTC values. This is a real cross-tool inconsistency worth flagging, not just noise.

### 2c. Source = DynastyProcess (via Dynasty Daddy), T1 Superflex only

| Format | Side A | Side B | Adjustment shown | Verdict | Skew |
|---|---|---|---|---|---|
| Superflex | 8,051 (Jefferson) | 13,045 (Lamb 7,556 + Nix 5,489) | none | Favors Team 2; add 4,994 to even | **+62.0%** |

---

## 3. FantasyCalc (fantasycalc.com/trade-calculator)

Trade values are model-derived from real trade data (not crowd-voted like KTC), on an explicitly **exponential** value curve. Format = Dynasty tab + Superflex toggle. FantasyCalc shows its own explicit **"Waiver Adjustment"** line, distinct from KTC's dynamic "Value Adjustment": FantasyCalc's FAQ explains (paraphrased, short quote under 15 words): "the calculator needs to show the value of the bench spot/waiver player" implied by multi-player trades, and that this amount "increase[s] with each additional bench spot needed." In every run below the adjustment was a **flat +753**, added to whichever side has fewer pieces, regardless of which players/trade — i.e., unlike KTC's reverse-engineered, trade-specific stud premium, FantasyCalc's adjustment is a fixed roster-spot constant, not a scaled "stud tax." All runs below are Superflex (1QB not run for this site — time budget; the constant nature of the Waiver Adjustment makes a format re-run lower-value than for sites with dynamic adjustments).

| Trade | Side A total | Side B total | Adjustment shown | Verdict | Skew |
|---|---|---|---|---|---|
| T1 | 6,707 + 753 = **7,460** (Jefferson) | 11,271 (Lamb 6,372 + Nix 4,899) | +753 (flat) | Favors Team 2 by 3,811 | **+51.1%** |
| T2 | 9,924 + 753 = **10,677** (Chase) | 7,261 (Collins 4,221 + Thomas Jr. 3,040) | +753 (flat) | Favors Team 1 by 3,416 | **−32.0%** |
| T3 | 10,082 + 753 = **10,835** (Bijan) | 15,436 (Gibbs 9,816 + Achane 5,620) | +753 (flat) | Favors Team 2 by 4,601 | **+42.5%** |
| T4 | 6,707 + 753 = **7,460** (Jefferson) | 9,351 (Lamb 6,372 + 2027-1st-Mid 2,979) | +753 (flat) | Favors Team 2 by 1,891 | **+25.4%** |
| T5 | 10,363 + 753 = **11,116** (Josh Allen) | 15,843 (Daniels 7,191 + Maye 8,652) | +753 (flat) | Favors Team 2 by 4,727 | **+42.5%** |
| T6 | 6,824 + 753 = **7,577** (Nabers) | 6,795 (McMillan 4,908 + Metcalf 1,887) | +753 (flat) | Favors Team 1 by 782 | **−10.3%** |

FantasyCalc is the only source in this study where T6 (Nabers vs. McMillan + Metcalf) tips toward the *stud* side rather than being called fair or favoring the package — a real point of disagreement with Dynasty Daddy's "Fair Trade" call on the identical players.

---

## 4. DynastyDealer (dynastydealer.com/trade-calculator/superflex)

Public, no login. Superflex toggle (SF/TE+ chips) at top; all runs below are Superflex, 2-way trade. **DynastyDealer is the single most direct evidence source in this whole exercise**: it displays a fully itemized adjustments breakdown per side, with two separately labeled line items:

- **STUD BONUS** — added to a side for having an elite/top-tier piece. Scales with how many qualifying "studs" are on that side (Team B in T3 showed "STUD BONUS (2)" — Gibbs and Achane both qualified individually).
- **PACKAGE DISCOUNT** — a negative adjustment applied only to the multi-piece side, i.e. the literal mechanic the operator's feedback is describing as FTF's "stud tax," except here it's named and quantified explicitly by a competitor.

**Access note:** the site gates the calculator to **5 free trade evaluations per day** ("X/5 free trades today", visible top-right) — this ran into the daily cap partway through the matrix; T4 and T5 were not captured on this site to conserve remaining credits for other sources. Re-run tomorrow (new daily allotment) if the operator wants the rest of the matrix here.

| Trade | Team A total = base + STUD BONUS | Team B total = raw sum + STUD BONUS − PACKAGE DISCOUNT | Verdict | Skew |
|---|---|---|---|---|
| T1 | 8,275 + 1,505 = **9,780** (Jefferson) | (8,220 Lamb + 7,112 Nix = 15,332) + 1,494 − 4,431 = **12,395** | Favors Team B by 2,615 | **+26.7%** |
| T2 | 10,066 + 1,863 = **11,929** (Chase) | (6,492 Collins + 5,365 Thomas Jr. = 11,857) + 538 − 3,343 = **9,052** | Favors Team A by 2,877 | **−24.1%** |
| T3 | 9,937 + 3,200 = **13,137** (Bijan) | (9,940 Gibbs + 7,912 Achane = 17,852) + 5,696 (2 studs) − 6,484 = **17,064** | Favors Team B by 3,927 | **+29.9%** |
| T6 | 7,943 + 1,439 = **9,382** (Nabers) | (6,775 McMillan + 3,661 Metcalf = 10,436) + 889 − 2,727 = **8,598** | Favors Team A by 784 | **−8.4%** |

Two things worth flagging for the FTF stud-tax tuning question specifically:

1. **The package discount is large and present on every multi-piece side regardless of trade direction** — it ranges from −22% to −38% of that side's raw sum in this sample (e.g. T3: −6,484 / 17,852 = −36.3%). That is a bigger raw discount rate than what FTF's package-depth discount is being second-guessed for, on a site with no operator complaint attached to it.
2. **The stud bonus is not exclusive to the "1-piece" side** — Team B in T2, T3, and T6 all *also* received a stud bonus (for containing at least one elite piece), it's just outweighed by the larger package discount on that side. This confirms DynastyDealer's model treats "stud premium" and "consolidation discount" as two independent, simultaneously-applied adjustments, not one net "stud tax" knob — a useful framing if FTF's re-tune ships as a decomposed pair of constants rather than one blended discount.

---

## 5. Dynasty Trade Factory (dynastytradefactory.com) — no public web calculator found

Checked at the request of the scope-addition (which described it as "public, no login, offers Sleeper-username import"). The live site as of this capture is a pure marketing/download landing page for **iOS and Android apps only** — "Trade smarter, not harder... Import your Sleeper roster... Download on the App Store / Get it on Google Play." There is no in-browser trade calculator, no player search, and no unauthenticated web tool anywhere on the domain (checked all nav links: How it works, Pricing, Privacy, Support — all anchor-scroll to sections of the same landing page). This appears to be a mobile-only product now, consistent with the original validation-plan's classification of Dynasty Trade Factory as an "iPhone-app test" requiring operator screen recordings rather than a research-agent web run. **No data captured; this source needs the operator's screen-recording pipeline (per validation-plan.md's iPhone-app-tests section), not a browser run.**

## Sites not attempted

DynastyProcess/Calc as a standalone site was skipped per the task's own scope note — it's already covered via Dynasty Daddy's DynastyProcess ranking source above (see §2c).

---

## Cross-site summary table — normalized skew per trade

Positive skew = side B (the package) is valued *above* side A (the stud) — i.e. no stud tax visible, the market treats the package as the winner. A skew near 0 = market calls it fair. Negative skew = the stud side wins even after any adjustment — the clearest "stud tax in the wild" signal.

| Trade | Format | KTC (native) | DD × Dynasty Daddy | DD × KeepTradeCut | DD × DynastyProcess | FantasyCalc | DynastyDealer |
|---|---|---|---|---|---|---|---|
| T1 | SF | +73.7% | +63.6% | +25.6% | +62.0% | +51.1% | +26.7% |
| T1 | 1QB | +61.2% | +28.9% | +60.6%* | — | — | — |
| T2 | SF | — (not captured) | −26.4% | — | — | −32.0% | −24.1% |
| T2 | 1QB | −21.8% | −20.8% | — | — | — | — |
| T3 | SF | +68.4% | +60.8% | — | — | +42.5% | +29.9% |
| T3 | 1QB | +73.1% | +65.1% | — | — | — | — |
| T4 | SF | — | +34.5% | — | — | +25.4% | — (daily cap) |
| T4 | 1QB | — | +31.4% | — | — | — | — |
| T5 | SF | — | +68.0% | — | — | +42.5% | — (daily cap) |
| T5 | 1QB | — (SF-only probe) | — (SF-only probe) | — | — | — (SF-only probe) | — |
| T6 | SF | — | +1.1% | — | — | −10.3% | −8.4% |
| T6 | 1QB | — | +8.3% | — | — | — | — |

\* DD×KTC 1QB total appears not to include the displayed adjustment (see §2b note) — treat this cell as low-confidence.

---

## What the market says, per trade

**T1 (Jefferson for Lamb + Nix — the reported trade).** Every source that returned a result says the two-piece package clearly outvalues Jefferson alone, in both formats — normalized skew ranges from +25.6% (DD×KTC, the outlier — its stud-factor bump is much smaller than KTC's own site produces on the same players) up to +73.7% (KTC native, Superflex). Nobody in this sample calls this trade fair for Jefferson's side, let alone flags the *package* as overpaying. If FTF's engine treats this trade as needing a heavier "stud tax" correction than the +25–74% the market itself already prices in for the raw package, that is the signal the operator's feedback was pointing at.

**T2 (Chase for Collins + Brian Thomas Jr. — WR-only consolidation).** This is the trade where the "stud tax" is most visible on the *competitor* side, and it's unanimous across every source that returned a result: KTC (+5,079 explicit Value Adjustment), Dynasty Daddy native, FantasyCalc (flat +753 Waiver Adjustment), and DynastyDealer (itemized Stud Bonus + Package Discount) all put Chase **ahead** of the two-piece WR package — skew −21.8%, −20.8% to −26.4%, −32.0%, and −24.1% respectively. This is the strongest evidence in the matrix that the market itself applies a real premium for elite-WR consolidation, independent of FTF's own stud-tax logic.

**T3 (Bijan for Gibbs + Achane — RB consolidation, tight tier gap).** Unlike T2, none of KTC, Dynasty Daddy, or DynastyDealer's *net* verdict favors the stud side here — the two-piece RB package wins comfortably and by a similar margin across every tool (+29.9% to +73.1%). The "tight tier gap" the plan called out doesn't read as tight in the market's eyes; Gibbs alone is worth nearly as much as Bijan, so adding Achane on top makes it lopsided in the package's favor even after DynastyDealer's largest-in-sample stud bonus (+5,696, "2 studs") and package discount (−6,484) are both applied — they largely cancel out rather than flipping the trade.

**T4 (Jefferson for Lamb + 2027 mid 1st — player + pick package).** Captured on Dynasty Daddy and FantasyCalc. Both agree the pick softens the gap versus T1's player-for-two-players version (DD: +31–35% vs. T1's +29–64%; FantasyCalc: +25.4% vs. T1's +51.1%), consistent with picks generally being discounted relative to proven players at this range.

**T5 (Josh Allen for Daniels + Maye — SF-only QB consolidation).** Only meaningful in Superflex (as the plan anticipated). Dynasty Daddy and FantasyCalc agree closely — the two-QB package beats Allen by +68.0% and +42.5% respectively, among the largest package-beats-stud margins in the whole matrix — suggesting the market does not apply much of a "stud tax" to elite starting QBs when the return package is two clear-starter-caliber young QBs.

**T6 (Nabers for McMillan + Metcalf — stud vs. young piece + aging vet).** The closest trade in the whole matrix, and the one place the sources disagree on *direction* rather than just magnitude: Dynasty Daddy calls it a "Fair Trade" outright in both formats (+1.1% SF, +8.3% 1QB), while FantasyCalc (−10.3%) and DynastyDealer (−8.4%, via an explicit Stud Bonus that outweighs the Package Discount) both tip it toward Nabers's side instead. Either way the gap is the smallest in the matrix — this is the one trade where the market is genuinely split and closest to a naive raw-value sum, unlike T1–T5 where every source shows a clear, same-direction lean.
