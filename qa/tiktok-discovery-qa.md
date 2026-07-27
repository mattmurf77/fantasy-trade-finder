# QA Tracker — TikTok-Discovery Deck Engine (2026-07-26)

Static gates were green at every wave ship (final: pytest 1336 passed / 1 pre-existing skip; tsc
clean; ~150 new tests across 8 suites). **Static tests prove nothing broke; they do not prove the
features work at runtime.** Device rows below are PENDING until verified on a TestFlight build ≥62.

Prod state at close: flags `deck.{signal_v2,replenishment,thompson_v2,fatigue,session_rerank,
taste_vectors,exploration,first_session}` **ON**; `deck.value_model` **DARK** (F8 graduation gate);
F8 harness unflagged. TestFlight: builds 58 (W1), 59 (W2), 60 (W3), 61 (W4), 62 (W5).

## Per-feature device verification

| # | Feature (flag) | Static | Device | Verify on device |
|---|---|---|---|---|
| 1 | F1 Signal spine (`deck.signal_v2`) | ✅ | ⬜ | Swipe a deck; operator: check `deck_impressions` rows have non-null propensity + board fields, `deck_outcomes` join by impression_id, dwell_ms sane (pass < like), served-never-viewed cards have no viewed row |
| 2 | F10 Replenishment (`deck.replenishment`) | ✅ | ⬜ | Finish a deck → "Deck done — N passed · M liked · K proposed" card; See liked → Portfolio; NO auto-regenerate. Wed tick: `deck_replenish_log` row; push only for opt-in users, deep link lands on Trades |
| 3 | F2 Thompson v2 (`deck.thompson_v2`) | ✅ | ⬜ | No visible change expected; operator: deck order varies run-to-run within bounds; junk-shape decks don't spike for new users |
| 4 | F3 Fatigue (`deck.fatigue`) | ✅ | ⬜ | Pass a concept repeatedly → it stops restacking next decks; decline a proposal → near-duplicates vanish + header note "Hiding trades like ones you declined" with working Undo |
| 5 | F4 Session re-rank (`deck.session_rerank`) | ✅ | ⬜ | Like 3 same-archetype cards → later same-archetype cards arrive sooner; the NEXT (peeked) card never swaps mid-thumb; wildcard/retest cards stay put |
| 6 | F5 Taste vectors (`deck.taste_vectors`) | ✅ | ⬜ | Multi-session: repeated pick-heavy likes tilt future decks pick-heavy; a rookie-heavy board tilts a FRESH user's first deck (board prior); untouchables never resurface |
| 7 | F7 Exploration (`deck.exploration`) | ✅ | ⬜ | Every deck ≥8 cards has exactly one "WILDCARD — OUTSIDE YOUR USUAL" chip at position ~5; wildcard is a legit trade (gate-passing), just off-taste |
| 8 | F8 Eval harness (unflagged) | ✅ | ⬜ | Operator: `python3 -m backend.eval.replay --self-check` on prod data once ~2 weeks of impressions accrue → SELF-CHECK PASS; nightly `runs.jsonl` accumulating |
| 9 | F9 First session (`deck.first_session`) | ✅ | ⬜ | Fresh league (or qa_* stage user): first deck ≤10 cards, first 5 simple/high-confidence; after a board edit, next deck shows "Built from your updated board — N players ranked"; adaptation card appears at most once and only when literally true |
| 10 | F6 Value model (`deck.value_model`) | ✅ | 🚫 DARK | Nothing to verify until graduation. Do NOT flip without the F8 gate (see FEATURES.md §10) |

## Cross-feature interaction watch-list

1. **Slot integrity under all layers:** F7 wildcard at slot 5 + F9 first-5 shaping + F4 client
   re-rank + likes-you pins + F3 retest cards — verify no double-placement or lock violation in one
   deck containing all five card classes.
2. **Header stacking:** F9 board-refresh line + F3 suppression note simultaneously (edit board AND
   have an active suppression) — both render, readable, dismissible independently.
3. **F10 completion card vs F9 adaptation moment** in the same first session (small deck): moment
   mid-deck, completion at end, no overlap.
4. **Multiplier stack sanity:** fatigue [0.25,1] × taste [0.7,1.4] × Thompson [0.5,1.5] — operator
   spot-check `final_score` vs `base_score` in deck_impressions stays within the composed bounds.
5. **Old-client mix:** pre-62 builds against the new backend (no impression_id sent) — decisions
   still work via the legacy path; no outcome rows fabricated.
6. **Replenishment × fatigue:** Wednesday pre-gen decks respect fresh suppressions from Tuesday.

## Data-accrual gates (calendar, not code)

- **~2 weeks:** F8 self-check on real data; first meaningful ESS numbers.
- **When ESS ≥ 100 on both metrics:** run F6 refit + replay; walk the graduation checklist.
- **Wednesday after ship:** first replenishment tick — check `deck_replenish_log` + push dedup caps.

## Issue log

| # | Date | Issue | Status |
|---|---|---|---|
| — | | *(none yet — device QA pending)* | |

## Build-time catches (context for QA)

- FLAG_KEYS registration gap: pre-registered `deck.*` config keys were silently ignored until F1's
  agent registered them in `feature_flags.py` (would have made every flip a no-op).
- Analytics taxonomy gap: `deck_card_viewed`/`swipe_undone`/`deck_reranked` were taxonomy-rejected
  (F1's outcome capture unaffected by design; analytics rows now land for F8).
- Legacy `test_deck_ordering.py` pinned to v1 sampler when Wave-2 flags flipped.
- F8 cron counter made conditional (`ran>0`) to preserve daily-tick byte-identity when idle.
