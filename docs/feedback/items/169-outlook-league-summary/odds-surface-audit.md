# #169 — Odds & projected-standings surface audit

**Date:** 2026-08-10 · **Author:** design orchestrator (4 surface-scoped sub-agents + reconciliation)
**Inputs:** [`odds-surface-audit-brief.md`](odds-surface-audit-brief.md) (mission) +
[`calibration-combined-2026-08-10.md`](calibration-combined-2026-08-10.md) (settled facts).
**Outputs:** this audit + `mockups/outlook-odds/league-summary-outlook-v2.html` +
`mockups/outlook-odds/outlook-card-v2.html` + updated `mockups/outlook-odds/index.html`.
**Scope guard:** mockups and docs only. Zero changes to `mobile/`, `backend/`, `web/`, `extension/`.
Nothing here ships; the operator reviews and picks.

## Table of contents

- [Settled constraints this audit designs within](#settled-constraints-this-audit-designs-within)
- [Route defect found during the audit (fix before lighting)](#route-defect-found-during-the-audit-fix-before-lighting)
- [Full surface enumeration — verdicts](#full-surface-enumeration--verdicts)
- [The four questions, answered](#the-four-questions-answered)
- [Reconciliation log](#reconciliation-log)
- [Ranked build order](#ranked-build-order)
- [Where the settled constraints forced a design](#where-the-settled-constraints-forced-a-design)
- [Open questions for the operator](#open-questions-for-the-operator)

---

## Settled constraints this audit designs within

Decided by [`calibration-combined-2026-08-10.md`](calibration-combined-2026-08-10.md) §7–8;
not re-opened here:

| Fact | Design consequence |
|---|---|
| Playoff odds validated (+60.1% in-season, +21.3% preseason, both CIs exclude 0) | Playoff odds may render, with the framing rules below |
| **Title odds: no demonstrated skill** (CI spans zero; 3 of 6 league-seasons worse than a constant) | **Removed everywhere.** Not caveated, not de-emphasized — absent |
| Over-confidence survived the fix wave (preseason 95% → 78% realized; lower CI bound worsened to +2.9%) | **Bands, not percentages, weeks 0–5:** Likely / Toss-up / Unlikely |
| Gate = week 6; `meta.beta` already clears at `completed_weeks >= 6` | **The beta flag IS the gate** — no new mechanism. Weeks 0–5 banded + "Projected · beta"; week 6+ numbers permitted |
| A 5%-rounded playoff % from week 6 is defensible on pooled calibration but not week-stratified | Presented as an **operator risk option** (frame C2), never as the recommendation |
| `meta.priced_slot_coverage` ships (FFv3: 0.4667, 8 unpriced slots) | IDP leagues MUST carry a "based on your offensive starters" caption whenever `affects_strength` is true; `trailing_scores` payloads never captioned |
| `status == "pre_draft"` → no schedule | Render nothing |

Proposed band thresholds (operator sign-off item): **Likely ≥ 0.65 · Toss-up 0.35–0.65 ·
Unlikely < 0.35.** Grounded in the preseason calibration table — buckets ≥ 0.65 realize
0.60–0.78 and buckets ≤ 0.35 realize 0.0–0.5, so three bands are the finest granularity the
preseason evidence supports. Chip colors reuse the pos/warn/neg tercile-chip precedent already
shipped on `LeagueSummaryScreen` (data encodings, not chrome). **The day any band ships, the
band keys, labels, thresholds, and colors become entries in `docs/cross-client-invariants.md`.**

## Route defect found during the audit (fix before lighting)

**`backend/server.py:19465` resolves `platform` from the SESSION's attached league, but
`backend/server.py:19439` takes `league_id` from the query string.** The two can name
different leagues:

```python
league_id = request.args.get("league_id") or (g_league.league_id if g_league else "")  # :19439
...
platform = (getattr(g_league, "platform", None) or "sleeper")                           # :19465
```

- A session attached to an **ESPN league** requesting a **Sleeper** `league_id` gets
  `platform="espn"` → `build_league_state` raises `NotImplementedError` → a spurious
  **501 not_supported** for a league the engine could serve.
- A session attached to a **Sleeper league** (or none) requesting an **ESPN** `league_id`
  queries that id against the Sleeper API → empty teams → a misleading
  **404 league_not_found** instead of the honest 501.

**Status: latent, not exploitable.** The flag is dark (route 404s first), the mobile client
always passes the active league's own id, and Sleeper league data is public so no
information-exposure exists. But it is wrong-answer-producing the day the flag lights for any
multi-league user. **Fix:** resolve platform from the *requested* league (or reject a
`league_id` that isn't one of the session's leagues), independent of any design decision here.

**FIXED (2026-08-10).** `backend/server.py`'s `league_outlook_route` now resolves `platform`
via `get_league_draft_context(league_id)` — the same DB-lookup convention the pick-assignments
seeder and the draft-status stamp already use — keyed on the *requested* `league_id`, defaulting
to `"sleeper"` only when that league has no `leagues` row (unlinked/never-synced, matching the
prior fallback). `g_league.platform` is no longer read at all. Regression coverage added in
`backend/tests/test_outlook_odds.py`: an ESPN-attached session requesting a Sleeper `league_id`
now gets the Sleeper 200 instead of the spurious 501; a Sleeper-attached session requesting an
ESPN `league_id` now gets the honest 501 `not_supported` instead of a Sleeper-API-driven 404;
the single-league case (session and request agree) is pinned unchanged. `outlook.odds` stays
dark — this is a correctness fix, not a lighting decision. Full suite: 2298 passed, 1 skipped,
plus 3 new tests → 2301 passed, 1 skipped.

**Sibling defect found, not fixed (out of scope for this pass):** the same class of mistake
exists at `pick_assignments_order_route` (`backend/server.py`, `POST
/api/league/pick-assignments/order`, ~line 11075 on `main`@16b1dcb) —
`platform=str(getattr(g_league, "platform", None) or (get_league_draft_context(league_id) or
{}).get("platform") or "espn").lower()` prefers the session's attached-league platform over a
DB lookup keyed on the request body's `league_id`, so it has the same latent multi-league
mismatch potential (masked today because that route's `league_id` also defaults from `g_league`
and the assignment feature is exercised almost exclusively single-league). Flagging for a
follow-up pass; not touched here per this fix's scope (`backend/server.py`'s outlook route
only).

## Full surface enumeration — verdicts

One **Belongs** now. Two **Belongs later**. Everything else rejected — per the operator's
own tenets (#205), a percentage sprinkled across screens is worse than none.

| # | Surface | Verdict | Which product | Reasoning (compressed; grounded in shipped code) |
|---|---|---|---|---|
| 1 | **`LeagueSummaryScreen` — the League tab root** | **BELONGS — the only "now"** | **Both, merged into ONE section** | The shipped `OddsSection` (~line 1406+, dark) is three revisions behind evidence: title stat, raw 1%-precision `pct()` at any week, "proj seed 3.2", no coverage caption. Redesign (mockup `league-summary-outlook-v2.html`): one seed-ordered "Season outlook" section = projected standings (row order) + playoff odds (band chip) + playoff cutline; weeks 0–5 banded, week 6+ numbers; IDP caption from `priced_slot_coverage`. |
| 2 | `LeagueScreen` (classic league home) | Doesn't belong | — | Single-surface discipline: the League tab root owns the outlook; a second rendering one push away adds maintenance and repetition, not information. |
| 3 | `MatchesScreen` | Doesn't belong | — | It's an inbox ("someone agrees with this trade"); per-match odds re-import the deck cost problem; season-strategy questions route to the calculator. |
| 4 | **TradesScreen deck cards** (`TradeCard.tsx`) | **Doesn't belong — ever, in numeric-delta form** | — | Measured: ~3.8s CPU per 10k-sim run; a generate job produces ~30 cards (`trade_service.py:2337`) and regenerates on every DNA edit → ~2 CPU-minutes per deck to (weeks 0–5) print "band unchanged" thirty times. The card already carries ~10 information layers. The deck's "why this trade" story is the SHIPPED #169 position-impact tier chips. |
| 5 | TradesScreen deck **context** (Trade-DNA receipt line) | Belongs later | Playoff **band** only | One cached league-level band ("Rebuilding · toss-up for the playoffs") validates the user's declared outlook at zero marginal per-card cost. Blockers: week gating, coordination with surface #1 (same payload), copy design. |
| 6 | Featured trade / asset ideas panel | Doesn't belong | — | Consensus-sweep candidates with no match score (the window already hides `StrengthBar` for them); attaching season-odds machinery to the least-personalized cards is upside-down. |
| 7 | **Trade calculator / trade summary** (`InLeagueCalculator` Mode B) | **Belongs later — the one trade surface that earns odds** | Playoff delta + projected record, **week 6+ only**, on-demand | One trade, user-built, explicit intent. Cost is O(1) per user action: cached baseline per (league, week) + one CRN-paired with-trade run (~2–4s, async, behind a tap-to-load disclosure below `LineupImpactTable` — never inside the 250ms-debounced evaluate). Blockers: with-trade sim endpoint doesn't exist; `meta.beta` gating; own sub-flag. Mockup: `outlook-card-v2.html`. |
| 8 | FreeAgents / DraftRoom / MockDraft / RankHome / Trends / Tiers / Settings / Profile / Portfolio | Doesn't belong (all) | — | Decoration on every one — none of these frames a season-outcome decision. Rejecting eight surfaces is the tenet-#205 outcome working as intended. |
| 9 | **Push notifications** | **Doesn't belong standalone** — narrow later exception | — | Consent grounds: the push primer promises **transactional match events**; an odds broadcast breaches that promise (kept verbatim per reconciliation — this WILL be re-proposed by someone who doesn't know). Odds drops are also unsolicited bad news. Only acceptable later shape: **one clause in the existing Tuesday `weekly_digest`, week 6+, band transitions only** ("You moved from Toss-up to Likely") — opted-in, weekly cadence matches the sim's real update rate, and transitions are rare enough to stay meaningful. |
| 10 | **Web** (`web/league-rankings.html`) | Belongs later | Same merged section as #1 | The natural host page exists but is itself behind a dark flag — lighting odds on web before the host surface lights inverts the dependency. When it comes: identical band grammar (cross-client invariants). |
| 11 | **Extension** (Sleeper overlay) | Doesn't belong — explicit non-goal | — | The overlay renders on Sleeper pages, where Sleeper's own native odds can appear; shipping a second, disagreeing number into that context is a credibility trap, not a feature. |
| 12 | **Non-Sleeper leagues** (ESPN/MFL/Fleaflicker) | Honest unavailable state required | — | `backend/outlook/league_state.py`: only `SleeperLeagueState` is real; the others are registered `NotImplemented` stubs. The League tab IS reachable for these leagues, so silence isn't honest degradation, it's a mystery. Design: client-side platform gate (don't call the endpoint; avoids the 501 round-trip) + one explanatory row: "Season outlook needs schedule and scoring history — Sleeper leagues only for now." Plus the route platform fix above. |

## The four questions, answered

### 1. Where do projected standings live?

**Inside the same League-tab section as the playoff odds — the seed order IS the standings.**
Nothing gets its own screen, tab, or toggle state. Evaluated and rejected: (a) a third basis
state on the ranked value list (overloads a toggle that means "which value board"); (b) a
second parallel section next to the odds section (two adjacent 12-row lists violate #205);
(d) a dedicated screen (a whole screen for one table nobody visits twice a week). Chosen:
**(c) merge** — the section's rows are ordered by projected finish, the dashed cutline marks
the playoff line, and each row carries the band chip. Weeks 0–5 the order alone carries the
standings claim (no W-L numbers — see reconciliation #1); week 6+ each row gains
`current record · proj final record`. This makes the standings product — previously shown
nowhere — the *skeleton* of the odds product rather than a competitor to it.

### 2. Does a trade need to move odds to be worth showing?

**No — and designing as if it does would break the product.** Most FTF trades *can't* move a
band, because the finder's whole point is near-fair mutual-gain trades; weeks 0–5 the only
permitted display would print "unchanged" thirty times per deck at ~2 CPU-minutes a run. A
"no change" chip actively undermines a good trade whose honest story is "TE21 → TE4" — which
already ships. Per surface: deck → qualitative framing (shipped tier chips) + later one
league-level band context line (no per-card sim); calculator/summary → the one earned odds
surface: on-demand before/after, week 6+ only, playoff only; matches → nothing. A technical
note that changes the cost calculus: the simulator seed is deterministic per league, so
with/without runs share random numbers and MC noise largely cancels in the delta — **the
binding constraint on deltas is model skill, not variance**, which is why `meta.beta` gates
deltas exactly as it gates levels. Seasonal framing worth stating: preseason dynasty trades
are roster-construction trades (tier chips are the right instrument); the week 6+ deadline
window is when "does this help my push" is both askable and answerable.

### 3. Do odds belong on a notification?

**Not as a standalone push.** Two independent grounds: (1) **consent** — the push opt-in
primer promises transactional match events; an odds broadcast breaches that promise; (2)
**welcome-ness** — odds move most dramatically downward after a loss the user already felt;
pushing "your playoff odds dropped 12 points" is the app volunteering bad news it wasn't
asked for. The one acceptable later shape: a clause in the existing opted-in Tuesday
`weekly_digest`, week 6+ only, **band transitions only** — rare, meaningful, cadence-matched
to when the sim actually updates. Never a new notification category, never preseason.

### 4. What about non-Sleeper leagues?

**Design the unavailable state; don't assume parity.** ESPN/MFL/Fleaflicker are
`NotImplemented` stubs in `league_state.py`; whether ESPN's integration can ever feed Phase 1
(full weekly scores + future schedule + playoff format) is unproven and NOT assumed here. The
honest state is a single explanatory row on the League tab (copy above), a client-side
platform gate so the app never fires a doomed request, and the `server.py:19465` platform fix
so the error taxonomy is at least truthful for multi-league sessions in the meantime.

## Reconciliation log

Disagreements between sub-agents (or sub-agent vs orchestrator), re-verified against code,
per the house dual-lens pattern:

1. **Preseason projected W-L in the league rows.** The League-tab agent's proposed row shape
   included "proj 10-4" during weeks 0–5. **Overruled by the orchestrator:** a projected
   final record is the same false-precision point estimate as "71%" wearing a different unit;
   the bands verdict exists precisely to withhold that. Weeks 0–5 rows carry seed order +
   band chip only; records join at week 6 (frames B vs C1).
2. **Projected record on the week-6+ trade card.** The trade-surfaces agent killed the July
   card's record-delta row outright ("a second noisy number #205 doesn't allow"); the
   orchestrator's anti-amputation design uses the record cell as title's replacement.
   **Resolution: keep the two-cell shape (record | playoff) on the on-demand summary** — the
   user explicitly opened this disclosure, `projected_wins` is a validated output post-BUG-1,
   and the two-up rhythm is what prevents the amputated look — while noting the agent's
   single-cell minimal variant remains available if the operator wants maximum austerity.
   Recorded as a genuine judgment call, not a fact.
3. **Deck-top band context line.** Proposed by the trade agent, not evaluated by the
   League-tab agent though it reads the same payload. Adopted as a "belongs later" item
   (#5) with an explicit coordination note — it must render the same band string, from the
   same cached response, as surface #1.
4. **Trade-surfaces agent's late return.** Its report arrived after the orchestrator had
   independently reached the same deck-rejection and calculator-only conclusions from
   `TradesScreen.tsx`; the agent's measured sim benchmark and CRN observation strengthen
   (and in the CRN case, correct the emphasis of) the reasoning and are credited above.

## Ranked build order

1. **League Summary "Season outlook" v2** — the ship-first recommendation. Frames B (weeks
   0–5, bands) + C1 (week 6+, records + bands) + D (IDP caption) in
   `league-summary-outlook-v2.html`. Playoff-only, merged standings, `meta.beta` two-state,
   `priced_slot_coverage` caption. Includes deleting the Title stat, `pct()` raw rendering,
   and decimal projected seed from the shipped dark code.
2. **Pre-lighting fixes bundled with #1:** the `server.py:19465` platform resolution defect;
   the non-Sleeper client-side gate + explanatory row; cross-client-invariants entries for
   band keys/labels/thresholds/colors.
3. **Operator decisions attached to #1:** C1 vs C2 (bands persist vs 5%-rounded numbers at
   week 6+); placement E (collapsed one-line strip vs full section — and if full, below the
   chart card, not above); two-tier (bands from week 0) vs the conservative single rule
   (nothing until week 6 — fully supported by the evidence if preferred).
4. **Later, in order:** calculator "Season impact" disclosure (week 6+, on-demand CRN-paired
   sim, own sub-flag — `outlook-card-v2.html` frames B/D); deck-top band context line;
   `weekly_digest` band-transition clause; web parity when `league-rankings.html` lights.
5. **Never:** title odds anywhere; the multi-year 2026/27/28 block; per-deck-card deltas;
   matches-inbox odds; extension odds; standalone odds pushes; anything for `pre_draft`
   leagues.

## Where the settled constraints forced a design

Recorded per the dispatch instruction — places the orchestrator would have argued otherwise
absent the calibration verdict:

- **Title odds removal.** Champion odds are the emotional headline dynasty users actually
  ask for (#169's original ask literally names them). Absent the backtest I would have
  argued for a caveated title number; the evidence (3 of 6 leagues worse than guessing, one
  champion above 0.4 predicted in eight tries) makes that indefensible. The record-cell
  design in `outlook-card-v2.html` exists *because* this door is closed.
- **No W-L numbers weeks 0–5.** The standings table was flagged as the most legible,
  highest-upside product for non-technical users — and the bands constraint defers its most
  legible element (the projected record) to week 6. The order-only compromise keeps the
  skeleton visible early; it is genuinely less compelling than a full table would be.
- **Bands from week 0 at all.** With 2 of 6 league-seasons losing to climatology preseason,
  a defensible alternative is showing *nothing* until week 6; the settled two-tier decision
  (bands week 0, numbers week 6) is followed here, and the conservative single-rule variant
  is surfaced as an operator option rather than argued for.

## Open questions for the operator

1. **C1 or C2 at week 6+** — bands persist (safe) vs 5%-rounded playoff % (legible; risk
   call on pooled, non-week-stratified calibration). If C2: make it a server-side
   presentation flag so it reverts without a client build.
2. **Band thresholds** 0.65 / 0.35 — sign off or adjust before they enter
   `cross-client-invariants.md`.
3. **Placement** — collapsed "your outlook" strip (frame E) vs full section; if full,
   confirm moving it BELOW the chart card (the shipped dark code mounts it above, which
   buries the screen's core product).
4. **Two-tier vs single rule** — bands from week 0 (recommended by the calibration doc,
   designed here) vs nothing until week 6 (conservative, equally supported).
5. **Basis interaction** — the outlook endpoint accepts `basis=personal`; should the odds
   section follow the screen's basis toggle (as the dark code does) or pin to consensus?
   Personal-board odds double the sim surface for marginal insight; recommend pinning to
   consensus until asked.
