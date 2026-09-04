# Manual TestFlight checklist — personal-market policy

**Written:** 2026-09-04 · **Run:** not yet · **Scope block:** [scope.md](scope.md)

Under D-056 this is the **only runtime evidence mobile gets**, so it is written to catch
a regression rather than to demonstrate a happy path.

**Not required to merge this branch** — both flags default off, so there is no runtime
behavior to verify. **Required before `trade.valuation_telemetry` is turned on in
production**, and again before `trade.personal_market_policy_v1` is.

Every production query below is `SELECT`-only inside a read-only transaction; use
`backend/tools/prod_analytics.py`, which forces `default_transaction_read_only=on` and a
statement timeout. Never print the URL, never commit output containing user data, and
hash user/league ids in anything written down.

---

## Stage A — telemetry only (`trade.valuation_telemetry` ON, policy OFF)

Precondition: the deploy has run `_migrate_db()` (check that `deck_impressions` has
`valuation_json`).

| # | Step | Expected |
|---|---|---|
| A1 | Open Acquire in a real league with at least one boarded league-mate. Pull a fresh deck. | Deck appears exactly as before — **same cards, same order, same count**. This is the whole claim of the stage: telemetry changes nothing a user can see. |
| A2 | Note the number of cards and the top card's players. Force-regenerate. | Behaviour unchanged from before the flag flip. |
| A3 | Query `deck_impressions` for that `deck_job_id`. | Every row has non-null `valuation_json`, `trade_concept_id` and `policy_variant = 'legacy'`. |
| A4 | Parse one row's `valuation_json`. | `schema_version` 1; `assets.give` / `assets.receive` ids and order **exactly** match the row's `assets_json`; `market.ratio` within 0.001 of the row's stored `fairness_score` for a card whose fairness came from the point ratio. |
| A5 | Find a card whose counterparty has a real board. | `partner_board.source = "personal"`, `package_confidence` non-null and **> 0** — this is the proof that persisted opponent confidence actually reaches generation, which is the entire schema change. |
| A6 | Find a card against a never-ranked league-mate. | `partner_board.source = "consensus"` and every partner personal/confidence field **null** — not a copy of consensus. |
| A7 | Swipe one card **like**. | A `trade_decisions` row with a non-null `impression_id` and `trade_concept_id`. |
| A8 | Have a second tester like the mirror of that concept in the same league. | A `trade_matches` row carrying both impression ids, `first_like_at`, `second_like_at`, a sane `match_latency_seconds`, and a `match_valuation_json` with `snapshot_stage: "match"`. |
| A9 | Confirm the two impressions share one `trade_concept_id`. | Identical string from both perspectives. **If this fails, mirrored-card attribution is broken and nothing downstream can be trusted.** |
| A10 | Send a trade from a card via Sleeper (or MFL/ESPN). Let it succeed. | Exactly **one** `trade_proposals` row: `impression_id` set, `edited_from_source = 0`, `origin_trade_hash == final_trade_hash`, `valuation_json` present with `snapshot_stage: "proposal"`. Also exactly one impression-linked `propose` `deck_outcomes` row. |
| A11 | Open a card, **edit the package** (swap or add a piece), then send. | One `trade_proposals` row with `edited_from_source = 1`, `origin_trade_hash != final_trade_hash`, `give_asset_ids` / `receive_asset_ids` matching **what was sent**, and a snapshot recalculated from the final package — *not* a copy of the impression's. |
| A12 | Attempt a send that the provider rejects (e.g. a stale roster). | **No** `trade_proposals` row and **no** `propose` outcome. An attempted send is not a proposal. |
| A13 | Send the same trade twice in quick succession (double-tap), if the client allows. | Still exactly one `trade_proposals` row — `proposal_event_id` is minted before the provider call for precisely this case. |
| A14 | Check `trades_generated.gen_ms` across ~10 jobs against the pre-flip baseline. | p95 up by no more than **5%**. |
| A15 | Read `trade_policy.HEALTH` (server log / admin health). | `asset_mismatches` = 0. Any non-zero value here means a snapshot was built from a different package than the one served — stop and investigate before trusting a readout. |

**Stage A blocker (from the brief):** a successful controlled TestFlight proposal that
fails to produce an owned, non-stale impression-linked row is a **release blocker**, not
a follow-up.

**Also verify while here:** the previously observed duplicate-`pass` emission. Swipe a
card to pass via the decline-reason tile and confirm exactly one live `pass` row on that
impression.

## Stage B — the treatment (`trade.personal_market_policy_v1` ON)

Do **not** run Stage B until Stage A's coverage bar (≥99% parseable snapshots) is met.

| # | Step | Expected |
|---|---|---|
| B1 | Pull a fresh deck. | The first **three** cards are `core` (`valuation_json.policy.eligibility_lane`). |
| B2 | Count lanes across the deck. | At most **two** `conviction`; Core at least 70% of the realized deck length. |
| B3 | Check the minimum market ratio served. | No card below `market_floor_absolute` (0.65 at ship). |
| B4 | Turn the fairness preference **on** (stricter) and regenerate. | The deck gets **smaller or equal**, never larger, and every served card's `effective_floor` is at least the requested value. This is the `min` → `max` correction; if the deck grows, the composition is still wrong. |
| B5 | Query `trade_policy_shadow` for the job. | Rejections recorded with `model_arm`, `reason`, `market_ratio` and `effective_floor`. An empty table on a job that served fewer cards than it generated means rejections are being lost from the denominator. |
| B6 | Confirm `policy_variant` on the served rows. | `personal_market_v1` on **every** row of the deck — a deck must never mix variants. |
| B7 | Compare deck size against a legacy job for the same league. | Empty-deck rate up by no more than **2 percentage points**; cards-per-job down by no more than 10%. |
| B8 | Open a Conviction card. | It visibly states that the trade involves a market premium, and shows no opponent value, ranking position or comparison count. |
| B9 | Check the explore control's copy. | It does **not** promise that fairness is disabled. "Explore ranking edges" or equivalent — the guardrail is never actually off. |

## Rollback

Deploy-free, in order of bluntness:

1. `trade.personal_market_policy_v1` → false, `POST /api/feature-flags/reload`.
2. Raise `market_floor_absolute` / `market_floor_two_board_base` toward 1.0 via
   `PUT /api/admin/config/<key>` to make the treatment conservative without turning it off.
3. `trade.valuation_telemetry` → false — stops every additive write.
4. Revert the commit.

Nothing persisted needs cleanup: every new column is nullable and every new table is
append-only telemetry.
