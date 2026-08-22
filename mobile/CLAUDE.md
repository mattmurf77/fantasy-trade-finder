# mobile/ — Notes for Claude

React Native / Expo iOS app. Ships as **Fleeced: Dynasty Trade Finder** (D-057); `app.json → expo.name` is `Fleeced`. Talks to the Flask backend in `backend/` over HTTP. Android is configured but iOS is the shipping target.

MAP, not a changelog — present behavior only. History: `git log -- <file>` and `living-memory/CHANGELOG.md`.

## Entry points

| File | Role |
|---|---|
| `index.ts` | Expo entry shim — `registerRootComponent(App)` |
| `App.tsx` | Root: Sentry wrap → gesture root → SafeArea → `PersistQueryClientProvider` → `RootNav`. Owns boot gating, deep-link listeners, and the AppState fan-out |
| `src/navigation/RootNav.tsx` | Root stack (SignIn → LeaguePicker → Main) |
| `src/navigation/TabNav.tsx` | Bottom tabs + per-tab stacks |
| `app.json` | Expo config (name, version, plugins, `extra.apiBaseUrl`, EAS project id) |
| `app.config.js` | Layers test-harness env over `app.json`. With no env set it is a no-op — `FTF_API_BASE_URL` and `FTF_ENV=test` are the only inputs |
| `eas.json` | EAS build profiles (`development` / `preview` / `production`) + iOS submit config |
| `tsconfig.json` | `expo/tsconfig.base`, `strict: true` |
| `babel.config.js`, `patches/` | Build config; `patch-package` runs on `postinstall` |

### App.tsx boot contract

Splash is gated on **local** legs only — `bootstrap()`, `loadCachedFlags()`, `hydrateOnboarding()`, `hydrateQuicksetProgress()` — plus font readiness. Everything network (`revalidateSession`, `getTierConfig`, `revalidateFlags`, `warmPlayerCache`) is detached and best-effort. Do not add a network await to the boot gate.

Also mounted here: TanStack Query `focusManager` ← AppState, `onlineManager` ← NetInfo, the analytics + recorded-picks offline queues, and the persisted query cache (`PERSIST_KEYS`, 30 min `maxAge`).

## Source layout

| Dir | Purpose | Doc |
|---|---|---|
| `src/api/` | HTTP clients. No React, no state | [src/api/CLAUDE.md](src/api/CLAUDE.md) |
| `src/components/` | Reusable UI; `chalkline/` primitives, `analyst/` mascot, `draft/` draft rows | [src/components/CLAUDE.md](src/components/CLAUDE.md) |
| `src/data/` | `calcTypes.ts` — shared calculator asset types | — |
| `src/hooks/` | Cross-cutting React hooks | [src/hooks/CLAUDE.md](src/hooks/CLAUDE.md) |
| `src/navigation/` | Stacks, tabs, re-tap registry, rank chooser model | [src/navigation/CLAUDE.md](src/navigation/CLAUDE.md) |
| `src/observability/` | `sentry.ts` — init wrapper, no-ops without a DSN | — |
| `src/screens/` | One file per route (32) | [src/screens/CLAUDE.md](src/screens/CLAUDE.md) |
| `src/shared/` | `types.ts` — wire types shared across api/screens/components | [src/shared/CLAUDE.md](src/shared/CLAUDE.md) |
| `src/state/` | 12 zustand stores, 3 module buses, the QueryClient | [src/state/CLAUDE.md](src/state/CLAUDE.md) |
| `src/theme/` | Chalkline tokens + data-encoding hexes | [src/theme/CLAUDE.md](src/theme/CLAUDE.md) |
| `src/transport/` | `credentialVault.ts` — the single SecureStore credential envelope (`ftf.platformCreds`) | [src/README.md](src/README.md) |
| `src/utils/` | Helpers. No React | [src/utils/CLAUDE.md](src/utils/CLAUDE.md) |
| `assets/` | App icon / adaptive icon / splash / favicon | [assets/CLAUDE.md](assets/CLAUDE.md) |
| `.maestro/` | Retained UI flows — **historical, never run** (D-056) | [.maestro/README.md](.maestro/README.md) |
| `scripts/` | testID lint + contrast guard (live); sim build/run/capture harness (dormant per D-056) | [scripts/README.md](scripts/README.md) |
| `tests/` | 50 dependency-free structural guards run under plain node | [tests/README.md](tests/README.md) |
| `ios/`, `android/` | Prebuilt native projects (checked in — `expo prebuild` output) | — |

The iOS project folder is `ios/DTFDynastyTradeFinder/` and the Expo slug is `dtf-dynasty-trade-finder`. Both keep the pre-rename identifiers **deliberately** (D-057) — scheme/project names are invisible to users, and renaming would churn Pods, workspace, scheme and EAS config for nothing. The bundle ID `com.fantasytradefinder.app` is immutable and stays. The display-name change is two lines: `expo.name` in `app.json` and `CFBundleDisplayName` in `ios/DTFDynastyTradeFinder/Info.plist` (bare workflow — `app.json` alone does nothing).

