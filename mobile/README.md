# mobile/

React Native (Expo) app for Fantasy Trade Finder — ships as **Fleeced: Dynasty Trade Finder** on iOS (bundle `com.fantasytradefinder.app`). ~497 tracked files: 32 screens, 77 components, 26 API modules.

Agent operating rules live in [CLAUDE.md](CLAUDE.md). This file is the map.

> The native project folder is `ios/DTFDynastyTradeFinder/` and the Expo slug is `dtf-dynasty-trade-finder`. Both keep the old name **on purpose** (D-057) — project/scheme names are invisible to users, and renaming would churn Pods, workspace, scheme and EAS config for nothing. The bundle ID is immutable and stays.

## Setup

```bash
cd mobile
npm install          # postinstall runs patch-package against patches/
npm start            # Expo dev server (scan the QR with Expo Go)
npm run ios          # native build + install on a booted iOS Simulator
```

The app reads its backend URL from `app.json → extra.apiBaseUrl` (production Render URL by default). To point at a local Flask instance, build through `app.config.js`'s env contract: `FTF_API_BASE_URL=http://localhost:5000 npm run ios`.

## Checks

```bash
npx tsc --noEmit               # strict typecheck
npm run test:contrast          # WCAG contrast floors on Chalkline tokens
npm run test:<name>            # 41 structural guards — see tests/README.md
bash scripts/testid-lint.sh    # testID cross-check (CI)
```

There is no simulator or Maestro step — retired 2026-08-15 (D-056). Runtime proof is a manual TestFlight pass against a written checklist.

## Layout

| Path | What's there |
|---|---|
| `index.ts` | Expo entry shim |
| `App.tsx` | Providers, boot gating, deep links, AppState fan-out |
| `app.json` / `app.config.js` / `eas.json` | Expo config, test-harness env layer, EAS build + submit profiles |
| `src/api/` | 26 HTTP client modules — FTF backend, Sleeper, ESPN, MFL, Fleaflicker |
| `src/components/` | 77 shared components + `chalkline/` (design-system primitives), `analyst/` (mascot poses), `draft/` (Draft Room / Mock pieces) |
| `src/data/` | `calcTypes.ts` — shared calculator asset types |
| `src/hooks/` | 6 cross-cutting hooks (push, scoring format, resume recovery, reduced motion, app-active, what's-new) |
| `src/navigation/` | `RootNav`, `TabNav`, rank-chooser model, scroll-to-top registry |
| `src/observability/` | `sentry.ts` — no-ops without a DSN |
| `src/screens/` | 32 screen components, one per route |
| `src/shared/` | `types.ts` — wire types |
| `src/state/` | 19 modules: 12 zustand stores, 3 module buses, 2 persisted hooks, the QueryClient, a target registry |
| `src/theme/` | `chalkline.ts` (tokens), `colors.ts` (data-encoding hexes), `spacing.ts` (legacy scale) |
| `src/transport/` | `credentialVault.ts` — the one SecureStore key holding every platform credential |
| `src/utils/` | 25 helpers — deep links, tier bands, trade text, session re-rank, CSV rank presets, ESPN cookies |
| `assets/` | icon / adaptive-icon / splash / favicon PNGs |
| `.maestro/` | Retained UI flows — historical only, never run (D-056, 2026-08-15) |
| `scripts/` | testID lint + contrast guard (live); simulator build/run/capture harness (dormant) |
| `tests/` | 50 dependency-free structural guards run under plain node |
| `ios/`, `android/` | Checked-in native projects (`expo prebuild` output) |
| `patches/` | `patch-package` diffs applied on install |

## Navigation at a glance

```
RootNav (stack)
├─ SignIn · LeaguePicker · LeagueJoin
├─ Main ──► TabNav + VerifyAccountBanner + PushPrimingModal + FeedbackFAB + AnalystGuide
│           ├─ Rank      → RankHome / Trios / Anchors / Tiers / QuickSetTiers /
│           │               QuickRank / ManualRanks / RookieRanks / Trends
│           ├─ Acquire   → TradesHome / TradeDeck / Portfolio / TradeCalculator
│           ├─ Draft     → DraftRoom            (flag draft.tab)
│           ├─ Matches
│           └─ League    → LeagueRankings / LeagueHome
└─ pushed: Settings · Profile · FeedbackInbox · LeagueSummary · FreeAgents ·
           DraftRoom · MockDraft · PickAssignment · RecordPicks · TestStages ·
           SleeperConnect · EspnConnect · PremiumRankingsBrowser
```

Details and sharp edges: [src/navigation/CLAUDE.md](src/navigation/CLAUDE.md).

## Where to make a change

| Task | Go to |
|---|---|
| New screen | `src/screens/` + register in `src/navigation/TabNav.tsx` or `RootNav.tsx` + add its route to `src/utils/deepLinks.ts` |
| New API call | `src/api/` (always through `client.ts`) |
| New shared UI | `src/components/`, built from `src/components/chalkline/` primitives |
| Colors / spacing / type | `src/theme/chalkline.ts` — never inline hexes or px |
| New wire field | `src/shared/types.ts`, matched to `docs/api-reference.md` |
| New regression guard | `tests/check-*.js` + an `npm run test:<name>` script (see `tests/README.md`) |
| Proving a change works | Structural guard + a file:line code-walk, plus a TestFlight checklist for the operator — **not** a Maestro run (D-056) |
