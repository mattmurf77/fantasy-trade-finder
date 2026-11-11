# Feature Scope — Engine revision 4 (`owner-v2-bilateral-4`) and its Calibration arm

**Date:** 2026-11-10
**Entry point:** direct operator ask, offer-learnings plan §3 WS1 (R1, R4, R5, R6). The plan
lives on the coordinator's branch (`docs/plans/offer-learnings/plan.md`); evidence in
`docs/plans/realtime-trade-engine/offer-history.md` there.
**Builder:** WS1 builder agent, branch `feat/bilateral-revision-4`
**Operator sign-off on waivers:** waivers below are backend-only (no mobile change); one open
operator decision on Calibration coverage (§6).

---

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** revision 4 ships dark behind its own
  selector and Calibration already records per-card arm attribution, grades and tags. Every
  served card already carries `generator_version` in `deck_impressions.valuation_json`, which
  distinguishes `owner-v2-bilateral-4` if it is ever served. No new event.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. Calibration's existing `grading_sessions.source_json`
  gains `extra_arms` and `counts_json.arms["owner-v2-bilateral-4"]` (with `role: "additive"`)
  only when the new flag is on; `grading_cards.arms_json` may carry a `revision_4` key. Data
  dictionary note added.
- New `model_config` key: **`owner_bilateral_revision_4_enabled`**, default **0** (DB seed and
  `trade_service._DEFAULT_CFG`). Exactly 1 selects revision 4, only while
  `owner_bilateral_enabled=1` and `owner_bilateral_revision_enabled=1`; it wins over
  `owner_outlook_evidence_enabled`. Any other value leaves today's selection and bytes.
  Rollback lever: set it to 0 via `PUT /api/admin/config/owner_bilateral_revision_4_enabled`.
- New feature flag: **`grading.revision4_arm`**, default **false** (`feature_flags.py`,
  `config/features.json`, the three flag fixtures that mirror `grading.outlook_prepare`).
  Graduation: none; it is a measuring tool, turned off when the operator has read the report.

## 3. Evidence scope

- [ ] **Structural guard:** WAIVED, no mobile change. Old and new binaries ignore extra arm keys
  in results (`mobile/src/components/GradingResults.tsx` renders `current`/`value_core` only).
- [x] **Unit tests:** `backend/tests/test_bilateral_revision_4.py` (71),
  `test_bilateral_revision_4_routes.py` (4), `test_calibration_revision_4.py` (10); arm-A
  golden inventory gained the knob. Sabotage names in TEST_LEDGER.
- [x] **Code-walk proof:** §7 below.
- [ ] **Manual TestFlight checklist:** WAIVED for the engine (dark, not served). For the
  Calibration arm, after the operator steps in §6: (1) open Calibration on a league whose deck
  was unexposed; expect a deck of the paired size plus up to 20 more cards, no labels on any
  card. (2) Grade to the end; results show Today's / New engine as before (the revision-4 arm
  is admin-report only). (3) A league already started before the switch keeps its exact deck
  and answers.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | Calibration round: additive arm in results/report |
| `living-memory/LLD.md` | updated | Revision-4 proof contract and additive-arm convention |
| `docs/architecture.md` | updated | "Bilateral revision 4" section |
| `living-memory/HLD.md` | updated | 2026-11-10 entry |
| `docs/cross-client-invariants.md` | n/a because no client constant changes; results keep their two wire aliases |
| `docs/glossary.md` | updated | Owned-pick premium, Best-asset rule, Additive Calibration arm |
| ADR or `DECISIONS.md` | updated | ADR-028 + `D-NEXT` |
| `docs/config-reference.md` | updated | selector paragraph + flag row |
| `docs/data-dictionary.md` | updated | grading_sessions JSON note |

## 5. Ship gate declaration

- CI green on the integrated tree (coordinator). `test_deck_pipeline_digest` is **red by
  design** on this branch: `_run_trade_job` passes revision 4's version to presentment and
  `_owner_selected_assignment` pops the dark knob. `DECK_PIPELINE_VERSION` not bumped; the
  coordinator pins one bump for the integrated tree.
- Evidence recorded in `living-memory/TEST_LEDGER.md`.
- Express lane declared: no.

## 6. What revision 4 does (precise)

All three rules act on support scores, the quantities the ranker and presentment read. None
touches `utility` (eligibility), `market_gain_fraction`, the priced package, the market floor
or the overpay gate, so the inventory of eligible offers equals revision 2's; only the order
changes (pinned by test on six worlds).

