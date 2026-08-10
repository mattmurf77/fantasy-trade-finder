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

## Calibration verdict (2026-08-09) — READ BEFORE FLIPPING THE FLAG

The engine was backtested against 6 real captured Sleeper seasons of the
operator's own leagues. Full method, numbers and verdict:
**[calibration-report-2026-08-09.md](calibration-report-2026-08-09.md)**.

- **Playoff odds: validated.** Brier 0.1113 vs climatology 0.2500 — **+55.5 %
  skill, 90 % CI [+44.5 %, +65.9 %]**, beats standings-extrapolation too, and
  improves monotonically from week 3 to week 12.
- **Title odds: NOT validated.** +5.1 % skill, CI **[−13.2 %, +22.3 %] includes
  zero**; at week 3 it is *worse* than a constant 1/12. Six champion events is
  not a validation.
- ~~**Preseason `roster_value` source: not backtestable** (no historical value
  board)~~ **→ BACKTESTED 2026-08-09** (dated DynastyProcess boards do exist —
  see **[dated-values-revalidation-2026-08-09.md](dated-values-revalidation-2026-08-09.md)**):
  playoff Brier **0.1959** vs climatology 0.2500 = **+21.6 %**, 90 % CI
  **[+4.1 %, +38.3 %]** (excludes 0) — real but weak, **over-confident at the
  extremes** (95 % → 75 % realized), beaten by climatology in **2 of 6**
  league-seasons, and **statistically indistinguishable from the week-3
  model**. Preseason **title** odds: **no skill** (+3.1 %, CI [−17.7, +24.9]).
  **Recommendation: render playoff odds only, banded rather than as a precise
  percentage, title odds withheld, BUG-1 fixed first.** A
  Sleeper-projections cross-check still disagrees with the roster-value prior
  on half the playoff field in the superflex league.
- **BUG-5 (moderate, pricing half open) — 2026-08-09:** `RosterValueStrength`
  prices lineups with a board that carries **QB/RB/WR/TE only**. The operator's
  **FFv3** league starts 8 IDP/K slots out of 15, so **53 % of its starting
  slots price at 0.0**, covering **~33 % of the points those teams scored** —
  and FFv3 is **4 of the 6 backtested league-seasons**. The preseason numbers
  above were therefore measured on an **offensive-core-only** basis for those
  four seasons. *They are arithmetically unaffected* (the gap is identical for
  every team in a league, so it cancels in the z-score) — but the revalidation
  report's "starting-slot coverage 100 %" row counted skill slots only and is
  corrected. **Fixed:** IDP slot eligibility in `select_starting_lineup()`
  (measured 0 of 72 predictions moved). **Not fixed:** the pricing. No
  license-clean dynasty IDP value board exists (DynastyProcess, nflverse,
  FantasyCalc, KTC, Sleeper `search_rank` all checked and rejected — see
  [idp-pricing-2026-08-09.md](idp-pricing-2026-08-09.md) §4.1), and both
  candidate workarounds were backtested and lost (league-mean fallback
  Δ Brier +0.0005; coverage attenuation −0.0019, CI [−0.0167, +0.0070]).
  **Open follow-up before lighting the flag for any IDP league:** wire
  `strength.lineup_pricing()` into the payload `meta` (owned by
  `backend/outlook/serialize.py`) so the UI can say *"based on your offensive
  starters"* instead of showing an unqualified number.
- **BUG-1 (severe, open):** `settings.league_average_match` (median match) is
  ignored — the operator's Lakeview league has it ON in the live 2026 season,
  which makes `projected_wins` read 22.29 in a 14-week season. Tracked by a
  strict `xfail` in `backend/tests/test_outlook_calibration.py`; see also
  `living-memory/GOTCHAS.md` G-024.
- **Resolved:** Sleeper *does* publish future-week `matchup_id` pairings once a
  league is scheduled (only `pre_draft` leagues lack them); the random-pairing
  fallback costs ~5 % of playoff Brier.

**Recommendation: do not flip `outlook.odds` until BUG-1 is fixed**; then ship
playoff odds only, gated to `completed_weeks >= 3` and `status != "pre_draft"`.

**Flagged for operator review:** the roster-value→weekly-points calibration
(`outlook_mean_points`/`outlook_points_per_value_sd`/`outlook_sigma_default`)
is a documented heuristic, not empirically fit — tune via the offline backtest
scaffold. Sleeper future-week `matchup_id` pairing stability is assumed, not
validated against live 2025 data (falls back to random re-pairing if absent).

## Productionization (2026-08-09) — hardened, still dark

The surface was productionized so that lighting it is a **one-touch flip**.
Nothing here lights anything: `outlook.odds` is false in every touch, the route
still 404s, and the mobile section still does not render or fetch. A parallel
calibration effort owns the go/no-go on the numbers themselves.

