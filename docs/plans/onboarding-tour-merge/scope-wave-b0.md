# Feature Scope — Wave B0: the layout merge (`calc.inline_home`)

**Date:** 2026-08-24
**Entry point:** [`docs/plans/onboarding-tour-merge/plan.md`](plan.md) §3b / §7 wave B0, decided as [D-158](../../../living-memory/DECISIONS.md)
**Builder:** agent session on `feat/inline-home-b0`
**Operator sign-off on waivers:** not needed — no waivers. Every section below is answered.

**One sentence:** behind a new dark flag `calc.inline_home`, the guided (Find a Trade)
landing hosts the In-league calculator canvas inline above the deck — build-or-find from one
surface, an anchored search shown as a filter receipt — and the pushed Calculator page drops
its In-league tab.

---

## 0. What ships, and the hard rule

| Piece | Flag ON | Flag OFF (the shipped state) |
|---|---|---|
| Guided landing | mounts `TradeBuildCanvas` (= `InLeagueCalculator` wholesale) above the deck, wired with Find a Trade + ✓ | no canvas, unless the unit holds the #270 experiment variant — unchanged |
| Suggestion rail | dropped (the deck below IS the rail; each card's edit action loads the canvas) | present on the experiment path |
| Find a Trade | in place: [D-153] fork → fair sweep or model, results below. No navigation, no `FinderHandoff` | pushed page → handoff → `popTo('TradesHome')`, unchanged |
| Anchored deck | `trades.anchor-receipt` filter row above the results (Change / Clear) | the end-of-deck "Search all trades" exit, unchanged |
| Deck edit hand-offs (×3) | load the inline canvas + scroll | `navigate('TradeCalculator', {prefill})`, unchanged |
| Pushed `TradeCalculatorScreen` | Real values only; no mode tabs, no In-league branch, tour suppressed | two tabs, prefill-lands-in-league, tour intact |
| Mode-bar Calc chip | reads `Real values` (still pushes the page) | reads `Calc` |

**The hard rule this wave was built to:** with the flag false, EVERY surface renders exactly
as it did before. §3's code-walk is the proof, and `mobile/tests/check-inline-home.js` is what
keeps it true.

**Functionality-loss guard (D-158's explicit operator constraint):** the inline canvas is
`InLeagueCalculator` *verbatim* — format chips + #191 note, league/team dropdowns, tier-badged
columns, verdict, eveners, adjustments disclosure, lineup impact, share, Send-in-Sleeper,
outlook row, action row. Every In-league feature arrives because the component does, not
because it was re-implemented; `check-calc-merged-behavior.js` 18–19d keeps pinning it.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it — no new events.**

| Event | Where it now lives | What it answers |
|---|---|---|
| `calc_find_a_trade_tapped` `{path, give_count, receive_count, has_partner}` | `mobile/src/utils/canvasSearch.ts:52` — the ONE emitter, called by both hosts (`TradeCalculatorScreen.tsx:823`, `TradesScreen.tsx:2625`) with a different `screen` label | which fork a canvas took, from either entry |
| `calc_trade_queued` `{queued, reason?}` | `mobile/src/utils/queueCalcTrade.ts:75` — the ONE emitter, both hosts | the ✓ outcome, from either host |
| `find_trades_tapped` `{source:'calculator', mode}` | unchanged — `runFairPackages` (`TradesScreen.tsx:2790`) and the choke point's model branch (`:2588`) | the inline search is attributed as a calculator-sourced dispatch, exactly as the pushed hand-off was |
| `deck_search_all_tapped` | unchanged — `handleSearchAllTrades`, now also reached by the receipt's **Clear** | anchor drops, whichever control did it |
| `trade_edit_in_calculator_tapped`, `deck_back_to_calculator` | unchanged, still emitted before the (now in-place) load | the hand-off is still measurable |

The two "moved" emitters are the same event names with the same registered property sets;
only the `screen` label differs between hosts, which the taxonomy already allows. `screen` is
an envelope field, not a registered prop, so no taxonomy edit is required — and
`check-inline-home.js` §6c/6d/6h assert exactly one emitter per event and no new registration.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. No migration, no `docs/data-dictionary.md` change.
- **New/changed feature flags:** `calc.inline_home`, **default false (dark)**.
  - `config/features.json` (with `_comment_inline_home`)
  - mirrored `false` into `backend/tests/fixtures/flags/release.json`, `onboarding-v2.json`,
    `profiles-on.json` — `test_seed_ui_test_db.test_release_flags_mirror_features_json` is an
    EXACT mirror on release, and the other two are what the onboarding/profile suites boot from
  - registered in `backend/feature_flags.py` `FLAG_KEYS` (`test_entitlements.test_features_json_keys_known`
    fails otherwise — this is how the first full pytest run caught it)
  - documented in `docs/config-reference.md`
  - **Prerequisite:** `calc.merged_layout` must stay true. The two routes the inline surface
    calls (`POST /api/trades/fair-packages`, `POST /api/trades/queue`) are gated on it and 404
    `feature_disabled` when it is off. This flag gates no route of its own — it is client-only.
  - **Graduation:** the Wave B0 section of
    [`docs/feedback/items/384-calc-finder-merge/testflight-checklist.md`](../../feedback/items/384-calc-finder-merge/testflight-checklist.md).
    **Do not light it before Wave B** unless a tour-free calculator is acceptable (see §6).
  - **Kill switch (deploy-free):** set `calc.inline_home` false →
    `POST /api/feature-flags/reload`. No client build; every surface reverts to the two-tab shape.
- **New env vars / `model_config` keys:** none. `fair_packages_cap` is consumed as-is.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-inline-home.js` + `npm run test:inline-home`.
      Pins, in ten sections: the flag ships false and is mirrored into all three fixtures and
      backend `DEFAULT_FLAGS`; **exactly one** canvas mount, with the flag path outranking the
      #270 experiment and the experiment's own gates (`!firstRun && !singlePin`) intact; the
      rail dies only on the flag path and its prop defaults to today's behavior; no
      `onShowMeAround` reaches the inline mount; the pushed page's tour is suppressed at BOTH
      doors, with the guard as a dep, and `utils/calcTour.ts` is untouched; the fork and the ✓
      queue are each ONE function with TWO callers and no second emitter; the inline search
      neither navigates nor writes a handoff, stamps `deckOrigin`, and adds no
      `generateMutation.mutate` site; the receipt's Clear IS `handleSearchAllTrades` and both
      end-of-deck Search-all buttons stand aside for it; all three prefill navigations survive
      for the flag-off path; the chip table still says `Calc`.
- [x] **Updated existing guards to the new truth** (never deleted to make them pass):
  - `check-calc-merged-behavior.js` — assertions 13/13a/13b re-pointed at
    `utils/canvasSearch.ts` (the fork moved files, the contract did not), plus new 13c–13e
    (one definition, two callers, no inline emitter, the handoff carries the fork's anchor
    verbatim); 18a–18f re-pointed at `utils/queueCalcTrade.ts`, plus 18h/18i.
  - `check-offer-prefill-330.js` — the choke-point region/dep pattern now admits the added
    `canvasRunSeq` trigger (the three original deps are still required, in order).
  - `check-calc-tour.js` 15a — the auto-start's dep list gained `inlineHomeOn`, the fifth guard.
  - `check-trades-banner-region.js` and the other 74 suites needed no change and still pass.
- [x] **Unit tests:** no backend pytest added. **Why none:** the wave adds no route, no schema,
      no server behavior; the only backend edit is one string in `FLAG_KEYS`, which the existing
      `test_entitlements.test_features_json_keys_known` and
      `test_seed_ui_test_db.test_release_flags_mirror_features_json` already cover. Full suite
      re-run as a regression check (§5).
- [x] **Code-walk proof — the flag-off byte-identity claim.** Every behavior change in this
      wave passes through one of these sites; each is shown with its flag-off value.

  **`mobile/src/screens/TradesScreen.tsx`**
  - `:667` `const inlineHomeOn = useFlag('calc.inline_home')` — the file's ONE read.
  - `:4887` `canvasHost` — flag-off the first ternary arm is dead, so the value is
    `homeInlineVariant === 'canvas' && … ? 'experiment' : null`, i.e. **literally the old mount
    condition**. `:6198` is the single `<TradeBuildCanvas>`; flag-off it receives
    `showSuggestionRail={true}` (`canvasHost === 'experiment'`), `onFindATrade`/`onLikeTrade`/
    `prefill`/`prefillSeq` all `undefined` — and `TradeBuildCanvas.tsx:76,109` default the rail
    to `true` while `:125` early-returns when `prefillSeq === undefined`, so the experiment
    variant renders exactly what it rendered before.
  - `:4901` `inlineAnchorShown` — flag-off `canvasHost !== 'flag'`, so it is `false`
    unconditionally. That makes `:6224` (the receipt) unreachable and turns `:6881` /
    `:6975` back into their original `calcMergedOn && fairDeck` / `fairDeck` conditions.
  - `:1410`, `:2855`, `:2940` — the three `if (inlineHomeOn) { loadCanvasPrefill(…); return; }`
    early exits sit ABOVE the untouched `navigation?.navigate?.('TradeCalculator', {prefill})`
    calls; flag-off control falls straight through to them.
  - `:2607` the choke point's dep list gained `canvasRunSeq`. `:742` initialises it to `0` and
    `:2644` (`setCanvasRunSeq`) is inside `handleInlineFindATrade`, which is only ever passed as
    a prop on the flag path (`:6205`) — so flag-off the dep is a frozen `0` and the effect fires
    on exactly the transitions it always did.
  - `:2620`–`:2683` (`handleInlineFindATrade`, `handleInlineLikeTrade`, `handleAnchorChange`,
    `loadCanvasPrefill`) are **definitions with no flag-off caller**. Declarations, not effects.
  - `:725`–`:743` are four unused-when-off state slots and one ref; no render reads them
    without `inlineAnchorShown` or `canvasHost === 'flag'`.

  **`mobile/src/screens/TradeCalculatorScreen.tsx`**
  - `:127` the ONE read. `:129` `prefill && !inlineHomeOn ? 'league' : 'live'` ⇒ flag-off
    `prefill ? 'league' : 'live'`, the original expression. `:193` same shape for the re-assert.
  - `:233` the auto-start's fifth guard is `|| inlineHomeOn` ⇒ flag-off the condition is the
    original four. `:257` adds it as a dep (a guard that is not a dep is frozen — that is the
    rule `check-calc-tour.js` 15a already enforced for the other four).
  - `:685` `{inlineHomeOn ? null : (<View style={styles.modeRow}>…)}` ⇒ flag-off renders the row.
  - `:747` `!inlineHomeOn && mode === 'league' && …` ⇒ flag-off the original condition.
  - `:782` `!inlineHomeOn && guidedAvatarActive() && guideV2Active()` ⇒ flag-off the original pair.
  - The two extracted handlers keep the same call shapes: `forkCanvasSearch` returns the same
    `path`/`anchor` the inline code computed, and the handoff spread at the `setHandoff` call is
    `...(anchor ? { fairAnchor: anchor } : {})` — the same object under the same condition.
    `queueCalcTrade` performs the same request, emits the same one event and returns the same
    six refusal lines; the screen still owns the `Toast`.

  **`mobile/src/components/TradeFinderModeBar.tsx`**
  - `:121` the ONE read; `:147` `c.key === 'calc' && inlineHomeOn ? 'Real values' : c.label`.
    `CHIPS` (`:44`) is untouched, so the array's object identity, order and testIDs are the same
    in both states, and flag-off every label is `c.label` — today's strings.

  **`mobile/src/components/TradeBuildCanvas.tsx`** — no flag read at all. Every change is a
  new optional prop with a today-preserving default, so an experiment mount that passes none of
  them is unchanged.

- [x] **Manual TestFlight checklist:** a **Wave B0** section added to
      [`docs/feedback/items/384-calc-finder-merge/testflight-checklist.md`](../../feedback/items/384-calc-finder-merge/testflight-checklist.md)
      — 5 flag-OFF regression steps (the byte-identity claim is the risk that matters while the
      flag is dark) and 14 flag-ON steps for when it lights. Runtime proof genuinely matters
      here: the inline search re-uses a choke point whose ordering (reset → fork → dispatch) is
      only observable at runtime, and no simulator exists to observe it (D-056).
- **`testID`s added:** `trades.anchor-receipt`, `trades.anchor-receipt.change`,
  `trades.anchor-receipt.clear` — all three are string literals in the grammar
  (`<surface>.<element>[.<sub>]`), so no `testid-lint` allowlist entry was needed.
  `bash mobile/scripts/testid-lint.sh` → `testid-lint OK`.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed or contract-changed. `POST /api/trades/fair-packages` and `POST /api/trades/queue` are consumed exactly as documented, from a second caller. |
| `living-memory/LLD.md` | **n/a** | No schema, route or invariant *convention* shifted. The flag-per-behavior + one-read-per-file convention this wave follows is the one already recorded. |
| `docs/architecture.md` | **n/a** | Backend module wiring and data flow unchanged; this is a mobile layout wave. |
| `living-memory/HLD.md` | **n/a** | No new module, client or major flow — an existing component gains a second host. |
| `docs/cross-client-invariants.md` | **n/a** | No shared constant, enum or color introduced. `CALC_QUEUE_REASONS` moved files inside the mobile client; its values are untouched. |
| `docs/glossary.md` | **n/a** | No new domain term. "canvas", "anchor", "filter receipt" are all already in use from #384/#231. |
| ADR / `DECISIONS.md` | **already exists** | [D-158](../../../living-memory/DECISIONS.md) is the decision this wave builds; nothing in the build overturned it, so no new entry. |
| `docs/config-reference.md` | **updated** | New `calc.inline_home` row directly under `calc.merged_layout`. |
| `mobile/src/screens/CLAUDE.md` | **updated** | `TradesScreen` and `TradeCalculatorScreen` rows. |
| `mobile/src/components/CLAUDE.md` | **updated** | `TradeBuildCanvas`, `TradeFinderModeBar`, `InLeagueCalculator` rows. |
| `mobile/src/utils/CLAUDE.md` + `README.md` | **updated** | Two new helpers. |
| `mobile/tests/README.md` | **updated** | The new guard's row. |

## 5. Ship gate declaration

- **CI green — run locally on this branch:**
  - `cd mobile && node node_modules/typescript/bin/tsc --noEmit` → clean, no output
  - all **78** `npm run test:*` guards → `FAILED: none`
  - `bash mobile/scripts/testid-lint.sh` → `testid-lint OK`
  - `python3 -m pytest backend/tests -q` → `4230 passed, 1 skipped`
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`, dated entry naming each gate.
- **TestFlight verification:** the Wave B0 checklist is written and **unrun** — the flag is
  dark, so the flag-OFF regression steps are what the next build should cover; the flag-ON
  steps wait on the operator lighting it.
- **Express lane declared by the operator?** No — full gates.

## 6. Known limits, stated rather than discovered

1. **The tour is OFF wherever this flag is on.** Beat n10 ("Tap In league") is an `action`
   beat that only advances on the real tab switch, and this wave deletes the tab. Rather than
   leave a runner that cannot clear its first beat, `TradeCalculatorScreen` refuses to start the
   tour and renders no "Show me around" while the flag is on, and the inline canvas is mounted
   without an opener. **Wave B** retargets the calculator beats at the inline module. Lighting
   `calc.inline_home` before then ships a calculator with no walkthrough.
2. **A zero-league user sees no canvas**, by construction (`canvasHost` requires `leagueId`).
   The guided landing already has nothing to build a trade *in* without one; the mode bar's
   `Real values` chip is the reachable calculator for that user, which is exactly the #310
   promise the pushed page now exists solely to keep. Plan §3b's "No league? Real values →"
   link near the canvas is **not built** in B0 — the relabeled chip already carries it, and a
   second link to the same destination is the kind of duplicate entry §15 of the #384 review
   removed. Recorded here so it is a choice, not an omission.
3. **The #270 experiment does not close in this wave.** D-158's rollout says
   `trades_home_inline.canvas` "graduates/closes when this lands"; the flag path outranks it, so
   a unit holding both sees the layout, but the variant's own code path stays alive and assigned
   until the operator closes the experiment. Removing it while `calc.inline_home` is dark would
   delete a live experiment arm to serve a feature nobody can see yet.
4. **`fairDeck` is the receipt's lifetime.** The "Built around" label lives only as long as the
   deck it describes, because it is gated on `fairDeck`, which every path that starts or
   invalidates a model search already clears. The label string itself is not cleared on those
   paths — it is simply unreachable. Deliberate: one write site beats five.
5. **The end-of-deck "Back to calculator" button survives flag-on**, now as a scroll. It keeps
   its `deck_back_to_calculator` event and pin payload, so the series is continuous across the
   flag flip rather than dropping to zero on the same surface.

## Post-review fixes (lead, 2026-08-24)

The Fable review pass verified flag-off byte-identity hunk-by-hunk and found one real gap, fixed
before merge:
- **B1 — a FOURTH prefill site.** `MatchesScreen`'s "edit in calculator" navigates cross-tab into
  the pushed page, which flag-on silently dropped the package (no In-league mode left to land in).
  Fixed: flag-on it routes to the guided landing with a `canvasPrefill` route param that
  TradesScreen consumes into the one loader (`check-inline-home` 9d–9f); flag-off navigate
  verbatim. Checklist step 99 covers it.
- **B3** — this wave's ledger/checklist self-references were re-pointed when the Wave-A rebase
  relettered the checklist section H → I (steps 79–98).
- Reviewer notes accepted as-is: B2 (the #270 experiment arm gains an inert wrapper View — render
  tree only), and the `fairDeck`-is-the-receipt's-lifetime stance (one write site, stated).