**R4 Owned-pick premium.** For the other manager's side only. Let `rate` = table below on the
other team's resolved outlook (`team["outlook"]` after `trade_gen_owner._OUTLOOKS`
normalization: declared, caller-supplied inferred, or the engine's own roster inference, the
same value every other outlook rule uses; its source is recorded). Picks = the picks in the
viewer's receive (all held by the other manager). `premium = rate × Σ market(pick)`.
Their package-priced outgoing value becomes `outgoing + premium`;
`gain' = (incoming − outgoing − premium) / max(incoming, outgoing + premium)`;
`market_acceptability' = clip(.5 + .5·gain'/tolerance, 0, 1)` with revision 2's
`tolerance = max(1 − floor, .05)`; their support moves by
`.35 × (market_acceptability' − market_acceptability)` (the existing weight).

| Other team's outlook | Premium |
|---|---|
| `jets` (tanking, incl. `tanking`) | 20% |
| `rebuilder` | 20% |
| `not_sure` | 10% |
| `contender`, `championship` (incl. `all_in`) | 0 |
| anything else / missing | 0 |

The viewer's own picks are never marked up.

**R1 Pay-picks tie-breaker.** Bilateral-1's ranker picks, inside a 32-card lookahead, among
offers whose weaker support is within `.025` (`_QUALITY_TOLERANCE`) and total support within
`.05` of the leader; it chooses the least-used identity, then the earliest. Revision 4 inserts
one key between those two: `pays_picks` (viewer sends a pick, receives no pick) 0,
`players_only`/`picks_both_ways` 1, `asks_picks` 2. The comparable set is unchanged, so the
key cannot promote anything outside the existing tolerance. The tolerance is revision 1's own
`_QUALITY_TOLERANCE`; nothing new was tuned. Term precedence (revision 2) then applies as
before.

**R5 Best-asset rule.** Fires when the viewer receives fewer assets than they send, the
viewer's receive holds the trade's most valuable asset (raw market), and every asset the
viewer sends is worth less. Exception: every asset sent is a pick and the other team is
`rebuilder` or `jets`. When it fires, both managers' support scores drop by
`BEST_ASSET_DEMOTION = 4 × .025 = .10` (so weaker support drops .10 and total .20). Demote,
never delete: the offer stays eligible and in the inventory.

