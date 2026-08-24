# Feature Scope — Onboarding-tour merge, Wave A ("stop the bleeding")

**Date:** 2026-08-24
**Entry point:** [docs/plans/onboarding-tour-merge/plan.md](plan.md) §7 Wave A — §2 items 2/3/4/8, §2b items 12/13/14/15/17, [D-157](../../../living-memory/DECISIONS.md)
**Builder:** Claude Code session, branch `feat/tour-wave-a`
**Operator sign-off on waivers:** not needed — no waivers taken. Two deliberate
deviations from the build brief are recorded in §6 and need a look, not a waiver.

Wave A is the half of Segrave's 2026-08-23 notes that is copy, config, and
sequencing. It ships no new surface, no new route, no new event, and no schema.
Every item is a defect the operator could feel in five minutes of use.

| # | Note | What changed |
|---|---|---|
| 2 | Remove the demo-league link | `landing.try_before_sync` → `false` (config only; nothing deleted) |
| 3 | Pop-ups only exit via the tiny ✕ | Ten onboarding talk beats become `advance: 'cta'` with a Next button |
| 4 | The opener should promise a walkthrough | `s0.1` rewritten (+ its `lineRam` twin) |
| 8 | Trade copy should explain provenance | `s2.1` rewritten to carry the consensus-now / your-values-next claim |
| 12 | n11 highlights nothing | Runner **parks** between n10 and n11 until the In-league content mounts |
| 13 | Outlook sheet sits too tight to the bottom | Safe-area + `space.lg` bottom pad on `TradeDnaSheet` |
| 14 | The Analyst pops out behind the sheet | Runner **parks** after n11's accept until the sheet closes |
| 15 | The ✕ clears the canvas mid-tour (D-157) | Action row becomes Find a Trade 50 / **Clear** 30 / confirm 20 |
| 17 | Fairness beat: no highlight, no scroll | n22 retargeted at the top card's meter (`trades.card-meter`) |

---

## 1. Analytics scope

- **(c) WAIVED — no analytics needed because this wave adds NO new events.**
  Every emitter it touches keeps its existing contract:
  - `guide_step_advanced {step, via}` already carries `via`, and `'cta'` is an
    existing value of it (`useGuide.ts` `advance`) — the ten converted beats
    change which value they report, not the event or its shape.
  - `calc_tour_ended {reason, beats_shown}` is unchanged. The two new parks can
    end a run `'abandoned'` on timeout, which is a value the property already
    has and the analysis already handles.
  - n22's `adoptionEvent` stays `help_opened`. That join weakened (see §6) and
    is documented in the beat rather than quietly repointed.
  - No `analytics_taxonomy.py` change, therefore no `NON_INTENT_EVENTS`
    classification change.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. `docs/data-dictionary.md` n/a.
- **New/changed feature flags:** none added. One **flipped**:
  `landing.try_before_sync` `true` → `false` in `config/features.json`, mirrored
  in `backend/tests/fixtures/flags/release.json` (the exact-mirror test
  `test_seed_ui_test_db.py::test_release_flags_mirror_features_json`),
  `onboarding-v2.json` and `profiles-on.json`. `docs/config-reference.md` row
  rewritten, and the Phase-A paragraph plus the `onboarding.landing` row
  annotated so the retired launch pairing does not read as current.
  **Deploy-free rollback:** set it back to `true` and
  `POST /api/feature-flags/reload`. The code path — `/api/session/demo`,
  `useSession.isDemo`, the landing link — is untouched, per the plan's "flag off
  now, delete the path in the build wave".
  `all-on.json`, `release-300.json` and `release-espn-send-off.json` keep
  `true` deliberately: they are not mirrors of `features.json` (only
  `release.json` is test-enforced) and nothing in this wave reads them.
- **New env vars / `model_config` keys:** none.

## 3. Evidence scope

