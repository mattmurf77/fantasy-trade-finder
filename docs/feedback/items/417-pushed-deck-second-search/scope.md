# Feature Scope — FB-417: no second, unanchored search from the pushed anchored deck

**Date:** 2026-09-03
**Entry point:** feedback #417 (operator report, v1.16.14, screen `TradeDeck`)
**Builder:** Claude session, branch `feat/fb417-pushed-deck-research`
**Operator sign-off on waivers:** not needed — no waivers. Every section is answered.

Full requirements and the code-walk proof: [prd.md](prd.md). Evidence timeline:
[investigation.md](investigation.md).

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** No new event, no changed property set.

  | Event | Answers | Change under #417 |
  |---|---|---|
  | `find_trades_tapped` | "how many searches did this deck start, and from where" — `{mode}` alone = a page-level CTA tap, `{source, mode}` = an attributed one | **Shapes unchanged.** Emitter census 4 → 3: the legacy `!consolidateOn` CTA arm's inline emitter is gone because that arm now calls `handleFindTrades()`, whose no-`source` branch sends the identical `{mode: deckMode}` row. Registered props untouched |
  | `calc_find_a_trade_tapped` (`{path, give_count, has_partner}`) | the landing fork — this is the row that proved the repro | Untouched |
  | `trade_card_viewed` (`{card_index, trade_id, mode}`) | the regression signature itself: two `card_index: 0` rows with different `trade_id`s and no swipe between them | Untouched. **This is the metric that says the fix worked** — that pattern must stop appearing on `TradeDeck` sessions with `path: fair` |
  | `deck_search_all_tapped` | the anchored deck's own exit, which is now one of only two search controls on that page | Untouched; more of the surviving traffic will carry it |

  Follow-through: nothing stored, so no `docs/data-dictionary.md` change; no taxonomy edit
  (pinned by `check-results-push.js` § 7, which asserts no new registration).

  Deliberate, stated: hiding the CTA on the pushed anchored deck removes the source-less
  `{mode: deck}` emission **from that surface by construction**. That emission was the defect.
  Every other surface keeps emitting it.

## 2. Schema & flag scope

- New/changed tables or columns: **none** → `docs/data-dictionary.md` n/a.
- New/changed feature flags: **none.** `calc.results_push` (D-171 ruling 5, LIT) stays the kill
  switch for this whole surface; with it off `isResultsPushed` is false and every predicate
  added here is inert. Pinned by assertion 8q (no #417 key in `config/features.json`).
- New env vars / `model_config` keys: **none** → `docs/config-reference.md` n/a. Deploy-free
  rollback lever, since this ships LIT: flip `calc.results_push` false (+ `calc.canvas_results`
  true) — the pre-existing D-171 kill switch, unchanged by this work.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-results-push.js` § 8 — 18 assertions
      (`8`, `8a`–`8q`; 23 printed lines) pinning: one shared derivation of the anchored-deck CTA suppression and
      both arms gated on it; both mounts still existing; the anchored deck's replacement search
      controls all present; `handleFindTrades` resetting a fair deck *before* dispatching and
      not touching the pin store; `handleSearchAllTrades` still routing through it; the legacy
      arm calling `handleFindTrades()` with no bare `dispatchGenerate`; the sweep arming
      `fairSweepPending` at entry and disarming at exactly its two post-epoch-guard exits; the
      reset disarming it; both CTA `disabled` predicates and the landing cell reading it; no new
      flag. **Each proven red by a named sabotage and restored green** — table in
      [build-notes.md](build-notes.md). Dependency-free plain node; existing
      `npm run test:results-push` script (no new script needed).
- [x] **Unit tests:** no backend pytest change — this is a client-render/dispatch defect with no
      server surface. `backend/tests` unchanged and green in CI as the pre-ship gate.
- [x] **Code-walk proof:** [prd.md](prd.md) § 7.2 — four file:line-cited traces (pushed fair
      deck → no CTA; receipt Clear → reset → clean model deck; landing double-tap during the
      sweep; pushed **model** deck → "Find more trades" still appends).
- [x] **Manual TestFlight checklist:** [prd.md](prd.md) § 7.3 — 10 numbered steps with expected
      results, including the two states that must NOT change (model deck on the pushed page,
      "Find more trades" append). Runtime proof genuinely matters here: the whole defect is a
      render gate plus a millisecond-scale race, and D-056 leaves TestFlight as the only runtime
      evidence mobile gets.
- [x] **WAIVED because:** n/a — nothing waived.
- `testID`s added/renamed: **none.** `mobile/scripts/testid-lint.sh` green.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed, removed or contract-changed. `POST /api/trades/fair-packages` and the generate/poll pipeline are called exactly as before |
| `living-memory/LLD.md` | n/a | No schema/route/invariant *convention* shifted. The change is one screen's render gate and one dispatch precondition, both inside conventions LLD already describes (the #330 single choke point, the epoch guard, `dispatchGenerate` as the only routed dispatch) |
| `docs/architecture.md` | n/a | No module wiring or data-flow change — no new module, no new call, no new client/server edge |
| `living-memory/HLD.md` | n/a | No architecture shift: no new module, client or major flow. The D-171 push flow is the one that already exists |
| `docs/cross-client-invariants.md` | n/a | No shared constant, enum, colour or threshold touched. `match_score: 0` on fair cards is unchanged (the fix removes the mixing, not the encoding) |
| `docs/glossary.md` | n/a | No new domain term. `fairSweepPending` / `findCtaHiddenForAnchoredDeck` are local React state and a local derivation, not user- or cross-client vocabulary |
| ADR or `DECISIONS.md` entry | n/a | No design choice overturned: this **enforces** D-171 rulings 1–2 and the D-153 fork rather than amending them. The four re-specced structural pins are recorded in [build-notes.md](build-notes.md) with dated `#417` notes in the suites themselves |

Item-local docs written: this file, [prd.md](prd.md), [status.md](status.md),
[build-notes.md](build-notes.md), plus a row in `docs/feedback/items/INDEX.md`.

## 5. Ship gate declaration

- **CI green:** `mobile-typecheck` (`npx tsc --noEmit`, clean) + all **89** `mobile/tests/check-*.js`
  suites green (the 32 that mention `TradesScreen` re-run explicitly) + `maestro-testid-lint`
  (`bash mobile/scripts/testid-lint.sh`, OK). `backend-tests` untouched by this change and to be
  confirmed green on the pushed sha by CI.
- **Evidence recorded:** to be logged in `living-memory/TEST_LEDGER.md` by the shipping session
  (sabotage table + command results are in [build-notes.md](build-notes.md) meanwhile). This
  branch is **not** pushed or merged by the building session, per its instructions.
- **TestFlight verification:** checklist written (§3); operator to run, outcome to TEST_LEDGER.
- Express lane declared by the operator? **No** — full gates were run.
