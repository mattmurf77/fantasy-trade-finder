# mobile/src/ — Notes for Claude

All app source. Subfolders are organized **by concern, not by feature** — a feature spreads across `api/` + `state/` + `screens/` + `components/` rather than getting its own directory.

| Dir | Use it for | Never put here |
|---|---|---|
| `api/` | Network calls, wire-shape parsing, offline write queues | React, navigation, UI (flag-store reads are the one allowed upward import — `events.ts`, `tradePregen.ts`) |
| `components/` | Reusable UI, prop-driven by default | Data fetching, unless the widget is self-contained (10 exceptions today — see [README.md](README.md)) |
| `data/` | Shared calculator asset types (`calcTypes.ts`) | Fixture/mock data — the demo calculator's `tradeCalcMock.ts` was removed 2026-08-22 (#384) |
| `hooks/` | Cross-cutting React hooks used by ≥2 screens | Screen-local hooks (keep those in the screen) |
| `navigation/` | Stack/tab definitions, navigator-level helpers | Screen bodies |
| `observability/` | Sentry init (`sentry.ts`) | Analytics — that's `api/events.ts` |
| `screens/` | One file per registered route | Anything not reachable from a navigator |
| `shared/` | Cross-cutting wire types (`types.ts`) | Runtime values |
| `state/` | zustand stores, module buses, the QueryClient | Fetching (call `api/`), pure math (use `utils/`) |
| `theme/` | Design tokens | Component styles |
| `transport/` | `credentialVault.ts` — the ONE SecureStore key holding every platform credential | A second credential slot, anywhere |
| `utils/` | Pure functions | React, I/O, module-level state |

## Adding a feature

1. **Wire shapes** → `shared/types.ts`
2. **Fetch** → new module in `api/`, always via `api/client.ts`
3. **Cross-screen state** → `state/` (zustand store or module bus)
4. **Math with a regression risk** → `utils/`, written with **zero runtime imports** so a `tests/check-*.js` guard can transpile and run it under plain node
5. **Screen** → `screens/` + register in `navigation/` + add its route to `utils/deepLinks.ts`
6. **Shared UI** → `components/`, built on `components/chalkline/` primitives
7. **Evidence** → a `../tests/check-*.js` guard plus a file:line code-walk, and a TestFlight checklist item if runtime proof matters. No Maestro flow, no simulator capture (D-056). Run `bash ../scripts/testid-lint.sh` — testID lint is still enforced in CI

## Cross-cutting rules

- **Tokens only.** Colors, spacing, radii, type come from `theme/chalkline.ts`. Position/tier hexes come from `theme/colors.ts` and are cross-client data encodings (`docs/cross-client-invariants.md`) — never local literals.
- **`chalkline/Text` for all new text** — it carries the Dynamic Type caps.
- **Flag-gated routes register unconditionally.** The flag gates the entry point; a stale deep link must land on an honest unavailable state, not a 404.
- **`onboarding.*` flags** are read through `useOnboardingFeature()` / `onboardingEnabled()`, which AND in the master `onboarding.v2`.
- **FeedbackFAB**: tab-stack screens are covered by RootNav's single mount; root-stack pushes render their own with `aboveTabBar={false}`. See the root [`mobile/CLAUDE.md`](../CLAUDE.md).
- Per-directory conventions and sharp edges live in each subfolder's `CLAUDE.md` — read those before editing inside one.
