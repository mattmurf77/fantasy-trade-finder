# Feature Scope — Counterparty breaker

**Date:** 2026-08-21
**Entry point:** direct operator ask (relayed via the tweet-product-gap-review session; item 3 of the three-plan batch: Receipts · Negative-results memory · Counterparty breaker)
**Builder:** counterparty-breaker planning session (branch `claude/counterparty-breaker-plan`)
**Operator sign-off on waivers:** PENDING — waivers listed in §3/§4 below are surfaced in PLAN.md §9 (decision register) and must get a yes before build. **This scope covers the PLANNED feature; no build starts until the doc suite is operator-approved.**

---

## 1. Analytics scope

- [x] **(b) Existing events cover it** — no new client events in v1.
  - `deck_outcomes.action` (`viewed | like | pass | not_interested | propose | undo`) — the outcome measures. The breaker's effect question ("does naming the counterparty's likely objection change like/propose behavior?") is answered by joining outcomes to the breaker stamp in `deck_impressions.features_json.breaker` (uniform-keys rule, see §2), split by flag state.
  - `trade_pass_reasons` layer-1/layer-2 codes (`database.py:5580-5582`) — the calibration measure. The breaker's top objection is expressed **in the same vocabulary** as the shipped decline-reason codes, so "predicted objection" vs "actual pass reason filed" is a direct join, no new instrumentation.
  - If the PRD lands a tappable "why they'd hesitate" UI element (vs. a plain narrative sentence), that adds a taxonomy row (`breaker_hesitation_expanded` or similar) — **deferred to the PRD**; registering an event and its emitter in the same commit per CLAUDE.md if that variant wins.

## 2. Schema & flag scope

- **New/changed tables or columns: none in v1.** The breaker result rides the card (`fit_diag`-precedent: attribute on the card object → copied into `deck_impressions.features_json` at impression-log time). The `breaker_` table prefix is RESERVED for this feature (coordinated with siblings: `receipts_` = Receipts, `negmem_` = negative-results memory) but v1 claims no tables. Stamp mechanics must respect the `save_deck_impressions` executemany first-row-keys trap (`database.py:5427`; precedent guard `test_impressions_uniform_columns`): the `breaker` key present (null-valued when unscored) on **every** row of a deck. *(Errata 2026-08-21, round-3 review: `save_deck_impressions` is at `database.py:5503` in this checkout, not `:5427`.)*
- **New feature flags** (both default **false**, both in `config/features.json` + `FLAG_KEYS` + `docs/config-reference.md`):
  - `trade.breaker` — compute + stamp only. Dark-measurement first, zero user-visible effect, zero ordering effect. Graduation criterion: stamp coverage ≥99% of served cards with no p95 job-time regression, and the calibration readout (PLAN §6) runs once.
  - `trade.breaker_narrative` — the on-card "their likely hesitation" line (product outcome 2). Requires `trade.breaker`. Graduation criterion: operator TestFlight pass + the A/B readout in PLAN §6.
  - Product outcome 1 (filter/demote) is **v2, not flagged here** — it gets its own scope block if/when the operator elects it (bright-line: it changes deck composition; see PLAN §3 for the interleave-discipline constraint that keeps it out of v1).
- **New `model_config` keys:** `breaker_*` family (severity thresholds per objection class, `breaker_min_severity` for the narrative line, `breaker_ms_budget`). Exact list is LLD territory; every key follows the five-registration rule (`trade_service.py:869-877`) and carries a documented disable value. **Deploy-free rollback lever:** `trade.breaker_narrative → false` (hot reload) kills the user-visible surface; `trade.breaker → false` kills compute entirely; knob levels 0 restore byte-identical behavior with flags on.
- **Env vars: none.**

## 3. Evidence scope

- [x] **Unit tests:** `backend/tests/test_trade_breaker.py` (new) — objection determinism (same inputs → same top objection), vocabulary closure (every emitted code exists in the shared taxonomy / `trade_pass_reasons` extension set), per-class predicate correctness on fixture rosters, severity ordering, flag-off byte-identity (organic decks unchanged; module never imported — `test_organic_never_imports_fit` precedent), interleave safety (breaker stamp present, deck ORDER unchanged on bake-off decks — `bypass_rerankers` discipline), stamp uniformity (extend `test_impressions_uniform_columns`), narrative honesty (the sentence never names a position/player the objection evidence doesn't contain — D-053 precedent).
- [x] **Code-walk proof:** file:line-cited trace of the stamp seam (post-ranking, pre-impression-log, `stamp_fit_diag` precedent at `server.py` M3 site) and of the narrative composition site in `trade_narrative.build_narrative` — written at build time, per D-056.
- [x] **Structural guard:** `mobile/tests/check-breaker-card.js` — REQUIRED. Verified 2026-08-21: **no client renders `TradeCard.narrative`** (arm-B audit refuted section + fresh grep — only a comment at `mobile/src/components/TradeCard.tsx:437`), so the hesitation line must be a distinct card element (the PLAN's amended default, decision register #3). The guard pins: element gated on the `breaker` payload key + `trade.breaker_narrative`, no render when absent, Chalkline-token styling assertions per the repo's structural-test idiom.
- [x] **Manual TestFlight checklist:** required before `trade.breaker_narrative` graduates (the line is user-visible copy). Drafted in the PRD; run by the operator; logged in TEST_LEDGER. Not required for `trade.breaker` (no user-visible surface).
- [ ] **WAIVED:** none claimed at scope time.
- `testID`s added/renamed: the hesitation element (e.g. `trade-card-breaker-hesitation`) — exact names in the LLD; must pass `mobile/scripts/testid-lint.sh`.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | planned | `trade_card_to_dict` gains additive optional `breaker` object (code, severity, sentence); no new routes in v1 |
| `living-memory/LLD.md` | planned | new convention: objection codes anchor on `trade_pass_reasons` vocabulary; breaker stamp rides `features_json` uniform-keys |
| `docs/architecture.md` | planned | new module row (`backend/trade_breaker.py`) + data-flow line in the trade-card lifecycle |
| `living-memory/HLD.md` | planned | evaluation-layer addition (generator arms → **breaker evaluation** → presentment → serving) |
| `docs/cross-client-invariants.md` | planned | objection-code enum IF any client ever switches on codes; n/a in v1 (server-composed sentence only) — row filled either way at build |
| `docs/glossary.md` | planned | "breaker", "objection", "hesitation line" |
| ADR or `DECISIONS.md` entry | planned | the objection-vocabulary-equals-decline-taxonomy decision + the v1 stamp-only/interleave-safety decision |

Shared artifact: `docs/plans/shared/trade-shape-taxonomy.md` (seeded by the Receipts session; this plan cites it and contributes the objection-vocabulary section; changes only by PR touching that file).

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (+ `check-*.js` suites) + `maestro-testid-lint` on the pushed sha. `FTF_SKIP_SIM_GATE=1` standing posture (D-056), evidence noted.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry at each merge naming what ran and what it proved.
- **TestFlight verification:** required before `trade.breaker_narrative` lights; checklist authored in the PRD.
- **Express lane declared by the operator?** **No — full gates, explicitly** (the assigning brief states "This is NOT express").
- **Change-control:** serving-affecting flips obey the one-engine-change-per-tester-week rule (`docs/plans/trade-engine-accuracy/PLAN.md`) and go through `scripts/set_knob.py` so `model_config_changes` logs them.
