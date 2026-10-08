# Home tab — plan

**Date:** 2026-10-02 · **Entry point:** direct operator ask · **Branch:** `feat/home-tab` (from `origin/main` @ `3bb981ed`) · **Scope block:** [scope.md](scope.md)

## What ships

A new **Home** tab, first in the mobile bottom bar, that the app opens on. It is deliberately simple: one line — "What would you like to do today?" — and four plain-text options.

| Option (exact copy) | Goes to | testID |
|---|---|---|
| Rank | `Rank` tab | `home.option.rank` |
| Find a Trade | `Trades` tab (labelled "Acquire" in the bar) | `home.option.trades` |
| See Matches | `Matches` tab | `home.option.matches` |
| View my Leagues | `League` tab | `home.option.league` |

Mobile only. `web/` and `extension/` are untouched.

## Operator decisions (2026-10-02)

1. **First-run users still land on Trades.** While `onboarding.trades_first` is live and the user has not swiped a trade yet, the launch tab stays `Trades`, so the analyst-guide onboarding (every step of which is scripted against the Trades screen) is unchanged. Everyone else opens on Home.
2. **"View my Leagues" opens the League tab**, not the root-stack `LeaguePicker`.

These narrow the 2026-08-28 trades-landing ruling (`nav.trades_landing`): Trades is no longer the front door for returning users. Logged as a new `DECISIONS.md` entry.

## Design

### Flag — `nav.home_tab` (default **true**)

Client-only, same shape as `draft.tab` / `nav.trades_landing`: read **imperatively, once at mount** in `TabNav`, so a mid-session revalidation can never insert/remove a tab or rewrite the launch tab under the user. It is the deploy-free rollback lever — flip it `false` and the next launch is today's app exactly (no Home tab, launch tab decided by the existing `initialTab` logic).

Must be set in all of these, with the same value (`revalidateFlags` replaces the whole map, so a key in only one place flickers):
`config/features.json` (+ `_comment_nav_home_tab`) · `backend/feature_flags.py` `FLAG_KEYS` · `backend/tests/fixtures/flags/*.json` (every fixture that carries `nav.trades_landing`) · `mobile/src/state/useFeatureFlags.ts` baked defaults · `docs/config-reference.md`.

### `mobile/src/navigation/TabNav.tsx`

- `const [showHomeTab] = useState(() => !!useFeatureFlags.getState().flags['nav.home_tab'])`.
- **Leave the existing `const [initialTab] = useState(...)` block byte-identical** — `mobile/tests/check-canvas-results.js` §10 pins its text, and it is the flag-off behavior. Add after it:
  ```ts
  const [launchTab] = useState(() =>
    showHomeTab &&
    !(onboardingEnabled('onboarding.trades_first') &&
      !getOnboardingState().firstSwipeDone)
      ? 'Home'
      : initialTab,
  );
  ```
  and pass `initialRouteName={launchTab}`.
- Render `{showHomeTab ? <Tab.Screen name="Home" … /> : null}` as the **first** child of the navigator: `component={HomeScreen}`, `tabBarIcon: tabIcon('home')`, `tabBarButtonTestID: 'tab.home'`, `tabPress` listener calling `trackTab('home', navigation)`. No nested stack, nothing to pop or scroll.

Bar becomes **Home · Rank · Acquire · [Calibration | Draft] · Matches · League**. Rebased 2026-10-08 onto the Calibration ship (#312, D-197): the third slot is Calibration while `grading.blind` is on (it is, for every user), Draft only when Calibration is absent and `draft.tab` is on (it is off), so the bar is six tabs today with "Calibration" as the longest label. Labels are 11px so it fits, but it is the one layout risk; it is on the TestFlight checklist.

### `mobile/src/screens/HomeScreen.tsx` (new)

- Root `View` `testID="home.screen"`, `ink.ink0` background, no `top` safe-area edge (TopBar owns it).
- Heading text: `What would you like to do today?`
- Four `Pressable` rows, plain text, `accessibilityRole="button"`, each `navigation.navigate('<Tab>')`. Rows are driven from one small array so copy/target/testID can't drift.
- Chalkline tokens only (`ink`, `chalk`, `ice`, `fonts` from `theme/chalkline`); no emoji, gradients, cards with radius >8, or new accents. Hairline `ink.line` separators between rows.
- **No `FeedbackFAB`** — tab screens are covered by RootNav's global mount.
- No data fetching, no new state.

### Supporting edits

- `mobile/src/components/chalkline/Icon.tsx` — add `'home'` to `IconName` and a stroke-only 20×20 house glyph matching the set (1.75 weight, square caps).
- `mobile/src/utils/deepLinks.ts` — add `Home: 'home'` under `Main.screens` (→ `app/home`), per the "adding a screen means three things" rule.

### Analytics — no new events

`tab_selected` (`tab: 'home'`) covers bar taps; `tab` is a free string prop, no enum to extend. Option taps are programmatic navigation and are covered by the existing auto-emitted `screen_viewed` (`screen` = destination, `prev_screen: 'Home'`), which answers "what do people pick from Home".

## Work split (disjoint file ownership)

| Agent | Owns |
|---|---|
| **A — mobile** | `mobile/src/screens/HomeScreen.tsx`, `mobile/src/navigation/TabNav.tsx`, `mobile/src/components/chalkline/Icon.tsx`, `mobile/src/utils/deepLinks.ts`, `mobile/src/state/useFeatureFlags.ts`, `mobile/tests/check-home-tab.js`, `mobile/package.json` (one script line), `mobile/src/navigation/{CLAUDE,README}.md`, `mobile/src/screens/{CLAUDE,README}.md` |
| **B — flag + backend docs** | `config/features.json`, `backend/feature_flags.py`, `backend/tests/fixtures/flags/*.json`, any backend test that pins the flag set, `docs/config-reference.md` |
| **Lead** | this plan + scope, integration review, `tsc`/pytest/structural suites, `living-memory/` write-back, commit |

## Evidence (D-056 — no simulator)

1. **Structural guard** `mobile/tests/check-home-tab.js` (`npm run test:home-tab`) pins: imperative once-at-mount flag read; Home is the first `Tab.Screen`; `launchTab` keeps the trades-first carve-out and falls back to `initialTab`; the four option labels/targets/testIDs; no `FeedbackFAB` in `HomeScreen`; `Home: 'home'` in the route table; flag value agrees across `features.json`, the baked default, the fixtures, and `FLAG_KEYS`.
2. **Existing suites stay green:** `check-canvas-results.js` (§10 trades-landing pins), `tsc --noEmit`, `testid-lint.sh`, `pytest backend/tests`.
3. **Manual TestFlight checklist** — in [scope.md](scope.md) §3.

## Not in scope

Web home page; changing any destination screen; a per-option analytics event; removing `nav.trades_landing` (it remains the flag-off behavior).
