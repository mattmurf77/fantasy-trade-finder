# #214 — Stud-Tax Competitive Validation Exercise

**Feedback (mattmurf77, TradeCalculator):** "Justin Jefferson for Lamb and Nix doesn't seem fair. I think the stud tax is too heavy. We need to run a competitive test."

**Question under test:** Is FTF's package-depth discount + crown/consolidation premium (the "stud tax") systematically heavier than the market-consensus calculators? I.e., when a stud is traded for a two-piece package, do we demand meaningfully more side-B value than DynastyDaddy / KeepTradeCut / DynastyNerds / others?

## Method

For each trade in the matrix, capture from every calculator:

1. **Verdict** — who wins, and by how much (each site's own units).
2. **Normalized skew** — `(sideB_total − sideA_total) / sideA_total`, using that site's own values. This makes sites comparable without unit conversion: it answers "how much extra package value does this calculator demand (or award) for the consolidation?"
3. **Package adjustment visibility** — does the site apply any explicit multi-player discount or stud premium (some show it, some just sum raw values)?
4. **FTF numbers** — same trade through `/api/trade/evaluate` (consensus mode, no league context) AND in-league mode in the operator's league: record `naive_totals`, `adjustments` (package-depth discount, crown premium), final totals, verdict, gap.

**Pass/fail heuristic:** compute FTF's normalized skew vs the median competitor skew per trade. If FTF's required package premium exceeds the competitor median by >10 percentage points on 3+ of the 6 matrix trades, the stud tax is too heavy — output is a recommended re-tune of the package-depth/crown constants (docs/cross-client-invariants.md governs where they live), gated behind a before/after replay of the trade matrix.

## Trade matrix

All run in **both 1QB and Superflex** where the calculator supports format switching (Nix's value swings hardest on format — flagging format mismatch as a confound is part of the exercise):

| # | Side A (stud) | Side B (package) | Probes |
|---|---|---|---|
| T1 | Justin Jefferson | CeeDee Lamb + Bo Nix | The reported trade |
| T2 | Ja'Marr Chase | Nico Collins + Brian Thomas Jr. | WR-only consolidation (no QB confound) |
| T3 | Bijan Robinson | Jahmyr Gibbs + De'Von Achane | RB consolidation, tight tier gap |
| T4 | Justin Jefferson | CeeDee Lamb + 2027 1st (mid) | Player + pick package (our pick ladder vs theirs) |
| T5 | Josh Allen | Jayden Daniels + Drake Maye | SF-only QB consolidation |
| T6 | Malik Nabers | Tetairoa McMillan + DK Metcalf | Stud vs young piece + aging vet (age handling) |

If a specific player is missing on a site, substitute the nearest-value same-position player *on that site's own rankings* and record the substitution.

## Sources

| Source | Access | Notes |
|---|---|---|
| KeepTradeCut | Public web | Crowd-sourced; the de facto market baseline |
| DynastyDaddy | Public web | Supports multiple ranking sources — run the trade under each available source (incl. KTC if offered) and record per-source |
| Dynasty Nerds | Operator browser login | Operator runs the matrix and screenshots (or screen-records) results |
| DynastyDealer | Public web | **Correction (landscape research):** not mobile-only — dynastydealer.com/trade-calculator. Uniquely shows a labeled "STUD BONUS" + itemized adjustments breakdown, so its premium is directly readable |
| Dynasty Trade Factory | Public web | **Correction:** not mobile-only — dynastytradefactory.com, no login |
| Others (research task) | TBD | Full enumeration in `research/calculator-landscape.md` (20+ sources, tiered test set). Notables: RosterAudit argues consolidation premium is already priced into market values (counter-hypothesis); DynastyProcess/Calc has a user-tunable star-weighting slider (prior art for the #215 toggle) |

### iPhone-app tests — how to give me access (per the feedback offer)

No credentials needed and none should be shared. Two working options, in preference order:

1. **Screen recordings** (proven pipeline — same as the DynastyGM/DynastyDealer teardowns): install the app, enter each matrix trade, record the screen showing the verdict, drop the recordings in chat. I extract frames with ffmpeg and read the values.
2. **Screenshots** of each trade's result screen, named `T1-<app>.png` etc.

Per the landscape research, only **DynastyGM** still needs this route — and it's the Dynasty Nerds app, so if the operator runs the matrix on Dynasty Nerds web (option in Sources above), the app pass is redundant and can be skipped entirely. DynastyDealer and Dynasty Trade Factory moved to the public-web column.

## Deliverables

- `research/calculator-landscape.md` — every dynasty trade calculator found, access class, ranking sources offered (research agent)
- `research/competitor-values.md` — the matrix run on public calculators, with normalized skew per trade per site (research agent)
- `results.md` — FTF's own numbers on the matrix + the comparison table + verdict on the heuristic (after research lands; FTF numbers pulled via `/api/trade/evaluate`)
- If the heuristic fails: a follow-up tuning proposal (constants, before/after replay) as `tuning-proposal.md` — **not** auto-applied; operator decision (note open #215 asks for a stud-tax *toggle*, which may be the ship vehicle)

## Confounds to record, not ignore

- Format (1QB vs SF) per run
- Ranking-source choice inside DynastyDaddy (record per source, don't average)
- Date of capture (crowd values move; capture the whole matrix in one sitting per site)
- FTF league-context vs consensus mode (our in-league adjustments — need/fit — are a feature, not stud tax; the comparison uses consensus mode, league mode recorded as a secondary column)
