# #207/#228 — MFL owned-pick draft parity — status

**Status: built (backend only; no flag — this rides the existing
`picks.owned_sync` + `picks.rank_year_labels` surfaces)** · 2026-08-05 ·
branch `worktree-agent-a16b8c9e20f110454` (off `teardown-remediation`,
merged from `worktree-agent-afae520a937d45e74` = #207)

## Operator report

> "replicate this for MFL leagues as well"

…referring to the post-draft owned-pick correctness Sleeper leagues got in
**#228**, and to the seam both prior items left open:

- [#207 status.md → Known seams](status.md#known-seams): *"MFL staleness
  persists for owned picks."*
- [#228 status.md → MFL](../228-post-draft-pick-hiding/status.md): *"the
  engine reads the copy stored at link/import time… accepted and
  documented."*

**The bug.** An MFL league linked BEFORE its rookie draft kept that season's
picks as tradable assets forever. `leagues.platform_future_picks` was a
one-shot capture written by `upsert_platform_league` at link/import;
`_sync_mfl_owned_picks` normalized that frozen list into `draft_picks`, and
every downstream consumer (trade suggestions, calculator,
`/api/league/picks`, League Summary, power rankings) faithfully served
picks that no longer exist. #207 fixed the *labels* for these leagues — it
reads the live verdict — but not the *assets*.

## Where the exclusion seam landed, and why

**`server._sync_mfl_owned_picks` — the write path.** Same layer #228 chose
for Sleeper.

The brief allowed a read/injection-path seam *if* MFL's data turned out to
be a genuinely static snapshot. Reading the code, it is not: while the
`platform_future_picks` **payload** was captured once, the **normalization**
into `draft_picks` already re-ran on four paths, and now five —

| Caller | When |
|---|---|
| `POST /api/mfl/link` | link |
| `POST /api/mfl/import` | manual re-sync |
| `POST /api/mfl/auth-import` | authenticated link |
| `session_init` background daemon (#200 guard) | every session init for that league |
| `_refresh_league_draft_status` (**new, this item**) | every draft-status refresh, incl. the hourly cron sweep |

— so `_sync_mfl_owned_picks` is the exact structural twin of
`_sync_sleeper_owned_picks`, and #228's rule drops straight into it.

**Why the write path beats the read path here:**

1. **Two platforms, one layer, no drift.** #228's exclusion is a write-path
   concern for Sleeper. Splitting MFL onto the read path would mean two
   different answers to "does this league still own 2026 picks?" living in
   two different places, which is precisely the divergence the brief warned
   against.
2. **One seam vs. five.** `load_draft_picks` has five consumers. A read-path
   filter is either five edits (and a sixth the next time someone adds a
   consumer) or a filter buried in `database.load_draft_picks`, which would
   need a league-status lookup on the hot trade path.
3. **Self-cleaning for free.** `replace_draft_picks` is delete-then-insert,
   so stale current-season rows vanish on the next normalization — the same
   "no manual data repair" property #228 relied on.
4. **Zero marginal cost.** `get_platform_league` already returns the whole
   `leagues` row, so the cached `draft_status` verdict rides along: no extra
   query, no network, on a path that runs inside request handlers.

The one asymmetry worth naming: Sleeper's exclusion reads a **live** drafts
fetch it makes itself, while MFL's reads the **cached** #207 verdict. That is
deliberate — MFL's authoritative signal (`TYPE=draftResults`) is already
fetched, decided and persisted by #207's refresh path, and re-fetching it
inside the pick sync would put a network call into three request handlers.
Instead the refresh path now *drives* the re-normalization (below), so the
cache is never the reason MFL is behind.

Both platforms route their fail-safe through the single predicate
`draft_status.current_year_picks_visible`, now reached from a shared
`server._current_season_picks_visible(status, confidence)` helper that
`_pick_rung_year_context` (#207's relabel) was refactored to use as well.
Change the asymmetry once, it changes everywhere.

## Snapshot refresh — `TYPE=futureDraftPicks`

**Auth verdict: ZERO-AUTH. Verified live, not assumed** — same discipline as
research-platforms.md §MFL and #207's `draftResults` probe. 2026-08-05, no
cookie, registered-client UA only:

| League | Host | HTTP | `futureDraftPicks` | `draftResults` |
|---|---|---|---|---|
| 10005 | `www48` | **200** | 10 franchises, 90 picks, years **2027/2028/2029** | 1 unit, **30/30** made (3 rd × 10 tm → rookie-shaped ⇒ `drafted`) |
| 60206 | `www46` | **200** | 32 franchises, 320 picks, years **2027/2028** | 2 units, **192/192** made (6 rd × 32 tm ⇒ `drafted`) |

Both probe leagues are post-draft, and **neither returns a 2026 pick** —
direct live confirmation of #228's premise that MFL drops a season from this
export once its draft is held. So a successful refresh is the *primary* fix;
the verdict-gated exclusion is the belt-and-braces layer behind it. No
fallback-to-exclusion-only was needed.

**Cadence: piggybacked, no new cron.** `_refresh_league_draft_status` — which
already has per-status TTL cheap-skips (3 h `not_drafted` / 12 h `drafted` /
1 h `unknown`) and a 50-league-per-tick sweep budget — now, for MFL leagues
only, also calls `_refresh_mfl_future_picks` and then re-runs
`_sync_mfl_owned_picks`. Cost: **one extra zero-auth export per refreshed MFL
league**, inside the existing budget. Reached from both the session-init
daemon and `/api/cron/hourly-tick`, so a draft that completes between
sessions is picked up without anyone opening the app.

**Never wipes on a flake** (#220's lesson). `fetch_future_draft_picks`
returns `{}` on any MFL error, which is *distinguishable* from a genuinely
empty grid (`futureDraftPicks` key present, no franchises). Only a payload
carrying the key is written; `{}` logs and keeps the stored snapshot. And the
re-normalization runs **even when the fetch fails**, so a verdict that just
flipped to `drafted` still drops the stale season immediately — the
exclusion-only path is a real, tested fallback, not a theoretical one.

## Behavior matrix

| League's cached `draft_status` | Snapshot fetch | Current season's picks in `draft_picks` | Future seasons |
|---|---|---|---|
| `drafted` | ok | **gone** (MFL already dropped them; exclusion is redundant here) | kept |
| `drafted` | unavailable | **gone** (exclusion alone) | kept, from the stale snapshot |
| `not_drafted` | ok | kept | kept |
| `unknown` / NULL (never checked) | either | **kept** — fail-safe | kept |
| any, Sleeper league | n/a | unchanged — #228's live drafts fetch still decides | unchanged |

## Files

- `backend/mfl_service.py` — **new** `fetch_future_draft_picks` (best-effort
  `TYPE=futureDraftPicks`); **new** `parse_future_picks`, extracted from
  `parse_bundle` (which now calls it) so the link-time bundle and the
  standalone refresher can never write different row shapes
- `backend/database.py` — **new** `set_platform_future_picks`: a deliberately
  narrow updater for that one column, so a refresh can never disturb the
  binding columns (host / auth / my_team / season) that only a real re-link
  may change
- `backend/server.py` — **new** `_current_season_picks_visible` (the shared
  cached-verdict fail-safe; `_pick_rung_year_context` refactored onto it);
  **new** `_refresh_mfl_future_picks`; the verdict-gated `exclude_season`
  in `_sync_mfl_owned_picks`; the MFL branch in `_refresh_league_draft_status`
- Docs: `api-reference.md` (the `/api/league/picks` MFL degradation note now
  reads "seam closed"), `data-dictionary.md` (`platform_future_picks` is no
  longer write-once and no longer "not read by the trade engine"),
  `architecture.md`, `runbook.md`, plus the #207 and #228 status docs

## Deliberate non-changes (scope guard)

- **Sleeper's #228 exclusion is untouched.** It still makes its own
  `_fetch_sleeper_drafts` call; it does not consult the #207 cache. Pinned by
  `test_cached_verdict_does_not_leak_into_the_sleeper_sync`, which seeds a
  cached `drafted` verdict on a Sleeper league and asserts a live `pre_draft`
  read still keeps 2026 picks.
- **No new feature flag.** The behavior is a correctness fix inside an
  already-flagged surface (`picks.owned_sync`), and it fails safe by
  construction; a flag would only add a way to keep serving picks that don't
  exist.
- **No new cron, no new column, no route or response-shape change.**
- **The daemon's step order is unchanged.** `_sync_mfl_owned_picks` still
  runs before `_refresh_league_draft_status`; the refresh's own
  re-normalization makes that first call redundant-but-harmless (it retains
  its #200 self-heal role) rather than requiring a reorder.
- **Trade-engine adjustment math, the serialization relabel sites and all of
  `mobile/` are untouched** (`git diff mobile/` is empty).
- **ESPN / Fleaflicker unchanged** — ESPN stores no pick ownership at all and
  Fleaflicker's draft board remains unverified (#207's ESPN caveat stands).

## Verification

- **`python3 -m pytest backend/tests -q` → 1557 passed, 1 skipped**
  (merged #207 baseline: **1531 passed, 1 skipped**; **+26 tests, zero
  existing tests modified**).
- **`mobile/ && tsc --noEmit` → exit 0** (and `git diff -- mobile/` is empty,
  so this is a proof of no collateral damage rather than a change under test).
- **Verify-failing-first, both halves:**
  - exclusion neutered (`exclude_season = None`) → **3 fail**
    (`test_mfl_drafted_verdict_excludes_only_the_current_season`,
    `…fail_safe_matches_228[drafted-None]`,
    `…replace_sync_cleans_stale_current_season_rows`), and — correctly — the
    `not_drafted` / `unknown` / never-checked fail-safe cases still **pass**,
    since they assert that nothing is hidden.
  - piggyback branch disabled → **3 fail**
    (`test_status_refresh_piggybacks_the_snapshot_and_renormalizes`,
    `…renormalizes_even_when_the_snapshot_fetch_fails`,
    `…keeps_the_current_season_when_not_drafted`).
- **Live smoke** — the two public MFL leagues in the auth table above,
  read-only, no cookie.

## New tests (+26)

- `backend/tests/test_mfl_service.py` (+6) — `futureDraftPicks` export URL
  shape and the **absence of a Cookie header**, degradation to `{}` on
  401/404/500, non-numeric league id, `parse_future_picks` normalization
  (incl. MFL's single-member-dict collapse), **byte-equality with
  `parse_bundle`'s `future_picks`**, empty/junk tolerance.
- `backend/tests/test_owned_picks.py` (+8) — drafted excludes the current
  season **only** (2027/2028 survive); the fail-safe parametrized over
  `not_drafted` / `unknown` / `drafted`-without-confidence / NULL; the
  replace-sync cleaning stale pre-draft rows; the shared predicate; and the
  Sleeper no-leak guard.
- `backend/tests/test_draft_status_wiring.py` (+12) — snapshot refresh write
  path, correct host/season/league id on the fetch, **never-wipe on
  unavailable** vs. **write a genuinely empty grid**, abstain without a host,
  no-op for a non-MFL league, the end-to-end piggyback (verdict → snapshot →
  owned picks), the fetch-failed exclusion-only fallback, the `not_drafted`
  fail-safe end to end, and the Sleeper platform gate.

## Known seams (accepted)

- **The MFL roster heuristic is only as fresh as the last import.** When
  `draftResults` is unavailable, `_detect_league_draft_status` falls back to
  rosters read from `league_members`, which for MFL are refreshed at
  link/import only (#207 research §3.4). Unchanged by this item, and it
  degrades toward `unknown` → picks stay visible.
- **A private MFL league behind a cookie is untested against live auth.**
  Both probes were public. If a credentialed league ever rejects these
  exports, `fetch_future_draft_picks` returns `{}` and the league lands on the
  exclusion-only path, which the tests cover explicitly.
- **Slot-level and per-round pick provenance are unchanged** — this item only
  decides *which seasons* exist.
