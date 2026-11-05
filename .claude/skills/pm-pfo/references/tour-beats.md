# Guided-tour beat contract

> Product-facing reference for `/pm-pfo`. Derived from code at `origin/main` `678834ab`
> (2026-10-15); every claim is `file:line` at that sha, and line numbers drift, so
> re-verify before citing one in an audit. Where a plan and the code disagree, **code
> wins** (§11). Ownership (decision P10): `onboarding-pm` owns the tour system and beat
> sequencing; `trades-pm` owns the content of the calculator tour's beats.

## 1. State today: the whole guided surface is dark

| Flag | Value | Line |
|---|---|---|
| `onboarding.v2` (master) | true | `config/features.json:124` |
| `onboarding.guided_avatar` (v1 tour) | **false** since `06a5ef67`, 2026-08-29 | `:134` |
| `onboarding.guide_v2` (v2 layer) | **false** since `380126a3`, 2026-08-28 | `:137` |
| `onboarding.guided_layer` (coach marks) | false | `:133` |
| `calc.merged_layout` / `calc.inline_home` | true / true | `:95` / `:97` |
| `ux.prompt_arbiter` | true | `:170` |

- An `onboarding.*` flag is on only when `onboarding.v2` is also on
  (`mobile/src/state/useFeatureFlags.ts:217-234`). `guidedAvatarActive()` = `guided_avatar`
  on and the user hasn't dismissed the tour; `guideV2Active()` = `guide_v2` on
  (`mobile/src/state/useGuide.ts:197-209`). `calc.inline_home` is a bare read, outside the
  master (`useGuide.ts:222-228`).
- So `requestStep` returns false on its first gate (`useGuide.ts:385`): no bubble, no
  `guide_*` event, not even a suppression. The calculator tour refuses to start
  (`mobile/src/utils/calcTour.ts:472`), the Settings row is hidden (§7), and coach marks are
  dark (`guided_layer` false). Only the arbiter's `prompt_shown` / `prompt_deferred` is live.
- Independently, `calc.inline_home` refuses every `screen: 'Trades'` beat
  (`useGuide.ts:408`) and suppresses the calculator tour's entry points
  (`mobile/src/screens/TradeCalculatorScreen.tsx:228-236`), so re-lighting the two avatar
  flags alone would still leave the Trades page tour-free.

So a Half A audit today walks a journey with **no tour beats**. Re-lighting the tour is a
journey-scope decision for `onboarding-pm` → `head-product`, not a flag flip.

## 2. What a beat is

A beat is a `GuideStep` (`useGuide.ts:84-134`) built by a function in the script
(`mobile/src/components/analystScript.ts`) and requested by a screen.
- Core fields: `id`, `line` (the copy), `pose`, `target` (the testID of the spotlit node),
  `advance` (`'tap' | 'action' | 'cta' | 'auto'` — tap anywhere, a real user action,
  in-bubble buttons, or a timer; `useGuide.ts:91-94`), `autoMs`, `ctas`, `once`, `side`,
  `band`, `screen`.
- v2-only fields (inert while `guide_v2` is off): `retireAfter`, `maxDisplayCount`,
  `invalidateOn`, `adoptionEvent`, `degradeLine`, `degrade: 'suppress'`, `lifetimeMs`
  (`useGuide.ts:107-133`).
- Copy budget by advance class: auto 12 words (and a reading-time floor on `autoMs`),
  action 16, tap 20, cta 16 with ≤4-word buttons and at most one primary
  (`analystScript.ts:11-19`).
- Ids: v1 beats are `s<scene>.<n>` (`s0.1` … `s8.1`, `s0.err-*`, `s2.wait`); v2 beats start
  with `n` (`n1`, `n2a`, `n2b`, `n4`, `n5`, `n6.1`, `n8`, `n9`; calculator tour `n10`–`n24`).
  `PROBES` in `mobile/tests/check-guide-script.js:103-151` pins the exact built set.
- Sign-off `s8.1` is requested once `s2.2` and a first-like beat (`n6.1`/`s6.1`) are seen,
  and seeing it completes the tour (`mobile/src/screens/TradesScreen.tsx:4631-4647`).

## 3. Adding a beat

1. **Script entry.** Add the builder to `S` in `analystScript.ts` (the file stays
   import-free). A v2 beat must declare `retireAfter` (or `'never'` with a same-line
   `// reason:`), a display cap (`maxDisplayCount` or `once`), and an `adoptionEvent`.
   A targeted beat needs a `degradeLine` or `degrade: 'suppress'`; an untargeted beat's
   copy must not point at anything. Retirement ids come from `GUIDE_RECEIPTS`
   (`analystScript.ts:49-61`). All of this is asserted by `check-guide-script.js`.
2. **Registries.** Add the builder to `PROBES` (`check-guide-script.js:103-151`) or
   assertion 1a fails. A calculator-tour beat also goes into `CALC_TOUR_CALCULATOR` or
   `CALC_TOUR_DECK` (`calcTour.ts:78-84`), and the pinned beat count in
   `mobile/tests/check-calc-tour.js:48` (13 today) changes with it.
