# Feature Scope — Trade-suggestion presentation v2

**Date:** 2026-08-18
**Entry point:** direct ask — operator decision 2026-08-18: *"build and ship it as a new tab in the acquire page for now. Shouldn't stop anything we're already doing."*
**Builder:** mobile build agent, branch `feat/trade-presentation-v2`
**Operator sign-off on waivers:** **NOT YET OBTAINED — three items below need an operator call before this ships.** See §6.

Design source (operator-approved, do not redesign): `mockups/trade-suggestion-redesign/`.
Research basis: `docs/research/matchmaking/round-2/05-presentation-and-conversion-engineering.md` §1/§5, `round-2/02` §2.6–2.7, `round-2/04` T1/T2/T7.

Governing principle, in the lab's own words: **"Scarcity is the endorsement — not the catalog."**

---

## 0. What was built, and what was deliberately not

### Built

| Lab state | Where it lives |
|---|---|
| `01-todays-trade` — one endorsed hero per league per cycle; binary badge; asymmetric two-sided explanation; fairness as a range band | `mobile/src/components/presentation/EndorsedTradeCard.tsx` + `FairnessRangeBand.tsx` |
| `03-bench` → Featured — small collapsed set beneath the hero with the browse exit | `mobile/src/components/presentation/FeaturedBench.tsx` |
| `09-browse-all` — the **uncapped** ranked list, per-row dismiss, dismissed-state acknowledgement + Undo | `mobile/src/screens/TradeBrowseAllScreen.tsx` + `components/presentation/TradeIdeaRow.tsx` |
| `04-confidence` — three labeled bands, no percentage, data-volume cap | `mobile/src/components/presentation/ConfidenceChip.tsx` + `utils/tradePresentation.ts` |
| `07-honest-empty` — the price-feedback pivot | `mobile/src/components/presentation/HonestEmptyState.tsx` |

Hosts: `mobile/src/screens/TodaysTradeScreen.tsx` (states 01/03/04/07) and `mobile/src/screens/TradeBrowseAllScreen.tsx` (state 09).

### Deliberately NOT built — blocked, not forgotten

| Lab state | Why it is blocked |
|---|---|
| `02-meso-variants` | MESO return-package variants come from `backend/trade_gen_v2.py`, which is **dark**: `trade_gen.v2` is `false` and has never served a card outside the bake-off's direct-call arm. There is no source of three equivalent-value return shapes for one centrepiece. Building a variant picker over synthesised alternates would be a fake — it would elicit a preference against packages the engine cannot actually produce. **Unblocks when `trade_gen.v2` serves.** |
| `05-turn-states` | Needs a per-thread state machine (`your_move \| their_move \| stalled \| expiring \| ended`). Nothing in `backend/` models a trade *thread* at all — `trade_matches` records dispositions, not turns, and there is no expiry clock. This is a backend feature with a UI, not a UI feature. **Unblocks when the thread model exists.** |
| `08-push-copy` | Notification copy, not a screen. Belongs to the notification pipeline, not this surface. |
| `06-mutual-reveal` | Out of the brief's scope list. The existing Matches inbox already implements double-opt-in reveal; re-skinning it was not requested and would have touched a shipped surface. |

---

## 1. Analytics scope

**(b) Existing events cover it.** No new event names, and that is the point.

| Event | Fires when | Why it is the SAME event, not a new one |
|---|---|---|
| `deck_card_viewed` | a card is front-of-view for ≥500 ms | The impression spine must not fork. A `presentation_card_viewed` twin would split every downstream estimator (Thompson propensity, taste vectors, fatigue, the three-model bake-off) into two incomparable populations. |
| `trade_pass_layer1` / `trade_pass_layer2` | the decline-reason panel's progressive commits | Same taxonomy, same panel component, same `postDeclineReason` module. |

**Dispositions ride the unchanged `POST /api/trades/swipe`** through the exported `swipeTrade(card, decision, signal)` — the identical function `TradesScreen`'s `swipeMutation` calls — carrying the identical `SwipeSignal` (`impression_id`, `dwell_ms`, `detail_expanded`, `calc_opened`). The type is *imported*, not redeclared, so a field added upstream cannot silently go unsent here.

