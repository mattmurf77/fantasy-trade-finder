# Tracking-plan addendum — #384 merged calculator + finder

**Date:** 2026-08-22 (amended same day for W6-A) · **Status:** adopted with the #384 registration commit; `calc_trade_queued` adopted with the W6-A route commit
**Parent:** [2026-07-17-tracking-plan-v2.md](2026-07-17-tracking-plan-v2.md) §S3
**Origin:** [../../feedback/items/384-calc-finder-merge/review-2026-08-22-e2e.md](../../feedback/items/384-calc-finder-merge/review-2026-08-22-e2e.md) § Analytics · plan [../../feedback/items/384-calc-finder-merge/plan.md](../../feedback/items/384-calc-finder-merge/plan.md) W2/W4
**Registries touched:** `backend/analytics_taxonomy.py` (`ALLOWED_CLIENT_EVENTS`, `CLIENT_EVENT_PROPS`) and `backend/analytics_queries.py` (`NON_INTENT_EVENTS`). **Not** `FUNNEL_CRITICAL`, **not** `SERVER_FIRED_EVENTS` — both omissions argued below.

The taxonomy is **default-deny**: an unregistered client event is counted and
dropped at ingest *behind a 200*, and an allowlisted event with no
`CLIENT_EVENT_PROPS` entry raises at **import**. This addendum is the
precondition `analytics_taxonomy.py`'s docstring demands.

## Why now

The #384 e2e review found the W4 guided tour already firing three names the
backend had never heard of (`calcTour.ts:100/53/72`), and `prompt_deferred` —
live since the prompt arbiter shipped — never registered at all, so the tour's
own `blocked_by:'tour'` signal landed nowhere. Everything below is registered
**before or with** its emitter; the four names with live emitters are
registration-only and their prop rows mirror what those emitters send today.

Mobile only. Web (`web/js/events.js`) and the extension fire none of these —
neither surface has the merged calculator or the deck.

## The events

| Event | Screen | Class | Fires when |
|---|---|---|---|
| `calc_tour_started` | TradeCalculator | **non-intent** (mount counter) | the guided tour starts — auto on landing, or from "Show me around" |
| `calc_tour_ended` | TradeCalculator | **non-intent** (terminator) | the tour finishes its last beat or is abandoned |
| `calc_tour_beat_missing` | TradeCalculator | **non-intent** (defect diagnostic) | a scripted beat id no longer resolves to a builder; the tour steps over it |
| `calc_mode_switched` | TradeCalculator | **intent** | the In-league / live mode chip is tapped |
| `calc_include_players_toggled` | TradeCalculator | **intent** | the include-players control is toggled |
| `calc_asset_added` | TradeCalculator | **intent** | an asset is added to either side |
| `calc_cleared` | TradeCalculator | **intent** | the trade is cleared |
| `calc_find_a_trade_tapped` | TradeCalculator | **intent** | the calculator's own Find-a-Trade hand-off is tapped |
| `deck_back_to_calculator` | Trades | **intent** | the end-of-deck "back to calculator" return is tapped |
| `deck_unpin_retry` | Trades | **intent** | "find a trade without `<player>` pinned" is tapped |
| `trade_pass_overlay_opened` | Trades | **non-intent** (exposure) | the #384-local decline-reason **overlay** is presented |
| `trade_pass_overlay_dismissed` | Trades | **non-intent** (dismissal) | that overlay is dismissed |
| `prompt_deferred` | any | **non-intent** (system refusal) | the interrupt arbiter refuses a surface the slot — once per deferral episode |
| `calc_trade_queued` **(W6-A, added 2026-08-22)** | TradeCalculator | **intent** | the merged action row's ✓ answers — recorded, already recorded, or refused |

### Props

