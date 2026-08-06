# Plan: Draft-Surface Extensions (rookie-rank bridge · ESPN manual tracking · mock drafts)

**Status: candidate v1 — dual-agent synthesis, under cross-review** · 2026-08-06
Sources: Agent A (execution lens) + Agent B (risk lens), both grounded on `origin/main` @ `3c976cb`.

## 0. Ground truth (verified, both lenses independently)

1. **Item 1 is already built AND flag-on.** `ranks.rookie_subset` and `draft.room` are `true` in prod config. `DraftRoomScreen` renders `draft-room.rank-rookies` in **every** board state → `Main → Rank → RookieRanks`. Three other entries exist. **Nothing to build for the link itself.** Two real gaps remain: the bridge is *one-way* (no return route, lands two hops from any editing gesture), and undrafted rows are inert `View`s with a **shared, non-unique testID** — the flow is currently untestable.
2. **The mock draft feature does not exist.** No service, table, or flag. `docs/plans/rookie-draft/mock-draft-plan.md` is an **untracked, local-only** reviewed draft. So item 3 is build-from-zero, not an entry-point wire-up.
3. **CORRECTED (review round 2).** The tab-predicate guard shipped in `ab5050f` was **inert as first written**, and the "live defect" it targeted was **unreachable**. Two facts, both verified: the leagues route never emitted a `platform` key, so `mobile/src/api/sleeper.ts` coerced every league to `'sleeper'` and the new branch returned `true` for all of them; and MFL/ESPN/Fleaflicker leagues **cannot appear on that route at all** — `load_local_leagues_for_user` filters to non-numeric ids while every linked platform validates numeric ids at link time. So no user has ever seen the MFL phantom tab, and the guard changed nothing.
   **Now made real** (this session): the route stamps `platform` from the draft context, the snapshot key is bumped `v1→v2` (a stale snapshot feeds TabNav at first mount), and `mflBound` is a required argument. The guard is correct defensive work — it becomes load-bearing the moment linked-platform leagues enter that list — but it is **not** evidence about ESPN.
   **The real gap this exposed, and a named prerequisite:** the tab's league source excludes every linked platform league by data path. §6's "tab qualification from an active tracking session" increment silently assumed ESPN leagues were in that list; **they are not**, so that increment must either add a league source or be dropped. Budget it or cut it — do not let a builder discover it.
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
- **The noise model is FITTED, and fit must be SEPARATED FROM VALIDATION.** Fitting jitter to Lakeview and then validating on Lakeview is true by construction — it detects simulator bugs, not a wrong model. Fit on a held-out split (rounds 1–2 → validate 3–4, or k-fold over the 48 picks) AND validate against an independent recorded completion already in the tree (`mfl-complete` 30/30, `mfl-partial` 36/72 — check rookie- vs startup-shape first; `mfl-multi-unit` is startup). State the numeric failure threshold and what happens when it is missed. **W2 abort criterion (it had none): if the noise model fails holdout validation inside the calibration batch, practice/replay ships as a QA-only surface and the CPU-bot mock is cut.**
- **Reuse the shipped consensus seam** (`_get_universal_pool()` → `consensus_seed`, the same source `BASIS_CONSENSUS` uses). A second "market consensus" definition means the room's undrafted order and the mock bots visibly disagree on the same screen.
- **Access (the operator's actual item 3):** CTA inside the Draft Room rendered in `upcoming`/`unavailable`/no-draft-object states — **not** restricted to `kind=="rookie"`, because an unscheduled draft is the *primary* mock case; plus the **Acquire chip**, which exists year-round whenever `draft.room` is on, so the mock inherits a 12-month home with **no new tab and no new chip** (the strip already measures ≈402pt vs ≈361pt usable). One canonical deep link on the root stack only.
- **Honest seasonality:** a *real-league rookie* mock needs an undrafted class, so it is dead Sept 2026–Apr 2027 like everything else. The year-round surface is **practice/replay mode** (2026 class vs pre-draft roster snapshots from the M1 corpora) — ship it as the dogfood/QA surface and the calibration harness, **not** as a marketed year-round feature.
*Done bar:* D7, D8, D9, D10.

**M12 — view a Sleeper mock: REJECT unless S-2 passes.** Concretely broken without a league: unreachable by route (`league_not_found`), ownerless slots, empty `my_picks`, no traded-pick overlay, no rostered subtraction, and mocks are typically 15+ rounds ⇒ classified startup ⇒ undrafted suppressed ⇒ the room renders nothing. Even if S-2 passes it is the lowest-value batch here.

## 6. W3 — ESPN pick assignment · Draft Room state · offline recording (item 2, REVISED)

**Supersedes the prior §6 entirely.** Operator revisions (2026-08-06): picks tie to rosters again; assignment lives on the **League tab, separate from the draft feature**; the ESPN Draft Room shows "picks have not been assigned"; any user may record picks during a real offline draft; **no user-entered values**; **assigned picks are TRADEABLE**.

### 6.0 Prior-plan artifacts this REVERSES (builders must be told)

| Artifact | Status |
|---|---|
| §2 "Out": writing `draft_picks` / flipping `picks_supported` | **REVERSED — now the core of the work** |
| §2 "Out": a board grid with slots/owners; "the schema must not be able to express ownership" | **REVERSED — ownership IS the feature** |
| Prior §6 "standalone, doesn't link to league rosters" | **REVERSED by the operator** |
| **D2** (import-graph proof no manual module reaches the engine) | **DELETED — a builder honoring it cannot build this.** Replaced by D12/D13 |
| **D3** (golden identity with a populated session) | **RESTATED as flag-OFF-only.** Flags ON, responses must change — that is the point |
| **D4** (platform-wins supersede machinery) | **RETIRED from W3** — ESPN has no draft object, ever; nothing can supersede. Recovers ≈0.5 batch |
| §8 O4 ("ownership later or never") | **CLOSED — now, tradeable, staged** |

### 6.1 RESOLVED DISAGREEMENT — storage: write `draft_picks` with a provenance triple

The two lenses split. **Risk lens:** never write `draft_picks` — `replace_draft_picks` is an unconditional DELETE+insert and `pick_id`'s unique key has no user dimension, so a second writer destroys the first and any platform sync wipes the board. **Execution lens:** write it — the grain is *already exactly* `pick_id = {league}_{season}_{round}_{original_roster}`; seven read sites share five pieces of pricing/labelling machinery (including the inverse bridge `inv_pick_value` at `server.py:8655`) that a parallel store must reimplement or adapter-convert into `draft_picks` shape anyway; and **MFL is a working precedent** — `_sync_mfl_owned_picks` builds rows outside the Sleeper sync, stamps `platform`, and calls `replace_draft_picks`.

**RESOLUTION: the execution lens wins, because the risk lens's objection was written for the per-user isolation model the operator has now rejected.** Under shared league truth, one row per slot is *correct*, so the "no user dimension" property is a feature. Its destruction concern is real but hypothetical (nothing calls `replace_draft_picks` for an ESPN league today) and is closed mechanically:
- `replace_draft_picks(..., preserve_source: str | None = None)`; the assignment projection is the only caller passing `'user'`, and every other caller's DELETE is scoped to `source != 'user'` for platforms with no pick ownership.
- **D12** (AST/import-graph) asserts no path outside the assignment routes reaches `replace_draft_picks`/`sync_draft_picks` for a `platform='espn'` league.
- Every write emits a `pick_assignment_changed` user_event, so any loss is reconstructible.

```
draft_picks:  + source       TEXT  -- 'platform' (NULL reads as platform) | 'user'
              + assigned_by  TEXT  -- FTF user_id of last editor
              + assigned_at  TEXT  -- ISO8601; also the optimistic-concurrency token
```
Added through the existing additive-column migration seam (the same one that added `pool_value`/`platform`). No backfill.

**Containment is the default, not a table split.** Both lenses independently converged here: `load_draft_picks(..., source='platform')` **defaults to platform-only**, so all seven existing call sites stay byte-identical until explicitly opted in, one at a time. Safe-by-default, greppable, testable.

**`picks_supported` becomes a DATA test, not a platform test:** `platform != "espn" or bool(assigned_rows)` — ESPN with no assignments still honestly says false. Note (verified by both lenses): `picks_supported` is a **display label only**, appearing twice inside `/api/league/picks`; the two engine guards are **duplicated literals** at `server.py:4571` and `:9310`, not shared — factor them into one `_owned_picks_available()` helper or they drift the moment one is relaxed.

### 6.2 The conservation bound — what the operator's "no values" ruling bought

Because price is a pure server-side function of `(round, season−current, format)` via the **shipped** `pick_pool_value` (the identical function Sleeper's sync uses), and because every owner must be an existing `league_members` row inside a fixed `rounds × total_rosters` grid, this holds provably:

> **Total asserted pick value in a league equals that of an equivalent Sleeper league of the same size. A bad or malicious assignment can REDISTRIBUTE value; it can never CREATE it.**

The only inflation lever is `rounds` — clamp to the shipped `ROOKIE_MAX_ROUNDS = 8` (V1 caps at 5). This is the strongest safety property in the design and it is a direct consequence of the operator's ruling.

### 6.3 Concurrency + disagreement (both lenses' answers, combined)

- **Per-SLOT last-writer-wins with optimistic concurrency** (execution lens): `PUT` carries the `assigned_at` the client read; mismatch ⇒ **409 + current row** ⇒ "Dana changed this 4 minutes ago — keep theirs, or use yours?" Two users fixing two different picks never collide. No locks, no roles, no approval.
- **Persistent disagreement ⇒ contested ⇒ UNPRICED** (risk lens): if the same slot is reassigned to a *different* owner by ≥2 distinct users, mark it contested, **exclude it from the priced union entirely**, and show it as an open question. Rationale: the worst outcome isn't disagreement, it's the engine silently re-pricing back and forth while two people correct each other. A visible hole beats invisible churn.
- **Audit trail is `user_events`**, not a new table — `pick_assignment_changed {league, season, round, original_team, old_owner, new_owner, actor}`.
- **Escalation trigger:** >5% of slots edited by ≥2 distinct users within 7 days ⇒ stop widening; consider commissioner designation. Below that, ship as-is.

### 6.4 Staged read-site enablement — this IS the containment

Do not light all seven at once. Each stage is a release gate.

| Stage | Sites | User gains | Blast radius |
|---|---|---|---|
| **S1** | `/api/league/picks` (8558), `evaluate` (8104) | sees and prices their picks in the calculator | acting user |
| **S2** | power rankings (17230), own outlook seed (4387) | draft capital in standings; better outlook | league-visible, descriptive |
| **S3** | owned-pick injection (8629), opponent shares (4526) | picks appear in **generated suggestions** | unsolicited recommendations about others' assets |
| **S4** | `_roster_eveners` (953) | one-tap "add their 2027 1st" sweeteners | **highest** |

**Ship S1 in this wave; S2 at the pilot; HOLD S3 and S4 until the contested rate is measured.** "FTF told me to ask for a pick I don't own" is the reputational failure that gets an app deleted. Filtering S4 is one predicate.

### 6.5 Milestones

**M-A — assignment (League tab) · flag `picks.assign`.** Store + seeder + routes (`GET/PUT /api/league/pick-assignments`, `POST …/order`) + `PickAssignmentScreen`.
**The 48-tap problem — three defaults, in priority order:** (1) **seed the pristine grid** — every team owns its own picks, so a league with 3 trades leaves 45 slots untouched; (2) **order is set once**, a drag list of N teams for round 1 + a snake/linear toggle — and note the execution lens's finding that **snake vs linear changes slot NUMBERING only, never ownership**, so the toggle is safe; (3) **edit only the traded ones**, which float into a "Traded picks" review summary. Progress explicit, save per-slot, no giant dirty form.
**Entry point: a dedicated "Draft picks" section BELOW Explore** — *not* a 4th Explore tile (that row is a fold-budgeted 3-across grid already contested by `draft.room`/`league.rookie_board_entry`). Sub-line reads "Not assigned yet" / "48 of 48 · 3 traded". This also keeps assignment visibly "separate from the draft feature," as the operator asked.

**M-B — Draft Room ESPN state · same flag.** New `notice.code = picks_not_assigned` (**no new member of any closed enum** — `state` stays `unavailable`); flag off ⇒ byte-identical `platform_unsupported`; assignments present ⇒ a real `upcoming` board (order from the grid, `picks: []`, full rookie class undrafted) with **zero platform egress**. CTA routes to M-A. Note the operator called this an "error" — it is an **unconfigured state with a user-performable fix**, and the copy must read that way.

**M-C — trade-math activation · SEPARATE flag `picks.assign_tradeable`.** The seven sites opt in per §6.4; both engine guards → one helper; provenance `source` on every payload that prices a pick; UI label **"Member-entered — not verified with ESPN"** on all five priced surfaces, each with a one-action correction deep-link (`{leagueId, season, focusPickId}`). **Two flags, deliberately:** trade math can be killed without destroying the 48 rows the user typed.

**M-D — live offline recording · flag `draft.manual_picks` (separate wave).** `recorded_picks(… league, season, round, slot, overall, picking_team_id, player_id, recorded_by, voided_at, UNIQUE(league,season,overall))`. **Both lenses converged and the risk lens retracted its earlier burden argument:** with the grid assigned, attribution costs ZERO extra gestures — the app knows whose pick 1.03 is, so recording stays ~two taps (tap player → confirm) with the cursor auto-advancing, and the team is editable only when the grid was wrong. **One recorder for all 48 picks, any linked user.** Non-destructive undo via `voided_at`. `(league, season, overall)` is the offline-queue idempotency key — **copy `mobile/src/api/events.ts`'s battle-tested AsyncStorage queue contract verbatim** (uuid idempotency, backoff, foreground flush, `{accepted, deduped, rejected}` reconciliation); do not invent a second one. **`overall` is legitimate here and must never leak backwards onto a `draft_picks` row.**

### 6.6 Two live defects this wave inherits

- **P-1 (BLOCKING for M-A, live TODAY):** `useSession.connectLeague` **replaces** the league cache with `/api/sleeper/leagues` output, which filters to non-numeric ids and therefore contains **no ESPN league**. So connecting any Sleeper league mid-session silently drops every ESPN row — the ESPN re-sync button already disappears this way, and the assignment tile would inherit it. **Fix (≈6 lines + test, owned by M-A): make `connectLeague` MERGE, preserving cached rows whose platform is not `sleeper`.**
- **P-2 (out of scope, budgeted):** the seasonal Draft tab stays ESPN-blind — three independent guards (the non-numeric filter, the predicate's ESPN line, and the `confidence === 'high'` requirement ESPN can never meet). Under the revision the League tab is the entry point, so this is not needed. If ever wanted: 0.5 batch, its own gate. **Recommend: cut for V1.**

### 6.7 Done-criteria (replacing D2/D3/D4 for this wave)

| # | Criterion |
|---|---|
| **D12** | Containment by default: `load_draft_picks` defaults `source='platform'`; an AST test enumerates every call site and asserts only the sanctioned set opts in; no path outside the assignment routes reaches `replace_draft_picks`/`sync_draft_picks` for an ESPN league; no path writes `leagues.draft_status*` from user input (**O9 survives, pinned behaviorally — not by source-text identity**) |
| **D13** | **No user-entered values, ever.** No assignment route accepts a value field; every `source='user'` row's price is byte-equal to `compute_pick_value`/`pick_pool_value` for its (round, years_out, format). Conservation bound property-tested |
| **D14** | Pristine-seed correctness: exactly R×N slots, each owned by its original team, idempotent re-seed, orphaned owner ids surface as re-assign rows and are excluded from pricing — never silently dropped |
| **D15** | The ESPN room is honest in all three states (flag off / assigned-none / assigned-some), zero platform egress |
| **D16** | Concurrent edits never silently clobber (409 on stale CAS; different slots both succeed); every write emits its audit event |
| **D17** | Provenance is inescapable: `source` on every payload that prices an asserted pick + the label and correction path on all five priced surfaces |
| **D18** | Recording is idempotent and non-destructive; replaying the offline queue changes nothing; `overall` never appears on a `draft_picks` row |
| **D10** | Both new flags OFF ⇒ byte-identical on all seven sites + board/picks/evaluate/power-rankings; zero new entry points; `schema` stays 1 |

### 6.8 Effort, risks, aborts

W3 grows **3.5 → ≈5.25 batches** (ownership was previously explicitly out of scope); plan total ≈**10.25**, offset ≈0.5 by retiring D4.

| Risk | Numeric abort |
|---|---|
| **Adoption — nobody completes the grid**, so everything downstream is inert (highest-probability failure, and measured before the expensive halves matter) | <50% of started grids reach 100% within 72h in the pilot ⇒ cut M-C and M-D; keep assignment as a draft-board-only surface |
| Live recording abandoned in a real draft room | <40% of started sessions reach 60% of slots in 24h ⇒ retire recording, keep the grid + board (which stand alone). **Report split by whether a grid existed**, or it conflates two failures |
| Offline queue integrity | **Zero tolerance** — any duplicate or lost pick after reconnect ⇒ recording stays on the allowlist. That is an idempotency bug, not a UX metric |
| Containment | If D10's golden diff cannot be made green on any un-opted site, the wave **stops at M-A** |
| Persistent multi-user disagreement | >5% of slots contested in 7 days ⇒ S3/S4 do not open |

### 6.9 Residual risks the operator is accepting knowingly

1. **A leaguemate can change what FTF recommends to you.** Inherent to shared truth. Bounded by the conservation bound, contested-⇒-unpriced, one-action correction, and staged propagation — but not engineerable away.
2. **There is usually no corrector.** Most ESPN leagues will have exactly one FTF user, so the realistic failure is one person's honest mistake persisting unnoticed — wiki mechanics without a wiki-sized crowd. This is why entry correctness (pristine seed, confirm-the-board step) matters more than conflict resolution.
3. **No self-healing.** Unlike Sleeper/MFL, ESPN will never contradict a wrong grid. A bad assignment is wrong until a human fixes it.
4. **Spent picks linger** unless retired — current-season assigned picks should hard-retire on a fixed date (Sept 1) in addition to the existing rosters-heuristic path.
5. **Provenance is a badge, and users skim badges.** Structural disclosure still reads as "FTF says" to some users — the strongest argument for holding S4.

### 6.10 Open questions needing the operator

- **O-D1 — Snake or linear default?** (Numbering only, never ownership — so the toggle is safe either way.) Recommend **linear** for rookie drafts; confirm.
- **O-D2 — Default rounds?** Recommend **4**, capped at 5 in V1.
- **O-D3 — Future seasons (2027/2028/2029 picks)?** The operator described 1.01–4.12 (this year). But **most dynasty pick value lives in future firsts**, and the pristine-seed default makes the seeder change a loop bound — though the grid becomes ~4× larger to review. Recommend **current season in V1, future seasons as the first follow-on** (expect it to be requested the moment trade math lights up).
- **O-D4 — Do assigned picks enter generated suggestions (S3/S4) at all in V1?** Recommend **no** — S1/S2 only, gate S3/S4 on the measured contested rate.
- **O-D5 — Rookie-only framing?** Assignment is round-count-agnostic and would work for an ESPN redraft, but that reopens O5 (startup support). Recommend rookie-only copy in V1.
- **A new ADR is warranted** — "user-asserted pick ownership is league-scoped truth in `draft_picks`" reverses a documented invariant and must not live only in a plan file.

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

---

## Operator decisions — ESPN pick assignment (2026-08-06). BINDING.

1. **Draft order default: LINEAR** (user-toggleable to snake; the toggle changes slot numbering only, never ownership).
2. **Rounds default: 4, and USER-SETTABLE.** Not a fixed constant — expose it in the assignment setup, clamped 1–`ROOKIE_MAX_ROUNDS` (8). The conservation bound (§6.2) depends on that clamp, so it is enforced server-side, not just in the UI.
3. **Future seasons ARE included: current + 3** (matching Sleeper's `seasons_ahead=3`). Consequences the build must handle, since this is ~4× the prior grid:
   - Seeder loops `range(season, season+4)` — a loop bound, effectively free.
   - **UX is NOT free.** A 12-team × 4-round × 4-season grid is ~192 slots. The screen must default to the **current season** with the other three seasons collapsed behind season tabs/accordions; the pristine-seed default means users still touch only traded picks, but the "confirm the board" review step must be **per-season**, not one 192-row scroll.
   - Pricing already handles it: `pick_pool_value(round, years_out, format)` is the shipped function and `years_out` discounts are existing behavior. No new value logic.
   - This is where most dynasty pick value lives, so it is also where a wrong assignment costs the most — the provenance label and one-action correction matter more here than in the current season.
4. **Assigned picks behave EXACTLY like any other league's picks — full engine parity.** All seven read sites light up, including `_roster_eveners` (S4) and generated suggestions (S3). **This overrides both lenses' recommendation to hold S3/S4 behind measured gates.**
   - **Staging survives as a BUILD SEQUENCE only, not as release gates:** implement and golden-diff S1 → S2 → S3 → S4 in that order within the wave so each site is verified independently, but all four land together behind `picks.assign_tradeable`.
   - The adoption / contested-rate / offline-integrity thresholds in §6.8 remain as **monitoring and rollback triggers**, not as ship gates.
   - Residual risk (§6.9 item 1) is **accepted knowingly by the operator**: a leaguemate's assignment can change what FTF recommends to you, including active "ask for their 2027 1st" sweeteners. Containment is unchanged — conservation bound, contested-⇒-unpriced, provenance label on every priced surface, one-action correction, and `picks.assign_tradeable` as a single kill switch that never destroys entered data.
