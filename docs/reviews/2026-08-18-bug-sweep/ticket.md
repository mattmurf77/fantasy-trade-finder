# Bug resolution ticket — 2026-08-18 operator sweep (B1–B5)

> **Purpose:** root causes, verified evidence, and agreed fixes for five operator-reported bugs.
> Every file:line in this ticket was re-verified by the orchestrator against `origin/main`
> (`90fb19a`) after the research agents reported. Branch: `fix/bug-sweep-2026-08-18`.

## Table of Contents
- [Provenance and method](#provenance-and-method)
- [B1 — Analyst spotlight does not track scroll](#b1--analyst-spotlight-does-not-track-scroll)
- [B2 — Tier-target chips drop players to the bottom](#b2--tier-target-chips-drop-players-to-the-bottom)
- [B3 — Picks filter shows a blank sheet](#b3--picks-filter-shows-a-blank-sheet)
- [B4 — Pass stalls permanently after a failed swipe](#b4--pass-stalls-permanently-after-a-failed-swipe)
- [B5 — Draft picks render as raw IDs on Matches](#b5--draft-picks-render-as-raw-ids-on-matches)
- [Cross-cutting decisions](#cross-cutting-decisions)
- [Verification baseline](#verification-baseline)

---

## Provenance and method

Five research agents investigated in parallel against a clean worktree branched from freshly
fetched `origin/main`. **The first round was discarded**: it ran against a checkout 151 commits
stale, where `TradesScreen.tsx` alone differed by ~1,200 lines. All findings below come from the
second round and were independently spot-checked by the orchestrator.

Reported severity order (ship priority): **B4 > B3 > B5 > B2 > B1**.

---

## B1 — Analyst spotlight does not track scroll

**Reported:** the guided-onboarding highlight box stays at a fixed screen position when the user
scrolls, instead of staying locked to the feature it points at.

**Root cause.** The spotlight frame comes from a one-shot `measureInWindow()` taken when the step
activates and never again. `measureInWindow` returns absolute *window* coordinates, so the moment
the host `ScrollView` moves, the target's real position changes while the cached frame does not.
There is no scroll listener anywhere in the guide path.

**Verified evidence**
- `mobile/src/state/guideTargets.ts:19-39` — `measureGuideTarget`, the only measurement primitive; `measureInWindow` with a 250 ms timeout resolving `null`.
- `mobile/src/components/AnalystGuide.tsx:63-86` — the measuring effect; deps are `[active?.id]` **only**, so it never re-runs on scroll.
- `config/features.json:92,95` — `onboarding.guided_avatar: true`, `onboarding.guide_v2: false`. **The live path is v1**, i.e. the local `measureGuideTarget` call, not the v2 engine.
- `mobile/src/components/AnalystGuide.tsx:147` — overlay root is `<View style={StyleSheet.absoluteFill}>`. **Not a Modal** (verified: no `Modal` import in the guide chain), so it *can* be made to follow in-page scroll without re-architecture.
- `mobile/src/navigation/RootNav.tsx:852` — mounted once, globally, as a sibling of `Stack.Navigator`.
- `mobile/src/screens/TradesScreen.tsx:4530-4537` — the host `ScrollView` already has an `onScroll`, but it is gated on `declineReasonsOn` and only writes a ref; nothing notifies the guide.
- `mobile/src/screens/LeagueSummaryScreen.tsx:1480` — host `ScrollView` with **no `onScroll` at all**.

**Fix**
1. `guideTargets.ts` — add a minimal pub/sub (`subscribeGuideTargetsMoved` / `notifyGuideTargetsMoved`) so hosts never import guide internals. No subscriber ⇒ no-op over an empty Set.
2. `AnalystGuide.tsx` — one effect, armed only while a spotlight step is active and a frame is already resolved. Coalesce with `requestAnimationFrame` + an in-flight guard. **A `null` re-measure keeps the last good frame** — it must never re-enter the degrade path.
3. `AnalystGuide.tsx:130` — **latch the placement decision.** `targetInBottomBand` re-solves every render; once the frame tracks scroll, the avatar/bubble band would flip between `{top:54}` and `{bottom:92}` mid-fling. Latch `atTop` in a ref for the life of the step.
4. `AnalystGuide.tsx:135-142` — the cutout clamps `x`/`y` via `Math.max(0, …)` but **not** `height`. Inert today because the frame never moves; once it tracks, a target scrolled above the viewport smears against `y=0`. Drop the scrim/ring entirely when the frame leaves the viewport instead of clamping.
5. Hosts: `TradesScreen.tsx:4530-4537` — make `onScroll` unconditional and call `notifyGuideTargetsMoved()`; `LeagueSummaryScreen.tsx:1480` — add `onScroll` + `scrollEventThrottle={16}`. `SignInScreen` has no scroll container; no change.
6. Fix **both** v1 and v2 paths, or it will appear fixed in v2 QA and stay broken in production.

**Rejected alternatives.** `Animated.event` + native-driver offset subtraction is pixel-locked but a
much larger diff (every host writes an `Animated.Value`, scrim panels must be over-sized, scroll
origin baseline captured) and still only fixes *vertical* scroll — keyboard insets and layout shifts
would still desync. Hold in reserve if QA sees the re-measure trail during a fast fling.
Moving the highlight inside the scroll content is out: `AnalystGuide.tsx:17-19` documents the
single global mount as deliberate.

**Risk.** Medium — touches a live onboarding surface. Mitigated by the latch (3) and viewport-exit
(4); without those the fix trades one bug for a worse one.

---

## B2 — Tier-target chips drop players to the bottom

**Reported:** pushing a player down a tier should land them at the **top** of the next tier, not the bottom.

**Root cause — not where it looks.** The "Tier down" button is **already correct**. The bug lives in
the two *other* non-drag paths: the tier-target chips ("Move to 3rd") and the VoiceOver
"Move to \<tier\>" action, both of which unconditionally append to the END of the destination tier.
The chips row sits above the Tier up/down buttons in the multi-select bar and is the more obvious
"send this player to that tier" affordance.

**Verified evidence**
- `mobile/src/screens/TiersScreen.tsx:1593-1594` — `moveTierByOne`: `direction === 'up'` appends to the bottom of the higher tier; **`else next[to] = [...movers[from], ...next[to]]`** — down already inserts at index 0. Correct as-is.
- `mobile/src/screens/TiersScreen.tsx:613` — `moveSelectedToTier`: `next[target] = [...next[target], ...movers];` ❌ **bottom**
- `mobile/src/screens/TiersScreen.tsx:633` — `movePlayerToTier` (a11y): `next[target] = [...next[target], player];` ❌ **bottom**
- `backend/ranking_service.py:1419-1427` — the submitted array index is spread linearly across the tier's Elo band (`hi - (hi-lo)*i/(n-1)`), strictly monotonic. **Client order round-trips faithfully; persistence is not the culprit.**
- `docs/data-dictionary.md:112` — `tier_overrides` stores raw Elo; tier keys are never stored.

**Fix.** Make both sites direction-aware, mirroring the `TIERS.indexOf` idiom already at `:1580-1585`:
movers whose source tier is *above* the target (moving down) prepend in order; movers from *below*
(moving up) append in order. A pool (`unassigned`) source keeps today's append. Update the three
stale comments at `:594-597`, `:611-612`, `:646-648`.

**Leave untouched:** `moveTierByOne` (`:1560-1598`), `bulkMove` (`:508`), `onDragEnd` (`:792`).

**Decisions taken** (see [Cross-cutting decisions](#cross-cutting-decisions)): direction-aware for
**all** jumps, not just adjacent; **"move up" stays as-is** (bottom of the higher tier — the
documented minimal-displacement rule at `:1552-1555`; the operator asked only about *down*).

**Confounder to avoid during QA.** Verify on a **single-position** tab. On the "All" board the save
splits into four per-position calls and the cross-position interleave is re-derived on reload
(`TiersScreen.tsx:340-381`, documented at `:345-350`), so a *correct* fix can still look wrong there.

**Risk.** Low — two `useCallback` bodies in one file. No backend, schema, API, or flag surface.

---

## B3 — Picks filter shows a blank sheet

**Reported:** filtering to "picks" when adding trade assets shows a blank screen instead of owned picks.

**Root cause.** The picker's filter compares one field (`p.pos === posFilter`) against a pool where
generic draft picks carry a **fake player position**. `build_universal_pool` deliberately stamps the
12 generic rungs with `_PICK_POS = {1:"RB", 2:"WR", 3:"TE", 4:"QB"}` and marks them as picks via
`team == "PICK"` instead. So "Early 1st Round Pick" is served as an **RB**, the PICK chip matches
zero rows, and the RB/WR/TE/QB chips wrongly list draft picks. With no `ListEmptyComponent`, a
zero-match filter paints an empty sheet with no explanation.

**Verified evidence**
- `mobile/src/components/PlayerPickerModal.tsx:114` — `.filter((p) => (posFilter ? p.pos === posFilter : true))` — the single-field predicate.
- `mobile/src/components/PlayerPickerModal.tsx:36` — `const POSITIONS: CalcPos[] = ['QB','RB','WR','TE','PICK'];`
- `backend/server.py:1464,1477-1478` — `_PICK_POS = {1:"RB",2:"WR",3:"TE",4:"QB"}`; the pool entry is built with `position = pick_pos`, `team = "PICK"`.
- `backend/trade_service.py:1138-1147` — the canonical predicate `is_pick_asset`: `position == "PICK" **or** team == "PICK"`. Its own docstring states generic picks "carry a REAL position so they mix into the trio tabs, but are always `team == 'PICK'`".
- `mobile/src/components/PlayerPickerModal.tsx` — **no `ListEmptyComponent`** (verified absent).
- `mobile/src/screens/TradeCalculatorScreen.tsx:111` — `useState<CalcMode>(prefill ? 'league' : 'live')`; **"Real values" (live) is the default mode**, which is the always-blank one.

**Per-mount verdict**

| Mount | Pool | PICK filter today |
|---|---|---|
| Calculator **live / "Real values"** (default) | `/api/trade/values` | **BLANK always** — picks present but typed RB/WR/TE/QB |
| Calculator **demo** | `tradeCalcMock` | works (`pos:'PICK'`) |
| **In-league** calculator | roster + `/api/league/picks` | works on Sleeper/MFL; **blank on ESPN** (`picks_supported:false`) |
| TradesScreen FB-47 target picker | roster ids | **BLANK always** — rosters carry no pick ids |

**Fix** (all client-side, `PlayerPickerModal.tsx`):
1. Mirror the backend predicate: `const isPickAsset = (p) => p.pos === 'PICK' || p.nflTeam === 'PICK';` — with a comment citing `trade_service.is_pick_asset` so the magic string can't drift silently.
2. Replace the `:114` filter with the two-sided rule so picks also stop leaking into the QB/RB/WR/TE chips (the #222 half of the bug).
3. Add a `ListEmptyComponent` regardless — it is the correct answer for the ESPN `picks_supported:false` case and the TradesScreen mount. Scoped copy: "No draft picks available here." under the PICK filter, "No players match." otherwise.

**Do NOT** change `_PICK_POS` server-side: the fake position is load-bearing for trio/rank
position-tab distribution and would ripple through five clients and the tier-occupancy tests.

**Not a regression from #330** — that commit never touched `PlayerPickerModal.tsx`.

**Risk.** Low, additive — no row disappears from `ALL`; the position chips only lose rows that were never legitimate.

---

## B4 — Pass stalls permanently after a failed swipe

**Reported:** `jonbonjourvi` (league FFv3) tapped the red ✕ to pass on a 2×2026-1sts-for-AJ-Brown
suggestion; the card stayed on screen with no way past it and no error shown.

**Build context.** The ✕ is replaced by Value/Fit/Neither tiles when `feedback.decline_reasons` is
on (`TradeCard.tsx:560`), which shipped in `00b2a2c` → **v1.14.0 build 116**. Build 114 (v1.13.5)
still renders the ✕. The user was on a pre-116 build. **The defect is byte-identical on current
`main` — this is not fixed.** Also note `feedback.decline_reasons` is absent from
`LAUNCHED_FLAG_DEFAULTS` (`mobile/src/state/useFeatureFlags.ts:45-89`), so the legacy ✕ path is
still reachable on first paint even on build 116.

**Root cause (mechanism: high confidence).** A pass that fails on the server **rewinds the deck to
re-front the card but never clears the double-fire guard**. Every subsequent ✕, ✓, or swipe on that
card is then a silent `return`. Permanent stall, no error, no visual change.

**Verified evidence**
- `mobile/src/screens/TradesScreen.tsx:1823-1834` — `swipeMutation.onError` rewinds: `if (prevCard && prevCard.trade_id === rawId) return cur - 1;` — the same card is fronted again.
- `mobile/src/screens/TradesScreen.tsx:3846-3847` — the guard: `if (lastDispositionedRef.current === dispatchRawId) return;` — **bare return**, decision-agnostic, so ✓ and the swipe gesture are dead too.
- **All six clear sites** are `:897, :1706, :2076, :2265, :2434, :2590` — verified by grep; **`onError` is not among them**. Two of those sites clear the ref for *exactly* this reason, including `:2586-2590` whose comment reads: *"A lane change can legitimately re-surface an already-dispositioned card at the top … clear the double-fire guard so re-swiping it isn't no-oped."* The omission in `onError` is an oversight, not a design.
- `config/features.json:124,205` — `ux.swipe_undo: true`, `feedback.decline_reasons: true`. Both live.

**Why no error was visible**
- `UNDO_HOLD_MS = 5000` (`:204`) — the POST is held 5 s before firing, so the failure lands long after the tap.
- `TradesScreen.tsx:4423` — `holdMs={toast?.holdMs ?? 1500}`; the warn toast flashes for 1.5 s.
- The toast says "try again" — and the retry is the no-op. The advice cannot work.

**Trigger (unproven — ranked).** No prod logs available. `/api/trades/swipe` is in `NO_RETRY_PATHS`
(`mobile/src/api/client.ts:240-246`) while `RETRY_STATUSES` is `{502,503,504}` — so a gateway error
on swipe is **never** retried, unlike every other transient.
1. Render 502/503 during cold start or deploy (most likely).
2. `409 session_not_initialized` (`backend/server.py:2319-2335`).
3. `403 verification_required` (`backend/server.py:2405-2429`) — **persistent, not transient**; would fail every swipe, which fits "no way to move past it" even better. `ApiError.isVerificationRequired` exists but `onError` never checks it.
4. 15 s deadline timeout.

**Hypothesis explicitly disproven.** The pick-heavy package is *incidental*. `trade_id` is
server-minted and echoed verbatim (`mobile/src/api/trades.ts:409`); nothing is client-generated or
hashed. Picks are ordinary entries in `give_players`, so a pick-only side yields a non-empty id
array. The stale-deck path is already covered by `_reconstruct_swipe_card`
(`backend/server.py:10621-10652`).

**Fix**
- **(a) The failure.** In `onError`, clear the guard whenever the deck rewinds — mirroring `:2076` and `:2590`. Also clear unconditionally when the poisoned id matches `ctx.rawId`, so the no-rewind case leaves nothing behind.
- **(b) Visibility and recovery.**
  1. Give the failure toast a real hold (`holdMs: 6000`) and a **working** Retry action — requires capturing `card`/`decision`/`signal` into the `onMutate` context (`:1789-1801` currently returns ids only).
  2. Route `verification_required` to its own copy — retrying can never succeed there.
  3. Close the **second live strand** found on build 116+: `DeclineReasonPanel.tsx:178` — tapping the already-open tile collapses layer 2 without committing, while the pass is already banked, so ✓ is disabled and swipe is inert with no visible way forward (`TradesScreen.tsx:5837-5842`, `:3838-3844`). This is `D-b` in `docs/plans/decline-reason-capture/scope-mobile.md:239-243` — deliberate, but it did not consider the collapse case.

**Deliberately NOT doing:** the proposed `swipe_guard_blocked` analytics event. A new event needs a
`backend/analytics_taxonomy.py` row, which crosses the CLAUDE.md bright line; it is not required to
fix the bug. Flagged for the operator as a follow-up.

**Observability gap worth recording.** Nothing records the guard's `return`. A user could tap ✕ fifty
times and produce zero events. Sentry is initialized (`mobile/app.json:65`) but `captureException`
is never called on the swipe path. The one usable signal is `api_request_failed`
(`mobile/src/api/client.ts:353-381`) — **querying that for this user's `/api/trades/swipe` would
settle the trigger ranking above.**

**Risk.** Re-arming the guard narrows double-fire protection: if a tap and a gesture both fire *and*
the first POST fails inside that window, two passes could be recorded. Low impact — the backend pass
path is effectively idempotent (`save_trade_decision` writes one row per `(user, league, trade_id)`;
the D-067 cooldown key is a `frozenset` added to a set). Cost is a duplicate Elo signal, bounded by
`trade_k_pass`. Leaving a user permanently stuck is strictly worse.

---

## B5 — Draft picks render as raw IDs on Matches

**Reported:** the "Awaiting them" section shows picks as a long ID string instead of the pick name.

**Root cause.** The serializer builds its name map exclusively from the `players` table and falls
back to the raw id: `player_name_by_id.get(pid, pid)`. Draft picks are never rows in `players` —
they live in `draft_picks`, keyed `{league_id}_{season}_{round}_{original_roster_id}`. So every pick
is emitted verbatim as its own "name". **The client is doing the right thing**; it has no pick
metadata to compose a label from.

**Verified evidence**
- `backend/server.py:14163-14164` — `/api/trades/awaiting`: `[player_name_by_id.get(pid, pid) for pid in give_ids]`. Map populated only from `players_table` at `:14150-14154`.
- `backend/database.py:884` — `pick_id format: "{league_id}_{season}_{round}_{original_roster_id}"`.
- `mobile/src/shared/types.ts:281-291` — `AwaitingTrade` carries no positions, teams, or pick metadata. There is no correct field the client is failing to read.
- `backend/server.py:9605-9613` — `_owned_pick_label`, the canonical formatter: `"2027 1st"`, or `"2026 2nd (from Jared)"` when traded. **Connector is `(from …)`, not `(via …)`** as the original report guessed.

**Scope correction — three sibling routes have the same defect.** The premise that "Mutual matches"
works is wrong at the code level:
- `backend/server.py:14076-14077` (`/api/trades/matches/all`) — identical `get(pid, pid)` defect; mutual matches show raw ids too.
- `backend/server.py:13965-13968` (`/api/trades/matches`, **the route web calls**) — worse: `[players_dict[pid].name for pid in m["my_give"] if pid in players_dict]` **silently drops** picks, so a 2-for-1 renders as 1-for-1 (parallel-array misalignment).
- `backend/server.py:14585-14588` (disposition refresh) — same shape.

The genuinely working reference is the **deck**, not Matches: `trade_card_to_dict`
(`backend/server.py:10091-10095`) resolves through the pool that `_inject_owned_picks` primed with
`name = _owned_pick_label(p)` (`:9788`).

`MockDraftScreen.tsx:1224` `pickLabelOf` is a **local one-off** formatting a draft-board slot
coordinate (`1.05`), unrelated to asset naming. There is no client-side pick-name formatter in
`mobile/src` by design.

**Fix — backend layer.** Add `_pick_labels_by_id()` next to `_owned_pick_label`, resolving generic
rungs via `generic_pick_label` and owned picks via one `IN` query on `draft_picks.pick_id` (uniquely
indexed). Overlay it after the players map at all four sites:
`player_name_by_id.get(pid) or pick_label_by_id.get(pid) or pid`. At `:13965-13968` **also drop the
`if pid in players_dict` filter** so the arrays stay index-parallel.

**Why backend.** The label cannot be composed client-side without shipping `season`/`round`/
`original_username` to three clients; `_owned_pick_label` is already canonical; and
`docs/cross-client-invariants.md:520` explicitly forbids re-authoring the display string per client.
Decisively: **a Render deploy fixes every already-installed TestFlight build with no app release.**

**Guard rails.** Real Sleeper player ids are digit-only, so a `not p.isdigit()` guard keeps the extra
query off the hot path entirely for pick-free payloads. Do **not** fold provenance into the label —
`cross-client-invariants.md:520` forbids it.

**Web.** Web has **no** awaiting list (`web/js/app.js:5093-5094` is a numeric tile only), but its
mutual-match list consumes `/api/trades/matches` and therefore shows the silently-short side. Fixing
at the backend layer repairs web in the same change.

**Out of scope (noted, not fixed):** `AwaitingTrade` carries no positions/teams at all, so the
adapter hardcodes `FLX` for every asset (`MatchesScreen.tsx:1437-1448`). After this fix a pick reads
`2026 1st` with an `FLX` chip. Separate pre-existing gap.

**Risk.** Low. One bounded `IN` query per request on three routes, skipped entirely when no
non-digit ids are present; `load_awaiting_trades` is already capped at 500 rows
(`backend/database.py:7653`). Response *values* change on four routes, but no field, route, flag, or
event is added.

---

## Cross-cutting decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | **B2: direction-aware for all jumps**, not only adjacent tiers | Direct reading of the operator's request. A far jump landing at the top of the destination is a strong value claim, but consistency with the Tier-down button matters more than the edge case. Flagged for review. |
| D2 | **B2: "move up" left unchanged** (bottom of the higher tier) | The up/down asymmetry is deliberate and documented at `TiersScreen.tsx:1552-1555` as minimal-displacement. The operator asked only about *down*. |
| D3 | **B3: no server-side `_PICK_POS` change** | Load-bearing for trio/rank position-tab distribution; changing it ripples through five clients and the tier-occupancy tests. |
| D4 | **B4: no new analytics event** | `swipe_guard_blocked` would need a `analytics_taxonomy.py` row — crosses the CLAUDE.md bright line and is not needed to fix the bug. Follow-up. |
| D5 | **B5: fix at the backend**, all four routes | Fixes every installed build via Render with no app release, and repairs web in the same change. |
| D6 | **Sim gate not run** | Maestro/simulator work was retired 2026-08-15 (D-056). TestFlight is primary QA; `FTF_SKIP_SIM_GATE=1` is standing posture. Two agents' test plans cited the retired gate — disregarded. |

**Gate posture.** The operator did **not** declare express, so full gates are the default. B5 changes
API response *values* (not contracts) on four routes; B4 touches a shipped, flag-scoped UX decision
(`D-b`). Both are called out here rather than waived silently. No schema, no new route, no new flag,
no new event across the whole sweep.

---

## Verification baseline

Captured on `origin/main` (`90fb19a`) **before** any edit, so every post-fix failure is attributable:

| Check | Result |
|---|---|
| `python -m pytest backend/tests -q` | **3125 passed, 1 skipped** (301 s) |
| `npx tsc --noEmit` (mobile) | **clean, 0 errors** |
| `for f in tests/check-*.js; do node "$f"; done` | **all pass** |
| `bash mobile/scripts/testid-lint.sh` | **OK** |

Existing suites to extend rather than duplicate: `check-awaiting-dismiss.js`,
`check-guide-script.js`, `check-decline-reasons.js`, `check-calc-pick-tiers.js`,
`check-single-pin-actions.js` (the source-assertion idiom).

---

## Review round — what the adversarial pass changed

Each bug's original research agent reviewed the fix built from its own analysis. The reviews
found **four real defects** plus one factual correction to this ticket. All are resolved.

| ID | Finding | Severity | Disposition |
|---|---|---|---|
| R1 | **B2: same-tier double-tap teleport.** Selection persists after a chip tap, so tapping "3rd" twice moved the player to the top of 3rd, then back to the bottom — reproducing the reported symptom. New regression, introduced by this sweep. | High | **Fixed.** A player already in the destination is a no-op in both handlers (`t === target` skipped in the gather; `fromIdx === targetIdx` returns `prev`). |
| R2 | **B2: the test could not detect an inverted comparison.** Reviewer flipped both guards — shipping the exact opposite behavior — and all 12 assertions passed green. | High | **Fixed.** Test rewritten to lift the updater bodies out of source and assert real placement. Inversion now fires 10 assertions. |
| R3 | **B5: `test_digit_only_ids_skip_the_pick_query` could never fail.** It raised `AssertionError` inside a block guarded by `except Exception`, which swallowed it. Proven empirically. | High | **Fixed.** Rewritten against a connection spy — an observable the `except` cannot swallow — with a positive control. |
| R4 | **B1: viewport-exit handled the endpoint, not the transit.** A target scrolling past the top edge kept full height while its top clamped to 0 — a frozen oversized ring for the whole transit (hundreds of points on `trades.card-body`). | Medium | **Fixed.** The cutout now clamps the span by the same delta as the origin. |
| R5 | **B3: the empty state lies during load.** `filtered === []` rendered "No players match." while the pool was still in flight — and on TradesScreen the queries are *enabled by the picker opening*. | Medium | **Fixed.** `loading` prop added and wired at all four mounts, following the `SwapPlayerSheet` house pattern. |
| R6 | **B5: pool-miss players emitted raw ids.** `sess["players"]` is the universal pool (~691), not the full player table, so a player who fell out of it rendered as a bare id where the old filter showed `—`. | Medium | **Fixed.** All four routes now share one ladder: session pool → `players_table` → pick label → raw id, with only misses passed to the fallbacks. |
| R7 | **B3: chip testIDs were UPPERCASE**, breaking convention and invisible to `testid-lint.sh`'s lowercase-only extractor — a flow referencing them would pass by accident. | Low | **Fixed.** Lowercased. |
| R8 | **B4: guard-clear assertion was text containment**, so keying the clear on `ctx.tradeId` (the `::edited` id) instead of `ctx.rawId` would have passed while silently restoring the bug for edited cards. | Low | **Fixed.** Assertion now pins `ctx.rawId` specifically. |

### Correction to this ticket

**B4's risk section claimed the backend pass path was "effectively idempotent."** That was wrong.
`save_trade_decision` (`backend/database.py:4794`) is a plain `INSERT` with no upsert and no unique
constraint on `trade_decisions`. A duplicate pass writes a second row, a second `trade_swipes` row,
and replays `trade_k_pass` twice.

**This changed a decision.** The fix had added a **Retry** action to the failure toast. With the
guard cleared, the card's own ✕ re-POSTs *and* advances the deck — strictly more than Retry, which
would re-POST while leaving the card fronted and invite exactly the duplicate the `INSERT` makes
costly. **Retry was removed**; the toast now reads "Swipe didn't save. Tap again to retry.", which
is honest because it is now true. The 403 branch keeps its own copy and points at the verify banner
the same failure raises.

### Accepted risks (recorded, not fixed)

- **B4:** re-arming the guard opens a duplicate-record path that the stall previously prevented — a swipe that succeeded server-side but lost its response now lets the user re-pass. Right trade (a permanent trap is worse), but real given the plain `INSERT`. → **G-049**.
- **B1:** hosts now emit `onScroll` at 16 ms unconditionally. No regression on Trades (the flag gating it was already `true` in prod); genuinely new on LeagueSummary, where the handler is a walk over an empty Set. Gate on `!!active?.target` if a fling ever feels heavy.
- **B1:** a *partially* offscreen frame is now clamped correctly, but layout-driven movement (a banner mounting and shifting the target with no scroll event) is still unhandled. Distinct trigger from the reported bug; deliberately out of scope. → follow-up.
- **B5:** a pick-only miss set includes pick ids in the `players_table` query where they cannot match — one wasted predicate, not a wasted query. Simplicity preferred over duplicating pick-id parsing at the call site.

### Deferred (logged, not in this sweep)

- **The web client has B3's bug too**, on a chip literally labeled "Picks" (`web/index.html:635`, `web/js/app.js:3156/3184/3219`). Both pools are roster-scoped and hold zero picks, so the tab is permanently empty with no empty state. Same shape, now diverged from mobile.
- **No `swipe_guard_blocked` analytics event** (D4). The stall remains invisible in telemetry — a user could tap ✕ fifty times and produce zero events. Needs an `analytics_taxonomy.py` row, which crosses the bright line.
- **`/api/trade/values` could emit an explicit `is_pick: true`** so five clients stop re-deriving pick identity from the `team == "PICK"` magic string. Would have prevented both this bug and #222.
- **Possible seventh guard-clear site** at `TradesScreen.tsx:3138` (Quick-Set regen). It is a deck *replacement*, not a rewind, so it is safe today — but its safety rests on "regenerated cards carry fresh uuids", which contradicts the comment at two sibling reset sites.