3. **Target registration.** Wrap the node in `<View ref collapsable={false}>`, then
   `registerGuideTarget(testID, ref)` in an effect, unregistering on cleanup
   (`mobile/src/screens/SignInScreen.tsx:257-264`). Last registration wins
   (`mobile/src/state/guideTargets.ts:9-17`); a missing node, 250 ms timeout or zero-width
   frame measures null (`:19-40`); scroll hosts call `notifyGuideTargetsMoved()` (`:42-60`).
4. **Request and advance.** The screen calls `requestGuideStep(step, handlers)`
   (`useGuide.ts:599-604`); an action beat advances via `advanceGuideIfActive(id)` at the
   real action (`:606-609`); screens record receipts with `recordGuideReceipt`
   (`:624-626`). A new beat reuses the `guide_*` events; a new event name is a separate
   ask (§6).

## 4. Request and suppression model

`requestStep(step, handlers?) => boolean` (`useGuide.ts:161`) checks, in order
(`:384-510`):
1. tour inactive → false, silent (`:385`);
2. Trades beat under `calc.inline_home` → false, silent (`:408`);
3. a tour hold is up and the id isn't tour-owned → false, silent (`:414-419`);
4. `once` and already seen → `seen`; then, v2 only, `display_cap`, `invalidated`,
   `retired`, `v1_release_cap`;
5. another bubble is up → `guide_active`; v2 only, the arbiter slot is taken → `slot_busy`.

`GuideBlockedBy` has nine values (`useGuide.ts:73-82`, mirrored at
`backend/analytics_taxonomy.py:1436-1439`): `guide_active`, `slot_busy`, `seen`,
`display_cap`, `invalidated`, `retired`, `degrade` (spotlight unmeasurable and
`degrade: 'suppress'`), `v1_release_cap`, `matched` (consumed by a call site).

**Once per deferral episode.** `guide_step_suppressed` fires once per (step, reason), not
per retry — call sites re-request on every render. The episode closes when the step shows
or the tour is re-enabled. It only fires with `guide_v2` on (`useGuide.ts:261-278`).

Progress persists per device in AsyncStorage `ftf_onboarding_state_v1`
(`mobile/src/state/useOnboardingState.ts:14`). "Skip the tour — don't show again" is on every
bubble (`mobile/src/components/AnalystGuide.tsx:507-520`).

## 5. Interrupt coordination

`mobile/src/state/useInterruptCoordinator.ts`:
- One slot, five surfaces by priority: `guide_step` 0, `quickset_prompt` 1, `coach_mark` 2,
  `apple_banner` 3, `outlook_banner` 4 (`:57-71`). No preemption: a taken slot refuses the
  claim. The guide claims it only when `guide_v2` is on (`useGuide.ts:476`).
- A **tour hold** (`beginTourHold` / `endTourHold`) refuses every surface except
  `guide_step`; the calculator tour takes it on start (`calcTour.ts:512`). Root modals
  (Apple save moment, push primer) defer while `isInterruptBusy`.
- With `ux.prompt_arbiter` on, a shown prompt emits `prompt_shown`; a refused one emits
  `prompt_deferred {surface, blocked_by}` (`'tour'` under the hold) once per episode.

## 6. Events a beat fires

| Event | Props | Emit site |
|---|---|---|
| `guide_step_shown` | `step, pose, screen` (+ `spotlight` under v2) | `useGuide.ts:494` (v1); `commitShown` (v2) |
| `guide_step_advanced` | `step, via` | `useGuide.ts:528` |
| `guide_step_skipped` | `step` | `useGuide.ts:539` |
| `guide_tour_dismissed` | `at_step` | `useGuide.ts:564` |
| `guide_tour_completed` | `steps_seen` | `useGuide.ts:578` |
| `guide_step_suppressed` | `step, blocked_by` | `useGuide.ts:277` |
| `guide_tour_reenabled` | — | `useGuide.ts:572` |
| `calc_tour_started` / `_ended` / `_beat_missing` | `source` / `reason, beats_shown` / `beat` | `calcTour.ts:529` / `:225` / `:257` |

Registered in `backend/analytics_taxonomy.py` (`:77-78`, `:350`, `:416`, `:590`);
`guide_step_suppressed` and the calc-tour events are non-intent in
`backend/analytics_queries.py` (`:243`, `:342-344`).

**The new-event rule.** A new client event name needs a tracking-plan addendum and
`analytics-lead`'s grant, then registration in `analytics_taxonomy.py` **and**
classification in `analytics_queries.NON_INTENT_EVENTS` (impression, suppression and
terminator names) in the **same commit as the emitter** — the registry is default-deny
behind a 200, so a name that lands late is silently lost.

## 7. The Settings re-enable row