**One knowable gap, recorded rather than papered over.** The events carry no property distinguishing which surface emitted them. Adding one (`surface: 'deck' | 'presentation_v2'`) would be an analytics-taxonomy change, which the bright line in CLAUDE.md says is not a quick fix — and it is not needed while the flag is OFF and nobody is on the surface. **Before the flag is turned on for anyone, that property must be specced against the taxonomy and added to both emitters**, or the two surfaces' data will be indistinguishable in every query. Logged in §6 as an operator decision.

Parity is enforced mechanically, not by assertion: `mobile/tests/check-presentation-v2.js` §4 pins the shared imports, the exact event names, the four signal fields, the two-part `signal_v2 && impression_id` gate, the boolean-only free-text property, the explicit `platform` prop, and the two duplicated timing constants against `TradesScreen`'s own literals.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. No backend route was added or changed.
- **New/changed feature flags:** `trades.presentation_v2` — **default OFF**.
  - `config/features.json` (with a `_comment_trades_presentation_v2` stating ON *and* OFF behaviour) ✔
  - `backend/feature_flags.py` `FLAG_KEYS` ✔ (registration only — **no route reads this key**; it is client-only and is registered so the `test_features_json_keys_known` guard accepts it and `/api/flags` serves it)
  - `docs/config-reference.md` ✔
  - Deliberately **absent** from `LAUNCHED_FLAG_DEFAULTS` in `mobile/src/state/useFeatureFlags.ts` — a dark flag listed there paints the chip for one frame before `revalidateFlags` flips it. Pinned by the check suite §7.
  - **Graduation criterion:** the surface-discriminating analytics property from §1 exists, and the operator has run the TestFlight checklist in §3.
- **New env vars / `model_config` keys:** none.
- **Rollback lever:** the flag itself, hot-reloadable via `POST /api/feature-flags/reload`. No deploy needed.

### Reused endpoints — and the fields that do not exist

Endpoints reused verbatim, none added: `POST /api/trades/generate`, `GET /api/trades/status`, `POST /api/trades/swipe`, `POST /api/trades/pass-reason`, `GET /api/rankings/progress`.

The generation call sends **only** `league_id` and `fairness_threshold`, and resolves the threshold through the shared `fairnessOnFromPref` / `fairnessThresholdFor` helpers. This is load-bearing: the server keys its job cache on `fairness_threshold`, so a locally-derived value would kick a *second* full generation and serve a different card set — and therefore a different set of impressions — than the deck for the same user in the same session. `force` is never sent, so this surface can never invalidate a deck the user is mid-triage on. Pinned by the check suite §3.

**Fields the design needs that no shipped response carries.** Per the brief, these are recorded rather than approximated:

| What the lab shows | Status | What ships instead |
|---|---|---|
| A confidence band per card | **No `confidence` field on the wire.** `TradeCard` carries `match_score` (0–100), `fairness` (0–1), `partner_fit` — all winner/score-shaped, none a band. | The band is **read off the two provenance fields that do ship** — `basis` (`divergence` = a real disagreement between two saved boards; `consensus` = the counterparty has not ranked and was priced off consensus) and `real_opponent` (their Elos are real vs noise-randomized). Both boards real → Strong; one side thin → Moderate; consensus-only *and* estimated → Early. That is a reading of shipped fields, and it is exactly what the lab's own band definitions describe ("both boards well-fed" / "thinner data on one side" / "not enough ranked players"). A reciprocated `likesYou` promotes to Strong. Documented at length in `utils/tradePresentation.ts`; **if a server-side `confidence_band` ever lands, delete the derivation and read the field.** |
| "You've ranked 34 of the **60 players this deal touches**" | **Per-deal ranking coverage does not exist.** Nothing computes which of a card's positional universe the user has ranked. | The user's **overall** board coverage from `GET /api/rankings/progress` (`total_completed` / `total_required`), labelled "Your board coverage" — honest about what the number measures. The lab's per-deal denominator is **not shipped**; inventing one would be the confidently-wrong failure the surface exists to prevent. |
| "Your ask on **Jahmyr Gibbs** is above league consensus · Your board RB2 8,900 vs League consensus RB5 7,400" | **Neither datum exists.** There is no blocking-ask diagnosis and no per-player board-vs-consensus pair on any generate/status payload. | The empty state keeps the lab's *structure* (refusal → why → levers → "keep my price" → we'll check again) but replaces the fabricated diagnosis with the levers that genuinely changed the outcome, each read from a real value: the roster count actually swept (`opponents_total`), the fairness threshold the job actually ran at, the decline-suppression count the snapshot already reports, and the user's real board coverage. **The named-blocking-player pivot is not shipped.** |
| A refresh cadence ("refreshes Tue 9:00a") | No cycle clock exists client-side. | The `refreshNote` prop exists on the hero and is currently passed nothing. Renders nothing rather than a guessed time. |