- **Structural guards** — three files extended, none created:
  - `mobile/tests/check-calc-tour.js` §45 — the two parks, three properties
    each: the park is taken at the right seam, it is **time-bounded** and
    expiry **ends** the tour rather than wedging the app-wide interrupt hold,
    and the resume is wired end to end (screen prop → runner export →
    `requestAt`). Plus 45c/45d/45e for the **level** semantics of the ready
    signal, and 45l/45m pinning that the component's `inLeagueReady` predicate
    is the negation of the two early returns it depends on. §40d–40f cover
    n22's new target: registered top-card-only, only while the bar renders,
    and `trades.fairness-help` still registered for its other consumers.
  - `mobile/tests/check-card-disposition.js` §4 — `trades.card-meter` is an
    effect registration gated on `cardMeterMounted`, unregisters on teardown,
    and its wrapper is a non-collapsable `View` holding the ref (Android
    flattens a styleless View and the ref then measures null).
  - `mobile/tests/check-guide-script.js` §10/§11 — the ten converted beats are
    `cta` **with buttons**, and the only `advance: 'tap'` beats left in the
    whole script are the two named exemptions (`s2.3`, deprecated; `n9`,
    outside Wave A's list). The closed-set half is what catches a *new* tap
    beat. §11 pins n22's target and that its copy names a control the meter
    actually has.
  - **Updated, not deleted:** `check-guide-script.js` assertion `8b` asserted
    `S.n6_1(false).ctas === undefined`, which was a statement about the beat
    being tap-advance. Restated as the property that actually mattered — the
    router-less variant carries exactly one plain `Next` and **none of the
    routing variant's buttons** — plus `8b-ii`, that it takes no lifetime
    bound. Sabotage still caught: copying `See it →` onto the arm with nowhere
    to send anyone.
  - **Falsifiability spot-check:** deleting the `if (inLeagueReady)` fast path
    from `calcTour.ts` turned 45c red; restoring it turned it green again.
- **Unit tests:** no backend pytest files added. The flag flip is data, and the
  suite that guards it (`test_release_flags_mirror_features_json`) already
  exists and already fails on drift — which is exactly how the 2026-08-23a
  main-CI break was caught. Full `pytest backend/tests` run recorded in
  TEST_LEDGER.
- **Code-walk proof:** §5 below.
- **Manual TestFlight checklist:** new **Wave A** section in
  [docs/feedback/items/384-calc-finder-merge/testflight-checklist.md](../../feedback/items/384-calc-finder-merge/testflight-checklist.md).
  Runtime proof genuinely matters here: both parks fix a *race* that the
  simulator hid behind a warm cache (that is why W8 falsely passed), and no
  structural guard can observe a spotlight actually landing on a mounted node.
- **`testID`s added/renamed:** one added — `trades.card-meter`
  (`TradeCard.tsx`). None renamed: `calc.action.clear` keeps its id even though
  its content changed from an icon to the word "Clear", so no flow, guard or
  `testid-lint` expectation moves. `mobile/scripts/testid-lint.sh` passes.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed or contract-changed. `/api/session/demo` is untouched — it already 404s when `landing.try_before_sync` is false, which is documented behaviour, not a new contract. |
| `living-memory/LLD.md` | **n/a** | No schema, route or invariant *convention* shifted. The park is a second instance of a pattern the runner already had (the deck-arrival park), not a new convention. |
| `docs/architecture.md` | **n/a** | Module wiring unchanged. Two new props on an existing component and two new exports from an existing util; the ownership boundary (screen owns navigation and the runner, component owns the canvas) is the one that already existed. |
| `living-memory/HLD.md` | **n/a** | No new module, client or major flow. |
| `docs/cross-client-invariants.md` | **n/a** | No shared constant, enum or colour changed. The action-row proportions are one client's layout, not a cross-client contract. |
| `docs/glossary.md` | **n/a** | No new domain term. "Clear" and "queue" already have entries and their meanings are unchanged — the ✕ cell was *always* Clear (D-153); D-157 only makes the label say so. |
| ADR / `DECISIONS.md` | **already exists** | [D-157](../../../living-memory/DECISIONS.md) (labelled Clear button) and D-158 are the decisions this wave builds; no new decision was made. The two deviations in §6 are judgement calls inside D-157/the brief, recorded here rather than minted as decisions. |
| `docs/config-reference.md` | **updated** | `landing.try_before_sync` row rewritten; Phase-A paragraph and the `onboarding.landing` row annotated. |

## 5. Code-walk proof — the two parks

Line numbers are `feat/tour-wave-a` at the time of writing.

### 5.1 · The n10 → n11 race, and the park that removes it

**The race, as it stood.** `TradeCalculatorScreen.tsx:527`
(`switchMode`) fires `advanceGuideIfActive('n10', 'action')` on the In-league
tab tap. That reaches `useGuide.ts:473` `advance`, which calls `terminate`
(`:299`) and invokes the runner's `onComplete` **synchronously** at `:310`.
`calcTour.ts` `onBeatComplete` then used to fall straight through to
`requestAt(i + 1)` (now `:347`) — n11 — in the same JS turn as the tap.

But `setMode('league')` (`TradeCalculatorScreen.tsx:530`) only *starts* the
switch. `InLeagueCalculator` mounts and immediately returns the loading card
(`InLeagueCalculator.tsx:694`, `if (rostersQ.isLoading || coverageQ.isLoading)`),
so the outlook row at `:747` — the `calc.outlook-row` wrapper that is n11's
`target` (`analystScript.ts:433`) — does not exist. `useGuide.resolveSpotlight`
(`:320-327`) measures null, retries **once** after 150 ms, and then degrades the
beat. On a warm cache the queries resolve inside that window, which is why the
W8 simulator pass was a false green; on a cold device they do not.

**The park.** `calcTour.ts:303-317`: when `slot === 'n10'`, the runner either
proceeds immediately (`:304`, the level check — see below) or records
`inLeaguePark = { at: i + 1 }` (`:308`) and arms `inLeagueParkTimer` for
`IN_LEAGUE_READY_TIMEOUT_MS` (10 s, `calcTour.ts:104`). Expiry calls
`endTour('abandoned')` (`:314`), which releases the interrupt hold at `:205` —
the reason the park must be bounded at all: a wedged park mutes every
interstitial app-wide for the rest of the session.

**The resume.** `InLeagueCalculator.tsx:444-451` derives
`inLeagueReady = merged && !rostersQ.isLoading && !coverageQ.isLoading && opponents.length > 0`
— the negation of both early returns (`:694` loading, `:704` no leaguemates) —
and fires `onInLeagueReady?.()` once per mount from an effect (`readyAnnouncedRef`,
`:446`). An effect, not render: the callback synchronously resumes the runner,
which writes the guide store. React attaches refs before effects, so
`outlookRowRef` (`:210`, attached at `:747`) is already populated when the
runner asks for it. `TradeCalculatorScreen.tsx:780` passes
`onInLeagueReady={calcTourInLeagueReady}`; `calcTour.ts:356-366` sets the level,
clears the timer, and calls `requestAt(at)`.

**Level, not edge.** `inLeagueReady` (`calcTour.ts:138`) is set by the callback
*whether or not anyone is waiting* (`:357`, before the `!inLeaguePark` guard at
`:358`). The re-run case is why: "Show me around" on a page whose league has
already loaded completes n10 with the content long since mounted, so there is no
announcement still to come — an edge-triggered park would sit there for the full
10 s and then end the tour the user just explicitly asked for. The fast path is
`:304-307`. The level is cleared in `calcTourScreenBlurred` (`:414-421`, the
assignment at `:419`), **before** its `!running || handingOffToDeck` early
return, so a departure on the hand-off path clears it too; a stale `true` would
let the next run request n11 against an unmounted target and re-create the bug.

### 5.2 · The n11 → n12 sheet overlap, and its park

**The overlap.** n11 is `advance: 'cta'` with a single "Set outlook" button
(`analystScript.ts:431-441`). `AnalystGuide.tsx:483-487` runs
`onAccept?.()` and then `advance('cta')` in the same handler.
`calcTour.ts:256` wires that `onAccept` to `handlers.openOutlook`, which is
`TradeCalculatorScreen.tsx:238`'s `() => outlookOpenerRef.current?.()` →
`InLeagueCalculator.tsx:215` `setDnaOpen(true)`. So one tap opens an RN `Modal`
(`TradeDnaSheet.tsx:521`) **and** completes the beat. The guide overlay is
mounted once in `RootNav`, i.e. below any Modal, so n12 rendered behind a sheet
the user was still editing.

**The park.** `calcTour.ts:326-333`: `slot === 'n11' && via === 'cta' && !!handlers.openOutlook`.
All three conjuncts matter. `via === 'cta'` excludes the ✕ (`'x'`), the
swipe-away and the timeout — none of those opened a sheet, so none of them has a
close to wait for. `!!handlers.openOutlook` excludes a host that passed no
opener (the accept path still advances in that case, per the comment at
`calcTour.ts:251-257`). Anything else falls through to the normal
`requestAt(i + 1)` at `:347`, so **n11 completed without opening the sheet does
not park** — which is the brief's explicit requirement.

**The resume.** `InLeagueCalculator.tsx:1312-1320` wraps the sheet's `onClose`
so every close route reaches the host: Done (`TradeDnaSheet.tsx:513-518`), the
backdrop press (`:535`), and `onRequestClose` (`:525-529`, hardware/system
back). `TradeCalculatorScreen.tsx:785` passes
`onOutlookClosed={calcTourOutlookClosed}`; `calcTour.ts:372-381` unparks and
requests n12. Bounded identically at `OUTLOOK_CLOSE_TIMEOUT_MS` (10 s,
`calcTour.ts:105`), expiring into `endTour('abandoned')`.

**Both timers die with the run.** `clearPark` (`calcTour.ts:159-177`) clears all
three parks and all three timers, and `endTour` calls it at `:196`. A surviving
timer would end a *later* run 'abandoned' out of nowhere.

### 5.3 · The converted beats' terminal handling still works

`AnalystGuide.tsx:476-499` renders `active.ctas` generically — any beat with a
`ctas` array gets its buttons, no per-beat branch. The button's handler calls
`onAccept?.()` / `onDismissCta?.()` and then `advance('cta')` (`:486`), which at
`useGuide.ts:473-482` writes `guideSeen` for `once` steps exactly as the tap
path did and terminates with `via: 'cta'`. So `once`, display caps, retirement
and the `guideSeen`-driven chains in `TradesScreen` are all unaffected.

The one call site that **branches on `via`** is `v2OnN61Complete`
(`TradesScreen.tsx:3808-3822`): `if (via === 'cta' && v2N61NavigatedRef.current)`.
The ref is set only inside the **routable** variant's `onAccept`
(`:3825`), so the newly-cta router-less variant reaches that line with the ref
`false` and falls through to `v2RunLikeChain()` — identical to its old
`via: 'advance'` behaviour. Verified by reading both arms; no other request site
for the ten converted beats passes an `onComplete` at all
(`SignInScreen.tsx:155/372`, `QuickSetTiersScreen.tsx:119`,
`TradesScreen.tsx:3306/3417/3603/3611`).

The router-less n6.1 also keeps its real bound: `TradesScreen.tsx:4313-4317`
dismisses an active `n6.1` on the next swipe, so a cta beat with no `lifetimeMs`
still cannot hold the interrupt slot across further swipes.

## 6. Two deliberate deviations from the build brief

Both are small, both are called out so the operator can overrule them.

1. **`s8.1` got `DONE`, not `NEXT`.** The brief lists `s8.1` among the beats to
   convert "with `ctas: [NEXT]`". Its line is *"That's the tour."* — a button
   labelled **Next** under that sentence promises a beat that does not exist,
   which is precisely the defect `check-calc-tour.js` assertion 39b forbids on
   n24. `DONE` is the constant already in the file for exactly this case. Wave B
   rewrites `s8.1` "to land as an ending" (plan §3), which this anticipates
   rather than contradicts.
2. **n22's line changed more than "minimally".** The brief suggested keeping
   *"Tap the meter to see how we judged this trade fair."* Against the ⓘ that
   was true; against `TradeValueBar` it is not — the bar itself is inert, and
   its explainer is a **"Why?"** disclosure (`TradeValueBar.tsx:170-180`,
   `testID="valuebar.why"`). Telling a user to tap something that does nothing
   is the §1.3 honesty failure, so the line now names the control that exists:
   *"The meter is the verdict. Tap Why? for how we judged it."* The wrapper the
   beat rings spans the whole bar, so the "Why?" line is inside the ring.
   **Known cost:** `valuebar.why` fires no client event, so n22's
   `adoptionEvent: 'help_opened'` no longer joins to the control it points at.
   Stated in the beat's comment rather than hidden, following the `n23b`
   precedent; giving that disclosure an event is a one-line follow-up for
   whoever next touches the taxonomy.

**Also checked and deliberately NOT changed:** n19's line *"Clear became this
cross. It records why you passed; the check still accepts."* D-157 asks for a
re-check now that the calculator's control is literally labelled **Clear**. It
reads *better*, not worse — the sentence names the calculator's Clear and the
deck's cross, and both now exist under those names. Left verbatim.

## 7. Ship gate declaration

- **CI green:** `pytest backend/tests`, `npx tsc --noEmit`, all 77
  `mobile/tests/check-*.js` suites, and `mobile/scripts/testid-lint.sh` — run
  locally on the branch tip, counts logged in `living-memory/TEST_LEDGER.md`.
- **Evidence recorded:** TEST_LEDGER entry dated 2026-08-24.
- **TestFlight verification:** checklist written (§3); **not yet run** — it is
  the operator's, and it is the only runtime evidence this wave gets.
- **Express lane declared by the operator?** No. Full gates.