### 1. Sleeper fan-out caching

`docs/integrations/sleeper.md` had `/api/league/outlook` as the worst uncached
surface in the app: Phase 1 walks EVERY regular-season week (`matchups/{week}`,
up to 14 upstream calls) live on every request. Fixed in `backend/server.py` —
`_outlook_sleeper_fetch()`, which the route now passes as `build_league_state`'s
`fetch=`. **`backend/outlook/` is untouched** (the injected-fetch seam was
already there), and every cache MISS still routes through `_sleeper_get`, the
instrumented egress chokepoint — so the cache shows up in apihealth as
`league.matchups` `api_call` events that stop happening.

Tiered by the grain of the data, keyed `(league_id, season, week)`:

| Week | Rule | TTL |
|---|---|---|
| below the scored high-water mark | a later week has scored ⇒ rows are immutable | **none** |
| at the high-water mark (or week 1 preseason) | the live/in-progress week | 900 s |
| above it | not yet played — pairings only | 3,600 s |

The high-water mark is learned from the fetched rows themselves (a week with
any nonzero `points`), so no new upstream endpoint (`/state/nfl`) was needed;
promotion into the settled tier is order-independent. `season` comes from the
league-meta read the provider already makes first, and a week is **never**
cached without one — a seasonless key could serve last year's scores.

Idiom: the per-key `(timestamp, value)` dict of `_SUGGESTED_ORDER_CACHE` /
`_FA_LEAGUE_META_CACHE`, **not** `espn_service._xwalk_cache` (that caches ONE
global blob on a TTL; this needs per league+season+week keys). In-process, like
every other cache in this codebase: completed-week rows are cheaply re-derivable
from Sleeper, so a DB table would buy durability across restarts at the cost of
schema + a data-dictionary entry the payload doesn't need. Both tiers are
bounded at 250 entries (matchup rows carry per-player point maps).

`rosters` / `users` / league meta stay **live on purpose** — `rosters` carries
the W/L/points-for standings the odds are computed FROM, and a stale standing is
a wrong answer, not a slow one. Steady state per league: 3 live reads, one
short-TTL week call, a few hourly schedule calls, and exactly one upstream call
per newly-completed week — free forever after.

### 2. Flag registration — verified, four touches, dark

`outlook.odds` is registered in all four places at **false**: `FLAG_KEYS` +
`DEFAULT_FLAGS` (`backend/feature_flags.py`), `config/features.json`,
`backend/tests/fixtures/flags/release.json`, and `docs/config-reference.md`. It
is deliberately **absent** from `backend/tests/fixtures/flags/all-on.json` (a
flag sweep must not light an uncalibrated surface) and from mobile's
`LAUNCHED_FLAG_DEFAULTS`. The route's gate is the LLD's: `is_enabled` false ⇒
`404 {"error": "not_found"}`, checked before session resolution and before any
Sleeper call. `backend/tests/test_outlook_route_cache.py` holds the ships-off
test (real flag map, nothing patched: 404 + zero Sleeper calls) and the mirror
assertions.

### 3. Contract reconciliation (mobile ↔ `serialize.py`)

