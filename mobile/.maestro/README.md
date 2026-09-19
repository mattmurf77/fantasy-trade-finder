# Maestro flows — HISTORICAL ARTIFACT (retired 2026-08-15, D-056)

> **These flows are not run. Do not author, extend, or execute them.**
>
> **D-056 — "Maestro / Simulator Retired Entirely, Not Just as a Gate"**
> (2026-08-15, operator decision, Status: Active) retired Maestro and the
> simulator across every pipeline — not just as a pre-ship gate. Operator's
> words: *"It's unreliable and a waste of tokens."*
>
> The flows in this directory are **deliberately kept**. D-056 explicitly
> rejected deleting them: *"flows document intended behavior even unrun."*
> Read them as a specification of what each screen was supposed to do; never
> as a workflow to run or a checklist to extend.
>
> **What replaced them:**
> | Evidence | Where |
> |---|---|
> | Automated | Structural guards in [`../tests/`](../tests/README.md) (`npm run test:<name>`) + unit tests |
> | Behavioral | A written code-walk proof — a file:line-cited trace through the commit sequence |
> | Runtime | A concrete manual TestFlight checklist for the operator |
>
> **Two things survive D-056:**
> 1. **`../scripts/testid-lint.sh` stays in CI.** Every `testID` these flows
>    reference must still exist in `mobile/src`, so the flows remain
>    load-bearing for the lint even though nothing runs them.
> 2. **The Flow-authoring laws below.** They are the expensive part — 23
>    on-sim-proven rules that would cost weeks to reconstruct if Maestro is
>    ever revived. Kept as a record of what the flows mean.
>
> `FTF_SKIP_SIM_GATE=1` is the standing posture for the `githooks/pre-push`
> hook. `docs/runbook.md` § Pre-ship simulator gate is likewise banner-marked
> historical.

---

## Directory map

106 files. Counts are against `origin/main`.

| Path | Count | What it was |
|---|---|---|
| `01-…` – `06-…` (this level) | 6 | The original 2026-07 smoke set, superseded by `flows/smoke/` |
| `flows/smoke/01…12` | 12 | The final smoke suite — sign-in, league pick, trios, tiers, trades render/deck, calculator, matches, league, canary, Apple entitlement, single-pin |
| `flows/league/` | 8 | League-rankings feature flows: pick subsets, position filter, no-picks league, picks flag-off, drill-in back affordance, position trade candidates, matches-tile scoped, invite-join |
| `flows/rookie/` | 7 | Rookie-draft flows — Draft Room complete / order-not-set, mock loop, mock manual mode, scoped tiers + consolidated, scoped quickset + trios, flag-off no-entry |
| `flows/trade-send/` | 1 | MFL send gating |
| `flows/` (loose) | 13 | P0 remediation (1/5/6), ESPN connect capture, decline-reasons (fixed option + other/free-text), matches awaiting-dismiss, trades banner region, trades-generation failure, tiers-all-board, s1 spikes (×2), guide no-false-signoff |
| `capture/` | 52 | Screen-library capture flows, `<screen>[@profile].yaml`; driven by `../scripts/screen-capture.sh` into `screens/mobile/` + `screens/manifest.json` |
| `capture/sheets/` | 5 | Sheet captures (ESPN link, feedback, league switcher, rank menu, trade DNA) |
| `capture/helpers/inject.js` | 1 | Fault-injection helper for the capture sweep |

The `@profile` suffix on a capture filename (`league@espn.yaml`,
`trios@fresh.yaml`) names the seeded backend profile the flow expected.

---

## Historical: how these were run

Everything below documents the retired workflow. It is preserved for context,
not for use.

### Setup

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

### Run

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

### The original root flows

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

This table predates the later flow families — see the directory map above for
the full inventory (`flows/smoke/01..12`, `flows/league/`, `flows/rookie/`,
`capture/`).

### Selectors

Flows match on `testID`s wherever one exists; text matchers were the fallback
for elements without an id. The testID grammar and registry live in
`docs/plans/mobile-testing/lld.md` Appendix A, cross-checked against source by
`../scripts/testid-lint.sh` — the one part of this harness still enforced.

## Flow-authoring laws (2026-08-10, screen-library build — each paid for on-sim)

Retained per D-056 as the expensive knowledge inside these flows. Every law
below cost at least one debugging round during the 141-capture build-out.
They describe how the retained flows are constructed and why they read the way
they do. **No new flows are authored, so these are a record, not a rulebook.**

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