## 3. Evidence scope

- **Structural guard:** `mobile/tests/check-presentation-v2.js` — **87 assertions, all passing**; `npm run test:presentation-v2`. Dependency-free apart from `typescript` (used to transpile-and-run the pure module, the `check-fairness-default.js` idiom). CI globs `tests/check-*.js`, so this gates `main` on landing. It pins:
  1. **Flag-off byte-identity at both call sites** — both `onTodaysTrade` pass sites are ternaries on `presentationV2On` and pass `undefined` when off (a *no-op handler* would still render the control, which is the exact failure mode).
  2. **Flag-off byte-identity inside both components** — the props are optional, the chip/button is built *from the handler's presence*, and `'today'` is asserted **not** to be in the static `CHIPS` array. The routes are asserted registered *and* asserted **not** flag-wrapped.
  3. The server cache-slot agreement (shared helper only; no raw threshold constants; never `force: true`).
  4. Instrumentation parity — shared imports, no hand-rolled `api.post`/`api.get` in the signals hook, exact event names cross-checked against `TradesScreen`, the four signal fields, the two-part gate, boolean-only free text, explicit `platform`, and `VIEWED_MIN_MS` / `DWELL_CAP_MS` matched against `TradesScreen`'s literals.
  5. The five design laws — no `TradeValueBar`, no `Meter`/`fairnessColor`, no `opponent_surplus`, no `partner_fit`, no `match_score`, no `showPercent`, no `.slice()` in browse, dismissed rows retained, no `numberOfLines` anywhere on the surface.
  6. The pure module **executed**: band derivation across all four provenance combinations, the `likesYou` promotion, "no band label contains a digit", the fairness band exposing no winner/margin, `userSideBullets` naming a concrete asset and never leaking `opponent_surplus`, `counterpartyStatement` returning a number-free single string, `partitionDeck` picking the first *endorsable* card and returning **no hero** when none qualifies, the Featured cap, browse remaining uncapped, dismissed cards excluded from hero but retained in browse, and the empty-state copy omitting an unknown roster count rather than rendering zero.
  7. Flag registration in all three places, and absence from `LAUNCHED_FLAG_DEFAULTS`.
- **Unit tests (backend):** none — no backend change.
- **Code-walk proof:** the flag-off byte-identity claim, traced.
  1. `mobile/src/screens/TradesScreen.tsx:658` — `const presentationV2On = useFlag('trades.presentation_v2');`. This is the file's *only* new binding; no state, no query, no render branch, no existing behaviour is touched.
  2. `TradesScreen.tsx:4717-4721` and `:4742-4746` — the two hosts each receive `onTodaysTrade={presentationV2On ? () => navigation?.navigate?.('TodaysTrade') : undefined}`.
  3. `mobile/src/components/TradeFinderModeBar.tsx:121-122` — `const withDraft = onDraft ? [DRAFT_CHIP, ...baseChips] : baseChips; const chips = onTodaysTrade ? [TODAY_CHIP, ...withDraft] : withDraft;`. With `onTodaysTrade === undefined` the second line evaluates to `withDraft` — the *same array reference*, same objects, same order as before this branch existed.
  4. `mobile/src/components/TradeHomeUtilityRow.tsx:45` — `{onTodaysTrade ? (…) : null}`; undefined ⇒ `null` ⇒ no node.
  5. `mobile/src/navigation/TabNav.tsx:455-465` — the two screens register unconditionally (house rule: the flag gates the entry point, not the navigator entry). A registered-but-unreachable route renders nothing; the *rendered* tree is unchanged.
  6. Therefore with the flag off, the Acquire tab's rendered output is byte-identical to `origin/main@a7f8783`, and the existing deck's behaviour is unchanged in **both** flag states.
