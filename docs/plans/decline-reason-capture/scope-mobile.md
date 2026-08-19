# Feature Scope — Decline reason capture (MOBILE half)

**Date:** 2026-08-17
**Entry point:** direct ask — operator-approved spec, [`SPEC.md`](./SPEC.md); approved prototype [`mockups/decline-reason-capture/07-two-step-diagnostic.html`](../../../mockups/decline-reason-capture/07-two-step-diagnostic.html)
**Builder:** mobile build agent, branch `feat/decline-reasons-mobile`
**Operator sign-off on waivers:** **REQUIRED** — see §6. Two items need an explicit yes before merge (§4 Elo suppression is backend-owned but named here; the assumptions in §6 need confirming at integration).

> Scope boundary: this document covers `mobile/**` only. The backend half —
> route, table, flag registration, Elo suppression knob, and the
> api-reference / data-dictionary / config-reference / glossary rows — is
> being built in parallel on `feat/decline-reasons-backend` and owns those
> files. Rows below that belong to that branch say so rather than claiming
> credit or leaving silence.

---

## 1. Analytics scope

**(a) New events specced.** Both are client-emitted from `TradesScreen`, on
the two moments that commit. Property values are enumerated exhaustively
(SPEC §6); `platform` is set explicitly at the emitter and never inferred —
the NULL-`platform` incident is why.

| Event | Properties | Fires when | Client |
|---|---|---|---|
| `trade_pass_layer1` | `reason` (`value`\|`fit`\|`other`), `switched_from` (`value`\|`fit`\|`other`\|`none`), `impression_id` (or the literal `none`), `trade_id`, `ms_since_render` (int), `platform` (`ios`\|`android`\|`web`) | The layer-1 tile tap. **Carries the disposition** — there is no separate pass event on this path. | mobile |
| `trade_pass_layer2` | `reason`, `detail` (the 8 layer-2 codes; 10 since the 2026-08-19 amendment — enum widened, event unchanged), `has_free_text` (bool), plus the five shared props above | A fixed layer-2 option tap, or the free-text send. | mobile |

Consequences that follow, deliberately:

- **Layer-1-without-layer-2 is directly measurable** (`trade_pass_layer1`
  with no matching `trade_pass_layer2` on the same `impression_id`) — SPEC §6
  names this as the signal that a category's options are wrong or missing.