The odds layer was typed in July; `LeagueSummaryScreen` has been rebuilt since
(#277 tier labels, #281 key dedupe, #279 aggregate labels). Re-verified:

- **Compiles into the current screen** — `OddsSection` still mounts between the
  basis toggle and the chart card, `useFlag`-gated on both the render and the
  `useQuery`'s `enabled`. `npx tsc --noEmit` exit 0.
- **Field-for-field vs the payload** — two mismatches found and fixed on the
  MOBILE side (the wire is the authority): `scoring_format` and
  `strength.{mu,sigma}` are nullable in `serialize.py` but were typed
  non-nullable in `mobile/src/api/league.ts`. Everything else matched exactly.
  Now pinned by a test that parses the TS interfaces and compares them to a
  live payload.
- **Preseason rules honored on both sides** — backend sets `meta.is_preseason
  = (completed_weeks == 0)` and (2026-08-10, see below) `meta.beta =
  (completed_weeks < 6)` as an INDEPENDENT signal; mobile composes "Projected
  · preseason · beta" from those two booleans and always renders the
  `strength_source` caption. The caption map covers every *selectable* provider
  (`roster_value`, `trailing_scores`, `blended`); the registered stubs fall
  through to the generic caption by design. Both are now test-pinned.
- **RESOLVED 2026-08-10** (was: "Open question for the lighting decision —
  `meta.beta` is derived from `is_preseason`, so the FIRST in-season payload
  drops the 'beta' word while the model is still uncalibrated"). Fixed in
  `backend/outlook/serialize.py`: `beta` is now an INDEPENDENT signal —
  `completed_weeks < 6` — not an alias of `is_preseason` (`completed_weeks ==
  0`). Threshold justified by the 2026-08-09 revalidation: preseason playoff
  Brier (0.1959) is statistically indistinguishable from the week-3 in-season
  model (0.1972); the engine only pulls clearly ahead at week 6 (0.120) and is
  well-calibrated by week 12 (0.055) — see
  [calibration-report-2026-08-09.md §3](calibration-report-2026-08-09.md#3-tier-1--backtest-against-reality).
  Both fields still ship on every payload; the mobile ribbon composition
  (`betaRibbonLabel`) and its "Projected · preseason · beta" wording are
  UNCHANGED — this is a backend value-semantics fix only, not a UI change.
  Tests: `test_beta_stays_true_through_week_5` / `test_beta_clears_at_week_6` /
  `test_is_preseason_and_beta_are_independent_signals` in
  `backend/tests/test_outlook_odds.py`.

### 4. Lighting procedure — RECOMMENDED: plain flag flip

**Not executed.** Run only after the calibration verdict passes and the
live-Sleeper `matchup_id` pairing check clears (both still open above).

**Recommendation: a plain flag flip, not the tester-allowlist experiment route
(#279 / `onboarding_v2_rollout`).** Reasoning:

- The flag is already the *complete* gate on both sides — route 404 AND the
  client's render AND the client's fetch. Lighting genuinely is one value. The
  experiment route would require NEW code on both sides: the route's global
  `is_enabled` check would have to become a per-unit
  `experiments.variant_for(...)` call, and mobile's `useFlag('outlook.odds')`
  would have to become a variant read — `/api/feature-flags` serves a GLOBAL
  `flags` map plus a SEPARATE `experiments` map, so an experiment cannot overlay
  a flag key. Building that is the opposite of "the only remaining step is a
  flip".
- #279 reached for the experiments engine because that surface's route was
  **already live for everyone**, so per-user targeting was the only way to
  isolate a cohort. Here the whole surface is dark, so the flag already provides
  the isolation; a second mechanism buys only cohort *granularity*.
- Blast radius is now bounded: the fan-out is cached (above), so lighting for
  every tester costs ~7 Sleeper calls per league on first hit and ~1 per 15 min
  after — this was the main argument for a narrow cohort, and it is gone.
- Honesty is not cohort-dependent: the beta ribbon + source caption ship with
  every render, so a wider audience is never shown a bare authoritative number.

**Procedure (operator, prod):**

1. Preconditions: calibration verdict green; future-week `matchup_id` pairing
   validated against a live league; a TestFlight build carrying the odds layer
   is installed (already merged — no new client code is needed to light).
2. **Soak (instantly revertible, no deploy):** in the Render dashboard set
   `FTF_FLAGS={"outlook.odds": true}`. Env wins over `config/features.json`
   (`_compute_flags`: defaults → features.json → `FTF_FLAGS`). Then restart, or
   `curl -X POST https://fantasy-trade-finder.onrender.com/api/feature-flags/reload -H "X-Cron-Secret: $CRON_SECRET"`.
3. Verify: `GET /api/league/outlook?league_id=<id>` returns 200 (not 404); the
   League tab shows "Playoff picture" with the "Projected · preseason · beta"
   ribbon and the source caption; apihealth shows `league.matchups` `api_call`
   volume at roughly one burst per league rather than one burst per view.
4. **Make it durable:** flip `"outlook.odds": true` in `config/features.json`
   (and the release fixture, to keep the mirror honest), merge → Render deploys,
   then remove the `FTF_FLAGS` override so there is one source of truth.
5. **Revert at any point:** delete the env var (or revert the one-line commit)
   and reload. The route 404s again and the client hides the section on its next
   flag refresh (boot + ≥30-min foreground refetch) — no client build involved.

If the operator would rather expose it to themselves only first, that is the
experiment route and it is a *build*, not a flip: add the `variant_for` check to
the route, add a client-side variant read, and create an account-unit experiment
keyed `outlook_odds_rollout` with `{"is_tester_allowlist": true}` targeting and
0/10000 weights, exactly as
`docs/feedback/items/279-aggregate-tier-labels/status.md` documents.

### Files (this pass)

- `backend/server.py` — `_outlook_sleeper_fetch()` + the tiered week cache; the
  route now injects it
- `backend/tests/test_outlook_route_cache.py` — new: cache behavior,
  instrumentation visibility, flag mirror + ships-off, wire contract
- `mobile/src/api/league.ts` — nullable `scoring_format` / `strength.{mu,sigma}`
- `docs/integrations/sleeper.md` — §5.4 rewritten (was "uncached"), endpoint
  table row 10
- `docs/api-reference.md`, `docs/config-reference.md` — caching + flag status

## Bye-week μ multiplier — evaluated, NO-SHIP (2026-08-09)

Operator directive: make the flat single-μ strength model bye-aware, considering
BOTH sides of a matchup, since Sleeper's player dump carries no bye field (byes
have to be derived from an nflverse schedule CSV). Built and validated as a
fully evaluated variant — full method, backtest, mechanism check, and verdict:
**[bye-week-multiplier-2026-08-09.md](bye-week-multiplier-2026-08-09.md)**.

- **Verdict: NO-SHIP.** At every tested `outlook_bye_multiplier_scale`
  (0.22/0.40/0.60/1.00) the multiplier is flat-to-worse on playoff Brier
  against the same 6-league/4-as-of-week backtest the shipped engine was
  validated against; at the shipped default (1.0) it's **+8.82% worse**
  (cluster-bootstrap 90% CI **[−0.0011, +0.0206]**, includes 0 — statistically
  null, but never positive at any scale or as-of week tested).
- **Why:** a mechanism check against 1,008 real team-weeks shows real fantasy
  managers absorb ~78% of a bye's value loss via bench swaps that a
  fixed-lineup multiplier can't model — empirical slope **−0.222** (90% CI
  **[−0.305, −0.138]**) vs. the multiplier's naive **−1.000** assumption.
- **Nothing live changed.** `bye_multiplier.py` is not imported by
  `pipeline.py`/`server.py`; `model_config.outlook_bye_multiplier_enabled`
  exists (default `0.0`) but is not read anywhere yet.
- **Kept regardless of the verdict:** `backend/outlook/bye_weeks.py` — tested,
  CC-BY-attributed nflverse schedule → bye-week ingestion, reusable by any
  future weekly-points projection source (`OwnModelStrength` stub).

## BUG-3 fix + honest `beta` signal (2026-08-10) — still dark

Two calibration-report follow-ups closed. `outlook.odds` untouched (still
false everywhere); no flag/config change; no mobile UI/behavior change.

**BUG-3 — `settings.playoff_seed_type` now modeled.** Dated FIXED note with
full method in
[calibration-report-2026-08-09.md §7](calibration-report-2026-08-09.md#7-bugs-found).
Summary: `backend/outlook/playoff_format.py` now branches on the Sleeper
setting — `0` → fixed/standard bracket (no re-seeding, empirically proven
against 3 divergent instances across the 4 completed `ffv3-*` fixture
seasons), `1` → reseed (today's unconditional pre-fix behavior, preserved
exactly; documented but not independently divergence-proven against the
fixture set), anything else → explicit LOGGED fallback to reseed
(`_resolve_seed_type`). Threaded from Sleeper's league-meta response (already
fetched by Phase 1) via a `captured` side-channel in
`backend/server.py::_outlook_sleeper_fetch()` — zero extra network calls, and
`backend/outlook/league_state.py` was NOT touched (a sibling agent owns
BUG-1/median-match in that file concurrently). `pipeline.run_outlook` gained
an optional `playoff_seed_type` kwarg, falling back to `getattr(state,
"playoff_seed_type", None)` — same precedent as the existing `scoring_format`
attribute-attach pattern.

**`meta.beta` aliasing — fixed.** Was: a plain alias of `meta.is_preseason`
(`completed_weeks == 0`), so the "beta" label vanished at week 1 while the
model was still uncalibrated (flagged as an open question above). Now:
`backend/outlook/serialize.py` computes `beta = completed_weeks < 6`,
independent of `is_preseason`. Threshold justified by the 2026-08-09
revalidation (preseason Brier 0.1959 ≈ week-3 Brier 0.1972, statistically
indistinguishable; the engine only pulls clearly ahead at week 6 — 0.120).
`is_preseason` still clears at week 1 as before; the two fields now
genuinely diverge in the week 1-5 window, which is the whole point.

**Not done:** `scripts/outlook_calibration_backtest.py` was not updated to
pass `playoff_seed_type` into its `get_playoff_format` calls, so a re-run of
the full calibration backtest still scores the pre-fix (always-reseed)
bracket simulation. Recommended before the next calibration revalidation.

**Files:** `backend/outlook/playoff_format.py`, `backend/outlook/serialize.py`
(owned this pass), `backend/outlook/pipeline.py`, `backend/server.py` (thin
wiring only — `league_state.py`/`simulator.py`/`strength.py` untouched, per
the sibling-agent file split), `backend/tests/test_outlook_playoff_seed_type.py`
(new), `backend/tests/test_outlook_odds.py`, `backend/tests/test_outlook_route_cache.py`,
`docs/api-reference.md`.
