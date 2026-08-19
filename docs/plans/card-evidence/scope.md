# Feature Scope — Card evidence (“would this close?”)

**Date:** 2026-08-19
**Entry point:** direct ask (operator: RA/MDV research → “where would those flow” → “write a PRD for these features”)
**Builder:** unassigned — EM tasks from [PRD.md](PRD.md)
**Operator sign-off on waivers:** needed on §1 for Wave 1 (existing events) and §3 mobile structural guards (E1 copy). Wave 2–3 are user-visible and not waived.

Parent: [PRD.md](PRD.md). Does **not** change generation math ([landability-challenger](../landability-challenger/PRD.md)).

---

## 0. What this builds

Presentment around cards the live engine already emits: honest verdict copy (E1), both-team impact (E2), you-vs-market sentence on divergence cards (E3), received-offer analyzer V1 (E4), scored league trade history (E5), this-league comps strip (E6).

What it is not: a new finder, a RA Elo ingest, an MDV VORP ranker, a Sleeper-wide Tradabase, pending-offer auto-inbox, or 1y/3y projections.

---

## 1. Analytics scope

- [x] **(b) Existing events cover Wave 1.** Deck impressions/outcomes already key a card. New payload fields (`verdict.band`, `impact`, `diff_highlights`) ride `features_json` / the card blob already stored. Questions:

  | Question | Field |
  |---|---|
  | did honest copy change like-rate? | `deck_outcomes.action` × `fairness_score` / new `verdict.band` (stamp band onto `features_json` when E1 ships) |
  | did impact change like-rate? | same, split by `trade.impact_preview` on/off |
  | inbound analyzer used? | new event only if E4 ships — see (a) below |

- [ ] **(a) New events, Wave 2–3 only:**

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `offer_analyzed` | league_id, counterpart_id, fairness, band, asset_counts | V1 analysis completes | mobile, web |
  | `offer_disposition_marked` | analysis_id, accepted\|declined\|countered | user marks E4 | mobile, web |
  | `trade_history_opened` | league_id, row_count | E5 feed viewed | mobile, web |
  | `comps_strip_tapped` | trade_id, n_comps | E6 expand | mobile, web |

  E4/E5/E6 do not ship without these.

## 2. Schema & flag scope

- New/changed tables:
  - E4: `offer_analyses` (id, user_id, league_id, counterpart_id, give_json, receive_json, card_json, created_at, disposition nullable). Migration required.
  - E5: additive columns on `sleeper_trades` **or** a sibling `sleeper_trade_scores` (transaction_id, scored_at, give_value, receive_value, fairness, band, payload_json). Prefer sibling so capture stays append-only (market-data-readiness invariant).
  - E1–E3: **no** new tables. Card JSON only.
- New flags / knobs: see PRD §7. All listed in `config/features.json` + `FLAG_KEYS` + `docs/config-reference.md` at merge of the ticket that introduces them.
- `offers.inbox_auto` stays false. `tiers.community_diff` not flipped. `market.trade_capture` already true — do not turn it off.
- Rollback: every user-visible layer is a flag. E1’s copy floor is also `verdict_even_min_ratio`.

## 3. Evidence scope

- [x] **Structural guard (E1):** `mobile/tests/check-honest-verdict.js` — asserts “balanced” / “Fair-value idea” as a fairness claim cannot render when `verdict.band !== 'even'`. Add `npm run test:honest-verdict`. Web: equivalent string guard or a pytest on the copy matrix helper if copy is server-driven.
- [x] **Unit tests:**
  - E1: `_value_verdict_payload` + new band helper; 0.58 → not even; 0.80 → even.
  - E2: fixture roster pair; impact ranks move; flag-off omits key (`test_impact_preview.py`).
  - E3: divergence vs consensus cards; shrink-to-zero hides chip.
  - E5: scoring idempotent on `transaction_id`; does not mutate `sleeper_trades.raw`.
- [x] **Code-walk proof:** E2 “after top-K only” — file:line in TEST_LEDGER. E1 “no client-side band math.”
- [ ] **TestFlight checklist (Wave 1):** (1) card at fairness ~0.58 does not say balanced; (2) impact strip present with flag on, gone with flag off; (3) one divergence card shows a named player chip, one consensus card does not.
- `testID`s: `trade-verdict-band`, `trade-impact-strip`, `trade-diff-chip`, `offer-analyzer-entry`, `league-trade-history` — lint via existing script.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | yes at each ticket | card shape; E4 routes; E5 feed |
| `living-memory/LLD.md` | n/a | no convention shift |
| `docs/architecture.md` | E5 | sleeper_trades → scores → UI |
| `living-memory/HLD.md` | n/a | presentment, not new module family |
| `docs/cross-client-invariants.md` | E1 | copy matrix; forbidden strings |
| `docs/glossary.md` | yes | verdict.band, impact, comps strip |
| ADR / DECISIONS.md | at Wave 1 merge | D-093 (proposed): evidence annotates, does not generate |
| `docs/config-reference.md` | each flag | PRD §7 |
| `docs/data-dictionary.md` | E4, E5 | new table / sibling scores |
| parent top20 specs | n/a | this PRD sequences them; do not rewrite #5/#6/#9/#11 |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (includes new `check-honest-verdict.js`) on the pushed sha.
- **Evidence recorded:** TEST_LEDGER per ticket.
- **TestFlight:** Wave 1 checklist in §3, operator-run.
- Express lane: **no.**
- **Generation math:** any diff under `_generate_trades_v2` / `_generate_consensus_for_pair` / `_shrink_user_elo` / `_tier_mult_v2` is **out of scope** and fails review.

## 6. Open operator decisions

1. E1 default ON (copy bug) vs dark-then-flip? PRD recommends ON.
2. E6 under `league.trade_history` or a child flag? PRD allows either; pick at E6 start.
3. Personal-Elo impact (you-view vs consensus-view) is #5’s open question; this PRD says consensus-only v1. Confirm.
