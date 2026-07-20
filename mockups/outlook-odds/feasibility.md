# FB #169 — Outlook, Odds & Value: feasibility brief

**Session type:** design + honest feasibility. Mockups only — no app code changed, nothing committed.
**Deliverables:** `mockups/outlook-odds/{index,value-bar,league-summary,outlook-card}.html` + this brief.
**Operator decision this brief supports:** how far to fund the modeling. The near-term slice ships value on its own; the modeling slice is a real, sequenced set of projects.

The operator expanded #169 into a vision of **outcome-framed, objective trade impact** — not just "is this fair" but "what does this do to my season, my odds, my roster." Below, every claim is graded against what the codebase actually serves today.

---

## TL;DR

| Piece | Verdict | Gated on |
|---|---|---|
| Value-bar trade verdict (pick-denominated) | **Near-term** — pure reskin | nothing (data exists) |
| League Summary bar chart, **dynasty** basis | **Near-term** | nothing (data exists) |
| Position filter → live reorder/rescale + roster drill-in | **Near-term** | nothing (client-side) |
| "About fit, not value" fit line on cards | **Near-term** | nothing (`analyze_roster_strengths` exists) |
| League Summary **redraft** basis | **Modeling** | redraft/projection value source |
| Season / final-standing projections | **Modeling** | projection model |
| Playoff % + championship % (single + multi-year) | **Modeling** | projection model + league-state simulator + playoff-format logic |
| Schedule-aware "+N wins" deltas | **Modeling** | the simulator, re-run with/without the player |
| Outlook-tightened 1st-round pick slotting | **Modeling** | projected final standings → draft slots |

**Two dependencies gate the entire modeling slice:** (1) a **redraft / current-season value source**, and (2) a **league-state season simulator**. Everything outcome-framed compounds these two.

---

## What exists today (grounding)

Read during this session:

- **`backend/power_rankings.py` / `GET /api/league/power-rankings`** — ranks every team by summed roster value. Returns `total_value`, `positions: {QB|RB|WR|TE: {count, value}}`, and `roster` already **grouped by position and value-desc within group**. Basis `consensus` | `personal`; **`redraft` is explicitly reserved but 501s `not_available`** (module docstring: "DynastyProcess ships dynasty values only").
- **`backend/trade_service.py`**
  - `elo_to_value` / `value_to_elo` — the single dynasty value scale for all v2 trade math (base 1000, ref 1500, k 0.005; top consensus asset ≈ Elo 1927 ≈ 4× a Mid 1st).
  - `analyze_roster_strengths` — profiles a roster into `tier_depth` (elite/starter/bench per position), `position_needs`, `position_surplus`. Already the substrate for a "you're thin at RB" fit line.
- **`GET /api/trade/evaluate`** (`backend/server.py`) — for a hand-built trade returns `give_value`, `receive_value`, `point_ratio`, `fairness`, `verdict`, `favors`, and a **`gap` object** `{value, add_to, firsts, pick_equivalent}`. `_pick_gap_equivalent()` converts any value gap into "≈ N firsts" + the nearest single generic pick (`GENERIC_PICK_SEEDS`, rounds 1–4 Early/Mid/Late). Mode B adds both owners' boards + `mutual_gain`.
- **Fairness meter invariant** (`docs/cross-client-invariants.md`) — `fairness_score` is a `[0,1]` float; clients render `round(fairness*100)`.
- **Pick-value ladder** — 8-tier ladder denominated in draft-pick terms (`firsts_4plus` … `waivers`), position-uniform by design.

**Net:** the value axis, the pick-denomination machinery, and per-position roster valuations all already exist. The outlook/odds axis does not exist in any form.

---

## Near-term slice — buildable now, no new data

### 1. Value-bar trade verdict  (`value-bar.html`)
Reframe the existing fairness meter as a **diverging bar centered on "even."** Left = they win, right = you win; fill length = the gap; tick marks at pick landmarks (−4th … +1st). The verdict copy is pick-denominated: *"You win, by +4,520 — the equivalent of ≈2.1 firsts"* or *"Ask them to add ≈ a Mid 2nd to even it out."*

