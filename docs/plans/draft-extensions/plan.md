# Plan: Draft-Surface Extensions (rookie-rank bridge · ESPN manual tracking · mock drafts)

**Status: candidate v1 — dual-agent synthesis, under cross-review** · 2026-08-06
Sources: Agent A (execution lens) + Agent B (risk lens), both grounded on `origin/main` @ `3c976cb`.

## 0. Ground truth (verified, both lenses independently)

1. **Item 1 is already built AND flag-on.** `ranks.rookie_subset` and `draft.room` are `true` in prod config. `DraftRoomScreen` renders `draft-room.rank-rookies` in **every** board state → `Main → Rank → RookieRanks`. Three other entries exist. **Nothing to build for the link itself.** Two real gaps remain: the bridge is *one-way* (no return route, lands two hops from any editing gesture), and undrafted rows are inert `View`s with a **shared, non-unique testID** — the flow is currently untestable.
2. **The mock draft feature does not exist.** No service, table, or flag. `docs/plans/rookie-draft/mock-draft-plan.md` is an **untracked, local-only** reviewed draft. So item 3 is build-from-zero, not an entry-point wire-up.
3. **A live defect existed and is FIXED** (`ab5050f`, this session): the seasonal tab predicate checked draft status but not platform binding, so MFL leagues got a tab leading to "not available for this platform." Predicate now requires a bound adapter (Sleeper always, MFL iff `draft.mfl`, others never). **This is also the template for the ESPN question below.**
4. **ESPN's exclusion is structural.** `draft_picks.platform` carries the comment "ESPN never writes rows"; `picks_supported = platform != "espn"` gates two engine guards; ESPN import is one read-only GET. But ESPN rosters DO arrive in our Sleeper id space via a 99.2%-coverage crosswalk — which is what makes an undrafted list computable at all.
5. **ESPN can never reach the seasonal tab today, by design:** its verdict routes to the rosters heuristic, which **caps at MEDIUM by construction**, and the tab requires `high`.
6. **There is a free, unspent ESPN probe.** `&view=mDraftDetail` costs **zero extra HTTP requests** (one token appended to an existing call) and reportedly returns `draftDetail:{drafted, picks[]}`. Never verified; explicitly "do not build on it." **Both lenses independently named running it the highest-leverage half-day available.**
7. **`draft-room.rank-rookies` emits no analytics.** The Draft Room has zero `track()` calls.

## 1. Objective & Definition of Done

**Objective:** (A) let a user act on a rookie *from* the draft board without losing their place; (B) give users of leagues FTF cannot read an honest, bounded way to see who's left; (C) build and make genuinely reachable an FTF-native mock draft.

