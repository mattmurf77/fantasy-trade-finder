# #207 — Draft-aware current-year pick labels in rank sets — status

**Status: built (backend, flag `picks.rank_year_labels` ON; zero mobile
changes)** · 2026-08-05 · branch `worktree-agent-afae520a937d45e74`
(off `teardown-remediation`)

## Operator report

> "Detect whether a league's rookie draft has happened based on whether
> rookies are on rosters (or ideally through an explicit data point from the
> platforms) and if it hasn't, add actual 2026 draft picks into the rank sets.
> Hide them if rookie drafts have happened."

Built to [plan.md](plan.md) (Option A — **relabel, don't add/remove**), with
[research-codebase.md](research-codebase.md) and
[research-platforms.md](research-platforms.md) as grounding.

## What shipped

**1. `backend/draft_status.py` — the detector.** Dependency-free: callers
fetch, this module decides, so the whole conflict matrix is unit-testable
without a network or a DB. Returns `DraftStatus(status, confidence, source,
evidence)`.

**2. `players.rookie_year`.** Sleeper's `metadata.rookie_year` — the exact
"class of YYYY" field — is now kept by `sync_players` (additive column +
`_migrate_db` entry). Only a plausible 4-digit year survives: the dump serves
the bogus `"0"` for ~5 % of `years_exp == 0` players and omits the field
entirely for camp bodies. `years_exp` remains a **fallback only**, because it
counts *accrued* seasons (a 2023 UDFA with two practice-squad years reads
`years_exp == 1`) — it is not a class field.

**3. League-row cache + refresh.** `leagues.draft_status` /
`draft_status_confidence` / `draft_status_checked_at`, written by
`server._refresh_league_draft_status`, wired into (a) the existing
session-init background daemon, right after the #158/#228 owned-pick sync,
and (b) a new sweep in `/api/cron/hourly-tick` (`draft_status_checked` in
the response body). Cheap-skip TTLs are **asymmetric**, per the plan: an
undrafted league flips exactly once so it is re-probed every **3 h**; a
drafted league never un-drafts inside a season so it waits **12 h**;
`unknown` waits **1 h**. The hourly sweep is bounded to `_DRAFT_STATUS_SWEEP_BUDGET` = 50 refreshes per tick over a never-checked-first, then stalest-first queue, so it rotates instead of turning a cron request into a multi-minute job. `checked_at` is stamped even for `unknown` so a
persistently flaking league backs off instead of being re-probed every tick.

**4. `mfl_service.fetch_draft_results`** — the `TYPE=draftResults` export
(zero-auth, verified). This upgrades MFL from #228's "documented degradation,
heuristic-only" position to **authoritative**.

**5. Serialization relabel.** `GET /api/rankings` and `GET /api/trio` — the
only two pick-rung serialization sites in the app (see "Serialization sites"
below). Rung ids, universal-pool membership, board `elo` and `rank` are
untouched.

## Detection matrix

| # | Platform | Signal | Verdict | Confidence | Source |
|---|---|---|---|---|---|
| 1 | Sleeper | rookie-shaped current-season draft `complete` **+ `last_picked` set** | `drafted` | high | `sleeper_draft_status` |
| 1a | Sleeper | …same, but rosters show **zero** rookies | `drafted` | **medium** (`anomaly: no_rookies_rostered`) | `sleeper_draft_status` |
| 1b | Sleeper | `complete` with `last_picked` null (flipped, zero picks made) | fall through to heuristic | — | — |
| 2 | Sleeper | rookie-shaped `pre_draft`/`drafting`, rosters show no rookie class | `not_drafted` | high | `sleeper_draft_status` |
| 2b | Sleeper | rookie-shaped `pre_draft`/`drafting`, **rosters show a full rookie class** | `drafted` | medium (`veto: rosters_show_rookie_class`) | `rosters_heuristic` |
| 3 | Sleeper | drafts read `[]` (flake **or** no draft object — indistinguishable) | heuristic, else `unknown` | medium / low | — |
| 3b | Sleeper | only a **startup-shaped** (≥15-round) current-season draft, even `complete` | heuristic, else `unknown` | medium / low | — |
| 4 | MFL | `made == total` on a rookie-sized grid (≤8 rounds) | `drafted` | high | `mfl_draft_results` |
| 5 | MFL | `0 ≤ made < total` (pre-draft or in progress — unmade picks still exist) | `not_drafted` | high | `mfl_draft_results` |
| 5b | MFL | startup-sized grid (`total/franchises > 8`), or export unavailable | heuristic, else `unknown` | medium / low | — |
| 6 | ESPN / Fleaflicker / other | — | heuristic, else `unknown` | medium / low | `rosters_heuristic` |
| 7 | any | ≥ `N` distinct rookies across ≥ `ceil(N/2)` teams | `drafted` | **medium** (never higher) | `rosters_heuristic` |
| 8 | any | exactly 0 classifiable rookies, small unknown-id tail | `not_drafted` | medium | `rosters_heuristic` |
| 9 | any | 0 rookies but ≥ `N` unclassifiable rostered ids (stale player table) | `unknown` | low | `rosters_heuristic` |
| 10 | any | nothing usable | `unknown` | low | `none` |

Rookie shape is decided by **round count**, never `settings.player_type`
(verified 0 even on a rookies-only draft): ≤8 rounds = rookie, ≥15 = startup,
in between = can't tell (treated as possibly-rookie).

Rookie test: `rookie_year == league season`, else
`years_exp == 0 AND team IS NOT NULL` (the team requirement drops the
teamless pre-NFL-draft prospect tail that would otherwise read as rookies
every January).

### Conflict rules
1. **Platform `complete` + rosters show no rookies** → platform wins, but the
   combination is near-impossible (usually stale player data or a dropped
   crosswalk) → downgraded to `medium` and tagged `anomaly`.
2. **Platform `pre_draft` + full rookie class rostered** → **rosters win**
   (off-platform draft, imported league, deleted draft object). This is the
   case a `status`-only rule gets wrong.
3. **Rosters unavailable** → the platform signal stands alone; the detector
   abstains rather than manufacturing a verdict.

## Fail-safe

`draft_status.current_year_picks_visible()` returns True for **everything
except a positive `drafted`** — `unknown`, `not_drafted`, a low-confidence
read and a never-checked league all keep current-year picks visible.
Confidence is recorded for diagnosis but gates nothing on this surface.

Rationale (research §5.3, and the same asymmetry #228 chose): a phantom
current-year pick is a *visible, self-correcting* error — it is literally
what got reported in #228. A silently hidden real asset produces **no
artifact at all**, and in the Feb–Aug window rookie picks are the most-traded
currency in dynasty; silent wrongness that can't be falsified is the worse
failure for a recommendation engine.

## What the user sees

| Active league's draft status | Rung label | `pick_value` |
|---|---|---|
| `not_drafted` / `unknown` / never checked | `"2026 Early 1st"` (the league's own season) | unchanged — `years_out=0` is an exact no-op |
| `drafted` | `"2027 Early 1st"` | one year of the existing 0.85 discount, applied in **value** space |
| flag off | `"Early 1st Round Pick"` | unchanged |

The value discount uses the same `elo_to_value → ×0.85 → value_to_elo`
round-trip `_owned_pick_assets` does, so a relabelled 2027 rung prices like
the owned 2027 pick of that round (`pick_pool_value(r, 1)`), to `pick_value`'s
1-decimal rounding.

**The operator's "hide the 2026 picks once drafted" is satisfied:** after the
draft, no 2026 pick exists anywhere — the rungs mean 2027.

## Deliberate non-changes (scope guard)

- **`build_universal_pool` membership and rung ids are untouched.** The pool
  is process-global and league-agnostic; filtering there would apply one
  league's status to every user in the process (landmine L1). Stable ids mean
  zero migration of saved boards and zero pool-shape test churn.
- **Board `elo` and `rank` are untouched.** Relabelling is display + value
  only, so a user's tier drags and `users.tier_overrides` survive intact and
  a mixed drafted/undrafted-league user keeps ONE coherent board (landmine
  L2). Two leagues can show different year text for the same rung id — which
  is the honest semantic.
- **Every `load_draft_picks` consumer** (trade-engine owned-pick injection,
  calculator, `/api/league/picks`, LeagueSummary picks segment, power
  rankings) is already correct post-#228 and was not touched.
- **#228's own exclusion rule is unchanged.** #207 *reuses* its
  `_fetch_sleeper_drafts` fetcher rather than duplicating it, but deliberately
  does not re-point #228's `exclude_seasons` logic at the new detector —
  that would change shipped owned-pick behavior, which is outside this item.
  Folding them together is the natural follow-up.
- **`/api/trade/values` is not relabelled** — it is public, sessionless and
  ETag-cached, so it has no league in scope. Same for
  `/api/trade/evaluate`'s `gap.pick_equivalent.label`.
- **Slot-level picks (1.01 vs 1.12) remain out of scope** — no value axis and
  no slot data source exists (research §5.3).
- **`league.rookie_board_entry`** is a first-year *player* browser, unrelated.

## ESPN caveat

ESPN's `view=mDraftDetail` (`draftDetail.drafted` / `.inProgress`) is
documented by multiple independent write-ups but was **not verifiable** — no
public ESPN league id was available; random ids return `GENERAL_NOT_FOUND`
and private ones return "not authorized". Nothing here is built on it: ESPN
is **heuristic-only**, and its verdict tops out at `medium`. Even if it were
wired, ESPN's `drafted` refers to the league's *annual* draft for that
`seasonId` — the annual-draft ↔ rookie-draft mapping in an ESPN "dynasty"
league is a convention, not a data guarantee. ESPN also stores no pick
ownership in FTF at all, so the blast radius is limited to rank-set labels.
Fleaflicker's `FetchLeagueDraftBoard` is likewise unverified → heuristic-only.
Verification plan if either is ever adopted: link one real league and diff the
payload before/after a draft, same live-smoke discipline the ESPN plan
already requires.

## Known seams (accepted)

- **MFL staleness persists for owned picks.** `draftResults` makes the
  *check* possible, but the engine still reads the `futureDraftPicks` copy
  stored at link time (`leagues.platform_future_picks`), so an MFL league
  linked before its draft keeps a stale year until re-import (#228 §MFL).
  #207's rank-set labels are unaffected — they read the live verdict.
- **Rankings paste-import** matches against pool names, which stay
  `"Early 1st Round Pick"`. Pasting the new displayed string won't match a
  rung; pasting the old one still does. External ranking lists never contain
  our generic rung names verbatim either way.
- **Tiers-board search** (`TiersScreen` name filter) matches the served
  label, so searching "round pick" stops finding rungs while the flag is on;
  "early 1st" and "2026" now do.

## Files

- `backend/draft_status.py` — **new**: detector, confidence model, conflict
  rules, fail-safe
- `backend/pick_values.py` — `parse_generic_pick_id`, `year_pick_label`,
  `discount_pick_value`
- `backend/database.py` — `players.rookie_year` + `leagues.draft_status*`
  columns and migrations; `sync_players` keeps `metadata.rookie_year`;
  `load_rookie_player_ids`, `count_known_player_ids`,
  `set_league_draft_status`, `get_league_draft_context`,
  `load_league_ids_for_draft_status_refresh`
- `backend/server.py` — `_refresh_league_draft_status` +
  `_detect_league_draft_status` + `_rosters_rookie_verdict` +
  `_draft_status_is_fresh`; the `_cached_draft_context` /
  `_pick_rung_year_context` / `_apply_pick_rung_year_labels` read path; wiring
  into the session-init daemon and `/api/cron/hourly-tick`
- `backend/mfl_service.py` — `fetch_draft_results`
- `backend/feature_flags.py`, `config/features.json`,
  `backend/tests/fixtures/flags/release.json` — `picks.rank_year_labels`
  (ON; the release.json mirror is test-enforced)
- Docs: `data-dictionary.md`, `api-reference.md`, `config-reference.md`,
  `glossary.md`, `architecture.md`, `cross-client-invariants.md`

### Serialization sites touched

`player_to_dict` / `ranked_player_to_dict` have exactly 6 call sites; only two
serve pool assets to a rank surface:

| Site | Touched | Why |
|---|---|---|
| `/api/rankings` (`server.py`, `ranked_player_to_dict`) | **yes** | Tiers, Quick Set, Quick Rank, Manual Ranks, web board, Pick Anchors all read it |
| `/api/trio` (`player_to_dict` ×3) | **yes** | rungs appear in matchups |
| trade-card deck (`trade_card_to_dict`) | no | serves owned picks, not rungs |
| asset-ideas give/receive/asset | no | same |
| `session/init` + demo `user_roster` | no | real players only |

## Mobile

**Zero changes required — verdict: no clipping.** The year-explicit label is
**strictly shorter** than the label it replaces for all 12 rungs (6 characters
and one word fewer: `"2026 Early 1st"` = 14 chars / 3 words vs
`"Early 1st Round Pick"` = 20 chars / 4 words) with the same longest token
(5 chars: `"Early"` vs `"Round"`). Pinned by
`test_pick_rung_year_labels.py::test_year_label_is_not_longer_than_the_label_it_replaces`.

- **QuickSet chips** (`QuickSetTiersScreen.chipName`, 12pt uiSemi,
  `numberOfLines={1}` + `flexShrink`) — single-line ellipsis, so a shorter
  string strictly reduces truncation.
- **Tiers tiles** (`PlayerCard.denseName`, `numberOfLines={1}`) — same.
- **Trios two-line mini-cards** (#243: fixed 36pt = 2 × 18pt box, 13pt
  uiSemi, `numberOfLines={2}`, `textBreakStrategy="simple"`, hyphenation off)
  — worst case wraps `"2026 Early"` / `"1st"`, both lines shorter than the
  old `"Early 1st"` / `"Round Pick"`. `glueSuffix()`'s regex
  (`/ (Jr\.?|Sr\.?|II|III|IV|V)$/`) does not match `1st`/`2nd`/`3rd`/`4th`,
  so it neither fires nor needs to.

Clients render `name` verbatim; none parse it (the one `/\s*Round Pick$/`
strip, in `TradeValueBar`, reads `/api/trade/evaluate`'s league-agnostic
`gap.pick_equivalent.label`, which is deliberately not relabelled). Recorded
as an invariant in `docs/cross-client-invariants.md`.

## Verification

- **`python3 -m pytest backend/tests -q` → 1531 passed, 1 skipped**
  (branch baseline, measured by stashing this diff: **1448 passed, 1
  skipped**; +83 new tests, **zero existing tests modified** — the relabel is
  serialization-only, so nothing that pins pool shape or rung ids moved).
- **`cd mobile && npx tsc --noEmit` → exit 0.**
- **Detection tests were written first and confirmed discriminating**: with
  `sleeper_verdict` swapped for #228's naive status-only rule, **6/6** of the
  conflict/ambiguity tests fail (roster veto, empty-drafts ambiguity,
  startup-shaped complete draft, complete-with-zero-picks, complete-with-no-
  rookies downgrade, drafting+veto).
- **Live smoke** against the research's two probe leagues (read-only public
  Sleeper API, 2026-08-05, 12 209-player dump):

  | League | draft status | rounds | rookies rostered | teams | verdict | rungs read as |
  |---|---|---|---|---|---|---|
  | Lakeview `1312076055586050048` | `complete` | 4 | 57 | 12/12 | `drafted`/**high** via `sleeper_draft_status` | **2027** |
  | FFv3 `1312140920132497408` | `pre_draft` | 4 | 0 | 0/12 | `not_drafted`/**high** via `sleeper_draft_status` | **2026** |

  Both signals agree in both leagues — perfect separation, matching
  research-platforms.md §2.3 exactly.

## New tests

- `backend/tests/test_draft_status.py` (34) — the full decision matrix:
  rookie-row test, heuristic thresholds at the exact boundary (`N` rookies /
  `ceil(N/2)` teams, and one under each), odd league sizes, the stale-player-
  table abstention, Sleeper signal ordering incl. all three conflict cases,
  MFL made/total math + multi-`draftUnit` aggregation, platform dispatch, the
  fail-safe.
- `backend/tests/test_draft_status_wiring.py` (27) — `rookie_year` sync
  (incl. Sleeper's bogus `"0"`), `load_rookie_player_ids` exact-vs-proxy,
  the roster scan, the asymmetric cheap-skip TTLs, end-to-end refresh
  (persistence, the roster veto, `unknown` still stamping `checked_at`,
  cheap-skip + `force`, never-raises, the platform-league members path), and
  the refresh queue ordering.
- `backend/tests/test_pick_rung_year_labels.py` (17) — labels per status,
  the fail-safe on `unknown`/NULL, league-season-drives-the-year, value
  no-op vs discount, ids/elo/rank untouched, real players untouched,
  `/api/trio` parity, **flag-off byte-identity** on both routes, abstention
  with no league row / demo league, and the label-length guard.
- `backend/tests/test_mfl_service.py` (+5) — `draftResults` export URL shape,
  best-effort degradation on 401/404/500, non-numeric league id.