- **Every input already served** by `/api/trade/evaluate`: `give_value`, `receive_value`, `gap.firsts`, `gap.pick_equivalent`. The mock reproduces `_pick_gap_equivalent`'s behavior exactly — including leaning on the `firsts` count (not a single pick) once the gap exceeds one pick's range.
- **Coordinate with FB-157** — same "value in pick terms" concept. Build one shared component; render it in both the calculator verdict and the finder card. Recommend #169 and #157 land together.
- **Scope:** front-end only (mobile `TradeCard` / `TradeCalculatorScreen` + web `renderTrades`). Respect the fairness-meter invariant (don't rescale server-side).

### 2. League Summary bar chart — dynasty basis  (`league-summary.html`, Dynasty tab)
Replace the current text list with a **vertical bar chart**: one bar per team, **stacked by position** (QB/RB/WR/TE in the canonical position hexes), ordered most→least valuable, total on the right, team links are the bars themselves.

- **Data already served** by `/api/league/power-rankings` — `total_value` + `positions[pos].value` per team is exactly the stack.
- **Position filter (single or multi)** — tapping QB/RB/WR/TE re-sums each team on the selected positions only, **reorders and rescales the chart live**, and collapses each bar to the filtered segment(s). "All" resets. This is a pure client-side transform over the same payload — verified working in the mockup (filter to WR → chart reorders by WR value, single blue segment, rescaled).
- **Roster drill-in** — tapping a team opens its roster **grouped by position, value-desc within group**, itself position-filterable. `team.roster` already arrives in this exact shape (`power_rankings.py` sorts it). This largely re-skins the existing `LeagueSummaryScreen` overlay.
- **Scope:** front-end only. The one honest caveat is the Redraft tab (below).

### 3. Fit line on suggestion cards
*"Even by value — this deal is about fit, not value"* + a position callout. `analyze_roster_strengths` already yields `position_needs` / `position_surplus`; the finder already stamps `need_fit` / `partner_fit` on cards. This is copy + light plumbing of signals that exist. (The green strip in `outlook-card.html`.)

---

## Modeling slice — real projects, do not fake

Everything below is rendered in the **amber block** of `outlook-card.html` and the **Redraft empty state** of `league-summary.html`, deliberately visually separated from the near-term green/dynasty content so the operator sees the line.

### Dependency A — Redraft / current-season value source
FTF's only value axis is **dynasty** (long-horizon, KTC-style). Redraft values, weekly-points projections, and standings projections are the **same missing input seen three ways** — all start from *"how many points will this player score the rest of THIS season."*

- **Unblocks:** the Redraft bar-chart tab; feeds the simulator below.
- **Options:** license/ingest a redraft value feed (DynastyDaddy and FantasyCalc both expose redraft), or build a projection→value pipeline. Either is an ingestion + modeling project, not a display change.
- **References:** DynastyDaddy ships dynasty **and** redraft; FantasyCalc has a redraft toggle.

### Dependency B — League-state season simulator
Projected record, playoff %, championship %, and "+N wins" all require **simulating the rest of this specific league's season**:

1. current **standings** (wins/losses/points) — need league scoring history ingestion,
2. **remaining schedule** — per-league matchup grid,
3. **per-matchup win probabilities** — from a starting-lineup points projection (Dependency A),
4. **Monte-Carlo** over the remaining weeks → playoff/title distributions,
5. **playoff-format logic** — seeds, byes, bracket (title odds must reflect that a bye ≈ a free round).

- **"+2 wins from this trade"** = re-run the sim with the added player in / removed player out and diff the expected wins. Only meaningful once 1–4 exist.
- **Multi-year (2026/27/28) championship odds** = the sim projected forward with roster aging + future picks; compounds every dependency.
- **Reference:** RosterAudit's multi-year championship-odds view is the scope target.

### Dependency C — Outlook-tightened pick slotting
Today picks are flat `GENERIC_PICK_SEEDS` (Early/Mid/Late × rounds 1–4). The vision prices a 1st by **projected draft slot** — a rebuilder's 1st projects early (more valuable), a contender's projects late. Requires **projected final standings** (output of Dependency B) → pick-slot → value. DynastyDaddy does exactly this. Downstream of B; also feeds back into every value/verdict surface once live.

**Sequencing:** A (redraft/projection values) → unlocks the redraft chart and feeds B. B (simulator) → unlocks record/playoff/title deltas. C (slot pricing) → rides on B's standings projections. The **near-term slice ships independently of all three.**

---

## Recommendation

1. **Ship the near-term slice now**, ideally #169 + #157 together as one "value in pick terms + bar-chart League Summary" release. Low risk, all front-end, high perceived-value.
2. **Treat the outlook/odds vision as a funded modeling track**, gated on Dependency A first (it's the cheapest unlock and independently useful as the Redraft basis). Scope A and B as their own specs before committing UI — the `outlook-card.html` amber block is the honest target, not a near-term promise.
3. **Do not ship any projected number** (record, %, wins) until B exists. A fabricated 86% playoff odds is worse than none — it reads as authoritative. The mockup marks every such number "Projected/beta" for exactly this reason.

---

## Files

| File | What it shows | Grade |
|---|---|---|
| `index.html` | Hub: mockup links + the near-term/modeling split + dependency map | — |
| `value-bar.html` | Diverging value bar + pick-denominated verdict (3 examples: lopsided/close/even) | Near-term |
| `league-summary.html` | Interactive bar chart: position filter reorder/rescale, dynasty/redraft toggle, roster drill-in | Near-term (dynasty); Redraft = modeling |
| `outlook-card.html` | Suggestion card with record/playoff/title deltas + multi-year odds; green (real) vs amber (modeling) split | Modeling |

All self-contained HTML, dark Chalkline tokens, mobile frames, realistic 12-team superflex league. Redraft numbers in `league-summary.html` are fabricated to demonstrate divergence and are labeled as non-existent in-product.