| # | Done criterion | Verified by |
|---|---|---|
| D0 | `draft-room.rank-rookies` and the new actions emit client events; per-player testIDs exist (`draft-room.undrafted-row.<pid>`) | analytics + Maestro |
| D1 | From the Draft Room a user sets a rookie's value in ≤3 taps without navigating away, via the **existing** `POST /api/anchor/save` lane; every untouched pid's override is byte-unchanged; `tiers_saved`/`all_done` untouched | write-identity test |
| D2 | **Manual data can never be mistaken for platform truth**: import-graph + AST test proves no manual module is imported by `trade_service`, `pick_values`, `power_rankings`, or `draft_status`, and no manual path calls `set_league_draft_status`/`sync_draft_picks`/`replace_draft_picks` | import-graph test (the shipped `test_m3_07` pattern) |
| D3 | **Golden byte-identity**: with a fully populated manual session, `/api/league/picks`, `/api/trade/evaluate`, `/api/trade/suggestions`, `/api/rankings`, `/api/league/power-rankings` are byte-identical to the same build with no session; `leagues.draft_status*` unchanged | golden diff |
| D4 | **Platform wins, never merges**: first authoritative platform read for a tracked (league, season) flips the session to `superseded` in one transaction, switches source wholesale, shows a one-time diff. No per-pick merge, no gap-filling, ever | reconciliation tests ×3 |
| D5 | Manual origin is visible everywhere: `source:"user"` per pick + `tracking:{active,coverage,marked}`; UI says it's the user's own tracking | payload + Maestro |
| D6 | A half-tracked draft degrades **monotonically in the safe direction**: under-marking shows players who are gone (visible, self-correcting); over-marking is undoable and never destructive; coverage always on screen | unit + Maestro |
| D7 | Mock CPU picks are drawn from **market consensus**, never the user's board; the noise model is **fitted to the real Lakeview 48-pick corpus**, not hand-chosen; bots replaying Lakeview land inside the fitted band | calibration test |
| D8 | Mock is deterministic per `rng_seed`, resumable, **zero platform egress after creation** | fixture-seam counters |
| D9 | Mock is reachable **when no draft is scheduled** (the off-season case) via a surface that exists year-round, plus one canonical deep link | nav test |
| D10 | Every flag OFF ⇒ byte-identical responses, zero new entry points, `schema` stays `1`, **no new member in any closed client enum** (`state`/`kind`/`order_confidence`) — new states ride `notice.code`, which the client already falls back on | golden diff + flag mirror |
| D11 | Full backend suite + `tsc` green (re-baseline after the in-flight M5/M6/M6b wave); docs updated | CI |

## 2. Scope

**In:** draft-room per-player actions (anchor lane only) + coverage nudge · user-asserted **availability** tracking for structurally-unreadable leagues (ESPN first; mechanism platform-agnostic) incl. bulk paste-recap import · FTF-native mock draft + its access path · two gating spikes.

**Out — positions, not omissions:**
- **A manual board GRID with slots/order/owners in V1.** Resolved disagreement (A wanted a `full_board` mode; B wanted marks-only): **B's position wins for V1.** The store's schema must not be *able* to express ownership — `draft_picks.pool_value` is a trade-engine input at 7 read sites with `trade.picks_in_pool` ON, so an unverifiable "I own 3 firsts" would become a priced asset in other people's suggestions. Ownership assertion is a separate increment with its own PRD and its own flag (§8 O4). Availability-only also survives a startup-shaped draft intact, which is a second reason to start there.
- **Inline drag/reorder of the undrafted list, and a "rank my undrafted now" session.** Both lenses reject: the first re-opens M2's hardest write-safety work (merged-band rule, snapshot) for a four-week surface; the second forks the scope invariant by making membership mutate mid-session. The anchor sheet delivers the on-the-clock job ("this guy isn't priced and I have 90 seconds") through a lane that is already shipped and tested.
- **Manual tracking for Sleeper/MFL on a transient failure.** Offered only where a board is *structurally* unreadable (ESPN, Fleaflicker, unknown, or `drafts == []` — the "we drafted on Discord" case), never on `upstream_error`/`breaker_open`. A flake must not spawn a phantom second source of truth.
- **Mirroring Sleeper's own mock drafts** — see §5 M12; conditionally rejected on evidence.
- **Writing asserted data into `draft_picks` or flipping `picks_supported`** · any platform write · league-wide/shared manual boards · mock trading, timers, multi-user · startup-draft support (O5 stands) · ESPN live polling · web/extension parity.

## 3. W0 — Spike pack (0.5 batch, no product code)

**S-1 (the ESPN `mDraftDetail` probe) is CANCELLED by operator ruling, 2026-08-06: "ESPN doesn't support rookie drafts. No need to research."** This is decisive and it *simplifies* the plan rather than complicating it:

