# Feature Scope — Partner activity in engine revision 4 (WS7, R8)

**Date:** 2026-11-10
**Entry point:** direct operator ask, offer-learnings [plan](plan.md) §3 WS7: "Yes, but controlled
via a capability flag. And it should more so be a league specific threshold that's evaluated. If
all managers are active in trading, it shouldn't get applied at all."
**Builder:** WS7 builder agent, branch `feat/partner-activity` (from `feat/offer-learnings`)
**Operator sign-off on waivers:** waivers below are backend-only (no mobile change); the
operator decisions are listed in §8.

---

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** the rule ships dark behind its own flag and
  only inside revision 4, itself dark. Its evidence is the frozen proof
  (`revision_4.partner_activity`) and the generator report (`revision_4.partner_activity`,
  `partner_activity_demoted`), which already reach `deck_impressions.valuation_json` and
  `bakeoff_runs` with every served revision-4 card. No new event.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. New read helper `database.load_manager_trade_counts`
  (`manager_profiles.owner_id`, `n_trades`; indexed on `league_id`). Data dictionary note on
  `manager_profiles` updated (it now has one dark reader).
- New feature flag: **`trade.partner_activity`**, default **false** (`feature_flags.py`
  `FLAG_KEYS`, `config/features.json`, fixtures `release.json`, `onboarding-v2.json`,
  `profiles-on.json`). Acts only while `owner_bilateral_revision_4_enabled` is exactly 1.
  Graduation: graded with revision 4; rollback = flag off (`POST /api/feature-flags/reload` or
  `FTF_FLAGS`).
- New `model_config` keys: **none**. The constants are module constants in
  `trade_gen_bilateral_r4.py` (`PARTNER_ACTIVITY_THRESHOLD_SHARE` 1/3,
  `PARTNER_ACTIVITY_MIN_MEDIAN` 2, `PARTNER_ACTIVITY_MIN_PROFILED_SHARE` .5,
  `PARTNER_ACTIVITY_DEMOTION` .05) and are recorded in every proof.

## 3. Evidence scope

- [ ] **Structural guard:** WAIVED, no mobile change.
- [x] **Unit tests:** `backend/tests/test_partner_activity.py` (26). Sabotage names in TEST_LEDGER.
- [x] **Code-walk proof:** §6 below.
- [ ] **Manual TestFlight checklist:** WAIVED: nothing is shown to users and revision 4 is not
  served. When revision 4 is served with this flag on, the check is server-side (proofs carry
  `partner_activity`), not on the device.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a because no route or response contract changes; the public card dict is unchanged except for order (pinned by test) |
| `living-memory/LLD.md` | updated | "Revision-4 proof and additive-arm conventions": DB-derived generator input only through the owner context, present only when flag and accepting engine are on |
| `docs/architecture.md` | updated | `manager_profiles.py` row: its first (dark) consumer |
| `living-memory/HLD.md` | n/a because no new module, client or major flow; one input added to an existing engine |
| `docs/cross-client-invariants.md` | n/a because no client constant |
| `docs/glossary.md` | updated | Partner activity rule, reluctant trader |
| ADR or `DECISIONS.md` | updated | ADR-029 decision 6 + DECISIONS `D-223` |
| `docs/config-reference.md` | updated | `trade.partner_activity` row |
| `docs/data-dictionary.md` | updated | `manager_profiles`: one dark consumer |

## 5. Ship gate declaration

- CI green on the integrated tree (coordinator). `test_deck_pipeline_digest` is **red by
  design** on this branch: `_owner_generation_context` (in `DECK_PIPELINE_FUNCTIONS`) changed.
  New digest `2eb43a7eb21b0009`. `DECK_PIPELINE_VERSION` not bumped; the coordinator pins one
  bump. The closure test is green (`load_manager_trade_counts` is a `database.py` import, not a
  `server.py` helper).
- Evidence recorded in `living-memory/TEST_LEDGER.md`.
- Express lane declared: no.

## 6. What the rule does (precise), and the code walk

**Input.** `server._owner_generation_context` (`backend/server.py`, the block after the
`context = dict(...)` build): when `FLAGS.trade_partner_activity` and
`_bakeoff.owner_revision_4_enabled(config)`, `context["partner_activity"] =
load_manager_trade_counts(league.league_id)`, a `{owner_id: n_trades}` map. `owner_id` is the
roster's league identity, the same id as `LeagueMember.user_id` and `card.target_user_id`.
`n_trades` counts completed public trades stored under this season's league id, i.e. this
league year. One two-column indexed SELECT per job (about a dozen rows), before
`detached_context` copies the context; no per-card query. Absent otherwise, so every other
engine (which would reject the kwarg) and every flag-off context is unchanged. The key enters
the selected-request hash only when present (a genuinely different input). Calibration
captures pin the revision-4 selector to 0, so they never load it.

**League threshold** (`trade_gen_bilateral_r4._league_activity`, once per search in
`_Search.__init__`): over the engine's managers (`self.teams`: viewer and league-mates),
`profiled` = counts of those with a profile (non-negative ints only).
- fewer than half the managers profiled, or none → `league_history_thin`, nobody flagged;
- median of `profiled` < 2 → `league_median_below_minimum`, nobody flagged;
- else `threshold = median / 3`; flagged = managers **with a profile** whose count ≤ threshold;
  if none → `every_manager_active`, nobody flagged.

