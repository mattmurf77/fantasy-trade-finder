# #248 — Combined rank bars (V2: ghost tick + delta arrows) — status

**Status:** BUILT (2026-08-05) — on branch `teardown-remediation` (worktree), not merged/pushed.
**Approved design:** Variant **V2** of `mockups/polish-lab-2026-08/combined-rank-bars.html` — my-board bars + consensus ghost tick + ▲/▼ delta chips.
**Code:** `mobile/src/screens/LeagueSummaryScreen.tsx` only. Backend untouched.

## What shipped

One chart now carries both boards on `LeagueRankings`/`LeagueSummary`:

- **Bars** — unchanged position-stacked columns (position hexes preserved per
  `docs/cross-client-invariants.md`), drawn from whichever basis the toggle selects.
- **Ghost tick** — a dashed ice hairline + end-cap dot per column
  (testID `league-summary.tick.<user_id>`) marking the OTHER basis' total for that team,
  on a **shared max scale** across both bases so a tick can never clip off the chart top
  (the league-average line moved to the same shared scale). New invariant recorded in
  `docs/cross-client-invariants.md` ("dashed-ice tick = other-board marker").
- **Delta chips** — signed ▲N (semantic pos-green) / ▼N (neg-red) chip above a column
  (testID `league-summary.delta.<user_id>`) when |my-board rank − consensus rank| ≥ 2
  under the current filters. A fixed-height chip row is reserved on every column while
  the overlay is live so bars stay baseline-aligned.
- **Toggle's new role** — Consensus/My board now swaps which basis draws the BARS
  (ticks always show the other). Labels read "Consensus sorts" / "My board sorts" once
  both boards are loaded and differ; testIDs `league-summary.basis.*` unchanged.
  Redraft chip unchanged (still disabled "(soon)").
- **Captions** — card caption gains "— both boards"; the focus caption and drill-in
  subline state both ranks ("My board rank 7/12 · Consensus rank 2/12" /
  "#7 of 12 (my board) · #2 of 12 (consensus) · 2,470 value"); the hint explains the
  encoding ("Bar height = your board. Dashed line = consensus. Arrows mark a 2+ rank
  swing."). Legend gains a dashed-tick key ("consensus rank" / "my board rank").

## Fetch-shape decision: two parallel queries (endpoint unchanged)

The mock's intro flagged the engineering dependency honestly: today's screen fetched one
basis at a time (`queryKey ['league-power-rankings', leagueId, basis]`). Chosen fix:
**two parallel `useQuery`s against the existing `GET /api/league/power-rankings`**, one
per basis, rather than extending the endpoint to return both bases in one response.
Why:

1. The payload does NOT nearly support a combined response — `compute_power_rankings`
   runs once per basis and every team's roster rows/values/starters are basis-specific,
   so a combined payload would be a new response shape (~2× size) plus client type churn
   and an api-reference change. Not additive enough to justify.
2. The two queries reuse the byte-identical pre-#248 queryKeys, so the react-query
   cache carries over and toggling the basis is instant (no refetch — the data is
   already resident, exactly what #248 wanted).
3. Zero backend diff keeps this build clear of the in-flight `trade_service.py` work
   and needs no backend test run (baseline untouched).

Cost: one extra request per league visit (both cached 60s, refreshed together by
pull-to-refresh and the header refresh control). Payloads are the same per-league
aggregates the screen already fetched on every toggle tap, so total transfer is at
worst what a single Consensus→My board toggle already cost.

The personal query fails quietly for unverified callers (no ticks, consensus renders
normally); toggling to My board surfaces the same verification error copy as before.

## Filter behavior (honest math)

Ticks and deltas recompute per the filtered subset using the **same derivation as the
bars** — `computeSubset` + `activeTotal` run over the *other* payload's own teams,
roster values, and basis-aware derived `starters`. So All/Starters/Bench and the
position pills (incl. Picks) reshape both signals consistently, and the consensus
starters subset is the server-derived consensus-optimal lineup, not an approximation.
One honest guard: if the other payload reports `starters_available: false` (shouldn't
diverge from the bars payload in practice — same server, same league), ticks/deltas
hide for the Starters/Bench subsets rather than fabricate; the unfiltered (All) view
keeps them.

## Fallback: no my-board data

A caller who hasn't ranked gets personal values identical to consensus (personal Elo
starts at the consensus seed), so the two payloads are value-identical. The overlay
detects this (per-team `total_value` equality) and hides ticks, chips, the "sorts"
labels, the "— both boards" caption, and the legend key — rendering exactly the
pre-#248 consensus-only chart (no ticks against themselves).

## #243 slim strip / drill-in

Unchanged mechanics: slim-strip collapse, "Filtered by:" caption, "‹ All teams" back
affordance, shared `subset`/`posFilter` state, mirrored drill-panel controls. The only
focused-state additions are the mock's declutter rule (non-focused ticks/chips hide;
the focused team keeps its tick + chip) and the dual-rank caption/subline.

**Deviation from mock (deliberate):** the mock's focused-state hint shows bespoke
dynamic copy ("▼5 vs consensus — …"). Kept today's hint composition instead — the
dual-rank focus caption + drill subline already carry that information, and the hint
stays consistent between focused/unfocused states.

## Verification

- `cd mobile && npx tsc --noEmit` — clean.
- `backend/tests` not run — backend untouched (route region unmodified).
- Docs updated: `mobile/src/screens/CLAUDE.md` (LeagueSummaryScreen row),
  `docs/cross-client-invariants.md` (dashed-ice tick encoding). `api-reference.md`
  unchanged (no endpoint change).
