# Maestro flows — FTF mobile smoke tests

Run against a booted iOS Simulator with the app installed (built via
`npx expo run:ios` or installed from EAS).

## Setup

```bash
# Maestro CLI (one-time, requires brew)
brew install mobile-dev-inc/tap/maestro

# JDK is bundled as a brew dep, but you need to point at it:
export JAVA_HOME=/opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home
export PATH=$JAVA_HOME/bin:$PATH

# Build + install on simulator (first time ~10min)
cd mobile
LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 npx expo run:ios
```

## Run

```bash
cd mobile

# Single flow
maestro test .maestro/01-launch.yaml

# Whole suite
maestro test .maestro/

# Studio (interactive — pick selectors visually)
maestro studio
```

Screenshots land in `.maestro/screenshots/` (Maestro's default).

## Flows

| File | What it covers |
|---|---|
| `01-launch.yaml` | Cold start, sign-in screen renders. |
| `02-demo-session.yaml` | Demo bootstrap → main tabs visible. |
| `03-tiers-render.yaml` | Rank → Tiers menu, screen renders. |
| `04-tabs-navigation.yaml` | Trades / Matches / League tabs render. |
| `05-feedback-capture.yaml` | Floating feedback FAB → compose note → save. |
| `06-tiers-drag-no-crash.yaml` | Regression for the worklet crash fixed in `f5c8bc3`. |

Flows 02–06 start from the demo CTA, which only renders when the
`landing.try_before_sync` flag is ON — it is OFF in the release flag set,
so run the backend with it overridden (e.g. `sim-run.sh --flags`).

## Selectors

Flows match on `testID`s from the registry in
`mobile/src/components/CLAUDE.md` wherever one exists (repaired 2026-07-12
after the 1.7.x copy changes); text matchers are the fallback for
elements without an id. When a flow flakes after a UI tweak, update the
matcher, don't loosen it.