- **Manual TestFlight checklist** (runtime proof genuinely matters here — this is a new user-facing surface, and under D-056 this is the only runtime evidence mobile gets). Requires `trades.presentation_v2` flipped ON for the tester.
  1. Flag **OFF**, Acquire tab: the chip strip reads exactly `Draft · Guided · Team · Player · Calc · Free agents` (or the five without Draft). **No "Today" chip.** Deck behaves exactly as before. → *If a Today chip appears with the flag off, stop: the gate is broken.*
  2. Flip the flag ON, force-quit, relaunch. Acquire tab: **"Today" now LEADS the strip.** Tap it.
  3. Hero: exactly ONE card. Badge reads `Today's Trade` + `Strong fit`. Confirm there is **no percentage anywhere** on the card.
  4. Explanation: at most three bullets on your side, each naming a player or position that is actually on the card. Their side is ONE sentence naming the manager, containing **no numbers and no player names of theirs**. → *A leaked value or need list here is a privacy defect, not a polish item.*
  5. Fairness: a track with a shaded zone and a marker, labelled "Within league-normal range". → *Any "you win by" wording or a coloured verdict bar is a P3 violation.*
  6. Tap **Pass** (or a decline tile if `feedback.decline_reasons` is on). The card is replaced by the next endorsable one; the pass is private (no toast naming the manager).
  7. Featured: at most 5 rows, each a **different** manager. Tap "Browse all N trades".
  8. Browse: scroll well past row 6 — the list must keep going to N. Tap a row's ✕. **The row must stay in place**, dimmed, reading "Dismissed — we'll rank ideas like this lower" with an Undo. Tap Undo; the row returns to normal.
  9. Back to Today. Confirm the row you dismissed in browse is **not** in Featured (the two views share one dismissed set).
  10. Text size: Settings → Accessibility → Larger Text to maximum. Reopen Today. Every string must **wrap**; nothing may be cut off mid-word or clipped by a row edge.
  11. VoiceOver on: swipe through the hero. The fairness band must announce "Within league-normal range, compared with league consensus" as one element, and the dismiss control must announce which state it is in.
  12. Flip the flag back OFF, relaunch, confirm step 1 again.
- **Maestro flows — AUTHORED, NOT RUN, AND IN TENSION WITH D-056.** Three flows written: `mobile/.maestro/flows/presentation-v2-hero.yaml`, `presentation-v2-browse-dismiss.yaml`, `presentation-v2-honest-empty.yaml`. Id-selectors only; `testid-lint.sh` passes.
  - **The conflict, stated plainly rather than resolved unilaterally.** The build brief for this branch required flow authoring. `living-memory/DECISIONS.md` D-056 (2026-08-15, Status: Active) and `mobile/.maestro/README.md` say the opposite in as many words: *"Do not author, extend, or execute them."* An agent instruction is not an operator decision, so the flows carry an explicit banner recording the tension and were **not executed**. **Whether they are ever run — and whether authoring them was correct at all — is the operator's call**, logged in §6.
  - `presentation-v2-honest-empty.yaml` declares a `# profile: empty-deck` fixture that **does not exist** under `backend/tests/fixtures/`. It is named honestly rather than pointed at `standard`, which would make the flow pass for the wrong reason.
- **`testID`s added:** static — `presentation.hero`, `.hero-title`, `.hero-give`, `.hero-receive`, `.hero-their-side`, `.hero-interested`, `.hero-pass`, `.fairness-band`, `.confidence-cap`, `.rank-more`, `.featured`, `.browse-all`, `.browse-list`, `.browse-count`, `.browse-focus`, `.browse-loading`, `.loading`, `.error`, `.empty`, `.empty-heading`, `.empty-review-board`, `.empty-widen`, `.empty-keep-price`, `.price-kept`, `trades.home-utility.todays-trade`, `trades.finder-mode.today` (from the existing template literal). Template-literal — `presentation.row.*`, `.row-open.*`, `.row-dismiss.*`, `.row-undo.*`, `.row-undo-link.*`, `.row-ack.*`, `presentation.featured.row.*`, `presentation.confidence.*`, each added to `mobile/scripts/testid-lint-allow.txt` with the constructing file:line. `bash mobile/scripts/testid-lint.sh` → **OK**.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed, or contract-changed. Every endpoint is reused verbatim through its existing client module. |
| `living-memory/LLD.md` | **updated** | New "Trade presentation v2" note — the presentation-surface convention (pure derivations in `utils/`, parity-by-reuse instrumentation hook, entry-by-optional-prop flag gating). |
| `docs/architecture.md` | **n/a** | No backend module wiring or data-flow change. The surface is a second reader of an existing flow. |
| `living-memory/HLD.md` | **n/a** | No architecture shift: no new client, no new module boundary, no new major flow — two screens in an existing stack over an existing job. |
| `docs/cross-client-invariants.md` | **n/a** | No shared constant, enum, or colour introduced. `NORMAL_LOW = 0.75` is the *existing* `FAIRNESS_ON_THRESHOLD`, referenced not redefined; it is client-only presentation geometry, not a cross-client encoding. **If web or the extension ever renders this band, it becomes an invariant and must move.** |
| `docs/glossary.md` | **updated** | Adds *endorsed trade*, *Featured tier*, *confidence band*, *league-normal range*. |
| `docs/config-reference.md` | **updated** | `trades.presentation_v2`. |
| ADR / `DECISIONS.md` | **updated** | New decision entry: the confidence band is DERIVED from `basis` + `real_opponent` because no `confidence` field exists — recorded so a future session does not mistake it for an arbitrary heuristic. |