**R6 Size.** Organic offers stay 1×1, 1×2 or 2×1 (owner-v1's `organic_shape` gate); pinned by
test, no change.

**Proof** (`data["revision_4"]` in every eligible revision-4 proof): premium rate, the outlook
and its source, the pick ids, raw pick market, premium value, market acceptability before and
after, support delta; best-asset `consolidation_ask`, `fired`, `exception`, best asset ids,
demotion; `pick_direction`; tie-breaker scope. Each side's `support` keeps
`revision_2_score` and `revision_4_adjustments`. The generator report adds a `revision_4`
block with counts, including how often the tie-breaker changed a choice.

**Selector composition.**

| bilateral | revision | outlook (v3) | revision 4 | Served |
|---|---|---|---|---|
| ≠1 | any | any | any | owner-v1 |
| 1 | ≠1 | any | any | bilateral-1 |
| 1 | 1 | ≠1 | ≠1 | bilateral-2 (production today) |
| 1 | 1 | 1 | ≠1 | bilateral-3 |
| 1 | 1 | any | **1** | **bilateral-4** (wins over v3; no v3 input evidence is attached) |

**Fast deck.** The module is `backend/trade_gen_bilateral_r4.py`, not one of the two modules
the coordinator's fast deck accepts, so the fast deck falls back to the full solve for it. The
fallback test belongs with `trade_fast_deck.py` on the coordinator's branch.

**Calibration.** Flag `grading.revision4_arm` (default off). When on, every new
`outlook-v2-v3-1` build runs the paired v2/v3 arms exactly as today, then runs revision 4 on
the same frozen capture through the same gates (`CapturedComparison.run_arm`, which now pins
the revision-4 selector per arm so a serving value of 1 can never turn a paired arm into v4).
Revision 4's top `n` unique trades (`n` = the pair quota, at most 20) are folded in: a trade
already in the deck gains a `revision_4` credit; a new one is inserted at a seeded random slot,
so the paired cards keep their exact relative order, selection and counts. A revision-4 failure
records an error and leaves the paired deck untouched. With the flag on, an open deck that is
unexposed, unanswered and was built without the arm is retired (`comparison_stale`) and
rebuilt on its next start/open or admin pregeneration; exposed, started and completed decks are
never changed.

Operator steps (production; not run by this builder):
1. Deploy with the flag off. The deploy changes the backend code revision, so unexposed ready
   decks already go stale and rebuild as they do after any deploy.
2. Turn on `grading.revision4_arm` (add it to Render's `FTF_FLAGS`, which wins over the file
   (G-076), then `POST /api/feature-flags/reload`).
3. Queue every connected user and linked league, in batches of 100, until `next_offset` is null:
   `curl -X POST "$BASE/api/admin/grading/pregenerate" -H "X-Cron-Secret: $CRON_SECRET" -H 'Content-Type: application/json' -d '{"round_id":"outlook-v2-v3-1","offset":0,"limit":100}'`
   (repeat with each returned `next_offset`). `grading.outlook_round` is already on in
   production, so the serial worker builds; no `grading.outlook_prepare` change is needed.
4. Read `GET /api/admin/grading/report?round_id=outlook-v2-v3-1&include_open=1`: the new
   `additive_arms["owner-v2-bilateral-4"]` and `arm_inventory_totals["owner-v2-bilateral-4"]`.
5. Rollback: flag off. New builds are byte-identical again; decks already holding revision-4
   cards keep them and their answers.

**Operator decision needed.** Decks already exposed (one started at the last readout) and any
completed deck cannot gain revision-4 cards without breaking the round's frozen as-of contract
(their capture no longer matches current inputs: the code revision is part of it). Those pairs
get no revision-4 trades under this design. Options: (a) accept that; (b) a separate round id
(`outlook-v2-v4-1`) for them, which needs round selection by id in start/current (today one
`ROUND_ID`); (c) fold into exposed decks from a fresh capture, labelled as a different as-of
date, which mixes inputs inside one exercise.

**Worth the operator's eye before grading.** As specified, the best-asset rule matches most
2-for-1 consolidations, and at a .10 demotion it nearly removes them from the first 30 (§8).
That is the spec applied literally; a smaller demotion is a one-constant change if the graded
cards show too few consolidations.

## 7. Code walk

- Selector: `backend/bakeoff_runner.py:300` (`owner_revision_4_enabled`), `:315` (v3 yields to
  v4), generator/version/evaluator branches just below.
- Dark bytes: `backend/trade_gen_owner.py:208` pops any non-1 value before the report;
  `backend/server.py:21989` pops it before the request hash; `backend/server.py:8288` adds the
  version to the page safety signature so a v2 page never serves under v4.
- Rules: `backend/trade_gen_bilateral_r4.py:62` `_revision_4` (premium `:77`, best-asset `:85`),
  applied at `:109` before bilateral-1 builds the weaker/total block; version frozen at `:115`.
  Ranker `:140`, tie-break key `:173`, term precedence `:185`.
- Serving: `backend/server.py:14055` hands v4 to `trade_bilateral_presentment.present`;
  `backend/prepared_trade_payload.py` admits the v4 proof identity.
- Calibration: `backend/outlook_calibration_adapter.py:159-170` (v4 accepted, selector pinned
  per arm, no v3 input evidence for v4), `backend/outlook_calibration.py:311-313` (fold after
  the paired order is fixed), `:342` `_fold_revision_4`, `:55` `_missing_requested_arm`;
  `backend/blind_grading.py` `ROUND_EXTRA_ARMS` for summaries.

## 8. Report on recorded production requests

40 of the recorded requests (every sixth by name), revision 2 and revision 4 run on the same
deep-copied inputs in one process per request. Aggregates only.

| Measure | Revision 4 (all rules) | Premium only | Demotion only | Tie-breaker only |
|---|---|---|---|---|
| Requests whose first 30 change | 40 / 40 | 22 | 38 | 36 |
| First-30 cards not in revision 2's first 30 | 560 / 1,200 (median 14 per request) | 120 | 461 | 86 |
| First-30 positions that differ | 1,105 / 1,200 | 411 | 1,009 | 597 |
| Share of first-30 offers asking for the other manager's picks (r2 → r4) | 17.7% → 9.3% | 17.8% → 10.5% | 17.7% → 19.3% | 17.7% → 15.3% |
| Share paying picks for a player (r2 → r4) | 17.7% → 16.2% | 17.8% → 18.3% | 17.5% → 14.0% | 17.4% → 19.2% |

- The eligible inventory was identical to revision 2's in all 40 requests.
- The best-asset rule matches about 460 of revision 2's 1,200 first-30 cards (most 2-for-1
  consolidations); with the demotion on, 8 remain in the first 30. It is the main source of
  churn. Most demoted 2-for-1s that pay picks go down with it, which is why the pays-picks
  share falls slightly overall.
- The premium applied to 18,598 eligible offers across the sample (26 in the final first 30);
  the tie-breaker changed 3,908 choices; the rebuilder/tanker exception covered 507 offers.
- First-30 counterparties: outlooks rebuilder 742, contender 336, not sure 77, championship
  45; source declared 410, inferred 790.
- Revision 2's own first 30 differ slightly between processes (hash seed), hence the small
  spread in the "before" shares across runs.