- ESPN has no rookie-draft concept, so an ESPN dynasty league's rookie draft necessarily runs **off-platform** (Discord, a spreadsheet, a third-party tool). There is therefore **no platform draft object to read — not now, not ever.**
- Consequence: **manual tracking is not a fallback for ESPN, it is the only possible path**, and W3 is **unconditional** — no probe, no branch, no ESPN adapter, no `espn_verdict()`, no `draft.espn` flag, no perishable credential window. The plan's former S-1-positive branch is deleted.
- It also settles §4's placement position permanently: ESPN can never satisfy "a platform draft object exists and hasn't run," so ESPN must never reach the seasonal tab on a platform signal. Its only route to that tab is the user's own act (an active tracking session), exactly as §6 specifies.
- `picks_supported`, the `draft_picks.platform` "ESPN never writes rows" rule, and the ESPN engine guards all stay **unchanged**.
- **S-2 Sleeper mocks enumerable?** Operator creates one mock; check `GET /v1/user/<uid>/drafts/nfl/2026` for a `league_id: null` row. Go/no-go on M12.
- **S-3 Population measurement (DB only, no network, ~30 min):** how many ESPN leagues are linked at all, and how many look like dynasty leagues (the rookie-shape test is meaningless for ESPN per the ruling — ESPN drafts are redraft-shaped by construction). This sizes the audience; it no longer gates a branch. **Abort criterion: if fewer than ~5 linked ESPN dynasty leagues exist, W3 is deferred behind W1/W2 rather than dropped** — the mechanism also serves Fleaflicker, unknown platforms, and Sleeper/MFL leagues returning `drafts == []`.

**Gate precision:** S-2 gates M12 only; S-3 sizes W3. **W1, W2 and W3 can all start Monday** — nothing blocks on a spike or on an operator credential.

## 4. W1 — Draft-room actions + instrumentation (item 1 depth) · 1 batch · high confidence

Long-press (plus an explicit "⋯" affordance for accessibility) on an undrafted row opens the **shipped** `PlayerContextMenu` with: **Set my value** → anchor sheet calling the shipped `saveAnchor`; **Rank the rookies** (existing jump, now passing a return route so the bridge is two-way); **Add to targets** (existing per-user-per-league asset-pref write). Optimistic re-price + query invalidation. Per-player testIDs. Coverage nudge from `undrafted[].valued` ("N of the top 25 have no value on your board"). Backend: **the `via` whitelist at `server.py:7141` belongs to the TIERS-SAVE route — the lane W1 explicitly forbids. Do not touch it.** Instead add an optional `via`/`surface` body field to `POST /api/anchor/save` (whitelist `{anchors, draft_room}`, fallback `anchors`) and carry it in the `anchor_answered` event props; request-only, so D10's byte-identical-RESPONSE bar is unaffected. Document in api-reference. Also add the missing `track()` events — the Draft Room emits none today.
**Hard constraint:** the anchor lane ONLY. No new surface may call `save_tiers_position` or the merged-band path. Flag `draft.rank_inline`, lands OFF.
*Done bar:* D0, D1, D10.

## 5. W2 — FTF-native mock draft (item 3) · 3.5 batches

