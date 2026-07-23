# #169 — League Summary redesign (bar chart + position filter + drill-in)

**Covered feedback IDs:** 169
**Scope shipped:** dynasty near-term slice (bar chart) + the **outlook-odds UI
layer wired behind the DARK `outlook.odds` flag**. The odds layer binds to
`GET /api/league/outlook`; while that modeling backend is dark the flag stays
off, so the layer never renders and the endpoint is never called (404).
**Status:** built + typecheck-clean on branch `teardown-remediation`.
**Approved mockups:** `mockups/outlook-odds/league-summary.html` (dynasty bar
chart) + `mockups/outlook-odds/outlook-card.html` (the amber "Projected"
odds visual language the odds layer adapts).

## What was built

Redesigned `mobile/src/screens/LeagueSummaryScreen.tsx` from a plain ranked
list into the mockup's stacked bar chart:

1. **Vertical stacked bar chart** — each team is a bar row (rank numeral, name +
   You badge, a position-stacked value track, active value + chevron). The
   track is a 16px `--ink-2` well; the fill is a flex row of QB/RB/WR/TE
   segments in the position hexes (data encodings), each sized to its share so
   segments fill the track exactly. Bars scale to the league max; teams sorted
   most→least. Position legend below.
2. **Position filter** — pill row (All + QB/RB/WR/TE), single OR multi select.
   On change the chart re-values to the selected position(s) only and re-sorts
   teams live. Pure client-side transform over the per-team
   `positions[pos].value` the payload already carries — **no refetch, no
   backend change**. Zero-value-under-filter teams show an empty track + "—"
   (honest, never a fabricated bar).
3. **Basis toggle** — Consensus | My board (existing `basis` param) + a disabled
   "Redraft (soon)" chip. The client never requests `basis=redraft` (backend
   501s it).
4. **Team drill-in** — tapping a bar opens the roster overlay grouped
   QB→RB→WR→TE→Other, value-desc within group, reusing the per-team `roster`
   already returned. The overlay has its own position filter that limits the
   shown groups.

## Outlook-odds layer (2026-07-23, flag `outlook.odds` — DARK)

Lit up the playoff/championship-odds view in `LeagueSummaryScreen`, gated behind
the dark `outlook.odds` flag. Sits between the basis toggle and the dynasty bar
chart as a SEPARATE section; the existing chart, position filter, and drill-in
are untouched.

1. **API client** — `getOutlook(leagueId, basis)` in `mobile/src/api/league.ts`
   (mirrors `getPowerRankings`), typed to the exact `GET /api/league/outlook`
   payload (`LeagueOutlookResponse` / `OutlookTeam` / `OutlookMeta` in the same
   file). Percentages are 0..1 fractions; teams arrive pre-sorted by
   `playoff_pct` desc and are rendered in payload order.
2. **Flag gating (truly dark)** — `useFlag('outlook.odds')` drives both the
   `useQuery` `enabled` and the render. The flag is absent from
   `LAUNCHED_FLAG_DEFAULTS` and from `config/features.json`, so it resolves
   false by default: the section does NOT render and `/api/league/outlook` is
   NEVER called (it 404s while the modeling backend is dark). Only when a live
   flag map turns it on do we fetch + render.
3. **UI** — a "Playoff picture" section: per-team rows with the **You** badge
   (`is_you`), record + projected seed, and the two headline odds (playoff% and
   title%) as figure + thin amber meter. Reuses the screen's Chalkline
   primitives (`TickLabel`, `Badge`, `type.data`, track/fill bars).