## Commands (from `package.json` / `eas.json` — do not invent others)

```bash
cd mobile
npm install                 # postinstall runs patch-package

npm start                   # expo start
npm run ios                 # expo run:ios  (native build + install on simulator)
npm run android             # expo run:android
npm run web                 # expo start --web

npx tsc --noEmit            # typecheck (strict)
npm run test:contrast       # WCAG token-contrast guard
npm run test:<name>         # one structural guard; see tests/README.md for the list

bash scripts/testid-lint.sh # flow ↔ source testID cross-check (runs in CI)
```

EAS (profiles in `eas.json`):

```bash
eas build --profile production --platform ios
eas submit --profile production --platform ios   # ascAppId 6771488431
```

The simulator harness in `scripts/` (`sim-build.sh`, `sim-run.sh`, `screen-capture.sh`, `screen-freshness.sh`) is **dormant per D-056** — retained, not run. See [scripts/README.md](scripts/README.md).

## Rules that apply to every mobile change

### Design — Chalkline (ADR-004 / ADR-005)

Tokens: [`src/theme/chalkline.ts`](src/theme/chalkline.ts). Specs: [docs/design/design-system.md](../docs/design/design-system.md) + [docs/design/components.md](../docs/design/components.md). Live reference: [web/style-guide.html](../web/style-guide.html).

Hard NEVERs: emoji as icons · gradients · glassmorphism/blur · Inter/Roboto/system font stacks · radius >8px (except specced pills) · accents other than ice (actions) and flare (informational highlights only).

Position and tier hexes are **data encodings**, not chrome — they live in `src/theme/colors.ts` and are governed by [docs/cross-client-invariants.md](../docs/cross-client-invariants.md); they must match web + extension.

New text goes through `components/chalkline/Text`, never a bare RN `<Text>` with a hand-written `maxFontSizeMultiplier`.

### FeedbackFAB (#188)

Every new user-facing screen shows the feedback FAB.

- **Tab-stack screens need nothing** — `RootNav.tsx` mounts one `<FeedbackFAB activeScreen={activeScreen} />` inside the `Main` screen, above `<TabNav />`. Adding a second is the #196/#197 double-FAB bug.
- **Root-stack pushes render their own**: `<FeedbackFAB activeScreen="<RouteName>" aboveTabBar={false} />`. Live examples: `FreeAgentsScreen`, `LeagueSummaryScreen`, `DraftRoomScreen`, `MockDraftScreen`, `PickAssignmentScreen`, `RecordPicksScreen`, `PremiumRankingsBrowserScreen`.
- `DraftRoomScreen` is dual-registered; the tab copy is passed `initialParams {inTabs:true}`, which suppresses its local FAB because RootNav already covers it.
- Exceptions: modals/sheets and onboarding flows. Screens with a pinned bottom bar call `setPinnedBottomBarHeight` (exported from `FeedbackFAB`) instead of mounting a second FAB — `TiersScreen`, `QuickSetTiersScreen`, `QuickRankScreen` do this.

### Evidence for a change (D-056, 2026-08-15)

**Maestro and the simulator are retired.** No flow authoring, no flow extension, no flow execution, no simulator captures — for any change, in any pipeline. `FTF_SKIP_SIM_GATE=1` is the standing posture for the pre-push hook. Do not budget Maestro work in a plan or PRD.

What replaces it:

| Evidence | How |
|---|---|
| Automated | Structural guards in [`tests/`](tests/README.md) (`npm run test:<name>`) + unit tests. Behavior that is a claim about code *shape* — placement, unconditional render, a marker's presence — gets a new `tests/check-*.js` guard |
| Behavioral | A written **code-walk proof**: a file:line-cited trace through the commit sequence. This is what a sim capture used to be |
| Runtime | A concrete manual **TestFlight checklist** for the operator, specific enough to actually catch the regression |
| Typecheck | `npx tsc --noEmit` |

**`testid-lint` survives and stays in CI.** `testID`s referenced by the retained flows must still pass `scripts/testid-lint.sh`; template-literal ids need an entry in `scripts/testid-lint-allow.txt`.

`.maestro/` is **kept but never run** — the flows document intended behavior even unrun. Treat them as a historical spec, not a workflow. See [.maestro/README.md](.maestro/README.md).

### Feature flags

Flags come from `/api/flags` via `state/useFeatureFlags`. `onboarding.*` features must be read through `useOnboardingFeature()` / `onboardingEnabled()` (master `onboarding.v2` **AND** the individual flag). Flag-gated *routes* stay registered unconditionally — the flag gates the entry point, not the navigator entry.

## Conventions

- **Search tracked files only**: `git ls-files mobile`, `git grep -n "pattern" -- mobile`. Never bare `grep -r` from the repo root.
- Version bumps live in `app.json → expo.version`; `eas.json` uses `appVersionSource: remote` with `autoIncrement` on production builds.
- Secrets never land here — credentials live in the gitignored `secrets.local.env` at the repo root.
- New wire fields go in `src/shared/types.ts` and must match the backend's JSON (`docs/api-reference.md`).
