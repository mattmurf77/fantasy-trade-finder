# Feature Scope — Propose-label spine: impression_id through the send path + `trade_proposed` source

**Date:** 2026-08-29
**Entry point:** direct ask (operator, trade-disposition review 2026-08-29 — prod shows 463 `trade_proposed` user_events but ZERO `deck_outcomes` rows with `action='propose'`, ever; the bake-off's strongest per-arm label never fires)
**Builder:** Claude session (worktree `app-entry-platform-options-3e16ac`)
**Operator sign-off on waivers:** PENDING — analytics-event change hits the feature-gate bright line; ship is held for a confirming yes (noted by the operator in the ask itself)

---

## 0. Diagnosis (what the investigation actually found)

The operator's hypothesis was "the client never sends `impression_id` on the propose
request." The code walk refines that:

- `trade_proposed` is **server-fired on a deck LIKE**, not on a send — two emitters:
  `/api/trades/swipe` (`backend/server.py` ~12781, `source="api"`) and
  `/api/trades/queue` (~13318, `source="calc_queue"`). The 463 events are likes.
- The `propose` outcome writes only in the real send routes
  (`/api/trades/propose` ~16274, `/api/trades/propose-mfl` ~28236) via
  `_save_deck_outcome_safe(body.get("impression_id"), "propose", ...)` — silent no-op
  without the id.
- `SendInSleeperButton` forwards `impression_id` correctly whenever its
  `impressionId` prop is set (`mobile/src/components/SendInSleeperButton.tsx:228`),
  and the **deck** mount has passed it since 2026-07-26
  (`mobile/src/screens/TradesScreen.tsx:8110`, gated on `deck.signal_v2` — TRUE in prod).
- The gap: in the current flow (v1.16.11 canvas browse → "Interested" = like →
  navigate to Matches → send from Matches), **sends happen from MatchesScreen**, whose
  mounts (`TradeCard.tsx:978/995`) pass no `impressionId` — and *cannot*, because
  `/api/trades/matches/all` and `/api/trades/awaiting` don't return one. The
  calculator mount legitimately has no impression.

So the fix is (a) backend: recover the caller's impression for match/awaiting rows via
the F1 `trade_hash` identity (`_deck_trade_hash(give, receive, partner)` — the exact
triple both rows carry) and return it; (b) client: thread it through the shapes into
the existing `impressionId` prop; (c) the `source` prop on `trade_proposed` so likes
are attributable to a surface without the impression join.

## 1. Analytics scope

- [x] **(a) New events specced:** no new event NAMES — one new property on two
  existing server-fired events, same-commit with the emitters per taxonomy rules:

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `trade_proposed` (existing) | + `source`: `deck` \| `browse` \| `today` \| `shop` \| `calculator` \| null | unchanged (like via swipe/queue) | server-fired |
  | `match_swiped` (existing) | + `source`: same enum, null when client omits/unknown | unchanged (pass via swipe) | server-fired |

  Trigger for the value: the swipe POST body gains an optional `surface` field
  (client-sent, validated server-side against a closed enum — unknown/absent ⇒ null,
  never a raw passthrough). `/api/trades/queue` stamps `source: "calculator"`
  server-side. NULL-`platform` lesson applied: closed enum, explicit at every
  emitter, old clients degrade to null rather than a wrong value.
  → follow-through: `backend/analytics_taxonomy.py` comment updated same commit;
  no new stored tables (`props` JSON only), so `docs/data-dictionary.md` n/a.

## 2. Schema & flag scope

- New/changed tables or columns: **none** (`deck_outcomes.action='propose'` already
  exists in the enum; `user_events.props` is schemaless JSON)
- New/changed feature flags: **none** — everything rides existing `deck.signal_v2`
  gating (impression enrichment + outcome writes are inert with it off)
- New env vars / `model_config` keys: **none**

## 3. Evidence scope

- [x] **Unit tests:** `backend/tests/test_deck_signal_v2.py` — new tests: swipe with
  `surface` records `props.source`; invalid surface ⇒ null; `/api/trades/awaiting`
  and `/api/trades/matches/all` return `impression_id` for a hash-matching owned
  impression (and omit it flag-off / no-match / ghost).
- [x] **Code-walk proof (mobile thread):**
  `/api/trades/awaiting` response `impression_id` →
  `normalizeTradeMatch`/awaiting normalizer (`mobile/src/api/trades.ts`) →
  `matchToTradeCardShape`/`awaitingToTradeCardShape` (`MatchesScreen.tsx:1644/1676`) →
  `TradeCard` `data.impression_id` → `SendInSleeperButton impressionId` prop
  (`TradeCard.tsx:978/995`) → propose body `impression_id`
  (`SendInSleeperButton.tsx:223-229`) → `_save_deck_outcome_safe(..., "propose")`
  (`server.py:16274`). Surface thread: `swipeTrade(card, decision, signal, surface)`
  → body `surface` → swipe emitter `props.source`.
- [x] **Manual TestFlight checklist** (runtime proof matters — this is a prod-data
  no-show):
  1. Like a deck card (Find a Trade), go to Matches → "Awaiting them", send it in
     Sleeper. Expect: a new `deck_outcomes` row `action='propose'` for that
     impression (operator: `SELECT action, acted_at FROM deck_outcomes ORDER BY id DESC LIMIT 5;`).
  2. Like a browse ("All trades") card. Expect newest `trade_proposed` row has
     `props.source='browse'`.
  3. Queue a calculator trade (✓ cell). Expect `trade_proposed` with
     `props.source='calculator'`.
- `testID`s added/renamed: none

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `/api/trades/swipe` (+`surface`), `/api/trades/matches/all` + `/api/trades/awaiting` (+`impression_id`), `/api/trades/queue` (props.source) |
| `living-memory/LLD.md` | n/a | no convention shift — extends the established F1 impression-spine pattern |
| `docs/architecture.md` | n/a | no module wiring change |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | updated | swipe-surface enum is a cross-client value set |
| `docs/glossary.md` | n/a | no new term |
| ADR / `DECISIONS.md` | n/a | mechanism follows D-056/F1 precedent; no non-obvious choice beyond this scope block |

## 5. Ship gate declaration

- **CI green:** pytest backend/tests + tsc --noEmit + testid-lint — run locally before push; CI must confirm on the sha
- **Evidence recorded:** TEST_LEDGER entry at ship
- **TestFlight verification:** checklist §3 handed to operator (it is the only runtime evidence)
- Express lane declared by the operator? **No** — full gates; ship additionally held on the bright-line confirming yes (analytics-event change).
