# Calculator Landscape — #214 Stud-Tax Validation

Research deliverable for [validation-plan.md](../validation-plan.md). Enumerates every dynasty
fantasy football trade calculator found (web + app), classified by access, ranking source(s),
format support, and whether the site visibly applies a multi-player package discount / stud
premium (vs. naively summing player values). Captured 2026-08-02 via web search + fetch — live
values were **not** captured here (that's `research/competitor-values.md`, a separate pass); this
doc is scoping only.

**Two corrections to the plan's starting assumptions**, found during research:
- **DynastyDealer is NOT mobile-only.** It has a public web calculator at
  `dynastydealer.com/trade-calculator/superflex` in addition to iOS/Android apps. Run it on the
  matrix directly — no screen recording needed.
- **Dynasty Trade Factory is NOT mobile-only either.** `dynastytradefactory.com` is a website —
  Sleeper-username import, no account login required for the core Trade Analyzer. Also runnable
  directly.

That leaves only **DynastyGM** (which turns out to be the app wrapper for Dynasty Nerds' paid
product — see its entry) as a case needing the screenshot/recording pipeline, plus a handful of
minor apps with no confirmed web counterpart (Dynasty Dominator, JD Trade Analyzer, Dynasty
Toolbox) that weren't in the plan's original list and are low-priority.

## Summary table

| Source | Access | Ranking source(s) | Format support | Visible package/stud adjustment? | Run on matrix? |
|---|---|---|---|---|---|
| [KeepTradeCut](https://keeptradecut.com/trade-calculator) | Public, no login | Own crowdsourced ELO (26M+ KTC votes) | 1QB/SF toggle, TE+/TE++/TE+++ tiers, league size, startup mode | **Yes** — explicit "stud factor" adjustment, reverse-engineered from the player that would even the trade | **Yes — baseline** |
| [Dynasty Daddy](https://dynasty-daddy.com/trade-calculator) | Public, no login (optional league sync) | Selectable: KTC, FantasyCalc, DynastyProcess, DynastySuperflex (note: DynastySuperflex's source site appears to have moved/rebranded to FantasyNavigator.com — its feed may be stale; flag if values look frozen) | 1QB/SF; league sync across Sleeper/MFL/Fleaflicker/ESPN/FFPC | Unconfirmed from docs — verify live per the plan's per-source instruction | **Yes — run under each source** |
| [Dynasty Nerds](https://www.dynastynerds.com/dynasty-tools/trade-calculator/) (Dynasty GM) | Free login: 3 trades/day; Premium $69.99/yr or $6.99/mo for unlimited + Trade Finder | Own expert-analyst values (not crowdsourced) | Separate value sets per format incl. Superflex | Unconfirmed — behind login, verify during operator session | **Yes — operator browser login, per plan** |
| [FantasyCalc](https://fantasycalc.com/trade-calculator) | Public, no login; league import supported | Own values, algorithmically generated from ~2.6-3.6M real trades | Superflex setting; a FantasyPros roundup calls it "simplistic, lacks contextual analysis" | Unconfirmed — the site is a client-rendered SPA that resisted fetch; FAQ didn't surface adjustment language. **Verify live.** | **Yes** |
| [DynastyProcess / Calc](https://calc.dynastyprocess.com/) | Public, no login | FantasyPros Dynasty ECR (rankings-based, not crowd/trade-based) | 1QB vs 2QB/SF toggle, league size 6-32, Rookie Pick Optimism, Future Pick Factor | **Yes, and unique** — an explicit user-tunable "Valuation Factor" slider controlling how star players are weighted vs. bench players. This is the only calculator found with the stud tax exposed as a **first-class dial** rather than a hidden constant. Open source (GitHub `dynastyprocess/apps-calculator`), actively maintained (v3.1.6, ECR refreshed July 2026). | **Yes — high value** |
| [Dynasty Trade Calculator](https://dynastytradecalculator.com/) | Appears public for core calculator; has a `/login/` page for account features (history/favorites) — verify live | "Open market player value" — mean of a player's buy/sell line, adjusted to league params (methodology unclear, likely crowd-derived) | Unconfirmed toggles — verify live | Unconfirmed | **Spot-check** — named directly in the plan |
| [RotoWire](https://www.rotowire.com/fantasy/football/dynasty-trade-calculator) | Public, no login | Own dynasty valuation system | 1QB/SF, PPR/.5PPR/standard, TE premium, rebuilding/contending toggle, up to 6 assets/side, 3-team trades | **Yes** — FAQ names it explicitly: *"The consolidation premium is the idea that receiving a single elite player is more valuable than getting the 'equivalent' spread over three or four players."* | **Yes** |
| [TheFFDynasty (FFD)](https://theffdynasty.com/trade-calculator) | Free core; premium features need sign-in | Own "FFD Score" — crowdsourced head-to-head swipe votes, ELO-style algorithm | 1QB, Superflex, TE Premium | **Yes** — explicitly "weights elite assets more heavily... top of a dynasty roster is harder to replace," plus a separate age/position depreciation curve | **Yes** |
| [Dynatyze](https://dynatyze.com/football/trade-calculator) | Free (login page exists but core tool is described as free access) | Blended: 90% expert consensus + 10% crowd-sourced, converted via exponential decay curve | SF/1QB/2QB, PPR/half/standard | Unconfirmed — no adjustment language surfaced; the exponential decay curve itself compresses the tail, which is a soft form of stud premium. **Verify live.** | **Yes** |
| [Draft Sharks](https://www.draftsharks.com/trade-calculator/dynasty) | Free core; premium "Draft War Room" for league-synced custom values | Own values | Separate URLs per format (`/dynasty`, `/dynasty/ppr`, `/dynasty/superflex`) rather than in-page toggle; TE-premium chart customizable 0/0.5/1.0 PPR | Unconfirmed — no adjustment language found | Optional |
| [RosterAudit](https://rosteraudit.com/trade-calculator/) | Public, no login (optional Sleeper sync for roster-locked mode) | Own market model from real completed Sleeper trades (~611K+ trades, daily updates) | SF, 1QB, TE premium, all PPR formats | **Explicitly none — and says so.** FAQ: *"Consolidation adjustments on other calculators are a bandaid for values that don't come from real trades. Since our values are built entirely from actual completed trades, the market's consolidation premium is already priced in."* This is a direct methodological counter-argument to a stud tax as a separate adjustment layer. | **Yes — high value, distinct stance** |
| [DynastyDealer](https://www.dynastydealer.com/trade-calculator/superflex) (web; also iOS/Android) | Free: 5 trades/day; Premium $5.99/mo unlimited | Own model: 710K+ real Sleeper trades blended with community votes, refreshed every ~12h | 2-way/3-way toggle, SF/TE+ chips, Sleeper league sync | **Yes — the most transparent found.** Shows a labeled **"+668 STUD BONUS"** line and a collapsible **"Trade Adjustments Breakdown"** panel itemizing each adjustment per team with plain-language rationale ("elite assets are harder to acquire, earning a value bonus"). Documented in prior FTF teardown: `docs/business/product/2026-07-26-dynastydealer-dtf-teardowns.md`. | **Yes — highest value, itemized numbers** |
| [Dynasty Trade Factory](https://www.dynastytradefactory.com/) (web) | Public — Sleeper username import, no account login for core Trade Analyzer; Pro tier for AI breakdowns | Own values (methodology not published; uses "value scores" internally) | Dynasty/Redraft, SF/1QB, TEP toggles | Indirect signal only: its "Counter Suggestions" feature proposes both a single-piece AND a **2-piece package** evener for an uneven trade — showing what package the tool considers equivalent, without labeling it as a "premium." Documented in the same prior teardown doc. | **Yes** |
| [FantasyPros](https://www.fantasypros.com/nfl/myplaybook/trade-analyzer.php) | Paid (MVP subscription) | Expert consensus dynasty rankings | Considers full roster + league scoring + draft picks | Unconfirmed — paywalled, not fetched | Optional (only if operator has a subscription already) |
| [Dynasty League Football (DLF)](https://dynastyleaguefootball.com/trade-analyzer/) | Paid (DLF Premium) | Blend of rankings, ADP, and recent trade data | League-sync supported | Unconfirmed — paywalled | Optional (only if operator has a subscription already) |
| [SleeperDynasty.com](https://sleeperdynasty.com/sleeper-dynasty-trade-calculator) | Public, no login | Describes itself as a "global market consensus formula" — likely an aggregator, not original data | 1QB/SF/IDP toggle | Unconfirmed; marketing language suggests this re-serves consensus rather than an independent model | Low priority — likely redundant |
| **DynastyGM (Dynasty Nerds app)** | Free download; same paid tiers as web Dynasty Nerds | Same as Dynasty Nerds web (own expert values) | Same as web | Same as web — this is the Dynasty Nerds product in an app wrapper, not a separate calculator | **Redundant with Dynasty Nerds web** — skip separate testing |
| Dynasty Dominator (iOS app, id1456158229) | Mobile app only, no confirmed web version | Unpublished/own model | Unconfirmed | Marketing copy claims it "prioritizes quality over quantity in dynasty dealmaking" (hints at a stud premium) but unverified | Low priority — needs screen recording if pursued |
| JD Trade Analyzer (iOS app) | Mobile app only | Unpublished | Dynasty + redraft | Unconfirmed, minimal public info | Skip — too new/undocumented to prioritize |
| Dynasty Toolbox (iOS app) | Mobile app only | Unpublished | Unconfirmed | Unconfirmed | Skip — minimal public info |
| Sleeper (native app) | N/A | **No built-in trade calculator.** All the Sleeper-integrated tools above (RosterAudit, DynastyDealer, Dynasty Trade Factory, Dynasty Nerds, Dynasty Daddy) are third parties reading Sleeper's public API. | — | — | Not applicable — not a calculator |

## Per-source detail

**KeepTradeCut** — the de facto crowd baseline named in the plan. Free, public, no login. Its FAQ
is unusually candid about the stud tax: *"Trading is more than simple addition. We add value to
the side of the trade that's giving up more when you look at roster spots, players' 'stud'
factor... the adjustment itself is actually reverse-engineered from the player needed to even the
trade."* That reverse-engineering detail matters for the matrix: KTC's displayed "adjustment" number
is not a fixed multiplier, it's back-solved per-trade, so our normalized-skew comparison should
line up cleanly with what KTC itself reports as the imbalance.

**Dynasty Daddy** — public, no login, open source (`Leondoff/dynasty-daddy` on GitHub, Angular +
Node/Postgres, values scraped daily by a Python cron job). Its distinguishing feature per the plan
is the multi-source toggle: KTC, FantasyCalc, DynastyProcess, and DynastySuperflex. Note DynastySuperflex's
original site appears to have rebranded/moved to FantasyNavigator.com, so that source's feed inside
Dynasty Daddy could be stale — worth a sanity check (e.g., does a rookie who debuted in 2026 show up
under that source) before trusting its numbers in the matrix.

**Dynasty Nerds (Dynasty GM)** — free tier caps at 3 trades/day, which is tight against the plan's
6 trades × 2 formats = 12 evaluations; either spread across two days or use the operator's paid
login (the plan already routes this one through "operator browser login"). Values are analyst-set,
not crowdsourced — the one calculator in this set positioned as "our humans decided, not the
market," useful as a genuinely different reference class from KTC/FantasyCalc/RosterAudit's
market-derived approaches.

**FantasyCalc** — public, no-login, and the calculator most often cited alongside KTC as a second
crowd-consensus source. Its site is a client-rendered SPA that static fetching couldn't get past, so
its stance on multi-player package adjustment is unconfirmed from docs — this is one to resolve
live during the values-capture pass rather than from research. Values come from a large corpus of
real trades (millions) run through an "optimization algorithm," conceptually similar to
RosterAudit's approach but a different, older dataset/model.

**DynastyProcess / Calc** — the most methodologically interesting find. It's the only calculator
that exposes the stud-tax question as a **user-facing control** (the "Valuation Factor" slider,
described as tuning "how star players are valued relative to bench players") rather than a hidden
constant baked into the values. Built on FantasyPros' Dynasty ECR, open source, actively maintained.
Worth running at its default slider position for the apples-to-apples matrix, and worth noting in
the tuning proposal (if the heuristic fails) that this is a precedent for shipping a stud-tax
control as a toggle rather than only a backend constant — which lines up with the open issue #215
referenced in the plan.

**Dynasty Trade Calculator (dynastytradecalculator.com)** — named directly in the plan. Be aware
there is a confusing family of similarly-named, likely-unrelated sites: `dynastytradecalculator.net`,
`dynastytradecalc.com`, `thedynastytradecalculator.com`, `dynastyfootballtradecalculator.com`, and a
Netlify-hosted `dynastytradecalculatoronline.netlify.app`. These read like programmatic-SEO
wrapper/clone sites built around standard KTC-style value charts, not independent methodologies —
treat all but the plan's named `.com` as redundant unless a live check shows otherwise.

**RotoWire** — public, no login, and explicitly names the exact phenomenon under test: the
"consolidation premium." Supports rebuilding/contending context, 3-team trades, and up to 6 assets
per side, which is more trade-shape flexibility than most competitors — useful if a matrix trade
needs a 3-for-1 substitution.

**TheFFDynasty (FFD)** — public core, crowdsourced via head-to-head swipe votes (an ELO-family
model philosophically close to KTC but implemented independently), with an explicit stated policy
of weighting elite assets more heavily plus a separate age/position depreciation curve. A genuinely
distinct second crowd-source data point from KTC.

**Dynatyze** — free, blends 90% expert consensus with 10% crowd data via an exponential decay
curve for rank-to-value conversion. The decay curve itself compresses tail-value spread (a
different mathematical family from KTC/RosterAudit's approach), which may show up as an implicit
rather than explicit stud premium — worth checking live whether it reports a package-adjustment
number.

**Draft Sharks** — free core, TE-premium chart with adjustable PPR bump, but splits formats across
separate URLs instead of an in-page toggle (less convenient for the matrix's need to flip 1QB/SF
per trade). No adjustment language found; lower priority than the sources above.

**RosterAudit** — already tracked in FTF's competitor matrix (`docs/business/product/2026-07-20-rosteraudit-teardown.md`).
For this exercise its value is argumentative, not just numeric: RosterAudit's FAQ takes the
position that a separate consolidation adjustment is *unnecessary* because real-trade data already
prices it in. If RosterAudit's normalized skew on a stud-for-package trade comes out close to zero
while KTC/FTF show a large skew, that's evidence the "premium" is a market-consensus artifact of
crowd voting rather than something real trades actually settle at — directly relevant to the
plan's pass/fail heuristic.

**DynastyDealer** — public web calculator (correcting the plan's mobile-only assumption), also
shipped as iOS/Android apps. The single most useful source for this exercise: it doesn't just
produce a verdict, it **shows the stud/package adjustment as its own labeled number** ("+668 STUD
BONUS") with a breakdown panel explaining each adjustment per team in plain language. That means we
can record its stud-bonus figure directly rather than inferring it from a skew calculation — a
useful cross-check on FTF's own `adjustments` output format. Already toured in
`docs/business/product/2026-07-26-dynastydealer-dtf-teardowns.md`.

**Dynasty Trade Factory** — public web calculator (correcting the plan's mobile-only assumption),
Sleeper-username import with no account login for the core Trade Analyzer. Doesn't label a
"premium" the way DynastyDealer does, but its Counter Suggestions feature proposes both a
single-piece and a 2-piece-package evener for an uneven trade — the exact shape of the T1/T2/T3
matrix trades — so its suggested package composition is an indirect read on what it considers a
fair stud-for-package exchange. Also toured in the same prior teardown doc.

**FantasyPros / DLF** — both paywalled (FantasyPros MVP subscription; DLF Premium). Both use
expert-consensus-flavored methodology, overlapping conceptually with Dynasty Nerds. Only worth
running if the operator already holds a subscription to one; otherwise they add a third "expert
consensus" data point where Dynasty Nerds already covers that category.

**SleeperDynasty.com** — public, no login, but describes its methodology as a "global market
consensus formula," which reads as an aggregation of the same crowd sources already covered (KTC,
FantasyCalc) rather than an independent model. Treat as likely redundant pending a live spot-check.

**DynastyGM** — turns out to be the Dynasty Nerds mobile app, not a separate product. The plan's
list of "iPhone apps needing screen recording" should drop this one; it's covered by testing
Dynasty Nerds on the web (same account, same values).

**Dynasty Dominator / JD Trade Analyzer / Dynasty Toolbox** — small mobile-only apps with thin
public documentation. None have a confirmed independent methodology worth the screen-recording
overhead unless the matrix's other 12+ sources leave the operator wanting more mobile-native
coverage.

**Sleeper** — confirmed no built-in trade value/calculator feature. Every Sleeper-adjacent tool in
this list (RosterAudit, DynastyDealer, Dynasty Trade Factory, Dynasty Nerds, Dynasty Daddy) is a
third party reading Sleeper's public league API, not a Sleeper-native feature.

## Recommended test set

**Tier 1 — run these first (public, no login, methodologically distinct, one is the plan's own baseline):**
1. **KeepTradeCut** — the named baseline; explicit reverse-engineered stud-factor methodology.
2. **RosterAudit** — real-trade values; explicitly argues *against* a separate consolidation
   adjustment. The most direct counter-hypothesis to test against FTF's stud tax.
3. **DynastyDealer** (web) — the only source that itemizes the stud premium as its own visible
   number; lets us compare FTF's `adjustments.crown_premium`/`package_depth_discount` against a
   competitor's labeled equivalent almost apples-to-apples.
4. **Dynasty Daddy** — run under all four selectable sources (KTC, FantasyCalc, DynastyProcess,
   DynastySuperflex) per the plan's own instruction; gives 4 data points from 1 site visit.
5. **DynastyProcess / Calc** — the only calculator with a user-tunable stud-tax dial; useful both
   as a data point and as prior art if the heuristic fails and FTF ships a toggle (issue #215).
6. **RotoWire** — names "consolidation premium" explicitly in its own FAQ; own independent
   valuation source (not KTC/FantasyCalc-derived).

**Tier 2 — worth adding if time allows (public, adds a genuinely different data point):**
7. **FantasyCalc** — widely cited second crowd-consensus source; confirm live whether it applies
   any package adjustment (unconfirmed from docs).
8. **TheFFDynasty (FFD)** — independent crowdsourced ELO model with explicit stud + age-depreciation weighting.
9. **Dynatyze** — blended expert/crowd model with a different math family (exponential decay).
10. **Dynasty Trade Factory** (web) — indirect signal via its package-evener suggestions.
11. **Dynasty Nerds** — the only pure analyst-set (non-crowd, non-real-trade) values in the set;
    access-constrained to 3 free trades/day, so route through the operator's paid login as the plan
    already specifies.

**Tier 3 — skip or deprioritize (redundant, paywalled without existing access, or undocumented):**
- **SleeperDynasty.com, Draft Sharks** — no confirmed independent adjustment methodology found;
  Draft Sharks' per-format URL split also makes it more friction to run than the Tier 1/2 sites.
- **FantasyPros, DLF** — paywalled; both are expert-consensus flavored, a category Dynasty Nerds
  already covers in Tier 2. Only run if the operator already has an active subscription.
- **dynastytradecalculator.net / dynastytradecalc.com / thedynastytradecalculator.com /
  dynastyfootballtradecalculator.com / dynastytradecalculatoronline.netlify.app** — likely
  programmatic-SEO clone sites re-serving standard KTC-style charts; add no independent signal.
  Spot-check only the plan-named `dynastytradecalculator.com` itself, not its lookalikes.
- **DynastyGM** — redundant with Dynasty Nerds web (same product, app wrapper only). Drop from the
  screen-recording list.
- **Dynasty Dominator, JD Trade Analyzer, Dynasty Toolbox** — thin documentation, mobile-only,
  unconfirmed methodology; not worth the screen-recording overhead unless Tier 1/2 results are
  ambiguous and more mobile-native coverage is wanted.
- **Sleeper native** — not a calculator; exclude entirely.

**Net effect on the plan's iPhone-app section:** of the three apps named (DynastyGM, Dynasty Trade
Factory, DynastyDealer), two (Dynasty Trade Factory, DynastyDealer) turn out to be runnable directly
on the public web — no screen recording needed — and the third (DynastyGM) is redundant with
Dynasty Nerds' web product. The screen-recording pipeline described in the plan may not be needed
for this round at all unless the operator wants to additionally cover Dynasty Dominator / JD Trade
Analyzer / Dynasty Toolbox for completeness.
