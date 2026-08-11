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

Newer flow families (this table predates them): `flows/smoke/01..11` is the
current smoke suite; `capture/` holds the screen-library capture flows
(`<screen>[@profile].yaml`, run via `mobile/scripts/screen-capture.sh` —
see `screens/CLAUDE.md`).


## Selectors

Flows match on `testID`s from the registry in
`mobile/src/components/CLAUDE.md` wherever one exists (repaired 2026-07-12
after the 1.7.x copy changes); text matchers are the fallback for
elements without an id. When a flow flakes after a UI tweak, update the
matcher, don't loosen it.

## Flow-authoring laws (2026-08-10, screen-library build — each paid for on-sim)

Every law below cost at least one debugging round during the 141-capture
build-out. New flows follow them; reviews check them. The `maestro-test`
skill's trap list points here.

### Selectors & assertions
1. **Text matchers are FULL-MATCH regex.** `"Easiest sells"` never matches
   `Easiest sells & easiest buys` — wrap in `.*` and verify every string
   against source bytes (killed 5 of 8 flows in one batch).
2. **`visible:` counts off-screen ScrollView children.** Assertions pass while
   taps land on dead coordinates and screenshots frame the wrong region. Use
   `scrollUntilVisible` with `visibilityPercentage: 100` before any
   possibly-below-fold tap or shutter; add `centerElement: true` for taps but
   NOT for tall-card shutters (centring overshoots and crops). Exception:
   virtualized lists (FlatList/DraggableFlatList) genuinely omit off-screen
   children — footers there need real scrolling, and list items scroll fine.
3. **`accessible` containers collapse their subtree.** iOS exposes the grouped
   label ("QA Standard League, 12 teams"), not inner text or testIDs — the 4/4
   ring's numeral is invisible to Maestro; anchor on the accessibilityLabel.
4. **Template-literal testIDs are lint-invisible** (`${prefix}.real`,
   `testID={obj.testID}`) — they need `scripts/testid-lint-allow.txt` entries
   naming the constructing file, never a workaround tap-by-text.

### Timing & state
5. **`waitForAnimationToEnd` can never stabilize on an ActivityIndicator** —
   it waits out the exact busy/loading state it was meant to hold (shipped two
   populated screens labeled "loading"). Shoot immediately after the trigger;
   reserve the wait for static content.
6. **The react-query cache is PERSISTED** (`PersistQueryClientProvider`, keys
   in `App.tsx PERSIST_KEYS`) and several screens use
   `placeholderData: (prev) => prev` — loading states need
   `clearState: true` COLD starts; a warm relaunch shows data instantly no
   matter the injected latency.
7. **An errored query renders the error branch (not the skeleton) on refetch**
   — order error states before loading, or give loading its own cold start.
8. **Tab taps race #244 launch routing.** The tab bar paints seconds before
   routing settles and the Rank stack steals the tap back — settle on the
   surface's own header control (`rank.more-ways`) before any tab tap.
9. **The guide coach-mark swallows the first tap on cold starts**
   (`guide.tap-catcher`, absolute-fill) — guarded conditional dismissal; its
   bubbles spring in over 250 ms and drop mid-animation taps — bounded
   conditional retry, safe only when the tapped step chains to a
   catcher-free step.
10. **Assert the typed username before submitting sign-in** — a raced
    `inputText` submits a partial name and books a real VCR miss. Preambles
    retry with `eraseText` first so retries are idempotent.

### Injection discipline
11. **Budgets:** query-driven GET errors `count: 2` (react-query `retry: 1`);
    `count: 4` when RankMenu or a sibling prefetches the same route under a
    second key; `count: 6` for 502/503/504 GETs (the HTTP client retries
    those 3x ON TOP of react-query); `count: 1` for bare POST mutations.
12. **Inject the endpoint's REAL production error body** — screens render
    `parsed.message || parsed.error`, so the harness default (`ftf_injected`)
    leaks into the captured copy. Grep `backend/server.py` for each route's
    actual JSON.
13. **Arm `fail_next` BEFORE opening any surface that could fire the real
    request.** Ordering is a precondition, not a convenience — an
    injection armed "just before the tap" left earlier steps unguarded and
    one POST reached real ESPN. (Also: ESPN egress is INVISIBLE to the rails
    audit today — Sleeper-only counters; fix task filed.)
14. **Never `/__test__/reset` mid-flow** — it clears backend sessions and
    signs the app out. Order states so leftovers are harmless instead.
15. **`fail_next`/`latency` path globs are `fnmatch` on `request.path`** —
    `"/api/rankings"` is exact; `"/api/rankings*"` also swallows
    `/progress` and `/reorder`.

### Harness & environment
16. **`# flags:` is a RESOLVED fixture filename** under
    `backend/tests/fixtures/flags/` AND a cell-grouping key — prose values
    silently split cells and fall back to defaults. Fixture `_comment*` keys
    are stripped by the runner before sim-run's all-bool validator.
17. **Deep links are dead** (`openLink` → undismissable SpringBoard confirm on
    iOS 18). Use launch-argument entry: `launchApp: arguments:
    {FTFTestRoute: <RouteName>}` after a normal first sign-in launch, then
    relaunch `clearState: false, stopApp: true`. Params are a QUERY STRING
    (`FTFTestRouteParams: 'username=x'`) — never JSON; the argument-domain
    plist parser silently eats values starting with `{`.
18. **The simulator degrades across erase/boot cycles** (same flow 50 s →
    26 min, then XCUITest fails to start; port-7001 reconnect loops read as
    phantom "app crashed"). Full `shutdown` + `erase` + `boot` of the
    canonical UDID fixes it — reset before big runs.
19. **Kill orphans on :5001 before running** (`lsof -ti :5001 | xargs kill
    -9`); a Flask killed mid-WAL-write can corrupt `data/ui-test` — if Flask
    dies at boot with "database disk image is malformed", delete the seed dir
    and reseed.
20. **`hideKeyboard` is a hazard**: it can tap a control underneath (opened a
    native confirm that poisoned every later step) and errors on custom
    inputs. Prefer `pressKey: Enter` on single-line fields, or design the
    keyboard into the frame. Fresh sims may also overlay the one-time
    QuickPath tutorial (`simctl spawn <udid> defaults write
    com.apple.keyboard.preferences DidShowContinuousPathIntroduction -bool
    true` derisks it).
21. **Never combine `--prune` with a profile filter** — prune scopes by
    screen only and will delete other profiles' variant captures.
22. **`PlayerPickerModal` keeps its search text across opens** — `eraseText`
    before every picker search.
23. **A green run is not a good capture.** Eyeball every screenshot: this
    build caught two populated-screens-labeled-loading, three wrong-framing
    shots, and one harness-copy leak that every assertion had passed.