Adopt `docs/plans/rookie-draft/mock-draft-plan.md` §4–9 — **now tracked on main (`dc32c2a`); it had been untracked local-only, so the wave it scopes had no spec to read** — with three risk-lens amendments that are binding:
- **CPU basis = market consensus**, explicitly labeled in-UI, never the user's board and never our internal user-influenced Elo. Otherwise every mock reads our rankings back to the user, and where our Elo disagrees with community consensus the bots look dumb and the user blames our values.
- **The noise model is FITTED, not chosen.** We hold a real completed 48-pick rookie draft (`lakeview-complete`). Measure the actual `|pick_no − consensus_rank|` distribution, fit jitter and the reach cap to it, and make the acceptance test "bots replaying Lakeview land inside the fitted band." Reach cap ≤2 slots initially, `model_config`-tunable.
- **Access (the operator's actual item 3):** CTA inside the Draft Room rendered in `upcoming`/`unavailable`/no-draft-object states — **not** restricted to `kind=="rookie"`, because an unscheduled draft is the *primary* mock case; plus the **Acquire chip**, which exists year-round whenever `draft.room` is on, so the mock inherits a 12-month home with **no new tab and no new chip** (the strip already measures ≈402pt vs ≈361pt usable). One canonical deep link on the root stack only.
- **Honest seasonality:** a *real-league rookie* mock needs an undrafted class, so it is dead Sept 2026–Apr 2027 like everything else. The year-round surface is **practice/replay mode** (2026 class vs pre-draft roster snapshots from the M1 corpora) — ship it as the dogfood/QA surface and the calibration harness, **not** as a marketed year-round feature.
*Done bar:* D7, D8, D9, D10.

**M12 — view a Sleeper mock: REJECT unless S-2 passes.** Concretely broken without a league: unreachable by route (`league_not_found`), ownerless slots, empty `my_picks`, no traded-pick overlay, no rostered subtraction, and mocks are typically 15+ rounds ⇒ classified startup ⇒ undrafted suppressed ⇒ the room renders nothing. Even if S-2 passes it is the lowest-value batch here.

## 6. W3 — Asserted availability tracking (item 2) · 3.5 batches · scope CONDITIONAL on S-1

**Store (per-user, ownership-free, append-only):**
```
manual_draft_sessions(id, user_id, league_id, season, platform,
                      mode 'paste'|'live', status 'active'|'superseded'|'abandoned'|'archived',
                      marked_count, created_at, updated_at, superseded_by, superseded_at)
manual_draft_marks(id, session_id, player_id, source 'user_paste'|'user_tap', marked_at)
                      -- NO slot, NO round, NO owner. The schema cannot express ownership.
```
Five properties, each answering a named failure: per-**user** (no cross-user blast radius); **no ownership columns** (keeps manual data structurally out of the trade engine); read by exactly one renderer; **never writes `leagues.draft_status*`**; always labeled in transit.

**The O9 tension, resolved:** O9 rejected a manual *draft-status override* because it makes user input feed `current_year_picks_visible()` → #228 pick hiding → #207 rung labels → asset math. That poison stays rejected. Separate the concepts: **board content** ("who's gone") lives in per-user marks read by one renderer; **visibility** ("should a draft surface appear for me") becomes `userIsTrackingDraft(leagueId)` — a record of the user's own act, not an assertion about the world. `leagueQualifiesForDraftTab()` stays byte-unchanged; the union happens at the call site in a separately-named function. Enforced by D2/D3 plus a test that the shipped predicate's source is unmodified. **If the store is ever made league-scoped or gains ownership columns, O9's objection lands and this must not ship.**

**Composition:** `draft_board_service` is untouched and never imports the manual store. The **route** builds the platform board first; only when it is `unavailable`/`platform_unsupported` (or the league has no current-season draft object) does it hand off to a manual renderer emitting the same `schema:1` envelope with `source:"user"`. New states ride `notice.code` (`manual_available`, `manual_tracking`, `manual_archived`) — never a new member of a closed enum.

**Interaction:** **one tap = taken, no attribution** (the 80% of the value; attribution is the expensive half). Undo always. Persistent "N of 48 recorded." **Paste-recap import ships FIRST** (one action for all 48, reusing the shipped tolerant paste parser + fuzzy pool matcher from `rankings_import`), then live marking.

**Placement:** the League tile and the Acquire chip — **the seasonal tab stays hidden for ESPN in V1** (matching the defect fix in §0.3: no tab without a renderable board). Tab qualification from an active asserted session ships dark and flips only after a pilot.

**Numeric abort:** instrument marks per session. If <40% of started live sessions reach 60% coverage within 24h in the first real window, retire live marking and keep paste-recap only.

## 7. Sequencing, effort, concurrency

```
W1 (1 batch) ──► W2 mock engine ──► W2 mobile ──► W2 access
W3a paste import ──► W3b live marks ──► W3d placement      (unconditional; ESPN has no platform path)
S-2 (optional) ──► M12 go/no-go (recommend: no)
```
| Wave | Batches | Confidence |
|---|---|---|
| W0 spikes | 0.5 | high |
| W1 draft-room actions | 1 | high |
| W2 mock (engine/calibration + mobile + access) | 3.5 | medium |
| W3 manual (store+composition, paste, live, placement) | 3.5 | medium-low (UX is the feature) |
| **Total** | **8.5** | no probe branch — W3 is unconditional |

**Calendar:** it is Aug 2026 — the rookie window is closed until May 2027, so the mock (year-round dogfood, class loaded and valued NOW, validatable against Lakeview) pays rent in the off-season and W1 is cheap-and-done. W3 builds calmly and pilots inside the parent plan's M8 spring rehearsal. **One perishable exception:** ESPN drafts run in the next ~6 weeks — S-1 and any live ESPN validation must happen inside that window or wait until Aug 2027.

**Concurrency discipline:** `backend/server.py` and `database.py` are single-writer resources across ALL waves; W1's `via` edit, W2's routes and W3's routes must never run concurrently. `DraftRoomScreen.tsx` is contended by W1/W2-access/W3 — serialize. Every agent: `git fetch && git merge origin/main` first, abort on conflict; never commit/stash/discard foreign WIP (other sessions are live); check pytest's **exit code**, not the last line; registry/`CLAUDE.md` conflicts resolve by union-dedupe.

## 8. Open questions

- **O1 — CLOSED by operator ruling (2026-08-06): ESPN has no rookie drafts; the probe is cancelled and W3 is unconditional.**
- **O2 — Does ESPN tracking cover a league's OFF-PLATFORM rookie draft only, or also its ESPN redraft?** Given the ruling, the target case is the off-platform rookie draft of an ESPN-hosted dynasty league. Availability tracking is round-count-agnostic so it would also work for a redraft, but that reopens O5 (startup support). Recommend: rookie-only copy and framing in V1; do not advertise redraft tracking.
- **O3 — Confirm manual tracking is NOT offered for Sleeper/MFL transient failures?** (Recommended; it deletes the worst reconciliation case.)
- **O4 — User-asserted pick OWNERSHIP: later or never?** Recommend later, with its own PRD/flag, and only if asserted picks are calculator-visible for the asserting user while excluded from generated suggestions and every leaguemate-facing surface.
- **O5 — Practice/replay mock: shipped feature or QA/tester-allowlist only?** Recommend allowlist — marketing an eight-month-dead feature as year-round earns "this app is broken" in November.
- **O6 — CLOSED:** `mock-draft-plan.md` is now tracked (`dc32c2a`).

## 9. Adopted review notes (non-blocking, binding on implementers)

- **Paste import must discard sequence.** The marks schema cannot express ownership, but `id`/`marked_at` reconstruct *order*. Explicitly discard the paste's index, and test that no route returns marks in a client-consumable order field — otherwise a well-meaning agent persists `overall`.
- **Scope D4's reconciliation tests to the case that can actually fire.** With ESPN having no platform path at all, D4's only live sub-case is a Sleeper/MFL league with `drafts == []` that later gains a draft object. General per-platform supersede machinery is ~half a batch on a path that cannot fire.
- **Name the flags now** so the mirror test has a target: `draft.rank_inline` (W1), `draft.mock` (W2), `draft.manual_tracking` + `draft.manual_import` (W3) — all 4-touch, all land OFF.
- **D1 restated:** "≤3 taps AND no navigation away" (long-press → Set my value → rung is already 3 gestures, leaving none for a confirm step).
- **The Acquire strip already scrolls** (≈402pt content vs ≈361pt usable) — state it plainly; it is the reason no new chip may be appended, not a hypothetical.
- **Predicate docs and `mflBound`** were corrected in `dc32c2a` (required arg; two registry files refreshed).
