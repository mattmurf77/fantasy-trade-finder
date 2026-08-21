# DECISIONS.md draft — D-147

> Paste into `living-memory/DECISIONS.md` at merge, and apply the Q-026 closure +
> new Q-027 below into `living-memory/OPEN_QUESTIONS.md`.
>
> **ID ritual (G-048):** `grep "^## D-1" living-memory/DECISIONS.md | tail` → max is **D-146**.
> Second grep across `living-memory/` + `docs/` (tracked and untracked) for `D-14[5-9]`
> → the only hits outside DECISIONS.md are this branch's own docs and
> `docs/plans/package-benchmark-sweetener/decisions-draft-arm-c.md`, whose D-145/D-146
> are already landed. **D-147 is free.**

---

## D-147 — One Pick, One Price: Every League Surface Reads the Engine's Waterfall

**Date:** 2026-08-21 ([scope](../../plans/league-pick-value-alignment/scope.md)); **closes [Q-026](OPEN_QUESTIONS.md) in full**; opens [Q-027](OPEN_QUESTIONS.md)

**Operator ruling.** *"I want the league values to reflect the same pick values.. But let's defer that until after finishing this one."* The deferral expired when the per-slot ship merged as PR [#167](https://github.com/mattmurf77/fantasy-trade-finder/pull/167) → `main` `3192d13`. This was a sequenced commitment, never an open question.

**The disagreement it ends.** [D-146](DECISIONS.md) put the three-step waterfall into the ENGINE and knowingly left two league surfaces on the stored `draft_picks.pool_value` (slot-pricing scope §6 waiver 2). Dark, that was invisible. Live under per-slot pricing it was stark: a **2026 1.01 read 2117.0 on the Power Rankings screen and 4867.1 inside a trade card** — 2.3×, about the single most valuable asset a team can hold, and it badged differently on each screen because a badge follows the value it is served (D-320-2).

**Decision.** Every site that displays or aggregates an owned pick's value calls **one** helper:

```python
def _priced_pick_value(p, slot_order, scoring_format) -> float:
    return priced_pool_value(p, scoring_format=scoring_format,
                             slot=pick_slots.slot_for(slot_order, p.get("season"),
                                                      p.get("round"),
                                                      p.get("original_roster_id")))
```

Five call sites, no sixth — `_roster_eveners`, `_trade_evaluate_impl`, `get_league_picks`, `_owned_pick_assets`, `_power_picks_by_owner`. Two of those were already priced (D-146) and were refactored onto the seam without behaviour change; three were genuinely aligned.

**The helper is the decision, not an implementation detail.** The five sites had been drifting *because* each held its own copy of one expression. Extracting the seam makes "the same waterfall with the same slot resolution" a structural property, guarded by a bidirectional AST walk (`test_league_pick_value_alignment.py`): one test asserts `priced_pool_value` is reached from exactly one function, another that the seam's callers are exactly the five. **Sabotage-verified three ways**, including one sabotage that is *behaviourally identical* (inlining the same expression at a call site) — it still fails, which is the point.

**Three surfaces moved, and one of them was a real defect.**

- **`GET /api/league/picks`** — `pool_value` on the wire is now the priced value, and `tier` follows it. No client change: `mobile/src/components/InLeagueCalculator.tsx:233` already read `p.pool_value` as its base.
- **`_power_picks_by_owner`** (Power Rankings + the ADR-011 history snapshot).
- **`_roster_eveners`** — **a defect, not merely an inconsistency.** Both call sites live inside `_trade_evaluate_impl`, whose `gap` is computed from priced picks, while the candidates were sized against the stored ladder. A one-tap "add their 2026 1.01" was offered as closing a 2117.0 hole the same response charged 4867.1 for.

**Badges move, and that is the ruling working.** The bands are byte-identical (`tier_config.json` + five client mirrors untouched) and so is the inverse (`value_to_elo`, D-088). Measured on a 12-team 2026–2028 grid: **50 of 96 picks re-band** — the 1.01 up to `firsts_2`, the 1.08–1.12 down to `second`, all twelve 2026 thirds and fourths down a band, and all twelve 2028 firsts from `first_1` to `second`.

**The number the operator will actually notice: Power Rankings totals DEFLATE.** Per-roster pick capital moves **+12.4 % (the roster picking 1.01) to −40.3 % (1.12), monotonically by slot, and −22.1 % league-wide.** The dispersion story is true *within* 2026 round 1; across a whole roster the round curve dominates, because DP decays future firsts hard (2028 1st: 2117.0 → 1263.0) where D-079's ladder held every first flat. These are the engine's prices as of `3192d13` — this decision does not create them, it stops one screen from disagreeing with them.

**Named consequence: an ADR-011 time-series boundary at this merge.** `roster_history.team_value` / `team_value_picks` are fed by `_power_picks_by_owner`, so the series steps here and is not comparable across the date for a pick-holding team; the Wrapped/recap and trends consumers read across it. **Nothing historical is recomputed**, and that is verified rather than argued: `roster_history` has no pricing path of its own — it is handed `picks_by_owner` and stores it — pinned by a test asserting the module contains no `priced_pool_value`, no `_priced_pick_value` and no `pick_pool_value` call.

**What did NOT move.** `GENERIC_PICK_SEEDS`, the tier ladder, the tier BANDS, `tier_config.json`, `pick_pool_value` itself, and `draft_picks.pool_value` (still sync-written, still never rewritten — it is explicitly the waterfall's step 3 and the entire safety net when DP is unreachable). No schema change, no flag change, no client change (`git diff origin/main -- mobile web extension` = zero files).

**Deliberately NOT aligned, and this needs a call — the pick-SHARE ratios.** `_user_pick_share` and the trade job's opponent shares sum the legacy `pick_value` column into a 0–1 ratio feeding the contend/rebuild classifier. Left alone because (a) nothing displays it — it is an inference input, not a surface; (b) aligning it changes which decks get generated, a behaviour change nobody commissioned and one the golden set cannot catch (arm A builds no `draft_picks` rows); (c) it reads a different column on a scale already documented as not client-facing. **Operator-visible consequence:** the app's guess at whether you are contending still counts every 2026 first as the same asset. Scope §6 waiver 3.

**Rejected: fixing the non-12-team board/engine mismatch here.** DP publishes one 12-team curve; the Draft Room maps smaller leagues onto it by percentile (`_basis_slot`) and `market_pick_slot_value` does not, so a 10-team league's last first *displays* as the 1.12 (820.8) and *prices* as the 1.10 (1069.8). Rejected because the fix reprices the ENGINE in every non-12-team league — outside a ruling about aligning surfaces to the engine. Pinned by a test that asserts both mappings and the exact gap, and raised as **Q-027**.

**Rejected: giving `/api/league/picks` a new key and leaving `pool_value` stored.** It would have kept the two numbers visible side by side and needed a five-client migration to decide which one to render — i.e. it would have shipped the disagreement into the clients instead of ending it.

**Evidence.** Golden set run **in isolation before any fixture was touched, and again after**: 29 tests / 156 assertions across four golden files, **zero edits, both times**; arm A's immunity verified rather than assumed. Full suite **3986 passed, 1 skipped** (baseline 3969). Three test files re-derived from the pricing functions with literal inputs, **no tolerance widened**; `test_league_picks_tier.py` grew 7 → 12 and re-verified all three of its original sabotages against the new prices, adding a fourth. One fixture had to be *reshaped* rather than renumbered: D-084's "one 3rd separates the literal and dollar label scales" trap collapsed under the new prices (both scales now round to ≈0.5 firsts), so `_PICKS_306` was re-derived to three thirds, which restores the divergence — the file explains why two would not do.

**Status:** Draft — pending operator ratification of scope §6 waivers 1 (the `picks.slot_labels` lever is now app-wide), 2 (Q-027) and 3 (pick shares).

---

## OPEN_QUESTIONS.md — apply at merge

### Q-026 — replace the RULED-DEFERRED block with:

**CLOSED 2026-08-21 by [D-147](DECISIONS.md)** (PR pending). `_power_picks_by_owner`, `GET /api/league/picks` and `_roster_eveners` now price through `server._priced_pick_value` — the same `priced_pool_value` waterfall and the same D-090 resolution the engine uses — guarded bidirectionally by an AST walk over the five known call sites. The 1.01's 2117.0-vs-4867.1 split is gone. `test_league_picks_tier.py` re-derived (7 → 12 tests, badges moved as designed); Power Rankings pick totals move +12.4 % to −40.3 % by draft slot, −22.1 % league-wide, and `roster_history` steps at the merge (an ADR-011 boundary, append-only, nothing recomputed). Two residues, both raised rather than buried: pick-SHARE ratios stay on the legacy scale (scope §6 waiver 3) and the non-12-team board/engine mismatch became **Q-027**.

### Q-027 — new entry:

**Q-027 — The Draft Room board and the engine map non-12-team leagues onto DP's curve differently**

**Raised:** 2026-08-21 (D-147 / league-pick-value-alignment scope §6 waiver 2). DynastyProcess publishes exactly one 12-team slot curve. `draft_board_service._basis_slot` maps a smaller league onto it by percentile within the round (plan O3, ends anchored), so a 10-team league's last first displays as the **1.12 → 820.8**. `pick_values.market_pick_slot_value` has no league size and looks the slot number up literally, so the same pick prices as the **1.10 → 1069.8** — a 30 % disagreement between a league's own board and its own trade cards. The mirror case: a 14-team league's 1.13/1.14 have no DP row, fall to the round curve (1859.5), and therefore price *above* that league's 1.12.

Pre-D-147 this lived only in the engine; D-147 spread it to Power Rankings, `/api/league/picks` and the eveners, which is why it is now worth a decision. Pinned by `test_league_pick_value_alignment.py::test_non_twelve_team_boards_disagree_and_that_is_pinned_not_fixed` so neither mapping can drift silently.

**Options:** (a) route `market_pick_slot_value` through `_basis_slot` — needs league size threaded into `priced_pool_value`, and reprices the engine in every non-12-team league; (b) drop `_basis_slot` and map the board literally — cheaper, but prices a 10-team league's last first as if four more teams existed; (c) accept — a 12-team curve on a 10-team league is an approximation either way, and the board already flags itself `slot_value_approx`. **Needs an operator call.** 12-team leagues are exact under all three.