| Event | Prop | Type / values | Why |
|---|---|---|---|
| `calc_tour_started` | `source` | `auto` \| `show_me_around` | The tour the product forces and the tour a user asked for are not comparable completion rates. Both entry points are `startCalcTour`'s only arguments. |
| `calc_tour_ended` | `reason` | `finished` \| `abandoned` | Completion vs drop-out. |
| | `beats_shown` | int ≥ 0 | Beats actually rendered at exit — where the tour loses people. The pre-fix emitter zeroed its counter *before* reading it and sent `beats_shown: 0` on every row (the e2e review's finding); it now snapshots first. **A window in which every row reads 0 is that bug returning**, not a tour nobody sees: beat 1 renders before any exit can fire. |
| `calc_tour_beat_missing` | `beat` | script beat id (`n10`…`n24`) | A hole in the sequence is a script defect; the id says which. Bounded vocabulary owned by `analystScript.ts` — never copy. |
| `calc_mode_switched` | `mode` | `live` \| `league` | The mode switched **to**. Same vocabulary as `calc_cleared.mode`. |
| `calc_include_players_toggled` | `on` | bool | The **resulting** state (post-toggle), the `untouchable_toggled.marked` convention. |
| `calc_asset_added` | `side` | `give` \| `receive` | The `player_menu_opened.side` / `finder_target_pinned.side` vocabulary. |
| `calc_cleared` | `mode` | `live` \| `league` | Which calculator was cleared. |
| `calc_find_a_trade_tapped` | `include_players`, `give_count`, `receive_count`, `has_partner` | bool, int, int, bool | The calculator's **shape at hand-off** — the only way to read whether people leave for the finder from an empty calculator or a half-built trade. No player ids, no names. |
| `deck_back_to_calculator` / `deck_unpin_retry` | `pin_count` | int ≥ 0 | Separates "the finder returns nothing with three pins" from "the user changed their mind" — the question both affordances exist to answer. |
| `trade_pass_overlay_opened` | *(none)* | — | Deliberately empty. The card is already identified by `trade_card_viewed` and by the `trade_pass_layer*` rows on the same card; a `trade_id` here would be a third source of truth for one interaction (#208/#248/#293). |
| `trade_pass_overlay_dismissed` | `banked` | bool | Dismissed-with-a-reason-banked vs dismissed-having-said-nothing. It is the **only** measure of whether the overlay presentation costs reasons the inline tiles were getting. Never the free text (it lives on the `trade_pass_reasons` row, SPEC §3.4) and never a reason code — that is `trade_pass_layer1.reason`'s job, and duplicating it would let the two disagree. |
| `prompt_deferred` | `surface` | `InterruptSurface` enum | Identical to `prompt_shown.surface` — the granted and refused halves must slice the same way. |
| | `blocked_by` | the literal `tour`, else the holding `InterruptSurface` | "The tour ate my prompt" is legible instead of looking like ordinary slot contention. |
| `calc_trade_queued` | `queued` | bool | Did the server record the package as a like. The **refusal rate is the point**: a merged calculator whose ✓ mostly refuses is a canvas users are building against preferences the app never showed them. |
| | `reason` | present **only** on `queued: false` — `likes_you_off` \| `not_league_member` \| `assets_not_on_roster` \| `opponent_untouchable` \| `opponent_not_interested` \| `fails_fairness_floor`, plus the client-only `error` | The six are `server.CALC_QUEUE_REASONS`, a closed cross-client enum. `error` is the client's own value for a request that never got an answer, and it exists so a network failure cannot masquerade as a product refusal. **NOT the server's `detail` string** — that is free text and can name player ids; admitting it would put unbounded cardinality and player names into a props column. |

**No `platform` prop anywhere in this batch.** Device platform is a
`user_events` **column** derived server-side at ingest (the NULL-`platform`
incident); the decline-reason family is the one operator-approved exception and
this batch does not inherit it. `league_id` rides the envelope column as
always. No player ids, no names, no free text.

## Intent classification — the DAU seam

`INTENT_EVENTS` is derived by **subtraction** in `analytics_queries.py`, so
taxonomy growth is intent-by-default: a passive name registered without its
`NON_INTENT_EVENTS` row step-changes DAU/WAU on ship day, silently and
permanently. Six of the thirteen are classified non-intent **in the same
commit**:

- **`calc_tour_started`** — the load-bearing one. The tour **auto-starts on
  landing**, so this is a mount counter for a primary surface (the
  `trio_session_started` precedent). Admitting it would make DAU ≈
  calculator-visit count from ship day.
- **`calc_tour_ended`** — a terminator, the `league_team_closed` /
  `team_review_exited` class; every end is preceded by its own start.
- **`calc_tour_beat_missing`** — a script-defect diagnostic. Nothing the user
  did, and nothing they were shown.
- **`trade_pass_overlay_opened`** — an **exposure** of the capture surface, not
  the decision it collects. `trade_pass_layer1` / `trade_pass_layer2` carry
  that and stay intent; an overlay opened and dismissed without a choice is
  precisely a non-conversion, and crediting it a user-day would repeat the
  `rankings_preset_detected` mistake. It opens no blind spot: every emission is
  preceded on the same card by `trade_card_viewed`, which is intent.
- **`trade_pass_overlay_dismissed`** — a dismissal, the
  `apple_banner_dismissed` class.
- **`prompt_deferred`** — a **system refusal**, the exact peer of
  `guide_step_suppressed`. Its granted twin `prompt_shown` is already
  non-intent, and the two halves must not straddle the line.

The other seven stay **intent** deliberately: two configuration changes
(`calc_mode_switched`, `calc_include_players_toggled` — the
`league_basis_changed` / `stud_tax_mode_changed` peers), the calculator's core
gesture (`calc_asset_added`), a deliberate destructive action whose undo
`calc_clear_undone` is already intent (`calc_cleared`), the hand-off tap that
is the merge's conversion moment (`calc_find_a_trade_tapped`), and two deck
actions reachable only from a deck the user asked for
(`deck_back_to_calculator` — the `trade_edit_in_calculator_tapped` peer;
`deck_unpin_retry` — the `find_trades_tapped{source: deck_error_retry}` peer).
None opens a DAU seam: each fires behind an intent event that already counts
the user that day.

**W6-A adds an eighth intent name, `calc_trade_queued`.** It is the one that
looks like it might belong in the deny-list, because it fires on a refusal too
— so, explicitly: the **tap** is the user's decision to offer the trade (the
`sleeper_send_attempted` class), and the server's `queued: false` is the answer
to that decision, not something shown to them unbidden (which is what makes
`prompt_deferred` non-intent). It also cannot open a DAU seam: the ✓ is
unreachable without a filled canvas, so `calc_asset_added` has already counted
the user that day.

## Deliberate omissions

- **`FUNNEL_CRITICAL` is unchanged.** That set is the SDK's drop-**last**
  policy under queue overflow, hand-mirrored in `mobile/src/api/events.ts`.
  None of these is a pre-auth funnel primitive, and a tour that fires
  fourteen rows in a minute is exactly the traffic that should be shed first.
- **`SERVER_FIRED_EVENTS` is unchanged.** Every name here is a client-side
  intent/exposure signal the server cannot see; the durable server truth for a
  pass is still the `trade_pass_reasons` row plus `deck_outcomes`, and for an
  evaluation still `calc_trade_evaluated`.
- **`calc_find_a_trade_tapped` is a new name, not a `source` value on
  `find_trades_tapped`.** The two do not double-count one tap: the
  calculator's control navigates to `TradesHome` and `TradesScreen` fires
  `find_trades_tapped` only from its own controls, never on mount. A separate
  name because the props are the *calculator's* state — meaningless on the
  deck's emitter, and folding them in would hollow out its two-prop row.
- **No `calc_opened`.** Tracking plan v2 §S3 reserved that name and nothing
  ever fired it; `screen_viewed{screen: TradeCalculator}` already covers the
  mount, and minting a second one would be the #208/#248/#293 bug class.
- **`calc_trade_queued` carries no `opponent_user_id` and no asset ids.** The
  question the event answers is "does the ✓ work, and when it does not, whose
  preference stopped it" — a six-value enum answers that. Who and what would
  make it a per-trade log, which is what `trade_decisions` already is.
- **The tour's per-beat `adoptionEvent`s** (`analystScript.ts`) point at
  registered names only. The pre-#384 script referenced `trade_card_swap`,
  `send_attempted` and `trade_disposition`, none of which exist in any
  registry; the calculator agent switches those to registered names in the
  same change. **A beat pointing at an unregistered name is not an error —
  it is an adoption metric that silently never resolves.**

## Verification

`backend/tests/test_analytics_taxonomy_384.py` — 11 tests: allowlist
membership, exact prop rows (asserted `==`, not `<=`), no device-platform
prop, no duplicate of a shipped name, the full intent/non-intent split, the
tour-start DAU argument, and an ingest round-trip proving each name lands with
every prop and that `prompt_deferred` is no longer counted in
`dropped_unknown_type` (with an unregistered-sibling control, so `dropped == 0`
is evidence rather than a tautology).