`mobile/src/screens/settings/sections/GuideSection.tsx` renders nothing unless
`onboarding.guided_avatar` is on (`:41`, `:46`), so it is hidden today. Its toggle
(`settings.guided-tour-toggle`, `:54`) calls `dismissTour()` or `enableTour()` (`:62-65`).
`enableTour` resets progress (all of it with `guide_v2` off; all but retired steps with it
on), clears suppression episodes and fires `guide_tour_reenabled` (`useGuide.ts:568-573`;
`useOnboardingState.ts:197-246`). A duplicate toggle lives in `SettingsScreen.tsx:927-946`.

## 8. The calculator tour and the merge seam

- Same engine, overlay and script as the Analyst tour, not a separate system. Beats:
  calculator half `n10 n11 n12 n13 n15 n16 n18`, deck half `n19`–`n24`
  (`calcTour.ts:78-84`); `n23b` replaces `n23` off Sleeper.
- Needs **both** `guided_avatar` and `guide_v2` (`calcTour.ts:465-472`). Auto-starts once
  on landing; "Show me around" re-runs it; `calc.inline_home` suppresses both. While it runs
  it owns the hold, so other beats are refused silently.
- **The merge plan** (`docs/plans/onboarding-tour-merge/plan.md`) proposes one tour: one
  runner over the onboarding spine, a bridge beat into the calculator half, auto-dispatch of
  the first search, calculator beats retargeted to the inline module. Waves A and B0 shipped
  (2026-08-24); **Wave B is not built** — the tour was switched off under `calc.inline_home`
  instead. Seam: `onboarding-pm` owns the runner, the order and the bridge; `trades-pm` owns
  what the calculator beats say.

## 9. Which guards pin what

All four run in CI (`.github/workflows/ci.yml:47`); npm scripts at
`mobile/package.json:23`, `:47-48`, `:108`.

| Suite | Pins |
|---|---|
| `check-guide-script.js` | The exact builder set; copy budget, CTA limits and the `autoMs` floor; the v2 contract (retirement, cap, `adoptionEvent`, degrade honesty); receipt hygiene; per-platform `s0.2`; which beats may still be tap-class |
| `check-guide-spotlight-tracking.js` | The spotlight re-measures on scroll and movement, keeps the last frame on a null measure, places the band next to the ring, and scrolls a target into view once per step |
| `check-tour-suppression.js` | Runs the real coordinator store: claim / no preemption / release; the hold refuses non-guide surfaces; root modals read `isInterruptBusy`; `prompt_deferred blocked_by:'tour'` is present |
| `check-calc-tour.js` | 13 argument-free beats (`n14` / `n17` gone); screen split; hold lifecycle; entry-point guards; targets registered; action beats have call sites; receipt / reset lifecycle |

## 10. Evidence a beat change needs (D-056)

No simulator, no Maestro, no captures ([D-056](../../../../living-memory/DECISIONS.md)).
A beat change carries, in its scope block (`docs/templates/feature-scope.md` §3):
1. **A guard update** — `PROBES`, the runner lists and any moved assertion, same commit;
2. **A code-walk** — request site → gate order (§4) → events fired, file:line at the sha,
   including the flag-off path;
3. **TestFlight steps** for the operator — fresh install, flags pinned, the exact screen
   and trigger, the expected bubble or its absence, and the events to look for — logged by
   `release-lead`. House example: `docs/plans/guided-onboarding-v2/testflight-checklist.md`.

## 11. Where plans and code disagree (code wins)

- `config/features.json:136` (`_comment_guide_v2`) says `guide_v2` was lit 2026-08-22 and
  that `guided_avatar` is "already true"; both are false (`:134`, `:137`).
- `onboarding-tour-merge/plan.md:3` says "nothing here is built"; Waves A and B0 shipped.
- `guided-onboarding-v2/PRD.md:424` cuts a "trade calculator walkthrough"; one was built
  (#384). `guided-onboarding-v2/scope.md:8` lists N5 as Phase 2; `n5` is built
  (`LeagueSummaryScreen.tsx:1004-1009`). N3, N6.2 and N7 are not in code. The PRD's copy and
  advance classes for `s0.1`, `s2.1`, N1 and N6.1 differ from the script; read the script.
- `onboarding-conversion/guided-avatar-script.md:9` offers "Skip the tour" only at S0 and
  after two skips; code puts it on every bubble. Its fallback, the "v2.1 passive
  experience", is nothing (`guided_layer` off).
- `docs/business/analytics/2026-08-15-guided-onboarding-v2-events.md:14` (and `scope.md:26`)
  retire QuickSet beats on `quicksetCompletedPositions`; code uses the
  `quickset_completed_local` receipt (`analystScript.ts:52`). Its nine `blocked_by` values match.
- The conversion plan's fourth coach mark (`trio_entry`) has no emitter; three marks fire.

## Open questions

- Experiment overlays (`client_config.flags`) can light a guide flag for a cohort from the
  database, which the repo can't show. Ask `analytics-lead` before assuming it's dark for all.
- `guided-onboarding-v2/scope.md:40` says `check-guide-script.js` pins the `s8.1` rewire
  (`n6.1 || s6.1`); no suite was found asserting it. Is the sign-off unguarded?
- The tour has been off since 2026-08-29 (operator ruling). Whether it returns, and in what
  form after Wave B, is open for `head-product`.