- **The "Other" tap emits NO event.** SPEC §6 says `trade_pass_layer2` fires
  "on the option tap or free-text send"; the Other tap neither advances nor
  terminates, it banks a code and opens a box. Emitting there and again on
  send would double-count every free-text pass in the funnel. The bank is
  therefore a **server write only** — the row is the record, exactly as SPEC
  §3.3 intends ("a tester who opens the box and bails still leaves 'none of
  the listed reasons'"). *Reviewer's call to overturn: if the operator wants
  Other-abandonment visible in analytics as well as in the table, the fix is
  one `track()` call in `handleReasonLayer2Bank` plus a funnel note.*
- **Free text is never an analytics property.** It rides the row write only;
  the events carry the `has_free_text` boolean. Pinned by
  `mobile/tests/check-decline-reasons.js` §3, which walks the AST of every
  `trade_pass_layer*` `track()` call rather than grepping.
- `ms_since_render` uses a dedicated per-fronted-card stamp, **not** the F1
  `dwellRef` — that one only runs under `deck.signal_v2` / `deck.session_rerank`,
  is capped at `DWELL_CAP_MS` and pauses on background, none of which SPEC §6
  asks for.

→ follow-through: the taxonomy doc + `docs/data-dictionary.md` rows for the
stored table are **backend-branch** work.

## 2. Schema & flag scope

- **New/changed tables or columns:** none in mobile. The decline-reason row
  (upsert keyed on `impression_id`, SPEC §3) is backend-branch work →
  `docs/data-dictionary.md` is theirs.
- **New/changed feature flags:** `feedback.decline_reasons` — **default OFF**,
  tester-allowlist scoped (SPEC §5). Mobile consumes it through the normal
  path: `useFlag('feedback.decline_reasons')` against the fetched map.
  - **Deliberately NOT added to `LAUNCHED_FLAG_DEFAULTS`** in
    `mobile/src/state/useFeatureFlags.ts`. That list exists for *launched*
    features that must fail open; a dark, allowlist-scoped diagnostic must
    stay absent so a missing key reads falsy on first paint.
  - Registration in `config/features.json` + `backend/feature_flags.py`
    `FLAG_KEYS` + `docs/config-reference.md` is **backend-branch** work.
  - **Graduation criterion:** operator flips it per tester via the allowlist;
    there is no "on for everyone" state planned — it is a diagnostic, not a
    feature. Kill switch = the same flag going false, which restores the ✕
    on the next successful flag revalidate with no build.
- **New env vars / `model_config` keys:** none.
- **Flag-off parity (the load-bearing claim).** Flag off ⇒ the shipped ✓/✕
  row renders byte-identically:
  - the ✕ `Pressable` is **conditioned** on `disposition.reasons`, never
    deleted, and stays inside the existing `disposition ?` guard (so
    `check-card-disposition.js` still passes unchanged);
  - `disposition.reasons` is `undefined` when the flag is off, so
    `DeclineReasonPanel` never mounts;
  - the two new `ScrollView` props resolve to `undefined`
    (`automaticallyAdjustKeyboardInsets`, `onScroll`/`scrollEventThrottle`),
    which is identical to not passing them;
  - the per-card reset effect returns on its first line;
  - `advance()`'s new `opts` parameter is undefined on every existing call
    site, so both new branches (`deferDeckAdvance`, the banked-card guard)
    are unreachable.
  Pinned by `mobile/tests/check-decline-reasons.js` §1.

## 3. Test scope (mobile test platform)

- **New flows** (no waiver — this is user-visible, SPEC §7):
  - `mobile/.maestro/flows/decline-reasons-fixed-option.yaml` (`TC-DECLINE-01`)
    — the ✕ is gone / the ✓ is present, tile tap opens layer 2 **on the same
    card** (the deck has not advanced), a fixed option advances to the next
    trade with no receipt in between.
  - `mobile/.maestro/flows/decline-reasons-other-free-text.yaml`
    (`TC-DECLINE-02`) — Fit → Other → composer, **the send button is asserted
    visible with the keyboard up** (the regression guard for the keyboard
    problem in §7), text typed, send commits and advances.
  - Both follow the flow-authoring laws: id-selectors only, no fixed sleeps,
    no coordinate taps, `scrollUntilVisible` + `visibilityPercentage: 100`
    before every possibly-below-fold tap (law 2), no `hideKeyboard` (law 20),
    typed input asserted before submit (law 10).
- **Extended flow:** none. `flows/smoke/06-trades-deck.yaml` runs under the
  `release` flag set (feature OFF) and taps `trades.pass-btn` — it must keep
  passing **unchanged**, and does; that is the flag-off proof at the flow level.
- **`testID`s added:** `trades.pass-reasons`, `trades.pass-reason.value|fit|other`,
  `trades.pass-reason.l2.<8 codes; 10 since 2026-08-19>`, `trades.pass-reason.text`,
  `trades.pass-reason.send`. `mobile/scripts/testid-lint.sh` → **OK**. Two
  allow-list globs added (`trades.pass-reason.*`, `trades.pass-reasons`) with
  the constructing file named, per law 4: the ids are object values on the
  SPEC §2 taxonomy table inside `DeclineReasonPanel.tsx`, which is what stops
  the ids and the codes from drifting apart.
- **INTEGRATION DEPENDENCY (blocks the flows from running, not from being
  correct):** both flows declare `# flags: all-on`, and
  `backend/tests/fixtures/flags/all-on.json` does not yet carry
  `feedback.decline_reasons: true`. That file is backend-owned and outside
  this branch's file ownership. Until the backend half adds the key, the
  flows fail at the first `trades.pass-reasons` assert — which is the correct
  failure (the feature genuinely is not on), not a flaky one. Both flow
  headers say so in place.
- **Capture delta:** `trades` (the deck card gains a whole block) — run
  `mobile/scripts/screen-capture.sh --screen trades` at ship, with the flag
  on, so the screen library shows the tile row rather than the ✕.
- **Smoke-suite impact:** only `smoke/06-trades-deck.yaml` crosses this
  surface. Under the release flag set it is untouched. Re-run at ship.
- **New check suite:** `mobile/tests/check-decline-reasons.js`
  (`npm run test:decline-reasons`) — pins flag-off parity, the three commit
  moments and the deferred advance, the free-text/analytics separation, the
  SPEC §2 taxonomy (cross-checked against `SPEC.md` when it is on the
  branch), and the 44pt / no-truncation / a11y-state rules.
- **Backend: pytest** — n/a on this branch; the route, the upsert and the Elo
  suppression tests belong to `feat/decline-reasons-backend`.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **no — backend-branch owned** | The new route (`POST /api/trades/pass-reason` as assumed here) is defined and documented by `feat/decline-reasons-backend`; two branches editing that file is a guaranteed conflict. Mobile's assumption is stated in §6 below and isolated to one file. |
| `living-memory/LLD.md` | n/a | No convention shifted. The client keeps its existing shapes: a thin `api/` module, a `useFlag` gate, `track()` for events. |
| `docs/architecture.md` | n/a | No backend module wiring or data flow changed by the mobile half. |
| `living-memory/HLD.md` | n/a | No new client, module or major flow — one card affordance changed behind a dark flag. |
| `docs/cross-client-invariants.md` | **no — flagged, not edited** | The layer-1/layer-2 codes ARE cross-client enum strings and belong there. Deliberately left to integration: only mobile implements them today, and the backend branch owns the glossary/data-dictionary rows they must agree with. **Follow-up at merge:** add a `§ Decline reasons` block listing the 3 + 8 codes verbatim from SPEC §2. **Still open as of 2026-08-19** (now 3 + 10) — re-checked by the player-preference amendment and deliberately left open: the codes are still backend+mobile only, with no web or extension consumer. |
| `docs/glossary.md` | **no — backend-branch owned** | Per the task's file-ownership split. |
| `docs/design/components.md` | **no — flagged, see §5** | Two new constructions named as candidates rather than added unilaterally. |
| ADR / `DECISIONS.md` | not yet | Three decisions worth recording at merge, listed in §6. No ADR: nothing architectural, all three are local product/interaction calls. |
| `mobile/src/components/CLAUDE.md` | **updated** | `DeclineReasonPanel` row added; `TradeCard` row extended with `disposition.reasons`. |

## 5. Chalkline compliance — and the two gaps

Built from `docs/design/design-system.md` tokens only. No new colors, no new
radii, no gradients/blur, no emoji, no system font stacks. Ice is used for
selection/action, `chalk.faint` for micro-labels, `ink.ink1/2/3` for the
surface steps.

**Two constructions the design system does not name.** Both are implemented
with existing tokens and are **candidates for `docs/design/components.md`,
flagged here rather than added unilaterally:**

1. **Selectable option row** — full-width row, `min-height 46` (≥44pt),
   `--ink-1` fill, 1px `--line`, radius `--r-sm`, 7px status dot in
   `--line-strong` + a wrapping `body` label; selected/pressed = 1px ice
   border, `--ink-3` fill, ice dot. This is the "pick one from a list inside a
   card" shape the system currently has no entry for (the closest existing
   things are the QuickSet chips, which are grid tiles, and `EvenerRows`,
   which is a data row with a + button). Should generalise to any future
   in-card single-select.
