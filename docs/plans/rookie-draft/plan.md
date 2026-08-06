# Plan: Rookie Rankings + Live Draft Support

**Status: FINAL — dual-agent converged (both lenses signed off, round 4/4)** · 2026-08-05
Sources: Agent A (execution lens, live API probes) + Agent B (risk lens, local-data probes). Both agents' platform/data claims were independently verified against live endpoints or the working tree on 2026-08-05.

## 0. Ground truth corrections (read first)

1. **#207 is SHIPPED, not pending.** Both draft agents read the local tree, which lags `origin/main`: `backend/draft_status.py`, `players.rookie_year`, the leagues draft-status columns, MFL `draftResults`/`futureDraftPicks` fetchers, and year-explicit rung labels all landed on `main` today (commits `e98560a`, `0118efc`). Everything below builds ON them. (Local `teardown-remediation` must `git pull` before any build wave.)
2. **The player-data pipeline has no refresh path** (verified): `_load_sleeper_cache` has no TTL; the only fetch is on file-miss; the "24h sync gate" re-syncs from the same stale file. Dev cache is dated Apr 11 (pre-NFL-draft: 157 teamless "rookies", 2 with teams). Prod is only accidentally fresher via Render cold boots. **This is the true M0 of this feature.**
3. **The universal pool is frozen per-process** (`_ensure_universal_pools` early-returns once built). A refreshed player table is invisible until redeploy. Needs a generation counter + lazy service rebuild.
4. **Seasonal window**: the 2026 class is loaded and valued NOW (rookie ranking is fully testable this fall, incl. the operator's pre-draft FFv3 league). The 2027 class will NOT exist in Sleeper's dump until ~late Apr 2027 — the "as drafts get closer" months of Feb–Apr 2027 are structurally empty and need a designed state, a class-load monitor, and a March re-verification pass. The `drafting` state IS testable any time via an operator-created throwaway Sleeper league with a started draft (resolves the "unobservable until May" objection) — recorded fixtures make it repeatable in CI.
5. **Per-slot pick values EXIST upstream** (falsifies research-codebase §5.3): DynastyProcess `files/values.csv` (repo reads only `values-players.csv` today) carries `2026 Pick 1.01…5.12` + future-year rungs in the exact scale `seed_elo_for_value()` consumes. Its future-year rungs corroborate our shipped ladder within ~2 Elo at Early/Late — and its current-year slot curve is much steeper than our ladder (1.01 ≈ 1817 vs "Early 1st" 1720), so engine adoption is a REPRICING decision, not a data plumb.

## 1. Objective & Definition of Done

**Objective:** (1) rookie-scoped ranking on the ranking surfaces, writing to the ONE existing per-user-per-format board; (2) a read-only Draft Room for Sleeper + MFL: real order where the platform provides one, per-slot ownership incl. traded picks, live pick feed, and an undrafted-rookies list ordered by consensus or the user's board.

| # | Done criterion | Verified by |
|---|---|---|
| D1 | Player cache refreshes on schedule (daemon thread, atomic swap — never inline on the request worker); a new class appears at the user's NEXT session_init within 24h, no restart; p95 request latency unchanged during a refresh; **a generation bump changes pool MEMBERSHIP only — existing members carry their prior seed Elo forward** (re-seeding stays on the session-boundary cadence); no service rebuild inside an active ranking session | forced-age + generation + latency tests |
| D2 | **Scope is a post-Elo VIEW filter**: for every rookie pid, scoped Elo == unscoped Elo exactly (same swipe multiset — rookie-vs-vet swipes included). Write-identity **by write shape**: permutation-shaped writes (`apply_reorder`, `apply_anchor`) are byte-identical to the equivalent unscoped action on that subsequence; **tier saves use the merged-band rule** — reconstruct the full-band ordered list by merging scoped pids into the current full-band order, compute the linear spread over that FULL list, persist overrides for scoped pids ONLY (each scoped pid gets exactly the value the equivalent full-band save would give it; untouched members' overrides byte-unchanged) | Elo-identity + per-shape write tests |
| D3 | Scoped tier saves follow D2's merged-band rule (scoped pids only, valued as the full-band save would value them; never a whole-band respread); a non-rookie with no override before a scoped save has none after; #161 demotion scoped to the visible subset; **a one-time pre-scope snapshot of the user's override blob exists (stored as a sibling key in the same `users` JSON column — no new datastore; data-dictionary updated) with an operator restore path, before the first scoped save — precondition for flipping `ranks.rookie_subset`** (`tier_overrides` is a wholesale-overwritten JSON blob with no history; a prior filtering bug permanently destroyed a board — server.py's own comment) | regression tests verify-failing-first + snapshot test |
| D4 | Same build, flag on vs off, data held constant ⇒ ranking responses byte-identical | golden diff |
| D5 | Draft Room: complete draft renders full board (probe: Lakeview); pre-draft with assigned order renders true slots + traded-pick overlay; `draft_order:null` renders honest "order not set" + round-level ownership — NEVER an invented order (the pre-draft identity `slot_to_roster_id` trap is unit-pinned) | probe fixtures |
| D6 | Live: picks appear ≤30s while focused; zero requests when blurred/background; N viewers of one draft ⇒ ≤1 upstream fetch per TTL | throwaway-league live test + instrumented QA |
| D7 | Undrafted list = `players.rookie_year == season` − drafted − rostered, ordered by consensus OR my-board, unvalued tail shown honestly ("no consensus value"), never dropped | unit + Maestro |
| D8 | MFL parity via `draftResults` grid (franchise on every unmade pick — verified live on a pending league) | probe fixtures |
| D9 | No platform writes; terminal CTA is a deep link to the platform's draft room | code review |
| D10 | Full suite green; flag mirror test; each flag off = no entry point + zero writes | CI + QA matrix |

## 2. Scope

**In:** Sleeper primary + MFL parity; rookie scope on Quick Set, Quick Rank, Trios, Tiers board, Overall ranks, Pick Anchors (all six — Quick Rank inherits the scoped payload for free but will mostly skip thin tiers; that's acceptable, not a build); Draft Room states upcoming/live/complete-recap + designed pre-class-load state; slot values as display-only axis.

**Out (positions, not omissions):** platform writes (no public write API; mis-picking in a live draft is irreversible harm — prepare-and-deep-link, the #179 precedent) · ESPN (no pick model in FTF; mDraftDetail unverified) · Fleaflicker (unverified) · startup drafts (detected via rounds-shape and LABELED "Startup draft" with the rookie undrafted list suppressed — never rendered as a rookie draft; full startup support is a possible V1.5, see O5) · mock drafts (no league binding; used only as QA fixtures) · on-the-clock push (needs a ≤1-min poller; realtime-tick is 15-min — M7) · slot values in the trade engine (separate calibration decision, #214-toggle precedent — O2) · a separate rookie Elo space (REJECTED on the merits: tier bands are absolute Elo anchored to pick values; a second space breaks tier colors, trade values, #161 demotion, and adds a 5th cross-client mirror) · devy/pre-NFL-draft boards (class is teamless + unvalued; pool requires DP value > 0).

## 3. Milestones

**M0 — Data foundation** (BE, solo wave; blocking everything rookie)
Cache TTL + daily-tick refresh of `/v1/players/nfl` — **NOTE: Render 'cron' is an HTTP POST into the single-worker web service, so the handler must acquire the existing sync lock, spawn a daemon thread, and return 202; cache written to a temp file + atomic rename (no reader sees a partial file)**; invalidation runs in ORDER: disk file → `_sleeper_cache` global → `sync_players` (reset `last_synced`) → DP value maps → universal pools (**build-new-then-rebind**, never clear-in-place — `_player_sync_lock` serializes writers but does not guard pool readers; a cleared pool would hand a concurrent session_init an empty board) → mark stale via the generation counter (never clear in place; rebuild happens lazily at session boundary) · single-flight guard on `_ensure_universal_pools` (the sync lock guards sync only — daemon + request worker could otherwise race two DP fetch fan-outs) · delete or atomically rebind the legacy `.clear()/.update()` globals before adding a background mutator · pool **generation counter**, membership-only (per D1: existing members carry seeds forward; rebuild only at session boundary via the existing rebuild-on-user-change seam) · **pin THE rookie predicate**: `draft_status.is_rookie_row` (`rookie_year == season`, `years_exp==0 AND team` proxy) recorded in `docs/cross-client-invariants.md` — the shipped `/api/rookies` + `load_rookies` use a LOOSER `years_exp==0 OR NULL` rule — rebase onto the EXISTING `load_rookie_player_ids(season)` (already indexed SQL mirroring `is_rookie_row`); M4 retires their surface · dev guard: log cache-file mtime at boot; refuse rookie scope from a >7-day cache outside prod, **exempting `FTF_TEST_MODE`** (the Maestro harness runs a pinned cache file) · **measurement script before any UI**: valued-rookie counts per position per format (expected ~40–90 league-wide; TE possibly <5 — gates rookie Trios) · class-load monitor: alert on first `rookie_year == next-season` row. *Done bar:* D1 + measured numbers in the plan folder. **1 batch, high confidence.**

**M1 — Draft replay & fixture harness** (BE, parallel with M0)
Record via the existing `FTF_SLEEPER_FIXTURES_DIR` seam: Lakeview complete draft (48 picks + traded_picks + draft_order), FFv3 pre-draft (identity-map trap, `draft_order:null`), MFL grids (made==0 / partial / complete / multi-`draftUnit`). Replayer truncates picks to k with a fake clock → any in-progress state deterministically in CI. *Done bar:* replay drives the full M3–M5 test matrix. **1 batch, high confidence.**

**M2 — Rookie scope: one server seam + six modes** (BE solo wave, then MOB; after M0)
`scope=rookie` on `/api/rankings` + `/api/trio` as a **post-Elo VIEW filter** — `_pool`/`_compute_elo`/`apply_reorder`/`apply_tiers` ALL stay on the full position pool (filtering `_pool` would drop every rookie-vs-vet swipe from `_compute_elo`, silently forking the Elo space — the round-2 review's central catch); the rookie subset is applied in the response/selection layer only, and every scoped WRITE derives from full-pool Elo. Never a client-side filter (5 clients mirror invariants). Trios: candidate SELECTION filters to rookies; Elo updates from picks are unchanged full-board updates. Lane audit: `_cross_position_trio` and the QC-trio path bypass the seam — re-scope or disable under scope. Thin-pool contract: typed 200 `{empty:true, reason}` (never the current <3-pool ValueError→400). **Write-safety (D3): scoped tier saves implement D2's merged-band rule (merge into full-band order → spread over the full list → persist scoped pids only — the ONLY construction satisfying both write-identity and no-respread; a naive scoped-list spread OR a full-band persist each destroys boards); pre-scope snapshot per user+format lands BEFORE any scoped-save UI; `demoted_pids` scopes to the visible subset; the scoped save path must NEVER pass scope into `upsert_member_rankings` (leaguemates' trade math reads it — cross-user blast radius); and a scoped save must NOT call `save_tiers_position` — `tiers_saved`/`all_done` are completeness markers consumed by LeagueScreen's ranked count, quicksetProgress's cache, the web celebration, and #244 launch routing, and a rookies-only save must not mark a position complete (test: no `tiers_saved` entry before ⇒ none after; `/api/tiers/status.all_done` unchanged). Note: `apply_reorder` is ALREADY subset-safe (permutes the submitted subset's own Elos, writes only submitted pids) — do not 'fix' it; only the tier-save lane needs the anchor-style path.** Suppress nothing else — same Elo, same board. `via:'rookie_*'` event tagging. Mobile: ONE shared control (rankChooserModel-style shared content), session-only (#133 precedent), rolled out Anchors → Tiers → Quick Set (start ladder at first rookie-bearing rung; must NOT mark quicksetProgress complete — #244 launch routing would misfire) → Overall/Quick Rank (inherit) → Trios last, gated on M0's measurement (position-limit or drop thin positions). *Done bar:* D2/D3/D4 + 6-mode Maestro matrix. **3 batches (1 BE + 2 MOB/QA), medium confidence — QA breadth is the cost.**

**M3 — Draft board service + `GET /api/draft/board`** (BE; after M1; parallel with M2's mobile half)
New `backend/draft_board_service.py`, one versioned payload `{schema:1, state: upcoming|live|complete|unavailable, kind: rookie|startup, order[], picks[], undrafted[], my_picks[], order_confidence, as_of, stale}`. Verified API mechanics: poll the 1.2KB draft-detail object's `last_picked` (s-maxage=30) and fetch the 20KB `/picks` only on change (complete drafts are CDN-cached ~24h — never poll picks directly); `traded_picks` overlay is available pre-draft; `draft_order != null` gates any slot rendering. Per-draft shared TTL cache (20s drafting / 5min pre / 24h complete): N viewers ⇒ 1 upstream read per TTL. Circuit breaker + budget counter → degrade to manual refresh. Divergence rule (tested): **draft object is truth for the board; `draft_picks` is truth for pre-draft ownership; V1 never writes one from the other** (note: #228 deletes the season's `draft_picks` rows at completion — the room must not read them for the live/recap board, or it empties at the finish line). Undrafted list per D7 (sourced from `rookie_year`, NOT the value pool; unvalued tail honest). Route carries `@_gate_unverified_read` (same auth posture as /api/rankings). *Done bar:* replay harness drives all states; D5 fixtures pinned. **2 batches** (payload + states + cache + breaker is more than one wave), high confidence.

**M4 — Draft Room UI** (MOB; after M3)
Root-stack route (FreeAgents pattern), entry = the existing `league.rookie_board_entry` Explore tile replaced ("Rookie draft" — O1) **conditional on `draft.room`: flag off restores today's rookie-board tile** (all new flags land OFF; an unconditional swap would strand users with nothing). Sections: board / your picks / undrafted (with the LeagueSummary-style Consensus|My-board toggle + FreeAgents-style fallback notices). Designed states: pre-class-load ("The 2027 class loads after the NFL draft (late April). Showing last year's class" — toggleable), order-not-set, startup-labeled, platform-unsupported, stale (`as_of` always visible). Live polling behind SEPARATE flag `draft.live_poll`: 15s client interval against OUR endpoint, focus+state gated, hard stop on background, manual Refresh always present. Note: `refetchInterval` has zero precedent in this app — instrument request counts in QA — pass threshold for background/blur is literally ZERO requests. *Done bar:* D5/D7 on fixtures close the batches; **the throwaway-league live test (O7) is a RELEASE gate for `draft.live_poll`, not a batch gate** — an operator slip can't block the wave. **2 batches, medium confidence (net-new polling machinery).**

**M5 — MFL parity** (BE; after M3 contract freezes)
Same payload shape from `TYPE=draftResults` (verified live: pending league returns the full pre-populated grid, franchise on every unmade pick, trade provenance in comments — MFL answers "who picks at 2.03" directly, better than Sleeper pre-draft). `liveDraft` type is dead (verified) — `draftResults` + per-pick timestamps IS the live feed; 30s server poll, `_REQUEST_SPACING_SECONDS` honored; `draftUnit` dict-or-list aggregation. Snapshot age surfaced (`as_of`); auth failure → stored snapshot + "reconnect MFL", never stale-as-live. Mid-draft update latency is UNVERIFIED — a timed probe against a genuinely drafting MFL league gates `draft.mfl` live mode; until then MFL ships upcoming+refresh. *Done bar:* D8 on fixtures; live gate documented. **1 batch, medium-high confidence.**

**M6 — Slot values, display-only** (BE; after M3 — it renders on M3's payload)
Read DP `values.csv` PICK rows; serve per-slot values on the draft board (and only there) behind `picks.slot_values` default OFF. `GENERIC_PICK_SEEDS`, the 8-tier ladder, tier bands, and the trade engine untouched. Non-12-team leagues: percentile map, labeled approximation (O3). Engine adoption = separate operator decision (O2). **1 batch, not on the critical path.**

**M7 — Deferred, named**: on-the-clock push (dedicated poller + cron cost) · draft recap analysis · `platform_future_picks` refresh from the live MFL grid · ESPN mDraftDetail verification · web parity for rookie scope · startup-draft full support.

**M8 — Spring rehearsal (calendar-gated)**: Mar 2027 re-verification of the (by then ~4-month-frozen) live code against fixtures + class-load simulation · late-Apr 2027 monitored class-load event (one-shot window; alert wired in M0) · May 2027 operator-league pilot via tester allowlist, then widen.

## 4. Sequencing

```
M0 data foundation ──┬─► M2 rookie scope (BE solo → MOB) ─────────┐
M1 fixture harness ──┴─► M3 board service ─► M4 room UI ─► live ──┼─► V1 gate ─► M8 spring
                              └────────────► M5 MFL ──────────────┘        M6 anytime
```
Critical path: M0 → M3 → M4. Hard rules: **server.py is a single-writer resource across ALL milestones** (M0, M2, M3, M6 each edit it — never two concurrently); M2's seam is a SOLO backend wave; M2 write-safety lands before any scoped-save UI; `git pull` before every wave — precondition: the working tree currently holds ~8 modified tracked files incl. `docs/api-reference.md` (which M3 also edits); commit/stash theirs first and expect that conflict; re-diff TabNav/quicksetProgress/pick regions before each wave (#244/#246 landed today).

## 5. Timeline & Effort (pipeline batches: plan → build worktrees → QA×2 → ship)

| Milestone | Batches | Confidence |
|---|---|---|
| M0 + M1 (parallel) | 2 | high |
| M2 scope + modes | 3 | medium (QA breadth) |
| M3 board service | 2 | high (all endpoint facts verified live) |
| M4 room UI + live | 2 | medium (new polling machinery) |
| M5 MFL | 1 | medium-high |
| M6 slot display | 1 | medium |
| **V1 total** | **11** | |
| M8 spring rehearsal | ~1 (Mar–May 2027, resourced now) | — |

Calendar: **Aug–Oct 2026** M0–M5 (rookie scope is fully real against the 2026 class; the room is real for late/new 2026 leagues + recaps). **Nov–Feb** freeze, flags off for live where unproven. **Mar–May 2027** M8. Schedule risk concentrates in M4 (new machinery) and the class-load event, not platform integration (best-evidenced part). +30% if the class-load behaves unlike fixtures or the Render decision (O8) goes sideways.

## 6. Top risks (full register argued in §sources; each with fix)

| Risk | Fix |
|---|---|
| Invented draft order (pre-draft identity `slot_to_roster_id`) | `draft_order != null` gate; both probe payloads pinned as fixtures |
| Stale CDN picks read as live | poll detail `last_picked`, fetch picks on change; `as_of` in UI |
| Scoped tier save respreads band / #161 demotes unshown vets | M2 write-safety, verify-failing-first (D3) |
| Trio lanes leak vets into rookie scope; thin pools 400 | lane audit + typed empty (M2) |
| Empty 2027 window Feb–Apr | designed pre-load state + last-year toggle + class-load monitor |
| No data refresh / frozen pool | M0 is the feature's true foundation; dev cache-age guard |
| Free-plan single worker + spin-down vs "live" | fan-in cache makes load trivial; cold-start stall remains → O8 operator decision; `draft.live_poll` ships OFF until the live test passes |
| One board serves drafted + undrafted leagues (override resurrection) | scope is a read filter, NEVER pool membership churn (#207 Option A discipline) |
| Rookies missing from value pool vanish | undrafted list sources from `rookie_year`, unvalued tail rendered honestly |
| DP `values.csv` is a second remote file — `FTF_TEST_MODE` only pins `values-players.csv` | M6 adds its own env override (hermetic test seam) before any fetch lands |
| Fan-in guarantee is per-process | if O8 upgrades to multi-worker, ≤3 req/min/draft multiplies by worker count — restate the budget then |
| Flag-off residue | per-milestone flags (`ranks.rookie_subset`, `draft.room`, `draft.live_poll`, `draft.mfl`, `picks.slot_values`), all land OFF, flip at release gates; scoped writes identifiable via `via:'rookie_*'` |

**Whole-feature abort criterion:** if M0's measurement shows a format with <15 valued rookies, rookie scope ships for Pick Anchors + Tiers only and the Draft Room becomes the primary deliverable; if the class-load rehearsal (M8.1) fails, `draft.live_poll` stays off for the season and the room ships as upcoming/recap + refresh.

## 7. Resourcing

No new infra, cron, or datastore (M7's push would need one). New artifacts: `draft_board_service.py`, one route, one screen, one players column read (already shipped), DP values.csv reader. Polling budget: client 15s (focused+drafting) → per-draft TTL 20s → ≤3 upstream req/min/draft regardless of viewers. Operator supplies in week one: (a) the throwaway Sleeper league with a startable draft (gates D6), (b) the Render plan decision (O8).

## 8. Open questions / decisions needed

- **O1** Explore tile: REPLACE `league.rookie_board_entry`'s rookie-board tile with the Draft Room (recommended) or keep both?
- **O2** Slot values into the trade engine later? (Repricing decision; #214-style toggle precedent. Display-only until you say otherwise.)
- **O3** Non-12-team slot mapping: percentile (recommended, labeled approximation) or round-rung fallback?
- **O4** Confirm the #161 rule under scope: a rookie-scoped save demotes only rookies that were visible and unselected. (The one place this can damage boards silently.)
- **O5** Startup drafts: label-and-degrade now; is full startup support wanted as V1.5 before next August (larger audience than rookie drafts)?
- **O6** "Live enough" = ~20-30s effective (Sleeper CDN floor). Sub-5s needs their private websocket — not committed.
- **O7** Throwaway Sleeper league for the live test — week one.
- **O8** Render plan: stay free (live polling ships OFF; room = upcoming/recap + manual refresh — still most of the ask) or upgrade (live polling real)?
- **O9** Manual per-league override ("my draft is/isn't done"): **recommend NO for V1** — it reintroduces a user-writable second source of truth for exactly what #207 centralized (the risk lens originally proposed it; the execution lens calls it risk theater; positions logged). Revisit only if confidence-tier misfires show up in the field.
- **O10** Do generic pick rungs appear under `scope=rookie`? (They're pool members and arguably the most draft-relevant asset; interacts with #207 labels + M6.) Decide before M2 builds — recommend YES, year-labeled, listed after players.


---

## Reconciliation Log

**Document type:** Plan · **Rounds run:** 4 · **Converged:** yes (both SIGN-OFF: yes, round 4)

### Round-by-round
**Round 1 (independent drafts):** A live-probed platform APIs (slot-value source in DP values.csv — falsifying prior research; Sleeper CDN TTLs; identity-map slot trap; MFL pending-grid quality). B probed local data (no player-cache refresh path; frozen pool; apply_tiers subset hazard; seasonal 2027-class window). Both independently missed that #207 had shipped to origin/main (local tree lags) — corrected in synthesis.
**Round 2:** A blocked on (1) pool-filter scope forking the Elo space (dropped rookie-vs-vet swipes) → post-Elo VIEW filter + Elo/write-identity bars; (2) undefined rookie predicate + /api/rookies//LeagueScreen-sheet collision → predicate pinned (is_rookie_row), surface retired in M4; (3) cron refresh inline on the single worker → daemon thread + 202 + atomic rename (also raised by B). B blocked on (4) generation-bump rebuild moving Elo mid-session → membership-only bumps, seeds carried, session-boundary rebuilds; (5) no recovery path for damaged boards → pre-scope snapshot + operator restore as a flag precondition; (6) D3/M2 contradiction on tier-save composition → resolved in round 3.
**Round 3:** B blocked on scoped saves tripping save_tiers_position/all_done completeness markers (cascading into ladder + #244 routing) → forbidden, with the no-entry-before/after test; A blocked on D2 byte-identity vs D3 no-respread being mutually unsatisfiable on the tiers lane → the merged-band rule (merge scoped pids into full-band order, spread over the full list, persist scoped pids only), write-identity split by write shape. Non-blocking adoptions: single-flight pool build, mark-stale-not-clear, conditional tile replacement, load_rookie_player_ids rebase, zero-request background threshold, snapshot storage named, M3=2 batches, M6 after M3, M8 resourced.
**Round 4:** both verified the patches; SIGN-OFF yes ×2. B noted (non-blocking) that partial saves can cosmetically invert against stale neighbors until the next full-band save — inherent to any partial save; one sentence for the build PRD.

### Unresolved disagreements
- **O9 (manual per-league draft-status override):** B originally proposed it as a cheap escape hatch; A called it risk theater reintroducing a second source of truth. Plan adopts A's NO-for-V1 with B's position recorded; revisit on field evidence of confidence-tier misfires.

---

## Operator decisions — 2026-08-06 (bind all build waves)

- **O8: UPGRADE Render** — live polling is real; ship `draft.live_poll` per M4 with the live-test release gate. Fan-in budget must be restated per worker count at upgrade time.
- **O7: YES** — operator creates the throwaway Sleeper league + started draft in week one.
- **O2: MARKET SLOT VALUES IN THE TRADE ENGINE** — not display-only. This invokes the plan's own guardrail: a dedicated calibration batch (M6b) with a #214-style user toggle (market-slots / tier-ladder), before/after matrix replay, deck sanity diff. Display on the draft board still lands first (M6). Note the operator's O10 remark for a future direction: pick values mapping to the USER'S OWN rookie rankings (personalized pick pricing) — not in scope now, but the toggle architecture should not preclude a third mode later.
- **O10: NO pick rungs inside rookie scope** — players only.
- **O1 (expanded scope): rookies get a CONSOLIDATED cross-position ranking view**, reachable from any rank page as a new section — rookies remain in their position views AND appear in one rookie-ranking view; values stay synced by construction (same Elo space, view filter — the D2 architecture already guarantees it). M2's mobile milestone adds this consolidated view as a first-class deliverable, not just per-mode toggles. League-page tile: Draft Room replaces it (flag-off restores).
- **O3: percentile map** for non-12-team slot prices, labeled approximation.
- **O5: NO startup-draft support now** — label-and-degrade stands.
- **O4 (default adopted): #161 demotion under scope demotes only visible, unselected rookies.**
- **O9: NO manual override** (as recommended).

## Operator decision — draft-surface placement (2026-08-06)

Approved mock: `mockups/polish-lab-2026-08/draft-surface-placement.html`. **Option B + seasonal A′** (the agent recommended B+D and holding A′; the operator took B plus the seasonal tab):

- **B (permanent home): a Draft chip in the Acquire tab's mode strip.** It must **LEAD** the strip — the shipped five chips already measure ≈402pt against ≈361pt usable, so the strip scrolls and an appended sixth chip would never be seen.
- **A′ (seasonal): a 5th bottom tab "Draft", visible ONLY during draft season**, driven by the shipped per-league `draft_status` verdicts (`not_drafted`/`drafting` with a current-season rookie-shaped draft object ⇒ visible; `drafted`/`unknown`/none ⇒ hidden). Sleeper exposes no trustworthy scheduled start time, so "imminent" can only mean "a draft object exists and hasn't run."
- **Multi-league rule (default, flag it in review):** the tab bar is global while draft status is per-league ⇒ the tab appears when ANY linked league qualifies, and lands on that league's room (a league chooser when >1 qualifies).
- **C stays** as the League-tab recap home for drafted leagues.
- **Required by the mock's finding #2:** any tab-based surface must carry a "Rank the rookies" entry back into `RookieRanks`, or the tab teaches users that rookie ranking and rookie drafting are unrelated.
- **D (Rank-tab adjacency): not now** — the operator chose B; revisit if QA shows draft prep starting on Rank.
