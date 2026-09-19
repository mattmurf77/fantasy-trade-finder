# mobile/scripts/

Two live checks and a dormant simulator harness.

## Live

| Script | Run via | What it does |
|---|---|---|
| `testid-lint.sh` | `bash scripts/testid-lint.sh` | **Runs in CI.** Cross-checks every `testID` referenced by a `.maestro` flow against `mobile/src`, and bans fixed sleeps, coordinate taps, and text-selector taps in flows. Exit: `0` ok · `1` flow references a missing id · `2` banned pattern |
| `testid-lint-allow.txt` | — | Glob-per-line allowlist for ids the source builds from template literals (`${prefix}.real`, `testID={obj.testID}`), each noting the constructing file. Grep cannot see those; this file is the escape hatch |
| `check-contrast.js` | `npm run test:contrast` | Parses hex tokens out of `src/theme/chalkline.ts` and asserts the WCAG contrast floors the design system commits to. Dependency-free |

`testid-lint.sh` survived the Maestro retirement on purpose: the retained flows still reference real ids, so the lint keeps source and spec honest even though nothing executes the flows.

## Dormant — the simulator harness

**Retired by [D-056](../../living-memory/DECISIONS.md) (2026-08-15).** These are kept, not run. No simulator captures, no Maestro execution, in any pipeline. `FTF_SKIP_SIM_GATE=1` is the standing posture for `githooks/pre-push`.

| Script | What it did |
|---|---|
| `sim-build.sh` | Release-config simulator build with the JS bundle embedded, `FTF_API_BASE_URL` baked in, Sentry DSN nulled; emitted `resolved-config.json` for the runner's preflight. `--env prod-check` statically asserted the shipping config without building |
| `sim-run.sh` | Single-cell executor: seed → start Flask in test mode → handshake → sim erase/boot → install → run flows → collect → stop. Exit: `0` ok · `1` flow failure · `2` infra · `3` rails · `5` bad args |
| `screen-capture.sh` | The only writer of `screens/mobile/` and `screens/manifest.json` — swept every screen in every profile on the canonical simulator, then compressed and manifested |
| `screen-freshness.sh` | Recomputes each screen's declared-source sha256 against `screens/manifest.json`. No simulator, no build, <1s. Exit: `0` fresh · `1` stale · `2` no manifest |
| `mutations.md` | Three seeded breakages ("testing the test system") — apply one, run the suite, the named flow must go red. A drill for the retired suite |

`screen-freshness.sh` is the only dormant script that is still cheap and side-effect-free to run; it reports that the captured screen library is stale, which after D-056 it permanently is.

## Design contract

The harness's env contract lives in `mobile/app.config.js`: with no env set it must be byte-identical in effect to `app.json` alone. `FTF_API_BASE_URL` and `FTF_ENV=test` are the only inputs, and `FTF_ENV=test` nulls the Sentry DSN with `""` (not `null` — `null` survives expo-config serialization as a truthy `{}`). Full spec: [docs/plans/mobile-testing/lld.md](../../docs/plans/mobile-testing/lld.md).