Directory maps updated: `mobile/src/screens/CLAUDE.md`, `mobile/src/navigation/CLAUDE.md`, `mobile/src/components/CLAUDE.md`, `mobile/src/hooks/CLAUDE.md`, `mobile/src/state/CLAUDE.md`, `mobile/src/utils/CLAUDE.md`, `mockups/CLAUDE.md` (lab status).

### Chalkline gaps — `components.md` candidates

Three constructions the design system does not name. All are built from existing tokens only — no new colour, radius, or type size — and each is flagged here rather than quietly added to the system.

1. **Fairness range band** (`FairnessRangeBand.tsx`) — a track carrying a shaded acceptable *zone* plus a marker. The system has `Meter` (single fill, colour = verdict) and `TradeValueBar` (diverging, names a winner); **both are winner-oriented and are banned on this surface**, which is why a third construction was necessary rather than preferred. Tokens: `ink.ink3` track, `semantic.pos` at 22% opacity for the zone, `chalk.base` marker.
2. **Banded confidence chip** (`ConfidenceChip.tsx`) — a `Badge` whose border colour encodes a three-value enum with no numeric readout. Closest precedent is `TradeCard.tsx:794-813`'s filled/hollow real-vs-estimated opponent dot; this generalises it to three states.
3. **Dismissed-row acknowledgement line** (`TradeIdeaRow.tsx`) — a sub-row that appears *beneath* a list row to acknowledge a destructive action in place, with inline undo. The system has toasts (transient, positioned globally); this is persistent and anchored to the row that caused it.

The **selectable option row** and **notched panel** the brief also mentions are already implemented in `DeclineReasonPanel.tsx` and were flagged by the decline-reason scope block; this surface reuses that component rather than re-cutting them.

## 5. Ship gate declaration

- **CI green:** `npx tsc --noEmit` clean ✔ · all 57 `mobile/tests/check-*.js` suites pass, including the new one ✔ · `mobile/scripts/testid-lint.sh` OK ✔ · `backend/tests` — **not run in this worktree** (no Python environment provisioned); the only backend change is a one-line `FLAG_KEYS` addition plus the `config/features.json` entry, which `test_entitlements.test_features_json_keys_known` covers. **Must be green on the pushed sha before merge.**
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming the 87-assertion guard, the typecheck, the lint, and the un-run flows.
- **TestFlight verification:** checklist written in §3; **not yet run** — operator action.
- **Express lane declared?** No. Full gates.

## 6. Open items needing an operator decision

1. **The Maestro conflict.** Flows were authored because the build brief required it; D-056 forbids authoring them. They are un-run and banner-marked. Decide: keep them as written specification, delete them, or amend D-056.
2. **The surface-discriminating analytics property.** `deck_card_viewed` / `trade_pass_layer1` / `trade_pass_layer2` currently cannot tell the two surfaces apart. Adding `surface` crosses the analytics-taxonomy bright line, so it was not done unilaterally. **This must be resolved before the flag is turned on for any user**, or the resulting data is unattributable.
3. **The `empty-deck` fixture.** `presentation-v2-honest-empty.yaml` needs a seeded profile that yields no endorsable card. Not created (out of scope for a flag-off branch), and deliberately not aliased to `standard`.
4. **Two lab states are blocked on backend that does not exist** (`02-meso-variants` on `trade_gen.v2`; `05-turn-states` on a thread state machine). Neither is a gap in this build — both need engine work first.