**Effect** (`_revision_4`): for an offer to a flagged manager, both support scores drop by
`PARTNER_ACTIVITY_DEMOTION = 2 × _QUALITY_TOLERANCE = .05`, through the same `_shift` as the
other rules (`revision_4_adjustments.partner_activity_demotion`). Never `utility`, market gain,
the package, the floor or the overpay gate, so the inventory is unchanged. Why `.05`: no larger
than the best-asset `.10`, because a one-season trade count is a weaker, noisier signal than
the offer's own shape; and larger than the comparable set (`.025` weaker, `.05` total), so a
flagged offer drops below near-equal ones but not below clearly better ones. Why both sides: the
weaker support falls by the full amount whichever side is weaker, and presentment, which
swaps only when both managers' scores are within `.025`, cannot move it back (WS1's reason).

**Evidence.** With the input present, every eligible revision-4 proof has
`revision_4.partner_activity` = `{managers, managers_with_profile, league_median, threshold,
flagged_managers, applies, reason_not_applied, threshold_share, min_league_median,
min_profiled_share, demotion, counterparty_trades, counterparty_has_profile, fired, source,
scope}`, and `revision_4.rules_version` = `offer-learnings-1+partner-activity-1`. The generator
report's `revision_4` carries the same rules version, `partner_activity_demoted` and the league
summary (counts only, no manager ids). Without the input, proofs and reports are WS1's bytes
(`offer-learnings-1`; goldens computed from WS1's module).

**Privacy.** Completed trades only, from the public transactions payload; never the private
offers read, declines, or anything not public. `trade_card_to_dict` exposes only
`model_arm`/`generator_version` from the proof; a test pins that the public card dict is
identical with and without the rule except for order (and the rank-derived
`composite_score`/`mismatch_score`, which follow position). The proof and the request snapshot
(which carries the league's counts) stay in server-side evidence tables.

**Staleness.** The engine code hash covers `trade_gen_*.py`, so this code is stamped. Flipping
the flag changes every job's request signature (`_trade_request_signature` hashes all flags), so
pages built under the other setting never serve. A profile rebuild, however, marks no stored
first page stale: a completed trade changes rosters (`roster_fp`), so the page falls through
then, but if the profile rebuild lands after the deck rebuilt, the stored page keeps the
previous count's order until its next invalidation (rankings, preferences, board publish,
roster change, deploy, card expiry). Option for the operator: mark the league's pages stale in
`replace_manager_profiles` while the flag is on.

## 7. Report on recorded production requests

Recorded requests in `data/prod-requests/` (247 requests, 13 leagues), revision 4 run without
and with `partner_activity` on deep copies of the same inputs, **in one process per request**.
Aggregates only.

**Counts.** Three of the 13 leagues have their 2026 season in the local public export
(`data/sleeper-export/public/league-trades.json`), so their counts are **real**: completed
trades per manager, built with `manager_profiles.build_league_profiles` from the export's trades
and rosters (6, 15 and 19 completed trades so far this season, 12 teams each). Every recorded
request in those leagues was run (146). For the other 10 leagues the counts are **constructed**:
a seeded draw per manager from production's per-manager decile distribution (design.md §4.1:
0, 1, 1, 2, 2, 3, 5, 6, 10.5), every sixth request (17 requests, 8 leagues).

| Measure | Real counts (3 leagues, 146 req.) | Constructed (8 leagues, 17 req.) |
|---|---|---|
| Leagues with any flagged manager | 2 / 3 (other: median 1, below 2) | 5 / 8 (2 median below 2; 1 everyone active) |
| Flagged managers per applying league | 3, 4 (of 12) | 1, 1, 3, 3, 4 |
| League medians | 1, 2, 3 | 1, 1.5, 2, 2, 2, 2, 3, 4 |
| Eligible inventory identical | 146 / 146 | 17 / 17 |
| Requests whose first 30 change | 119 / 146 (119 of the 124 where it applies) | 10 / 17 |
| First-30 positions that differ | 3,350 / 4,380 | 250 / 510 |
| First-30 cards not in the no-rule first 30 | 1,187 / 4,380 (27%) | 77 / 510 (15%) |
| First-30 cards offered to a flagged manager, before → after | 1,392 → 292 | 66 → 3 |

- In a league where it applies, it moves most of the first page: a flagged manager's offers
  drop `.05` on both scores, which is past the comparable set, so near-equal offers from
  active managers go ahead of them. About four in five first-page offers to flagged managers
  leave the first 30.
- With one season of history the median is low (1–3), so the threshold is a third of a trade
  to one trade: in practice "0 trades" (median 2) or "0–1 trades" (median 3). That flagged 3–4
  of 12 managers in the real leagues. Whether that is "clearly less than their league-mates" is
  the operator's call (§8.2).
- One real league (median 1) and two constructed ones change nothing: the median-of-two floor.
- Revision 4's own output varies between processes (hash seed); every comparison is inside one
  process. Runner: scratchpad `ws7/report.py` (not committed).

## 8. Operator decisions

1. **Calibration.** The revision-4 Calibration arm carries no partner activity (captures pin
   the selector to 0). Should graded revision-4 cards include it? That changes the frozen
   capture (and WS1b's round), so it is not done here.
2. **Starting constants** (1/3 of median, median ≥ 2, half profiled, `.05`) are the spec's
   starting rule, not fitted. With one season of history (median 2 trades per manager in
   production) the median floor of 2 switches the rule off in many leagues; prior seasons
   (manager-profiles open question 2) would make it a stronger signal.
3. **Profile staleness** (§6): accept, or mark pages stale on profile rebuild.
4. **The viewer counts toward the median.** The viewer is one of the league's managers, so
   their own count is included; they are never a counterparty, so they are never demoted.