2. **Notched panel** — full-width `--ink-2` well, 1px ice border, radius
   `--r-sm`, with a 10×10 rotated hairline square half-buried in its top edge
   pointing at the control that opened it (tile centre = `(i*2+1)/6` of the
   row width for three tiles). The system has sheets, cards and disclosures
   but nothing that visually attaches an expansion to its opener.

**Two deliberate deviations from the prototype**, both toward the system:

- The prototype's mono micro-labels are 8.5–9px; **raised to the 11px type
  floor** (teardown S2 PRD-04 — 11px is the global floor). Rendered in Plex
  Mono, uppercase, wide tracking, which is the shipped micro-label convention
  (TopBar's `LEAGUE`, tier headers).
- Borders on the composer and the option dot use `ink.lineStrongA11y`
  (#59647A, ≥3:1) rather than the legacy `lineStrong`, **without** gating on
  `visual.chalkline_cleanup`. That flag exists to migrate *existing* code; new
  construction should be born at the accessible value.

**Accessibility.** 44pt minimum on every target (tiles 58, options 46, send
44 — all `minHeight`, never fixed, so Dynamic Type can grow them); no
`numberOfLines` or `ellipsizeMode` anywhere in the panel, so labels wrap
rather than truncate; `accessibilityRole="button"` + a spoken label on every
control; tiles report `accessibilityState={{ expanded, selected }}`, options
report `{{ selected }}`; text rendered through the chalkline `Text` primitive
so the `a11y.text_scaling` caps apply (`body` for labels, `dense` for the mono
micro-labels). All pinned by `check-decline-reasons.js` §5.

## 6. Assumptions, decisions and the things needing a yes

**Backend contract assumption (reconcile at integration).** Mobile writes to
**`POST /api/trades/pass-reason`** with:

```
{ impression_id?, trade_id, league_id?, layer: 1|2, reason, switched_from?, detail?, free_text? }
```

fire-and-forget (never blocks the deck, never surfaces an error), server
upsert keyed on `impression_id` per SPEC §3. **All of that knowledge lives in
exactly one file — `mobile/src/api/declineReasons.ts`.** If the sibling
branch's route differs in name, verb, field names, or folds layer 1 into
`/api/trades/swipe`, the integration change is that file and nothing else;
no caller sees the route shape.

Three sub-assumptions inside it:

1. **`impression_id` may be absent** (`deck.signal_v2` off, or a legacy /
   echo-rebuilt card). The panel still renders and still writes; the field is
   omitted and the server is assumed to fall back to `(user, trade_id)`.
   Analytics uses the literal `none`, matching the `switched_from` convention.
   *If the backend requires `impression_id`, the alternative is to gate the
   panel on it — which would make the feature invisible whenever
   `deck.signal_v2` is off. Operator call at integration.*
2. **The disposition still rides the unchanged `/api/trades/swipe` POST.**
   The layer-1 tap calls the existing `advance('pass')` path in full, so Elo,
   session re-rank, onboarding counters, deck fatigue and the F1 signal spine
   all behave exactly as they do for any other pass. Only the deck-index
   increment is deferred. This means the reason write is **additive**, not a
   replacement — if the backend instead expects the reason on the swipe body,
   that is a one-field addition in `api/trades.ts`.
3. **SPEC §4 (Elo suppression) is not implemented here** and is backend-owned.
   Flagging it as SPEC §4 demands: today every pass asserts "my players are
   worth more", which is false for `value_getting`, `fit_*` and `other`.
   **This touches ranking math and must not merge without the operator's
   explicit yes.** Nothing on this branch changes Elo behaviour.

**Decisions taken (candidates for `DECISIONS.md` at merge):**

- **D-a — the swipe-undo window is suppressed while decline reasons are on.**
  A "Passed · Undo" toast under a live layer-2 panel offers to rewind a deck
  that has not moved yet. The tile tap is a deliberate, reasoned gesture, so
  it commits immediately — the same treatment the bad-trade flag already gets.
- **D-b — the ✓ goes inert once a pass is banked, and so do the swipe gesture
  and the VoiceOver pass/like actions.** The card is already dispositioned;
  layer 2 owns what happens next on it. Guarded on the RAW deck id via a ref
  (state alone loses the race when a tap and a gesture land in one React batch).
- **D-c — no analytics on the "Other" bank.** Reasoning in §1.

## 7. Keyboard and the send button — how it is handled

The prototype scrolls the send button into view on open
(`scrollIntoView({block:'nearest'})`). The RN equivalent needed three parts,
because the send button sits **below** the composer and RN's own
focused-input scroll only guarantees the *input* is visible:

1. **`keyboardShouldPersistTaps="handled"`** — already on the main
   `ScrollView`; it is what makes the send tap register on the first tap
   instead of being eaten dismissing the keyboard.
2. **`automaticallyAdjustKeyboardInsets`** (added, flag-scoped) — without it
   the ScrollView's maximum offset stops at the content bottom and there is
   physically no scroll range to lift the button above the keyboard.
3. **Measure-and-ask** — on `keyboardDidShow` *and* on the send button's first
   layout, the panel calls `measureInWindow` on the button and compares its
   bottom edge (plus a 12pt gap) against the keyboard's `screenY`. Any
   positive overlap is handed to the host as `onRevealRequest(dy)`, and
   `TradesScreen` scrolls by exactly that much from its tracked offset. Zero
   overlap ⇒ no scroll, so the panel never jumps when it is already clear.

`hideKeyboard` is deliberately never used (flow-authoring law 20 — it taps
whatever is underneath). `TC-DECLINE-02` asserts the button is visible with
the keyboard up, which is the regression guard for all three parts.

## 8. Ship gate declaration

- **Simulator-gate tier: 2** — feature flows + the affected smoke subset.
  The change is user-visible on the primary surface but confined to one card
  affordance behind a dark flag; it touches no schema, no navigation and no
  auth. Concretely: `TC-DECLINE-01`, `TC-DECLINE-02`, plus
  `flows/smoke/05-trades-render.yaml` and `06-trades-deck.yaml` (the latter
  under the release flag set, as the flag-off parity proof).
- **Not run on this branch.** Nothing is being pushed or merged, and the
  feature flows cannot pass until the backend half registers
  `feedback.decline_reasons` in the flag fixtures (§3). The gate runs at
  integration, on the combined branch.
- Evidence at that run: `living-memory/TEST_LEDGER.md` entry +
  `qa/sim-runs/last-sim-run.json`.
- **Operator deviation from the matrix:** none requested.

### Verification actually performed on this branch

| Check | Result |
|---|---|
| `tsc --noEmit` | Clean. One pre-existing error remains (`ImportRankingsSheet.tsx` → `expo-document-picker` not installed in the shared `node_modules`); confirmed present on a stashed `origin/main` tree, so it is not from this work. |
| `mobile/scripts/testid-lint.sh` | OK |
| All 38 `npm run test:*` check suites | Green, including the two new ones and the pre-existing `test:card-disposition` (the flag-off parity proof) and `test:session-rerank` (shares `advance()`). |
| Maestro flows | Authored, lint-clean. Not executed — see the gate note above. |

## 9. Separate change on this branch — fairness preference now defaults OFF

Operator directive, 2026-08-17. Shipped as its **own commit** so it is
independently revertible from the decline-reason work.

- **What changed.** `ftf:trades:fairness_on` unset now resolves to **OFF**
  (the wide 0.5 net). Previously both read sites read `raw === 'off' ? OFF :
  ON`, i.e. unset meant balanced-only at 0.75.
- **Why.** Widen the net so testers see and judge more trades — with the
  decline-reason capture above collecting their verdicts on the wider set.
- **Explicit choices are preserved.** The new reading keys on the stored value
  being exactly `'on'`. A user who deliberately turned balancing on stays on;
  `'off'` stays off; unset simply now resolves to off. **Nothing clears or
  rewrites anyone's stored preference** — the hydrate is read-only, and the
  test asserts zero writes on the read path.
- **One helper, two readers.** `fairnessOnFromPref()` + `fairnessThresholdFor()`
  live next to the constants in `mobile/src/api/tradePregen.ts`. Both the
  session-init pregen and `TradesScreen`'s generate derive from them, because
  a mismatch sends different `fairness_threshold` values and misses the server
  cache slot (`_trade_job_is_fresh` keys on it), turning the pregen into
  wasted work and the user into a second full wait.
- **The toggle reflects reality.** `useState(fairnessOnFromPref(null))` — the
  control paints OFF for an unset user on the very first frame, matching the
  threshold actually being sent. A hard-coded `useState(true)` was exactly the
  bug this guards against.
- **Known, pre-existing race (unchanged in kind):** a generate fired before the
  mount hydrate completes uses the default rather than the stored value. It
  was there before with the polarity reversed; the affected population flips
  from explicit-`off` users to explicit-`on` users. Not worsened, and the only
  generate on that path is a user tap well after mount. Not fixed here —
  fixing it means making the hydrate a gate, which is a bigger change than the
  directive asked for.
- **Tests:** `mobile/tests/check-fairness-default.js`
  (`npm run test:fairness-default`) — loads and RUNS the real module with a
  recording AsyncStorage shim. Covers unset → off (null / undefined / empty /
  unrecognised), explicit `'on'` → on, explicit `'off'` → off, the pregen read
  site end-to-end for all three, zero writes on read, and six assertions that
  the screen derives from the helpers rather than re-deriving locally.
- **Reaching users requires an app build** — this is a client-side
  AsyncStorage preference, not a server flag. There is no deploy-free lever;
  the rollback is reverting this commit and shipping a build.
- **Analytics:** no new events. Existing `find_trades_tapped` and the deck
  events already carry deck mode; the threshold change is visible server-side
  in the job's `fairness_threshold`.
