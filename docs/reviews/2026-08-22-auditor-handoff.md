# Auditor handoff — where the trade-engine reports live

> **Purpose:** a single entry point for an external reviewer auditing FTF's trade
> generation. Everything referenced here is in `mattmurf77/fantasy-trade-finder`.
>
> **Status:** point-in-time index, 2026-08-22. Per [`CLAUDE.md`](CLAUDE.md), the reports
> below are audit snapshots, not reference — the code and
> [`docs/api-reference.md`](../api-reference.md) are truth.

---

## Start here

**[`2026-08-19-armb-audit-consolidated.md`](2026-08-19-armb-audit-consolidated.md)** — on `main`.
Verdicts on all seven review claims and all fifteen remedy rows, with file:line citations,
live knob values, and measured deltas. It is the index for everything else.

## The validation memos

On `main`, all seven:

| File | Covers |
|---|---|
| [`2026-08-19-armb-audit-claims-1-2.md`](2026-08-19-armb-audit-claims-1-2.md) | consensus user-win gate; user-only 1-for-1 gate |
| [`2026-08-19-armb-audit-claims-3-4.md`](2026-08-19-armb-audit-claims-3-4.md) | R5 need gate; Elo asymmetry (the replay harness lives here) |
| [`2026-08-19-armb-audit-claims-5-6.md`](2026-08-19-armb-audit-claims-5-6.md) | pick representability; fairness basis |
| [`2026-08-19-armb-audit-claim-7.md`](2026-08-19-armb-audit-claim-7.md) | ranking overlays and narrative copy |
| [`2026-08-19-armb-remedy-bucket-a.md`](2026-08-19-armb-remedy-bucket-a.md) | six dualization proposals, measured |
| [`2026-08-19-armb-remedy-bucket-b.md`](2026-08-19-armb-remedy-bucket-b.md) | four drop-or-invert proposals |
| [`2026-08-19-armb-remedy-bucket-c.md`](2026-08-19-armb-remedy-bucket-c.md) | five "safe to keep user-only" overlays |

## Supporting measurements

On `main`:

- **[`2026-08-19-consensus-gate-matrix.md`](2026-08-19-consensus-gate-matrix.md)** — the both-ways
  replay. Answers the P3 question: 0.75 both-ways **doubles** the deck rather than collapsing it,
  and fairness becomes a hard damage cap at exactly `1 − threshold`.
- **[`2026-08-19-knockout-waterfall.md`](2026-08-19-knockout-waterfall.md)** (+ its `/` data
  directory) — every candidate trade, which rule killed it, and which rules kill trades
  *nothing else would*.
- The pick-ladder trio: [`ktc-pick-value-comparison`](2026-08-19-ktc-pick-value-comparison.md),
  [`pick-year-valuation`](2026-08-19-pick-year-valuation.md),
  [`pick-badge-scale`](2026-08-19-pick-badge-scale.md).

**Newest, on branch `audit/knockout-waterfall-v2`:** `docs/reviews/2026-08-22-knockout-waterfall-v2.md`
— re-run against the current three-arm production roster, with per-arm waterfalls, value-bar gap
analysis, and the 200 most lopsided candidates. Not on `main`.

**Product spec, on branch `docs/landability-challenger`:** the challenger-arm PRD, with the C1
measurement on branch `docs/landability-c1-measurement`.

---

## Four things most worth an outside eye

1. **The challenger flips direction rather than centring.** `current`'s survivors are 82% in the
   viewer's favour; the challenger's are 60% the *partner's*, at double the gap. Removing the
   user-Elo shrink did not make the deck even — it pointed it the other way. That was not the intent.
2. **The challenger's headline levers are untested.** `consensus_both_ways`, the 0.75 floor and the
   consensus half of the shrink execute only when the partner has no board. The one league with
   enough boards to measure has all-boarded members, so **84.5% of the product is unmeasured** — and
   that is the half the design targets.
3. **Only four rules do independent work** — `min_side_surplus`, `fairness`, `S3d_fairness_band`,
   `feasibility` — stopping 0.15% of the universe between them. `gap_max` first-kills roughly half of
   everything and uniquely kills essentially nothing.
4. **Survivors fell 300 → 133 (−56%)** between the two knockout runs and nobody has isolated why.
   ~30 commits sit between them; no bisect was run.

## Two caveats to carry into any reading

- **Every number is a replay of one league** — six boarded members, the only league in production
  that qualifies. Replay counts, **not production serving counts**.
- **A pick-horizon defect contaminates pre-2026-08-19 outcome data.** 12.8% of historically served
  cards contained draft picks that did not exist in the league, and they were passed at roughly
  double their like rate. Compositional findings hold; acceptance-rate inference from that window
  does not.