4. **Preseason/beta labeling (load-bearing)** — every render carries a
   **"Projected · preseason · beta"** ribbon (composed from `meta.is_preseason`
   / `meta.beta`; both true today) plus a source caption mapping
   `meta.strength_source` → friendly text (`roster_value` → "Preseason
   roster-value projection", `trailing_scores` → "Based on recent scoring",
   `blended` → "Blended projection"; unknown keys → "Projected from team
   strength"). Amber (`semantic.warn`) is the projection signal throughout, per
   `outlook-card.html`. No bare authoritative percentage is ever shown.
5. **testIDs** — `league-summary.odds.section` · `.beta-ribbon` · `.source` ·
   `.row.<roster_id>` (see the components/CLAUDE.md tranche).

**Mockup-vs-payload reconciliation:** the odds visual language comes from
`outlook-card.html` (a trade card), which frames odds as before/after DELTAS
(record ▲+2, playoff +11, multi-year 2026/27/28 championship odds). The
`/api/league/outlook` payload carries no deltas and no multi-year series — it's
a single per-team snapshot (`playoff_pct`/`bye_pct`/`title_pct`/
`projected_wins`/`projected_seed`). In the League Summary (no trade context)
the delta framing doesn't apply, so the odds render as absolute per-team
figures; the delta/multi-year treatments are omitted rather than fabricated.

## Backend

**No backend change.** `GET /api/league/power-rankings` already returns, per
team, `positions[pos].value` (the position stack) and the value-sorted
`roster`, which is everything the filter/re-sort/drill-in need.
`basis=redraft` stays 501 (`backend/power_rankings.py` unchanged).

## Files

Bar-chart redesign (earlier):
- `mobile/src/screens/LeagueSummaryScreen.tsx` — redesigned (bar chart,
  position filter, drill-in filter; reuses existing `BasisChip`, `groupRoster`,
  PlayerCard overlay)
- `docs/design/components.md` — added "League rankings — stacked bar chart" spec

Outlook-odds layer (2026-07-23):
- `mobile/src/api/league.ts` — `getOutlook()` + `LeagueOutlookResponse` /
  `OutlookTeam` / `OutlookMeta` / `OutlookBasis` types bound to the exact
  `GET /api/league/outlook` payload
- `mobile/src/screens/LeagueSummaryScreen.tsx` — gated `OddsSection` /
  `OddsRow` / `OddStat` between the basis toggle and the dynasty chart; flag
  hook + gated `useQuery`
- `mobile/src/components/CLAUDE.md` — new testID tranches (#169 chart + odds)
- `docs/feedback/items/169-outlook-league-summary/status.md` — this file

## New testIDs

Bar chart:
- `league-summary.posfilter.<all|qb|rb|wr|te>` — chart position filter
- `league-summary.roster-posfilter.<all|qb|rb|wr|te>` — drill-in position filter

Outlook odds (flag `outlook.odds`, dark):
- `league-summary.odds.section` — gated container
- `league-summary.odds.beta-ribbon` — "Projected · preseason · beta" label
- `league-summary.odds.source` — strength-source caption
- `league-summary.odds.row.<roster_id>` — per-team projected odds row

(existing `league-summary.basis.*`, `league-summary.team.<user_id>`,
`league-summary.roster-close` unchanged.)

## Verification

- `cd mobile && npx tsc --noEmit` → exit 0, clean (typechecked via the main
  repo's `mobile/node_modules`; the worktree has no local install).
- No backend touched → no pytest run needed.
- Confirmed dark: `outlook.odds` is absent from `LAUNCHED_FLAG_DEFAULTS` and
  `config/features.json`, so `useFlag('outlook.odds')` is false by default —
  the odds section does not render and `/api/league/outlook` is never called.

## Deferred / parked

Now BUILT (backend pipeline + mobile UI), dark behind `outlook.odds`. Still open:
- **Empirical calibration** of the roster-value→weekly-points heuristic — tune
  via the offline backtest scaffold (current values are defaults, not fit).
- **Live Sleeper validation** — future-week `matchup_id` pairing is assumed, not
  validated (falls back to random re-pairing). Verify before flipping the flag on.
- **Real projection source** — swap `RosterValueStrength` for Sleeper projections
  or an own model in-season (Phase 2 seam: `FTF_OUTLOOK_STRENGTH_SOURCE` + 1 class).
- **Redraft-value tab** — `basis=redraft` stays a "(soon)" chip until a redraft
  VALUE source lands (dynasty-only today).

## As-built — odds pipeline backend (2026-07-23)

The previously-deferred "Outlook odds" layer now has a **backend pipeline** +
mobile UI, both dark behind `outlook.odds`. The payload contract is fixed in
`odds-pipeline-lld.md`; source research in `projection-source-research.md`.

**Package `backend/outlook/`** — five swappable phases, each a `typing.Protocol`
with concrete impls registered in a per-phase lookup; `pipeline.py` wires them
from config via factories (nothing downstream imports a concrete provider):

- `league_state.py` — Phase 1 `LeagueStateProvider`. `SleeperLeagueState`
  ingests `/league/{id}` + `/rosters` + `/users` + `/matchups/{week}` via the
  shared `server._sleeper_get` (injected). `mfl`/`fleaflicker`/`espn` are
  registered NotImplemented stubs.
- `strength.py` — Phase 2 `StrengthProvider` (**the key swap seam**).
  `RosterValueStrength` (preseason default, works at `completed_weeks==0`),
  `TrailingScoresStrength` (in-season, requires ≥K weeks), `BlendedStrength`.
  `SleeperProjectionsStrength`/`OwnModelStrength` are registered stubs. Source
  via env `FTF_OUTLOOK_STRENGTH_SOURCE` (default `auto`).
- `simulator.py` — Phase 3 pure `simulate()`. Deterministically seeded from
  `stable_hash(league_id) ^ outlook_seed` (SHA-256, not builtin `hash()` which
  is process-salted). No clock, no global random. N=`outlook_sim_count` (10000).
- `playoff_format.py` — Phase 4 `StandardFormat`: seed by record, `points_for`
  tiebreak, top-seed byes, reseeding single-elimination bracket.
- `serialize.py` — Phase 5 fixed payload; sets `meta.is_preseason`/`meta.beta`.

**Endpoint** `GET /api/league/outlook?league_id=&basis=` (`backend/server.py`),
**dark behind flag `outlook.odds`** (default false — 404 when off).

**Config:** `outlook.odds` flag (features.json + feature_flags.py + release
fixture); `model_config` `outlook_*` numeric knobs; `FTF_OUTLOOK_STRENGTH_SOURCE`
env string.

**Tests:** `backend/tests/test_outlook_odds.py` (19 pass + 1 skipped backtest
scaffold). Full backend suite 998 passed / 1 skipped (was 979).

**Flagged for operator review:** the roster-value→weekly-points calibration
(`outlook_mean_points`/`outlook_points_per_value_sd`/`outlook_sigma_default`)
is a documented heuristic, not empirically fit — tune via the offline backtest
scaffold. Sleeper future-week `matchup_id` pairing stability is assumed, not
validated against live 2025 data (falls back to random re-pairing if absent).
